"""
inventory/views.py

Two JSON API endpoints for the public-facing inventory page:

  GET  /api/inventory/   — items visible to students/teachers
  POST /api/borrow/      — saves a borrowing form submission

CHANGES vs v1:
  - inventory_list now filters item__is_visible=True  (hidden items are
    excluded for regular users; the dashboard shows everything)
  - inventory_list also excludes non-borrowable items from the frontend
    count so students can't request them
"""

import json
import time
import datetime
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http            import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (InventoryRecord, Item, BorrowRequest, BorrowRequestItem,
                     InventoryLog, BorrowRecord, LimsUser)
from .dashboard_views import get_active_lims_user
from .availability import (date_capacity, reservations_for,
                           pending_reservations_for)
from .units import (normalize_unit, auto_display, conversion_factor, qty_step,
                    unit_options_for)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

def index(request):
    if not request.user.is_authenticated:
        # Redirect rather than render the template directly — the allauth view
        # supplies the login form, which this template needs for password login.
        return redirect('/accounts/login/')
    profile = getattr(request.user, 'profile', None)
    role    = profile.role if profile else 'student_teacher'
    return render(request, 'index.html', {'current_role': role})

@login_required
def dashboard(request):
    profile = getattr(request.user, 'profile', None)
    role    = profile.role if profile else 'student_teacher'
    # Block student/teacher from dashboard
    if role == 'student_teacher':
        return redirect('/')
    return render(request, 'dashboard.html', {'current_role': role})

# ─── ICON MAPPING ─────────────────────────────────────────────────────────────
ICON_MAP = {
    'Equipment': '🧪',
    'Material':  '🧴',
    'Slide':     '🔍',
    'Model':     '🦴',
}


def _frontend_type(item_type):
    """
    Map an ItemType to the frontend category string.
    'Equipment/Anatomical Model' → 'Model'
    Everything else              → category (Equipment / Material / Slide)
    """
    if 'Anatomical Model' in item_type.type_label:
        return 'Model'
    return item_type.category


