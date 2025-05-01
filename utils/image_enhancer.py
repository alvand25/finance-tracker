#!/usr/bin/env python3
"""
Image enhancement utilities for improving OCR results.
"""

import os
import cv2
import numpy as np
import logging
from PIL import Image, ImageEnhance, ImageFilter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ImageEnhancer:
    """Class for enhancing images to improve OCR results."""
    
    def __init__(self, image_path: str, debug: bool = False):
        """
        Initialize the image enhancer.
        
        Args:
            image_path: Path to the image file
            debug: Whether to enable debug logging and save intermediate images
        """
        self.image_path = image_path
        self.debug = debug
        self.debug_dir = "debug/images"
        
        if self.debug:
            os.makedirs(self.debug_dir, exist_ok=True)
    
    def enhance(self, resize: bool = True, target_width: int = 2000,
                contrast: float = 1.5, brightness: float = 1.2,
                sharpness: float = 1.5, denoise: bool = True) -> np.ndarray:
        """
        Enhance an image for better OCR results.
        
        Args:
            resize: Whether to resize the image
            target_width: Target width for resizing
            contrast: Contrast enhancement factor
            brightness: Brightness enhancement factor
            sharpness: Sharpness enhancement factor
            denoise: Whether to apply denoising
            
        Returns:
            Enhanced image as a numpy array
        """
        # Read the image
        try:
            image = cv2.imread(self.image_path)
            if image is None:
                logger.error(f"Failed to read image: {self.image_path}")
                return None
                
            if self.debug:
                logger.debug(f"Original image shape: {image.shape}")
                self._save_debug_image(image, "01_original.jpg")
        except Exception as e:
            logger.error(f"Error reading image: {str(e)}")
            return None
        
        # Resize the image if requested
        if resize:
            height, width = image.shape[:2]
            if width > target_width:
                scale = target_width / width
                new_height = int(height * scale)
                image = cv2.resize(image, (target_width, new_height))
                
                if self.debug:
                    logger.debug(f"Resized image to {target_width}x{new_height}")
                    self._save_debug_image(image, "02_resized.jpg")
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.debug:
            self._save_debug_image(gray, "03_grayscale.jpg")
        
        # Check if the image has a dark background with light text
        is_inverted = self._is_inverted(gray)
        if is_inverted:
            logger.debug("Detected dark background, inverting image")
            gray = cv2.bitwise_not(gray)
            if self.debug:
                self._save_debug_image(gray, "04_inverted.jpg")
        
        # Apply adaptive histogram equalization
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        if self.debug:
            self._save_debug_image(enhanced, "05_clahe.jpg")
        
        # Convert to PIL image for easier enhancement
        pil_image = Image.fromarray(enhanced)
        
        # Enhance contrast
        contrast_enhancer = ImageEnhance.Contrast(pil_image)
        pil_image = contrast_enhancer.enhance(contrast)
        
        # Enhance brightness
        brightness_enhancer = ImageEnhance.Brightness(pil_image)
        pil_image = brightness_enhancer.enhance(brightness)
        
        # Enhance sharpness
        sharpness_enhancer = ImageEnhance.Sharpness(pil_image)
        pil_image = sharpness_enhancer.enhance(sharpness)
        
        # Apply median filter to reduce noise
        pil_image = pil_image.filter(ImageFilter.MedianFilter(size=3))
        
        # Convert back to OpenCV format
        enhanced = np.array(pil_image)
        if self.debug:
            self._save_debug_image(enhanced, "06_enhanced.jpg")
        
        # Apply denoising if requested
        if denoise:
            enhanced = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
            if self.debug:
                self._save_debug_image(enhanced, "07_denoised.jpg")
        
        # Threshold to make text more clear
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug:
            self._save_debug_image(binary, "08_binary.jpg")
        
        # Apply dilation to thicken text slightly
        kernel = np.ones((1, 1), np.uint8)
        dilated = cv2.dilate(binary, kernel, iterations=1)
        if self.debug:
            self._save_debug_image(dilated, "09_dilated.jpg")
        
        return dilated
    
    def _is_inverted(self, gray_image: np.ndarray) -> bool:
        """
        Check if the image has a dark background with light text.
        
        Args:
            gray_image: Grayscale image as a numpy array
            
        Returns:
            True if the image has a dark background, False otherwise
        """
        # Calculate the average pixel value
        avg_value = np.mean(gray_image)
        
        # If the average value is less than 128, it's likely a dark background
        return avg_value < 128
    
    def _save_debug_image(self, image: np.ndarray, filename: str) -> None:
        """
        Save an image for debugging purposes.
        
        Args:
            image: Image as a numpy array
            filename: Filename to save as
        """
        if not self.debug:
            return
            
        try:
            # Create a debug filename with the original filename as a prefix
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            debug_filename = f"{base_name}_{filename}"
            debug_path = os.path.join(self.debug_dir, debug_filename)
            
            # Save the image
            cv2.imwrite(debug_path, image)
            logger.debug(f"Saved debug image: {debug_path}")
        except Exception as e:
            logger.error(f"Error saving debug image: {str(e)}")

def enhance_receipt_image(image_path: str, debug: bool = False) -> np.ndarray:
    """
    Enhance a receipt image for better OCR results.
    
    Args:
        image_path: Path to the image file
        debug: Whether to enable debug logging and save intermediate images
        
    Returns:
        Enhanced image as a numpy array
    """
    enhancer = ImageEnhancer(image_path, debug)
    return enhancer.enhance() 