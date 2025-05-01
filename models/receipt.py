from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class ReceiptItem(BaseModel):
    """Represents an item extracted from a receipt."""
    description: str
    amount: float
    confidence_score: Optional[float] = None
    item_type: Optional[str] = None  # e.g., product, service, discount
    item_category: Optional[str] = None  # e.g., food, electronics, etc.
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    confidence_scores: Optional[Dict[str, float]] = None  # Field-specific confidence

class Receipt(BaseModel):
    """Model representing a receipt with OCR capabilities."""
    id: UUID = Field(default_factory=uuid4)
    expense_id: Optional[UUID] = None
    image_url: str
    store_name: Optional[str] = None
    transaction_date: Optional[datetime] = None
    date: Optional[datetime] = None  # Alias for transaction_date
    subtotal_amount: Optional[float] = None
    subtotal: Optional[float] = None  # Alias for subtotal_amount
    tax_amount: Optional[float] = None
    tax: Optional[float] = None  # Alias for tax_amount
    total_amount: Optional[float] = None
    total: Optional[float] = None  # Alias for total_amount
    items: List[ReceiptItem] = []
    raw_text: Optional[str] = None
    processed_date: datetime = Field(default_factory=datetime.now)
    processing_status: str = "pending"  # pending, processing, completed, failed
    processing_error: Optional[Union[str, Dict[str, Any]]] = None
    error_message: Optional[str] = None  # Alias for processing_error
    
    # New enhanced fields
    currency_type: Optional[str] = None  # e.g., USD, EUR, etc.
    currency: Optional[str] = None  # Alias for currency_type
    payment_method: Optional[str] = None  # e.g., cash, credit card, etc.
    confidence_score: Optional[float] = None  # Overall OCR confidence
    template_id: Optional[UUID] = None  # ID of matched receipt template
    template_metadata: Optional[Dict[str, Any]] = None  # Template-specific data
    location_data: Optional[Dict[str, Any]] = None  # Store location info
    processing_time: Optional[float] = None  # Time taken to process in seconds
    confidence_scores: Optional[Dict[str, float]] = Field(default_factory=dict)  # Field-specific confidence
    is_store_specific: Optional[bool] = False  # Flag for store-specific processing
    store_specific_metadata: Optional[Dict[str, Any]] = None  # Store-specific info
    file_path: Optional[str] = None  # Path to the receipt image file

    @classmethod
    def create_new(cls):
        """Create a new receipt with default values."""
        return cls(
            image_url="placeholder",
            processing_status="pending"
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    def link_to_expense(self, expense_id: UUID) -> None:
        """Link this receipt to an expense."""
        self.expense_id = expense_id

    def update_from_analysis(self, analyzed_items: List[dict], totals: Dict[str, Optional[float]], raw_text: str) -> None:
        """
        Update receipt data from OCR analysis results.
        
        Args:
            analyzed_items: List of extracted items with descriptions and amounts
            totals: Dictionary containing subtotal, tax, and total amounts
            raw_text: Raw text extracted from the receipt
        """
        # Record the processing start time
        start_time = datetime.now()
        
        self.raw_text = raw_text
        self.items = [
            ReceiptItem(
                description=item["description"],
                amount=item["amount"],
                confidence_score=item.get("confidence_score"),
                item_type=item.get("item_type"),
                item_category=item.get("item_category"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                confidence_scores=item.get("confidence_scores")
            ) for item in analyzed_items
        ]
        
        # Set amounts from extracted totals
        self.subtotal_amount = totals.get('subtotal')
        self.tax_amount = totals.get('tax')
        self.total_amount = totals.get('total')
        
        # Currency information if available
        if 'currency' in totals:
            self.currency_type = totals['currency']
            
        # Payment method if available
        if 'payment_method' in totals:
            self.payment_method = totals['payment_method']
            
        # Store name if available
        if 'store_name' in totals:
            self.store_name = totals['store_name']
            
            # Check if this is a store with special handling
            store_name_lower = self.store_name.lower() if self.store_name else ""
            if "costco" in store_name_lower:
                self.is_store_specific = True
                self.store_specific_metadata = {"store_type": "costco"}
            
        # Date information if available
        if 'date' in totals:
            self.transaction_date = totals['date']
            
        # Location data if available
        if 'location' in totals:
            self.location_data = totals['location']
            
        # Confidence scores
        if 'confidence_scores' in totals:
            self.confidence_scores = totals['confidence_scores']
            
        # Overall confidence score (average of individual scores)
        if self.confidence_scores:
            self.confidence_score = sum(self.confidence_scores.values()) / len(self.confidence_scores)
        
        # If we have subtotal and tax but no total, calculate it
        if self.subtotal_amount is not None and self.tax_amount is not None and self.total_amount is None:
            self.total_amount = round(self.subtotal_amount + self.tax_amount, 2)
        
        # If we only have a subtotal and no tax, use it as the total
        elif self.subtotal_amount is not None and self.tax_amount is None and self.total_amount is None:
            self.total_amount = self.subtotal_amount
            
        # Fallback: if we still don't have a total amount, sum the items
        if self.total_amount is None and self.items:
            self.total_amount = round(sum(item.amount for item in self.items), 2)
        
        # For Costco receipts, try additional processing if needed
        if self.is_store_specific and self.store_specific_metadata and self.store_specific_metadata.get("store_type") == "costco":
            # If we still don't have good data, try special Costco parsing
            if not self.items or not self.total_amount:
                self._parse_costco_receipt()
        
        # Calculate processing time
        self.processing_time = (datetime.now() - start_time).total_seconds()
        
        # Set status based on what we extracted
        if self.items and self.total_amount:
            self.processing_status = "completed"
        else:
            # If we have a total but no items, it's partial success
            if self.total_amount:
                self.processing_status = "partial"
            else:
                self.processing_status = "failed"
                self.processing_error = "Failed to extract essential receipt data"

    @staticmethod
    def _parse_costco_receipt(text: str) -> Dict[str, Any]:
        """Parse a Costco receipt with specialized patterns."""
        import re
        import logging
        
        logging.info("Parsing Costco receipt with specialized method")
        
        # Initialize result data structure
        result = {
            'store': 'Costco',
            'currency': 'USD',
            'items': [],
            'subtotal': None,
            'tax': None,
            'total': None,
            'date': None,
            'payment_method': None
        }
        
        # Split into lines for processing
        lines = text.split('\n')
        
        # Extract date with Costco-specific patterns
        date_patterns = [
            r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
            r'DATE\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})'
        ]
        
        for pattern in date_patterns:
            for line in lines:
                match = re.search(pattern, line)
                if match:
                    try:
                        month, day, year = match.groups()
                        # Handle 2-digit years
                        if len(year) == 2:
                            year = f"20{year}"
                        result['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        break
                    except (ValueError, IndexError):
                        continue
            if result['date']:
                break
        
        # Define item extraction patterns
        item_patterns = [
            # Standard pattern: Description followed by price
            r'^\s*([A-Za-z0-9\s\.\-\&\'\"\,\/\(\)]{3,})\s+(\d{1,3}(?:,\d{3})*\.\d{2})$',
            # Item with item number
            r'^\s*(\d{5,})\s+([A-Za-z0-9\s\.\-\&\'\"\,\/\(\)]{3,})\s+(\d{1,3}(?:,\d{3})*\.\d{2})$',
            # Item with quantity (like "2 X $10.99")
            r'^\s*([A-Za-z0-9\s\.\-\&\'\"\,\/\(\)]{3,})\s+(\d+)\s*[xX]\s*\$?(\d{1,3}(?:,\d{3})*\.\d{2})$',
            # Item with quantity and price
            r'^\s*([A-Za-z0-9\s\.\-\&\'\"\,\/\(\)]{3,})\s+(\d+)\s+(\d{1,3}(?:,\d{3})*\.\d{2})$',
            # More flexible pattern that just looks for a price at the end
            r'([A-Za-z0-9\s\.\-\&\'\"\,\/\(\)]{3,})\s+\$?(\d{1,3}(?:,\d{3})*\.\d{2})$'
        ]
        
        # Skip keywords that indicate non-item lines
        skip_keywords = ['total', 'subtotal', 'tax', 'balance', 'change', 'payment', 'visa', 
                        'mastercard', 'cash', 'credit', 'date', 'time', 'thank', 'member', 
                        'cashier', 'warehouse', 'receipt', 'return']
        
        # Extract items
        seen_descriptions = set()
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
                
            # Skip lines with keywords that indicate it's not an item
            if any(keyword in line.lower() for keyword in skip_keywords):
                continue
                
            for pattern in item_patterns:
                match = re.search(pattern, line)
                if match:
                    try:
                        # Extract based on pattern
                        if len(match.groups()) == 2:
                            description, price = match.groups()
                            quantity = 1
                        elif len(match.groups()) == 3:
                            if re.search(r'^\d{5,}', match.group(1)):
                                # Pattern with item number
                                item_code, description, price = match.groups()
                                quantity = 1
                            else:
                                # Pattern with quantity
                                description, quantity, price = match.groups()
                        
                        # Clean description and price
                        description = description.strip()
                        price = price.replace(',', '')
                        
                        # Skip if description too short or already seen
                        if len(description) < 3 or description.lower() in seen_descriptions:
                            continue
                            
                        # Create item dictionary
                        try:
                            price_float = float(price)
                            quantity_int = int(quantity)
                            item = {
                                'description': description,
                                'quantity': quantity_int,
                                'price': price_float,
                                'unit_price': price_float / quantity_int if quantity_int > 1 else price_float
                            }
                            
                            # Add to results and mark as seen
                            result['items'].append(item)
                            seen_descriptions.add(description.lower())
                            break
                        except (ValueError, ZeroDivisionError) as e:
                            logging.debug(f"Error processing item: {e}")
                            continue
                            
                    except (ValueError, IndexError) as e:
                        logging.debug(f"Error parsing item line: {line}. Error: {str(e)}")
                        continue
        
        # Extract totals with specialized patterns
        # Subtotal patterns
        subtotal_patterns = [
            r'(?i)(?:sub[\s\-]*total|merchandise|basket\s*total)[\s\:]*\$?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)(?:sub[\s\-]*total|merchandise|basket\s*total)[\s\:]*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)sub[\s\-]*total\s*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})'
        ]
        
        # Tax patterns
        tax_patterns = [
            r'(?i)(?:tax|sales\s*tax|vat)[\s\:]*\$?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)(?:tax|sales\s*tax|vat)[\s\:]*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)\btax\b[\s\:]*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})'
        ]
        
        # Total patterns
        total_patterns = [
            r'(?i)(?:total|amount\s*due|balance\s*due|grand\s*total)[\s\:]*\$?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)(?:total|amount\s*due|balance\s*due|grand\s*total)[\s\:]*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})',
            r'(?i)\btotal\b[\s\:]*[\$£€]?(\d{1,3}(?:,\d{3})*\.\d{2})'
        ]
        
        # Extract subtotal
        for pattern in subtotal_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    result['subtotal'] = float(match.group(1).replace(',', ''))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract tax
        for pattern in tax_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    result['tax'] = float(match.group(1).replace(',', ''))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract total
        for pattern in total_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    result['total'] = float(match.group(1).replace(',', ''))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract payment method
        payment_patterns = [
            r'(?i)(VISA|MASTERCARD|AMEX|DISCOVER|CASH|CHECK|EBT)',
            r'(?i)PAID\s*(?:WITH|VIA|BY)?\s*(\w+)'
        ]
        
        for pattern in payment_patterns:
            match = re.search(pattern, text)
            if match:
                result['payment_method'] = match.group(1).upper()
                break
        
        # If we have items but no subtotal, calculate it
        if result['items'] and not result['subtotal']:
            subtotal = sum(item['price'] for item in result['items'])
            result['subtotal'] = round(subtotal, 2)
        
        # If we have subtotal and tax but no total, calculate it
        if result['subtotal'] and result['tax'] and not result['total']:
            result['total'] = round(result['subtotal'] + result['tax'], 2)
        
        # If we have subtotal and total but no tax, calculate it
        if result['subtotal'] and result['total'] and not result['tax']:
            result['tax'] = round(result['total'] - result['subtotal'], 2)
        
        logging.info(f"Costco receipt parser extracted {len(result['items'])} items")
        return result

    def mark_processing_failed(self, error: Union[str, Dict[str, Any]]) -> None:
        """Mark the receipt processing as failed with an error message or detailed error info."""
        self.processing_status = "failed"
        self.processing_error = error

    def get_extraction_confidence(self) -> Dict[str, Any]:
        """
        Get a report of confidence levels for all extracted data.
        
        Returns:
            Dictionary with field names and their confidence scores
        """
        confidence_report = {
            'overall': self.confidence_score or 0.0,
            'fields': self.confidence_scores or {},
            'items': [
                {
                    'description': item.description,
                    'confidence': item.confidence_score or 0.0,
                    'field_confidence': item.confidence_scores or {}
                } for item in self.items
            ]
        }
        return confidence_report

    def to_dict(self) -> Dict[str, Any]:
        """Convert receipt to dictionary format suitable for JSON serialization."""
        return {
            'id': str(self.id),
            'expense_id': str(self.expense_id) if self.expense_id else None,
            'image_url': self.image_url,
            'store_name': self.store_name,
            'transaction_date': self.transaction_date.isoformat() if self.transaction_date else None,
            'subtotal_amount': self.subtotal_amount,
            'tax_amount': self.tax_amount,
            'total_amount': self.total_amount,
            'items': [item.dict() for item in self.items],
            'processed_date': self.processed_date.isoformat(),
            'processing_status': self.processing_status,
            'processing_error': self.processing_error,
            'currency_type': self.currency_type,
            'payment_method': self.payment_method,
            'confidence_score': self.confidence_score,
            'processing_time': self.processing_time,
            'location_data': self.location_data
        }

    @property
    def date(self) -> Optional[datetime]:
        """Getter for the date alias."""
        return self.transaction_date
        
    @date.setter
    def date(self, value: Optional[datetime]) -> None:
        """Setter for the date alias."""
        self.transaction_date = value
        
    @property
    def subtotal(self) -> Optional[float]:
        """Getter for the subtotal alias."""
        return self.subtotal_amount
        
    @subtotal.setter
    def subtotal(self, value: Optional[float]) -> None:
        """Setter for the subtotal alias."""
        self.subtotal_amount = value
        
    @property
    def tax(self) -> Optional[float]:
        """Getter for the tax alias."""
        return self.tax_amount
        
    @tax.setter
    def tax(self, value: Optional[float]) -> None:
        """Setter for the tax alias."""
        self.tax_amount = value
        
    @property
    def total(self) -> Optional[float]:
        """Getter for the total alias."""
        return self.total_amount
        
    @total.setter
    def total(self, value: Optional[float]) -> None:
        """Setter for the total alias."""
        self.total_amount = value
        
    @property
    def currency(self) -> Optional[str]:
        """Getter for the currency alias."""
        return self.currency_type
        
    @currency.setter
    def currency(self, value: Optional[str]) -> None:
        """Setter for the currency alias."""
        self.currency_type = value
        
    @property
    def error_message(self) -> Optional[str]:
        """Getter for the error_message alias."""
        if isinstance(self.processing_error, str):
            return self.processing_error
        elif self.processing_error:
            return str(self.processing_error)
        return None
        
    @error_message.setter
    def error_message(self, value: Optional[str]) -> None:
        """Setter for the error_message alias."""
        self.processing_error = value 