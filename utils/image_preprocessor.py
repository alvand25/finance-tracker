"""Image preprocessing module for OCR optimization."""

import os
import cv2
import numpy as np
import logging
from PIL import Image, ImageEnhance
from typing import Optional, Tuple, Dict, Any, Union
import io

logger = logging.getLogger(__name__)

class ImagePreprocessor:
    """Class for preprocessing images before OCR."""
    
    def __init__(self, debug_mode: bool = False, debug_output_dir: str = 'debug_output'):
        """
        Initialize the image preprocessor.
        
        Args:
            debug_mode: Whether to save intermediate processing steps
            debug_output_dir: Directory to save debug output
        """
        self.debug_mode = debug_mode
        self.debug_output_dir = debug_output_dir
        self.last_ocr_stats = {}
        
        if debug_mode:
            os.makedirs(debug_output_dir, exist_ok=True)
            
    def preprocess(self, image_data: Union[bytes, io.BytesIO, np.ndarray]) -> Image.Image:
        """
        Preprocess an image for better OCR results.
        
        Args:
            image_data: Image data as bytes, BytesIO, or numpy array
            
        Returns:
            PIL.Image: Preprocessed image
        """
        # Convert to numpy array
        if isinstance(image_data, (bytes, io.BytesIO)):
            nparr = np.frombuffer(image_data.read() if hasattr(image_data, 'read') else image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            img = image_data

        # Save original if in debug mode
        if self.debug_mode:
            self._save_debug_image(img, 'original.jpg')

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.debug_mode:
            self._save_debug_image(gray, 'grayscale.jpg')
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        if self.debug_mode:
            self._save_debug_image(thresh, 'threshold.jpg')
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh)
        if self.debug_mode:
            self._save_debug_image(denoised, 'denoised.jpg')
        
        # Convert back to PIL Image
        pil_image = Image.fromarray(denoised)
        
        return pil_image

    def extract_text(self, image: Union[str, Image.Image], ocr_engine: Optional[Any] = None) -> str:
        """
        Extract text from an image using the specified OCR engine.
        
        Args:
            image: PIL Image or path to image file
            ocr_engine: OCR engine to use (GoogleVisionOCR or TesseractOCR)
            
        Returns:
            Extracted text
        """
        try:
            # Preprocess the image
            preprocessed = self.preprocess(image)
            
            # Extract text using the OCR engine
            if ocr_engine is not None:
                result = ocr_engine.extract_text(preprocessed)
                self.last_ocr_stats = {
                    'engine': ocr_engine.__class__.__name__,
                    'confidence': result.get('confidence', 0),
                    'processing_time': result.get('processing_time', 0)
                }
                return result.get('text', '')
            else:
                logger.warning("No OCR engine provided, returning empty text")
                return ''
                
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            return ''
            
    def create_thumbnail(self, image: Image.Image, max_size: Tuple[int, int] = (300, 300)) -> Image.Image:
        """
        Create a thumbnail while maintaining aspect ratio.
        
        Args:
            image: PIL Image object
            max_size: Maximum dimensions (width, height)
            
        Returns:
            PIL.Image: Thumbnail image
        """
        thumb = image.copy()
        thumb.thumbnail(max_size, Image.Resampling.LANCZOS)
        return thumb

    def deskew(self, image: Image.Image) -> Image.Image:
        """
        Attempt to deskew a receipt image.
        
        Args:
            image: PIL Image object
            
        Returns:
            PIL.Image: Deskewed image
        """
        # Convert to numpy array
        img_array = np.array(image)
        
        # Convert to grayscale if needed
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        if self.debug_mode:
            self._save_debug_image(gray, 'deskew_gray.jpg')
        
        # Apply threshold
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        if self.debug_mode:
            self._save_debug_image(thresh, 'deskew_thresh.jpg')
        
        # Find all non-zero points
        coords = np.column_stack(np.where(thresh > 0))
        
        # Get the angle
        angle = cv2.minAreaRect(coords)[-1]
        
        # Adjust the angle
        if angle < -45:
            angle = 90 + angle
        
        # Rotate the image
        rotated = image.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
        
        if self.debug_mode:
            rotated_array = np.array(rotated)
            self._save_debug_image(rotated_array, 'deskew_result.jpg')
        
        return rotated

    def enhance_contrast(self, image: Image.Image) -> Image.Image:
        """
        Enhance image contrast using CLAHE.
        
        Args:
            image: PIL Image object
            
        Returns:
            PIL.Image: Contrast-enhanced image
        """
        # Convert to numpy array
        img_array = np.array(image)
        
        # Convert to LAB color space
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        
        if self.debug_mode:
            self._save_debug_image(lab, 'enhance_lab.jpg')
        
        # Split channels
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        cl = clahe.apply(l)
        
        if self.debug_mode:
            self._save_debug_image(cl, 'enhance_clahe.jpg')
        
        # Merge channels
        limg = cv2.merge((cl,a,b))
        
        # Convert back to RGB
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
        
        if self.debug_mode:
            self._save_debug_image(enhanced, 'enhance_result.jpg')
        
        return Image.fromarray(enhanced)

    def _save_debug_image(self, image: np.ndarray, filename: str):
        """Save an intermediate processing step image for debugging."""
        try:
            path = os.path.join(self.debug_output_dir, filename)
            cv2.imwrite(path, image)
            logger.debug(f"Saved debug image: {path}")
        except Exception as e:
            logger.error(f"Error saving debug image: {str(e)}")

    def save_image(self, image: Image.Image, path: str) -> None:
        """
        Save a PIL Image to disk.
        
        Args:
            image: PIL Image to save
            path: Path to save the image to
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Save the image
            image.save(path)
            logger.debug(f"Saved image to {path}")
        except Exception as e:
            logger.error(f"Error saving image to {path}: {str(e)}")

def preprocess_image(image_data):
    """
    Preprocess an image for better OCR results.
    
    Args:
        image_data: Either a file-like object or bytes containing the image data
        
    Returns:
        PIL.Image: Preprocessed image ready for OCR
    """
    # Convert to numpy array
    if isinstance(image_data, (bytes, io.BytesIO)):
        nparr = np.frombuffer(image_data.read() if hasattr(image_data, 'read') else image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    else:
        # Assume it's already a numpy array
        img = image_data

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # Denoise
    denoised = cv2.fastNlMeansDenoising(thresh)
    
    # Convert back to PIL Image
    pil_image = Image.fromarray(denoised)
    
    return pil_image

def create_thumbnail(image, max_size=(300, 300)):
    """
    Create a thumbnail of the image while maintaining aspect ratio.
    
    Args:
        image: PIL.Image object
        max_size: Tuple of (width, height) for maximum thumbnail dimensions
        
    Returns:
        PIL.Image: Thumbnail image
    """
    # Create a copy to avoid modifying the original
    thumb = image.copy()
    thumb.thumbnail(max_size, Image.Resampling.LANCZOS)
    return thumb

def rotate_image(image, angle):
    """
    Rotate an image by the specified angle.
    
    Args:
        image: PIL.Image object
        angle: Rotation angle in degrees
        
    Returns:
        PIL.Image: Rotated image
    """
    return image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)

def deskew_image(image):
    """
    Attempt to deskew a receipt image by detecting the dominant text angle.
    
    Args:
        image: PIL.Image object
        
    Returns:
        PIL.Image: Deskewed image
    """
    # Convert to numpy array
    img_array = np.array(image)
    
    # Convert to grayscale if needed
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # Apply threshold to get binary image
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Find all non-zero points
    coords = np.column_stack(np.where(thresh > 0))
    
    # Get the angle
    angle = cv2.minAreaRect(coords)[-1]
    
    # Adjust the angle
    if angle < -45:
        angle = 90 + angle
    
    # Rotate the image
    return rotate_image(image, -angle)

def enhance_contrast(image):
    """
    Enhance the contrast of the image using CLAHE (Contrast Limited Adaptive Histogram Equalization).
    
    Args:
        image: PIL.Image object
        
    Returns:
        PIL.Image: Contrast-enhanced image
    """
    # Convert to numpy array
    img_array = np.array(image)
    
    # Convert to LAB color space
    lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
    
    # Split the LAB channels
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE to L channel
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    
    # Merge channels
    limg = cv2.merge((cl,a,b))
    
    # Convert back to RGB
    enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)
    
    return Image.fromarray(enhanced)