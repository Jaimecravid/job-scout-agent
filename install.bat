@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   Job Scout Agent -- One-Click Installer
echo ============================================================
echo.

:: ---------------------------------------------------------------------------
:: STEP 1: Verify Python is installed and on PATH
:: ---------------------------------------------------------------------------
echo [1/4] Checking Python installation...
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  ERROR: Python was not found on this machine.
    echo.
    echo  Please install Python 3.10 or higher from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, check the box that says:
    echo    "Add python.exe to PATH"
    echo  Then run this installer again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  Found: %PYVER%
echo.

:: ---------------------------------------------------------------------------
:: STEP 2: Change into the project root (same folder as this .bat file)
:: ---------------------------------------------------------------------------
cd /d "%~dp0"

:: ---------------------------------------------------------------------------
:: STEP 3: Install Python dependencies from requirements.txt
:: ---------------------------------------------------------------------------
echo [2/4] Installing Python dependencies...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: pip install failed. Check your internet connection
    echo  and ensure requirements.txt is present in this folder.
    echo.
    pause
    exit /b 1
)
echo.
echo  Dependencies installed successfully.
echo.

:: ---------------------------------------------------------------------------
:: STEP 4: Create the data/ directory if it does not exist
:: ---------------------------------------------------------------------------
echo [3/4] Preparing data directory...
if not exist "data\" (
    mkdir data
    echo  Created: data\
) else (
    echo  Already exists: data\
)
echo.

:: ---------------------------------------------------------------------------
:: STEP 5: Register the hourly Task Scheduler entry (silent background runs)
:: ---------------------------------------------------------------------------
echo [4/4] Registering hourly background automation...
echo  (You may see a Windows permissions prompt -- click Yes to allow.)
echo.
python src\setup_scheduler.py
if errorlevel 1 (
    echo.
    echo  WARNING: Task Scheduler registration failed.
    echo  You can run it manually later with:
    echo    python src\setup_scheduler.py
    echo.
) else (
    echo.
    echo  Task Scheduler entry created. The agent will run every hour,
    echo  silently in the background, with no console window.
)

echo.
echo ============================================================
echo   Installation complete.
echo.
echo   Next step: open .env (copy from .env.example) and add
echo   your Gmail App Password, Gemini API Key, and optionally
echo   your Telegram Bot Token for mobile alerts.
echo ============================================================
echo.
pause