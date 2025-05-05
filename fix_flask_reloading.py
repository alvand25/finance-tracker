#!/usr/bin/env python3

"""
This script helps diagnose and potentially fix Flask reloading issues
by checking the current configuration, modifying app.py, and creating
a compatible development environment.
"""

import os
import sys
import glob
import subprocess
import time
from pathlib import Path

def print_section(title):
    """Print a section header for better readability."""
    print(f"\n{'='*80}\n{title}\n{'='*80}")

def run_command(cmd, capture_output=True):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=False, 
            capture_output=capture_output,
            text=True
        )
        return result.stdout if capture_output else None
    except Exception as e:
        print(f"Error running command '{cmd}': {e}")
        return None

def main():
    print_section("FLASK DEVELOPMENT SERVER DIAGNOSTICS AND REPAIR")
    
    # Check if we're in the correct directory
    cwd = os.getcwd()
    print(f"Current directory: {cwd}")

    # Check if app.py exists
    if not os.path.exists('app.py'):
        print("Error: app.py not found in the current directory")
        return False

    # Check Python version
    python_version = run_command("python --version")
    print(f"Python version: {python_version.strip()}")

    # Check for virtual environment
    venv_paths = ["venv", "venv_new", ".venv"]
    active_venv = None
    for venv in venv_paths:
        if os.path.exists(venv) and os.path.isdir(venv):
            print(f"Found virtual environment: {venv}")
            active_venv = venv
            break

    if not active_venv:
        print("Warning: No virtual environment found")
    
    # Check Flask installation
    print_section("CHECKING FLASK INSTALLATION")
    flask_version = run_command(f"{active_venv}/bin/pip freeze | grep Flask" if active_venv else "pip freeze | grep Flask")
    if flask_version:
        print(f"Flask installed: {flask_version.strip()}")
    else:
        print("Warning: Flask not found in pip freeze output")
    
    # Check for __pycache__ directories
    print_section("CHECKING FOR __PYCACHE__ DIRECTORIES")
    pycache_dirs = glob.glob("**/__pycache__", recursive=True)
    if pycache_dirs:
        print(f"Found {len(pycache_dirs)} __pycache__ directories")
        clear_pycache = input("Clear all __pycache__ directories? (y/n): ").lower() == 'y'
        if clear_pycache:
            run_command("find . -name '__pycache__' -type d -exec rm -rf {} \\; 2>/dev/null || true", capture_output=False)
            print("All __pycache__ directories cleared")
    else:
        print("No __pycache__ directories found")
    
    # Check current Flask configuration in app.py
    print_section("CHECKING CURRENT FLASK CONFIGURATION")
    
    # Look for the run block in app.py
    with open('app.py', 'r') as f:
        content = f.read()
    
    if '__name__ == "__main__"' in content or '__name__ == \'__main__\'' in content:
        print("Found app.run() block in app.py")
    else:
        print("Warning: Couldn't identify app.run() block in app.py")
    
    # Check for environment variables
    flask_env = os.environ.get('FLASK_ENV')
    flask_debug = os.environ.get('FLASK_DEBUG')
    print(f"FLASK_ENV: {flask_env or 'Not set'}")
    print(f"FLASK_DEBUG: {flask_debug or 'Not set'}")
    
    # Check for templates
    template_dir = os.path.join(cwd, 'templates')
    if os.path.exists(template_dir) and os.path.isdir(template_dir):
        print(f"Templates directory exists: {template_dir}")
        template_count = len(glob.glob(f"{template_dir}/**/*.html", recursive=True))
        print(f"Found {template_count} template files")
        
        # Check specific templates
        specific_templates = [
            "expense/new.html",
            "new_expense.html"
        ]
        
        for template in specific_templates:
            template_path = os.path.join(template_dir, template)
            if os.path.exists(template_path):
                print(f"Template exists: {template}")
            else:
                print(f"Template missing: {template}")
    else:
        print(f"Templates directory not found: {template_dir}")
    
    # Offer to fix the app.py configuration
    print_section("FLASK APP CONFIGURATION OPTIONS")
    print("1. Update app.py to force debug mode and proper reloading")
    print("2. Set environment variables for Flask development")
    print("3. Create a start_flask.sh script for consistent startup")
    print("4. Exit without changes")
    
    choice = input("\nEnter your choice (1-4): ")
    
    if choice == '1':
        print_section("UPDATING APP.PY")
        
        # Find the position of the app.run block
        main_block = """\
if __name__ == "__main__":
    # Force debug mode and reloading
    import os
    import sys
    
    # Set environment variables
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = '1'
    
    # Print debug info
    print(f"\\n{'='*80}\\nSTARTING FLASK SERVER (DEBUG MODE)\\n{'='*80}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    print(f"Debug mode: {app.debug}")
    
    # Verify template paths
    template_path = os.path.join(os.getcwd(), 'templates')
    print(f"Templates directory exists: {os.path.exists(template_path)}")
    
    port = int(os.environ.get('PORT', 5004))
    print(f"\\nStarting server on port {port}\\n{'='*80}\\n")
    
    # Start with explicit settings
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=True,
        threaded=True
    )
"""
        # Read the current content
        with open('app.py', 'r') as f:
            content = f.readlines()
        
        # Find the if __name__ == '__main__' block
        start_idx = None
        end_idx = None
        for i, line in enumerate(content):
            if '__name__' in line and ('__main__' in line):
                start_idx = i
                # Find the end of the block (next line with same indentation or EOF)
                indent = len(line) - len(line.lstrip())
                j = i + 1
                while j < len(content):
                    if content[j].strip() and len(content[j]) - len(content[j].lstrip()) <= indent:
                        break
                    j += 1
                end_idx = j
                break
        
        # Replace or append the main block
        new_content = []
        if start_idx is not None and end_idx is not None:
            new_content = content[:start_idx] + [main_block] + content[end_idx:]
            print(f"Replacing app.run() block (lines {start_idx+1}-{end_idx})")
        else:
            new_content = content + ["\n", main_block]
            print("Appending app.run() block at the end of the file")
        
        # Write the new content
        with open('app.py', 'w') as f:
            f.writelines(new_content)
        
        print("app.py updated successfully")
    
    elif choice == '2':
        print_section("SETTING ENVIRONMENT VARIABLES")
        
        # Create a .env file
        env_content = """FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
PORT=5004
"""
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print(".env file created with development settings")
        print("Use 'python -m flask run' to start the app")
    
    elif choice == '3':
        print_section("CREATING START SCRIPT")
        
        # Create a start_flask.sh script
        script_content = """#!/bin/bash

# Clear cache and start Flask development server
echo "Clearing Python cache..."
find . -name "__pycache__" -type d -exec rm -rf {} \\; 2>/dev/null || true
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
"""
        with open('start_flask.sh', 'w') as f:
            f.write(script_content)
        
        # Make it executable
        os.chmod('start_flask.sh', 0o755)
        
        print("start_flask.sh script created and made executable")
        print("Run './start_flask.sh' to start the Flask server")
    
    else:
        print("No changes made")
    
    print_section("RECOMMENDATIONS")
    print("1. Make sure your virtual environment is activated before running Flask")
    print("2. Use 'debug=True, use_reloader=True' in your app.run() call")
    print("3. Set FLASK_ENV=development and FLASK_DEBUG=1")
    print("4. Clear __pycache__ directories if you see stale code behavior")
    print("5. Check that templates exist in the expected locations")
    
    return True

if __name__ == "__main__":
    main() 