import sys
import os
import platform
import site

print("Python Version:", platform.python_version())
print("Python Executable:", sys.executable)
print("Virtual Environment:", os.environ.get('VIRTUAL_ENV', 'Not in a virtual environment'))
print("Python Path:")
for path in sys.path:
    print(f"  - {path}")

print("\nAvailable site-packages directories:")
for path in site.getsitepackages():
    print(f"  - {path}")

try:
    import requests
    print("\nRequests module found!")
    print("Version:", requests.__version__)
except ImportError:
    print("\nRequests module not found!")
    
print("\nWhich pip is being used:")
os.system("which pip")
print("\nPip packages in current environment:")
os.system("pip list | grep requests") 