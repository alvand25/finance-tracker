"""Receipt analyzer module for extracting structured information from receipt text."""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)

# Import OCR-related modules after logger setup
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR

class ReceiptAnalyzer:
    """Class for analyzing receipt text and extracting structured information."""
    
    def __init__(self, debug_mode: bool = False, output_dir: str = 'debug'):
        """
        Initialize the receipt analyzer.
        
        Args:
            debug_mode: Whether to save debug information
            output_dir: Directory to save debug files
        """
        self.debug_mode = debug_mode
        self.output_dir = output_dir
        self.preprocessor = ImagePreprocessor()
        
        # Initialize OCR engines
        self.google_ocr = None
        self.tesseract_ocr = None
        
        # Initialize Google Vision OCR if configured
        try:
            config = GoogleVisionConfig()
            if config.is_configured:
                self.google_ocr = GoogleVisionOCR(credentials_path=config.credentials_path)
        except Exception as e:
            logger.warning("Failed to initialize Google Cloud Vision OCR: %s", str(e))
            
        # Initialize Tesseract OCR
        try:
            self.tesseract_ocr = TesseractOCR()
        except Exception as e:
            logger.warning("Failed to initialize Tesseract OCR: %s", str(e))
            
        # Store debug info
        self.last_debug_info = {}
        
    def extract_text(self, image: Image.Image, use_google_ocr: bool = False) -> Dict[str, Any]:
        """Extract text from an image using the configured OCR engine."""
        try:
            # Preprocess image
            processed_image = self.preprocessor.preprocess(image)
            
            # Select OCR engine
            if use_google_ocr and self.google_ocr:
                ocr_result = self.google_ocr.extract_text(processed_image)
            elif self.tesseract_ocr:
                ocr_result = self.tesseract_ocr.extract_text(processed_image)
            else:
                raise RuntimeError("No OCR engine available")
                
            # Store debug info
            self.last_debug_info = {
                'ocr_engine': 'google_vision' if use_google_ocr else 'tesseract',
                'confidence': ocr_result.get('confidence', 0),
                'processing_time': ocr_result.get('processing_time', 0),
                'text_blocks': ocr_result.get('text_blocks', [])
            }
            
            return ocr_result
            
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            return {
                'error': str(e),
                'text': '',
                'confidence': 0,
                'text_blocks': []
            }
            
    def analyze_receipt(self, text: str, image_path: Optional[str] = None, store_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze receipt text and extract structured information.
        
        Args:
            text: The OCR text from the receipt
            image_path: Optional path to the original image for debugging
            store_hint: Optional hint about the store name to improve detection
            
        Returns:
            Dictionary containing extracted receipt information
        """
        try:
            # Initialize results dictionary
            results = {
                'text': text,
                'image_path': image_path,
                'store': None,
                'date': None,
                'time': None,
                'items': [],
                'total': None,
                'payment_method': None,
                'card_number': None,
                'tax': None
            }
            
            # Extract store information
            results['store'] = self._extract_store_info(text)
            
            # Use store_hint if provided and no store detected
            if store_hint and not results['store']:
                logger.info(f"Using provided store hint: {store_hint}")
                results['store'] = store_hint
            
            # Extract date and time
            date_time = self._extract_date_time(text)
            if date_time:
                results['date'] = date_time.get('date')
                results['time'] = date_time.get('time')
                
            # Extract items
            results['items'] = self._extract_items(text)
            
            # Extract total amount
            results['total'] = self._extract_total(text)
            
            # Extract payment information
            payment_info = self._extract_payment_info(text)
            results['payment_method'] = payment_info.get('method')
            results['card_number'] = payment_info.get('card_number')
            
            # Extract tax amount
            results['tax'] = self._extract_tax(text)
            
            # Save debug information if enabled
            if self.debug_mode and image_path:
                self._save_debug_info(results, image_path)
                
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing receipt: {str(e)}")
            return {
                'error': str(e),
                'text': text,
                'image_path': image_path
            }
            
    def _extract_store_info(self, text: str) -> Optional[str]:
        """Extract store name from receipt text."""
        try:
            # Common store patterns
            store_patterns = [
                r'COSTCO\s+WHOLESALE',
                r'ZOSTCO\s+WHOLESALE',  # Common OCR error for COSTCO
                r'TRADER\s+JOE\'?S',
                r'WHOLE\s+FOODS',
                r'H\s*MART',
                r'KEY\s*FOOD',
                r'STOP\s*&\s*SHOP',
                r'WALMART',
                r'TARGET',
                r'SAFEWAY',
                r'KROGER',
                r'PUBLIX',
                r'ALDI',
                r'WEGMANS'
            ]
            
            for pattern in store_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    store_name = match.group(0).strip()
                    logger.debug(f"Detected store: {store_name}")
                    return store_name
            
            # Check for h-mart.com domain
            if re.search(r'h\s*mart\.com', text, re.IGNORECASE):
                logger.debug("Detected H-Mart from website URL")
                return 'hmart'
                    
            logger.debug("No store pattern matched in text")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting store info: {str(e)}")
            return None
            
    def _extract_date_time(self, text: str) -> Dict[str, Optional[str]]:
        """Extract date and time from receipt text."""
        try:
            # Date patterns
            date_patterns = [
                r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YYYY or M/D/YY
                r'(\d{1,2}-\d{1,2}-\d{2,4})',  # MM-DD-YYYY or M-D-YY
                r'([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})'  # Mon DD, YYYY
            ]
            
            # Time patterns
            time_patterns = [
                r'(\d{1,2}:\d{2}\s*[AaPp][Mm])',  # HH:MM AM/PM
                r'(\d{2}:\d{2}:\d{2})'  # HH:MM:SS
            ]
            
            date_str = None
            time_str = None
            
            # Find date
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    break
                    
            # Find time
            for pattern in time_patterns:
                match = re.search(pattern, text)
                if match:
                    time_str = match.group(1)
                    break
                    
            return {
                'date': date_str,
                'time': time_str
            }
            
        except Exception as e:
            logger.error(f"Error extracting date/time: {str(e)}")
            return {
                'date': None,
                'time': None
            }
            
    def _extract_items(self, text: str) -> List[Dict[str, Any]]:
        """Extract item details from receipt text."""
        try:
            items = []
            
            # Common item patterns
            item_patterns = [
                # Price at end of line
                r'^(.*?)\s+(\d+\.\d{2})\s*$',
                
                # Item with quantity
                r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})\s*$',
                
                # Item with pound/weight
                r'^([\d.]+)\s*(?:LB|lb|Lb)\s+@\s+(\d+\.\d{2})/(?:LB|lb|Lb)\s+(.*?)\s+(\d+\.\d{2})\s*$'
            ]
            
            # Process each line
            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Try each pattern
                for pattern in item_patterns:
                    match = re.match(pattern, line)
                    if match:
                        # Extract item details based on pattern
                        if '@' in pattern:
                            # Item with quantity/weight
                            qty = float(match.group(1))
                            unit_price = float(match.group(2))
                            name = match.group(3)
                            total = float(match.group(4))
                        else:
                            # Simple item
                            name = match.group(1)
                            total = float(match.group(2))
                            qty = 1
                            unit_price = total
                            
                        items.append({
                            'name': name.strip(),
                            'quantity': qty,
                            'unit_price': unit_price,
                            'total': total
                        })
                        break
                        
            return items
            
        except Exception as e:
            logger.error(f"Error extracting items: {str(e)}")
            return []
            
    def _extract_total(self, text: str) -> Optional[float]:
        """Extract total amount from receipt text."""
        try:
            # Total amount patterns
            total_patterns = [
                r'TOTAL\s*\$?\s*(\d+\.\d{2})',
                r'TOTAL:?\s*\$?\s*(\d+\.\d{2})',
                r'AMOUNT\s*\$?\s*(\d+\.\d{2})',
                r'AMOUNT:?\s*\$?\s*(\d+\.\d{2})',
                r'BALANCE\s*\$?\s*(\d+\.\d{2})',
                r'\*\*\*\*\s*BALANCE\s*\$?\s*(\d+\.\d{2})',
                r'GRAND\s+TOTAL\s*\$?\s*(\d+\.\d{2})',
                r'PURCHASE\s*\$?\s*(\d+\.\d{2})',
                r'TOTAL PURCHASE\s*\$?\s*(\d+\.\d{2})',
                r'TOTAL AMOUNT:?\s*\$?\s*(\d+\.\d{2})'
            ]
            
            for pattern in total_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    total = float(match.group(1))
                    logger.debug(f"Extracted total amount: ${total:.2f}")
                    return total
            
            # Try simple dollar amount pattern for smaller receipts
            dollar_match = re.search(r'\$\s*(\d+\.\d{2})', text)
            if dollar_match:
                total = float(dollar_match.group(1))
                logger.debug(f"Found simple dollar amount as total: ${total:.2f}")
                return total
            
            logger.debug("Failed to extract total amount from receipt text")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting total: {str(e)}")
            return None
            
    def _extract_payment_info(self, text: str) -> Dict[str, Optional[str]]:
        """Extract payment method and card details from receipt text."""
        try:
            payment_info = {
                'method': None,
                'card_number': None
            }
            
            # Payment method patterns
            method_patterns = {
                'CREDIT': r'CREDIT\s*CARD',
                'DEBIT': r'DEBIT\s*CARD',
                'CASH': r'CASH\s*PAYMENT',
                'VISA': r'VISA\s*\d{4}',
                'MASTERCARD': r'MASTER\s*CARD\s*\d{4}',
                'AMEX': r'AMEX\s*\d{4}'
            }
            
            # Card number pattern
            card_pattern = r'X+\s*(\d{4})'
            
            # Find payment method
            for method, pattern in method_patterns.items():
                if re.search(pattern, text, re.IGNORECASE):
                    payment_info['method'] = method
                    break
                    
            # Find card number
            match = re.search(card_pattern, text)
            if match:
                payment_info['card_number'] = match.group(1)
                
            return payment_info
            
        except Exception as e:
            logger.error(f"Error extracting payment info: {str(e)}")
            return {
                'method': None,
                'card_number': None
            }
            
    def _extract_tax(self, text: str) -> Optional[float]:
        """Extract tax amount from receipt text."""
        try:
            # Tax amount patterns
            tax_patterns = [
                r'TAX\s*\$?\s*(\d+\.\d{2})',
                r'TAX:?\s*\$?\s*(\d+\.\d{2})',
                r'SALES\s+TAX\s*\$?\s*(\d+\.\d{2})',
                r'SALES\s+TAX:?\s*\$?\s*(\d+\.\d{2})',
                r'HST\s*\$?\s*(\d+\.\d{2})',
                r'GST\s*\$?\s*(\d+\.\d{2})',
                r'VAT\s*\$?\s*(\d+\.\d{2})'
            ]
            
            for pattern in tax_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    tax = float(match.group(1))
                    logger.debug(f"Extracted tax amount: ${tax:.2f}")
                    return tax
            
            # Check for 0.00 tax amount
            zero_tax_patterns = [
                r'TAX\s*\$?\s*0\.00',
                r'TAX:?\s*\$?\s*0\.00',
                r'TAX\s*\$?\s*0\s*\.',
                r'TAX:?\s*\$?\s*0\s*\.'
            ]
            
            for pattern in zero_tax_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.debug("Found zero tax amount")
                    return 0.0
                    
            logger.debug("Failed to extract tax amount from receipt")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting tax: {str(e)}")
            return None
            
    def _save_debug_info(self, results: Dict[str, Any], image_path: str) -> None:
        """Save debug information to file."""
        try:
            # Create debug output directory
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Save analysis results
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            debug_file = os.path.join(self.output_dir, f'{base_name}_analysis.json')
            
            with open(debug_file, 'w') as f:
                json.dump(results, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving debug info: {str(e)}")
            
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the last OCR operation."""
        return self.last_debug_info 