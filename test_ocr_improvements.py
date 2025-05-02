#!/usr/bin/env python
"""
OCR Confidence Testing Script

This script tests OCR confidence scores on sample receipts to track improvements.
"""

import os
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ANSI colors for terminal output
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

# Import receipt analyzer
try:
    from services.receipt_analyzer import UnifiedReceiptAnalyzer
except ImportError:
    logger.error("UnifiedReceiptAnalyzer not found, falling back to old method")
    from utils.receipt_analyzer import ReceiptAnalyzer
    from services.receipt_service import ReceiptService
    from storage.json_storage import JSONStorage


def test_receipt_confidence(image_path: str, options: Optional[Dict] = None) -> Dict:
    """
    Test OCR confidence on a receipt image.
    
    Args:
        image_path: Path to receipt image
        options: Processing options
        
    Returns:
        Dictionary with confidence scores and processing results
    """
    logger.info(f"Testing receipt confidence for {image_path}")
    
    options = options or {}
    results = {}
    
    try:
        # Use new unified analyzer if available
        try:
            analyzer = UnifiedReceiptAnalyzer(debug_mode=True)
            receipt, success = analyzer.analyze(image_path, options)
            
            results = {
                'image_path': image_path,
                'confidence': receipt.confidence_score,
                'confidence_scores': receipt.confidence_scores,
                'success': success,
                'store': receipt.store_name,
                'total': receipt.total_amount,
                'subtotal': receipt.subtotal_amount,
                'tax': receipt.tax_amount,
                'items_count': len(receipt.items) if receipt.items else 0,
                'processing_status': receipt.processing_status,
                'error': receipt.processing_error
            }
        except NameError:
            # Fall back to old method if unified analyzer not available
            logger.info("Using legacy analyzer")
            analyzer = ReceiptAnalyzer(debug_mode=True)
            storage = JSONStorage()
            service = ReceiptService(storage, debug_mode=True)
            
            # Process the receipt
            ocr_result = analyzer.extract_text(image_path, use_google_ocr=True)
            receipt_data = analyzer.analyze_receipt(ocr_result['text'], image_path)
            
            results = {
                'image_path': image_path,
                'confidence': ocr_result.get('confidence', 0.0),
                'success': 'error' not in receipt_data,
                'store': receipt_data.get('store'),
                'total': receipt_data.get('total'),
                'items_count': len(receipt_data.get('items', [])),
                'processing_status': 'failed' if 'error' in receipt_data else 'completed',
                'error': receipt_data.get('error')
            }
            
    except Exception as e:
        logger.error(f"Error testing receipt: {str(e)}")
        results = {
            'image_path': image_path,
            'confidence': 0.0,
            'success': False,
            'error': str(e),
            'processing_status': 'failed'
        }
    
    return results


def get_confidence_color(confidence: float) -> str:
    """Return appropriate ANSI color code based on confidence score."""
    if confidence >= 0.7:
        return Colors.GREEN
    elif confidence >= 0.5:
        return Colors.YELLOW
    else:
        return Colors.RED


def print_colored_result(result: Dict) -> None:
    """Print a receipt result with color-coded confidence levels."""
    filename = os.path.basename(result['image_path'])
    confidence = result['confidence']
    color = get_confidence_color(confidence)
    
    # Determine emoji based on what was extracted
    if result['store'] and result['total']:
        status_emoji = "✅"
    elif result['store'] or result['total']:
        status_emoji = "⚠️"
    else:
        status_emoji = "❌"
    
    print(f"{status_emoji} {filename}: {color}{confidence:.4f}{Colors.RESET} | ", end="")
    
    # Print key details
    if result['store']:
        print(f"Store: {Colors.GREEN}{result['store']}{Colors.RESET}", end=" | ")
    else:
        print(f"Store: {Colors.RED}Missing{Colors.RESET}", end=" | ")
        
    if result['total']:
        print(f"Total: {Colors.GREEN}${result['total']}{Colors.RESET}", end=" | ")
    else:
        print(f"Total: {Colors.RED}Missing{Colors.RESET}", end=" | ")
        
    print(f"Items: {len(result['items']) if result.get('items') else 0}")


