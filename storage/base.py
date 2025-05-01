from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from models.expense import Expense, BalanceSheet


class StorageBase(ABC):
    """Base class for storage implementations."""
    
    @abstractmethod
    def save_expense(self, expense: Expense) -> None:
        """Save an expense to storage."""
        pass
    
    @abstractmethod
    def get_expense(self, expense_id: UUID) -> Optional[Expense]:
        """Retrieve an expense by ID."""
        pass
    
    @abstractmethod
    def update_expense(self, expense: Expense) -> None:
        """Update an existing expense."""
        pass
    
    @abstractmethod
    def delete_expense(self, expense_id: UUID) -> None:
        """Delete an expense by ID."""
        pass
    
    @abstractmethod
    def get_balance_sheet(self, month: str) -> BalanceSheet:
        """Get the balance sheet for a specific month."""
        pass
    
    @abstractmethod
    def get_all_months(self) -> List[str]:
        """Get a list of all months that have expenses."""
        pass 