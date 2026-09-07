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
"""

import json
import time
import datetime
import os
import django
from functools import wraps

from django.conf          import settings
from django.db            import transaction
from django.db.models     import F
from django.http          import JsonResponse
from django.utils         import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    Item, ItemType, Location,
    InventoryRecord,
    BorrowRequest, BorrowRequestItem,
    InventoryLog, LimsUser,
)
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


def _serialise_request(br):
    """Turn a BorrowRequest into a JSON-safe dict, including its items."""
    items_data = []
    for ri in br.items.select_related('item').all():
        rec = InventoryRecord.objects.filter(item_id=ri.item_id).first()
        items_data.append({
            'item_id':   ri.item_id,
            'item_name': ri.item.item_name,
            'quantity':  ri.quantity,
            'available': rec.available_count if rec else 0,
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
                'item_count':     item.item_count,
                'unit':           item.unit or 'pcs',
                'description':    item.item_description or '',
                'is_borrowable':  item.is_borrowable,
                'is_visible':     item.is_visible,
                'available_count': rec.available_count,
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

        count = int(body.get('item_count', 0))
        avail = int(body.get('available_count', count))

        with transaction.atomic():
            item = Item(
                item_name        = body['name'].strip(),
                type             = itype,
                item_count       = count,
                unit             = (body.get('unit') or 'pcs').strip(),
                item_description = (body.get('description') or '').strip(),
                is_borrowable    = bool(body.get('is_borrowable', True)),
                is_visible       = bool(body.get('is_visible', True)),
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
            'item_count':    ('item_count',        int),
            'is_borrowable': ('is_borrowable',     bool),
            'is_visible':    ('is_visible',        bool),
        }
        item_dirty = False
        old_values = {}
        new_values = {}
        for key, (model_field, cast) in scalar_map.items():
            if key in body:
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
            new_avail = int(body['available_count'])
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
                qty = int(entry.get('quantity', 1))
                if qty < 1:
                    return JsonResponse(
                        {'error': 'Quantity must be at least 1.'}, status=400
                    )
                if rec.available_count < qty:
                    return JsonResponse(
                        {
                            'error': (
                                f'Not enough stock for "{rec.item.item_name}". '
                                f'Available: {rec.available_count}'
                            )
                        },
                        status=409,
                    )
                validated.append((rec, qty))

            br = BorrowRequest.objects.create(
                ref_number    = ref,
                borrower_name = body.get('borrower_name', '').strip(),
                section       = body.get('section', '').strip(),
                teacher_name  = body.get('teacher_name', '').strip(),
                role          = body.get('role', 'Lab Personnel'),
                purpose       = body.get('purpose', '').strip(),
                date_needed   = body['date_needed'],
                return_date   = body['return_date'],
                notes         = body.get('notes', '').strip(),
                status        = 'approved',   # manual entries are pre-approved
            )
            BorrowRequestItem.objects.bulk_create([
                BorrowRequestItem(borrow_request=br, item=rec.item, quantity=qty)
                for rec, qty in validated
            ])
            # Atomically decrement available counts and log BORROW
            active_user = get_active_lims_user(request)
            for rec, qty in validated:
                InventoryRecord.objects.filter(pk=rec.pk).update(
                    available_count=F('available_count') - qty
                )
                InventoryLog.objects.create(
                    user=active_user,
                    item=rec.item,
                    action_type='BORROW',
                    new_value=f"Manual pre-approved borrow entry {br.ref_number} for {qty} {rec.item.unit} to {br.borrower_name}."
                )

        return JsonResponse({'id': br.pk, 'ref': ref, 'status': 'approved'}, status=201)

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

            # Approving a pending request — take stock
            if old_status == 'pending' and new_status == 'approved':
                for ri in br.items.select_related('item').all():
                    rec = InventoryRecord.objects.filter(item_id=ri.item_id).first()
                    if not rec:
                        return JsonResponse(
                            {'error': f'No inventory record for "{ri.item.item_name}"'},
                            status=400,
                        )
                    if rec.available_count < ri.quantity:
                        return JsonResponse(
                            {
                                'error': (
                                    f'Not enough stock for "{ri.item.item_name}". '
                                    f'Available: {rec.available_count}, '
                                    f'Requested: {ri.quantity}'
                                )
                            },
                            status=409,
                        )
                    InventoryRecord.objects.filter(pk=rec.pk).update(
                        available_count=F('available_count') - ri.quantity
                    )
                    InventoryLog.objects.create(
                        user=active_user,
                        item=ri.item,
                        action_type='BORROW',
                        new_value=f"Approved borrow request {br.ref_number} for {ri.quantity} {ri.item.unit} to {br.borrower_name}."
                    )

            # Returning or cancelling an approved request — restore stock
            elif old_status == 'approved' and new_status in ('returned', 'cancelled'):
                for ri in br.items.all():
                    InventoryRecord.objects.filter(item_id=ri.item_id).update(
                        available_count=F('available_count') + ri.quantity
                    )
                    action = 'RETURN' if new_status == 'returned' else 'UPDATE'
                    desc_action = 'returned' if new_status == 'returned' else 'cancelled'
                    InventoryLog.objects.create(
                        user=active_user,
                        item=ri.item,
                        action_type=action,
                        new_value=f"Marked borrow request {br.ref_number} as {desc_action}: {ri.quantity} {ri.item.unit} from {br.borrower_name}."
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
                'quantity':      ri.quantity,
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
