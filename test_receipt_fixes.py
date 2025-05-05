#!/usr/bin/env python3
"""
Test script to verify the fixes implemented for receipt parsing.
Focuses on Costco, H Mart, and other receipt types with known issues.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import receipt analysis modules
from services.receipt_analyzer import UnifiedReceiptAnalyzer, ParsedReceipt
from utils.image_preprocessor import ImagePreprocessor

def find_test_receipts(directory: str, filter_term: str = None) -> List[str]:
    """Find receipt images in the specified directory, optionally filtering by name."""
    image_paths = []
    for ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic']:
        if filter_term:
            glob_pattern = f"*{filter_term}*{ext}"
        else:
            glob_pattern = f"*{ext}"
        for path in Path(directory).glob(glob_pattern):
            image_paths.append(str(path))
    
    return sorted(image_paths)

def test_receipt_parser(image_path: str) -> Dict[str, Any]:
    """Test a receipt image with the enhanced parser and return results."""
    logger.info(f"Testing receipt: {image_path}")
    
    # Initialize analyzer
    analyzer = UnifiedReceiptAnalyzer(debug_mode=True)
    
    # Process the file
    parsed_receipt, success = analyzer.process_file(image_path)
    
    # Extract results
    results = {
        "image_path": image_path,
        "filename": os.path.basename(image_path),
        "success": success,
        "store_name": parsed_receipt.store_name,
        "total_amount": parsed_receipt.total_amount,
        "confidence_score": parsed_receipt.confidence_score,
        "items_count": len(parsed_receipt.items) if parsed_receipt.items else 0,
        "expected_items": parsed_receipt.expected_item_count,
        "flagged_for_review": parsed_receipt.flagged_for_review,
        "has_suspicious_items": parsed_receipt.has_suspicious_items,
        "validation_notes": parsed_receipt.validation_notes,
        "processing_status": parsed_receipt.processing_status
    }
    
    # Log the results
    logger.info(f"Results for {os.path.basename(image_path)}:")
    logger.info(f"  Store: {results['store_name']}")
    logger.info(f"  Total: ${results['total_amount']}")
    logger.info(f"  Confidence: {results['confidence_score']:.4f}")
    logger.info(f"  Items: {results['items_count']}")
    
    if parsed_receipt.expected_item_count:
        logger.info(f"  Expected Items: {parsed_receipt.expected_item_count}")
    
    if parsed_receipt.validation_notes:
        logger.info(f"  Validation Notes: {parsed_receipt.validation_notes}")
    
    if parsed_receipt.has_suspicious_items:
        suspicious_count = sum(1 for item in parsed_receipt.items if item.get('suspicious', False))
        logger.info(f"  Suspicious Items: {suspicious_count}")
        
        # Print a few suspicious items as examples
        suspicious_items = [item for item in parsed_receipt.items if item.get('suspicious', False)]
        if suspicious_items:
            logger.info("  Examples of suspicious items:")
            for item in suspicious_items[:3]:
                logger.info(f"    - {item.get('name')} (${item.get('total', 0):.2f})")
    
    # List a few items as examples
    if parsed_receipt.items:
        logger.info("  Item examples:")
        for item in parsed_receipt.items[:5]:
            if not item.get('suspicious', False):
                logger.info(f"    - {item.get('name')} (${item.get('total', 0):.2f})")
    
    return results

def test_all_receipts(test_dir: str, filter_terms: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Test all receipts in the directory, filtering by optional terms."""
    logger.info(f"Testing receipts in {test_dir}")
    
    # Find all receipt images
    all_receipts = find_test_receipts(test_dir)
    logger.info(f"Found {len(all_receipts)} receipt images")
    
    # Filter receipts if needed
    if filter_terms:
        filtered_receipts = []
        for term in filter_terms:
            term_receipts = [path for path in all_receipts if term.lower() in Path(path).name.lower()]
            filtered_receipts.extend(term_receipts)
        test_receipts = list(set(filtered_receipts))  # Remove duplicates
    else:
        test_receipts = all_receipts
    
    logger.info(f"Testing {len(test_receipts)} receipts")
    
    # Test each receipt
    all_results = {
        "costco": [],
        "h_mart": [],
        "trader_joes": [],
        "key_food": [],
        "other": []
    }
    
    for image_path in test_receipts:
        try:
            result = test_receipt_parser(image_path)
            
            # Categorize by store type
            if result["store_name"] and "costco" in result["store_name"].lower():
                all_results["costco"].append(result)
            elif result["store_name"] and ("h mart" in result["store_name"].lower() or "hmart" in result["store_name"].lower()):
                all_results["h_mart"].append(result)
            elif result["store_name"] and "trader" in result["store_name"].lower():
                all_results["trader_joes"].append(result)
            elif result["store_name"] and "key food" in result["store_name"].lower():
                all_results["key_food"].append(result)
            else:
                all_results["other"].append(result)
                
        except Exception as e:
            logger.error(f"Error testing receipt {image_path}: {str(e)}")
    
    # Print summary
    logger.info("\nTesting Summary:")
    for store, results in all_results.items():
        if results:
            success_count = sum(1 for r in results if r["success"])
            avg_confidence = sum(r["confidence_score"] for r in results) / len(results) if results else 0
            avg_items = sum(r["items_count"] for r in results) / len(results) if results else 0
            
            logger.info(f"{store.upper()} Receipts: {len(results)}")
            logger.info(f"  Success Rate: {success_count / len(results):.2%}")
            logger.info(f"  Average Confidence: {avg_confidence:.4f}")
            logger.info(f"  Average Items: {avg_items:.1f}")
    
    return all_results

def save_test_results(results: Dict[str, List[Dict[str, Any]]], filename: str = None) -> None:
    """Save test results to a JSON file."""
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"receipt_test_results_{timestamp}.json"
    
    # Convert results to serializable format
    serializable_results = {}
    for store, store_results in results.items():
        serializable_results[store] = []
        for result in store_results:
            serializable_result = result.copy()
            # Ensure all values are serializable
            for key, value in serializable_result.items():
                if isinstance(value, Path):
                    serializable_result[key] = str(value)
            serializable_results[store].append(serializable_result)
    
    # Save to file
    with open(filename, 'w') as f:
        json.dump(serializable_results, f, indent=2)
    
    logger.info(f"Test results saved to {filename}")

def main():
    """Main function to run the tests."""
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Test receipt parsing")
    parser.add_argument("--dir", "-d", help="Directory with test receipts", default="test_receipts")
    parser.add_argument("--output", "-o", help="Output file for results")
    parser.add_argument("--filter", "-f", nargs="+", help="Filter receipts by filename terms")
    args = parser.parse_args()
    
    # Test receipts
    test_dir = args.dir
    if not os.path.exists(test_dir):
        logger.error(f"Test directory '{test_dir}' does not exist!")
        return 1
    
    # Run tests
    results = test_all_receipts(test_dir, args.filter)
    
    # Save results if requested
    if args.output:
        save_test_results(results, args.output)
    else:
        save_test_results(results)
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 