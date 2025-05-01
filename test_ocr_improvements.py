#!/usr/bin/env python
"""
Test script to verify OCR improvements.
Compares original and improved OCR processing with detailed metrics.
"""

import os
import logging
import argparse
import json
from datetime import datetime
from typing import Dict, Any, List
import difflib
from receipt_processor import ReceiptProcessor

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ocr_test.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two text strings."""
    return difflib.SequenceMatcher(None, text1, text2).ratio()

def analyze_ocr_quality(result: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze OCR quality metrics from a result."""
    metrics = {
        'item_count': len(result.get('items', [])),
        'has_total': result.get('total') is not None,
        'has_subtotal': result.get('subtotal') is not None,
        'has_tax': result.get('tax') is not None,
        'store_confidence': result.get('store_confidence', 0),
        'overall_confidence': result.get('confidence', {}).get('overall', 0),
        'extraction_quality': result.get('extraction_quality', 0)
    }
    
    # Calculate completeness score
    completeness = 0.0
    if metrics['has_total']: completeness += 0.4
    if metrics['has_subtotal']: completeness += 0.3
    if metrics['has_tax']: completeness += 0.3
    metrics['completeness'] = completeness
    
    return metrics

def test_ocr_improvements(image_path: str, debug_dir: str = "debug_output", 
                         ground_truth: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Test OCR improvements on a single image.
    
    Args:
        image_path: Path to the receipt image
        debug_dir: Directory for debug output
        ground_truth: Optional ground truth data for accuracy comparison
        
    Returns:
        Dictionary containing test results and metrics
    """
    # Create debug directory if it doesn't exist
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    logger.info(f"Testing OCR improvements on: {image_path}")
    
    # Process with original settings
    logger.info("Processing with original settings...")
    processor_original = ReceiptProcessor(
        debug_mode=True,
        debug_output_dir=os.path.join(debug_dir, "original"),
        debug_ocr_output=True
    )
    result_original = processor_original.process_image(image_path)
    
    # Process with improved settings
    logger.info("Processing with improved settings...")
    processor_improved = ReceiptProcessor(
        debug_mode=True,
        debug_output_dir=os.path.join(debug_dir, "improved"),
        debug_ocr_output=True
    )
    # Use enhanced settings
    processor_improved.image_preprocessor.max_skew_angle = 45.0
    processor_improved.image_preprocessor.target_dpi = 300
    result_improved = processor_improved.process_image(image_path)
    
    # Calculate metrics
    metrics_original = analyze_ocr_quality(result_original)
    metrics_improved = analyze_ocr_quality(result_improved)
    
    # Calculate text similarity if OCR text is available
    if hasattr(processor_original.image_preprocessor, 'last_ocr_text') and \
       hasattr(processor_improved.image_preprocessor, 'last_ocr_text'):
        text_similarity = calculate_text_similarity(
            processor_original.image_preprocessor.last_ocr_text,
            processor_improved.image_preprocessor.last_ocr_text
        )
    else:
        text_similarity = None
    
    # Compare results
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON RESULTS:")
    logger.info("=" * 80)
    
    # Compare store detection
    logger.info("\nStore Detection:")
    logger.info(f"  Original: {result_original.get('store', 'unknown')} (confidence: {result_original.get('store_confidence', 0):.2f})")
    logger.info(f"  Improved: {result_improved.get('store', 'unknown')} (confidence: {result_improved.get('store_confidence', 0):.2f})")
    
    # Compare item extraction
    orig_items = result_original.get('items', [])
    impr_items = result_improved.get('items', [])
    logger.info("\nItem Extraction:")
    logger.info(f"  Original: {len(orig_items)} items found")
    logger.info(f"  Improved: {len(impr_items)} items found")
    
    # Compare totals
    logger.info("\nTotal Detection:")
    logger.info(f"  Original: {result_original.get('total')}")
    logger.info(f"  Improved: {result_improved.get('total')}")
    
    # Compare OCR confidence
    logger.info("\nOCR Confidence:")
    orig_conf = metrics_original['overall_confidence']
    impr_conf = metrics_improved['overall_confidence']
    logger.info(f"  Original: {orig_conf:.2f}")
    logger.info(f"  Improved: {impr_conf:.2f}")
    
    # Show improvement percentages
    if orig_conf > 0:
        conf_improvement = ((impr_conf - orig_conf) / orig_conf) * 100
        logger.info(f"  Confidence improvement: {conf_improvement:+.1f}%")
    
    items_improvement = ((len(impr_items) - len(orig_items)) / max(1, len(orig_items))) * 100
    logger.info(f"  Items extraction improvement: {items_improvement:+.1f}%")
    
    # Compare completeness
    logger.info("\nCompleteness Score:")
    logger.info(f"  Original: {metrics_original['completeness']:.2f}")
    logger.info(f"  Improved: {metrics_improved['completeness']:.2f}")
    
    if text_similarity is not None:
        logger.info(f"\nText Similarity: {text_similarity:.2f}")
    
    # Prepare results summary
    results = {
        'timestamp': datetime.now().isoformat(),
        'image_path': image_path,
        'original': {
            'results': result_original,
            'metrics': metrics_original
        },
        'improved': {
            'results': result_improved,
            'metrics': metrics_improved
        },
        'improvements': {
            'confidence': conf_improvement if orig_conf > 0 else None,
            'items': items_improvement,
            'text_similarity': text_similarity
        }
    }
    
    # Save results
    results_file = os.path.join(debug_dir, f"ocr_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nSaved detailed results to: {results_file}")
    
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test OCR improvements")
    parser.add_argument("image", help="Path to the receipt image to test")
    parser.add_argument("--debug-dir", default="debug_output", help="Directory for debug output")
    parser.add_argument("--ground-truth", help="Path to ground truth JSON file for accuracy comparison")
    
    args = parser.parse_args()
    
    # Load ground truth if provided
    ground_truth = None
    if args.ground_truth and os.path.exists(args.ground_truth):
        with open(args.ground_truth, 'r') as f:
            ground_truth = json.load(f)
    
    if not os.path.exists(args.image):
        logger.error(f"Image file not found: {args.image}")
    else:
        test_ocr_improvements(args.image, args.debug_dir, ground_truth) 