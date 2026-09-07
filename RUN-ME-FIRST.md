# How to run Lab Hub

## The short version

**Windows:** double-click **`START-WINDOWS.bat`**

**Mac / Linux:** open Terminal in this folder and run:

```bash
chmod +x start-mac-linux.sh    # first time only
./start-mac-linux.sh
```

That's it. The first run takes a few minutes while it installs things. Every
run after that takes about five seconds. Your browser opens automatically at
`http://127.0.0.1:8000`.

Sign in with any of these:

| Username   | Password       | What you can see                      |
|------------|----------------|---------------------------------------|
| `labstaff` | `labpass123`   | Inventory + dashboard                 |
| `itstaff`  | `itpass123`    | Everything, including Diagnostics     |
| `student`  | `studpass123`  | Inventory + borrowing only            |

To stop the server: close the window (Windows) or press `Ctrl+C` (Mac/Linux).

---

## About the ".exe"

I couldn't make you a real `.exe` — building a Windows executable has to be done
*on* Windows, and I'm working on Linux. But `START-WINDOWS.bat` is the same
experience: double-click, it runs. Windows may show a blue "Windows protected
your PC" box the first time because the file isn't signed — click **More info**
→ **Run anyway**.

If you genuinely want a single `.exe` file, you can build one yourself on a
Windows machine after running the launcher once:

```
venv\Scripts\pip install pyinstaller
venv\Scripts\pyinstaller --onefile --name LabHub manage.py
```

Honestly though, it's not worth it. A Django project isn't really a desktop
app — it's a web server plus a database plus templates, and bundling all of it
into one file causes more problems than it solves. The `.bat` file is the right
tool here.

---

## What the launcher actually does

Nothing magic, just the five steps you'd otherwise type by hand:

1. Checks Python is installed
2. Creates a `venv` folder (an isolated space for this project's packages, so
   it can't break anything else on your computer)
3. Installs the packages from `requirements.txt`
4. Creates your `.env` config file with a freshly generated secret key, then
   builds the database and loads the lab inventory
5. Starts the server and opens your browser

Steps 2–4 only happen once. After that it skips straight to step 5.

---

## What changed to make this work

The project previously needed two things set up *before* it would run at all.
Both are now optional.

**MySQL is no longer required.** The app defaults to SQLite, which is a database
that lives in a single file (`db.sqlite3`) and needs no installation. Nothing
about the app changes — same models, same queries, same features.

To use MySQL instead, set `DB_ENGINE=mysql` in `.env` and fill in your
credentials, then import `biology_lab_lims.sql` as described in `SETUP.md`.

**Google sign-in is no longer required.** Previously you could not log in
without creating a Google Cloud project first, because the app crashed if
`GOOGLE_CLIENT_ID` was missing. Now it falls back to username/password, and
the Google button appears automatically once you fill in
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.

---

## Step-by-step, if you'd rather do it manually

<details>
<summary>Windows</summary>

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
</details>

<details>
<summary>Mac / Linux</summary>

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
</details>

Then open `http://127.0.0.1:8000`.

---

## Useful commands

Run these with the venv activated (`venv\Scripts\activate` on Windows,
`source venv/bin/activate` on Mac/Linux).

| Command | What it does |
|---|---|
| `python manage.py seed_demo` | Reload inventory + demo accounts. Safe to re-run — it never deletes or overwrites. |
| `python manage.py createsuperuser` | Make your own admin account |
| `python manage.py runserver 8080` | Use a different port if 8000 is busy |
| `python manage.py check --deploy` | Security audit before going live |

**Starting completely over:** delete `db.sqlite3` and run the launcher again.
It rebuilds the database and reloads all 547 items from scratch.

---

## If something goes wrong

**"Python is not installed"** — install from
[python.org/downloads](https://www.python.org/downloads/) and make sure you tick
**Add Python to PATH** on the first screen. That checkbox is easy to miss and is
the cause of most of these.

**"Windows protected your PC"** — click *More info* → *Run anyway*. It appears
because the file isn't code-signed, not because anything is wrong with it.

**`mysqlclient` fails to install** — expected on Windows, and harmless. The
launcher notices, retries without it, and carries on. You only need
`mysqlclient` if you're using MySQL.

**"That port is already in use"** — either the server is already running in
another window, or something else has port 8000. Try
`python manage.py runserver 8080` and open `http://127.0.0.1:8080`.

**The page loads but has no styling** — you opened `index.html` directly as a
file instead of going through the server. Use `http://127.0.0.1:8000`.

**Login says the credentials are wrong** — run `python manage.py seed_demo` to
recreate the accounts, or make your own with
`python manage.py createsuperuser`.

---

Ready to put this on a real domain? See **`DEPLOYMENT.md`**.
