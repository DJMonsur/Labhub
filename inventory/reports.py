"""
inventory/reports.py

Report generation shared by the Reports dashboard tab and the weekly
auto-report management command.

Reports an aggregate of four event classes over a [start, end] date window:
  • borrowed  — items taken out (BorrowRequest status approved/returned,
                anchored on date_needed)
  • missing   — units flagged missing at return (BorrowRequestItem.missing_qty)
  • damaged   — units flagged damaged at return  (BorrowRequestItem.damaged_qty)
  • added     — newly created items (InventoryLog 'ADD') plus restocks
                (InventoryLog 'RESTOCK'), anchored on log timestamp
"""

import datetime
from collections import defaultdict

from .models import BorrowRequest, BorrowRequestItem, InventoryLog


def _period_for(type_, today=None):
    """Return (start_date, end_date) for a report type. Weekly = Mon–today."""
    import datetime
    today = today or datetime.date.today()
    if type_ == 'daily':
        return today, today
    if type_ == 'weekly':
        start = today - datetime.timedelta(days=today.weekday())
        return start, today
    if type_ == 'monthly':
        start = today.replace(day=1)
        return start, today
    if type_ == 'yearly':
        start = today.replace(month=1, day=1)
        return start, today
    raise ValueError(f'Unknown report type: {type_}')


def _agg(defaultdict_of_itemdicts, entries):
    """entries: iterable of (item_id, item_name, category, quantity)."""
    for item_id, name, category, qty in entries:
        key = (item_id, name, category)
        d = defaultdict_of_itemdicts[key]
        d['item_id'] = item_id
        d['item_name'] = name
        d['category'] = category
        d['quantity'] = d.get('quantity', 0) + qty
    return defaultdict_of_itemdicts


def _category_of(item):
    try:
        return item.type.category
    except Exception:
        return 'Uncategorised'


def _borrowed_events(start, end):
    """Fulfilled borrows within the window, one row per request item."""
    qs = (
        BorrowRequest.objects
        .filter(status__in=('approved', 'returned'),
                date_needed__date__gte=start,
                date_needed__date__lte=end)
        .prefetch_related('items__item')
    )
    for br in qs:
        for ri in br.items.select_related('item__type').all():
            yield (ri.item_id, ri.item.item_name,
                   _category_of(ri.item), ri.quantity,
                   br.ref_number, br.borrower_name, br.date_needed.date().isoformat())


def _condition_events(start, end, condition):
    """Missing / damaged items from returned requests within the window.

    Anchored on when the item was flagged (BorrowRequestItem.status_updated_at,
    set at return time) rather than on date_needed, so an item marked today
    shows up in today's report even if it was borrowed earlier.

    Quantities come from missing_qty / damaged_qty so a partial return
    (e.g. 2 of 5 units missing) is reported correctly.
    """
    from django.db.models import Q

    flagged = Q(status_updated_at__date__gte=start,
                status_updated_at__date__lte=end)
    legacy = Q(status_updated_at__isnull=True,
               borrow_request__date_needed__date__gte=start,
               borrow_request__date_needed__date__lte=end)
    qs = (
        BorrowRequestItem.objects
        .filter(borrow_request__status='returned')
        .filter(flagged | legacy)
        .select_related('item__type', 'borrow_request')
    )
    for ri in qs:
        qty = ri.missing_qty if condition == 'missing' else ri.damaged_qty
        if not qty:
            continue
        br = ri.borrow_request
        yield (ri.item_id, ri.item.item_name,
               _category_of(ri.item), qty,
               br.ref_number, br.borrower_name, br.date_needed.date().isoformat())


def _added_events(start, end):
    """Newly created items (ADD) and restocks (RESTOCK), by log timestamp."""
    qs = (
        InventoryLog.objects
        .filter(action_type__in=('ADD', 'RESTOCK'),
                timestamp__date__gte=start,
                timestamp__date__lte=end)
        .select_related('item__type')
    )
    for log in qs:
        qty = _extract_qty(log.action_type, log.new_value)
        yield (log.item_id, log.item.item_name,
               _category_of(log.item), qty,
               log.action_type, log.timestamp.date().isoformat())


def _extract_qty(action_type, text):
    """Pull the quantity out of a log's new_value text.

    ADD:     "Created item 'X' with count 12 at location 'Y'."
    RESTOCK: "Restocked 12 pcs of 'X'."
    Defaults to 1 when the text can't be parsed (e.g. legacy rows).
    """
    import re
    if not text:
        return 1
    if action_type == 'ADD':
        m = re.search(r"with count (\d+)", text, re.IGNORECASE)
    else:  # RESTOCK
        m = re.search(r"Restocked (\d+)", text, re.IGNORECASE)
    try:
        return int(m.group(1)) if m else 1
    except (ValueError, IndexError):
        return 1


