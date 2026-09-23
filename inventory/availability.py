"""
inventory/availability.py

Date-aware booking capacity.

The main page keeps showing *currently available* stock (approved requests are
deducted from `available_count`, returns restore it). But a borrow request
should not be blocked just because another *future* approved borrow already
subtracted from that number - anyone should be able to book an item for a date
range that does not overlap an already-approved booking.

These helpers compute how much of an item is still bookable for a given date
range: the item's total physical count minus the quantities of APPROVED /
BORROWED requests whose [date_needed, return_date] overlaps the range.
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone as dj_timezone

from .models import BorrowRequestItem

# Requests holding stock against a date range.
ACTIVE_STATUSES = ('approved', 'borrowed')


def _overlap_queryset(item_id, date_needed, return_date, exclude_request_id=None):
    """BorrowRequestItem rows that reserve `item_id` during the range."""
    lower = date_needed.date() if hasattr(date_needed, 'date') else date_needed
    # The range runs through the END of the return_date day.
    upper = datetime.datetime.combine(
        return_date,
        datetime.time(hour=23, minute=59, second=59),
    )
    if settings.USE_TZ:
        upper = dj_timezone.make_aware(upper)
    qs = (
        BorrowRequestItem.objects
        .filter(
            item_id=item_id,
            borrow_request__status__in=ACTIVE_STATUSES,
            borrow_request__date_needed__lt=upper,
            borrow_request__return_date__gte=lower,
        )
        .select_related('borrow_request')
    )
    if exclude_request_id:
        qs = qs.exclude(borrow_request_id=exclude_request_id)
    return qs


def overlapping_qty(item_id, date_needed, return_date, exclude_request_id=None):
    """Total quantity (in the item's stored unit) of approved/borrowed requests
    whose date range overlaps [date_needed, return_date]."""
    qs = _overlap_queryset(item_id, date_needed, return_date, exclude_request_id)
    total = qs.aggregate(total=Sum('quantity'))['total']
    return total if total is not None else Decimal('0')


def date_capacity(item, date_needed, return_date, exclude_request_id=None):
    """How many units (stored unit) can still be booked for this item over the
    given date range. Negative when the range is already over-booked."""
    committed = overlapping_qty(item.item_id, date_needed, return_date,
                                exclude_request_id)
    return Decimal(str(item.item_count)) - committed


def reservations_for(item_id, limit=50):
    """Active (approved/borrowed) date reservations for an item.

    Returns a list of dicts {qty, date_needed, return_date, ref, status} used
    by the frontend to block overlapping submissions.
    """
    return _reservations_in_statuses(item_id, ACTIVE_STATUSES, limit)


def pending_reservations_for(item_id, limit=50):
    """Pending-only date reservations for an item.

    These are warnings, never blockers: a pending request may still be
    rejected before its dates arrive, so it does not hold stock.
    """
    return _reservations_in_statuses(item_id, ('pending',), limit)


def _reservations_in_statuses(item_id, statuses, limit):
    rows = (
        BorrowRequestItem.objects
        .filter(item_id=item_id, borrow_request__status__in=statuses)
        .values(
            'quantity',
            'borrow_request__ref_number',
            'borrow_request__status',
            'borrow_request__date_needed',
            'borrow_request__return_date',
        )[:limit]
    )
    out = []
    for r in rows:
        dn = r['borrow_request__date_needed']
        rd = r['borrow_request__return_date']
        out.append({
            'qty':         float(r['quantity']),
            'ref':         r['borrow_request__ref_number'],
            'status':      r['borrow_request__status'],
            'date_needed': dn.strftime('%Y-%m-%d') if dn else '',
            'return_date': rd.strftime('%Y-%m-%d') if rd else '',
        })
    return out