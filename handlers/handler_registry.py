import os
import importlib
import inspect
import json
import logging
from typing import Dict, List, Type, Optional, Any

from handlers.base_handler import BaseReceiptHandler
from handlers.generic_handler import GenericHandler

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
        self.handlers: Dict[str, Type[BaseReceiptHandler]] = {}
        self.store_mappings: Dict[str, List[str]] = {}
        self.handlers_path = handlers_path
        self.known_stores_path = known_stores_path
        
        # Register built-in handlers
        self._register_builtin_handlers()
        
        # Load store mappings
        self._load_store_mappings()
        
        logger.info(f"Handler registry initialized with {len(self.handlers)} handlers and {len(self.store_mappings)} store mappings")
    
    def _register_builtin_handlers(self) -> None:
        """Register built-in handlers."""
        # Ensure we have a generic handler
        if 'generic' not in self.handlers:
            self.handlers['generic'] = GenericHandler
            
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
                                
                                # Register the handler
                                self.handlers[handler_key] = obj
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
    
    def get_handler_for_store(self, store_name: str) -> BaseReceiptHandler:
        """
        Get the appropriate handler for a store name.
        
        Args:
            store_name: The store name to look up
            
        Returns:
            An instance of the appropriate handler
        """
        if not store_name:
            logger.debug("[Registry] No store name provided, using generic handler")
            return GenericHandler()
        
        logger.debug(f"[Registry] Available Handlers: {list(self.handlers.keys())}")
        logger.debug(f"[Registry] Looking for handler for store: '{store_name}'")
        
        # Normalize store name to lowercase for comparison
        store_name_lower = store_name.lower()
        
        # Check direct mappings first
        for handler_key, store_variations in self.store_mappings.items():
            for variation in store_variations:
                logger.debug(f"[Registry] Checking if '{variation.lower()}' matches '{store_name_lower}'")
                if variation.lower() in store_name_lower:
                    if handler_key in self.handlers:
                        logger.debug(f"[Registry] Selected Handler: {self.handlers[handler_key].__name__} for store '{store_name}'")
                        return self.handlers[handler_key]()
                    else:
                        logger.warning(f"[Registry] Handler key '{handler_key}' not registered for store '{store_name}'")
        
        # No direct mapping found, try some common vendor names
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
        
        logger.debug(f"[Registry] No direct mapping found, checking common vendor keywords")
        
        for handler_key, keywords in common_vendors.items():
            matched_keywords = [keyword for keyword in keywords if keyword in store_name_lower]
            if matched_keywords:
                logger.debug(f"[Registry] Found match in common vendors: {matched_keywords} for handler '{handler_key}'")
                if handler_key in self.handlers:
                    logger.debug(f"[Registry] Selected Handler: {self.handlers[handler_key].__name__}")
                    return self.handlers[handler_key]()
        
        # Fallback to generic handler
        logger.debug(f"[Registry] No specific handler found for store '{store_name}', using generic handler")
        return GenericHandler()
    
    def add_store_mapping(self, handler_key: str, store_name: str) -> bool:
        """
        Add a new store name mapping to a handler.
        
        Args:
            handler_key: The handler key to map to
            store_name: The store name to add
            
        Returns:
            True if successful, False otherwise
        """
        if handler_key not in self.handlers:
            logger.error(f"Cannot add mapping: Handler key '{handler_key}' not registered")
            return False
        
        if handler_key not in self.store_mappings:
            self.store_mappings[handler_key] = []
            
        # Add the store name if it's not already in the list
        if store_name not in self.store_mappings[handler_key]:
            self.store_mappings[handler_key].append(store_name)
            
            # Save the updated mappings
            try:
                with open(self.known_stores_path, 'w') as f:
                    json.dump(self.store_mappings, f, indent=2)
                logger.info(f"Added mapping: {store_name} -> {handler_key}")
                return True
            except Exception as e:
                logger.error(f"Error saving store mappings: {str(e)}")
                return False
        
        return True  # Already exists
    
    def list_registered_handlers(self) -> Dict[str, List[str]]:
        """
        Get a dictionary of registered handlers and their store mappings.
        
        Returns:
            Dictionary with handler keys and associated store names
        """
        result = {}
        for handler_key in self.handlers:
            result[handler_key] = self.store_mappings.get(handler_key, [])
        return result
    
    def register_custom_handler(self, handler_key: str, handler_class: Type[BaseReceiptHandler]) -> bool:
        """
        Register a custom handler class.
        
        Args:
            handler_key: The key to register the handler under
            handler_class: The handler class to register
            
        Returns:
            True if successful, False otherwise
        """
        if not issubclass(handler_class, BaseReceiptHandler):
            logger.error(f"Cannot register handler: {handler_class.__name__} is not a subclass of BaseReceiptHandler")
            return False
            
        self.handlers[handler_key] = handler_class
        logger.info(f"Registered custom handler: {handler_key} -> {handler_class.__name__}")
        return True 