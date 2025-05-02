import logging
import os
import json
import csv
import io
from datetime import datetime
from functools import wraps
from uuid import UUID

from flask import (
    Flask, flash, redirect, render_template, request, 
    session, url_for, jsonify, send_from_directory, Response, send_file
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models.expense import User, ExpenseItem, Expense, BalanceSheet
from models.receipt import Receipt
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService
from utils.email_service import EmailService
from utils.receipt_uploader import ReceiptUploader
from utils.scheduler import Scheduler
from routes.receipt_routes import receipt_bp
from routes.report_routes import report_routes
from utils.ocr_controller import OCRController


# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Register blueprints
app.register_blueprint(receipt_bp, url_prefix='/api')
app.register_blueprint(report_routes)

# Initialize storage and utilities
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

storage = JSONStorage(data_dir=os.getenv('DATA_DIR', 'data'))
uploader = ReceiptUploader(upload_dir=os.path.join(UPLOAD_FOLDER, 'receipts'))
receipt_service = ReceiptService(
    storage=storage,
    debug_mode=os.getenv('FLASK_DEBUG', 'True').lower() == 'true',
    debug_output_dir='debug_output',
    debug_ocr_output=True,
    upload_dir=os.path.join(UPLOAD_FOLDER, 'receipts')
)

# Add receipt_service to app config
app.config['receipt_service'] = receipt_service

# Initialize email service
email_service = EmailService(
    smtp_server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
    smtp_port=int(os.getenv('SMTP_PORT', '587')),
    sender_email=os.getenv('SENDER_EMAIL'),
    sender_password=os.getenv('SENDER_PASSWORD'),
    recipients=[os.getenv('RECIPIENT_EMAIL_1'), os.getenv('RECIPIENT_EMAIL_2')]
)

# Initialize scheduler if enabled
if os.getenv('ENABLE_SCHEDULER', 'False').lower() == 'true':
    scheduler = Scheduler(storage, email_service)
    scheduler.start()
else:
    scheduler = None

# Create upload directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'receipts'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'thumbnails'), exist_ok=True)

# Initialize OCR controller
ocr_controller = OCRController()

# Configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')  # Change this in production!

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails'), exist_ok=True)

# Add current year to all templates
@app.context_processor
def inject_now():
    """Add current datetime to all templates."""
    return {'now': datetime.now()}

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_month():
    """Get the current month in YYYY-MM format."""
    return datetime.now().strftime('%Y-%m')

def get_balance_sheet(month):
    """Get the balance sheet for a month, with error handling."""
    try:
        data = storage.get_balance_sheet(month)
        
        # Validate data structure
        if not data:
            # Create empty balance sheet
            return BalanceSheet(month=month, expenses=[])
        
        # Check if expenses field exists
        if not hasattr(data, 'expenses'):
            # Create balance sheet with empty expenses
            return BalanceSheet(month=month, expenses=[])
            
        return data
    except Exception as e:
        logging.error(f"Error loading balance sheet for {month}: {str(e)}")
        # Return empty balance sheet in case of error
        return BalanceSheet(month=month, expenses=[])


@app.route('/')
def index():
    """Main page showing the current month's balance sheet."""
    current_month = get_current_month()
    balance_sheet = get_balance_sheet(current_month)
    summary = balance_sheet.summary()
    
    return render_template(
        'index.html',
        month=current_month,
        summary=summary,
        expenses=balance_sheet.expenses
    )


@app.route('/months')
def list_months():
    """List all months with expense data."""
    months = storage.get_all_months()
    month_data = []
    
    for month in months:
        balance_sheet = storage.get_balance_sheet(month)
        summary = balance_sheet.summary()
        month_data.append({
            'month': month,
            'expense_count': len(balance_sheet.expenses),
            'total_expenses': summary['total_expenses'],
            'balance': summary['balance'],
            'owed_statement': summary['owed_statement']
        })
    
    return render_template('months.html', months=month_data)


@app.route('/month/<month>')
def month_detail(month):
    """Show details for a specific month."""
    try:
        datetime.strptime(month, '%Y-%m')
    except ValueError:
        flash('Invalid month format', 'error')
        return redirect(url_for('index'))
    
    balance_sheet = get_balance_sheet(month)
    summary = balance_sheet.summary()
    
    return render_template(
        'month_detail.html',
        month=month,
        summary=summary,
        expenses=balance_sheet.expenses
    )


@app.route('/expense/new', methods=['GET', 'POST'])
def new_expense():
    """Create a new expense."""
    if request.method == 'POST':
        try:
            # Get form data
            payer = User(request.form['payer'])
            date_str = request.form['date']
            store = request.form['store']
            total_amount = float(request.form['total_amount'])
            
            # Parse date
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Parse items from the form
            items = []
            i = 0
            while f'item_name_{i}' in request.form:
                name = request.form[f'item_name_{i}']
                amount = float(request.form[f'item_amount_{i}'])
                shared = f'item_shared_{i}' in request.form
                
                if name and amount > 0:
                    items.append(ExpenseItem(name=name, amount=amount, shared=shared))
                
                i += 1
            
            if not items:
                flash('Please add at least one item', 'error')
                return redirect(url_for('new_expense'))
            
            # Create base expense
            expense = Expense(
                payer=payer,
                date=date_obj,
                store=store,
                total_amount=total_amount,
                items=items
            )
            
            # Handle receipt upload
            receipt_id = request.form.get('receipt_id')
            if receipt_id:
                # Receipt was already processed via AJAX
                try:
                    receipt = receipt_service.get_receipt(UUID(receipt_id))
                    if receipt:
                        # Attach the pre-processed receipt to the expense
                        expense.attach_receipt(receipt)
                        flash('Receipt attached successfully', 'success')
                except Exception as e:
                    flash(f'Error attaching receipt: {str(e)}', 'warning')
            elif 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename and allowed_file(file.filename):
                    # Process receipt with our unified analyzer
                    from services.receipt_analyzer import UnifiedReceiptAnalyzer
                    
                    # Set up options
                    options = {
                        'store_type_hint': store,  # Use the form's store name as a hint
                    }
                    
                    analyzer = UnifiedReceiptAnalyzer()
                    parsed_receipt, success = analyzer.analyze(file, options)
                    
                    if success:
                        # Convert to Receipt model and save
                        receipt = parsed_receipt.to_receipt_model()
                        receipt_service.save_receipt(receipt)
                        
                        # Attach the receipt to the expense
                        expense.attach_receipt(receipt)
                        flash('Receipt processed successfully', 'success')
                    else:
                        flash(f'Receipt processing partially failed: {parsed_receipt.processing_error}', 'warning')
                        
                        # Still try to use partial results
                        receipt = parsed_receipt.to_receipt_model()
                        receipt_service.save_receipt(receipt)
                        expense.attach_receipt(receipt)
            
            # Calculate shared total
            expense.calculate_shared_total()
            
            # Save the expense
            storage.save_expense(expense)
            
            flash('Expense added successfully', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('new_expense'))
    
    # GET request - show the form
    return render_template('expense/new.html')


@app.route('/expense/<expense_id>')
def expense_detail(expense_id):
    """Show details for a specific expense."""
    expense = storage.get_expense(expense_id)
    if not expense:
        flash('Expense not found', 'error')
        return redirect(url_for('index'))
    
    return render_template('expense_detail.html', expense=expense)


@app.route('/expense/<expense_id>/edit', methods=['GET', 'POST'])
def edit_expense(expense_id):
    """Edit an existing expense."""
    expense = storage.get_expense(expense_id)
    if not expense:
        flash('Expense not found', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            payer = User(request.form['payer'])
            date_str = request.form['date']
            store = request.form['store']
            total_amount = float(request.form['total_amount'])
            
            # Parse date
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Handle receipt upload
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename and allowed_file(file.filename):
                    # Delete old receipt if it exists
                    if expense.receipt:
                        receipt_service.delete_receipt(expense.receipt.id)
                        expense.receipt = None
                    
                    # Process new receipt
                    receipt, success = receipt_service.process_uploaded_file(file)
                    
                    if success:
                        # Attach the receipt to the expense
                        expense.attach_receipt(receipt)
                        flash('Receipt processed successfully', 'success')
                    else:
                        flash(f'Receipt processing failed: {receipt.processing_error}', 'warning')
            
            # Parse items from the form
            items = []
            i = 0
            while f'item_name_{i}' in request.form:
                name = request.form[f'item_name_{i}']
                amount = float(request.form[f'item_amount_{i}'])
                shared = f'item_shared_{i}' in request.form
                
                if name and amount > 0:
                    items.append(ExpenseItem(name=name, amount=amount, shared=shared))
                
                i += 1
            
            if not items:
                flash('Please add at least one item', 'error')
                return redirect(url_for('edit_expense', expense_id=expense_id))
            
            # Update the expense
            expense.payer = payer
            expense.date = date_obj
            expense.store = store
            expense.total_amount = total_amount
            expense.items = items
            expense.shared_total = None  # Reset to recalculate
            
            # Calculate shared total
            expense.calculate_shared_total()
            
            # Save the expense
            storage.update_expense(expense)
            
            flash('Expense updated successfully', 'success')
            return redirect(url_for('expense_detail', expense_id=expense_id))
            
        except Exception as e:
            flash(f'Error updating expense: {str(e)}', 'error')
            return redirect(url_for('edit_expense', expense_id=expense_id))
    
    # GET request - show the form
    return render_template('edit_expense.html', expense=expense)


@app.route('/expense/<expense_id>/delete', methods=['POST'])
def delete_expense(expense_id):
    """Delete an expense."""
    expense = storage.get_expense(expense_id)
    if not expense:
        flash('Expense not found', 'error')
        return redirect(url_for('index'))
    
    # Delete receipt if it exists
    if expense.receipt:
        receipt_service.delete_receipt(expense.receipt.id)
    
    # Delete the expense
    storage.delete_expense(expense.id)
    
    flash('Expense deleted successfully', 'success')
    return redirect(url_for('index'))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files."""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/api/summary/<month>')
def api_summary(month):
    """API endpoint for getting a month's summary."""
    try:
        balance_sheet = get_balance_sheet(month)
        summary = balance_sheet.summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/expense/<expense_id>')
def api_expense(expense_id):
    """API endpoint for getting an expense."""
    expense = storage.get_expense(expense_id)
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404
    
    return jsonify(expense.dict())


@app.route('/api/receipts/upload', methods=['POST'])
def api_upload_receipt():
    """API endpoint to upload and process a receipt."""
    try:
        if 'receipt_image' not in request.files and 'receipt' not in request.files:
            key_used = next((k for k in request.files.keys()), None)
            if key_used:
                # Use whatever file was sent
                file = request.files[key_used]
            else:
                return jsonify({'success': False, 'error': 'No file part'}), 400
        else:
            # Get file using expected keys
            file = request.files.get('receipt_image') or request.files.get('receipt')
            
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
        
        # Get processing options
        options = {
            'force_currency': request.form.get('currency') or request.form.get('force_currency'),
            'store_type_hint': request.form.get('store_override') or request.form.get('store_type_hint'),
            'debug_mode': request.form.get('debug', 'false').lower() == 'true'
        }
            
        # Process the receipt using the unified analyzer
        from services.receipt_analyzer import UnifiedReceiptAnalyzer
        analyzer = UnifiedReceiptAnalyzer(debug_mode=options.get('debug_mode', False))
        parsed_receipt, success = analyzer.analyze(file, options)
        
        # Convert to Receipt model and save
        receipt = parsed_receipt.to_receipt_model()
        
        # Save the receipt to storage
        receipt_service.save_receipt(receipt)
        
        if success:
            # Return the processed receipt data
            return jsonify({
                'success': True,
                'receipt_id': str(receipt.id),
                'store_name': receipt.store_name,
                'date': receipt.date.isoformat() if receipt.date else None,
                'items': [item.dict() for item in receipt.items] if receipt.items else [],
                'total_amount': receipt.total,
                'subtotal_amount': receipt.subtotal,
                'tax_amount': receipt.tax,
                'currency_type': receipt.currency,
                'processing_status': receipt.processing_status,
                'confidence_score': receipt.metadata.get('confidence', 0.0),
                'image_url': receipt.image_url
            })
        else:
            return jsonify({
                'success': False,
                'receipt_id': str(receipt.id),
                'processing_status': receipt.processing_status,
                'error': receipt.processing_error or 'Unknown processing error',
                'partial_data': {
                    'store_name': receipt.store_name,
                    'total_amount': receipt.total,
                    'items_count': len(receipt.items) if receipt.items else 0
                }
            }), 422  # Unprocessable Entity
            
    except Exception as e:
        logging.error(f"Receipt upload error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
        
@app.route('/api/receipts/<receipt_id>', methods=['GET'])
def api_get_receipt(receipt_id):
    """API endpoint to get receipt details."""
    try:
        receipt = receipt_service.get_receipt(UUID(receipt_id))
        if not receipt:
            return jsonify({'success': False, 'error': 'Receipt not found'}), 404
            
        return jsonify({
            'success': True,
            'receipt': {
                'id': str(receipt.id),
                'items': [{'description': item.description, 'amount': item.amount} for item in receipt.items],
                'total_amount': receipt.total_amount,
                'store_name': receipt.store_name,
                'processing_status': receipt.processing_status,
                'image_url': receipt.image_url,
                'raw_text': receipt.raw_text
            }
        })
        
    except Exception as e:
        logging.error(f"Get receipt error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('500.html'), 500


@app.template_filter('format_date')
def format_date(date_obj):
    """Format a date for display."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    return date_obj.strftime('%B %d, %Y')


@app.template_filter('month_name')
def month_name(month_str):
    """Convert YYYY-MM to a readable month name."""
    date_obj = datetime.strptime(month_str, '%Y-%m')
    return date_obj.strftime('%B %Y')


def load_receipt_data():
    """Load all receipt data from test_results directory."""
    receipts = []
    test_results_dir = 'test_results'
    
    if not os.path.exists(test_results_dir):
        return []
        
    for filename in os.listdir(test_results_dir):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(test_results_dir, filename), 'r') as f:
                    data = json.load(f)
                    # Add thumbnail path if it exists
                    image_name = data.get('image_filename', '')
                    thumbnail_path = f'uploads/thumbnails/{image_name}'
                    data['thumbnail_exists'] = os.path.exists(thumbnail_path)
                    data['thumbnail_path'] = thumbnail_path if data['thumbnail_exists'] else None
                    # Add processed time if not present
                    if 'processed_time' not in data:
                        data['processed_time'] = datetime.fromtimestamp(
                            os.path.getctime(os.path.join(test_results_dir, filename))
                        ).strftime('%Y-%m-%d %H:%M:%S')
                    receipts.append(data)
            except Exception as e:
                print(f"Error loading {filename}: {str(e)}")
    
    # Sort by processed time descending
    receipts.sort(key=lambda x: x.get('processed_time', ''), reverse=True)
    return receipts

def get_unique_stores(receipts):
    """Get list of unique store names from receipts."""
    return sorted(list(set(
        r['store']['name']
        for r in receipts
        if isinstance(r.get('store'), dict) and r['store'].get('name')
    )))

@app.route('/receipts')
def receipts():
    """Render the receipts gallery page."""
    receipts_data = [r for r in load_receipt_data() if isinstance(r.get('store'), dict)]
    stores = get_unique_stores(receipts_data)
    return render_template('receipts/gallery.html', 
                         receipts=receipts_data,
                         stores=stores)

@app.route('/receipts/<receipt_id>')
def receipt_detail(receipt_id):
    """Show detailed view of a specific receipt."""
    receipts_data = load_receipt_data()
    receipt = next((r for r in receipts_data if r.get('receipt_id') == receipt_id), None)
    if not receipt:
        flash('Receipt not found', 'error')
        return redirect(url_for('receipts'))
    return render_template('receipts/detail.html', receipt=receipt)

@app.route('/receipts/<receipt_id>/json')
def receipt_json(receipt_id):
    """Download the raw JSON data for a receipt."""
    receipts_data = load_receipt_data()
    receipt = next((r for r in receipts_data if r.get('receipt_id') == receipt_id), None)
    if not receipt:
        return jsonify({'error': 'Receipt not found'}), 404
    
    response = jsonify(receipt)
    response.headers['Content-Disposition'] = f'attachment; filename={receipt_id}.json'
    return response

@app.route('/receipts/<receipt_id>/csv')
def receipt_csv(receipt_id):
    """Export receipt items as CSV."""
    receipts_data = load_receipt_data()
    receipt = next((r for r in receipts_data if r.get('receipt_id') == receipt_id), None)
    if not receipt:
        return jsonify({'error': 'Receipt not found'}), 404
    
    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Item', 'Quantity', 'Unit Price', 'Total', 'Confidence'])
    
    # Write items
    for item in receipt.get('items', []):
        writer.writerow([
            item.get('description', ''),
            item.get('quantity', 1),
            item.get('unit_price', item.get('price', 0)),
            item.get('price', 0),
            item.get('confidence', 0)
        ])
    
    # Write totals
    writer.writerow([])
    writer.writerow(['Subtotal', '', '', receipt.get('totals', {}).get('subtotal', 0), ''])
    writer.writerow(['Tax', '', '', receipt.get('totals', {}).get('tax', 0), ''])
    writer.writerow(['Total', '', '', receipt.get('totals', {}).get('total', 0), ''])
    
    # Prepare response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={receipt_id}.csv'}
    )

@app.route('/receipts/upload', methods=['GET'])
def upload_page():
    return render_template('receipts/upload.html')

@app.route('/receipts/upload', methods=['POST'])
def upload_receipt():
    if 'receipt' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('upload_page'))
    
    file = request.files['receipt']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('upload_page'))

    try:
        # Process the receipt using OCR controller
        receipt_data = ocr_controller.process_receipt(file)
        receipt_id = receipt_data.get('receipt_id')
        
        # Redirect to the receipt detail page
        return redirect(url_for('receipt_detail', receipt_id=receipt_id))
    
    except Exception as e:
        app.logger.error(f"Error processing receipt: {str(e)}")
        flash('Error processing receipt. Please try again.', 'error')
        return redirect(url_for('upload_page'))

@app.route('/receipts/<receipt_id>/reprocess', methods=['POST'])
def reprocess_receipt(receipt_id):
    try:
        # Get the original receipt data
        receipt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{receipt_id}.json")
        if not os.path.exists(receipt_path):
            flash('Receipt not found', 'error')
            return redirect(url_for('receipts'))

        with open(receipt_path, 'r') as f:
            receipt_data = json.load(f)

        # Get the image path from the receipt data
        image_path = receipt_data.get('image_path')
        if not image_path or not os.path.exists(image_path):
            flash('Original receipt image not found', 'error')
            return redirect(url_for('receipt_detail', receipt_id=receipt_id))

        # Reprocess the receipt
        with open(image_path, 'rb') as f:
            new_receipt_data = ocr_controller.process_receipt(f, reprocess=True)
        
        # Redirect to the new receipt detail page
        return redirect(url_for('receipt_detail', receipt_id=new_receipt_data['receipt_id']))

    except Exception as e:
        app.logger.error(f"Error reprocessing receipt: {str(e)}")
        flash('Error reprocessing receipt. Please try again.', 'error')
        return redirect(url_for('receipt_detail', receipt_id=receipt_id))

@app.route('/receipts/<receipt_id>/image')
def receipt_image(receipt_id):
    try:
        # Get the receipt data
        receipt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{receipt_id}.json")
        if not os.path.exists(receipt_path):
            return 'Receipt not found', 404

        with open(receipt_path, 'r') as f:
            receipt_data = json.load(f)

        # Get the image path
        image_path = receipt_data.get('image_path')
        if not image_path or not os.path.exists(image_path):
            return 'Receipt image not found', 404

        # Return the image file
        return send_file(image_path)

    except Exception as e:
        app.logger.error(f"Error serving receipt image: {str(e)}")
        return 'Error serving receipt image', 500

@app.route('/receipts/<receipt_id>/update', methods=['POST'])
def update_receipt(receipt_id):
    """Update receipt data and verification status."""
    try:
        receipts_data = load_receipt_data()
        receipt = next((r for r in receipts_data if r.get('receipt_id') == receipt_id), None)
        if not receipt:
            return jsonify({'error': 'Receipt not found'}), 404

        # Get the receipt file path
        receipt_path = os.path.join('test_results', f"{receipt_id}.json")
        if not os.path.exists(receipt_path):
            return jsonify({'error': 'Receipt file not found'}), 404

        # Update receipt data from form
        updates = request.get_json()
        if 'store' in updates:
            if isinstance(updates['store'], dict):
                receipt['store'].update(updates['store'])
            else:
                receipt['store'] = {'name': updates['store']}
        
        if 'items' in updates:
            receipt['items'] = updates['items']
        
        if 'totals' in updates:
            receipt['totals'].update(updates['totals'])
        
        # Update verification status
        receipt['verified'] = updates.get('verified', False)
        receipt['verified_at'] = datetime.now().isoformat() if updates.get('verified') else None
        receipt['verification_notes'] = updates.get('verification_notes', '')

        # Save updated receipt
        with open(receipt_path, 'w') as f:
            json.dump(receipt, f, indent=4)

        return jsonify({'success': True, 'receipt': receipt})

    except Exception as e:
        app.logger.error(f"Error updating receipt: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'True').lower() == 'true', host='0.0.0.0', port=5003) 