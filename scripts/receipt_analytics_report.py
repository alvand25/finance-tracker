#!/usr/bin/env python
"""
Receipt Analytics Report Generator

This script analyzes receipt OCR test results and generates analytics reports,
grouping results by store, confidence brackets, and success/failure rates.
"""

import os
import sys
import argparse
import json
import logging
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

# Add the parent directory to sys.path to allow imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('receipt_analytics')

# ANSI colors for terminal output
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

# Define confidence brackets
CONFIDENCE_BRACKETS = [
    {"name": "Very Low", "range": (0.0, 0.5), "color": Colors.RED},
    {"name": "Low", "range": (0.5, 0.75), "color": Colors.YELLOW},
    {"name": "Medium", "range": (0.75, 0.9), "color": Colors.BLUE},
    {"name": "High", "range": (0.9, 1.0), "color": Colors.GREEN}
]

def find_latest_test_log(logs_dir: str) -> str:
    """Find the most recent OCR test log file."""
    log_files = glob.glob(os.path.join(logs_dir, "ocr_test_*.json"))
    
    if not log_files:
        raise FileNotFoundError(f"No OCR test log files found in {logs_dir}")
    
    # Sort by modification time, newest first
    log_files.sort(key=os.path.getmtime, reverse=True)
    
    logger.info(f"Found latest log file: {log_files[0]}")
    return log_files[0]

def load_test_results(file_path: str) -> Dict[str, Any]:
    """Load OCR test results from a JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        logger.info(f"Loaded test results from {file_path}")
        return data
    except Exception as e:
        logger.error(f"Error loading test results: {str(e)}")
        raise

def get_confidence_bracket(confidence: float) -> Dict[str, Any]:
    """Get the confidence bracket for a confidence score."""
    for bracket in CONFIDENCE_BRACKETS:
        min_val, max_val = bracket["range"]
        if min_val <= confidence < max_val:
            return bracket
    # Default to the highest bracket if out of range
    return CONFIDENCE_BRACKETS[-1]

def get_store_display_name(store: Optional[str]) -> str:
    """Get a display name for a store, handling None values."""
    if store is None:
        return "Unknown"
    if store == "":
        return "Empty"
    return store

def get_performance_indicator(rate: float) -> str:
    """Get a visual indicator based on performance rate."""
    if rate >= 0.9:
        return "✅"  # Excellent
    elif rate >= 0.7:
        return "✓"   # Good
    elif rate >= 0.5:
        return "⚠️"  # Warning
    else:
        return "❌"  # Poor

def analyze_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze OCR test results and generate analytics.
    
    Args:
        results: Dictionary of test results
        
    Returns:
        Dictionary of analytics data
    """
    analytics = {
        "timestamp": datetime.now().isoformat(),
        "source_file": results.get("test_run_id", "unknown"),
        "overall": {
            "total_receipts": results.get("total_receipts", 0),
            "success_count": results.get("success_count", 0),
            "failure_count": results.get("failure_count", 0),
            "recovered_count": results.get("recovered_count", 0),
            "success_rate": results.get("success_rate", 0),
            "average_confidence": results.get("average_confidence", 0)
        },
        "by_store": defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "failure_count": 0,
            "total_confidence": 0,
            "success_rate": 0,
            "average_confidence": 0
        }),
        "by_confidence": defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0
        }),
        "top_errors": []
    }
    
    # Process results by receipt
    receipt_results = results.get("results", [])
    for receipt in receipt_results:
        store = get_store_display_name(receipt.get("store"))
        confidence = receipt.get("confidence", 0)
        success = receipt.get("success", False)
        bracket = get_confidence_bracket(confidence)["name"]
        
        # Update store stats
        analytics["by_store"][store]["count"] += 1
        if success:
            analytics["by_store"][store]["success_count"] += 1
            analytics["by_store"][store]["total_confidence"] += confidence
        else:
            analytics["by_store"][store]["failure_count"] += 1
            # Track errors
            if "error" in receipt and receipt["error"]:
                analytics["top_errors"].append({
                    "receipt_id": receipt.get("receipt_id", "unknown"),
                    "store": store,
                    "error": receipt["error"]
                })
        
        # Update confidence bracket stats
        analytics["by_confidence"][bracket]["count"] += 1
        if success:
            analytics["by_confidence"][bracket]["success_count"] += 1
        else:
            analytics["by_confidence"][bracket]["failure_count"] += 1
    
    # Calculate rates and averages for stores
    for store, stats in analytics["by_store"].items():
        if stats["count"] > 0:
            stats["success_rate"] = stats["success_count"] / stats["count"]
            if stats["success_count"] > 0:
                stats["average_confidence"] = stats["total_confidence"] / stats["success_count"]
    
    # Calculate rates for confidence brackets
    for bracket, stats in analytics["by_confidence"].items():
        if stats["count"] > 0:
            stats["success_rate"] = stats["success_count"] / stats["count"]
    
    # Convert defaultdicts to regular dicts for JSON serialization
    analytics["by_store"] = dict(analytics["by_store"])
    analytics["by_confidence"] = dict(analytics["by_confidence"])
    
    # Sort top errors by frequency (for now just take top 5)
    analytics["top_errors"] = analytics["top_errors"][:5]
    
    return analytics

