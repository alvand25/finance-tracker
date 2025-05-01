import logging
import os
from datetime import datetime
from functools import wraps
from uuid import UUID

from flask import (
    Flask, flash, redirect, render_template, request, 
    session, url_for, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models.expense import User, ExpenseItem, Expense
from models.receipt import Receipt
from storage.json_storage import JSONStorage
from services.receipt_service import ReceiptService
from utils.email_service import EmailService
from utils.receipt_uploader import ReceiptUploader
from utils.scheduler import Scheduler
from routes.receipt_routes import receipt_bp


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

# Initialize storage and utilities
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

storage = JSONStorage(data_dir=os.getenv('DATA_DIR', 'data'))
uploader = ReceiptUploader(upload_dir=os.path.join(UPLOAD_FOLDER, 'receipts'))
receipt_service = ReceiptService(storage, upload_dir=os.path.join(UPLOAD_FOLDER, 'receipts'))

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


def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_month():
    """Get the current month in YYYY-MM format."""
    return datetime.now().strftime('%Y-%m')


@app.context_processor
def inject_now():
    """Add current datetime to all templates."""
    return {'now': datetime.now()}


@app.route('/')
def index():
    """Main page showing the current month's balance sheet."""
    current_month = get_current_month()
    balance_sheet = storage.get_balance_sheet(current_month)
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
    
    balance_sheet = storage.get_balance_sheet(month)
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
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename and allowed_file(file.filename):
                    # Process receipt with our service
                    receipt, success = receipt_service.process_uploaded_file(file)
                    
                    if success:
                        # Attach the receipt to the expense
                        expense.attach_receipt(receipt)
                        flash('Receipt processed successfully', 'success')
                    else:
                        flash(f'Receipt processing failed: {receipt.processing_error}', 'warning')
            
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
    return render_template('new_expense.html')


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
        balance_sheet = storage.get_balance_sheet(month)
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
        if 'receipt' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400
            
        file = request.files['receipt']
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
            
        # Process the receipt
        receipt, success = receipt_service.process_uploaded_file(file)
        
        if success:
            # Return the processed receipt data
            return jsonify({
                'success': True,
                'receipt': {
                    'id': str(receipt.id),
                    'items': [{'description': item.description, 'amount': item.amount} for item in receipt.items],
                    'total_amount': receipt.total_amount,
                    'store_name': receipt.store_name,
                    'processing_status': receipt.processing_status,
                    'image_url': receipt.image_url
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': receipt.processing_error or 'Unknown processing error'
            }), 500
            
    except Exception as e:
        logging.error(f"Receipt upload error: {str(e)}")
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


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'True').lower() == 'true', host='0.0.0.0', port=5003) 