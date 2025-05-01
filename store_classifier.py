import os
import re
import json
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class StoreClassifier:
    """
    Classifier for identifying store names from OCR text.
    
    This class uses multiple techniques to identify the vendor from receipt text:
    1. Pattern matching for known store formats
    2. Keyword matching against a store alias database
    3. Position-based heuristics (store names are typically at the top)
    """
    
    def __init__(self, known_stores_path: str = "data/known_stores.json"):
        """
        Initialize the store classifier.
        
        Args:
            known_stores_path: Path to the JSON file containing store aliases
        """
        self.known_stores_path = known_stores_path
        self.store_aliases = {}
        self._load_store_aliases()
        
    def _load_store_aliases(self) -> None:
        """Load store aliases from JSON file."""
        try:
            if os.path.exists(self.known_stores_path):
                with open(self.known_stores_path, 'r') as f:
                    self.store_aliases = json.load(f)
                    logger.debug(f"Loaded {len(self.store_aliases)} store aliases from {self.known_stores_path}")
            else:
                logger.warning(f"Store aliases file not found: {self.known_stores_path}")
                # Create default aliases
                self.store_aliases = {
                    "costco": ["COSTCO", "COSTCO WHOLESALE", "WHOLESALE"],
                    "trader_joes": ["TRADER JOE'S", "TRADER JOES", "TJ"],
                    "h_mart": ["H MART", "H-MART"],
                    "key_food": ["KEY FOOD", "KEYFOOD"],
                    "walmart": ["WALMART", "WAL-MART", "WAL MART"],
                    "target": ["TARGET", "SUPER TARGET"],
                    "kroger": ["KROGER", "KROGER'S"],
                    "safeway": ["SAFEWAY"],
                    "publix": ["PUBLIX"],
                    "whole_foods": ["WHOLE FOODS", "WHOLE FOODS MARKET"],
                    "aldi": ["ALDI"]
                }
                
                # Ensure the directory exists
                os.makedirs(os.path.dirname(self.known_stores_path), exist_ok=True)
                
                # Save default aliases
                with open(self.known_stores_path, 'w') as f:
                    json.dump(self.store_aliases, f, indent=2)
                    logger.info(f"Created default store aliases at {self.known_stores_path}")
        except Exception as e:
            logger.error(f"Error loading store aliases: {str(e)}")
            # Fallback to empty aliases
            self.store_aliases = {}
    
    def classify(self, ocr_text: str) -> Tuple[str, float]:
        """
        Classify the store name from OCR text.
        
        Args:
            ocr_text: The OCR text from the receipt
            
        Returns:
            Tuple of (store_name, confidence_score)
        """
        # Log input OCR text snippet
        if ocr_text:
            ocr_preview = "\n".join(ocr_text.strip().split('\n')[:10])
            logger.debug(f"[Classifier] OCR Input Preview:\n{ocr_preview}")
        else:
            logger.debug("[Classifier] OCR Input is empty")
            
        if not ocr_text:
            logger.debug("[Classifier] Empty OCR text, returning 'unknown' with 0.0 confidence")
            return "unknown", 0.0
            
        # Split text into lines for analysis
        lines = ocr_text.strip().split('\n')
        if not lines:
            logger.debug("[Classifier] No lines in OCR text, returning 'unknown' with 0.0 confidence")
            return "unknown", 0.0
            
        # Clean lines (remove empty lines and lines with just special characters)
        clean_lines = [line.strip() for line in lines if line.strip()]
        clean_lines = [line for line in clean_lines if re.search(r'[a-zA-Z]', line)]
        
        if not clean_lines:
            logger.debug("[Classifier] No valid text lines after cleaning, returning 'unknown' with 0.0 confidence")
            return "unknown", 0.0
            
        # First pass - check for exact matches in aliases
        store_name, confidence = self._check_aliases(ocr_text)
        if store_name != "unknown" and confidence > 0.8:
            logger.debug(f"[Classifier] Found high-confidence match in aliases: {store_name} ({confidence:.2f})")
            return store_name, confidence
            
        # Second pass - check for special patterns
        store_name, confidence = self._check_special_patterns(ocr_text, clean_lines)
        if store_name != "unknown" and confidence > 0.7:
            logger.debug(f"[Classifier] Found high-confidence match in special patterns: {store_name} ({confidence:.2f})")
            return store_name, confidence
            
        # Third pass - check header position
        store_name, confidence = self._check_header_position(clean_lines)
        if store_name != "unknown" and confidence > 0.6:
            logger.debug(f"[Classifier] Found high-confidence match in header position: {store_name} ({confidence:.2f})")
            return store_name, confidence
            
        # If we detected something with low confidence in an earlier pass, return it
        if store_name != "unknown":
            logger.debug(f"[Classifier] Returning low-confidence match: {store_name} ({confidence:.2f})")
            return store_name, confidence
            
        # No confident match found
        logger.debug("[Classifier] No store match found, returning 'unknown' with 0.0 confidence")
        logger.debug(f"[Classifier] First few lines of OCR text: {clean_lines[:3]}")
        return "unknown", 0.0
        
    def _check_aliases(self, ocr_text: str) -> Tuple[str, float]:
        """Check OCR text against known store aliases."""
        
        # Convert to lowercase for case-insensitive matching
        ocr_lower = ocr_text.lower()
        
        # Direct exact matches (highest confidence)
        for store_key, aliases in self.store_aliases.items():
            for alias in aliases:
                pattern = r'\b' + re.escape(alias.lower()) + r'\b'
                if re.search(pattern, ocr_lower):
                    logger.debug(f"[Classifier] Found exact match for store: {store_key} (alias: {alias})")
                    return store_key, 0.95
        
        # Log all the keywords being checked for debugging
        logger.debug(f"[Classifier] Checking for matches among these store aliases: {self.store_aliases}")
        
        # Partial matches (medium confidence)
        best_match = None
        best_confidence = 0.0
        
        for store_key, aliases in self.store_aliases.items():
            for alias in aliases:
                alias_lower = alias.lower()
                # Check if alias appears anywhere in the text
                if alias_lower in ocr_lower:
                    # Longer aliases are more specific, so give them higher confidence
                    confidence = 0.7 + min(0.2, len(alias_lower) / 50)
                    logger.debug(f"[Classifier] Partial match found: '{alias}' for store '{store_key}' with confidence {confidence:.2f}")
                    if confidence > best_confidence:
                        best_match = store_key
                        best_confidence = confidence
        
        if best_match:
            logger.debug(f"[Classifier] Best partial match for store: {best_match} (confidence: {best_confidence:.2f})")
            return best_match, best_confidence
            
        logger.debug("[Classifier] No matches found in store aliases")
        return "unknown", 0.0
    
    def _check_special_patterns(self, ocr_text: str, lines: List[str]) -> Tuple[str, float]:
        """Check for special patterns indicative of specific stores."""
        
        # Join all text for pattern matching
        all_text = ' '.join(lines).lower()
        
        # Costco - Check for pattern with === WHOLESALE
        if re.search(r'={2,}wholesale|wholesale={2,}', all_text.replace(' ', '')) or ("===" in all_text and "wholesale" in all_text):
            return "costco", 0.9
            
        # Costco - Check for membership numbers
        if re.search(r'(?:member|membership)\s*(?:number|#|no)?\s*\d{6,}', all_text):
            return "costco", 0.85
            
        # Trader Joe's - Check for store numbers
        if re.search(r'(?:store|tr)\s*#\s*\d{3}', all_text) and ("trader" in all_text or "joe" in all_text):
            return "trader_joes", 0.9
            
        # H Mart - Check for Korean characters
        if re.search(r'[\uac00-\ud7a3]', ocr_text):  # Korean character range
            if "mart" in all_text or "h-mart" in all_text or "h mart" in all_text:
                return "h_mart", 0.9
                
        # Key Food - Check for Queens locations
        if (re.search(r'(queens|queens blvd|sunnyside|queens ny|long island city|astoria|flushing)', all_text) and 
            ("key food" in all_text or "keyfood" in all_text)):
            return "key_food", 0.9
            
        # Key Food - Check for specific address
        if "46-02 queens" in all_text or ("queens blvd" in all_text and "sunnyside" in all_text):
            return "key_food", 0.85
            
        # Walmart receipt patterns
        if (re.search(r'save money\.? live better', all_text) or
            (re.search(r'walmart', all_text) and re.search(r'supercenter|neighborhood market', all_text))):
            return "walmart", 0.9
            
        # Target receipt patterns
        if re.search(r'expect more\.? pay less', all_text) or "target.com" in all_text:
            return "target", 0.9
            
        return "unknown", 0.0
    
    def _check_header_position(self, lines: List[str]) -> Tuple[str, float]:
        """Check the header position for store names."""
        
        # Store name is typically in the first few lines
        header_candidates = lines[:5] if len(lines) > 5 else lines
        
        # Common receipt headers that indicate a store name
        header_patterns = [
            r'(?:welcome to|store:?)\s*(.*)',
            r'^(.*?)\s*(?:store|receipt|invoice)',
            r'^(.*?)\s*(?:tel|telephone|phone|fax)',
            r'^(.*?)\s*(?:address|location)'
        ]
        
        for line in header_candidates:
            line_lower = line.lower()
            
            # Check direct matches first
            for store_key, aliases in self.store_aliases.items():
                for alias in aliases:
                    if alias.lower() in line_lower:
                        # Confidence is higher for matches in the first lines
                        position_factor = 1.0 - (header_candidates.index(line) * 0.1)
                        confidence = 0.75 * position_factor
                        return store_key, confidence
            
            # Check header patterns
            for pattern in header_patterns:
                match = re.search(pattern, line_lower)
                if match and match.group(1).strip():
                    # Extract the potential store name
                    store_candidate = match.group(1).strip()
                    
                    # Check if this matches any known store
                    for store_key, aliases in self.store_aliases.items():
                        for alias in aliases:
                            if alias.lower() in store_candidate:
                                position_factor = 1.0 - (header_candidates.index(line) * 0.1)
                                confidence = 0.7 * position_factor
                                return store_key, confidence
                    
                    # No match in aliases, but still return what we found with lower confidence
                    position_factor = 1.0 - (header_candidates.index(line) * 0.1)
                    confidence = 0.5 * position_factor
                    
                    # Clean the store name (no need for lowercase here since we're returning what we detected)
                    store_name = ' '.join(store_candidate.split())
                    if len(store_name) > 30:
                        store_name = store_name[:30]
                        
                    # If it looks like a valid store name
                    if len(store_name) >= 3:
                        return store_name, confidence
        
        # Fallback to first line if it looks like a name
        if header_candidates and len(header_candidates[0]) >= 3 and len(header_candidates[0]) <= 30:
            store_name = header_candidates[0].strip()
            return store_name, 0.4
            
        return "unknown", 0.0
    
    def add_store_alias(self, store_key: str, alias: str) -> bool:
        """
        Add a new alias for a store.
        
        Args:
            store_key: The store key to add an alias for
            alias: The new alias to add
            
        Returns:
            True if successful, False otherwise
        """
        if store_key not in self.store_aliases:
            self.store_aliases[store_key] = []
            
        if alias not in self.store_aliases[store_key]:
            self.store_aliases[store_key].append(alias)
            
            # Save the updated aliases
            try:
                with open(self.known_stores_path, 'w') as f:
                    json.dump(self.store_aliases, f, indent=2)
                logger.info(f"Added alias: {alias} -> {store_key}")
                return True
            except Exception as e:
                logger.error(f"Error saving store aliases: {str(e)}")
                return False
                
        return True  # Already exists 