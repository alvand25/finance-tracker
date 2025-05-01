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


class ReceiptService:
    """Service for handling receipt operations, including OCR processing."""
    
    def __init__(self, storage: JSONStorage, upload_dir: str = "uploads/receipts"):
        """
        Initialize ReceiptService.
        
        Args:
            storage: JSON storage instance for receipts
            upload_dir: Directory to store uploaded receipt images
        """
        self.storage = storage
        self.upload_dir = upload_dir
        self._ensure_upload_dir()
        
        # Initialize template registry
        self.template_registry = TemplateRegistry(storage_path="data/templates", create_built_in=True)
        
        # Cache for processed receipts
        self.processing_cache = {}
    
    def _ensure_upload_dir(self) -> None:
        """Ensure the upload directory exists."""
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
            
    def _save_receipt_image(self, receipt_id: UUID, image_data: bytes) -> str:
        """Save the receipt image to disk and return the file path."""
        # Create a unique filename
        filename = f"{receipt_id}.jpg"
        filepath = os.path.join(self.upload_dir, filename)
        
        # Save the image
        with open(filepath, 'wb') as f:
            f.write(image_data)
            
        return filepath
    
    def process_receipt(self, file_path: str, user_id: str = None, db_session: Session = None, analyzer: Optional[ReceiptAnalyzer] = None) -> Dict:
        """Process a receipt image file to extract information.

        Args:
            file_path (str): Path to the receipt image file
            user_id (str, optional): User ID for associating the receipt. Defaults to None.
            db_session (Session, optional): Database session. Defaults to None.
            analyzer (ReceiptAnalyzer, optional): Receipt analyzer instance. Defaults to None.

        Returns:
            Dict: Receipt data extracted from the image
        """
        logger.info(f"Processing receipt: {file_path}")
        receipt_data = {}
            
        # Create an analyzer if one wasn't provided
        if analyzer is None:
            analyzer = ReceiptAnalyzer()
        
        try:
            # Extract text using OCR
            receipt_text = analyzer.extract_text(file_path)
            
            # Try to identify the store from the receipt text
            store_name = analyzer._extract_store_name(receipt_text)
            logger.info(f"Detected store name: {store_name}")
            
            # Check if this is a Costco receipt
            if store_name and "costco" in store_name.lower():
                logger.info("Using specialized Costco receipt handler")
                parsed_data = analyzer.handle_costco_receipt(receipt_text, file_path)
                if parsed_data and parsed_data.get('items'):
                    logger.info(f"Costco handler extracted {len(parsed_data.get('items', []))} items")
                    receipt_data = parsed_data
            # Check if this is a Trader Joe's receipt
            elif store_name and "trader" in store_name.lower() and "joe" in store_name.lower():
                logger.info("Using specialized Trader Joe's receipt handler")
                parsed_data = analyzer.handle_trader_joes_receipt(receipt_text, file_path)
                if parsed_data and parsed_data.get('items'):
                    logger.info(f"Trader Joe's handler extracted {len(parsed_data.get('items', []))} items")
                    receipt_data = parsed_data
            # Check if this is an H Mart receipt
            elif store_name and ("h mart" in store_name.lower() or "hmart" in store_name.lower()):
                logger.info("Using specialized H Mart receipt handler")
                parsed_data = analyzer.handle_hmart_receipt(receipt_text, file_path)
                if parsed_data and parsed_data.get('items'):
                    logger.info(f"H Mart handler extracted {len(parsed_data.get('items', []))} items")
                    receipt_data = parsed_data
            # Check if this is a Key Food receipt
            elif store_name and "key food" in store_name.lower():
                logger.info("Using specialized Key Food receipt handler")
                parsed_data = analyzer.handle_key_food_receipt(receipt_text, file_path)
                if parsed_data and parsed_data.get('items'):
                    logger.info(f"Key Food handler extracted {len(parsed_data.get('items', []))} items")
                    receipt_data = parsed_data
            
            # If no specialized handler matched or they failed, try template matching
            if not receipt_data:
                # Use template registry to find matching template
                template_registry = TemplateRegistry()
                template = template_registry.find_matching_template(receipt_text)
                
                if template:
                    logger.info(f"Using template: {template.__class__.__name__}")
                    parsed_data = template.parse(receipt_text)
                    if parsed_data:
                        receipt_data = parsed_data
                else:
                    # Fall back to generic receipt analysis
                    logger.info("No template matched, using generic analyzer")
                    parsed_data = analyzer.analyze_receipt(receipt_text, file_path)
                    if parsed_data:
                        receipt_data = parsed_data
            
            # Create receipt object and save to database if user_id and db_session provided
            if receipt_data and user_id and db_session:
                receipt = Receipt(
                    user_id=user_id,
                    store_name=receipt_data.get('store', ''),
                    date=receipt_data.get('date'),
                    total=receipt_data.get('total'),
                    subtotal=receipt_data.get('subtotal'),
                    tax=receipt_data.get('tax'),
                    currency=receipt_data.get('currency', 'USD'),
                    payment_method=receipt_data.get('payment_method', ''),
                    image_path=file_path,
                    processing_status="processed" if receipt_data.get('confidence', {}).get('overall', 0) > 0.5 else "needs_review"
                )
                
                # Add receipt to database
                db_session.add(receipt)
                db_session.flush()  # Get the receipt ID
                
                # Create receipt items
                for item_data in receipt_data.get('items', []):
                    item = ReceiptItem(
                        receipt_id=receipt.id,
                        description=item_data.get('description', ''),
                        quantity=item_data.get('quantity', 1),
                        price=item_data.get('price', 0),
                        category=item_data.get('category', '')
                    )
                    db_session.add(item)
                
                db_session.commit()
            
            return receipt_data
        
        except Exception as e:
            logger.error(f"Error processing receipt: {str(e)}")
            if db_session:
                db_session.rollback()
            receipt_data = {
                'error': str(e),
                'processing_status': 'failed'
            }
            return receipt_data
    
    def process_receipt_progressive(self, receipt: Receipt, image_data: bytes) -> Tuple[Receipt, bool]:
        """
        Process a receipt with progressive enhancement.
        
        This approach gives quick initial results and then improves them with more detailed analysis.
        
        Args:
            receipt: Receipt object to update
            image_data: Raw receipt image data
            
        Returns:
            Tuple of (updated receipt, is_complete)
        """
        # Quick phase: Fast initial processing
        try:
            # Record the start time
            start_time = time.time()
            
            # Save the image if needed
            if not receipt.image_url or not os.path.exists(receipt.image_url):
                filepath = self._save_receipt_image(receipt.id, image_data)
                receipt.image_url = filepath
            
            # Set status to quick processing
            receipt.processing_status = "processing_quick"
            
            # Save to storage
            self.storage.save_receipt(receipt)
            
            # Quick OCR with basic features
            processed_image = ReceiptAnalyzer.preprocess_image(image_data)
            text = ReceiptAnalyzer.extract_text(processed_image)
            
            # Quick parsing
            totals = ReceiptAnalyzer.extract_receipt_totals(text)
            
            # Set basic information
            receipt.raw_text = text
            receipt.total_amount = totals.get('total')
            receipt.store_name = totals.get('store_name')
            receipt.transaction_date = totals.get('date')
            receipt.processing_status = "partial"
            receipt.processing_time = time.time() - start_time
            
            # Save partial results
            self.storage.save_receipt(receipt)
            
            # Add to processing cache for detailed analysis
            self.processing_cache[str(receipt.id)] = {
                'image_data': image_data,
                'start_time': start_time
            }
            
            return receipt, False
        
        except Exception as e:
            receipt.mark_processing_failed(f"Fast processing failed: {str(e)}")
            self.storage.save_receipt(receipt)
            return receipt, True
    
    def complete_progressive_processing(self, receipt_id: UUID) -> Optional[Receipt]:
        """
        Complete the detailed phase of progressive processing.
        
        Args:
            receipt_id: ID of the receipt to complete processing
            
        Returns:
            Fully processed receipt or None if not found
        """
        receipt = self.get_receipt(receipt_id)
        if not receipt:
            return None
            
        # Check if we have the image data in cache
        cache_key = str(receipt_id)
        if cache_key not in self.processing_cache:
            # Try to load the image from disk
            try:
                with open(receipt.image_url, 'rb') as f:
                    image_data = f.read()
            except Exception:
                receipt.mark_processing_failed("Cannot find receipt image for detailed processing")
                self.storage.save_receipt(receipt)
                return receipt
        else:
            image_data = self.processing_cache[cache_key]['image_data']
            
        # Full detailed processing
        try:
            receipt.processing_status = "processing_detailed"
            self.storage.save_receipt(receipt)
            
            # Analyze with all features enabled
            items, totals, raw_text = ReceiptAnalyzer.analyze_receipt(image_data, use_layout=True)
            
            # Update receipt with complete analysis
            receipt.update_from_analysis(items, totals, raw_text)
            
            # Remove from cache
            if cache_key in self.processing_cache:
                del self.processing_cache[cache_key]
                
            # Save the fully processed receipt
            self.storage.save_receipt(receipt)
            return receipt
            
        except Exception as e:
            receipt.mark_processing_failed(f"Detailed processing failed: {str(e)}")
            self.storage.save_receipt(receipt)
            return receipt
            
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
                receipt, is_complete = self.process_receipt_progressive(receipt, image_data)
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
            self.storage.save_receipt(receipt)
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
                receipt, is_complete = self.process_receipt_progressive(receipt, image_data)
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
            self.storage.save_receipt(receipt)
            return receipt, False
            
    def get_receipt(self, receipt_id: UUID) -> Optional[Receipt]:
        """Get a receipt by ID."""
        return self.storage.get_receipt(receipt_id)
    
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
        self.storage.delete_receipt(receipt_id)
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
            processed_receipt = self.process_receipt_image(image_path, options)
            
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
            self.storage.save_receipt(receipt)
            
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
                    self.storage.save_receipt(receipt)
            except Exception as update_err:
                logging.error(f"Failed to update receipt status: {str(update_err)}")
            
            return {'status': 'error', 'message': str(e)}

    def process_receipt_image(self, image_path: str, options: Dict[str, Any] = None) -> Receipt:
        """
        Process a receipt image to extract items and total amounts.
        
        Args:
            image_path: Path to the receipt image
            options: Optional processing options:
                - force_currency: Override detected currency
                - store_type_hint: Hint for the store type
                - use_fallback: Whether to use fallback methods if standard methods fail
                - template_id: Use a specific template for parsing
                
        Returns:
            A Receipt object containing the extracted data
        """
        # Initialize options with defaults if not provided
        if options is None:
            options = {}
            
        # Set up logging
        logging.info(f"Processing receipt image: {image_path}")
        logging.info(f"Processing options: {options}")
        
        analyzer = ReceiptAnalyzer()
        
        # Create a Receipt object
        receipt = Receipt()
        receipt.processing_status = "processing"
        receipt.image_path = image_path
        
        try:
            # Extract text from the image
            receipt_text = analyzer.extract_text(image_path)
            if not receipt_text:
                receipt.mark_processing_failed("Failed to extract text from receipt image")
                return receipt
                
            receipt.raw_text = receipt_text
            
            # Extract store name
            store_name = analyzer._extract_store_name(receipt_text)
            receipt.merchant_name = store_name
            
            # Check if we should handle this as a Costco receipt
            is_costco = analyzer.is_costco_receipt(receipt_text) or \
                        (store_name and 'costco' in store_name.lower()) or \
                        options.get('store_type_hint') == 'costco'
            
            if is_costco:
                logging.info("Detected Costco receipt, using specialized handler")
                costco_result = analyzer.handle_costco_receipt(receipt_text, image_path)
                
                if costco_result and costco_result.get('items'):
                    logging.info(f"Costco handler extracted {len(costco_result.get('items', []))} items")
                    
                    # Convert the items to ReceiptItem objects
                    items = []
                    for item_data in costco_result.get('items', []):
                        item = ReceiptItem(
                            description=item_data.get('description', ''),
                            amount=item_data.get('price', 0),
                            quantity=item_data.get('quantity', 1),
                            confidence_score=0.8,
                            item_type="product"
                        )
                        items.append(item)
                    
                    receipt.items = items
                    receipt.subtotal_amount = costco_result.get('subtotal')
                    receipt.tax_amount = costco_result.get('tax')
                    receipt.total_amount = costco_result.get('total')
                    receipt.currency_type = costco_result.get('currency', 'USD')
                    receipt.payment_method = costco_result.get('payment_method')
                    
                    # Update confidence scores
                    confidence = costco_result.get('confidence', {})
                    receipt.confidence_scores = {
                        'store': confidence.get('store', 0.8),
                        'currency': confidence.get('currency', 0.8),
                        'items': confidence.get('items', 0.7),
                        'subtotal': confidence.get('subtotal', 0.7) if receipt.subtotal_amount else 0,
                        'tax': confidence.get('tax', 0.7) if receipt.tax_amount else 0,
                        'total': confidence.get('total', 0.7) if receipt.total_amount else 0
                    }
                    
                    # Calculate overall confidence
                    if receipt.confidence_scores:
                        receipt.confidence_score = sum(receipt.confidence_scores.values()) / len(receipt.confidence_scores)
                    
                    # Update processing status
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                    else:
                        receipt.processing_status = "failed"
                        receipt.processing_error = "Failed to extract essential receipt data"
                        
                    return receipt
            
            # Check if we should handle this as a Trader Joe's receipt
            is_trader_joes = (store_name and ('trader' in store_name.lower() and 'joe' in store_name.lower())) or \
                           options.get('store_type_hint') == 'trader_joes'
            
            if is_trader_joes:
                logging.info("Detected Trader Joe's receipt, using specialized handler")
                trader_joes_result = analyzer.handle_trader_joes_receipt(receipt_text, image_path)
                
                if trader_joes_result and trader_joes_result.get('items'):
                    logging.info(f"Trader Joe's handler extracted {len(trader_joes_result.get('items', []))} items")
                    
                    # Convert the items to ReceiptItem objects
                    items = []
                    for item_data in trader_joes_result.get('items', []):
                        item = ReceiptItem(
                            description=item_data.get('description', ''),
                            amount=item_data.get('price', 0),
                            quantity=item_data.get('quantity', 1),
                            confidence_score=0.8,
                            item_type="product"
                        )
                        items.append(item)
                    
                    receipt.items = items
                    receipt.subtotal_amount = trader_joes_result.get('subtotal')
                    receipt.tax_amount = trader_joes_result.get('tax')
                    receipt.total_amount = trader_joes_result.get('total')
                    receipt.currency_type = trader_joes_result.get('currency', 'USD')
                    receipt.payment_method = trader_joes_result.get('payment_method')
                    receipt.transaction_date = trader_joes_result.get('date')
                    
                    # Update confidence scores
                    confidence = 0.8  # Default confidence
                    if isinstance(trader_joes_result.get('confidence'), dict):
                        confidence_dict = trader_joes_result.get('confidence', {})
                        receipt.confidence_scores = {
                            'store': confidence_dict.get('store', 0.8),
                            'currency': confidence_dict.get('currency', 0.8),
                            'items': confidence_dict.get('items', 0.7),
                            'subtotal': confidence_dict.get('subtotal', 0.7) if receipt.subtotal_amount else 0,
                            'tax': confidence_dict.get('tax', 0.7) if receipt.tax_amount else 0,
                            'total': confidence_dict.get('total', 0.7) if receipt.total_amount else 0
                        }
                        # Calculate overall confidence
                        if receipt.confidence_scores:
                            receipt.confidence_score = sum(receipt.confidence_scores.values()) / len(receipt.confidence_scores)
                    else:
                        # If confidence is a single value
                        receipt.confidence_score = trader_joes_result.get('confidence', 0.7)
                    
                    # Update processing status
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                    else:
                        receipt.processing_status = "failed"
                        receipt.processing_error = "Failed to extract essential receipt data"
                        
                    return receipt
            
            # Check if we should handle this as an H Mart receipt
            is_hmart = (store_name and ('h mart' in store_name.lower() or 'hmart' in store_name.lower())) or \
                      options.get('store_type_hint') == 'hmart'
            
            if is_hmart:
                logging.info("Detected H Mart receipt, using specialized handler")
                hmart_result = analyzer.handle_hmart_receipt(receipt_text, image_path)
                
                if hmart_result and hmart_result.get('items'):
                    logging.info(f"H Mart handler extracted {len(hmart_result.get('items', []))} items")
                    
                    # Convert the items to ReceiptItem objects
                    items = []
                    for item_data in hmart_result.get('items', []):
                        item = ReceiptItem(
                            description=item_data.get('description', ''),
                            amount=item_data.get('price', 0),
                            quantity=item_data.get('quantity', 1),
                            confidence_score=0.8,
                            item_type="product"
                        )
                        items.append(item)
                    
                    receipt.items = items
                    receipt.subtotal_amount = hmart_result.get('subtotal')
                    receipt.tax_amount = hmart_result.get('tax')
                    receipt.total_amount = hmart_result.get('total')
                    receipt.currency_type = hmart_result.get('currency', 'USD')
                    receipt.payment_method = hmart_result.get('payment_method')
                    
                    # Update confidence scores
                    confidence = hmart_result.get('confidence', {})
                    receipt.confidence_scores = {
                        'store': confidence.get('store', 0.8),
                        'currency': confidence.get('currency', 0.8),
                        'items': confidence.get('items', 0.7),
                        'subtotal': confidence.get('subtotal', 0.7) if receipt.subtotal_amount else 0,
                        'tax': confidence.get('tax', 0.7) if receipt.tax_amount else 0,
                        'total': confidence.get('total', 0.7) if receipt.total_amount else 0
                    }
                    
                    # Calculate overall confidence
                    if receipt.confidence_scores:
                        receipt.confidence_score = sum(receipt.confidence_scores.values()) / len(receipt.confidence_scores)
                    
                    # Update processing status
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                    else:
                        receipt.processing_status = "failed"
                        receipt.processing_error = "Failed to extract essential receipt data"
                        
                    return receipt
            
            # Check if we should handle this as a Key Food receipt
            is_key_food = (store_name and 'key food' in store_name.lower()) or \
                      options.get('store_type_hint') == 'key_food'
            
            if is_key_food:
                logging.info("Detected Key Food receipt, using specialized handler")
                key_food_result = analyzer.handle_key_food_receipt(receipt_text, image_path)
                
                if key_food_result and key_food_result.get('items'):
                    logging.info(f"Key Food handler extracted {len(key_food_result.get('items', []))} items")
                    
                    # Convert the items to ReceiptItem objects
                    items = []
                    for item_data in key_food_result.get('items', []):
                        item = ReceiptItem(
                            description=item_data.get('description', ''),
                            amount=item_data.get('price', 0),
                            quantity=item_data.get('quantity', 1),
                            confidence_score=0.8,
                            item_type="product"
                        )
                        items.append(item)
                    
                    receipt.items = items
                    receipt.subtotal_amount = key_food_result.get('subtotal')
                    receipt.tax_amount = key_food_result.get('tax')
                    receipt.total_amount = key_food_result.get('total')
                    receipt.currency_type = key_food_result.get('currency', 'USD')
                    receipt.payment_method = key_food_result.get('payment_method')
                    
                    # Update confidence scores
                    confidence = key_food_result.get('confidence', {})
                    receipt.confidence_scores = {
                        'store': confidence.get('store', 0.8),
                        'currency': confidence.get('currency', 0.8),
                        'items': confidence.get('items', 0.7),
                        'subtotal': confidence.get('subtotal', 0.7) if receipt.subtotal_amount else 0,
                        'tax': confidence.get('tax', 0.7) if receipt.tax_amount else 0,
                        'total': confidence.get('total', 0.7) if receipt.total_amount else 0
                    }
                    
                    # Calculate overall confidence
                    if receipt.confidence_scores:
                        receipt.confidence_score = sum(receipt.confidence_scores.values()) / len(receipt.confidence_scores)
                    
                    # Update processing status
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                    else:
                        receipt.processing_status = "failed"
                        receipt.processing_error = "Failed to extract essential receipt data"
                        
                    return receipt
            
            # Check if a specific template was requested
            if options.get('template_id'):
                template_id = options['template_id']
                logging.info(f"Using template with ID: {template_id}")
                
                try:
                    # Try to get the template from the registry
                    template = self.template_registry.get_template(template_id)
                    
                    if template:
                        # Apply the template for parsing
                        parsed_data = template.parse(receipt_text)
                        
                        if parsed_data:
                            # Update receipt with parsed data
                            receipt.items = parsed_data.get('items', [])
                            receipt.subtotal_amount = parsed_data.get('subtotal')
                            receipt.tax_amount = parsed_data.get('tax')
                            receipt.total_amount = parsed_data.get('total')
                            receipt.currency_type = parsed_data.get('currency')
                            receipt.confidence_score = parsed_data.get('confidence', 0.7)
                            
                            if receipt.items and receipt.total_amount:
                                receipt.processing_status = "completed"
                            elif receipt.total_amount:
                                receipt.processing_status = "partial" 
                            else:
                                # Template failed, but we'll continue with other methods
                                logging.warning(f"Template {template_id} failed to extract data")
                        else:
                            logging.warning(f"Template {template_id} returned no data")
                    else:
                        logging.warning(f"Template with ID {template_id} not found")
                except Exception as e:
                    logging.error(f"Error applying template: {str(e)}")
            
            # If we haven't successfully processed the receipt yet, try standard methods
            if receipt.processing_status == "processing":
                # Try to match with a template first
                template_match_result = analyzer.match_template(receipt_text)
                
                if template_match_result and template_match_result.get('items'):
                    # Template matched successfully
                    logging.info(f"Template matched: {template_match_result.get('template_name')}")
                    
                    receipt.items = template_match_result.get('items', [])
                    receipt.subtotal_amount = template_match_result.get('subtotal')
                    receipt.tax_amount = template_match_result.get('tax')
                    receipt.total_amount = template_match_result.get('total')
                    receipt.currency_type = template_match_result.get('currency')
                    receipt.confidence_score = template_match_result.get('confidence', 0.7)
                    
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                else:
                    # No template matched, use generic analyzer
                    logging.info("No template matched, using generic analyzer")
                    
                    # Check if user overrode currency
                    force_currency = options.get('force_currency')
                    
                    # If user forced a currency, adjust the analyzer's behavior
                    if force_currency:
                        logging.info(f"Forcing currency to: {force_currency}")
                        analyzed_data = analyzer.analyze_receipt(receipt_text, image_path, force_currency)
                    else:
                        analyzed_data = analyzer.analyze_receipt(receipt_text, image_path)
                    
                    # Update receipt with analyzed data
                    receipt.items = analyzed_data.get('items', [])
                    receipt.subtotal_amount = analyzed_data.get('subtotal')
                    receipt.tax_amount = analyzed_data.get('tax')
                    receipt.total_amount = analyzed_data.get('total')
                    receipt.currency_type = analyzed_data.get('currency')
                    
                    # Handle confidence scores
                    if 'confidence_scores' in analyzed_data:
                        receipt.confidence_scores = analyzed_data['confidence_scores']
                        if receipt.confidence_scores:
                            receipt.confidence_score = sum(receipt.confidence_scores.values()) / len(receipt.confidence_scores)
                    else:
                        receipt.confidence_score = analyzed_data.get('confidence', 0.5)
                    
                    # Update processing status
                    if receipt.items and receipt.total_amount:
                        receipt.processing_status = "completed"
                    elif receipt.total_amount:
                        receipt.processing_status = "partial"
                    else:
                        # Try fallback methods if enabled
                        if options.get('use_fallback', True):
                            logging.info("Using fallback methods for extraction")
                            
                            # Try to extract items with fallback
                            if not receipt.items:
                                store_type = options.get('store_type_hint')
                                fallback_items = analyzer.parse_items_fallback(receipt_text, store_type)
                                
                                if fallback_items:
                                    logging.info(f"Fallback extracted {len(fallback_items)} items")
                                    # Convert to ReceiptItem objects
                                    items = []
                                    for item_data in fallback_items:
                                        item = ReceiptItem(
                                            description=item_data.get('description', ''),
                                            amount=item_data.get('price', 0),
                                            quantity=item_data.get('quantity', 1),
                                            confidence_score=0.6,
                                            item_type="product"
                                        )
                                        items.append(item)
                                    
                                    receipt.items = items
                            
                            # Try to extract totals with fallback
                            if not receipt.total_amount:
                                fallback_totals = analyzer.extract_totals_fallback(
                                    receipt_text, 
                                    receipt.currency_type or options.get('force_currency'),
                                    options.get('store_type_hint')
                                )
                                
                                if fallback_totals:
                                    logging.info("Fallback extracted totals")
                                    receipt.subtotal_amount = fallback_totals.get('subtotal')
                                    receipt.tax_amount = fallback_totals.get('tax')
                                    receipt.total_amount = fallback_totals.get('total')
                                    
                                    # If currency was extracted and not already set
                                    if fallback_totals.get('currency') and not receipt.currency_type:
                                        receipt.currency_type = fallback_totals.get('currency')
                            
                            # Update processing status again after fallbacks
                            if receipt.items and receipt.total_amount:
                                receipt.processing_status = "completed"
                                receipt.confidence_score = 0.6  # Lower confidence for fallback methods
                            elif receipt.total_amount:
                                receipt.processing_status = "partial"
                                receipt.confidence_score = 0.5
                            else:
                                receipt.processing_status = "failed"
                                receipt.processing_error = "Failed to extract essential receipt data"
                        else:
                            receipt.processing_status = "failed"
                            receipt.processing_error = "Failed to extract essential receipt data"
        
        except Exception as e:
            logging.error(f"Error processing receipt: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            receipt.mark_processing_failed(str(e))
        
        logging.info(f"Receipt processing completed with status: {receipt.processing_status}")
        if receipt.items:
            logging.info(f"Extracted {len(receipt.items)} items")
        
        return receipt 