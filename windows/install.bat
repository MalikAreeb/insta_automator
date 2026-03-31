@echo off
title E-Insta Feedback Bot
color 0A
cd /d "%~dp0"

:: Check if this is first run (venv doesn't exist)
if not exist "venv\" goto setup

:: ========================================
:: RUN THE BOT
:: ========================================
:run
cls
echo ========================================
echo   🤖 E-INSTA FEEDBACK BOT
echo ========================================
echo.
echo 📍 Dashboard: http://localhost:5001
echo ⚠️  DO NOT CLOSE THIS WINDOW!
echo.
echo Starting bot...
echo.

:: Open browser after 2 seconds
start /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5001"

:: Activate virtual environment and run
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    venv\Scripts\python app.py
) else (
    python app.py
)

:: Bot stopped
echo.
echo Bot stopped. You can close this window.
echo.
pause
goto :eof

:: ========================================
:: FIRST TIME SETUP
:: ========================================
:setup
cls
echo ========================================
echo   FIRST TIME SETUP
echo ========================================
echo.
echo This will install everything needed...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed!
    echo.
    echo Please install Python 3.8+ from:
    echo https://python.org
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    echo After installing Python, run this file again.
    echo.
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] Python %PYTHON_VER% found
echo.

:: Create virtual environment
echo [1/3] Creating virtual environment...
if exist "venv\" rmdir /s /q venv
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created
echo.

:: Install packages
echo [2/3] Installing Python packages (this may take a minute)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install flask flask-cors selenium webdriver-manager pdfplumber werkzeug
if errorlevel 1 (
    echo [WARNING] Some packages had issues, but continuing...
)
echo [OK] Packages installed
echo.

:: Check Chrome
echo [3/3] Checking Chrome browser...
where chrome >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Chrome not found!
    echo.
    echo The bot needs Google Chrome to work.
    echo.
    echo Download Chrome from: https://www.google.com/chrome/
    echo.
    echo After installing Chrome, run this file again.
    echo.
    pause
    exit /b 1
) else (
    echo [OK] Chrome found
)

echo.
echo ========================================
echo   SETUP COMPLETE!
echo ========================================
echo.
echo The bot will now start...
timeout /t 2 /nobreak >nul
goto run