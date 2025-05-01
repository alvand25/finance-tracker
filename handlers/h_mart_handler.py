"""
Handler for H Mart receipts.
"""

import re
import logging
from typing import List, Tuple, Optional
from decimal import Decimal

from .base_handler import BaseReceiptHandler
from models.receipt_item import ReceiptItem
from models.item import Item
from models.totals import Totals

logger = logging.getLogger(__name__)

class HMartHandler(BaseReceiptHandler):
    """Handler for processing H Mart receipts."""
    
    def __init__(self):
        """Initialize H Mart handler with store aliases."""
        self.store_aliases = ["H MART", "HMART", "H-MART"]
        
    def extract_items(self, text: str) -> List[Item]:
        """Extract items from H Mart receipt text.
        
        Args:
            text: The receipt text to parse
            
        Returns:
            List of Item objects containing the extracted item information
        """
        items = []
        lines = text.split('\n')
        
        # Regular expression for matching item lines
        # Format: ITEM_NAME     QTY [lb] @ PRICE    TOTAL
        # or:     ITEM_NAME     PRICE              TOTAL
        item_pattern = re.compile(
            r'^([A-Z\s]+)\s+(?:(\d+(?:\.\d+)?)\s*(?:lb)?\s*@\s*(\d+\.\d+)|(\d+\.\d+))\s+(\d+\.\d+)\s*$'
        )
        
        for line in lines:
            line = line.strip()
            match = item_pattern.match(line)
            
            if match:
                name = match.group(1).strip()
                
                # Check if it's a quantity-based item or single item
                if match.group(2) and match.group(3):  # Has quantity and unit price
                    quantity = Decimal(match.group(2))
                    unit_price = Decimal(match.group(3))
                else:  # Single item with just price
                    quantity = Decimal("1")
                    unit_price = Decimal(match.group(4))
                    
                total_price = Decimal(match.group(5))
                
                items.append(Item(
                    name=name,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price
                ))
                
        return items
        
    def extract_total(self, text: str) -> Totals:
        """Extract totals from H Mart receipt text.
        
        Args:
            text: The receipt text to parse
            
        Returns:
            Totals object containing the extracted totals information
        """
        subtotal = Decimal("0")
        tax = Decimal("0")
        total = Decimal("0")
        
        lines = text.split('\n')
        
        # Regular expressions for matching total lines
        subtotal_pattern = re.compile(r'SUBTOTAL\s+(\d+\.\d+)')
        tax_pattern = re.compile(r'TAX\s+(\d+\.\d+)')
        total_pattern = re.compile(r'TOTAL\s+(\d+\.\d+)')
        
        for line in lines:
            line = line.strip()
            
            # Try to match each type of total
            subtotal_match = subtotal_pattern.search(line)
            if subtotal_match:
                subtotal = Decimal(subtotal_match.group(1))
                continue
                
            tax_match = tax_pattern.search(line)
            if tax_match:
                tax = Decimal(tax_match.group(1))
                continue
                
            total_match = total_pattern.search(line)
            if total_match:
                total = Decimal(total_match.group(1))
                
        return Totals(
            subtotal=subtotal,
            tax=tax,
            total=total
        ) 