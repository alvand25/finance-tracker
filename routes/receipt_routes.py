from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from uuid import UUID
import json
import os
import time
import traceback
import logging

from services.receipt_service import ReceiptService
from models.receipt import Receipt
from utils.receipt_analyzer import ReceiptAnalyzer

receipt_bp = Blueprint('receipts', __name__)

def get_receipt_service():
    """Get the receipt service from the Flask app config."""
    receipt_service = current_app.config.get('receipt_service')
    if receipt_service is None:
        # This should not happen in production, but useful for testing
        print("WARNING: Creating new receipt_service instance in routes!")
        from storage.json_storage import JSONStorage
        storage = JSONStorage()
        receipt_service = ReceiptService(storage)
        current_app.config['receipt_service'] = receipt_service
    return receipt_service

@receipt_bp.route('/api/receipts/upload', methods=['POST'])
@login_required
def upload_receipt():
    """
    Upload and process a receipt image
    """
    try:
        print("Entering upload_receipt endpoint")
        
        if 'receipt_image' not in request.files:
            print("No receipt_image found in request.files")
            return jsonify({'error': 'No receipt image provided'}), 400
        
        file = request.files['receipt_image']
        if file.filename == '':
            print("Empty filename submitted")
            return jsonify({'error': 'No selected file'}), 400
            
        # Get processing options
        options = {
            'force_currency': request.form.get('force_currency'),
            'store_type_hint': request.form.get('store_type_hint'),
            'use_fallback': request.form.get('use_fallback', 'true').lower() == 'true'
        }
        
        print(f"Processing options: {options}")
            
        # Save the uploaded file temporarily
        from werkzeug.utils import secure_filename
        import os
        import tempfile
        import uuid
        
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{filename}")
        file.save(temp_path)
        
        print(f"Saved uploaded file to {temp_path}")
        
        # Process using the receipt service
        from services.receipt_service import ReceiptService
        service = None
        try:
            print("Creating ReceiptService instance")
            from storage.json_storage import JSONStorage
            storage = JSONStorage()
            service = ReceiptService(storage)
            print("ReceiptService created successfully")
        except Exception as e:
            print(f"Error creating ReceiptService: {str(e)}")
            return jsonify({"error": f"Service initialization error: {str(e)}"}), 500
        
        # Process the receipt image
        print("Calling process_receipt_image")
        try:
            processed_receipt = service.process_receipt_image(temp_path, options)
            print(f"Receipt processed with status: {processed_receipt.processing_status}")
        except Exception as e:
            print(f"Error in process_receipt_image: {str(e)}")
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Traceback: {traceback_str}")
            return jsonify({"error": f"Receipt processing error: {str(e)}", "traceback": traceback_str}), 500
        
        # Save the receipt to storage
        from models.receipt import Receipt
        from datetime import datetime
        
        try:
            print("Creating Receipt object")
            receipt = Receipt(image_url=temp_path) 
            receipt.user_id = current_user.id
            receipt.file_path = temp_path  # Temporary path, service will handle permanent storage
            receipt.upload_date = datetime.now()
            receipt.store_name = processed_receipt.merchant_name
            receipt.date = processed_receipt.date
            receipt.processing_status = 'completed' if processed_receipt.processing_status == 'completed' else 'processing'
            
            # Save totals
            receipt.subtotal = processed_receipt.subtotal_amount
            receipt.tax = processed_receipt.tax_amount
            receipt.total = processed_receipt.total_amount
            receipt.currency = processed_receipt.currency_type
            
            # Save metadata
            receipt.metadata = {
                'confidence': processed_receipt.confidence_score,
                'processing_time': datetime.now().isoformat(),
                'store_type_hint': options.get('store_type_hint'),
                'forced_currency': options.get('force_currency')
            }
            
            # Save items if any were extracted
            if processed_receipt.items:
                receipt.items = processed_receipt.items
                
            # Save receipt to database
            print("Saving receipt to database")
            saved_receipt = service.save_receipt(receipt)
            print(f"Receipt saved with ID: {saved_receipt.id}")
        except Exception as e:
            print(f"Error creating or saving receipt: {str(e)}")
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Traceback: {traceback_str}")
            return jsonify({"error": f"Error saving receipt: {str(e)}", "traceback": traceback_str}), 500
        
        # Queue for background processing if only partial results
        if processed_receipt.processing_status != 'completed':
            # Set up a background task for full processing
            # This would integrate with a task queue system like Celery
            pass
                
        # Return success with receipt ID for client to check status
        return jsonify({
            'status': 'success',
            'receipt_id': str(saved_receipt.id),
            'processing_status': processed_receipt.processing_status,
            'store_name': processed_receipt.merchant_name,
            'items_count': len(processed_receipt.items) if processed_receipt.items else 0,
            'currency': processed_receipt.currency_type,
            'total': processed_receipt.total_amount,
            'confidence': processed_receipt.confidence_score
        }), 200
            
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        logging.error(f"Error in upload endpoint: {str(e)}")
        logging.error(traceback_str)
        print(f"Unhandled exception in upload_receipt: {str(e)}")
        print(f"Traceback: {traceback_str}")
        return jsonify({"error": str(e), "traceback": traceback_str}), 500

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