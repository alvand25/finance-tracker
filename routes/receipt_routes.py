from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from uuid import UUID
import json
import os
import time
import traceback
import logging
from typing import Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename
from datetime import datetime

from services.receipt_service import ReceiptService
from models.receipt import Receipt
from utils.receipt_analyzer import ReceiptAnalyzer
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.google_vision_config import GoogleVisionConfig
from utils.ocr_setup import OCRSetup
from utils.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)
receipt_bp = Blueprint('receipts', __name__)

def get_receipt_service():
    """Get the receipt service from the Flask app config."""
    receipt_service = current_app.config.get('receipt_service')
    if receipt_service is None:
        # This should not happen in production, but useful for testing
        logger.warning("Creating new receipt_service instance in routes!")
        from storage.json_storage import JSONStorage
        storage = JSONStorage()
        receipt_service = ReceiptService(storage)
        current_app.config['receipt_service'] = receipt_service
    return receipt_service

def get_ocr_engine() -> Tuple[Optional[GoogleVisionOCR], Dict[str, Any]]:
    """Get configured OCR engine and setup results."""
    try:
        # Use OCRSetup utility to get best available engine
        setup_results = OCRSetup.setup_ocr()
        if setup_results['error']:
            logger.error(f"OCR setup error: {setup_results['error']}")
            return None, setup_results
            
        engine = OCRSetup.get_ocr_engine(setup_results)
        if not engine:
            logger.error("Failed to initialize OCR engine")
            return None, {
                'error': 'Failed to initialize OCR engine',
                'setup_results': setup_results
            }
            
        logger.info(f"Using OCR engine: {setup_results['selected_engine']}")
        return engine, setup_results
        
    except Exception as e:
        error_info = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat()
        }
        logger.error(f"Error initializing OCR engine: {error_info}")
        return None, error_info

