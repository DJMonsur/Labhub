"""
Creates the tables that biology_lab_lims.sql normally provides.

Most models in this app are `managed = False`, meaning Django reads them but
never creates them — on MySQL they come from importing biology_lab_lims.sql.
That's fine for MySQL, but it means a SQLite database would come up completely
empty and every page would fail with "no such table".

This migration fills that gap. It runs ONLY on SQLite and does nothing at all
on MySQL, so the original setup path is untouched.
"""

from django.db import migrations


SQLITE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS location (
        location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        location_name VARCHAR(120) NOT NULL,
        building      VARCHAR(80),
        room_code     VARCHAR(30)
    )""",
    """
    CREATE TABLE IF NOT EXISTS item_type (
        type_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        type_label VARCHAR(60) NOT NULL UNIQUE,
        category   VARCHAR(40) NOT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS user (
        user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name     VARCHAR(100) NOT NULL,
        user_email    VARCHAR(150) NOT NULL UNIQUE,
        user_role     VARCHAR(20)  NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at    DATETIME     NOT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS item (
        item_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name        VARCHAR(200) NOT NULL,
        type_id          INTEGER      NOT NULL REFERENCES item_type(type_id),
        item_count       INTEGER      NOT NULL DEFAULT 0,
        unit             VARCHAR(20),
        item_description TEXT,
        is_borrowable    BOOL         NOT NULL DEFAULT 1,
        is_visible       BOOL         NOT NULL DEFAULT 1
    )""",
    """
    CREATE TABLE IF NOT EXISTS inventory_record (
        record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER  NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
        location_id     INTEGER  NOT NULL REFERENCES location(location_id),
        available_count INTEGER  NOT NULL DEFAULT 0,
        last_updated    DATETIME NOT NULL,
        UNIQUE (item_id, location_id)
    )""",
    """
    CREATE TABLE IF NOT EXISTS borrow_record (
        borrow_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id           INTEGER NOT NULL REFERENCES user(user_id),
        item_id           INTEGER NOT NULL REFERENCES item(item_id),
        location_id       INTEGER NOT NULL REFERENCES location(location_id),
        quantity_borrowed INTEGER NOT NULL DEFAULT 1,
        status            VARCHAR(20) NOT NULL DEFAULT 'pending',
        borrow_date       DATETIME,
        return_date       DATETIME,
        due_date          DATE,
        notes             TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS inventory_log (
        log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES user(user_id),
        item_id     INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
        action_type VARCHAR(30) NOT NULL,
        old_value   TEXT,
        new_value   TEXT,
        timestamp   DATETIME NOT NULL
    )""",
]


def create_sqlite_tables(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        return  # MySQL gets these tables from biology_lab_lims.sql
    with schema_editor.connection.cursor() as cursor:
        for statement in SQLITE_TABLES:
            cursor.execute(statement)


def drop_sqlite_tables(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        return
    tables = ['inventory_log', 'borrow_record', 'inventory_record',
              'item', 'user', 'item_type', 'location']
    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_borrowrecord_inventorylog_inventoryrecord_item_and_more'),
    ]

    operations = [
        migrations.RunPython(create_sqlite_tables, drop_sqlite_tables),
    ]
