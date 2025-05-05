"""Receipt analyzer module for extracting structured information from receipt text."""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image
from datetime import datetime
from difflib import SequenceMatcher
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
import time
import traceback

logger = logging.getLogger(__name__)

# Import OCR-related modules after logger setup
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR

class ReceiptAnalyzer:
    """Receipt text analysis and parsing."""
    
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
                logger.info("Google Vision OCR initialized")
        except Exception as e:
            logger.warning("Failed to initialize Google Cloud Vision OCR: %s", str(e))
            
        # Initialize Tesseract OCR
        try:
            self.tesseract_ocr = TesseractOCR()
            logger.info("Tesseract OCR initialized")
        except Exception as e:
            logger.warning("Failed to initialize Tesseract OCR: %s", str(e))
            
        # Store debug info
        self.last_debug_info = {}
        
        # Initialize store patterns with fuzzy matching thresholds
        self.store_patterns = {
            'COSTCO WHOLESALE': {
                'patterns': [
                    r'COSTCO\s+WHOLESALE',
                    r'ZOSTCO\s+WHOLESALE',
                    r'C[O0]STC[O0]',
                    r'WHOLESALE\s+CLUB',
                    r'COSTCO\s+#\d+',  # Store numbers
                    r'COSTCO\s+GASOLINE',  # Gas stations
                    r'COSTCO\s+PHARMACY'  # Pharmacy
                ],
                'threshold': 0.75,  # Lowered threshold for better matching
                'item_patterns': [
                    r'^\d{6,}\s+(.*?)\s+(\d+\.\d{2})',  # Item number pattern
                    r'^\d{1,2}\s+@\s+\$?\d+\.\d{2}\s+(.*?)\s+(\d+\.\d{2})',  # Quantity pattern
                    r'^([A-Z0-9\s\-\'\.]+)\s+(\d+\.\d{2})'  # Generic item pattern
                ],
                'header_keywords': ['WHOLESALE', 'WAREHOUSE', 'MEMBER']
            },
            'H MART': {
                'patterns': [
                    r'H\s*MART',
                    r'H-MART',
                    r'HMART',
                    r'H\s*MART\.COM',
                    r'H\s*MART\s+#\d+',
                    r'HMART\s+[A-Z]+',  # Location names
                    r'H\s*MART\s+FRESH'  # Fresh departments
                ],
                'threshold': 0.75,
                'item_patterns': [
                    r'^(\d*\s*)?([^@]+?)\s+(\d+\.\d{2})',
                    r'^(\d+)\s*@\s*(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})',
                    r'^([A-Z0-9\s\-\'\.]+)\s+(\d+\.\d{2})'
                ],
                'header_keywords': ['ASIAN', 'MARKET', 'FRESH']
            },
            'TRADER JOE\'S': {
                'patterns': [
                    r'TRADER\s*JOE\'?S',
                    r'TJ\'?S',
                    r'TRADER\s*JOES',
                    r'TRADER\s*JOE\'?S\s+#\d+',
                    r'TJ\'?S\s+#\d+',
                    r'TRADER\s*JOE\'?S\s+[A-Z]+',  # Location names
                    r'TJ\'?S\s+[A-Z]+'  # Location abbreviations
                ],
                'threshold': 0.75,
                'item_patterns': [
                    r'^(.*?)\s+(\d+\.\d{2})\s*[Ff]?$',
                    r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})',
                    r'^([A-Z0-9\s\-\'\.]+)\s+(\d+\.\d{2})'
                ],
                'header_keywords': ['FEARLESS', 'FLYER', 'NEIGHBORHOOD']
            },
            'KEY FOOD': {
                'patterns': [
                    r'KEY\s*FOOD',
                    r'KEYFOOD',
                    r'KEY-FOOD',
                    r'KEY\s*FOOD\s+#\d+',
                    r'KEY\s*FOOD\s+MARKETPLACE',
                    r'KEY\s*FOOD\s+FRESH',
                    r'KEY\s*FOOD\s+[A-Z]+',  # Location names
                    r'KEYFOOD\s+EXPRESS'
                ],
                'threshold': 0.75,
                'item_patterns': [
                    r'^(.*?)\s+(\d+\.\d{2})',
                    r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})',
                    r'^([A-Z0-9\s\-\'\.]+)\s+(\d+\.\d{2})'
                ],
                'header_keywords': ['SUPERMARKET', 'MARKETPLACE', 'FRESH']
            }
        }
        
        # Add common store chains
        self.store_patterns.update({
            'WHOLE FOODS': {
                'patterns': [
                    r'WHOLE\s*FOODS\s*MARKET',
                    r'WFM',
                    r'WHOLE\s*FOODS\s*#\d+',
                    r'WF\s*MARKET'
                ],
                'threshold': 0.75,
                'item_patterns': [
                    r'^(.*?)\s+(\d+\.\d{2})',
                    r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})'
                ],
                'header_keywords': ['MARKET', 'ORGANIC', 'NATURAL']
            },
            'TARGET': {
                'patterns': [
                    r'TARGET',
                    r'TARGET\s*STORE',
                    r'TARGET\s*#\d+',
                    r'TARGET\s*T-\d+'
                ],
                'threshold': 0.75,
                'item_patterns': [
                    r'^(.*?)\s+(\d+\.\d{2})',
                    r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})'
                ],
                'header_keywords': ['EXPECT', 'MORE', 'PAY', 'LESS']
            }
        })
        
        self.validation_notes = []
        self.requires_review = False
        
    def _fuzzy_match_store(self, text: str, store_name: str, threshold: float) -> bool:
        """Fuzzy match store name in text with improved accuracy."""
        # Get first 8 lines of text for header matching (increased from 5)
        header_lines = text.split('\n')[:8]
        header_text = ' '.join(header_lines).upper()
        
        # Try exact pattern matching first
        store_info = self.store_patterns.get(store_name, {})
        patterns = store_info.get('patterns', [])
        
        # Check for exact pattern matches
        for pattern in patterns:
            if re.search(pattern, header_text, re.IGNORECASE):
                logger.debug(f"Exact pattern match found for {store_name}: {pattern}")
                return True
        
        # Check for header keywords
        keywords = store_info.get('header_keywords', [])
        keyword_matches = sum(1 for kw in keywords if kw in header_text)
        if keyword_matches >= 2:  # At least 2 keywords should match
            logger.debug(f"Multiple keyword matches found for {store_name}")
            return True
        
        # Try fuzzy matching if exact match fails
        # Clean up text for better matching
        clean_header = re.sub(r'[^\w\s]', '', header_text)
        clean_store = re.sub(r'[^\w\s]', '', store_name)
        
        # Try matching against each line individually
        for line in header_lines:
            clean_line = re.sub(r'[^\w\s]', '', line.upper())
            matcher = SequenceMatcher(None, clean_store, clean_line)
            ratio = matcher.ratio()
            
            if ratio > threshold:
                logger.debug(f"Fuzzy match found for {store_name} with ratio {ratio:.2f}")
                return True
        
        # Try matching against concatenated header
        matcher = SequenceMatcher(None, clean_store, clean_header)
        ratio = matcher.ratio()
        
        if ratio > threshold:
            logger.debug(f"Fuzzy match found in header for {store_name} with ratio {ratio:.2f}")
            return True
            
        return False
        
    def _extract_store_info(self, text: str) -> Optional[str]:
        """Extract store name from receipt text with improved accuracy."""
        try:
            best_match = None
            best_ratio = 0.0
            
            # Try pattern matching for each store
            for store_name, store_info in self.store_patterns.items():
                threshold = store_info['threshold']
                
                if self._fuzzy_match_store(text, store_name, threshold):
                    # For exact matches, return immediately
                    if any(re.search(pattern, text[:200], re.IGNORECASE) for pattern in store_info['patterns']):
                        logger.debug(f"Found exact match for store: {store_name}")
                        return store_name
                    
                    # For fuzzy matches, keep track of the best match
                    clean_text = re.sub(r'[^\w\s]', '', text[:200].upper())
                    clean_store = re.sub(r'[^\w\s]', '', store_name.upper())
                    matcher = SequenceMatcher(None, clean_store, clean_text)
                    ratio = matcher.ratio()
                    
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = store_name
            
            if best_match:
                logger.debug(f"Best matching store: {best_match} with confidence {best_ratio:.2f}")
                if best_ratio < 0.6:  # Very low confidence
                    self.requires_review = True
                    self.validation_notes.append(f"Low confidence store match: {best_match} ({best_ratio:.2f})")
                return best_match
            
            logger.debug("No store pattern matched in text")
            self.requires_review = True
            self.validation_notes.append("No store name detected")
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting store info: {str(e)}")
            self.requires_review = True
            self.validation_notes.append(f"Error in store detection: {str(e)}")
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
            
    def _normalize_price(self, price_str: str) -> Optional[float]:
        """Normalize price string to float, handling common OCR errors."""
        try:
            # Remove any non-price characters
            price_str = re.sub(r'[^\d.]', '', price_str)
            
            # Handle cases where decimal point is missing
            if '.' not in price_str and len(price_str) > 2:
                price_str = price_str[:-2] + '.' + price_str[-2:]
                
            price = float(price_str)
            # Round to 2 decimal places
            return round(price, 2)
        except (ValueError, TypeError):
            return None

    def _clean_item_name(self, name: str) -> str:
        """Clean item name by removing special characters and normalizing whitespace."""
        # Remove special characters but keep basic punctuation
        name = re.sub(r'[^\w\s\-\',.]', '', name)
        # Normalize whitespace
        name = ' '.join(name.split())
        return name.strip()

    def _is_duplicate_item(self, item1: Dict[str, Any], item2: Dict[str, Any], threshold: float = 0.9) -> bool:
        """Check if two items are duplicates using fuzzy matching."""
        name1 = self._clean_item_name(item1['name'].lower())
        name2 = self._clean_item_name(item2['name'].lower())
        
        # Check for exact price match first
        price_match = abs(item1['price'] - item2['price']) < 0.01
        
        # If prices match, check name similarity
        if price_match:
            matcher = SequenceMatcher(None, name1, name2)
            return matcher.ratio() > threshold
            
        return False

    def _extract_items(self, text: str, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract items from receipt text with improved duplicate handling and store-specific patterns."""
        items = []
        try:
            lines = text.split('\n')
            continuation_buffer = []
            seen_items = defaultdict(int)  # Track duplicates
            
            # Get store-specific patterns if available
            store_info = self.store_patterns.get(store_name, {})
            store_patterns = store_info.get('item_patterns', [])
            
            # Default patterns if no store-specific ones exist
            default_patterns = [
                r'^([\d.]+)\s*(?:LB|lb|Lb)\s+@\s+(\d+\.\d{2})/(?:LB|lb|Lb)\s+(.*?)\s+(\d+\.\d{2})',
                r'^(\d+)\s+@\s+(\d+\.\d{2})\s+(.*?)\s+(\d+\.\d{2})',
                r'^\d{3,4}\s+(.*?)\s+(\d+\.\d{2})',
                r'^(.*?)\s+(\d+\.\d{2})',
            ]
            
            all_patterns = store_patterns + default_patterns
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                    
                # Skip likely header or footer lines
                if any(skip in line.upper() for skip in ['TOTAL', 'SUBTOTAL', 'TAX', 'BALANCE', 'PAYMENT']):
                    continue
                    
                # Try all patterns
                item_found = False
                for pattern in all_patterns:
                    match = re.search(pattern, line)
                    if match:
                        # Extract item details based on pattern
                        groups = match.groups()
                        if len(groups) == 2:  # Simple item with price
                            name, price = groups
                            quantity = 1
                        elif len(groups) == 4:  # Quantity-based item
                            quantity = float(groups[0])
                            name = groups[2]
                            price = groups[3]
                        else:
                            continue
                            
                        # Clean and normalize values
                        name = self._clean_item_name(name)
                        price = self._normalize_price(price)
                        
                        if name and price:
                            item = {
                                'name': name,
                                'price': price,
                                'quantity': quantity,
                                'line_number': i + 1,
                                'confidence': 1.0  # Default confidence
                            }
                            
                            # Check for duplicates
                            is_duplicate = False
                            for existing_item in items:
                                if self._is_duplicate_item(item, existing_item):
                                    existing_item['duplicate_count'] = existing_item.get('duplicate_count', 1) + 1
                                    is_duplicate = True
                                    break
                                    
                            if not is_duplicate:
                                item['duplicate_count'] = 1
                                items.append(item)
                                
                            item_found = True
                            break
                            
                # Handle potential continuation lines
                if not item_found and continuation_buffer:
                    # Try to merge with previous line
                    merged_line = ' '.join(continuation_buffer + [line])
                    continuation_buffer = []
                    
                    # Try parsing merged line
                    for pattern in all_patterns:
                        match = re.search(pattern, merged_line)
                        if match:
                            # Process merged line as a new item
                            name = match.group(1)
                            price = self._normalize_price(match.group(2))
                            
                            if name and price:
                                item = {
                                    'name': self._clean_item_name(name),
                                    'price': price,
                                    'quantity': 1,
                                    'line_number': i,
                                    'confidence': 0.8  # Lower confidence for merged lines
                                }
                                items.append(item)
                            break
                elif not item_found:
                    # Add to continuation buffer if line might be incomplete
                    continuation_buffer.append(line)
                    
            return items
            
        except Exception as e:
            logger.error(f"Error extracting items: {str(e)}")
            return []
            
    def _extract_total(self, text: str) -> Tuple[Optional[float], float]:
        """Extract total amount from receipt text with improved accuracy and validation."""
        try:
            # Look for total amount in common formats
            total_patterns = [
                # Standard total patterns
                r'TOTAL\s*[:\$]?\s*(\d+\.\d{2})',
                r'BALANCE\s*[:\$]?\s*(\d+\.\d{2})',
                r'AMOUNT\s*[:\$]?\s*(\d+\.\d{2})',
                # Multi-line total patterns
                r'TOTAL\s*\n\s*[:\$]?\s*(\d+\.\d{2})',
                # Patterns with currency symbols
                r'TOTAL\s*\$\s*(\d+\.\d{2})',
                # Patterns with "DUE"
                r'(?:TOTAL|BALANCE|AMOUNT)\s*DUE\s*[:\$]?\s*(\d+\.\d{2})',
                # Patterns with decimals
                r'(?:TOTAL|BALANCE|AMOUNT)\s*[:\$]?\s*(\d{1,10}\.\d{2})'
            ]
            
            # Find all potential totals
            potential_totals = []
            for pattern in total_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    try:
                        amount = self._normalize_price(match.group(1))
                        if amount is not None:
                            potential_totals.append({
                                'amount': amount,
                                'position': match.start(),  # Track position for priority
                                'confidence': 1.0  # Base confidence
                            })
                    except (ValueError, IndexError):
                        continue
            
            # Sort potential totals by position (later in receipt = higher priority)
            potential_totals.sort(key=lambda x: x['position'])
            
            # Calculate sum of items for validation
            items_total = 0.0
            tax_amount = self._extract_tax(text) or 0.0
            
            # If we have items, calculate their total
            if hasattr(self, '_last_extracted_items') and self._last_extracted_items:
                items_total = sum(item['price'] * item.get('quantity', 1) for item in self._last_extracted_items)
                items_total = round(items_total, 2)
            
            # Validate potential totals against items total + tax
            expected_total = items_total + tax_amount
            best_total = None
            best_confidence = 0.0
            
            for total in potential_totals:
                confidence = total['confidence']
                amount = total['amount']
                
                # Adjust confidence based on various factors
                if abs(amount - expected_total) < 0.01:
                    confidence *= 1.2  # Boost confidence if matches expected total
                elif abs(amount - expected_total) < 1.00:
                    confidence *= 0.9  # Slightly reduce confidence if close
                else:
                    confidence *= 0.7  # Significantly reduce confidence if far off
                    
                # Boost confidence for totals found near the end of the receipt
                relative_position = total['position'] / len(text)
                if relative_position > 0.7:  # In the last 30% of the receipt
                    confidence *= 1.1
                    
                # Update best total if this one has higher confidence
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_total = amount
            
            # If no total found or confidence too low, use calculated total
            if best_total is None or best_confidence < 0.5:
                logger.debug("Using calculated total from items")
                return (expected_total, 0.8)  # Return calculated total with medium confidence
                
            return (best_total, best_confidence)
            
        except Exception as e:
            logger.error(f"Error extracting total: {str(e)}")
            return (None, 0.0)
            
    def analyze_receipt(self, text: str, image_path: Optional[str] = None, store_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze receipt text and extract structured information.
        
        Args:
            text: Receipt text to analyze
            image_path: Optional path to receipt image
            store_hint: Optional store name hint
            
        Returns:
            Dictionary containing extracted receipt data
        """
        logger.info("Starting receipt analysis...")
        
        try:
            # Initialize result with safe defaults
            result = {
                'store_name': store_hint or 'Unknown Store',
                'date': None,
                'time': None,
                'items': [],
                'subtotal': 0.0,
                'tax': 0.0,
                'total': 0.0,
                'currency': 'USD',
                'confidence': 0.0,
                'requires_review': False,
                'validation_notes': [],
                'debug_info': {
                    'ocr_engine': None,
                    'processing_time': None,
                    'text_length': len(text),
                    'store_match_confidence': 0.0
                }
            }
            
            start_time = time.time()
            
            # Extract store info if not provided
            if not store_hint:
                store_name = self._extract_store_info(text)
                if store_name:
                    result['store_name'] = store_name
                    result['debug_info']['store_match_confidence'] = 1.0
                    logger.info(f"Detected store: {store_name}")
                else:
                    result['validation_notes'].append("Store name not detected")
                    result['requires_review'] = True
            
            # Extract date/time
            datetime_info = self._extract_date_time(text)
            result.update(datetime_info)
            if not result['date']:
                result['validation_notes'].append("Date not detected")
                result['requires_review'] = True
            
            # Extract currency
            result['currency'] = self._extract_currency(text)
            
            # Extract items with store-specific patterns
            items = self._extract_items(text, result['store_name'])
            if items:
                result['items'] = items
                logger.info(f"Extracted {len(items)} items")
            else:
                result['validation_notes'].append("No items detected")
                result['requires_review'] = True
                # Add a fallback item
                result['items'] = [{
                    'name': 'Unparsed Item',
                    'price': 0.0,
                    'quantity': 1,
                    'confidence': 0.0
                }]
            
            # Extract totals
            totals = self._extract_totals(text)
            if totals['subtotal'] is not None:
                result['subtotal'] = totals['subtotal']
            if totals['tax'] is not None:
                result['tax'] = totals['tax']
            if totals['total'] is not None:
                result['total'] = totals['total']
            
            # Validate totals
            if result['total'] == 0.0:
                # Try to calculate total from items
                items_total = sum(item['price'] * item.get('quantity', 1) for item in result['items'])
                if items_total > 0:
                    result['total'] = round(items_total, 2)
                    result['validation_notes'].append("Total calculated from items")
                    result['requires_review'] = True
            
            # Calculate confidence score
            result['confidence'] = self._calculate_confidence(
                result['items'],
                {'subtotal': result['subtotal'], 'tax': result['tax'], 'total': result['total']},
                bool(store_name)
            )
            
            # Add validation notes for low confidence
            if result['confidence'] < 0.7:
                result['validation_notes'].append(f"Low confidence score: {result['confidence']:.2f}")
                result['requires_review'] = True
            
            # Update debug info
            result['debug_info']['processing_time'] = time.time() - start_time
            result['debug_info']['ocr_engine'] = self.google_ocr.__class__.__name__ if self.google_ocr else 'TesseractOCR'
            
            # Save debug info if enabled
            if self.debug_mode and image_path:
                self._save_debug_info(result, image_path)
            
            logger.info(f"Receipt analysis completed with confidence: {result['confidence']:.2f}")
            if result['requires_review']:
                logger.warning(f"Receipt requires review: {', '.join(result['validation_notes'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing receipt: {str(e)}\n{traceback.format_exc()}")
            # Return safe defaults on error
            return {
                'store_name': store_hint or 'Unknown Store',
                'date': None,
                'time': None,
                'items': [{
                    'name': 'Error Processing Receipt',
                    'price': 0.0,
                    'quantity': 1,
                    'confidence': 0.0
                }],
                'subtotal': 0.0,
                'tax': 0.0,
                'total': 0.0,
                'currency': 'USD',
                'confidence': 0.0,
                'requires_review': True,
                'validation_notes': [f"Error during analysis: {str(e)}"],
                'debug_info': {
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
            }
            
    def _extract_currency(self, text: str) -> str:
        """Extract currency from receipt text."""
        try:
            # Look for currency symbols
            if '$' in text:
                return 'USD'
            elif '£' in text:
                return 'GBP'
            elif '€' in text:
                return 'EUR'
            
            return 'USD'  # Default to USD
            
        except Exception as e:
            logger.error(f"Error extracting currency: {str(e)}")
            return 'USD'
            
    def _extract_totals(self, text: str) -> Dict[str, Optional[float]]:
        """Extract total amounts from receipt text."""
        try:
            totals = {
                'subtotal': None,
                'tax': None,
                'total': None
            }
            
            # Look for totals from bottom up
            lines = text.split('\n')[::-1]
            
            # Define patterns with variations
            total_patterns = [
                (r'(?i)total\s*:?\s*\$?\s*(\d+\.\d{2})', 'total'),
                (r'(?i)(?:sub[\s-]*total|merchandise)\s*:?\s*\$?\s*(\d+\.\d{2})', 'subtotal'),
                (r'(?i)tax\s*:?\s*\$?\s*(\d+\.\d{2})', 'tax')
            ]
            
            for line in lines:
                for pattern, total_type in total_patterns:
                    match = re.search(pattern, line)
                    if match and totals[total_type] is None:
                        try:
                            amount = float(match.group(1))
                            totals[total_type] = amount
                        except ValueError:
                            continue
            
            # Validate and fix totals
            if totals['subtotal'] is not None and totals['tax'] is not None:
                expected_total = round(totals['subtotal'] + totals['tax'], 2)
                if totals['total'] is None:
                    totals['total'] = expected_total
                elif abs(totals['total'] - expected_total) > 0.01:
                    logger.warning(f"Total mismatch: {totals['total']} != {expected_total}")
                    self.validation_notes.append("Total amount mismatch")
                    self.requires_review = True
            
            return totals
            
        except Exception as e:
            logger.error(f"Error extracting totals: {str(e)}")
            return {'subtotal': None, 'tax': None, 'total': None}
            
    def _calculate_confidence(self, items: List[Dict], totals: Dict, has_store: bool) -> float:
        """Calculate overall confidence score."""
        try:
            weights = {
                'store': 0.2,
                'items': 0.4,
                'totals': 0.4
            }
            
            scores = {
                'store': 1.0 if has_store else 0.5,
                'items': 0.0,
                'totals': 0.0
            }
            
            # Calculate items score
            if items:
                item_confidences = [item.get('confidence', 0) for item in items]
                scores['items'] = sum(item_confidences) / len(item_confidences)
            
            # Calculate totals score
            if totals.get('total') is not None:
                scores['totals'] = 1.0
                if totals.get('subtotal') is not None and totals.get('tax') is not None:
                    expected_total = totals['subtotal'] + totals['tax']
                    if abs(expected_total - totals['total']) < 0.01:
                        scores['totals'] = 1.0
                    else:
                        scores['totals'] = 0.7
            
            # Calculate weighted average
            confidence = sum(weights[k] * scores[k] for k in weights)
            
            return round(confidence, 2)
            
        except Exception as e:
            logger.error(f"Error calculating confidence: {str(e)}")
            return 0.0
            
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