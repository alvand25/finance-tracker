#!/bin/bash

# Finance Tracker Installation Script

# Print colored output
print_green() {
    echo -e "\033[0;32m$1\033[0m"
}

print_yellow() {
    echo -e "\033[0;33m$1\033[0m"
}

print_red() {
    echo -e "\033[0;31m$1\033[0m"
}

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_red "Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

print_green "Setting up Finance Tracker..."

# Check if virtual environment exists
if [ ! -d "venv_new" ]; then
    print_yellow "Creating virtual environment..."
    python3 -m venv venv_new
else
    print_yellow "Virtual environment already exists."
fi

# Activate virtual environment
print_yellow "Activating virtual environment..."
source venv_new/bin/activate

# Install dependencies
print_yellow "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
print_yellow "Creating directories..."
mkdir -p data
mkdir -p uploads/receipts
mkdir -p uploads/thumbnails
mkdir -p debug_output

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_yellow "Creating .env file from env.example..."
    cp env.example .env
    print_yellow "Please update the .env file with your credentials."
else
    print_yellow ".env file already exists."
fi

print_green "✅ Installation complete!"
print_yellow "To run the finance tracker:"
print_yellow "1. Activate the virtual environment: source venv_new/bin/activate"
print_yellow "2. Run the application: python app.py"
print_yellow "3. Open a browser and go to: http://localhost:5003"

# Exit the virtual environment
deactivate 