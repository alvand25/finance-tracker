#!/usr/bin/env python
"""
Script to test all receipt samples with enhanced debug logging.
This will help diagnose why the OCR system is failing on some receipts.
"""

import os
import sys
import argparse
import logging
import json
import glob
from datetime import datetime

from receipt_processor import ReceiptProcessor

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug_test.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def test_receipt_image(image_path, debug_dir, options=None):
    """Test a single receipt image and return results."""
    try:
        processor = ReceiptProcessor(
            debug_mode=True,
            debug_output_dir=debug_dir,
            debug_ocr_output=options.get('debug_ocr_output', False)
        )
        
        logger.info("=" * 80)
        logger.info(f"Processing image: {image_path}")
        logger.info("=" * 80)
        
        # Process the receipt
        results = processor.process_image(image_path, options)
        
        # Log results summary
        logger.info(f"Results for {os.path.basename(image_path)}:")
        logger.info(f"  Store: {results.get('store', 'unknown')} (confidence: {results.get('store_confidence', 0):.2f})")
        logger.info(f"  Handler: {results.get('handler', 'unknown')}")
        logger.info(f"  Items: {len(results.get('items', []))}")
        logger.info(f"  Subtotal: {results.get('subtotal')}")
        logger.info(f"  Tax: {results.get('tax')}")
        logger.info(f"  Total: {results.get('total')}")
        logger.info(f"  Confidence: {results.get('confidence', {}).get('overall', 0):.2f}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "image_path": image_path}

def test_all_samples(samples_dir, debug_dir, store_hint=None, recursive=False):
    """Test all samples in the directory."""
    # Create debug directory if it doesn't exist
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    # Find all image files
    image_files = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        if recursive:
            # Use ** pattern for recursive search through subdirectories
            pattern = os.path.join(samples_dir, "**", ext)
            image_files.extend(glob.glob(pattern, recursive=True))
        else:
            pattern = os.path.join(samples_dir, ext)
            image_files.extend(glob.glob(pattern))
        
    if not image_files:
        logger.error(f"No image files found in {samples_dir}" + (" (including subdirectories)" if recursive else ""))
        # Check if images directory exists within samples
        images_dir = os.path.join(samples_dir, "images")
        if os.path.isdir(images_dir):
            logger.info(f"Found 'images' subdirectory at {images_dir}, trying there...")
            images_pattern = os.path.join(images_dir, "*.jpg")
            image_files.extend(glob.glob(images_pattern))
            images_pattern = os.path.join(images_dir, "*.jpeg")
            image_files.extend(glob.glob(images_pattern))
            images_pattern = os.path.join(images_dir, "*.png")
            image_files.extend(glob.glob(images_pattern))
            
            if not image_files:
                logger.error(f"No image files found in {images_dir} either.")
                logger.info("Try specifying the exact path with --samples-dir or use --recursive to scan subdirectories.")
                return
        else:
            # Suggest directories to check
            logger.info("Checking for potential image directories...")
            for subdir in os.listdir(samples_dir):
                full_path = os.path.join(samples_dir, subdir)
                if os.path.isdir(full_path):
                    logger.info(f"Found directory: {full_path}")
            logger.info("Try specifying one of these directories with --samples-dir or use --recursive to scan all subdirectories.")
            return
        
    logger.info(f"Found {len(image_files)} images to process")
    
    # Process each image
    results = []
    for image_path in image_files:
        options = {}
        if store_hint:
            options["store_hint"] = store_hint
            
        result = test_receipt_image(image_path, debug_dir, options)
        result["image_path"] = image_path
        results.append(result)
        
    # Save overall results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = os.path.join(debug_dir, f"test_results_{timestamp}.json")
    
    try:
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Saved results to {results_file}")
    except Exception as e:
        logger.error(f"Error saving results: {str(e)}")
        
    # Generate a summary report
    success_count = sum(1 for r in results if len(r.get("items", [])) > 0)
    total_count = len(results)
    success_rate = success_count / total_count if total_count > 0 else 0
    
    logger.info("\n" + "=" * 40)
    logger.info(f"TEST SUMMARY:")
    logger.info(f"  Total images: {total_count}")
    logger.info(f"  Successful extractions: {success_count} ({success_rate:.1%})")
    logger.info(f"  Failed extractions: {total_count - success_count} ({1-success_rate:.1%})")
    logger.info("=" * 40)
    
    # List all failures for quick reference
    if total_count - success_count > 0:
        logger.info("\nFailed images:")
        for result in results:
            if len(result.get("items", [])) == 0:
                image_name = os.path.basename(result["image_path"])
                store = result.get("store", "unknown")
                error = result.get("error", "No items extracted")
                logger.info(f"  - {image_name}: {store} - {error}")
                
    return results

def generate_side_by_side_report(results, debug_dir):
    """Generate an HTML report with side-by-side comparisons."""
    # Create an HTML file for better visualization
    html_path = os.path.join(debug_dir, "side_by_side_report.html")
    
    with open(html_path, "w") as f:
        f.write(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Receipt OCR Results</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .receipt {{ margin-bottom: 30px; border: 1px solid #ccc; padding: 15px; }}
                .receipt-header {{ background-color: #f5f5f5; padding: 10px; margin-bottom: 10px; }}
                .receipt-body {{ display: flex; }}
                .image-section {{ flex: 1; padding-right: 15px; }}
                .results-section {{ flex: 2; }}
                .image-section img {{ max-width: 300px; border: 1px solid #ddd; }}
                .success {{ color: green; }}
                .failure {{ color: red; }}
                table {{ border-collapse: collapse; width: 100%; }}
                table, th, td {{ border: 1px solid #ddd; }}
                th, td {{ padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Receipt OCR Test Results</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """)
        
        # Add summary section
        success_count = sum(1 for r in results if len(r.get("items", [])) > 0)
        total_count = len(results)
        success_rate = success_count / total_count if total_count > 0 else 0
        
        f.write(f"""
            <div class="summary">
                <h2>Summary</h2>
                <p>Total receipts tested: {total_count}</p>
                <p>Successful extractions: {success_count} ({success_rate:.1%})</p>
                <p>Failed extractions: {total_count - success_count} ({1-success_rate:.1%})</p>
            </div>
        """)
        
        # Add each receipt
        for result in results:
            image_path = result.get("image_path", "")
            image_name = os.path.basename(image_path)
            store = result.get("store", "unknown")
            store_confidence = result.get("store_confidence", 0)
            handler = result.get("handler", "unknown")
            items = result.get("items", [])
            subtotal = result.get("subtotal")
            tax = result.get("tax")
            total = result.get("total")
            confidence = result.get("confidence", {}).get("overall", 0)
            
            status_class = "success" if len(items) > 0 else "failure"
            status_text = "SUCCESS" if len(items) > 0 else "FAILURE"
            
            f.write(f"""
                <div class="receipt">
                    <div class="receipt-header">
                        <h2>{image_name} - <span class="{status_class}">{status_text}</span></h2>
                    </div>
                    <div class="receipt-body">
                        <div class="image-section">
                            <h3>Image</h3>
                            <img src="{image_path}" alt="{image_name}" />
                        </div>
                        <div class="results-section">
                            <h3>Results</h3>
                            <table>
                                <tr><th>Property</th><th>Value</th></tr>
                                <tr><td>Store</td><td>{store} (confidence: {store_confidence:.2f})</td></tr>
                                <tr><td>Handler</td><td>{handler}</td></tr>
                                <tr><td>Items Count</td><td>{len(items)}</td></tr>
                                <tr><td>Subtotal</td><td>{subtotal}</td></tr>
                                <tr><td>Tax</td><td>{tax}</td></tr>
                                <tr><td>Total</td><td>{total}</td></tr>
                                <tr><td>Confidence</td><td>{confidence:.2f}</td></tr>
                            </table>
            """)
            
            # Add items table if there are any
            if items:
                f.write("""
                            <h3>Items</h3>
                            <table>
                                <tr><th>Description</th><th>Price</th><th>Quantity</th></tr>
                """)
                
                for item in items:
                    f.write(f"""
                                <tr>
                                    <td>{item.get('description', '')}</td>
                                    <td>{item.get('price', '')}</td>
                                    <td>{item.get('quantity', 1)}</td>
                                </tr>
                    """)
                    
                f.write("""
                            </table>
                """)
                
            # Link to OCR text file if it exists
            ocr_text_path = os.path.join(debug_dir, f"ocr_{image_name}.txt")
            if os.path.exists(ocr_text_path):
                relative_path = os.path.relpath(ocr_text_path, debug_dir)
                f.write(f"""
                            <h3>OCR Text</h3>
                            <p><a href="{relative_path}" target="_blank">View OCR Text</a></p>
                """)
                
            f.write("""
                        </div>
                    </div>
                </div>
            """)
            
        f.write("""
        </body>
        </html>
        """)
        
    logger.info(f"Generated side-by-side report at {html_path}")
    return html_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test receipt OCR on sample images")
    parser.add_argument("--samples-dir", default="samples", help="Directory containing sample receipt images")
    parser.add_argument("--debug-dir", default="debug_output", help="Directory for debug output")
    parser.add_argument("--store-hint", help="Optional store hint to apply to all samples")
    parser.add_argument("--html-report", action="store_true", help="Generate HTML report with side-by-side results")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories recursively for images")
    parser.add_argument("--images-subdir", help="Specific images subdirectory within samples dir (e.g., 'images')")
    parser.add_argument("--single-image", help="Process a single image file only")
    parser.add_argument("--debug-ocr-output", action="store_true", help="Log raw OCR output for debugging")
    
    args = parser.parse_args()
    
    logger.info("Starting test with enhanced debug logging")
    
    # Handle single-image processing
    if args.single_image:
        if not os.path.exists(args.single_image):
            logger.error(f"Image file not found: {args.single_image}")
        else:
            logger.info(f"Processing single image: {args.single_image}")
            result = test_receipt_image(args.single_image, args.debug_dir, 
                                        {"store_hint": args.store_hint,
                                         "debug_ocr_output": args.debug_ocr_output} if args.store_hint else {"debug_ocr_output": args.debug_ocr_output})
            
            # Save result for potential HTML report
            results = [{"image_path": args.single_image, **result}]
            
            if args.html_report:
                generate_side_by_side_report(results, args.debug_dir)
    else:
        # Handle images subdirectory if specified
        samples_path = args.samples_dir
        if args.images_subdir:
            samples_path = os.path.join(samples_path, args.images_subdir)
            logger.info(f"Looking for images in: {samples_path}")
            
        options = {}
        if args.store_hint:
            options["store_hint"] = args.store_hint
        if args.debug_ocr_output:
            options["debug_ocr_output"] = True
            
        results = test_all_samples(samples_path, args.debug_dir, args.store_hint, args.recursive)
        
        if args.html_report and results:
            generate_side_by_side_report(results, args.debug_dir) 