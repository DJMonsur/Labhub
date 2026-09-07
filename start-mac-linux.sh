#!/usr/bin/env bash
# ===========================================================================
#  Lab Hub - macOS / Linux launcher
#
#  Run:  ./start-mac-linux.sh
#  (first time only:  chmod +x start-mac-linux.sh)
# ===========================================================================

cd "$(dirname "$0")"

echo
echo "  ============================================"
echo "    Lab Hub - PSHS-CARC Biology Laboratory"
echo "  ============================================"
echo

# --- 1. Python -------------------------------------------------------------
PY=""
command -v python3 >/dev/null 2>&1 && PY=python3
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY=python
if [ -z "$PY" ]; then
    echo "  [X] Python 3 is not installed."
    echo "      macOS:  brew install python"
    echo "      Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi
echo "  [1/5] Python found."

# --- 2. Virtual environment ------------------------------------------------
if [ ! -x "venv/bin/python" ]; then
    echo "  [2/5] Creating virtual environment - one moment..."
    if ! "$PY" -m venv venv 2>/tmp/labhub_venv_err; then
        echo
        echo "  [X] Could not create the virtual environment."
        # On Debian/Ubuntu, venv ships as a separate package and this is
        # overwhelmingly the reason this step fails.
        if grep -qiE "ensurepip|python3-venv|No module named venv" /tmp/labhub_venv_err 2>/dev/null; then
            echo
            echo "      Your Linux is missing the venv package. Install it with:"
            echo
            echo "          sudo apt install python3-venv python3-pip"
            echo
            echo "      (Fedora: sudo dnf install python3-virtualenv)"
            echo "      Then run this script again."
        else
            cat /tmp/labhub_venv_err
        fi
        echo
        rm -f /tmp/labhub_venv_err
        exit 1
    fi
    rm -f /tmp/labhub_venv_err
else
    echo "  [2/5] Virtual environment ready."
fi
VPY="venv/bin/python"

# --- 3. Dependencies -------------------------------------------------------
if [ ! -f "venv/.installed" ]; then
    echo "  [3/5] Installing packages - takes a few minutes the first time..."
    "$VPY" -m pip install --upgrade pip --quiet
    if ! "$VPY" -m pip install -r requirements.txt; then
        echo
        echo "  [X] Package install failed - the reason is printed above."
        echo
        echo "      If it mentions a compiler, gcc, or Python.h, run:"
        echo "          sudo apt install python3-dev build-essential"
        echo "      then run this script again."
        echo
        exit 1
    fi
    touch venv/.installed
else
    echo "  [3/5] Packages already installed."
fi

# --- 4. Config + database --------------------------------------------------
if [ ! -f ".env" ]; then
    echo "  [4/5] Creating .env with a fresh secret key..."
    cp .env.example .env
    "$VPY" -c "import secrets,pathlib; p=pathlib.Path('.env'); p.write_text(p.read_text().replace('change-this-to-a-long-random-string', secrets.token_urlsafe(64)))"
else
    echo "  [4/5] Config found."
fi

FRESH=0
[ ! -f "db.sqlite3" ] && FRESH=1

if ! "$VPY" manage.py migrate --noinput >/dev/null 2>&1; then
    echo "  [X] Database setup failed. Running again to show the error:"
    "$VPY" manage.py migrate
    exit 1
fi

if [ "$FRESH" = "1" ]; then
    echo "        Loading the lab inventory..."
    "$VPY" manage.py seed_demo
fi

# --- 5. Go -----------------------------------------------------------------
echo "  [5/5] Starting the server."
echo
echo "  ============================================"
echo "    Open:  http://127.0.0.1:8000"
echo
echo "    Sign in with:"
echo "      labstaff / labpass123     (lab personnel)"
echo "      itstaff  / itpass123      (IT personnel)"
echo "      student  / studpass123    (student)"
echo
echo "    Press Ctrl+C to stop the server."
echo "  ============================================"
echo

( sleep 2; (command -v open >/dev/null && open http://127.0.0.1:8000) || \
           (command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8000) ) >/dev/null 2>&1 &

exec "$VPY" manage.py runserver