def preprocess_image(image_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Preprocess receipt image for better OCR results.
    
    Args:
        image_path: Path to receipt image file
        
    Returns:
        Tuple of (processed_image_path, preprocessing_info)
    """
    try:
        preprocessor = ImagePreprocessor()
        processed_path = preprocessor.preprocess(image_path)
        
        return processed_path, {
            'success': True,
            'original_path': image_path,
            'processed_path': processed_path,
            'preprocessing_steps': preprocessor.get_applied_steps()
        }
        
    except Exception as e:
        error_info = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat()
        }
        logger.error(f"Image preprocessing failed: {error_info}")
        return image_path, {
            'success': False,
            'error': str(e),
            'error_info': error_info
        }

def process_receipt_image(image_path: str) -> Dict[str, Any]:
    """
    Process receipt image and extract data with enhanced error handling and validation.
    
    Args:
        image_path: Path to receipt image file
        
    Returns:
        Dictionary containing extracted receipt data and status
    """
    start_time = time.time()
    debug_info = {
        'start_time': datetime.now().isoformat(),
        'image_path': image_path,
        'steps': []
    }
    
    try:
        # Step 1: Preprocess image
        processed_path, preprocessing_info = preprocess_image(image_path)
        debug_info['preprocessing'] = preprocessing_info
        debug_info['steps'].append({
            'step': 'preprocess_image',
            'success': preprocessing_info['success'],
            'time': time.time() - start_time
        })
        
        # Step 2: Get OCR engine
        engine, setup_results = get_ocr_engine()
        debug_info['ocr_setup'] = setup_results
        debug_info['steps'].append({
            'step': 'get_ocr_engine',
            'success': engine is not None,
            'time': time.time() - start_time
        })
        
        if not engine:
            return {
                'success': False,
                'error': 'OCR engine not available',
                'debug_info': debug_info
            }
            
        # Step 3: Extract receipt data
        step_start = time.time()
        receipt_data = engine.extract_receipt_data(processed_path)
        debug_info['steps'].append({
            'step': 'extract_receipt_data',
            'success': True,
            'time': time.time() - step_start
        })
        
        # Step 4: Validate and enhance results
        step_start = time.time()
        validation_results = validate_receipt_data(receipt_data)
        debug_info['steps'].append({
            'step': 'validate_results',
            'success': True,
            'validation': validation_results,
            'time': time.time() - step_start
        })
        
        # Update receipt data with validation results
        receipt_data.update(validation_results)
        
        # Step 5: Create receipt model
        step_start = time.time()
        try:
            receipt = Receipt(
                store_name=receipt_data.get('store_name', 'Unknown Store'),
                total_amount=receipt_data.get('total', 0),
                items=receipt_data.get('items', []),
                date=receipt_data.get('date'),
                tax_amount=receipt_data.get('tax', 0),
                subtotal_amount=receipt_data.get('subtotal'),
                image_url=image_path,
                confidence_score=receipt_data.get('confidence', 0),
                requires_review=receipt_data.get('requires_review', False),
                ocr_engine=engine.__class__.__name__,
                processing_time=time.time() - start_time,
                validation_notes=receipt_data.get('validation_notes', []),
                debug_info=debug_info
            )
            debug_info['steps'].append({
                'step': 'create_receipt_model',
                'success': True,
                'time': time.time() - step_start
            })
        except Exception as e:
            logger.error(f"Failed to create receipt model: {str(e)}")
            debug_info['steps'].append({
                'step': 'create_receipt_model',
                'success': False,
                'error': str(e),
                'time': time.time() - step_start
            })
            raise
        
        return {
            'success': True,
            'data': receipt.dict(),
            'debug_info': debug_info
        }
        
    except Exception as e:
        error_info = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat()
        }
        logger.error(f"Error processing receipt: {error_info}")
        debug_info['error'] = error_info
        debug_info['total_time'] = time.time() - start_time
        
        return {
            'success': False,
            'error': str(e),
            'debug_info': debug_info
        }

def validate_receipt_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and enhance receipt data.
    
    Args:
        data: Raw receipt data from OCR
        
    Returns:
        Dictionary with validation results and enhanced data
    """
    validation_notes = []
    requires_review = False
    
    # Check confidence
    confidence = data.get('confidence', 0.0)
    if confidence < 0.7:
        validation_notes.append(f"Low confidence score: {confidence:.2f}")
        requires_review = True
    
    # Check items
    items = data.get('items', [])
    if not items:
        validation_notes.append("No items found in receipt")
        requires_review = True
    else:
        # Check for suspicious items
        for item in items:
            if item.get('price', 0) == 0:
                validation_notes.append(f"Item with zero price: {item.get('description', 'Unknown')}")
                requires_review = True
            if item.get('confidence', 0) < 0.5:
                validation_notes.append(f"Low confidence item: {item.get('description', 'Unknown')}")
                requires_review = True
    
    # Check totals
    total = data.get('total', 0)
    subtotal = data.get('subtotal', 0)
    tax = data.get('tax', 0)
    
    if total == 0:
        validation_notes.append("Total amount is zero")
        requires_review = True
    
    if subtotal and tax:
        expected_total = subtotal + tax
        if abs(expected_total - total) > 0.01:
            validation_notes.append(f"Total mismatch: {total} != {subtotal} + {tax}")
            requires_review = True
    
    # Check store name
    store_name = data.get('store_name', '')
    if not store_name or store_name == 'Unknown Store':
        validation_notes.append("Store name not detected")
        requires_review = True
    
    # Check date
    if not data.get('date'):
        validation_notes.append("Date not detected")
        requires_review = True
    
    return {
        'validation_notes': validation_notes,
        'requires_review': requires_review,
        'enhanced_confidence': confidence * (0.8 if requires_review else 1.0)
    }

@receipt_bp.route('/api/receipts/upload', methods=['POST'])
def upload_receipt():
    """
    Upload and process a receipt image with enhanced error handling and validation.
    
    Returns:
        JSON response with processing results or error
    """
    start_time = time.time()
    debug_info = {
        'start_time': datetime.now().isoformat(),
        'request_info': {
            'files': list(request.files.keys()),
            'form_data': dict(request.form)
        }
    }
    
    try:
        # Validate request
        if 'receipt_image' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No receipt image provided',
                'debug_info': debug_info
            }), 400
            
        file = request.files['receipt_image']
        if not file.filename:
            return jsonify({
                'success': False,
                'error': 'No file selected',
                'debug_info': debug_info
            }), 400
            
        # Create upload directory if needed
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'receipts')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save uploaded file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{secure_filename(file.filename)}"
        upload_path = os.path.join(upload_dir, filename)
        file.save(upload_path)
        
        debug_info['file_info'] = {
            'original_name': file.filename,
            'saved_name': filename,
            'path': upload_path
        }
        
        # Process receipt
        result = process_receipt_image(upload_path)
        result['debug_info'].update(debug_info)
        
        # Clean up
        try:
            os.remove(upload_path)
            result['debug_info']['cleanup'] = {'success': True}
        except Exception as e:
            logger.warning(f"Failed to remove temp file {upload_path}: {str(e)}")
            result['debug_info']['cleanup'] = {
                'success': False,
                'error': str(e)
            }
            
        # Add total processing time
        result['debug_info']['total_time'] = time.time() - start_time
        
        if not result['success']:
            logger.error(f"Receipt processing failed: {result['error']}")
            return jsonify(result), 500
            
        logger.info("Receipt processed successfully")
        return jsonify(result)
        
    except Exception as e:
        error_info = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'total_time': time.time() - start_time
        }
        logger.error(f"Error in receipt upload: {error_info}")
        debug_info['error'] = error_info
        
        return jsonify({
            'success': False,
            'error': str(e),
            'debug_info': debug_info
        }), 500

