"""
Migrate the quantity columns to decimal so mass/volume items (kg, mL, L, ...)
can be tracked and borrowed fractionally (1.5 kg, 0.5 kg, ...).

Django-managed tables (`borrow_request_item`) are altered by the framework.
The legacy `managed = False` tables (item, inventory_record, borrow_record) are
not touched by makemigrations, so their columns are updated with raw SQL here:

  • MySQL      → ALTER TABLE ... MODIFY col DECIMAL(12,3)
  • SQLite     → no schema change needed. SQLite column types are loose
                 affinity hints; a REAL such as 1.5 is stored fine in an
                 INTEGER-affinity column and every fractional read/write works.
"""

from django.db import migrations, models


MYSQL_ALTERS = [
    ('item',              'item_count',        'DECIMAL(12,3) NOT NULL DEFAULT 0'),
    ('inventory_record',  'available_count',   'DECIMAL(12,3) NOT NULL DEFAULT 0'),
    ('borrow_record',     'quantity_borrowed', 'DECIMAL(12,3) NOT NULL DEFAULT 1'),
]


def alter_mysql_columns(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    with schema_editor.connection.cursor() as cursor:
        for table, column, definition in MYSQL_ALTERS:
            cursor.execute(
                f'ALTER TABLE `{table}` MODIFY `{column}` {definition}'
            )


def reverse_alters(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    reverse = [
        ('item', 'item_count', 'INT NOT NULL DEFAULT 0'),
        ('inventory_record', 'available_count', 'INT NOT NULL DEFAULT 0'),
        ('borrow_record', 'quantity_borrowed', 'INT NOT NULL DEFAULT 1'),
    ]
    with schema_editor.connection.cursor() as cursor:
        for table, column, definition in reverse:
            cursor.execute(
                f'ALTER TABLE `{table}` MODIFY `{column}` {definition}'
            )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_borrowrequestitem_qty'),
    ]

    operations = [
        migrations.AlterField(
            model_name='borrowrequestitem',
            name='quantity',
            field=models.DecimalField(decimal_places=3, max_digits=12),
        ),
        migrations.AlterField(
            model_name='borrowrequestitem',
            name='missing_qty',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name='borrowrequestitem',
            name='damaged_qty',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
        migrations.RunPython(alter_mysql_columns, reverse_alters),
    ]