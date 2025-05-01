# Receipt OCR System Debugging Guide

This guide explains how to use the enhanced debugging features to diagnose issues with the receipt OCR system.

## Overview of Issues

Recent tests across receipt images show repeated failures with the same pattern:
- Store classification fails entirely ("Unknown store type")
- 0 items detected
- No totals extracted
- Confidence is defaulted to 0.70 or 0.0

This indicates possible issues with:
1. OCR text extraction from images
2. Store classification logic
3. Handler selection
4. Item and total extraction patterns

## Using the Debug Tools

### Running the Debug Test Script

The `debug_test_samples.py` script provides detailed logging and generates HTML reports:

```bash
# Run with default settings
python debug_test_samples.py

# Run with specific samples directory
python debug_test_samples.py --samples-dir path/to/samples

# Run with HTML report generation
python debug_test_samples.py --html-report

# Run with store hint (forces all samples to try specific store handler)
python debug_test_samples.py --store-hint costco

# Run with recursive subdirectory scanning
python debug_test_samples.py --recursive

# Specify a specific images subdirectory
python debug_test_samples.py --images-subdir images

# Process a single image file
python debug_test_samples.py --single-image samples/images/IMG_5655.jpg

# Combine options
python debug_test_samples.py --samples-dir samples --images-subdir receipts --html-report --store-hint costco
```

### Common Directory Structures

The script is smart enough to handle different directory structures:

1. Images directly in samples directory:
   ```
   samples/
   ├── image1.jpg
   ├── image2.jpg
   └── image3.jpg
   ```

2. Images in an "images" subdirectory (auto-detected):
   ```
   samples/
   └── images/
       ├── image1.jpg
       ├── image2.jpg
       └── image3.jpg
   ```

3. Images in various nested subdirectories (use `--recursive`):
   ```
   samples/
   ├── costco/
   │   ├── image1.jpg
   │   └── image2.jpg
   └── target/
       ├── image3.jpg
       └── image4.jpg
   ```

### Debug Output

The debug tools generate the following outputs:

1. **Debug Log File**: `debug_test.log` contains detailed logs from all components
2. **Debug Output Directory**: `debug_output/` contains:
   - Original and preprocessed images 
   - OCR text extracted from each image
   - JSON results for each receipt
   - Error logs for failed processing
   - HTML report with side-by-side comparisons (if enabled)

### Examining Debug Data

1. **Check OCR Text**:
   - Review the OCR text files to see if text extraction is working
   - Look for store name, items, and totals in the raw text

2. **Check Store Classification**:
   - Look for `[Classifier]` logs in the debug log
   - Check which aliases were matched or not matched
   - Verify if the correct store type is being identified

3. **Check Handler Selection**:
   - Look for `[Registry]` logs to see which handler was selected
   - Check if fallback to the generic handler is occurring

4. **Check Item Extraction**:
   - Look for `[GenericHandler]` logs showing which lines matched regex patterns
   - Identify price-looking lines that didn't match existing patterns

## Addressing Common Issues

### Store Classification Failures

- Check if OCR text contains store names
- Update `known_stores.json` with additional aliases
- Add store-specific patterns to `_check_special_patterns()`

### Missing Items

- Check if OCR correctly extracted item lines with prices
- Review regex patterns in `extract_items()` to ensure they match your receipt formats
- Add additional patterns for specific store formats

### Missing Totals

- Check if OCR text includes total information
- Add patterns to match different total formats
- Check currency symbol handling in the preprocessing

## Next Steps After Debugging

Once you've identified specific issues:

1. Update regex patterns in the appropriate handler
2. Add more store aliases to improve classification
3. Enhance image preprocessing if OCR quality is poor
4. Consider implementing store-specific handlers for problematic formats

## Troubleshooting

If you're having trouble finding images:

1. Check that the images exist in the expected directory
2. Try using `--recursive` to scan all subdirectories
3. Specify the exact path with `--samples-dir samples/images`
4. Use `--images-subdir images` if your images are in a subdirectory called "images"
5. Process a single image with `--single-image path/to/image.jpg` to verify the system works

If no items are extracted:

1. Check the OCR text files in the debug output to verify text extraction is working
2. Use `--store-hint costco` to force a specific handler
3. Analyze the debug logs for pattern matching failures 