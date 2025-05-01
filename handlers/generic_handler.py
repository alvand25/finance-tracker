import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from handlers.base_handler import BaseReceiptHandler

logger = logging.getLogger(__name__)

class GenericHandler(BaseReceiptHandler):
    """
    Generic receipt handler for processing receipts with unknown vendor formats.
    
    This handler uses robust pattern matching to extract items and totals from
    receipts with arbitrary formats, serving as a fallback when specialized
    handlers cannot be used.
    """
    
    def __init__(self):
        """Initialize the generic handler."""
        super().__init__()
        logger.debug("Generic handler initialized")
        
    def extract_items(self, ocr_text: str, image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract line items from the receipt OCR text.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image
            
        Returns:
            List of item dictionaries
        """
        logger.info("Extracting items using generic handler")
        
        if not ocr_text:
            logger.warning("Empty OCR text provided")
            return []
            
        # Split into lines
        lines = ocr_text.strip().split('\n')
        logger.debug(f"[GenericHandler] Processing {len(lines)} lines of OCR text")
        
        # Patterns for matching items
        item_patterns = [
            # Description followed by price (no quantity)
            r'([\w\s\'\"\&\-\,\.\(\)\/]+?)\s+(\d+[\.,]\d{2})$',
            
            # Description with quantity and price
            r'([\w\s\'\"\&\-\,\.\(\)\/]+?)\s+(\d+)\s+(?:@\s+[\$\£\€]?\s*[\d\,\.]+)?\s+([\$\£\€]?\s*\d+[\.,]\d{2})$',
            
            # Description with price and optional currency symbol
            r'([\w\s\'\"\&\-\,\.\(\)\/]+?)\s+([\$\£\€]?\s*\d+[\.,]\d{2})$',
            
            # Description followed by quantity and price
            r'([\w\s\'\"\&\-\,\.\(\)\/]+?)\s+(\d+)\s*[xX]?\s*([\$\£\€]?\s*\d+[\.,]\d{2})$'
        ]
        
        # Keywords to skip
        skip_keywords = [
            'total', 'subtotal', 'tax', 'sum', 'amount', 'balance', 'credit',
            'debit', 'change', 'cash', 'payment', 'paid', 'discount', 'due',
            'account', 'customer', 'store', 'receipt', 'invoice', 'date',
            'welcome', 'thank you', 'thanks', 'phone', 'tel', 'fax', 'address',
            'website', 'url', 'http', 'www', 'email', 'e-mail'
        ]
        
        # Extract items
        items = []
        seen_descriptions = set()
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            
            # Skip short lines or likely non-item lines
            if len(line) < 5:
                logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping short line: '{line}'")
                continue
                
            if any(keyword in line.lower() for keyword in skip_keywords):
                logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping line with skip keyword: '{line}'")
                continue
                
            logger.debug(f"[GenericHandler] Line {line_num+1}: Checking line: '{line}'")
            
            # Try each pattern
            pattern_matched = False
            for pattern_idx, pattern in enumerate(item_patterns):
                match = re.search(pattern, line)
                if match:
                    pattern_matched = True
                    logger.debug(f"[GenericHandler] Line {line_num+1}: Matched pattern {pattern_idx+1}")
                    groups = match.groups()
                    
                    # Extract description and price
                    description = groups[0].strip()
                    
                    # Skip if description is short or contains skip keywords
                    if len(description) < 3:
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping item with short description: '{description}'")
                        continue
                        
                    if any(keyword in description.lower() for keyword in skip_keywords):
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping item with keyword in description: '{description}'")
                        continue
                        
                    # Skip if it's likely a header
                    if re.search(r'^(item|qty|description|price|amount)$', description.lower()):
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping header line: '{description}'")
                        continue
                    
                    # Extract price from the last group
                    price_str = groups[-1].strip()
                    # Remove currency symbols and thousand separators
                    price_str = re.sub(r'[^\d\.,]', '', price_str)
                    # Replace comma with dot if used as decimal separator
                    if ',' in price_str and '.' not in price_str:
                        price_str = price_str.replace(',', '.')
                    
                    try:
                        price = float(price_str)
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Extracted price: {price}")
                    except ValueError:
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Failed to parse price: '{price_str}'")
                        continue
                    
                    # Extract quantity if available (groups length varies by pattern)
                    quantity = 1
                    if len(groups) >= 3 and groups[1].isdigit():
                        quantity = int(groups[1])
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Extracted quantity: {quantity}")
                    
                    # Avoid duplicates (normalized by lowercase description)
                    normalized_desc = description.lower()
                    if normalized_desc in seen_descriptions:
                        logger.debug(f"[GenericHandler] Line {line_num+1}: Skipping duplicate item: '{description}'")
                        continue
                    seen_descriptions.add(normalized_desc)
                    
                    # Add the item
                    item = {
                        'description': description,
                        'price': price,
                        'quantity': quantity,
                        'confidence': 0.7  # Medium confidence for generic extraction
                    }
                    
                    logger.debug(f"[GenericHandler] Line {line_num+1}: Added item: {item}")
                    items.append(item)
                    break  # Stop pattern matching for this line once we have a match
            
            if not pattern_matched:
                logger.debug(f"[GenericHandler] Line {line_num+1}: No pattern matched for line: '{line}'")
        
        logger.info(f"[GenericHandler] Extracted {len(items)} items with generic handler")
        
        # Add fallback log if no items were found
        if len(items) == 0:
            logger.warning("[GenericHandler] No items were extracted. Checking for potential price-looking lines...")
            price_looking_lines = []
            for line_num, line in enumerate(lines):
                if re.search(r'\$?\d+\.\d{2}', line) or re.search(r'\d+\.\d{2}$', line) or re.search(r'\d+\,\d{2}$', line):
                    logger.debug(f"[GenericHandler] Potential price line: '{line}'")
                    price_looking_lines.append(line)
            
            if price_looking_lines:
                logger.debug(f"[GenericHandler] Found {len(price_looking_lines)} lines that appear to contain prices but didn't match patterns")
                logger.debug(f"[GenericHandler] Sample price-looking lines: {price_looking_lines[:5]}")
            else:
                logger.debug("[GenericHandler] No price-looking lines were found in the OCR text")
                
        return items
    
    def extract_totals(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract total amounts from the receipt OCR text.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image
            
        Returns:
            Dictionary with totals information
        """
        logger.info("Extracting totals using generic handler")
        
        if not ocr_text:
            logger.warning("Empty OCR text provided")
            return {}
            
        # Initialize results
        results = {
            'subtotal': None,
            'tax': None,
            'total': None,
            'confidence': 0.6  # Base confidence
        }
        
        # Split into lines
        lines = ocr_text.strip().split('\n')
        logger.debug(f"[GenericHandler] Analyzing {len(lines)} lines for totals")
        
        # Patterns for matching totals
        subtotal_patterns = [
            r'sub[\s\-]*total\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'subtotal\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'sub\s*total\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'goods\s*(?:[\$\£\€]?\s*)([\d\,\.]+)'
        ]
        
        tax_patterns = [
            r'tax\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'vat\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'gst\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'hst\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'sales\s*tax\s*(?:[\$\£\€]?\s*)([\d\,\.]+)'
        ]
        
        total_patterns = [
            r'total\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'amount\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'due\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'balance\s*(?:[\$\£\€]?\s*)([\d\,\.]+)',
            r'sum\s*(?:[\$\£\€]?\s*)([\d\,\.]+)'
        ]
        
        # Helper function to extract value using patterns
        def extract_value(patterns, text_lines, pattern_name):
            logger.debug(f"[GenericHandler] Searching for {pattern_name} using {len(patterns)} patterns")
            for line_num, line in enumerate(text_lines):
                line_lower = line.lower()
                logger.debug(f"[GenericHandler] Checking {pattern_name} in line {line_num+1}: '{line}'")
                for pattern_idx, pattern in enumerate(patterns):
                    match = re.search(pattern, line_lower)
                    if match:
                        logger.debug(f"[GenericHandler] Found {pattern_name} match with pattern {pattern_idx+1}: '{pattern}'")
                        try:
                            value_str = match.group(1).strip()
                            logger.debug(f"[GenericHandler] Extracted {pattern_name} raw value: '{value_str}'")
                            
                            # Remove currency symbols and thousand separators
                            value_str = re.sub(r'[^\d\.,]', '', value_str)
                            # Replace comma with dot if used as decimal separator
                            if ',' in value_str and '.' not in value_str:
                                value_str = value_str.replace(',', '.')
                                
                            value = float(value_str)
                            logger.debug(f"[GenericHandler] Parsed {pattern_name} value: {value}")
                            return value
                        except (ValueError, IndexError) as e:
                            logger.debug(f"[GenericHandler] Failed to parse {pattern_name} value: {str(e)}")
                            continue
            logger.debug(f"[GenericHandler] No {pattern_name} found")
            return None
        
        # Extract totals
        results['subtotal'] = extract_value(subtotal_patterns, lines, "subtotal")
        results['tax'] = extract_value(tax_patterns, lines, "tax")
        results['total'] = extract_value(total_patterns, lines, "total")
        
        # Calculate missing values if possible
        if results['subtotal'] and results['tax'] and not results['total']:
            results['total'] = round(results['subtotal'] + results['tax'], 2)
            logger.debug(f"[GenericHandler] Calculated total: {results['total']}")
        elif results['subtotal'] and results['total'] and not results['tax']:
            results['tax'] = round(results['total'] - results['subtotal'], 2)
            # Ensure tax is not negative or unreasonably large
            if results['tax'] < 0 or results['tax'] > results['total'] * 0.25:
                logger.debug(f"[GenericHandler] Calculated tax {results['tax']} seems invalid, discarding")
                results['tax'] = None
            else:
                logger.debug(f"[GenericHandler] Calculated tax: {results['tax']}")
        elif results['tax'] and results['total'] and not results['subtotal']:
            results['subtotal'] = round(results['total'] - results['tax'], 2)
            # Ensure subtotal is positive
            if results['subtotal'] <= 0:
                logger.debug(f"[GenericHandler] Calculated subtotal {results['subtotal']} is non-positive, discarding")
                results['subtotal'] = None
            else:
                logger.debug(f"[GenericHandler] Calculated subtotal: {results['subtotal']}")
        
        # Add fallback for total detection
        if results['total'] is None:
            logger.debug("[GenericHandler] No total found, looking for lines with currency symbols or decimal values")
            potential_totals = []
            
            for line_num, line in enumerate(lines):
                # Look for currency symbols or decimal values in format X.XX
                if re.search(r'[$€£]\s*\d+\.\d{2}', line) or re.search(r'\d+\.\d{2}$', line):
                    logger.debug(f"[GenericHandler] Potential total line found: '{line}'")
                    potential_totals.append(line)
            
            if potential_totals:
                logger.debug(f"[GenericHandler] Found {len(potential_totals)} lines with potential total values")
                logger.debug(f"[GenericHandler] Sample potential total lines: {potential_totals[:3]}")
        
        # Extract date
        results['date'] = self._extract_date(ocr_text)
        
        # Extract currency
        results['currency'] = self._extract_currency(ocr_text)
        
        # Extract payment method
        results['payment_method'] = self._extract_payment_method(ocr_text)
        
        # Update confidence based on what we found
        confidence_factors = {
            'subtotal': 0.2 if results['subtotal'] else 0.0,
            'tax': 0.2 if results['tax'] else 0.0,
            'total': 0.3 if results['total'] else 0.0,
            'date': 0.1 if results['date'] else 0.0,
            'payment_method': 0.1 if results['payment_method'] else 0.0,
            'base': 0.1
        }
        
        # Calculate weighted confidence
        confidence_sum = sum(confidence_factors.values())
        results['confidence'] = min(confidence_sum, 0.9)  # Cap at 0.9 for generic handler
        
        logger.info(f"[GenericHandler] Extracted totals with confidence {results['confidence']:.2f}: " +
                  f"subtotal={results['subtotal']}, tax={results['tax']}, total={results['total']}")
        
        return results
    
    def extract_metadata(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract additional metadata from the receipt.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image
            
        Returns:
            Dictionary with metadata
        """
        logger.info("Extracting metadata using generic handler")
        
        if not ocr_text:
            logger.warning("Empty OCR text provided")
            return {}
            
        metadata = {
            'store_name': None,
            'date': None,
            'payment_method': None,
            'currency': 'USD',  # Default currency
            'confidence': 0.5   # Base confidence
        }
        
        # Extract date
        metadata['date'] = self._extract_date(ocr_text)
        
        # Extract currency
        metadata['currency'] = self._extract_currency(ocr_text)
        
        # Extract payment method
        metadata['payment_method'] = self._extract_payment_method(ocr_text)
        
        # Extract store name (first non-empty line is often the store name)
        lines = ocr_text.strip().split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and len(line) > 2 and len(line) < 30:
                # Skip lines that look like dates or addresses
                if not re.search(r'\d{2}[/\.-]\d{2}[/\.-]\d{2,4}', line) and \
                   not re.search(r'\d+ .+ st|ave|rd|blvd', line.lower()):
                    metadata['store_name'] = line
                    break
        
        # Update confidence based on what we found
        confidence_factors = {
            'store_name': 0.2 if metadata['store_name'] else 0.0,
            'date': 0.2 if metadata['date'] else 0.0,
            'payment_method': 0.2 if metadata['payment_method'] else 0.0,
            'base': 0.1
        }
        
        # Calculate confidence
        metadata['confidence'] = sum(confidence_factors.values())
        
        logger.info(f"Extracted metadata with confidence {metadata['confidence']:.2f}")
        return metadata
    
    def _extract_date(self, ocr_text: str) -> Optional[datetime]:
        """Extract date from receipt text."""
        # Common date patterns (MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD, etc.)
        date_patterns = [
            r'(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{2,4})',  # MM/DD/YYYY or DD/MM/YYYY
            r'(\d{4})[/\.-](\d{1,2})[/\.-](\d{1,2})',    # YYYY-MM-DD
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})',  # Month DD, YYYY
            r'(\d{1,2})(?:st|nd|rd|th)? (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})'     # DD Month YYYY
        ]
        
        for line in ocr_text.strip().split('\n'):
            line_lower = line.lower()
            
            # Check for explicit date indicators
            if re.search(r'\b(?:date|time|receipt|transaction)\b', line_lower):
                for pattern in date_patterns:
                    match = re.search(pattern, line)
                    if match:
                        try:
                            # Extract date components
                            if len(match.groups()) == 3:  # Numeric date format
                                if match.group(1).startswith('20'):  # YYYY-MM-DD
                                    year = int(match.group(1))
                                    month = int(match.group(2))
                                    day = int(match.group(3))
                                else:  # MM/DD/YYYY or DD/MM/YYYY
                                    # Assume MM/DD/YYYY for simplicity (would need more context to disambiguate)
                                    month = int(match.group(1))
                                    day = int(match.group(2))
                                    year = int(match.group(3))
                                    if year < 100:
                                        year += 2000 if year < 50 else 1900
                                
                                # Validate date components
                                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                                    return datetime(year, month, day)
                        except (ValueError, IndexError):
                            continue
        
        # If no date with indicator, try any date in the text
        for line in ocr_text.strip().split('\n'):
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match:
                    try:
                        # Extract date components
                        if len(match.groups()) == 3:  # Numeric date format
                            if match.group(1).startswith('20'):  # YYYY-MM-DD
                                year = int(match.group(1))
                                month = int(match.group(2))
                                day = int(match.group(3))
                            else:  # MM/DD/YYYY or DD/MM/YYYY
                                month = int(match.group(1))
                                day = int(match.group(2))
                                year = int(match.group(3))
                                if year < 100:
                                    year += 2000 if year < 50 else 1900
                            
                            # Validate date components
                            if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                                return datetime(year, month, day)
                    except (ValueError, IndexError):
                        continue
        
        return None
    
    def _extract_currency(self, ocr_text: str) -> str:
        """Extract currency from receipt text."""
        # Look for currency symbols
        if '€' in ocr_text or 'EUR' in ocr_text:
            return 'EUR'
        elif '£' in ocr_text or 'GBP' in ocr_text:
            return 'GBP'
        elif '¥' in ocr_text or 'JPY' in ocr_text:
            return 'JPY'
        
        # Check for Canadian or Australian dollar indicators
        if re.search(r'\bCAD\b', ocr_text) or re.search(r'\bCanad(a|ian)\b', ocr_text, re.IGNORECASE):
            return 'CAD'
        elif re.search(r'\bAUD\b', ocr_text) or re.search(r'\bAustralia\b', ocr_text, re.IGNORECASE):
            return 'AUD'
        
        # Default to USD for $ symbol or if nothing specific found
        return 'USD'
    
    def _extract_payment_method(self, ocr_text: str) -> Optional[str]:
        """Extract payment method from receipt text."""
        ocr_lower = ocr_text.lower()
        
        # Common payment method indicators
        if re.search(r'\b(?:credit|visa|mastercard|amex|american express)\b', ocr_lower):
            return 'credit'
        elif re.search(r'\b(?:debit|check card)\b', ocr_lower):
            return 'debit'
        elif re.search(r'\b(?:cash|money)\b', ocr_lower) and re.search(r'\bchange\b', ocr_lower):
            return 'cash'
        elif re.search(r'\b(?:paypal|venmo|apple pay|google pay)\b', ocr_lower):
            return 'electronic'
        elif re.search(r'\b(?:check|cheque)\b', ocr_lower):
            return 'check'
        elif re.search(r'\b(?:gift card|store credit)\b', ocr_lower):
            return 'gift_card'
        
        # Look for specific credit card branding
        for line in ocr_lower.strip().split('\n'):
            if re.search(r'\b(?:approved|auth|code|transaction)\b', line):
                if re.search(r'\b(?:visa|mastercard|mc|amex|discover)\b', line):
                    return 'credit'
        
        return None 