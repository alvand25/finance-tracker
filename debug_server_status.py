#!/usr/bin/env python
"""
Debug script to check the Flask server configuration and template paths.
Run this script to diagnose template loading and server issues.
"""

import os
import sys
import importlib.util
from datetime import datetime

def print_section(title):
    """Print a section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def check_file_exists(path):
    """Check if file exists and print details"""
    exists = os.path.exists(path)
    status = "✅ EXISTS" if exists else "❌ MISSING"
    size = f"({os.path.getsize(path)/1024:.1f} KB)" if exists else ""
    print(f"{status} {path} {size}")
    return exists

print_section("FINANCE TRACKER SERVER DIAGNOSTICS")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Current working directory: {os.getcwd()}")
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

# Check if Flask is installed
print_section("FLASK INSTALLATION")
try:
    import flask
    print(f"✅ Flask is installed (version {flask.__version__})")
except ImportError:
    print("❌ Flask is not installed!")

# Check app.py existence
print_section("APPLICATION FILE")
app_path = os.path.join(os.getcwd(), "app.py")
if check_file_exists(app_path):
    # Try to import app.py to get routes
    try:
        spec = importlib.util.spec_from_file_location("app", app_path)
        app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_module)
        
        if hasattr(app_module, 'app'):
            print(f"✅ Flask app found in app.py")
            
            # Print routes
            print_section("REGISTERED ROUTES")
            for rule in app_module.app.url_map.iter_rules():
                print(f"Route: {rule} → {rule.endpoint}")
        else:
            print("❌ Flask app not found in app.py")
    except Exception as e:
        print(f"❌ Error importing app.py: {e}")

# Check templates directory
print_section("TEMPLATES DIRECTORY")
templates_dir = os.path.join(os.getcwd(), "templates")
if os.path.isdir(templates_dir):
    print(f"✅ Templates directory exists at {templates_dir}")
    
    # Check for expense templates
    print_section("EXPENSE TEMPLATES")
    expense_template_root = os.path.join(templates_dir, "new_expense.html")
    expense_template_dir = os.path.join(templates_dir, "expense")
    expense_template_nested = os.path.join(expense_template_dir, "new.html")
    
    print("Checking root template:")
    root_exists = check_file_exists(expense_template_root)
    
    print("\nChecking expense directory:")
    if os.path.isdir(expense_template_dir):
        print(f"✅ Expense directory exists at {expense_template_dir}")
        print("\nChecking nested template:")
        nested_exists = check_file_exists(expense_template_nested)
        
        if root_exists and nested_exists:
            print("\n⚠️ WARNING: Both templates exist, which might cause confusion!")
            print("  -> Flask will load templates/new_expense.html by default")
            print("  -> To use the nested template, specify 'expense/new.html'")
    else:
        print(f"❌ Expense directory does not exist at {expense_template_dir}")
else:
    print(f"❌ Templates directory not found at {templates_dir}")

# Check __pycache__ directories
print_section("CACHE DIRECTORIES")
pycache_dirs = []
for root, dirs, files in os.walk(os.getcwd()):
    if "__pycache__" in dirs:
        pycache_path = os.path.join(root, "__pycache__")
        pycache_dirs.append(pycache_path)
        print(f"Found: {pycache_path}")

if pycache_dirs:
    print(f"\nFound {len(pycache_dirs)} __pycache__ directories that could be cleared")
    print("To clear them, run: `find . -name '__pycache__' -type d -exec rm -rf {} +`")
else:
    print("No __pycache__ directories found")

# Check for environment variables
print_section("ENVIRONMENT VARIABLES")
env_vars = {
    "FLASK_APP": os.environ.get("FLASK_APP"),
    "FLASK_ENV": os.environ.get("FLASK_ENV"),
    "FLASK_DEBUG": os.environ.get("FLASK_DEBUG"),
    "PORT": os.environ.get("PORT")
}

for var, value in env_vars.items():
    status = "✅" if value else "❌"
    value_display = value if value else "Not set"
    print(f"{status} {var}: {value_display}")

# Print final recommendations
print_section("RECOMMENDATIONS")
print("Based on the diagnostics, you should:")
print("1. Ensure only one template exists or that you're using the correct path")
print("2. Clear __pycache__ directories if there are stale cached files")
print("3. Set FLASK_ENV=development and FLASK_DEBUG=True")
print("4. Ensure app.run() has debug=True and use_reloader=True")
print("5. Restart your virtualenv: deactivate, source venv/bin/activate, python app.py") 