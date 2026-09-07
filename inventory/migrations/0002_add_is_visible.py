"""
0002_add_is_visible.py

Adds an is_visible column to the unmanaged `item` table.

The `item` table is created outside Django — by biology_lab_lims.sql on MySQL,
or by migration 0005 on SQLite. This migration therefore only has work to do on
MySQL, where the .sql file predates the column. On SQLite, 0005 creates the
table with is_visible already present, and `item` doesn't even exist yet at
this point, so the migration correctly does nothing.

The column check keeps it safe to run against a database where someone already
added the column by hand.
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
    if connection.vendor != 'mysql':
        return  # SQLite: handled by 0005_sqlite_tables
    if not _table_exists(connection, 'item'):
        return
    if _has_column(connection, 'item', 'is_visible'):
        return
    with connection.cursor() as c:
        c.execute("ALTER TABLE item ADD COLUMN is_visible TINYINT(1) NOT NULL DEFAULT 1")


def backward(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return
    if not _table_exists(connection, 'item'):
        return
    if not _has_column(connection, 'item', 'is_visible'):
        return
    with connection.cursor() as c:
        c.execute("ALTER TABLE item DROP COLUMN is_visible")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations   = [migrations.RunPython(forward, backward)]
