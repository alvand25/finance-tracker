import argparse
import os
import csv
import traceback
import sys
from typing import Dict, List, Any, Optional

# Add project root to path to allow importing from project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.receipt_service import ReceiptService
from utils.receipt_analyzer import ReceiptAnalyzer
from storage.json_storage import JSONStorage

def process_vendor_specifics(results, store_name, ocr_text, image_path, analyzer):
    """
    Apply vendor-specific processing to improve results.
    
    Args:
        results (dict): Current results dictionary
        store_name (str): Detected store name
        ocr_text (str): OCR text extracted from the receipt
        image_path (str): Path to the receipt image
        analyzer (ReceiptAnalyzer): Analyzer instance
        
    Returns:
        dict: Updated results dictionary
    """
    if not store_name:
        return results
    
    store_name_lower = store_name.lower()
    
    # Handle Costco receipts
    if "costco" in store_name_lower and hasattr(analyzer, "handle_costco_receipt"):
        print(f"Applying Costco-specific handler for {store_name}")
        costco_result = analyzer.handle_costco_receipt(ocr_text, image_path)
        
        # If Costco handler found more items or better totals, merge results
        if costco_result:
            if (len(costco_result.get("items", [])) > len(results.get("items", [])) or
                (not results.get("total") and costco_result.get("total"))):
                
                print(f"Costco handler found {len(costco_result.get('items', []))} items")
                
                # Update results with Costco data
                results["items_count"] = len(costco_result.get("items", []))
                results["store_name"] = "Costco Wholesale"
                results["subtotal"] = costco_result.get("subtotal")
                results["tax"] = costco_result.get("tax")
                results["total"] = costco_result.get("total")
                results["currency"] = costco_result.get("currency", "USD")
                results["confidence"] = costco_result.get("confidence", {}).get("overall", 0.7)
                
                if results["total"]:
                    results["processing_status"] = "processed"
    
    # Handle Trader Joe's receipts
    elif ("trader" in store_name_lower and "joe" in store_name_lower) and hasattr(analyzer, "handle_trader_joes_receipt"):
        print(f"Applying Trader Joe's-specific handler for {store_name}")
        tj_result = analyzer.handle_trader_joes_receipt(ocr_text, image_path)
        
        # If TJ handler found more items or better totals, merge results
        if tj_result:
            if (len(tj_result.get("items", [])) > len(results.get("items", [])) or
                (not results.get("total") and tj_result.get("total"))):
                
                print(f"Trader Joe's handler found {len(tj_result.get('items', []))} items")
                
                # Update results with TJ data
                results["items_count"] = len(tj_result.get("items", []))
                results["store_name"] = "Trader Joe's"
                results["subtotal"] = tj_result.get("subtotal")
                results["tax"] = tj_result.get("tax")
                results["total"] = tj_result.get("total")
                results["currency"] = tj_result.get("currency", "USD")
                results["confidence"] = tj_result.get("confidence", {}).get("overall", 0.7)
                
                if results["total"]:
                    results["processing_status"] = "processed"
    
    # Handle H Mart receipts
    elif ("h mart" in store_name_lower or "hmart" in store_name_lower) and hasattr(analyzer, "handle_hmart_receipt"):
        print(f"Applying H Mart-specific handler for {store_name}")
        hmart_result = analyzer.handle_hmart_receipt(ocr_text, image_path)
        
        # If H Mart handler found more items or better totals, merge results
        if hmart_result:
            if (len(hmart_result.get("items", [])) > len(results.get("items", [])) or
                (not results.get("total") and hmart_result.get("total"))):
                
                print(f"H Mart handler found {len(hmart_result.get('items', []))} items")
                
                # Update results with H Mart data
                results["items_count"] = len(hmart_result.get("items", []))
                results["store_name"] = "H Mart"
                results["subtotal"] = hmart_result.get("subtotal")
                results["tax"] = hmart_result.get("tax")
                results["total"] = hmart_result.get("total")
                results["currency"] = hmart_result.get("currency", "USD")
                results["confidence"] = hmart_result.get("confidence", {}).get("overall", 0.7)
                
                if results["total"]:
                    results["processing_status"] = "processed"
    
    # Apply fallback parsing for other stores
    else:
        # For H Mart or Key Food without specialized handlers, use fallback
        if ("h mart" in store_name_lower or "hmart" in store_name_lower or
            "key food" in store_name_lower):
            
            store_type = "hmart" if "mart" in store_name_lower else "key_food"
            print(f"Applying generic fallback parsing for {store_name} with type hint: {store_type}")
            
            # Try fallback item parsing
            if not results.get("items") and hasattr(analyzer, "parse_items_fallback"):
                fallback_items = analyzer.parse_items_fallback(ocr_text, store_type)
                if fallback_items:
                    print(f"Fallback parsing found {len(fallback_items)} items")
                    results["items_count"] = len(fallback_items)
            
            # Try fallback total extraction
            if (not results.get("total") or not results.get("subtotal")) and hasattr(analyzer, "extract_totals_fallback"):
                fallback_totals = analyzer.extract_totals_fallback(ocr_text, store_type)
                if fallback_totals:
                    print("Fallback extraction found totals")
                    if fallback_totals.get("subtotal"):
                        results["subtotal"] = fallback_totals.get("subtotal")
                    if fallback_totals.get("tax"):
                        results["tax"] = fallback_totals.get("tax")
                    if fallback_totals.get("total"):
                        results["total"] = fallback_totals.get("total")
                        results["processing_status"] = "processed"
    
    return results 

