#!/usr/bin/env python3
import requests
import json
import os

# Path to suspicious items test file
test_file_path = 'samples/images/test_suspicious_detection.txt'

# Read the test file
with open(test_file_path, 'r') as f:
    receipt_text = f.read()

# API endpoint
url = 'http://127.0.0.1:5003/api/parse-receipt'

# Send the request with text data
response = requests.post(
    url,
    json={
        'test_text': True,
        'receipt_text': receipt_text
    },
    proxies={},  # Disable proxies
    verify=False  # Disable SSL verification
)

# Print the response status
print(f"Response status code: {response.status_code}")

# Format and print the JSON response
if response.ok:
    data = response.json()
    print(json.dumps(data, indent=2))
    
    if data.get('success'):
        parsed_receipt = data.get('parsed_receipt', {})
        
        # Print summary info
        print("\nSummary:")
        print(f"Store: {parsed_receipt.get('store_name', 'Unknown')}")
        print(f"Total: ${parsed_receipt.get('total_amount', 0)}")
        print(f"Confidence: {parsed_receipt.get('confidence_score', 0)}")
        
        # List detected items
        items = parsed_receipt.get('items', [])
        print(f"\nDetected {len(items)} items:")
        for i, item in enumerate(items, 1):
            status = "⚠️ SUSPICIOUS" if item.get('suspicious') else "✅ VALID"
            print(f"{i}. {item.get('name')} - ${item.get('price')} [{status}]")
        
        # Show validation info
        print("\nValidation Info:")
        print(f"Flagged for review: {parsed_receipt.get('flagged_for_review', False)}")
        print(f"Has suspicious items: {parsed_receipt.get('has_suspicious_items', False)}")
        
        if parsed_receipt.get('validation_notes'):
            print("\nValidation Notes:")
            for note in parsed_receipt.get('validation_notes', []):
                print(f"- {note}")
else:
    print(f"Error: {response.text}") 