"""Test configuration and fixtures."""
import os
import pytest
from unittest.mock import Mock, patch
from google.cloud import vision

@pytest.fixture
def mock_vision_client():
    """Create a mock Vision client."""
    with patch('google.cloud.vision.ImageAnnotatorClient') as mock_client:
        # Set up mock response
        mock_response = Mock()
        mock_response.full_text_annotation.text = "Sample Receipt\nTotal: $10.99"
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
        mock_block.paragraphs[0].words[0].symbols = [Mock(confidence=0.95)]
        mock_response.full_text_annotation.pages[0].blocks = [mock_block]
        
        mock_client.return_value.document_text_detection.return_value = mock_response
        yield mock_client.return_value

@pytest.fixture
def mock_credentials(tmp_path):
    """Create mock Google Cloud credentials."""
    creds_file = tmp_path / "test_credentials.json"
    creds_content = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "test-private-key",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "test-client-id",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test"
    }
    
    creds_file.write_text(str(creds_content))
    with patch.dict(os.environ, {'GOOGLE_APPLICATION_CREDENTIALS': str(creds_file)}):
        yield str(creds_file)

@pytest.fixture
def mock_vision_config():
    """Create mock Google Vision configuration."""
    with patch.dict(os.environ, {
        'GOOGLE_VISION_API_ENDPOINT': 'https://test-endpoint',
        'GOOGLE_VISION_TIMEOUT': '60',
        'GOOGLE_VISION_MAX_RETRIES': '5',
        'GOOGLE_VISION_BATCH_SIZE': '20'
    }):
        yield 