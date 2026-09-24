"""
Creates the tables that biology_lab_lims.sql normally provides.

Most models in this app are `managed = False`, meaning Django reads them but
never creates them — on MySQL they come from importing biology_lab_lims.sql.
That's fine for MySQL, but it means a SQLite or PostgreSQL database would come
up completely empty and every page would fail with "no such table".

This migration fills that gap. It runs on SQLite and PostgreSQL (neither of
which has a .sql file to import) and does nothing at all on MySQL, so the
original setup path is untouched.
"""

from django.db import migrations


# ── SQLite ────────────────────────────────────────────────────────────────────
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

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# The same seven tables, spelled for PostgreSQL:
#   • SERIAL identity columns instead of AUTOINCREMENT
#   • "user" quoted — it is a reserved word in PostgreSQL
#   • TIMESTAMPTZ for datetimes, because Django writes tz-aware values with
#     USE_TZ=True and the ORM maps DateTimeField to timestamp with time zone
#   • NUMERIC(12,3) for quantity columns (Django 0009 made these DecimalField)
#   • BOOLEAN for the flag columns
#   • SMALLSERIAL for item_type.type_id — the model declares SmallAutoField
POSTGRES_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS location (
        location_id   SERIAL PRIMARY KEY,
        location_name VARCHAR(120) NOT NULL,
        building      VARCHAR(80),
        room_code     VARCHAR(30)
    )""",
    """
    CREATE TABLE IF NOT EXISTS item_type (
        type_id    SMALLSERIAL PRIMARY KEY,
        type_label VARCHAR(60) NOT NULL UNIQUE,
        category   VARCHAR(40) NOT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS "user" (
        user_id       SERIAL PRIMARY KEY,
        user_name     VARCHAR(100) NOT NULL,
        user_email    VARCHAR(150) NOT NULL UNIQUE,
        user_role     VARCHAR(20)  NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at    TIMESTAMPTZ  NOT NULL
    )""",
    """
    CREATE TABLE IF NOT EXISTS item (
        item_id          SERIAL PRIMARY KEY,
        item_name        VARCHAR(200) NOT NULL,
        type_id          SMALLINT     NOT NULL REFERENCES item_type(type_id),
        item_count       NUMERIC(12,3) NOT NULL DEFAULT 0,
        unit             VARCHAR(20),
        item_description TEXT,
        is_borrowable    BOOLEAN      NOT NULL DEFAULT TRUE,
        is_visible       BOOLEAN      NOT NULL DEFAULT TRUE
    )""",
    """
    CREATE TABLE IF NOT EXISTS inventory_record (
        record_id       SERIAL PRIMARY KEY,
        item_id         INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
        location_id     INTEGER NOT NULL REFERENCES location(location_id),
        available_count NUMERIC(12,3) NOT NULL DEFAULT 0,
        last_updated    TIMESTAMPTZ NOT NULL,
        UNIQUE (item_id, location_id)
    )""",
    """
    CREATE TABLE IF NOT EXISTS borrow_record (
        borrow_id         SERIAL PRIMARY KEY,
        user_id           INTEGER NOT NULL REFERENCES "user"(user_id),
        item_id           INTEGER NOT NULL REFERENCES item(item_id),
        location_id       INTEGER NOT NULL REFERENCES location(location_id),
        quantity_borrowed NUMERIC(12,3) NOT NULL DEFAULT 1,
        status            VARCHAR(20) NOT NULL DEFAULT 'pending',
        borrow_date       TIMESTAMPTZ,
        return_date       TIMESTAMPTZ,
        due_date          DATE,
        notes             TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS inventory_log (
        log_id      SERIAL PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES "user"(user_id),
        item_id     INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
        action_type VARCHAR(30) NOT NULL,
        old_value   TEXT,
        new_value   TEXT,
        timestamp   TIMESTAMPTZ NOT NULL
    )""",
]

LEGACY_TABLES = {
    'sqlite':     SQLITE_TABLES,
    'postgresql': POSTGRES_TABLES,
}

# Drop order matters — children before parents so FKs never block the DROP.
LEGACY_TABLE_NAMES = ['inventory_log', 'borrow_record', 'inventory_record',
                      'item', 'user', 'item_type', 'location']


def create_legacy_tables(apps, schema_editor):
    statements = LEGACY_TABLES.get(schema_editor.connection.vendor)
    if not statements:
        return  # MySQL gets these tables from biology_lab_lims.sql
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def drop_legacy_tables(apps, schema_editor):
    if schema_editor.connection.vendor not in LEGACY_TABLES:
        return
    with schema_editor.connection.cursor() as cursor:
        for table in LEGACY_TABLE_NAMES:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_borrowrecord_inventorylog_inventoryrecord_item_and_more'),
    ]

    operations = [
        migrations.RunPython(create_legacy_tables, drop_legacy_tables),
    ]
