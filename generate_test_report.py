#!/usr/bin/env python3
"""
Generate HTML reports from receipt test results.

This script processes test results from the continuous test runner and generates
detailed HTML reports with confidence metrics and test statistics.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from jinja2 import Environment, FileSystemLoader

# Constants
RESULTS_DIR = "test_results"
REPORTS_DIR = "reports"
TEMPLATE_DIR = "templates"

def load_test_results() -> List[Dict]:
    """Load all test results from the results directory."""
    results = []
    results_path = Path(RESULTS_DIR)
    
    for result_file in results_path.glob("*.json"):
        with open(result_file) as f:
            results.append(json.load(f))
            
    # Sort by timestamp
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results

def calculate_statistics(results: List[Dict]) -> Dict:
    """Calculate overall test statistics."""
    stats = {
        "total_tests": len(results),
        "successful": 0,
        "failed": 0,
        "low_confidence": 0,
        "total_confidence": 0.0,
        "average_confidence": 0.0
    }
    
    for result in results:
        if result["status"] == "success":
            stats["successful"] += 1
            confidence = result["result"].get("confidence", {}).get("overall", 0.0)
            stats["total_confidence"] += confidence
        elif result["status"] == "low_confidence":
            stats["low_confidence"] += 1
            confidence = result["result"].get("confidence", {}).get("overall", 0.0)
            stats["total_confidence"] += confidence
        else:
            stats["failed"] += 1
            
    if stats["total_tests"] > 0:
        stats["average_confidence"] = (
            stats["total_confidence"] / 
            (stats["successful"] + stats["low_confidence"])
        )
        
    return stats

def format_confidence(confidence: float) -> str:
    """Format confidence score as percentage."""
    return f"{confidence * 100:.1f}%"

def generate_report(results: List[Dict], stats: Dict) -> str:
    """Generate HTML report from test results."""
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("test_report.html")
    
    return template.render(
        results=results,
        stats=stats,
        format_confidence=format_confidence,
        timestamp=datetime.now().isoformat()
    )

def save_report(html: str):
    """Save HTML report to file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(REPORTS_DIR) / f"test_report_{timestamp}.html"
    
    with open(report_path, "w") as f:
        f.write(html)
        
    print(f"Report saved to {report_path}")

def main():
    """Main entry point."""
    # Ensure directories exist
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Load results
    print("Loading test results...")
    results = load_test_results()
    
    if not results:
        print("No test results found.")
        return
        
    # Calculate statistics
    print("Calculating statistics...")
    stats = calculate_statistics(results)
    
    # Generate report
    print("Generating report...")
    html = generate_report(results, stats)
    
    # Save report
    save_report(html)

if __name__ == "__main__":
    main() 