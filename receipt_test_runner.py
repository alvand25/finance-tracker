#!/usr/bin/env python3
"""
Receipt Test Runner

This script tests the receipt processing pipeline by:
1. Processing sample receipt images
2. Extracting and saving raw OCR text from each image
3. Running the processing pipeline on each image
4. Comparing results with expected outputs
5. Generating a test report

Usage:
  python receipt_test_runner.py [options]

Options:
  --all                 Process all sample images
  --image=<path>        Process a specific image
  --generate-expected   Generate expected output JSON files
  --verbose             Show detailed output
"""

import os
import sys
import json
import argparse
import shutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import cv2
import pytesseract
from PIL import Image
import io
import time
import traceback

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.receipt import Receipt
from utils.receipt_analyzer import ReceiptAnalyzer
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService

# Constants
SAMPLES_DIR = "samples"
IMAGES_DIR = os.path.join(SAMPLES_DIR, "images")
OCR_DIR = os.path.join(SAMPLES_DIR, "ocr")
EXPECTED_DIR = os.path.join(SAMPLES_DIR, "expected")
REPORT_DIR = os.path.join(SAMPLES_DIR, "reports")

# Test vendors to focus on
VENDORS = ["Costco", "Trader Joe's", "Target", "H Mart", "Key Food"]