def process_receipt_image(image_path, receipt_service):
    """
    Process a receipt image file and extract information.
    
    Args:
        image_path (str): Path to the image file
        receipt_service (ReceiptService): Service to process receipts
        
    Returns:
        dict: Results of processing
    """
    # Initialize analyzer
    analyzer = ReceiptAnalyzer()
    
    try:
        # Read the image file
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        # Extract OCR text
        ocr_text = analyzer.extract_text(image_path)
        store_name = analyzer._extract_store_name(ocr_text)
        
        # Process with receipt service
        receipt = receipt_service.process_receipt_image(image_path)
        
        # Prepare results
        results = {
            "processing_status": receipt.processing_status,
            "store_name": receipt.merchant_name or store_name,
            "date": receipt.date,
            "currency": receipt.currency_type,
            "subtotal": receipt.subtotal_amount,
            "tax": receipt.tax_amount,
            "total": receipt.total_amount,
            "payment_method": receipt.payment_method,
            "items_count": len(receipt.items or []),
            "confidence": receipt.confidence_score
        }
        
        # Apply vendor-specific processing
        results = process_vendor_specifics(results, store_name, ocr_text, image_path, analyzer)
        
        return results
        
    except Exception as e:
        print(f"Error processing image {image_path}: {str(e)}")
        traceback.print_exc()
        return {
            "processing_status": "failed",
            "error": str(e)
        } 

def main():
    """Parse arguments and process receipt images."""
    parser = argparse.ArgumentParser(description="Test receipt processing capabilities")
    parser.add_argument("--image", help="Path to a receipt image file to process")
    parser.add_argument("--dir", help="Directory containing receipt images to process")
    parser.add_argument("--output", help="Path to output CSV file for results")
    parser.add_argument("--create-samples", action="store_true", help="Create sample dataset from uploaded receipts")
    
    args = parser.parse_args()
    
    # Initialize services
    storage = JSONStorage(base_path="data")
    receipt_service = ReceiptService(storage)
    
    # Create sample dataset if requested
    if args.create_samples:
        try:
            print("Creating sample dataset from uploaded receipts...")
            from create_sample_dataset import main as create_samples
            create_samples(["--process-all"])
            return
        except Exception as e:
            print(f"Error creating sample dataset: {str(e)}")
            traceback.print_exc()
            return
    
    # Process a single image
    if args.image:
        if not os.path.exists(args.image):
            print(f"Image file not found: {args.image}")
            return
        
        print(f"Processing receipt image: {args.image}")
        result = process_receipt_image(args.image, receipt_service)
        print("\nResults:")
        for key, value in result.items():
            print(f"{key}: {value}")
    
    # Process a directory of images
    elif args.dir:
        if not os.path.exists(args.dir):
            print(f"Directory not found: {args.dir}")
            return
        
        results = []
        image_files = []
        
        # Get image files from directory
        for filename in os.listdir(args.dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_files.append(os.path.join(args.dir, filename))
        
        print(f"Found {len(image_files)} image files to process")
        
        # Process each image
        for i, image_path in enumerate(image_files):
            print(f"\nProcessing image {i+1}/{len(image_files)}: {image_path}")
            result = process_receipt_image(image_path, receipt_service)
            
            # Add filename to result
            result["filename"] = os.path.basename(image_path)
            results.append(result)
            
            # Print summary
            print(f"  Status: {result.get('processing_status')}")
            print(f"  Store: {result.get('store_name')}")
            print(f"  Total: {result.get('total')}")
            print(f"  Items: {result.get('items_count')}")
        
        # Save results to CSV if output specified
        if args.output and results:
            try:
                print(f"\nSaving results to {args.output}")
                with open(args.output, 'w', newline='') as csvfile:
                    # Get all unique keys from results
                    fieldnames = set()
                    for result in results:
                        fieldnames.update(result.keys())
                    
                    fieldnames = sorted(fieldnames)
                    
                    # Write CSV
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)
                    
                print(f"Successfully saved results for {len(results)} receipts")
            except Exception as e:
                print(f"Error saving results to CSV: {str(e)}")
                traceback.print_exc()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 