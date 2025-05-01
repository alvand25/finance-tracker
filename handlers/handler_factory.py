from typing import Optional
from .base_handler import BaseHandler
from .generic_handler import GenericHandler
from .h_mart_handler import HMartHandler

class HandlerFactory:
    """Factory for creating receipt handlers."""
    
    def __init__(self):
        """Initialize the factory with available handlers."""
        self.handlers = {
            'generic': GenericHandler(),
            'h_mart': HMartHandler()
        }
        
    def get_handler(self, store_name: Optional[str] = None) -> BaseHandler:
        """
        Get the appropriate handler for a store.
        
        Args:
            store_name: Name of the store (optional)
            
        Returns:
            BaseHandler: Appropriate handler for the store
        """
        if not store_name:
            return self.handlers['generic']
            
        store_name = store_name.lower()
        
        # Check each handler's store aliases
        for handler in self.handlers.values():
            if any(alias in store_name for alias in handler.store_aliases):
                return handler
                
        # Fall back to generic handler
        return self.handlers['generic'] 