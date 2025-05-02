"""Tests for receipt service with Google Cloud Vision integration."""
import os
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from services.receipt_service import ReceiptService
from models.receipt import Receipt
from utils.image_preprocessor import ImagePreprocessor
from utils.receipt_analyzer import ReceiptAnalyzer
from ocr.google_vision_ocr import GoogleVisionOCR

@pytest.fixture
def mock_storage():
    """Create a mock storage instance."""
    storage = Mock()
    storage.get.return_value = None
    return storage

@pytest.fixture
def mock_image_file(tmp_path):
    """Create a mock image file."""
    image_file = tmp_path / "test_receipt.jpg"
    image_file.write_bytes(b"dummy image content")
    
    mock_file = Mock()
    mock_file.save = lambda path: image_file.read_bytes()
    return mock_file

@pytest.fixture
def receipt_service(mock_storage, mock_vision_config, mock_credentials, tmp_path):
    """Create a receipt service instance with mocked dependencies."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return ReceiptService(mock_storage, str(upload_dir))

def test_init_with_google_vision(mock_storage, mock_vision_config, mock_credentials, tmp_path):
    """Test initialization with Google Cloud Vision configuration."""
    service = ReceiptService(mock_storage, str(tmp_path))
    assert isinstance(service.ocr, GoogleVisionOCR)
    assert service.vision_config.is_configured is True

def test_init_without_google_vision(mock_storage, tmp_path):
    """Test initialization without Google Cloud Vision configuration."""
    with pytest.MonkeyPatch().context() as mp:
        mp.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
        service = ReceiptService(mock_storage, str(tmp_path))
        assert service.ocr is None
        assert service.vision_config.is_configured is False

def test_process_receipt_with_google_vision(receipt_service, mock_image_file, mock_vision_client):
    """Test receipt processing with Google Cloud Vision."""
    result = receipt_service.process_receipt(mock_image_file)
    
    assert result is not None
    assert 'error' not in result
    assert result['ocr_metadata']['engine'] == 'google_vision'
    assert result['ocr_metadata']['confidence'] > 0.9

def test_process_receipt_with_tesseract_fallback(mock_storage, mock_image_file, tmp_path):
    """Test receipt processing with Tesseract fallback when Google Vision is not configured."""
    with pytest.MonkeyPatch().context() as mp:
        mp.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
        service = ReceiptService(mock_storage, str(tmp_path))
        result = service.process_receipt(mock_image_file)
        
        assert result is not None
        assert 'error' not in result
        assert result['ocr_metadata']['engine'] == 'tesseract'

def test_process_receipt_with_database(receipt_service, mock_image_file, mock_vision_client):
    """Test receipt processing with database integration."""
    mock_session = Mock()
    result = receipt_service.process_receipt(mock_image_file, user_id='test_user', db_session=mock_session)
    
    assert result is not None
    assert 'error' not in result
    assert 'receipt_id' in result
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

def test_process_receipt_progressive(receipt_service, mock_image_file):
    """Test progressive receipt processing."""
    task_id, result = receipt_service.process_receipt_progressive(mock_image_file)
    
    assert task_id is not None
    assert result['status'] == 'processing'
    assert result['task_id'] == task_id
    
    # Verify task data was stored
    stored_data = receipt_service.json_storage.get(task_id)
    assert stored_data is not None
    assert stored_data['status'] == 'processing'
    assert 'image_path' in stored_data
    assert 'initial_text' in stored_data
    assert 'timestamp' in stored_data

def test_complete_progressive_processing(receipt_service, mock_image_file, mock_vision_client):
    """Test completion of progressive receipt processing."""
    # Start progressive processing
    task_id, _ = receipt_service.process_receipt_progressive(mock_image_file)
    
    # Complete processing
    result = receipt_service.complete_progressive_processing(task_id)
    
    assert result is not None
    assert 'error' not in result
    assert result['ocr_metadata']['engine'] == 'google_vision'
    assert result['ocr_metadata']['confidence'] > 0.9
    
    # Verify task data was updated
    stored_data = receipt_service.json_storage.get(task_id)
    assert stored_data['status'] == 'completed'
    assert 'result' in stored_data
    assert 'completed_at' in stored_data

def test_complete_progressive_processing_error(receipt_service):
    """Test error handling in progressive processing completion."""
    result = receipt_service.complete_progressive_processing('nonexistent_task')
    
    assert result is not None
    assert 'error' in result
    assert 'Task nonexistent_task not found' in result['error']

def test_process_receipt_image_error(receipt_service):
    """Test error handling in receipt image processing."""
    result = receipt_service.process_receipt_image('/nonexistent/path/image.jpg')
    
    assert result is not None
    assert 'error' in result

def test_process_receipt_with_vision_error(receipt_service, mock_image_file):
    """Test error handling when Google Vision API fails."""
    with patch('ocr.google_vision_ocr.GoogleVisionOCR.extract_text') as mock_extract:
        mock_extract.side_effect = Exception("API Error")
        result = receipt_service.process_receipt(mock_image_file)
        
        assert result is not None
        assert 'error' in result
        assert 'API Error' in result['error'] 