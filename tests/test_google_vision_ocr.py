"""Tests for Google Cloud Vision OCR implementation."""
import os
import pytest
from unittest.mock import Mock, patch
from google.cloud import vision

from ocr.google_vision_ocr import GoogleVisionOCR

@pytest.fixture
def mock_vision_client():
    """Create a mock Vision client."""
    with patch('google.cloud.vision.ImageAnnotatorClient') as mock_client:
        yield mock_client.return_value

@pytest.fixture
def mock_credentials():
    """Create a mock credentials file."""
    with patch.dict(os.environ, {'GOOGLE_APPLICATION_CREDENTIALS': '/mock/path/credentials.json'}):
        yield

@pytest.fixture
def vision_ocr(mock_credentials):
    """Create a GoogleVisionOCR instance with mock credentials."""
    return GoogleVisionOCR()

def test_init_with_credentials_path():
    """Test initialization with explicit credentials path."""
    ocr = GoogleVisionOCR(credentials_path='/test/path/credentials.json')
    assert isinstance(ocr.client, vision.ImageAnnotatorClient)

def test_init_without_credentials_path(mock_credentials):
    """Test initialization without explicit credentials path."""
    ocr = GoogleVisionOCR()
    assert isinstance(ocr.client, vision.ImageAnnotatorClient)

def test_extract_text_success(mock_vision_client, vision_ocr, tmp_path):
    """Test successful text extraction from an image."""
    # Create a test image file
    test_image = tmp_path / "test_receipt.jpg"
    test_image.write_bytes(b"dummy image content")
    
    # Mock the Vision API response
    mock_text = "Sample Receipt\nTotal: $10.99"
    mock_response = Mock()
    mock_response.full_text_annotation.text = mock_text
    mock_response.full_text_annotation.pages = [Mock()]
    mock_block = Mock()
    mock_block.bounding_box.vertices = [
        Mock(x=10, y=10),
        Mock(x=100, y=10),
        Mock(x=100, y=50),
        Mock(x=10, y=50)
    ]
    mock_block.paragraphs = [Mock()]
    mock_block.paragraphs[0].words = [Mock()]
    mock_block.paragraphs[0].words[0].symbols = [Mock()]
    mock_block.paragraphs[0].words[0].symbols[0].confidence = 0.95
    mock_response.full_text_annotation.pages[0].blocks = [mock_block]
    
    mock_vision_client.document_text_detection.return_value = mock_response
    
    # Test the extract_text method
    result = vision_ocr.extract_text(str(test_image))
    
    assert result["text"] == mock_text
    assert result["confidence"] > 0.9
    assert len(result["text_blocks"]) > 0
    assert "error" not in result

def test_extract_text_file_not_found(vision_ocr):
    """Test handling of non-existent image file."""
    result = vision_ocr.extract_text("/nonexistent/path/image.jpg")
    
    assert "error" in result
    assert "File not found" in result["error"]
    assert result["confidence"] == 0
    assert result["text"] == ""
    assert result["text_blocks"] == []

def test_extract_text_api_error(mock_vision_client, vision_ocr, tmp_path):
    """Test handling of API errors."""
    # Create a test image file
    test_image = tmp_path / "test_receipt.jpg"
    test_image.write_bytes(b"dummy image content")
    
    # Mock an API error
    mock_vision_client.document_text_detection.side_effect = Exception("API Error")
    
    result = vision_ocr.extract_text(str(test_image))
    
    assert "error" in result
    assert "API Error" in result["error"]
    assert result["confidence"] == 0
    assert result["text"] == ""
    assert result["text_blocks"] == []

def test_estimate_confidence(vision_ocr):
    """Test confidence score calculation."""
    # Create mock symbols with different confidence scores
    mock_symbols = [
        Mock(confidence=0.9),
        Mock(confidence=0.8),
        Mock(confidence=0.95)
    ]
    
    confidence = vision_ocr._estimate_confidence(mock_symbols)
    assert confidence == pytest.approx(0.8833, rel=1e-3)

def test_extract_text_blocks(vision_ocr):
    """Test extraction of text blocks with positions."""
    # Create mock blocks with positions
    mock_block1 = Mock()
    mock_block1.bounding_box.vertices = [
        Mock(x=10, y=10),
        Mock(x=100, y=10),
        Mock(x=100, y=50),
        Mock(x=10, y=50)
    ]
    mock_block1.paragraphs = [Mock()]
    mock_block1.paragraphs[0].words = [Mock()]
    mock_block1.paragraphs[0].words[0].symbols = [Mock(text="A")]
    
    mock_block2 = Mock()
    mock_block2.bounding_box.vertices = [
        Mock(x=20, y=60),
        Mock(x=110, y=60),
        Mock(x=110, y=100),
        Mock(x=20, y=100)
    ]
    mock_block2.paragraphs = [Mock()]
    mock_block2.paragraphs[0].words = [Mock()]
    mock_block2.paragraphs[0].words[0].symbols = [Mock(text="B")]
    
    mock_page = Mock()
    mock_page.blocks = [mock_block1, mock_block2]
    
    text_blocks = vision_ocr._extract_text_blocks([mock_page])
    
    assert len(text_blocks) == 2
    assert all(isinstance(block["position"], dict) for block in text_blocks)
    assert all(isinstance(block["text"], str) for block in text_blocks) 