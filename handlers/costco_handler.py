"""
Handler for processing Costco receipts.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from handlers.base_handler import BaseReceiptHandler
from utils.image_preprocessor import ImagePreprocessor
from utils.receipt_analyzer import ReceiptAnalyzer

logger = logging.getLogger(__name__)

class CostcoReceiptHandler(BaseReceiptHandler):
    """Handler for processing Costco receipts."""
    
    def __init__(self, debug_mode: bool = False, debug_output_dir: str = 'debug_output'):
        """
        Initialize the Costco receipt handler.
        
        Args:
            debug_mode: Enable debug output
            debug_output_dir: Directory for debug output
        """
        super().__init__()
        self.debug_mode = debug_mode
        self.debug_output_dir = debug_output_dir
        self.preprocessor = ImagePreprocessor(
            debug_mode=debug_mode,
            output_dir=debug_output_dir
        )
        self.logger = logger
        
    def process_receipt(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Process receipt text and extract relevant information."""
        try:
            # Extract items first
            items = self.extract_items(text, image_path)
            
            # Extract totals
            subtotal, tax, total = self.extract_totals(text, image_path)
            
            # Extract metadata
            metadata = self.extract_metadata(text, image_path)
            
            # Calculate confidence scores
            confidence = self._calculate_confidence(text, items, subtotal, tax, total, metadata)
            
            # Build result dictionary
            result = {
                'items': items,
                'subtotal': subtotal,
                'tax': tax,
                'total': total,
                'confidence': confidence,
                'metadata': metadata
            }
            
            self.logger.info(f"Extracted metadata with confidence {confidence['overall']}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing receipt: {str(e)}")
            return {
                'items': [],
                'subtotal': None,
                'tax': None,
                'total': None,
                'confidence': {
                    'items': 0.0,
                    'totals': 0.0,
                    'metadata': 0.0,
                    'overall': 0.0
                },
                'metadata': {}
            }
            
    def _calculate_confidence(
        self,
        text: str,
        items: List[Dict[str, Any]],
        subtotal: Optional[float],
        tax: Optional[float],
        total: Optional[float],
        metadata: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate confidence scores for the extraction."""
        # Calculate items confidence
        items_confidence = 0.0
        if items:
            # Check price and description confidence
            price_confidences = [item.get('confidence', {}).get('price', 0.0) for item in items]
            desc_confidences = [item.get('confidence', {}).get('description', 0.0) for item in items]
            
            avg_price_conf = sum(price_confidences) / len(items) if items else 0.0
            avg_desc_conf = sum(desc_confidences) / len(items) if items else 0.0
            
            # Weight price confidence more heavily
            items_confidence = (avg_price_conf * 0.7 + avg_desc_conf * 0.3)
            
        # Calculate totals confidence
        totals_confidence = 0.0
        if total is not None:
            totals_confidence += 0.4  # Base confidence for having a total
            
            # Check if subtotal and tax add up to total
            if subtotal is not None and tax is not None:
                expected_total = round(subtotal + tax, 2)
                if abs(expected_total - total) <= 0.02:  # Allow small rounding differences
                    totals_confidence += 0.4
                    
            # Additional confidence if we have item prices that sum close to total
            if items:
                items_sum = sum(item.get('price', 0) for item in items)
                if abs(items_sum - total) <= total * 0.1:  # Within 10%
                    totals_confidence += 0.2
                    
        # Get metadata confidence
        metadata_confidence = metadata.get('confidence', 0.0)
        
        # Calculate overall confidence with weights
        weights = {
            'items': 0.5,      # Items are most important
            'totals': 0.3,     # Totals are next
            'metadata': 0.2    # Metadata is least important
        }
        
        confidence = {
            'items': items_confidence,
            'totals': totals_confidence,
            'metadata': metadata_confidence,
            'overall': sum(
                confidence * weight
                for confidence, weight in zip(
                    [items_confidence, totals_confidence, metadata_confidence],
                    weights.values()
                )
            )
        }
        
        return confidence
        
    def extract_items(self, ocr_text: str, image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract items from receipt text."""
        items = []
        lines = ocr_text.split('\n')
        current_item = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for price pattern at end of line
            price_match = re.search(r'(\d+\.\d{2})\s*$', line)
            if price_match:
                price = float(price_match.group(1))
                # Remove price from description
                description = line[:price_match.start()].strip()
                
                # Check if this is a quantity line
                qty_match = re.search(r'^\s*(\d+)\s*@\s*(\d+\.\d{2})', description)
                if qty_match:
                    # This is a quantity line for previous item
                    if current_item:
                        quantity = int(qty_match.group(1))
                        unit_price = float(qty_match.group(2))
                        current_item.update({
                            'quantity': quantity,
                            'unit_price': unit_price,
                            'confidence': {
                                'price': 0.9,
                                'description': 0.9
                            }
                        })
                        items.append(current_item)
                        current_item = None
                else:
                    # This is a new item
                    current_item = {
                        'description': description,
                        'price': price,
                        'quantity': 1,
                        'unit_price': price,
                        'confidence': {
                            'price': 0.9,
                            'description': 0.8
                        }
                    }
                    
            # Look for item number
            elif current_item and re.match(r'^\d{5,}$', line):
                current_item['item_number'] = line
                items.append(current_item)
                current_item = None
                
        # Add last item if pending
        if current_item:
            items.append(current_item)
            
        return items
        
    def extract_totals(self, ocr_text: str, image_path: Optional[str] = None) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Extract total amounts from receipt text.
        
        Returns:
            Tuple of (subtotal, tax, total)
        """
        subtotal = None
        tax = None
        total = None
        
        lines = ocr_text.split('\n')
        
        # Look for total pattern
        for line in lines:
            line = line.strip().upper()
            
            # Look for total amount
            if 'TOTAL' in line and not any(x in line for x in ['SUBTOTAL', 'TAX']):
                total_match = re.search(r'(\d+\.\d{2})\s*$', line)
                if total_match:
                    total = float(total_match.group(1))
                    
            # Look for tax amount (though Costco typically includes tax in item prices)
            elif 'TAX' in line:
                tax_match = re.search(r'(\d+\.\d{2})\s*$', line)
                if tax_match:
                    tax = float(tax_match.group(1))
                    
            # Look for subtotal
            elif 'SUBTOTAL' in line:
                subtotal_match = re.search(r'(\d+\.\d{2})\s*$', line)
                if subtotal_match:
                    subtotal = float(subtotal_match.group(1))
                    
        return subtotal, tax, total
        
    def extract_metadata(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract metadata from receipt text."""
        metadata = super().extract_metadata(ocr_text, image_path)
        
        # Extract store information
        store_info = self._extract_store_info(ocr_text)
        metadata.update(store_info)
        
        # Extract date and time
        date_time = self._extract_date_time(ocr_text)
        metadata.update(date_time)
        
        # Extract membership number
        membership = self._extract_membership(ocr_text)
        if membership:
            metadata['membership_number'] = membership
            
        metadata['store_name'] = 'Costco'
        metadata['currency'] = 'USD'
        
        # Calculate metadata confidence
        confidence = 0.0
        if metadata.get('store_name'):
            confidence += 0.3
        if metadata.get('date'):
            confidence += 0.2
        if metadata.get('time'):
            confidence += 0.1
        if metadata.get('membership_number'):
            confidence += 0.2
        if metadata.get('address'):
            confidence += 0.2
            
        metadata['confidence'] = confidence
        
        return metadata
        
    def _extract_store_info(self, text: str) -> Dict[str, str]:
        """Extract store information from receipt text."""
        store_info = {
            'name': 'Costco',
            'address': '',
            'phone': ''
        }
        
        # Look for address pattern (usually after "COSTCO WHOLESALE" and before date)
        lines = text.split('\n')
        address_started = False
        address_lines = []
        
        for line in lines:
            if 'COSTCO WHOLESALE' in line.upper():
                address_started = True
                continue
                
            if address_started:
                # Stop if we hit a date pattern
                if re.search(r'\d{2}/\d{2}/\d{2,4}', line):
                    break
                    
                # Clean and add address line
                clean_line = line.strip()
                if clean_line and not clean_line.startswith('***'):
                    address_lines.append(clean_line)
                    
        if address_lines:
            store_info['address'] = ' '.join(address_lines)
            
            # Try to extract phone from last line
            phone_match = re.search(r'(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}', address_lines[-1])
            if phone_match:
                store_info['phone'] = phone_match.group()
                # Remove phone from address
                address_lines[-1] = address_lines[-1].replace(phone_match.group(), '').strip()
                store_info['address'] = ' '.join(address_lines)
                
        return store_info
        
    def _extract_date_time(self, text: str) -> Dict[str, str]:
        """Extract date and time from receipt text."""
        result = {'date': None, 'time': None}
        
        # Look for date pattern
        date_match = re.search(r'(\d{2})/(\d{2})/(\d{2,4})', text)
        if date_match:
            month, day, year = date_match.groups()
            # Handle 2-digit year
            if len(year) == 2:
                year = '20' + year
            result['date'] = f"{year}-{month}-{day}"
            
        # Look for time pattern (usually near date)
        time_match = re.search(r'(\d{1,2}):(\d{2})\s*([AaPp][Mm])?', text)
        if time_match:
            hour, minute, meridiem = time_match.groups()
            if meridiem:
                # Convert to 24-hour format
                hour = int(hour)
                if meridiem.upper() == 'PM' and hour < 12:
                    hour += 12
                elif meridiem.upper() == 'AM' and hour == 12:
                    hour = 0
                result['time'] = f"{hour:02d}:{minute}"
            else:
                # If no AM/PM indicator, assume 24-hour format
                result['time'] = f"{int(hour):02d}:{minute}"
            
        return result
        
    def _extract_membership(self, text: str) -> Optional[str]:
        """Extract membership number from receipt text."""
        # Look for membership number pattern
        membership_match = re.search(r'MEMBER\s*#?\s*(\d{10,})', text, re.I)
        if membership_match:
            return membership_match.group(1)
        return None 