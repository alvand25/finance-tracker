"""Configuration settings for Google Cloud Vision OCR."""
import os
from typing import Optional

class GoogleVisionConfig:
    """Configuration class for Google Cloud Vision settings."""
    
    def __init__(self):
        """Initialize Google Vision configuration."""
        self.credentials_path: Optional[str] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.api_endpoint: Optional[str] = os.getenv('GOOGLE_VISION_API_ENDPOINT')
        self.timeout: int = int(os.getenv('GOOGLE_VISION_TIMEOUT', '30'))
        self.max_retries: int = int(os.getenv('GOOGLE_VISION_MAX_RETRIES', '3'))
        self.batch_size: int = int(os.getenv('GOOGLE_VISION_BATCH_SIZE', '10'))
        
    @property
    def is_configured(self) -> bool:
        """Check if Google Vision is properly configured."""
        return bool(self.credentials_path)
    
    def validate(self) -> None:
        """Validate the configuration settings."""
        if not self.credentials_path:
            raise ValueError("Google Cloud Vision credentials path not set. "
                           "Set GOOGLE_APPLICATION_CREDENTIALS environment variable.")
        
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Google Cloud Vision credentials file not found at: "
                                  f"{self.credentials_path}")
        
        if self.timeout < 1:
            raise ValueError("Timeout must be at least 1 second")
            
        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
            
        if self.batch_size < 1:
            raise ValueError("Batch size must be at least 1")
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            'credentials_path': self.credentials_path,
            'api_endpoint': self.api_endpoint,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'batch_size': self.batch_size
        }
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'GoogleVisionConfig':
        """Create configuration from dictionary."""
        instance = cls()
        
        # Set environment variables from dictionary
        if config_dict.get('credentials_path'):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config_dict['credentials_path']
        
        if config_dict.get('api_endpoint'):
            os.environ['GOOGLE_VISION_API_ENDPOINT'] = config_dict['api_endpoint']
            
        if config_dict.get('timeout'):
            os.environ['GOOGLE_VISION_TIMEOUT'] = str(config_dict['timeout'])
            
        if config_dict.get('max_retries'):
            os.environ['GOOGLE_VISION_MAX_RETRIES'] = str(config_dict['max_retries'])
            
        if config_dict.get('batch_size'):
            os.environ['GOOGLE_VISION_BATCH_SIZE'] = str(config_dict['batch_size'])
        
        # Reinitialize with new environment variables
        return cls() 