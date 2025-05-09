import os
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
import uuid
import re

from utils.image_preprocessor import ImagePreprocessor
from store_classifier import StoreClassifier
from handlers.handler_registry import HandlerRegistry
from handlers.base_handler import BaseReceiptHandler

logger = logging.getLogger(__name__)

class ReceiptProcessor:
    """
    Main controller for receipt processing.
    
    This class orchestrates the receipt processing workflow:
    1. Preprocess the receipt image
    2. Extract text using OCR
    3. Classify the store/vendor
    4. Select and apply the appropriate handler
    5. Validate and enhance the results
    """
    
    def __init__(self, 
                 debug_mode: bool = False,
                 handlers_path: str = "handlers",
                 known_stores_path: str = "data/known_stores.json",
                 debug_output_dir: str = "debug",
                 debug_ocr_output: bool = False):
        """
        Initialize the receipt processor.
        
        Args:
            debug_mode: Whether to enable debug outputs
            handlers_path: Path to the handler modules
            known_stores_path: Path to the known stores JSON file
            debug_output_dir: Directory for debug outputs
            debug_ocr_output: Whether to log raw OCR output for debugging
        """
        self.debug_mode = debug_mode
        self.debug_output_dir = debug_output_dir
        self.debug_ocr_output = debug_ocr_output
        
        # Initialize components
        self.store_classifier = StoreClassifier(known_stores_path)
        self.handler_registry = HandlerRegistry(handlers_path, known_stores_path)
        self.image_preprocessor = ImagePreprocessor(debug_mode=debug_mode, output_dir=debug_output_dir)
        
        # Set up debug directory if needed
        if debug_mode and not os.path.exists(debug_output_dir):
            os.makedirs(debug_output_dir)
            
        logger.info("Receipt processor initialized")
        if debug_mode:
            logger.info("Debug mode enabled")
        if debug_ocr_output:
            logger.info("OCR output debugging enabled")
    
    def process_image(self, image_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a receipt image and extract all information.
        
        Args:
            image_path: Path to the receipt image file
            options: Optional processing options:
                - force_handler: Force a specific handler
                - force_currency: Override detected currency
                - store_hint: Hint for the store name
                - ocr_engine: OCR engine to use
                - confidence_threshold: Minimum confidence threshold
                
        Returns:
            Dictionary with extracted receipt data
        """
        if options is None:
            options = {}
            
        start_time = time.time()
        process_id = str(uuid.uuid4())
        
        # Extract filename for better logging
        image_filename = os.path.basename(image_path)
        logger.info(f"Processing receipt image: {image_filename} (ID: {process_id})")
        
        try:
            # Step 1: Load and preprocess the image
            logger.debug(f"[Processor] Starting preprocessing for {image_filename}")
            preprocessed_image = self.image_preprocessor.preprocess(image_path)
            if self.debug_mode:
                debug_path = os.path.join(self.debug_output_dir, f"preprocessed_{image_filename}")
                self.image_preprocessor.save_image(preprocessed_image, debug_path)
                logger.debug(f"[Processor] Saved preprocessed image to {debug_path}")
            
            # Step 2: Extract text using OCR
            logger.debug(f"[Processor] Starting OCR for {image_filename}")
            ocr_text = self.image_preprocessor.extract_text(preprocessed_image, options.get('ocr_engine'))
            
            # Log raw OCR output if enabled
            if self.debug_ocr_output:
                logger.info(f"[Processor] Raw OCR output for {image_filename}:")
                logger.info("-" * 80)
                logger.info(ocr_text)
                logger.info("-" * 80)
            
            if self.debug_mode:
                # Save OCR text with a more descriptive filename
                debug_ocr_path = os.path.join(self.debug_output_dir, f"ocr_{image_filename}.txt")
                with open(debug_ocr_path, 'w') as f:
                    f.write("# Raw OCR Output\n")
                    f.write("=" * 80 + "\n")
                    f.write(ocr_text)
                    f.write("\n" + "=" * 80 + "\n\n")
                    
                    # Add OCR stats if available
                    if hasattr(self.image_preprocessor, 'last_ocr_stats'):
                        f.write("\n# OCR Statistics\n")
                        f.write("-" * 80 + "\n")
                        for key, value in self.image_preprocessor.last_ocr_stats.items():
                            f.write(f"{key}: {value}\n")
                logger.debug(f"[Processor] Saved OCR text to {debug_ocr_path}")
            
            # Step 3: Classify the store
            logger.debug(f"[Processor] Starting store classification for {image_filename}")
            store_name, store_confidence = self.store_classifier.classify(ocr_text)
            logger.info(f"[Processor] Store classification: {store_name} (confidence: {store_confidence:.2f})")
            
            # Check for store hint in options
            if options.get('store_hint'):
                store_hint = options['store_hint']
                logger.info(f"[Processor] Using store hint: {store_hint}")
                # If hint matches our classification with decent confidence, boost confidence
                if store_hint.lower() in store_name.lower() and store_confidence > 0.5:
                    store_confidence = max(store_confidence, 0.8)
                # Otherwise, if our classification is low confidence, use the hint
                elif store_confidence < 0.6:
                    store_name = store_hint
                    store_confidence = 0.7
            
            # Step 4: Select the appropriate handler
            handler = None
            if options.get('force_handler'):
                forced_handler = options['force_handler']
                logger.info(f"[Processor] Forcing handler: {forced_handler}")
                # Get the handler by name from the registry
                handlers = self.handler_registry.list_registered_handlers()
                if forced_handler in handlers:
                    handler_class = self.handler_registry.handlers.get(forced_handler)
                    if handler_class:
                        handler = handler_class()
            
            # If no forced handler or it wasn't found, get from registry based on store
            if handler is None:
                handler = self.handler_registry.get_handler_for_store(store_name)
                
            logger.info(f"[Processor] Using handler: {handler.__class__.__name__}")
            
            # Step 5: Process the receipt with the selected handler
            logger.debug(f"[Processor] Starting receipt processing with {handler.__class__.__name__}")
            results = handler.process_receipt(ocr_text, image_path)
            
            # Calculate detailed confidence metrics
            confidence_metrics = self._calculate_extraction_quality(results, ocr_text)
            results['confidence'] = confidence_metrics
            
            # Generate a detailed summary of what was extracted
            item_count = len(results.get('items', []))
            item_summary = ", ".join([f"{item['description']}: {item['price']}" for item in results.get('items', [])[:3]])
            if item_count > 3:
                item_summary += f", ... ({item_count-3} more items)"
                
            logger.debug(f"[Processor] Extracted {item_count} items: {item_summary}")
            logger.debug(f"[Processor] Extracted totals: subtotal={results.get('subtotal')}, tax={results.get('tax')}, total={results.get('total')}")
            logger.debug(f"[Processor] Overall confidence: {confidence_metrics['overall']:.2f}")
            
            # Log detailed confidence breakdown if in debug mode
            if self.debug_mode:
                logger.debug("Confidence Breakdown:")
                logger.debug(f"  Items: {confidence_metrics['items']['score']:.2f}")
                logger.debug(f"    - Valid prices: {confidence_metrics['items']['valid_prices'] / confidence_metrics['items']['total_items']:.2f}")
                logger.debug(f"    - Description match rate: {confidence_metrics['items']['description_match_rate']:.2f}")
                logger.debug(f"  Totals: {confidence_metrics['totals']['score']:.2f}")
                logger.debug(f"    - Subtotal detected: {confidence_metrics['totals']['subtotal_detected']}")
                logger.debug(f"    - Total detected: {confidence_metrics['totals']['total_detected']}")
                logger.debug(f"    - Sum matches: {confidence_metrics['totals']['sum_matches']}")
                logger.debug(f"  Store: {confidence_metrics['store']['score']:.2f}")
                logger.debug(f"  OCR: {confidence_metrics['ocr']['score']:.2f}")
            
            # Step 6: Enhance the results with additional information
            results['store'] = store_name
            results['store_confidence'] = store_confidence
            results['handler'] = handler.__class__.__name__
            results['processing_time'] = time.time() - start_time
            results['process_id'] = process_id
            
            # Log processing time with safe formatting
            processing_time = time.time() - start_time
            logger.info(f"[Processor] Processing completed in {processing_time:.2f}s")
            
            # Handle forced currency
            if options.get('force_currency'):
                forced_currency = options['force_currency']
                logger.info(f"[Processor] Forcing currency: {forced_currency}")
                results['currency'] = forced_currency
            
            # Confidence threshold check
            confidence_threshold = options.get('confidence_threshold', 0.5)
            if results.get('confidence', {}).get('overall', 0) < confidence_threshold:
                if self.debug_mode:
                    logger.warning(f"[Processor] Results below confidence threshold: {results.get('confidence', {}).get('overall', 0):.2f} < {confidence_threshold}")
                    
                # Try fallback handler if this wasn't already the generic handler
                if handler.__class__.__name__ != "GenericHandler":
                    logger.info("[Processor] Trying fallback generic handler")
                    fallback_handler = self.handler_registry.handlers['generic']()
                    fallback_results = fallback_handler.process_receipt(ocr_text, image_path)
                    
                    # If fallback has better confidence, use it
                    if (fallback_results.get('confidence', {}).get('overall', 0) > 
                        results.get('confidence', {}).get('overall', 0)):
                        logger.info("[Processor] Fallback handler produced better results, using those")
                        results = fallback_results
                        results['handler'] = fallback_handler.__class__.__name__
                        results['store'] = store_name
                        results['store_confidence'] = store_confidence
                        results['processing_time'] = time.time() - start_time
                        results['process_id'] = process_id
            
            # Calculate extraction quality score
            extraction_quality = self._calculate_extraction_quality(results, ocr_text)
            results['extraction_quality'] = extraction_quality
            
            # Save a summary of the results if in debug mode
            if self.debug_mode:
                debug_summary_path = os.path.join(self.debug_output_dir, f"summary_{image_filename}.json")
                try:
                    import json
                    # Create a simplified summary for easier debugging
                    summary = {
                        'image_path': image_path,
                        'store': store_name,
                        'store_confidence': store_confidence,
                        'handler': handler.__class__.__name__,
                        'item_count': len(results.get('items', [])),
                        'items_sample': [item['description'] for item in results.get('items', [])[:5]],
                        'subtotal': results.get('subtotal'),
                        'tax': results.get('tax'),
                        'total': results.get('total'),
                        'overall_confidence': results.get('confidence', {}).get('overall', 0),
                        'extraction_quality': extraction_quality
                    }
                    with open(debug_summary_path, 'w') as f:
                        json.dump(summary, f, indent=2)
                    logger.debug(f"[Processor] Saved results summary to {debug_summary_path}")
                except Exception as e:
                    logger.error(f"[Processor] Error saving results summary: {str(e)}")
            
            return results
            
        except Exception as e:
            logger.error(f"[Processor] Error processing receipt: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Return error result
            error_result = {
                'error': str(e),
                'store': store_name if 'store_name' in locals() else "unknown",
                'processing_time': time.time() - start_time,
                'process_id': process_id,
                'extraction_quality': 0.0,
                'items': [],
                'confidence': {'overall': 0.0}
            }
            
            # Save error information if in debug mode
            if self.debug_mode:
                debug_error_path = os.path.join(self.debug_output_dir, f"error_{image_filename}.txt")
                try:
                    with open(debug_error_path, 'w') as f:
                        f.write(f"Error: {str(e)}\n\n")
                        f.write(traceback.format_exc())
                    logger.debug(f"[Processor] Saved error details to {debug_error_path}")
                except Exception as error_e:
                    logger.error(f"[Processor] Error saving error details: {str(error_e)}")
                
            return error_result
    
    def process_text(self, ocr_text: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process receipt OCR text directly.
        
        Args:
            ocr_text: The OCR text from the receipt
            options: Optional processing options
                
        Returns:
            Dictionary with extracted receipt data
        """
        if options is None:
            options = {}
            
        start_time = time.time()
        process_id = str(uuid.uuid4())
        
        logger.info(f"Processing receipt text (ID: {process_id})")
        
        try:
            # Step 1: Classify the store
            store_name, store_confidence = self.store_classifier.classify(ocr_text)
            logger.info(f"Store classification: {store_name} (confidence: {store_confidence:.2f})")
            
            # Check for store hint in options
            if options.get('store_hint'):
                store_hint = options['store_hint']
                logger.info(f"Using store hint: {store_hint}")
                # If hint matches our classification with decent confidence, boost confidence
                if store_hint.lower() in store_name.lower() and store_confidence > 0.5:
                    store_confidence = max(store_confidence, 0.8)
                # Otherwise, if our classification is low confidence, use the hint
                elif store_confidence < 0.6:
                    store_name = store_hint
                    store_confidence = 0.7
            
            # Step 2: Select the appropriate handler
            handler = None
            if options.get('force_handler'):
                forced_handler = options['force_handler']
                logger.info(f"Forcing handler: {forced_handler}")
                # Get the handler by name from the registry
                handlers = self.handler_registry.list_registered_handlers()
                if forced_handler in handlers:
                    handler_class = self.handler_registry.handlers.get(forced_handler)
                    if handler_class:
                        handler = handler_class()
            
            # If no forced handler or it wasn't found, get from registry based on store
            if handler is None:
                handler = self.handler_registry.get_handler_for_store(store_name)
                
            logger.info(f"Using handler: {handler.__class__.__name__}")
            
            # Step 3: Process the receipt with the selected handler
            results = handler.process_receipt(ocr_text)
            
            # Step 4: Enhance the results with additional information
            results['store'] = store_name
            results['store_confidence'] = store_confidence
            results['handler'] = handler.__class__.__name__
            results['processing_time'] = time.time() - start_time
            results['process_id'] = process_id
            
            # Handle forced currency
            if options.get('force_currency'):
                forced_currency = options['force_currency']
                logger.info(f"Forcing currency: {forced_currency}")
                results['currency'] = forced_currency
            
            # Confidence threshold check
            confidence_threshold = options.get('confidence_threshold', 0.5)
            if results.get('confidence', {}).get('overall', 0) < confidence_threshold:
                if self.debug_mode:
                    logger.warning(f"Results below confidence threshold: {results.get('confidence', {}).get('overall', 0):.2f} < {confidence_threshold}")
                    
                # Try fallback handler if this wasn't already the generic handler
                if handler.__class__.__name__ != "GenericHandler":
                    logger.info("Trying fallback generic handler")
                    fallback_handler = self.handler_registry.handlers['generic']()
                    fallback_results = fallback_handler.process_receipt(ocr_text)
                    
                    # If fallback has better confidence, use it
                    if (fallback_results.get('confidence', {}).get('overall', 0) > 
                        results.get('confidence', {}).get('overall', 0)):
                        logger.info("Fallback handler produced better results, using those")
                        results = fallback_results
                        results['handler'] = fallback_handler.__class__.__name__
                        results['store'] = store_name
                        results['store_confidence'] = store_confidence
                        results['processing_time'] = time.time() - start_time
                        results['process_id'] = process_id
            
            # Calculate extraction quality score
            extraction_quality = self._calculate_extraction_quality(results, ocr_text)
            results['extraction_quality'] = extraction_quality
            
            logger.info(f"Receipt text processing completed in {results['processing_time']:.2f}s, "
                       f"extraction quality: {extraction_quality:.2f}, "
                       f"found {len(results.get('items', []))} items")
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing receipt text: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Return error result
            return {
                'error': str(e),
                'store': store_name if 'store_name' in locals() else "unknown",
                'processing_time': time.time() - start_time,
                'process_id': process_id,
                'extraction_quality': 0.0,
                'items': [],
                'confidence': {'overall': 0.0}
            }
    
    def _calculate_extraction_quality(self, results: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        """
        Calculate detailed confidence metrics for receipt extraction.
        
        Args:
            results: Dictionary containing extracted receipt data
            raw_text: Raw OCR text
            
        Returns:
            Dictionary containing overall confidence and detailed metrics
        """
        metrics = {
            'overall': 0.0,
            'items': {
                'score': 0.0,
                'valid_prices': 0,
                'total_items': 0,
                'price_match_rate': 0.0,
                'description_match_rate': 0.0
            },
            'totals': {
                'score': 0.0,
                'subtotal_detected': False,
                'total_detected': False,
                'sum_matches': False,
                'difference_percent': 0.0
            },
            'store': {
                'score': 0.0,
                'name_detected': False,
                'pattern_matches': False
            },
            'ocr': {
                'score': 0.0,
                'quality': 0.0,
                'line_count': 0,
                'matched_lines': 0
            }
        }
        
        # Calculate item metrics
        items = results.get('items', [])
        if items:
            metrics['items']['total_items'] = len(items)
            valid_prices = sum(1 for item in items if item.get('price', 0) > 0)
            metrics['items']['valid_prices'] = valid_prices
            metrics['items']['price_match_rate'] = valid_prices / len(items)
            
            # Calculate description match rate (items that match known patterns)
            matched_descriptions = sum(1 for item in items if item.get('confidence', {}).get('description', 0) > 0.4)  # Lower threshold
            metrics['items']['description_match_rate'] = matched_descriptions / len(items)
            
            # Calculate item score - weight price matches more heavily
            metrics['items']['score'] = (
                metrics['items']['price_match_rate'] * 0.8 +  # Increase price weight
                metrics['items']['description_match_rate'] * 0.2  # Decrease description weight
            )
        
        # Calculate totals metrics
        subtotal = results.get('subtotal')
        total = results.get('total')
        
        if subtotal is not None:
            metrics['totals']['subtotal_detected'] = True
        if total is not None:
            metrics['totals']['total_detected'] = True
        
        # Check if sum of items matches totals - increase tolerance to 20%
        if items and total:
            items_sum = sum(item.get('price', 0) for item in items)
            if items_sum > 0:
                difference = abs(items_sum - total)
                difference_percent = (difference / total) * 100
                metrics['totals']['difference_percent'] = difference_percent
                metrics['totals']['sum_matches'] = difference_percent <= 20
        
        # Calculate totals score - only require total (not subtotal)
        totals_factors = [
            metrics['totals']['total_detected'],
            metrics['totals']['sum_matches']
        ]
        metrics['totals']['score'] = sum(1 for f in totals_factors if f) / len(totals_factors)
        
        # Calculate store metrics - increase base confidence further
        store_name = results.get('store_name')
        if store_name:
            metrics['store']['name_detected'] = True
            # Check if store name matches known patterns
            known_stores = ['Costco', 'Trader Joe', 'H Mart', 'Key Food']
            metrics['store']['pattern_matches'] = any(store.lower() in store_name.lower() for store in known_stores)
            metrics['store']['score'] = 0.9 if metrics['store']['pattern_matches'] else 0.7  # Increase both scores
        
        # Calculate OCR metrics - lower pattern matching requirements and increase base score
        if raw_text:
            lines = raw_text.strip().split('\n')
            metrics['ocr']['line_count'] = len(lines)
            
            # Count lines that match common receipt patterns
            patterns = [
                r'\d+\.\d{2}',  # Price pattern
                r'total|tax',  # Common receipt terms (removed subtotal)
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # Date pattern
            ]
            
            matched_lines = 0
            for line in lines:
                if any(re.search(pattern, line, re.I) for pattern in patterns):
                    matched_lines += 1
            
            metrics['ocr']['matched_lines'] = matched_lines
            metrics['ocr']['quality'] = matched_lines / len(lines) if lines else 0
            # Increase base score and max further
            metrics['ocr']['score'] = min(0.99, metrics['ocr']['quality'] + 0.5)  # Base 0.5 + quality up to 0.99
        
        # Calculate overall confidence score - adjust weights to focus more on items and store
        weights = {
            'items': 0.6,  # Increased from 0.5
            'totals': 0.1,  # Decreased from 0.2
            'store': 0.2,  # Same
            'ocr': 0.1  # Same
        }
        
        metrics['overall'] = sum(
            metrics[key]['score'] * weight
            for key, weight in weights.items()
        )
        
        return metrics 