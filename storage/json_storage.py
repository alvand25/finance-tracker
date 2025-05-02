import json
import os
from datetime import date, datetime
from typing import Dict, List, Optional, Union
from uuid import UUID
import logging

from models.expense import Expense, BalanceSheet, ExpenseItem, User
from models.receipt import Receipt
from storage.base import StorageBase


class JSONStorage(StorageBase):
    """Storage implementation using JSON files."""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.receipts_dir = os.path.join(data_dir, "receipts")
        self._ensure_data_dirs()
    
    def _ensure_data_dirs(self) -> None:
        """Ensure that all required directories exist."""
        for directory in [self.data_dir, self.receipts_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
    
    def _get_month_file_path(self, month: str) -> str:
        """Get the file path for a specific month's data."""
        return os.path.join(self.data_dir, f"{month}.json")
    
    def _get_receipt_path(self, receipt_id: UUID) -> str:
        """Get the file path for a specific receipt's data."""
        return os.path.join(self.receipts_dir, f"{str(receipt_id)}.json")
    
    def _get_month_from_date(self, date_obj: date) -> str:
        """Extract month string from a date object."""
        return date_obj.strftime("%Y-%m")
    
    def _read_month_data(self, month: str) -> Dict:
        """Read month data from file, creating an empty file if it doesn't exist."""
        file_path = self._get_month_file_path(month)
        
        if not os.path.exists(file_path):
            # Create empty month data and save it
            data = {"month": month, "expenses": []}
            self._write_month_data(month, data)
            return data
        
        with open(file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # If file is corrupted, create new empty data
                data = {"month": month, "expenses": []}
                self._write_month_data(month, data)
                return data
    
    def _write_month_data(self, month: str, data: Dict) -> None:
        """Write month data to file."""
        file_path = self._get_month_file_path(month)
        
        with open(file_path, "w") as f:
            json.dump(data, f, default=self._json_serialize, indent=2)
    
    def _json_serialize(self, obj: object) -> Union[str, dict]:
        """Custom serializer for objects that aren't JSON serializable."""
        if isinstance(obj, (UUID, date, datetime)):
            return str(obj)
        
        # For pydantic models, use their dict method
        if hasattr(obj, "dict"):
            return obj.dict()
        
        raise TypeError(f"Type {type(obj)} not serializable")
    
    def save_receipt(self, receipt: Receipt) -> None:
        """Save a receipt to storage."""
        file_path = self._get_receipt_path(receipt.id)
        
        with open(file_path, "w") as f:
            json.dump(receipt.dict(), f, default=self._json_serialize, indent=2)
    
    def get_receipt(self, receipt_id: UUID) -> Optional[Receipt]:
        """Retrieve a receipt by ID."""
        file_path = self._get_receipt_path(receipt_id)
        
        if not os.path.exists(file_path):
            return None
            
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
                return Receipt.parse_obj(data)
            except json.JSONDecodeError:
                return None
    
    def delete_receipt(self, receipt_id: UUID) -> None:
        """Delete a receipt by ID."""
        file_path = self._get_receipt_path(receipt_id)
        
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def save_expense(self, expense: Expense) -> None:
        """Save an expense to storage."""
        month = self._get_month_from_date(expense.date)
        data = self._read_month_data(month)
        
        # Calculate shared total before saving
        if expense.shared_total is None:
            expense.calculate_shared_total()
        
        # If there's a receipt attached, save it separately
        if expense.receipt:
            self.save_receipt(expense.receipt)
        
        # Convert the expense to a dict and add to the expenses list
        expense_dict = expense.dict()
        data["expenses"].append(expense_dict)
        
        # Write back to the file
        self._write_month_data(month, data)
    
    def get_expense(self, expense_id: UUID) -> Optional[Expense]:
        """Retrieve an expense by ID."""
        # We need to search all months
        for month in self.get_all_months():
            data = self._read_month_data(month)
            
            for expense_dict in data["expenses"]:
                if UUID(expense_dict["id"]) == expense_id:
                    return Expense.parse_obj(expense_dict)
        
        return None
    
    def update_expense(self, expense: Expense) -> None:
        """Update an existing expense."""
        month = self._get_month_from_date(expense.date)
        data = self._read_month_data(month)
        
        # Calculate shared total before saving
        if expense.shared_total is None:
            expense.calculate_shared_total()
        
        # Find and update the expense
        for i, expense_dict in enumerate(data["expenses"]):
            if UUID(expense_dict["id"]) == expense.id:
                data["expenses"][i] = expense.dict()
                break
        
        # Write back to the file
        self._write_month_data(month, data)
    
    def delete_expense(self, expense_id: UUID) -> None:
        """Delete an expense by ID."""
        # Convert expense_id to string for comparison if it's a UUID
        expense_id_str = str(expense_id)
        
        # We need to search all months
        for month in self.get_all_months():
            data = self._read_month_data(month)
            
            for i, expense_dict in enumerate(data["expenses"]):
                if expense_dict["id"] == expense_id_str:
                    # Remove the expense from the list
                    data["expenses"].pop(i)
                    # Write back to the file
                    self._write_month_data(month, data)
                    return
    
    def get_balance_sheet(self, month: str) -> BalanceSheet:
        """
        Get the balance sheet for a month with defensive error handling.
        
        Args:
            month (str): Month in YYYY-MM format
            
        Returns:
            BalanceSheet: Balance sheet for the month (empty if no data or error)
        """
        try:
            # Make sure the data directory exists
            self._ensure_data_dirs()
            
            # Get the month's expenses
            file_path = self._get_month_file_path(month)
            
            if not os.path.exists(file_path):
                # Month file doesn't exist yet, return empty sheet
                return BalanceSheet(month=month, expenses=[])
            
            # Load the month's data
            with open(file_path, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    logging.error(f"Failed to decode JSON for month {month}")
                    return BalanceSheet(month=month, expenses=[])
            
            # Validate data structure
            if not isinstance(data, dict) or 'expenses' not in data:
                logging.error(f"Invalid data format for month {month}")
                return BalanceSheet(month=month, expenses=[])
            
            # Create balance sheet from data
            expenses = []
            for expense_data in data.get('expenses', []):
                try:
                    # Make sure each expense has required fields
                    if not all(k in expense_data for k in ['id', 'payer', 'date', 'store', 'total_amount']):
                        logging.warning(f"Skipping expense with missing required fields: {expense_data.get('id', 'unknown')}")
                        continue
                    
                    # Create items
                    items = []
                    for item_data in expense_data.get('items', []):
                        if 'name' in item_data and 'amount' in item_data:
                            items.append(ExpenseItem(**item_data))
                    
                    # Standardize date format
                    if isinstance(expense_data['date'], str):
                        try:
                            expense_data['date'] = datetime.strptime(expense_data['date'], '%Y-%m-%d').date()
                        except ValueError:
                            logging.warning(f"Invalid date format in expense {expense_data.get('id', 'unknown')}")
                            continue
                    
                    # Create the expense
                    expense = Expense(
                        id=UUID(expense_data['id']) if isinstance(expense_data['id'], str) else expense_data['id'],
                        payer=User(expense_data['payer']),
                        date=expense_data['date'],
                        store=expense_data['store'],
                        total_amount=float(expense_data['total_amount']),
                        items=items,
                        shared_total=expense_data.get('shared_total')
                    )
                    
                    # Add receipt if present
                    if 'receipt' in expense_data and expense_data['receipt']:
                        receipt_id = expense_data['receipt'].get('id')
                        if receipt_id:
                            receipt = self.get_receipt(UUID(receipt_id) if isinstance(receipt_id, str) else receipt_id)
                            if receipt:
                                expense.receipt = receipt
                    
                    # Recalculate shared total if missing
                    if expense.shared_total is None:
                        expense.calculate_shared_total()
                    
                    expenses.append(expense)
                except Exception as e:
                    logging.warning(f"Error processing expense: {str(e)}")
                    continue
                
            return BalanceSheet(month=month, expenses=expenses)
            
        except Exception as e:
            logging.error(f"Error getting balance sheet for {month}: {str(e)}")
            return BalanceSheet(month=month, expenses=[])
    
    def get_all_months(self) -> List[str]:
        """Get a list of all months that have expenses."""
        # Look for json files in the data directory
        months = []
        
        if not os.path.exists(self.data_dir):
            return months
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".json"):
                # Extract the month from the filename (remove .json extension)
                month = os.path.splitext(filename)[0]
                months.append(month)
        
        # Sort months chronologically
        return sorted(months) 