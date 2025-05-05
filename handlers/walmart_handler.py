"""Walmart receipt handler implementation."""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime

from .base_handler import BaseReceiptHandler
from models.receipt import Receipt, ReceiptItem

logger = logging.getLogger(__name__)

class WalmartReceiptHandler(BaseReceiptHandler):
    """Handler for Walmart receipts."""
    
    STORE_NAME_PATTERNS = [
        r'WALMART',
        r'WAL\s*MART',
        r'WAL-MART',
        r'WALMART\s*SUPERCENTER',
    ]
    
    ITEM_PATTERNS = [
        # Standard item with price and optional department code
        r'^(?:\d{3,4}\s+)?([A-Z0-9\s\-\'\.&]+?)\s+(\d+\.\d{2})$',
        # Quantity-based item
        r'^(\d+)\s*@\s*([A-Z0-9\s\-\'\.&]+?)\s+(\d+\.\d{2})$',
        # Weight-based item
        r'^([\d\.]+)\s*(?:LB|lb|Lb)\s*@\s*\$?([\d\.]+)/(?:LB|lb|Lb)\s+([A-Z0-9\s\-\'\.&]+?)\s+(\d+\.\d{2})$',
        # UPC code item
        r'^(?:\*+)?(\d{12,13})\s+([A-Z0-9\s\-\'\.&]+?)\s+(\d+\.\d{2})$'
    ]
    
    TOTAL_PATTERNS = [
        r'TOTAL\s*\$?\s*(\d+\.\d{2})',
        r'SUBTOTAL\s*\$?\s*(\d+\.\d{2})',
        r'BALANCE\s*DUE\s*\$?\s*(\d+\.\d{2})'
    ]
    
    TAX_PATTERNS = [
        r'(?:SALES\s*)?TAX\s*\$?\s*(\d+\.\d{2})',
        r'(?:STATE|COUNTY)\s*TAX\s*\$?\s*(\d+\.\d{2})'
    ]
    
    SUBTOTAL_PATTERNS = [
        r'SUBTOTAL\s*\$?\s*(\d+\.\d{2})',
        r'SUB\s*TOTAL\s*\$?\s*(\d+\.\d{2})'
    ]
    
    DATE_PATTERNS = [
        r'(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(\d{2}-\d{2}-\d{2,4})'
    ]
    
    def __init__(self):
        """Initialize the handler."""
        super().__init__()
        self.store_number: Optional[str] = None
        self.cashier: Optional[str] = None
        self.register: Optional[str] = None
        self.transaction_id: Optional[str] = None
        self.department_codes: Dict[str, str] = {}
    
    def can_handle_receipt(self, text: str) -> float:
        """Check if this handler can process the receipt."""
        # Check for store name matches
        store_confidence = self._check_store_name(text)
        if store_confidence < 0.5:
            return 0.0
            
        # Check for Walmart specific formatting
        format_confidence = 0.0
        if re.search(r'SAVE\s*MONEY\.*\s*LIVE\s*BETTER', text):
            format_confidence += 0.4
        if re.search(r'TC#\s*\d+-\d+-\d+', text):
            format_confidence += 0.3
        if any(re.search(pattern, text) for pattern in self.TOTAL_PATTERNS):
            format_confidence += 0.3
            
        return min(store_confidence * (0.7 + format_confidence), 1.0)
    
    def extract_store_info(self, text: str) -> Tuple[str, float]:
        """Extract store name and store number."""
        store_name = "WALMART"
        confidence = 0.0
        
        # Try to find store number
        store_match = re.search(r'STORE\s*#?\s*(\d+)', text)
        if store_match:
            self.store_number = store_match.group(1)
            store_name = f"WALMART #{self.store_number}"
            confidence = 1.0
        else:
            # Look for simpler matches
            for pattern in self.STORE_NAME_PATTERNS:
                if re.search(pattern, text):
                    confidence = 0.8
                    break
        
        # Extract additional metadata
        cashier_match = re.search(r'CASHIER:?\s*([A-Z0-9]+)', text)
        if cashier_match:
            self.cashier = cashier_match.group(1)
            
        register_match = re.search(r'REG(?:ISTER)?:?\s*#?(\d+)', text)
        if register_match:
            self.register = register_match.group(1)
            
        trans_match = re.search(r'TC#\s*(\d+-\d+-\d+)', text)
        if trans_match:
            self.transaction_id = trans_match.group(1)
        
        return store_name, confidence
    
    def extract_items(self, text: str) -> List[ReceiptItem]:
        """Extract items from the receipt text."""
        items = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip header/footer lines
            if any(re.search(pattern, line) for pattern in 
                  self.TOTAL_PATTERNS + self.TAX_PATTERNS + self.SUBTOTAL_PATTERNS):
                continue
            
            item = None
            confidence = 0.0
            
            # Try UPC code pattern first
            match = re.match(self.ITEM_PATTERNS[3], line)
            if match:
                upc, name, price = match.groups()
                item = ReceiptItem(
                    name=name.strip(),
                    price=Decimal(price),
                    quantity=Decimal('1'),
                    confidence=0.95,
                    notes=f"UPC: {upc}"
                )
            
            # Try standard item pattern with department code
            if not item:
                match = re.match(self.ITEM_PATTERNS[0], line)
                if match:
                    name, price = match.groups()
                    dept_match = re.match(r'^(\d{3,4})\s+(.+)$', name)
                    if dept_match:
                        dept_code, name = dept_match.groups()
                        self.department_codes[name.strip()] = dept_code
                    item = ReceiptItem(
                        name=name.strip(),
                        price=Decimal(price),
                        quantity=Decimal('1'),
                        confidence=0.9
                    )
            
            # Try quantity-based pattern
            if not item:
                match = re.match(self.ITEM_PATTERNS[1], line)
                if match:
                    qty, name, price = match.groups()
                    item = ReceiptItem(
                        name=name.strip(),
                        price=Decimal(price),
                        quantity=Decimal(qty),
                        confidence=0.85
                    )
            
            # Try weight-based pattern
            if not item:
                match = re.match(self.ITEM_PATTERNS[2], line)
                if match:
                    weight, price_per_lb, name, total = match.groups()
                    item = ReceiptItem(
                        name=name.strip(),
                        price=Decimal(total),
                        quantity=Decimal(weight),
                        confidence=0.8
                    )
            
            if item:
                # Additional validation
                if item.price <= 0 or item.quantity <= 0:
                    logger.warning(f"Invalid price or quantity in line: {line}")
                    continue
                    
                if item.price > 1000:  # Probably an error if item costs more than $1000
                    logger.warning(f"Suspiciously high price in line: {line}")
                    item.suspicious = True
                    item.confidence *= 0.5
                
                # Add department code if available
                if item.name in self.department_codes:
                    item.notes = f"Dept: {self.department_codes[item.name]}"
                
                items.append(item)
        
        return items
    
    def extract_total(self, text: str) -> Tuple[Optional[Decimal], float]:
        """Extract total amount from receipt text."""
        for pattern in self.TOTAL_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    total = Decimal(match.group(1))
                    if 0 < total < 10000:  # Reasonable range for Walmart
                        return total, 0.9
                    else:
                        logger.warning(f"Total amount {total} seems unreasonable")
                        return total, 0.5
                except (ValueError, decimal.InvalidOperation) as e:
                    logger.error(f"Error parsing total: {e}")
        
        return None, 0.0
    
    def extract_tax(self, text: str) -> Tuple[Optional[Decimal], float]:
        """Extract tax amount from receipt text."""
        total_tax = Decimal('0')
        confidence = 0.0
        
        for pattern in self.TAX_PATTERNS:
            match = re.search(pattern, text)
            if match:
                try:
                    tax = Decimal(match.group(1))
                    total_tax += tax
                    confidence = 0.9
                except (ValueError, decimal.InvalidOperation) as e:
                    logger.error(f"Error parsing tax: {e}")
        
        if total_tax > 0:
            return total_tax, confidence
        return None, 0.0
    
    def extract_date(self, text: str) -> Tuple[Optional[datetime], float]:
        """Extract date from receipt text."""
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                try:
                    # Try different date formats
                    for fmt in ['%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y']:
                        try:
                            return datetime.strptime(date_str, fmt), 0.9
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parsing date {date_str}: {e}")
        
        return None, 0.0
    
    def extract_payment_method(self, text: str) -> Tuple[Optional[str], float]:
        """Extract payment method from receipt text."""
        payment_patterns = {
            r'VISA\s*\**\d{4}': ('VISA', 0.9),
            r'MASTERCARD\s*\**\d{4}': ('MASTERCARD', 0.9),
            r'AMEX\s*\**\d{4}': ('AMEX', 0.9),
            r'DISCOVER\s*\**\d{4}': ('DISCOVER', 0.9),
            r'CASH': ('CASH', 0.9),
            r'DEBIT': ('DEBIT', 0.8),
            r'EBT': ('EBT', 0.9),
            r'WALMART\s*PAY': ('WALMART PAY', 0.95)
        }
        
        for pattern, (method, conf) in payment_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                return method, conf
        
        return None, 0.0
    
    def process_receipt(self, text: str) -> Receipt:
        """Process the receipt text and return a Receipt object."""
        receipt = Receipt()
        
        # Extract store information
        store_name, store_conf = self.extract_store_info(text)
        receipt.store_name = store_name
        
        # Extract items
        receipt.items = self.extract_items(text)
        
        # Extract totals
        total, total_conf = self.extract_total(text)
        if total:
            receipt.total_amount = total
            
        tax, tax_conf = self.extract_tax(text)
        if tax:
            receipt.tax_amount = tax
            
        # Calculate subtotal if not explicitly found
        if receipt.items:
            items_total = sum(item.price * item.quantity for item in receipt.items)
            receipt.subtotal_amount = items_total
        
        # Extract date and payment method
        date, date_conf = self.extract_date(text)
        if date:
            receipt.date = date
            
        payment_method, payment_conf = self.extract_payment_method(text)
        if payment_method:
            receipt.payment_method = payment_method
        
        # Add metadata
        receipt.debug_info.update({
            'store_number': self.store_number,
            'cashier': self.cashier,
            'register': self.register,
            'transaction_id': self.transaction_id,
            'department_codes': self.department_codes,
            'confidence_scores': {
                'store': store_conf,
                'total': total_conf,
                'tax': tax_conf,
                'date': date_conf,
                'payment': payment_conf
            }
        })
        
        # Calculate confidence and validate
        receipt.calculate_confidence()
        receipt.calculate_totals()
        
        return receipt 