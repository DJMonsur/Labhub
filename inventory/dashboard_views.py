"""
inventory/dashboard_views.py

REST API consumed exclusively by the Lab Personnel Dashboard (/dashboard/).
All paths live under /api/dashboard/...

Authentication is NOT enforced yet — role gating will be added in the next
development phase alongside the login system.

Endpoints
─────────
Reference data
  GET  /api/dashboard/item-types/
  GET  /api/dashboard/locations/

Inventory (full CRUD including hidden items)
  GET    /api/dashboard/items/
  POST   /api/dashboard/items/
  PATCH  /api/dashboard/items/<item_id>/
  DELETE /api/dashboard/items/<item_id>/

Borrow requests
  GET   /api/dashboard/requests/         ?status=<filter>
  POST  /api/dashboard/requests/          manual pre-approved entry
  PATCH /api/dashboard/requests/<req_id>/ edit dates / notes / status

Schedule (timeline source)
  GET  /api/dashboard/schedule/           ?year=YYYY&month=MM

Reports
  GET  /api/dashboard/reports/            list saved reports
  POST /api/dashboard/reports/            generate (weekly/daily/monthly/yearly/custom)
  GET  /api/dashboard/reports/<id>/       report detail + data
  GET  /api/dashboard/reports/<id>/export/?format=csv|html

Item restock
  POST /api/dashboard/items/<id>/restock/ add stock + RESTOCK log
"""

import json
import time
import datetime
import os
import django
from functools import wraps
from decimal import Decimal, InvalidOperation

from django.conf          import settings
from django.db            import transaction
from django.db.models     import F
from django.http          import JsonResponse, HttpResponse
from django.utils         import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    Item, ItemType, Location,
    InventoryRecord,
    BorrowRequest, BorrowRequestItem,
    InventoryLog, LimsUser, Report,
)
from .reports import (_period_for, generate_report_data,
                      build_report_title, render_report_html, export_csv)
from .availability import date_capacity
from .units import normalize_unit
def get_active_lims_user(request):
    """Return the legacy LIMS user matching the signed-in Django user."""
    if request.user.is_authenticated and request.user.email:
        lims_user = LimsUser.objects.filter(user_email=request.user.email).first()
        if lims_user:
            return lims_user

    profile = getattr(request.user, 'profile', None)
    role = profile.role if profile else 'student'
    role_to_id = {
        'lab_personnel': 1,
        'it_personnel': 2,
        'teacher': 3,
        'student': 4,
    }
    user_id = role_to_id.get(role, 1)
    try:
        return LimsUser.objects.get(user_id=user_id)
    except LimsUser.DoesNotExist:
        return LimsUser.objects.first()

