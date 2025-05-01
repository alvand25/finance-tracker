"""Receipt handler package.

This package contains handlers for processing receipts from different vendors.
Each handler implements the BaseReceiptHandler interface and provides
vendor-specific logic for extracting information from receipts.
"""

from .base_handler import BaseReceiptHandler
from .generic_handler import GenericHandler
from .costco_handler import CostcoReceiptHandler

__all__ = [
    'BaseReceiptHandler',
    'GenericHandler',
    'CostcoReceiptHandler'
]

# The following will be populated by handler discovery:
# handlers.trader_joes_handler.TraderJoesHandler
# etc. 