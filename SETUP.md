# PSHS-CARC LIMS — Setup Guide
# Asirit, Espallardo & Garcia (2025)
# ══════════════════════════════════════════════════════════════════

## Prerequisites
- Python 3.10 or higher
- MySQL 8.0 or MariaDB 10.6 (XAMPP / standalone install)
- pip

─────────────────────────────────────────────────────────────────
## STEP 1 — Clone the repo & create your own virtual environment
─────────────────────────────────────────────────────────────────

    git clone <repo-url>
    cd lims_django_project

    python -m venv venv
    venv\Scripts\activate          # Windows
    # source venv/bin/activate     # macOS / Linux

    pip install -r requirements.txt

If mysqlclient fails to install on Windows, try:
    pip install mysqlclient --only-binary :all:

─────────────────────────────────────────────────────────────────
## STEP 2 — Create the MySQL database and import the SQL file
─────────────────────────────────────────────────────────────────

Open MySQL shell (or phpMyAdmin → SQL tab):

    CREATE DATABASE lims_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

Then import the schema + seed data from the command line:

    mysql -u root -p lims_db < biology_lab_lims.sql

(Replace `root` with your MySQL username if different.)

─────────────────────────────────────────────────────────────────
## STEP 3 — Configure your environment variables
─────────────────────────────────────────────────────────────────

Copy the example env file and edit it with your own values:

    copy .env.example .env          # Windows
    # cp .env.example .env          # macOS / Linux

Open `.env` and set at minimum:

    DB_USER=root
    DB_PASSWORD=<your MySQL password>

Everything else in `.env.example` has working defaults for local dev.
`.env` is gitignored — never commit it, since it can contain real
credentials.

─────────────────────────────────────────────────────────────────
## STEP 4 — Run Django migrations
─────────────────────────────────────────────────────────────────

    python manage.py migrate

This applies all migrations in inventory/migrations/, including:
  • 0001_initial          — creates borrow_request + borrow_request_item
  • 0002_add_is_visible   — adds is_visible column to item
  • 0003_add_is_signed    — adds is_signed column to borrow_request

The other tables (item, inventory_record, etc.) already exist from
the SQL import in Step 2; Django reads them without touching them.

─────────────────────────────────────────────────────────────────
## STEP 5 — Start the development server
─────────────────────────────────────────────────────────────────

    python manage.py runserver

Open your browser at:
  • Inventory page   →  http://127.0.0.1:8000/
  • Lab Dashboard    →  http://127.0.0.1:8000/dashboard/
                         (also linked from the top bar on the inventory page)

─────────────────────────────────────────────────────────────────
## WHAT THE ENDPOINTS DO
─────────────────────────────────────────────────────────────────

Public (inventory page):
  GET  /api/inventory/
    Returns a JSON array of all visible inventory items with live
    available_count pulled from inventory_record.

  POST /api/borrow/
    Accepts the borrowing form data as JSON, validates quantities
    against available_count, saves to borrow_request +
    borrow_request_item. Returns { "ref": "BRW-XXXXXX", "status": "pending" }.

Lab Personnel Dashboard (/dashboard/):
  GET  /api/dashboard/item-types/        reference data for dropdowns
  GET  /api/dashboard/locations/         reference data for dropdowns

  GET    /api/dashboard/items/           all items, including hidden ones
  POST   /api/dashboard/items/           create a new item
  PATCH  /api/dashboard/items/<id>/      edit any field of an item
  DELETE /api/dashboard/items/<id>/      delete (blocked if borrow history exists)

  GET   /api/dashboard/requests/         all borrow requests (?status= filter)
  POST  /api/dashboard/requests/         manual entry, pre-approved
  PATCH /api/dashboard/requests/<id>/    edit dates/notes/status/is_signed
                                          (approving/returning auto-adjusts stock)

  GET  /api/dashboard/schedule/          ?year=YYYY&month=MM — Gantt timeline data

─────────────────────────────────────────────────────────────────
## PROJECT FILE STRUCTURE
─────────────────────────────────────────────────────────────────

lims_django_project/
├── manage.py
├── requirements.txt
├── biology_lab_lims.sql          ← run this once to seed the database
├── .env.example                  ← copy to .env and fill in your values
├── .gitignore
├── static/
│   ├── styles.css                ← inventory page styling
│   ├── dashboard.css             ← dashboard styling
│   └── images/
│       └── 404845-middle-removebg-preview.png
├── templates/
│   ├── index.html                ← inventory + borrowing page (served at /)
│   └── dashboard.html            ← lab personnel dashboard (served at /dashboard/)
├── lims_project/
│   ├── __init__.py
│   ├── settings.py               ← reads config from .env
│   ├── urls.py
│   └── wsgi.py
└── inventory/
    ├── __init__.py
    ├── models.py                 ← ORM models matching the SQL schema
    ├── views.py                  ← /api/inventory/ and /api/borrow/
    ├── dashboard_views.py        ← all /api/dashboard/ endpoints
    ├── urls.py
    └── migrations/
        ├── __init__.py
        ├── 0001_initial.py       ← creates borrow_request tables
        ├── 0002_add_is_visible.py
        └── 0003_add_is_signed.py

─────────────────────────────────────────────────────────────────
## TROUBLESHOOTING
─────────────────────────────────────────────────────────────────

"django.db.utils.OperationalError: (1045, Access denied)"
  → Wrong DB_USER / DB_PASSWORD in .env

"No module named 'MySQLdb'"
  → Run:  pip install mysqlclient

"No module named 'decouple'"
  → Run:  pip install python-decouple
    (or just re-run: pip install -r requirements.txt)

"Table 'lims_db.inventory_record' doesn't exist"
  → Re-run Step 2. The SQL file must be imported BEFORE Step 4.

Inventory grid says "Could not load inventory"
  → Django server is not running, or you opened the file directly
    instead of via http://127.0.0.1:8000/

Schedule tab on /dashboard/ shows "No borrow records for this period"
  → This is correct if no borrow_request rows fall within the month
    you're viewing. Use the month arrows (◀ ▶) to navigate, or create
    a test entry via "+ Manual Entry".

"django.core.exceptions.ImproperlyConfigured: No module named 'corsheaders'"
  → Run:  pip install django-cors-headers
