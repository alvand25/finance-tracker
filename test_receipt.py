#!/usr/bin/env python
"""
Test script for the receipt processing functionality.
This demonstrates how to use the receipt processing system.
"""

import os
import sys
import json
from uuid import UUID

from models.receipt import Receipt
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService

def test_receipt_processing():
    """Test the receipt processing functionality."""
    print("Receipt Processing Test")
    print("=====================")
    
    # Initialize storage and receipt service
    storage = JSONStorage(data_dir='data')
    receipt_service = ReceiptService(storage, upload_dir='uploads/receipts')
    
    # Check if a sample image was provided
    if len(sys.argv) < 2:
        print("Usage: python test_receipt.py <path_to_receipt_image>")
        print("\nNo image provided. Checking for existing receipts instead...")
        
        # List any existing receipts
        receipts_path = os.path.join('data', 'receipts')
        if os.path.exists(receipts_path):
            receipt_files = [f for f in os.listdir(receipts_path) if f.endswith('.json')]
            
            if receipt_files:
                print(f"Found {len(receipt_files)} existing receipts:")
                for rf in receipt_files:
                    # Load the receipt data
                    with open(os.path.join(receipts_path, rf), 'r') as f:
                        receipt_data = json.load(f)
                    
                    # Extract receipt ID from filename
                    receipt_id = rf.replace('.json', '')
                    
                    # Print receipt details
                    print(f"Receipt ID: {receipt_id}")
                    print(f"  Store: {receipt_data.get('store_name', 'Unknown')}")
                    print(f"  Total: ${receipt_data.get('total_amount', 0)}")
                    print(f"  Status: {receipt_data.get('processing_status', 'Unknown')}")
                    print(f"  Items: {len(receipt_data.get('items', []))}")
                    
                    # Print confidence score if available
                    if 'confidence_score' in receipt_data:
                        print(f"  Confidence: {receipt_data.get('confidence_score', 0):.2f}")
                    
                    print("")
            else:
                print("No existing receipts found.")
        else:
            print("No receipts directory found.")
            
        return
    
    # Process a receipt image
    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Error: Image file not found at {image_path}")
        return
    
    print(f"Processing receipt image: {image_path}")
    
    # Read the image file
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Create a receipt object
    receipt = Receipt(image_url=image_path)
    
    # Process the receipt (two options)
    use_progressive = '--progressive' in sys.argv
    
    if use_progressive:
        print("Using progressive processing...")
        receipt, is_complete = receipt_service.process_receipt_progressive(receipt, image_data)
        
        print(f"Initial processing complete: {receipt.processing_status}")
        print(f"Initial results:")
        print(f"  Store: {receipt.store_name}")
        print(f"  Total: ${receipt.total_amount if receipt.total_amount else 'Unknown'}")
        
        if not is_complete:
            print("\nCompleting detailed processing...")
            receipt = receipt_service.complete_progressive_processing(receipt.id)
    else:
        print("Using standard processing...")
        receipt = receipt_service.process_receipt(receipt, image_data)
    
    # Print results
    print("\nProcessing Results:")
    print(f"Receipt ID: {receipt.id}")
    print(f"Status: {receipt.processing_status}")
    
    if receipt.processing_status == 'failed':
        print(f"Error: {receipt.processing_error}")
        return
    
    print(f"Store: {receipt.store_name or 'Unknown'}")
    print(f"Date: {receipt.transaction_date or 'Unknown'}")
    print(f"Currency: {receipt.currency_type or 'Unknown'}")
    print(f"Payment Method: {receipt.payment_method or 'Unknown'}")
    
    print(f"\nAmounts:")
    print(f"  Subtotal: ${receipt.subtotal_amount or 'Unknown'}")
    print(f"  Tax: ${receipt.tax_amount or 'Unknown'}")
    print(f"  Total: ${receipt.total_amount or 'Unknown'}")
    
    print(f"\nItems ({len(receipt.items)}):")
    for item in receipt.items:
        print(f"  - {item.description}: ${item.amount}")
        if item.quantity:
            print(f"    Qty: {item.quantity}, Unit Price: ${item.unit_price}")
    
    if receipt.confidence_score:
        print(f"\nConfidence Score: {receipt.confidence_score:.2f}")
    
    if receipt.template_id:
        print(f"\nTemplate: {receipt.template_metadata.get('name', 'Unknown')}")
        print(f"Template Match Confidence: {receipt.template_metadata.get('confidence', 0):.2f}")
    
    print(f"\nProcessing Time: {receipt.processing_time:.2f} seconds")
    
    print("\nDone.")


if __name__ == "__main__":
    test_receipt_processing() 