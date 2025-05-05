"""Base OCR engine interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class OCREngineType(Enum):
    """Supported OCR engine types."""
    GOOGLE_VISION = "google_vision"
    TESSERACT = "tesseract"

@dataclass
class OCRResult:
    """Container for OCR results."""
    text: str
    confidence: float
    bounding_box: Dict[str, float]
    page: int = 1
    engine: OCREngineType = None
    error: Optional[str] = None

class OCRError(Exception):
    """Base exception for OCR errors."""
    def __init__(self, message: str, engine: OCREngineType, details: Dict[str, Any] = None):
        super().__init__(message)
        self.engine = engine
        self.details = details or {}

class BaseOCR(ABC):
    """Abstract base class for OCR engines."""
    
    def __init__(self, fallback_engine: Optional['BaseOCR'] = None):
        """
        Initialize OCR engine.
        
        Args:
            fallback_engine: Optional fallback OCR engine to use if primary fails
        """
        self.fallback_engine = fallback_engine
        
    @abstractmethod
    def process_image(self, image_path: str, **kwargs) -> List[OCRResult]:
        """
        Process an image and extract text.
        
        Args:
            image_path: Path to image file
            **kwargs: Additional engine-specific arguments
            
        Returns:
            List of OCR results with position and confidence
            
        Raises:
            OCRError: If text extraction fails
        """
        pass
        
    @abstractmethod
    def extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """
        Extract structured data from a receipt image.
        
        Args:
            image_path: Path to receipt image
            
        Returns:
            Dictionary containing extracted receipt data:
            {
                'merchant': str,
                'date': str,
                'total': float,
                'items': List[Dict],
                'confidence': float,
                'engine': OCREngineType,
                'error': Optional[str]
            }
            
        Raises:
            OCRError: If receipt data extraction fails
        """
        pass
    
    def try_with_fallback(self, method: str, *args, **kwargs) -> Any:
        """
        Try a method with fallback support.
        
        Args:
            method: Name of method to try
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result from primary or fallback engine
            
        Raises:
            OCRError: If both primary and fallback fail
        """
        try:
            return getattr(self, f"_{method}")(*args, **kwargs)
        except OCRError as e:
            if self.fallback_engine:
                try:
                    result = getattr(self.fallback_engine, method)(*args, **kwargs)
                    if isinstance(result, dict):
                        result['engine'] = self.fallback_engine.engine_type
                    return result
                except Exception as fallback_error:
                    raise OCRError(
                        f"Both primary and fallback engines failed. Primary: {str(e)}, Fallback: {str(fallback_error)}",
                        self.engine_type,
                        {'primary_error': str(e), 'fallback_error': str(fallback_error)}
                    )
            raise 