import os
import time
from typing import Optional, Tuple, Union, List, Dict, Any, TypeVar
from uuid import UUID
import requests
from io import BytesIO
from datetime import datetime
import re
import logging
import traceback
import json
from PIL import Image
from werkzeug.utils import secure_filename
import uuid

# Make SQLAlchemy optional
try:
    from sqlalchemy.orm import Session
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    # Define a TypeVar as a placeholder for Session
    Session = TypeVar('Session')

from models.receipt import Receipt
from models.receipt_template import ReceiptTemplate
from utils.receipt_analyzer import ReceiptAnalyzer
from storage.json_storage import JSONStorage
from services.template_registry import TemplateRegistry
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR
from config.google_vision_config import GoogleVisionConfig
from utils.module_utils import stub_missing_module

# Try to import StorageManager, create stub if not found
try:
    from storage.storage_manager import StorageManager
except ModuleNotFoundError:
    logger.warning("StorageManager not found, creating stub")
    stub_missing_module("storage", "storage_manager")
    from storage.storage_manager import StorageManager

logger = logging.getLogger(__name__)

class ReceiptService:
    """
    Service for processing receipts using OCR and analysis.
    """
    
    def __init__(self,
                 storage: Optional[StorageManager] = None,
                 debug_mode: bool = False,
                 debug_output_dir: str = 'debug_output',
                 debug_ocr_output: bool = False,
                 ocr_engine: Optional[str] = None,
                 upload_dir: str = 'uploads'):
        """
        Initialize the receipt service.
        
        Args:
            storage: Storage manager instance
            debug_mode: Enable debug output
            debug_output_dir: Directory for debug output
            debug_ocr_output: Save OCR output to files
            ocr_engine: Force specific OCR engine ('google_vision' or 'tesseract')
            upload_dir: Directory path for storing uploaded receipt images
        """
        self.storage = storage or StorageManager()
        self.debug_mode = debug_mode
        self.debug_output_dir = debug_output_dir
        self.debug_ocr_output = debug_ocr_output
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)
        
        # Set up OCR engine
        self.ocr = self._setup_ocr(ocr_engine)
        
        # Create preprocessor and analyzer
        self.preprocessor = ImagePreprocessor(
            debug_mode=debug_mode,
            debug_output_dir=debug_output_dir
        )
        self.analyzer = ReceiptAnalyzer()
        
        # Create debug directory if needed
        if debug_mode and not os.path.exists(debug_output_dir):
            os.makedirs(debug_output_dir)
            
        # Initialize template registry
        self.template_registry = TemplateRegistry(storage_path="data/templates", create_built_in=True)
        
        # Cache for processed receipts
        self.processing_cache = {}
    
    def _setup_ocr(self, preferred_engine: Optional[str] = None) -> Any:
        """Set up OCR engine based on configuration and preference."""
        if preferred_engine == 'tesseract':
            logger.info("Using Tesseract OCR as preferred engine")
            try:
                return TesseractOCR()
            except Exception as e:
                logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
                return None
                
        # Try Google Cloud Vision first (unless Tesseract was explicitly requested)
        if preferred_engine != 'tesseract':
            try:
                config = GoogleVisionConfig()
                if config.is_configured:
                    logger.info("Using Google Cloud Vision OCR")
                    config.validate()
                    return GoogleVisionOCR(credentials_path=config.credentials_path)
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Vision OCR: {str(e)}")
                
        # Fall back to Tesseract if Google Vision not available
        if not preferred_engine:  # Only fall back if no specific engine was requested
            logger.info("Falling back to Tesseract OCR")
            try:
                return TesseractOCR()
            except Exception as e:
                logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
                
        return None
        
    def _ensure_upload_dir(self) -> None:
        """Ensure the upload directory exists."""
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
            
    def _save_receipt_image(self, image_file) -> str:
        """Save the receipt image and return the file path."""
        filename = secure_filename(image_file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{str(uuid.uuid4())[:8]}_{filename}"
        filepath = os.path.join(self.upload_dir, unique_filename)
        
        image_file.save(filepath)
        return filepath
    
    def process_receipt(self, image_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a receipt image.
        
        Args:
            image_path: Path to receipt image
            options: Processing options
                - store_hint: Expected store name
                - ocr_engine: Override OCR engine
                
        Returns:
            Dictionary containing extracted receipt information
        """
        try:
            # Override OCR engine if specified in options
            if options and 'ocr_engine' in options:
                ocr = options['ocr_engine']
            else:
                ocr = self.ocr
                
            # Preprocess image
            processed_image = self.preprocessor.preprocess(image_path)
            
            # Extract text using OCR
            if ocr is not None:
                logger.info("Using configured OCR engine")
                ocr_result = ocr.extract_text(processed_image)
                text = ocr_result["text"]
                confidence = ocr_result["confidence"]
                text_blocks = ocr_result.get("text_blocks", [])
            else:
                logger.info("No OCR engine available")
                return {
                    'error': 'No OCR engine available',
                    'image_path': image_path
                }
                
            # Save OCR text for debugging
            if self.debug_ocr_output:
                debug_text_path = os.path.join(
                    self.debug_output_dir,
                    f'ocr_{os.path.basename(image_path)}.txt'
                )
                with open(debug_text_path, 'w') as f:
                    f.write(text)
                logger.info(f"Saved OCR text to {debug_text_path}")
                
            # Analyze receipt
            store_hint = options.get('store_hint') if options else None
            results = self.analyzer.analyze_receipt(text, image_path, store_hint=store_hint)
            
            # Add OCR metadata
            results['ocr_metadata'] = {
                'engine': 'google_vision' if isinstance(ocr, GoogleVisionOCR) else 'tesseract',
                'confidence': confidence,
                'text_blocks': text_blocks,
                'processing_time': getattr(ocr, 'last_processing_time', 0)
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing receipt {image_path}: {str(e)}")
            return {
                'error': str(e),
                'image_path': image_path
            }
            
    def process_receipt_progressive(self, image_path: str, task_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start progressive processing of a receipt.
        
        Args:
            image_path: Path to receipt image
            task_id: Unique task identifier
            options: Processing options
            
        Returns:
            Initial results and task ID
        """
        try:
            # Create task data
            task_data = {
                'id': task_id,
                'image_path': image_path,
                'status': 'processing',
                'created_at': datetime.now().isoformat(),
                'options': options or {}
            }
            
            # Save task data
            task_file = os.path.join(self.debug_output_dir, f'task_{task_id}.json')
            with open(task_file, 'w') as f:
                json.dump(task_data, f, indent=2)
                
            # Start processing
            logger.info(f"Starting progressive processing for task {task_id}")
            results = self.process_receipt(image_path, options)
            
            # Update task data
            task_data.update({
                'status': 'completed' if 'error' not in results else 'error',
                'results': results,
                'completed_at': datetime.now().isoformat()
            })
            
            # Save updated task data
            with open(task_file, 'w') as f:
                json.dump(task_data, f, indent=2)
                
            return {
                'task_id': task_id,
                'status': task_data['status'],
                'initial_results': results
            }
            
        except Exception as e:
            logger.error(f"Error starting progressive processing for {image_path}: {str(e)}")
            return {
                'task_id': task_id,
                'status': 'error',
                'error': str(e)
            }
            
    def complete_progressive_processing(self, task_id: str) -> Dict[str, Any]:
        """
        Complete progressive processing of a receipt.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Final processing results
        """
        try:
            # Load task data
            task_file = os.path.join(self.debug_output_dir, f'task_{task_id}.json')
            if not os.path.exists(task_file):
                raise ValueError(f"Task {task_id} not found")
                
            with open(task_file, 'r') as f:
                task_data = json.load(f)
                
            # Check if task is already completed
            if task_data.get('status') == 'completed':
                return task_data.get('results', {})
                
            # Get initial results
            results = task_data.get('results', {})
            
            # Perform additional processing if needed
            # (e.g., enhanced analysis, validation, etc.)
            
            # Update task data
            task_data.update({
                'status': 'completed',
                'results': results,
                'completed_at': datetime.now().isoformat()
            })
            
            # Save final task data
            with open(task_file, 'w') as f:
                json.dump(task_data, f, indent=2)
                
            return results
            
        except Exception as e:
            logger.error(f"Error completing progressive processing for task {task_id}: {str(e)}")
            return {
                'error': str(e),
                'task_id': task_id
            }
    
    def process_uploaded_file(self, file_storage, progressive: bool = False) -> Tuple[Receipt, bool]:
        """
        Process an uploaded file object (typically from Flask's request.files).
        
        Args:
            file_storage: File storage object from Flask (request.files['file'])
            progressive: Whether to use progressive processing
            
        Returns:
            Tuple of (Receipt, success_boolean)
        """
        try:
            # Read the file data
            image_data = file_storage.read()
            
            # Create a new receipt
            filename = file_storage.filename if hasattr(file_storage, 'filename') else "uploaded_receipt"
            receipt = Receipt(image_url=filename)
            
            # Process the receipt
            if progressive:
                receipt, is_complete = self.process_receipt_progressive(receipt, filename, image_data)
                return receipt, not is_complete  # Return True if processing is continuing
            else:
                processed_receipt = self.process_receipt(receipt, image_data)
                return processed_receipt, True
            
        except Exception as e:
            # Create a failed receipt
            receipt = Receipt(
                image_url="upload_failed",
                processing_status="failed",
                processing_error=str(e)
            )
            self.json_storage.save_receipt(receipt)
            return receipt, False
    
    def _extract_raw_text(self, image_data: bytes) -> str:
        """Extract raw text from the receipt image."""
        try:
            # Preprocess the image
            preprocessed = ReceiptAnalyzer.preprocess_image(image_data)
            # Extract text
            return ReceiptAnalyzer.extract_text(preprocessed)
        except Exception as e:
            return f"Error extracting text: {str(e)}"
    
    def _extract_store_name(self, receipt: Receipt) -> None:
        """Attempt to extract store name from receipt text."""
        if not receipt.raw_text:
            return
            
        # Simple heuristic: look at the first few lines for store name
        lines = receipt.raw_text.strip().split('\n')
        if lines:
            # Often the store name is in the first line
            # Filter out common receipt headers
            first_lines = [line.strip() for line in lines[:3] if len(line.strip()) > 2]
            if first_lines:
                receipt.store_name = first_lines[0]
                
    def upload_receipt_from_url(self, url: str, progressive: bool = False) -> Tuple[Receipt, bool]:
        """Create a receipt from a URL, download and process the image."""
        try:
            # Download the image
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            image_data = response.content
            
            # Create a new receipt
            receipt = Receipt(image_url=url)
            
            # Process the receipt
            if progressive:
                receipt, is_complete = self.process_receipt_progressive(receipt, url, image_data)
                return receipt, not is_complete  # Return True if processing is continuing
            else:
                processed_receipt = self.process_receipt(receipt, image_data)
                return processed_receipt, True
                
        except Exception as e:
            # Create a failed receipt
            receipt = Receipt(
                image_url=url,
                processing_status="failed",
                processing_error=str(e)
            )
            self.json_storage.save_receipt(receipt)
            return receipt, False
            
    def get_receipt(self, receipt_id: UUID) -> Optional[Receipt]:
        """Get a receipt by ID."""
        return self.json_storage.get_receipt(receipt_id)
    
    def get_receipt_templates(self) -> List[Dict[str, Any]]:
        """Get all receipt templates."""
        templates = self.template_registry.get_all_templates()
        return [template.to_dict() for template in templates]
    
    def get_receipt_template(self, template_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a specific template by ID."""
        template = self.template_registry.get_template(template_id)
        if template:
            return template.to_dict()
        return None
        
    def delete_receipt(self, receipt_id: UUID) -> bool:
        """Delete a receipt and its image file."""
        receipt = self.get_receipt(receipt_id)
        if not receipt:
            return False
            
        # Delete the image file if it's stored locally
        if receipt.image_url and os.path.exists(receipt.image_url):
            try:
                os.remove(receipt.image_url)
            except Exception:
                pass  # Continue even if file deletion fails
                
        # Delete from storage
        self.json_storage.delete_receipt(receipt_id)
        return True
    
    def delete_template(self, template_id: UUID) -> bool:
        """Delete a receipt template."""
        return self.template_registry.delete_template(template_id) 

    def process_receipt_by_id(self, receipt_id: str) -> Dict[str, Any]:
        """Process a receipt by its ID"""
        try:
            receipt = self.get_receipt(receipt_id)
            if not receipt:
                return {'status': 'error', 'message': f'Receipt with ID {receipt_id} not found'}
            
            image_path = receipt.file_path
            if not os.path.exists(image_path):
                return {'status': 'error', 'message': f'Receipt image not found at {image_path}'}
            
            # Analyze the receipt
            logging.info(f"Processing receipt {receipt_id} with image {image_path}")
            
            # Set up options
            options = {}
            
            # Apply store-specific options
            store_name = receipt.store_name
            if store_name:
                # Store-specific currency overrides
                store_overrides = {
                    'costco': 'USD',
                    'walmart': 'USD',
                    'target': 'USD',
                    'tesco': 'GBP',
                    'sainsbury': 'GBP',
                    'carrefour': 'EUR',
                }
                
                for store_key, currency in store_overrides.items():
                    if store_key.lower() in store_name.lower():
                        options['force_currency'] = currency
                        options['store_type_hint'] = store_key
                        logging.info(f"Applied store-specific options for {store_key}")
                        break
            
            # Use template if available
            if receipt.template_id:
                options['template_id'] = receipt.template_id
            
            # Process the receipt using our enhanced method
            processed_receipt = self.process_receipt(image_path, options)
            
            # Update the database receipt with processed data
            receipt.store_name = processed_receipt.merchant_name
            receipt.date = processed_receipt.date
            receipt.subtotal = processed_receipt.subtotal_amount
            receipt.tax = processed_receipt.tax_amount
            receipt.total = processed_receipt.total_amount
            receipt.currency = processed_receipt.currency_type
            receipt.payment_method = processed_receipt.payment_method
            receipt.items = processed_receipt.items if processed_receipt.items else []
            receipt.raw_text = processed_receipt.raw_text
            
            receipt.metadata = {
                'confidence': processed_receipt.confidence_score,
                'confidence_scores': processed_receipt.confidence_scores,
                'processing_time': datetime.now().isoformat(),
                'processing_status': processed_receipt.processing_status
            }
            
            if processed_receipt.processing_status == "completed":
                receipt.processing_status = 'processed'
            elif processed_receipt.processing_status == "partial":
                receipt.processing_status = 'partial'
            else:
                receipt.processing_status = 'failed'
                receipt.metadata['error'] = processed_receipt.processing_error
            
            # Save the updated receipt
            self.json_storage.save_receipt(receipt)
            
            # Prepare response
            return {
                'status': 'success' if receipt.processing_status in ['processed', 'partial'] else 'error',
                'receipt_id': receipt_id,
                'processing_status': receipt.processing_status,
                'items_count': len(receipt.items),
                'confidence': processed_receipt.confidence_score
            }
            
        except Exception as e:
            logging.error(f"Error processing receipt {receipt_id}: {str(e)}", exc_info=True)
            # Update receipt status to failed
            try:
                receipt = self.get_receipt(receipt_id)
                if receipt:
                    receipt.processing_status = 'failed'
                    receipt.metadata = {
                        'error': str(e),
                        'processing_time': datetime.now().isoformat()
                    }
                    self.json_storage.save_receipt(receipt)
            except Exception as update_err:
                logging.error(f"Failed to update receipt status: {str(update_err)}")
            
            return {'status': 'error', 'message': str(e)} 

    def save_receipt_image(self, file) -> str:
        """
        Save an uploaded receipt image.
        
        Args:
            file: File object from request.files
            
        Returns:
            str: Path to the saved image file
        """
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{str(uuid.uuid4())[:8]}_{filename}"
        file_path = os.path.join(self.upload_dir, unique_filename)
        file.save(file_path)
        return file_path

    def create_receipt(self, data: Dict[str, Any], image_path: Optional[str] = None) -> str:
        """
        Create a new receipt record.
        
        Args:
            data: Receipt data dictionary
            image_path: Optional path to the receipt image file
            
        Returns:
            str: ID of the created receipt
        """
        receipt_id = str(uuid.uuid4())
        receipt_data = {
            'receipt_id': receipt_id,
            'created_at': datetime.now().isoformat(),
            'image_path': image_path,
            **data
        }
        self.storage.save(receipt_id, receipt_data)
        return receipt_id

    def get_receipt(self, receipt_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a receipt by its ID.
        
        Args:
            receipt_id: ID of the receipt to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Receipt data if found, None otherwise
        """
        return self.storage.get(receipt_id)

    def list_receipts(self) -> List[Dict[str, Any]]:
        """
        Get a list of all receipts.
        
        Returns:
            List[Dict[str, Any]]: List of receipt data dictionaries
        """
        return self.storage.list_all()

    def update_receipt(self, receipt_id: str, data: Dict[str, Any]) -> bool:
        """
        Update a receipt's data.
        
        Args:
            receipt_id: ID of the receipt to update
            data: New receipt data
            
        Returns:
            bool: True if successful, False otherwise
        """
        existing_data = self.get_receipt(receipt_id)
        if not existing_data:
            return False
        
        updated_data = {**existing_data, **data}
        self.storage.save(receipt_id, updated_data)
        return True

    def delete_receipt(self, receipt_id: str) -> bool:
        """
        Delete a receipt and its associated image.
        
        Args:
            receipt_id: ID of the receipt to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        receipt_data = self.get_receipt(receipt_id)
        if not receipt_data:
            return False
        
        # Delete the image file if it exists
        image_path = receipt_data.get('image_path')
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError as e:
                print(f"Error deleting image file: {e}")
        
        return self.storage.delete(receipt_id)

    def get_receipt_image_path(self, receipt_id: str) -> Optional[str]:
        """
        Get the path to a receipt's image file.
        
        Args:
            receipt_id: ID of the receipt
            
        Returns:
            Optional[str]: Path to the image file if it exists, None otherwise
        """
        receipt_data = self.get_receipt(receipt_id)
        if not receipt_data:
            return None
        
        image_path = receipt_data.get('image_path')
        if not image_path or not os.path.exists(image_path):
            return None
            
        return image_path 