# Labhub - Django LIMS

PSHS-CARC Biology Laboratory Information Management System. Single Django app (`inventory`) with JSON API backend and template-rendered frontend (`templates/index.html` + `templates/dashboard.html`, big inline-JS files).

## Quick Start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo        # loads 547 items + creates demo accounts
python manage.py runserver
```

Open `http://127.0.0.1:8000` (redirects to `/accounts/login/`). Demo accounts:
`labstaff/labpass123`, `itstaff/itpass123`, `student/studpass123`.

## Essential Commands

| Command | Purpose |
|---------|---------|
| `python manage.py seed_demo` | Idempotent, never deletes. **Requires `biology_lab_lims.sql` next to `manage.py` and migrations applied first** — it parses the SQL file with regex and `get_or_create`s everything |
| `python manage.py migrate` | Apply migrations (run before seed_demo on fresh DB) |
| `python manage.py generate_weekly_report` | Save a Mon→today report row (for cron/Railway cron) |
| `python manage.py runserver 8080` | Use different port if 8000 is busy |
| `DJANGO_DEBUG=False python manage.py check --deploy` | Pre-production security audit |

## Architecture

**Code layout — where the logic lives:**
- `lims_project/` - Django project config (settings, urls, wsgi). Settings read `.env` via `python-decouple`
- `inventory/views.py` - public API: `GET /api/inventory/`, `POST /api/borrow/`
- `inventory/dashboard_views.py` - ALL `/api/dashboard/*` endpoints (~1100 lines)
- `inventory/availability.py` - date-window booking capacity (approve-reserves logic)
- `inventory/units.py` - mass/volume unit families, display-unit conversion
- `inventory/reports.py` - report aggregation + export (shared with dashboard + weekly command)
- `inventory/signals.py` - auth glue: creates `UserProfile` on login, **auto-syncs Django `is_staff`/`is_superuser` from role** (`it_personnel` → `is_superuser=True`)

**Database dual-mode:**
- **SQLite** (default): zero setup, `db.sqlite3`. Legacy tables are created by migration 0005 (`RunPython`, SQLite-only)
- **MySQL**: set `DB_ENGINE=mysql` in `.env`, import `biology_lab_lims.sql`, and install `requirements-mysql.txt` — `mysqlclient` is deliberately NOT in `requirements.txt` (no Linux wheels, broke installs). Migration 0005 no-ops on MySQL

**Models (legacy = `managed = False`):** `Location`, `ItemType`, `LimsUser` (table `user`), `Item`, `InventoryRecord`, `BorrowRecord`, `InventoryLog` map to tables from the SQL file/0005 — Django reads them, never alters schema. **Django-managed** (created by migrations, `managed` default True): `UserProfile` (`user_profile`), `BorrowRequest`, `BorrowRequestItem`, `Report`. Migration 0009 switched counts to `Decimal(12,3)`; 0010 is a data-fix migration that recomputes `available_count`. New models you add will be Django-managed — give them a real migration; they will NOT be auto-created alongside the legacy tables on SQLite.

**API routes** (all under `/api/`; dashboard routes require `lab_personnel`/`it_personnel` via `dashboard_role_required` decorator):
- `GET inventory/` - visible items + live `available_count` + reservations
- `GET inventory/items/<id>/borrows/?date=YYYY-MM-DD` - date-aware borrow lookup (who/how many/time window; used by the details page's optional date field)
- `POST borrow/` - submit borrow request (`@csrf_exempt`, validates date-window capacity)
- `GET dashboard/item-types/`, `dashboard/locations/` - dropdown reference data
- `GET/POST dashboard/items/`, `PATCH/DELETE dashboard/items/<id>/`, `POST dashboard/items/<id>/restock/`
- `GET/POST dashboard/requests/`, `PATCH dashboard/requests/<id>/`
- `GET dashboard/schedule/?year=&month=` - Gantt timeline
- `GET/POST dashboard/reports/`, `GET/DELETE dashboard/reports/<id>/`, `GET dashboard/reports/<id>/export/?format=csv|html`
- `GET dashboard/diagnostics/` - IT personnel only (own check, not the decorator)

**Role system** (`UserProfile.role`): `student_teacher` (view + borrow only), `lab_personnel` (dashboard), `it_personnel` (dashboard + diagnostics + superuser). Google sign-in optional — blank `GOOGLE_CLIENT_ID`/`SECRET` falls back to username/password.

**Stock lifecycle (the core quirk):** approving a request *reserves* capacity (via `availability.date_capacity`) but does NOT change `available_count`. Deduction happens on hand-off (`approved → borrowed`), restoration on return. A request can only reach `borrowed` from `approved`. Partial returns via per-item `missing_qty`/`damaged_qty` (those units are not restored). `DELETE` on an item is blocked if it has any borrow history — hide with `is_visible` instead.

## Key Gotchas

1. **No tests exist.** No test suite, no CI, no linter config. Verify with `python manage.py check` and a manual smoke test via `runserver`
2. **Static files in production:** `collectstatic` on every deploy (build.sh does it). WhiteNoise serves them when `DEBUG=False`; hashed-manifest storage is production-only
3. **CSRF_TRUSTED_ORIGINS:** required for Django 4+ POSTs in production (borrow form silently fails otherwise). Set in `.env`
4. **`requirements.txt` is complete without mysqlclient** — don't add it back; use `requirements-mysql.txt` only for MySQL setups
5. **`scripts/_archive/fix.py` is dangerous**: rewrites `inventory/views.py` in place with no backup. Never run it or anything in `_archive/` (one-off scratch, imported by nothing)
6. **Reset DB:** delete `db.sqlite3` and re-run `seed_demo` (`.env`, `db.sqlite3`, `venv/` are all gitignored)

## Deployment

See `DEPLOYMENT.md` (Railway recommended). `Procfile` runs `gunicorn lims_project.wsgi` with a `release: python manage.py migrate` phase. `runtime.txt` pins `python-3.12.7` (local venv may be newer). `RUN-ME-FIRST.md` covers the launcher scripts (`START-WINDOWS.bat`, `start-mac-linux.sh`). Hosting docs: `SETUP.md` (original MySQL path) and `DEPLOYMENT.md` (production).

Production settings go in `.env`:
```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
```