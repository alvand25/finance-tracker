# Finance Tracker

A personal finance tracking application with a focus on shared expenses between two people.

## Features

- Track shared expenses between two users (Alvand and Roni)
- Automatically calculate how much one person owes the other
- View expense history by month
- Upload receipts (optional)
- Weekly and monthly summary emails

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Google Cloud Vision API credentials (for enhanced OCR)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/finance-tracker.git
   cd finance-tracker
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Copy the example environment file and update it with your settings:
   ```
   cp env.example .env
   # Edit .env with your preferred text editor
   ```

5. Create necessary directories:
   ```
   mkdir -p data uploads/receipts uploads/thumbnails
   ```

6. Set up Google Cloud Vision:
   ```
   # Run the setup script
   ./scripts/setup_google_vision.py
   
   # Test the setup (optional)
   ./scripts/test_vision_setup.py
   # Or test with a specific image:
   ./scripts/test_vision_setup.py --image path/to/test/image.jpg
   ```

### Running the Application

#### Web Interface

Run the Flask application:
```
flask run
```

Or directly with Python:
```
python app.py
```

The application will be available at http://localhost:5000

#### Command Line Interface

You can also use the application via a command-line interface:
```
python cli.py
```

### Running Tests

```
python -m unittest discover tests
```

## Project Structure

- `app.py`: Main application entry point (Flask web app)
- `cli.py`: Command-line interface
- `models/`: Data models for the application
- `storage/`: Storage implementation (JSON files)
- `utils/`: Utility functions for emails, receipts, etc.
- `templates/`: HTML templates for the web interface
- `tests/`: Unit tests

## How It Works

1. Each user (Alvand or Roni) can submit expenses with individual items
2. Items can be marked as "shared" or "personal"
3. The application calculates the shared portion of each expense
4. A running balance is maintained to track who owes whom
5. Monthly summaries are generated for settling up

## Future Plans

This is the first phase of a larger finance tracking application. Future features will include:
- Connecting with bank accounts
- Budget tracking
- Investment portfolio monitoring
- Net worth calculations 

# Enhanced Receipt Processing System

## Overview

The receipt processing system is a comprehensive solution for extracting, analyzing, and managing receipt data. It combines Optical Character Recognition (OCR) with advanced layout analysis and template-based recognition to accurately extract information from receipts.

## Key Features

### 1. Advanced OCR Processing
- Google Cloud Vision integration for high-accuracy OCR
- Tesseract OCR fallback for offline processing
- Image preprocessing with adaptive thresholding and deskewing
- Layout analysis for better understanding of receipt structure
- Multiple price pattern recognition for accurate item extraction

### 2. Template-Based Recognition
- Automatic template creation from processed receipts
- Template matching for familiar receipt layouts
- Version control for continuous template improvement

### 3. Progressive Processing
- Fast initial results for immediate feedback
- Detailed secondary processing for comprehensive data extraction
- Caching mechanisms for improved performance

### 4. Confidence Scoring
- Confidence metrics for all extracted data
- Field-specific confidence scores for granular quality assessment
- Reporting system for confidence levels

### 5. Error Handling
- Recovery strategies for partial OCR failures
- Missing field inference for incomplete data
- Validation of totals against item sums

## Configuration

### Google Cloud Vision Setup
1. Obtain Google Cloud Vision API credentials:
   - Create a project in Google Cloud Console
   - Enable the Cloud Vision API
   - Create a service account and download the JSON key file

