# Sample Images

This directory contains sample receipt images for testing the OCR and receipt processing functionality.

## Usage

Images placed in this directory will be automatically processed by:

```bash
python continuous_test_runner.py
```

## Naming Convention

- Use descriptive filenames that include the store name, e.g., `costco_receipt_01.jpg`
- Supported formats: JPG, PNG, TIFF

## Expected Output

- OCR and processing results will be saved to `test_results/`
- Visual reports will be saved to `reports/` 