#!/bin/bash

# E-Insta Feedback Bot - ONE FILE DOES EVERYTHING
# Place this in the same folder as app.py

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

clear
echo "========================================"
echo "   🤖 E-INSTA FEEDBACK BOT"
echo "========================================"
echo ""

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo -e "${RED}❌ ERROR: app.py not found!${NC}"
    echo "Make sure this script is in the same folder as app.py"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# FIRST TIME SETUP (only runs if venv doesn't exist)
if [ ! -d "venv" ]; then
    echo -e "${BLUE}📦 FIRST TIME SETUP - Installing...${NC}"
    echo ""
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ ERROR: Python 3 not found!${NC}"
        echo "Install from: https://python.org"
        echo ""
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo -e "${GREEN}✅ Python: $(python3 --version)${NC}"
    echo ""
    
    # Create virtual environment
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo ""
    
    # Install packages
    echo "📦 Installing packages (this may take a minute)..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install flask flask-cors selenium webdriver-manager pdfplumber werkzeug
    echo ""
    
    # Check Chrome
    if ! command -v google-chrome &> /dev/null; then
        echo -e "${YELLOW}⚠️  WARNING: Google Chrome not found!${NC}"
        echo "Please install Chrome from: https://www.google.com/chrome/"
        echo ""
    else
        echo -e "${GREEN}✅ Chrome found${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}✅ SETUP COMPLETE!${NC}"
    echo ""
    sleep 2
    clear
fi

# START THE BOT
echo "========================================"
echo "   🤖 E-INSTA FEEDBACK BOT"
echo "========================================"
echo ""
echo -e "${GREEN}📍 Dashboard: http://localhost:5001${NC}"
echo -e "${YELLOW}⚠️  DO NOT CLOSE THIS TERMINAL!${NC}"
echo ""

# Activate virtual environment
source venv/bin/activate

# Open browser after 2 seconds
(sleep 2 && open http://localhost:5001) &

# Run the bot
python3 app.py

# If we get here, bot stopped
echo ""
echo -e "${RED}❌ Bot stopped${NC}"
read -p "Press Enter to exit..."