2. Configure environment variables:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/credentials.json
   GOOGLE_VISION_API_ENDPOINT=https://vision.googleapis.com  # Optional
   GOOGLE_VISION_TIMEOUT=30  # Optional, in seconds
   GOOGLE_VISION_MAX_RETRIES=3  # Optional
   GOOGLE_VISION_BATCH_SIZE=10  # Optional
   ```

3. Test the setup:
   ```
   ./scripts/test_vision_setup.py
   ```

4. Verify OCR quality:
   ```python
   from ocr.google_vision_ocr import GoogleVisionOCR
   
   # Initialize OCR with credentials
   ocr = GoogleVisionOCR()
   
   # Process an image
   result = ocr.extract_text('path/to/image.jpg')
   print(f"Extracted text: {result['text']}")
   print(f"Confidence: {result['confidence']}")
   ```

### OCR Engine Selection
The system automatically selects the best available OCR engine:
1. If Google Cloud Vision is configured and accessible, it will be used as the primary engine
2. If Google Cloud Vision is not available or fails, Tesseract OCR will be used as a fallback
3. OCR engine selection can be manually controlled through environment variables

## Components

### Models
- `Receipt`: Core data model for receipt information
- `ReceiptItem`: Model for individual items on a receipt
- `ReceiptTemplate`: Model for storing and matching receipt layouts

### Services
- `ReceiptService`: Main service for receipt processing operations
- `TemplateRegistry`: Service for managing receipt templates

### Utilities
- `ReceiptAnalyzer`: Utility for OCR and text analysis

## API Endpoints

### Receipt Processing
- `POST /receipts/upload`: Upload and process a receipt image
- `POST /receipts/url`: Process a receipt from a URL
- `POST /receipts/complete/:receipt_id`: Complete detailed processing for a receipt

### Receipt Management
- `GET /receipts/:receipt_id`: Get a receipt by ID
- `DELETE /receipts/:receipt_id`: Delete a receipt
- `GET /receipts/confidence/:receipt_id`: Get confidence information for a receipt

### Template Management
- `GET /receipts/templates`: Get all receipt templates
- `GET /receipts/templates/:template_id`: Get a specific template
- `DELETE /receipts/templates/:template_id`: Delete a template

## Usage

### Regular Processing
```python
# Example of processing a receipt with Google Cloud Vision
from config.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR

# Initialize services
receipt_service = ReceiptService(
    storage,
    ocr_engine=GoogleVisionOCR(credentials_path=GoogleVisionConfig().credentials_path)
)

# Process a receipt
with open('receipt.jpg', 'rb') as f:
    image_data = f.read()
receipt = Receipt(image_url="receipt.jpg")
processed_receipt = receipt_service.process_receipt(receipt, image_data)

# Check OCR confidence
print(f"OCR Confidence: {processed_receipt.ocr_confidence:.2f}")
```

### Progressive Processing
```python
# Example of progressive processing with Google Cloud Vision
from config.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR

# Initialize services with Google Cloud Vision
receipt_service = ReceiptService(
    storage,
    ocr_engine=GoogleVisionOCR(credentials_path=GoogleVisionConfig().credentials_path)
)

# Start progressive processing
with open('receipt.jpg', 'rb') as f:
    image_data = f.read()
receipt = Receipt(image_url="receipt.jpg")
receipt, is_complete = receipt_service.process_receipt_progressive(receipt, image_data)

# Check initial results
print(f"Initial OCR Confidence: {receipt.ocr_confidence:.2f}")
print(f"Items found: {len(receipt.items)}")

# Later, complete the processing
if not is_complete:
    fully_processed = receipt_service.complete_progressive_processing(receipt.id)
    print(f"Final OCR Confidence: {fully_processed.ocr_confidence:.2f}")
    print(f"Total items found: {len(fully_processed.items)}")
```

### Direct OCR Usage
```python
# Example of using Google Cloud Vision OCR directly
from config.google_vision_config import GoogleVisionConfig
from ocr.google_vision_ocr import GoogleVisionOCR

# Initialize OCR with configuration
config = GoogleVisionConfig()
ocr = GoogleVisionOCR(credentials_path=config.credentials_path)

# Process an image
result = ocr.extract_text('receipt.jpg')

# Check results
if 'error' in result:
    print(f"Error: {result['error']}")
else:
    print(f"Extracted text: {result['text']}")
    print(f"OCR Confidence: {result['confidence']:.2f}")
    
    # Access text blocks with positions
    for block in result['text_blocks']:
        print(f"Text: {block['text']}")
        print(f"Position: {block['position']}")
        print(f"Confidence: {block['confidence']:.2f}")
