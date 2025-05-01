#!/usr/bin/env python3
"""
A simple script to run the Finance Tracker application.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    from app import app
    
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    port = int(os.getenv('FLASK_PORT', '5000'))
    
    print(f"Starting Finance Tracker on http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    app.run(debug=debug, port=port, host='0.0.0.0') 