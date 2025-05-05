from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging
import traceback
from decimal import Decimal
from datetime import datetime

from models.receipt import Receipt, ReceiptItem

logger = logging.getLogger(__name__)

class BaseHandler(ABC):
    """Abstract base class for receipt handlers."""
    
    def __init__(self):
        """Initialize the base handler."""
        self.store_name = None
        self.confidence_threshold = 0.7
        
    @abstractmethod
    def can_handle(self, text: str, confidence_threshold: float = 0.7) -> bool:
        """Check if this handler can process the receipt text.
        
        Args:
            text: The receipt text to check.
            confidence_threshold: Minimum confidence threshold.
            
        Returns:
            True if this handler can process the text, False otherwise.
        """
        pass
        
    @abstractmethod
    def extract_items(self, text: str) -> List[Dict[str, Any]]:
        """Extract items from receipt text.
        
        Args:
            text: The receipt text to process.
            
        Returns:
            List of dictionaries containing item data.
        """
        pass
        
    @abstractmethod
    def extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract metadata from receipt text.
        
        Args:
            text: The receipt text to process.
            
        Returns:
            Dictionary containing receipt metadata.
        """
        pass
        
    @abstractmethod
    def _extract_totals(self, text: str) -> Dict[str, Optional[float]]:
        """Extract total amounts from receipt text.
        
        Args:
            text: The receipt text to process.
            
        Returns:
            Dictionary containing total amounts.
        """
        pass
        
    @abstractmethod
    def _calculate_item_confidence(self, name: str, price: float, quantity: float) -> float:
        """Calculate confidence score for an item.
        
        Args:
            name: Item name.
            price: Item price.
            quantity: Item quantity.
            
        Returns:
            Confidence score between 0 and 1.
        """
        pass
        
    @abstractmethod
    def _calculate_overall_confidence(self, items: List[Dict[str, Any]], 
                                    totals: Dict[str, Optional[float]], 
                                    metadata: Dict[str, Any]) -> float:
        """Calculate overall confidence score for the receipt.
        
        Args:
            items: List of item dictionaries.
            totals: Dictionary of total amounts.
            metadata: Dictionary of receipt metadata.
            
        Returns:
            Overall confidence score between 0 and 1.
        """
        pass
        
    def process(self, text: str, image_path: Optional[str] = None) -> Receipt:
        """Process receipt text into structured data.
        
        Args:
            text: The receipt text to process.
            image_path: Optional path to receipt image.
            
        Returns:
            Processed Receipt object.
        """
        # Extract basic metadata
        metadata = self.extract_metadata(text)
        
        # Extract items
        items = self.extract_items(text)
        
        # Extract totals
        totals = self._extract_totals(text)
        
        # Create receipt items
        receipt_items = []
        for item in items:
            receipt_items.append(ReceiptItem(
                name=item['name'],
                quantity=Decimal(str(item['quantity'])),
                price=Decimal(str(item['price'])),
                confidence=item['confidence'],
                suspicious=item['suspicious']
            ))
            
        # Create receipt
        receipt = Receipt(
            store_name=metadata['store_name'],
            date=metadata['date'],
            total_amount=Decimal(str(totals['total'])) if totals['total'] else Decimal('0'),
            tax_amount=Decimal(str(totals['tax'])) if totals['tax'] else Decimal('0'),
            subtotal_amount=Decimal(str(totals['subtotal'])) if totals['subtotal'] else Decimal('0'),
            items=receipt_items,
            confidence_score=self._calculate_overall_confidence(items, totals, metadata),
            requires_review=any(item['suspicious'] for item in items)
        )
        
        # Add validation notes
        if not metadata['date']:
            receipt.add_validation_note("Date not detected")
        if not totals['total']:
            receipt.add_validation_note("Total amount not detected")
        if not items:
            receipt.add_validation_note("No items detected")
            
        return receipt

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