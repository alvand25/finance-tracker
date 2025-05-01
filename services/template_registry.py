from typing import List, Dict, Optional, Any, Tuple
from uuid import UUID
import os
import json
import traceback
from datetime import datetime

from models.receipt_template import ReceiptTemplate
from storage.json_storage import JSONStorage

# Custom JSON encoder that can handle UUID objects
class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        print(f"UUIDEncoder.default called with: {type(obj)} - {obj}")
        try:
            if isinstance(obj, UUID):
                # Convert UUID objects to strings
                print(f"Converting UUID to string: {obj}")
                return str(obj)
            elif isinstance(obj, datetime):
                # Convert datetime objects to ISO format strings
                print(f"Converting datetime to string: {obj}")
                return obj.isoformat()
            # Let the base class handle everything else
            try:
                result = super().default(obj)
                print(f"Super().default returned: {result}")
                return result
            except TypeError as e:
                print(f"TypeError in super().default: {e}")
                # Last resort: convert to string
                str_result = str(obj)
                print(f"Converted to string instead: {str_result}")
                return str_result
        except Exception as e:
            print(f"EXCEPTION in UUIDEncoder.default: {e}")
            traceback.print_exc()
            return str(obj)  # Ultimate fallback

class TemplateRegistry:
    """
    Service for managing and retrieving receipt templates.
    Handles storage, versioning, and matching of templates to receipts.
    """
    
    def __init__(self, storage_path: str = "data/templates", create_built_in: bool = True):
        """
        Initialize the template registry.
        
        Args:
            storage_path: Path to store templates
            create_built_in: Whether to create built-in templates
        """
        self.storage_path = storage_path
        self.templates_cache = {}
        
        # Ensure storage directory exists
        os.makedirs(storage_path, exist_ok=True)
        
        # Load existing templates
        self._load_templates()
        
        # Create built-in templates if needed
        if create_built_in and len(self.templates_cache) == 0:
            built_in_templates = self._create_built_in_templates()
            
            # Save built-in templates
            for template in built_in_templates:
                try:
                    self.save_template(template)
                    logger.info(f"Created built-in template for {template.name} with id {template.id}")
                except Exception as e:
                    logger.error(f"Error saving built-in template {template.name}: {str(e)}")
                    traceback.print_exc()
    
    def _ensure_templates_dir(self) -> None:
        """Ensure the templates directory exists."""
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
    
    def _load_templates(self) -> None:
        """Load all templates from storage."""
        print("\n===== LOADING TEMPLATES =====")
        # Get all template files
        if not os.path.exists(self.storage_path):
            print(f"Templates directory does not exist: {self.storage_path}")
            return
        
        templates = []
        files = os.listdir(self.storage_path)
        print(f"Found {len(files)} files in template directory")
        
        for filename in files:
            if filename.endswith('.json'):
                print(f"\nProcessing template file: {filename}")
                try:
                    template_path = os.path.join(self.storage_path, filename)
                    print(f"Reading file: {template_path}")
                    
                    with open(template_path, 'r') as f:
                        file_content = f.read()
                        print(f"File content length: {len(file_content)} bytes")
                        
                        # Check if file content is valid JSON
                        try:
                            template_data = json.loads(file_content)
                            print(f"Successfully loaded JSON data with keys: {template_data.keys()}")
                            
                            # Convert string ID back to UUID
                            if 'id' in template_data and isinstance(template_data['id'], str):
                                print(f"Converting ID from string to UUID: {template_data['id']}")
                                template_data['id'] = UUID(template_data['id'])
                            
                            # Convert ISO format strings back to datetime
                            for date_field in ['created_at', 'updated_at']:
                                if date_field in template_data and template_data[date_field]:
                                    print(f"Converting {date_field} from string to datetime: {template_data[date_field]}")
                                    template_data[date_field] = datetime.fromisoformat(template_data[date_field])
                            
                            # Create the template
                            print("Creating ReceiptTemplate from data")
                            template = ReceiptTemplate(**template_data)
                            print(f"Created template object with ID: {template.id}")
                            templates.append(template)
                        except json.JSONDecodeError as json_err:
                            print(f"JSON parsing error: {json_err}")
                            print(f"Invalid JSON content: {file_content[:100]}...")
                            # Remove corrupted template file
                            os.remove(template_path)
                            print(f"Removed corrupted template file: {filename}")
                except Exception as e:
                    print(f"Error loading template {filename}: {str(e)}")
                    traceback.print_exc()
                    # Remove corrupted template file
                    try:
                        template_path = os.path.join(self.storage_path, filename)
                        print(f"Attempting to remove corrupted file: {template_path}")
                        os.remove(template_path)
                        print(f"Removed corrupted template file: {filename}")
                    except Exception as remove_error:
                        print(f"Failed to remove corrupted template file {filename}: {str(remove_error)}")
        
        print(f"\nLoaded {len(templates)} templates successfully")
        # Add to cache
        for template in templates:
            print(f"Adding template to cache: {template.id} - {template.name}")
            self.templates_cache[template.id] = template
    
    def save_template(self, template: ReceiptTemplate) -> None:
        """
        Save a template to storage.
        
        Args:
            template: The template to save
        """
        # Update cache
        self.templates_cache[template.id] = template
        
        # Save to file
        template_path = os.path.join(self.storage_path, f"{template.id}.json")
        
        try:
            # Use the template's to_dict method which properly handles serialization
            template_dict = template.to_dict()
            
            # Serialize to JSON
            json_str = json.dumps(template_dict, indent=2)
            
            # Write to file
            with open(template_path, 'w') as f:
                f.write(json_str)
                
            print(f"Successfully saved template {template.id} to {template_path}")
            
        except Exception as e:
            print(f"Error saving template: {str(e)}")
            try:
                # Fallback to a more direct approach
                manual_dict = {
                    'id': str(template.id),
                    'name': template.name,
                    'store_name_patterns': template.store_name_patterns,
                    'header_patterns': template.header_patterns,
                    'item_patterns': template.item_patterns,
                    'summary_patterns': template.summary_patterns,
                    'layout_markers': {},  # Simplified to avoid serialization issues
                    'layout_signature': template.layout_signature,
                    'version': template.version,
                    'created_at': template.created_at.isoformat() if template.created_at else None,
                    'updated_at': template.updated_at.isoformat() if template.updated_at else None,
                    'usage_count': template.usage_count,
                    'success_rate': template.success_rate,
                    'date_formats': template.date_formats,
                    'currency_symbol': template.currency_symbol,
                    'item_format': template.item_format,
                    'total_format': template.total_format,
                    'patterns': {},  # Simplified to avoid serialization issues
                    'headerRegex': template.headerRegex,
                    'keywordMatch': template.keywordMatch,
                    'examples': template.examples,
                    'metadata': {}  # Simplified to avoid serialization issues
                }
                
                # Copy safe values from patterns and metadata
                for k, v in template.patterns.items():
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        manual_dict['patterns'][k] = v
                
                for k, v in template.metadata.items():
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        manual_dict['metadata'][k] = v
                
                # Serialize to JSON
                json_str = json.dumps(manual_dict, indent=2)
                
                # Write to file
                with open(template_path, 'w') as f:
                    f.write(json_str)
                    
                print(f"Successfully saved template {template.id} using fallback method")
            except Exception as e2:
                print(f"Failed to save template using fallback method: {str(e2)}")
    
    def get_template(self, template_id: UUID) -> Optional[ReceiptTemplate]:
        """
        Get a template by ID.
        
        Args:
            template_id: The ID of the template to get
            
        Returns:
            The template if found, None otherwise
        """
        return self.templates_cache.get(template_id)
    
    def get_all_templates(self) -> List[ReceiptTemplate]:
        """
        Get all templates.
        
        Returns:
            List of all templates
        """
        return list(self.templates_cache.values())
    
    def delete_template(self, template_id: UUID) -> bool:
        """
        Delete a template.
        
        Args:
            template_id: The ID of the template to delete
            
        Returns:
            True if the template was deleted, False otherwise
        """
        # Remove from cache
        if template_id in self.templates_cache:
            del self.templates_cache[template_id]
        else:
            return False
            
        # Delete file
        template_path = os.path.join(self.storage_path, f"{template_id}.json")
        if os.path.exists(template_path):
            os.remove(template_path)
            return True
        
        return False
    
    def find_matching_template(self, text_lines: List[str], store_name: Optional[str] = None) -> Tuple[Optional[ReceiptTemplate], float]:
        """
        Find the best matching template for a receipt.
        
        Args:
            text_lines: List of text lines from the receipt
            store_name: Optional store name for better matching
            
        Returns:
            Tuple of (best matching template, confidence score) or (None, 0.0) if no match
        """
        if not self.templates_cache:
            return None, 0.0
            
        best_template = None
        best_confidence = 0.0
        
        for template in self.templates_cache.values():
            confidence = template.match_confidence(text_lines, store_name)
            if confidence > best_confidence:
                best_confidence = confidence
                best_template = template
        
        # Only return a match if confidence is above threshold (0.6)
        if best_confidence >= 0.6:
            return best_template, best_confidence
        else:
            return None, 0.0
    
    def create_or_update_template(self, store_name: str, text_lines: List[str]) -> ReceiptTemplate:
        """
        Create a new template or update an existing one.
        
        Args:
            store_name: Name of the store
            text_lines: Text lines from the receipt
            
        Returns:
            The created or updated template
        """
        # Check if we already have a template for this store
        existing_templates = [t for t in self.templates_cache.values() 
                             if t.matches_store(store_name)]
        
        if existing_templates:
            # Update the most used template
            existing_templates.sort(key=lambda t: t.usage_count, reverse=True)
            template = existing_templates[0]
            
            # Update template with new layout signature
            template.layout_signature = template.calc_layout_signature(text_lines)
            template.increment_usage()
            
            # Add the store name pattern if it's not already there
            if store_name and not any(store_name.lower() in pattern.lower() for pattern in template.store_name_patterns):
                template.store_name_patterns.append(f"^{store_name}$")
            
            self.save_template(template)
            return template
        else:
            # Create new template
            template = ReceiptTemplate(
                name=store_name,
                store_name_patterns=[f"^{store_name}$"]
            )
            
            # Calculate and set layout signature
            template.layout_signature = template.calc_layout_signature(text_lines)
            
            # Extract common patterns
            self._extract_patterns(template, text_lines)
            
            self.save_template(template)
            return template
    
    def _extract_patterns(self, template: ReceiptTemplate, text_lines: List[str]) -> None:
        """
        Extract common patterns from receipt text and add to template.
        
        Args:
            template: The template to update
            text_lines: Text lines from the receipt
        """
        # Find header patterns (typically first few lines)
        if len(text_lines) > 3:
            template.header_patterns = [line.strip() for line in text_lines[:3] if line.strip()]
            
        # Find summary patterns (typically contain keywords like total, subtotal, etc.)
        summary_keywords = ['total', 'subtotal', 'tax', 'balance', 'amount due']
        for line in text_lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in summary_keywords):
                template.summary_patterns.append(line.strip())
                
        # Find item patterns (lines with prices but not in summary)
        import re
        price_pattern = r'\$?(\d+\.\d{2})'
        for line in text_lines:
            # Skip if it's a summary line
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in summary_keywords):
                continue
                
            # Check if it has a price pattern
            if re.search(price_pattern, line):
                template.item_patterns.append(line.strip())
                
        # Find date formats
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # MM/DD/YYYY or DD/MM/YYYY
            r'\d{1,2}-\d{1,2}-\d{2,4}',  # MM-DD-YYYY or DD-MM-YYYY
            r'\d{1,2}\.\d{1,2}\.\d{2,4}',  # MM.DD.YYYY or DD.MM.YYYY
            r'\w{3,9} \d{1,2},? \d{4}'   # Month DD, YYYY
        ]
        
        found_date_formats = []
        for line in text_lines:
            for pattern in date_patterns:
                if re.search(pattern, line):
                    found_date_formats.append(pattern)
                    break
                    
        if found_date_formats:
            template.date_formats = found_date_formats
            
        # Find currency symbol
        currency_symbols = ['$', '€', '£', '¥']
        for line in text_lines:
            for symbol in currency_symbols:
                if symbol in line:
                    template.currency_symbol = symbol
                    break
            if template.currency_symbol:
                break
    
    def _create_built_in_templates(self) -> List[ReceiptTemplate]:
        """Create built-in templates for common receipt formats."""
        built_in_templates = []

        # Costco template
        built_in_templates.append(ReceiptTemplate(
            name="Costco",
            version=2,
            metadata={
                "description": "Template for parsing Costco receipts",
                "author": "System",
                "built_in": True,
                "fallback_enabled": True  # Allow fallback parsing if primary fails
            },
            headerRegex=r'(?i)(costco|wholesale|warehouse|members?hip|executive)',
            keywordMatch=["COSTCO", "WHOLESALE", "WAREHOUSE", "MEMBERSHIP", "EXECUTIVE"],
            currency="USD",
            examples=[
                "COSTCO WHOLESALE",
                "COSTCO WHOLESALE #1107",
                "COSTCO WHOLESALE CORPORATION",
                "COSTCO MEMBERSHIP"
            ],
            item_pattern=r'(?<!\*)(?<!\d)(?!\d+\s+ITEMS)(?!\d+\s+ARTICLE)(?!SUBTOTAL)(?!TAX)[A-Z0-9][A-Za-z0-9\s\-\.\,\&\'\(\)\/\*\#\+]{3,}?\s+(?:\d+\s+@\s+[\d\.,]+\s+)?(\d+\.\d{2})',
            subtotal_pattern=r'(?i)(?:SUB[\s-]*(?:TOTAL)?|SUBTOT|ARTICLES)(?:\s+\d+)?\s*\$?\s*(\d+\.\d{2})',
            total_pattern=r'(?i)(?:\*+\s+)?(?:TOTAL|BALANCE|\*\s+BALANCE|\*\s+TOTAL)(?:\s+(?:SALE|DUE))?\s*\$?\s*(\d+\.\d{2})',
            tax_pattern=r'(?i)(?:TAX|SALES\s+TAX|GST|HST|PST|TVQ)\s*\$?\s*(\d+\.\d{2})',
            payment_pattern=r'(?i)(?:MASTERCARD|VISA|AMEX|DISCOVER|CREDIT|DEBIT)\s+(?:TEND|CARD|END)?\s*\$?\s*\d+\.\d{2}',
            keywords=[
                "COSTCO", "WHOLESALE", "WAREHOUSE", "MEMBERSHIP", "EXECUTIVE",
                "SUBTOTAL", "ARTICLES", "TAX", "TOTAL", "BALANCE"
            ]
        ))

        # Target template
        built_in_templates.append(ReceiptTemplate(
            name="Target",
            version=2,
            metadata={
                "description": "Template for parsing Target receipts",
                "author": "System",
                "built_in": True,
                "fallback_enabled": True  # Allow fallback parsing if primary fails
            },
            headerRegex=r'(?i)(target|expect\s+more|pay\s+less)',
            keywordMatch=["TARGET", "EXPECT MORE PAY LESS"],
            currency="USD",
            examples=[
                "TARGET",
                "TARGET STORE",
                "TARGET #1234",
                "EXPECT MORE. PAY LESS."
            ],
            item_pattern=r'(?<!\*)(?<!\d)(?!SUBTOTAL)(?!TAX)(?!TOTAL)(?!BALANCE)[A-Z0-9][A-Za-z0-9\s\-\.\,\&\'\(\)\/\*\#\+]{3,}?\s+(?:\d+\s+@\s+[\d\.,]+\s+)?(\d+\.\d{2})',
            subtotal_pattern=r'(?i)(?:SUB[\s-]*TOTAL|SUBTOT)(?:\s+\d+)?\s*\$?\s*(\d+\.\d{2})',
            total_pattern=r'(?i)(?:TOTAL|BALANCE)(?:\s+(?:SALE|DUE))?\s*\$?\s*(\d+\.\d{2})',
            tax_pattern=r'(?i)(?:TAX|SALES\s+TAX)\s*\$?\s*(\d+\.\d{2})',
            payment_pattern=r'(?i)(?:MASTERCARD|VISA|AMEX|DISCOVER|CREDIT|DEBIT)\s+(?:CARD)?\s*\$?\s*\d+\.\d{2}',
            keywords=[
                "TARGET", "EXPECT MORE PAY LESS", "SUBTOTAL", "TAX", "TOTAL",
                "BULLSEYE", "REDCARD", "DPCI", "RECEIPT ID"
            ]
        ))

        # Add H Mart template
        built_in_templates.append(ReceiptTemplate(
            name="H Mart",
            version=2,
            metadata={
                "description": "Template for parsing H Mart receipts",
                "author": "System",
                "built_in": True,
                "fallback_enabled": True  # Allow fallback parsing if primary fails
            },
            headerRegex=r'(?i)(h\s*mart|h[\.\-]mart|hmart|korean|asian\s+grocery)',
            keywordMatch=["H MART", "HMART", "KOREAN", "ASIAN", "GROCERY"],
            currency="USD",
            examples=[
                "H MART",
                "H-MART",
                "HMART",
                "H.MART",
                "H MART ASIAN GROCERY"
            ],
            item_pattern=r'(?<!\d)(?!SUB\s*TOTAL)(?!TAX)(?!TOTAL)(?!BALANCE)[A-Za-z0-9][\w\s\-\.\,\&\'\(\)\/]{3,}?\s+(?:\d+\s+(?:EA|ea|PK|pk|PC|pc)?\s+)?(\d+\.\d{2})',
            subtotal_pattern=r'(?i)(?:SUB[\s-]*TOTAL|SUBTOT|SUB\s*AMT)(?:\s+\d+)?\s*\$?\s*(\d+\.\d{2})',
            total_pattern=r'(?i)(?:TOTAL|AMOUNT|BALANCE)(?:\s+DUE)?\s*\$?\s*(\d+\.\d{2})',
            tax_pattern=r'(?i)(?:TAX|TX|SALES\s+TAX)\s*\$?\s*(\d+\.\d{2})',
            payment_pattern=r'(?i)(?:MASTERCARD|VISA|AMEX|DISCOVER|CREDIT|DEBIT)\s*(?:CARD)?\s*\$?\s*\d+\.\d{2}',
            keywords=[
                "H MART", "HMART", "ASIAN", "KOREAN", "GROCERY", "THANK YOU",
                "SUBTOTAL", "TAX", "TOTAL", "PURCHASE", "AMOUNT"
            ]
        ))

        # Walmart template
        built_in_templates.append(ReceiptTemplate(
            name="Walmart",
            version=2,
            metadata={
                "description": "Template for parsing Walmart receipts",
                "author": "System",
                "built_in": True,
                "fallback_enabled": True  # Allow fallback parsing if primary fails
            },
            headerRegex=r'(?i)(walmart|wal[\s\-]mart|supercenter|save\s+money|live\s+better)',
            keywordMatch=["WALMART", "WAL-MART", "SUPERCENTER", "SAVE MONEY", "LIVE BETTER"],
            currency="USD",
            examples=[
                "WALMART",
                "WAL-MART",
                "WALMART SUPERCENTER",
                "WAL-MART #123",
                "SAVE MONEY. LIVE BETTER."
            ],
            item_pattern=r'(?<!\*)(?<!\d)(?!SUBTOTAL)(?!TAX)(?!TOTAL)[A-Z0-9][A-Za-z0-9\s\-\.\,\&\'\(\)\/\*\#\+]{3,}?\s+(?:\d+\s+(?:FOR|@|X)\s+[\d\.,]+\s+)?\s*(\d+\.\d{2})',
            subtotal_pattern=r'(?i)(?:SUB[\s-]*TOTAL|SUBTOT)(?:\s+\d+)?\s*\$?\s*(\d+\.\d{2})',
            total_pattern=r'(?i)(?:TOTAL|BALANCE)(?:\s+(?:SALE|DUE))?\s*\$?\s*(\d+\.\d{2})',
            tax_pattern=r'(?i)(?:TAX|SALES\s+TAX|T(?=\s+\d+\.\d{2}))\s*\$?\s*(\d+\.\d{2})',
            payment_pattern=r'(?i)(?:MASTERCARD|VISA|AMEX|DISCOVER|CREDIT|DEBIT|CHANGE|CASH)\s+(?:TEND|CARD|DUE)?\s*\$?\s*\d+\.\d{2}',
            keywords=[
                "WALMART", "WAL-MART", "SUPERCENTER", "SAVE MONEY", "LIVE BETTER",
                "SUBTOTAL", "TAX", "TOTAL", "RECEIPT", "THANK YOU"
            ]
        ))

        # Trader Joe's template
        built_in_templates.append(ReceiptTemplate(
            name="Trader Joe's",
            version=1,
            metadata={
                "description": "Template for parsing Trader Joe's receipts",
                "author": "System",
                "built_in": True,
                "fallback_enabled": True  # Allow fallback parsing if primary fails
            },
            headerRegex=r'(?i)(trader\s*joe\'?s?)',
            keywordMatch=["TRADER JOE", "TRADER JOE'S"],
            currency="USD",
            examples=[
                "TRADER JOE'S",
                "TRADER JOE",
                "TRADER JOES"
            ],
            item_pattern=r'(?<!\d)(?!SUBTOTAL)(?!TAX)(?!TOTAL)(?!BALANCE)[A-Za-z0-9][A-Za-z0-9\s\-\.\,\&\'\(\)\/\*\#\+]{3,}?\s+(\d+\.\d{2})',
            subtotal_pattern=r'(?i)(?:SUBTOTAL|SUB\s*TOTAL)\s*\$?\s*(\d+\.\d{2})',
            total_pattern=r'(?i)(?:TOTAL|BALANCE)(?:\s+(?:SALE|DUE))?\s*\$?\s*(\d+\.\d{2})',
            tax_pattern=r'(?i)(?:TAX|SALES\s+TAX)\s*\$?\s*(\d+\.\d{2})',
            payment_pattern=r'(?i)(?:CREDIT|DEBIT|CASH|CASH BACK|CHANGE)\s*\$?\s*\d+\.\d{2}',
            keywords=[
                "TRADER JOE'S", "TRADER JOE", "THANK YOU", 
                "SUBTOTAL", "TAX", "TOTAL", "BALANCE"
            ]
        ))

        return built_in_templates 