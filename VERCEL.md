# Deploying on Vercel (serverless, auto-deploy from GitHub)

Vercel is the recommend-alternative host if you want the site to deploy itself
every time you push to GitHub — no server to babysit, free tier is fine for a
school LIMS. It uses **zero-config Django support** (Vercel detects `manage.py`),
a **Neon Postgres** database, and this repo already contains everything
(`vercel.json`, the Postgres migration branch, the seed command).

> The Railway path (see `DEPLOYMENT.md`) still works exactly as before; these
> are two independent hosting options.

## How it works (30-second version)

1. You push to GitHub.
2. Vercel builds the project: installs `requirements.txt`, runs the
   `buildCommand` from `vercel.json` — `collectstatic`, `migrate`, `seed_demo`.
3. Your `lims_project.wsgi` (already set as `WSGI_APPLICATION`) becomes a
   serverless function that Vercel scales per-request.
4. Static files (`collectstatic` output) are served from Vercel's CDN.
5. First deploy seeds the Neon database from the committed
   `biology_lab_lims.sql`; later deploys skip it (seed_demo fast-path).
6. Environment variables (Neon `DATABASE_URL` etc.) are injected into the build
   *and* the running functions by the Neon + Vercel integrations.

## Step 1 — Create a Neon Postgres database

The app's production database is **PostgreSQL, not MySQL**: Vercel's build
image cannot compile `mysqlclient` (no Linux wheel), so MySQL cannot run there.

- Go to https://neon.tech, create an account, create a project (any region).
- In Vercel's dashboard: **Project → Integrations → Browse → Neon**, install it,
  and connect it to your Vercel project. This **injects `DATABASE_URL`
  automatically** — you do not need to copy the connection string.
- (`DATABASE_URL` alone also works — the app parses any
  `postgresql://user:pass@host:port/dbname?sslmode=require` string.)

## Step 2 — Import the GitHub repo into Vercel

- On vercel.com: **Add New → Project → Import Git Repository** → pick the repo
  (it appears after a `git push` to GitHub).
- Vercel auto-detects Django from `manage.py`. Leave the framework as-is.
- Set the project **Environment Variables**:

  | Variable | Value |
  |---|---|
  | `DJANGO_SECRET_KEY` | any long random string (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
  | `DJANGO_DEBUG` | `False` |
  | `DJANGO_ALLOWED_HOSTS` | `your-project.vercel.app,www.your-domain.com` |
  | `CSRF_TRUSTED_ORIGINS` | `https://your-project.vercel.app,https://www.your-domain.com` |
  | `CORS_ALLOW_ALL_ORIGINS` | `False` |
  | `SEED_DEMO_ACCOUNTS` | leave **unset** (demo logins are blocked in production unless you set `true`) |

- Click **Deploy**. The first build runs `migrate` + `seed_demo` against Neon,
  so the site works the moment the deploy finishes. Every later push to the
  default branch re-deploys automatically.

## Step 3 — (Optional) Google sign-in

After you have a real domain, create OAuth credentials at
console.cloud.google.com and add the redirect URIs:

- `https://your-project.vercel.app/accounts/google/login/callback/`
- `https://www.your-domain.com/accounts/google/login/callback/`

Then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (and optionally
`ALLOWED_EMAIL_DOMAINS`) in the Vercel project's environment variables.

## Notes that will save you an hour

- **Demo accounts are production-blocked by default.** `seed_demo` seeds the
  500+ inventory items everywhere, but only creates `labstaff`/`itstaff`/`student`
  logins when `DJANGO_DEBUG=True` **or** `SEED_DEMO_ACCOUNTS=true`. For a real
  launch, create accounts with `python manage.py createsuperuser`
  (Vercel → Project → Terminal) instead of enabling demo passwords in prod.
- **The weekly report cron** uses `python manage.py generate_weekly_report`.
  Vercel doesn't run cron by itself — hook it to a scheduled job
  (GitHub Actions `schedule: cron`, or a small hosted cron service) hitting a
  Vercel function is not needed; run the management command via a scheduled
  GitHub Action on a checkout, or connect a cron host that runs it.
- **Neon scales to zero after 5 idle minutes.** Each request wakes the compute
  (~0.3–1s cold start). `CONN_MAX_AGE=0` + `CONN_HEALTH_CHECKS` in
  `settings.py` already handle dropped idle connections.
- **MySQL stays the local/original path.** Nothing about the MySQL or SQLite
  setups changed; Vercel is an *additional* deployment option.
- **`biology_lab_lims.sql` must stay next to `manage.py`** — it is the seed
  source and is committed, so it's on Vercel's build image automatically.

## Files involved

| File | What it does |
|---|---|
| `vercel.json` | build command: collectstatic → migrate → seed_demo |
| `lims_project/settings.py` | parses `DATABASE_URL` (Postgres), keeps sqlite/mysql paths |
| `inventory/migrations/0005_sqlite_tables.py` | PostgreSQL DDL branch for the legacy tables |
| `inventory/migrations/0010_correct_stock_counts.py` | vendor-safe `GREATEST`/`MAX` clamp |
| `inventory/management/commands/seed_demo.py` | fast-path skip + production demo-account guard |
| `requirements.txt` | adds `psycopg[binary]` (Postgres driver) |