#!/bin/bash
# VisaDesk Launcher — double-click this file to start the app

cd "$(dirname "$0")"

echo "=============================="
echo "  Starting VisaDesk..."
echo "=============================="
echo ""

# Find python3
PYTHON=$(which python3)
if [ -z "$PYTHON" ]; then
    echo "Python 3 not found. Please install it from https://www.python.org/downloads/"
    echo "Press any key to exit..."
    read -n 1
    exit 1
fi

echo "Using Python: $PYTHON"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Setting up virtual environment (first time only)..."
    "$PYTHON" -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.deps_installed" ]; then
    echo "Installing dependencies (first time only)..."
    pip install -r requirements.txt
    touch venv/.deps_installed
fi

# Initialize database if needed
if [ ! -f "visadesk.db" ]; then
    echo "Setting up database..."
    python seed.py
fi

echo ""
echo "=============================="
echo "  VisaDesk is running!"
echo "  Open: http://localhost:9090"
echo "  Login: admin / admin123"
echo "=============================="
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

# Open browser automatically
open http://localhost:9090 &

# Start the app
python app.py
