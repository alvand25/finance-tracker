from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging
import traceback

logger = logging.getLogger(__name__)

class BaseReceiptHandler(ABC):
    """Base class for receipt handlers.
    
    All vendor-specific receipt handlers should inherit from this class and implement
    the required methods for extracting data from receipts.
    """
    
    def __init__(self):
        """Initialize the handler."""
        self.name = self.__class__.__name__
        logger.debug(f"Initialized {self.name}")
    
    @abstractmethod
    def extract_items(self, ocr_text: str, image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract line items from the receipt OCR text.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image for additional analysis
            
        Returns:
            List of item dictionaries with at least 'description' and 'price' keys
        """
        pass
    
    @abstractmethod
    def extract_totals(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract total amounts from the receipt OCR text.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image for additional analysis
            
        Returns:
            Dictionary with keys like 'subtotal', 'tax', 'total', etc.
        """
        pass
    
    def extract_metadata(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract additional metadata from the receipt.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image for additional analysis
            
        Returns:
            Dictionary with metadata like 'store_name', 'date', 'payment_method', etc.
        """
        # Default implementation provides empty metadata
        return {
            'store_name': None,
            'date': None,
            'payment_method': None,
            'currency': 'USD',  # Default currency
        }
    
    def validate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean up extraction results.
        
        Args:
            results: The extraction results to validate
            
        Returns:
            Validated and cleaned up results
        """
        # Default validation logic
        validated = results.copy()
        
        # Calculate subtotal from items if missing
        if 'items' in validated and validated.get('items') and not validated.get('subtotal'):
            try:
                subtotal = sum(item.get('price', 0) for item in validated['items'])
                validated['subtotal'] = round(subtotal, 2)
                logger.debug(f"Calculated subtotal from items: {validated['subtotal']}")
            except Exception as e:
                logger.error(f"Error calculating subtotal from items: {str(e)}")
        
        # Verify total = subtotal + tax if all present
        if (validated.get('subtotal') is not None and 
            validated.get('tax') is not None and 
            validated.get('total') is not None):
            
            expected_total = round(validated['subtotal'] + validated['tax'], 2)
            actual_total = validated['total']
            
            # Allow small floating point differences
            if abs(expected_total - actual_total) > 0.02:
                logger.warning(
                    f"Total mismatch: subtotal ({validated['subtotal']}) + tax ({validated['tax']}) "
                    f"= {expected_total}, but total is {actual_total}"
                )
        
        # Ensure confidence scores
        if 'confidence' not in validated:
            validated['confidence'] = {
                'overall': 0.5,  # Default confidence
                'items': 0.5,
                'totals': 0.5,
                'metadata': 0.5
            }
        
        return validated
    
    def process_receipt(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Process receipt text and extract relevant information.
        
        Args:
            text (str): The OCR text from the receipt
            image_path (Optional[str]): Path to the receipt image, for debugging
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - items (List[Dict]): List of extracted items with descriptions and prices
                - subtotal (float): Receipt subtotal
                - tax (float): Tax amount
                - total (float): Total amount
                - confidence (Dict): Confidence scores for different aspects
                - metadata (Dict): Additional receipt metadata
        """
        try:
            # Extract items first
            items = self.extract_items(text, image_path)
            
            # Extract totals
            subtotal, tax, total = self.extract_totals(text, image_path)
            
            # Extract metadata and calculate confidence
            metadata = self.extract_metadata(text)
            confidence = {
                'items': 0.8 if items else 0.0,
                'totals': 0.8 if total is not None else 0.0,
                'metadata': metadata.get('confidence', 0.0),
                'overall': 0.0  # Will be calculated below
            }
            
            # Calculate overall confidence
            weights = {'items': 0.4, 'totals': 0.4, 'metadata': 0.2}
            confidence['overall'] = sum(
                confidence[key] * weight 
                for key, weight in weights.items()
            )
            
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
            self.logger.error(traceback.format_exc())
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