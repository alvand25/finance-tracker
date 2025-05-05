"""Google Cloud Vision OCR configuration."""

import os
import json
import logging
from typing import Optional, Dict, Any
from google.cloud import vision
from google.oauth2 import service_account
from google.api_core import retry

logger = logging.getLogger(__name__)

class GoogleVisionConfigError(Exception):
    """Base exception for Google Vision configuration errors."""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.details = details or {}

class GoogleVisionConfig:
    """Configuration for Google Cloud Vision OCR."""
    
    DEFAULT_SCOPES = ['https://www.googleapis.com/auth/cloud-vision']
    REQUIRED_CREDS_FIELDS = [
        'type', 'project_id', 'private_key_id', 
        'private_key', 'client_email'
    ]
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            credentials_path: Optional path to credentials file.
                            If not provided, will use GOOGLE_APPLICATION_CREDENTIALS env var.
        """
        self.credentials_path = credentials_path or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self._credentials = None
        self._client = None
        self._project_id = None
        
        # Initialize logging
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    @property
    def is_configured(self) -> bool:
        """Check if Google Vision is configured."""
        return bool(self.credentials_path and os.path.exists(self.credentials_path))
    
    @property
    def project_id(self) -> Optional[str]:
        """Get the configured project ID."""
        if not self._project_id and self.is_configured:
            try:
                with open(self.credentials_path) as f:
                    self._project_id = json.load(f).get('project_id')
            except Exception:
                pass
        return self._project_id
    
    def validate(self) -> None:
        """
        Validate Google Vision configuration.
        
        Raises:
            GoogleVisionConfigError: If configuration is invalid
        """
        if not self.credentials_path:
            raise GoogleVisionConfigError(
                "Google Cloud Vision credentials path not set",
                {'error_type': 'missing_credentials_path'}
            )
            
        if not os.path.exists(self.credentials_path):
            raise GoogleVisionConfigError(
                f"Credentials file not found: {self.credentials_path}",
                {'error_type': 'credentials_not_found'}
            )
            
        try:
            with open(self.credentials_path) as f:
                creds_data = json.load(f)
                
            # Validate required fields
            missing = [f for f in self.REQUIRED_CREDS_FIELDS if f not in creds_data]
            if missing:
                raise GoogleVisionConfigError(
                    f"Missing required fields in credentials",
                    {
                        'error_type': 'missing_fields',
                        'missing_fields': missing
                    }
                )
                
            # Store project ID
            self._project_id = creds_data['project_id']
            
            # Validate by creating credentials object
            self._credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.DEFAULT_SCOPES
            )
            
            logger.info(f"Successfully validated credentials for project {self._project_id}")
            
        except json.JSONDecodeError:
            raise GoogleVisionConfigError(
                "Invalid JSON in credentials file",
                {'error_type': 'invalid_json'}
            )
        except Exception as e:
            raise GoogleVisionConfigError(
                f"Failed to validate credentials: {str(e)}",
                {
                    'error_type': 'validation_error',
                    'original_error': str(e)
                }
            )
    
    @retry.Retry(predicate=retry.if_exception_type(Exception))
    def _create_client(self) -> vision.ImageAnnotatorClient:
        """Create Vision client with retry logic."""
        return vision.ImageAnnotatorClient(credentials=self._credentials)
    
    @property
    def client(self) -> vision.ImageAnnotatorClient:
        """
        Get configured Vision client.
        
        Returns:
            vision.ImageAnnotatorClient: Configured client
            
        Raises:
            GoogleVisionConfigError: If client creation fails
        """
        if not self._client:
            if not self._credentials:
                self.validate()
            try:
                self._client = self._create_client()
                logger.info("Successfully created Vision client")
            except Exception as e:
                raise GoogleVisionConfigError(
                    f"Failed to create Vision client: {str(e)}",
                    {
                        'error_type': 'client_creation_error',
                        'original_error': str(e)
                    }
                )
        return self._client
    
    def get_status(self) -> Dict[str, Any]:
        """Get current configuration status."""
        return {
            'is_configured': self.is_configured,
            'project_id': self.project_id,
            'has_credentials': bool(self._credentials),
            'has_client': bool(self._client),
            'credentials_path': self.credentials_path
        } 