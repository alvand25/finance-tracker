#!/usr/bin/env python3
"""
Test script for Trader Joe's receipt handler

This script tests the Trader Joe's receipt handler specifically by:
1. Loading sample Trader Joe's receipt(s)
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

def test_trader_joes_handler(image_path=None, mock_text=None):
    """Test Trader Joe's receipt handler on a specific image or mock text"""
    
    if image_path:
        print(f"\n==== Testing Trader Joe's Handler on {os.path.basename(image_path)} ====")
    else:
        print(f"\n==== Testing Trader Joe's Handler with Mock Data ====")
    
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
        
        # Validate this is actually a Trader Joe's receipt
        if store_name and not any(s in store_name.lower() for s in ['trader', 'joe']):
            print(f"WARNING: This does not appear to be a Trader Joe's receipt. Detected store: {store_name}")
            print("Skipping specialized handler test to prevent misclassification")
            return {
                "error": "Not a Trader Joe's receipt",
                "detected_store": store_name
            }
        
        # First try parsing items with the specialized parser
        items = analyzer.parse_trader_joes_items(receipt_text)
        print(f"Specialized parser found {len(items)} items")
        
        # Display some example items
        if items:
            print("\nExample items:")
            for i, item in enumerate(items[:3]):
                print(f"  {i+1}. {item.get('description')} - ${item.get('price')}")
            
        # Now run the full handler
        print("\nRunning full Trader Joe's handler...")
        result = analyzer.handle_trader_joes_receipt(receipt_text, image_path)
        
        # Display results
        print("\nHandler results:")
        print(f"Items found: {len(result.get('items', []))}")
        print(f"Total: ${result.get('total')}")
        print(f"Subtotal: ${result.get('subtotal')}")
        print(f"Tax: ${result.get('tax')}")
        print(f"Date: {result.get('date')}")
        print(f"Payment method: {result.get('payment_method')}")
        print(f"Confidence score: {result.get('confidence')}")
        
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


def create_mock_trader_joes_receipt():
    """Create a mock Trader Joe's receipt text for testing"""
    return """
    Trader Joe's #123
    100 Main Street
    Anytown, CA 90210
    (555) 555-1234
    
    ORGANIC BANANAS         0.99
    SPINACH SALAD           3.99
    GREEK YOGURT            2.49
    EVERYTHING BAGEL SEASONING  1.99
    DARK CHOCOLATE PEANUT BUTTER CUPS  4.99
    UNEXPECTED CHEDDAR      4.29
    ORANGE CHICKEN          5.99
    CAULIFLOWER GNOCCHI     2.99
    
    SUBTOTAL               27.72
    TAX                     1.66
    TOTAL                  29.38
    
    VISA ************1234   29.38
    
    Thank you for shopping at Trader Joe's!
    2023-06-15 14:30:22
    """


def main():
    """Main entry point for testing"""
    
    # Check for Trader Joe's sample images
    samples_dir = "samples/images"
    
    # First look for Trader Joe's samples
    tj_samples = []
    if os.path.exists(samples_dir):
        for filename in os.listdir(samples_dir):
            if "trader" in filename.lower() and "joe" in filename.lower():
                tj_samples.append(os.path.join(samples_dir, filename))
    
    # If no samples found, check uploads directory
    if not tj_samples:
        # Check if uploads directory has any potential Trader Joe's receipts
        uploads_dir = "uploads/receipts"
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                if filename.endswith(('.jpg', '.jpeg', '.png')):
                    tj_samples.append(os.path.join(uploads_dir, filename))
    
    # If actual images were found, test them
    if tj_samples:
        print(f"Found {len(tj_samples)} potential Trader Joe's receipts to test")
        for sample_path in tj_samples:
            test_trader_joes_handler(image_path=sample_path)
    else:
        # If no samples found, use mock data
        print("No Trader Joe's sample receipts found. Testing with mock data instead.")
        mock_text = create_mock_trader_joes_receipt()
        test_trader_joes_handler(mock_text=mock_text)
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 