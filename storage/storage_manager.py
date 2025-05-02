"""
Storage manager for handling receipt and expense data persistence.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Manages storage and retrieval of receipt and expense data.
    
    This class provides a unified interface for storing and retrieving:
    - Receipt images
    - Receipt processing results
    - OCR data
    - Expense records
    """
    
    def __init__(self, 
                 data_dir: str = "data",
                 receipts_dir: str = "receipts",
                 results_dir: str = "results"):
        """
        Initialize the storage manager.
        
        Args:
            data_dir: Base directory for all stored data
            receipts_dir: Directory for receipt images
            results_dir: Directory for processing results
        """
        self.data_dir = Path(data_dir)
        self.receipts_dir = self.data_dir / receipts_dir
        self.results_dir = self.data_dir / results_dir
        
        # Create directories if they don't exist
        self.data_dir.mkdir(exist_ok=True)
        self.receipts_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)
        
        logger.info(f"Storage manager initialized with data directory: {data_dir}")
    
    def save_receipt_image(self, receipt_id: UUID, image_data: bytes) -> str:
        """
        Save a receipt image to storage.
        
        Args:
            receipt_id: UUID of the receipt
            image_data: Raw image data
            
        Returns:
            str: Path to the saved image file
        """
        image_path = self.receipts_dir / f"{receipt_id}.jpg"
        
        with open(image_path, "wb") as f:
            f.write(image_data)
            
        logger.debug(f"Saved receipt image: {image_path}")
        return str(image_path)
    
    def save_receipt_result(self, receipt_id: UUID, result: Dict[str, Any]) -> str:
        """
        Save receipt processing results.
        
        Args:
            receipt_id: UUID of the receipt
            result: Processing results dictionary
            
        Returns:
            str: Path to the saved results file
        """
        result_path = self.results_dir / f"{receipt_id}.json"
        
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
            
        logger.debug(f"Saved receipt results: {result_path}")
        return str(result_path)
    
    def load_receipt_result(self, receipt_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Load receipt processing results.
        
        Args:
            receipt_id: UUID of the receipt
            
        Returns:
            Optional[Dict]: Processing results or None if not found
        """
        result_path = self.results_dir / f"{receipt_id}.json"
        
        if not result_path.exists():
            logger.warning(f"Receipt results not found: {receipt_id}")
            return None
            
        with open(result_path) as f:
            return json.load(f)
    
    def delete_receipt(self, receipt_id: UUID) -> bool:
        """
        Delete a receipt and its associated data.
        
        Args:
            receipt_id: UUID of the receipt
            
        Returns:
            bool: True if deletion was successful
        """
        success = True
        
        # Delete image
        image_path = self.receipts_dir / f"{receipt_id}.jpg"
        if image_path.exists():
            try:
                image_path.unlink()
            except Exception as e:
                logger.error(f"Error deleting receipt image {receipt_id}: {str(e)}")
                success = False
        
        # Delete results
        result_path = self.results_dir / f"{receipt_id}.json"
        if result_path.exists():
            try:
                result_path.unlink()
            except Exception as e:
                logger.error(f"Error deleting receipt results {receipt_id}: {str(e)}")
                success = False
        
        return success
    
    def list_receipts(self) -> List[UUID]:
        """
        List all stored receipt IDs.
        
        Returns:
            List[UUID]: List of receipt IDs
        """
        receipts = []
        
        for result_file in self.results_dir.glob("*.json"):
            try:
                receipt_id = UUID(result_file.stem)
                receipts.append(receipt_id)
            except ValueError:
                logger.warning(f"Invalid receipt ID format: {result_file.stem}")
                continue
        
        return receipts 