def _num(value):
    """JSON-safe number: Decimal → plain float (1.500 → 1.5)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _item_unit_meta(item, available):
    """Display-unit metadata for the frontend.

    Returns
      unit           canonical stored unit (g / kg / mL / pcs / ...)
      display_unit   the friendlier unit to show / enter quantities in
      display_factor multiply a value in display_unit to get the stored unit
      qty_step       smallest sensible input increment
      options        every unit the user may pick from for this item
    """
    stored = normalize_unit(item.unit) or 'pcs'
    _disp_value, display_unit = auto_display(available, stored)
    return {
        'unit':           stored,
        'display_unit':   display_unit,
        'display_factor': float(conversion_factor(display_unit, stored)),
        'qty_step':       float(qty_step(stored)),
        'options':        unit_options_for(item.unit),
    }


# ─── GET /api/inventory/ ──────────────────────────────────────────────────────
@require_http_methods(['GET'])
def inventory_list(request):
    """
    Returns a JSON array of every *visible* item in the Biology Lab with live
    available_count data from inventory_record.

    Filters applied (for public users):
      • item__is_visible = True   — hidden items are not shown
    """
    records = (
        InventoryRecord.objects
        .select_related('item__type', 'location')
        .filter(item__is_visible=True)          # ← only visible items
        .all()
    )

    # Build active-borrow lookup: item_id → list of borrow summaries.
    #
    # This used raw SQL with DATE_FORMAT(), which only exists on MySQL and
    # crashed on SQLite. The ORM version below is database-agnostic and does
    # the date formatting in Python instead.
    #
    # User names are fetched separately rather than joined, so a borrow_record
    # pointing at a missing user degrades to "Unknown" instead of vanishing
    # from the results the way an INNER JOIN would drop it.
    user_names = dict(LimsUser.objects.values_list('user_id', 'user_name'))

    active_borrows = {}
    borrow_rows = (
        BorrowRecord.objects
        .filter(status__in=('approved', 'borrowed'))
        .values('item_id', 'user_id', 'quantity_borrowed', 'due_date')
    )
    for row in borrow_rows:
        due = row['due_date']
        active_borrows.setdefault(row['item_id'], []).append({
            'user': user_names.get(row['user_id'], 'Unknown'),
            'qty':  _num(row['quantity_borrowed']),
            'due':  due.strftime('%Y-%m-%d') if due else '',
        })

    data = []
    for record in records:
        item      = record.item
        item_type = item.type
        ftype     = _frontend_type(item_type)

        avail_disp, disp_unit = auto_display(record.available_count,
                                             normalize_unit(item.unit) or 'pcs')
        total_disp, _         = auto_display(item.item_count,
                                             normalize_unit(item.unit) or 'pcs')
        meta                  = _item_unit_meta(item, record.available_count)

        data.append({
            'id':           item.item_id,
            'name':         item.item_name,
            'type':         ftype,
            'type_label':   item_type.type_label,
            'category':     item_type.category,
            'icon':         ICON_MAP.get(ftype, '🔬'),
            # -- units -------------------------------------------------
            'unit':             meta['unit'],
            'display_unit':     meta['display_unit'],
            'display_factor':   meta['display_factor'],  # display qty → stored qty
            'qty_step':         meta['qty_step'],
            'unit_options':     meta['options'],
            'available':        _num(record.available_count),
            'total':            _num(item.item_count),
            'available_display': _num(avail_disp),
            'total_display':     _num(total_disp),
            'is_borrowable':    item.is_borrowable,
            'borrows':          active_borrows.get(item.item_id, []),
            # approved/borrowed date ranges reserving this item (hard blockers)
            'reservations':     reservations_for(item.item_id),
            # pending date ranges (warnings only — still can change)
            'pending_reservations': pending_reservations_for(item.item_id),
        })

    return JsonResponse(data, safe=False)


# ─── POST /api/borrow/ ────────────────────────────────────────────────────────
@csrf_exempt
@require_http_methods(['POST'])
def submit_borrow(request):
    """
    Accepts a JSON body from the borrowing form and saves it to
    borrow_request + borrow_request_item.

    Expected body:
    {
      "borrower_name": "...",
      "section":       "...",
      "teacher_name":  "...",
      "role":          "Student" | "Teacher" | "Lab Personnel",
      "purpose":       "...",
      "date_needed":   "2025-12-15T08:00",
      "return_date":   "2025-12-16",
      "notes":         "...",   (optional)
      "items": [
        { "item_id": 1, "quantity": 3 },          // decimal ok: 1.5, 0.5
        ...
      ]
    }

    Returns:  { "ref": "BRW-XXXXXX", "status": "pending" }
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    required = ['borrower_name', 'section', 'teacher_name', 'role',
                'purpose', 'date_needed', 'return_date', 'items']
    missing = [f for f in required if not body.get(f)]
    if missing:
        return JsonResponse(
            {'error': f'Missing required fields: {", ".join(missing)}'},
            status=400,
        )

    items_payload = body['items']
    if not isinstance(items_payload, list) or len(items_payload) == 0:
        return JsonResponse({'error': 'items must be a non-empty list.'}, status=400)

    # Parse the requested window; overlap checks need real date objects.
    from django.conf import settings as dj_settings
    from django.utils import timezone as dj_tz
    from django.utils.dateparse import parse_datetime, parse_date
    date_needed = parse_datetime(body['date_needed'])
    return_date = parse_date(body['return_date'])
    if date_needed is None or return_date is None:
        return JsonResponse(
            {'error': 'date_needed and return_date must be valid dates.'},
            status=400,
        )
    if dj_settings.USE_TZ and dj_tz.is_naive(date_needed):
        date_needed = dj_tz.make_aware(date_needed)

    validated_items = []
    for entry in items_payload:
        item_id  = entry.get('item_id')
        try:
            quantity = Decimal(str(entry.get('quantity', 0))).quantize(
                Decimal('0.001'))
        except Exception:
            return JsonResponse(
                {'error': f'Invalid quantity for item entry: {entry}'},
                status=400,
            )

        if not item_id or quantity <= 0:
            return JsonResponse(
                {'error': f'Invalid item entry: {entry}'},
                status=400,
            )
        try:
            record = InventoryRecord.objects.select_related('item').get(
                item__item_id=item_id
            )
        except InventoryRecord.DoesNotExist:
            return JsonResponse(
                {'error': f'Item ID {item_id} not found in inventory.'},
                status=404,
            )

        item  = record.item
        avail = record.available_count
        # Date-aware booking check. The physical number on the shelf may have
        # been reduced by approvals for *other* windows; those approvals don't
        # block this window unless they overlap it.
        capacity = date_capacity(item, date_needed, return_date)
        if quantity > capacity:
            overlap    = Decimal(str(item.item_count)) - capacity
            disp, dunit = auto_display(avail, normalize_unit(item.unit) or 'pcs')
            return JsonResponse(
                {
                    'error': (
                        f'"{item.item_name}" can\'t be booked for those dates: '
                        f'{_num(overlap)} {item.unit or "pcs"} of {_num(item.item_count)} '
                        f'{item.unit or "pcs"} total are already reserved in that '
                        f'window by approved/borrowed requests, leaving only '
                        f'{_num(capacity)} {item.unit or "pcs"} free. Pending '
                        f'requests don\'t reserve stock yet, so pick different '
                        f'dates or reduce the quantity. '
                        f'({_num(disp)} {dunit} currently on hand.)'
                    )
                },
                status=409,
            )
        validated_items.append((item, quantity))

    ref = 'BRW-' + str(int(time.time() * 1000))[-6:]

    borrow_request = BorrowRequest.objects.create(
        ref_number    = ref,
        borrower_name = body['borrower_name'].strip(),
        section       = body['section'].strip(),
        teacher_name  = body['teacher_name'].strip(),
        role          = body['role'],
        purpose       = body['purpose'].strip(),
        date_needed   = date_needed,
        return_date   = body['return_date'],
        notes         = body.get('notes', '').strip(),
        status        = 'pending',
    )

    BorrowRequestItem.objects.bulk_create([
        BorrowRequestItem(
            borrow_request=borrow_request,
            item=item,
            quantity=qty,
        )
        for item, qty in validated_items
    ])

    # ── Inventory logging for each requested item ──────────────────────
    active_user = get_active_lims_user(request)
    for item, qty in validated_items:
        InventoryLog.objects.create(
            user=active_user,
            item=item,
            action_type='BORROW_REQUEST',
            new_value=(
                f"Borrow request {ref} submitted by "
                f"{body['borrower_name']} for {qty} {item.unit or 'pcs'}."
            ),
        )

    return JsonResponse({'ref': ref, 'status': 'pending'}, status=201)


