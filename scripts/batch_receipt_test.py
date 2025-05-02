#!/usr/bin/env python
"""
Batch Receipt Test Script

This script tests the receipt OCR system on a batch of receipts and logs the results.
It identifies successes and failures based on store detection and total amount extraction.
"""

import os
import sys
import argparse
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import traceback

# Add the parent directory to sys.path to allow imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'batch_ocr_test.log'))
    ]
)
logger = logging.getLogger('batch_receipt_test')

# ANSI colors for terminal output
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

# Import UnifiedReceiptAnalyzer
try:
    from services.receipt_analyzer import UnifiedReceiptAnalyzer, ParsedReceipt
except ImportError as e:
    logger.error(f"Failed to import UnifiedReceiptAnalyzer: {e}")
    sys.exit(1)

def test_single_receipt(
    analyzer: UnifiedReceiptAnalyzer, 
    image_path: str, 
    options: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], bool]:
    """
    Test a single receipt and return results.
    
    Args:
        analyzer: Receipt analyzer instance
        image_path: Path to receipt image
        options: Processing options
        
    Returns:
        Tuple of (results_dict, success_boolean)
    """
    logger.info(f"Testing receipt: {image_path}")
    options = options or {}
    receipt_id = os.path.basename(image_path)
    
    try:
        # Analyze the receipt
        parsed_receipt, success = analyzer.analyze(image_path, options)
        
        # Determine success based on our criteria
        # Success = either store OR total amount is detected
        has_store = parsed_receipt.store_name is not None and parsed_receipt.store_name != ""
        has_total = parsed_receipt.total_amount is not None
        
        # Override the success flag based on our criteria
        success = has_store or has_total
        
        # Create result dictionary
        result = {
            "receipt_id": receipt_id,
            "image_path": image_path,
            "timestamp": datetime.now().isoformat(),
            "store": parsed_receipt.store_name,
            "total": parsed_receipt.total_amount,
            "tax": parsed_receipt.tax_amount,
            "confidence": parsed_receipt.confidence_score,
            "confidence_scores": parsed_receipt.confidence_scores,
            "store_detected": has_store,
            "total_detected": has_total,
            "items_count": len(parsed_receipt.items) if parsed_receipt.items else 0,
            "success": success,
            "processing_status": parsed_receipt.processing_status,
            "error": parsed_receipt.processing_error,
            "store_hint_used": options.get("store_type_hint") is not None and options.get("store_type_hint") == parsed_receipt.store_name
        }
        
        # Log the result
        if success:
            success_type = "full" if has_store and has_total else "partial"
            logger.info(f"✅ {success_type.upper()} SUCCESS on {receipt_id} - Store: {parsed_receipt.store_name}, Total: {parsed_receipt.total_amount}, Confidence: {parsed_receipt.confidence_score:.4f}")
        else:
            logger.error(f"❌ FAILED on {receipt_id} - Store: {parsed_receipt.store_name}, Total: {parsed_receipt.total_amount}, Confidence: {parsed_receipt.confidence_score:.4f}")
        
        return result, success
        
    except Exception as e:
        error_msg = f"Error testing receipt {image_path}: {str(e)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        
        result = {
            "receipt_id": receipt_id,
            "image_path": image_path,
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "exception_type": type(e).__name__,
            "success": False,
            "processing_status": "exception"
        }
        return result, False

def find_receipt_images(directory: str) -> List[str]:
    """Find all receipt images in the given directory."""
    image_paths = []
    # Support common image formats
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.tif', '*.tiff']:
        image_paths.extend([str(p) for p in Path(directory).glob(ext)])
        image_paths.extend([str(p) for p in Path(directory).glob(ext.upper())])
    return sorted(image_paths)

def copy_failed_receipt(image_path: str, failures_dir: str) -> str:
    """Copy a failed receipt to the failures directory."""
    os.makedirs(failures_dir, exist_ok=True)
    filename = os.path.basename(image_path)
    destination = os.path.join(failures_dir, filename)
    
    # If it's a symlink, resolve it and copy the actual file
    if os.path.islink(image_path):
        real_path = os.path.realpath(image_path)
        shutil.copy2(real_path, destination)
    else:
        shutil.copy2(image_path, destination)
        
    logger.info(f"Copied failed receipt to {destination}")
    return destination

