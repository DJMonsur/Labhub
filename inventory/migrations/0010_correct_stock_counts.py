"""
Correct stock counts after the stock-lifecycle change.

Before this change, approval PATCHed `available_count` down immediately, and
the manual "borrow entry" endpoint deducted too, so the same units could get
consumed twice (e.g. alcohol showing -1 of 4). Now approval only reserves:
`available_count` moves only when an item is actually handed out (status
'borrowed') and is restored on return.

This migration recomputes every record so existing data matches the new rule:

    available_count = max(0, item_count − quantity currently out 'borrowed')

Works across SQLite, MySQL, and PostgreSQL (raw SQL; the legacy tables are
unmanaged).
"""

from django.db import migrations


# `inventory_record` holds one row per item×location; the item's current on-hand
# is the physical count minus anything that is actually out right now.
#
# The "don't go below zero" clamp is spelled differently per engine:
#   SQLite/MySQL: scalar MAX(0, x) works.
#   PostgreSQL:   MAX is only an aggregate — the scalar form is GREATEST(0, x).
# The vendor is substituted at apply time (see rebaseline_stock below).
REBASELINE_TEMPLATE = """
UPDATE inventory_record
SET available_count = {scalar_max}(0,
    COALESCE((SELECT item.item_count FROM item
              WHERE item.item_id = inventory_record.item_id), 0)
  - COALESCE((SELECT SUM(borrow_request_item.quantity)
              FROM borrow_request_item
              JOIN borrow_request
                   ON borrow_request.id = borrow_request_item.borrow_request_id
              WHERE borrow_request_item.item_id = inventory_record.item_id
                AND borrow_request.status = 'borrowed'), 0))
"""


def rebaseline_stock(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    scalar_max = 'GREATEST' if vendor == 'postgresql' else 'MAX'
    schema_editor.execute(REBASELINE_TEMPLATE.format(scalar_max=scalar_max))


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_decimal_quantities'),
    ]

    operations = [
        migrations.RunPython(rebaseline_stock, migrations.RunPython.noop,
                             atomic=True),
    ]