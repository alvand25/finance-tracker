#!/usr/bin/env python3
"""
Receipt Test Runner

This script runs receipt processing tests on sample images and generates reports.
It provides a simple, single-pass test flow with optional fallback processing.

Usage:
    python continuous_test_runner.py [--with-fallback]
"""

import os
import sys
import time
import json
import logging
import argparse
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from receipt_processor import ReceiptProcessor
from utils.receipt_analyzer import ReceiptAnalyzer
from utils.image_preprocessor import ImagePreprocessor
from ocr.google_vision_ocr import GoogleVisionOCR
from ocr.tesseract_ocr import TesseractOCR
from config.google_vision_config import GoogleVisionConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
RESULTS_DIR = "test_results"
REPORTS_DIR = "reports"
LOGS_DIR = "logs"
SAMPLES_DIR = "samples/images"

# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class TestStats:
    """Track test statistics."""
    
    def __init__(self):
        self.total_runs = 0
        self.successful = 0
        self.failed = 0
        self.start_time = datetime.now()
        
    def record_success(self):
        """Record a successful test."""
        self.total_runs += 1
        self.successful += 1
        
    def record_failure(self):
        """Record a failed test."""
        self.total_runs += 1
        self.failed += 1
        
    @property
    def duration(self):
        """Get test duration."""
        return datetime.now() - self.start_time

