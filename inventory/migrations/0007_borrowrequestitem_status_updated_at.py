"""
Add BorrowRequestItem.status_updated_at and backfill it from the
MISSING/DAMAGED inventory logs.

status_updated_at records when lab personnel flagged an item missing/damaged
at return time. Reports anchor missing/damaged entries on this timestamp, so
an item marked today appears in today's report even when the borrow happened
earlier (date_needed falls outside the report window).

Existing flags were written together with a MISSING/DAMAGED InventoryLog whose
new_value text names the request ref, so we can recover the flag time and link
it back to the matching BorrowRequestItem.
"""

import re

from django.db import migrations, models


def backfill_status_updated_at(apps, schema_editor):
    """Link each MISSING/DAMAGED log to its BorrowRequestItem using raw SQL.

    The historical inventory_log model in migration state has no item_id
    column (migrations only define the Django models), but the actual tables
    came from biology_lab_lims.sql / migration 0005 and do carry item_id.
    BorrowRequest/BorrowRequestItem are Django-managed, so their columns match
    the model definitions here.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT item_id, timestamp, new_value FROM inventory_log "
            "WHERE action_type IN ('MISSING', 'DAMAGED')"
        )
        for item_id, ts, new_value in cursor.fetchall():
            m = re.search(r'\brequest\s+([A-Z0-9-]+)', new_value or '')
            if not m:
                continue
            cursor.execute(
                "UPDATE borrow_request_item "
                "SET status_updated_at = %s "
                "WHERE item_id = %s "
                "AND item_status IN ('missing', 'damaged') "
                "AND borrow_request_id = "
                "    (SELECT id FROM borrow_request WHERE ref_number = %s)",
                [ts, item_id, m.group(1)],
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_report_item_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequestitem',
            name='status_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_status_updated_at, noop),
    ]