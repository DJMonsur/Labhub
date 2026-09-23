"""
Add BorrowRequestItem.missing_qty / damaged_qty and backfill from item_status.

Lets lab personnel record a PARTIAL return (e.g. 2 of 5 units missing) instead
of the all-or-nothing item_status flag. The report's missing/damaged sections
are driven by these quantities.

Existing flags are backfilled so a whole request previously flagged missing or
damaged simply moves all of its quantity into the matching column.
"""

from django.db import migrations, models
from django.db.models import F


def backfill_qty(apps, schema_editor):
    BorrowRequestItem = apps.get_model('inventory', 'BorrowRequestItem')
    BorrowRequestItem.objects.filter(item_status='missing').update(
        missing_qty=F('quantity'))
    BorrowRequestItem.objects.filter(item_status='damaged').update(
        damaged_qty=F('quantity'))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_borrowrequestitem_status_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequestitem',
            name='missing_qty',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='borrowrequestitem',
            name='damaged_qty',
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(backfill_qty, noop),
    ]