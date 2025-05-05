# Finance Tracker Phase 6 - Manual Testing Checklist

This document provides a structured checklist for manually validating all Phase 6 features and functionality in the Finance Tracker application. Use this checklist to verify that all implemented features are working as expected.

## Setup Instructions

1. Ensure the application is running:
   ```bash
   flask run
   ```
2. Visit: http://localhost:5003/expense/new for receipt upload and expense entry

## 1. Receipt-Based Expense Entry

### Receipt Upload
- [ ] Drag-and-drop upload works on desktop browsers
- [ ] File selector upload works on mobile browsers
- [ ] Upload progress indicator displays during upload
- [ ] Receipt image preview shows after selection
- [ ] Removing receipt image clears form data properly

### OCR Processing
- [ ] Receipt text is properly extracted from uploaded image
- [ ] Store name is correctly identified
- [ ] Date is correctly extracted
- [ ] Total amount is correctly extracted
- [ ] Individual items are correctly identified

### Item Management
- [ ] All receipt items appear in the form
- [ ] Shared/personal item checkbox toggles work correctly 
- [ ] Suspicious items appear at bottom of the list, unchecked by default
- [ ] Items flagged with low confidence show warning indicator
- [ ] Adding/removing items updates total in real-time

### Form Submission
- [ ] Submitting form with receipt data works correctly
- [ ] Validation errors display appropriately when required fields are missing
- [ ] Form submission shows success message
- [ ] Page redirects to expenses list after successful submission
- [ ] Balance card and shared expense totals update in less than 1 second

## 2. Manual Expense Entry

### Basic Functionality
- [ ] Add expense form works without a receipt (text-only input)
- [ ] Date picker functions correctly
- [ ] Store name autocomplete shows previously used stores
- [ ] Adding multiple items works correctly
- [ ] Removing items works correctly

### Validation
- [ ] Form validation prevents submission with missing required fields
- [ ] Numeric fields only accept valid numbers
- [ ] Date validation works correctly
- [ ] Error messages are clear and informative

### Post-Submission
- [ ] New manually entered expense appears in recent expenses list
- [ ] Expense appears in the correct month view
- [ ] Balance card updates correctly with new expense
- [ ] "Who owes who" section updates live with correct calculations

## 3. Exporting Functionality

### Monthly Export
- [ ] Export current month to CSV button works
- [ ] CSV download starts automatically
- [ ] CSV contains correct headers (Date, Store, Amount, Items, Shared)
- [ ] All expenses for the month are included
- [ ] Values match UI totals exactly
- [ ] Date formatting is consistent

### Summary Export
- [ ] Export full summary CSV button works
- [ ] CSV contains monthly breakdown
- [ ] Summary totals match UI display
- [ ] Balance calculations are accurate
- [ ] File naming follows expected convention (finance_summary_YYYY-MM-DD.csv)

### CSV Format
- [ ] CSV files open correctly in spreadsheet applications
- [ ] Special characters are properly escaped/encoded
- [ ] Numeric formatting is consistent (2 decimal places)
- [ ] No extraneous columns or data

## 4. Mobile API Testing

### Upload Endpoint
- [ ] Upload a .jpg image file to `/api/upload-receipt`
- [ ] Upload a .heic image file to `/api/upload-receipt` (iOS format)
- [ ] Upload works from mobile device
- [ ] Receives appropriate error response for invalid file types

### API Response Structure
- [ ] API returns JSON with structured receipt data:
  - [ ] Items array with descriptions and amounts
  - [ ] Store name
  - [ ] Receipt total
  - [ ] Date
  - [ ] Confidence scores
  - [ ] Suspicious item flags (if any)
  
### Mobile Integration
- [ ] Mobile-specific headers are properly handled
- [ ] Response times are reasonable (under 5 seconds)
- [ ] Error responses include appropriate HTTP status codes
- [ ] CORS headers allow cross-origin requests

## 5. Live Balance Update System

### Real-time Updates
- [ ] Adding a new expense updates balance immediately
- [ ] Editing an expense updates balance immediately
- [ ] Deleting an expense updates balance immediately
- [ ] Balance card shows correct total after any modification

### Shared Expense Calculations
- [ ] "Who owes who" calculations are accurate
- [ ] Shared vs. personal expense separation works correctly
- [ ] Multi-person expenses distribute properly
- [ ] Edge cases (zero-sum, negative amounts) handle correctly

## 6. Suspicious Item Handling

### Detection
- [ ] System correctly identifies suspicious items based on confidence
- [ ] Items with unusual prices are flagged appropriately
- [ ] Items with garbled or incomplete text are marked suspicious

### UI Representation
- [ ] Suspicious items appear visually distinct in the form
- [ ] Warning indicators clearly show which items are suspicious
- [ ] Unchecking suspicious items excludes them from the expense

### Handling Options
- [ ] User can manually override suspicious item flags
- [ ] Editing suspicious items clears the suspicious flag
- [ ] Suspicious items are excluded from totals when unchecked

## Test Results

**Tester:** _________________________

**Date:** _________________________

**Browser/Device:** _________________________

### Issues Found:
1. 
2. 
3. 

### Notes: 