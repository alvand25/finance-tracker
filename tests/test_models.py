import unittest
from datetime import date
from uuid import uuid4

from models.expense import User, ExpenseItem, Expense, BalanceSheet


class TestExpenseModel(unittest.TestCase):
    """Test the Expense model."""
    
    def test_calculate_shared_total(self):
        """Test that shared_total is calculated correctly."""
        expense = Expense(
            id=uuid4(),
            payer=User.ALVAND,
            date=date(2023, 1, 1),
            store="Test Store",
            total_amount=100.0,
            items=[
                ExpenseItem(name="Shared item 1", amount=40.0, shared=True),
                ExpenseItem(name="Shared item 2", amount=30.0, shared=True),
                ExpenseItem(name="Personal item", amount=30.0, shared=False),
            ]
        )
        
        # Calculate shared total
        shared_total = expense.calculate_shared_total()
        
        # 70/100 of the total amount is shared
        self.assertEqual(shared_total, 70.0)
        self.assertEqual(expense.shared_total, 70.0)
    
    def test_amount_owed(self):
        """Test that amount_owed is calculated correctly."""
        expense = Expense(
            id=uuid4(),
            payer=User.ALVAND,
            date=date(2023, 1, 1),
            store="Test Store",
            total_amount=100.0,
            items=[
                ExpenseItem(name="Shared item 1", amount=40.0, shared=True),
                ExpenseItem(name="Shared item 2", amount=60.0, shared=True),
            ]
        )
        
        # Calculate amount owed (half of the shared total)
        amount_owed = expense.amount_owed()
        
        self.assertEqual(amount_owed, 50.0)
    
    def test_balance_sheet_net_balance(self):
        """Test that the balance sheet calculates net balance correctly."""
        # Create expenses
        expense1 = Expense(
            id=uuid4(),
            payer=User.ALVAND,
            date=date(2023, 1, 1),
            store="Store 1",
            total_amount=100.0,
            items=[
                ExpenseItem(name="Shared item 1", amount=100.0, shared=True),
            ]
        )
        
        expense2 = Expense(
            id=uuid4(),
            payer=User.RONI,
            date=date(2023, 1, 2),
            store="Store 2",
            total_amount=60.0,
            items=[
                ExpenseItem(name="Shared item 2", amount=60.0, shared=True),
            ]
        )
        
        # Create balance sheet with both expenses
        balance_sheet = BalanceSheet(
            month="2023-01",
            expenses=[expense1, expense2]
        )
        
        # Calculate net balance
        # Alvand paid 100, Roni owes 50
        # Roni paid 60, Alvand owes 30
        # Net: Roni owes Alvand 20
        net_balance = balance_sheet.net_balance
        
        self.assertEqual(net_balance, 20.0)
    
    def test_balance_sheet_summary(self):
        """Test that the balance sheet summary is generated correctly."""
        # Create expenses
        expense1 = Expense(
            id=uuid4(),
            payer=User.ALVAND,
            date=date(2023, 1, 1),
            store="Store 1",
            total_amount=100.0,
            items=[
                ExpenseItem(name="Shared item 1", amount=80.0, shared=True),
                ExpenseItem(name="Personal item 1", amount=20.0, shared=False),
            ]
        )
        
        expense2 = Expense(
            id=uuid4(),
            payer=User.RONI,
            date=date(2023, 1, 2),
            store="Store 2",
            total_amount=50.0,
            items=[
                ExpenseItem(name="Shared item 2", amount=50.0, shared=True),
            ]
        )
        
        # Create balance sheet with both expenses
        balance_sheet = BalanceSheet(
            month="2023-01",
            expenses=[expense1, expense2]
        )
        
        # Get summary
        summary = balance_sheet.summary()
        
        # Check summary values
        self.assertEqual(summary["month"], "2023-01")
        self.assertEqual(summary["total_expenses"], 150.0)
        self.assertEqual(summary["total_shared_expenses"], 130.0)
        self.assertEqual(summary["alvand_paid"], 100.0)
        self.assertEqual(summary["roni_paid"], 50.0)
        self.assertEqual(summary["balance"], 15.0)  # Roni owes Alvand $15
        self.assertEqual(summary["owed_statement"], "Roni owes Alvand $15.00")


if __name__ == "__main__":
    unittest.main() 