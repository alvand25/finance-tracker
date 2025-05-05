"""Unified receipt analysis service to centralize OCR and receipt parsing."""

import os
import logging
import re
from typing import Dict, Any, Optional, Union, Tuple
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime
from werkzeug.datastructures import FileStorage
from PIL import Image
import io

from models.receipt import Receipt, ReceiptItem
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR
from utils.receipt_analyzer import ReceiptAnalyzer
from ocr.google_vision_config import GoogleVisionConfig

logger = logging.getLogger(__name__)

class ParsedReceipt:
    """
    Data class to hold parsed receipt information.
    Used to standardize the interface between different receipt analyzers.
    """
    
    def __init__(self):
        """Initialize parsed receipt with default values."""
        self.store_name = None
        self.total_amount = None
        self.subtotal_amount = None
        self.tax_amount = None
        self.date = None
        self.time = None
        self.items = []
        self.raw_text = None
        self.image_path = None
        self.currency_type = "USD"  # Default currency
        self.payment_method = None
        self.processing_status = "pending"  # pending, processing, completed, failed, partial
        self.processing_error = None
        self.confidence_score = 0.0
        self.confidence_scores = {}
        self.metadata = {}
        
        # Validation fields
        self.flagged_for_review = False
        self.validation_notes = []
        self.expected_item_count = None
        self.has_suspicious_items = False

    def to_receipt_model(self) -> Receipt:
        """Convert to Receipt model for database storage."""
        items = []
        for item_dict in self.items:
            item = ReceiptItem(
                name=item_dict.get('name', ''),
                price=item_dict.get('total', 0),
                quantity=item_dict.get('quantity', 1),
                item_type=item_dict.get('category', 'general'),
                metadata=item_dict.get('metadata', {})
            )
            items.append(item)
        
        # Prepare metadata dictionary
        metadata = self.metadata.copy() if self.metadata else {}
        
        # Add confidence scores to metadata
        if self.confidence_scores:
            metadata.update({
                'confidence_scores': self.confidence_scores,
                'confidence': self.confidence_score
            })
        
        # Add validation information to metadata
        if self.flagged_for_review:
            metadata.update({
                'flagged_for_review': self.flagged_for_review,
                'validation_notes': self.validation_notes
            })
        
        if self.expected_item_count is not None:
            metadata['expected_item_count'] = self.expected_item_count
            
        if self.has_suspicious_items:
            metadata['has_suspicious_items'] = self.has_suspicious_items
        
        # Create Receipt model
        receipt = Receipt(
            store_name=self.store_name,
            date=self.date or datetime.now(),
            total_amount=self.total_amount or 0,
            tax_amount=self.tax_amount,
            subtotal_amount=self.subtotal_amount,
            payment_method=self.payment_method,
            currency=self.currency_type,
            status=self.processing_status,
            items=items,
            metadata=metadata
        )
        
        return receipt

