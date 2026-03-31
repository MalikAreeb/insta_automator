@echo off
title E-Insta Feedback Bot - One Click
color 0A
cd /d "%~dp0"

:: ========================================
:: ONE-CLICK AUTO SETUP & RUN
:: ========================================

echo.
echo ========================================
echo    🤖 E-INSTA FEEDBACK BOT
echo ========================================
echo.

:: Check if setup is needed
if not exist "venv\Scripts\python.exe" goto setup
call venv\Scripts\python -c "import flask, selenium, pdfplumber" >nul 2>&1
if errorlevel 1 goto setup

:: Everything is ready - run the bot
goto run

:setup
echo 📦 First time setup - Installing dependencies...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found!
    echo.
    echo Please install Python 3.8+ from python.org
    echo Make sure to check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ❌ Failed to create venv
    pause
    exit /b 1
)

:: Install packages
echo Installing packages (this may take a minute)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install flask flask-cors selenium webdriver-manager pdfplumber werkzeug --quiet

echo.
echo ✅ Setup complete!
timeout /t 2 /nobreak >nul

:run
cls
echo ========================================
echo    🤖 BOT IS RUNNING
echo ========================================
echo.
echo 📍 Dashboard: http://localhost:5001
echo ⚠️  DO NOT CLOSE THIS WINDOW!
echo.
echo Opening browser...
start /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5001"

:: Run the bot
call venv\Scripts\activate.bat 2>nul
python app.py

echo.
echo Bot stopped. Press any key to exit...
pause >nul