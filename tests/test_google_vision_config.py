"""Tests for Google Cloud Vision configuration."""
import os
import pytest
from config.google_vision_config import GoogleVisionConfig

@pytest.fixture
def mock_env(tmp_path):
    """Create a mock environment with test credentials."""
    # Create a dummy credentials file
    creds_file = tmp_path / "test_credentials.json"
    creds_file.write_text("{}")
    
    # Set up test environment variables
    test_env = {
        'GOOGLE_APPLICATION_CREDENTIALS': str(creds_file),
        'GOOGLE_VISION_API_ENDPOINT': 'https://test-endpoint',
        'GOOGLE_VISION_TIMEOUT': '60',
        'GOOGLE_VISION_MAX_RETRIES': '5',
        'GOOGLE_VISION_BATCH_SIZE': '20'
    }
    
    with pytest.MonkeyPatch().context() as mp:
        for key, value in test_env.items():
            mp.setenv(key, value)
        yield test_env

def test_init_with_env(mock_env):
    """Test initialization with environment variables."""
    config = GoogleVisionConfig()
    
    assert config.credentials_path == mock_env['GOOGLE_APPLICATION_CREDENTIALS']
    assert config.api_endpoint == mock_env['GOOGLE_VISION_API_ENDPOINT']
    assert config.timeout == 60
    assert config.max_retries == 5
    assert config.batch_size == 20

def test_init_defaults():
    """Test initialization with default values."""
    with pytest.MonkeyPatch().context() as mp:
        # Clear relevant environment variables
        mp.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
        mp.delenv('GOOGLE_VISION_API_ENDPOINT', raising=False)
        mp.delenv('GOOGLE_VISION_TIMEOUT', raising=False)
        mp.delenv('GOOGLE_VISION_MAX_RETRIES', raising=False)
        mp.delenv('GOOGLE_VISION_BATCH_SIZE', raising=False)
        
        config = GoogleVisionConfig()
        
        assert config.credentials_path is None
        assert config.api_endpoint is None
        assert config.timeout == 30  # default value
        assert config.max_retries == 3  # default value
        assert config.batch_size == 10  # default value

def test_is_configured(mock_env):
    """Test is_configured property."""
    config = GoogleVisionConfig()
    assert config.is_configured is True
    
    with pytest.MonkeyPatch().context() as mp:
        mp.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
        config = GoogleVisionConfig()
        assert config.is_configured is False

def test_validate_success(mock_env):
    """Test successful validation."""
    config = GoogleVisionConfig()
    config.validate()  # Should not raise any exceptions

def test_validate_missing_credentials():
    """Test validation with missing credentials."""
    with pytest.MonkeyPatch().context() as mp:
        mp.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
        config = GoogleVisionConfig()
        
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "credentials path not set" in str(exc_info.value)

def test_validate_invalid_credentials_path(tmp_path):
    """Test validation with non-existent credentials file."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv('GOOGLE_APPLICATION_CREDENTIALS', str(tmp_path / "nonexistent.json"))
        config = GoogleVisionConfig()
        
        with pytest.raises(FileNotFoundError) as exc_info:
            config.validate()
        assert "credentials file not found" in str(exc_info.value)

def test_validate_invalid_timeout(mock_env):
    """Test validation with invalid timeout."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv('GOOGLE_VISION_TIMEOUT', '0')
        config = GoogleVisionConfig()
        
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Timeout must be at least 1 second" in str(exc_info.value)

def test_validate_invalid_max_retries(mock_env):
    """Test validation with invalid max retries."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv('GOOGLE_VISION_MAX_RETRIES', '-1')
        config = GoogleVisionConfig()
        
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Max retries cannot be negative" in str(exc_info.value)

def test_validate_invalid_batch_size(mock_env):
    """Test validation with invalid batch size."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv('GOOGLE_VISION_BATCH_SIZE', '0')
        config = GoogleVisionConfig()
        
        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Batch size must be at least 1" in str(exc_info.value)

def test_to_dict(mock_env):
    """Test conversion to dictionary."""
    config = GoogleVisionConfig()
    config_dict = config.to_dict()
    
    assert config_dict['credentials_path'] == mock_env['GOOGLE_APPLICATION_CREDENTIALS']
    assert config_dict['api_endpoint'] == mock_env['GOOGLE_VISION_API_ENDPOINT']
    assert config_dict['timeout'] == 60
    assert config_dict['max_retries'] == 5
    assert config_dict['batch_size'] == 20

def test_from_dict():
    """Test creation from dictionary."""
    config_dict = {
        'credentials_path': '/path/to/credentials.json',
        'api_endpoint': 'https://custom-endpoint',
        'timeout': 45,
        'max_retries': 4,
        'batch_size': 15
    }
    
    config = GoogleVisionConfig.from_dict(config_dict)
    
    assert config.credentials_path == config_dict['credentials_path']
    assert config.api_endpoint == config_dict['api_endpoint']
    assert config.timeout == config_dict['timeout']
    assert config.max_retries == config_dict['max_retries']
    assert config.batch_size == config_dict['batch_size'] 