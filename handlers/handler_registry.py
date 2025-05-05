import os
import importlib
import inspect
import json
import logging
from typing import Dict, List, Type, Optional, Any

from handlers.base_handler import BaseReceiptHandler
from handlers.generic_handler import GenericReceiptHandler
from handlers.costco_handler import CostcoReceiptHandler
from handlers.trader_joes_handler import TraderJoesReceiptHandler
from handlers.key_food_handler import KeyFoodReceiptHandler
from handlers.walmart_handler import WalmartReceiptHandler

logger = logging.getLogger(__name__)

class HandlerRegistry:
    """Registry for receipt handlers.
    
    This class manages the registration and lookup of receipt handlers for different vendors.
    """
    
    def __init__(self, handlers_path: str = "handlers", known_stores_path: str = "data/known_stores.json"):
        """
        Initialize the handler registry.
        
        Args:
            handlers_path: Path to the directory containing handler modules
            known_stores_path: Path to the JSON file mapping store names to handler keys
        """
        self._handlers: Dict[str, Type[BaseReceiptHandler]] = {
            'trader_joes': TraderJoesReceiptHandler,
            'key_food': KeyFoodReceiptHandler,
            'walmart': WalmartReceiptHandler,
            'costco': CostcoReceiptHandler,
            'generic': GenericReceiptHandler
        }
        
        # Initialize handler instances
        self._handler_instances: Dict[str, BaseReceiptHandler] = {}
        for name, handler_class in self._handlers.items():
            try:
                self._handler_instances[name] = handler_class()
            except Exception as e:
                logger.error(f"Failed to initialize handler {name}: {e}")
        
        self.handlers_path = handlers_path
        self.known_stores_path = known_stores_path
        
        # Register built-in handlers
        self._register_builtin_handlers()
        
        # Load store mappings
        self._load_store_mappings()
        
        logger.info(f"Handler registry initialized with {len(self._handlers)} handlers and {len(self.store_mappings)} store mappings")
    
    def _register_builtin_handlers(self) -> None:
        """Register built-in handlers."""
        # Try to auto-discover handlers in the handlers directory
        if os.path.isdir(self.handlers_path):
            for filename in os.listdir(self.handlers_path):
                if filename.endswith('_handler.py') and filename != 'base_handler.py' and filename != 'generic_handler.py':
                    try:
                        # Extract module name (remove .py extension)
                        module_name = filename[:-3]
                        
                        # Import the module
                        module_path = f"handlers.{module_name}"
                        module = importlib.import_module(module_path)
                        
                        # Find handler classes in the module
                        for name, obj in inspect.getmembers(module):
                            if (inspect.isclass(obj) and 
                                issubclass(obj, BaseReceiptHandler) and 
                                obj is not BaseReceiptHandler):
                                
                                # Get the handler key (lowercase without 'Handler' suffix)
                                handler_key = name.lower()
                                if handler_key.endswith('handler'):
                                    handler_key = handler_key[:-7]
                                elif handler_key.endswith('receipthandler'):
                                    handler_key = handler_key[:-13]
                                
                                # Register the handler
                                self._handlers[handler_key] = obj
                                logger.debug(f"Registered handler: {handler_key} -> {obj.__name__}")
                    except Exception as e:
                        logger.error(f"Error loading handler from {filename}: {str(e)}")
    
    def _load_store_mappings(self) -> None:
        """Load store name to handler mappings from JSON file."""
        try:
            if os.path.exists(self.known_stores_path):
                with open(self.known_stores_path, 'r') as f:
                    self.store_mappings = json.load(f)
                    logger.debug(f"Loaded store mappings from {self.known_stores_path}")
            else:
                logger.warning(f"Store mappings file not found: {self.known_stores_path}")
                # Create default mappings
                self.store_mappings = {
                    "costco": ["COSTCO", "COSTCO WHOLESALE", "WHOLESALE"],
                    "trader_joes": ["TRADER JOE'S", "TRADER JOES", "TJ"],
                    "h_mart": ["H MART", "H-MART"],
                    "key_food": ["KEY FOOD", "KEYFOOD"]
                }
                # Ensure the directory exists
                os.makedirs(os.path.dirname(self.known_stores_path), exist_ok=True)
                
                # Save default mappings
                with open(self.known_stores_path, 'w') as f:
                    json.dump(self.store_mappings, f, indent=2)
                    logger.info(f"Created default store mappings at {self.known_stores_path}")
        except Exception as e:
            logger.error(f"Error loading store mappings: {str(e)}")
            # Fallback to empty mappings
            self.store_mappings = {}
    
    def get_handler(self, text: str) -> Optional[BaseReceiptHandler]:
        """Get the most appropriate handler for the receipt text."""
        best_handler = None
        best_confidence = 0.0
        
        for name, handler in self._handler_instances.items():
            try:
                confidence = handler.can_handle_receipt(text)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_handler = handler
            except Exception as e:
                logger.error(f"Error checking handler {name}: {e}")
        
        if best_handler and best_confidence >= 0.7:
            return best_handler
            
        # Fall back to generic handler if no specific handler is confident enough
        return self._handler_instances['generic']
    
    def get_handler_by_name(self, name: str) -> Optional[BaseReceiptHandler]:
        """Get a handler by its registered name."""
        return self._handler_instances.get(name)
    
    def get_available_handlers(self) -> List[str]:
        """Get a list of available handler names."""
        return list(self._handlers.keys())
    
    def register_handler(self, name: str, handler_class: Type[BaseReceiptHandler]) -> None:
        """Register a new handler."""
        if name in self._handlers:
            logger.warning(f"Overwriting existing handler: {name}")
            
        try:
            handler_instance = handler_class()
            self._handlers[name] = handler_class
            self._handler_instances[name] = handler_instance
            logger.info(f"Successfully registered handler: {name}")
        except Exception as e:
            logger.error(f"Failed to register handler {name}: {e}")
            raise