class UnifiedReceiptAnalyzer:
    """Central service for receipt analysis with unified interface."""
    
    def __init__(self, upload_dir: str = 'uploads', debug_mode: bool = False):
        self.upload_dir = upload_dir
        self.debug_mode = debug_mode
        self.preprocessor = ImagePreprocessor(debug_mode=debug_mode)
        self.analyzer = ReceiptAnalyzer(debug_mode=debug_mode)
        
        # Ensure upload directory exists
        os.makedirs(upload_dir, exist_ok=True)
        
        # Initialize OCR engines
        self.ocr = self._setup_ocr()
        
    def _setup_ocr(self):
        """Set up optimal OCR engine based on availability."""
        # Try Google Cloud Vision first
        try:
            config = GoogleVisionConfig()
            if config.is_configured:
                logger.info("Using Google Cloud Vision OCR")
                return GoogleVisionOCR(credentials_path=config.credentials_path)
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Vision OCR: {str(e)}")
            
        # Fall back to Tesseract
        try:
            logger.info("Falling back to Tesseract OCR")
            return TesseractOCR()
        except Exception as e:
            logger.error(f"Failed to initialize Tesseract OCR: {str(e)}")
            return None
    
    def analyze(self, receipt_text: str, store_hint: Optional[str] = None) -> ParsedReceipt:
        """
        Analyze receipt text to extract structured information using a unified approach.
        Uses multiple extractors and selects the best results or combines them.
        
        Args:
            receipt_text: Raw receipt text from OCR
            store_hint: Optional hint about the store name
            
        Returns:
            ParsedReceipt: Parsed receipt data with confidence scores
        """
        logger.debug("Starting unified receipt analysis")
        
        # Initialize a basic ParsedReceipt with minimum values
        result = ParsedReceipt()
        result.raw_text = receipt_text
        
        try:
            # Use analyzer to extract receipt information
            logger.debug("Using receipt analyzer")
            rule_based_results = self.analyzer.analyze_receipt(receipt_text)
            
            # Initialize the result with defaults from the rule-based extractor
            store_name = rule_based_results.get('store', '')  # Note: in analyzer it's 'store', not 'store_name'
            total_amount = rule_based_results.get('total', 0.0)  # Note: in analyzer it's 'total', not 'total_amount'
            items = rule_based_results.get('items', [])
            
            # Fix store name fragmentation for cases like "H MART" by looking for known store patterns
            if not store_name or len(store_name) < 4:
                # Check for store names split across lines in the first few lines
                lines = receipt_text.split('\n')[:8]  # Only check first 8 lines
                
                combined_lines = ' '.join(line.strip() for line in lines if line.strip())
                
                # Look for known fragmented store names
                store_patterns = {
                    'H MART': [r'H\s+MART', r'H-MART', r'HMART'],
                    'TRADER JOE\'S': [r'TRADER\s+JOE', r'TRADER\s+JOES'],
                    'KEY FOOD': [r'KEY\s+FOOD'],
                    'WHOLE FOODS': [r'WHOLE\s+FOODS', r'WF\s+MARKET'],
                    'STOP & SHOP': [r'STOP\s+&\s+SHOP', r'STOP\s+AND\s+SHOP'],
                }
                
                for store, patterns in store_patterns.items():
                    for pattern in patterns:
                        if re.search(pattern, combined_lines, re.IGNORECASE):
                            logger.debug(f"Fixed fragmented store name: {store}")
                            store_name = store
                            break
                    if store_name:
                        break
                
                # Special case for H Mart - sometimes found after handling Korean characters
                if not store_name and any('MART' in line.upper() for line in lines):
                    for line in lines:
                        if 'H' in line.upper() and len(line.strip()) < 5:
                            next_line_idx = lines.index(line) + 1
                            if next_line_idx < len(lines) and 'MART' in lines[next_line_idx].upper():
                                store_name = 'H MART'
                                logger.debug("Detected H MART from split lines")
                                break

            # Validate the results from rule-based extractor
            validation_issues = []
            
            # Default confidence scores (optimistic starting point)
            store_confidence = 0.9 if store_name else 0.3
            total_confidence = 0.9 if total_amount and total_amount > 0 else 0.3
            items_confidence = 0.9 if items else 0.3
            
            # If we have a store hint, try to validate or improve store detection
            if store_hint:
                if store_name.lower() == store_hint.lower():
                    # Our extraction matches the hint, boost confidence
                    store_confidence = 0.98
                elif not store_name:
                    # We couldn't extract, but we have a hint
                    store_name = store_hint
                    store_confidence = 0.85
                    logger.debug(f"Using store hint: {store_name}")
                else:
                    # Our extraction differs from hint, prefer our extraction but reduce confidence
                    store_confidence = 0.7
                    logger.debug(f"Store extraction '{store_name}' differs from hint '{store_hint}'")
            
            # For Costco receipts specifically, handle edge cases
            if store_name and 'costco' in store_name.lower():
                logger.debug("Detected Costco receipt, applying special handling")
                
                # Handle common Costco issues
                if not total_amount or total_amount == 0.0:
                    # Search for more Costco-specific total patterns
                    costco_patterns = [
                        r'(?:TOTAL|Total)(?:\s*CHARGE|\s*Charge)?\s*[\$]?\s*(\d+\.\d{2})',
                        r'(?:TOTAL|Total)(?:\s*SALE|\s*Sale|AMOUNT)?\s*[\$]?\s*(\d+\.\d{2})',
                        r'(?:XXXX\s+)+Amount\s+(\d+\.\d{2})',
                        r'(?:XXXX\s+)+Total\s+(\d+\.\d{2})',
                        r'^\s*(TOTAL|AMOUNT DUE|BALANCE)\s*[:\-]?\s*\$?([\d,]+\.\d{2})',
                        r'\*\*\*\s*(TOTAL)\s*[:\-]?\s*\$?([\d,]+\.\d{2})',
                        r'TOTAL\s+[\$:]*\s*([\d,]+\.\d{2})',
                        r'5UBTOTAL\s+(\d+\.\d{2})',  # Costco OCR often reads "SUBTOTAL" as "5UBTOTAL"
                        r'/?\s*5UBTOTAL\s+(\d+\.\d{2})',  # With potential slash prefix
                        r'[*\s]*TOTAL[*\s]*[\$:]*\s*([\d,]+\.\d{2})',  # Match TOTAL with any surrounding stars or spaces
                        r'SUBTOTAL\s+(\d+\.\d{2})'  # Use subtotal as fallback for Costco
                    ]
                    
                    for pattern in costco_patterns:
                        for match in re.finditer(pattern, receipt_text, re.IGNORECASE):
                            try:
                                # Check which group contains the amount - some patterns use group 1, others group 2
                                if len(match.groups()) > 1 and match.group(2):
                                    potential_total = float(match.group(2))
                                else:
                                    potential_total = float(match.group(1))
                                
                                if potential_total > 0:
                                    total_amount = potential_total
                                    total_confidence = 0.8  # Slightly lower confidence for this fallback method
                                    logger.debug(f"Found Costco-specific total: ${total_amount:.2f}")
                                    break
                            except (ValueError, IndexError):
                                continue
                    
                    if total_amount == 0.0:
                        # Look for largest dollar amount on the receipt as a last resort
                        largest_amount = 0.0
                        # Focus on the last 5 lines for total
                        last_lines = receipt_text.split('\n')[-5:]
                        last_text = '\n'.join(last_lines)
                        
                        # Find all potential totals in the last 5 lines
                        dollar_amounts = []
                        for match in re.finditer(r'[\$]?\s*(\d+\.\d{2})', last_text):
                            try:
                                amount = float(match.group(1))
                                if amount < 300:  # Reasonable upper limit for most receipts
                                    dollar_amounts.append(amount)
                            except (ValueError, IndexError):
                                continue
                        
                        # Sort amounts and take the largest
                        if dollar_amounts:
                            dollar_amounts.sort()
                            largest_amount = dollar_amounts[-1]
                        
                        if largest_amount > 0:
                            total_amount = largest_amount
                            total_confidence = 0.7  # Lower confidence for this method
                            logger.debug(f"Using largest amount as Costco total: ${total_amount:.2f}")
            
            # For H Mart receipts, handle specific issues
            elif store_name and ('h mart' in store_name.lower() or 'hmart' in store_name.lower()):
                logger.debug("Detected H Mart receipt, applying special handling")
                
                # Fix common H Mart garbled item names
                for item in items:
                    item_name = item.get('name', '').strip()
                    
                    # Replace common OCR errors in H Mart receipts
                    item_name = re.sub(r'^[A-Z0-9]{1,3}\s+[A-Z0-9]{1,3}\s+', '', item_name)  # Remove leading garbled tokens
                    
                    # Check if item name starts with unreadable tokens but ends with food vocabulary
                    # Common pattern: "LITE BOV BEE BY FUEL UN" -> "BEEF"
                    food_vocab = ['BEEF', 'PORK', 'CHICKEN', 'FISH', 'RICE', 'NOODLE', 'KIMCHI', 'TOFU', 
                                 'MILK', 'EGGS', 'BREAD', 'SAUCE', 'OIL', 'SALT', 'SUGAR', 'TEA', 'SNACK']
                    
                    tokens = item_name.split()
                    if len(tokens) >= 4:
                        unreadable_start = all(len(token) <= 3 for token in tokens[:2])
                        food_match = any(food in item_name for food in food_vocab)
                        
                        if unreadable_start and food_match:
                            # Truncate unreadable beginning tokens
                            for food in food_vocab:
                                if food in item_name:
                                    food_index = item_name.find(food)
                                    if food_index > 0:
                                        item_name = item_name[food_index:]
                                        logger.debug(f"Fixed garbled H Mart item: {item.get('name')} -> {item_name}")
                                        break
                    
                    # Update the item name
                    item['name'] = item_name
            
            # Check for item count hints in the raw text
            expected_item_count = None
            item_count_matches = [
                re.search(r'Items\s+in\s+Transaction[:\s]+(\d+)', receipt_text, re.IGNORECASE),
                re.search(r'ITEM[S]?\s+COUNT[:\s]+(\d+)', receipt_text, re.IGNORECASE),
                re.search(r'TOTAL\s+ITEM[S]?[:\s]+(\d+)', receipt_text, re.IGNORECASE),
                re.search(r'TOTAL\s+NUMBER\s+OF\s+ITEMS\s+(?:SOLD|PURCHASED)[^\d]*(\d+)', receipt_text, re.IGNORECASE),
                re.search(r'ITEM[S]?\s+(?:SOLD|PURCHASED|IN\s+CART)[^\d]*(\d+)', receipt_text, re.IGNORECASE)
            ]
            
            for match in item_count_matches:
                if match:
                    try:
                        expected_item_count = int(match.group(1))
                        logger.debug(f"Found expected item count: {expected_item_count}")
                        break
                    except (ValueError, IndexError):
                        pass
            
            # Flag for potentially suspicious items
            has_suspicious_items = False
            
            # Check for payment-related keywords in item names
            payment_keywords = [
                'card', 'credit', 'debit', 'visa', 'mastercard', 'payment', 'paid',
                'change', 'cash', 'total', 'subtotal', 'balance', 'approved', 
                'authorization', 'receipt', 'transaction', 'purchase', 'terminal',
                'auth', 'sequence', 'account', 'approv', 'reference', 'auth code',
                'xxxx', 'chase', 'amex', 'discover'
            ]
            
            # If we didn't get any items, reduce confidence drastically
            if not items:
                items_confidence = 0.1
                validation_issues.append("No items were extracted from the receipt")
            else:
                # Check for item issues and mark suspicious items
                for item in items:
                    item_name = item.get('name', '').lower()
                    item_price = item.get('total', 0.0)
                    
                    is_suspicious = False
                    
                    # Check for payment-related keywords in item names
                    if any(keyword in item_name for keyword in payment_keywords):
                        logger.debug(f"Found payment keyword in item name: {item_name}")
                        is_suspicious = True
                    
                    # Check for extremely high prices (likely errors)
                    if item_price is not None and item_price > 300:  # Arbitrary threshold
                        logger.debug(f"Found suspiciously high price: ${item_price:.2f} for {item_name}")
                        is_suspicious = True
                    
                    # Check if price equals total amount (shouldn't happen for genuine items)
                    if item_price is not None and total_amount is not None and abs(item_price - total_amount) < 0.01:
                        logger.debug(f"Item price matches total amount: ${item_price:.2f}")
                        is_suspicious = True
                    
                    # Check for zero price
                    if item_price is not None and item_price == 0.00:
                        logger.debug(f"Found zero price item: {item_name}")
                        is_suspicious = True
                    
                    # Check for suspiciously short or numeric-only names
                    if len(item_name.strip()) < 3 or re.match(r'^[\d\s\W]+$', item_name):
                        logger.debug(f"Found suspiciously short or numeric-only name: {item_name}")
                        is_suspicious = True
                    
                    # Check for names with more than 60% numeric tokens
                    tokens = item_name.split()
                    numeric_tokens = sum(1 for token in tokens if token.isdigit() or re.match(r'^\d+[\-\.]\d+$', token))
                    if tokens and len(tokens) > 0 and numeric_tokens / len(tokens) > 0.6:
                        logger.debug(f"Found name with >60% numeric tokens: {item_name}")
                        is_suspicious = True
                    
                    # Check for names with long digit sequences
                    if re.search(r'\d{4,}', item_name):
                        logger.debug(f"Found name with 4+ digit sequence: {item_name}")
                        is_suspicious = True
                    
                    # Mark suspicious items instead of filtering them out
                    if is_suspicious:
                        has_suspicious_items = True
                        item['suspicious'] = True
                        logger.debug(f"Marked suspicious item: {item}")
                    else:
                        item['suspicious'] = False
                
                # Add validation note if we have suspicious items
                if has_suspicious_items:
                    suspicious_count = sum(1 for item in items if item.get('suspicious', False))
                    validation_issues.append(f"Found {suspicious_count} suspicious items that may not be actual products")
                
                # Validate against expected item count
                if expected_item_count is not None:
                    extracted_count = len(items)
                    if abs(extracted_count - expected_item_count) > 1:  # Allow for small variance
                        # This is a significant mismatch
                        logger.warning(f"Mismatch between extracted ({extracted_count}) and expected ({expected_item_count}) item count")
                        validation_issues.append(f"Item count mismatch: extracted {extracted_count}, expected {expected_item_count}")
                        
                        # More serious discrepancy when we have significantly fewer items than expected
                        if extracted_count < expected_item_count - 2:
                            validation_issues.append(f"Parsed fewer items than expected. Receipt indicates {expected_item_count} items but only found {extracted_count}")
                            # Lower confidence more if subtotal doesn't match total, which would suggest we're truly missing items
                            if total_amount is not None and total_amount > 0:
                                items_sum = sum(item.get('total', 0) for item in items)
                                if items_sum > 0 and (abs(items_sum - total_amount) / total_amount) > 0.1:
                                    items_confidence -= 0.1
                                    logger.warning(f"Lowering confidence due to missing items and total mismatch. Total: ${total_amount:.2f}, Sum: ${items_sum:.2f}")
                        
                        # Adjust confidence based on the degree of mismatch
                        discrepancy_ratio = min(extracted_count, expected_item_count) / max(extracted_count, expected_item_count)
                        items_confidence *= discrepancy_ratio
            
            # Calculate sum of item prices for validation
            item_sum = sum(item.get('total', 0.0) for item in items if not item.get('suspicious', False))
            
            # Validate that sum of items roughly matches total (allowing for tax differences)
            if total_amount > 0 and item_sum > 0:
                # Check for significant difference between sum of items and total
                diff = abs(item_sum - total_amount)
                if diff > 5.0:  # $5 threshold
                    validation_issues.append(f"Parsed item sum (${item_sum:.2f}) differs from receipt total (${total_amount:.2f}) by ${diff:.2f}")
                    # Reduce confidence
                    items_confidence = max(0.5, items_confidence - 0.2)
                    total_confidence = max(0.5, total_confidence - 0.1)
                    
                    logger.warning(f"Item sum (${item_sum:.2f}) differs significantly from total (${total_amount:.2f})")
            
            # Adjust overall confidence based on relation between total and sum of items
            try:
                if total_amount is not None and total_amount > 0 and items:
                    items_sum = sum(item.get('total', 0) for item in items)
                    if items_sum > 0:
                        # Calculate the ratio between sum of items and total
                        ratio = min(items_sum, total_amount) / max(items_sum, total_amount)
                        
                        # If they're very close, it's a good sign
                        if ratio > 0.9:
                            items_confidence = max(items_confidence, 0.9)
                            total_confidence = max(total_confidence, 0.9)
                            logger.debug(f"Total matches sum of items well (ratio: {ratio:.2f})")
                        # If they're somewhat close
                        elif ratio > 0.7:
                            # Maintain confidence
                            logger.debug(f"Total and sum of items are somewhat consistent (ratio: {ratio:.2f})")
                        # If they're quite different
                        else:
                            items_confidence *= ratio
                            total_confidence *= ratio
                            logger.debug(f"Discrepancy between total and sum of items (ratio: {ratio:.2f})")
                            validation_issues.append(f"Sum of items (${items_sum:.2f}) differs from total (${total_amount:.2f})")
            except Exception as e:
                logger.error(f"Error calculating confidence from item sum: {str(e)}")
                # Don't let this error prevent processing - just continue
            
            # Set overall status
            if total_amount is not None and total_amount > 0 and store_name:
                processing_status = "SUCCESS"
            elif total_amount is not None and total_amount > 0:
                processing_status = "PARTIAL_SUCCESS"
                validation_issues.append("Missing store name")
            elif store_name:
                processing_status = "PARTIAL_SUCCESS"
                validation_issues.append("Missing total amount")
            else:
                processing_status = "FAILURE"
                validation_issues.append("Missing critical information (store name and total)")
            
            # Calculate average confidence - with safety checks
            try:
                average_confidence = (store_confidence + total_confidence + items_confidence) / 3
            except Exception as e:
                logger.error(f"Error calculating average confidence: {str(e)}")
                average_confidence = 0.3  # Default to low confidence on calculation error
            
            # Floor confidence at 0.75 if certain criteria are met indicating high quality results 
            if (store_name and 
                total_amount is not None and total_amount > 0 and
                items and len(items) >= 3 and
                average_confidence > 0.5):
                
                # Check how many items have valid names and prices
                valid_items = sum(1 for item in items if 
                                 len(item.get('name', '').strip()) > 3 and  # Valid name
                                 not item.get('suspicious', False) and      # Not suspicious
                                 item.get('total', 0) > 0)                 # Valid price
                
                # If 80% or more items are valid, boost confidence
                if valid_items / len(items) >= 0.8:
                    logger.debug(f"Setting floor confidence of 0.75 due to high quality parsing")
                    average_confidence = max(average_confidence, 0.75)
                
                # Check for expected item count match
                if expected_item_count is not None:
                    if abs(len(items) - expected_item_count) <= 2:
                        # Close match to expected count also suggests good quality
                        logger.debug(f"Boosting confidence due to item count match with expected ({expected_item_count})")
                        average_confidence = max(average_confidence, 0.75)
            
            # Prepare the result with safety checks
            result = ParsedReceipt()
            result.store_name = store_name
            result.total_amount = float(total_amount) if total_amount is not None else 0.0
            result.items = items or []
            result.confidence_score = average_confidence
            result.confidence_scores = {
                'store': store_confidence,
                'total': total_confidence,
                'items': items_confidence
            }
            result.processing_status = processing_status
            
            # Add validation information
            if validation_issues:
                result.flagged_for_review = True
                result.validation_notes = validation_issues
            
            if expected_item_count is not None:
                result.expected_item_count = expected_item_count
            
            if has_suspicious_items:
                result.has_suspicious_items = True
            
            logger.debug(f"Completed unified receipt analysis with confidence: {average_confidence:.4f}")
            return result
            
        except Exception as e:
            # Global exception handler to ensure we always return something
            error_msg = f"Error in receipt analysis: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Create a minimal ParsedReceipt with error information
            result = ParsedReceipt()
            result.raw_text = receipt_text
            result.processing_status = "FAILURE"
            result.processing_error = error_msg
            result.confidence_score = 0.3
            result.flagged_for_review = True
            result.validation_notes = [f"Processing error: {str(e)}"]
            
            return result
            
    def _save_file(self, image_data: bytes, original_filename: str) -> str:
        """Save uploaded file to disk with unique filename."""
        from werkzeug.utils import secure_filename
        import uuid
        
        # Generate unique filename
        filename = secure_filename(original_filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{str(uuid.uuid4())[:8]}_{filename}"
        filepath = os.path.join(self.upload_dir, unique_filename)
        
        # Save file
        with open(filepath, 'wb') as f:
            f.write(image_data)
            
        return filepath 

    def process_file(self, file_or_path: Union[FileStorage, str, Path], 
                 options: Optional[Dict[str, Any]] = None) -> Tuple[ParsedReceipt, bool]:
        """
        Process a receipt image, extract text, and analyze it.
        
        Args:
            file_or_path: File upload object or path to image
            options: Processing options like store_hint, etc.
            
        Returns:
            Tuple of (ParsedReceipt, success_boolean)
        """
        parsed = ParsedReceipt()
        options = options or {}
        filename = ""
        
        try:
            # Handle different input types
            if isinstance(file_or_path, FileStorage):
                image_data = file_or_path.read()
                filename = file_or_path.filename
                image_path = self._save_file(image_data, filename)
                parsed.image_path = image_path
            elif isinstance(file_or_path, (str, Path)):
                image_path = str(file_or_path)
                parsed.image_path = image_path
                filename = os.path.basename(image_path)
                with open(image_path, 'rb') as f:
                    image_data = f.read()
            else:
                raise ValueError(f"Unsupported input type: {type(file_or_path)}")
            
            # Preprocess image
            processed_image = self.preprocessor.preprocess(io.BytesIO(image_data))
            
            # Extract text using OCR
            if self.ocr is None:
                parsed.processing_status = "FAILURE"
                parsed.processing_error = "No OCR engine available"
                parsed.confidence_score = 0.3
                parsed.validation_notes = ["Error: No OCR engine available"]
                parsed.flagged_for_review = True
                return parsed, False
                
            logger.info(f"Extracting text from receipt using {type(self.ocr).__name__}")
            ocr_result = self.ocr.extract_text(processed_image)
            parsed.raw_text = ocr_result["text"]
            
            # Check if OCR returned text
            if not parsed.raw_text or len(parsed.raw_text.strip()) < 10:
                parsed.processing_status = "FAILURE"
                parsed.processing_error = "OCR extracted insufficient text"
                parsed.confidence_score = 0.3
                parsed.validation_notes = ["Error: OCR extracted insufficient text"]
                parsed.flagged_for_review = True
                return parsed, False
            
            # Get store hint if provided
            store_hint = options.get('store_hint')
            
            # Analyze the extracted text
            parsed = self.analyze(parsed.raw_text, store_hint)
            parsed.image_path = image_path
            
            return parsed, parsed.processing_status != "FAILURE"
            
        except Exception as e:
            logger.error(f"Error processing receipt file '{filename}': {str(e)}", exc_info=True)
            parsed.processing_status = "FAILURE"
            parsed.processing_error = str(e)
            parsed.confidence_score = 0.3
            parsed.validation_notes = [f"Processing error: {str(e)}"]
            parsed.flagged_for_review = True
            return parsed, False 