"""
Tesseract OCR engine implementation.
"""

import os
import logging
import pytesseract
from PIL import Image
import cv2
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TesseractOCR:
    """
    OCR engine using Tesseract.
    """
    
    def __init__(self, 
                 tesseract_cmd: Optional[str] = None,
                 config: Optional[str] = None):
        """
        Initialize Tesseract OCR.
        
        Args:
            tesseract_cmd: Path to Tesseract executable (optional)
            config: Custom Tesseract configuration (optional)
        """
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
            raise RuntimeError("Tesseract not properly installed or configured")
            
    def extract_text(self, image: Any) -> Dict[str, Any]:
        """
        Extract text from an image using Tesseract OCR.
        
        Args:
            image: Image path (str) or numpy array
            
        Returns:
            Dictionary containing:
                - text: Extracted text
                - confidence: Overall confidence score
                - text_blocks: List of text blocks with positions
                - processing_time: Time taken for OCR
        """
        try:
            # Convert image to PIL if needed
            if isinstance(image, str):
                # Load image path
                pil_image = Image.open(image)
            elif isinstance(image, np.ndarray):
                # Convert OpenCV image to PIL
                pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            elif isinstance(image, Image.Image):
                pil_image = image
            else:
                raise ValueError("Unsupported image type")
                
            # Get OCR data with confidence scores
            ocr_data = pytesseract.image_to_data(
                pil_image, 
                lang='eng',
                config=self.config,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text and calculate statistics
            text_parts = []
            text_blocks = []
            total_confidence = 0
            word_count = 0
            
            for i in range(len(ocr_data['text'])):
                word = ocr_data['text'][i].strip()
                conf = float(ocr_data['conf'][i])
                
                if word and conf > -1:  # Skip empty words and invalid confidence
                    text_parts.append(word)
                    total_confidence += conf
                    word_count += 1
                    
                    # Add text block info
                    text_blocks.append({
                        'text': word,
                        'confidence': conf,
                        'left': ocr_data['left'][i],
                        'top': ocr_data['top'][i],
                        'width': ocr_data['width'][i],
                        'height': ocr_data['height'][i],
                        'block_num': ocr_data['block_num'][i],
                        'line_num': ocr_data['line_num'][i]
                    })
            
            # Calculate overall confidence
            avg_confidence = total_confidence / word_count if word_count > 0 else 0
            self.last_confidence = avg_confidence
            
            # Join text parts with proper spacing
            text = ' '.join(text_parts)
            
            # Clean up the text
            text = text.strip()
            text = ' '.join(text.split())  # Normalize whitespace
            
            # Store statistics
            stats = {
                'word_count': word_count,
                'average_confidence': avg_confidence,
                'config': self.config
            }
            
            logger.info(f"Extracted {word_count} words with {avg_confidence:.1f}% confidence")
            
            return {
                'text': text,
                'confidence': avg_confidence / 100.0,  # Convert to 0-1 scale
                'text_blocks': text_blocks,
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Error extracting text with Tesseract: {str(e)}")
            return {
                'text': '',
                'confidence': 0.0,
                'text_blocks': [],
                'error': str(e)
            }
            
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the last OCR run."""
        return {
            'engine': 'tesseract',
            'confidence': self.last_confidence,
            'processing_time': self.last_processing_time,
            'config': self.config
        } 