"""
import os
import json
import logging
from typing import Dict, Any, Optional

from handlers.handler_registry import HandlerRegistry
from utils.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)

class ReceiptProcessor:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.registry = HandlerRegistry()
        self.preprocessor = ImagePreprocessor(debug_mode=debug_mode)
        
    def process_receipt(self, image_path: str, ocr_text: str) -> Dict[str, Any]:
        """Process a receipt image and OCR text to extract structured data."""
        try:
            # Extract store name from OCR text
            store_name = self._extract_store_name(ocr_text)
            
            # Get appropriate handler
            handler = self.registry.get_handler_for_store(store_name)
            handler_name = handler.__class__.__name__
            
            # Initialize result with template
            with open('utils/test_result_template.json', 'r') as f:
                result = json.load(f)
            
            # Set basic metadata
            result['image_filename'] = os.path.basename(image_path)
            result['receipt_id'] = os.path.splitext(os.path.basename(image_path))[0]
            
            # Process with handler
            handler_result = handler.process_receipt(ocr_text, image_path)
            
            # Update store info
            result['store'].update({
                'name': store_name,
                'confidence': self._calculate_store_confidence(store_name, ocr_text),
                'handler_used': handler_name
            })
            
            # Update items
            result['items'] = handler_result.get('items', [])
            
            # Update totals
            result['totals'].update({
                'subtotal': handler_result.get('subtotal'),
                'tax': handler_result.get('tax'),
                'total': handler_result.get('total'),
                'confidence': self._calculate_totals_confidence(
                    handler_result.get('subtotal'),
                    handler_result.get('tax'),
                    handler_result.get('total'),
                    result['items']
                )
            })
            
            # Update OCR confidence
            result['ocr'].update({
                'text': ocr_text,
                'confidence': self._calculate_ocr_confidence(ocr_text),
                'keywords_found': self._extract_ocr_keywords(ocr_text)
            })
            
            # Calculate overall confidence
            result['confidence'].update({
                'items': self._calculate_items_confidence(result['items']),
                'totals': result['totals']['confidence'],
                'store': result['store']['confidence'],
                'ocr': result['ocr']['confidence']
            })
            
            # Calculate weighted overall confidence
            weights = {
                'items': 0.6,
                'totals': 0.1,
                'store': 0.2,
                'ocr': 0.1
            }
            
            result['confidence']['overall'] = sum(
                score * weight
                for metric, score in result['confidence'].items()
                if metric != 'overall'
                for metric_name, weight in weights.items()
                if metric_name == metric
            )
            
            # Update status
            result['status'].update({
                'success': result['confidence']['overall'] >= 0.7,
                'fallback_used': handler_name == 'GenericHandler',
                'errors': [],
                'warnings': []
            })
            
            # Add warnings for low confidence
            if result['confidence']['items'] < 0.6:
                result['status']['warnings'].append(f"Low item confidence: {result['confidence']['items']:.2f}")
            if result['confidence']['totals'] < 0.6:
                result['status']['warnings'].append(f"Low totals confidence: {result['confidence']['totals']:.2f}")
            if result['confidence']['store'] < 0.6:
                result['status']['warnings'].append(f"Low store confidence: {result['confidence']['store']:.2f}")
            if result['confidence']['ocr'] < 0.6:
                result['status']['warnings'].append(f"Low OCR confidence: {result['confidence']['ocr']:.2f}")
            
            # Update metadata
            result['metadata'].update(handler_result.get('metadata', {}))
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing receipt: {str(e)}")
            return self._create_error_result(str(e), image_path)
    
    def _calculate_items_confidence(self, items: list) -> float:
        """Calculate confidence score for extracted items."""
        if not items:
            return 0.0
            
        # Get individual item confidences
        price_confidences = []
        desc_confidences = []
        
        for item in items:
            conf = item.get('confidence', {})
            if isinstance(conf, dict):
                price_confidences.append(conf.get('price', 0.0))
                desc_confidences.append(conf.get('description', 0.0))
            
        if not price_confidences or not desc_confidences:
            return 0.0
            
        # Calculate weighted average
        avg_price_conf = sum(price_confidences) / len(price_confidences)
        avg_desc_conf = sum(desc_confidences) / len(desc_confidences)
        
        # Price confidence weighted more heavily
        return (avg_price_conf * 0.8 + avg_desc_conf * 0.2)
    
    def _calculate_totals_confidence(
        self,
        subtotal: Optional[float],
        tax: Optional[float],
        total: Optional[float],
        items: list
    ) -> float:
        """Calculate confidence score for totals extraction."""
        confidence = 0.0
        
        if total is not None:
            confidence += 0.4  # Base confidence for having total
            
            # Check if items sum matches total
            if items:
                items_sum = sum(item.get('price', 0) for item in items)
                if abs(items_sum - total) <= total * 0.2:  # Within 20%
                    confidence += 0.3
                    
            # Check if subtotal + tax = total
            if subtotal is not None and tax is not None:
                expected_total = round(subtotal + tax, 2)
                if abs(expected_total - total) <= 0.02:  # Allow small rounding differences
                    confidence += 0.3
                    
        return min(confidence, 0.99)  # Cap at 0.99
    
    def _calculate_store_confidence(self, store_name: str, ocr_text: str) -> float:
        """Calculate confidence score for store identification."""
        if not store_name:
            return 0.0
            
        # Base confidence for having a store name
        confidence = 0.7
        
        # Check if store name appears multiple times
        store_name_lower = store_name.lower()
        occurrences = sum(1 for line in ocr_text.lower().split('\n') if store_name_lower in line)
        
        if occurrences > 1:
            confidence = 0.9  # High confidence if store name appears multiple times
            
        return confidence
    
    def _calculate_ocr_confidence(self, ocr_text: str) -> float:
        """Calculate confidence score for OCR quality."""
        if not ocr_text:
            return 0.0
            
        # Start with base confidence
        confidence = 0.5
        
        # Check for key receipt elements
        keywords = ['total', 'tax', 'date', 'time']
        found_keywords = self._extract_ocr_keywords(ocr_text)
        
        # Add confidence for each found keyword
        keyword_boost = 0.1
        confidence += len(found_keywords) * keyword_boost
        
        return min(confidence, 0.99)  # Cap at 0.99
    
    def _extract_ocr_keywords(self, ocr_text: str) -> list:
        """Extract key receipt keywords found in OCR text."""
        keywords = ['total', 'tax', 'date', 'time', 'store', 'amount']
        found = []
        
        text_lower = ocr_text.lower()
        for keyword in keywords:
            if keyword in text_lower:
                found.append(keyword)
                
        return found
    
    def _extract_store_name(self, ocr_text: str) -> str:
        """Extract store name from OCR text."""
        # Simple extraction - first non-empty line
        for line in ocr_text.split('\n'):
            line = line.strip()
            if line:
                return line
        return ""
    
    def _create_error_result(self, error_message: str, image_path: str) -> Dict[str, Any]:
        """Create an error result using the template."""
        try:
            with open('utils/test_result_template.json', 'r') as f:
                result = json.load(f)
                
            result['image_filename'] = os.path.basename(image_path)
            result['receipt_id'] = os.path.splitext(os.path.basename(image_path))[0]
            result['status']['success'] = False
            result['status']['errors'].append(error_message)
            
            return result
        except Exception as e:
            logger.error(f"Error creating error result: {str(e)}")
            return {
                'status': {
                    'success': False,
                    'errors': [str(error_message), f"Template error: {str(e)}"]
                }
            }
""" 