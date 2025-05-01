#!/usr/bin/env python3
"""
Create a sample dataset from uploaded receipts for testing and development.
"""

import os
import sys
import shutil
import argparse
import logging
import json
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path to allow importing from project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.receipt_service import ReceiptService
from utils.receipt_analyzer import ReceiptAnalyzer
from storage.json_storage import JSONStorage
from utils.receipt_test_runner import process_receipt_image, process_vendor_specifics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_sample_dataset(upload_dir: str = "uploads/receipts",
                          sample_dir: str = "samples",
                          process_all: bool = False,
                          num_samples: int = 10) -> None:
    """
    Create a sample dataset from uploaded receipts.
    
    Args:
        upload_dir: Directory containing uploaded receipts
        sample_dir: Directory to save sample dataset
        process_all: Whether to process all receipts
        num_samples: Number of samples to create if not processing all
    """
    logger.info(f"Creating sample dataset from {upload_dir} to {sample_dir}")
    
    # Initialize services
    storage = JSONStorage(base_path="data")
    receipt_service = ReceiptService(storage)
    analyzer = ReceiptAnalyzer()
    
    # Ensure upload directory exists
    if not os.path.exists(upload_dir):
        logger.error(f"Upload directory does not exist: {upload_dir}")
        return
    
    # Create sample directory
    os.makedirs(sample_dir, exist_ok=True)
    os.makedirs(os.path.join(sample_dir, "images"), exist_ok=True)
    os.makedirs(os.path.join(sample_dir, "metadata"), exist_ok=True)
    
    # Get all image files from upload directory
    image_files = []
    for root, _, files in os.walk(upload_dir):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_files.append(os.path.join(root, file))
    
    # Limit number of samples if not processing all
    if not process_all and len(image_files) > num_samples:
        logger.info(f"Limiting to {num_samples} samples")
        image_files = image_files[:num_samples]
    
    logger.info(f"Found {len(image_files)} receipt images to process")
    
    # Process each image
    results = []
    for i, image_path in enumerate(image_files):
        logger.info(f"Processing image {i+1}/{len(image_files)}: {image_path}")
        
        # Generate a unique filename for the sample
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base_filename = os.path.basename(image_path)
        name, ext = os.path.splitext(base_filename)
        sample_filename = f"{name}_{timestamp}{ext}"
        
        # Copy image to sample directory
        sample_image_path = os.path.join(sample_dir, "images", sample_filename)
        shutil.copy2(image_path, sample_image_path)
        
        # Process receipt image
        try:
            # Extract OCR text
            ocr_text = analyzer.extract_text(image_path)
            store_name = analyzer._extract_store_name(ocr_text)
            
            # Process with both service and vendor-specific handlers
            receipt = receipt_service.process_receipt_image(image_path)
            
            # Create result dictionary
            result = {
                "processing_status": receipt.processing_status,
                "store_name": receipt.merchant_name or store_name,
                "date": receipt.date,
                "currency": receipt.currency_type,
                "subtotal": receipt.subtotal_amount,
                "tax": receipt.tax_amount,
                "total": receipt.total_amount,
                "payment_method": receipt.payment_method,
                "items_count": len(receipt.items or []),
                "confidence": receipt.confidence_score,
                "original_path": image_path,
                "sample_path": sample_image_path,
                "ocr_text": ocr_text,
                "items": [item.__dict__ for item in (receipt.items or [])]
            }
            
            # Apply vendor-specific processing
            result = process_vendor_specifics(result, store_name, ocr_text, image_path, analyzer)
            
            # Save metadata as JSON
            metadata_path = os.path.join(sample_dir, "metadata", f"{name}_{timestamp}.json")
            with open(metadata_path, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            
            # Add to results
            results.append(result)
            
            logger.info(f"  Status: {result.get('processing_status')}")
            logger.info(f"  Store: {result.get('store_name')}")
            logger.info(f"  Total: {result.get('total')}")
            logger.info(f"  Items: {result.get('items_count')}")
            
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Save summary file
    summary = {
        "created_at": datetime.now().isoformat(),
        "total_samples": len(results),
        "by_store": {},
        "by_status": {}
    }
    
    # Compile statistics
    for result in results:
        store = result.get("store_name", "unknown")
        status = result.get("processing_status", "unknown")
        
        # Count by store
        if store not in summary["by_store"]:
            summary["by_store"][store] = 0
        summary["by_store"][store] += 1
        
        # Count by status
        if status not in summary["by_status"]:
            summary["by_status"][status] = 0
        summary["by_status"][status] += 1
    
    # Save summary
    with open(os.path.join(sample_dir, "summary.json"), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    logger.info(f"\nCreated {len(results)} samples in {sample_dir}")
    logger.info(f"Summary by store: {summary['by_store']}")
    logger.info(f"Summary by status: {summary['by_status']}")

def main(args: List[str] = None) -> None:
    """Parse command line arguments and create sample dataset."""
    parser = argparse.ArgumentParser(description="Create a sample dataset from uploaded receipts")
    parser.add_argument("--upload-dir", default="uploads/receipts", help="Directory containing uploaded receipts")
    parser.add_argument("--sample-dir", default="samples", help="Directory to save sample dataset")
    parser.add_argument("--process-all", action="store_true", help="Process all receipts instead of a limited number")
    parser.add_argument("--num-samples", type=int, default=10, help="Number of samples to create if not processing all")
    
    parsed_args = parser.parse_args(args)
    
    create_sample_dataset(
        upload_dir=parsed_args.upload_dir,
        sample_dir=parsed_args.sample_dir,
        process_all=parsed_args.process_all,
        num_samples=parsed_args.num_samples
    )

if __name__ == "__main__":
    main() 