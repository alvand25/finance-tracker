import os
import time
import json
import pytest
from decimal import Decimal
from functools import partial
from receipt_processor import ReceiptProcessor
from handlers.handler_registry import HandlerRegistry

# Optional: Use jsonschema for validating expected result files
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Create a registry instance
registry = HandlerRegistry()

# Debug flag - can be set with environment variable
DEBUG_HANDLERS = os.getenv("DEBUG_HANDLERS", "0") == "1"
# Timeout for processing a receipt (in seconds)
RECEIPT_TIMEOUT = int(os.getenv("RECEIPT_TIMEOUT", "30"))
# Maximum allowed difference for price comparisons
PRICE_TOLERANCE = Decimal("0.05")

# Path to JSON schema for expected result files
SCHEMA_PATH = os.path.join("schemas", "expected_result_schema.json")

# Helper function to get all test images from samples/images directory
def get_test_images():
    images_dir = os.path.join('samples', 'images')
    if not os.path.exists(images_dir):
        return []
    return [
        os.path.join(images_dir, f) 
        for f in os.listdir(images_dir) 
        if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('.')
    ]

# Helper function to get expected results for a test image
def get_expected_results(image_path):
    # Expected results should be in samples/expected/<image_name>.png.expected.json
    base_name = os.path.basename(image_path)
    expected_path = os.path.join('samples', 'expected', f"{base_name}.expected.json")
    
    if not os.path.exists(expected_path):
        pytest.skip(f"No expected results found for {image_path}")
    
    with open(expected_path, 'r') as f:
        data = json.load(f)
    
    # Validate against JSON schema if available
    if HAS_JSONSCHEMA and os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, 'r') as schema_file:
            schema = json.load(schema_file)
        try:
            jsonschema.validate(data, schema)
        except jsonschema.exceptions.ValidationError as e:
            pytest.fail(f"JSON schema validation failed for {expected_path}: {e}")
    
    return data

def test_all_images_have_expected_results():
    """Test that all images have corresponding expected results files."""
    images = get_test_images()
    for image_path in images:
        base_name = os.path.basename(image_path)
        expected_path = os.path.join('samples', 'expected', f"{base_name}.expected.json")
        assert os.path.exists(expected_path), f"Missing expected results for {image_path}"

def test_expected_files_have_required_fields():
    """Test that all expected result files have the required fields."""
    images = get_test_images()
    required_fields = ['store', 'items', 'total']
    item_fields = ['description', 'price']
    
    for image_path in images:
        expected = get_expected_results(image_path)
        
        # Check top-level required fields
        for field in required_fields:
            assert field in expected, f"Missing required field '{field}' in {image_path}"
        
        # Check items structure
        assert isinstance(expected['items'], list), f"'items' must be a list in {image_path}"
        for i, item in enumerate(expected['items']):
            for field in item_fields:
                assert field in item, f"Missing required field '{field}' in item #{i} in {image_path}"

def process_with_timeout(processor, image_path, timeout=RECEIPT_TIMEOUT):
    """Process a receipt with a timeout to prevent hanging."""
    import threading
    import queue
    
    result_queue = queue.Queue()
    
    def _process():
        try:
            start_time = time.time()
            result = processor.process_image(image_path)
            elapsed = time.time() - start_time
            if DEBUG_HANDLERS or elapsed > 5:  # Log if debugging or slow (>5s)
                print(f"[DEBUG] Processed {os.path.basename(image_path)} in {elapsed:.2f} seconds")
            result_queue.put(("success", result))
        except Exception as e:
            result_queue.put(("error", str(e)))
    
    thread = threading.Thread(target=_process)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        # If still running after timeout, consider it failed
        error_msg = f"Receipt processing timed out after {timeout} seconds: {image_path}"
        print(f"[ERROR] {error_msg}")
        return {"error": error_msg, "items": [], "total": None}
    
    status, result = result_queue.get()
    if status == "error":
        print(f"[ERROR] Receipt processing failed: {result}")
        return {"error": result, "items": [], "total": None}
    
    return result

