"""Tests for Key Food receipt handler."""

import unittest
from decimal import Decimal
from datetime import datetime
from handlers.key_food_handler import KeyFoodHandler

class TestKeyFoodHandler(unittest.TestCase):
    """Test cases for Key Food receipt handler."""
    
    def setUp(self):
        """Set up test cases."""
        self.handler = KeyFoodHandler()
        
        # Sample receipt text
        self.sample_receipt = """
            KEY FOOD MARKETPLACE
            123 MAIN STREET
            BROOKLYN, NY 11201
            STORE #456
            
            MEMBER #: 123456
            CASHIER: JOHN123
            
            05/20/2023 11:45 AM
            
            ORGANIC BANANAS     3.99
            2 @ $2.50 APPLES    5.00
            1.5 LB @ $3.99/LB GRAPES 5.99
            BREAD              4.99
            MILK               3.99
            
            SUBTOTAL          23.96
            TAX               2.00
            TOTAL            25.96
            
            VISA **** 5678
            
            MEMBER SAVINGS: $2.50
            THANK YOU FOR SHOPPING AT
            KEY FOOD
        """
        
    def test_can_handle(self):
        """Test store name detection."""
        # Should handle Key Food receipts
        self.assertTrue(self.handler.can_handle(self.sample_receipt))
        
        # Should handle variations
        variations = [
            "KEY FOOD #123",
            "KEYFOOD",
            "KEY-FOOD MARKETPLACE",
            "KEY FOOD FRESH"
        ]
        for text in variations:
            self.assertTrue(self.handler.can_handle(text))
            
        # Should not handle other stores
        other_stores = [
            "TRADER JOE'S",
            "WALMART",
            "COSTCO"
        ]
        for text in other_stores:
            self.assertFalse(self.handler.can_handle(text))
            
    def test_extract_metadata(self):
        """Test metadata extraction."""
        metadata = self.handler.extract_metadata(self.sample_receipt)
        
        self.assertEqual(metadata['store_name'], "KEY FOOD")
        self.assertEqual(metadata['store_number'], "456")
        self.assertEqual(metadata['cashier'], "JOHN123")
        self.assertEqual(metadata['member_number'], "123456")
        self.assertEqual(metadata['date'].strftime('%Y-%m-%d'), "2023-05-20")
        self.assertEqual(metadata['time'], "11:45 AM")
        
    def test_extract_items(self):
        """Test item extraction."""
        items = self.handler.extract_items(self.sample_receipt)
        
        # Check number of items
        self.assertEqual(len(items), 5)
        
        # Check specific items
        self.assertEqual(items[0]['name'], "ORGANIC BANANAS")
        self.assertEqual(items[0]['price'], 3.99)
        self.assertEqual(items[0]['quantity'], 1)
        
        # Check quantity-based item
        self.assertEqual(items[1]['name'], "APPLES")
        self.assertEqual(items[1]['price'], 5.00)
        self.assertEqual(items[1]['quantity'], 2)
        self.assertEqual(items[1]['unit_price'], 2.50)
        
        # Check weight-based item
        self.assertEqual(items[2]['name'], "GRAPES")
        self.assertEqual(items[2]['price'], 5.99)
        self.assertEqual(items[2]['quantity'], 1.5)
        self.assertEqual(items[2]['unit_price'], 3.99)
        
    def test_extract_totals(self):
        """Test totals extraction."""
        totals = self.handler._extract_totals(self.sample_receipt)
        
        self.assertEqual(totals['subtotal'], 23.96)
        self.assertEqual(totals['tax'], 2.00)
        self.assertEqual(totals['total'], 25.96)
        
    def test_process_receipt(self):
        """Test complete receipt processing."""
        receipt = self.handler.process(self.sample_receipt)
        
        # Check basic receipt data
        self.assertEqual(receipt.store_name, "KEY FOOD")
        self.assertEqual(receipt.total_amount, Decimal('25.96'))
        self.assertEqual(receipt.tax_amount, Decimal('2.00'))
        self.assertEqual(receipt.subtotal_amount, Decimal('23.96'))
        
        # Check items
        self.assertEqual(len(receipt.items), 5)
        
        # Check confidence score
        self.assertGreater(receipt.confidence_score, 0.7)
        
        # Check requires_review flag
        self.assertFalse(receipt.requires_review)
        
    def test_handle_missing_data(self):
        """Test handling of receipts with missing data."""
        incomplete_receipt = """
            KEY FOOD
            
            BREAD      2.99
            MILK       3.99
            
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
            KEY FOOD
            
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
        
    def test_clean_item_name(self):
        """Test item name cleaning."""
        test_cases = [
            ("ORGANIC BANANAS!", "ORGANIC BANANAS"),
            ("2% MILK   ", "2% MILK"),
            ("BREAD & BUTTER", "BREAD & BUTTER"),
            ("CHIPS#123", "CHIPS123"),
            ("  SODA  ", "SODA")
        ]
        
        for input_name, expected_name in test_cases:
            cleaned_name = self.handler._clean_item_name(input_name)
            self.assertEqual(cleaned_name, expected_name)

if __name__ == '__main__':
    unittest.main() 