def reprocess_failed_receipt(
    analyzer: UnifiedReceiptAnalyzer, 
    image_path: str,
    original_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Reprocess a failed receipt with alternate configurations.
    
    Args:
        analyzer: Receipt analyzer instance
        image_path: Path to receipt image
        original_result: Original processing result
        
    Returns:
        Dictionary with reprocessing results
    """
    logger.info(f"🔄 Reprocessing failed receipt: {image_path}")
    
    alt_configs = [
        {"name": "no_sharpening", "options": {"disable_sharpening": True}},
        {"name": "alt_threshold", "options": {"threshold_method": "adaptive"}},
        {"name": "no_crop", "options": {"skip_cropping": True}},
        {"name": "high_contrast", "options": {"enhance_contrast": True}},
    ]
    
    best_result = original_result
    best_success = original_result.get("success", False)
    best_confidence = original_result.get("confidence", 0.0)
    best_config = "original"
    
    # Try each alternative configuration
    for config in alt_configs:
        logger.info(f"Trying alternative config: {config['name']}")
        try:
            result, success = test_single_receipt(analyzer, image_path, config["options"])
            
            # Check if this result is better
            if success and not best_success:
                best_result = result
                best_success = success
                best_config = config["name"]
                logger.info(f"✅ Config {config['name']} fixed the receipt!")
            elif success and result["confidence"] > best_confidence:
                best_result = result
                best_confidence = result["confidence"]
                best_config = config["name"]
                logger.info(f"✅ Config {config['name']} improved confidence to {result['confidence']:.4f}")
                
        except Exception as e:
            logger.error(f"Error with config {config['name']}: {str(e)}")
    
    if best_config != "original":
        best_result["recovery_method"] = best_config
        best_result["improved"] = True
        best_result["original_confidence"] = original_result.get("confidence", 0.0)
        best_result["confidence_improvement"] = best_confidence - original_result.get("confidence", 0.0)
    else:
        best_result["recovery_method"] = None
        best_result["improved"] = False
    
    return best_result

def batch_test_receipts(directory: str, output_file: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Test all receipts in a directory and log the results.
    
    Args:
        directory: Directory containing receipt images
        output_file: File to save test results
        options: Processing options
        
    Returns:
        Dictionary with test results summary
    """
    logger.info(f"Starting batch receipt test on directory: {directory}")
    options = options or {}
    
    # Find all receipt images
    image_paths = find_receipt_images(directory)
    if not image_paths:
        logger.error(f"No receipt images found in {directory}")
        return {"error": "No receipt images found", "success": False}
    
    logger.info(f"Found {len(image_paths)} receipt images")
    
    # Initialize test results
    test_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "test_run_id": test_run_id,
        "timestamp": datetime.now().isoformat(),
        "total_receipts": len(image_paths),
        "success_count": 0,
        "failure_count": 0,
        "average_confidence": 0.0,
        "results": []
    }
    
    # Initialize analyzer
    analyzer = UnifiedReceiptAnalyzer(debug_mode=options.get("debug", False))
    
    # Lists to track successes and failures
    successes = []
    failures = []
    recovered = []
    
    # Process each receipt
    for image_path in image_paths:
        # Test the receipt
        result, success = test_single_receipt(analyzer, image_path, options)
        
        # Add the result to the appropriate list
        if success:
            successes.append(result)
        else:
            failures.append(result)
            
            # Copy failed receipt to failures directory
            failure_dir = os.path.join(directory, "failures")
            copy_failed_receipt(image_path, failure_dir)
            
            # Try to recover the failed receipt with different processing options
            if options.get("try_recovery", True):
                recovered_result = reprocess_failed_receipt(analyzer, image_path, result)
                if recovered_result.get("improved", False):
                    recovered.append(recovered_result)
                    # Replace the original result with the improved one
                    result = recovered_result
        
        # Save individual result to receipts directory
        receipt_id = result["receipt_id"]
        receipt_result_file = os.path.join("logs", "receipts", f"{receipt_id}_{test_run_id}.json")
        os.makedirs(os.path.dirname(receipt_result_file), exist_ok=True)
        with open(receipt_result_file, "w") as f:
            json.dump(result, f, indent=2)
        
        # Add the result to the overall results
        results["results"].append(result)
    
    # Update summary statistics
    results["success_count"] = len(successes)
    results["failure_count"] = len(failures)
    results["recovered_count"] = len(recovered)
    results["success_rate"] = len(successes) / len(image_paths) if image_paths else 0
    
    # Calculate average confidence for successful receipts
    confidence_scores = [r.get("confidence", 0) for r in successes]
    results["average_confidence"] = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
    
    # Store results by category
    results["successes"] = successes
    results["failures"] = failures
    results["recovered"] = recovered
    
    # Save results to file
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Test results saved to {output_file}")
    
    # Save failures to a separate file
    if failures:
        failures_file = os.path.join("logs", "failures.json")
        with open(failures_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_failures": len(failures),
                "failures": failures
            }, f, indent=2)
        logger.info(f"Failure details saved to {failures_file}")
    
    # Save recovery information
    if recovered:
        recovery_file = os.path.join("logs", f"self_tuning_diff_{test_run_id}.json")
        with open(recovery_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_recovered": len(recovered),
                "recovered": recovered
            }, f, indent=2)
        logger.info(f"Recovery details saved to {recovery_file}")
    
    # Print summary
    print_summary(results)
    
    return results

