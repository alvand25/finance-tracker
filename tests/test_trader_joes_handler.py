"""Tests for Trader Joe's receipt handler."""

import unittest
from decimal import Decimal
from datetime import datetime
from handlers.trader_joes_handler import TraderJoesHandler

class TestTraderJoesHandler(unittest.TestCase):
    """Test cases for Trader Joe's receipt handler."""
    
    def setUp(self):
        """Set up test cases."""
        self.handler = TraderJoesHandler()
        
        # Sample receipt text
        self.sample_receipt = """
            TRADER JOE'S #123
            123 MAIN STREET
            CITY, STATE 12345
            STORE # 123
            
            CREW MEMBER: JOHN
            
            05/15/2023 10:30 AM
            
            ORGANIC BANANAS     2.99
            2 @ $3.99 AVOCADOS  7.98
            0.50 lb @ $5.99/lb APPLES 2.99
            DARK CHOCOLATE      3.49
            GREEK YOGURT       4.99
            
            SUBTOTAL          22.44
            TAX               1.87
            TOTAL            24.31
            
            VISA **** 1234
            
            THANK YOU FOR SHOPPING AT
            TRADER JOE'S
        """
        
    def test_can_handle(self):
        """Test store name detection."""
        # Should handle Trader Joe's receipts
        self.assertTrue(self.handler.can_handle(self.sample_receipt))
        
        # Should handle variations
        variations = [
            "TJ'S #123",
            "TRADER JOES",
            "TRADER JOE'S STORE #456"
        ]
        for text in variations:
            self.assertTrue(self.handler.can_handle(text))
            
        # Should not handle other stores
        other_stores = [
            "COSTCO WHOLESALE",
            "WALMART",
            "TARGET"
        ]
        for text in other_stores:
            self.assertFalse(self.handler.can_handle(text))
            
    def test_extract_metadata(self):
        """Test metadata extraction."""
        metadata = self.handler.extract_metadata(self.sample_receipt)
        
        self.assertEqual(metadata['store_name'], "TRADER JOE'S")
        self.assertEqual(metadata['store_number'], "123")
        self.assertEqual(metadata['cashier'], "JOHN")
        self.assertEqual(metadata['date'].strftime('%Y-%m-%d'), "2023-05-15")
        self.assertEqual(metadata['time'], "10:30 AM")
        
    def test_extract_items(self):
        """Test item extraction."""
        items = self.handler.extract_items(self.sample_receipt)
        
        # Check number of items
        self.assertEqual(len(items), 5)
        
        # Check specific items
        self.assertEqual(items[0]['name'], "ORGANIC BANANAS")
        self.assertEqual(items[0]['price'], 2.99)
        self.assertEqual(items[0]['quantity'], 1)
        
        # Check quantity-based item
        self.assertEqual(items[1]['name'], "AVOCADOS")
        self.assertEqual(items[1]['price'], 7.98)
        self.assertEqual(items[1]['quantity'], 2)
        self.assertEqual(items[1]['unit_price'], 3.99)
        
        # Check weight-based item
        self.assertEqual(items[2]['name'], "APPLES")
        self.assertEqual(items[2]['price'], 2.99)
        self.assertEqual(items[2]['quantity'], 0.50)
        self.assertEqual(items[2]['unit_price'], 5.99)
        
    def test_extract_totals(self):
        """Test totals extraction."""
        totals = self.handler._extract_totals(self.sample_receipt)
        
        self.assertEqual(totals['subtotal'], 22.44)
        self.assertEqual(totals['tax'], 1.87)
        self.assertEqual(totals['total'], 24.31)
        
    def test_process_receipt(self):
        """Test complete receipt processing."""
        receipt = self.handler.process(self.sample_receipt)
        
        # Check basic receipt data
        self.assertEqual(receipt.store_name, "TRADER JOE'S")
        self.assertEqual(receipt.total_amount, Decimal('24.31'))
        self.assertEqual(receipt.tax_amount, Decimal('1.87'))
        self.assertEqual(receipt.subtotal_amount, Decimal('22.44'))
        
        # Check items
        self.assertEqual(len(receipt.items), 5)
        
        # Check confidence score
        self.assertGreater(receipt.confidence_score, 0.7)
        
        # Check requires_review flag
        self.assertFalse(receipt.requires_review)
        
    def test_handle_missing_data(self):
        """Test handling of receipts with missing data."""
        incomplete_receipt = """
            TRADER JOE'S
            
            BANANAS     2.99
            APPLES      3.99
            
            TOTAL      6.98
        """
        
        receipt = self.handler.process(incomplete_receipt)
        
        # Should still process but with lower confidence
        self.assertLess(receipt.confidence_score, 0.7)
        self.assertTrue(receipt.requires_review)
        self.assertTrue(any("tax not detected" in note.lower() for note in receipt.validation_notes))
        
    def test_handle_invalid_data(self):
        """Test handling of invalid data."""
        invalid_receipt = """
            TRADER JOE'S
            
            ITEM WITH INVALID PRICE   ABC.DE
            ITEM WITH ZERO PRICE      0.00
            
            TOTAL                     0.00
        """
        
        receipt = self.handler.process(invalid_receipt)
        
        # Should process but mark items as suspicious
        self.assertTrue(receipt.requires_review)
        self.assertTrue(any(item.suspicious for item in receipt.items))
        
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        # Test with perfect data
        perfect_score = self.handler._calculate_item_confidence(
            name="ORGANIC BANANAS",
            price=2.99,
            quantity=1
        )
        self.assertGreaterEqual(perfect_score, 0.9)
        
        # Test with suspicious data
        suspicious_score = self.handler._calculate_item_confidence(
            name="A",  # Too short
            price=0,   # Zero price
            quantity=50  # Unusually high quantity
        )
        self.assertLess(suspicious_score, 0.5)

if __name__ == '__main__':
    unittest.main() 