"""Google Cloud Vision OCR implementation."""

import io
import os
import logging
import time
from typing import Dict, Any, List, Optional, Union
from google.cloud import vision
from google.api_core import retry
from PIL import Image

logger = logging.getLogger(__name__)

class GoogleVisionOCR:
    """OCR engine using Google Cloud Vision API."""
    
    def __init__(self, 
                 credentials_path: str,
                 timeout: int = 30,
                 max_retries: int = 3,
                 batch_size: int = 10):
        """
        Initialize Google Cloud Vision OCR.
        
        Args:
            credentials_path: Path to service account credentials JSON
            timeout: API request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            batch_size: Number of images to process in parallel
        """
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        self.client = vision.ImageAnnotatorClient()
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.last_processing_time = 0
        
        # Configure retry strategy
        self.retry_strategy = retry.Retry(
            initial=1.0,  # Initial delay in seconds
            maximum=10.0,  # Maximum delay between retries
            multiplier=2.0,  # Multiplier for exponential backoff
            predicate=retry.if_exception_type(
                ConnectionError,
                TimeoutError,
                Exception  # Add specific exceptions as needed
            )
        )

        # Validate API access on initialization
        self.validate_api_access()
        
    def validate_api_access(self) -> None:
        """
        Validate that the Google Cloud Vision API is enabled and accessible.
        Raises an exception if the API is disabled or inaccessible.
        """
        try:
            # Create a minimal test image (1x1 pixel)
            test_image = Image.new('RGB', (1, 1), color='white')
            img_byte_arr = io.BytesIO()
            test_image.save(img_byte_arr, format='PNG')
            content = img_byte_arr.getvalue()
            
            # Create Vision API image
            vision_image = vision.Image(content=content)
            
            # Attempt a minimal API call
            self.client.document_text_detection(
                image=vision_image,
                timeout=5  # Short timeout for validation
            )
            
            logger.info("Successfully validated Google Cloud Vision API access")
            
        except Exception as e:
            error_msg = str(e)
            if "SERVICE_DISABLED" in error_msg:
                # Extract project ID from error message
                import re
                project_match = re.search(r'project=(\d+)', error_msg)
                project_id = project_match.group(1) if project_match else "unknown"
                
                raise RuntimeError(
                    f"Google Cloud Vision API is disabled for project {project_id}. "
                    f"Please enable it at: https://console.developers.google.com/apis/api/"
                    f"vision.googleapis.com/overview?project={project_id}"
                )
            else:
                raise RuntimeError(f"Failed to validate Google Cloud Vision API access: {error_msg}")
        
    @retry.Retry(predicate=retry.if_exception_type(Exception))
    def _extract_text_with_retry(self, image: vision.Image) -> vision.TextAnnotation:
        """Extract text from image with retry logic."""
        try:
            start_time = time.time()
            response = self.client.document_text_detection(
                image=image,
                timeout=self.timeout
            )
            self.last_processing_time = time.time() - start_time
            return response.full_text_annotation
        except Exception as e:
            logger.error(f"Error in OCR request: {str(e)}")
            raise
            
    def extract_text(self, image: Union[str, Image.Image]) -> Dict[str, Any]:
        """
        Extract text from an image using Google Cloud Vision.
        
        Args:
            image: Path to image file or PIL Image object
            
        Returns:
            Dictionary containing:
                - text: Extracted text
                - confidence: Overall confidence score
                - text_blocks: List of text blocks with positions
                - processing_time: Time taken for OCR
        """
        try:
            # Handle both file paths and PIL Image objects
            if isinstance(image, str):
                # Load image from file path
                with open(image, 'rb') as image_file:
                    content = image_file.read()
            else:
                # Convert PIL Image to bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format=image.format or 'PNG')
                content = img_byte_arr.getvalue()
            
            # Create Vision API image
            vision_image = vision.Image(content=content)
            
            # Extract text with retry
            annotation = self._extract_text_with_retry(vision_image)
            
            # Process text blocks
            text_blocks = []
            total_confidence = 0
            block_count = 0
            
            for page in annotation.pages:
                for block in page.blocks:
                    block_text = ''
                    block_confidence = block.confidence
                    
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            word_text = ''.join([
                                symbol.text for symbol in word.symbols
                            ])
                            block_text += word_text + ' '
                            
                    text_blocks.append({
                        'text': block_text.strip(),
                        'confidence': block_confidence,
                        'bounding_box': {
                            'left': block.bounding_box.vertices[0].x,
                            'top': block.bounding_box.vertices[0].y,
                            'right': block.bounding_box.vertices[2].x,
                            'bottom': block.bounding_box.vertices[2].y
                        }
                    })
                    
                    total_confidence += block_confidence
                    block_count += 1
                    
            # Calculate overall confidence
            avg_confidence = total_confidence / block_count if block_count > 0 else 0
            
            return {
                'text': annotation.text,
                'confidence': avg_confidence,
                'text_blocks': text_blocks,
                'processing_time': self.last_processing_time
            }
            
        except Exception as e:
            logger.error(f"Error extracting text from image: {str(e)}")
            return {
                'text': '',
                'confidence': 0,
                'text_blocks': [],
                'error': str(e)
            }
            
    def batch_process_images(self, image_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple images in batches.
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            List of OCR results for each image
        """
        results = []
        
        # Process images in batches
        for i in range(0, len(image_paths), self.batch_size):
            batch = image_paths[i:i + self.batch_size]
            logger.info(f"Processing batch {i//self.batch_size + 1}")
            
            for image_path in batch:
                try:
                    result = self.extract_text(image_path)
                    result['image_path'] = image_path
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {image_path}: {str(e)}")
                    results.append({
                        'image_path': image_path,
                        'error': str(e)
                    })
                    
        return results
        
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the OCR engine."""
        return {
            'engine': 'google_vision',
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'batch_size': self.batch_size,
            'last_processing_time': self.last_processing_time
        } 