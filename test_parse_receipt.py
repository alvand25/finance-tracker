#!/usr/bin/env python3
"""
Test script for the /api/parse-receipt endpoint.
This script sends a receipt image to the endpoint and displays the results.
"""

import requests
import json
import sys
import os
from pprint import pprint
from PIL import Image
import io

def test_parse_receipt():
    base_url = "http://localhost:5003"
    endpoint = "/api/parse-receipt"
    test_image_path = "samples/images/IMG_5655.png"
    
    print(f"Testing parse-receipt with image: {test_image_path}")
    
    # Check if file exists
    if not os.path.exists(test_image_path):
        print(f"Error: Test image not found at {test_image_path}")
        return
    
    # Resize the image to reduce its size
    try:
        print("Resizing image to reduce file size...")
        img = Image.open(test_image_path)
        # Calculate new dimensions (50% of original)
        width, height = img.size
        new_width = width // 2
        new_height = height // 2
        resized_img = img.resize((new_width, new_height), Image.LANCZOS)
        
        # Save to a bytes buffer instead of a file
        img_byte_arr = io.BytesIO()
        resized_img.save(img_byte_arr, format=img.format)
        img_byte_arr.seek(0)
        
        print(f"Original size: {width}x{height}, Resized: {new_width}x{new_height}")
    except Exception as e:
        print(f"Error resizing image: {e}")
        return
    
    print("Sending request to endpoint...")
    
    try:
        # Send the request with the file
        files = {'receipt_image': ('receipt.png', img_byte_arr, 'image/png')}
        data = {'store_type_hint': 'grocery', 'currency_hint': 'USD'}
        
        response = requests.post(f"{base_url}{endpoint}", files=files, data=data)
        
        # Check the response
        if response.status_code == 200:
            result = response.json()
            if result['success']:
                print("Successfully parsed receipt!")
                print("\nParsed Data:")
                pprint(result['data'])
            else:
                print(f"Error parsing receipt: {result.get('error', 'Unknown error')}")
        else:
            print(f"Error: Status code {response.status_code}")
            try:
                print(json.dumps(response.json(), indent=2))
            except:
                print(response.text)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_parse_receipt() 