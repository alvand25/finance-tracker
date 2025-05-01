from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
import traceback
from pydantic import BaseModel, Field

class ReceiptTemplate(BaseModel):
    """
    Model representing a receipt template for optimized recognition and parsing.
    Templates are used to improve accuracy for frequently encountered receipt formats.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    store_name_patterns: List[str] = Field(default_factory=list)  # Regex patterns to match store names
    header_patterns: List[str] = []  # Patterns to identify header section
    item_patterns: List[str] = []  # Patterns to match item lines
    summary_patterns: List[str] = []  # Patterns to match summary section
    
    # Layout information
    layout_markers: Dict[str, Any] = Field(default_factory=dict)
    layout_signature: Optional[str] = None  # Hash of layout characteristics
    
    # Template metadata
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    usage_count: int = 0
    success_rate: float = 0.0
    
    # Custom parsing rules
    date_formats: List[str] = []  # Date formats used by this store
    currency_symbol: Optional[str] = None
    item_format: Optional[str] = None  # Format string for item parsing
    total_format: Optional[str] = None  # Format string for total parsing
    
    # New fields for enhanced templates
    patterns: Dict[str, str] = Field(default_factory=dict)  # Specific regex patterns for this template
    headerRegex: Optional[str] = None  # Regex to match header section
    keywordMatch: List[str] = Field(default_factory=list)  # Keywords that identify this template
    examples: List[str] = Field(default_factory=list)  # Example text snippets for this template
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Additional metadata
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Override dict() method to handle UUID serialization.
        This ensures UUID objects are converted to strings properly.
        """
        try:
            # First convert to a basic dict
            data = super().dict(*args, **kwargs)
            
            # Convert UUID to string explicitly
            if 'id' in data and isinstance(data['id'], UUID):
                data['id'] = str(data['id'])
            
            # Convert datetime objects
            for key in ['created_at', 'updated_at']:
                if key in data and isinstance(data[key], datetime):
                    data[key] = data[key].isoformat()
            
            # Handle nested dictionaries
            for key, value in data.items():
                if isinstance(value, dict):
                    # Process nested dictionaries for UUID and datetime objects
                    for sub_key, sub_value in list(value.items()):
                        if isinstance(sub_value, UUID):
                            data[key][sub_key] = str(sub_value)
                        elif isinstance(sub_value, datetime):
                            data[key][sub_key] = sub_value.isoformat()
                        elif isinstance(sub_value, (dict, list)):
                            # Convert nested dictionaries and lists to JSON-safe values
                            data[key][sub_key] = self._make_json_safe(sub_value)
                
                # Handle lists (which might contain dictionaries with problematic values)
                elif isinstance(value, list):
                    data[key] = self._make_json_safe(value)
            
            return data
        except Exception as e:
            # Return a minimal dict as fallback
            return {'id': str(self.id), 'name': self.name}
    
    def _make_json_safe(self, value: Any) -> Any:
        """Recursively convert a value to be JSON-safe."""
        if isinstance(value, UUID):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._make_json_safe(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._make_json_safe(item) for item in value]
        else:
            return value
    
    def increment_usage(self, success: bool = True) -> None:
        """
        Increment the usage count and update success rate.
        
        Args:
            success: Whether the template was used successfully
        """
        current_success_total = self.success_rate * self.usage_count
        self.usage_count += 1
        
        if success:
            current_success_total += 1
            
        self.success_rate = current_success_total / self.usage_count
        self.updated_at = datetime.now()
    
    def update(self, updated_data: Dict[str, Any]) -> None:
        """
        Update template with new data.
        
        Args:
            updated_data: Dictionary with fields to update
        """
        for key, value in updated_data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        self.version += 1
        self.updated_at = datetime.now()
    
    def matches_store(self, store_name: str) -> bool:
        """
        Check if a store name matches this template.
        
        Args:
            store_name: The store name to check
            
        Returns:
            True if the store name matches any pattern
        """
        import re
        
        # First check store name patterns
        for pattern in self.store_name_patterns:
            if re.search(pattern, store_name, re.IGNORECASE):
                return True
        
        # Also check if store name contains any of the keywords
        store_name_lower = store_name.lower()
        for keyword in self.keywordMatch:
            if keyword.lower() in store_name_lower:
                return True
        
        # Check header regex if defined
        if self.headerRegex and re.search(self.headerRegex, store_name, re.IGNORECASE):
            return True
        
        return False
    
    def calc_layout_signature(self, text_lines: List[str]) -> str:
        """
        Calculate a signature for receipt layout based on text lines.
        
        Args:
            text_lines: List of text lines from the receipt
            
        Returns:
            String signature representing layout characteristics
        """
        import hashlib
        
        # Create signature based on:
        # 1. Line length distribution
        # 2. Position of key markers (total, subtotal, etc.)
        # 3. Presence of specific symbols
        
        line_lengths = [len(line) for line in text_lines]
        avg_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0
        std_dev = (sum((l - avg_length) ** 2 for l in line_lengths) / len(line_lengths)) ** 0.5 if line_lengths else 0
        
        # Find positions of key words
        key_word_positions = {}
        for i, line in enumerate(text_lines):
            lower_line = line.lower()
            for word in ['total', 'subtotal', 'tax', 'date', 'payment']:
                if word in lower_line:
                    key_word_positions[word] = i / len(text_lines) if text_lines else 0
        
        # Create a signature dictionary
        signature_data = {
            'line_count': len(text_lines),
            'avg_length': round(avg_length, 2),
            'std_dev': round(std_dev, 2),
            'key_positions': key_word_positions
        }
        
        # Convert to string and hash
        signature_str = str(signature_data)
        return hashlib.md5(signature_str.encode()).hexdigest()
    
    def match_confidence(self, text_lines: List[str], store_name: Optional[str] = None) -> float:
        """
        Calculate the confidence that this template matches the given receipt.
        
        Args:
            text_lines: List of text lines from the receipt
            store_name: Optional store name for additional matching
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Start with base confidence
        confidence = 0.0
        
        # Check store name match (50% of confidence)
        if store_name and self.matches_store(store_name):
            confidence += 0.5
        
        # Calculate and compare layout signature (50% of confidence)
        signature = self.calc_layout_signature(text_lines)
        if self.layout_signature:
            # Compare signatures for similarity
            import difflib
            similarity = difflib.SequenceMatcher(None, signature, self.layout_signature).ratio()
            confidence += 0.5 * similarity
        
        return confidence
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary for JSON serialization."""
        try:
            # Create a basic dictionary with all fields converted to JSON-safe values
            result = {
                'id': str(self.id),
                'name': self.name,
                'store_name_patterns': self.store_name_patterns,
                'header_patterns': self.header_patterns,
                'item_patterns': self.item_patterns,
                'summary_patterns': self.summary_patterns,
                'layout_markers': self._make_json_safe(self.layout_markers),
                'layout_signature': self.layout_signature,
                'version': self.version,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'usage_count': self.usage_count,
                'success_rate': self.success_rate,
                'date_formats': self.date_formats,
                'currency_symbol': self.currency_symbol,
                'item_format': self.item_format,
                'total_format': self.total_format,
                'patterns': self._make_json_safe(self.patterns),
                'headerRegex': self.headerRegex,
                'keywordMatch': self.keywordMatch,
                'examples': self.examples,
                'metadata': self._make_json_safe(self.metadata)
            }
            
            return result
        except Exception as e:
            # Return a minimal dict as fallback
            return {'id': str(self.id), 'name': self.name} 