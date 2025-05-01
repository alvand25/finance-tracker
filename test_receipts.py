#!/usr/bin/env python3
"""
Test script to verify receipt parsing with different store handlers.
This script processes all receipts in the uploads directory and checks the results.
"""

import os
import sys
import argparse
import json
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path to allow importing from project modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.receipt_analyzer import ReceiptAnalyzer
from services.receipt_service import ReceiptService
from storage.json_storage import JSONStorage
from utils.receipt_test_runner import process_receipt_image, process_vendor_specifics

def test_receipt(image_path: str, analyzer: ReceiptAnalyzer, debug: bool = False) -> Dict[str, Any]:
    """
    Test receipt parsing with a specific image.
    
    Args:
        image_path: Path to the image file
        analyzer: ReceiptAnalyzer instance
        debug: Whether to enable debug mode
        
    Returns:
        Dict with test results
    """
    print(f"\n===== Testing receipt: {os.path.basename(image_path)} =====")
    
    # Extract text from the receipt
    ocr_text = analyzer.extract_text(image_path, debug=debug)
    print(f"Extracted {len(ocr_text)} characters of text")
    
    # Show a preview of the OCR text
    if ocr_text:
        preview_lines = ocr_text.split('\n')[:10]
        print("OCR Text Preview:")
        for line in preview_lines:
            print(f"  {line}")
        print("...")
    
    # Try to identify the store name
    store_name = analyzer._extract_store_name(ocr_text)
    print(f"Detected store: {store_name}")
    
    # Process the receipt with different handlers based on store name
    if store_name:
        store_name_lower = store_name.lower()
        
        # Test Costco handler
        if "costco" in store_name_lower:
            print("\nTesting Costco handler...")
            costco_result = analyzer.handle_costco_receipt(ocr_text, image_path)
            print(f"Items extracted: {len(costco_result.get('items', []))}")
            print(f"Subtotal: {costco_result.get('subtotal')}")
            print(f"Tax: {costco_result.get('tax')}")
            print(f"Total: {costco_result.get('total')}")
            print(f"Confidence: {costco_result.get('confidence', 0)}")
            
            # Show extracted items
            if costco_result.get('items'):
                print("\nExtracted items:")
                for i, item in enumerate(costco_result.get('items')[:5], 1):
                    print(f"  {i}. {item.get('description')} - ${item.get('price')}")
                if len(costco_result.get('items')) > 5:
                    print(f"  ... and {len(costco_result.get('items')) - 5} more items")
                    
            return {
                'image_path': image_path,
                'store_name': store_name,
                'handler': 'costco',
                'items_count': len(costco_result.get('items', [])),
                'subtotal': costco_result.get('subtotal'),
                'tax': costco_result.get('tax'),
                'total': costco_result.get('total'),
                'confidence': costco_result.get('confidence', 0),
                'success': costco_result.get('confidence', 0) > 0.6 and len(costco_result.get('items', [])) > 0
            }
            
        # Test H Mart handler
        elif "h mart" in store_name_lower or "hmart" in store_name_lower:
            print("\nTesting H Mart handler...")
            hmart_result = analyzer.handle_hmart_receipt(ocr_text, image_path)
            print(f"Items extracted: {len(hmart_result.get('items', []))}")
            print(f"Subtotal: {hmart_result.get('subtotal')}")
            print(f"Tax: {hmart_result.get('tax')}")
            print(f"Total: {hmart_result.get('total')}")
            print(f"Confidence: {hmart_result.get('confidence', 0)}")
            
            # Show extracted items
            if hmart_result.get('items'):
                print("\nExtracted items:")
                for i, item in enumerate(hmart_result.get('items')[:5], 1):
                    print(f"  {i}. {item.get('description')} - ${item.get('price')}")
                if len(hmart_result.get('items')) > 5:
                    print(f"  ... and {len(hmart_result.get('items')) - 5} more items")
                    
            return {
                'image_path': image_path,
                'store_name': store_name,
                'handler': 'hmart',
                'items_count': len(hmart_result.get('items', [])),
                'subtotal': hmart_result.get('subtotal'),
                'tax': hmart_result.get('tax'),
                'total': hmart_result.get('total'),
                'confidence': hmart_result.get('confidence', 0),
                'success': hmart_result.get('confidence', 0) > 0.6 and len(hmart_result.get('items', [])) > 0
            }
            
        # Test Trader Joe's handler
        elif "trader" in store_name_lower and ("joe" in store_name_lower or "joes" in store_name_lower):
            print("\nTesting Trader Joe's handler...")
            tj_result = analyzer.handle_trader_joes_receipt(ocr_text, image_path)
            print(f"Items extracted: {len(tj_result.get('items', []))}")
            print(f"Subtotal: {tj_result.get('subtotal')}")
            print(f"Tax: {tj_result.get('tax')}")
            print(f"Total: {tj_result.get('total')}")
            print(f"Confidence: {tj_result.get('confidence', 0)}")
            
            # Show extracted items
            if tj_result.get('items'):
                print("\nExtracted items:")
                for i, item in enumerate(tj_result.get('items')[:5], 1):
                    print(f"  {i}. {item.get('description')} - ${item.get('price')}")
                if len(tj_result.get('items')) > 5:
                    print(f"  ... and {len(tj_result.get('items')) - 5} more items")
                    
            return {
                'image_path': image_path,
                'store_name': store_name,
                'handler': 'trader_joes',
                'items_count': len(tj_result.get('items', [])),
                'subtotal': tj_result.get('subtotal'),
                'tax': tj_result.get('tax'),
                'total': tj_result.get('total'),
                'confidence': tj_result.get('confidence', 0),
                'success': tj_result.get('confidence', 0) > 0.6 and len(tj_result.get('items', [])) > 0
            }
            
        # Test Key Food handler with fallback parsing
        elif "key" in store_name_lower and "food" in store_name_lower:
            print("\nTesting Key Food handler with fallback parsing...")
            # Use fallback parsing for Key Food
            items = analyzer.parse_items_fallback(ocr_text, 'key_food')
            totals = analyzer.extract_totals_fallback(ocr_text, 'key_food')
            
            print(f"Items extracted: {len(items)}")
            print(f"Subtotal: {totals.get('subtotal')}")
            print(f"Tax: {totals.get('tax')}")
            print(f"Total: {totals.get('total')}")
            
            # Show extracted items
            if items:
                print("\nExtracted items:")
                for i, item in enumerate(items[:5], 1):
                    print(f"  {i}. {item.get('description')} - ${item.get('price')}")
                if len(items) > 5:
                    print(f"  ... and {len(items) - 5} more items")
                    
            return {
                'image_path': image_path,
                'store_name': store_name,
                'handler': 'key_food',
                'items_count': len(items),
                'subtotal': totals.get('subtotal'),
                'tax': totals.get('tax'),
                'total': totals.get('total'),
                'confidence': 0.6 if len(items) > 0 and totals.get('total') else 0.3,
                'success': len(items) > 0 and totals.get('total') is not None
            }
    
    # If no store was detected or no specialized handler matched, use generic parsing
    print("\nUsing generic fallback parsing...")
    items = analyzer.parse_items_fallback(ocr_text)
    totals = analyzer.extract_totals_fallback(ocr_text)
    
    print(f"Items extracted: {len(items)}")
    print(f"Subtotal: {totals.get('subtotal')}")
    print(f"Tax: {totals.get('tax')}")
    print(f"Total: {totals.get('total')}")
    
    # Show extracted items
    if items:
        print("\nExtracted items:")
        for i, item in enumerate(items[:5], 1):
            print(f"  {i}. {item.get('description')} - ${item.get('price')}")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more items")
    
    return {
        'image_path': image_path,
        'store_name': store_name or "Unknown",
        'handler': 'generic',
        'items_count': len(items),
        'subtotal': totals.get('subtotal'),
        'tax': totals.get('tax'),
        'total': totals.get('total'),
        'confidence': 0.5 if len(items) > 0 and totals.get('total') else 0.2,
        'success': len(items) > 0 and totals.get('total') is not None
    }

