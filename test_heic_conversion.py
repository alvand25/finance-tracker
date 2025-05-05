#!/usr/bin/env python
"""
Test script to verify HEIC conversion and receipt parsing functionality.
"""

import os
import requests
import time
import json
from PIL import Image
import io

# Base URL for the Flask application
BASE_URL = "http://localhost:5003"

def test_heic_conversion():
    """Test conversion of a HEIC image to JPEG format."""
    print("Testing HEIC conversion...")
    
    # Get the path to a test HEIC file
    # Note: You'll need to replace this with an actual HEIC file path
    heic_path = "test_receipts/sample.heic"
    
    if not os.path.exists(heic_path):
        print(f"Warning: Test HEIC file not found at {heic_path}")
        print("Skipping HEIC conversion test. Please add a sample.heic file to test_receipts/ directory.")
        return False
    
    # Prepare the file for upload
    files = {'receipt_image': open(heic_path, 'rb')}
    
    try:
        # Send the request
        response = requests.post(f"{BASE_URL}/api/parse-receipt", files=files)
        
        # Check for successful response
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ HEIC conversion and parsing successful!")
                print(f"Store: {data['parsed_receipt']['store_name']}")
                print(f"Total: {data['parsed_receipt']['total_amount']}")
                print(f"Items: {len(data['parsed_receipt']['items'])}")
                return True
            else:
                print("❌ HEIC parsing failed:")
                print(data.get('error', 'Unknown error'))
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False
    finally:
        # Close the file
        files['receipt_image'].close()

def test_large_image_upload():
    """Test uploading a large image (>10MB but <16MB)."""
    print("\nTesting large image upload...")
    
    # For this test, we'll create a large image in memory
    # 4000x4000 RGB image should be around 48MB uncompressed
    image = Image.new('RGB', (4000, 4000))
    
    # Save it to a BytesIO object with moderate compression
    img_io = io.BytesIO()
    image.save(img_io, format='JPEG', quality=70)  # Adjust quality to get size between 10-16MB
    img_io.seek(0)
    
    # Calculate file size in MB
    size_mb = len(img_io.getvalue()) / (1024 * 1024)
    print(f"Generated test image of {size_mb:.2f} MB")
    
    # If image is larger than 16MB, resize it
    if size_mb > 16:
        print("Image is too large, resizing...")
        compression = 50
        while size_mb > 16 and compression > 10:
            img_io = io.BytesIO()
            image.save(img_io, format='JPEG', quality=compression)
            img_io.seek(0)
            size_mb = len(img_io.getvalue()) / (1024 * 1024)
            print(f"Resized image to {size_mb:.2f} MB with quality {compression}")
            compression -= 10
    
    # If image is smaller than 10MB, we can still test but it's not a true large file test
    if size_mb < 10:
        print("Warning: Generated image is smaller than 10MB, not a true large file test")
    
    try:
        # Prepare the file for upload
        files = {'receipt_image': ('large_test.jpg', img_io.getvalue(), 'image/jpeg')}
        
        # Send the request
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/api/parse-receipt", files=files)
        end_time = time.time()
        
        print(f"Request took {end_time - start_time:.2f} seconds")
        
        # Check for successful response
        if response.status_code == 200:
            print("✅ Large image upload successful!")
            return True
        elif response.status_code == 413:
            print("❌ File size limit exceeded (413 error)")
            print("This suggests the 16MB limit is not properly configured")
            return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False

def test_regular_receipt():
    """Test parsing a regular receipt image."""
    print("\nTesting regular receipt parsing...")
    
    # Look for sample receipts in test_receipts or samples directory
    sample_dirs = ['test_receipts', 'samples', 'samples/images']
    receipt_path = None
    
    for directory in sample_dirs:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    receipt_path = os.path.join(directory, filename)
                    break
            if receipt_path:
                break
    
    if not receipt_path:
        print("No sample receipt images found. Skipping regular receipt test.")
        return False
    
    print(f"Using sample receipt: {receipt_path}")
    
    # Prepare the file for upload
    files = {'receipt_image': open(receipt_path, 'rb')}
    
    try:
        # Send the request
        response = requests.post(f"{BASE_URL}/api/parse-receipt", files=files)
        
        # Check for successful response
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Receipt parsing successful!")
                print(f"Store: {data['parsed_receipt']['store_name']}")
                print(f"Total: {data['parsed_receipt']['total_amount']}")
                print(f"Items: {len(data['parsed_receipt']['items'])}")
                return True
            else:
                print("❌ Receipt parsing failed:")
                print(data.get('error', 'Unknown error'))
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False
    finally:
        # Close the file
        files['receipt_image'].close()

if __name__ == "__main__":
    print("=== Receipt Processing System Tests ===")
    print("Make sure the Flask application is running on port 5003")
    
    # Wait a moment for the server to be fully up
    time.sleep(1)
    
    # Run tests
    regular_test = test_regular_receipt()
    large_test = test_large_image_upload()
    heic_test = test_heic_conversion()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Regular Receipt Test: {'PASS' if regular_test else 'FAIL'}")
    print(f"Large Image Upload Test: {'PASS' if large_test else 'FAIL'}")
    print(f"HEIC Conversion Test: {'PASS' if heic_test else 'FAIL or SKIPPED'}")
    
    # Overall result
    if regular_test:
        print("\n✅ Basic functionality is working!")
        if large_test and heic_test:
            print("✅ All functionality is working perfectly!")
        elif large_test:
            print("✅ Large image uploads are working, but HEIC conversion wasn't tested.")
        elif heic_test:
            print("⚠️ HEIC conversion is working, but large image uploads might have issues.")
        else:
            print("⚠️ Advanced features (large uploads, HEIC) have issues or weren't tested.")
    else:
        print("\n❌ Basic functionality is not working correctly.") 