@pytest.mark.parametrize("store_filter", [None], indirect=False, ids=["all"])
def test_process_receipts(store_filter):
    """
    Test that all receipt images can be processed correctly.
    
    Args:
        store_filter: Optional store name to filter tests by
    """
    processor = ReceiptProcessor(debug_mode=DEBUG_HANDLERS)
    images = get_test_images()
    results = []
    
    for image_path in images:
        # Get expected results
        expected = get_expected_results(image_path)
        expected_store = expected["store"].lower()
        
        # Skip if a store filter is provided and doesn't match
        if store_filter and store_filter.lower() != expected_store:
            continue
        
        # Process the receipt with timeout
        start_time = time.time()
        result = process_with_timeout(processor, image_path)
        
        # Store result for summary report
        results.append({
            "image": os.path.basename(image_path),
            "store": expected_store,
            "success": "error" not in result,
            "time": time.time() - start_time,
            "expected_items": len(expected["items"]),
            "found_items": len(result.get("items", [])),
        })
        
        # Basic structure checks
        assert isinstance(result, dict), f"Result should be a dict for {image_path}"
        assert "store" in result, f"Result missing 'store' field for {image_path}"
        assert "items" in result, f"Result missing 'items' field for {image_path}"
        assert "total" in result, f"Result missing 'total' field for {image_path}"
        
        # Store name check
        assert result["store"].lower() == expected_store, \
            f"Store mismatch for {image_path}: expected {expected_store}, got {result['store']}"
        
        # Items check
        assert len(result["items"]) == len(expected["items"]), \
            f"Item count mismatch for {image_path}: expected {len(expected['items'])}, got {len(result['items'])}"
        
        # Total check (with tolerance for floating point)
        if expected["total"] is not None and result["total"] is not None:
            assert abs(Decimal(str(result["total"])) - Decimal(str(expected["total"]))) < PRICE_TOLERANCE, \
                f"Total mismatch for {image_path}: expected {expected['total']}, got {result['total']}"
        
        # Optional: Check individual items if they should match exactly
        if expected.get("check_items_exactly", False):
            for exp_item, res_item in zip(expected["items"], result["items"]):
                assert exp_item["description"].lower() == res_item["description"].lower(), \
                    f"Item description mismatch in {image_path}: expected '{exp_item['description']}', got '{res_item['description']}'"
                if exp_item["price"] is not None and res_item["price"] is not None:
                    assert abs(Decimal(str(exp_item["price"])) - Decimal(str(res_item["price"]))) < PRICE_TOLERANCE, \
                        f"Item price mismatch in {image_path}: expected {exp_item['price']}, got {res_item['price']}"
    
    # Print a summary of the results
    if DEBUG_HANDLERS:
        print("\n====== RECEIPT PROCESSING SUMMARY ======")
        print(f"Total images: {len(results)}")
        print(f"Successful: {sum(1 for r in results if r['success'])}")
        print(f"Failed: {sum(1 for r in results if not r['success'])}")
        print(f"Average processing time: {sum(r['time'] for r in results) / len(results):.2f}s")
        print("======================================\n")
        
        # Identify slow images (over 5 seconds)
        slow_results = [r for r in results if r['time'] > 5]
        if slow_results:
            print("Slow images (>5s):")
            for r in sorted(slow_results, key=lambda x: -x['time']):
                print(f"{r['image']} ({r['store']}): {r['time']:.2f}s - {r['found_items']}/{r['expected_items']} items")
            print()

def test_store_handlers_error_handling():
    """Test that all store handlers gracefully handle invalid input."""
    # Get a list of all unique stores from expected results
    stores = set()
    for image_path in get_test_images():
        expected = get_expected_results(image_path)
        stores.add(expected["store"].lower())
    
    for store_name in stores:
        handler = registry.get_handler_for_store(store_name)
        assert handler is not None, f"No handler found for store: {store_name}"
        
        # Test with empty string
        result = handler.process_receipt("")
        assert result["items"] == [], f"{store_name} handler should return empty items for empty input"
        assert result["total"] is None, f"{store_name} handler should return None total for empty input"
        
        # Test with invalid text
        result = handler.process_receipt("INVALID RECEIPT CONTENT")
        assert result["items"] == [], f"{store_name} handler should return empty items for invalid input"
        assert result["total"] is None, f"{store_name} handler should return None total for invalid input"

# Optional: Add specific test cases for edge cases or special features of each store
# This can be dynamically populated based on the stores found in the expected results
def test_store_specific_features():
    """Test store-specific features or edge cases."""
    
    # Get unique stores from expected results
    stores = set()
    for image_path in get_test_images():
        expected = get_expected_results(image_path)
        stores.add(expected["store"].lower())
    
    # Define special cases for known stores
    special_cases = {}
    special_cases["costco"] = [("membership_validation", "VALID MEMBER 12345", True)]
    special_cases["h_mart"] = [("korean_text_handling", "한글 텍스트", True)]
    special_cases["trader_joes"] = [("organic_item_detection", "ORGANIC BANANAS", True)]
    special_cases["key_food"] = [("loyalty_card_detection", "REWARDS CARD: 1234", True)]
    
    # Test applicable special cases
    for store_name in stores:
        store_name_lower = store_name.lower().replace('_', '')
        if store_name_lower in special_cases:
            handler = registry.get_handler_for_store(store_name)
            for feature, test_input, expected in special_cases[store_name_lower]:
                # Skip if handler doesn't support the feature
                if not hasattr(handler, feature):
                    pytest.skip(f"{store_name} handler doesn't support {feature}")
                
                result = getattr(handler, feature)(test_input)
                assert result == expected, f"{feature} test failed for {store_name}"

# Allow filtering tests by store name
def pytest_addoption(parser):
    parser.addoption("--store", action="store", default=None, 
                     help="Filter tests by store name (e.g., costco, h_mart)")

def pytest_generate_tests(metafunc):
    if "store_filter" in metafunc.fixturenames:
        store_filter = metafunc.config.getoption("store")
        if store_filter:
            metafunc.parametrize("store_filter", [store_filter], ids=[store_filter])
        else:
            metafunc.parametrize("store_filter", [None], ids=["all"]) 