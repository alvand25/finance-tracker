"""
Tesseract OCR engine implementation.
"""

import os
import logging
import datetime
import pytesseract
from PIL import Image
import cv2
import numpy as np
import re
from typing import Dict, List, Any, Optional

from .base_ocr import BaseOCR, OCRResult, OCRError, OCREngineType

logger = logging.getLogger(__name__)

class TesseractOCR(BaseOCR):
    """
    OCR engine using Tesseract.
    """
    
    def __init__(self, 
                 tesseract_cmd: Optional[str] = None,
                 config: Optional[str] = None,
                 fallback_engine: Optional[BaseOCR] = None):
        """
        Initialize Tesseract OCR.
        
        Args:
            tesseract_cmd: Path to Tesseract executable (optional)
            config: Custom Tesseract configuration (optional)
            fallback_engine: Optional fallback OCR engine
        """
        super().__init__(fallback_engine)
        self.engine_type = OCREngineType.TESSERACT
        
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            
        self.config = config or '--psm 6 --oem 3 -l eng'
        self.last_confidence = 0.0
        self.last_processing_time = 0.0
        
        # Verify Tesseract installation
        try:
            pytesseract.get_tesseract_version()
            logger.info("Successfully initialized Tesseract OCR")
        except Exception as e:
            logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
            raise OCRError(
                "Tesseract not properly installed or configured",
                self.engine_type,
                {'error_type': 'initialization'}
            )
            
    def validate(self) -> bool:
        """
        Validate Tesseract OCR functionality.
        
        Returns:
            bool: True if validation succeeds, False otherwise
        """
        try:
            # Create a simple test image with text
            test_image = Image.new('RGB', (100, 30), color='white')
            test_text = pytesseract.image_to_string(test_image)
            
            # Version check
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract version: {version}")
            
            # Basic functionality test
            test_result = self._process_image(test_image)
            
            return True
        except Exception as e:
            logger.error(f"Tesseract validation failed: {str(e)}")
            return False
            
    def _process_image(self, image_path: str, **kwargs) -> List[OCRResult]:
        """Internal implementation of process_image."""
        try:
            # Convert image to PIL if needed
            if isinstance(image_path, str):
                # Load image path
                pil_image = Image.open(image_path)
            elif isinstance(image_path, np.ndarray):
                # Convert OpenCV image to PIL
                pil_image = Image.fromarray(cv2.cvtColor(image_path, cv2.COLOR_BGR2RGB))
            elif isinstance(image_path, Image.Image):
                pil_image = image_path
            else:
                raise OCRError(
                    "Unsupported image type",
                    self.engine_type,
                    {'error_type': 'input_validation'}
                )
                
            # Get OCR data with confidence scores
            ocr_data = pytesseract.image_to_data(
                pil_image, 
                lang='eng',
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text and calculate statistics
            results = []
            
            for i in range(len(ocr_data['text'])):
                word = ocr_data['text'][i].strip()
                conf = float(ocr_data['conf'][i])
                
                if word and conf > -1:  # Skip empty words and invalid confidence
                    # Create bounding box
                    box = {
                        'left': ocr_data['left'][i],
                        'top': ocr_data['top'][i],
                        'right': ocr_data['left'][i] + ocr_data['width'][i],
                        'bottom': ocr_data['top'][i] + ocr_data['height'][i]
                    }
                    
                    results.append(OCRResult(
                        text=word,
                        confidence=conf / 100.0,  # Convert to 0-1 scale
                        bounding_box=box,
                        page=1,
                        engine=self.engine_type
                    ))
            
            return results
            
        except OCRError:
            raise
        except Exception as e:
            raise OCRError(
                f"Error extracting text with Tesseract: {str(e)}",
                self.engine_type,
                {'error_type': 'processing'}
            )
    
    def process_image(self, image_path: str, **kwargs) -> List[OCRResult]:
        """Process image with fallback support."""
        return self.try_with_fallback('process_image', image_path, **kwargs)
    
    def _extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """Internal implementation of extract_receipt_data."""
        results = self._process_image(image_path)
        if not results:
            return {
                'merchant': None,
                'date': None,
                'total': None,
                'items': [],
                'confidence': 0.0,
                'engine': self.engine_type,
                'error': 'No text detected'
            }
            
        # Sort blocks by vertical position
        blocks = sorted(results, key=lambda r: (r.bounding_box['top'], r.bounding_box['left']))
        
        # Find merchant name (usually at top)
        merchant = blocks[0].text if blocks else None
        
        # Find date (look for date patterns)
        date = None
        date_formats = ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%d/%m/%Y']
        for block in blocks:
            text = block.text.strip()
            for fmt in date_formats:
                try:
                    date = datetime.datetime.strptime(text, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue
            if date:
                break
        
        # Find total amount (usually at bottom, after keywords)
        total = None
        total_keywords = ['total', 'amount', 'sum', 'balance']
        amount_pattern = r'\$?\d+\.\d{2}'
        
        for i in range(len(blocks) - 1, -1, -1):
            text = blocks[i].text.lower()
            if any(keyword in text for keyword in total_keywords):
                # Look for amount in this or next block
                for j in range(i, min(i + 2, len(blocks))):
                    matches = re.findall(amount_pattern, blocks[j].text)
                    if matches:
                        try:
                            total = float(matches[0].replace('$', ''))
                            break
                        except ValueError:
                            continue
                if total:
                    break
        
        # Extract line items (middle section)
        items = []
        current_item = None
        
        for block in blocks:
            text = block.text.strip()
            if not text:
                continue
                
            # Skip if this looks like header or footer
            if any(keyword in text.lower() for keyword in ['receipt', 'tel:', 'phone:', 'thank you']):
                continue
                
            # Look for price pattern
            price_match = re.search(amount_pattern, text)
            if price_match:
                if current_item:
                    items.append(current_item)
                current_item = {
                    'description': text[:price_match.start()].strip(),
                    'price': float(price_match.group().replace('$', '')),
                    'confidence': block.confidence
                }
            elif current_item:
                # Append to current item description
                current_item['description'] = f"{current_item['description']} {text}"
            else:
                # Start new item
                current_item = {
                    'description': text,
                    'price': None,
                    'confidence': block.confidence
                }
        
        # Add last item if exists
        if current_item:
            items.append(current_item)
        
        # Calculate overall confidence
        confidence = sum(r.confidence for r in results) / len(results) if results else 0.0
        
        return {
            'merchant': merchant,
            'date': date,
            'total': total,
            'items': items,
            'confidence': confidence,
            'engine': self.engine_type,
            'error': None
        }
    
    def extract_receipt_data(self, image_path: str) -> Dict[str, Any]:
        """Extract receipt data with fallback support."""
        return self.try_with_fallback('extract_receipt_data', image_path)
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the last OCR run."""
        return {
            'engine': self.engine_type.value,
            'confidence': self.last_confidence,
            'processing_time': self.last_processing_time,
            'config': self.config
        } 