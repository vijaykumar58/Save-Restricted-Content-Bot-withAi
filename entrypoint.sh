#!/bin/bash
set -e

# Start Flask app in background
flask run --host=0.0.0.0 --port=5000 &

# Start main application
python3 main.py

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?