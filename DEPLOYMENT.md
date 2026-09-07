# Deploying Lab Hub to a real website

Right now the project runs on `python manage.py runserver`, which is a
development tool only — it's single-threaded, it serves static files insecurely,
and it's explicitly not meant to face the internet. This guide covers what to
change and where to host it.

Everything the app needs is already in this repo (`Procfile`, `build.sh`,
`requirements.txt` with gunicorn + WhiteNoise). What's left is choosing a host
and setting environment variables.

---

## The four pieces of a live Django site

Understanding this makes every host's docs make sense, because they all
assemble the same four things:

| Piece | What it does | What we use |
|---|---|---|
| **App server** | Runs your Python code, one process per request | gunicorn |
| **Database** | Stores items, requests, users — must live outside the app | MySQL |
| **Static files** | Serves your CSS/JS/images | WhiteNoise |
| **Domain + TLS** | A real address, over HTTPS | Handled by the host |

The dev server fakes all four badly. gunicorn + WhiteNoise handles two of them
properly, and a managed host gives you the other two.

---

## Before you deploy: five things that will break

These are the ones that bite everyone, in the order they'll bite you.

**1. `DEBUG=True` in production leaks everything.** Any error page shows your
settings, file paths, and SQL. Set `DJANGO_DEBUG=False`.

**2. With `DEBUG=False`, static files stop being served.** Django deliberately
refuses. This is why the site loads with zero CSS and everyone panics. WhiteNoise
(already wired into `settings.py`) fixes it, but you *must* run
`python manage.py collectstatic` on every deploy — `build.sh` does this for you.

**3. `ALLOWED_HOSTS` must list your real domain,** or every request returns a
400. Set `DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com`.

**4. `CSRF_TRUSTED_ORIGINS` must list it too, with the scheme.** Django 4 rejects
POSTs otherwise, so every borrow request submission fails with a CSRF error while
GETs look fine. Set `CSRF_TRUSTED_ORIGINS=https://yourdomain.com`.

