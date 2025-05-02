#!/usr/bin/env python3
"""
Create Sample Dataset

This script processes receipt images and generates a standardized dataset with:
1. Original image
2. Raw OCR text
3. Annotated receipt data (manual or auto-generated)

Usage:
  python create_sample_dataset.py [options]

Options:
  --source=<dir>      Source directory for receipt images (default: uploads/receipts)
  --target=<dir>      Target directory for dataset (default: samples)
  --annotate          Interactively annotate receipts
  --process-all       Process all images from source
  --vendor=<name>     Process images from a specific vendor
"""

import os
import sys
import json
import argparse
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime
import cv2
from PIL import Image
import io
import time
import traceback
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.receipt_analyzer import ReceiptAnalyzer
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR
from config.google_vision_config import GoogleVisionConfig

# Constants
SOURCE_DIR = "uploads/receipts"
TARGET_DIR = "samples"
IMAGE_DIR = os.path.join(TARGET_DIR, "images")
OCR_DIR = os.path.join(TARGET_DIR, "ocr")
ANNOTATION_DIR = os.path.join(TARGET_DIR, "annotations")
VENDORS = ["Costco", "Trader Joe's", "Target", "H Mart", "Key Food"]

logger = logging.getLogger(__name__)

def ensure_dirs():
    """Ensure all required directories exist."""
    for dir_path in [TARGET_DIR, IMAGE_DIR, OCR_DIR, ANNOTATION_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Created directory: {dir_path}")

def setup_ocr(use_google_ocr: bool = False) -> Any:
    """Set up OCR engine."""
    if use_google_ocr:
        try:
            config = GoogleVisionConfig()
            if config.is_configured:
                logger.info("Using Google Cloud Vision OCR")
                config.validate()
                return GoogleVisionOCR(credentials_path=config.credentials_path)
            else:
                logger.warning("Google Cloud Vision not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Vision OCR: {str(e)}")
            
    # Fall back to Tesseract
    logger.info("Using Tesseract OCR")
    try:
        return TesseractOCR()
    except Exception as e:
        logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
        return None

def extract_text_from_image(image_path: str, ocr_engine: Any = None) -> str:
    """
    Extract text from an image using OCR.
    
    Args:
        image_path: Path to the image file
        ocr_engine: Optional OCR engine to use
        
    Returns:
        Extracted text
    """
    print(f"Extracting text from: {image_path}")
    
    try:
        # Initialize preprocessor
        preprocessor = ImagePreprocessor()
        
        # Read and preprocess the image
        start_time = time.time()
        processed_image = preprocessor.preprocess(image_path)
        preprocess_time = time.time() - start_time
        print(f"Image preprocessing took {preprocess_time:.2f} seconds")
        
        # Set up OCR engine if not provided
        if ocr_engine is None:
            ocr_engine = setup_ocr()
            
        if ocr_engine is None:
            raise RuntimeError("No OCR engine available")
            
        # Extract text
        start_time = time.time()
        ocr_result = ocr_engine.extract_text(processed_image)
        extraction_time = time.time() - start_time
        print(f"Text extraction took {extraction_time:.2f} seconds")
        
        return ocr_result.get('text', '')
        
    except Exception as e:
        logger.error(f"Error extracting text: {str(e)}")
        return ''

def save_text_to_file(text: str, output_path: str) -> None:
    """
    Save text to a file.
    
    Args:
        text: Text to save
        output_path: Path to save the text file
    """
    with open(output_path, "w") as f:
        f.write(text)
    
    print(f"Saved text to: {output_path}")

def process_image(image_path: str, ocr_engine: Any, debug_output_dir: str = 'debug_output') -> Dict[str, Any]:
    """Process a single receipt image."""
    try:
        # Create preprocessor
        preprocessor = ImagePreprocessor(
            debug_mode=True,
            debug_output_dir=debug_output_dir
        )
        
        # Preprocess image
        processed_image = preprocessor.preprocess(image_path)
        
        # Extract text using OCR
        if ocr_engine is not None:
            ocr_result = ocr_engine.extract_text(processed_image)
            text = ocr_result["text"]
            confidence = ocr_result["confidence"]
            text_blocks = ocr_result.get("text_blocks", [])
        else:
            logger.error("No OCR engine available")
            return {
                'error': 'No OCR engine available',
                'image_path': image_path
            }
            
        # Save OCR text for debugging
        debug_text_path = os.path.join(debug_output_dir, f'ocr_{os.path.basename(image_path)}.txt')
        with open(debug_text_path, 'w') as f:
            f.write(text)
            
        # Analyze receipt
        analyzer = ReceiptAnalyzer(debug_mode=True, debug_output_dir=debug_output_dir)
        results = analyzer.analyze_receipt(text, image_path)
        
        # Add OCR metadata
        results['ocr_metadata'] = {
            'engine': 'google_vision' if isinstance(ocr_engine, GoogleVisionOCR) else 'tesseract',
            'confidence': confidence,
            'text_blocks': text_blocks,
            'processing_time': getattr(ocr_engine, 'last_processing_time', 0)
        }
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        return {
            'error': str(e),
            'image_path': image_path
        }

def detect_vendor(ocr_text: str) -> Optional[str]:
    """
    Detect the vendor from OCR text.
    
    Args:
        ocr_text: OCR text from the receipt
        
    Returns:
        Detected vendor name or None if not detected
    """
    # Convert to lowercase for case-insensitive matching
    ocr_lower = ocr_text.lower()
    
    for vendor in VENDORS:
        # Check for vendor name in the OCR text
        if vendor.lower() in ocr_lower:
            return vendor
    
    # Check for common vendor identifiers
    if "wholesale" in ocr_lower and "costco" in ocr_lower:
        return "Costco"
    elif "trader" in ocr_lower and "joe" in ocr_lower:
        return "Trader Joe's"
    elif "super target" in ocr_lower or "target store" in ocr_lower:
        return "Target"
    elif "h mart" in ocr_lower or "h-mart" in ocr_lower:
        return "H Mart"
    elif "key food" in ocr_lower:
        return "Key Food"
    
    return None

def create_annotation_template(ocr_path: str, image_path: str) -> Dict[str, Any]:
    """
    Create an annotation template from OCR text.
    
    Args:
        ocr_path: Path to the OCR text file
        image_path: Path to the image file
        
    Returns:
        Annotation template dictionary
    """
    # Read OCR text
    with open(ocr_path, "r") as f:
        ocr_text = f.read()
    
    # Detect vendor
    vendor = detect_vendor(ocr_text)
    
    # Create template
    annotation = {
        "metadata": {
            "image_path": image_path,
            "ocr_path": ocr_path,
            "vendor": vendor,
            "date_processed": datetime.now().isoformat(),
            "quality": {
                "ocr_confidence": None,
                "image_quality": None
            }
        },
        "receipt": {
            "store_name": vendor or "Unknown",
            "date": None,
            "time": None,
            "transaction_id": None,
            "store_location": None,
            "payment_method": None,
            "currency": "USD",
            "subtotal": None,
            "tax": None,
            "total": None,
            "items": []
        },
        "ocr_issues": [],
        "parsing_challenges": []
    }
    
    return annotation

def save_annotation(annotation: Dict[str, Any], image_path: str) -> str:
    """
    Save annotation to a file.
    
    Args:
        annotation: Annotation dictionary
        image_path: Path to the original image file
        
    Returns:
        Path to the saved annotation file
    """
    # Get base filename without extension
    base_name = os.path.basename(image_path).split('.')[0]
    annotation_path = os.path.join(ANNOTATION_DIR, f"{base_name}.json")
    
    with open(annotation_path, "w") as f:
        json.dump(annotation, f, indent=2)
    
    print(f"Saved annotation to: {annotation_path}")
    
    return annotation_path

def interactive_annotation(ocr_path: str, image_path: str) -> Dict[str, Any]:
    """
    Interactively annotate a receipt.
    
    Args:
        ocr_path: Path to the OCR text file
        image_path: Path to the image file
        
    Returns:
        Annotation dictionary
    """
    # Read OCR text
    with open(ocr_path, "r") as f:
        ocr_text = f.read()
    
    # Create initial annotation
    annotation = create_annotation_template(ocr_path, image_path)
    
    print("\n===== INTERACTIVE RECEIPT ANNOTATION =====")
    print(f"OCR Text from {ocr_path}:")
    print("-" * 50)
    print(ocr_text)
    print("-" * 50)
    
    # Get store name
    vendor = annotation["receipt"]["store_name"]
    store_name = input(f"Store name [{vendor}]: ").strip()
    if store_name:
        annotation["receipt"]["store_name"] = store_name
    
    # Get date
    date_str = input("Receipt date (YYYY-MM-DD): ").strip()
    if date_str:
        annotation["receipt"]["date"] = date_str
    
    # Get currency
    currency = input("Currency [USD]: ").strip()
    if currency:
        annotation["receipt"]["currency"] = currency
    
    # Get subtotal, tax, total
    subtotal = input("Subtotal: ").strip()
    if subtotal:
        try:
            annotation["receipt"]["subtotal"] = float(subtotal)
        except ValueError:
            print("Invalid subtotal. Using None.")
    
    tax = input("Tax: ").strip()
    if tax:
        try:
            annotation["receipt"]["tax"] = float(tax)
        except ValueError:
            print("Invalid tax. Using None.")
    
    total = input("Total: ").strip()
    if total:
        try:
            annotation["receipt"]["total"] = float(total)
        except ValueError:
            print("Invalid total. Using None.")
    
    # Get payment method
    payment_method = input("Payment method: ").strip()
    if payment_method:
        annotation["receipt"]["payment_method"] = payment_method
    
    # Items
    print("\nEnter receipt items (leave description blank to finish):")
    items = []
    while True:
        description = input("Item description: ").strip()
        if not description:
            break
        
        price = input("Item price: ").strip()
        try:
            price_float = float(price)
            items.append({
                "description": description,
                "price": price_float,
                "quantity": 1
            })
        except ValueError:
            print("Invalid price. Item not added.")
    
    annotation["receipt"]["items"] = items
    
    # OCR issues
    print("\nNote any OCR issues (leave blank to finish):")
    ocr_issues = []
    while True:
        issue = input("OCR issue: ").strip()
        if not issue:
            break
        ocr_issues.append(issue)
    
    annotation["ocr_issues"] = ocr_issues
    
    # Parsing challenges
    print("\nNote any parsing challenges (leave blank to finish):")
    parsing_challenges = []
    while True:
        challenge = input("Parsing challenge: ").strip()
        if not challenge:
            break
        parsing_challenges.append(challenge)
    
    annotation["parsing_challenges"] = parsing_challenges
    
    return annotation

def filter_images_by_vendor(image_paths: List[str], vendor: str) -> List[str]:
    """
    Filter images by vendor.
    
    Args:
        image_paths: List of image paths
        vendor: Vendor name to filter by
        
    Returns:
        Filtered list of image paths
    """
    filtered_paths = []
    
    for image_path in image_paths:
        # Extract text from the image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        analyzer = ReceiptAnalyzer()
        preprocessed_image = analyzer.preprocess_image(image_data)
        extracted_text = analyzer.extract_text(preprocessed_image)
        
        # Check if the vendor name is in the extracted text
        if vendor.lower() in extracted_text.lower():
            filtered_paths.append(image_path)
    
    return filtered_paths

def main():
    """Main entry point for the create_sample_dataset script."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Create Sample Dataset")
    parser.add_argument("--source", default=SOURCE_DIR, help="Source directory for receipt images")
    parser.add_argument("--target", default=TARGET_DIR, help="Target directory for dataset")
    parser.add_argument("--annotate", action="store_true", help="Interactively annotate receipts")
    parser.add_argument("--process-all", action="store_true", help="Process all images from source")
    parser.add_argument("--vendor", help="Process images from a specific vendor")
    parser.add_argument("--use-google-ocr", action="store_true", help="Use Google Cloud Vision OCR")
    args = parser.parse_args()
    
    # Update constants
    global SOURCE_DIR, TARGET_DIR, IMAGE_DIR, OCR_DIR, ANNOTATION_DIR
    SOURCE_DIR = args.source
    TARGET_DIR = args.target
    IMAGE_DIR = os.path.join(TARGET_DIR, "images")
    OCR_DIR = os.path.join(TARGET_DIR, "ocr")
    ANNOTATION_DIR = os.path.join(TARGET_DIR, "annotations")
    
    # Ensure directories exist
    ensure_dirs()
    
    # Get all receipt images from the source directory
    image_paths = []
    if os.path.exists(SOURCE_DIR):
        for filename in os.listdir(SOURCE_DIR):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                image_paths.append(os.path.join(SOURCE_DIR, filename))
    
    # Filter by vendor if specified
    if args.vendor:
        print(f"Filtering images for vendor: {args.vendor}")
        image_paths = filter_images_by_vendor(image_paths, args.vendor)
    
    # Set up OCR engine
    ocr_engine = setup_ocr(args.use_google_ocr)
    
    # Process images
    processed_files = []
    if args.process_all or args.vendor:
        for image_path in image_paths:
            print(f"\nProcessing: {image_path}")
            result = process_image(
                image_path,
                ocr_engine,
                debug_output_dir=os.path.join(TARGET_DIR, 'debug')
            )
            
            # Create annotation
            if args.annotate:
                annotation = interactive_annotation(result["ocr_path"], result["image_path"])
            else:
                annotation = create_annotation_template(result["ocr_path"], result["image_path"])
            
            # Save annotation
            annotation_path = save_annotation(annotation, result["image_path"])
            result["annotation"] = annotation_path
            
            processed_files.append(result)
    else:
        print("No processing mode specified. Use --process-all or --vendor to process images.")
    
    print(f"\nProcessed {len(processed_files)} receipt images.")

    # Save dataset
    dataset_file = os.path.join(TARGET_DIR, 'dataset.json')
    with open(dataset_file, 'w') as f:
        json.dump(processed_files, f, indent=2)
    
    print(f"\nDataset saved to {dataset_file}")

    # Generate summary
    total = len(processed_files)
    success_count = len([r for r in processed_files if 'error' not in r])
    failure_count = total - success_count
    
    print("\nDataset Creation Summary")
    print("=======================")
    print(f"Total images processed: {total}")
    print(f"Successfully processed: {success_count}")
    print(f"Failed to process: {failure_count}")
    print(f"Success rate: {(success_count/total)*100:.1f}%")
    
    if failure_count > 0:
        print("\nFailures:")
        for result in processed_files:
            if 'error' in result:
                print(f"- {result['image_path']}: {result['error']}")

if __name__ == "__main__":
    main() 