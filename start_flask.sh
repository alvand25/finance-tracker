#!/bin/bash

# Clear cache and start Flask development server
echo "Clearing Python cache..."
find . -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "*.pyc" -delete

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=development
export FLASK_DEBUG=1
export PORT=5004

echo "Starting Flask development server..."
if [ -d "venv_new" ]; then
    source venv_new/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "No virtual environment found. Using system Python."
fi

# Start the server
python app.py 