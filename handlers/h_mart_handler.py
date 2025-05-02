"""
Handler for processing H-Mart receipts.
"""

import re
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from models.receipt_item import ReceiptItem

class HMartHandler:
    """Handler for processing H-Mart receipts."""
    
    STORE_NAME = "H-Mart"
    CONFIDENCE_THRESHOLD = 0.75
    
    # Regular expressions for H-Mart receipt patterns
    ITEM_PATTERN = r"^([A-Z0-9 -]+)\s+(\d*\.?\d+)\s*(?:@\s*(\d+\.?\d*))?$"
    TOTAL_PATTERN = r"^TOTAL\s+\$?\s*(\d+\.?\d+)$"
    SUBTOTAL_PATTERN = r"^SUB\s*TOTAL\s+\$?\s*(\d+\.?\d+)$"
    TAX_PATTERN = r"^TAX\s+\$?\s*(\d+\.?\d+)$"
    
    def __init__(self):
        """Initialize the H-Mart receipt handler."""
        self.confidence_scores = {
            'store_match': 0.0,
            'item_extraction': 0.0,
            'total_verification': 0.0,
            'overall': 0.0
        }
    
    def can_handle(self, text: str) -> bool:
        """
        Check if this handler can process the given receipt text.
        
        Args:
            text: Raw OCR text from the receipt
            
        Returns:
            bool: True if this handler can process the receipt
        """
        # Look for H-Mart specific patterns
        h_mart_indicators = [
            "H-MART",
            "H MART",
            "HMART",
        ]
        
        text_upper = text.upper()
        for indicator in h_mart_indicators:
            if indicator in text_upper:
                self.confidence_scores['store_match'] = 1.0
                return True
        
        # Check for characteristic H-Mart receipt patterns
        pattern_matches = 0
        total_patterns = 3
        
        if re.search(self.TOTAL_PATTERN, text, re.MULTILINE):
            pattern_matches += 1
        if re.search(self.SUBTOTAL_PATTERN, text, re.MULTILINE):
            pattern_matches += 1
        if re.search(self.TAX_PATTERN, text, re.MULTILINE):
            pattern_matches += 1
            
        confidence = pattern_matches / total_patterns
        self.confidence_scores['store_match'] = confidence
        
        return confidence >= 0.5
    
    def extract_items(self, text: str) -> Tuple[List[ReceiptItem], Dict[str, Any]]:
        """
        Extract items from the receipt text.
        
        Args:
            text: Raw OCR text from the receipt
            
        Returns:
            Tuple containing:
            - List of ReceiptItem objects
            - Dictionary with additional receipt information (totals, tax, etc.)
        """
        items = []
        metadata = {
            'subtotal': Decimal('0'),
            'tax': Decimal('0'),
            'total': Decimal('0'),
            'store': self.STORE_NAME,
            'confidence_scores': self.confidence_scores
        }
        
        lines = text.split('\n')
        item_count = 0
        valid_items = 0
        
        for line in lines:
            # Try to match item pattern
            item_match = re.match(self.ITEM_PATTERN, line.strip())
            if item_match:
                item_count += 1
                try:
                    description = item_match.group(1).strip()
                    price = Decimal(item_match.group(2))
                    quantity = 1.0
                    unit_price = None
                    
                    if item_match.group(3):  # Unit price is present
                        unit_price = Decimal(item_match.group(3))
                        quantity = float(price / unit_price)
                        price = unit_price * Decimal(str(quantity))
                    
                    confidence = {
                        'description': 0.9 if len(description) > 2 else 0.7,
                        'price': 0.95 if price > 0 else 0.5,
                        'quantity': 0.9 if quantity > 0 else 0.5,
                        'overall': 0.0  # Will be calculated below
                    }
                    
                    # Calculate overall confidence for this item
                    confidence['overall'] = sum(
                        score for score in confidence.values() if isinstance(score, float)
                    ) / (len(confidence) - 1)  # -1 to exclude the overall key
                    
                    item = ReceiptItem(
                        description=description,
                        price=price,
                        quantity=quantity,
                        unit_price=unit_price,
                        confidence=confidence
                    )
                    items.append(item)
                    valid_items += 1
                except (ValueError, TypeError) as e:
                    print(f"Error processing item: {line.strip()} - {str(e)}")
                    continue
            
            # Try to match total patterns
            total_match = re.match(self.TOTAL_PATTERN, line.strip())
            if total_match:
                try:
                    metadata['total'] = Decimal(total_match.group(1))
                except (ValueError, TypeError):
                    continue
            
            subtotal_match = re.match(self.SUBTOTAL_PATTERN, line.strip())
            if subtotal_match:
                try:
                    metadata['subtotal'] = Decimal(subtotal_match.group(1))
                except (ValueError, TypeError):
                    continue
            
            tax_match = re.match(self.TAX_PATTERN, line.strip())
            if tax_match:
                try:
                    metadata['tax'] = Decimal(tax_match.group(1))
                except (ValueError, TypeError):
                    continue
        
        # Calculate confidence scores
        if item_count > 0:
            self.confidence_scores['item_extraction'] = valid_items / item_count
        
        # Verify totals
        calculated_total = sum(item.price for item in items)
        if metadata['total'] > 0:
            total_diff = abs(calculated_total - metadata['total'])
            self.confidence_scores['total_verification'] = 1.0 if total_diff < Decimal('0.01') else 0.5
        
        # Calculate overall confidence
        self.confidence_scores['overall'] = sum(
            score for score in self.confidence_scores.values() if isinstance(score, float)
        ) / len([score for score in self.confidence_scores.values() if isinstance(score, float)])
        
        metadata['confidence_scores'] = self.confidence_scores
        return items, metadata 