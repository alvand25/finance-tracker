#!/usr/bin/env python3
"""
Receipt Testing CLI

Command-line tool for testing receipt processing with detailed debug output.

Features:
- Test receipts by vendor type
- Generate/compare against expected results
- Save debug information to log files
- Batch process multiple receipts
- Output detailed test statistics

Usage:
  python test_receipts_cli.py --vendor=<vendor_name> [options]
  python test_receipts_cli.py --all [options]
  python test_receipts_cli.py --image=<image_path> [options]

Options:
  --vendor=<name>          Process receipts for specific vendor (costco, trader_joes, hmart, key_food)
  --all                    Process all receipts in samples directory
  --image=<path>           Process a specific receipt image file
  --dev                    Enable developer mode with detailed debug output
  --generate-expected      Generate expected output files from results
  --validate               Validate results against expected outputs
  --verbose                Show detailed processing information
  --help                   Show this help message
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import traceback

# Set up logging
LOG_FILE = f"receipt_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import project modules
from utils.receipt_analyzer import ReceiptAnalyzer
from utils.receipt_validator import ReceiptValidator, save_validation_report
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService

# Constants
SAMPLES_DIR = "samples"
IMAGES_DIR = os.path.join(SAMPLES_DIR, "images")
OCR_DIR = os.path.join(SAMPLES_DIR, "ocr")
VENDOR_DIRS = {
    "costco": os.path.join(SAMPLES_DIR, "costco"),
    "trader_joes": os.path.join(SAMPLES_DIR, "trader_joes"),
    "hmart": os.path.join(SAMPLES_DIR, "hmart"),
    "key_food": os.path.join(SAMPLES_DIR, "key_food")
}
EXPECTED_DIR = os.path.join(SAMPLES_DIR, "expected")
DEBUG_DIR = os.path.join("debug")

def ensure_dirs():
    """Ensure all required directories exist."""
    for dir_path in [SAMPLES_DIR, IMAGES_DIR, OCR_DIR, EXPECTED_DIR, DEBUG_DIR] + list(VENDOR_DIRS.values()):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logger.info(f"Created directory: {dir_path}")


def process_receipt(image_path: str, dev_mode: bool = False) -> Dict[str, Any]:
    """
    Process a receipt image and return the results.
    
    Args:
        image_path: Path to the receipt image file
        dev_mode: Whether to enable developer mode with debug output
        
    Returns:
        Dictionary with processing results
    """
    logger.info(f"Processing receipt: {image_path}")
    
    # Initialize analyzer and service
    analyzer = ReceiptAnalyzer()
    analyzer.DEBUG_MODE = dev_mode
    
    storage = JSONStorage(data_dir="data")
    service = ReceiptService(storage, upload_dir="uploads/receipts")
    
    try:
        # Read the image file
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # Extract OCR text
        receipt_text = analyzer.extract_text(image_path)
        
        # Save OCR text to file if in dev mode
        if dev_mode:
            base_name = os.path.basename(image_path).split('.')[0]
            ocr_path = os.path.join(OCR_DIR, f"{base_name}.txt")
            with open(ocr_path, "w") as f:
                f.write(receipt_text)
            logger.info(f"Saved OCR text to: {ocr_path}")
        
        # Extract store name
        store_name = analyzer._extract_store_name(receipt_text.split('\n'))
        logger.info(f"Detected store name: {store_name}")
        
        # Initialize results dictionary
        results = {
            "image_path": image_path,
            "store_name": store_name,
            "items": [],
            "processing_status": "pending"
        }
        
        # Process by vendor-specific handler based on detected store
        store_name_lower = store_name.lower() if store_name else ""
        
        if "costco" in store_name_lower:
            logger.info("Using Costco-specific handler")
            costco_data = analyzer.handle_costco_receipt(receipt_text, image_path)
            if costco_data and costco_data.get('items'):
                results = {**results, **costco_data}
                results["handler"] = "costco"
                results["processing_status"] = "processed"
        
        elif ("trader" in store_name_lower and "joe" in store_name_lower):
            logger.info("Using Trader Joe's-specific handler")
            tj_data = analyzer.handle_trader_joes_receipt(receipt_text, image_path)
            if tj_data and tj_data.get('items'):
                results = {**results, **tj_data}
                results["handler"] = "trader_joes"
                results["processing_status"] = "processed"
        
        elif ("h mart" in store_name_lower or "hmart" in store_name_lower):
            logger.info("Using H Mart-specific handler")
            hmart_data = analyzer.handle_hmart_receipt(receipt_text, image_path)
            if hmart_data and hmart_data.get('items'):
                results = {**results, **hmart_data}
                results["handler"] = "hmart"
                results["processing_status"] = "processed"
        
        elif "key food" in store_name_lower:
            logger.info("Using Key Food-specific handler")
            key_food_data = analyzer.handle_key_food_receipt(receipt_text, image_path)
            if key_food_data and key_food_data.get('items'):
                results = {**results, **key_food_data}
                results["handler"] = "key_food"
                results["processing_status"] = "processed"
        
        # If no specialized handler matched or they failed, try generic analysis
        if results["processing_status"] == "pending":
            logger.info("Using generic receipt analysis")
            generic_data = analyzer.analyze_receipt(receipt_text, image_path)
            if generic_data:
                results = {**results, **generic_data}
                results["handler"] = "generic"
                results["processing_status"] = "processed"
            else:
                results["processing_status"] = "failed"
                results["error"] = "Failed to extract receipt data with any handler"
        
        # Log the results
        item_count = len(results.get("items", []))
        logger.info(f"Handler: {results.get('handler')}, Items: {item_count}, Total: {results.get('total')}")
        
        # Save debug information if in dev mode
        if dev_mode:
            base_name = os.path.basename(image_path).split('.')[0]
            debug_path = os.path.join(DEBUG_DIR, f"{base_name}_results.json")
            with open(debug_path, "w") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Saved debug results to: {debug_path}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error processing receipt: {str(e)}")
        traceback.print_exc()
        
        return {
            "image_path": image_path,
            "processing_status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def process_vendor_receipts(vendor: str, dev_mode: bool = False, 
                           validate: bool = False, generate_expected: bool = False) -> List[Dict[str, Any]]:
    """
    Process all receipts for a specific vendor.
    
    Args:
        vendor: Vendor name (costco, trader_joes, hmart, key_food)
        dev_mode: Whether to enable developer mode with debug output
        validate: Whether to validate results against expected outputs
        generate_expected: Whether to generate expected output files
        
    Returns:
        List of processing result dictionaries
    """
    logger.info(f"Processing receipts for vendor: {vendor}")
    
    # Normalize vendor name for directory lookup
    vendor_norm = vendor.lower().replace(" ", "_").replace("'", "")
    
    # Get vendor-specific directory
    vendor_dir = VENDOR_DIRS.get(vendor_norm)
    
    if not vendor_dir or not os.path.exists(vendor_dir):
        logger.warning(f"No vendor directory found for {vendor}")
        # Look in general images directory
        vendor_dir = IMAGES_DIR
    
    # Find matching receipt images
    receipts = []
    for filename in os.listdir(vendor_dir):
        if filename.endswith(('.jpg', '.jpeg', '.png')):
            receipts.append(os.path.join(vendor_dir, filename))
    
    # If no receipts found in vendor directory, check general images directory
    if not receipts and vendor_dir != IMAGES_DIR:
        logger.info(f"No receipts found in {vendor_dir}, checking general images directory")
        for filename in os.listdir(IMAGES_DIR):
            # Try to match vendor name in filename
            if vendor_norm in filename.lower() and filename.endswith(('.jpg', '.jpeg', '.png')):
                receipts.append(os.path.join(IMAGES_DIR, filename))
    
    if not receipts:
        logger.warning(f"No receipts found for vendor: {vendor}")
        return []
    
    logger.info(f"Found {len(receipts)} receipts for vendor: {vendor}")
    
    # Process each receipt
    results = []
    validator = ReceiptValidator(expected_dir=EXPECTED_DIR) if validate or generate_expected else None
    
    for image_path in receipts:
        result = process_receipt(image_path, dev_mode)
        
        # Validate against expected results
        if validator and validate:
            receipt_id = os.path.basename(image_path).split('.')[0]
            validation = validator.validate(receipt_id, result)
            result["validation"] = validation
        
        # Generate expected output
        if validator and generate_expected:
            receipt_id = os.path.basename(image_path).split('.')[0]
            expected_path = validator.save_expected(receipt_id, result)
            logger.info(f"Generated expected output: {expected_path}")
        
        results.append(result)
    
    return results


def process_all_receipts(dev_mode: bool = False, validate: bool = False, 
                        generate_expected: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """
    Process all receipts organized by vendor.
    
    Args:
        dev_mode: Whether to enable developer mode with debug output
        validate: Whether to validate results against expected outputs
        generate_expected: Whether to generate expected output files
        
    Returns:
        Dictionary mapping vendor names to lists of processing results
    """
    logger.info("Processing all receipts")
    
    results = {}
    
    for vendor in VENDOR_DIRS.keys():
        vendor_results = process_vendor_receipts(
            vendor, 
            dev_mode=dev_mode, 
            validate=validate, 
            generate_expected=generate_expected
        )
        
        if vendor_results:
            results[vendor] = vendor_results
    
    # Also process general images directory for unorganized receipts
    general_results = []
    
    for filename in os.listdir(IMAGES_DIR):
        if filename.endswith(('.jpg', '.jpeg', '.png')):
            # Skip if already processed in a vendor-specific folder
            image_path = os.path.join(IMAGES_DIR, filename)
            already_processed = any(
                any(r.get("image_path") == image_path for r in vendor_results)
                for vendor_results in results.values()
            )
            
            if not already_processed:
                result = process_receipt(image_path, dev_mode)
                
                # Validate against expected results
                if validate:
                    validator = ReceiptValidator(expected_dir=EXPECTED_DIR)
                    receipt_id = os.path.basename(image_path).split('.')[0]
                    validation = validator.validate(receipt_id, result)
                    result["validation"] = validation
                
                # Generate expected output
                if generate_expected:
                    validator = ReceiptValidator(expected_dir=EXPECTED_DIR)
                    receipt_id = os.path.basename(image_path).split('.')[0]
                    expected_path = validator.save_expected(receipt_id, result)
                    logger.info(f"Generated expected output: {expected_path}")
                
                general_results.append(result)
    
    if general_results:
        results["unclassified"] = general_results
    
    return results


def generate_report(results):
    """Generate a summary report of the test results."""
    if isinstance(results, list):
        # Single vendor results
        total = len(results)
        successful = sum(1 for r in results if r.get("processing_status") == "processed")
        failed = sum(1 for r in results if r.get("processing_status") in ["failed", "error"])
        
        # Calculate averages
        avg_items = sum(len(r.get("items", [])) for r in results) / max(total, 1)
        
        validation_stats = None
        if any("validation" in r for r in results):
            validations = [r["validation"] for r in results if "validation" in r]
            validation_stats = {
                "total": len(validations),
                "success": sum(1 for v in validations if v.get("status") == "success"),
                "partial": sum(1 for v in validations if v.get("status") == "partial"),
                "failed": sum(1 for v in validations if v.get("status") == "failed")
            }
            if validation_stats["total"] > 0:
                validation_stats["success_rate"] = (
                    f"{(validation_stats['success'] / validation_stats['total']) * 100:.1f}%"
                )
        
        report = {
            "total_receipts": total,
            "successful": successful,
            "failed": failed,
            "success_rate": f"{(successful / total) * 100:.1f}%" if total > 0 else "0.0%",
            "avg_items_per_receipt": round(avg_items, 1),
            "validation": validation_stats
        }
        
        return report
    
    elif isinstance(results, dict):
        # All vendors results
        report = {"vendors": {}}
        
        for vendor, vendor_results in results.items():
            report["vendors"][vendor] = generate_report(vendor_results)
        
        # Overall statistics
        total_all = sum(stats["total_receipts"] for stats in report["vendors"].values())
        successful_all = sum(stats["successful"] for stats in report["vendors"].values())
        
        report["overall"] = {
            "total_receipts": total_all,
            "successful": successful_all,
            "success_rate": f"{(successful_all / total_all) * 100:.1f}%" if total_all > 0 else "0.0%"
        }
        
        return report


def print_report(report):
    """Print a formatted report to the console."""
    if "vendors" in report:
        # All vendors report
        print("\n===== RECEIPT TESTING SUMMARY =====")
        print(f"Total Receipts: {report['overall']['total_receipts']}")
        print(f"Successfully Processed: {report['overall']['successful']}")
        print(f"Success Rate: {report['overall']['success_rate']}")
        
        print("\n----- RESULTS BY VENDOR -----")
        for vendor, stats in report["vendors"].items():
            print(f"\n{vendor.upper()}:")
            print(f"  Receipts: {stats['total_receipts']}")
            print(f"  Success Rate: {stats['success_rate']}")
            print(f"  Avg Items: {stats['avg_items_per_receipt']}")
            
            if stats.get("validation"):
                v_stats = stats["validation"]
                print(f"  Validation Success: {v_stats.get('success_rate', 'N/A')}")
    else:
        # Single vendor report
        print("\n===== RECEIPT TESTING SUMMARY =====")
        print(f"Total Receipts: {report['total_receipts']}")
        print(f"Successfully Processed: {report['successful']}")
        print(f"Failed: {report['failed']}")
        print(f"Success Rate: {report['success_rate']}")
        print(f"Average Items Per Receipt: {report['avg_items_per_receipt']}")
        
        if report.get("validation"):
            v_stats = report["validation"]
            print("\n----- VALIDATION RESULTS -----")
            print(f"Total Validations: {v_stats['total']}")
            print(f"Success: {v_stats['success']}")
            print(f"Partial: {v_stats['partial']}")
            print(f"Failed: {v_stats['failed']}")
            print(f"Success Rate: {v_stats.get('success_rate', 'N/A')}")


def main():
    """Main entry point for the receipt testing CLI."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Receipt Testing CLI")
    parser.add_argument("--vendor", help="Process receipts for specific vendor")
    parser.add_argument("--all", action="store_true", help="Process all receipts")
    parser.add_argument("--image", help="Process a specific receipt image")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode with detailed debug output")
    parser.add_argument("--generate-expected", action="store_true", help="Generate expected output files")
    parser.add_argument("--validate", action="store_true", help="Validate results against expected outputs")
    parser.add_argument("--verbose", action="store_true", help="Show detailed processing information")
    
    args = parser.parse_args()
    
    # Configure logging based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Ensure directories exist
    ensure_dirs()
    
    # Process based on arguments
    if args.image:
        # Process a single image
        if not os.path.exists(args.image):
            logger.error(f"Image file not found: {args.image}")
            return 1
        
        result = process_receipt(args.image, dev_mode=args.dev)
        
        # Validate against expected results
        if args.validate:
            validator = ReceiptValidator(expected_dir=EXPECTED_DIR)
            receipt_id = os.path.basename(args.image).split('.')[0]
            validation = validator.validate(receipt_id, result)
            result["validation"] = validation
        
        # Generate expected output
        if args.generate_expected:
            validator = ReceiptValidator(expected_dir=EXPECTED_DIR)
            receipt_id = os.path.basename(args.image).split('.')[0]
            expected_path = validator.save_expected(receipt_id, result)
            logger.info(f"Generated expected output: {expected_path}")
        
        # Generate and print report
        report = generate_report([result])
        print_report(report)
        
        # Save result to file
        output_file = f"receipt_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Saved result to: {output_file}")
    
    elif args.vendor:
        # Process all receipts for a specific vendor
        results = process_vendor_receipts(
            args.vendor,
            dev_mode=args.dev,
            validate=args.validate,
            generate_expected=args.generate_expected
        )
        
        if not results:
            logger.error(f"No receipts processed for vendor: {args.vendor}")
            return 1
        
        # Generate and print report
        report = generate_report(results)
        print_report(report)
        
        # Save results to file
        output_file = f"{args.vendor}_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Saved results to: {output_file}")
        
        # Save validation report if validation was performed
        if args.validate:
            validation_results = [r["validation"] for r in results if "validation" in r]
            if validation_results:
                save_validation_report(validation_results)
    
    elif args.all:
        # Process all receipts
        results = process_all_receipts(
            dev_mode=args.dev,
            validate=args.validate,
            generate_expected=args.generate_expected
        )
        
        if not results:
            logger.error("No receipts processed")
            return 1
        
        # Generate and print report
        report = generate_report(results)
        print_report(report)
        
        # Save results to file
        output_file = f"all_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Saved results to: {output_file}")
        
        # Save validation report if validation was performed
        if args.validate:
            all_validations = []
            for vendor_results in results.values():
                all_validations.extend(
                    r["validation"] for r in vendor_results if "validation" in r
                )
            
            if all_validations:
                save_validation_report(all_validations)
    
    else:
        # No mode specified, show help
        parser.print_help()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 