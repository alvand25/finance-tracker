"""Enhanced test runner for receipt handler tests."""

import os
import sys
import unittest
import json
import csv
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import logging
from collections import defaultdict
import time

from handlers.handler_registry import get_handler, HandlerRegistry
from models.receipt import Receipt

logger = logging.getLogger(__name__)

class ReceiptTestRunner:
    """Enhanced test runner for receipt handler tests."""
    
    def __init__(self, test_data_dir: str = "tests/test_data"):
        """Initialize the test runner.
        
        Args:
            test_data_dir: Directory containing test data files.
        """
        self.test_data_dir = test_data_dir
        self.results: List[Dict[str, Any]] = []
        self.handler_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'avg_confidence': 0.0,
            'avg_processing_time': 0.0,
            'errors': []
        })
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def load_test_cases(self) -> List[Dict[str, Any]]:
        """Load test cases from CSV file."""
        test_cases = []
        csv_path = os.path.join(self.test_data_dir, "test_cases.csv")
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    test_cases.append({
                        'test_id': row['test_id'],
                        'store_name': row['store_name'],
                        'receipt_file': row['receipt_file'],
                        'expected_total': Decimal(row['expected_total']),
                        'expected_tax': Decimal(row['expected_tax']),
                        'expected_subtotal': Decimal(row['expected_subtotal']),
                        'expected_item_count': int(row['expected_item_count']),
                        'min_confidence': float(row['min_confidence']),
                        'expected_handler': row['expected_handler']
                    })
        except Exception as e:
            logger.error(f"Error loading test cases: {e}")
            sys.exit(1)
            
        return test_cases
    
    def run_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test case.
        
        Args:
            test_case: Dictionary containing test case data.
            
        Returns:
            Dictionary containing test results.
        """
        result = {
            'test_id': test_case['test_id'],
            'store_name': test_case['store_name'],
            'receipt_file': test_case['receipt_file'],
            'passed': False,
            'errors': [],
            'warnings': [],
            'processing_time': 0.0
        }
        
        try:
            # Read receipt text
            receipt_path = os.path.join(self.test_data_dir, test_case['receipt_file'])
            with open(receipt_path, 'r') as f:
                receipt_text = f.read()
            
            # Process receipt
            start_time = time.time()
            handler = get_handler(receipt_text)
            result['handler_used'] = handler.__class__.__name__
            
            # Verify correct handler was selected
            if handler.__class__.__name__ != test_case['expected_handler']:
                result['warnings'].append(
                    f"Wrong handler selected: expected {test_case['expected_handler']}, "
                    f"got {handler.__class__.__name__}"
                )
            
            receipt = handler.process_receipt(receipt_text)
            end_time = time.time()
            result['processing_time'] = end_time - start_time
            
            # Validate results
            result['confidence_score'] = receipt.confidence_score
            result['total_amount'] = str(receipt.total_amount)
            result['tax_amount'] = str(receipt.tax_amount)
            result['subtotal_amount'] = str(receipt.subtotal_amount)
            result['item_count'] = len(receipt.items)
            result['validation_notes'] = receipt.validation_notes
            result['requires_review'] = receipt.requires_review
            
            # Check confidence threshold
            if receipt.confidence_score < test_case['min_confidence']:
                result['errors'].append(
                    f"Confidence score {receipt.confidence_score:.2f} below minimum "
                    f"threshold {test_case['min_confidence']:.2f}"
                )
            
            # Check totals match
            if abs(receipt.total_amount - test_case['expected_total']) > Decimal('0.01'):
                result['errors'].append(
                    f"Total amount mismatch: expected {test_case['expected_total']}, "
                    f"got {receipt.total_amount}"
                )
            
            if abs(receipt.tax_amount - test_case['expected_tax']) > Decimal('0.01'):
                result['errors'].append(
                    f"Tax amount mismatch: expected {test_case['expected_tax']}, "
                    f"got {receipt.tax_amount}"
                )
            
            if abs(receipt.subtotal_amount - test_case['expected_subtotal']) > Decimal('0.01'):
                result['errors'].append(
                    f"Subtotal amount mismatch: expected {test_case['expected_subtotal']}, "
                    f"got {receipt.subtotal_amount}"
                )
            
            # Check item count
            if len(receipt.items) != test_case['expected_item_count']:
                result['errors'].append(
                    f"Item count mismatch: expected {test_case['expected_item_count']}, "
                    f"got {len(receipt.items)}"
                )
            
            # Update handler stats
            handler_name = handler.__class__.__name__
            self.handler_stats[handler_name]['total_tests'] += 1
            if not result['errors']:
                self.handler_stats[handler_name]['passed_tests'] += 1
                result['passed'] = True
            else:
                self.handler_stats[handler_name]['failed_tests'] += 1
                self.handler_stats[handler_name]['errors'].extend(result['errors'])
            
            # Update running averages
            prev_avg_conf = self.handler_stats[handler_name]['avg_confidence']
            prev_tests = self.handler_stats[handler_name]['total_tests']
            self.handler_stats[handler_name]['avg_confidence'] = (
                (prev_avg_conf * (prev_tests - 1) + receipt.confidence_score) / prev_tests
            )
            
            prev_avg_time = self.handler_stats[handler_name]['avg_processing_time']
            self.handler_stats[handler_name]['avg_processing_time'] = (
                (prev_avg_time * (prev_tests - 1) + result['processing_time']) / prev_tests
            )
            
        except Exception as e:
            result['errors'].append(f"Test execution error: {str(e)}")
            logger.error(f"Error running test {test_case['test_id']}: {e}", exc_info=True)
        
        return result
    
    def run_all_tests(self) -> None:
        """Run all test cases and collect results."""
        test_cases = self.load_test_cases()
        logger.info(f"Running {len(test_cases)} test cases...")
        
        for test_case in test_cases:
            result = self.run_test(test_case)
            self.results.append(result)
            
            # Log result
            status = "PASSED" if result['passed'] else "FAILED"
            logger.info(f"Test {result['test_id']} {status}")
            if result['errors']:
                for error in result['errors']:
                    logger.error(f"  Error: {error}")
            if result['warnings']:
                for warning in result['warnings']:
                    logger.warning(f"  Warning: {warning}")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive test report."""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['passed'])
        failed_tests = total_tests - passed_tests
        
        report = {
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': passed_tests / total_tests if total_tests > 0 else 0
            },
            'handler_stats': dict(self.handler_stats),
            'test_results': self.results
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], format: str = 'both') -> None:
        """Save the test report.
        
        Args:
            report: The test report to save.
            format: Output format ('json', 'text', or 'both').
        """
        # Save JSON report
        if format in ['json', 'both']:
            json_path = os.path.join(self.test_data_dir, 'test_report.json')
            try:
                with open(json_path, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
                logger.info(f"JSON report saved to {json_path}")
            except Exception as e:
                logger.error(f"Error saving JSON report: {e}")
        
        # Save text report
        if format in ['text', 'both']:
            text_path = os.path.join(self.test_data_dir, 'test_report.txt')
            try:
                with open(text_path, 'w') as f:
                    # Write summary
                    f.write("=== TEST SUMMARY ===\n")
                    f.write(f"Total Tests: {report['summary']['total_tests']}\n")
                    f.write(f"Passed Tests: {report['summary']['passed_tests']}\n")
                    f.write(f"Failed Tests: {report['summary']['failed_tests']}\n")
                    f.write(f"Success Rate: {report['summary']['success_rate']*100:.1f}%\n\n")
                    
                    # Write handler stats
                    f.write("=== HANDLER STATISTICS ===\n")
                    for handler, stats in report['handler_stats'].items():
                        f.write(f"\n{handler}:\n")
                        f.write(f"  Total Tests: {stats['total_tests']}\n")
                        f.write(f"  Passed Tests: {stats['passed_tests']}\n")
                        f.write(f"  Failed Tests: {stats['failed_tests']}\n")
                        f.write(f"  Average Confidence: {stats['avg_confidence']:.2f}\n")
                        f.write(f"  Average Processing Time: {stats['avg_processing_time']*1000:.1f}ms\n")
                        if stats['errors']:
                            f.write("  Errors:\n")
                            for error in stats['errors']:
                                f.write(f"    - {error}\n")
                    
                    # Write detailed test results
                    f.write("\n=== DETAILED TEST RESULTS ===\n")
                    for result in report['test_results']:
                        f.write(f"\nTest {result['test_id']} - {result['store_name']}\n")
                        f.write(f"  Status: {'PASSED' if result['passed'] else 'FAILED'}\n")
                        f.write(f"  Handler: {result['handler_used']}\n")
                        f.write(f"  Confidence: {result['confidence_score']:.2f}\n")
                        f.write(f"  Processing Time: {result['processing_time']*1000:.1f}ms\n")
                        if result['errors']:
                            f.write("  Errors:\n")
                            for error in result['errors']:
                                f.write(f"    - {error}\n")
                        if result['warnings']:
                            f.write("  Warnings:\n")
                            for warning in result['warnings']:
                                f.write(f"    - {warning}\n")
                
                logger.info(f"Text report saved to {text_path}")
            except Exception as e:
                logger.error(f"Error saving text report: {e}")

def main():
    """Run the test suite."""
    runner = ReceiptTestRunner()
    runner.run_all_tests()
    report = runner.generate_report()
    runner.save_report(report)
    
    # Print summary to console
    print("\n=== TEST SUMMARY ===")
    print(f"Total Tests: {report['summary']['total_tests']}")
    print(f"Passed Tests: {report['summary']['passed_tests']}")
    print(f"Failed Tests: {report['summary']['failed_tests']}")
    print(f"Success Rate: {report['summary']['success_rate']*100:.1f}%")
    
    # Exit with appropriate status code
    sys.exit(0 if report['summary']['failed_tests'] == 0 else 1)

if __name__ == '__main__':
    main() 