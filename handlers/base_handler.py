from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging

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
    
    def process_receipt(self, ocr_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a receipt and extract all relevant information.
        
        Args:
            ocr_text: The OCR text from the receipt
            image_path: Optional path to the receipt image for additional analysis
            
        Returns:
            Dictionary with all extracted data
        """
        try:
            logger.info(f"Processing receipt with {self.name}")
            
            # Extract data
            items = self.extract_items(ocr_text, image_path)
            totals = self.extract_totals(ocr_text, image_path)
            metadata = self.extract_metadata(ocr_text, image_path)
            
            # Combine results
            results = {
                'items': items,
                'subtotal': totals.get('subtotal'),
                'tax': totals.get('tax'),
                'total': totals.get('total'),
                'store': metadata.get('store_name'),
                'date': metadata.get('date'),
                'payment_method': metadata.get('payment_method'),
                'currency': metadata.get('currency', 'USD'),
                'confidence': {
                    'items': 0.7 if items else 0.0,
                    'totals': 0.7 if totals.get('total') else 0.0,
                    'metadata': 0.7 if metadata.get('store_name') else 0.0
                }
            }
            
            # Calculate overall confidence
            confidences = [v for v in results['confidence'].values() if v > 0]
            if confidences:
                results['confidence']['overall'] = sum(confidences) / len(confidences)
            else:
                results['confidence']['overall'] = 0.0
            
            # Validate results
            validated_results = self.validate_results(results)
            
            # Log processing results
            logger.info(
                f"Receipt processing complete: {len(validated_results.get('items', []))} items, "
                f"total: {validated_results.get('total')}, "
                f"confidence: {validated_results.get('confidence', {}).get('overall', 0):.2f}"
            )
            
            return validated_results
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Return error result
            return {
                'error': str(e),
                'items': [],
                'subtotal': None,
                'tax': None,
                'total': None,
                'confidence': {'overall': 0.0}
            } 