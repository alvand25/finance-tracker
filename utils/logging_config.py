"""Logging configuration for the receipt processing system."""

import os
import logging.config
import json
from datetime import datetime
from typing import Dict, Any

def setup_logging(
    log_dir: str = 'logs',
    debug_mode: bool = False,
    log_to_file: bool = True
) -> None:
    """
    Set up logging configuration for the application.
    
    Args:
        log_dir: Directory to store log files
        debug_mode: Whether to enable debug logging
        log_to_file: Whether to log to files
    """
    # Create logs directory if it doesn't exist
    if log_to_file and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Generate log filenames with timestamp
    timestamp = datetime.now().strftime('%Y%m%d')
    log_files = {
        'error': os.path.join(log_dir, f'error_{timestamp}.log'),
        'info': os.path.join(log_dir, f'info_{timestamp}.log'),
        'debug': os.path.join(log_dir, f'debug_{timestamp}.log')
    }
    
    # Define logging configuration
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
            },
            'json': {
                'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
                '()': 'utils.logging_config.JsonFormatter'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG' if debug_mode else 'INFO',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console'],
                'level': 'DEBUG' if debug_mode else 'INFO',
                'propagate': True
            },
            'ocr': {
                'handlers': ['console'],
                'level': 'DEBUG' if debug_mode else 'INFO',
                'propagate': False
            },
            'utils': {
                'handlers': ['console'],
                'level': 'DEBUG' if debug_mode else 'INFO',
                'propagate': False
            }
        }
    }
    
    # Add file handlers if logging to files
    if log_to_file:
        config['handlers'].update({
            'error_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'ERROR',
                'formatter': 'detailed',
                'filename': log_files['error'],
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'info_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'filename': log_files['info'],
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            },
            'debug_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'detailed',
                'filename': log_files['debug'],
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        })
        
        # Update logger handlers
        config['loggers']['']['handlers'].extend(['error_file', 'info_file'])
        if debug_mode:
            config['loggers']['']['handlers'].append('debug_file')
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info('Logging system initialized')
    if debug_mode:
        logger.debug('Debug mode enabled')

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        # Basic log record attributes
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        # Add custom fields if present
        if hasattr(record, 'data'):
            log_data['data'] = record.data
            
        return json.dumps(log_data)

def log_with_context(
    logger: logging.Logger,
    level: int,
    msg: str,
    context: Dict[str, Any] = None,
    **kwargs
) -> None:
    """
    Log message with additional context data.
    
    Args:
        logger: Logger instance
        level: Logging level
        msg: Log message
        context: Additional context data
        **kwargs: Additional logging arguments
    """
    if context:
        extra = {'data': context}
        if 'extra' in kwargs:
            kwargs['extra'].update(extra)
        else:
            kwargs['extra'] = extra
    
    logger.log(level, msg, **kwargs)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name) 