"""Utility for checking and configuring OCR engines."""

import os
import logging
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from ocr.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR

logger = logging.getLogger(__name__)

class OCRSetup:
    """Helper class for OCR engine setup and validation."""
    
    @staticmethod
    def check_tesseract_installation() -> Dict[str, Any]:
        """Check if Tesseract is properly installed."""
        logger.info("Checking Tesseract installation...")
        try:
            import pytesseract
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract found: version {version}")
            
            # Test Tesseract functionality
            test_result = OCRSetup._test_tesseract()
            if test_result['error']:
                logger.warning(f"Tesseract test failed: {test_result['error']}")
                return {
                    'installed': True,
                    'functional': False,
                    'version': version,
                    'error': test_result['error']
                }
            
            logger.info("Tesseract test successful")
            return {
                'installed': True,
                'functional': True,
                'version': version,
                'error': None
            }
        except Exception as e:
            logger.warning(f"Tesseract check failed: {str(e)}")
            return {
                'installed': False,
                'functional': False,
                'version': None,
                'error': str(e)
            }
    
    @staticmethod
    def _test_tesseract() -> Dict[str, Any]:
        """Test Tesseract functionality with a simple image."""
        try:
            # Create a test OCR engine
            ocr = TesseractOCR()
            
            # Test with a simple image or text extraction
            test_result = ocr.validate()
            if not test_result:
                return {'error': 'Tesseract validation failed'}
            
            return {'error': None}
            
        except Exception as e:
            return {'error': f"Tesseract test failed: {str(e)}"}
    
    @staticmethod
    def check_google_vision_setup() -> Dict[str, Any]:
        """Check Google Cloud Vision configuration."""
        logger.info("Checking Google Cloud Vision setup...")
        try:
            config = GoogleVisionConfig()
            if not config.is_configured:
                logger.warning("Google Cloud Vision credentials not configured")
                return {
                    'configured': False,
                    'functional': False,
                    'error': 'Google Cloud Vision credentials not configured'
                }
            
            logger.info(f"Found credentials at: {config.credentials_path}")
            
            # Validate credentials
            logger.info("Validating Google Cloud credentials...")
            config.validate()
            
            # Test connection and functionality
            logger.info("Testing Google Cloud Vision API access...")
            ocr = GoogleVisionOCR(credentials_path=config.credentials_path)
            if not ocr.validate_api_access():
                logger.error("Google Cloud Vision API test failed")
                return {
                    'configured': True,
                    'functional': False,
                    'credentials_path': config.credentials_path,
                    'error': 'API access test failed'
                }
            
            logger.info("Google Cloud Vision setup validated successfully")
            return {
                'configured': True,
                'functional': True,
                'credentials_path': config.credentials_path,
                'error': None
            }
        except Exception as e:
            logger.error(f"Google Cloud Vision setup failed: {str(e)}")
            return {
                'configured': False,
                'functional': False,
                'credentials_path': config.credentials_path if hasattr(config, 'credentials_path') else None,
                'error': str(e)
            }
    
    @staticmethod
    def setup_ocr(preferred_engine: Optional[str] = None) -> Dict[str, Any]:
        """
        Set up OCR engine based on configuration and preference.
        
        Args:
            preferred_engine: Optional preferred OCR engine ('google_vision' or 'tesseract')
            
        Returns:
            Dictionary with setup results and selected engine
        """
        results = {
            'google_vision': OCRSetup.check_google_vision_setup(),
            'tesseract': OCRSetup.check_tesseract_installation(),
            'selected_engine': None,
            'error': None,
            'fallback_available': False
        }
        
        # Log setup results
        logger.info("OCR Setup Results:")
        logger.info(f"Google Vision: configured={results['google_vision']['configured']}, functional={results['google_vision'].get('functional', False)}")
        logger.info(f"Tesseract: installed={results['tesseract']['installed']}, functional={results['tesseract'].get('functional', False)}")
        
        # Try to use preferred engine if specified
        if preferred_engine:
            if preferred_engine == 'google_vision' and results['google_vision']['configured'] and results['google_vision'].get('functional', False):
                results['selected_engine'] = 'google_vision'
                results['fallback_available'] = results['tesseract']['installed'] and results['tesseract'].get('functional', False)
            elif preferred_engine == 'tesseract' and results['tesseract']['installed'] and results['tesseract'].get('functional', False):
                results['selected_engine'] = 'tesseract'
                results['fallback_available'] = results['google_vision']['configured'] and results['google_vision'].get('functional', False)
            else:
                results['error'] = f"Preferred engine '{preferred_engine}' not available or not functional"
        
        # Auto-select best available engine
        if not results['selected_engine']:
            if results['google_vision']['configured'] and results['google_vision'].get('functional', False):
                results['selected_engine'] = 'google_vision'
                results['fallback_available'] = results['tesseract']['installed'] and results['tesseract'].get('functional', False)
            elif results['tesseract']['installed'] and results['tesseract'].get('functional', False):
                results['selected_engine'] = 'tesseract'
                results['fallback_available'] = False
            else:
                results['error'] = "No OCR engine available"
                logger.error("No functional OCR engine available")
        
        logger.info(f"Selected engine: {results['selected_engine']}")
        logger.info(f"Fallback available: {results['fallback_available']}")
        
        return results
    
    @staticmethod
    def get_ocr_engine(setup_results: Dict[str, Any]) -> Optional[Any]:
        """
        Get configured OCR engine based on setup results.
        
        Args:
            setup_results: Results from setup_ocr()
            
        Returns:
            Configured OCR engine instance or None
        """
        engine_type = setup_results.get('selected_engine')
        fallback_available = setup_results.get('fallback_available', False)
        
        try:
            if engine_type == 'google_vision':
                config = GoogleVisionConfig()
                # Create Tesseract fallback if available
                fallback = TesseractOCR() if fallback_available else None
                return GoogleVisionOCR(credentials_path=config.credentials_path, fallback_engine=fallback)
            elif engine_type == 'tesseract':
                return TesseractOCR()
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating OCR engine: {str(e)}")
            return None
    
    @staticmethod
    def install_tesseract() -> bool:
        """Attempt to install Tesseract if missing."""
        try:
            # Check if already installed
            if OCRSetup.check_tesseract_installation()['installed']:
                return True
            
            # Determine OS and package manager
            if os.name == 'posix':  # Unix-like
                if os.path.exists('/usr/bin/apt-get'):  # Debian/Ubuntu
                    cmd = ['sudo', 'apt-get', 'install', '-y', 'tesseract-ocr']
                elif os.path.exists('/usr/bin/brew'):  # macOS with Homebrew
                    cmd = ['brew', 'install', 'tesseract']
                else:
                    return False
                    
                # Run installation command
                subprocess.run(cmd, check=True)
                
                # Verify installation
                result = OCRSetup.check_tesseract_installation()
                return result['installed'] and result.get('functional', False)
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to install Tesseract: {str(e)}")
            return False
    
    @staticmethod
    def configure_google_vision(credentials_path: str) -> bool:
        """
        Configure Google Cloud Vision with provided credentials.
        
        Args:
            credentials_path: Path to Google Cloud credentials JSON file
            
        Returns:
            bool: Whether configuration was successful
        """
        try:
            # Validate credentials file
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
            
            # Set environment variable
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            
            # Test configuration
            config = GoogleVisionConfig()
            config.validate()
            
            # Test API access
            ocr = GoogleVisionOCR(credentials_path=credentials_path)
            if not ocr.validate_api_access():
                raise Exception("API access validation failed")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure Google Vision: {str(e)}")
            return False 