def print_summary(results: Dict[str, Any]) -> None:
    """Print a summary of the test results."""
    print(f"\n{Colors.BOLD}===== BATCH RECEIPT TEST SUMMARY ====={Colors.RESET}")
    
    total = results["total_receipts"]
    success_count = results["success_count"]
    failure_count = results["failure_count"]
    recovered_count = results.get("recovered_count", 0)
    success_rate = results["success_rate"]
    avg_confidence = results["average_confidence"]
    
    # Determine colors
    success_color = Colors.GREEN if success_rate >= 0.7 else (Colors.YELLOW if success_rate >= 0.5 else Colors.RED)
    conf_color = Colors.GREEN if avg_confidence >= 0.7 else (Colors.YELLOW if avg_confidence >= 0.5 else Colors.RED)
    
    print(f"Test Run ID: {results['test_run_id']}")
    print(f"Timestamp: {results['timestamp']}")
    print(f"Total Receipts: {total}")
    print(f"Success Rate: {success_color}{success_rate:.2%}{Colors.RESET} ({success_count}/{total})")
    print(f"Average Confidence: {conf_color}{avg_confidence:.4f}{Colors.RESET}")
    
    if recovered_count > 0:
        print(f"Recovered Receipts: {Colors.BLUE}{recovered_count}{Colors.RESET}")
    
    # Print failure summary if any
    if failure_count > 0:
        print(f"\n{Colors.RED}Failed Receipts ({failure_count}):{Colors.RESET}")
        for failure in results["failures"]:
            print(f"  - {failure['receipt_id']}: {failure.get('error', 'No error details')}")
    
    # Print recovery summary if any
    if recovered_count > 0:
        print(f"\n{Colors.BLUE}Recovered Receipts ({recovered_count}):{Colors.RESET}")
        for recovered in results["recovered"]:
            print(f"  - {recovered['receipt_id']}: Improved by {recovered.get('recovery_method')} " + 
                  f"(+{recovered.get('confidence_improvement', 0):.4f} confidence)")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Batch test receipt OCR system")
    
    parser.add_argument("--directory", "-d", default="test_receipts",
                       help="Directory containing receipt images (default: test_receipts)")
    parser.add_argument("--output", "-o", 
                       default=f"logs/ocr_test_{datetime.now().strftime('%Y%m%d')}.json",
                       help="Output file to save test results (default: logs/ocr_test_YYYYMMDD.json)")
    parser.add_argument("--debug", action="store_true", 
                       help="Enable debug output")
    parser.add_argument("--no-color", action="store_true", 
                       help="Disable colored output")
    parser.add_argument("--store", "-s", 
                       help="Store name hint to use for all receipts")
    parser.add_argument("--no-recovery", action="store_true",
                       help="Disable automatic recovery attempts for failed receipts")
    parser.add_argument("--single",
                       help="Test only a single receipt image file")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Disable colors if requested
    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, "")
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Build options
    options = {
        "debug": args.debug,
        "try_recovery": not args.no_recovery
    }
    if args.store:
        options["store_type_hint"] = args.store
    
    # Run single test if specified
    if args.single:
        if not os.path.exists(args.single):
            logger.error(f"File not found: {args.single}")
            sys.exit(1)
            
        logger.info(f"Testing single receipt: {args.single}")
        
        # Initialize analyzer
        analyzer = UnifiedReceiptAnalyzer(debug_mode=args.debug)
        
        # Test the receipt
        result, success = test_single_receipt(analyzer, args.single, options)
        
        # Print result
        print(f"\n{Colors.BOLD}===== SINGLE RECEIPT TEST RESULT ====={Colors.RESET}")
        print(f"Image: {result['receipt_id']}")
        print(f"Store: {result['store']}")
        print(f"Total: {result['total']}")
        print(f"Tax: {result['tax']}")
        print(f"Confidence: {result['confidence']:.4f}")
        print(f"Success: {'Yes' if success else 'No'}")
        
        # Save result to file
        receipt_id = result["receipt_id"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join("logs", "receipts", f"{receipt_id}_{timestamp}.json")
        os.makedirs(os.path.dirname(result_file), exist_ok=True)
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)
        logger.info(f"Result saved to {result_file}")
        
        # Exit with success/failure code
        sys.exit(0 if success else 1)
    
    # Run batch test
    try:
        batch_test_receipts(args.directory, args.output, options)
    except Exception as e:
        logger.error(f"Error running batch test: {str(e)}")
        logger.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 