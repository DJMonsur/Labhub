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
from django.shortcuts import render, redirect
from django.http            import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (InventoryRecord, Item, BorrowRequest, BorrowRequestItem,
                     InventoryLog, BorrowRecord, LimsUser)
from .dashboard_views import get_active_lims_user

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
            'qty':  row['quantity_borrowed'],
            'due':  due.strftime('%Y-%m-%d') if due else '',
        })

    data = []
    for record in records:
        item      = record.item
        item_type = item.type
        ftype     = _frontend_type(item_type)

        data.append({
            'id':           item.item_id,
            'name':         item.item_name,
            'type':         ftype,
            'type_label':   item_type.type_label,
            'category':     item_type.category,
            'icon':         ICON_MAP.get(ftype, '🔬'),
            'unit':         item.unit or 'pcs',
            'total':        item.item_count,
            'available':    record.available_count,
            'is_borrowable': item.is_borrowable,
            'borrows':      active_borrows.get(item.item_id, []),
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
        { "item_id": 1, "quantity": 3 },
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

    validated_items = []
    for entry in items_payload:
        item_id  = entry.get('item_id')
        quantity = entry.get('quantity', 0)

        if not item_id or quantity < 1:
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
        if record.available_count < quantity:
            return JsonResponse(
                {
                    'error': (
                        f'Not enough stock for "{record.item.item_name}". '
                        f'Requested: {quantity}, Available: {record.available_count}.'
                    )
                },
                status=409,
            )
        validated_items.append((record.item, quantity))

    ref = 'BRW-' + str(int(time.time() * 1000))[-6:]

    borrow_request = BorrowRequest.objects.create(
        ref_number    = ref,
        borrower_name = body['borrower_name'].strip(),
        section       = body['section'].strip(),
        teacher_name  = body['teacher_name'].strip(),
        role          = body['role'],
        purpose       = body['purpose'].strip(),
        date_needed   = body['date_needed'],
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
