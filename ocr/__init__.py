"""OCR module for receipt processing.

This module provides OCR engines for text extraction from receipt images.
Both Google Cloud Vision and Tesseract OCR are supported with a common interface.
"""

from .google_vision_ocr import GoogleVisionOCR
from .tesseract_ocr import TesseractOCR
from .google_vision_config import GoogleVisionConfig

__all__ = ['GoogleVisionOCR', 'TesseractOCR', 'GoogleVisionConfig'] 