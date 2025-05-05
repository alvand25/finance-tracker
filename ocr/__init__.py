"""OCR module for receipt processing.

This module provides OCR engines for text extraction from receipt images.
Both Google Cloud Vision and Tesseract OCR are supported with a common interface.
"""

import logging
from typing import Optional, Dict, Any

from .base_ocr import BaseOCR, OCRResult, OCRError, OCREngineType
from .google_vision_ocr import GoogleVisionOCR
from .tesseract_ocr import TesseractOCR
from .google_vision_config import GoogleVisionConfig

logger = logging.getLogger(__name__)

def create_ocr_engine(
    engine_type: OCREngineType = OCREngineType.GOOGLE_VISION,
    credentials_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    tesseract_config: Optional[str] = None,
    use_fallback: bool = True
) -> BaseOCR:
    """
    Create an OCR engine with optional fallback.
    
    Args:
        engine_type: Primary OCR engine to use
        credentials_path: Path to Google Vision credentials
        tesseract_cmd: Path to Tesseract executable
        tesseract_config: Custom Tesseract configuration
        use_fallback: Whether to use fallback engine
        
    Returns:
        Configured OCR engine
        
    Raises:
        OCRError: If engine creation fails
    """
    try:
        # Create fallback engine first if needed
        fallback = None
        if use_fallback:
            if engine_type == OCREngineType.GOOGLE_VISION:
                try:
                    fallback = TesseractOCR(
                        tesseract_cmd=tesseract_cmd,
                        config=tesseract_config
                    )
                    logger.info("Created Tesseract fallback engine")
                except Exception as e:
                    logger.warning(f"Failed to create Tesseract fallback: {str(e)}")
            else:
                try:
                    fallback = GoogleVisionOCR(credentials_path=credentials_path)
                    logger.info("Created Google Vision fallback engine")
                except Exception as e:
                    logger.warning(f"Failed to create Google Vision fallback: {str(e)}")
        
        # Create primary engine
        if engine_type == OCREngineType.GOOGLE_VISION:
            engine = GoogleVisionOCR(
                credentials_path=credentials_path,
                fallback_engine=fallback
            )
            logger.info("Created Google Vision primary engine")
        else:
            engine = TesseractOCR(
                tesseract_cmd=tesseract_cmd,
                config=tesseract_config,
                fallback_engine=fallback
            )
            logger.info("Created Tesseract primary engine")
            
        return engine
        
    except Exception as e:
        raise OCRError(
            f"Failed to create OCR engine: {str(e)}",
            engine_type,
            {'error_type': 'engine_creation'}
        )

def get_engine_status(engine: BaseOCR) -> Dict[str, Any]:
    """Get status information about an OCR engine."""
    status = {
        'engine_type': engine.engine_type.value,
        'has_fallback': bool(engine.fallback_engine)
    }
    
    if isinstance(engine, GoogleVisionOCR):
        status.update(engine.config.get_status())
    elif isinstance(engine, TesseractOCR):
        status.update(engine.get_debug_info())
        
    return status

__all__ = ['GoogleVisionOCR', 'TesseractOCR', 'GoogleVisionConfig'] 