def ensure_dirs():
    """Ensure all required directories exist."""
    for dir_path in [SAMPLES_DIR, IMAGES_DIR, OCR_DIR, EXPECTED_DIR, REPORT_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Created directory: {dir_path}")


def extract_ocr_text(image_path: str, save: bool = True) -> str:
    """
    Extract raw OCR text from an image.
    
    Args:
        image_path: Path to the image file
        save: Whether to save the extracted text to a file
        
    Returns:
        Extracted text as a string
    """
    print(f"Extracting OCR text from: {image_path}")
    
    # Read the image file
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Initialize ReceiptAnalyzer
    analyzer = ReceiptAnalyzer()
    
    # Preprocess the image and extract text
    preprocessed_image = analyzer.preprocess_image(image_data)
    extracted_text = analyzer.extract_text(preprocessed_image)
    
    if save:
        # Save the extracted text to a file
        base_name = os.path.basename(image_path).split('.')[0]
        output_path = os.path.join(OCR_DIR, f"{base_name}.txt")
        
        with open(output_path, "w") as f:
            f.write(extracted_text)
        
        print(f"Saved OCR text to: {output_path}")
    
    return extracted_text


def process_receipt_image(image_path: str, service: ReceiptService) -> Tuple[Receipt, Dict[str, Any]]:
    """
    Process a receipt image using the receipt service.
    
    Args:
        image_path: Path to the image file
        service: Receipt service instance
        
    Returns:
        Processed receipt and results dictionary
    """
    print(f"Processing receipt image: {image_path}")
    
    # Initialize analyzer
    analyzer = ReceiptAnalyzer()
    
    # Read the image file
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Process the receipt
    try:
        # First extract OCR text
        preprocessed_image = analyzer.preprocess_image(image_data)
        receipt_text = analyzer.extract_text(preprocessed_image)
        
        # Extract store name
        store_name = analyzer._extract_store_name(receipt_text.split('\n'))
        print(f"Detected store name: {store_name}")
        
        # Process with the receipt service
        receipt = service.process_receipt({}, image_data=image_data, file_path=image_path)
        
        # Prepare results
        results = {
            "image_path": image_path,
            "processing_status": receipt.processing_status,
            "store_name": receipt.store_name,
            "date": receipt.transaction_date.isoformat() if receipt.transaction_date else None,
            "currency": receipt.currency_type if hasattr(receipt, 'currency_type') else receipt.currency,
            "subtotal": receipt.subtotal_amount if hasattr(receipt, 'subtotal_amount') else receipt.subtotal,
            "tax": receipt.tax_amount if hasattr(receipt, 'tax_amount') else receipt.tax,
            "total": receipt.total_amount if hasattr(receipt, 'total_amount') else receipt.total,
            "payment_method": receipt.payment_method,
            "items_count": len(receipt.items),
            "items": receipt.items
        }
        
        # Apply vendor-specific processing for improved results
        results = process_vendor_specifics(results, store_name, receipt_text, image_path, analyzer)
        
        return receipt, results
    
    except Exception as e:
        print(f"Error processing receipt: {str(e)}")
        traceback.print_exc()
        
        # Return a minimal results dictionary
        error_results = {
            "image_path": image_path,
            "processing_status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        
        return None, error_results


def save_expected_output(results: Dict[str, Any], image_path: str) -> None:
    """
    Save expected output JSON file for a processed receipt.
    
    Args:
        results: Results dictionary from processing
        image_path: Path to the original image file
    """
    base_name = os.path.basename(image_path).split('.')[0]
    output_path = os.path.join(EXPECTED_DIR, f"{base_name}.json")
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Saved expected output to: {output_path}")


def compare_with_expected(results: Dict[str, Any], image_path: str) -> Dict[str, Any]:
    """
    Compare processing results with expected output.
    
    Args:
        results: Results dictionary from processing
        image_path: Path to the original image file
        
    Returns:
        Dictionary with comparison results
    """
    base_name = os.path.basename(image_path).split('.')[0]
    expected_path = os.path.join(EXPECTED_DIR, f"{base_name}.json")
    
    if not os.path.exists(expected_path):
        return {
            "status": "no_expected_file",
            "message": f"No expected output file found at {expected_path}",
            "image": image_path
        }
    
    # Load expected output
    with open(expected_path, "r") as f:
        expected = json.load(f)
    
    # Initialize comparison
    comparison = {
        "status": "pass",
        "differences": [],
        "image": image_path,
        "vendor": expected.get("store", "Unknown"),
        "handler_used": results.get("handler", "generic"),
        "confidence": results.get("confidence", 0)
    }
    
    # Store processing time if available
    if "processing_time" in results:
        comparison["processing_time"] = results["processing_time"]
    
    # Fields to compare with exact match
    exact_match_fields = ["store_name", "currency", "payment_method"]
    
    for field in exact_match_fields:
        if field in results and field in expected:
            if results[field] != expected[field]:
                comparison["status"] = "fail"
                comparison["differences"].append({
                    "field": field,
                    "actual": results[field],
                    "expected": expected[field],
                    "match_type": "exact"
                })
    
    # Numerical fields to compare with tolerance
    # Define tolerance: either 1% or absolute 0.05, whichever is larger
    numeric_fields = ["subtotal", "tax", "total"]
    
    for field in numeric_fields:
        if field in results and field in expected:
            # Skip if either value is None
            if results[field] is None or expected[field] is None:
                if results[field] != expected[field]:
                    comparison["status"] = "fail"
                    comparison["differences"].append({
                        "field": field,
                        "actual": results[field],
                        "expected": expected[field],
                        "match_type": "exact",
                        "note": "One value is None"
                    })
                continue
                
            # Convert to float if necessary
            try:
                actual = float(results[field])
                expected_val = float(expected[field])
                
                # Calculate difference and tolerance
                diff = abs(actual - expected_val)
                percent_tolerance = expected_val * 0.01
                abs_tolerance = 0.05
                tolerance = max(percent_tolerance, abs_tolerance)
                
                if diff > tolerance:
                    comparison["status"] = "fail"
                    comparison["differences"].append({
                        "field": field,
                        "actual": actual,
                        "expected": expected_val,
                        "difference": diff,
                        "tolerance": tolerance,
                        "match_type": "numeric"
                    })
            except (ValueError, TypeError):
                # Fall back to exact comparison if conversion fails
                if results[field] != expected[field]:
                    comparison["status"] = "fail"
                    comparison["differences"].append({
                        "field": field,
                        "actual": results[field],
                        "expected": expected[field],
                        "match_type": "exact",
                        "note": "Could not convert to numeric for tolerance comparison"
                    })
    
    # Specialized comparison for items
    if "items" in results and "items" in expected:
        # First check count match
        result_items_count = len(results.get("items", []))
        expected_items_count = len(expected.get("items", []))
        
        # Add item count information regardless of match
        comparison["item_counts"] = {
            "actual": result_items_count,
            "expected": expected_items_count,
            "difference": result_items_count - expected_items_count
        }
        
        # Acceptable item count difference (e.g., within 20% or 2 items, whichever is greater)
        count_tolerance = max(2, expected_items_count * 0.2)
        count_diff = abs(result_items_count - expected_items_count)
        
        if count_diff > count_tolerance:
            comparison["status"] = "fail"
            comparison["differences"].append({
                "field": "items_count",
                "actual": result_items_count,
                "expected": expected_items_count,
                "difference": count_diff,
                "tolerance": count_tolerance,
                "match_type": "numeric"
            })
        
        # Check specific items
        if result_items_count > 0 and expected_items_count > 0:
            # Normalize item keys for comparison
            expected_items = []
            for item in expected["items"]:
                normalized_item = {}
                if "name" in item:
                    normalized_item["description"] = item["name"]
                elif "description" in item:
                    normalized_item["description"] = item["description"]
                    
                if "price" in item:
                    normalized_item["price"] = item["price"]
                elif "amount" in item:
                    normalized_item["price"] = item["amount"]
                
                if "quantity" in item:
                    normalized_item["quantity"] = item["quantity"]
                else:
                    normalized_item["quantity"] = 1
                    
                expected_items.append(normalized_item)
            
            # Create lists of descriptions for fuzzy matching
            expected_descriptions = [item.get("description", "").lower() for item in expected_items]
            actual_descriptions = [item.get("description", "").lower() for item in results["items"]]
            
            # Count recognized items (exact match or close enough by description)
            recognized_count = 0
            price_match_count = 0
            
            # Check each expected item exists in results (by description)
            for i, expected_item in enumerate(expected_items):
                expected_desc = expected_item.get("description", "").lower()
                expected_price = float(expected_item.get("price", 0))
                best_match_idx = -1
                best_match_score = 0
                
                # Look for exact or close match
                for j, actual_desc in enumerate(actual_descriptions):
                    if expected_desc == actual_desc:
                        best_match_idx = j
                        best_match_score = 1.0
                        break
                    elif expected_desc in actual_desc or actual_desc in expected_desc:
                        score = min(len(expected_desc), len(actual_desc)) / max(len(expected_desc), len(actual_desc))
                        if score > 0.7 and score > best_match_score:
                            best_match_idx = j
                            best_match_score = score
                
                # If found a match, check price
                if best_match_idx >= 0:
                    recognized_count += 1
                    actual_price = float(results["items"][best_match_idx].get("price", 0))
                    
                    # Calculate price difference and tolerance
                    price_diff = abs(actual_price - expected_price)
                    price_tolerance = max(0.05, expected_price * 0.05)  # 5% or $0.05, whichever is larger
                    
                    if price_diff <= price_tolerance:
                        price_match_count += 1
            
            # Calculate recognition rates
            if expected_items_count > 0:
                description_recognition_rate = recognized_count / expected_items_count
                price_recognition_rate = price_match_count / expected_items_count
                
                comparison["item_recognition"] = {
                    "description_matches": recognized_count,
                    "price_matches": price_match_count,
                    "description_rate": f"{description_recognition_rate:.2f}",
                    "price_rate": f"{price_recognition_rate:.2f}"
                }
                
                # Fail if too few items recognized
                if description_recognition_rate < 0.7:
                    comparison["status"] = "fail"
                    comparison["differences"].append({
                        "field": "item_recognition",
                        "actual": f"{description_recognition_rate:.2f}",
                        "expected": "0.70+",
                        "match_type": "rate",
                        "note": "Too few items recognized correctly"
                    })
                
                # Warn if price matching is poor
                if price_recognition_rate < 0.7 and description_recognition_rate >= 0.7:
                    comparison["differences"].append({
                        "field": "price_recognition",
                        "actual": f"{price_recognition_rate:.2f}",
                        "expected": "0.70+",
                        "match_type": "rate",
                        "note": "Item descriptions matched but prices did not"
                    })
    
    # If no handler was used but still passed, make note of it
    if comparison["status"] == "pass" and not results.get("handler"):
        comparison["note"] = "Passed without using a specialized handler"
    
    # Summarize results
    comparison["summary"] = {
        "outcome": comparison["status"],
        "differences_count": len(comparison["differences"]),
        "confidence": results.get("confidence", 0),
        "vendor": expected.get("store", "Unknown")
    }
    
    return comparison


def generate_report(test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a test report from the test results.
    
    Args:
        test_results: List of test result dictionaries
        
    Returns:
        Report dictionary
    """
    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results if result.get("comparison", {}).get("status") == "pass")
    no_expected_tests = sum(1 for result in test_results if result.get("comparison", {}).get("status") == "no_expected_file")
    failed_tests = total_tests - passed_tests - no_expected_tests
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": failed_tests,
        "no_expected_tests": no_expected_tests,
        "pass_rate": f"{passed_tests / total_tests * 100:.1f}%" if total_tests > 0 else "N/A",
        "tests": test_results
    }
    
    # Group results by vendor
    vendor_results = {}
    for result in test_results:
        store_name = result.get("results", {}).get("store_name", "Unknown")
        
        # Find the vendor this belongs to
        vendor = "Other"
        for v in VENDORS:
            if v.lower() in store_name.lower():
                vendor = v
                break
        
        if vendor not in vendor_results:
            vendor_results[vendor] = {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "no_expected": 0
            }
        
        vendor_results[vendor]["total"] += 1
        
        comparison_status = result.get("comparison", {}).get("status")
        if comparison_status == "pass":
            vendor_results[vendor]["passed"] += 1
        elif comparison_status == "no_expected_file":
            vendor_results[vendor]["no_expected"] += 1
        else:
            vendor_results[vendor]["failed"] += 1
    
    report["vendor_results"] = vendor_results
    
    return report


def save_report(report: Dict[str, Any]) -> str:
    """
    Save the test report to a file.
    
    Args:
        report: Report dictionary
        
    Returns:
        Path to the saved report file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"report_{timestamp}.json")
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"Saved test report to: {report_path}")
    
    # Also save as latest report
    latest_path = os.path.join(REPORT_DIR, "latest_report.json")
    shutil.copyfile(report_path, latest_path)
    
    return report_path


def print_report_summary(report: Dict[str, Any]) -> None:
    """Print a summary of the test report."""
    print("\n===== TEST REPORT SUMMARY =====")
    print(f"Timestamp: {report['timestamp']}")
    print(f"Total Tests: {report['total_tests']}")
    print(f"Passed Tests: {report['passed_tests']} ({report['pass_rate']})")
    print(f"Failed Tests: {report['failed_tests']}")
    print(f"No Expected Output: {report['no_expected_tests']}")
    
    print("\nVendor Results:")
    for vendor, results in report.get("vendor_results", {}).items():
        pass_rate = results["passed"] / results["total"] * 100 if results["total"] > 0 else 0
        print(f"  {vendor}: {results['passed']}/{results['total']} passed ({pass_rate:.1f}%)")
    
    print("\nFailed Tests:")
    for test in report.get("tests", []):
        if test.get("comparison", {}).get("status") == "fail":
            print(f"  {test.get('image_path')}: {len(test.get('comparison', {}).get('differences', []))} differences")


def initialize_receipt_service() -> ReceiptService:
    """Initialize and return a ReceiptService instance."""
    storage = JSONStorage(data_dir="data")
    service = ReceiptService(storage, upload_dir="uploads/receipts")
    return service


def copy_uploads_to_samples():
    """Copy existing uploaded receipts to the samples directory."""
    uploads_dir = "uploads/receipts"
    if not os.path.exists(uploads_dir):
        print(f"Uploads directory does not exist: {uploads_dir}")
        return
    
    # Get all uploaded receipt images
    receipt_files = [f for f in os.listdir(uploads_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
    
    for file_name in receipt_files:
        source_path = os.path.join(uploads_dir, file_name)
        target_path = os.path.join(IMAGES_DIR, file_name)
        
        # Skip if file already exists in samples
        if os.path.exists(target_path):
            print(f"File already exists in samples: {file_name}")
            continue
        
        # Copy the file
        shutil.copy2(source_path, target_path)
        print(f"Copied {file_name} to samples directory")


def process_vendor_specifics(results, store_name, ocr_text, image_path, analyzer):
    """
    Apply vendor-specific processing to improve results.
    
    Args:
        results: Current results dictionary
        store_name: Detected store name
        ocr_text: OCR text from the receipt
        image_path: Path to the receipt image
        analyzer: Receipt analyzer instance
        
    Returns:
        Updated results dictionary
    """
    # Lowercase store name for comparison
    store_name_lower = store_name.lower() if store_name else ""
    
    # Process Costco receipts using specialized handler
    if "costco" in store_name_lower and hasattr(analyzer, "handle_costco_receipt"):
        print("Applying Costco-specific handler")
        costco_data = analyzer.handle_costco_receipt(ocr_text, image_path)
        
        # Merge Costco results if they have more items or better totals
        if costco_data and (len(costco_data.get("items", [])) > len(results.get("items", [])) or
            (costco_data.get("total") and not results.get("total"))):
            
            print(f"Costco handler found {len(costco_data.get('items', []))} items")
            
            results["items"] = costco_data.get("items", [])
            results["subtotal"] = costco_data.get("subtotal")
            results["tax"] = costco_data.get("tax")
            results["total"] = costco_data.get("total")
            results["store_name"] = costco_data.get("store") or results.get("store_name")
            results["currency"] = costco_data.get("currency") or results.get("currency")
            results["date"] = costco_data.get("date") or results.get("date")
            results["confidence"] = costco_data.get("confidence", 0.7)
            results["handler"] = "costco"
            
            if results.get("total"):
                results["processing_status"] = "processed"
    
    # Process Trader Joe's receipts using specialized handler
    elif ("trader" in store_name_lower and "joe" in store_name_lower) and hasattr(analyzer, "handle_trader_joes_receipt"):
        print("Applying Trader Joe's-specific handler")
        tj_data = analyzer.handle_trader_joes_receipt(ocr_text, image_path)
        
        # Merge Trader Joe's results if they have more items or better totals
        if tj_data and (len(tj_data.get("items", [])) > len(results.get("items", [])) or
            (tj_data.get("total") and not results.get("total"))):
            
            print(f"Trader Joe's handler found {len(tj_data.get('items', []))} items")
            
            results["items"] = tj_data.get("items", [])
            results["subtotal"] = tj_data.get("subtotal")
            results["tax"] = tj_data.get("tax")
            results["total"] = tj_data.get("total")
            results["store_name"] = tj_data.get("store") or results.get("store_name")
            results["currency"] = tj_data.get("currency") or results.get("currency")
            results["date"] = tj_data.get("date") or results.get("date")
            results["confidence"] = tj_data.get("confidence", 0.7)
            results["handler"] = "trader_joes"
            
            if results.get("total"):
                results["processing_status"] = "processed"
    
    # Process H Mart receipts using specialized handler
    elif ("h mart" in store_name_lower or "hmart" in store_name_lower) and hasattr(analyzer, "handle_hmart_receipt"):
        print("Applying H Mart-specific handler")
        hmart_data = analyzer.handle_hmart_receipt(ocr_text, image_path)
        
        # Merge H Mart results if they have more items or better totals
        if hmart_data and (len(hmart_data.get("items", [])) > len(results.get("items", [])) or
            (hmart_data.get("total") and not results.get("total"))):
            
            print(f"H Mart handler found {len(hmart_data.get('items', []))} items")
            
            results["items"] = hmart_data.get("items", [])
            results["subtotal"] = hmart_data.get("subtotal")
            results["tax"] = hmart_data.get("tax")
            results["total"] = hmart_data.get("total")
            results["store_name"] = hmart_data.get("store") or results.get("store_name")
            results["currency"] = hmart_data.get("currency") or results.get("currency")
            results["date"] = hmart_data.get("date") or results.get("date")
            results["confidence"] = hmart_data.get("confidence", {}).get("overall", 0.7)
            results["handler"] = "hmart"
            
            if results.get("total"):
                results["processing_status"] = "processed"
    
    # Process Key Food receipts using specialized handler
    elif "key food" in store_name_lower and hasattr(analyzer, "handle_key_food_receipt"):
        print("Applying Key Food-specific handler")
        key_food_data = analyzer.handle_key_food_receipt(ocr_text, image_path)
        
        # Merge Key Food results if they have more items or better totals
        if key_food_data and (len(key_food_data.get("items", [])) > len(results.get("items", [])) or
            (key_food_data.get("total") and not results.get("total"))):
            
            print(f"Key Food handler found {len(key_food_data.get('items', []))} items")
            
            results["items"] = key_food_data.get("items", [])
            results["subtotal"] = key_food_data.get("subtotal")
            results["tax"] = key_food_data.get("tax")
            results["total"] = key_food_data.get("total")
            results["store_name"] = key_food_data.get("store") or results.get("store_name")
            results["currency"] = key_food_data.get("currency") or results.get("currency")
            results["date"] = key_food_data.get("date") or results.get("date")
            results["confidence"] = key_food_data.get("confidence", {}).get("overall", 0.7)
            results["handler"] = "key_food"
            
            if results.get("total"):
                results["processing_status"] = "processed"
    
    # Apply fallback processing for unrecognized stores
    elif not results.get("handler"):
        print(f"Using fallback processing for store: {store_name}")
        
        # Determine store type for fallback processing
        store_type = None
        if "costco" in store_name_lower:
            store_type = "costco"
        elif "trader" in store_name_lower and "joe" in store_name_lower:
            store_type = "trader_joes"
        elif "h mart" in store_name_lower or "hmart" in store_name_lower:
            store_type = "hmart"
        elif "key food" in store_name_lower:
            store_type = "key_food"
        
        # Parse items using fallback with store type hint
        if hasattr(analyzer, "parse_items_fallback") and store_type:
            items = analyzer.parse_items_fallback(ocr_text, store_type=store_type)
            if items and len(items) > len(results.get("items", [])):
                print(f"Fallback parsing found {len(items)} items with {store_type} patterns")
                results["items"] = items
                results["handler"] = f"{store_type}_fallback"
        
        # Extract totals using fallback with store type hint
        if hasattr(analyzer, "extract_totals_fallback") and store_type:
            totals = analyzer.extract_totals_fallback(ocr_text, store_type=store_type)
            if totals and totals.get("total") and not results.get("total"):
                print(f"Fallback extraction found totals with {store_type} patterns")
                results["subtotal"] = totals.get("subtotal")
                results["tax"] = totals.get("tax")
                results["total"] = totals.get("total")
                results["currency"] = totals.get("currency") or results.get("currency", "USD")
                results["handler"] = f"{store_type}_fallback"
                results["processing_status"] = "processed"
    
    # Add confidence score if missing
    if "confidence" not in results:
        # Calculate confidence based on available data
        confidence = 0.5  # Base confidence
        
        if results.get("items"):
            confidence += min(0.2, len(results.get("items", [])) * 0.01)
        
        if results.get("total"):
            confidence += 0.1
            
        if results.get("subtotal") and results.get("tax"):
            confidence += 0.1
            
        results["confidence"] = min(0.95, confidence)
    
    return results


def main():
    """Main entry point for the receipt test runner."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Receipt Test Runner")
    parser.add_argument("--all", action="store_true", help="Process all sample images")
    parser.add_argument("--image", help="Process a specific image")
    parser.add_argument("--generate-expected", action="store_true", help="Generate expected output JSON files")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--copy-uploads", action="store_true", help="Copy uploaded receipts to samples directory")
    parser.add_argument("--create-samples", action="store_true", help="Create sample dataset from uploaded receipts")
    parser.add_argument("--vendor", help="Filter images by vendor (e.g., 'Key Food', 'Costco')")
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_dirs()
    
    # Copy uploaded receipts if requested
    if args.copy_uploads:
        copy_uploads_to_samples()
    
    # Create sample dataset if requested
    if args.create_samples:
        print("Creating sample dataset from uploaded receipts")
        try:
            # Import the create_sample_dataset script
            import create_sample_dataset
            
            # Create sample dataset
            create_sample_dataset.main(["--process-all"])
            print("Sample dataset created successfully")
        except Exception as e:
            print(f"Error creating sample dataset: {str(e)}")
            traceback.print_exc()
    
    # Initialize receipt service
    service = initialize_receipt_service()
    
    # Determine which images to process
    image_paths = []
    
    if args.image:
        # Process a specific image
        if os.path.exists(args.image):
            image_paths.append(args.image)
        else:
            # Check if it's in the samples directory
            sample_path = os.path.join(IMAGES_DIR, args.image)
            if os.path.exists(sample_path):
                image_paths.append(sample_path)
            else:
                print(f"Image file not found: {args.image}")
                return
    elif args.all:
        # Process all sample images
        image_paths = [
            os.path.join(IMAGES_DIR, f) 
            for f in os.listdir(IMAGES_DIR) 
            if f.endswith((".jpg", ".jpeg", ".png"))
        ]
    else:
        print("No images specified. Use --all to process all samples or --image to specify an image.")
        return
    
    # Filter by vendor if specified
    if args.vendor and image_paths:
        filtered_paths = []
        vendor_lower = args.vendor.lower()
        
        for path in image_paths:
            # Check if vendor name is in expected output
            base_name = os.path.basename(path).split('.')[0]
            expected_path = os.path.join(EXPECTED_DIR, f"{base_name}.json")
            
            if os.path.exists(expected_path):
                try:
                    with open(expected_path, "r") as f:
                        expected = json.load(f)
                        if "store" in expected and vendor_lower in expected["store"].lower():
                            filtered_paths.append(path)
                except Exception:
                    # If can't parse JSON, include the path anyway
                    filtered_paths.append(path)
            else:
                # If no expected file, include the path
                filtered_paths.append(path)
        
        # Update image paths
        image_paths = filtered_paths
        print(f"Filtered to {len(image_paths)} images matching vendor: {args.vendor}")
    
    # Process each image
    test_results = []
    summary = {
        "total": len(image_paths),
        "passed": 0,
        "failed": 0,
        "processed": 0,
        "errors": 0,
        "by_vendor": {},
        "by_handler": {}
    }
    
    print(f"\n{'='*80}")
    print(f"RECEIPT TEST RUNNER - Processing {len(image_paths)} images")
    print(f"{'='*80}")
    
    for i, image_path in enumerate(image_paths, 1):
        print(f"\n[{i}/{len(image_paths)}] Processing: {os.path.basename(image_path)}")
        print(f"{'-'*80}")
        
        start_time = time.time()
        
        try:
            # Extract OCR text
            ocr_text = extract_ocr_text(image_path)
            
            # Process the receipt
            receipt, results = process_receipt_image(image_path, service)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            results["processing_time"] = f"{processing_time:.2f}s"
            
            # Save expected output if requested
            if args.generate_expected and results:
                save_expected_output(results, image_path)
                comparison = {"status": "expected_generated"}
                print(f"✓ Generated expected output file")
            else:
                # Compare with expected output
                comparison = compare_with_expected(results, image_path)
                
                # Print comparison result
                if comparison["status"] == "pass":
                    print(f"✅ PASS - {os.path.basename(image_path)}")
                    summary["passed"] += 1
                elif comparison["status"] == "fail":
                    print(f"❌ FAIL - {os.path.basename(image_path)}")
                    summary["failed"] += 1
                elif comparison["status"] == "no_expected_file":
                    print(f"⚠️ NO EXPECTED FILE - {os.path.basename(image_path)}")
                    summary["processed"] += 1
                else:
                    print(f"ℹ️ {comparison['status'].upper()} - {os.path.basename(image_path)}")
                    summary["processed"] += 1
            
            # Track vendor stats
            vendor = results.get("store_name", "Unknown")
            if vendor not in summary["by_vendor"]:
                summary["by_vendor"][vendor] = {"total": 0, "passed": 0, "failed": 0}
            
            summary["by_vendor"][vendor]["total"] += 1
            if comparison["status"] == "pass":
                summary["by_vendor"][vendor]["passed"] += 1
            elif comparison["status"] == "fail":
                summary["by_vendor"][vendor]["failed"] += 1
            
            # Track handler stats
            handler = results.get("handler", "generic")
            if handler not in summary["by_handler"]:
                summary["by_handler"][handler] = {"total": 0, "passed": 0, "failed": 0}
            
            summary["by_handler"][handler]["total"] += 1
            if comparison["status"] == "pass":
                summary["by_handler"][handler]["passed"] += 1
            elif comparison["status"] == "fail":
                summary["by_handler"][handler]["failed"] += 1
            
            # Add to test results
            test_result = {
                "image_path": image_path,
                "results": results,
                "comparison": comparison,
                "processing_time": processing_time
            }
            
            test_results.append(test_result)
            
            # Print results if verbose or comparison failed
            if args.verbose or comparison["status"] == "fail":
                print(f"\nProcessing details:")
                print(f"- Store: {results.get('store_name', 'Unknown')}")
                print(f"- Handler: {results.get('handler', 'generic')}")
                print(f"- Confidence: {results.get('confidence', 0):.2f}")
                print(f"- Processing time: {processing_time:.2f}s")
                print(f"- Items extracted: {len(results.get('items', []))}")
                print(f"- Subtotal: ${results.get('subtotal', 0):.2f}")
                print(f"- Tax: ${results.get('tax', 0):.2f}")
                print(f"- Total: ${results.get('total', 0):.2f}")
                
                if comparison["status"] == "fail" and "differences" in comparison:
                    print("\nDifferences:")
                    for diff in comparison["differences"]:
                        print(f"- {diff['field']}: Expected {diff['expected']}, got {diff['actual']}")
                
                if "item_recognition" in comparison:
                    item_recog = comparison["item_recognition"]
                    print(f"\nItem Recognition:")
                    print(f"- Description matches: {item_recog['description_matches']}/{comparison['item_counts']['expected']} ({item_recog['description_rate']})")
                    print(f"- Price matches: {item_recog['price_matches']}/{comparison['item_counts']['expected']} ({item_recog['price_rate']})")
        
        except Exception as e:
            print(f"❌ ERROR - {os.path.basename(image_path)}")
            print(f"Error: {str(e)}")
            traceback.print_exc()
            
            # Add to error count
            summary["errors"] += 1
            
            # Add error result
            test_result = {
                "image_path": image_path,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "processing_time": time.time() - start_time
            }
            
            test_results.append(test_result)
    
    # Generate and save report
    report = generate_report(test_results)
    report_path = save_report(report)
    
    # Print report summary
    print_report_summary(report)
    
    # Print overall summary
    print(f"\n{'='*80}")
    print(f"TEST SUMMARY")
    print(f"{'='*80}")
    print(f"Total receipts: {summary['total']}")
    print(f"Passed: {summary['passed']} ({summary['passed']/summary['total']*100:.1f}%)")
    print(f"Failed: {summary['failed']} ({summary['failed']/summary['total']*100:.1f}%)")
    print(f"Errors: {summary['errors']} ({summary['errors']/summary['total']*100:.1f}%)")
    
    # Print vendor summary
    if summary["by_vendor"]:
        print(f"\nResults by vendor:")
        for vendor, stats in summary["by_vendor"].items():
            if stats["total"] > 0:
                pass_rate = stats["passed"] / stats["total"] * 100
                print(f"- {vendor}: {stats['passed']}/{stats['total']} passed ({pass_rate:.1f}%)")
    
    # Print handler summary
    if summary["by_handler"]:
        print(f"\nResults by handler:")
        for handler, stats in summary["by_handler"].items():
            if stats["total"] > 0:
                pass_rate = stats["passed"] / stats["total"] * 100
                print(f"- {handler}: {stats['passed']}/{stats['total']} passed ({pass_rate:.1f}%)")
    
    print(f"\nDetailed report saved to: {report_path}")
    
    # Return 0 if all tests passed, 1 otherwise
    return 0 if summary["failed"] == 0 and summary["errors"] == 0 else 1


if __name__ == "__main__":
    main() 