```

## Implementation Details

The system combines several advanced techniques:
1. **Hybrid OCR with Layout Analysis**: Combines Google Cloud Vision's high-accuracy OCR with spatial analysis of text elements
2. **Template Recognition**: Identifies known receipt formats for optimized parsing
3. **Progressive Processing**: Provides immediate feedback with ongoing enhancements
4. **Confidence Metrics**: Offers transparent quality assessment of extracted data

This approach ensures high accuracy across a wide variety of receipt formats while providing excellent performance and user experience. 

# Receipt OCR System

A modular system for processing and extracting data from receipts of any vendor using OCR and specialized handling.

## Architecture

The Receipt OCR System is built with a modular, extensible architecture:

### Core Components

1. **Store Classifier**
   - Identifies the vendor from receipt text
   - Uses pattern matching and heuristics
   - References known store aliases from configuration

2. **Handler Framework**
   - `BaseReceiptHandler`: Interface for all vendor handlers
   - `HandlerRegistry`: Dynamically loads appropriate handlers
   - Vendor-specific handlers for Costco, Trader Joe's, etc.
   - `GenericHandler`: Robust fallback for unknown vendors

3. **Image Processing**
   - Contrast enhancement
   - Deskew operation
   - Border removal
   - Noise reduction

4. **Receipt Processor**
   - Main pipeline controller
   - Orchestrates image preprocessing, OCR, vendor detection, and data extraction
   - Implements fallback mechanisms for robust processing

### Directory Structure

```
finance-tracker/
├── handlers/                      # Vendor-specific handlers
│   ├── __init__.py                # Package initialization
│   ├── base_handler.py            # Base handler interface
│   ├── generic_handler.py         # Generic fallback handler
│   ├── costco_handler.py          # Costco-specific handler
│   ├── trader_joes_handler.py     # Trader Joe's-specific handler
│   └── ...                        # Other vendor-specific handlers
├── utils/
│   ├── image_preprocessor.py      # Image processing utilities
│   └── ...                        # Other utility modules
├── data/
│   ├── known_stores.json          # Store name aliases
│   └── ...                        # Other data files
├── receipt_processor.py           # Main processing controller
├── store_classifier.py            # Vendor classification module
└── ...                            # Other application files
```

## Features

- **Vendor Detection**: Automatically identifies receipt vendor with confidence scoring
- **Specialized Handling**: Vendor-specific extraction rules for improved accuracy
- **Robust Fallbacks**: Generic parser for unknown vendors
- **Image Enhancement**: Preprocessing for better OCR results
- **Debug Outputs**: Visual verification of processing steps
- **Confidence Scoring**: Quality assessment of extracted data

## Extending with New Vendors

To add support for a new vendor:

1. Create a new handler in `handlers/vendor_name_handler.py`
2. Implement the `BaseReceiptHandler` interface
3. Add store name aliases to `data/known_stores.json`
4. The system will automatically discover and utilize the new handler

## Usage

```python
from receipt_processor import ReceiptProcessor

# Initialize the processor
processor = ReceiptProcessor(debug_mode=True)

# Process a receipt image
results = processor.process_image("path/to/receipt.jpg")

# Extract data
items = results["items"]
total = results["total"]
store = results["store"]

# Process text directly
ocr_text = "... receipt text ..."
results = processor.process_text(ocr_text)
```

## Options

The processor supports various options:

- `debug_mode`: Output debug information
- `force_handler`: Force a specific vendor handler
- `force_currency`: Override detected currency
- `store_hint`: Provide a hint for store classification
- `confidence_threshold`: Set minimum confidence for results 

## Testing Receipt Handlers

### Unified Vendor Testing

The test system supports testing multiple receipt handler implementations with a single, unified approach:

```
tests/
└── test_vendor_handlers.py   # Parameterized tests for all handlers
```

Rather than maintaining separate test files for each vendor handler, our approach uses:

1. **Centralized Expected Results**: Each test image has a corresponding JSON file with expected extraction results
2. **Parameterized Testing**: Test functions support filtering by store name
3. **Timeout Protection**: Processing is wrapped with timeouts to prevent test hangs
4. **JSON Schema Validation**: Expected result files are validated against a schema

### Expected Results Format

Test expectations are stored in `samples/expected/` with filenames matching their corresponding images:

```
samples/expected/
├── IMG_5655.png.expected.json
├── IMG_5656.png.expected.json
└── ...
```

Each expected result file follows this format:

```json
{
  "store": "Costco",
  "items": [
    {
      "description": "ITEM NAME",
      "price": 19.99
    },
    ...
  ],
  "subtotal": 34.97,
  "tax": 2.80,
  "total": 37.77,
  "payment_method": "VISA",
  "timestamp": "2024-04-10T14:32:00",
  "check_items_exactly": true
}
```

### Running Tests

Use the test runner script for easy testing:

```bash
# Run all tests
./test_runner.py

