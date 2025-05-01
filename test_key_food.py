#!/usr/bin/env python3
"""
Test script for Key Food receipt handler

This script tests the Key Food receipt handler specifically by:
1. Loading sample Key Food receipt(s)
2. Running the specialized handler on it
3. Displaying the results
"""

import os
import sys
import json
from utils.receipt_analyzer import ReceiptAnalyzer

# Set up basic logging
import logging
logging.basicConfig(level=logging.INFO)

def test_key_food_handler(image_path=None, mock_text=None):
    """Test Key Food receipt handler on a specific image or mock text"""
    
    if image_path:
        print(f"\n==== Testing Key Food Handler on {os.path.basename(image_path)} ====")
    else:
        print(f"\n==== Testing Key Food Handler with Mock Data ====")
    
    # Initialize the analyzer
    analyzer = ReceiptAnalyzer()
    
    # Extract text from image or use mock text
    try:
        if image_path:
            receipt_text = analyzer.extract_text(image_path)
            print(f"Extracted {len(receipt_text)} characters of text")
        else:
            receipt_text = mock_text
            print(f"Using mock text with {len(receipt_text)} characters")
        
        # Extract store name
        store_name = analyzer._extract_store_name(receipt_text.split('\n'))
        print(f"Detected store name: {store_name}")
        
        # Validate this is actually a Key Food receipt
        if store_name and not any(s in store_name.lower() for s in ['key food', 'keyfood']):
            print(f"WARNING: This does not appear to be a Key Food receipt. Detected store: {store_name}")
            # Check for Queens/Sunnyside address patterns which indicate it's likely Key Food
            queens_indicator = any("queens" in line.lower() or "sunnyside" in line.lower() 
                                   for line in receipt_text.split('\n')[:10])
            if not queens_indicator:
                print("Skipping specialized handler test to prevent misclassification")
                return {
                    "error": "Not a Key Food receipt",
                    "detected_store": store_name
                }
            else:
                print("Queens/Sunnyside location detected, likely a Key Food receipt. Proceeding with test.")
        
        # Get items using the parse_items_fallback with key_food store type
        items = analyzer.parse_items_fallback(receipt_text, 'key_food')
        print(f"Fallback parser found {len(items)} items")
        
        # Display some example items
        if items:
            print("\nExample items:")
            for i, item in enumerate(items[:3]):
                print(f"  {i+1}. {item.get('description')} - ${item.get('price')}")
            
        # Now run the full handler
        print("\nRunning full Key Food handler...")
        result = analyzer.handle_key_food_receipt(receipt_text, image_path)
        
        # Display results
        print("\nHandler results:")
        print(f"Items found: {len(result.get('items', []))}")
        print(f"Total: ${result.get('total')}")
        print(f"Subtotal: ${result.get('subtotal')}")
        print(f"Tax: ${result.get('tax')}")
        print(f"Date: {result.get('date')}")
        print(f"Payment method: {result.get('payment_method')}")
        print(f"Confidence score: {result.get('confidence', {}).get('overall', 0)}")
        
        # Display detailed item list
        print("\nDetailed item list:")
        if result.get('items'):
            for i, item in enumerate(result.get('items')):
                print(f"  {i+1}. {item.get('description')} - ${item.get('price')}")
        else:
            print("  No items found")
        
        return result
        
    except Exception as e:
        print(f"Error testing handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def create_mock_key_food_receipt():
    """Create a mock Key Food receipt text for testing"""
    return """
    KEY FOOD
    46-02 Queens Blvd.
    Sunnyside, NY 11104
    (718) 706-6563
    
    CILANTRO MACHO              2.49 F
    BASIL                       2.50 F
    SPINACH                     3.99 F
    MILK 2%                     4.29 F
    BREAD                       2.99 F
    EGGS LARGE                  3.49 F
    CHEESE SHREDDED             4.99 F
    
    TAX                         0.00
    BALANCE                    24.74
    
    MasterCard Card - CONTACTLESS
    ACCOUNT NUMBER: ************2836
    APPROVAL CODE: 81146P
    SEQUENCE NUMBER: 3310
    TERMINAL ID:
    TOTAL AMOUNT: 24.74 Purchase
    RESPONSE CODE: APPROVED
    04/11/25 04:49pm 110 3
    
    MasterCard                  24.74
    CHANGE                       0.00
    TOTAL NUMBER OF ITEMS SOLD - 7
    
    Join the Savings Club for
    Additional Dollar Savings.
    Thank You for shopping with us
    """


def main():
    """Main entry point for testing"""
    
    # Check for Key Food sample images
    samples_dir = "samples/key_food"
    if not os.path.exists(samples_dir):
        os.makedirs(samples_dir)
        print(f"Created directory: {samples_dir}")
    
    # First look for Key Food samples in dedicated folder
    kf_samples = []
    if os.path.exists(samples_dir):
        for filename in os.listdir(samples_dir):
            if filename.endswith(('.jpg', '.jpeg', '.png')):
                kf_samples.append(os.path.join(samples_dir, filename))
    
    # If no samples found in dedicated folder, check general samples directory
    if not kf_samples:
        general_samples_dir = "samples/images"
        if os.path.exists(general_samples_dir):
            for filename in os.listdir(general_samples_dir):
                if "key" in filename.lower() and "food" in filename.lower():
                    kf_samples.append(os.path.join(general_samples_dir, filename))
                # Also check for Key Food via Queens/Sunnyside patterns in OCR text
                elif filename.endswith(('.jpg', '.jpeg', '.png')):
                    ocr_filename = os.path.splitext(filename)[0] + ".txt"
                    ocr_path = os.path.join("samples/ocr", ocr_filename)
                    if os.path.exists(ocr_path):
                        with open(ocr_path, 'r') as f:
                            ocr_text = f.read().lower()
                            if ("queens" in ocr_text and "blvd" in ocr_text) or \
                               ("sunnyside" in ocr_text and "ny" in ocr_text):
                                kf_samples.append(os.path.join(general_samples_dir, filename))
    
    # If still no samples found, check uploads directory
    if not kf_samples:
        uploads_dir = "uploads/receipts"
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                if filename.endswith(('.jpg', '.jpeg', '.png')):
                    kf_samples.append(os.path.join(uploads_dir, filename))
    
    # If actual images were found, test them
    if kf_samples:
        print(f"Found {len(kf_samples)} potential Key Food receipts to test")
        for sample_path in kf_samples:
            test_key_food_handler(image_path=sample_path)
    else:
        # If no samples found, use mock data
        print("No Key Food sample receipts found. Testing with mock data instead.")
        mock_text = create_mock_key_food_receipt()
        test_key_food_handler(mock_text=mock_text)
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 