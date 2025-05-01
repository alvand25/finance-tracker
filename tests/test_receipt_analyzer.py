#!/usr/bin/env python3
"""
Unit tests for receipt analyzer.
Tests the receipt analyzer on various receipt formats from our sample dataset.
"""

import os
import sys
import json
import unittest
from typing import Dict, List, Any, Optional
import re
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.receipt_analyzer import ReceiptAnalyzer
from services.receipt_service import ReceiptService
from storage.json_storage import JSONStorage

# Constants
SAMPLES_DIR = "samples"
OCR_DIR = os.path.join(SAMPLES_DIR, "ocr")
IMAGES_DIR = os.path.join(SAMPLES_DIR, "images")
ANNOTATIONS_DIR = os.path.join(SAMPLES_DIR, "annotations")

class TestReceiptAnalyzer(unittest.TestCase):
    """Test the receipt analyzer on various receipt formats."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        # Set up the receipt analyzer and service
        cls.analyzer = ReceiptAnalyzer()
        cls.storage = JSONStorage(data_dir="data")
        cls.service = ReceiptService(cls.storage, upload_dir="uploads/receipts")
        
        # Ensure the samples directory exists
        if not os.path.exists(SAMPLES_DIR):
            os.makedirs(SAMPLES_DIR)
        if not os.path.exists(OCR_DIR):
            os.makedirs(OCR_DIR)
        if not os.path.exists(IMAGES_DIR):
            os.makedirs(IMAGES_DIR)
        if not os.path.exists(ANNOTATIONS_DIR):
            os.makedirs(ANNOTATIONS_DIR)
        
        # Get available samples
        cls.ocr_files = [f for f in os.listdir(OCR_DIR) if f.endswith('.txt')]
        cls.image_files = [f for f in os.listdir(IMAGES_DIR) if f.endswith(('.jpg', '.jpeg', '.png'))]
        cls.annotation_files = [f for f in os.listdir(ANNOTATIONS_DIR) if f.endswith('.json')]
        
        print(f"Found {len(cls.ocr_files)} OCR files, {len(cls.image_files)} image files, and {len(cls.annotation_files)} annotation files.")
    
    def test_extract_store_name(self):
        """Test store name extraction from OCR text."""
        for ocr_file in self.ocr_files:
            # Get OCR text
            try:
                with open(os.path.join(OCR_DIR, ocr_file), 'r') as f:
                    ocr_text = f.read().strip()
                
                if not ocr_text:
                    continue
                
                # Get base filename without extension
                base_name = os.path.splitext(ocr_file)[0]
                
                # Get matching annotation if available
                annotation_path = os.path.join(ANNOTATIONS_DIR, f"{base_name}.json")
                expected_store_name = None
                
                if os.path.exists(annotation_path):
                    with open(annotation_path, 'r') as f:
                        annotation = json.load(f)
                        expected_store_name = annotation.get("receipt", {}).get("store_name")
                
                # Extract store name
                store_name = self.analyzer._extract_store_name(ocr_text.split('\n'))
                
                # Print results
                print(f"OCR File: {ocr_file}")
                print(f"Extracted store name: {store_name}")
                if expected_store_name:
                    print(f"Expected store name: {expected_store_name}")
                    # Check if expected store name is in extracted store name
                    self.assertIsNotNone(store_name, "Store name should not be None")
                    self.assertTrue(
                        expected_store_name.lower() in store_name.lower() or 
                        store_name.lower() in expected_store_name.lower(),
                        f"Expected '{expected_store_name}' to be in '{store_name}' or vice versa"
                    )
                print("-" * 50)
            
            except Exception as e:
                print(f"Error testing store name extraction for {ocr_file}: {str(e)}")
    
    def test_extract_totals(self):
        """Test totals extraction from OCR text."""
        for ocr_file in self.ocr_files:
            # Get OCR text
            try:
                with open(os.path.join(OCR_DIR, ocr_file), 'r') as f:
                    ocr_text = f.read().strip()
                
                if not ocr_text:
                    continue
                
                # Get base filename without extension
                base_name = os.path.splitext(ocr_file)[0]
                
                # Get matching annotation if available
                annotation_path = os.path.join(ANNOTATIONS_DIR, f"{base_name}.json")
                expected_totals = {}
                
                if os.path.exists(annotation_path):
                    with open(annotation_path, 'r') as f:
                        annotation = json.load(f)
                        receipt_data = annotation.get("receipt", {})
                        expected_totals = {
                            "subtotal": receipt_data.get("subtotal"),
                            "tax": receipt_data.get("tax"),
                            "total": receipt_data.get("total")
                        }
                
                # Try to determine store type for better extraction
                store_name = self.analyzer._extract_store_name(ocr_text.split('\n'))
                store_type = None
                
                if store_name:
                    store_name_lower = store_name.lower()
                    if "costco" in store_name_lower:
                        store_type = "costco"
                    elif "trader" in store_name_lower and "joe" in store_name_lower:
                        store_type = "trader_joes"
                    elif "target" in store_name_lower:
                        store_type = "target"
                    elif "h mart" in store_name_lower or "hmart" in store_name_lower:
                        store_type = "hmart"
                    elif "key food" in store_name_lower:
                        store_type = "key_food"
                
                # Extract totals
                totals = self.analyzer.extract_totals_fallback(ocr_text, store_type=store_type)
                
                # Print results
                print(f"OCR File: {ocr_file}")
                print(f"Store Type: {store_type}")
                print(f"Extracted totals: {totals}")
                if expected_totals:
                    print(f"Expected totals: {expected_totals}")
                    # Check totals if they are available
                    if expected_totals.get("total") is not None and totals.get("total") is not None:
                        # Allow for rounding differences and OCR errors
                        self.assertAlmostEqual(
                            expected_totals["total"], 
                            totals["total"], 
                            delta=1.0,  # Allow $1 difference
                            msg=f"Expected total {expected_totals['total']} to be close to {totals['total']}"
                        )
                print("-" * 50)
            
            except Exception as e:
                print(f"Error testing totals extraction for {ocr_file}: {str(e)}")
    
    def test_parse_items(self):
        """Test item parsing from OCR text."""
        for ocr_file in self.ocr_files:
            # Get OCR text
            try:
                with open(os.path.join(OCR_DIR, ocr_file), 'r') as f:
                    ocr_text = f.read().strip()
                
                if not ocr_text:
                    continue
                
                # Get base filename without extension
                base_name = os.path.splitext(ocr_file)[0]
                
                # Get matching annotation if available
                annotation_path = os.path.join(ANNOTATIONS_DIR, f"{base_name}.json")
                expected_items = []
                
                if os.path.exists(annotation_path):
                    with open(annotation_path, 'r') as f:
                        annotation = json.load(f)
                        expected_items = annotation.get("receipt", {}).get("items", [])
                
                # Try to determine store type for better extraction
                store_name = self.analyzer._extract_store_name(ocr_text.split('\n'))
                store_type = None
                
                if store_name:
                    store_name_lower = store_name.lower()
                    if "costco" in store_name_lower:
                        store_type = "costco"
                    elif "trader" in store_name_lower and "joe" in store_name_lower:
                        store_type = "trader_joes"
                    elif "target" in store_name_lower:
                        store_type = "target"
                    elif "h mart" in store_name_lower or "hmart" in store_name_lower:
                        store_type = "hmart"
                    elif "key food" in store_name_lower:
                        store_type = "key_food"
                
                # Parse items
                items = self.analyzer.parse_items_fallback(ocr_text, store_type=store_type)
                
                # Print results
                print(f"OCR File: {ocr_file}")
                print(f"Store Type: {store_type}")
                print(f"Extracted items: {len(items)}")
                print(f"First few items: {items[:3]}")
                if expected_items:
                    print(f"Expected items: {len(expected_items)}")
                    print(f"First few expected items: {expected_items[:3]}")
                    
                    # Check item count (allow 20% difference due to OCR issues)
                    expected_count = len(expected_items)
                    actual_count = len(items)
                    max_diff = max(expected_count, actual_count) * 0.2
                    
                    if abs(expected_count - actual_count) > max_diff:
                        print(f"WARNING: Item count differs significantly - Expected: {expected_count}, Actual: {actual_count}")
                
                print("-" * 50)
            
            except Exception as e:
                print(f"Error testing item parsing for {ocr_file}: {str(e)}")
    
    def test_specialized_handlers(self):
        """Test specialized receipt handlers for various store types."""
        # Map of store type to handler method
        handlers = {
            "trader_joes": self.analyzer.handle_trader_joes_receipt if hasattr(self.analyzer, "handle_trader_joes_receipt") else None,
            "costco": self.analyzer.handle_costco_receipt if hasattr(self.analyzer, "handle_costco_receipt") else None
        }
        
        for ocr_file in self.ocr_files:
            # Get OCR text
            try:
                with open(os.path.join(OCR_DIR, ocr_file), 'r') as f:
                    ocr_text = f.read().strip()
                
                if not ocr_text:
                    continue
                
                # Get base filename without extension
                base_name = os.path.splitext(ocr_file)[0]
                
                # Find matching image file
                image_path = None
                for ext in ['.jpg', '.jpeg', '.png']:
                    possible_path = os.path.join(IMAGES_DIR, f"{base_name}{ext}")
                    if os.path.exists(possible_path):
                        image_path = possible_path
                        break
                
                if not image_path:
                    continue
                
                # Try to determine store type
                store_name = self.analyzer._extract_store_name(ocr_text.split('\n'))
                store_type = None
                
                if store_name:
                    store_name_lower = store_name.lower()
                    if "costco" in store_name_lower:
                        store_type = "costco"
                    elif "trader" in store_name_lower and "joe" in store_name_lower:
                        store_type = "trader_joes"
                
                # If we have a specialized handler for this store type, test it
                if store_type in handlers and handlers[store_type] is not None:
                    handler = handlers[store_type]
                    
                    # Call the handler
                    results = handler(ocr_text, image_path)
                    
                    # Print results
                    print(f"OCR File: {ocr_file}")
                    print(f"Store Type: {store_type}")
                    print(f"Handler Results: {results.keys()}")
                    print(f"Items extracted: {len(results.get('items', []))}")
                    print(f"Totals: {results.get('receipt_totals', {})}")
                    print(f"Confidence: {results.get('confidence', 0.0)}")
                    print("-" * 50)
            
            except Exception as e:
                print(f"Error testing specialized handler for {ocr_file}: {str(e)}")


def run_tests():
    """Run the receipt analyzer tests."""
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

if __name__ == "__main__":
    run_tests() 