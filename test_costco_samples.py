#!/usr/bin/env python3
"""Test script for running the Costco receipt handler on sample images."""

import os
import json
import logging
from datetime import datetime
import pytesseract
from PIL import Image

from handlers.costco_handler import CostcoReceiptHandler
from utils.image_utils import preprocess_image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_image(image_path: str, handler: CostcoReceiptHandler) -> dict:
    """
    Process a single receipt image.
    
    Args:
        image_path: Path to the receipt image
        handler: Initialized receipt handler
        
    Returns:
        Dictionary with extraction results and metadata
    """
    try:
        # Preprocess image
        logger.info(f"Processing image: {image_path}")
        processed_image = preprocess_image(image_path, debug=True)
        
        if processed_image is None:
            logger.error("Image preprocessing failed")
            return {
                'error': 'Image preprocessing failed',
                'path': image_path
            }
        
        # Extract text using OCR
        ocr_text = pytesseract.image_to_string(
            processed_image,
            config='--psm 6 -l eng'
        )
        
        if not ocr_text.strip():
            logger.error("OCR produced no text")
            return {
                'error': 'OCR failed to extract text',
                'path': image_path
            }
        
        # Process receipt
        results = handler.process_receipt(ocr_text, image_path)
        
        # Add metadata
        results['image_path'] = image_path
        results['processed_at'] = datetime.now().isoformat()
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        return {
            'error': str(e),
            'path': image_path
        }

def main():
    """Main test function."""
    # Initialize handler
    handler = CostcoReceiptHandler()
    
    # Get list of sample images
    samples_dir = os.path.join('samples', 'images')
    results = []
    
    # Process each image
    for filename in os.listdir(samples_dir):
        if filename.endswith(('.jpg', '.jpeg', '.png')) and not filename.startswith('.'):
            image_path = os.path.join(samples_dir, filename)
            result = process_image(image_path, handler)
            results.append(result)
    
    # Save results
    output_dir = os.path.join('samples', 'reports')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(
        output_dir,
        f'costco_test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {output_file}")
    
    # Print summary
    total = len(results)
    errors = sum(1 for r in results if 'error' in r)
    successes = total - errors
    
    print("\nTest Results Summary")
    print("===================")
    print(f"Total images processed: {total}")
    print(f"Successful: {successes}")
    print(f"Failed: {errors}")
    print(f"Success rate: {(successes/total)*100:.1f}%")
    
    # Print details of failures
    if errors > 0:
        print("\nFailures:")
        for result in results:
            if 'error' in result:
                print(f"- {result['path']}: {result['error']}")

if __name__ == '__main__':
    main() 