#!/usr/bin/env python3
"""
Test script for Trader Joe's receipt parsing using the parse-receipt API endpoint.
"""

import os
import sys
import json
import requests
from pprint import pprint
from glob import glob
import io
from PIL import Image

# Configuration
BASE_URL = "http://127.0.0.1:5003"
API_ENDPOINT = f"{BASE_URL}/api/parse-receipt"

# Disable any proxies
os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ['no_proxy'] = '127.0.0.1,localhost'

def resize_image_if_needed(image_path, max_size_mb=3):
    """Resize image if it's too large to reduce upload time"""
    img = Image.open(image_path)
    img_size_bytes = os.path.getsize(image_path)
    img_size_mb = img_size_bytes / (1024 * 1024)
    
    if img_size_mb <= max_size_mb:
        print(f"Image size is {img_size_mb:.2f}MB, no resizing needed")
        return image_path
    
    # Calculate new dimensions to reduce size
    width, height = img.size
    print(f"Original image dimensions: {width}x{height}, size: {img_size_mb:.2f}MB")
    
    # Start with 50% reduction and adjust if needed
    scale_factor = 0.5
    
    # Create a temp file path
    temp_path = f"{os.path.splitext(image_path)[0]}_resized{os.path.splitext(image_path)[1]}"
    
    # Resize and save
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)
    resized_img = img.resize((new_width, new_height), Image.LANCZOS)
    resized_img.save(temp_path)
    
    new_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
    print(f"Resized to {new_width}x{new_height}, new size: {new_size_mb:.2f}MB")
    
    return temp_path

def test_parse_receipt(image_path, store_hint=None):
    """Test the receipt parsing API endpoint with a given image."""
    if not os.path.exists(image_path):
        print(f"Error: File {image_path} not found")
        sys.exit(1)
        
    print(f"Testing image: {image_path}")
    
    # Resize image if needed
    image_path = resize_image_if_needed(image_path)
    
    # Prepare the request
    with open(image_path, 'rb') as f:
        files = {'receipt_image': f}
        data = {}
        
        if store_hint:
            data['store_type_hint'] = store_hint
        
        # Send request
        print(f"Sending request to {API_ENDPOINT}...")
        try:
            response = requests.post(API_ENDPOINT, files=files, data=data, proxies={'http': None, 'https': None})
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            sys.exit(1)
    
    # Process response
    print(f"Response status code: {response.status_code}")
    
    try:
        result = response.json()
    except json.JSONDecodeError:
        print("Failed to parse JSON response")
        print(f"Raw response: {response.text}")
        sys.exit(1)
    
    # Display results
    if result.get('success'):
        print("\nParsing successful!")
        parsed_data = result.get('parsed_receipt', {})
        
        print(f"Store: {parsed_data.get('store_name', 'Unknown')}")
        print(f"Total: ${parsed_data.get('total_amount', 0)}")
        print(f"Confidence: {parsed_data.get('confidence_score', 0)}")
        
        items = parsed_data.get('items', [])
        if items:
            print(f"\nDetected {len(items)} items:")
            for i, item in enumerate(items, 1):
                price = item.get('price', 0) or item.get('amount', 0)
                print(f"{i}. {item.get('name', 'Unknown')} - ${price}")
        else:
            print("\nNo items detected")
    else:
        print("\nParsing failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        
        if 'partial_data' in result:
            print("\nPartial data extracted:")
            partial = result['partial_data']
            print(f"Store: {partial.get('store_name', 'Unknown')}")
            print(f"Total: ${partial.get('total_amount', 0)}")
            
            items = partial.get('items', [])
            if items:
                print(f"\nDetected {len(items)} items:")
                for i, item in enumerate(items, 1):
                    price = item.get('price', 0) or item.get('amount', 0)
                    print(f"{i}. {item.get('name', 'Unknown')} - ${price}")
    
    # Return the result for potential further processing
    return result

if __name__ == "__main__":
    # Check if we have command line arguments
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        store_hint = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Look for samples
        sample_files = glob('samples/images/*.png') + glob('samples/images/*.jpg')
        
        if not sample_files:
            print("No sample files found. Please provide an image path.")
            sys.exit(1)
        
        # Prefer Trader Joe's receipts if available
        trader_joes_samples = [f for f in sample_files if 'trader' in f.lower()]
        
        if trader_joes_samples:
            image_path = trader_joes_samples[0]
            store_hint = "TRADER JOE'S"
        else:
            image_path = sample_files[0]
            store_hint = None
    
    test_parse_receipt(image_path, store_hint) 