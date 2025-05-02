"""
Receipt item model for representing individual items on a receipt.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from decimal import Decimal

@dataclass
class ReceiptItem:
    """
    Represents a single item on a receipt.
    """
    description: str
    price: Decimal
    quantity: float = 1.0
    unit_price: Optional[Decimal] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    confidence: Dict[str, Any] = field(default_factory=lambda: {
        'overall': 0.0,
        'description': 0.0,
        'price': 0.0,
        'quantity': 0.0
    })
    
    def __post_init__(self):
        """Convert price and unit_price to Decimal if they aren't already."""
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if self.unit_price is not None and not isinstance(self.unit_price, Decimal):
            self.unit_price = Decimal(str(self.unit_price))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the item to a dictionary."""
        return {
            'description': self.description,
            'price': float(self.price),
            'quantity': self.quantity,
            'unit_price': float(self.unit_price) if self.unit_price else None,
            'category': self.category,
            'sku': self.sku,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReceiptItem':
        """Create a ReceiptItem from a dictionary."""
        return cls(
            description=data['description'],
            price=Decimal(str(data['price'])),
            quantity=data.get('quantity', 1.0),
            unit_price=Decimal(str(data['unit_price'])) if data.get('unit_price') else None,
            category=data.get('category'),
            sku=data.get('sku'),
            confidence=data.get('confidence', {
                'overall': 0.0,
                'description': 0.0,
                'price': 0.0,
                'quantity': 0.0
            })
        ) 