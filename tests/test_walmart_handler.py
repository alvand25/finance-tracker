"""Tests for Walmart receipt handler."""

import unittest
from decimal import Decimal
from datetime import datetime
from handlers.walmart_handler import WalmartHandler

class TestWalmartHandler(unittest.TestCase):
    """Test cases for Walmart receipt handler."""
    
    def setUp(self):
        """Set up test cases."""
        self.handler = WalmartHandler()
        
        # Sample receipt text
        self.sample_receipt = """
            WALMART SUPERCENTER
            SAVE MONEY. LIVE BETTER.
            123 MAIN STREET
            ANYTOWN, ST 12345
            STORE #789
            
            CASHIER: JOHN456
            REG# 12
            TRANS# 789012
            
            05/25/2023 2:30 PM
            
            BANANAS           2.99
            2 @ $1.99 APPLES  3.98
            1.5 LB @ $4.99/LB GRAPES 7.49
            012345678901 BREAD 3.49
            DEPT 123 MILK     4.99
            
            SUBTOTAL         22.94
            TAX              1.91
            TOTAL           24.85
            
            VISA **** 1234
            
            # ITEMS SOLD 5
            TC# 456-789-012
            
            THANK YOU FOR SHOPPING
            AT WALMART
        """
        
    def test_can_handle(self):
        """Test store name detection."""
        # Should handle Walmart receipts
        self.assertTrue(self.handler.can_handle(self.sample_receipt))
        
        # Should handle variations
        variations = [
            "WAL-MART #123",
            "WALMART",
            "WAL MART SUPERCENTER",
            "WALMART STORE #456"
        ]
        for text in variations:
            self.assertTrue(self.handler.can_handle(text))
            
        # Should not handle other stores
        other_stores = [
            "TARGET",
            "COSTCO WHOLESALE",
            "KROGER"
        ]
        for text in other_stores:
            self.assertFalse(self.handler.can_handle(text))
            
    def test_extract_metadata(self):
        """Test metadata extraction."""
        metadata = self.handler.extract_metadata(self.sample_receipt)
        
        self.assertEqual(metadata['store_name'], "WALMART")
        self.assertEqual(metadata['store_number'], "789")
        self.assertEqual(metadata['cashier'], "JOHN456")
        self.assertEqual(metadata['register'], "12")
        self.assertEqual(metadata['transaction'], "789012")
        self.assertEqual(metadata['date'].strftime('%Y-%m-%d'), "2023-05-25")
        self.assertEqual(metadata['time'], "2:30 PM")
        
    def test_extract_items(self):
        """Test item extraction."""
        items = self.handler.extract_items(self.sample_receipt)
        
        # Check number of items
        self.assertEqual(len(items), 5)
        
        # Check specific items
        self.assertEqual(items[0]['name'], "BANANAS")
        self.assertEqual(items[0]['price'], 2.99)
        self.assertEqual(items[0]['quantity'], 1)
        
        # Check quantity-based item
        self.assertEqual(items[1]['name'], "APPLES")
        self.assertEqual(items[1]['price'], 3.98)
        self.assertEqual(items[1]['quantity'], 2)
        self.assertEqual(items[1]['unit_price'], 1.99)
        
        # Check weight-based item
        self.assertEqual(items[2]['name'], "GRAPES")
        self.assertEqual(items[2]['price'], 7.49)
        self.assertEqual(items[2]['quantity'], 1.5)
        self.assertEqual(items[2]['unit_price'], 4.99)
        
        # Check UPC item
        self.assertEqual(items[3]['name'], "BREAD")
        self.assertEqual(items[3]['price'], 3.49)
        
        # Check department code item
        self.assertEqual(items[4]['name'], "MILK")
        self.assertEqual(items[4]['price'], 4.99)
        
    def test_extract_totals(self):
        """Test totals extraction."""
        totals = self.handler._extract_totals(self.sample_receipt)
        
        self.assertEqual(totals['subtotal'], 22.94)
        self.assertEqual(totals['tax'], 1.91)
        self.assertEqual(totals['total'], 24.85)
        
    def test_process_receipt(self):
        """Test complete receipt processing."""
        receipt = self.handler.process(self.sample_receipt)
        
        # Check basic receipt data
        self.assertEqual(receipt.store_name, "WALMART")
        self.assertEqual(receipt.total_amount, Decimal('24.85'))
        self.assertEqual(receipt.tax_amount, Decimal('1.91'))
        self.assertEqual(receipt.subtotal_amount, Decimal('22.94'))
        
        # Check items
        self.assertEqual(len(receipt.items), 5)
        
        # Check confidence score
        self.assertGreater(receipt.confidence_score, 0.7)
        
        # Check requires_review flag
        self.assertFalse(receipt.requires_review)
        
    def test_handle_missing_data(self):
        """Test handling of receipts with missing data."""
        incomplete_receipt = """
            WALMART
            
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
            WALMART
            
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
            
    def test_handle_special_cases(self):
        """Test handling of special receipt cases."""
        # Receipt with savings/discounts
        receipt_with_savings = """
            WALMART
            
            BREAD          3.99
            SAVINGS       -1.00
            MILK           4.99
            
            SUBTOTAL       7.98
            TAX           0.66
            TOTAL         8.64
        """
        
        receipt = self.handler.process(receipt_with_savings)
        self.assertEqual(len(receipt.items), 2)  # Should not count SAVINGS as an item
        
        # Receipt with multiple tax lines
        receipt_with_multiple_tax = """
            WALMART
            
            ITEM1          10.00
            ITEM2          20.00
            
            SUBTOTAL       30.00
            STATE TAX       2.00
            COUNTY TAX      1.00
            TOTAL          33.00
        """
        
        receipt = self.handler.process(receipt_with_multiple_tax)
        self.assertEqual(receipt.tax_amount, Decimal('3.00'))  # Should sum all tax lines

if __name__ == '__main__':
    unittest.main() 