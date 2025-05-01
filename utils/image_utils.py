import cv2
import numpy as np
import logging
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)

def is_image_valid(image: np.ndarray) -> bool:
    """
    Check if an image is valid for OCR processing.
    
    Args:
        image: Input image as numpy array
        
    Returns:
        True if image is valid, False otherwise
    """
    if image is None:
        return False
        
    # Check image dimensions
    h, w = image.shape[:2]
    if h < 100 or w < 100:  # Too small to be a receipt
        return False
        
    # Check if image is too dark or too bright
    if len(image.shape) == 3:  # Color image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
        
    mean_brightness = np.mean(gray)
    if mean_brightness < 20 or mean_brightness > 235:
        return False
        
    # Check if image has enough contrast
    std_dev = np.std(gray)
    if std_dev < 20:  # Too little contrast
        return False
    
    return True

def preprocess_image(image_path: str, debug: bool = False) -> Optional[np.ndarray]:
    """
    Preprocess an image for better OCR results.
    
    Args:
        image_path: Path to the image file
        debug: Whether to log debug information
        
    Returns:
        Preprocessed image as numpy array, or None if processing fails
    """
    try:
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"Could not read image from {image_path}")
            return None
            
        if debug:
            logger.debug(f"Original image shape: {image.shape}")
        
        # Validate image
        if not is_image_valid(image):
            logger.error(f"Image validation failed for {image_path}")
            return None
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Basic noise removal
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # Enhance contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(denoised)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        
        # Deskew if needed (with timeout protection)
        angle = get_skew_angle(thresh, timeout=5.0)
        if angle is not None and abs(angle) > 0.5:  # Only deskew if angle is significant
            if debug:
                logger.debug(f"Deskewing image by {angle:.2f} degrees")
            result = deskew(thresh, angle)
        else:
            result = thresh
        
        # Final validation
        if not is_image_valid(result):
            logger.error("Preprocessing resulted in invalid image")
            return None
            
        return result
        
    except Exception as e:
        logger.error(f"Error preprocessing image: {str(e)}")
        return None

def get_skew_angle(image: np.ndarray, timeout: float = 5.0) -> Optional[float]:
    """
    Calculate the skew angle of text in an image with timeout protection.
    
    Args:
        image: Input image as numpy array
        timeout: Maximum time in seconds to spend on angle detection
        
    Returns:
        Estimated skew angle in degrees, or None if detection fails/times out
    """
    try:
        start_time = time.time()
        
        # Detect edges
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        
        # Use Hough transform to detect lines
        lines = cv2.HoughLines(edges, 1, np.pi/180, 100)
        
        if lines is None or time.time() - start_time > timeout:
            return None
        
        # Limit number of lines to process
        max_lines = 100
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        
        angles = []
        for rho, theta in lines[:, 0]:
            if time.time() - start_time > timeout:
                logger.warning("Skew angle detection timed out")
                return None
                
            # Convert theta to degrees and normalize
            angle = np.degrees(theta)
            if angle < 45:
                angles.append(angle)
            elif angle > 135:
                angles.append(angle - 180)
        
        if angles:
            # Use median angle to avoid outliers
            return np.median(angles)
        
        return None
        
    except Exception as e:
        logger.error(f"Error in skew angle detection: {str(e)}")
        return None

def deskew(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotate an image to correct skew.
    
    Args:
        image: Input image as numpy array
        angle: Angle to rotate in degrees
        
    Returns:
        Deskewed image
    """
    try:
        # Get image dimensions
        h, w = image.shape[:2]
        center = (w//2, h//2)
        
        # Get rotation matrix
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Perform rotation
        rotated = cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        
        return rotated
        
    except Exception as e:
        logger.error(f"Error in deskewing: {str(e)}")
        return image  # Return original image if deskewing fails 