def generate_report_data(start, end):
    """Compile the full report data dict for a [start, end] window."""
    borrowed_sum = defaultdict(dict)
    missing_sum = defaultdict(dict)
    damaged_sum = defaultdict(dict)
    added_sum = defaultdict(dict)

    borrowed_lines = []
    missing_lines = []
    damaged_lines = []
    added_lines = []

    # Borrowed — summary + line items
    for item_id, name, cat, qty, ref, borrower, date in _borrowed_events(start, end):
        _agg(borrowed_sum, [(item_id, name, cat, qty)])
        borrowed_lines.append({
            'ref': ref, 'borrower_name': borrower, 'item_name': name,
            'quantity': qty, 'date': date,
        })

    # Missing / damaged — summary + line items
    for item_id, name, cat, qty, ref, borrower, date in _condition_events(start, end, 'missing'):
        _agg(missing_sum, [(item_id, name, cat, qty)])
        missing_lines.append({
            'ref': ref, 'borrower_name': borrower, 'item_name': name,
            'quantity': qty, 'date': date,
        })
    for item_id, name, cat, qty, ref, borrower, date in _condition_events(start, end, 'damaged'):
        _agg(damaged_sum, [(item_id, name, cat, qty)])
        damaged_lines.append({
            'ref': ref, 'borrower_name': borrower, 'item_name': name,
            'quantity': qty, 'date': date,
        })

    # Added — summary + line items (ADD = new item, RESTOCK = restocked)
    for item_id, name, cat, qty, action, date in _added_events(start, end):
        _agg(added_sum, [(item_id, name, cat, qty)])
        added_lines.append({
            'item_name': name, 'quantity': qty, 'date': date, 'action': action,
        })

    summary = {
        'borrowed': sorted(borrowed_sum.values(), key=lambda d: (-d['quantity'], d['item_name'])),
        'missing':  sorted(missing_sum.values(),  key=lambda d: (-d['quantity'], d['item_name'])),
        'damaged':  sorted(damaged_sum.values(),  key=lambda d: (-d['quantity'], d['item_name'])),
        'added':    sorted(added_sum.values(),    key=lambda d: (-d['quantity'], d['item_name'])),
    }

    totals = {
        'borrowed_qty': sum(d['quantity'] for d in summary['borrowed']),
        'borrowed_items': len(summary['borrowed']),
        'missing_qty': sum(d['quantity'] for d in summary['missing']),
        'missing_items': len(summary['missing']),
        'damaged_qty': sum(d['quantity'] for d in summary['damaged']),
        'damaged_items': len(summary['damaged']),
        'added_qty': sum(d['quantity'] for d in summary['added']),
        'added_items': len(summary['added']),
    }

    return {
        'summary': summary,
        'line_items': {
            'borrowed': borrowed_lines,
            'missing': missing_lines,
            'damaged': damaged_lines,
            'added': added_lines,
        },
        'totals': totals,
    }


def build_report_title(report_type):
    import datetime
    from .models import Report
    label = dict(Report.REPORT_TYPE_CHOICES).get(report_type, report_type)
    now = datetime.datetime.now()
    # Include the generation time so reports created the same day can be told apart.
    return f'{label} Report — {now.strftime("%B %d, %Y %I:%M %p")}'


def render_report_html(report):
    """Very small HTML document used by report_detail / PDF export."""
    data = report.data
    start = report.start_date
    end = report.end_date

    def section(title, rows, key, qty_key):
        totals = data.get('totals', {})
        qty = totals.get(qty_key, 0)
        heads = (
            '<th>Item</th><th>Category</th><th>Quantity</th>'
        ) if title in ('Borrowed', 'Missing', 'Damaged') else (
            '<th>Item</th><th>Category</th><th>Quantity</th>'
        )
        if not rows:
            return (
                f'<h3>{title} <span class="qty">({qty})</span></h3>'
                f'<p class="none">No {title.lower()} items in this period.</p>'
            )
        body = ''.join(
            f'<tr><td>{row["item_name"]}</td><td>{row["category"]}</td>'
            f'<td>{row["quantity"]}</td></tr>'
            for row in rows
        )
        return (
            f'<h3>{title} <span class="qty">({qty})</span></h3>'
            f'<table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table>'
        )

    data = report.data or {}
    summary = data.get('summary') or {}
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 24px; color: #14202b; }}
  h1 {{ font-size: 20px; margin-bottom: 2px; }}
  .sub {{ color: #5a7080; font-size: 13px; margin-bottom: 18px; }}
  h3 {{ font-size: 15px; border-bottom: 1px solid #dde6ec; padding-bottom: 4px; margin: 18px 0 8px; }}
  .qty {{ color: #5a7080; font-weight: 400; }}
  .none {{ color: #5a7080; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  td, th {{ border: 1px solid #dde6ec; padding: 5px 8px; text-align: left; }}
  th {{ background: #f0f4f7; }}
</style></head><body>
  <h1>{report.title}</h1>
  <div class="sub">{start.isoformat()} → {end.isoformat()} · generated {report.generated_at:%b %d, %Y %H:%M}</div>
  {section('Borrowed', summary.get('borrowed', []), 'b', 'borrowed_qty')}
  {section('Missing', summary.get('missing', []), 'm', 'missing_qty')}
  {section('Damaged', summary.get('damaged', []), 'd', 'damaged_qty')}
  {section('Added', summary.get('added', []), 'a', 'added_qty')}
</body></html>"""
    return html


def export_csv(report):
    """CSV export of the report summary sections."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    data = report.data
    writer.writerow(['Report', report.title])
    writer.writerow(['Period', f'{report.start_date.isoformat()} → {report.end_date.isoformat()}'])
    writer.writerow([])

    for label, key in (('Borrowed', 'borrowed'), ('Missing', 'missing'),
                       ('Damaged', 'damaged'), ('Added', 'added')):
        rows = data.get('summary', {}).get(key, [])
        writer.writerow([label])
        writer.writerow(['Item', 'Category', 'Quantity'])
        for row in rows:
            writer.writerow([row['item_name'], row['category'], row['quantity']])
        writer.writerow([])

    return buf.getvalue()