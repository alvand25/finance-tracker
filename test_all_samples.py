#!/usr/bin/env python3
"""Unified testing script for receipt handlers."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import pytesseract
from PIL import Image

from handlers.handler_registry import HandlerRegistry
from handlers.base_handler import BaseReceiptHandler
from utils.image_utils import preprocess_image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_store_from_ocr(ocr_text: str) -> Optional[str]:
    """
    Extract store name from OCR text.
    
    Args:
        ocr_text: OCR text from receipt
        
    Returns:
        Store name if found, None otherwise
    """
    # Convert to uppercase for consistent matching
    text_upper = ocr_text.upper()
    
    # Load store mappings
    with open('data/known_stores.json', 'r') as f:
        store_mappings = json.load(f)
    
    # Check each store's patterns
    for store_key, patterns in store_mappings.items():
        for pattern in patterns:
            if pattern.upper() in text_upper:
                return store_key
    
    return None

def process_receipt(image_path: str, registry: HandlerRegistry) -> Dict[str, Any]:
    """
    Process a receipt image using the appropriate handler.
    
    Args:
        image_path: Path to receipt image
        registry: Handler registry instance
        
    Returns:
        Dictionary with processing results
    """
    try:
        logger.info(f"Processing: {image_path}")
        
        # Initialize result structure
        result = {
            'file': os.path.basename(image_path),
            'store': None,
            'items_found': 0,
            'total': None,
            'confidence': 0.0,
            'status': 'pending',
            'errors': [],
            'processed_at': datetime.now().isoformat()
        }
        
        # Preprocess image
        processed_image = preprocess_image(image_path, debug=True)
        if processed_image is None:
            result['status'] = 'failed'
            result['errors'].append('Image preprocessing failed')
            return result
        
        # Perform OCR
        ocr_text = pytesseract.image_to_string(
            processed_image,
            config='--psm 6 -l eng'
        )
        
        if not ocr_text.strip():
            result['status'] = 'failed'
            result['errors'].append('OCR produced no text')
            return result
            
        # Log first few lines of OCR text for debugging
        logger.debug("OCR Text Preview:")
        for line in ocr_text.split('\n')[:5]:
            logger.debug(f"  {line}")
        
        # Determine store type
        store_type = get_store_from_ocr(ocr_text)
        if store_type:
            logger.info(f"Detected store type: {store_type}")
            result['store'] = store_type
        else:
            logger.warning("Could not determine store type")
            result['errors'].append('Unknown store type')
        
        # Get appropriate handler
        handler = registry.get_handler_for_store(store_type or '')
        logger.info(f"Using handler: {handler.__class__.__name__}")
        
        # Process receipt
        receipt_data = handler.process_receipt(ocr_text, image_path)
        
        # Update result with extracted data
        result['items_found'] = len(receipt_data.get('items', []))
        result['total'] = receipt_data.get('total')
        result['confidence'] = receipt_data.get('confidence', {}).get('overall', 0.0)
        
        if result['items_found'] > 0 or result['total'] is not None:
            result['status'] = 'success'
        else:
            result['status'] = 'partial'
            result['errors'].append('No items or total extracted')
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        return {
            'file': os.path.basename(image_path),
            'store': None,
            'items_found': 0,
            'total': None,
            'confidence': 0.0,
            'status': 'failed',
            'errors': [str(e)],
            'processed_at': datetime.now().isoformat()
        }

def main():
    """Main test function."""
    # Initialize handler registry
    registry = HandlerRegistry()
    
    # Get list of sample images
    samples_dir = os.path.join('samples', 'images')
    results: List[Dict[str, Any]] = []
    
    # Process each image
    for filename in sorted(os.listdir(samples_dir)):
        if filename.endswith(('.jpg', '.jpeg', '.png')) and not filename.startswith('.'):
            image_path = os.path.join(samples_dir, filename)
            result = process_receipt(image_path, registry)
            results.append(result)
    
    # Save detailed results
    output_dir = os.path.join('samples', 'reports')
    os.makedirs(output_dir, exist_ok=True)
    
    json_output = os.path.join(
        output_dir,
        f'receipt_test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
    
    with open(json_output, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save CSV summary
    csv_output = os.path.join(
        output_dir,
        f'receipt_test_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )
    
    with open(csv_output, 'w') as f:
        # Write header
        f.write('file,store,items_found,total,confidence,status,errors\n')
        
        # Write each result
        for r in results:
            errors = ';'.join(r['errors']).replace(',', ';')
            f.write(f"{r['file']},{r['store'] or 'unknown'},{r['items_found']},{r['total'] or ''},")
            f.write(f"{r['confidence']:.2f},{r['status']},\"{errors}\"\n")
    
    # Print summary
    print("\nTest Results Summary")
    print("===================")
    
    total = len(results)
    successful = sum(1 for r in results if r['status'] == 'success')
    partial = sum(1 for r in results if r['status'] == 'partial')
    failed = sum(1 for r in results if r['status'] == 'failed')
    
    print(f"Total receipts processed: {total}")
    print(f"Successful: {successful} ({successful/total*100:.1f}%)")
    print(f"Partial: {partial} ({partial/total*100:.1f}%)")
    print(f"Failed: {failed} ({failed/total*100:.1f}%)")
    
    # Print store-type breakdown
    print("\nResults by Store:")
    store_counts = {}
    for r in results:
        store = r['store'] or 'unknown'
        if store not in store_counts:
            store_counts[store] = {'total': 0, 'success': 0, 'partial': 0, 'failed': 0}
        store_counts[store]['total'] += 1
        store_counts[store][r['status']] += 1
    
    for store, counts in sorted(store_counts.items()):
        print(f"\n{store.upper()}:")
        print(f"  Total: {counts['total']}")
        print(f"  Success Rate: {counts['success']/counts['total']*100:.1f}%")
        if counts['partial'] > 0:
            print(f"  Partial: {counts['partial']}")
        if counts['failed'] > 0:
            print(f"  Failed: {counts['failed']}")
    
    print(f"\nDetailed results saved to: {json_output}")
    print(f"Summary saved to: {csv_output}")

if __name__ == '__main__':
    main() 