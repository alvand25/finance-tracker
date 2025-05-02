import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from handlers.base_handler import BaseReceiptHandler

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
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Generic handler initialized")
        
    def extract_items(self, text: str, image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract item descriptions and prices from receipt text.
        
        Args:
            text (str): The OCR text from the receipt
            image_path (Optional[str]): Path to receipt image for debugging
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries containing:
                - description: str (Item description)
                - price: float (Item price)
                - quantity: float (Optional quantity)
                - unit_price: float (Optional price per unit)
        """
        items = []
        seen_items = set()  # Track seen items to avoid duplicates
        
        # Skip lines containing these keywords
        skip_keywords = [
            'total', 'subtotal', 'tax', 'balance', 'change', 'payment',
            'card', 'cash', 'credit', 'debit', 'mastercard', 'visa',
            'american express', 'discover', 'auth', 'approved', 'member',
            'transaction', 'store', 'tel', 'phone', 'date', 'time',
            'cashier', 'register', 'receipt', 'duplicate', 'copy',
            'thank you', 'thanks', 'welcome', 'wifi', 'rewards',
            'points', 'save', 'discount', 'coupon', 'void', 'refund',
            'return', 'exchange', 'website', 'survey', 'feedback',
            'promotion', 'promo', 'offer', 'deal', 'sale', 'special'
        ]
        
        # Price patterns
        price_patterns = [
            # Basic price pattern with description
            r'(?P<description>.*?)\s+(?P<price>\d+\.\d{2})\s*(?:F|T|N|$)',
            
            # Price per unit pattern
            r'(?P<quantity>\d*\.?\d+)\s*(?:lb|kg|oz|g|ea)\s*@\s*(?P<unit_price>\d+\.\d{2})\s*/(?:lb|kg|oz|g|ea).*?(?P<price>\d+\.\d{2})',
            
            # SKU/item number pattern
            r'(?P<sku>\d{4,})\s+(?P<description>[A-Za-z].*?)\s+(?P<price>\d+\.\d{2})',
            
            # Simple price pattern
            r'^\$?(?P<price>\d+\.\d{2})\s*(?:F|T|N|$)',
            
            # Price with quantity pattern
            r'(?P<quantity>\d+)\s*@\s*\$?(?P<unit_price>\d+\.\d{2}).*?(?P<price>\d+\.\d{2})',
            
            # Trader Joe's style pattern
            r'(?P<description>[A-Z][A-Z0-9\s]+[A-Z0-9])\n\$(?P<price>\d+\.\d{2})',
            
            # Price with optional tax/discount indicator
            r'(?P<description>.*?)\s+\$(?P<price>\d+\.\d{2})\s*(?:F|T|N|$)',
        ]
        
        lines = text.split('\n')
        prev_line = ''
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Skip lines with common non-item keywords
            if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                continue
            
            # Try each pattern
            for pattern in price_patterns:
                match = re.search(pattern, line)
                if not match:
                    # For multi-line patterns, try with previous line
                    if prev_line:
                        match = re.search(pattern, prev_line + '\n' + line)
                
                if match:
                    item_dict = {}
                    
                    # Get price
                    try:
                        price = float(match.group('price'))
                        if price <= 0 or price > 10000:  # Skip invalid prices
                            continue
                        item_dict['price'] = price
                    except (ValueError, IndexError):
                        continue
                    
                    # Get description
                    try:
                        description = match.group('description')
                        if description:
                            # Clean up description
                            description = re.sub(r'\s+', ' ', description.strip())
                            description = re.sub(r'[^\w\s\-\.]', '', description)
                            if len(description) < 2:  # Skip very short descriptions
                                continue
                            item_dict['description'] = description
                        elif prev_line and not any(keyword.lower() in prev_line.lower() for keyword in skip_keywords):
                            # Use previous line as description if current line is just a price
                            description = re.sub(r'\s+', ' ', prev_line.strip())
                            description = re.sub(r'[^\w\s\-\.]', '', description)
                            if len(description) >= 2:
                                item_dict['description'] = description
                    except IndexError:
                        if prev_line and not any(keyword.lower() in prev_line.lower() for keyword in skip_keywords):
                            # Use previous line as description
                            description = re.sub(r'\s+', ' ', prev_line.strip())
                            description = re.sub(r'[^\w\s\-\.]', '', description)
                            if len(description) >= 2:
                                item_dict['description'] = description
                    
                    # Get quantity and unit price if available
                    try:
                        quantity = match.group('quantity')
                        if quantity:
                            item_dict['quantity'] = float(quantity)
                    except (IndexError, ValueError):
                        pass
                    
                    try:
                        unit_price = match.group('unit_price')
                        if unit_price:
                            item_dict['unit_price'] = float(unit_price)
                    except (IndexError, ValueError):
                        pass
                    
                    # Only add item if we have both price and description
                    if 'price' in item_dict and 'description' in item_dict:
                        item_key = f"{item_dict['description']}_{item_dict['price']}"
                        if item_key not in seen_items:
                            seen_items.add(item_key)
                            items.append(item_dict)
                            self.logger.debug(f"Extracted item: {item_dict}")
                    break
            
            prev_line = line
        
        self.logger.info(f"Extracted {len(items)} items")
        self._last_extracted_items = items
        return items
    
    def extract_totals(self, text: str, image_path: Optional[str] = None) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Extract subtotal, tax, and total from receipt text.
        
        Args:
            text: The OCR text from the receipt
            image_path: Optional path to receipt image for debugging
            
        Returns:
            Tuple of (subtotal, tax, total), each being a float or None if not found
        """
        # First pass - find discounts
        discounts = []
        discount_patterns = [
            r"You saved (?:[\$\s]*)(\d+\.\d{2})",
            r"Savings (?:[\$\s]*)(\d+\.\d{2})",
            r"Discount (?:[\$\s]*)(\d+\.\d{2})",
            r"Member savings (?:[\$\s]*)(\d+\.\d{2})",
            r"(?:[\$\s]*)(\d+\.\d{2}) off",
            r"Regular price (?:[\$\s]*)(\d+\.\d{2}).*?(?:[\$\s]*)(\d+\.\d{2})",
            r"Price reduction (?:[\$\s]*)(\d+\.\d{2})"
        ]
        
        seen_discounts = set()  # Track discounts to avoid duplicates
        for pattern in discount_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if "Regular price" in match.group(0):
                    # For "Regular price X.XX -> Y.XX" patterns, discount is the difference
                    regular_price = float(match.group(1))
                    sale_price = float(match.group(2))
                    discount = regular_price - sale_price
                else:
                    discount = float(match.group(1))
                    
                # Convert to string with 2 decimal places to avoid float comparison issues
                discount_str = f"{discount:.2f}"
                if discount_str not in seen_discounts:
                    seen_discounts.add(discount_str)
                    discounts.append(discount)
        
        total_discounts = sum(discounts)
        self.logger.debug(f"Found discounts: {discounts}, total={total_discounts}")
        
        # Calculate subtotal from items if available
        subtotal = None
        if hasattr(self, '_last_extracted_items') and self._last_extracted_items:
            try:
                subtotal = sum(item['price'] for item in self._last_extracted_items)
                self.logger.debug(f"Calculated subtotal from {len(self._last_extracted_items)} items: {subtotal}")
            except (KeyError, TypeError) as e:
                self.logger.warning(f"Error calculating subtotal from items: {e}")
                subtotal = None
        
        # Second pass - find totals
        tax = None
        total = None
        
        # Look for tax amount
        tax_patterns = [
            r"(?:Tax|TAX|Sales Tax|SALES TAX)[\s:]*(?:[\$\s]*)(\d+\.\d{2})",
            r"(?:Tax|TAX|Sales Tax|SALES TAX)[\s:]*(?:[\$\s]*)(\d+)",
        ]
        
        for pattern in tax_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    tax = float(match.group(1))
                    if tax <= 0 or tax > 1000:  # Basic validation
                        tax = None
                    break
                except (ValueError, TypeError):
                    continue
        
        # Look for total amount in last 5 lines
        total_patterns = [
            r"(?:Total|TOTAL|Balance|BALANCE|Amount Due|AMOUNT DUE)[\s:]*(?:[\$\s]*)(\d+\.\d{2})",
            r"(?:Total|TOTAL|Balance|BALANCE|Amount Due|AMOUNT DUE)[\s:]*(?:[\$\s]*)(\d+)",
            r"(?:[\$\s]*)(\d+\.\d{2})\s*$"  # Standalone amount at end of line
        ]
        
        # Get last 5 lines
        lines = text.splitlines()[-5:]
        for line in lines:
            for pattern in total_patterns:
                match = re.search(pattern, line)
                if match:
                    try:
                        total = float(match.group(1))
                        if total <= 0 or total > 10000:  # Basic validation
                            total = None
                        break
                    except (ValueError, TypeError):
                        continue
            if total is not None:
                break
        
        # Validate totals
        if subtotal is not None:
            # Adjust subtotal by discounts
            adjusted_subtotal = subtotal - total_discounts
            
            # Validate tax (should be between 0-20% of adjusted subtotal)
            if tax is not None:
                if tax < 0 or tax > (adjusted_subtotal * 0.20):
                    tax = None
            
            # Validate total with 5% tolerance when discounts present, 2% otherwise
            if total is not None:
                expected_total = adjusted_subtotal
                if tax is not None:
                    expected_total += tax
                    
                tolerance = 0.05 if total_discounts > 0 else 0.02
                if abs(total - expected_total) / expected_total > tolerance:
                    # Only clear total if it's significantly off
                    if total < (expected_total * 0.5) or total > (expected_total * 1.5):
                        total = None
        
        return subtotal, tax, total
    
    def extract_metadata(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract additional metadata from the receipt.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image
            
        Returns:
            Dictionary with metadata
        """
        self.logger.info("Extracting metadata using generic handler")
        
        if not ocr_text:
            self.logger.warning("Empty OCR text provided")
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
        
        self.logger.info(f"Extracted metadata with confidence {metadata['confidence']:.2f}")
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