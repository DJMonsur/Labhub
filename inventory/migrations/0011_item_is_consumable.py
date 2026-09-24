"""
0011_item_is_consumable.py

Adds an is_consumable flag to the unmanaged `item` table.

The `item` table is created outside Django (biology_lab_lims.sql on MySQL /
Postgres, migration 0005 on SQLite), so the column is added with raw SQL here
rather than a Django AddField. Unlike 0002 (is_visible), this migration runs
*after* the tables exist on every backend, so the ALTER applies everywhere:

  • MySQL    → ALTER TABLE item ADD COLUMN is_consumable TINYINT(1) ... (BOOL)
  • SQLite   → ALTER TABLE item ADD COLUMN ... (BOOL stays BOOL)
  • Postgres → ALTER TABLE item ADD COLUMN ... (native BOOLEAN)

It also back-fills the flag for pre-existing databases (already seeded, so
seed_demo's early-exit never re-runs): items whose type category is 'Material'
(Alcohol, PCR supplies, microbiological media) are consumables by convention.
Fresh databases get the same classification from seed_demo at insert time.

The column/table checks keep it safe to run against a database where the
column was already added by hand.
"""

from django.db import migrations


def _has_column(connection, table, column):
    with connection.cursor() as c:
        description = connection.introspection.get_table_description(c, table)
    return any(col.name == column for col in description)


def _table_exists(connection, table):
    with connection.cursor() as c:
        return table in connection.introspection.table_names(c)


def forward(apps, schema_editor):
    connection = schema_editor.connection
    if not _table_exists(connection, 'item'):
        return
    if not _has_column(connection, 'item', 'is_consumable'):
        with connection.cursor() as c:
            c.execute(
                "ALTER TABLE item ADD COLUMN is_consumable BOOL NOT NULL DEFAULT 0"
            )

    # Back-fill classification for already-seeded databases: Material category
    # (consumable / PCR supply / microbiological media) ⇒ consumable.
    with connection.cursor() as c:
        c.execute(
            "UPDATE item SET is_consumable = 1 "
            "WHERE is_consumable = 0 AND type_id IN ("
            "  SELECT type_id FROM item_type WHERE category = 'Material')"
        )


def backward(apps, schema_editor):
    connection = schema_editor.connection
    if not _table_exists(connection, 'item'):
        return
    if not _has_column(connection, 'item', 'is_consumable'):
        return
    with connection.cursor() as c:
        c.execute("ALTER TABLE item DROP COLUMN is_consumable")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0010_correct_stock_counts")]
    operations   = [migrations.RunPython(forward, backward)]