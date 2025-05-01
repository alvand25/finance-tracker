import os
import shutil
import uuid
from datetime import date
from typing import Optional

from PIL import Image


class ReceiptUploader:
    """Utility for handling receipt image uploads."""
    
    def __init__(self, upload_dir: str = "uploads/receipts"):
        self.upload_dir = upload_dir
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self) -> None:
        """Ensure that the upload directory exists."""
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)
    
    def save_receipt(self, file_path: str, date_obj: date, store: str) -> Optional[str]:
        """
        Save a receipt image to the uploads directory.
        
        Args:
            file_path: Path to the receipt image file
            date_obj: Date of the expense
            store: Store name
            
        Returns:
            URL path to the saved receipt, or None if there was an error
        """
        try:
            # Make sure file exists
            if not os.path.exists(file_path):
                print(f"Error: Receipt file not found: {file_path}")
                return None
            
            # Generate a unique filename for the receipt
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.pdf']:
                print(f"Error: Unsupported file format: {file_ext}")
                return None
            
            # Format the date for the filename
            date_str = date_obj.strftime("%Y%m%d")
            # Create a clean store name (remove spaces and special characters)
            clean_store = ''.join(e for e in store if e.isalnum()).lower()
            # Generate a unique ID
            unique_id = str(uuid.uuid4())[:8]
            
            # Create the target filename
            target_filename = f"{date_str}_{clean_store}_{unique_id}{file_ext}"
            target_path = os.path.join(self.upload_dir, target_filename)
            
            # Copy the file to the uploads directory
            shutil.copy2(file_path, target_path)
            
            # For image files, create a thumbnail for faster loading
            if file_ext in ['.jpg', '.jpeg', '.png']:
                try:
                    self._create_thumbnail(target_path)
                except Exception as e:
                    print(f"Warning: Could not create thumbnail: {str(e)}")
            
            # Return the relative path to the receipt
            return os.path.join('receipts', target_filename)
        
        except Exception as e:
            print(f"Error saving receipt: {str(e)}")
            return None
    
    def _create_thumbnail(self, image_path: str, max_size: int = 500) -> None:
        """Create a thumbnail version of the image."""
        thumb_dir = os.path.join(os.path.dirname(self.upload_dir), 'thumbnails')
        if not os.path.exists(thumb_dir):
            os.makedirs(thumb_dir)
        
        # Get the filename
        filename = os.path.basename(image_path)
        thumb_path = os.path.join(thumb_dir, filename)
        
        # Open the image and resize it
        with Image.open(image_path) as img:
            # Calculate the new dimensions
            width, height = img.size
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))
            
            # Resize the image and save it
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)
            img_resized.save(thumb_path, optimize=True, quality=85)
    
    def delete_receipt(self, receipt_url: str) -> bool:
        """
        Delete a receipt image.
        
        Args:
            receipt_url: URL path to the receipt
            
        Returns:
            True if the receipt was deleted, False otherwise
        """
        try:
            # Extract the filename from the URL
            filename = os.path.basename(receipt_url)
            
            # Build the full path to the receipt and thumbnail
            receipt_path = os.path.join(self.upload_dir, filename)
            thumb_dir = os.path.join(os.path.dirname(self.upload_dir), 'thumbnails')
            thumb_path = os.path.join(thumb_dir, filename)
            
            # Delete the files if they exist
            if os.path.exists(receipt_path):
                os.remove(receipt_path)
                
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                
            return True
        
        except Exception as e:
            print(f"Error deleting receipt: {str(e)}")
            return False 