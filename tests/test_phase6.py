#!/usr/bin/env python3
"""
End-to-end tests for Phase 6 features of the Finance Tracker.
These tests validate the final implementation of shared expense features,
CSV exports, suspicious items handling, and mobile API functionality.
"""
import os
import sys
import json
import csv
import unittest
import tempfile
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path to allow importing app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, ExportManager
from models.expense import Expense, ExpenseItem
from models.user import User
from models.receipt import Receipt, ReceiptItem

class TestPhase6Features(unittest.TestCase):
    """Test suite for Phase 6 features of the Finance Tracker."""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        
        # Create a temporary directory for test uploads
        self.test_upload_dir = tempfile.mkdtemp()
        self.app.config['UPLOAD_FOLDER'] = self.test_upload_dir
        
        # Sample test data
        self.sample_receipt_data = {
            'store_name': 'Test Store',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 53.97,
            'items': [
                {'description': 'Test Item 1', 'amount': 12.99, 'confidence_score': 0.95},
                {'description': 'Test Item 2', 'amount': 24.99, 'confidence_score': 0.92},
                {'description': 'GarbledItemX789%', 'amount': 15.99, 'confidence_score': 0.45, 'flagged_for_review': True}
            ],
            'confidence_score': 0.85
        }
    
    def tearDown(self):
        """Clean up after each test."""
        # Remove temporary test directory
        import shutil
        if os.path.exists(self.test_upload_dir):
            shutil.rmtree(self.test_upload_dir)
    
    @patch('services.receipt_service.process_receipt_image')
    def test_api_receipt_upload(self, mock_process_receipt):
        """Test the mobile API endpoint for receipt uploads."""
        # Mock the receipt service to return test data
        mock_process_receipt.return_value = (self.sample_receipt_data, self.sample_receipt_data['items'])
        
        # Create test image file
        with tempfile.NamedTemporaryFile(suffix='.jpg') as test_img:
            test_img.write(b'test image content')
            test_img.flush()
            test_img.seek(0)
            
            # Send test request to API
            response = self.client.post(
                '/api/upload-receipt',
                data={'file': (test_img, 'test_receipt.jpg')},
                content_type='multipart/form-data'
            )
            
            # Verify response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertEqual(data['store_name'], 'Test Store')
            self.assertEqual(data['total'], 53.97)
            
            # Verify suspicious item handling
            items = data['items']
            self.assertEqual(len(items), 3)
            self.assertTrue(any(item['flagged_for_review'] for item in items))
            
            # Verify that at least one item is flagged as suspicious
            suspicious_items = [item for item in items if item['flagged_for_review']]
            self.assertEqual(len(suspicious_items), 1)
            self.assertEqual(suspicious_items[0]['description'], 'GarbledItemX789%')
    
    @patch('app.storage.save_expense')
    @patch('app.receipt_service.process_receipt_image')
    def test_shared_expense_creation(self, mock_process_receipt, mock_save_expense):
        """Test the shared expense creation process with selective item sharing."""
        # Mock the receipt service
        mock_process_receipt.return_value = (self.sample_receipt_data, self.sample_receipt_data['items'])
        
        # Create POST data for a new expense with shared/unshared items
        expense_data = {
            'payer': 'Alvand',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'store': 'Test Store',
            'total_amount': '53.97',
            'item_name_0': 'Test Item 1',
            'item_amount_0': '12.99',
            'item_shared_0': 'on',  # This item is shared
            'item_name_1': 'Test Item 2',
            'item_amount_1': '24.99',
            # No item_shared_1 means this is not shared
            'item_name_2': 'GarbledItemX789%',
            'item_amount_2': '15.99',
            'item_shared_2': 'on',  # This suspicious item is shared
            'receipt_data': json.dumps(self.sample_receipt_data)
        }
        
        # Send request to create expense
        response = self.client.post('/expense/new', data=expense_data, follow_redirects=True)
        
        # Verify the response
        self.assertEqual(response.status_code, 200)
        
        # Check that save_expense was called with correct data
        args, kwargs = mock_save_expense.call_args
        expense = args[0]
        
        # Verify expense details
        self.assertEqual(expense.payer.name, 'Alvand')
        self.assertEqual(expense.store, 'Test Store')
        self.assertEqual(expense.total_amount, 53.97)
        
        # Verify items
        self.assertEqual(len(expense.items), 3)
        
        # Check shared status of items
        shared_items = [item for item in expense.items if item.shared]
        non_shared_items = [item for item in expense.items if not item.shared]
        
        self.assertEqual(len(shared_items), 2)
        self.assertEqual(len(non_shared_items), 1)
        
        # Verify the non-shared item is Test Item 2
        self.assertEqual(non_shared_items[0].name, 'Test Item 2')
        self.assertEqual(non_shared_items[0].amount, 24.99)
    
    def test_live_balance_update(self):
        """Test that balance calculations update immediately after expense changes."""
        # This would ideally use a WebSocket client or similar to test real-time updates
        # For simplicity, we'll test the balance calculation logic directly
        
        # Create mock expenses
        alvand = User("Alvand")
        roommate = User("Roommate")
        
        expenses = [
            Expense(
                id="1",
                payer=alvand,
                date=datetime.now().date(),
                store="Grocery",
                total_amount=50.0,
                items=[
                    ExpenseItem(name="Shared Item 1", amount=30.0, shared=True),
                    ExpenseItem(name="Personal Item", amount=20.0, shared=False)
                ]
            ),
            Expense(
                id="2",
                payer=roommate,
                date=datetime.now().date(),
                store="Restaurant",
                total_amount=40.0,
                items=[
                    ExpenseItem(name="Shared Meal", amount=40.0, shared=True)
                ]
            )
        ]
        
        # Calculate shared amounts for each expense
        for expense in expenses:
            expense.calculate_shared_total()
        
        # Mock the storage to return these expenses for the current month
        month_str = datetime.now().strftime('%Y-%m')
        
        with patch('app.storage.get_expenses_for_month', return_value=expenses):
            # Get the balance sheet
            balance_sheet = app.get_balance_sheet(month_str)
            
            # Verify balance calculations
            self.assertEqual(balance_sheet['alvand_paid'], 50.0)
            self.assertEqual(balance_sheet['roommate_paid'], 40.0)
            self.assertEqual(balance_sheet['alvand_share'], 35.0)  # 30/2 + 20 + 40/2
            self.assertEqual(balance_sheet['roommate_share'], 35.0)  # 30/2 + 40/2
            
            # Verification of who_owes calculation
            self.assertEqual(balance_sheet['who_owes'], 'even')
            self.assertEqual(balance_sheet['amount_owed'], 0.0)
    
    def test_suspicious_item_exclusion(self):
        """Test that suspicious items can be excluded from shared expenses."""
        # Create a receipt with a suspicious item
        receipt = Receipt.create_new()
        receipt.store_name = "Test Store"
        receipt.total_amount = 53.97
        receipt.items = [
            ReceiptItem(name="Normal Item", amount=12.99, confidence_score=0.95),
            ReceiptItem(name="GarbledItemX789%", amount=15.99, confidence_score=0.45)
        ]
        
        # Flag the suspicious item
        receipt.items[1].flagged_for_review = True
        receipt.items[1].validation_notes = "Low confidence item"
        
        # Create an expense that excludes the suspicious item
        expense_data = {
            'payer': 'Alvand',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'store': 'Test Store',
            'total_amount': '53.97',
            'item_name_0': 'Normal Item',
            'item_amount_0': '12.99',
            'item_shared_0': 'on',  # This item is shared
            # Note that the suspicious item is not included in the form data
        }
        
        with patch('app.receipt_service.process_uploaded_file', return_value=(receipt, True)):
            with patch('app.storage.save_expense') as mock_save_expense:
                # Send request to create expense
                response = self.client.post('/expense/new', data=expense_data, follow_redirects=True)
                
                # Verify the response
                self.assertEqual(response.status_code, 200)
                
                # Check that save_expense was called with correct data
                args, kwargs = mock_save_expense.call_args
                expense = args[0]
                
                # Verify expense details
                self.assertEqual(len(expense.items), 1)  # Only the normal item is included
                self.assertEqual(expense.items[0].name, "Normal Item")
                self.assertEqual(expense.items[0].amount, 12.99)
    
    def test_csv_export_validation(self):
        """Test that CSV export content matches UI totals and has correct format."""
        # Create mock expenses for testing
        alvand = User("Alvand")
        roommate = User("Roommate")
        
        start_date = datetime.now().date().replace(day=1)  # First day of current month
        expenses = [
            Expense(
                id="1",
                payer=alvand,
                date=start_date,
                store="Grocery",
                total_amount=50.0,
                items=[
                    ExpenseItem(name="Shared Item 1", amount=30.0, shared=True),
                    ExpenseItem(name="Personal Item", amount=20.0, shared=False)
                ]
            ),
            Expense(
                id="2",
                payer=roommate,
                date=start_date + timedelta(days=2),
                store="Restaurant",
                total_amount=40.0,
                items=[
                    ExpenseItem(name="Shared Meal", amount=40.0, shared=True)
                ]
            )
        ]
        
        # Calculate shared totals
        for expense in expenses:
            expense.calculate_shared_total()
        
        # Mock the storage to return these expenses
        month_str = start_date.strftime('%Y-%m')
        
        with patch('app.storage.get_expenses_for_month', return_value=expenses):
            # Create an ExportManager instance
            export_manager = ExportManager()
            
            # Test monthly export
            csv_data = export_manager.export_monthly_data(month_str)
            
            # Parse the CSV data
            reader = csv.DictReader(StringIO(csv_data.getvalue()))
            rows = list(reader)
            
            # Verify row count
            self.assertEqual(len(rows), 2)
            
            # Verify content matches our mock data
            self.assertEqual(rows[0]['Store'], 'Grocery')
            self.assertEqual(float(rows[0]['Amount']), 50.0)
            self.assertEqual(rows[1]['Store'], 'Restaurant')
            self.assertEqual(float(rows[1]['Amount']), 40.0)
            
            # Verify shared amounts
            self.assertEqual(float(rows[0]['Shared Amount']), 30.0)
            self.assertEqual(float(rows[1]['Shared Amount']), 40.0)
            
            # Test summary export
            with patch('app.storage.get_all_months', return_value=[month_str]):
                csv_data = export_manager.export_summary()
                
                # Parse the CSV data
                reader = csv.DictReader(StringIO(csv_data.getvalue()))
                rows = list(reader)
                
                # Verify the summary data
                self.assertEqual(rows[0]['Month'], month_str)
                self.assertEqual(float(rows[0]['Total Expenses']), 90.0)  # 50 + 40
                self.assertEqual(float(rows[0]['Shared Expenses']), 70.0)  # 30 + 40
                self.assertEqual(float(rows[0]['Alvand Paid']), 50.0)
                self.assertEqual(float(rows[0]['Roommate Paid']), 40.0)
    
    @patch('services.receipt_service.process_receipt_image')
    def test_confidence_flag_behavior(self, mock_process_receipt):
        """Test that low confidence items are properly flagged in the UI."""
        # Sample receipt with varying confidence scores
        receipt_data = {
            'store_name': 'Test Store',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 45.97,
            'items': [
                {'description': 'High Confidence Item', 'amount': 10.99, 'confidence_score': 0.95},
                {'description': 'Medium Confidence', 'amount': 19.99, 'confidence_score': 0.75},
                {'description': 'LowUnknown', 'amount': 14.99, 'confidence_score': 0.35}
            ],
            'confidence_score': 0.70
        }
        
        # Mock the receipt service
        mock_process_receipt.return_value = (receipt_data, receipt_data['items'])
        
        # Test the API endpoint directly
        with tempfile.NamedTemporaryFile(suffix='.jpg') as test_img:
            test_img.write(b'test image content')
            test_img.flush()
            test_img.seek(0)
            
            response = self.client.post(
                '/api/upload-receipt',
                data={'file': (test_img, 'test_receipt.jpg')},
                content_type='multipart/form-data'
            )
            
            # Verify response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            
            # Check flagged items
            flagged_items = [item for item in data['items'] if item['flagged_for_review']]
            self.assertEqual(len(flagged_items), 1)
            self.assertEqual(flagged_items[0]['description'], 'LowUnknown')
            self.assertTrue(data['flagged_for_review'])  # Overall receipt is flagged
            
            # Check that high confidence items are not flagged
            non_flagged = [item for item in data['items'] if not item['flagged_for_review']]
            self.assertEqual(len(non_flagged), 2)
            self.assertEqual(non_flagged[0]['description'], 'High Confidence Item')
            self.assertEqual(non_flagged[1]['description'], 'Medium Confidence')

if __name__ == '__main__':
    unittest.main() 