# Test a specific store
./test_runner.py --store=costco

# Debug mode with verbose output
./test_runner.py --store=h_mart --debug -v

# Custom timeout
./test_runner.py --timeout=60
```

### Adding a New Store

To add support for testing a new store:

1. Add expected result files in `samples/expected/` for your test images
2. Add handler implementation in `handlers/<store>_handler.py`
3. Update store mappings in `handlers/handler_registry.py` if needed

The test framework will automatically detect and test your new handler. 

## OCR Configuration

The application supports two OCR engines:

1. **Google Cloud Vision OCR (Recommended)**
   - Higher accuracy and better text extraction
   - Requires Google Cloud credentials
   - Set up:
     1. Create a Google Cloud project
     2. Enable the Cloud Vision API
     3. Create a service account and download credentials
     4. Set environment variables:
        ```bash
        export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
        export GOOGLE_VISION_API_ENDPOINT=https://vision.googleapis.com  # Optional
        export GOOGLE_VISION_TIMEOUT=30  # Optional, default: 30
        export GOOGLE_VISION_MAX_RETRIES=3  # Optional, default: 3
        export GOOGLE_VISION_BATCH_SIZE=10  # Optional, default: 10
        ```

2. **Tesseract OCR (Fallback)**
   - Used when Google Cloud Vision is not configured
   - No additional setup required
   - Lower accuracy but works offline

The application will automatically use Google Cloud Vision if configured, otherwise falling back to Tesseract OCR. 

# Finance Tracker - Receipt OCR System

A system for processing receipt images using OCR to extract store information, items, and totals for personal finance tracking.

## Project Structure

The project follows a modular structure with clearly defined components:

### OCR Engines

- `ocr/google_vision_ocr.py`: Primary OCR engine using Google Cloud Vision
- `ocr/tesseract_ocr.py`: Fallback OCR using Tesseract
- Both engines provide a unified interface with confidence scores, text blocks, and error handling

### Receipt Processing Pipeline

- `receipt_processor.py`: Central controller for the receipt processing pipeline
- `utils/image_preprocessor.py`: Image enhancement using OpenCV and PIL
- `store_classifier.py`: Store identification using regex and keyword matching
- `handlers/`: Store-specific handlers for extracting items and totals
  - `handlers/costco_handler.py`: Costco-specific receipt handling
  - `handlers/h_mart_handler.py`: H-Mart-specific receipt handling
  - `handlers/generic_handler.py`: Generic receipt handling

### Testing

- `continuous_test_runner.py`: Modern test runner that monitors for code changes and automatically runs tests
- `scripts/test_vision_setup.py`: Environment validation for Google Cloud Vision

### Directories

- `samples/images/`: Test receipt images
- `test_results/`: JSON output from OCR and receipt processing
- `reports/`: HTML reports and visualizations

## Environment Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `env.example` to `.env` and configure as needed

### Google Cloud Vision Setup

1. Create a Google Cloud project
2. Enable the Vision API
3. Create a service account and download credentials JSON
4. Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to the path of your credentials JSON

## Usage

### Testing Receipt Processing

```bash
# Run continuous test runner (monitors code changes and processes samples/images/)
python continuous_test_runner.py

# Test Google Cloud Vision setup
python scripts/test_vision_setup.py
```

### Expected Test Output

- JSON results in the `test_results/` directory
- HTML reports in the `reports/` directory
- Logs in the `logs/` directory

## License

[MIT License](LICENSE)