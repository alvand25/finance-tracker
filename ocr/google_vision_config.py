"""Google Cloud Vision configuration module."""

import os
import logging

logger = logging.getLogger(__name__)

class GoogleVisionConfig:
    """Configuration for Google Cloud Vision API."""
    
    def __init__(self):
        """Initialize Google Cloud Vision configuration."""
        self.credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.is_configured = bool(self.credentials_path and os.path.exists(self.credentials_path))
        
        if not self.is_configured:
            logger.warning("Google Cloud Vision credentials not found or invalid.") 