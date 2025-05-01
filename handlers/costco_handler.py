from typing import Dict, List, Any, Optional
import logging
import re
from datetime import datetime
import pytesseract
import cv2
import numpy as np

from .base_handler import BaseReceiptHandler
from utils.image_utils import preprocess_image

logger = logging.getLogger(__name__)

class CostcoReceiptHandler(BaseReceiptHandler):
    """Handler for Costco receipts."""
    
    def __init__(self):
        """Initialize the Costco receipt handler."""
        super().__init__()
        self.store_name = "Costco"
        self.currency = "USD"
        
        # Costco-specific patterns
        self.item_pattern = re.compile(r'^([A-Z0-9].*?)\s+(\d+\.\d{2})$')
        self.total_patterns = {
            'subtotal': re.compile(r'(?i)subtotal\s*\$?\s*(\d+\.\d{2})'),
            'tax': re.compile(r'(?i)tax\s*\$?\s*(\d+\.\d{2})'),
            'total': re.compile(r'(?i)total\s*\$?\s*(\d+\.\d{2})')
        }
        self.payment_patterns = {
            'credit': re.compile(r'(?i)(visa|mastercard|amex|discover)'),
            'debit': re.compile(r'(?i)debit'),
            'cash': re.compile(r'(?i)cash\s+tendered'),
            'ebt': re.compile(r'(?i)ebt')
        }
    
    def extract_items(self, ocr_text: str, image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract line items from Costco receipt."""
        items = []
        lines = ocr_text.split('\n')
        
        for line in lines:
            # Skip empty lines and summary lines
            if not line.strip() or any(keyword in line.lower() for keyword in ['subtotal', 'tax', 'total']):
                continue
            
            # Try to match item pattern
            match = self.item_pattern.match(line.strip())
            if match:
                description, price = match.groups()
                try:
                    items.append({
                        'description': description.strip(),
                        'price': float(price),
                        'quantity': 1  # Default quantity
                    })
                except ValueError:
                    logger.warning(f"Could not parse price from line: {line}")
                    continue
        
        # If no items found and image path provided, try enhanced OCR
        if not items and image_path:
            try:
                # Preprocess image for better OCR
                processed_image = preprocess_image(image_path)
                if processed_image is not None:
                    enhanced_text = pytesseract.image_to_string(
                        processed_image,
                        config='--psm 6 -l eng'
                    )
                    # Recursively try with enhanced text
                    items = self.extract_items(enhanced_text)
            except Exception as e:
                logger.error(f"Error in enhanced OCR: {str(e)}")
        
        return items
    
    def extract_totals(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract total amounts from Costco receipt."""
        totals = {
            'subtotal': None,
            'tax': None,
            'total': None
        }
        
        # Try to find totals using patterns
        for total_type, pattern in self.total_patterns.items():
            match = pattern.search(ocr_text)
            if match:
                try:
                    totals[total_type] = float(match.group(1))
                except ValueError:
                    logger.warning(f"Could not parse {total_type} amount")
        
        # Validate and calculate missing values
        if totals['subtotal'] and totals['tax'] and not totals['total']:
            totals['total'] = round(totals['subtotal'] + totals['tax'], 2)
        elif totals['subtotal'] and totals['total'] and not totals['tax']:
            totals['tax'] = round(totals['total'] - totals['subtotal'], 2)
        
        return totals
    
    def extract_metadata(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract metadata from Costco receipt."""
        metadata = super().extract_metadata(ocr_text, image_path)
        
        # Set store name
        metadata['store_name'] = self.store_name
        metadata['currency'] = self.currency
        
        # Try to extract date
        date_pattern = re.compile(r'(\d{2}/\d{2}/\d{2,4})')
        date_match = date_pattern.search(ocr_text)
        if date_match:
            try:
                date_str = date_match.group(1)
                # Handle 2-digit years
                if len(date_str.split('/')[-1]) == 2:
                    date_str = date_str[:-2] + '20' + date_str[-2:]
                metadata['date'] = datetime.strptime(date_str, '%m/%d/%Y')
            except ValueError:
                logger.warning("Could not parse receipt date")
        
        # Try to extract payment method
        for method, pattern in self.payment_patterns.items():
            if pattern.search(ocr_text):
                metadata['payment_method'] = method
                break
        
        return metadata
    
    def validate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean up extraction results."""
        validated = super().validate_results(results)
        
        # Costco-specific validation
        if validated.get('items'):
            # Remove any items with suspiciously high prices (likely misread)
            validated['items'] = [
                item for item in validated['items']
                if item.get('price', 0) < 1000  # Costco rarely has items over $1000
            ]
            
            # Update confidence based on number of items found
            if len(validated['items']) > 0:
                validated['confidence']['items'] = min(0.9, 0.5 + len(validated['items']) * 0.02)
        
        return validated 