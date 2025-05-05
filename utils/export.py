"""
Export utilities for expense data.

This module provides functionality to export expense data to various formats,
such as CSV, for downloading and sharing.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Dict, List, Any, Union, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

class ExportManager:
    """Manages the export of expense data to various formats."""
    
    def __init__(self, storage=None):
        """
        Initialize the ExportManager.
        
        Args:
            storage: Optional storage backend for retrieving data
        """
        self.storage = storage
        
    def generate_csv(self, data: Dict[str, Any], export_type: str = 'monthly') -> io.StringIO:
        """
        Generate a CSV file from expense data.
        
        Args:
            data: Dictionary containing expense data to export
            export_type: Type of export ('monthly', 'summary', etc.)
            
        Returns:
            StringIO object containing CSV data
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        if export_type == 'monthly':
            self._generate_monthly_csv(writer, data)
        elif export_type == 'summary':
            self._generate_summary_csv(writer, data)
        else:
            raise ValueError(f"Unknown export type: {export_type}")
            
        output.seek(0)
        return output
        
    def _generate_monthly_csv(self, writer: csv.writer, data: Dict[str, Any]) -> None:
        """
        Generate a CSV file for monthly expense data.
        
        Args:
            writer: CSV writer object
            data: Dictionary containing monthly expense data
        """
        # Write the header
        writer.writerow([
            'Date', 'Store', 'Item', 'Amount', 'Payer', 'Shared', 
            'Confidence', 'Receipt ID', 'Flagged'
        ])
        
        # Format: YYYY-MM
        month = data.get('month', datetime.now().strftime('%Y-%m'))
        
        # Write the expenses
        expenses = data.get('expenses', [])
        for expense in expenses:
            # Skip expenses without items
            if not expense.get('items'):
                continue
                
            # Basic expense info
            date = expense.get('date', '')
            store = expense.get('store', '')
            payer = expense.get('payer', '')
            receipt_id = expense.get('receipt_id', '')
            
            # Write each item as a row
            for item in expense.get('items', []):
                # Get item data with defaults for missing fields
                item_name = item.get('name', '')
                amount = item.get('amount', 0.0)
                shared = 'Yes' if item.get('shared', False) else 'No'
                confidence = item.get('confidence_score', '')
                flagged = 'Yes' if item.get('flagged_for_review', False) else 'No'
                
                writer.writerow([
                    date, store, item_name, amount, payer, shared, 
                    confidence, receipt_id, flagged
                ])
        
        # Add a blank row
        writer.writerow([])
        
        # Add summary section if available
        summary = data.get('summary', {})
        if summary:
            writer.writerow(['Summary'])
            writer.writerow(['Total Expenses', summary.get('total_expenses', 0.0)])
            writer.writerow(['Balance', summary.get('balance', 0.0)])
            
            # Add who owes who statement
            owed_statement = summary.get('owed_statement', '')
            if owed_statement:
                writer.writerow(['Balance Statement', owed_statement])
                
    def _generate_summary_csv(self, writer: csv.writer, data: Dict[str, Any]) -> None:
        """
        Generate a CSV file for expense summary data.
        
        Args:
            writer: CSV writer object
            data: Dictionary containing summary expense data
        """
        # Write the header
        writer.writerow(['Month', 'Total Expenses', 'Balance', 'Statement'])
        
        # Write data for each month
        months = data.get('months', [])
        for month_data in months:
            month = month_data.get('month', '')
            total = month_data.get('total_expenses', 0.0)
            balance = month_data.get('balance', 0.0)
            statement = month_data.get('owed_statement', '')
            
            writer.writerow([month, total, balance, statement])
            
        # Add overall summary if available
        overall = data.get('overall', {})
        if overall:
            writer.writerow([])
            writer.writerow(['Overall Summary'])
            writer.writerow(['Total Expenses', overall.get('total_expenses', 0.0)])
            writer.writerow(['Net Balance', overall.get('net_balance', 0.0)])
        
    def export_monthly_data(self, month: str) -> io.StringIO:
        """
        Export data for a specific month.
        
        Args:
            month: Month in YYYY-MM format
            
        Returns:
            StringIO object containing CSV data
        """
        if not self.storage:
            raise ValueError("Storage is required for monthly export")
        
        # Get the balance sheet data for the month
        try:
            balance_sheet = self.storage.get_balance_sheet(month)
            
            # Convert to dictionary representation
            data = {
                'month': month,
                'expenses': [expense.to_dict() for expense in balance_sheet.expenses],
                'summary': balance_sheet.summary()
            }
            
            return self.generate_csv(data, 'monthly')
            
        except Exception as e:
            logger.error(f"Error exporting monthly data for {month}: {str(e)}")
            raise
            
    def export_summary(self, months: List[str] = None) -> io.StringIO:
        """
        Export a summary of expenses across multiple months.
        
        Args:
            months: List of months in YYYY-MM format, or None for all months
            
        Returns:
            StringIO object containing CSV data
        """
        if not self.storage:
            raise ValueError("Storage is required for summary export")
            
        try:
            # Get list of all months if not specified
            if not months:
                months = self.storage.get_all_months()
                
            # Build summary data for each month
            month_data = []
            total_expenses = 0.0
            net_balance = 0.0
            
            for month in months:
                balance_sheet = self.storage.get_balance_sheet(month)
                summary = balance_sheet.summary()
                
                month_info = {
                    'month': month,
                    'total_expenses': summary.get('total_expenses', 0.0),
                    'balance': summary.get('balance', 0.0),
                    'owed_statement': summary.get('owed_statement', '')
                }
                
                month_data.append(month_info)
                total_expenses += summary.get('total_expenses', 0.0)
                
                # Balance could be positive or negative depending on who owes whom
                # For overall summary, we're interested in the absolute imbalance
                net_balance += abs(summary.get('balance', 0.0))
                
            # Prepare the data structure
            data = {
                'months': month_data,
                'overall': {
                    'total_expenses': total_expenses,
                    'net_balance': net_balance
                }
            }
            
            return self.generate_csv(data, 'summary')
            
        except Exception as e:
            logger.error(f"Error exporting summary data: {str(e)}")
            raise

def get_filename_for_export(month: str = None, export_type: str = 'monthly') -> str:
    """
    Generate a filename for an export.
    
    Args:
        month: Month in YYYY-MM format, or None for summary exports
        export_type: Type of export ('monthly', 'summary', etc.)
        
    Returns:
        Filename string with appropriate prefix and extension
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if export_type == 'monthly' and month:
        return f"expenses_{month}_{timestamp}.csv"
    elif export_type == 'summary':
        return f"expenses_summary_{timestamp}.csv"
    else:
        return f"expenses_export_{timestamp}.csv" 