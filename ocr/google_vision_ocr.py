"""Google Cloud Vision OCR implementation."""

import io
import os
import logging
import datetime
import time
from typing import Dict, List, Any, Optional, Tuple
from google.cloud import vision
from google.cloud.vision_v1 import types

from .base_ocr import BaseOCR, OCRResult, OCRError, OCREngineType
from .google_vision_config import GoogleVisionConfig

logger = logging.getLogger(__name__)

class GoogleVisionOCR(BaseOCR):
    """Google Cloud Vision OCR implementation with enhanced fallback handling."""
    
    def __init__(self, credentials_path: Optional[str] = None, fallback_engine: Optional[BaseOCR] = None,
                 max_retries: int = 3, timeout: float = 30.0):
        """
        Initialize Google Vision OCR.
        
        Args:
            credentials_path: Optional path to credentials file
            fallback_engine: Optional fallback OCR engine
            max_retries: Maximum number of retries for API calls
            timeout: Timeout for API calls in seconds
        """
        super().__init__(fallback_engine)
        self.engine_type = OCREngineType.GOOGLE_VISION
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_processing_time = 0.0
        
        if credentials_path:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            
        self.config = GoogleVisionConfig()
        self._client = None
        self._last_error = None
    
    @property
    def client(self) -> vision.ImageAnnotatorClient:
        """Get Vision client with retry logic."""
        if not self._client:
            for attempt in range(self.max_retries):
                try:
                    self._client = self.config.client
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{self.max_retries} to initialize client failed: {str(e)}")
                    if attempt == self.max_retries - 1:
                        raise OCRError(
                            f"Failed to initialize Google Vision client after {self.max_retries} attempts: {str(e)}",
                            self.engine_type,
                            {'error_type': 'initialization', 'last_error': str(e)}
                        )
                    time.sleep(1)  # Wait before retrying
        return self._client
    
    def try_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        """Enhanced fallback mechanism with better error handling."""
        start_time = time.time()
        try:
            # Try primary engine first
            method = getattr(self, f"_{method_name}")
            result = method(*args, **kwargs)
            self.last_processing_time = time.time() - start_time
            return result
        except Exception as e:
            logger.error(f"Primary engine failed: {str(e)}")
            self._last_error = str(e)
            
            # If we have a fallback engine, try it
            if self.fallback_engine:
                logger.info("Attempting fallback OCR")
                try:
                    fallback_method = getattr(self.fallback_engine, method_name)
                    result = fallback_method(*args, **kwargs)
                    self.last_processing_time = time.time() - start_time
                    logger.info("Fallback OCR successful")
                    return result
                except Exception as fallback_e:
                    logger.error(f"Fallback engine also failed: {str(fallback_e)}")
                    raise OCRError(
                        f"Both primary and fallback engines failed. Primary: {str(e)}, Fallback: {str(fallback_e)}",
                        self.engine_type,
                        {
                            'primary_error': str(e),
                            'fallback_error': str(fallback_e),
                            'processing_time': time.time() - start_time
                        }
                    )
            else:
                logger.error("No fallback engine available")
                raise OCRError(
                    f"OCR failed and no fallback available: {str(e)}",
                    self.engine_type,
                    {'error': str(e), 'processing_time': time.time() - start_time}
                )
    
    def validate_api_access(self) -> bool:
        """
        Test API access by running a simple detection.
        
        Returns:
            bool: Whether API access is working
        """
        try:
            # Create a small test image
            content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x00\x00\x02\x00\x01\xe5\x27\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82'
            image = types.Image(content=content)
            
            # Try to detect text
            self.client.text_detection(image=image)
            return True
            
        except Exception as e:
            logger.error(f"API access validation failed: {str(e)}")
            return False
    
    def _process_image(self, image_path: str, **kwargs) -> List[OCRResult]:
        """Internal implementation of process_image with enhanced error handling."""
        try:
            # Read image file with timeout
            with io.open(image_path, 'rb') as image_file:
                content = image_file.read()
                
            image = vision.Image(content=content)
            
            # Detect text with retry logic
            for attempt in range(self.max_retries):
                try:
                    response = self.client.text_detection(
                        image=image,
                        timeout=self.timeout
                    )
                    if response.error.message:
                        raise OCRError(
                            f'Error detecting text: {response.error.message}',
                            self.engine_type,
                            {'api_error': response.error.message}
                        )
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {str(e)}")
                    time.sleep(1)
                
            texts = response.text_annotations
            if not texts:
                return []
                
            results = []
            # Process individual words/blocks with enhanced confidence calculation
            for text in texts[1:]:  # Skip first element (full text)
                vertices = text.bounding_poly.vertices
                box = {
                    'left': min(v.x for v in vertices),
                    'top': min(v.y for v in vertices),
                    'right': max(v.x for v in vertices),
                    'bottom': max(v.y for v in vertices)
                }
                
                # Calculate confidence based on multiple factors
                base_confidence = text.confidence or 0.0
                size_factor = min(1.0, (box['right'] - box['left']) * (box['bottom'] - box['top']) / 1000)
                position_factor = 1.0 - (box['top'] / 2000)  # Assume 2000px max height
                confidence = (base_confidence * 0.6 + size_factor * 0.2 + position_factor * 0.2)
                
                results.append(OCRResult(
                    text=text.description,
                    confidence=confidence,
                    bounding_box=box,
                    engine=self.engine_type
                ))
                
            return results
            
        except OCRError:
            raise
        except Exception as e:
            raise OCRError(
                f"Failed to process image: {str(e)}",
                self.engine_type,
                {'error_type': 'processing'}
            )
    
    def process_image(self, image_path: str, **kwargs) -> List[OCRResult]:
        """Process image with fallback support."""
        return self.try_with_fallback('process_image', image_path, **kwargs)
    
    def _extract_text(self, image_path: str) -> str:
        """Internal implementation of extract_text."""
        try:
            results = self._process_image(image_path)
            if not results:
                return ""
                
            # Sort results by vertical position and then horizontal position
            sorted_results = sorted(results, key=lambda r: (
                r.bounding_box['top'],
                r.bounding_box['left']
            ))
            
            # Combine text with newlines for significant vertical gaps
            text_blocks = []
            last_bottom = 0
            line_buffer = []
            
            for result in sorted_results:
                # Calculate vertical gap
                vertical_gap = result.bounding_box['top'] - last_bottom if last_bottom > 0 else 0
                
                # Start a new line if there's a significant vertical gap
                if vertical_gap > 20:  # Threshold for new line
                    if line_buffer:
                        text_blocks.append(' '.join(line_buffer))
                        line_buffer = []
                    text_blocks.append('')  # Add blank line for large gaps
                
                # Add text to current line
                line_buffer.append(result.text)
                last_bottom = result.bounding_box['bottom']
            
            # Add any remaining text
            if line_buffer:
                text_blocks.append(' '.join(line_buffer))
            
            # Join all blocks with newlines
            return '\n'.join(text_blocks)
            
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            if self.fallback_engine:
                logger.info("Attempting fallback text extraction")
                return self.fallback_engine.extract_text(image_path)
            raise OCRError(
                f"Failed to extract text: {str(e)}",
                self.engine_type,
                {'error_type': 'text_extraction', 'error': str(e)}
            )
    
    def extract_text(self, image_path: str) -> str:
        """Extract text from image with fallback support."""
        return self.try_with_fallback('extract_text', image_path)
    
    def _extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """Internal implementation of receipt data extraction."""
        try:
            # Get text with bounding boxes
            results = self._process_image(image_path)
            if not results:
                raise OCRError(
                    "No text detected in image",
                    self.engine_type,
                    {'error_type': 'no_text_detected'}
                )
            
            # Sort results by position
            sorted_results = sorted(results, key=lambda r: (
                r.bounding_box['top'],
                r.bounding_box['left']
            ))
            
            # Extract header (first few lines)
            header_results = [r for r in sorted_results if r.bounding_box['top'] < 200]
            header_text = ' '.join(r.text for r in header_results)
            
            # Extract items (middle section)
            items_results = [r for r in sorted_results if 200 <= r.bounding_box['top'] <= 800]
            items_text = '\n'.join(r.text for r in items_results)
            
            # Extract footer (last few lines)
            footer_results = [r for r in sorted_results if r.bounding_box['top'] > 800]
            footer_text = ' '.join(r.text for r in footer_results)
            
            # Calculate overall confidence
            confidences = [r.confidence for r in results if r.confidence is not None]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {
                'header': header_text,
                'items': items_text,
                'footer': footer_text,
                'confidence': avg_confidence,
                'engine': self.engine_type.value,
                'processing_time': self.last_processing_time,
                'text_blocks': len(results),
                'raw_text': self._extract_text(image_path)
            }
            
        except Exception as e:
            logger.error(f"Error extracting receipt data: {str(e)}")
            if self.fallback_engine:
                logger.info("Attempting fallback receipt data extraction")
                return self.fallback_engine.extract_receipt_data(image_path)
            raise OCRError(
                f"Failed to extract receipt data: {str(e)}",
                self.engine_type,
                {'error_type': 'receipt_extraction', 'error': str(e)}
            )
    
    def extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """Extract receipt data with fallback support."""
        return self.try_with_fallback('extract_receipt_data', image_path)
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error
    
    def get_engine_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        return {
            'engine_type': self.engine_type.value,
            'is_initialized': self._client is not None,
            'has_fallback': self.fallback_engine is not None,
            'last_error': self._last_error,
            'last_processing_time': self.last_processing_time,
            'api_accessible': self.validate_api_access(),
            'max_retries': self.max_retries,
            'timeout': self.timeout
        } 