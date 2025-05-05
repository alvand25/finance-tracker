"""Receipt handler package.

This package contains handlers for processing receipts from different vendors.
Each handler implements the BaseReceiptHandler interface and provides
vendor-specific logic for extracting information from receipts.
"""

from .base_handler import BaseReceiptHandler
from .generic_handler import GenericReceiptHandler
from .costco_handler import CostcoReceiptHandler
from .trader_joes_handler import TraderJoesReceiptHandler
from .key_food_handler import KeyFoodReceiptHandler
from .walmart_handler import WalmartReceiptHandler
from .handler_registry import (
    get_handler,
    get_handler_by_name,
    get_available_handlers,
    register_handler
)

__all__ = [
    'BaseReceiptHandler',
    'GenericReceiptHandler',
    'CostcoReceiptHandler',
    'TraderJoesReceiptHandler',
    'KeyFoodReceiptHandler',
    'WalmartReceiptHandler',
    'get_handler',
    'get_handler_by_name',
    'get_available_handlers',
    'register_handler'
]

# The following will be populated by handler discovery:
# handlers.trader_joes_handler.TraderJoesHandler
# etc. 