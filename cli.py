import argparse
import datetime
import os
import sys
from datetime import date as Date
from typing import List

from models.expense import Expense, ExpenseItem, User
from storage.json_storage import JSONStorage
from utils.receipt_uploader import ReceiptUploader


def parse_date(date_str: str) -> Date:
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"Error: Invalid date format: {date_str}. Expected format: YYYY-MM-DD")
        sys.exit(1)


def add_expense(storage: JSONStorage, uploader: ReceiptUploader) -> None:
    """Interactive function to add a new expense."""
    print("\n=== Add New Expense ===\n")
    
    # Get payer
    payer_input = input("Who paid? (1: Alvand, 2: Roni): ").strip()
    if payer_input == "1":
        payer = User.ALVAND
    elif payer_input == "2":
        payer = User.RONI
    else:
        print("Invalid input. Please enter 1 for Alvand or 2 for Roni.")
        return
    
    # Get date
    date_input = input("Date of expense (YYYY-MM-DD): ").strip()
    try:
        date_obj = parse_date(date_input)
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        return
    
    # Get store name
    store = input("Store/merchant name: ").strip()
    if not store:
        print("Store name cannot be empty.")
        return
    
    # Get total amount
    try:
        total_amount = float(input("Total amount paid: $").strip())
        if total_amount <= 0:
            print("Amount must be greater than zero.")
            return
    except ValueError:
        print("Invalid amount. Please enter a numeric value.")
        return
    
    # Get receipt path (optional)
    receipt_path = input("Receipt image path (optional, press enter to skip): ").strip()
    receipt_url = None
    if receipt_path:
        if os.path.exists(receipt_path):
            receipt_url = uploader.save_receipt(receipt_path, date_obj, store)
            if receipt_url:
                print(f"Receipt uploaded: {receipt_url}")
            else:
                print("Warning: Failed to upload receipt.")
        else:
            print(f"Warning: Receipt file not found: {receipt_path}")
    
    # Get items
    items = []
    print("\nEnter individual items (enter an empty name to finish):")
    
    item_index = 1
    while True:
        print(f"\nItem #{item_index}")
        name = input("Item name (or press enter to finish): ").strip()
        if not name:
            break
        
        try:
            amount = float(input("Item amount: $").strip())
            if amount <= 0:
                print("Amount must be greater than zero.")
                continue
        except ValueError:
            print("Invalid amount. Please enter a numeric value.")
            continue
        
        shared_input = input("Is this item shared? (Y/n): ").strip().lower()
        shared = shared_input != "n"
        
        items.append(ExpenseItem(name=name, amount=amount, shared=shared))
        item_index += 1
    
    if not items:
        print("Error: No items added to the expense.")
        return
    
    # Create and save the expense
    expense = Expense(
        payer=payer,
        date=date_obj,
        store=store,
        total_amount=total_amount,
        receipt_url=receipt_url,
        items=items
    )
    
    # Calculate shared total
    shared_total = expense.calculate_shared_total()
    
    # Save the expense
    storage.save_expense(expense)
    
    print("\n=== Expense Added Successfully ===")
    print(f"Shared total: ${shared_total:.2f}")
    amount_owed = expense.amount_owed()
    if payer == User.ALVAND:
        print(f"Roni owes Alvand: ${amount_owed:.2f}")
    else:
        print(f"Alvand owes Roni: ${amount_owed:.2f}")


def show_month_summary(storage: JSONStorage) -> None:
    """Show a summary of expenses for a specific month."""
    # Get month input
    month_input = input("Enter month (YYYY-MM): ").strip()
    try:
        datetime.datetime.strptime(month_input, "%Y-%m")
    except ValueError:
        print("Invalid month format. Please use YYYY-MM.")
        return
    
    # Get the balance sheet for the month
    balance_sheet = storage.get_balance_sheet(month_input)
    
    # Get the summary
    summary = balance_sheet.summary()
    
    print("\n=== Month Summary ===")
    print(f"Month: {summary['month']}")
    print(f"Total expenses: ${summary['total_expenses']:.2f}")
    print(f"Total shared expenses: ${summary['total_shared_expenses']:.2f}")
    print(f"Alvand paid: ${summary['alvand_paid']:.2f}")
    print(f"Roni paid: ${summary['roni_paid']:.2f}")
    print(f"Balance: ${abs(summary['balance']):.2f}")
    print(f"Status: {summary['owed_statement']}")
    
    # Print expenses
    if balance_sheet.expenses:
        print("\n=== Expenses ===")
        for expense in balance_sheet.expenses:
            shared_total = expense.shared_total if expense.shared_total is not None else expense.calculate_shared_total()
            print(f"- {expense.date}: {expense.store} - ${expense.total_amount:.2f} (${shared_total:.2f} shared)")


def list_all_months(storage: JSONStorage) -> None:
    """List all months with expenses."""
    months = storage.get_all_months()
    
    if not months:
        print("No expenses found in any month.")
        return
    
    print("\n=== Available Months ===")
    for month in months:
        balance_sheet = storage.get_balance_sheet(month)
        summary = balance_sheet.summary()
        print(f"{month}: {len(balance_sheet.expenses)} expenses, ${summary['total_expenses']:.2f} total")


def main() -> None:
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="Finance Tracker CLI")
    parser.add_argument("--data-dir", default="data", help="Directory for storing expense data")
    parser.add_argument("--upload-dir", default="uploads/receipts", help="Directory for storing receipt uploads")
    
    args = parser.parse_args()
    
    # Initialize storage and uploader
    storage = JSONStorage(data_dir=args.data_dir)
    uploader = ReceiptUploader(upload_dir=args.upload_dir)
    
    # Main menu loop
    while True:
        print("\n=== Finance Tracker CLI ===")
        print("1. Add a new expense")
        print("2. Show month summary")
        print("3. List all months")
        print("0. Exit")
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice == "1":
            add_expense(storage, uploader)
        elif choice == "2":
            show_month_summary(storage)
        elif choice == "3":
            list_all_months(storage)
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main() 