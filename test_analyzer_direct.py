#!/usr/bin/env python3
import json
from services.receipt_analyzer import UnifiedReceiptAnalyzer, ParsedReceipt

# Path to suspicious items test file
test_file_path = 'samples/images/test_suspicious_detection.txt'

# Read the test file
with open(test_file_path, 'r') as f:
    receipt_text = f.read()

# Create analyzer
analyzer = UnifiedReceiptAnalyzer()

# Process the text directly
parsed_receipt = analyzer.analyze(receipt_text)

# Add some suspicious items manually to test detection
parsed_receipt.items.extend([
    {
        'name': 'VISA PAYMENT',
        'total': 100.00,
        'quantity': 1,
        'unit_price': 100.00
    },
    {
        'name': 'CASH BACK',
        'total': 20.00,
        'quantity': 1,
        'unit_price': 20.00
    },
    {
        'name': 'CHANGE DUE',
        'total': 1.50,
        'quantity': 1,
        'unit_price': 1.50
    },
    {
        'name': '123',  # Suspiciously short name
        'total': 5.99,
        'quantity': 1,
        'unit_price': 5.99
    },
    {
        'name': 'OVERPRICED ITEM',  # Suspiciously high price
        'total': 999.99,
        'quantity': 1,
        'unit_price': 999.99
    }
])

# Run detection again with our injected items
has_suspicious_items = False
validation_issues = []

# Payment-related keywords
payment_keywords = [
    'card', 'credit', 'debit', 'visa', 'mastercard', 'payment', 'paid',
    'change', 'cash', 'total', 'subtotal', 'balance', 'approved', 
    'authorization', 'receipt', 'transaction', 'purchase'
]

# Check for item issues and mark suspicious items
for item in parsed_receipt.items:
    item_name = item.get('name', '').lower()
    item_price = item.get('total', 0.0)
    
    is_suspicious = False
    
    # Check for payment-related keywords in item names
    if any(keyword in item_name for keyword in payment_keywords):
        print(f"Found payment keyword in item name: {item_name}")
        is_suspicious = True
    
    # Check for extremely high prices (likely errors)
    if item_price is not None and item_price > 300:  # Arbitrary threshold
        print(f"Found suspiciously high price: ${item_price:.2f} for {item_name}")
        is_suspicious = True
    
    # Check for suspiciously short or numeric-only names
    if len(item_name.strip()) < 3 or any(c.isdigit() for c in item_name) and all(c.isdigit() or c.isspace() for c in item_name):
        print(f"Found suspiciously short or numeric-only name: {item_name}")
        is_suspicious = True
    
    # Mark suspicious items
    if is_suspicious:
        has_suspicious_items = True
        item['suspicious'] = True
        print(f"Marked suspicious item: {item.get('name')} - ${item.get('total', 0.0)}")
    else:
        item['suspicious'] = False

# Update validation flags
if has_suspicious_items:
    parsed_receipt.has_suspicious_items = True
    suspicious_count = sum(1 for item in parsed_receipt.items if item.get('suspicious', False))
    validation_issues.append(f"Found {suspicious_count} suspicious items that may not be actual products")
    parsed_receipt.flagged_for_review = True
    parsed_receipt.validation_notes.extend(validation_issues)

# Print results
print("\nSummary:")
print(f"Store: {parsed_receipt.store_name or 'Unknown'}")
print(f"Total: ${parsed_receipt.total_amount or 0}")
print(f"Confidence: {parsed_receipt.confidence_score or 0}")

# List detected items
items = parsed_receipt.items or []
print(f"\nDetected {len(items)} items:")
for i, item in enumerate(items, 1):
    status = "⚠️ SUSPICIOUS" if item.get('suspicious', False) else "✅ VALID"
    print(f"{i}. {item.get('name', '')} - ${item.get('total', 0.0)} [{status}]")

# Show validation info
print("\nValidation Info:")
print(f"Flagged for review: {parsed_receipt.flagged_for_review}")
print(f"Has suspicious items: {parsed_receipt.has_suspicious_items}")

if parsed_receipt.validation_notes:
    print("\nValidation Notes:")
    for note in parsed_receipt.validation_notes:
        print(f"- {note}") 