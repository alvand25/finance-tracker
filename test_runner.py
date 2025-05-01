#!/usr/bin/env python
"""
Test runner for receipt OCR tests.

This script provides a user-friendly interface for running the receipt OCR tests
with various options.

Usage:
    python test_runner.py [options]

Options:
    --store=<name>     Run tests only for a specific store (e.g., costco, h_mart)
    --debug            Enable debug output from handlers
    --timeout=<secs>   Set timeout for receipt processing in seconds (default: 30)
    --verbose, -v      Enable verbose pytest output
    --help, -h         Show this help message
"""

import os
import sys
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Run receipt OCR tests")
    parser.add_argument("--store", help="Run tests only for a specific store (e.g., costco, h_mart)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output from handlers")
    parser.add_argument("--timeout", type=int, default=30, help="Set timeout for receipt processing in seconds (default: 30)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose pytest output")
    
    args = parser.parse_args()
    
    # Build pytest command
    command = ["python", "-m", "pytest", "tests/test_vendor_handlers.py"]
    
    # Add verbose flag if requested
    if args.verbose:
        command.append("-v")
    
    # Add store filter if provided
    if args.store:
        command.append(f"--store={args.store}")
    
    # Set environment variables for debug mode
    env = os.environ.copy()
    if args.debug:
        env["DEBUG_HANDLERS"] = "1"
    
    # Set receipt timeout
    env["RECEIPT_TIMEOUT"] = str(args.timeout)
    
    print(f"Running command: {' '.join(command)}")
    if args.debug:
        print("Debug mode enabled")
    
    # Run the command
    result = subprocess.run(command, env=env)
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main() 