def test_all_receipts(upload_dir: str = "uploads/receipts", save_results: bool = True, debug: bool = False) -> Dict[str, Any]:
    """
    Test all receipt images in the uploads directory.
    
    Args:
        upload_dir: Directory containing receipt images
        save_results: Whether to save test results to a JSON file
        debug: Whether to enable debug mode
        
    Returns:
        Dict with test results summary
    """
    # Initialize analyzer
    analyzer = ReceiptAnalyzer()
    
    # Get all image files from the upload directory
    image_files = []
    for root, _, files in os.walk(upload_dir):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_files.append(os.path.join(root, file))
    
    print(f"Found {len(image_files)} receipt images to test")
    
    # Initialize results
    results = []
    
    # Test each image
    for i, image_path in enumerate(image_files):
        print(f"\nTesting image {i+1}/{len(image_files)}")
        try:
            result = test_receipt(image_path, analyzer, debug=debug)
            result['filename'] = os.path.basename(image_path)
            results.append(result)
        except Exception as e:
            import traceback
            print(f"Error testing receipt {image_path}: {str(e)}")
            print(traceback.format_exc())
            results.append({
                'image_path': image_path,
                'filename': os.path.basename(image_path),
                'error': str(e),
                'success': False
            })
    
    # Create summary
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_receipts': len(results),
        'successful': sum(1 for r in results if r.get('success', False)),
        'failed': sum(1 for r in results if not r.get('success', False)),
        'by_store': {},
        'by_handler': {},
        'results': results
    }
    
    # Compile statistics
    for result in results:
        store = result.get('store_name', 'Unknown')
        handler = result.get('handler', 'unknown')
        
        # Count by store
        if store not in summary['by_store']:
            summary['by_store'][store] = {
                'total': 0,
                'successful': 0,
                'items_extracted': 0
            }
        summary['by_store'][store]['total'] += 1
        if result.get('success', False):
            summary['by_store'][store]['successful'] += 1
        summary['by_store'][store]['items_extracted'] += result.get('items_count', 0)
        
        # Count by handler
        if handler not in summary['by_handler']:
            summary['by_handler'][handler] = {
                'total': 0,
                'successful': 0,
                'items_extracted': 0
            }
        summary['by_handler'][handler]['total'] += 1
        if result.get('success', False):
            summary['by_handler'][handler]['successful'] += 1
        summary['by_handler'][handler]['items_extracted'] += result.get('items_count', 0)
    
    # Print summary
    print("\n===== TESTING SUMMARY =====")
    print(f"Total receipts tested: {summary['total_receipts']}")
    print(f"Successful: {summary['successful']} ({summary['successful']/summary['total_receipts']*100:.1f}%)")
    print(f"Failed: {summary['failed']} ({summary['failed']/summary['total_receipts']*100:.1f}%)")
    
    print("\nResults by store:")
    for store, stats in summary['by_store'].items():
        success_rate = stats['successful'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {store}: {stats['successful']}/{stats['total']} ({success_rate:.1f}%), {stats['items_extracted']} items extracted")
    
    print("\nResults by handler:")
    for handler, stats in summary['by_handler'].items():
        success_rate = stats['successful'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"  {handler}: {stats['successful']}/{stats['total']} ({success_rate:.1f}%), {stats['items_extracted']} items extracted")
    
    # Save results if requested
    if save_results:
        output_file = f"receipt_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\nTest results saved to {output_file}")
    
    return summary

def main():
    """Parse command line arguments and run tests."""
    parser = argparse.ArgumentParser(description="Test receipt parsing with different store handlers")
    parser.add_argument("--upload-dir", default="uploads/receipts", help="Directory containing receipt images")
    parser.add_argument("--image", help="Path to a single receipt image to test")
    parser.add_argument("--no-save", action="store_true", help="Don't save test results to JSON")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Test a single image if specified
    if args.image:
        analyzer = ReceiptAnalyzer()
        test_receipt(args.image, analyzer, debug=args.debug)
    # Otherwise test all images in the upload directory
    else:
        test_all_receipts(args.upload_dir, not args.no_save, args.debug)

if __name__ == "__main__":
    main() 