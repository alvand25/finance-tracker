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
   cp .env.example .env
   # Edit .env with your preferred text editor
   ```

5. Create necessary directories:
   ```
   mkdir -p data uploads/receipts uploads/thumbnails
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
# Example of processing a receipt
receipt_service = ReceiptService(storage)
with open('receipt.jpg', 'rb') as f:
    image_data = f.read()
receipt = Receipt(image_url="receipt.jpg")
processed_receipt = receipt_service.process_receipt(receipt, image_data)
```

### Progressive Processing
```python
# Example of progressive processing
receipt_service = ReceiptService(storage)
with open('receipt.jpg', 'rb') as f:
    image_data = f.read()
receipt = Receipt(image_url="receipt.jpg")
receipt, is_complete = receipt_service.process_receipt_progressive(receipt, image_data)
# Later, complete the processing
if not is_complete:
    fully_processed = receipt_service.complete_progressive_processing(receipt.id)
```

## Implementation Details

The system combines several advanced techniques:
1. **Hybrid OCR with Layout Analysis**: Examines spatial relationships between text elements
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