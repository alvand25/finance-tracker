#!/usr/bin/env python3
"""
Test script for Costco receipt parsing.
This script tests the improvements to the receipt parser for Costco receipts.
"""

import os
import sys
import json
from typing import Dict, Any
import re

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.receipt import Receipt
from utils.receipt_analyzer import ReceiptAnalyzer
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService

def test_costco_receipt(image_path: str) -> Dict[str, Any]:
    """
    Test Costco receipt parsing using the enhanced parser.
    
    Args:
        image_path: Path to the Costco receipt image
        
    Returns:
        Dictionary with test results
    """
    print(f"Testing Costco receipt parsing with image: {image_path}")
    
    # Initialize storage and receipt service
    storage = JSONStorage(data_dir="data")
    receipt_service = ReceiptService(storage, upload_dir="uploads/receipts")
    
    # Sample receipt text for testing without image
    costco_text = """
    COSTCO WHOLESALE
    Queens #243
    32-50 Vernon Blvd
    Long Island, NY 11106
    
    TX Member 112016559052
    1854948 GAP SHORT     14.99 F
    1583270 NIKECLUBCREW  32.99 F
    1841021 GERRY SHORT   12.99 F
    00003483l0 / 1841021   3.00-
    E     818073 KS TORTELLON  11.29
    E    1234809 SNAPPLEDIET*  19.99
    E     549797 BISCOFF        7.99
    E    1853333 COOKIEMOUSSE  10.99
    E      3741 ALB ENVY        8.99
    E    1748763 KS BRKFSTSND  16.49
    E     399999 MADELEINES     8.49
    E    1780170 32DTANK3PACK  12.99 F
    E    1792879 POM JUICE     10.39
    E    1235089 BAGELS         7.99
    E     890181 KS WLDSALMON  18.99
    E    1312509 MUSH VTY       9.99
    TOTAL NUMBER OF ITEMS SOLD -  15
    SUBTOTAL                  202.55
    TAX                         0.00
    *** TOTAL                 202.55
    XXXXXXXXXXXXXX9433           H
    AID:  A0000000031010
    Seq#  4646      App#: 09430D
    Visa      Resp: APPROVED
    Tran ID#: 50970000464...
    """
    
    results = {
        "receipt_type": "Costco",
        "tests": []
    }
    
    # Test 1: Test store recognition
    test1 = {"name": "Store Recognition", "passed": False, "details": ""}
    store_name = ReceiptAnalyzer._extract_store_name(costco_text.split('\n'))
    test1["passed"] = store_name and "costco" in store_name.lower()
    test1["details"] = f"Store name extracted: {store_name}"
    results["tests"].append(test1)
    
    # Validate this is actually a Costco receipt for image-based tests
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_data = f.read()
            analyzer = ReceiptAnalyzer()
            receipt_text = analyzer.extract_text(image_path)
            detected_store = analyzer._extract_store_name(receipt_text.split('\n'))
            
            if detected_store and "costco" not in detected_store.lower():
                print(f"WARNING: The provided image does not appear to be a Costco receipt. Detected: {detected_store}")
                results["warning"] = f"Not a Costco receipt. Detected: {detected_store}"
                results["summary"] = {
                    "total_tests": 1,
                    "passing_tests": 0,
                    "success_rate": "0.0%"
                }
                return results
    
    # Test 2: Test currency detection
    test2 = {"name": "Currency Detection", "passed": False, "details": ""}
    currency = ReceiptAnalyzer._extract_currency(costco_text)
    test2["passed"] = currency == "USD"
    test2["details"] = f"Currency extracted: {currency}"
    results["tests"].append(test2)
    
    # Test 3: Test total extraction
    test3 = {"name": "Total Extraction", "passed": False, "details": ""}
    totals = ReceiptAnalyzer.extract_receipt_totals(costco_text)
    test3["passed"] = totals.get("total") == 202.55
    test3["details"] = f"Total extracted: {totals.get('total')}"
    results["tests"].append(test3)
    
    # Test 4: Test item extraction
    test4 = {"name": "Item Extraction", "passed": False, "details": ""}
    items = ReceiptAnalyzer.parse_items(costco_text)
    test4["passed"] = len(items) > 0
    test4["details"] = f"Items extracted: {len(items)}"
    results["tests"].append(test4)
    
    # Test 5: Test with actual image if available
    test5 = {"name": "Full Receipt Analysis", "passed": False, "details": ""}
    
    if os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
                
                # Create a new receipt
                receipt = Receipt(image_url="test_costco_receipt.jpg")
                
                # Process the receipt
                processed_receipt = receipt_service.process_receipt(receipt, image_data)
                
                test5["passed"] = (processed_receipt.processing_status == "completed" 
                                and processed_receipt.total_amount == 202.55
                                and len(processed_receipt.items) > 0)
                test5["details"] = (f"Processing status: {processed_receipt.processing_status}, "
                                  f"Total amount: {processed_receipt.total_amount}, "
                                  f"Items extracted: {len(processed_receipt.items)}")
        except Exception as e:
            test5["details"] = f"Error processing image: {str(e)}"
    else:
        test5["details"] = f"Image file not found: {image_path}"
    
    results["tests"].append(test5)
    
    # Calculate overall result
    passing_tests = sum(1 for test in results["tests"] if test["passed"])
    results["summary"] = {
        "total_tests": len(results["tests"]),
        "passing_tests": passing_tests,
        "success_rate": f"{passing_tests / len(results['tests']) * 100:.1f}%"
    }
    
    # Print results
    print(json.dumps(results, indent=2))
    
    return results

if __name__ == "__main__":
    # Get image path from command line or use default
    image_path = sys.argv[1] if len(sys.argv) > 1 else "sample_receipt.jpg"
    test_costco_receipt(image_path) 