class ReceiptTestRunner:
    """Run receipt processing tests."""
    
    def __init__(self, use_fallback: bool = False):
        """Initialize the test runner.
        
        Args:
            use_fallback: Whether to use fallback processing
        """
        self.use_fallback = use_fallback
        self.stats = TestStats()
        
        # Set up directories
        os.makedirs(RESULTS_DIR, exist_ok=True)
        os.makedirs(REPORTS_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        # Initialize processor
        self.processor = ReceiptProcessor(debug_mode=True)
        
        # Initialize OCR engines
        self._setup_ocr()
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
    def _setup_ocr(self):
        """Set up OCR engines."""
        # Initialize Google Vision
        config = GoogleVisionConfig()
        if not config.is_configured:
            logger.error("Google Vision credentials not configured")
            sys.exit(1)
            
        try:
            config.validate()
            self.google_vision = GoogleVisionOCR(
                credentials_path=config.credentials_path,
                timeout=config.timeout,
                max_retries=config.max_retries,
                batch_size=config.batch_size
            )
            logger.info("Using Google Cloud Vision OCR")
            
            # Initialize Tesseract if fallback enabled
            if self.use_fallback:
                self.tesseract = TesseractOCR()
                logger.info("Initialized Tesseract OCR for fallback")
                
        except Exception as e:
            logger.error(f"Failed to initialize OCR: {e}")
            sys.exit(1)
        
    def run_tests(self):
        """Run tests on all sample images."""
        logger = logging.getLogger(__name__)
        logger.info("Starting receipt test runner...")
        
        # Find sample images
        sample_images = [f for f in os.listdir(SAMPLES_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))]
        logger.info(f"Found {len(sample_images)} sample images to process")
        
        # Process each sample
        logger.info("Using %s processing mode", "fallback" if self.use_fallback else "standard")
        for image_name in sample_images:
            image_path = os.path.join(SAMPLES_DIR, image_name)
            logger.info(f"Processing {image_path}...")
            
            try:
                if self.use_fallback:
                    result = self._process_with_fallback(image_path)
                else:
                    result = self._process_standard(image_path)
                    
                # Save outputs
                base_name = os.path.splitext(image_name)[0]
                self._save_outputs(base_name, result)
                
            except Exception as e:
                logger.error(f"Error processing {image_name}: {str(e)}")
                logger.error(traceback.format_exc())
                self.stats.record_failure()
                continue
                
        # Log final statistics
        logger.info("Test Statistics:\n---------------")
        logger.info(f"Total Runs: {self.stats.total_runs}")
        logger.info(f"Successful Extractions: {self.stats.successful}")
        logger.info(f"Failed Extractions: {self.stats.failed}")
        logger.info(f"Duration: {self.stats.duration}")
        
    def _process_standard(self, image_path: str) -> Dict[str, Any]:
        """Process a sample with standard settings."""
        options = {
            'debug_mode': True,
            'ocr_engine': self.google_vision
        }
        
        try:
            result = self.processor.process_image(image_path, options)
            if result.get('confidence', {}).get('overall', 0) > 0.5:
                self.stats.record_success()
            else:
                self.stats.record_failure()
            return result
        except Exception as e:
            logger.error(f"Standard processing failed: {str(e)}")
            self.stats.record_failure()
            return {'status': 'failed', 'error': str(e)}
            
    def _process_with_fallback(self, image_path: str) -> Dict[str, Any]:
        """Process a sample with fallback settings."""
        # First try with Google Vision
        standard_options = {
            'debug_mode': True,
            'ocr_engine': self.google_vision
        }
        
        try:
            result = self.processor.process_image(image_path, standard_options)
            if result.get('confidence', {}).get('overall', 0) > 0.5:
                self.stats.record_success()
                return result
                
            # If low confidence, try Tesseract with enhanced preprocessing
            fallback_options = {
                'debug_mode': True,
                'ocr_engine': self.tesseract,
                'preprocess_options': {
                    'enhance_contrast': True,
                    'denoise': True
                }
            }
            
            fallback_result = self.processor.process_image(image_path, fallback_options)
            
            # Compare results and use the better one
            if fallback_result.get('confidence', {}).get('overall', 0) > result.get('confidence', {}).get('overall', 0):
                self.stats.record_success()
                return fallback_result
            else:
                self.stats.record_failure()
                return result
                
        except Exception as e:
            logger.error(f"Fallback processing failed: {str(e)}")
            self.stats.record_failure()
            return {'status': 'failed', 'error': str(e)}
            
    def _save_outputs(self, base_name: str, result: Dict[str, Any]):
        """Save test outputs for a receipt."""
        # Save JSON result
        json_path = os.path.join(RESULTS_DIR, f"{base_name}.json")
        with open(json_path, 'w') as f:
            json.dump(result, f, indent=2, cls=DateTimeEncoder)
            
        # Save HTML report
        html_path = os.path.join(REPORTS_DIR, f"{base_name}.html")
        self._generate_html_report(html_path, result)
        
        # Log status
        status = 'success' if result.get('confidence', {}).get('overall', 0) > 0.5 else 'failed'
        logger.info(f"Saved outputs for {base_name} with status: {status}")
        
    def _generate_html_report(self, path: str, result: Dict[str, Any]):
        """Generate an HTML report for the test result."""
        # Get values with defaults for None
        store_name = result.get('store', 'Unknown Store')
        confidence = result.get('confidence', {}).get('overall', 0)
        items = result.get('items', [])
        subtotal = result.get('subtotal', 0) or 0
        tax = result.get('tax', 0) or 0
        total = result.get('total', 0) or 0
        
        html = f"""
        <html>
        <head>
            <title>Receipt Test Report - {store_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #f0f0f0; padding: 10px; }}
                .section {{ margin: 20px 0; }}
                .items {{ list-style: none; }}
                .confidence {{ color: {'green' if confidence > 0.5 else 'red'}; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Receipt Test Report</h1>
                <p>Store: {store_name}</p>
                <p>Confidence: <span class="confidence">{confidence:.2f}</span></p>
            </div>
            
            <div class="section">
                <h2>Items</h2>
                <ul class="items">
        """
        
        for item in items:
            description = item.get('description', 'Unknown Item')
            price = item.get('price', 0) or 0
            html += f"<li>{description}: ${price:.2f}</li>"
            
        html += f"""
                </ul>
            </div>
            
            <div class="section">
                <h2>Totals</h2>
                <p>Subtotal: ${subtotal:.2f}</p>
                <p>Tax: ${tax:.2f}</p>
                <p>Total: ${total:.2f}</p>
            </div>
        </body>
        </html>
        """
        
        with open(path, 'w') as f:
            f.write(html)

def main():
    """Run the receipt tests."""
    parser = argparse.ArgumentParser(description='Run receipt processing tests.')
    parser.add_argument('--with-fallback', action='store_true', help='Enable fallback processing')
    args = parser.parse_args()
    
    runner = ReceiptTestRunner(use_fallback=args.with_fallback)
    runner.run_tests()

if __name__ == '__main__':
    main() 