**5. Google sign-in will reject your new domain** until you add it. In
[Google Cloud Console](https://console.cloud.google.com) → APIs & Services →
Credentials → your OAuth client, add:

- Authorised JavaScript origin: `https://yourdomain.com`
- Authorised redirect URI: `https://yourdomain.com/accounts/google/login/callback/`

Keep the `http://127.0.0.1:8000` entries so local development still works.

Also generate a fresh `DJANGO_SECRET_KEY` — never reuse the dev fallback:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Option A — Railway (recommended)

Best fit here: it provisions MySQL for you, reads the `Procfile` automatically,
and deploys on every git push. Roughly $5/month of usage credit on the hobby
plan.

**1.** Push this repo to GitHub (confirm `.env` is *not* committed — `.gitignore`
already covers it).

**2.** At [railway.app](https://railway.app) → New Project → Deploy from GitHub
repo → pick your repo.

**3.** In the same project: **+ New → Database → MySQL**. Railway creates it and
exposes variables like `MYSQLHOST`, `MYSQLUSER`, `MYSQLPASSWORD`.

**4.** On your app service → **Variables**, add:

```
DJANGO_SECRET_KEY   = <the key you generated>
DJANGO_DEBUG        = False
DJANGO_ALLOWED_HOSTS = ${{RAILWAY_PUBLIC_DOMAIN}}
CSRF_TRUSTED_ORIGINS = https://${{RAILWAY_PUBLIC_DOMAIN}}
DB_NAME     = ${{MySQL.MYSQL_DATABASE}}
DB_USER     = ${{MySQL.MYSQLUSER}}
DB_PASSWORD = ${{MySQL.MYSQLPASSWORD}}
DB_HOST     = ${{MySQL.MYSQLHOST}}
DB_PORT     = ${{MySQL.MYSQLPORT}}
GOOGLE_CLIENT_ID     = <your client id>
GOOGLE_CLIENT_SECRET = <your client secret>
```

The `${{...}}` syntax is Railway's variable reference — it wires the database
credentials across automatically, so you never paste a password.

**5.** Settings → Build Command: `./build.sh`. The `Procfile` already supplies
the start command.

**6.** Import your seed data once, from your own machine:

```bash
mysql -h <MYSQLHOST> -P <MYSQLPORT> -u <MYSQLUSER> -p <MYSQL_DATABASE> < biology_lab_lims.sql
```

**7.** Settings → Networking → Generate Domain, or add a custom one.

---

## Option B — Render

Same shape, but Render's free tier offers PostgreSQL rather than MySQL. Either
pay for an external MySQL (PlanetScale, Aiven) or switch the project to Postgres
— which is a small change: replace `mysqlclient` with `psycopg[binary]` in
`requirements.txt` and change `ENGINE` to `django.db.backends.postgresql`. Your
models and migrations work unchanged; the `.sql` seed file would need converting.

Web Service settings: build command `./build.sh`, start command
`gunicorn lims_project.wsgi:application`.

---

## Option C — PythonAnywhere (free, MySQL included)

The most forgiving option for a school project, and MySQL comes with it. The
trade-off is a manual reload after each change instead of git-push deploys, and
the free tier sleeps and gives you a `yourname.pythonanywhere.com` address.

Console → clone the repo → make a virtualenv → `pip install -r requirements.txt`.
Then Databases tab → create `lims_db`, import the `.sql`, and note the host
(`yourname.mysql.pythonanywhere-services.com`). Web tab → add a Django app,
point the WSGI config at `lims_project.wsgi`, set the static files mapping to
`/static/` → `/home/yourname/Labhub/staticfiles`, and put your environment
variables in the WSGI file or a `.env` beside `manage.py`.

---

## Option D — Your own VPS (full control)

A €4/month Hetzner or DigitalOcean box, if you want to actually learn the stack.
The architecture is: **nginx** (public, terminates HTTPS, serves static)
→ **gunicorn** (via a unix socket, runs Django) → **MySQL** (local).

```bash
sudo apt update && sudo apt install python3-venv nginx mysql-server \
     pkg-config python3-dev default-libmysqlclient-dev certbot python3-certbot-nginx

# app
cd /srv && sudo git clone <your-repo> labhub && cd labhub
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env      # fill in real values, DJANGO_DEBUG=False
python manage.py migrate && python manage.py collectstatic --noinput
```

Run gunicorn as a systemd service so it survives reboots —
`/etc/systemd/system/labhub.service`:

```ini
[Unit]
Description=Lab Hub
After=network.target

[Service]
User=www-data
WorkingDirectory=/srv/labhub
ExecStart=/srv/labhub/venv/bin/gunicorn lims_project.wsgi:application \
          --workers 3 --bind unix:/run/labhub.sock
Restart=always

[Install]
WantedBy=multi-user.target
```

`/etc/nginx/sites-available/labhub`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ { alias /srv/labhub/staticfiles/; }
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/labhub.sock;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/labhub /etc/nginx/sites-enabled/
sudo systemctl enable --now labhub && sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com   # free HTTPS
```

Certbot rewrites the nginx config for TLS and renews automatically.

---

## Getting a domain

`.com` runs ~$12/year (Namecheap, Porkbun, Cloudflare Registrar). For a school
project, `.dev` or `.app` are fine and force HTTPS by default.

Point it at your host with a DNS record: an **A record** to your VPS's IP, or a
**CNAME** to the hostname Railway/Render gives you. Propagation is usually
minutes, occasionally a few hours.

---

## Deploy checklist

- [ ] `.env` is gitignored and was never committed
- [ ] Fresh `DJANGO_SECRET_KEY` generated for production
- [ ] `DJANGO_DEBUG=False`
- [ ] `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` both list the real domain
- [ ] `collectstatic` runs on every deploy
- [ ] `migrate` runs on every deploy
- [ ] `biology_lab_lims.sql` imported once into the production database
- [ ] Google OAuth origin + redirect URI updated for the live domain
- [ ] `python manage.py check --deploy` reports no issues
- [ ] A superuser exists (`python manage.py createsuperuser`) for `/admin/`
- [ ] Database backups scheduled

Run the built-in audit before you announce the URL:

```bash
DJANGO_DEBUG=False python manage.py check --deploy
```

---

## Repo cleanup worth doing first

The project root currently holds `test.py` through `test9.py`, `test_copy.py`,
`test_flow.py`, and `fix.py` — one-off scratch scripts, plus `fix.py` which
rewrites `inventory/views.py` in place and would be genuinely dangerous to run by
accident. None of them are real tests. Move anything worth keeping into a
`scripts/` folder and delete the rest, so the repo you hand in reads clearly.

The `X3_Asirit, Espallardo, Garcia.pdf` and `biology_lab_lims.sql` are fine to
keep — the SQL file is your seed data and you'll need it on first deploy.
