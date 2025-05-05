"""Receipt model implementation."""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator, field_validator
from decimal import Decimal
import logging
import re

logger = logging.getLogger(__name__)

class ReceiptItem(BaseModel):
    """Model for individual receipt items with validation."""
    
    name: str = Field(..., min_length=1, max_length=200)
    quantity: Decimal = Field(default=Decimal('1'), ge=Decimal('0'))
    price: Decimal = Field(..., ge=Decimal('0'))
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suspicious: bool = Field(default=False)
    category: Optional[str] = None
    notes: Optional[str] = None
    
    @field_validator('name')
    @classmethod
    def clean_name(cls, v):
        """Clean and validate item name."""
        # Remove excessive whitespace
        v = ' '.join(v.split())
        # Remove common OCR artifacts
        v = re.sub(r'[^\w\s\-\'\.&$@#%]', '', v)
        if not v:
            v = "Unknown Item"
        return v
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        """Ensure price has at most 2 decimal places and is reasonable."""
        if v.as_tuple().exponent < -2:
            v = v.quantize(Decimal('0.01'))
        if v > Decimal('10000'):  # Probably an error if item costs more than $10,000
            raise ValueError('Price seems unreasonably high')
        return v
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        """Ensure quantity has at most 3 decimal places and is reasonable."""
        if v.as_tuple().exponent < -3:
            v = v.quantize(Decimal('0.001'))
        if v > Decimal('1000'):  # Probably an error if quantity is over 1000
            raise ValueError('Quantity seems unreasonably high')
        return v
    
    def calculate_confidence(self) -> float:
        """Calculate item-level confidence score."""
        factors = {
            'name_quality': 0.3,  # Name looks reasonable
            'price_reasonability': 0.4,  # Price within reasonable range
            'quantity_reasonability': 0.3  # Quantity within reasonable range
        }
        
        # Check name quality
        name_score = 0.0
        if len(self.name) >= 3:  # At least 3 characters
            name_score += 0.5
        if re.match(r'^[A-Z0-9\s\-\'\.&$@#%]+$', self.name):  # Valid characters
            name_score += 0.5
            
        # Check price reasonability
        price_score = 1.0
        price_float = float(self.price)
        if price_float == 0:
            price_score = 0.0
        elif price_float > 1000:
            price_score = 0.5
            
        # Check quantity reasonability
        quantity_score = 1.0
        quantity_float = float(self.quantity)
        if quantity_float == 0:
            quantity_score = 0.0
        elif quantity_float > 100:
            quantity_score = 0.5
            
        scores = {
            'name_quality': name_score,
            'price_reasonability': price_score,
            'quantity_reasonability': quantity_score
        }
        
        confidence = sum(factors[k] * scores[k] for k in factors)
        return round(confidence, 2)

