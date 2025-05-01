import os
import logging
import cv2
import numpy as np
from typing import Optional, Tuple, Union
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

class ImagePreprocessor:
    """
    Image preprocessing for receipt OCR.
    
    This class handles various image enhancement techniques to improve OCR accuracy:
    - Contrast enhancement
    - Deskewing (rotation correction)
    - Noise reduction
    - Border removal
    - Text enhancement
    - Resolution optimization
    """
    
    def __init__(self, 
                 debug_mode: bool = False, 
                 debug_dir: str = "debug",
                 ocr_engine: str = "tesseract",
                 max_skew_angle: float = 45.0,
                 target_dpi: int = 300):
        """
        Initialize the image preprocessor.
        
        Args:
            debug_mode: Whether to save debug images
            debug_dir: Directory to save debug images
            ocr_engine: OCR engine to use ("tesseract" or "custom")
            max_skew_angle: Maximum skew angle to attempt correction (in degrees)
            target_dpi: Target DPI for image scaling (300 DPI is optimal for Tesseract)
        """
        self.debug_mode = debug_mode
        self.debug_dir = debug_dir
        self.ocr_engine = ocr_engine
        self.last_ocr_stats = {}
        self.max_skew_angle = max_skew_angle
        self.target_dpi = target_dpi
        
        # Enhanced Tesseract configuration
        self.tesseract_config = '--psm 6 --oem 3 -l eng'
        
        # Ensure debug directory exists if in debug mode
        if debug_mode and not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
            
        logger.info(f"Image preprocessor initialized with OCR engine: {ocr_engine}")
    
    def preprocess(self, image_path: str) -> np.ndarray:
        """
        Preprocess an image for improved OCR.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Preprocessed image as numpy array
        """
        logger.info(f"[Preprocessor] Starting processing for {image_path}")
        
        try:
            # Read the image
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"[Preprocessor] Failed to read image: {image_path}")
                raise ValueError(f"Failed to read image: {image_path}")
                
            logger.debug(f"[Preprocessor] Original image shape: {image.shape}")
                
            # Save original image if in debug mode
            if self.debug_mode:
                debug_path = os.path.join(self.debug_dir, "original_image.jpg")
                cv2.imwrite(debug_path, image)
                logger.debug(f"[Preprocessor] Saved original image to {debug_path}")
            
            # Step 1: Convert to grayscale if not already
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                logger.debug(f"[Preprocessor] Converted to grayscale → shape: {gray.shape}")
            else:
                gray = image.copy()
                logger.debug(f"[Preprocessor] Image already grayscale → shape: {gray.shape}")
            
            # Step 2: Scale the image to optimal DPI for OCR
            scaled = self._scale_to_dpi(gray)
            
            # Step 3: Apply advanced noise reduction
            denoised = self._advanced_denoise(scaled)
            
            # Step 4: Enhance text using multiple techniques
            enhanced = self._enhance_text(denoised)
            
            # Step 5: Apply adaptive thresholding
            binary = self._adaptive_threshold(enhanced)
            
            # Step 6: Deskew the image
            deskewed = self._deskew(binary)
            
            # Step 7: Remove borders
            cropped = self._crop_borders(deskewed)
            
            # Save final processed image if in debug mode
            if self.debug_mode:
                debug_path = os.path.join(self.debug_dir, "processed_image.jpg")
                cv2.imwrite(debug_path, cropped)
                logger.debug(f"[Preprocessor] Saved processed image to {debug_path}")
            
            logger.info("[Preprocessor] Image preprocessing completed successfully")
            return cropped
            
        except Exception as e:
            logger.error(f"[Preprocessor] Error preprocessing image: {str(e)}")
            # Return original image if preprocessing fails
            return cv2.imread(image_path)
    
    def _scale_to_dpi(self, image: np.ndarray) -> np.ndarray:
        """Scale image to target DPI."""
        try:
            # Calculate scale factor (assuming source is 72 DPI)
            scale_factor = self.target_dpi / 72.0
            
            # Calculate new dimensions
            new_width = int(image.shape[1] * scale_factor)
            new_height = int(image.shape[0] * scale_factor)
            
            # Scale using Lanczos interpolation for better quality
            scaled = cv2.resize(image, (new_width, new_height), 
                              interpolation=cv2.INTER_LANCZOS4)
            
            logger.debug(f"Scaled image to {new_width}x{new_height} for {self.target_dpi} DPI")
            return scaled
            
        except Exception as e:
            logger.warning(f"Error scaling image: {str(e)}")
            return image
    
    def _advanced_denoise(self, image: np.ndarray) -> np.ndarray:
        """Apply advanced noise reduction techniques."""
        try:
            # Apply Non-local Means Denoising
            denoised = cv2.fastNlMeansDenoising(image, None, h=10, templateWindowSize=7, searchWindowSize=21)
            
            # Apply bilateral filter to preserve edges
            denoised = cv2.bilateralFilter(denoised, d=9, sigmaColor=75, sigmaSpace=75)
            
            # Remove small noise using morphological operations
            kernel = np.ones((2, 2), np.uint8)
            denoised = cv2.morphologyEx(denoised, cv2.MORPH_OPEN, kernel)
            
            logger.debug("Applied advanced noise reduction")
            return denoised
            
        except Exception as e:
            logger.warning(f"Error in advanced denoising: {str(e)}")
            return image
    
    def _enhance_text(self, image: np.ndarray) -> np.ndarray:
        """Enhance text using multiple techniques."""
        try:
            # Apply CLAHE for local contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(image)
            
            # Sharpen the image using unsharp masking
            gaussian = cv2.GaussianBlur(enhanced, (0, 0), 3.0)
            enhanced = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)
            
            # Enhance text edges
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            enhanced = cv2.filter2D(enhanced, -1, kernel)
            
            logger.debug("Applied text enhancement techniques")
            return enhanced
            
        except Exception as e:
            logger.warning(f"Error enhancing text: {str(e)}")
            return image
    
    def _adaptive_threshold(self, image: np.ndarray) -> np.ndarray:
        """Apply adaptive thresholding with optimized parameters."""
        try:
            # Calculate optimal block size based on image size
            height = image.shape[0]
            block_size = max(11, min(31, int(height * 0.02) | 1))
            
            # Apply adaptive threshold
            binary = cv2.adaptiveThreshold(
                image,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size,
                2
            )
            
            logger.debug(f"Applied adaptive threshold with block size {block_size}")
            return binary
            
        except Exception as e:
            logger.warning(f"Error in adaptive thresholding: {str(e)}")
            return image
    
    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """
        Correct skew in an image.
        
        Returns:
            Deskewed image if angle is within max_skew_angle, otherwise original image
        """
        try:
            # Find all non-zero points
            coords = np.column_stack(np.where(image > 0))
            
            # Get the minimum area rectangle
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            
            # Adjust the angle
            if angle < -45:
                angle = 90 + angle
            elif angle > 45:
                angle = angle - 90
            
            # Store the detected angle for OCR stats
            self.last_ocr_stats['detected_skew_angle'] = f"{angle:.2f}°"
            
            # Skip if angle exceeds maximum
            if abs(angle) > self.max_skew_angle:
                logger.warning(f"Skew angle {angle:.2f}° exceeds maximum {self.max_skew_angle}°, skipping deskew")
                self.last_ocr_stats['skew_correction'] = 'skipped - angle too large'
                return image
            
            # Skip small angles
            if abs(angle) < 0.5:
                logger.debug("Skew angle too small, skipping deskew")
                self.last_ocr_stats['skew_correction'] = 'skipped - angle too small'
                return image
                
            # Get the rotation matrix
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            
            # Apply the rotation
            rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            
            logger.debug(f"Deskewed image by {angle:.2f} degrees")
            self.last_ocr_stats['skew_correction'] = f"applied {angle:.2f}° rotation"
            return rotated
            
        except Exception as e:
            logger.warning(f"Error deskewing image: {str(e)}")
            self.last_ocr_stats['skew_correction'] = f'error - {str(e)}'
            return image
    
    def _crop_borders(self, image: np.ndarray) -> np.ndarray:
        """Crop unnecessary borders from an image."""
        try:
            # Find all non-zero points
            non_zero_pixels = cv2.findNonZero(image)
            
            # Get the bounding rectangle
            x, y, w, h = cv2.boundingRect(non_zero_pixels)
            
            # Add a small padding
            padding = 10
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(image.shape[1] - x, w + 2 * padding)
            h = min(image.shape[0] - y, h + 2 * padding)
            
            # Crop the image
            cropped = image[y:y+h, x:x+w]
            
            logger.debug(f"Cropped image to {w}x{h} from {image.shape[1]}x{image.shape[0]}")
            return cropped
            
        except Exception as e:
            logger.warning(f"Error cropping image: {str(e)}")
            return image
    
    def extract_text(self, image: Union[str, np.ndarray]) -> str:
        """
        Extract text from an image using OCR.
        
        Args:
            image: Image path or numpy array
            
        Returns:
            Extracted text
        """
        try:
            # If image is a string, load it
            if isinstance(image, str):
                image = cv2.imread(image)
                if image is None:
                    raise ValueError(f"Failed to read image: {image}")
            
            # Convert OpenCV image (numpy array) to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            
            # Get OCR data with confidence scores
            ocr_data = pytesseract.image_to_data(pil_image, lang='eng', config=self.tesseract_config, output_type=pytesseract.Output.DICT)
            
            # Extract text and calculate statistics
            text_parts = []
            total_confidence = 0
            word_count = 0
            low_conf_words = 0
            
            for i in range(len(ocr_data['text'])):
                word = ocr_data['text'][i].strip()
                conf = float(ocr_data['conf'][i])
                
                if word and conf > -1:  # Skip empty words and invalid confidence
                    text_parts.append(word)
                    total_confidence += conf
                    word_count += 1
                    if conf < 60:  # Track low confidence words
                        low_conf_words += 1
            
            # Calculate statistics
            avg_confidence = total_confidence / word_count if word_count > 0 else 0
            low_conf_ratio = low_conf_words / word_count if word_count > 0 else 1
            
            # Store OCR statistics
            self.last_ocr_stats = {
                'word_count': word_count,
                'average_confidence': f"{avg_confidence:.2f}%",
                'low_confidence_words': low_conf_words,
                'low_confidence_ratio': f"{low_conf_ratio:.2%}",
                'tesseract_config': self.tesseract_config
            }
            
            # Join text parts with proper spacing
            text = ' '.join(text_parts)
            
            # Clean up the text
            text = text.strip()
            
            # Remove non-ASCII characters and normalize whitespace
            text = ''.join(c if ord(c) < 128 else ' ' for c in text)
            text = ' '.join(text.split())
            
            logger.info(f"Extracted {len(text)} characters of text with {avg_confidence:.1f}% average confidence")
            logger.debug(f"OCR Stats: {word_count} words, {low_conf_words} low confidence words ({low_conf_ratio:.1%})")
            
            return text
            
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            self.last_ocr_stats = {
                'error': str(e),
                'word_count': 0,
                'average_confidence': '0%',
                'low_confidence_words': 0,
                'low_confidence_ratio': '100%',
                'tesseract_config': self.tesseract_config
            }
            return ""
    
    def save_image(self, image: np.ndarray, path: str) -> bool:
        """
        Save an image to disk.
        
        Args:
            image: Image as numpy array
            path: Path to save the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cv2.imwrite(path, image)
            logger.debug(f"Saved image to {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving image to {path}: {str(e)}")
            return False 