# ─── Role Decorator ───────────────────────────────────────────────────────────
def dashboard_role_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        profile = getattr(request.user, 'profile', None)
        role = profile.role if profile else None
        if role not in ('lab_personnel', 'it_personnel'):
            return JsonResponse({'error': 'Permission denied. Dashboard access required.'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view



# ─── helpers ──────────────────────────────────────────────────────────────────

def _parse_body(request):
    """Returns (dict, None) on success or (None, JsonResponse) on error."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse({'error': 'Invalid JSON body.'}, status=400)


def _num(value):
    """JSON-safe number: Decimal → plain float. Swallow quirks like '' or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_decimal(value, default=None):
    """Coerce a request value (int / float / str) to a Decimal, or `default`."""
    try:
        if value is None or value == '':
            return default
        return Decimal(str(value)).quantize(Decimal('0.001'))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _parse_window(body):
    """Extract date_needed (datetime) and return_date (date) from form data."""
    from django.utils.dateparse import parse_datetime, parse_date
    try:
        date_needed = parse_datetime(body.get('date_needed'))
    except Exception:
        date_needed = None
    try:
        return_date = parse_date(body.get('return_date'))
    except Exception:
        return_date = None
    return date_needed, return_date


def _serialise_request(br):
    """Turn a BorrowRequest into a JSON-safe dict, including its items."""
    items_data = []
    for ri in br.items.select_related('item').all():
        rec = InventoryRecord.objects.filter(item_id=ri.item_id).first()
        items_data.append({
            'item_id':   ri.item_id,
            'item_name': ri.item.item_name,
            'quantity':  _num(ri.quantity),
            'unit':      (ri.item.unit or 'pcs'),
            'available': _num(rec.available_count if rec else 0),
            'is_consumable': ri.item.is_consumable,
            'item_status': ri.item_status,
            'missing_qty': _num(ri.missing_qty),
            'damaged_qty': _num(ri.damaged_qty),
        })
    return {
        'id':            br.pk,
        'ref':           br.ref_number,
        'borrower_name': br.borrower_name,
        'section':       br.section,
        'teacher_name':  br.teacher_name,
        'role':          br.role,
        'purpose':       br.purpose,
        'date_needed':   br.date_needed.isoformat() if br.date_needed else None,
        'return_date':   br.return_date.isoformat() if br.return_date else None,
        'notes':         br.notes,
        'status':        br.status,
        'is_signed':     br.is_signed,
        'submitted_at':  br.submitted_at.isoformat(),
        'items':         items_data,
    }


# ─── Reference data ───────────────────────────────────────────────────────────

@require_http_methods(['GET'])
@dashboard_role_required
def dashboard_item_types(request):
    """GET /api/dashboard/item-types/"""
    data = list(
        ItemType.objects
        .values('type_id', 'type_label', 'category')
        .order_by('category', 'type_label')
    )
    return JsonResponse(data, safe=False)


@require_http_methods(['GET'])
@dashboard_role_required
def dashboard_locations(request):
    """GET /api/dashboard/locations/"""
    data = list(
        Location.objects
        .values('location_id', 'location_name')
        .order_by('location_name')
    )
    return JsonResponse(data, safe=False)


# ─── Items CRUD ───────────────────────────────────────────────────────────────

@csrf_exempt
@dashboard_role_required
def dashboard_items(request):
    """
    GET  /api/dashboard/items/  — returns ALL items (no is_visible filter)
    POST /api/dashboard/items/  — creates a new item + inventory record
    """

    # ── GET: list all items ────────────────────────────────────────────────
    if request.method == 'GET':
        records = (
            InventoryRecord.objects
            .select_related('item__type', 'location')
            .all()
            .order_by(
                'item__type__category',
                'item__type__type_label',
                'item__item_name',
            )
        )
        data = []
        for rec in records:
            item = rec.item
            data.append({
                'id':             item.item_id,
                'name':           item.item_name,
                'type_id':        item.type_id,
                'type_label':     item.type.type_label,
                'category':       item.type.category,
                'item_count':     _num(item.item_count),
                'unit':           normalize_unit(item.unit) or 'pcs',
                'description':    item.item_description or '',
                'is_borrowable':  item.is_borrowable,
                'is_visible':     item.is_visible,
                'is_consumable':  item.is_consumable,
                'available_count': _num(rec.available_count),
                'location_id':    rec.location_id,
                'location_name':  rec.location.location_name,
                'record_id':      rec.record_id,
            })
        return JsonResponse(data, safe=False)

    # ── POST: create item ──────────────────────────────────────────────────
    if request.method == 'POST':
        body, err = _parse_body(request)
        if err:
            return err

        for field in ('name', 'type_id', 'location_id'):
            if body.get(field) is None or body.get(field) == '':
                return JsonResponse(
                    {'error': f'Missing required field: {field}'}, status=400
                )

        try:
            itype = ItemType.objects.get(type_id=body['type_id'])
        except ItemType.DoesNotExist:
            return JsonResponse({'error': 'Invalid type_id'}, status=400)

        try:
            loc = Location.objects.get(location_id=body['location_id'])
        except Location.DoesNotExist:
            return JsonResponse({'error': 'Invalid location_id'}, status=400)

        count = _to_decimal(body.get('item_count'), Decimal('0'))
        avail = _to_decimal(body.get('available_count'), count)

        with transaction.atomic():
            item = Item(
                item_name        = body['name'].strip(),
                type             = itype,
                item_count       = count,
                unit             = (body.get('unit') or 'pcs').strip(),
                item_description = (body.get('description') or '').strip(),
                is_borrowable    = bool(body.get('is_borrowable', True)),
                is_visible       = bool(body.get('is_visible', True)),
                is_consumable    = bool(body.get('is_consumable', False)),
            )
            item.save()
            InventoryRecord.objects.create(
                item            = item,
                location        = loc,
                available_count = avail,
            )
            InventoryLog.objects.create(
                user=get_active_lims_user(request),
                item=item,
                action_type='ADD',
                new_value=f"Created item '{item.item_name}' with count {item.item_count} at location '{loc.location_name}'."
            )

        return JsonResponse({'id': item.item_id, 'status': 'created'}, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@dashboard_role_required
def dashboard_item_detail(request, item_id):
    """
    PATCH  /api/dashboard/items/<item_id>/  — update any combination of fields
    DELETE /api/dashboard/items/<item_id>/  — remove item permanently

    DELETE is blocked when the item has any borrow history to preserve
    referential integrity. Use PATCH {is_visible: false} to hide it instead.
    """
    try:
        item = Item.objects.select_related('type').get(pk=item_id)
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found.'}, status=404)

    # ── PATCH: update fields ───────────────────────────────────────────────
    if request.method == 'PATCH':
        body, err = _parse_body(request)
        if err:
            return err

        # Scalar fields that live on the Item row
        scalar_map = {
            'name':          ('item_name',        str),
            'unit':          ('unit',              str),
            'description':   ('item_description', str),
            'item_count':    ('item_count',        lambda v: _to_decimal(v, 0)),
            'is_borrowable': ('is_borrowable',     bool),
            'is_visible':    ('is_visible',        bool),
            'is_consumable': ('is_consumable',     bool),
        }
        item_dirty = False
        old_values = {}
        new_values = {}
        for key, (model_field, cast) in scalar_map.items():
            if key in body:
                if key == 'item_count':
                    val = _to_decimal(body[key])
                    if val is None:
                        return JsonResponse(
                            {'error': f'Invalid value for {key}.'}, status=400)
                else:
                    val = bool(body[key]) if cast is bool else cast(body[key])
                old_val = getattr(item, model_field)
                if old_val != val:
                    old_values[key] = old_val
                    new_values[key] = val
                    setattr(item, model_field, val)
                    item_dirty = True

        if 'type_id' in body:
            try:
                new_type = ItemType.objects.get(type_id=body['type_id'])
                if item.type != new_type:
                    old_values['type'] = item.type.type_label
                    new_values['type'] = new_type.type_label
                    item.type = new_type
                    item_dirty = True
            except ItemType.DoesNotExist:
                return JsonResponse({'error': 'Invalid type_id'}, status=400)

        # Fields that live on the InventoryRecord row
        inv_record = InventoryRecord.objects.filter(item=item).first()
        inv_updates = {}
        if 'available_count' in body:
            new_avail = _to_decimal(body['available_count'])
            if new_avail is None:
                return JsonResponse(
                    {'error': 'Invalid value for available_count.'}, status=400)
            if inv_record and inv_record.available_count != new_avail:
                old_values['available_count'] = inv_record.available_count
                new_values['available_count'] = new_avail
                inv_updates['available_count'] = new_avail
        if 'location_id' in body:
            try:
                loc = Location.objects.get(location_id=body['location_id'])
                if inv_record and inv_record.location != loc:
                    old_values['location'] = inv_record.location.location_name
                    new_values['location'] = loc.location_name
                    inv_updates['location'] = loc
            except Location.DoesNotExist:
                return JsonResponse({'error': 'Invalid location_id'}, status=400)

        with transaction.atomic():
            if item_dirty:
                item.save()

            if inv_updates:
                InventoryRecord.objects.filter(item=item).update(**inv_updates)

            if old_values or new_values:
                InventoryLog.objects.create(
                    user=get_active_lims_user(request),
                    item=item,
                    action_type='UPDATE',
                    old_value=json.dumps(old_values),
                    new_value=json.dumps(new_values),
                )

        return JsonResponse({'status': 'updated'})

    # ── DELETE ─────────────────────────────────────────────────────────────
    if request.method == 'DELETE':
        # Block deletion if ANY borrow history exists (including returned)
        has_history = BorrowRequestItem.objects.filter(item=item).exists()
        if has_history:
            return JsonResponse(
                {
                    'error': (
                        'Cannot delete: this item has borrow history. '
                        'Set "Visible" to off to hide it from the inventory instead.'
                    )
                },
                status=409,
            )
        try:
            with transaction.atomic():
                InventoryLog.objects.create(
                    user=get_active_lims_user(request),
                    item=item,
                    action_type='DELETE',
                    old_value=f"Deleted item '{item.item_name}'."
                )
                item.delete()   # cascades to inventory_record
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=409)

        return JsonResponse({'status': 'deleted'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ─── Borrow Requests ──────────────────────────────────────────────────────────

@csrf_exempt
@dashboard_role_required
def dashboard_requests(request):
    """
    GET  /api/dashboard/requests/?status=<filter>
         Returns all borrow requests, most-recent first.
         Optional ?status= query param filters by status.

    POST /api/dashboard/requests/
         Creates a manual borrow entry pre-set to 'approved'.
         Immediately decrements available_count for each item.
    """

    # ── GET ────────────────────────────────────────────────────────────────
    if request.method == 'GET':
        status_filter = request.GET.get('status')
        qs = (
            BorrowRequest.objects
            .prefetch_related('items__item')
            .order_by('-submitted_at')
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        return JsonResponse([_serialise_request(r) for r in qs], safe=False)

    # ── POST: manual entry ─────────────────────────────────────────────────
    if request.method == 'POST':
        body, err = _parse_body(request)
        if err:
            return err

        required = ['borrower_name', 'purpose', 'date_needed', 'return_date', 'items']
        missing  = [f for f in required if not body.get(f)]
        if missing:
            return JsonResponse(
                {'error': f'Missing required fields: {", ".join(missing)}'}, status=400
            )

        items_payload = body['items']
        if not isinstance(items_payload, list) or not items_payload:
            return JsonResponse({'error': 'items must be a non-empty list.'}, status=400)

        # Unique ref for manually-entered records
        ref = 'MAN-' + str(int(time.time() * 1000))[-6:]

        with transaction.atomic():
            # Validate stock up-front before touching anything
            dn, rd = _parse_window(body)
            if dn is None or rd is None:
                return JsonResponse(
                    {'error': 'date_needed and return_date are required.'}, status=400)

            validated = []
            for entry in items_payload:
                try:
                    rec = InventoryRecord.objects.select_related('item').get(
                        item__item_id=entry['item_id']
                    )
                except InventoryRecord.DoesNotExist:
                    return JsonResponse(
                        {'error': f'Item ID {entry["item_id"]} not found.'}, status=404
                    )
                qty = _to_decimal(entry.get('quantity'))
                if qty is None or qty <= 0:
                    return JsonResponse(
                        {'error': 'Quantity must be a positive number.'}, status=400
                    )
                capacity = date_capacity(rec.item, dn, rd)
                if qty > capacity:
                    booked = Decimal(str(rec.item.item_count)) - capacity
                    return JsonResponse(
                        {
                            'error': (
                                f'"{rec.item.item_name}" can\'t be borrowed for '
                                f'those dates: {_num(booked)} {rec.item.unit or "pcs"} '
                                f'of {_num(rec.item.item_count)} total are already '
                                f'reserved in that window by approved/borrowed '
                                f'requests, leaving only {_num(capacity)} '
                                f'{rec.item.unit or "pcs"} free. Pick different '
                                f'dates or reduce the quantity.'
                            )
                        },
                        status=409,
                    )
                validated.append((rec, qty))

            # Physical hand-off guard: never let on-hand drop below zero even
            # if reservations/approvals for other windows already look fine.
            for rec, qty in validated:
                if rec.available_count < qty:
                    return JsonResponse(
                        {
                            'error': (
                                f'Not enough "{rec.item.item_name}" on hand right '
                                f'now ({_num(rec.available_count)} '
                                f'{rec.item.unit or "pcs"} available) to hand out '
                                f'{_num(qty)} {rec.item.unit or "pcs"}. Restock '
                                f'first or reduce the quantity.'
                            )
                        },
                        status=409,
                    )

            br = BorrowRequest.objects.create(
                ref_number    = ref,
                borrower_name = body.get('borrower_name', '').strip(),
                section       = body.get('section', '').strip(),
                teacher_name  = body.get('teacher_name', '').strip(),
                role          = body.get('role', 'Lab Personnel'),
                purpose       = body.get('purpose', '').strip(),
                date_needed   = (
                    dj_timezone.make_aware(dn)
                    if settings.USE_TZ and dj_timezone.is_naive(dn) else dn
                ),
                return_date   = rd,
                notes         = body.get('notes', '').strip(),
                status        = 'borrowed',   # a manual entry is a real hand-off
            )
            BorrowRequestItem.objects.bulk_create([
                BorrowRequestItem(borrow_request=br, item=rec.item, quantity=qty)
                for rec, qty in validated
            ])
            # Atomically deduct stock for the hand-off (never below zero), and log.
            active_user = get_active_lims_user(request)
            for rec, qty in validated:
                handed = InventoryRecord.objects.filter(
                    pk=rec.pk, available_count__gte=qty
                ).update(available_count=F('available_count') - qty)
                if not handed:
                    raise ValueError(
                        f'Not enough "{rec.item.item_name}" on hand to hand out '
                        f'{qty} {rec.item.unit or "pcs"} to {br.borrower_name}.'
                    )
                InventoryLog.objects.create(
                    user=active_user,
                    item=rec.item,
                    action_type='BORROW',
                    new_value=f"Handed out {qty} {rec.item.unit} of \"{rec.item.item_name}\" to {br.borrower_name} (entry {br.ref_number})."
                )

        return JsonResponse({'id': br.pk, 'ref': ref, 'status': 'borrowed'}, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@dashboard_role_required
def dashboard_request_detail(request, req_id):
    """
    PATCH /api/dashboard/requests/<req_id>/

    Request forms are read-only after submit. This endpoint only allows:
      • status     — approve / reject / return / cancel (with inventory effects)
      • is_signed  — paper signature checkbox
    """
    try:
        br = BorrowRequest.objects.prefetch_related('items__item').get(pk=req_id)
    except BorrowRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found.'}, status=404)

    if request.method != 'PATCH':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    body, err = _parse_body(request)
    if err:
        return err

    # Reject attempts to edit form fields (dates, notes, borrower details, etc.)
    forbidden = [
        'date_needed', 'return_date', 'notes', 'borrower_name',
        'section', 'teacher_name', 'role', 'purpose', 'items',
    ]
    blocked = [k for k in forbidden if k in body]
    if blocked:
        return JsonResponse(
            {'error': 'Submitted forms cannot be edited. Only status and signature can change.'},
            status=403,
        )

    new_status = body.get('status')
    old_status = br.status
    valid_statuses = [s for s, _ in BorrowRequest.STATUS_CHOICES]

    if new_status and new_status not in valid_statuses:
        return JsonResponse({'error': f'Invalid status: {new_status}'}, status=400)

    with transaction.atomic():

        # ── Inventory adjustments on status transitions ────────────────────
        if new_status and new_status != old_status:
            active_user = get_active_lims_user(request)

            # Approving a pending request RESERVES stock for its window but does
            # NOT change available_count. The deduction happens only later, when
            # the item is handed out (approved → borrowed). This keeps
            # available_count as true physical on-hand instead of a forecast.
            if old_status == 'pending' and new_status == 'approved':
                dn = br.date_needed
                rd = br.return_date
                for ri in br.items.select_related('item').all():
                    rec = InventoryRecord.objects.filter(
                        item_id=ri.item_id).first()
                    if not rec:
                        return JsonResponse(
                            {'error': f'No inventory record for "{ri.item.item_name}"'},
                            status=400,
                        )
                    capacity = date_capacity(
                        rec.item, dn, rd, exclude_request_id=br.pk)
                    if ri.quantity > capacity:
                        booked = Decimal(str(rec.item.item_count)) - capacity
                        return JsonResponse(
                            {
                                'error': (
                                    f'Can\'t approve "{ri.item.item_name}" for '
                                    f'those dates: {_num(booked)} '
                                    f'{rec.item.unit or "pcs"} are already '
                                    f'reserved in that window by other '
                                    f'approved/borrowed requests, leaving only '
                                    f'{_num(capacity)} {rec.item.unit or "pcs"} '
                                    f'free (this request needs '
                                    f'{_num(ri.quantity)}).'
                                )
                            },
                            status=409,
                        )
                    InventoryLog.objects.create(
                        user=active_user,
                        item=ri.item,
                        action_type='APPROVE',
                        new_value=(
                            f"Approved borrow request {br.ref_number} for "
                            f"{ri.quantity} {ri.item.unit} to {br.borrower_name} "
                            f"(reserves stock for {dn.date()}–{rd}; stock is "
                            f"deducted when handed out)."
                        )
                    )

            # Hand-off: approved → borrowed deducts the physical stock.
            # Directly jumping from any other status to 'borrowed' would skip
            # the deduction, so only the approved → borrowed hop is allowed.
            if new_status == 'borrowed' and old_status != 'approved':
                return JsonResponse(
                    {
                        'error': 'A request can only be marked borrowed after it has been approved (approved → borrowed).'
                    },
                    status=409,
                )
            elif old_status == 'approved' and new_status == 'borrowed':
                for ri in br.items.select_related('item').all():
                    rec = InventoryRecord.objects.filter(
                        item_id=ri.item_id).first()
                    if not rec:
                        return JsonResponse(
                            {'error': f'No inventory record for "{ri.item.item_name}"'},
                            status=400,
                        )
                    handed = InventoryRecord.objects.filter(
                        pk=rec.pk, available_count__gte=ri.quantity
                    ).update(available_count=F('available_count') - ri.quantity)
                    if not handed:
                        return JsonResponse(
                            {
                                'error': (
                                    f'Not enough "{ri.item.item_name}" on hand to '
                                    f'hand out {_num(ri.quantity)} '
                                    f'{rec.item.unit or "pcs"} '
                                    f'({_num(rec.available_count)} '
                                    f'{rec.item.unit or "pcs"} available now).'
                                )
                            },
                            status=409,
                        )
                    InventoryLog.objects.create(
                        user=active_user,
                        item=ri.item,
                        action_type='BORROW',
                        new_value=f"Handed out {ri.quantity} {ri.item.unit} of \"{ri.item.item_name}\" to {br.borrower_name} (request {br.ref_number})."
                    )

            # Return (also allowed straight from an approved reservation):
            # what actually came back goes on the shelf; missing/damaged units
            # are consumed. Stock is only restored if it was deducted (i.e. the
            # item had been handed out via the borrowed status), and never for
            # consumables — those are used up on hand-out.
            elif new_status == 'returned' and old_status in ('borrowed', 'approved'):
                # Optional per-item condition flags with partial quantities sent
                # when marking returned:
                #   {"status":"returned",
                #    "item_statuses":[{"item_id":5,"condition":"missing","quantity":2}]}
                # Any units not counted as missing/damaged are restored to stock.
                conditions = {}
                for ri in br.items.all():
                    conditions[ri.item_id] = {'missing': Decimal('0'),
                                              'damaged': Decimal('0')}
                if isinstance(body.get('item_statuses'), list):
                    for entry in body['item_statuses']:
                        try:
                            iid  = int(entry['item_id'])
                            cond = (entry.get('condition') or 'ok').lower()
                            qty  = _to_decimal(entry.get('quantity'), Decimal('0'))
                        except (TypeError, ValueError, KeyError):
                            continue
                        if iid in conditions and cond in ('missing', 'damaged'):
                            conditions[iid][cond] = qty

                for ri in br.items.all():
                    flag = conditions.get(
                        ri.item_id, {'missing': Decimal('0'), 'damaged': Decimal('0')}
                    )
                    missing = min(flag['missing'], ri.quantity)
                    damaged = min(flag['damaged'], ri.quantity - missing)
                    ok_qty  = ri.quantity - missing - damaged

                    # Missing/damaged units were never returned — consume them.
                    if missing or damaged:
                        ri.missing_qty = missing
                        ri.damaged_qty = damaged
                        ri.item_status = (
                            'damaged' if damaged and not missing else 'missing'
                        )
                        ri.status_updated_at = dj_timezone.now()
                        ri.save(update_fields=[
                            'missing_qty', 'damaged_qty',
                            'item_status', 'status_updated_at',
                        ])

                    # Only a real hand-off took stock out; only it gets restored.
                    # Consumables (alcohol, reagents, PCR supplies) are used up
                    # when handed out — nothing comes back to the shelf, so the
                    # return only closes the request (and records consumption).
                    if old_status == 'borrowed' and ok_qty > 0:
                        if ri.item.is_consumable:
                            InventoryLog.objects.create(
                                user=active_user,
                                item=ri.item,
                                action_type='CONSUME',
                                new_value=f"Consumed {ok_qty} {ri.item.unit} of \"{ri.item.item_name}\" on request {br.ref_number} ({br.borrower_name}); no stock restored."
                            )
                        else:
                            InventoryRecord.objects.filter(
                                item_id=ri.item_id).update(
                                available_count=F('available_count') + ok_qty
                            )
                            InventoryLog.objects.create(
                                user=active_user,
                                item=ri.item,
                                action_type='RETURN',
                                new_value=f"Returned {ok_qty} {ri.item.unit} of \"{ri.item.item_name}\" from {br.borrower_name} (request {br.ref_number})."
                            )
                    if missing:
                        InventoryLog.objects.create(
                            user=active_user,
                            item=ri.item,
                            action_type='MISSING',
                            new_value=f"Missing {missing} {ri.item.unit} of \"{ri.item.item_name}\" on request {br.ref_number}."
                        )
                    if damaged:
                        InventoryLog.objects.create(
                            user=active_user,
                            item=ri.item,
                            action_type='DAMAGED',
                            new_value=f"Damaged {damaged} {ri.item.unit} of \"{ri.item.item_name}\" on request {br.ref_number}."
                        )

        # ── Allowed updates only ───────────────────────────────────────────
        if 'is_signed' in body:
            br.is_signed = bool(body['is_signed'])
        if new_status:
            br.status = new_status

        br.save()

    # Re-fetch to get updated item available counts in the response
    br.refresh_from_db()
    br.items.all()   # force re-evaluation of prefetch
    return JsonResponse(_serialise_request(br))


# ─── Schedule (timeline) ──────────────────────────────────────────────────────

@require_http_methods(['GET'])
@dashboard_role_required
def dashboard_schedule(request):
    """
    GET /api/dashboard/schedule/?year=YYYY&month=MM

    Returns one entry per (request × item) for all borrow requests that
    overlap the requested calendar month.  The frontend uses this to build
    the Gantt chart.
    """
    today = datetime.date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        return JsonResponse({'error': 'Invalid year or month.'}, status=400)

    if not (1 <= month <= 12):
        return JsonResponse({'error': 'Month must be 1–12.'}, status=400)

    first_day = datetime.date(year, month, 1)
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    # ── Build an exclusive upper bound for date_needed (start of the day
    #    AFTER last_day) and make it timezone-aware if USE_TZ is enabled.
    #    We deliberately avoid the __date lookup here: on MySQL it requires
    #    CONVERT_TZ + loaded timezone tables, which are often missing on
    #    Windows/dev setups and silently return NULL, making __date lookups
    #    match nothing.
    upper_bound_naive = datetime.datetime.combine(
        last_day + datetime.timedelta(days=1), datetime.time.min
    )
    if settings.USE_TZ:
        upper_bound = dj_timezone.make_aware(upper_bound_naive)
    else:
        upper_bound = upper_bound_naive

    # Include requests that overlap this month at all
    qs = (
        BorrowRequest.objects
        .prefetch_related('items__item')
        .filter(
            date_needed__lt=upper_bound,
            return_date__gte=first_day,
            status__in=('pending', 'approved', 'returned'),
        )
        .order_by('date_needed')
    )

    entries = []
    for br in qs:
        # Normalise date_needed to a plain date for the timeline, converting
        # to the local timezone first so the displayed date matches what the
        # lab personnel entered (avoids UTC-storage day-shift).
        dn = br.date_needed
        if hasattr(dn, 'date'):
            if settings.USE_TZ and dj_timezone.is_aware(dn):
                dn = dj_timezone.localtime(dn)
            date_needed_str = dn.date().isoformat()
        else:
            date_needed_str = str(dn)

        for ri in br.items.all():
            entries.append({
                'request_id':    br.pk,
                'ref':           br.ref_number,
                'item_id':       ri.item_id,
                'item_name':     ri.item.item_name,
                'quantity':      _num(ri.quantity),
                'borrower_name': br.borrower_name,
                'status':        br.status,
                'date_needed':   date_needed_str,
                'return_date':   br.return_date.isoformat(),
            })

    return JsonResponse({
        'year':      year,
        'month':     month,
        'first_day': first_day.isoformat(),
        'last_day':  last_day.isoformat(),
        'entries':   entries,
    })


# ─── Diagnostics View for IT Personnel ────────────────────────────────────────
@require_http_methods(['GET'])
def dashboard_diagnostics(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    profile = getattr(request.user, 'profile', None)
    role = profile.role if profile else None
    if role != 'it_personnel':
        return JsonResponse({'error': 'Permission denied. IT Personnel access only.'}, status=403)

    # Check DB status
    db_status = "Healthy"
    try:
        from django.db import connection
        connection.ensure_connection()
    except Exception as e:
        db_status = f"Error: {str(e)}"

    # Get environment variables (sanitized)
    env_vars = {}
    for key, value in os.environ.items():
        if any(x in key.upper() for x in ('KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'AUTH')):
            env_vars[key] = "********"
        else:
            env_vars[key] = value

    # Get safe Django settings
    safe_settings = {
        'ALLOWED_HOSTS': settings.ALLOWED_HOSTS,
        'DEBUG': settings.DEBUG,
        'DEFAULT_DATABASE': {
            'ENGINE': settings.DATABASES['default']['ENGINE'],
            'HOST': settings.DATABASES['default']['HOST'],
            'PORT': settings.DATABASES['default']['PORT'],
            'USER': settings.DATABASES['default']['USER'],
        },
        'TIME_ZONE': settings.TIME_ZONE,
        'USE_TZ': settings.USE_TZ,
        'INSTALLED_APPS': [app for app in settings.INSTALLED_APPS if not app.startswith('django.')],
    }

    # Query system logs (InventoryLog)
    logs = []
    try:
        log_qs = InventoryLog.objects.select_related('user', 'item').order_by('-timestamp')[:100]
        for log in log_qs:
            logs.append({
                'log_id': log.log_id,
                'user_name': log.user.user_name if log.user else 'Unknown',
                'user_role': log.user.user_role if log.user else 'Unknown',
                'item_name': log.item.item_name if log.item else 'Unknown',
                'action_type': log.action_type,
                'timestamp': log.timestamp.isoformat(),
            })
    except Exception as e:
        logs = [{'error': f"Failed to retrieve logs: {str(e)}"}]

    data = {
        'django_version': django.get_version(),
        'django_debug': settings.DEBUG,
        'db_status': db_status,
        'db_engine': settings.DATABASES['default']['ENGINE'],
        'env_vars': env_vars,
        'settings': safe_settings,
        'logs': logs,
    }
    return JsonResponse(data)


# ─── Reports ──────────────────────────────────────────────────────────────────

@csrf_exempt
@dashboard_role_required
def dashboard_reports(request):
    """
    GET  /api/dashboard/reports/              — list all saved reports
    POST /api/dashboard/reports/              — generate a report
        body: { "report_type": "daily|weekly|monthly|yearly|custom",
                "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }
              (start/end only required for custom; other types auto-compute)
    """
    if request.method == 'GET':
        reports = list(
            Report.objects
            .select_related('created_by')
            .values('id', 'report_type', 'title', 'start_date', 'end_date',
                    'generated_at')[:200]
        )
        for r in reports:
            r['start_date'] = r['start_date'].isoformat()
            r['end_date']   = r['end_date'].isoformat()
            r['generated_at'] = r['generated_at'].isoformat()
        return JsonResponse(reports, safe=False)

    if request.method == 'POST':
        body, err = _parse_body(request)
        if err:
            return err

        rtype = (body.get('report_type') or 'weekly').lower()
        valid = [t for t, _ in Report.REPORT_TYPE_CHOICES]
        if rtype not in valid:
            return JsonResponse({'error': f'Invalid report_type: {rtype}'}, status=400)

        try:
            if rtype == 'custom':
                start = datetime.date.fromisoformat(body['start_date'])
                end = datetime.date.fromisoformat(body['end_date'])
            else:
                start, end = _period_for(rtype)
        except (KeyError, ValueError):
            return JsonResponse(
                {'error': 'start_date and end_date are required (YYYY-MM-DD) for custom reports.'},
                status=400,
            )

        if end < start:
            return JsonResponse({'error': 'end_date must be on/after start_date.'}, status=400)

        data = generate_report_data(start, end)
        title = body.get('title') or build_report_title(rtype)
        report = Report.objects.create(
            report_type=rtype,
            title=title,
            start_date=start,
            end_date=end,
            data=data,
            created_by=request.user if request.user.is_authenticated else None,
        )
        return JsonResponse({
            'id': report.pk, 'report_type': report.report_type, 'title': report.title,
            'start_date': report.start_date.isoformat(), 'end_date': report.end_date.isoformat(),
            'generated_at': report.generated_at.isoformat(),
        }, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@dashboard_role_required
def dashboard_report_detail(request, report_id):
    """GET /api/dashboard/reports/<id>/     — report metadata + data
       DELETE /api/dashboard/reports/<id>/  — delete a saved report"""
    try:
        report = Report.objects.get(pk=report_id)
    except Report.DoesNotExist:
        return JsonResponse({'error': 'Report not found.'}, status=404)

    if request.method == 'DELETE':
        report.delete()
        return JsonResponse({'status': 'deleted'})

    return JsonResponse({
        'id': report.pk,
        'report_type': report.report_type,
        'title': report.title,
        'start_date': report.start_date.isoformat(),
        'end_date': report.end_date.isoformat(),
        'generated_at': report.generated_at.isoformat(),
        'data': report.data,
    })


@dashboard_role_required
def dashboard_report_export(request, report_id):
    """GET /api/dashboard/reports/<id>/export/?format=csv — download export."""
    try:
        report = Report.objects.get(pk=report_id)
    except Report.DoesNotExist:
        return JsonResponse({'error': 'Report not found.'}, status=404)

    fmt = request.GET.get('format', 'csv').lower()
    if fmt == 'csv':
        csv_text = export_csv(report)
        resp = HttpResponse(csv_text, content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="report-{report.pk}.csv"'
        return resp
    if fmt == 'html':
        html = render_report_html(report)
        resp = HttpResponse(html, content_type='text/html')
        resp['Content-Disposition'] = f'attachment; filename="report-{report.pk}.html"'
        return resp
    return JsonResponse({'error': f'Unsupported format: {fmt}'}, status=400)


# ─── Restock ──────────────────────────────────────────────────────────────────

@csrf_exempt
@dashboard_role_required
def dashboard_item_restock(request, item_id):
    """
    POST /api/dashboard/items/<id>/restock/
        body: { "quantity": N }
    Adds N to item_count and available_count, logs a RESTOCK entry.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    body, err = _parse_body(request)
    if err:
        return err

    qty = _to_decimal(body.get('quantity'))
    if qty is None or qty <= 0:
        return JsonResponse(
            {'error': 'quantity must be a positive number.'}, status=400)

    try:
        item = Item.objects.get(pk=item_id)
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found.'}, status=404)

    inv_record = InventoryRecord.objects.filter(item=item).first()
    with transaction.atomic():
        item.item_count = F('item_count') + qty
        item.save(update_fields=['item_count'])
        if inv_record:
            InventoryRecord.objects.filter(item=item).update(
                available_count=F('available_count') + qty
            )
        InventoryLog.objects.create(
            user=get_active_lims_user(request),
            item=item,
            action_type='RESTOCK',
            new_value=f"Restocked {qty} {item.unit or 'pcs'} of '{item.item_name}'.",
        )

    return JsonResponse({'status': 'restocked', 'item_id': item_id, 'quantity': _num(qty)})
