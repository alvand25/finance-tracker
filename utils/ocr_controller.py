import os
import json
import logging
from datetime import datetime
from uuid import uuid4
from PIL import Image
import pytesseract
from werkzeug.utils import secure_filename
from utils.image_preprocessor import ImagePreprocessor

from handlers.handler_registry import HandlerRegistry
from utils.image_preprocessor import preprocess_image

logger = logging.getLogger(__name__)

class OCRController:
    def __init__(self, upload_dir: str = 'uploads/receipts', results_dir='test_results', thumbnail_dir='uploads/thumbnails'):
        self.upload_dir = upload_dir
        self.results_dir = results_dir
        self.thumbnail_dir = thumbnail_dir
        self.handler_registry = HandlerRegistry()
        
        # Ensure directories exist
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        # Initialize preprocessor
        self.preprocessor = ImagePreprocessor(
            debug_mode=False,
            debug_output_dir=os.path.join(upload_dir, 'debug')
        )
    
    def _create_thumbnail(self, image_path, max_size=(300, 300)):
        """Create a thumbnail of the receipt image."""
        try:
            with Image.open(image_path) as img:
                img.thumbnail(max_size)
                thumbnail_path = os.path.join(
                    self.thumbnail_dir,
                    os.path.basename(image_path)
                )
                img.save(thumbnail_path)
                return True
        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return False
    
    def _extract_text(self, image_path):
        """Extract text from image using OCR."""
        try:
            # Preprocess the image
            processed_image = preprocess_image(image_path)
            
            # Run OCR
            ocr_text = pytesseract.image_to_string(processed_image)
            ocr_data = pytesseract.image_to_data(processed_image, output_type=pytesseract.Output.DICT)
            
            # Calculate average confidence
            confidences = [conf for conf in ocr_data['conf'] if conf != -1]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return ocr_text, avg_confidence / 100  # Convert to 0-1 scale
            
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            return "", 0.0
    
    def process_receipt(self, file, reprocess=False):
        """Process a receipt file through the OCR pipeline."""
        try:
            # Generate unique ID if not reprocessing
            receipt_id = str(uuid4()) if not reprocess else file.split('/')[-1].split('.')[0]
            
            # Save file if it's a new upload
            if not reprocess:
                filename = secure_filename(file.filename)
                base, ext = os.path.splitext(filename)
                filename = f"{receipt_id}{ext}"
                file_path = os.path.join(self.upload_dir, filename)
                file.save(file_path)
            else:
                file_path = file
                filename = os.path.basename(file)
            
            # Create thumbnail
            self._create_thumbnail(file_path)
            
            # Extract text and get OCR confidence
            ocr_text, ocr_confidence = self._extract_text(file_path)
            
            # Determine handler and process receipt
            handler = self.handler_registry.get_handler_for_text(ocr_text)
            result = handler.process_receipt(ocr_text)
            
            # Build result dictionary
            result_data = {
                'receipt_id': receipt_id,
                'image_filename': filename,
                'processed_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'store': {
                    'name': result.store_name,
                    'handler_used': handler.__class__.__name__,
                    'confidence': result.store_confidence
                },
                'items': [
                    {
                        'description': item.description,
                        'quantity': item.quantity,
                        'unit_price': item.unit_price,
                        'price': item.price,
                        'confidence': item.confidence
                    }
                    for item in result.items
                ],
                'totals': {
                    'subtotal': result.subtotal,
                    'tax': result.tax,
                    'total': result.total,
                    'confidence': result.totals_confidence
                },
                'confidence': {
                    'overall': result.overall_confidence,
                    'items': result.items_confidence,
                    'totals': result.totals_confidence,
                    'store': result.store_confidence,
                    'ocr': ocr_confidence
                },
                'status': {
                    'success': result.success,
                    'fallback_used': result.fallback_used,
                    'warnings': result.warnings,
                    'errors': result.errors
                },
                'raw_text': ocr_text
            }
            
            # Save result
            result_path = os.path.join(self.results_dir, f"{receipt_id}.json")
            with open(result_path, 'w') as f:
                json.dump(result_data, f, indent=2)
            
            return result_data, True
            
        except Exception as e:
            logger.error(f"Receipt processing error: {e}")
            error_data = {
                'receipt_id': receipt_id if 'receipt_id' in locals() else str(uuid4()),
                'image_filename': filename if 'filename' in locals() else None,
                'processed_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': {
                    'success': False,
                    'errors': [str(e)]
                }
            }
            return error_data, False
    
    def save_confirmed_data(self, receipt_id, confirmed_data):
        """Save user-confirmed receipt data."""
        try:
            # Load original data
            original_path = os.path.join(self.results_dir, f"{receipt_id}.json")
            with open(original_path, 'r') as f:
                original_data = json.load(f)
            
            # Update with confirmed data
            original_data.update(confirmed_data)
            original_data['user_confirmed'] = True
            original_data['confirmation_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Save to confirmed file
            confirmed_path = os.path.join(self.results_dir, f"{receipt_id}_confirmed.json")
            with open(confirmed_path, 'w') as f:
                json.dump(original_data, f, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"Error saving confirmed data: {e}")
            return False 