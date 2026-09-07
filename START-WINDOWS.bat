@echo off
REM ===========================================================================
REM  Lab Hub - Windows launcher
REM
REM  Double-click this file. It sets everything up the first time and just
REM  starts the server every time after that.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo   ============================================
echo     Lab Hub - PSHS-CARC Biology Laboratory
echo   ============================================
echo.

REM --- 1. Find Python ------------------------------------------------------
set PY=
python --version >nul 2>&1 && set PY=python
if not defined PY (
    py --version >nul 2>&1 && set PY=py
)
if not defined PY (
    echo   [X] Python is not installed.
    echo.
    echo   Install it from:  https://www.python.org/downloads/
    echo   IMPORTANT: tick "Add Python to PATH" on the first install screen,
    echo   then run this file again.
    echo.
    pause
    exit /b 1
)
echo   [1/5] Python found.

REM --- 2. Virtual environment ----------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo   [2/5] Creating virtual environment - one moment...
    %PY% -m venv venv
    if errorlevel 1 (
        echo   [X] Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo   [2/5] Virtual environment ready.
)
set VPY=venv\Scripts\python.exe

REM --- 3. Dependencies -----------------------------------------------------
REM  A marker file records that install already succeeded, so restarts are fast.
if not exist "venv\.installed" (
    echo   [3/5] Installing packages - this takes a few minutes the first time...
    %VPY% -m pip install --upgrade pip --quiet
    %VPY% -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo.
        echo   [!] Some packages failed. Retrying without MySQL support,
        echo       which this project does not need by default...
        findstr /v /c:"mysqlclient" requirements.txt > requirements.tmp
        %VPY% -m pip install -r requirements.tmp --quiet
        del requirements.tmp
        if errorlevel 1 (
            echo   [X] Install failed. Scroll up for the reason.
            pause
            exit /b 1
        )
    )
    echo ok > venv\.installed
) else (
    echo   [3/5] Packages already installed.
)

REM --- 4. Config + database -------------------------------------------------
if not exist ".env" (
    echo   [4/5] Creating .env with a fresh secret key...
    copy /y ".env.example" ".env" >nul
    %VPY% -c "import secrets,pathlib; p=pathlib.Path('.env'); t=p.read_text(); p.write_text(t.replace('change-this-to-a-long-random-string', secrets.token_urlsafe(64)))"
) else (
    echo   [4/5] Config found.
)

set FRESH=0
if not exist "db.sqlite3" set FRESH=1

%VPY% manage.py migrate --noinput >nul 2>&1
if errorlevel 1 (
    echo   [X] Database setup failed. Running again to show the error:
    %VPY% manage.py migrate
    pause
    exit /b 1
)

if "!FRESH!"=="1" (
    echo         Loading the lab inventory...
    %VPY% manage.py seed_demo
)

REM --- 5. Go ---------------------------------------------------------------
echo   [5/5] Starting the server.
echo.
echo   ============================================
echo     Open:  http://127.0.0.1:8000
echo.
echo     Sign in with:
echo       labstaff / labpass123     (lab personnel)
echo       itstaff  / itpass123      (IT personnel)
echo       student  / studpass123    (student)
echo.
echo     Close this window to stop the server.
echo   ============================================
echo.

start "" http://127.0.0.1:8000
%VPY% manage.py runserver

pause
