#!/bin/bash
# Clean and restart script for finance tracker

echo "🧹 Cleaning up cached files..."

# Kill any running Flask instances
echo "Stopping any running Flask servers..."
pkill -f "python app.py" || echo "No Flask servers running"

# Clear all __pycache__ directories
echo "Clearing Python cache files..."
find . -name "__pycache__" -type d -exec rm -rf {} +
find . -name "*.pyc" -delete

# Clear Flask session files if they exist
if [ -d "flask_session" ]; then
    echo "Clearing Flask session files..."
    rm -rf flask_session/*
fi

# Remove .DS_Store files on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Removing .DS_Store files..."
    find . -name ".DS_Store" -delete
fi

# Set environment variables
export FLASK_ENV=development
export FLASK_DEBUG=1
export FLASK_APP=app.py

echo "🔄 Restarting virtual environment..."
# Deactivate current venv if active
if [[ -n "$VIRTUAL_ENV" ]]; then
    echo "Deactivating current virtual environment: $VIRTUAL_ENV"
    deactivate
fi

# Determine the correct virtual environment
if [ -d "venv_new" ]; then
    VENV="venv_new"
elif [ -d "venv" ]; then
    VENV="venv"
else
    echo "❌ Error: No virtual environment found. Please create one first."
    exit 1
fi

echo "Activating $VENV environment..."
source "$VENV/bin/activate"

# Run diagnostics
echo "🔍 Running server diagnostics..."
python debug_server_status.py

# Start the server
echo "🚀 Starting Flask development server..."
python app.py

# Note: This last command will keep the script running until the server is stopped 