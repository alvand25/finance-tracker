#!/usr/bin/env python3
"""Script to test Google Cloud Vision setup."""
import os
import sys
import argparse
import logging
from pathlib import Path

from config.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_vision_setup(test_image: str = None) -> bool:
    """Test Google Cloud Vision setup."""
    try:
        # Load and validate configuration
        logger.info("Loading Google Cloud Vision configuration...")
        config = GoogleVisionConfig()
        
        if not config.is_configured:
            logger.error("Google Cloud Vision is not configured. "
                        "Set GOOGLE_APPLICATION_CREDENTIALS environment variable.")
            return False
            
        try:
            config.validate()
        except (ValueError, FileNotFoundError) as e:
            logger.error(f"Configuration validation failed: {str(e)}")
            return False
            
        logger.info("Configuration validation successful")
        
        # Initialize OCR client
        logger.info("Initializing Google Cloud Vision client...")
        ocr = GoogleVisionOCR(credentials_path=config.credentials_path)
        
        # Test with sample image if provided, otherwise use a test pattern
        if test_image and os.path.exists(test_image):
            logger.info(f"Testing OCR with provided image: {test_image}")
            image_path = test_image
        else:
            # Create a simple test image
            logger.info("Creating test image...")
            from PIL import Image, ImageDraw, ImageFont
            
            image = Image.new('RGB', (400, 100), color='white')
            draw = ImageDraw.Draw(image)
            text = "Google Cloud Vision Test"
            
            # Try to use a system font
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
                except:
                    font = ImageFont.load_default()
            
            # Draw text
            text_bbox = draw.textbbox((0, 0), text, font=font)
            x = (400 - (text_bbox[2] - text_bbox[0])) // 2
            y = (100 - (text_bbox[3] - text_bbox[1])) // 2
            draw.text((x, y), text, fill='black', font=font)
            
            # Save the test image
            image_path = "test_vision_setup.jpg"
            image.save(image_path)
            logger.info(f"Created test image: {image_path}")
        
        # Test OCR
        logger.info("Testing OCR...")
        result = ocr.extract_text(image_path)
        
        if 'error' in result:
            logger.error(f"OCR test failed: {result['error']}")
            return False
            
        logger.info("OCR test successful")
        logger.info(f"Extracted text: {result['text']}")
        logger.info(f"Confidence: {result['confidence']:.2f}")
        
        # Clean up test image if we created it
        if not test_image and os.path.exists("test_vision_setup.jpg"):
            os.remove("test_vision_setup.jpg")
            logger.info("Cleaned up test image")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Test Google Cloud Vision setup')
    parser.add_argument('--image', help='Path to test image (optional)')
    args = parser.parse_args()
    
    success = test_vision_setup(args.image)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main() 