def run_confidence_tests(directory: str, output_file: str, options: Optional[Dict] = None) -> None:
    """
    Run OCR confidence tests on all images in a directory.
    
    Args:
        directory: Directory containing receipt images
        output_file: File to save test results
        options: Processing options to apply to all receipts
    """
    logger.info(f"Running confidence tests on {directory}")
    
    # Find all image files
    image_paths = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_paths.extend(list(Path(directory).glob(ext)))
        image_paths.extend(list(Path(directory).glob(ext.upper())))
    
    # Sort by name
    image_paths.sort()
    
    # Load previous results if available
    previous_results = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                previous_results = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load previous results: {str(e)}")
    
    # Initialize results
    results = {
        'timestamp': datetime.now().isoformat(),
        'test_count': len(image_paths),
        'receipts': []
    }
    
    # Test each image
    success_count = 0
    total_confidence = 0.0
    error_paths = []
    
    print(f"\n{Colors.BOLD}===== OCR CONFIDENCE TEST RESULTS ====={Colors.RESET}\n")
    
    for image_path in image_paths:
        path_str = str(image_path)
        logger.info(f"Testing {path_str}")
        
        receipt_result = test_receipt_confidence(path_str, options)
        
        # Add to results
        results['receipts'].append(receipt_result)
        
        # Update statistics
        if receipt_result['success']:
            success_count += 1
            total_confidence += receipt_result['confidence']
        else:
            error_paths.append(path_str)
            
        # Print results
        print_colored_result(receipt_result)
    
    # Calculate overall statistics
    avg_confidence = total_confidence / success_count if success_count > 0 else 0.0
    success_rate = success_count / len(image_paths) if image_paths else 0.0
    
    results['success_count'] = success_count
    results['success_rate'] = success_rate
    results['average_confidence'] = avg_confidence
    
    # Compare with previous results
    if previous_results:
        prev_avg = previous_results.get('average_confidence', 0.0)
        prev_rate = previous_results.get('success_rate', 0.0)
        
        results['confidence_delta'] = avg_confidence - prev_avg
        results['success_rate_delta'] = success_rate - prev_rate
        
        conf_delta = avg_confidence - prev_avg
        rate_delta = success_rate - prev_rate
        
        conf_delta_color = Colors.GREEN if conf_delta >= 0 else Colors.RED
        rate_delta_color = Colors.GREEN if rate_delta >= 0 else Colors.RED
        
        logger.info(f"Previous avg confidence: {prev_avg:.4f}, new: {avg_confidence:.4f}, delta: {conf_delta_color}{conf_delta:+.4f}{Colors.RESET}")
        logger.info(f"Previous success rate: {prev_rate:.2%}, new: {success_rate:.2%}, delta: {rate_delta_color}{rate_delta:+.2%}{Colors.RESET}")
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print(f"\n{Colors.BOLD}===== SUMMARY ====={Colors.RESET}")
    print(f"Completed testing {len(image_paths)} receipts")
    
    success_color = Colors.GREEN if success_rate > 0.7 else (Colors.YELLOW if success_rate > 0.5 else Colors.RED)
    conf_color = get_confidence_color(avg_confidence)
    
    print(f"Success rate: {success_color}{success_rate:.2%}{Colors.RESET} ({success_count}/{len(image_paths)})")
    print(f"Average confidence: {conf_color}{avg_confidence:.4f}{Colors.RESET}")
    
    if error_paths:
        print(f"\n{Colors.RED}Failed to process {len(error_paths)} receipts:{Colors.RESET}")
        for path in error_paths:
            print(f"  - {path}")
            
    # Check for receipts with 0 confidence
    zero_confidence = [r for r in results['receipts'] if r['success'] and r['confidence'] <= 0.0]
    if zero_confidence:
        print(f"\n{Colors.YELLOW}Found {len(zero_confidence)} receipts with 0 confidence:{Colors.RESET}")
        for receipt in zero_confidence:
            print(f"  - {receipt['image_path']}")
    
    # Check for receipts with very low confidence
    low_confidence = [r for r in results['receipts'] if r['success'] and 0.0 < r['confidence'] < 0.3]
    if low_confidence:
        print(f"\n{Colors.YELLOW}Found {len(low_confidence)} receipts with low confidence (<0.3):{Colors.RESET}")
        for receipt in low_confidence:
            print(f"  - {receipt['image_path']}: {receipt['confidence']:.4f}")
    
    # Error if no receipts were successful
    if success_count == 0:
        logger.error("No receipts were successfully processed!")
        raise RuntimeError("All receipt processing failed")
    
    # Error if the average confidence is too low
    min_confidence = options.get('min_confidence', 0.3) if options else 0.3
    if avg_confidence < min_confidence:
        logger.error(f"Average confidence too low: {avg_confidence:.4f}")
        raise RuntimeError(f"Average confidence score below threshold: {avg_confidence:.4f} < {min_confidence:.1f}")
    
    logger.info(f"Results saved to {output_file}")
    print(f"\nDetailed results saved to: {output_file}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Test OCR confidence on receipt images")
    parser.add_argument("--directory", "-d", default="samples/images",
                       help="Directory containing receipt images")
    parser.add_argument("--output", "-o", default="confidence_test_results.json",
                       help="Output file to save test results")
    parser.add_argument("--store", "-s", help="Store name hint to use")
    parser.add_argument("--currency", "-c", help="Currency to use")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--min-confidence", type=float, default=0.3,
                       help="Minimum acceptable average confidence (default: 0.3)")
    parser.add_argument("--single", help="Test only a single image file")
    
    args = parser.parse_args()
    
    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Disable colors if requested
    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, "")
    
    # Build options
    options = {}
    if args.store:
        options['store_type_hint'] = args.store
    if args.currency:
        options['force_currency'] = args.currency
    if args.min_confidence:
        options['min_confidence'] = args.min_confidence
    
    # Run single test if specified
    if args.single:
        if not os.path.exists(args.single):
            logger.error(f"File not found: {args.single}")
            return
        
        print(f"\n{Colors.BOLD}===== TESTING SINGLE RECEIPT ====={Colors.RESET}\n")
        result = test_receipt_confidence(args.single, options)
        print_colored_result(result)
        return
    
    # Run tests
    run_confidence_tests(args.directory, args.output, options)


if __name__ == "__main__":
    main() 