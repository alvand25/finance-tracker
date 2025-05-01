#!/bin/bash

# Activate the correct virtual environment
source venv_new/bin/activate

# Run the app in the background
python app.py > app_output.log 2>&1 &

# Save the process ID
echo "Server started with PID $!"
echo "To stop the server, run: kill $!"
echo "To view logs, run: tail -f app_output.log"
echo "Access the app at: http://localhost:5000" 