@receipt_bp.route('/receipts/url', methods=['POST'])
def upload_receipt_from_url():
    """Upload and process a receipt from a URL."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400
        
    # Check if progressive processing is requested
    use_progressive = data.get('progressive', False)
        
    # Process the URL
    receipt_service = get_receipt_service()
    receipt, success = receipt_service.upload_receipt_from_url(data['url'], progressive=use_progressive)
    
    if not success and receipt.processing_status == 'failed':
        return jsonify({
            "error": "Receipt processing failed",
            "details": receipt.processing_error
        }), 500
    
    # For progressive processing, indicate that processing will continue
    if success and receipt.processing_status == 'partial':
        return jsonify({
            "receipt_id": str(receipt.id),
            "processing_status": receipt.processing_status,
            "message": "Initial processing complete, detailed processing in progress",
            "total_amount": receipt.total_amount,
            "store_name": receipt.store_name
        }), 202  # Accepted status
        
    # Return the processed receipt data
    return jsonify({
        "receipt_id": str(receipt.id),
        "processing_status": receipt.processing_status,
        "items": [item.dict() for item in receipt.items],
        "total_amount": receipt.total_amount,
        "subtotal_amount": receipt.subtotal_amount,
        "tax_amount": receipt.tax_amount,
        "currency_type": receipt.currency_type,
        "payment_method": receipt.payment_method,
        "confidence_score": receipt.confidence_score
    }), 200

@receipt_bp.route('/receipts/complete/<receipt_id>', methods=['POST'])
def complete_receipt_processing(receipt_id):
    """Complete the detailed processing for a progressively processed receipt."""
    try:
        receipt_id = UUID(receipt_id)
    except ValueError:
        return jsonify({"error": "Invalid receipt ID"}), 400
        
    receipt_service = get_receipt_service()
    receipt = receipt_service.complete_progressive_processing(receipt_id)
    
    if not receipt:
        return jsonify({"error": "Receipt not found"}), 404
        
    if receipt.processing_status == 'failed':
        return jsonify({
            "error": "Receipt processing failed",
            "details": receipt.processing_error
        }), 500
        
    # Return the fully processed receipt data
    return jsonify({
        "receipt_id": str(receipt.id),
        "processing_status": receipt.processing_status,
        "items": [item.dict() for item in receipt.items],
        "total_amount": receipt.total_amount,
        "subtotal_amount": receipt.subtotal_amount,
        "tax_amount": receipt.tax_amount,
        "currency_type": receipt.currency_type,
        "payment_method": receipt.payment_method,
        "confidence_score": receipt.confidence_score
    }), 200
    
@receipt_bp.route('/receipts/<receipt_id>', methods=['GET'])
def get_receipt(receipt_id):
    """Get a receipt by ID."""
    try:
        receipt_id = UUID(receipt_id)
    except ValueError:
        return jsonify({"error": "Invalid receipt ID"}), 400
        
    receipt_service = get_receipt_service()
    receipt = receipt_service.get_receipt(receipt_id)
    
    if not receipt:
        return jsonify({"error": "Receipt not found"}), 404
        
    # Return the receipt data
    return jsonify({
        "receipt_id": str(receipt.id),
        "image_url": receipt.image_url,
        "processed_date": receipt.processed_date.isoformat(),
        "store_name": receipt.store_name,
        "processing_status": receipt.processing_status,
        "processing_error": receipt.processing_error,
        "items": [item.dict() for item in receipt.items],
        "total_amount": receipt.total_amount,
        "subtotal_amount": receipt.subtotal_amount,
        "tax_amount": receipt.tax_amount,
        "raw_text": receipt.raw_text,
        "currency_type": receipt.currency_type,
        "payment_method": receipt.payment_method,
        "confidence_score": receipt.confidence_score,
        "template_id": str(receipt.template_id) if receipt.template_id else None,
        "processing_time": receipt.processing_time
    }), 200
    
@receipt_bp.route('/receipts/<receipt_id>', methods=['DELETE'])
def delete_receipt(receipt_id):
    """Delete a receipt."""
    try:
        receipt_id = UUID(receipt_id)
    except ValueError:
        return jsonify({"error": "Invalid receipt ID"}), 400
        
    receipt_service = get_receipt_service()
    success = receipt_service.delete_receipt(receipt_id)
    
    if not success:
        return jsonify({"error": "Receipt not found or could not be deleted"}), 404
        
    return jsonify({"message": "Receipt deleted successfully"}), 200

@receipt_bp.route('/receipts/templates', methods=['GET'])
def get_templates():
    """Get all receipt templates."""
    receipt_service = get_receipt_service()
    templates = receipt_service.get_receipt_templates()
    
    return jsonify({
        "templates": templates
    }), 200
    
@receipt_bp.route('/receipts/templates/<template_id>', methods=['GET'])
def get_template(template_id):
    """Get a specific template by ID."""
    try:
        template_id = UUID(template_id)
    except ValueError:
        return jsonify({"error": "Invalid template ID"}), 400
        
    receipt_service = get_receipt_service()
    template = receipt_service.get_receipt_template(template_id)
    
    if not template:
        return jsonify({"error": "Template not found"}), 404
        
    return jsonify(template), 200
    
@receipt_bp.route('/receipts/templates/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a receipt template."""
    try:
        template_id = UUID(template_id)
    except ValueError:
        return jsonify({"error": "Invalid template ID"}), 400
        
    receipt_service = get_receipt_service()
    success = receipt_service.delete_template(template_id)
    
    if not success:
        return jsonify({"error": "Template not found or could not be deleted"}), 404
        
    return jsonify({"message": "Template deleted successfully"}), 200