# ─── GET /api/inventory/items/<id>/borrows/ ───────────────────────────────────
# Date-aware borrow lookup for the item details page: given an optional
# ?date=YYYY-MM-DD, returns every borrow covering that date — the physical
# loans in the legacy borrow_record table plus the approved/borrowed web
# reservations from borrow_request. Without ?date it returns them all.
#
# Only active bookings count (approved / borrowed), matching the definitions
# used everywhere else in the app (ACTIVE_STATUSES). Returned/cancelled/
# pending rows are never shown.

def _fmt_dt(value):
    """ISO-format a date/datetime for the API, in the local timezone."""
    if value is None:
        return None
    from django.utils import timezone as dj_timezone
    try:
        if dj_timezone.is_aware(value):
            value = dj_timezone.localtime(value)
    except Exception:
        pass
    return value.isoformat()


def _in_window(start, end, target):
    """True when the [start, end] window covers `target` (a date, or None to
    match everything). Open-ended windows count as covering anything."""
    if not target:
        return True

    def _d(v):
        return v.date() if hasattr(v, 'date') else v  # datetime → date

    s, e = _d(start), _d(end)
    if s is None and e is None:
        return True                    # active but undated — show it anyway
    if s is not None and target < s:
        return False
    if e is not None and target > e:
        return False
    return True


@require_http_methods(['GET'])
def item_borrows(request, item_id):
    """
    GET /api/inventory/items/<item_id>/borrows/?date=YYYY-MM-DD

    Returns the active borrows for one item, optionally narrowed to the
    bookings that overlap a given date. Each entry carries who borrowed it
    (name), how much, and the time window:

      { "item_id", "item_name", "date", "borrows": [
          { "source": "borrow_request"|"borrow_record",
            "ref": "BRW-XXXXXX" | "BR#<id>",
            "user", "qty", "unit", "start", "end", "status" }, ... ] }

    `end` is end-of-day for date-only return dates; `start` keeps the time.
    """
    try:
        item = Item.objects.get(pk=item_id)
    except Item.DoesNotExist:
        return JsonResponse({'error': 'Item not found.'}, status=404)

    date_param = (request.GET.get('date') or '').strip()
    target = None
    if date_param:
        try:
            target = datetime.date.fromisoformat(date_param)
        except ValueError:
            return JsonResponse(
                {'error': 'Invalid date. Use YYYY-MM-DD.'}, status=400)

    user_names = dict(LimsUser.objects.values_list('user_id', 'user_name'))
    unit = item.unit or 'pcs'
    entries = []

    # ── legacy borrow_record (physical loans) ────────────────────────────
    for br in BorrowRecord.objects.filter(
            item_id=item_id, status__in=('approved', 'borrowed')):
        end = br.return_date
        if end is None and br.due_date is not None:
            end = datetime.datetime.combine(br.due_date, datetime.time.max)
        if not _in_window(br.borrow_date, end, target):
            continue
        entries.append({
            'source': 'borrow_record',
            'ref':    f'BR#{br.borrow_id}',
            'user':   user_names.get(br.user_id, 'Unknown'),
            'qty':    _num(br.quantity_borrowed),
            'unit':   unit,
            'start':  _fmt_dt(br.borrow_date),
            'end':    _fmt_dt(end),
            'status': br.status,
        })

    # ── web borrow_request reservations (approved / borrowed) ────────────
    qs = (
        BorrowRequestItem.objects
        .filter(item_id=item_id,
                borrow_request__status__in=('approved', 'borrowed'))
        .select_related('borrow_request')
    )
    for ri in qs:
        brq = ri.borrow_request
        end = (datetime.datetime.combine(brq.return_date, datetime.time.max)
               if brq.return_date else None)
        if not _in_window(brq.date_needed, end, target):
            continue
        entries.append({
            'source': 'borrow_request',
            'ref':    brq.ref_number,
            'user':   brq.borrower_name,
            'qty':    _num(ri.quantity),
            'unit':   unit,
            'start':  _fmt_dt(brq.date_needed),
            'end':    _fmt_dt(end),
            'status': brq.status,
        })

    entries.sort(key=lambda e: (e['start'] is None, e['start'] or ''))
    return JsonResponse({
        'item_id':   item.item_id,
        'item_name': item.item_name,
        'date':      date_param or None,
        'borrows':   entries,
    })
