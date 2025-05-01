from datetime import date as Date
from enum import Enum
from typing import List, Optional, Union, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, validator

from models.receipt import Receipt


class User(str, Enum):
    ALVAND = "Alvand"
    RONI = "Roni"


class ExpenseItem(BaseModel):
    name: str
    amount: float
    shared: bool = True


class Expense(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    payer: User
    date: Date
    store: str
    total_amount: float
    receipt: Optional[Receipt] = None
    items: List[ExpenseItem]
    shared_total: Optional[float] = None
    
    def attach_receipt(self, receipt: Receipt) -> None:
        """Attach a receipt to this expense and sync relevant data."""
        self.receipt = receipt
        receipt.link_to_expense(self.id)
        
        # If receipt has store name and we don't, use it
        if not self.store and receipt.store_name:
            self.store = receipt.store_name
            
        # If receipt has items and we don't, convert them to expense items
        if not self.items and receipt.items:
            self.items = [
                ExpenseItem(
                    name=item.description,
                    amount=item.amount,
                    shared=True  # Default to shared
                ) for item in receipt.items
            ]
            
        # Update total amount if needed
        if receipt.total_amount:
            self.total_amount = receipt.total_amount
    
    @classmethod
    def create_with_receipt_url(cls, receipt_url: str, **expense_data):
        """Factory method to create an expense with an attached receipt from URL."""
        from services.receipt_service import ReceiptService
        from storage.json_storage import JSONStorage
        
        # Create the basic expense
        expense = cls(**expense_data)
        
        # Process the receipt if URL is provided
        if receipt_url:
            # Initialize services
            storage = JSONStorage()
            receipt_service = ReceiptService(storage)
            
            # Create and process the receipt
            receipt, success = receipt_service.upload_receipt_from_url(receipt_url)
            
            # Attach the receipt to the expense
            if success:
                expense.attach_receipt(receipt)
            
        return expense
        
    @classmethod
    def create_with_receipt_file(cls, receipt_file: Any, **expense_data):
        """Factory method to create an expense with an attached receipt from file upload."""
        from services.receipt_service import ReceiptService
        from storage.json_storage import JSONStorage
        
        # Create the basic expense
        expense = cls(**expense_data)
        
        # Process the receipt if file is provided
        if receipt_file:
            # Initialize services
            storage = JSONStorage()
            receipt_service = ReceiptService(storage)
            
            # Process the uploaded file
            receipt, success = receipt_service.process_uploaded_file(receipt_file)
            
            # Attach the receipt to the expense
            if success:
                expense.attach_receipt(receipt)
            
        return expense
    
    def calculate_shared_total(self) -> float:
        """Calculate the total amount that should be shared between users."""
        if not self.items:
            return 0.0
            
        # Calculate the amount for shared items
        shared_items_amount = sum(item.amount for item in self.items if item.shared)
        
        # Calculate the proportion of shared items
        shared_proportion = shared_items_amount / sum(item.amount for item in self.items)
        
        # Apply the proportion to the total (includes tax and other fees)
        self.shared_total = round(self.total_amount * shared_proportion, 2)
        return self.shared_total
    
    def amount_owed(self) -> float:
        """Calculate how much the other person owes to the payer."""
        if self.shared_total is None:
            self.calculate_shared_total()
        
        # Half of the shared amount is owed by the other person
        return round(self.shared_total / 2, 2)


class BalanceSheet(BaseModel):
    month: str  # Format: YYYY-MM
    expenses: List[Expense] = []
    
    @property
    def net_balance(self) -> float:
        """
        Calculate the net balance between users.
        Positive: Roni owes Alvand
        Negative: Alvand owes Roni
        """
        balance = 0.0
        
        for expense in self.expenses:
            # First make sure shared_total is calculated
            if expense.shared_total is None:
                expense.calculate_shared_total()
                
            # Calculate the amount owed to the payer
            amount_owed = expense.amount_owed()
            
            # Adjust the balance based on payer
            if expense.payer == User.ALVAND:
                balance += amount_owed  # Roni owes Alvand
            else:
                balance -= amount_owed  # Alvand owes Roni
        
        return round(balance, 2)
    
    def summary(self) -> dict:
        """Generate a summary of the balance sheet."""
        total_expenses = sum(expense.total_amount for expense in self.expenses)
        total_shared = sum(
            expense.shared_total if expense.shared_total is not None 
            else expense.calculate_shared_total() 
            for expense in self.expenses
        )
        
        alvand_paid = sum(
            expense.total_amount for expense in self.expenses 
            if expense.payer == User.ALVAND
        )
        roni_paid = sum(
            expense.total_amount for expense in self.expenses 
            if expense.payer == User.RONI
        )
        
        balance = self.net_balance
        
        if balance > 0:
            owed_statement = f"Roni owes Alvand ${balance:.2f}"
        elif balance < 0:
            owed_statement = f"Alvand owes Roni ${abs(balance):.2f}"
        else:
            owed_statement = "All settled! No one owes anything."
        
        return {
            "month": self.month,
            "total_expenses": round(total_expenses, 2),
            "total_shared_expenses": round(total_shared, 2),
            "alvand_paid": round(alvand_paid, 2),
            "roni_paid": round(roni_paid, 2),
            "balance": balance,
            "owed_statement": owed_statement
        } 