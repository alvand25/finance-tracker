#!/usr/bin/env python3
"""Setup script for Google Cloud Vision credentials."""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_credentials(creds_path: str) -> Optional[Dict[str, Any]]:
    """Validate Google Cloud Vision credentials file."""
    try:
        with open(creds_path, 'r') as f:
            creds = json.load(f)
            
        required_fields = [
            'type',
            'project_id',
            'private_key_id',
            'private_key',
            'client_email',
            'client_id',
            'auth_uri',
            'token_uri',
            'auth_provider_x509_cert_url',
            'client_x509_cert_url'
        ]
        
        missing_fields = [field for field in required_fields if field not in creds]
        
        if missing_fields:
            logger.error(f"Credentials file missing required fields: {', '.join(missing_fields)}")
            return None
            
        if creds['type'] != 'service_account':
            logger.error("Credentials must be for a service account")
            return None
            
        return creds
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in credentials file")
        return None
    except Exception as e:
        logger.error(f"Error validating credentials: {str(e)}")
        return None

def setup_environment(creds_path: str, env_file: str = '.env') -> bool:
    """Set up environment variables for Google Cloud Vision."""
    try:
        # Validate the credentials first
        if not validate_credentials(creds_path):
            return False
            
        # Get absolute path to credentials
        abs_creds_path = os.path.abspath(creds_path)
        
        # Check if .env file exists
        env_exists = os.path.exists(env_file)
        env_lines = []
        
        if env_exists:
            # Read existing .env file
            with open(env_file, 'r') as f:
                env_lines = f.readlines()
                
            # Remove any existing Google Vision settings
            env_lines = [line for line in env_lines if not line.startswith(('GOOGLE_APPLICATION_CREDENTIALS=',
                                                                          'GOOGLE_VISION_API_ENDPOINT=',
                                                                          'GOOGLE_VISION_TIMEOUT=',
                                                                          'GOOGLE_VISION_MAX_RETRIES=',
                                                                          'GOOGLE_VISION_BATCH_SIZE='))]
        
        # Add Google Vision settings
        env_lines.extend([
            f"\n# Google Cloud Vision OCR Configuration\n",
            f"GOOGLE_APPLICATION_CREDENTIALS={abs_creds_path}\n",
            "GOOGLE_VISION_API_ENDPOINT=https://vision.googleapis.com\n",
            "GOOGLE_VISION_TIMEOUT=30\n",
            "GOOGLE_VISION_MAX_RETRIES=3\n",
            "GOOGLE_VISION_BATCH_SIZE=10\n"
        ])
        
        # Write updated .env file
        with open(env_file, 'w') as f:
            f.writelines(env_lines)
            
        logger.info(f"Successfully updated {env_file} with Google Cloud Vision settings")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up environment: {str(e)}")
        return False

def test_credentials(creds_path: str) -> bool:
    """Test Google Cloud Vision credentials by attempting to initialize the client."""
    try:
        from google.cloud import vision
        
        # Set environment variable temporarily
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
        
        # Try to create a client
        client = vision.ImageAnnotatorClient()
        
        # Simple API call to verify credentials
        client.annotate_image({
            'image': {'source': {'image_uri': 'gs://cloud-samples-data/vision/text/screen.jpg'}},
            'features': [{'type_': vision.Feature.Type.TEXT_DETECTION}]
        })
        
        logger.info("Successfully tested Google Cloud Vision credentials")
        return True
        
    except Exception as e:
        logger.error(f"Error testing credentials: {str(e)}")
        return False

def main():
    """Main function for setting up Google Cloud Vision credentials."""
    parser = argparse.ArgumentParser(description='Setup Google Cloud Vision credentials')
    parser.add_argument('--credentials', required=True,
                      help='Path to Google Cloud Vision credentials JSON file')
    parser.add_argument('--env-file', default='.env',
                      help='Path to environment file (default: .env)')
    parser.add_argument('--test', action='store_true',
                      help='Test the credentials after setup')
    args = parser.parse_args()
    
    # Check if credentials file exists
    if not os.path.exists(args.credentials):
        logger.error(f"Credentials file not found: {args.credentials}")
        sys.exit(1)
    
    # Validate and setup credentials
    logger.info("Setting up Google Cloud Vision credentials...")
    if not setup_environment(args.credentials, args.env_file):
        logger.error("Failed to set up credentials")
        sys.exit(1)
    
    # Test credentials if requested
    if args.test:
        logger.info("Testing credentials...")
        if not test_credentials(args.credentials):
            logger.error("Credentials test failed")
            sys.exit(1)
    
    logger.info("Google Cloud Vision setup completed successfully")

if __name__ == '__main__':
    main() 