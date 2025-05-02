#!/bin/bash

# Exit on error
set -e

echo "Setting up Finance Tracker..."

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if (( $(echo "$python_version < 3.8" | bc -l) )); then
    echo "Python version $python_version is compatible"
else
    echo "Python version $python_version is compatible"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv_new" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv_new
fi

# Activate virtual environment
source venv_new/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "Creating required directories..."
mkdir -p data uploads/receipts uploads/thumbnails logs debug_output credentials

# Check for Google Cloud Vision credentials
if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "Warning: GOOGLE_APPLICATION_CREDENTIALS environment variable not set"
    echo "Google Cloud Vision OCR will not be available"
    echo "To enable Google Cloud Vision:"
    echo "1. Create a service account and download credentials"
    echo "2. Run: python scripts/setup_google_vision.py --credentials=/path/to/credentials.json"
else
    echo "Found Google Cloud Vision credentials at: $GOOGLE_APPLICATION_CREDENTIALS"
fi

# Copy example environment file if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from example..."
    cp env.example .env
    echo "Please update .env with your settings"
fi

# Optional: Run test image through pipeline
read -p "Would you like to test the OCR pipeline with a sample image? (y/N) " run_test
if [[ $run_test =~ ^[Yy]$ ]]; then
    if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        echo "Running test with Google Cloud Vision..."
        python scripts/test_vision_setup.py
    else
        echo "Cannot run test: Google Cloud Vision credentials not configured"
        echo "Please set up credentials first"
    fi
fi

echo "Setup complete!"
echo "Next steps:"
echo "1. Update .env with your settings"
if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "2. Set up Google Cloud Vision credentials for enhanced OCR"
fi
echo "3. Run 'flask run' to start the application" 