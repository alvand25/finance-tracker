#!/usr/bin/env python3
"""
Receipt Validator

Utility for validating receipt parsing results against expected values.
This tool helps verify that the receipt processing pipeline produces correct results.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class ReceiptValidator:
    """Validates receipt parsing results against expected values."""
    
    def __init__(self, expected_dir: str = "samples/expected"):
        """
        Initialize the validator with the directory containing expected results.
        
        Args:
            expected_dir: Path to directory with expected result JSON files
        """
        self.expected_dir = expected_dir
        
        # Create expected directory if it doesn't exist
        if not os.path.exists(expected_dir):
            os.makedirs(expected_dir)
            logger.info(f"Created expected results directory: {expected_dir}")
    
    def validate(self, receipt_id: str, parsed_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parsed receipt results against expected values.
        
        Args:
            receipt_id: Receipt ID or filename (without extension)
            parsed_results: The parsed receipt data to validate
            
        Returns:
            Dictionary with validation results
        """
        # Clean the receipt ID (remove file extension if present)
        receipt_id = os.path.splitext(os.path.basename(receipt_id))[0]
        
        # Path to expected results file
        expected_path = os.path.join(self.expected_dir, f"{receipt_id}.json")
        
        # Check if expected results file exists
        if not os.path.exists(expected_path):
            return {
                "status": "no_expected_file",
                "receipt_id": receipt_id,
                "message": f"No expected results file found for {receipt_id}"
            }
        
        # Load expected results
        try:
            with open(expected_path, 'r') as f:
                expected = json.load(f)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "receipt_id": receipt_id,
                "message": f"Failed to parse expected results JSON for {receipt_id}"
            }
        
        # Initialize validation results
        validation = {
            "status": "success",
            "receipt_id": receipt_id,
            "tests": []
        }
        
        # Validate store name
        self._validate_field(validation, "store_name", 
                             parsed_results.get("store_name"), 
                             expected.get("store_name"))
        
        # Validate currency
        self._validate_field(validation, "currency", 
                             parsed_results.get("currency"), 
                             expected.get("currency"))
        
        # Validate date
        self._validate_field(validation, "date", 
                             parsed_results.get("date"), 
                             expected.get("date"))
        
        # Validate payment method
        self._validate_field(validation, "payment_method", 
                             parsed_results.get("payment_method"), 
                             expected.get("payment_method"))
        
        # Validate totals
        self._validate_numeric(validation, "subtotal", 
                              parsed_results.get("subtotal"), 
                              expected.get("subtotal"),
                              tolerance=0.01)
        
        self._validate_numeric(validation, "tax", 
                              parsed_results.get("tax"), 
                              expected.get("tax"),
                              tolerance=0.01)
        
        self._validate_numeric(validation, "total", 
                              parsed_results.get("total"), 
                              expected.get("total"),
                              tolerance=0.01)
        
        # Validate item count
        parsed_item_count = len(parsed_results.get("items", []))
        expected_item_count = len(expected.get("items", []))
        
        self._validate_numeric(validation, "item_count", 
                              parsed_item_count, 
                              expected_item_count,
                              exact_match=True)
        
        # Validate specific items if both expected and parsed have items
        if expected.get("items") and parsed_results.get("items"):
            # For simplicity, just check a few sample items by description
            expected_items = {item.get("description", "").lower(): item 
                              for item in expected.get("items", [])}
            
            item_matches = 0
            for parsed_item in parsed_results.get("items", []):
                desc = parsed_item.get("description", "").lower()
                if desc in expected_items:
                    item_matches += 1
                    
                    # Validate item price
                    expected_price = expected_items[desc].get("price")
                    parsed_price = parsed_item.get("price")
                    
                    if expected_price is not None and parsed_price is not None:
                        price_match = abs(float(expected_price) - float(parsed_price)) <= 0.01
                    else:
                        price_match = expected_price == parsed_price
                    
                    validation["tests"].append({
                        "name": f"item_price:{desc}",
                        "passed": price_match,
                        "expected": expected_price,
                        "actual": parsed_price
                    })
            
            # Calculate item match percentage
            match_percentage = (item_matches / len(expected_items)) * 100 if expected_items else 0
            
            validation["tests"].append({
                "name": "item_match_percentage",
                "passed": match_percentage >= 50,  # Pass if at least 50% of items match
                "expected": "≥50%",
                "actual": f"{match_percentage:.1f}%"
            })
        
        # Calculate overall result
        passing_tests = sum(1 for test in validation["tests"] if test.get("passed"))
        total_tests = len(validation["tests"])
        
        if total_tests > 0:
            success_rate = (passing_tests / total_tests) * 100
            validation["passing_tests"] = passing_tests
            validation["total_tests"] = total_tests
            validation["success_rate"] = f"{success_rate:.1f}%"
            
            # Overall validation status
            if success_rate >= 80:
                validation["status"] = "success"
            elif success_rate >= 50:
                validation["status"] = "partial"
            else:
                validation["status"] = "failed"
        else:
            validation["status"] = "no_tests"
            validation["message"] = "No validation tests were performed"
        
        return validation
    
    def save_expected(self, receipt_id: str, parsed_results: Dict[str, Any]) -> str:
        """
        Save parsed results as the expected values for future validation.
        
        Args:
            receipt_id: Receipt ID or filename (without extension)
            parsed_results: The parsed receipt data to save as expected
            
        Returns:
            Path to the saved expected results file
        """
        # Clean the receipt ID (remove file extension if present)
        receipt_id = os.path.splitext(os.path.basename(receipt_id))[0]
        
        # Path to expected results file
        expected_path = os.path.join(self.expected_dir, f"{receipt_id}.json")
        
        # Save parsed results as expected
        with open(expected_path, 'w') as f:
            json.dump(parsed_results, f, indent=2)
        
        logger.info(f"Saved expected results for {receipt_id} to {expected_path}")
        
        return expected_path
    
    def _validate_field(self, validation: Dict[str, Any], field_name: str, 
                        actual_value: Any, expected_value: Any) -> None:
        """
        Validate a simple field value.
        
        Args:
            validation: Validation results dictionary to update
            field_name: Name of the field being validated
            actual_value: Actual value from parsed results
            expected_value: Expected value from reference data
        """
        # Skip validation if expected value is None or empty
        if expected_value is None or (isinstance(expected_value, str) and not expected_value.strip()):
            return
        
        # For string fields, do case-insensitive comparison
        if isinstance(expected_value, str) and isinstance(actual_value, str):
            passed = actual_value.lower() == expected_value.lower()
        else:
            passed = actual_value == expected_value
        
        validation["tests"].append({
            "name": field_name,
            "passed": passed,
            "expected": expected_value,
            "actual": actual_value
        })
    
    def _validate_numeric(self, validation: Dict[str, Any], field_name: str, 
                         actual_value: Any, expected_value: Any, 
                         tolerance: float = 0.0, exact_match: bool = False) -> None:
        """
        Validate a numeric field value with optional tolerance.
        
        Args:
            validation: Validation results dictionary to update
            field_name: Name of the field being validated
            actual_value: Actual value from parsed results
            expected_value: Expected value from reference data
            tolerance: Allowed difference between actual and expected values
            exact_match: Whether to require an exact match (ignores tolerance)
        """
        # Skip validation if expected value is None
        if expected_value is None:
            return
        
        try:
            actual_num = float(actual_value) if actual_value is not None else None
            expected_num = float(expected_value)
            
            if actual_num is None:
                passed = False
            elif exact_match:
                passed = actual_num == expected_num
            else:
                passed = abs(actual_num - expected_num) <= tolerance
                
            validation["tests"].append({
                "name": field_name,
                "passed": passed,
                "expected": expected_value,
                "actual": actual_value,
                "tolerance": None if exact_match else tolerance
            })
        except (ValueError, TypeError):
            # If values can't be converted to float, do direct comparison
            passed = actual_value == expected_value
            
            validation["tests"].append({
                "name": field_name,
                "passed": passed,
                "expected": expected_value,
                "actual": actual_value
            })


def save_validation_report(validation_results: List[Dict[str, Any]], output_dir: str = "samples/reports") -> str:
    """
    Save validation results to a JSON report file.
    
    Args:
        validation_results: List of validation result dictionaries
        output_dir: Directory to save the report
        
    Returns:
        Path to the saved report file
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Create report filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"validation_report_{timestamp}.json")
    
    # Compile overall statistics
    total_receipts = len(validation_results)
    passing_receipts = sum(1 for result in validation_results 
                          if result.get("status") == "success")
    partial_receipts = sum(1 for result in validation_results 
                          if result.get("status") == "partial")
    failed_receipts = sum(1 for result in validation_results 
                         if result.get("status") == "failed")
    
    # Create the report
    report = {
        "timestamp": timestamp,
        "summary": {
            "total_receipts": total_receipts,
            "passing_receipts": passing_receipts,
            "partial_receipts": partial_receipts,
            "failed_receipts": failed_receipts,
            "success_rate": f"{(passing_receipts / total_receipts) * 100:.1f}%" if total_receipts > 0 else "0.0%"
        },
        "results": validation_results
    }
    
    # Save the report
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Saved validation report to {report_path}")
    
    return report_path 