@receipt_bp.route('/receipts/confidence/<receipt_id>', methods=['GET'])
def get_receipt_confidence(receipt_id):
    """Get detailed confidence information for a receipt."""
    try:
        receipt_id = UUID(receipt_id)
    except ValueError:
        return jsonify({"error": "Invalid receipt ID"}), 400
        
    receipt_service = get_receipt_service()
    receipt = receipt_service.get_receipt(receipt_id)
    
    if not receipt:
        return jsonify({"error": "Receipt not found"}), 404
        
    confidence_report = receipt.get_extraction_confidence()
    return jsonify(confidence_report), 200

@receipt_bp.route('/receipts/debug/<receipt_id>', methods=['GET'])
def debug_receipt(receipt_id):
    """Debug endpoint to view receipt text and parsed data"""
    try:
        # Get the file path from receipt service
        receipt_service = ReceiptService()
        receipt = receipt_service.get_receipt(receipt_id)
        
        if not receipt:
            return jsonify({"error": "Receipt not found"}), 404
            
        # Get the image path
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        image_path = os.path.join(upload_folder, receipt['file_path']) if 'file_path' in receipt else None
        
        if not image_path or not os.path.exists(image_path):
            return jsonify({"error": "Receipt image not found"}), 404
            
        # Analyze the receipt directly to get raw text
        analyzer = ReceiptAnalyzer()
        image = analyzer._load_image(image_path)
        preprocessed = analyzer.preprocess_image(image)
        text = analyzer.extract_text(preprocessed)
        
        # Parse with the specialized handler if it's a Costco receipt
        parsed_data = None
        store_name = analyzer._extract_store_name(text)
        if store_name and 'costco' in store_name.lower():
            parsed_data = analyzer.handle_costco_receipt(text, image_path)
        
        # Return debug info
        debug_info = {
            "receipt_id": receipt_id,
            "image_path": image_path,
            "raw_text": text,
            "detected_store": store_name,
            "parsed_data": parsed_data,
            "saved_receipt_data": receipt
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logging.error(f"Error in debug endpoint: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@receipt_bp.route('/api/receipts/debug', methods=['POST'])
@login_required
def debug_receipt_parsing():
    """
    Debug endpoint for receipt parsing with detailed output
    """
    if 'receipt_image' not in request.files:
        return jsonify({'error': 'No receipt image provided'}), 400
        
    file = request.files['receipt_image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    # Store options from the request
    options = {
        'force_currency': request.form.get('force_currency'),
        'store_type_hint': request.form.get('store_type_hint'),
        'use_fallback': request.form.get('use_fallback', 'true').lower() == 'true',
        'debug': True
    }
    
    # Save the uploaded file
    from werkzeug.utils import secure_filename
    import os
    import tempfile
    
    filename = secure_filename(file.filename)
    temp_dir = tempfile.gettempdir()
    image_path = os.path.join(temp_dir, filename)
    file.save(image_path)
    
    # Process the receipt for debugging
    from utils.receipt_analyzer import ReceiptAnalyzer
    analyzer = ReceiptAnalyzer()
    
    # Extract basic text
    receipt_text = analyzer.extract_text(image_path)
    
    # Initialize debug results
    debug_results = {
        'receipt_text': receipt_text,
        'extracted_store': analyzer._extract_store_name(receipt_text),
        'extracted_currency': analyzer._extract_currency(receipt_text),
        'preprocessing': {},
        'parsed_data': {}
    }
    
    # Test preprocessing
    try:
        # Get image dimensions and preprocessing status
        import cv2
        original_image = cv2.imread(image_path)
        if original_image is not None:
            height, width = original_image.shape[:2]
            debug_results['preprocessing']['original_dimensions'] = f"{width}x{height}"
            
            # Test standard preprocessing
            standard_preprocessed = analyzer.preprocess_image(image_path)
            if standard_preprocessed is not None:
                p_height, p_width = standard_preprocessed.shape[:2]
                debug_results['preprocessing']['standard_dimensions'] = f"{p_width}x{p_height}"
                
            # Test enhanced preprocessing
            enhanced_preprocessed = analyzer.preprocess_image(image_path, enhance_for_costco=True)
            if enhanced_preprocessed is not None:
                e_height, e_width = enhanced_preprocessed.shape[:2]
                debug_results['preprocessing']['enhanced_dimensions'] = f"{e_width}x{e_height}"
                
                # Extract text from enhanced image
                enhanced_text = analyzer.extract_text(enhanced_preprocessed)
                debug_results['enhanced_text'] = enhanced_text
    except Exception as e:
        debug_results['preprocessing']['error'] = str(e)
    
    # Test different parsing approaches
    # 1. Standard analyzer
    try:
        standard_result = analyzer.analyze_receipt(receipt_text, image_path)
        debug_results['parsed_data']['standard'] = standard_result
    except Exception as e:
        debug_results['parsed_data']['standard_error'] = str(e)
    
    # 2. Fallback methods
    try:
        fallback_items = analyzer.parse_items_fallback(receipt_text)
        fallback_totals = analyzer.extract_totals_fallback(receipt_text, debug_results['extracted_currency'])
        debug_results['parsed_data']['fallback'] = {
            'items': fallback_items,
            'totals': fallback_totals
        }
    except Exception as e:
        debug_results['parsed_data']['fallback_error'] = str(e)
    
    # 3. Try Costco-specific if name contains "costco"
    if 'costco' in debug_results['extracted_store'].lower() or options.get('store_type_hint') == 'costco':
        try:
            costco_result = analyzer.handle_costco_receipt(receipt_text, image_path)
            debug_results['parsed_data']['costco'] = costco_result
        except Exception as e:
            debug_results['parsed_data']['costco_error'] = str(e)
    
    # Clean up temporary file
    try:
        os.remove(image_path)
    except:
        pass
    
    return jsonify(debug_results), 200

@receipt_bp.route('/api/debug/ocr-status', methods=['GET'])
def get_ocr_status():
    """Get OCR engine status and configuration."""
    try:
        # Check OCR setup
        setup_results = OCRSetup.setup_ocr()
        
        # Test Google Vision
        gv_status = OCRSetup.check_google_vision_setup()
        
        # Test Tesseract
        tesseract_status = OCRSetup.check_tesseract_installation()
        
        return jsonify({
            'setup_results': setup_results,
            'google_vision': gv_status,
            'tesseract': tesseract_status,
            'selected_engine': setup_results.get('selected_engine'),
            'error': setup_results.get('error')
        })
        
    except Exception as e:
        logger.error(f"Error checking OCR status: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500 