# Global registry instance
_registry = HandlerRegistry()

def get_handler(text: str) -> Optional[BaseReceiptHandler]:
    """Get the most appropriate handler for the receipt text."""
    return _registry.get_handler(text)

def get_handler_by_name(name: str) -> Optional[BaseReceiptHandler]:
    """Get a handler by its registered name."""
    return _registry.get_handler_by_name(name)

def get_available_handlers() -> List[str]:
    """Get a list of available handler names."""
    return _registry.get_available_handlers()

def register_handler(name: str, handler_class: Type[BaseReceiptHandler]) -> None:
    """Register a new handler."""
    _registry.register_handler(name, handler_class)

# List of available handlers in order of preference
HANDLERS: List[Type[BaseReceiptHandler]] = [
    CostcoReceiptHandler,
    TraderJoesReceiptHandler,
    KeyFoodReceiptHandler,
    WalmartReceiptHandler,
    GenericReceiptHandler  # Always keep generic handler last as fallback
]

def get_handler_for_store(store_name: str) -> BaseReceiptHandler:
    """
    Get the appropriate handler for a store name.
    
    Args:
        store_name: The store name to look up
        
    Returns:
        An instance of the appropriate handler
    """
    if not store_name:
        logger.debug("[Registry] No store name provided, using generic handler")
        return GenericReceiptHandler()
    
    # Normalize store name to lowercase for comparison
    store_name_lower = store_name.lower().strip()
    logger.debug(f"[Registry] Looking for handler for store: '{store_name}' (normalized: '{store_name_lower}')")
    logger.debug(f"[Registry] Available Handlers: {list(HANDLERS)}")
    logger.debug(f"[Registry] Store Mappings: {HANDLERS}")
    
    # First try direct handler key match
    if store_name_lower in HANDLERS:
        logger.debug(f"[Registry] Direct handler match found: {store_name_lower}")
        return HANDLERS[store_name_lower]()
    
    # Check store mappings
    for handler_key, store_variations in HANDLERS.items():
        normalized_variations = [v.lower().strip() for v in store_variations]
        logger.debug(f"[Registry] Checking variations for {handler_key}: {normalized_variations}")
        
        # Check if store name contains any of the variations
        for variation in normalized_variations:
            if variation in store_name_lower or store_name_lower in variation:
                if handler_key in HANDLERS:
                    logger.debug(f"[Registry] Selected Handler: {HANDLERS[handler_key].__name__} for store '{store_name}'")
                    return HANDLERS[handler_key]()
                else:
                    logger.warning(f"[Registry] Handler key '{handler_key}' not registered for store '{store_name}'")
    
    # No direct mapping found, try common vendor names
    common_vendors = {
        "costco": ["costco", "wholesale"],
        "trader_joes": ["trader", "joe"],
        "h_mart": ["h mart", "h-mart", "hmart"],
        "key_food": ["key food", "keyfood"],
        "walmart": ["walmart"],
        "target": ["target"],
        "kroger": ["kroger"],
        "safeway": ["safeway"],
        "publix": ["publix"],
        "whole_foods": ["whole foods"],
        "aldi": ["aldi"]
    }
    
    logger.debug(f"[Registry] Checking common vendor keywords")
    
    for handler_key, keywords in common_vendors.items():
        matched_keywords = [keyword for keyword in keywords if keyword in store_name_lower]
        if matched_keywords:
            logger.debug(f"[Registry] Found match in common vendors: {matched_keywords} for handler '{handler_key}'")
            if handler_key in HANDLERS:
                logger.debug(f"[Registry] Selected Handler: {HANDLERS[handler_key].__name__}")
                return HANDLERS[handler_key]()
    
    # Fallback to generic handler
    logger.debug(f"[Registry] No specific handler found for store '{store_name}', using generic handler")
    return GenericReceiptHandler() 