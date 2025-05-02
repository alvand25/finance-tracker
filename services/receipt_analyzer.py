"""Unified receipt analysis service to centralize OCR and receipt parsing."""

import os
import logging
from typing import Dict, Any, Optional, Union, Tuple
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime
from werkzeug.datastructures import FileStorage
from PIL import Image
import io

from models.receipt import Receipt
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR
from utils.receipt_analyzer import ReceiptAnalyzer
from ocr.google_vision_config import GoogleVisionConfig

logger = logging.getLogger(__name__)

class ParsedReceipt:
    """Container for parsed receipt data with normalized interface."""
    
    def __init__(self):
        self.id = uuid4()
        self.store_name = None
        self.date = None
        self.items = []
        self.subtotal_amount = None
        self.tax_amount = None
        self.total_amount = None
        self.currency_type = "USD"  # Default
        self.confidence_score = 0.0
        self.confidence_scores = {}
        self.payment_method = None
        self.raw_text = None
        self.processing_status = "pending"
        self.processing_error = None
        self.image_path = None
        self.metadata = {}
        
    def to_receipt_model(self) -> Receipt:
        """Convert parsed data to Receipt model"""
        receipt = Receipt(
            id=self.id,
            image_url=self.image_path,
            store_name=self.store_name,
            date=self.date,
            subtotal=self.subtotal_amount,
            tax=self.tax_amount,
            total=self.total_amount,
            currency=self.currency_type,
            payment_method=self.payment_method,
            items=self.items.copy() if self.items else [],
            raw_text=self.raw_text,
            processing_status=self.processing_status,
            processing_error=self.processing_error,
            metadata={
                'confidence': self.confidence_score,
                'confidence_scores': self.confidence_scores,
                'processing_time': datetime.now().isoformat()
            }
        )
        return receipt

class UnifiedReceiptAnalyzer:
    """Central service for receipt analysis with unified interface."""
    
    def __init__(self, upload_dir: str = 'uploads', debug_mode: bool = False):
        self.upload_dir = upload_dir
        self.debug_mode = debug_mode
        self.preprocessor = ImagePreprocessor(debug_mode=debug_mode)
        self.analyzer = ReceiptAnalyzer(debug_mode=debug_mode)
        
        # Ensure upload directory exists
        os.makedirs(upload_dir, exist_ok=True)
        
        # Initialize OCR engines
        self.ocr = self._setup_ocr()
        
    def _setup_ocr(self):
        """Set up optimal OCR engine based on availability."""
        # Try Google Cloud Vision first
        try:
            config = GoogleVisionConfig()
            if config.is_configured:
                logger.info("Using Google Cloud Vision OCR")
                return GoogleVisionOCR(credentials_path=config.credentials_path)
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Vision OCR: {str(e)}")
            
        # Fall back to Tesseract
        try:
            logger.info("Falling back to Tesseract OCR")
            return TesseractOCR()
        except Exception as e:
            logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
            return None
    
    def analyze(self, file_or_path: Union[FileStorage, str, Path], 
                options: Optional[Dict[str, Any]] = None) -> Tuple[ParsedReceipt, bool]:
        """
        Analyze a receipt from a file or path with unified interface.
        
        Args:
            file_or_path: File upload object or path to image
            options: Processing options like store_hint, currency, etc.
            
        Returns:
            Tuple of (ParsedReceipt, success_boolean)
        """
        parsed = ParsedReceipt()
        options = options or {}
        
        try:
            # Handle different input types
            if isinstance(file_or_path, FileStorage):
                image_data = file_or_path.read()
                filename = file_or_path.filename
                image_path = self._save_file(image_data, filename)
                parsed.image_path = image_path
            elif isinstance(file_or_path, (str, Path)):
                image_path = str(file_or_path)
                parsed.image_path = image_path
                with open(image_path, 'rb') as f:
                    image_data = f.read()
            else:
                raise ValueError(f"Unsupported input type: {type(file_or_path)}")
            
            # Preprocess image
            processed_image = self.preprocessor.preprocess(io.BytesIO(image_data))
            
            # Extract text using OCR
            if self.ocr is None:
                parsed.processing_status = "failed"
                parsed.processing_error = "No OCR engine available"
                return parsed, False
                
            logger.info(f"Extracting text from receipt using {type(self.ocr).__name__}")
            ocr_result = self.ocr.extract_text(processed_image)
            parsed.raw_text = ocr_result["text"]
            confidence = ocr_result.get("confidence", 0.0)
            
            # Analyze receipt text
            store_hint = options.get('store_type_hint')
            logger.info(f"Analyzing receipt text (store hint: {store_hint})")
            
            try:
                results = self.analyzer.analyze_receipt(parsed.raw_text, image_path, store_hint=store_hint)
                logger.debug(f"Analysis results: {results}")
            except Exception as e:
                logger.error(f"Error in analyze_receipt: {str(e)}", exc_info=True)
                parsed.processing_status = "failed"
                parsed.processing_error = f"Receipt analysis failed: {str(e)}"
                return parsed, False
            
            # If store hint provided and no store detected, use the hint
            if store_hint and not results.get('store'):
                results['store'] = store_hint
                logger.debug(f"Using store hint: {store_hint}")
            
            # Populate parsed receipt with analyzed data
            parsed.store_name = results.get('store', None)
            if 'date' in results and results['date']:
                parsed.date = results['date']
            
            parsed.items = results.get('items', [])
            parsed.total_amount = results.get('total', None)
            parsed.tax_amount = results.get('tax', None)
            
            # Estimate subtotal if not directly found
            if parsed.total_amount and parsed.tax_amount:
                parsed.subtotal_amount = round(parsed.total_amount - parsed.tax_amount, 2)
            elif parsed.total_amount and results.get('items'):
                # Sum up items as estimate
                item_total = sum(item.get('amount', 0) for item in results['items'])
                parsed.subtotal_amount = item_total
            
            # Override currency if specified
            if options.get('force_currency'):
                parsed.currency_type = options['force_currency']
            
            # Set payment method if found
            if 'payment_method' in results:
                parsed.payment_method = results['payment_method']
            
            # Set confidence scores
            parsed.confidence_score = confidence
            parsed.confidence_scores = {
                'overall': confidence,
                'store': 0.7 if parsed.store_name else 0.0,
                'total': 0.8 if parsed.total_amount else 0.0,
                'items': 0.6 if parsed.items else 0.0,
                'tax': 0.7 if parsed.tax_amount else 0.0
            }
            
            # Set processing status
            if parsed.total_amount and parsed.store_name:
                # Basic successful parsing
                parsed.processing_status = "completed"
                return parsed, True
            elif parsed.total_amount or parsed.store_name:
                # Partial but acceptable results
                parsed.processing_status = "partial"
                logger.info("Partial success - found total or store name")
                return parsed, True
            else:
                # Insufficient results
                parsed.processing_status = "partial"
                parsed.processing_error = "Could not extract all required fields"
                return parsed, False
                
        except Exception as e:
            logger.error(f"Error analyzing receipt: {str(e)}", exc_info=True)
            parsed.processing_status = "failed"
            parsed.processing_error = str(e)
            return parsed, False
            
    def _save_file(self, image_data: bytes, original_filename: str) -> str:
        """Save uploaded file to disk with unique filename."""
        from werkzeug.utils import secure_filename
        import uuid
        
        # Generate unique filename
        filename = secure_filename(original_filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{str(uuid.uuid4())[:8]}_{filename}"
        filepath = os.path.join(self.upload_dir, unique_filename)
        
        # Save file
        with open(filepath, 'wb') as f:
            f.write(image_data)
            
        return filepath 