import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import re
import os
import dateutil.parser
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any, Union
from collections import defaultdict
import logging
import time
from PIL import ImageEnhance
import traceback
import tempfile
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ReceiptAnalyzer:
    # Keywords to ignore as they're not actual items
    SUMMARY_KEYWORDS = ['subtotal', 'sub total', 'sub-total', 'tax', 'total', 'balance', 'amount due', 'change']
    
    # Keywords that might indicate a discount
    DISCOUNT_KEYWORDS = ['discount', 'coupon', 'savings', 'member', 'sale', 'promo']
    
    # Payment method keywords
    PAYMENT_METHODS = {
        'credit': ['credit', 'visa', 'mastercard', 'amex', 'american express', 'discover'],
        'debit': ['debit', 'check card'],
        'cash': ['cash', 'change'],
        'gift card': ['gift card', 'gift certificate'],
        'paypal': ['paypal', 'pp'],
        'apple pay': ['apple pay', 'applepay'],
        'g pay': ['google pay', 'googlepay', 'g pay']
    }
    
    # Currency symbols
    CURRENCY_SYMBOLS = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        'CA$': 'CAD',
        'A$': 'AUD'
    }
    
    # Debug mode flag
    DEBUG_MODE = True
    
    # Store-specific patterns and formatters
    STORE_PATTERNS = {
        'costco': {
            'name_variations': ['costco', 'costco wholesale'],
            'price_pattern': r'(\d+\.\d{2})\s*[Ff]',
            'item_pattern': r'(?:\d{6,8}|[A-Z0-9]{7,10})?\s*([\w\s\-]+)\s+(\d+\.\d{2})\s*[Ff]?',
            'subtotal_pattern': r'(?i)(?:sub\s*total|subtotal)[^\n]*?(\d+\.\d{2})',
            'tax_pattern': r'(?i)tax[^\n]*?(\d+\.\d{2})',
            'total_pattern': r'(?i)(?:\*{3,})?\s*total[^\n]*?(\d+\.\d{2})',
            'currency': 'USD'
        }
    }
    
    @staticmethod
    def preprocess_image(image_bytes: bytes, disable_deskew=False, disable_enhancements=False) -> np.ndarray:
        """
        Preprocess receipt image for better OCR results.
        
        Args:
            image_bytes: Raw image bytes
            disable_deskew: Skip deskewing which can sometimes damage image readability
            disable_enhancements: Skip contrast enhancements which can sometimes damage image readability
            
        Returns:
            Preprocessed image as numpy array
        """
        # Read image from bytes
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        
        # Convert to proper format
        if len(image_np.shape) == 2:
            # Already grayscale
            gray = image_np
        elif len(image_np.shape) == 3:
            # Convert color image to grayscale
            if image_np.shape[2] == 4:  # RGBA
                # Convert RGBA to RGB
                image_np = cv2.cvtColor(image_np, cv2.COLOR_RGBA2RGB)
            gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        else:
            raise ValueError(f"Unexpected image shape: {image_np.shape}")
        
        # Print debug info
        if ReceiptAnalyzer.DEBUG_MODE:
            print(f"Original image dimensions: {image_np.shape[1]}x{image_np.shape[0]}")
            
        # Resize if the image is too large (helps performance and improves OCR)
        max_dim = 1500
        h, w = gray.shape
        if max(h, w) > max_dim:
            scaling_factor = max_dim / max(h, w)
            new_w, new_h = int(w * scaling_factor), int(h * scaling_factor)
            gray = cv2.resize(gray, (new_w, new_h))
            if ReceiptAnalyzer.DEBUG_MODE:
                print(f"Resized image to {new_w}x{new_h}")
        
        # Save original before processing for comparison
        original_for_compare = gray.copy()
        
        # Only apply enhancements if not disabled
        if not disable_enhancements:
            try:
                # Apply bilateral filter to reduce noise while preserving edges
                gray = cv2.bilateralFilter(gray, 9, 75, 75)
                
                # Get histogram of image
                hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
                
                # Get min and max values from 5% to 95% of histogram to avoid outliers
                min_val = 0
                max_val = 255
                cum_sum = 0
                total_pixels = gray.shape[0] * gray.shape[1]
                
                # Find 5th percentile for min_val
                for i in range(256):
                    cum_sum += hist[i][0]
                    if cum_sum >= total_pixels * 0.05:
                        min_val = i
                        break
                
                # Find 95th percentile for max_val
                cum_sum = 0
                for i in range(255, -1, -1):
                    cum_sum += hist[i][0]
                    if cum_sum >= total_pixels * 0.05:
                        max_val = i
                        break
                
                if ReceiptAnalyzer.DEBUG_MODE:
                    print(f"Applying contrast enhancement, range: {min_val}-{max_val}")
                
                # Apply contrast enhancement if the range is meaningful
                if max_val > min_val + 20:
                    gray = cv2.normalize(gray, None, min_val, max_val, cv2.NORM_MINMAX)
                
                # Apply adaptive thresholding
                gray = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 9)
                
                # Check if the image is inverted (white text on black background)
                # by counting black vs white pixels
                black_pixels = np.sum(gray == 0)
                white_pixels = np.sum(gray == 255)
                if black_pixels > white_pixels:
                    # Invert the image if it has more black than white
                    gray = cv2.bitwise_not(gray)
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print("Inverted image (detected white text on black background)")
                
                # Simple denoising
                kernel = np.ones((1, 1), np.uint8)
                gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            except Exception as e:
                print(f"Warning: Error during image enhancement: {str(e)}")
                # On error, revert to original
                gray = original_for_compare
        
        # Deskew if needed and not disabled
        if not disable_deskew:
            try:
                # Calculate skew angle
                angle = ReceiptAnalyzer._get_skew_angle(gray)
                
                # Only deskew if angle is significant
                if abs(angle) > 1.0 and abs(angle) < 30.0:
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print(f"Deskewing image by {angle:.2f} degrees")
                    gray = ReceiptAnalyzer._deskew(gray, angle)
                elif abs(angle) >= 30.0:
                    # Extreme angles are usually detection errors - log but don't apply
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print(f"Skipping extreme deskew angle: {angle:.2f} degrees")
            except Exception as e:
                print(f"Warning: Error during deskew: {str(e)}")
        
        # Save processed image for debugging
        if ReceiptAnalyzer.DEBUG_MODE:
            cv2.imwrite("debug_processed_image.png", gray)
            print("Saved processed image for debugging to debug_processed_image.png")
            
            # Also save the original grayscale for comparison
            cv2.imwrite("debug_original_image.png", original_for_compare)
            print("Saved original grayscale image for debugging to debug_original_image.png")
        
        return gray
    
    @staticmethod
    def _get_skew_angle(image: np.ndarray) -> float:
        """Detect the skew angle of the image."""
        # Apply edge detection
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        
        # Use Hough Line Transform to detect lines
        lines = cv2.HoughLines(edges, 1, np.pi/180, 100)
        
        if lines is None:
            return 0.0
            
        # Calculate the skew angle
        angles = []
        for line in lines:
            rho, theta = line[0]
            if theta < np.pi/4 or theta > 3*np.pi/4:  # Only consider vertical lines
                angles.append(theta)
                
        if not angles:
            return 0.0
            
        median_angle = np.median(angles)
        skew_angle = np.degrees(median_angle - np.pi/2)
        return skew_angle
    
    @staticmethod
    def _deskew(image: np.ndarray, angle: float) -> np.ndarray:
        """Rotate the image to correct skew."""
        # Get image dimensions
        height, width = image.shape[:2]
        
        # Calculate the rotation matrix
        center = (width // 2, height // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Apply the rotation
        return cv2.warpAffine(image, M, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def extract_text(image: np.ndarray, tesseract_config: str = '') -> str:
        """
        Extract text from image using Tesseract OCR.
        
        Args:
            image: Preprocessed image as numpy array
            tesseract_config: Additional Tesseract configuration
            
        Returns:
            Extracted text
        """
        # Define a character whitelist including letters, numbers, and common symbols
        # Note: We use double backslashes to escape the quote characters properly
        char_whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:$%&()=?@#+-*/\\\'\\\"\\ "
        
        # Configure Tesseract
        custom_config = f'--oem 3 --psm 6'
        if tesseract_config:
            custom_config += f' {tesseract_config}'
        
        # Extract text
        try:
            # First try with char whitelist
            try:
                config_with_whitelist = f'{custom_config} -c tessedit_char_whitelist="{char_whitelist}"'
                ocr_text = pytesseract.image_to_string(image, config=config_with_whitelist)
            except Exception as whitelist_error:
                print(f"Error with char whitelist: {str(whitelist_error)}, falling back to basic config")
                # Fall back to basic config if whitelist causes problems
                ocr_text = pytesseract.image_to_string(image, config=custom_config)
            
            # Basic post-processing to fix common OCR errors
            ocr_text = ocr_text.replace('|', '1')  # Fix pipe symbol as 1
            ocr_text = ocr_text.replace('l', '1')  # Fix lowercase L as 1 when next to numbers
            ocr_text = ocr_text.replace('S', '5')  # Fix S as 5 when in number context
            
            # Remove excessive whitespace and normalize line breaks
            ocr_text = '\n'.join([line.strip() for line in ocr_text.splitlines() if line.strip()])
            
            # Debug: Print sample of extracted text
            if ReceiptAnalyzer.DEBUG_MODE:
                print("\n----- EXTRACTED TEXT SAMPLE (first 10 lines) -----")
                lines = ocr_text.splitlines()
                for i, line in enumerate(lines[:min(10, len(lines))]):
                    print(f"{i+1}: {line}")
                print(f"... ({len(lines)} lines total)")
            
            return ocr_text
        except Exception as e:
            print(f"OCR extraction error: {str(e)}")
            # Return empty string on error but ensure we log it
            return ""
    
    @staticmethod
    def extract_text_with_layout(image: np.ndarray) -> List[Dict[str, Any]]:
        """Extract text with bounding box and confidence data."""
        # Convert numpy array to PIL Image
        pil_image = Image.fromarray(image)
        
        # Extract text using pytesseract with data about layout
        custom_config = r'--oem 3 --psm 6 -l eng'
        data = pytesseract.image_to_data(pil_image, config=custom_config, output_type=pytesseract.Output.DICT)
        
        # Combine text into lines based on bounding box positioning
        lines = ReceiptAnalyzer._group_text_into_lines(data)
        return lines
    
    @staticmethod
    def _group_text_into_lines(ocr_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Group OCR results into lines based on y-coordinates."""
        line_items = []
        current_line = None
        current_y = -1
        
        # Maximum y-coordinate difference to consider texts on the same line
        y_threshold = 5
        
        # Group by line
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            # Skip empty text
            if not ocr_data['text'][i].strip():
                continue
                
            # Get the bounding box and text
            text = ocr_data['text'][i]
            conf = ocr_data['conf'][i]
            x = ocr_data['left'][i]
            y = ocr_data['top'][i]
            w = ocr_data['width'][i]
            h = ocr_data['height'][i]
            
            # Check if this is part of the current line or a new line
            if current_y == -1 or abs(y - current_y) > y_threshold:
                # Save the current line if it exists
                if current_line:
                    line_items.append(current_line)
                    
                # Start a new line
                current_line = {
                    'text': text,
                    'x': x,
                    'y': y,
                    'width': w,
                    'height': h,
                    'conf': conf
                }
                current_y = y
            else:
                # Add to current line
                current_line['text'] += ' ' + text
                current_line['width'] = (x + w) - current_line['x']
                
        # Add the last line
        if current_line:
            line_items.append(current_line)
            
        return line_items
    
    @staticmethod
    def _extract_currency(text: str, store_name: Optional[str] = None) -> Optional[str]:
        """
        Extract currency information from receipt text.
        
        Args:
            text: Raw text from receipt
            store_name: Optional store name for better currency detection
            
        Returns:
            Currency code (e.g., 'USD', 'EUR', 'GBP') or None if not found
        """
        # Store-based currency detection
        if store_name:
            store_name_lower = store_name.lower()
            if 'costco' in store_name_lower:
                return 'USD'
            if any(uk_store in store_name_lower for uk_store in ['tesco', 'sainsbury', 'asda', 'morrisons', 'waitrose']):
                return 'GBP'
        
        # Check for currency symbols
        if '£' in text or 'GBP' in text:
            return 'GBP'
        if '€' in text or 'EUR' in text:
            return 'EUR'
        if '$' in text:
            # Check for CAD or AUD specific indicators
            if 'CAD' in text or 'canada' in text.lower():
                return 'CAD'
            if 'AUD' in text or 'australia' in text.lower():
                return 'AUD'
            # Default to USD for $ symbol
            return 'USD'
        if '¥' in text or 'JPY' in text:
            return 'JPY'
        
        # Check for currency words
        if re.search(r'\bdollar', text.lower()):
            return 'USD'
        if re.search(r'\beuro', text.lower()):
            return 'EUR'
        if re.search(r'\bpound', text.lower()):
            return 'GBP'
        if re.search(r'\byen', text.lower()):
            return 'JPY'
        
        # Default to USD
        return 'USD'
    
    @staticmethod
    def extract_receipt_totals(text: str) -> Dict[str, Optional[float]]:
        """
        Extract subtotal, tax, and total amount from receipt text.
        
        Returns:
            Dictionary with keys 'subtotal', 'tax', and 'total' if found
        """
        # Initialize result
        result = {
            'subtotal': None,
            'tax': None,
            'total': None,
            'currency': None,
            'payment_method': None,
            'date': None,
            'store_name': None,
            'confidence_scores': {}
        }
        
        # Split text into lines for easier analysis
        lines = text.split('\n')
        
        # Try to identify store first to use store-specific patterns
        store_name = ReceiptAnalyzer._extract_store_name(lines)
        result['store_name'] = store_name
        
        # Extract currency
        currency = ReceiptAnalyzer._extract_currency(text)
        if currency:
            result['currency'] = currency
            result['confidence_scores']['currency'] = 0.7
        
        # Check if we have store-specific patterns
        store_key = None
        if store_name:
            store_name_lower = store_name.lower() if store_name else ""
            for key, store_data in ReceiptAnalyzer.STORE_PATTERNS.items():
                if any(variation in store_name_lower for variation in store_data['name_variations']):
                    store_key = key
                    # Set currency from store-specific data
                    result['currency'] = store_data['currency']
                    result['confidence_scores']['currency'] = 0.9
                    break
        
        # Define patterns based on the detected currency
        currency_sym = '£' if result['currency'] == 'GBP' else '\$'
        if result['currency'] == 'EUR':
            currency_sym = '€|[Ee]'
        
        # Regular expressions for finding typical receipt total lines
        if store_key and store_key in ReceiptAnalyzer.STORE_PATTERNS:
            # Use store-specific patterns
            store_data = ReceiptAnalyzer.STORE_PATTERNS[store_key]
            subtotal_pattern = store_data['subtotal_pattern']
            tax_pattern = store_data['tax_pattern']
            total_pattern = store_data['total_pattern']
        else:
            # Use default patterns adapted for the detected currency
            subtotal_pattern = fr'(?i)(?:sub[ -]?total|subtotal)[^\n]*?{currency_sym}?\s*(\d+[\.,]\d{{2}})'
            tax_pattern = fr'(?i)(?:tax|vat|sales tax)[^\n]*?{currency_sym}?\s*(\d+[\.,]\d{{2}})'
            total_pattern = fr'(?i)(?:total|balance|amount due|grand total)[^\n]*?{currency_sym}?\s*(\d+[\.,]\d{{2}})'
        
        # Find subtotal
        subtotal_match = re.search(subtotal_pattern, text)
        if subtotal_match:
            try:
                subtotal_str = subtotal_match.group(1).replace(',', '.')
                result['subtotal'] = float(subtotal_str)
                result['confidence_scores']['subtotal'] = 0.8
            except (ValueError, IndexError):
                pass
        
        # Also try alternative patterns for international receipts
        if result['subtotal'] is None:
            # Try looking for patterns like "Subtotal 12.34" without currency symbol
            alt_subtotal_pattern = r'(?i)(?:sub[ -]?total|subtotal)[\s:]*(\d+[\.,]\d{2})'
            subtotal_match = re.search(alt_subtotal_pattern, text)
        if subtotal_match:
                try:
                    subtotal_str = subtotal_match.group(1).replace(',', '.')
                    result['subtotal'] = float(subtotal_str)
                    result['confidence_scores']['subtotal'] = 0.7
                except (ValueError, IndexError):
                    pass
        
        # Find tax/VAT amount
        tax_match = re.search(tax_pattern, text)
        if tax_match:
            try:
                tax_str = tax_match.group(1).replace(',', '.')
                result['tax'] = float(tax_str)
                result['confidence_scores']['tax'] = 0.8
            except (ValueError, IndexError):
                pass
        
        # Also try alternative tax patterns for international receipts
        if result['tax'] is None:
            # In UK/EU, look for VAT
            vat_pattern = r'(?i)(?:VAT|V\.A\.T\.)[\s:]*(\d+[\.,]\d{2})'
            vat_match = re.search(vat_pattern, text)
            if vat_match:
                try:
                    tax_str = vat_match.group(1).replace(',', '.')
                    result['tax'] = float(tax_str)
                    result['confidence_scores']['tax'] = 0.7
                except (ValueError, IndexError):
                    pass
        
        # Find total amount 
        total_match = re.search(total_pattern, text)
        if total_match:
            try:
                total_str = total_match.group(1).replace(',', '.')
                result['total'] = float(total_str)
                result['confidence_scores']['total'] = 0.8
            except (ValueError, IndexError):
                pass
        
        # Try more aggressive patterns for total if we didn't find it
        if result['total'] is None:
            # Try looking for patterns like "TOTAL: 12.34" or just "12.34" near the word "total"
            for line in lines:
                line_lower = line.lower()
                if 'total' in line_lower and not any(w in line_lower for w in ['subtotal', 'sub-total', 'sub total']):
                    # Extract all numbers with decimal points
                    amount_matches = re.findall(r'(\d+[\.,]\d{2})', line)
                    if amount_matches:
                        # Use the last match, as total is typically the last number in the line
                        try:
                            total_str = amount_matches[-1].replace(',', '.')
                            result['total'] = float(total_str)
                            result['confidence_scores']['total'] = 0.6
                            break
                        except ValueError:
                            pass
        
        # Extract payment method
        result['payment_method'] = ReceiptAnalyzer._extract_payment_method(text)
        
        # Extract date
        result['date'] = ReceiptAnalyzer._extract_date(text)
        
        return result
    
    @staticmethod
    def _extract_payment_method(text: str) -> Optional[str]:
        """Extract payment method from the text."""
        text_lower = text.lower()
        
        # Check for payment method keywords
        for method, keywords in ReceiptAnalyzer.PAYMENT_METHODS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return method
        
        return None
    
    @staticmethod
    def _extract_date(text: str) -> Optional[datetime]:
        """Extract date from the text."""
        # Common date patterns
        date_patterns = [
            r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YYYY or DD/MM/YYYY
            r'(\d{1,2}-\d{1,2}-\d{2,4})',  # MM-DD-YYYY or DD-MM-YYYY
            r'(\d{1,2}\.\d{1,2}\.\d{2,4})',  # MM.DD.YYYY or DD.MM.YYYY
            r'([A-Za-z]{3,9} \d{1,2},? \d{4})'  # Month DD, YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    date_str = match.group(1)
                    return dateutil.parser.parse(date_str)
                except Exception:
                    continue
        
        return None
    
    @staticmethod
    def _extract_store_name(lines: List[str]) -> Optional[str]:
        """Attempt to extract the store name from receipt text."""
        # Common store names to check for
        common_stores = {
            'costco': ['costco', 'wholesale', 'costco wholesale', 'costco whse', '===wholesale', '====wholesale', 'wholesale===', 'wholesale===='],
            'trader joe': ['trader', 'joe', "trader joe's", 'trader joes', 'tj'],
            'walmart': ['walmart', 'wal-mart', 'wal mart', 'walmart supercenter'],
            'target': ['target', 'target store'],
            'safeway': ['safeway'],
            'kroger': ['kroger'],
            'whole foods': ['whole foods', 'whole foods market', 'wfm'],
            'cvs': ['cvs', 'cvs pharmacy', 'cvs/pharmacy'],
            'walgreens': ['walgreens'],
            'h mart': ['h mart', 'h-mart', 'hmart'],
            'key food': ['key food', 'keyfood'],
            'aldi': ['aldi'],
            'publix': ['publix', 'publix super markets'],
            'meijer': ['meijer'],
            'stop & shop': ['stop & shop', 'stop and shop'],
            'wegmans': ['wegmans'],
            'giant': ['giant', 'giant food'],
            'food lion': ['food lion'],
            'harris teeter': ['harris teeter'],
            'heb': ['heb', 'h-e-b', 'h e b'],
            'albertsons': ['albertsons'],
            'vons': ['vons'],
            'ralphs': ['ralphs'],
            'shoprite': ['shoprite', 'shop rite'],
            'starbucks': ['starbucks', 'starbucks coffee'],
            'mcdonalds': ['mcdonalds', 'mcdonald\'s', 'mcd'],
            'subway': ['subway'],
            'chipotle': ['chipotle', 'chipotle mexican grill'],
            'taco bell': ['taco bell'],
            'dunkin': ['dunkin', 'dunkin\' donuts', 'dunkin donuts'],
            'petco': ['petco'],
            'petsmart': ['petsmart'],
            'office depot': ['office depot', 'officedepot'],
            'staples': ['staples'],
            'best buy': ['best buy', 'bestbuy'],
            'home depot': ['home depot', 'the home depot'],
            'lowes': ['lowes', 'lowe\'s'],
            'ikea': ['ikea']
        }
        
        # Log the first few lines for debugging
        if ReceiptAnalyzer.DEBUG_MODE:
            debug_lines = lines[:3] if len(lines) >= 3 else lines
            print(f"DEBUG: First lines for store detection: {debug_lines}")
        
        # Special case for Costco - check for patterns unique to Costco receipts
        all_text = ' '.join(lines).lower()
        # Check for "===WHOLESALE" pattern common in Costco receipts
        if re.search(r'={2,}wholesale|wholesale={2,}', all_text.replace(' ', '')) or "===" in all_text and "wholesale" in all_text:
            if ReceiptAnalyzer.DEBUG_MODE:
                print(f"DEBUG: Identified Costco from ===WHOLESALE pattern")
            return "Costco"
            
        # Check for "member" followed by a member number (Costco membership format)
        if re.search(r'(?:member|membership)\s*(?:number|#|no)?\s*\d{6,}', all_text):
            if ReceiptAnalyzer.DEBUG_MODE:
                print(f"DEBUG: Identified Costco from membership number pattern")
            return "Costco"
        
        # First pass: Check for exact store matches anywhere in the text
        for store_name, variations in common_stores.items():
            for variation in variations:
                # Check for whole word match with word boundaries
                pattern = r'\b' + re.escape(variation) + r'\b'
                if re.search(pattern, all_text):
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print(f"DEBUG: Found store name match: {store_name} (from '{variation}')")
                    return store_name.title()
        
        # Store name is typically in the first few lines
        potential_lines = lines[:15] if len(lines) > 15 else lines
        
        # Remove empty lines and lines with just special characters
        potential_lines = [line.strip() for line in potential_lines if line.strip()]
        potential_lines = [line for line in potential_lines if re.search(r'[a-zA-Z]', line)]
        
        if not potential_lines:
            if ReceiptAnalyzer.DEBUG_MODE:
                print("DEBUG: No potential store name lines found")
            return None
            
        # Second pass: Look for partial matches in the first few lines
        for line in potential_lines:
            line_lower = line.lower()
            
            # Special case for specific store patterns
            if "wholesale" in line_lower or "====" in line_lower:
                if ReceiptAnalyzer.DEBUG_MODE:
                    print(f"DEBUG: Found Costco pattern in line: '{line}'")
                return "Costco"
            
            # Special case for Key Food locations in Queens/NYC
            if re.search(r'(queens|queens blvd|sunnyside|queens ny|long island city|astoria|flushing)', line_lower):
                # Check next few lines for hints of Key Food
                for next_line in potential_lines[:5]:
                    if "key food" in next_line.lower() or "keyfood" in next_line.lower():
                        if ReceiptAnalyzer.DEBUG_MODE:
                            print(f"DEBUG: Found Key Food in Queens from location pattern")
                        return "Key Food"
            
            # Additional common Key Food location indicators
            if "46-02 queens" in line_lower or "queens blvd" in line_lower or "sunnyside, ny" in line_lower:
                if ReceiptAnalyzer.DEBUG_MODE:
                    print(f"DEBUG: Identified Key Food from Queens Blvd address")
                return "Key Food"
                
            for store_name, variations in common_stores.items():
                for variation in variations:
                    if variation in line_lower:
                        if ReceiptAnalyzer.DEBUG_MODE:
                            print(f"DEBUG: Found store name in line: {store_name} (from '{line}')")
                        return store_name.title()
        
        # The rest of the method remains unchanged
        # Third pass: Try to find a line that looks like a store name
        # Usually it's all caps, relatively short, and contains only letters and spaces
        for line in potential_lines:
            # Skip lines that are likely addresses or contain excessive punctuation
            if re.search(r'\d{5,}|www\.|\.com|@|#|\$|%|\^|&|\*|\+|=', line):
                continue
                
            # Skip lines that are too short
            if len(line) < 3:
                continue
                
            # Skip lines with backslashes or other problematic characters
            if '\\' in line or '/' in line:
                continue
                
            # Prioritize lines that are all uppercase or title case
            if line.isupper() or line.istitle():
                # Check if this might be a store name (not an address or other text)
                # Store names typically don't contain many spaces or punctuation
                if len(re.findall(r'\s', line)) <= 3 and len(re.findall(r'[^\w\s]', line)) <= 2:
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print(f"DEBUG: Using likely store name: {line}")
                    return line.strip()
        
        # Check for receipt headers that often contain store names
        receipt_headers = [
            r'thank.*shopping.*at\s+(.+?)\s*$',  # "Thank you for shopping at STORE"
            r'welcome\s+to\s+(.+?)\s*$',         # "Welcome to STORE"
            r'store\s*:\s*(.+?)\s*$',            # "Store: STORE"
            r'location\s*:\s*(.+?)\s*$',         # "Location: STORE"
        ]
        
        for line in potential_lines:
            line_lower = line.lower()
            for pattern in receipt_headers:
                match = re.search(pattern, line_lower)
                if match and match.group(1).strip():
                    store_candidate = match.group(1).strip()
                    if ReceiptAnalyzer.DEBUG_MODE:
                        print(f"DEBUG: Found store name from header pattern: {store_candidate}")
                    return store_candidate.title()
        
        # If we still haven't found a good candidate, use the first non-empty line
        for line in potential_lines:
            if line and len(line) >= 3 and len(line) <= 30:
                if ReceiptAnalyzer.DEBUG_MODE:
                    print(f"DEBUG: Using first reasonable line as store name: {line}")
                return line.strip()
                
        # If all else fails, return None
        if ReceiptAnalyzer.DEBUG_MODE:
            print("DEBUG: Failed to identify store name")
        return None

    @staticmethod
    def is_summary_line(line: str) -> bool:
        """Check if a line is a summary line (subtotal, tax, total, etc.)."""
        line_lower = line.lower()
        return any(keyword in line_lower for keyword in ReceiptAnalyzer.SUMMARY_KEYWORDS)
    
    @staticmethod
    def is_likely_discount(item_text: str, amount: float) -> bool:
        """
        Determine if an item is likely a discount based on its description and amount.
        
        Args:
            item_text: The description text of the item
            amount: The amount/price of the item
        
        Returns:
            bool: True if the item is likely a discount, False otherwise
        """
        # Negative amounts are almost always discounts
        if amount < 0:
            return True
        
        # Common discount keywords
        discount_keywords = [
            'discount', 'coupon', 'off', 'save', 'savings', 'member savings',
            'instant savings', 'rebate', 'promo', 'promotion', 'credit',
            'adjustment', 'refund', 'return', 'void', 'cancel'
        ]
        
        # Product patterns that indicate actual items rather than discounts
        product_patterns = [
            r'\d+\s*[xX]\s*\d+', # Dimensions (e.g., 2x4)
            r'\d+\s*[cC][tT]',   # Count (e.g., 24ct)
            r'\d+\s*[pP][kK]',   # Pack (e.g., 6pk)
            r'\d+\s*[oO][zZ]',   # Ounces (e.g., 16oz)
            r'\d+\s*[lL][bB]',   # Pounds (e.g., 2lb)
            r'\d+\s*[gG]',       # Grams (e.g., 500g)
            r'\d+\s*[mM][lL]',   # Milliliters (e.g., 750ml)
        ]
        
        # Check for common discount terms
        lower_text = item_text.lower()
        for keyword in discount_keywords:
            if keyword in lower_text:
                return True
        
        # Check for product patterns (items with these patterns are likely not discounts)
        for pattern in product_patterns:
            if re.search(pattern, item_text):
                return False
        
        # Check for quantity indicators suggesting a product
        if re.search(r'^\d+\s', item_text):  # Starts with a number followed by space
            return False
        
        # Look for capitalized brand names (typical product format)
        if re.search(r'^[A-Z][a-z]+\s', item_text) and not any(k in lower_text for k in discount_keywords):
            return False
        
        # Final heuristic: very short item names are likely regular items unless they contain discount keywords
        if len(item_text.split()) <= 2 and not any(k in lower_text for k in discount_keywords):
            return False
        
        # If none of the above conditions are met, default behavior based on context
        return False
    
    @staticmethod
    def detect_line_type(line: str) -> str:
        """
        Detect the type of line: header, item, summary, or other.
        
        Args:
            line: The line of text
            
        Returns:
            String indicating line type: 'header', 'item', 'summary', or 'other'
        """
        # Check if it's a summary line
        if ReceiptAnalyzer.is_summary_line(line):
            return 'summary'
            
        # Check if it's an item line (has a price)
        # Support both standard price pattern and Costco's format with F suffix
        price_pattern = r'(\$?-?\d+\.\d{2}|(\d+\.\d{2})\s*[Ff])'
        if re.search(price_pattern, line):
            return 'item'
            
        # Check if it's a header line (store name, date, receipt number)
        header_keywords = ['receipt', 'order', 'date', 'time', 'location', 'store', 'tel', 'phone']
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in header_keywords):
            return 'header'
            
        # Default to other
        return 'other'

    @classmethod
    def parse_items(cls, text: str, layout_data: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Parse the extracted text to identify items and their prices with improved layout understanding.
        
        Args:
            text: The OCR text
            layout_data: Optional layout information for better item parsing
            
        Returns:
            List of dictionaries containing item information
        """
        items = []
        
        # Try to identify store for store-specific parsing
        lines = text.split('\n')
        store_name = cls._extract_store_name(lines)
        
        # Use layout data if available for improved parsing
        if layout_data:
            return cls._parse_items_with_layout(layout_data, store_name)
            
        # Regular expressions for price matching
        price_pattern = r'\$?(-?\d+\.\d{2})'
        quantity_pattern = r'^(\d+)\s*[xX]'  # Pattern for quantities like "2 x Item"
        
        # Handle Costco-specific patterns
        is_costco = False
        if store_name and 'costco' in store_name.lower():
            is_costco = True
            price_pattern = r'(\d+\.\d{2})\s*[Ff]'
        
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
                
            # Skip summary lines
            if cls.is_summary_line(line):
                continue
                
            # For Costco receipts, try to match their specific item format
            if is_costco:
                # Costco format: [E] [item code] [ITEM NAME] [price] F
                costco_item_pattern = r'(?:[E]\s+)?(?:\d{6,8}|[A-Z0-9]{7,10})?\s*([\w\s\-\.\/]+)\s+(\d+\.\d{2})\s*[Ff]?'
                costco_match = re.search(costco_item_pattern, line)
                
                if costco_match:
                    try:
                        description = costco_match.group(1).strip()
                        price = float(costco_match.group(2))
                        
                        # Skip likely discount lines
                        if cls.is_likely_discount(description, price):
                            continue
                        
                        if description:  # Only add if we have a description
                            item_data = {
                                "description": description,
                                "amount": price,
                                "confidence_score": 0.85,  # Higher confidence for formatted match
                                "quantity": None,
                                "unit_price": None,
                                "item_type": "product"  # Default type
                            }
                            items.append(item_data)
                    except (ValueError, IndexError):
                        continue
            else:
                # Standard item parsing for non-Costco receipts
                price_match = re.search(price_pattern, line)
                if price_match:
                    price_str = price_match.group(1).replace('$', '')
                    try:
                        price = float(price_str)
                        # Get item description (everything before the price)
                        description = line[:price_match.start()].strip()
                        
                        # Skip likely discount lines
                        if cls.is_likely_discount(description, price):
                            continue
                        
                        # Check for quantity
                        quantity = 1.0
                        quantity_match = re.search(quantity_pattern, description)
                        if quantity_match:
                            try:
                                quantity = float(quantity_match.group(1))
                                # Remove quantity from description
                                description = re.sub(quantity_pattern, '', description).strip()
                            except ValueError:
                                pass
                            
                        # Calculate unit price
                        unit_price = price / quantity if quantity > 0 else price
                        
                        if description:  # Only add if we have a description
                            item_data = {
                                "description": description,
                                "amount": price,
                                "confidence_score": 0.8,  # Default confidence
                                "quantity": quantity if quantity > 1 else None,
                                "unit_price": unit_price if quantity > 1 else None,
                                "item_type": "product"  # Default type
                            }
                            items.append(item_data)
                    except ValueError:
                        continue
        
        return items
    
    @classmethod
    def _parse_items_with_layout(cls, layout_data: List[Dict[str, Any]], store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parse items using layout information for better accuracy.
        
        Args:
            layout_data: Layout information from OCR
            store_name: Optional store name for store-specific parsing
            
        Returns:
            List of dictionaries containing item information
        """
        items = []
        
        # Check if this is a Costco receipt
        is_costco = store_name and 'costco' in store_name.lower()
        
        # Group lines by type to identify item section
        line_types = {}
        for i, line_data in enumerate(layout_data):
            line_type = cls.detect_line_type(line_data['text'])
            line_types[i] = line_type
        
        # Find regions in the receipt
        header_region = []
        item_region = []
        summary_region = []
        
        # Identify contiguous regions
        current_region = 'header'
        for i, line_type in sorted(line_types.items()):
            if current_region == 'header':
                if line_type == 'item':
                    current_region = 'item'
                    item_region.append(i)
                else:
                    header_region.append(i)
            elif current_region == 'item':
                if line_type == 'summary':
                    current_region = 'summary'
                    summary_region.append(i)
                elif line_type == 'item':
                    item_region.append(i)
            elif current_region == 'summary':
                summary_region.append(i)
        
        # Process lines in the item region
        price_pattern = r'\$?(-?\d+\.\d{2})'
        quantity_pattern = r'^(\d+)\s*[xX]'
        
        # For Costco receipts, use their specific item pattern
        if is_costco:
            price_pattern = r'(\d+\.\d{2})\s*[Ff]'
            costco_item_pattern = r'(?:[E]\s+)?(?:\d{6,8}|[A-Z0-9]{7,10})?\s*([\w\s\-\.\/]+)\s+(\d+\.\d{2})\s*[Ff]?'
        
        for idx in item_region:
            line = layout_data[idx]['text']
            confidence = layout_data[idx]['conf']
            
            if is_costco:
                # Try Costco-specific pattern first
                costco_match = re.search(costco_item_pattern, line)
                if costco_match:
                    try:
                        description = costco_match.group(1).strip()
                        price = float(costco_match.group(2))
                        
                        # Check if this is a discount (negative amounts or discount keywords)
                        if cls.is_likely_discount(description, price):
                            item_type = "discount"
                        else:
                            item_type = "product"
                        
                        if description or item_type == "discount":
                            item_data = {
                                "description": description or "Discount",
                                "amount": price,
                                "confidence_score": confidence / 100 if confidence else 0.85,
                                "quantity": None,
                                "unit_price": None,
                                "item_type": item_type,
                                "confidence_scores": {
                                    "description": confidence / 100 if confidence else 0.8,
                                    "amount": 0.9  # Price patterns are usually reliable
                                }
                            }
                            items.append(item_data)
                    except (ValueError, IndexError):
                        continue
            else:
                # Standard item parsing for non-Costco receipts
                price_match = re.search(price_pattern, line)
                if price_match:
                    price_str = price_match.group(1).replace('$', '')
                    try:
                        price = float(price_str)
                        # Get item description (everything before the price)
                        description = line[:price_match.start()].strip()
                        
                        # Skip likely discount lines unless explicitly checking for them
                        if cls.is_likely_discount(description, price):
                            item_type = "discount"
                        else:
                            item_type = "product"
                        
                        # Check for quantity
                        quantity = 1.0
                        quantity_match = re.search(quantity_pattern, description)
                        if quantity_match:
                            try:
                                quantity = float(quantity_match.group(1))
                                # Remove quantity from description
                                description = re.sub(quantity_pattern, '', description).strip()
                            except ValueError:
                                pass
                            
                        # Calculate unit price
                        unit_price = price / quantity if quantity > 0 else price
                        
                        if description or item_type == "discount":  # Allow empty description for discounts
                            item_data = {
                                "description": description or "Discount",
                                "amount": price,
                                "confidence_score": confidence / 100 if confidence else 0.7,
                                "quantity": quantity if quantity > 1 else None,
                                "unit_price": unit_price if quantity > 1 else None,
                                "item_type": item_type,
                                "confidence_scores": {
                                    "description": confidence / 100 if confidence else 0.7,
                                    "amount": 0.9  # Price patterns are usually reliable
                                }
                            }
                            items.append(item_data)
                    except ValueError:
                        continue
        
        return items

    @classmethod
    def parse_items_fallback(cls, receipt_text, store_type=None):
        """
        Extract items from receipt text using aggressive pattern matching.
        
        Args:
            receipt_text (str): The OCR text extracted from a receipt image
            store_type (str, optional): The type of store (e.g., 'costco', 'trader_joes', 'hmart', 'key_food')
            
        Returns:
            list: List of dictionaries with item information
        """
        
        items = []
        seen_descriptions = set()
        
        # Skip lines that contain these
        skip_keywords = [
            'subtotal', 'sub-total', 'sub total', 'total',
            'tax', 'change', 'cash', 'credit', 'debit', 'card',
            'payment', 'balance', 'due', 'cashier', 'clerk',
            'store', 'tel:', 'phone:', 'receipt', 'transaction',
            'date:', 'time:', 'thank you', 'member', 'invoice',
            'coupon', 'savings', 'discount', 'reward', 'loyalty',
            'welcome to', 'www.', 'http', '.com', 'order',
            'terminal', 'approval', 'account', 'customer',
            'purchased', 'items sold', 'original'
        ]
        
        # Define patterns based on store type
        if store_type == 'costco':
            # Costco specific patterns
            # Format: DESCRIPTION followed by price on the same line
            item_patterns = [
                # Item with item number optional, price at end of line
                r'(?:\d+\s+)?([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{5,})\s+(\d+\.\d{2})$',
                
                # Item with item number and quantity (e.g., "2 @ 9.99")
                r'(?:\d+\s+)?([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{5,})\s+\d+\s*@\s*\d+\.\d{2}\s+(\d+\.\d{2})$',
                
                # Item with quantity and price
                r'(?:\d+\s+)?([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{5,})\s+(?:QTY|qty)?[:\s]*(\d+)[xX\s]+(?:@\s*)?(\d+\.\d{2})',
            ]
            
            for pattern in item_patterns:
                matches = re.finditer(pattern, receipt_text, re.MULTILINE)
                for match in matches:
                    line = match.group(0)
                    
                    # Skip if line contains any skip keywords
                    if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                        continue
                    
                    if len(match.groups()) == 2:
                        description, price = match.groups()
                    elif len(match.groups()) == 3:
                        description, quantity, unit_price = match.groups()
                        # Calculate total price
                        price = str(float(quantity) * float(unit_price))
                    else:
                        continue
                    
                    # Clean up description
                    description = description.strip()
                    if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                        continue
                    
                    # Avoid duplicates
                    if description.lower() in seen_descriptions:
                        continue
                    seen_descriptions.add(description.lower())
                    
                    items.append({
                        'description': description,
                        'price': float(price)
                    })
        
        elif store_type == 'trader_joes':
            # Trader Joe's specific patterns
            item_patterns = [
                # Standard TJ format: description followed by price
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
                
                # TJ variation with quantity (e.g. "2 @ 1.99 3.98")
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+\d+\s*@\s*\d+\.\d{2}\s+(\d+\.\d{2})$',
                
                # Description with price separated by dots or spaces
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s*\.+\s*(\d+\.\d{2})$',
            ]
            
            for pattern in item_patterns:
                matches = re.finditer(pattern, receipt_text, re.MULTILINE)
                for match in matches:
                    line = match.group(0)
                    
                    # Skip if line contains any skip keywords
                    if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                        continue
                    
                    description, price = match.groups()
                    
                    # Clean up description
                    description = description.strip()
                    if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                        continue
                    
                    # Avoid duplicates
                    if description.lower() in seen_descriptions:
                        continue
                    seen_descriptions.add(description.lower())
                    
                    items.append({
                        'description': description,
                        'price': float(price)
                    })
        
        elif store_type == 'hmart':
            # H Mart specific patterns
            item_patterns = [
                # Standard format: description followed by price
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
                
                # Format with quantity and price
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+)\s+(?:EA|ea|PK|pk)?\s+(\d+\.\d{2})$',
                
                # Format with quantity, unit price, and total
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+)\s+(?:EA|ea|PK|pk)?\s+(?:@\s+)?(\d+\.\d{2})\s+(\d+\.\d{2})$',
                
                # Price right-aligned (common in H Mart)
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s*\.+\s*(\d+\.\d{2})$',
                
                # Korean/Asian products often have codes/numbers
                r'^(?:\[\w+\])?\s*([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
            ]
            
            for pattern in item_patterns:
                matches = re.finditer(pattern, receipt_text, re.MULTILINE)
                for match in matches:
                    line = match.group(0).strip()
                    
                    # Skip if line contains any skip keywords
                    if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                        continue
                    
                    groups = match.groups()
                    description = groups[0].strip()
                    
                    # Get price based on pattern match
                    if len(groups) == 2:
                        price = groups[1]
                    elif len(groups) == 3:
                        # If format is description, quantity, price
                        price = groups[2]
                    elif len(groups) == 4:
                        # If format is description, quantity, unit price, total
                        price = groups[3]
                    else:
                        continue
                    
                    # Clean up description
                    if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                        continue
                    
                    # Skip if it looks like a header or footer line
                    if re.search(r'^(item|qty|description|price|amount|total|subtotal)$', description, re.IGNORECASE):
                        continue
                    
                    # Avoid duplicates
                    if description.lower() in seen_descriptions:
                        continue
                    seen_descriptions.add(description.lower())
                    
                    items.append({
                        'description': description,
                        'price': float(price)
                    })
                    
        elif store_type == 'key_food':
            # Key Food specific patterns
            item_patterns = [
                # Common Key Food format: description with price at end (separated by space)
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
                
                # Format with spaces or dots between description and price
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s*[\.]+\s*(\d+\.\d{2})$',
                
                # Key Food often uses ALL CAPS for items
                r'^([A-Z][A-Z0-9\s\-\.\,\&\'\(\)\/\+]{2,})\s+(\d+\.\d{2})$',
                
                # Items with quantity indicator
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+)\s+@\s+(\d+\.\d{2})\s+(\d+\.\d{2})$',
                
                # Items with unit price (e.g. "$1.99 /lb")
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+\$?(\d+\.\d{2})\s+\/\w+',
                
                # Items with multiple spaces between description and price
                r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s{2,}(\d+\.\d{2})$',
                
                # Items with SKU or code at beginning
                r'^\#?\d+\s+([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$'
            ]
            
            for pattern in item_patterns:
                matches = re.finditer(pattern, receipt_text, re.MULTILINE)
                for match in matches:
                    line = match.group(0)
                    
                    # Skip if line contains any skip keywords
                    if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                        continue
                    
                    groups = match.groups()
                    description = groups[0].strip()
                    
                    # Get price based on pattern match
                    if len(groups) == 2:
                        price = groups[1]
                    elif len(groups) == 3 and '@' not in line:
                        # If format is description, quantity, price
                        price = groups[2]
                    elif len(groups) == 4 and '@' in line:
                        # If format is description, quantity, unit price, total
                        price = groups[3]
                    else:
                        continue
                    
                    # Clean up description
                    if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                        continue
                    
                    # Skip if it looks like a header or footer line
                    if re.search(r'^(item|qty|description|price|amount|total|subtotal)$', description, re.IGNORECASE):
                        continue
                    
                    # Avoid duplicates
                    if description.lower() in seen_descriptions:
                        continue
                    seen_descriptions.add(description.lower())
                    
                    items.append({
                        'description': description,
                        'price': float(price)
                    })
        
        else:
            # Generic patterns that work for most receipts
            # Format: DESCRIPTION followed by price at end of line
            matches = re.finditer(r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$', receipt_text, re.MULTILINE)
            
            for match in matches:
                line = match.group(0)
                
                # Skip if line contains any skip keywords
                if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                    continue
                
                description, price = match.groups()
                
                # Clean up description
                description = description.strip()
                if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                    continue
                
                # Avoid duplicates
                if description.lower() in seen_descriptions:
                    continue
                seen_descriptions.add(description.lower())
                
                items.append({
                    'description': description,
                    'price': float(price)
                })
        
        # For all store types, look for special generic patterns too
        # Common format: Description with price at end, separated by space
        generic_patterns = [
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+\$?(\d+\.\d{2})$',
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s*\.+\s*\$?(\d+\.\d{2})$'
        ]
        
        for pattern in generic_patterns:
            matches = re.finditer(pattern, receipt_text, re.MULTILINE)
            for match in matches:
                line = match.group(0)
                
                # Skip if line contains any skip keywords
                if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                    continue
                
                description, price = match.groups()
                
                # Clean up description
                description = description.strip()
                if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                    continue
                
                # Avoid duplicates
                if description.lower() in seen_descriptions:
                    continue
                seen_descriptions.add(description.lower())
                
                items.append({
                    'description': description,
                    'price': float(price.replace('$', ''))
                })
        
        print(f"Fallback parsed {len(items)} items")
        return items

    def handle_costco_receipt(self, receipt_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle Costco receipts with specialized logic.
        
        Args:
            receipt_text: OCR text from the receipt
            image_path: Optional path to the receipt image for enhanced processing
            
        Returns:
            Dictionary with extracted data
        """
        import pytesseract
        
        # Initialize result
        result = {
            'store': 'Costco',
            'currency': 'USD',
            'items': [],
            'subtotal': None,
            'tax': None,
            'total': None,
            'date': None,
            'payment_method': None,
            'confidence': 0.7  # Start with base confidence
        }
        
        # Step 1: Try to extract items using fallback method
        items = self.parse_items_fallback(receipt_text, store_type="costco")
        if items:
            result['items'] = items
            result['confidence'] += 0.1
            print(f"Extracted {len(items)} items using Costco fallback parser")
        
        # Step 2: Try to extract totals using fallback method
        totals = self.extract_totals_fallback(receipt_text, store_type="costco")
        if totals.get('subtotal'):
            result['subtotal'] = totals.get('subtotal')
            result['confidence'] += 0.05
        if totals.get('tax'):
            result['tax'] = totals.get('tax')
            result['confidence'] += 0.05
        if totals.get('total'):
            result['total'] = totals.get('total')
            result['confidence'] += 0.05
        if totals.get('payment_method'):
            result['payment_method'] = totals.get('payment_method')
            result['confidence'] += 0.025
        if totals.get('date'):
            result['date'] = totals.get('date')
            result['confidence'] += 0.025
        
        # Step 3: Process receipt text to find the date
        if not result['date']:
            date = self._extract_date(receipt_text)
            if date:
                result['date'] = date
                result['confidence'] += 0.025
        
        # Step 4: Find payment method if not already set
        if not result['payment_method']:
            payment_method = self._extract_payment_method(receipt_text)
            if payment_method:
                result['payment_method'] = payment_method
                result['confidence'] += 0.025
        
        # Step 5: If we still don't have good data, try enhanced OCR
        if not result['items'] or not result['total']:
            if image_path:
                print("Attempting enhanced OCR for Costco receipt")
                try:
                    # Load image and preprocess for OCR
                    processed_image = self.preprocess_image(image_path, debug=True)
                    
                    if processed_image is not None:
                        # Extract text with improved settings
                        enhanced_text = pytesseract.image_to_string(processed_image, config='--psm 6 -l eng')
                        
                        if enhanced_text and len(enhanced_text) > len(receipt_text) * 0.8:
                            print("Using enhanced OCR text")
                            # Try again with enhanced text
                            enhanced_items = self.parse_items_fallback(enhanced_text, store_type="costco")
                            if enhanced_items and (not result['items'] or len(enhanced_items) > len(result['items'])):
                                result['items'] = enhanced_items
                                result['confidence'] += 0.1
                                print(f"Enhanced OCR extracted {len(enhanced_items)} items")
                            
                            enhanced_totals = self.extract_totals_fallback(enhanced_text, store_type="costco")
                            if enhanced_totals.get('total') and not result['total']:
                                result['total'] = enhanced_totals.get('total')
                                result['confidence'] += 0.05
                except Exception as e:
                    print(f"Error in enhanced OCR processing: {str(e)}")
        
        # Step 6: Calculate any missing values
        if result['subtotal'] is not None and result['tax'] is not None and result['total'] is None:
            result['total'] = round(result['subtotal'] + result['tax'], 2)
            result['confidence'] += 0.025
        
        # If we have items but no subtotal, calculate it
        if result['items'] and result['subtotal'] is None:
            result['subtotal'] = round(sum(item.get('amount', 0) for item in result['items']), 2)
            result['confidence'] += 0.025
        
        # If we have subtotal and total but no tax, calculate it
        if result['subtotal'] is not None and result['total'] is not None and result['tax'] is None:
            result['tax'] = round(result['total'] - result['subtotal'], 2)
            if result['tax'] < 0:  # Sanity check
                result['tax'] = None
        else:
                result['confidence'] += 0.025
        
        print(f"Costco handler results: {len(result['items'])} items, Subtotal={result['subtotal']}, Tax={result['tax']}, Total={result['total']}, Confidence={result['confidence']}")
        return result
        
    def handle_trader_joes_receipt(self, receipt_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle Trader Joe's receipts with specialized logic.
        
        Args:
            receipt_text: OCR text from the receipt
            image_path: Optional path to the receipt image for enhanced processing
            
        Returns:
            Dictionary with extracted data
        """
        # Initialize result
        result = {
            'store': "Trader Joe's",
            'currency': 'USD',
            'items': [],
            'subtotal': None,
            'tax': None,
            'total': None,
            'date': None,
            'payment_method': None,
            'confidence': 0.7  # Start with base confidence
        }
        
        # Extract items using specialized Trader Joe's parser
        items = self.parse_trader_joes_items(receipt_text)
        if items:
            result['items'] = items
            result['confidence'] += 0.1
            print(f"Extracted {len(items)} items using Trader Joe's parser")
        
        # Extract totals using fallback method tailored for Trader Joe's
        totals = self.extract_totals_fallback(receipt_text, store_type="trader_joes")
        if totals.get('subtotal'):
            result['subtotal'] = totals.get('subtotal')
            result['confidence'] += 0.05
        if totals.get('tax'):
            result['tax'] = totals.get('tax')
            result['confidence'] += 0.05
        if totals.get('total'):
            result['total'] = totals.get('total')
            result['confidence'] += 0.05
        if totals.get('payment_method'):
            result['payment_method'] = totals.get('payment_method')
            result['confidence'] += 0.025
        if totals.get('date'):
            result['date'] = totals.get('date')
            result['confidence'] += 0.025
            
        # Try to extract the date if not already found
        if not result['date']:
            date = self._extract_date(receipt_text)
            if date:
                result['date'] = date
                result['confidence'] += 0.025
                
        # Try to extract payment method if not already found
        if not result['payment_method']:
            payment_method = self._extract_payment_method(receipt_text)
            if payment_method:
                result['payment_method'] = payment_method
                result['confidence'] += 0.025
        
        # Try enhanced OCR if we don't have good data
        if not result['items'] or not result['total']:
            if image_path and os.path.exists(image_path):
                print("Attempting enhanced OCR for Trader Joe's receipt")
                try:
                    # Load image
                    enhanced_image = cv2.imread(image_path)
                    
                    # Apply additional preprocessing
                    enhanced_image = cv2.cvtColor(enhanced_image, cv2.COLOR_BGR2GRAY)
                    enhanced_image = cv2.adaptiveThreshold(
                        enhanced_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                        cv2.THRESH_BINARY, 11, 2
                    )
                    
                    # Extract text with standard Tesseract
                    enhanced_text = pytesseract.image_to_string(enhanced_image)
                    
                    if enhanced_text and len(enhanced_text) > len(receipt_text) * 0.8:
                        print("Using enhanced OCR text")
                        # Try again with enhanced text
                        enhanced_items = self.parse_trader_joes_items(enhanced_text)
                        if enhanced_items and (not result['items'] or len(enhanced_items) > len(result['items'])):
                            result['items'] = enhanced_items
                            result['confidence'] += 0.1
                            print(f"Enhanced OCR extracted {len(enhanced_items)} items")
                        
                        enhanced_totals = self.extract_totals_fallback(enhanced_text, store_type="trader_joes")
                        if enhanced_totals.get('total') and not result['total']:
                            result['total'] = enhanced_totals.get('total')
                            result['confidence'] += 0.05
                except Exception as e:
                    print(f"Error in enhanced OCR processing: {str(e)}")
        
        # Calculate any missing values
        if result['subtotal'] is not None and result['tax'] is not None and result['total'] is None:
            result['total'] = round(result['subtotal'] + result['tax'], 2)
            result['confidence'] += 0.025
            
        # If we have items but no subtotal, calculate it
        if result['items'] and result['subtotal'] is None:
            result['subtotal'] = round(sum(item.get('price', 0) for item in result['items']), 2)
            result['confidence'] += 0.025
            
        # If we have subtotal and total but no tax, calculate it
        if result['subtotal'] is not None and result['total'] is not None and result['tax'] is None:
            result['tax'] = round(result['total'] - result['subtotal'], 2)
            if result['tax'] < 0:  # Sanity check
                result['tax'] = None
            else:
                result['confidence'] += 0.025
                
        print(f"Trader Joe's handler results: {len(result['items'])} items, Subtotal={result['subtotal']}, Tax={result['tax']}, Total={result['total']}, Confidence={result['confidence']}")
        return result
        
    def analyze_receipt(self, image_path: str) -> Dict[str, Any]:
        """
        Analyze a receipt image and extract all relevant information.
        
        Args:
            image_path: Path to the receipt image file
            
        Returns:
            Dictionary with extracted data including items, totals, etc.
        """
        result = {
            'items': [],
            'currency': 'USD',
            'receipt_totals': {
                'subtotal': None,
                'tax': None,
                'total': None
            },
            'date': None,
            'payment_method': None,
            'store_name': None
        }
        
        # Step 1: Extract text from image
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                
            # Preprocess image
            processed_image = self.preprocess_image(image_data)
            
            # Extract text
            receipt_text = self.extract_text(processed_image)
            if not receipt_text:
                print("Failed to extract text from receipt image")
                return result
                
            # Store raw text for debugging
            result['raw_text'] = receipt_text
            
            # Extract store name
            store_name = self._extract_store_name(receipt_text.split('\n'))
            result['store_name'] = store_name
            
            # Extract currency
            currency = self._extract_currency(receipt_text, store_name)
            if currency:
                result['currency'] = currency
            
            # Step 2: Extract items
            items = self.parse_items_fallback(receipt_text)
            if items:
                result['items'] = items
                print(f"Extracted {len(items)} items from receipt")
            
            # Step 3: Extract totals
            totals = self.extract_totals_fallback(receipt_text, currency=result['currency'])
            if totals:
                result['receipt_totals']['subtotal'] = totals.get('subtotal')
                result['receipt_totals']['tax'] = totals.get('tax')
                result['receipt_totals']['total'] = totals.get('total')
                
                # Update other data if available
                if totals.get('date'):
                    result['date'] = totals.get('date')
                    
                if totals.get('payment_method'):
                    result['payment_method'] = totals.get('payment_method')
            
            # Step 4: Try to extract date if not already found
            if not result['date']:
                date = self._extract_date(receipt_text)
                if date:
                    result['date'] = date
            
            # Step 5: Try to extract payment method if not already found
            if not result['payment_method']:
                payment_method = self._extract_payment_method(receipt_text)
                if payment_method:
                    result['payment_method'] = payment_method
            
            # Step 6: If we have items but no subtotal, calculate it
            if result['items'] and not result['receipt_totals']['subtotal']:
                subtotal = sum(item.get('amount', 0) for item in result['items'])
                result['receipt_totals']['subtotal'] = round(subtotal, 2)
            
            # Step 7: Calculate missing values
            if (result['receipt_totals']['subtotal'] is not None and 
                result['receipt_totals']['tax'] is not None and 
                result['receipt_totals']['total'] is None):
                total = result['receipt_totals']['subtotal'] + result['receipt_totals']['tax']
                result['receipt_totals']['total'] = round(total, 2)
            
            # If we have subtotal and total but no tax
            if (result['receipt_totals']['subtotal'] is not None and 
                result['receipt_totals']['total'] is not None and 
                result['receipt_totals']['tax'] is None):
                tax = result['receipt_totals']['total'] - result['receipt_totals']['subtotal']
                if tax >= 0:  # Sanity check
                    result['receipt_totals']['tax'] = round(tax, 2)
            
            print(f"Analysis complete: {len(result['items'])} items, Subtotal={result['receipt_totals']['subtotal']}, Tax={result['receipt_totals']['tax']}, Total={result['receipt_totals']['total']}")
            return result
            
        except Exception as e:
            print(f"Error analyzing receipt: {str(e)}")
            import traceback
            traceback.print_exc()
            return result

    def handle_hmart_receipt(self, receipt_text, image_path=None):
        """
        Specialized handler for H Mart receipts
        
        Args:
            receipt_text (str): The OCR text from the receipt
            image_path (str, optional): Path to the receipt image
            
        Returns:
            dict: Dictionary with parsed receipt data
        """
        logger.debug("Using specialized H Mart receipt handler")
        
        # Initialize results
        result = {
            'store': 'H Mart',
            'currency': 'USD',
            'items': [],
            'confidence': {
                'overall': 0.7,
                'store': 0.9,
                'items': 0.0,
                'subtotal': 0.0,
                'tax': 0.0,
                'total': 0.0
            }
        }
        
        # Try to extract items using specialized fallback
        items = self.parse_items_fallback(receipt_text, 'hmart')
        if items:
            result['items'] = items
            result['confidence']['items'] = min(0.8, 0.4 + (len(items) * 0.03))
        
        # Try to extract totals
        totals = self.extract_totals_fallback(receipt_text, 'hmart')
        if totals.get('subtotal'):
            result['subtotal'] = totals.get('subtotal')
            result['confidence']['subtotal'] = 0.8
        
        if totals.get('tax'):
            result['tax'] = totals.get('tax')
            result['confidence']['tax'] = 0.8
        
        if totals.get('total'):
            result['total'] = totals.get('total')
            result['confidence']['total'] = 0.8
        
        # Find date and payment method
        date_match = self._extract_date(receipt_text)
        if date_match:
            result['date'] = date_match
        
        payment_method = self._extract_payment_method(receipt_text)
        if payment_method:
            result['payment_method'] = payment_method
        
        # If we have too few items or missing totals, try enhanced OCR
        if (len(result.get('items', [])) < 2 or 
            result.get('subtotal') is None or 
            result.get('total') is None) and image_path:
            
            logger.debug("Using enhanced OCR for H Mart receipt")
            
            # Try different preprocessing parameters
            enhancer = ImageEnhance.Brightness(Image.open(image_path))
            enhanced_image = enhancer.enhance(
                factor=1.5,
                threshold=0.5
            )
            
            # Try OCR again with enhanced image
            enhanced_text = self.extract_text(enhanced_image)
            
            if len(enhanced_text) > len(receipt_text) * 0.7:  # Only use if we got a reasonable amount of text
                # Try extracting items with enhanced text
                enhanced_items = self.parse_items_fallback(enhanced_text, 'hmart')
                if len(enhanced_items) > len(result.get('items', [])):
                    result['items'] = enhanced_items
                    result['confidence']['items'] = min(0.8, 0.4 + (len(enhanced_items) * 0.03))
                
                # Try extracting totals with enhanced text
                enhanced_totals = self.extract_totals_fallback(enhanced_text, 'hmart')
                if not result.get('subtotal') and enhanced_totals.get('subtotal'):
                    result['subtotal'] = enhanced_totals.get('subtotal')
                    result['confidence']['subtotal'] = 0.7
                
                if not result.get('tax') and enhanced_totals.get('tax'):
                    result['tax'] = enhanced_totals.get('tax')
                    result['confidence']['tax'] = 0.7
                
                if not result.get('total') and enhanced_totals.get('total'):
                    result['total'] = enhanced_totals.get('total')
                    result['confidence']['total'] = 0.7
        
        # Calculate missing values
        if result.get('subtotal') and result.get('tax') and not result.get('total'):
            result['total'] = round(result['subtotal'] + result['tax'], 2)
            result['confidence']['total'] = 0.6
        
        elif result.get('subtotal') and result.get('total') and not result.get('tax'):
            calculated_tax = round(result['total'] - result['subtotal'], 2)
            if 0 <= calculated_tax <= result['total'] * 0.15:  # Reasonable tax range
                result['tax'] = calculated_tax
                result['confidence']['tax'] = 0.6
        
        elif result.get('tax') and result.get('total') and not result.get('subtotal'):
            result['subtotal'] = round(result['total'] - result['tax'], 2)
            result['confidence']['subtotal'] = 0.6
        
        # Update overall confidence
        confidence_sum = sum([
            result['confidence'].get('items', 0),
            result['confidence'].get('subtotal', 0),
            result['confidence'].get('tax', 0),
            result['confidence'].get('total', 0)
        ])
        
        if confidence_sum > 0:
            result['confidence']['overall'] = round(confidence_sum / 4, 2)
        
        # Final check of data quality
        if not result.get('items'):
            logger.warning("H Mart handler failed to extract any items")
            result['confidence']['overall'] = max(0.3, result['confidence']['overall'] - 0.3)
        
        if not result.get('total'):
            logger.warning("H Mart handler failed to extract total")
            result['confidence']['overall'] = max(0.3, result['confidence']['overall'] - 0.2)
        
        logger.debug(f"H Mart receipt handler results: {len(result.get('items', []))} items, "
                    f"subtotal: {result.get('subtotal')}, tax: {result.get('tax')}, "
                    f"total: {result.get('total')}, confidence: {result['confidence']['overall']}")
        
        return result

    def handle_key_food_receipt(self, receipt_text, image_path=None):
        """
        Specialized handler for Key Food receipts.
        
        Args:
            receipt_text (str): The OCR text extracted from the receipt
            image_path (str, optional): Path to the receipt image file
        
        Returns:
            dict: Extracted receipt data
        """
        logger.info(f"Processing Key Food receipt using specialized handler")
        
        # Initialize result with default values
        result = {
            'store': 'Key Food',
            'currency': 'USD',
            'items': [],
            'confidence': {
                'items_confidence': 0,
                'totals_confidence': 0,
                'date_confidence': 0,
                'payment_confidence': 0,
                'store_confidence': 0.9  # High confidence since we're in the specialized handler
            }
        }
        
        # Extract items using the fallback method with store type
        extracted_items = self.parse_items_fallback(receipt_text, 'key_food')
        logger.info(f"Extracted {len(extracted_items)} items from Key Food receipt")
        result['items'] = extracted_items
        
        # Extract totals
        totals = self.extract_totals_fallback(receipt_text, 'key_food')
        result['subtotal'] = totals['subtotal']
        result['tax'] = totals['tax']
        result['total'] = totals['total']
        
        # Set confidence based on extracted data
        if len(result['items']) > 0:
            result['confidence']['items_confidence'] = min(0.8, 0.3 + (len(result['items']) * 0.05))
        
        if result['subtotal'] and result['tax'] and result['total']:
            result['confidence']['totals_confidence'] = 0.85
        elif result['total']:
            result['confidence']['totals_confidence'] = 0.7
        
        # Try to find the date
        date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', receipt_text)
        if date_match:
            month, day, year = date_match.groups()
            # Handle 2-digit years
            if len(year) == 2:
                year = '20' + year
            try:
                # Parse and format the date
                date_obj = datetime.datetime(int(year), int(month), int(day))
                result['date'] = date_obj.strftime('%Y-%m-%d')
                result['confidence']['date_confidence'] = 0.8
            except ValueError:
                # If date parsing fails, try alternative format
                try:
                    # Try day/month/year format
                    date_obj = datetime.datetime(int(year), int(day), int(month))
                    result['date'] = date_obj.strftime('%Y-%m-%d')
                    result['confidence']['date_confidence'] = 0.6
                except ValueError:
                    pass
        
        # If date not found with the first pattern, try alternatives
        if 'date' not in result:
            alt_date_patterns = [
                r'DATE\s*[:;]\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
                r'DATE\s*[:;]\s*(\d{1,2})(\d{2})(\d{2,4})',
                r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*\d{1,2}:\d{1,2}',
                r'DATE\s+(\d{1,2})\/(\d{1,2})\/(\d{2,4})',
                r'(\d{2})\/(\d{2})\/(\d{2,4})',
                r'(\d{1,2})\/(\d{1,2})\/(\d{2,4})'
            ]
            
            for pattern in alt_date_patterns:
                date_match = re.search(pattern, receipt_text)
                if date_match:
                    month, day, year = date_match.groups()
                    if len(year) == 2:
                        year = '20' + year
                    try:
                        date_obj = datetime.datetime(int(year), int(month), int(day))
                        result['date'] = date_obj.strftime('%Y-%m-%d')
                        result['confidence']['date_confidence'] = 0.7
                        break
                    except ValueError:
                        continue
        
        # Try to find payment method
        payment_patterns = [
            (r'CREDIT\s+CARD', 'credit_card'),
            (r'DEBIT\s+CARD', 'debit_card'),
            (r'VISA', 'visa'),
            (r'MASTERCARD|MASTER\s+CARD', 'mastercard'),
            (r'AMEX|AMERICAN\s+EXPRESS', 'amex'),
            (r'DISCOVER', 'discover'),
            (r'SNAP|EBT|FOOD\s+STAMPS', 'ebt'),
            (r'CASH', 'cash'),
            (r'APPLE\s+PAY', 'apple_pay'),
            (r'GOOGLE\s+PAY', 'google_pay'),
            (r'CHANGE', 'cash')
        ]
        
        for pattern, payment_type in payment_patterns:
            if re.search(pattern, receipt_text, re.IGNORECASE):
                result['payment_method'] = payment_type
                result['confidence']['payment_confidence'] = 0.8
                break
        
        # If we couldn't determine the payment method from the text, set default
        if 'payment_method' not in result:
            result['payment_method'] = 'unknown'
            result['confidence']['payment_confidence'] = 0.1
        
        # If values are still missing, try to enhance extraction with OCR if image path is provided
        if image_path and (not result['total'] or len(result['items']) < 2):
            logger.info("Using enhanced OCR to improve Key Food receipt extraction")
            try:
                enhanced_text = self.extract_text(image_path, preprocess=True, enhance=True)
                
                # If enhanced text is significantly different, try extracting data again
                if len(enhanced_text) > len(receipt_text) * 1.2:
                    # Try to extract items again
                    enhanced_items = self.parse_items_fallback(enhanced_text, 'key_food')
                    if len(enhanced_items) > len(result['items']):
                        result['items'] = enhanced_items
                        result['confidence']['items_confidence'] = min(0.75, 0.3 + (len(result['items']) * 0.05))
                    
                    # Try to extract totals again
                    enhanced_totals = self.extract_totals_fallback(enhanced_text, 'key_food')
                    if not result['subtotal'] and enhanced_totals['subtotal']:
                        result['subtotal'] = enhanced_totals['subtotal']
                    if not result['tax'] and enhanced_totals['tax']:
                        result['tax'] = enhanced_totals['tax']
                    if not result['total'] and enhanced_totals['total']:
                        result['total'] = enhanced_totals['total']
                    
                    # Update confidence if we found more data
                    if result['subtotal'] and result['tax'] and result['total']:
                        result['confidence']['totals_confidence'] = 0.8
            except Exception as e:
                logger.error(f"Error during enhanced OCR for Key Food receipt: {str(e)}")
        
        # Calculate missing values if possible
        if result['subtotal'] and result['tax'] and not result['total']:
            result['total'] = round(result['subtotal'] + result['tax'], 2)
        elif result['subtotal'] and result['total'] and not result['tax']:
            result['tax'] = round(result['total'] - result['subtotal'], 2)
        elif result['tax'] and result['total'] and not result['subtotal']:
            result['subtotal'] = round(result['total'] - result['tax'], 2)
        
        # Final confidence calculation based on available data
        overall_confidence = sum([
            result['confidence']['items_confidence'],
            result['confidence']['totals_confidence'],
            result['confidence']['date_confidence'],
            result['confidence']['payment_confidence'],
            result['confidence']['store_confidence']
        ]) / 5.0
        
        result['confidence']['overall'] = overall_confidence
        logger.info(f"Key Food receipt processed with overall confidence: {overall_confidence:.2f}")
        
        return result

    def preprocess_image(self, image_path: str, debug: bool = False) -> np.ndarray:
        """
        Preprocess an image for better OCR results.
        
        Args:
            image_path: Path to the image file
            debug: Whether to enable debug logging
            
        Returns:
            Preprocessed image as a numpy array
        """
        try:
            from .image_enhancer import ImageEnhancer
            
            logger.debug(f"Preprocessing image: {image_path}")
            
            # Use our specialized image enhancer
            enhancer = ImageEnhancer(image_path, debug=debug)
            enhanced_image = enhancer.enhance(
                resize=True,
                target_width=2000,
                contrast=1.5,
                brightness=1.2,
                sharpness=1.5
            )
            
            if enhanced_image is not None:
                logger.debug("Image preprocessing successful")
                return enhanced_image
            else:
                logger.warning("Image enhancement failed, falling back to default preprocessing")
        except ImportError:
            logger.warning("ImageEnhancer not found, using default preprocessing")
        except Exception as e:
            logger.error(f"Error in image preprocessing: {str(e)}")
            logger.debug(traceback.format_exc())
        
        # Default preprocessing if enhancer fails or is not available
        try:
            # Read the image
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Failed to read image: {image_path}")
                return None
                
            if debug:
                logger.debug(f"Original image shape: {image.shape}")
            
            # Resize if too large
            height, width = image.shape[:2]
            if width > 2000:
                scale = 2000 / width
                new_height = int(height * scale)
                image = cv2.resize(image, (2000, new_height))
                
                if debug:
                    logger.debug(f"Resized image to 2000x{new_height}")
            
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive threshold
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            return binary
            
        except Exception as e:
            logger.error(f"Error in default image preprocessing: {str(e)}")
            logger.debug(traceback.format_exc())
            
        return None

    def extract_text(self, image_path: str, debug: bool = False) -> str:
        """
        Extract text from an image using OCR.
        
        Args:
            image_path: Path to the image file
            debug: Whether to enable debug logging
            
        Returns:
            Extracted text as a string
        """
        try:
            import pytesseract
            
            start_time = time.time()
            logger.debug(f"Extracting text from image: {image_path}")
            
            # Preprocess the image for better OCR results
            preprocessed_image = self.preprocess_image(image_path, debug=debug)
            
            if preprocessed_image is None:
                logger.error("Image preprocessing failed, attempting OCR on original image")
                extracted_text = pytesseract.image_to_string(Image.open(image_path))
            else:
                # Use Tesseract OCR to extract text with optimized parameters
                custom_config = r'--oem 3 --psm 6 -l eng'
                extracted_text = pytesseract.image_to_string(preprocessed_image, config=custom_config)
            
            # Clean up the text
            extracted_text = self._clean_ocr_text(extracted_text)
            
            execution_time = time.time() - start_time
            logger.debug(f"Text extraction completed in {execution_time:.2f} seconds")
            
            if debug:
                text_length = len(extracted_text)
                logger.debug(f"Extracted {text_length} characters")
                
                # Log a sample of the extracted text
                sample_lines = extracted_text.split('\n')[:5]
                sample = '\n'.join(sample_lines)
                logger.debug(f"Sample of extracted text:\n{sample}")
            
            return extracted_text
            
        except ImportError:
            logger.error("pytesseract not installed, OCR not available")
            return ""
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            logger.debug(traceback.format_exc())
            return ""

    def _clean_ocr_text(self, text: str) -> str:
        """
        Clean up OCR-extracted text to improve quality.
        
        Args:
            text: OCR-extracted text
        
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Replace multiple newlines with a single newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove excessive whitespace
        text = re.sub(r' {2,}', ' ', text)
        
        # Fix common OCR errors
        replacements = {
            'S0': 'SO',
            'SO.': 'SO',
            'O0': 'OO',
            'l.': '1.',
            '|.': '1.',
            '$0.': '$0',
            'S5': 'S5',
            '!': 'I',
            # Add more replacements as needed
        }
        
        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)
        
        # Fix price patterns (e.g., $ 12.99 -> $12.99)
        text = re.sub(r'\$ (\d+\.\d{2})', r'$\1', text)
        
        # Fix common currency errors
        text = re.sub(r'S(\d+\.\d{2})', r'$\1', text)
        
        return text.strip()

    @classmethod
    def extract_totals_fallback(cls, receipt_text, store_type=None):
        """
        Extract total amounts from receipt text using fallback regex patterns.
        
        Args:
            receipt_text (str): The OCR text from the receipt
            store_type (str, optional): The type of store (e.g., 'costco', 'trader_joes', 'hmart', 'key_food')
        
        Returns:
            dict: Dictionary with subtotal, tax, and total values
        """
        result = {
            'subtotal': None,
            'tax': None,
            'total': None
        }
        
        # Store-specific patterns
        if store_type == 'costco':
            # Costco specific patterns
            subtotal_patterns = [
                r'(?:SUB\s*(?:TOTAL|total)|SUBTOTAL|Subtotal)\s*(?:\$)?\s*(\d+\.\d{2})',
                r'(?:TOTAL|Total)\s+BEFORE\s+TAX\s*(?:\$)?\s*(\d+\.\d{2})',
                r'(?:SUB\s*(?:TOTAL|total)|SUBTOTAL|Subtotal)[\s\*]*(\d+\.\d{2})',
            ]
            
            tax_patterns = [
                r'(?:TAX|Tax|SALES\s*TAX|Sales\s*Tax)\s*(?:\$)?\s*(\d+\.\d{2})',
                r'(?:TAX|Tax|SALES\s*TAX|Sales\s*Tax)[\s\*]*(\d+\.\d{2})',
            ]
            
            total_patterns = [
                r'(?:TOTAL|Total)\s*(?:\$)?\s*(\d+\.\d{2})',
                r'(?:TOTAL|Total)\s+PURCHASE\s*(?:\$)?\s*(\d+\.\d{2})',
                r'(?:TOTAL|Total)[\s\*]*(\d+\.\d{2})',
                r'(?:AMOUNT|Amount)\s+(?:DUE|Due)\s*(?:\$)?\s*(\d+\.\d{2})',
            ]
        elif store_type == 'trader_joes':
            # Trader Joe's specific patterns
            subtotal_patterns = [
                r'SUBTOTAL\s*[\$]?(\d+\.\d{2})',
                r'SUB\s*TOTAL\s*[\$]?(\d+\.\d{2})',
                r'SubTotal\s*[\$]?(\d+\.\d{2})',
                r'Sub\s*Total\s*[\$]?(\d+\.\d{2})',
            ]
            
            tax_patterns = [
                r'SALES\s*TAX\s*[\$]?(\d+\.\d{2})',
                r'TAX\s*[\$]?(\d+\.\d{2})',
                r'Tax\s*[\$]?(\d+\.\d{2})',
            ]
            
            total_patterns = [
                r'TOTAL\s*[\$]?(\d+\.\d{2})',
                r'Total\s*[\$]?(\d+\.\d{2})',
                r'BALANCE\s*DUE\s*[\$]?(\d+\.\d{2})',
                r'AMOUNT\s*[\$]?(\d+\.\d{2})',
            ]
        elif store_type == 'hmart':
            # H Mart specific patterns
            subtotal_patterns = [
                r'SUB\s*TOTAL\s*[\$]?(\d+\.\d{2})',
                r'SUBTOTAL\s*[\$]?(\d+\.\d{2})',
                r'Sub\s*Total\s*[\$]?(\d+\.\d{2})',
                r'Purchase\s*Subtotal\s*[\$]?(\d+\.\d{2})',
                r'Amount\s*[\$]?(\d+\.\d{2})\s*Tax\s*[\$]?',  # For when subtotal is before tax
            ]
            
            tax_patterns = [
                r'(?:TAX|Tax|SALES\s*TAX|Sales\s*Tax)\s*[\$]?(\d+\.\d{2})',
                r'(?:TAX|Tax)\s*AMOUNT\s*[\$]?(\d+\.\d{2})',
                r'(?:TAX|Tax)\s*TOTAL\s*[\$]?(\d+\.\d{2})',
                r'(?:TAX|Tax)\s*[\$]?(\d+\.\d{2})',
                r'Amount\s*[\$]?\d+\.\d{2}\s*Tax\s*[\$]?(\d+\.\d{2})',  # For when tax follows subtotal
            ]
            
            total_patterns = [
                r'(?:TOTAL|Total)\s*[\$]?(\d+\.\d{2})',
                r'(?:TOTAL|Total)\s*AMOUNT\s*[\$]?(\d+\.\d{2})',
                r'(?:BALANCE|Balance)\s*(?:DUE|Due)\s*[\$]?(\d+\.\d{2})',
                r'PLEASE\s*PAY\s*[\$]?(\d+\.\d{2})',
                r'AMOUNT\s*TENDERED\s*[\$]?(\d+\.\d{2})',
                r'(?:VISA|AMEX|MASTERCARD|MC|CREDIT|DEBIT)\s*(?:PURCHASE|PAYMENT|SALE)?\s*[\$]?(\d+\.\d{2})',
            ]
        elif store_type == 'key_food':
            # Key Food specific patterns
            subtotal_patterns = [
                r'(?:SUB\s*TOTAL|SUBTOTAL)\s*[\$]?(\d+\.\d{2})',
                r'SUB\-TOTAL\s*[\$]?(\d+\.\d{2})',
                r'SUBTL\s*[\$]?(\d+\.\d{2})',
                r'GOODS\s*SUBTOTAL\s*[\$]?(\d+\.\d{2})',
                r'NET\s*SALE\s*[\$]?(\d+\.\d{2})',
                r'MERCHANDISE\s*SUBTOTAL\s*[\$]?(\d+\.\d{2})',
                r'SUB[\s\.\-]?TOTAL\s*[\.\s]*[\$]?(\d+\.\d{2})',  # Common Key Food format
                r'ITEMS\s*SUBTOTAL\s*[\$]?(\d+\.\d{2})',
                r'ITEM\s*PRICE\s*TOTAL\s*[\$]?(\d+\.\d{2})'
            ]
            
            tax_patterns = [
                r'(?:TAX|TAX AMOUNT|SALES TAX|NYC TAX|NY TAX)\s*[\$]?(\d+\.\d{2})',
                r'(?:TAX|SALES TAX)\s*\(?\d+(?:\.\d+)?\%\)?\s*[\$]?(\d+\.\d{2})',
                r'(?:STATE (?:TAX|TX)|CITY (?:TAX|TX))\s*[\$]?(\d+\.\d{2})',
                r'TAX\s+1\s+[\$]?(\d+\.\d{2})',
                r'(?:TAX|TX)\s*\d*\s*[\$]?(\d+\.\d{2})',  # Tax followed by amount
                r'(?:TAX|TX)[\s\.\-]*[\$]?(\d+\.\d{2})',  # More flexible for Key Food
                r'[Tt][Aa][Xx]\s*[\.\s]*[\$]?(\d+\.\d{2})'  # Case insensitive tax
            ]
            
            total_patterns = [
                r'(?:TOTAL|TOTAL SALE|TOTAL DUE)\s*[\$]?(\d+\.\d{2})',
                r'(?:BALANCE DUE)\s*[\$]?(\d+\.\d{2})',
                r'(?:PURCHASE AMOUNT)\s*[\$]?(\d+\.\d{2})',
                r'(?:PAYMENT AMOUNT)\s*[\$]?(\d+\.\d{2})',
                r'(?:SALE AMOUNT)\s*[\$]?(\d+\.\d{2})',
                r'(?:TENDER AMOUNT)\s*[\$]?(\d+\.\d{2})',
                r'(?:CHARGE AMOUNT)\s*[\$]?(\d+\.\d{2})',
                r'(?:VISA|CREDIT|DEBIT|MASTERCARD|DISCOVER)\s*[\$]?(\d+\.\d{2})',
                r'(?:TOTAL)[\s\.\-]*[\$]?(\d+\.\d{2})',  # More flexible for Key Food
                r'TOTAL[^\n\r]*?[\$]?(\d+\.\d{2})$',  # Total at end of line
                r'AMOUNT\s*DUE[^\n\r]*?[\$]?(\d+\.\d{2})$'  # Amount due at end of line
            ]
        else:
            # Generic patterns
            subtotal_patterns = [
                r'(?:SUB\s*TOTAL|SUBTOTAL|Sub\s*total|Subtotal)\s*[\$]?(\d+\.\d{2})',
                r'(?:SUB\s*TOTAL|SUBTOTAL|Sub\s*total|Subtotal)[:\s]+[\$]?(\d+\.\d{2})',
                r'(?:SUB\s*TOTAL|SUBTOTAL|Sub\s*total|Subtotal)[\s\*]+[\$]?(\d+\.\d{2})'
            ]
            
            tax_patterns = [
                r'(?:TAX|Tax|VAT|SALES\s*TAX|Sales\s*Tax)\s*[\$]?(\d+\.\d{2})',
                r'(?:TAX|Tax|VAT|SALES\s*TAX|Sales\s*Tax)[:\s]+[\$]?(\d+\.\d{2})',
                r'(?:TAX|Tax|VAT|SALES\s*TAX|Sales\s*Tax)[\s\*]+[\$]?(\d+\.\d{2})'
            ]
            
            total_patterns = [
                r'(?:TOTAL|Total)\s*[\$]?(\d+\.\d{2})',
                r'(?:TOTAL|Total)[:\s]+[\$]?(\d+\.\d{2})',
                r'(?:TOTAL|Total)[\s\*]+[\$]?(\d+\.\d{2})',
                r'(?:GRAND\s*TOTAL|Grand\s*Total)\s*[\$]?(\d+\.\d{2})',
                r'(?:AMOUNT\s*DUE|Amount\s*Due)\s*[\$]?(\d+\.\d{2})',
                r'(?:BALANCE\s*DUE|Balance\s*Due)\s*[\$]?(\d+\.\d{2})'
            ]
        
        # Extract subtotal
        for pattern in subtotal_patterns:
            match = re.search(pattern, receipt_text, re.IGNORECASE)
            if match:
                try:
                    result['subtotal'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract tax
        for pattern in tax_patterns:
            match = re.search(pattern, receipt_text, re.IGNORECASE)
            if match:
                try:
                    result['tax'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract total
        for pattern in total_patterns:
            match = re.search(pattern, receipt_text, re.IGNORECASE)
            if match:
                try:
                    result['total'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # If still missing values, try to calculate them
        if result['total'] is not None:
            # If we have subtotal and total but no tax, calculate tax
            if result['subtotal'] is not None and result['tax'] is None:
                tax = round(result['total'] - result['subtotal'], 2)
                if 0 <= tax <= result['total'] * 0.15:  # Reasonable tax range (0-15%)
                    result['tax'] = tax
            
            # If we have tax and total but no subtotal, calculate subtotal
            elif result['tax'] is not None and result['subtotal'] is None:
                subtotal = round(result['total'] - result['tax'], 2)
                if subtotal > 0:
                    result['subtotal'] = subtotal
        
        # If we have subtotal and tax but no total, calculate total
        elif result['subtotal'] is not None and result['tax'] is not None and result['total'] is None:
            result['total'] = round(result['subtotal'] + result['tax'], 2)
        
        print(f"Extracted totals using fallback method: {result}")
        return result

    def parse_trader_joes_items(self, receipt_text: str) -> List[Dict[str, Any]]:
        """
        Specialized method to parse items from Trader Joe's receipts.
        
        Args:
            receipt_text (str): The OCR text from the receipt
            
        Returns:
            List[Dict[str, Any]]: List of items with descriptions and prices
        """
        items = []
        seen_descriptions = set()
        
        # Skip lines that contain these keywords
        skip_keywords = [
            'subtotal', 'sub-total', 'sub total', 'total',
            'tax', 'change', 'cash', 'credit', 'debit', 'card',
            'payment', 'balance', 'due', 'cashier', 'clerk',
            'store', 'tel:', 'phone:', 'receipt', 'transaction',
            'date:', 'time:', 'thank you', 'member', 'invoice',
            'coupon', 'savings', 'discount', 'reward', 'loyalty',
            'welcome to', 'www.', 'http', '.com', 'order',
            'terminal', 'approval', 'account', 'customer',
            'purchased', 'items sold', 'trader', 'joe'
        ]
        
        # Trader Joe's specific patterns
        item_patterns = [
            # Standard TJ format: description followed by price
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
            
            # TJ variation with quantity (e.g. "2 @ 1.99 3.98")
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+\d+\s*@\s*\d+\.\d{2}\s+(\d+\.\d{2})$',
            
            # Description with price separated by dots or spaces
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s*\.+\s*(\d+\.\d{2})$',
            
            # Trader Joe's sometimes has irregular spacing
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s{2,}(\d+\.\d{2})$',
            
            # Trader Joe's organic items often prefixed with "ORG"
            r'^(?:ORG\s+)?([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+(\d+\.\d{2})$',
            
            # Items with weight (common for produce, cheese, etc.)
            r'^([A-Za-z0-9\s\-\.\,\&\'\(\)\/\+]{3,})\s+\d+\.\d+\s+(?:lb|oz|kg|g)\s+(?:@\s+\$?\d+\.\d{2}\s*\/\s*(?:lb|oz|kg|g))?\s+(\d+\.\d{2})$'
        ]
        
        # Process each line of the receipt
        lines = receipt_text.split('\n')
        for line in lines:
            line = line.strip()
            
            # Skip short lines or lines with skip keywords
            if len(line) < 5 or any(keyword.lower() in line.lower() for keyword in skip_keywords):
                continue
                
            # Try each pattern
            for pattern in item_patterns:
                match = re.search(pattern, line)
                if match:
                    # Skip if line contains any skip keywords
                    if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                        continue
                    
                    groups = match.groups()
                    if len(groups) >= 2:
                        description = groups[0].strip()
                        price = groups[-1]  # Last group is always the price
                        
                        # Clean up description
                        if len(description) < 3 or any(skip.lower() in description.lower() for skip in skip_keywords):
                            continue
                        
                        # Skip if it looks like a header or footer line
                        if re.search(r'^(item|qty|description|price|amount|total|subtotal)$', description, re.IGNORECASE):
                            continue
                        
                        # Avoid duplicates
                        normalized_desc = description.lower()
                        if normalized_desc in seen_descriptions:
                            continue
                        seen_descriptions.add(normalized_desc)
                        
                        try:
                            price_float = float(price.replace('$', ''))
                            
                            # TJ items are rarely over $50
                            if price_float > 50 and price_float < 100:
                                price_float = price_float / 10
                                
                            # Build item dictionary
                            item = {
                                'description': description,
                                'price': price_float
                            }
                            
                            # Try to extract quantity if present in description
                            qty_match = re.search(r'(\d+)\s*[xX]\s*', description)
                            if qty_match:
                                quantity = int(qty_match.group(1))
                                if quantity > 0:
                                    item['quantity'] = quantity
                                    # Clean up description by removing the quantity part
                                    item['description'] = re.sub(r'\d+\s*[xX]\s*', '', description).strip()
                            
                            items.append(item)
                            break  # Move to next line after finding a match
                            
                        except (ValueError, TypeError):
                            # If price conversion fails, skip this item
                            continue
        
        print(f"Extracted {len(items)} items from Trader Joe's receipt")
        return items