class Receipt(BaseModel):
    """Enhanced receipt model with validation and confidence scoring."""
    
    # Required fields with defaults
    store_name: str = Field(default="Unknown Store", min_length=1, max_length=100)
    total_amount: Decimal = Field(..., ge=Decimal('0'))
    items: List[ReceiptItem] = Field(default_factory=list)
    
    # Optional fields with defaults
    date: Optional[datetime] = None
    tax_amount: Decimal = Field(default=Decimal('0'), ge=Decimal('0'))
    subtotal_amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    image_url: Optional[str] = None
    
    # Metadata
    receipt_id: UUID = Field(default_factory=uuid4)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_review: bool = Field(default=False)
    ocr_engine: Optional[str] = None
    processing_time: Optional[float] = None
    validation_notes: List[str] = Field(default_factory=list)
    debug_info: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('store_name')
    @classmethod
    def clean_store_name(cls, v):
        """Clean and validate store name."""
        v = ' '.join(v.split())  # Remove excessive whitespace
        v = re.sub(r'[^\w\s\-\'\.&]', '', v)  # Remove invalid characters
        return v or "Unknown Store"
    
    @field_validator('total_amount', 'tax_amount', 'subtotal_amount')
    @classmethod
    def validate_amounts(cls, v):
        """Ensure monetary amounts have at most 2 decimal places."""
        if v is None:
            return v
        if v.as_tuple().exponent < -2:
            return v.quantize(Decimal('0.01'))
        return v
    
    @field_validator('items')
    @classmethod
    def validate_items(cls, v):
        """Ensure items list is valid."""
        if not v:
            logger.warning("Receipt has no items")
            return []
        return v
    
    @model_validator(mode='after')
    def validate_totals(self):
        """Validate and fix totals if needed."""
        items = self.items
        total = self.total_amount
        tax = self.tax_amount
        subtotal = self.subtotal_amount
        
        if not items:
            return self
            
        # Calculate items total
        items_total = sum(item.price * item.quantity for item in items)
        
        # If subtotal is missing, use items total
        if subtotal is None:
            self.subtotal_amount = items_total
            
        # If tax is zero but we can calculate it, do so
        if tax == 0 and total and subtotal:
            calculated_tax = total - subtotal
            if calculated_tax > 0:
                self.tax_amount = calculated_tax
                
        # If total is missing but we can calculate it, do so
        if total is None and subtotal is not None:
            self.total_amount = subtotal + tax
            
        return self
    
    def calculate_totals(self) -> None:
        """Calculate and validate totals."""
        items_total = sum(item.price * item.quantity for item in self.items)
        
        if not self.subtotal_amount:
            self.subtotal_amount = items_total
            self.add_validation_note("Subtotal was missing and calculated from items")
        
        if not self.tax_amount:
            if self.total_amount and self.subtotal_amount:
                self.tax_amount = self.total_amount - self.subtotal_amount
                if self.tax_amount > 0:
                    self.add_validation_note("Tax amount was calculated from total and subtotal")
        
        expected_total = self.subtotal_amount + self.tax_amount
        if abs(float(expected_total - self.total_amount)) > 0.01:
            logger.warning(f"Total amount mismatch: {self.total_amount} != {expected_total}")
            self.requires_review = True
            self.validation_notes.append(f"Total amount mismatch: expected {expected_total}, got {self.total_amount}")
    
    def calculate_confidence(self) -> float:
        """Calculate overall receipt confidence score."""
        weights = {
            'items_confidence': 0.3,
            'totals_match': 0.3,
            'metadata_completeness': 0.2,
            'store_recognition': 0.2
        }
        
        # Calculate items confidence
        items_confidence = (
            sum(item.calculate_confidence() for item in self.items) / len(self.items)
            if self.items else 0.0
        )
        
        # Check if totals match
        items_total = sum(item.price * item.quantity for item in self.items)
        expected_total = items_total + self.tax_amount
        totals_diff = abs(float(expected_total - self.total_amount))
        totals_match = 1.0 if totals_diff <= 0.01 else (0.5 if totals_diff <= 1.0 else 0.0)
        
        # Check metadata completeness
        metadata_fields = ['date', 'payment_method', 'image_url']
        metadata_completeness = sum(1 for f in metadata_fields if getattr(self, f) is not None) / len(metadata_fields)
        
        # Store recognition confidence
        store_recognition = 0.0
        if self.store_name and self.store_name != "Unknown Store":
            store_recognition = 0.5  # Base score for having a store name
            if len(self.store_name) > 3 and not re.search(r'[^A-Za-z0-9\s\-\'\.&]', self.store_name):
                store_recognition = 1.0  # Full score for clean store name
        
        # Calculate weighted score
        confidence = sum(weights[k] * v for k, v in {
            'items_confidence': items_confidence,
            'totals_match': totals_match,
            'metadata_completeness': metadata_completeness,
            'store_recognition': store_recognition
        }.items())
        
        self.confidence_score = round(confidence, 2)
        
        # Set review flag and add notes for low confidence areas
        if items_confidence < 0.7:
            self.add_validation_note(f"Low items confidence: {items_confidence:.2f}")
        if totals_match < 0.7:
            self.add_validation_note(f"Totals mismatch: difference of ${totals_diff:.2f}")
        if metadata_completeness < 0.7:
            self.add_validation_note("Missing important metadata fields")
        if store_recognition < 0.7:
            self.add_validation_note("Low confidence in store recognition")
        
        if self.confidence_score < 0.7:
            self.requires_review = True
            self.add_validation_note(f"Overall low confidence score: {self.confidence_score:.2f}")
        
        return self.confidence_score
    
    def add_validation_note(self, note: str) -> None:
        """Add a validation note and mark for review."""
        if note not in self.validation_notes:
            self.validation_notes.append(note)
            self.requires_review = True
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get detailed debug information."""
        return {
            'receipt_id': str(self.receipt_id),
            'confidence_score': self.confidence_score,
            'requires_review': self.requires_review,
            'validation_notes': self.validation_notes,
            'ocr_engine': self.ocr_engine,
            'processing_time': self.processing_time,
            'items_count': len(self.items),
            'suspicious_items': [item.dict() for item in self.items if item.suspicious],
            'totals': {
                'items_total': str(sum(item.price * item.quantity for item in self.items)),
                'subtotal': str(self.subtotal_amount) if self.subtotal_amount else None,
                'tax': str(self.tax_amount),
                'total': str(self.total_amount)
            },
            **self.debug_info
        }

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