def print_analytics_table(analytics: Dict[str, Any], use_color: bool = True) -> None:
    """Print analytics data in a formatted table."""
    if not use_color:
        # Disable colors
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, "")
    
    # Print header
    print(f"\n{Colors.BOLD}===== RECEIPT OCR ANALYTICS REPORT ====={Colors.RESET}")
    print(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Source: {analytics['source_file']}\n")
    
    # Print overall statistics
    overall = analytics["overall"]
    total = overall["total_receipts"]
    success_rate = overall["success_rate"]
    success_color = Colors.GREEN if success_rate >= 0.7 else (Colors.YELLOW if success_rate >= 0.5 else Colors.RED)
    
    print(f"{Colors.BOLD}Overall Statistics:{Colors.RESET}")
    print(f"Total Receipts: {total}")
    print(f"Success Rate: {success_color}{success_rate:.2%}{Colors.RESET} ({overall['success_count']}/{total})")
    print(f"Average Confidence: {overall['average_confidence']:.4f}")
    if overall.get("recovered_count", 0) > 0:
        print(f"Recovered Receipts: {Colors.BLUE}{overall['recovered_count']}{Colors.RESET}")
    
    # Print store statistics
    print(f"\n{Colors.BOLD}Performance by Store:{Colors.RESET}")
    print(f"{Colors.UNDERLINE}{'Store':<20} | {'Success Rate':<15} | {'Avg. Confidence':<15} | {'Count':<10}{Colors.RESET}")
    
    # Sort stores by success rate (descending)
    sorted_stores = sorted(
        analytics["by_store"].items(),
        key=lambda x: (x[1]["success_rate"], x[1]["average_confidence"]),
        reverse=True
    )
    
    for store, stats in sorted_stores:
        success_rate = stats["success_rate"]
        confidence = stats["average_confidence"]
        count = stats["count"]
        
        # Determine colors
        rate_color = Colors.GREEN if success_rate >= 0.7 else (Colors.YELLOW if success_rate >= 0.5 else Colors.RED)
        conf_color = Colors.GREEN if confidence >= 0.7 else (Colors.YELLOW if confidence >= 0.5 else Colors.RED)
        
        # Get performance indicator
        indicator = get_performance_indicator(success_rate)
        
        # Print row
        print(f"{store:<20} | {indicator} {rate_color}{success_rate:.2%}{Colors.RESET}  | " +
              f"{conf_color}{confidence:.4f}{Colors.RESET}    | {count}")
    
    # Print confidence bracket statistics
    print(f"\n{Colors.BOLD}Performance by Confidence Bracket:{Colors.RESET}")
    print(f"{Colors.UNDERLINE}{'Bracket':<15} | {'Success Rate':<15} | {'Count':<10}{Colors.RESET}")
    
    # Sort brackets by range (ascending)
    bracket_order = {bracket["name"]: i for i, bracket in enumerate(CONFIDENCE_BRACKETS)}
    sorted_brackets = sorted(
        analytics["by_confidence"].items(),
        key=lambda x: bracket_order.get(x[0], 999)
    )
    
    for bracket, stats in sorted_brackets:
        success_rate = stats["success_rate"]
        count = stats["count"]
        
        # Find bracket configuration
        bracket_config = next((b for b in CONFIDENCE_BRACKETS if b["name"] == bracket), CONFIDENCE_BRACKETS[0])
        rate_color = bracket_config["color"]
        
        # Get performance indicator
        indicator = get_performance_indicator(success_rate)
        
        # Print row
        print(f"{bracket:<15} | {indicator} {rate_color}{success_rate:.2%}{Colors.RESET}  | {count}")
    
    # Print top errors if any
    if analytics["top_errors"]:
        print(f"\n{Colors.BOLD}Top Errors:{Colors.RESET}")
        for i, error in enumerate(analytics["top_errors"], 1):
            print(f"{i}. Receipt: {error['receipt_id']} (Store: {error['store']})")
            print(f"   {Colors.RED}{error['error']}{Colors.RESET}")

def compare_test_logs(log1: Dict[str, Any], log2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two test logs and generate a diff report.
    
    Args:
        log1: Earlier test log
        log2: Later test log
        
    Returns:
        Dictionary with comparison results
    """
    comparison = {
        "timestamp": datetime.now().isoformat(),
        "log1_id": log1.get("test_run_id", "unknown"),
        "log2_id": log2.get("test_run_id", "unknown"),
        "overall_diff": {
            "success_rate_change": log2.get("success_rate", 0) - log1.get("success_rate", 0),
            "confidence_change": log2.get("average_confidence", 0) - log1.get("average_confidence", 0)
        },
        "receipts": {
            "improved": [],
            "worsened": [],
            "unchanged": []
        }
    }
    
    # Create lookup dictionaries by receipt_id
    log1_receipts = {r.get("receipt_id"): r for r in log1.get("results", [])}
    log2_receipts = {r.get("receipt_id"): r for r in log2.get("results", [])}
    
    # Find common receipt IDs
    common_ids = set(log1_receipts.keys()).intersection(set(log2_receipts.keys()))
    
    # Compare each receipt
    for receipt_id in common_ids:
        old = log1_receipts[receipt_id]
        new = log2_receipts[receipt_id]
        
        old_success = old.get("success", False)
        new_success = new.get("success", False)
        old_confidence = old.get("confidence", 0)
        new_confidence = new.get("confidence", 0)
        
        # Determine if improved, worsened, or unchanged
        if new_success and not old_success:
            comparison["receipts"]["improved"].append({
                "receipt_id": receipt_id,
                "reason": "Success status improved",
                "confidence_change": new_confidence - old_confidence
            })
        elif not new_success and old_success:
            comparison["receipts"]["worsened"].append({
                "receipt_id": receipt_id,
                "reason": "Success status worsened",
                "confidence_change": new_confidence - old_confidence
            })
        elif new_confidence > old_confidence + 0.05:  # Significant improvement
            comparison["receipts"]["improved"].append({
                "receipt_id": receipt_id,
                "reason": "Confidence significantly improved",
                "confidence_change": new_confidence - old_confidence
            })
        elif new_confidence < old_confidence - 0.05:  # Significant worsening
            comparison["receipts"]["worsened"].append({
                "receipt_id": receipt_id,
                "reason": "Confidence significantly worsened",
                "confidence_change": new_confidence - old_confidence
            })
        else:
            comparison["receipts"]["unchanged"].append({
                "receipt_id": receipt_id,
                "confidence_change": new_confidence - old_confidence
            })
    
    # Count changes
    comparison["counts"] = {
        "improved": len(comparison["receipts"]["improved"]),
        "worsened": len(comparison["receipts"]["worsened"]),
        "unchanged": len(comparison["receipts"]["unchanged"]),
        "new_receipts": len(set(log2_receipts.keys()) - set(log1_receipts.keys())),
        "removed_receipts": len(set(log1_receipts.keys()) - set(log2_receipts.keys()))
    }
    
    return comparison

def print_comparison(comparison: Dict[str, Any], use_color: bool = True) -> None:
    """Print a comparison report between two test logs."""
    if not use_color:
        # Disable colors
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, "")
    
    # Print header
    print(f"\n{Colors.BOLD}===== RECEIPT OCR COMPARISON REPORT ====={Colors.RESET}")
    print(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Comparing: {comparison['log1_id']} → {comparison['log2_id']}\n")
    
    # Print overall differences
    overall = comparison["overall_diff"]
    success_change = overall["success_rate_change"]
    confidence_change = overall["confidence_change"]
    
    success_color = Colors.GREEN if success_change > 0 else (Colors.RED if success_change < 0 else Colors.RESET)
    confidence_color = Colors.GREEN if confidence_change > 0 else (Colors.RED if confidence_change < 0 else Colors.RESET)
    
    print(f"{Colors.BOLD}Overall Changes:{Colors.RESET}")
    print(f"Success Rate: {success_color}{success_change:+.2%}{Colors.RESET}")
    print(f"Average Confidence: {confidence_color}{confidence_change:+.4f}{Colors.RESET}")
    
    # Print counts
    counts = comparison["counts"]
    print(f"\n{Colors.BOLD}Receipt Changes:{Colors.RESET}")
    print(f"{Colors.GREEN}Improved:{Colors.RESET} {counts['improved']}")
    print(f"{Colors.RED}Worsened:{Colors.RESET} {counts['worsened']}")
    print(f"{Colors.RESET}Unchanged:{Colors.RESET} {counts['unchanged']}")
    print(f"New Receipts: {counts['new_receipts']}")
    print(f"Removed Receipts: {counts['removed_receipts']}")
    
    # Print improved receipts
    if comparison["receipts"]["improved"]:
        print(f"\n{Colors.BOLD}{Colors.GREEN}Improved Receipts:{Colors.RESET}")
        for receipt in comparison["receipts"]["improved"]:
            print(f"- {receipt['receipt_id']}: {receipt['reason']} ({confidence_color}{receipt['confidence_change']:+.4f}{Colors.RESET})")
    
    # Print worsened receipts
    if comparison["receipts"]["worsened"]:
        print(f"\n{Colors.BOLD}{Colors.RED}Worsened Receipts:{Colors.RESET}")
        for receipt in comparison["receipts"]["worsened"]:
            print(f"- {receipt['receipt_id']}: {receipt['reason']} ({Colors.RED}{receipt['confidence_change']:+.4f}{Colors.RESET})")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Generate receipt OCR analytics report")
    
    parser.add_argument("--input", "-i", 
                       help="Input test log file (default: latest in logs/ directory)")
    parser.add_argument("--output", "-o",
                       help="Output JSON file for analytics summary (optional)")
    parser.add_argument("--no-color", action="store_true",
                       help="Disable colored output")
    parser.add_argument("--compare", "-c", nargs=2, metavar=('LOG1', 'LOG2'),
                       help="Compare two test logs")
    
    args = parser.parse_args()
    
    try:
        # Compare mode
        if args.compare:
            log1_path, log2_path = args.compare
            log1 = load_test_results(log1_path)
            log2 = load_test_results(log2_path)
            
            comparison = compare_test_logs(log1, log2)
            print_comparison(comparison, not args.no_color)
            
            # Save comparison report if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(comparison, f, indent=2)
                logger.info(f"Comparison report saved to {args.output}")
                
        # Regular analytics mode
        else:
            # Find the latest test log if not specified
            input_file = args.input
            if not input_file:
                input_file = find_latest_test_log("logs")
            
            # Load test results
            results = load_test_results(input_file)
            
            # Analyze results
            analytics = analyze_results(results)
            
            # Print analytics report
            print_analytics_table(analytics, not args.no_color)
            
            # Save analytics summary if requested
            if args.output:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = args.output
                with open(output_file, 'w') as f:
                    json.dump(analytics, f, indent=2)
                logger.info(f"Analytics summary saved to {output_file}")
                
    except Exception as e:
        logger.error(f"Error generating analytics report: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 