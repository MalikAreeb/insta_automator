#!/bin/bash

# Get the directory where this script is located
cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Check if this is first run
if [ ! -d "venv" ]; then
    clear
    echo "========================================"
    echo "   FIRST TIME SETUP"
    echo "========================================"
    echo ""
    echo "This will install everything needed..."
    echo ""
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR] Python 3 is not installed!${NC}"
        echo ""
        echo "Please install Python 3.8+ from:"
        echo "https://python.org"
        echo ""
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo -e "${GREEN}[OK] Python found${NC}"
    echo ""
    
    # Create virtual environment
    echo "[1/3] Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}[OK] Virtual environment created${NC}"
    echo ""
    
    # Install packages
    echo "[2/3] Installing Python packages..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install flask flask-cors selenium webdriver-manager pdfplumber werkzeug
    echo -e "${GREEN}[OK] Packages installed${NC}"
    echo ""
    
    # Check Chrome
    echo "[3/3] Checking Chrome browser..."
    if ! command -v google-chrome &> /dev/null && ! command -v chromium-browser &> /dev/null; then
        echo -e "${RED}[WARNING] Chrome not found!${NC}"
        echo ""
        echo "The bot needs Google Chrome to work."
        echo "Download from: https://www.google.com/chrome/"
        echo ""
        read -p "Press Enter after installing Chrome..."
    else
        echo -e "${GREEN}[OK] Chrome found${NC}"
    fi
    
    echo ""
    echo "========================================"
    echo "   SETUP COMPLETE!"
    echo "========================================"
    echo ""
    echo "The bot will now start..."
    sleep 2
fi

# Run the bot
clear
echo "========================================"
echo "   🤖 E-INSTA FEEDBACK BOT"
echo "========================================"
echo ""
echo "📍 Dashboard: http://localhost:5001"
echo "⚠️  DO NOT CLOSE THIS TERMINAL!"
echo ""
echo "Starting bot..."
echo ""

source venv/bin/activate

# Open browser after 2 seconds
(sleep 2 && open http://localhost:5001) &

# Run the bot
python3 app.py

echo ""
echo "Bot stopped. You can close this window."
read -p "Press Enter to exit..."