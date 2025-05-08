#!/usr/bin/env python3
"""
Phase 8 CI Runner

This script orchestrates the end-to-end Phase 8 testing pipeline for the Receipt OCR system.
It runs regression monitoring, pattern debt analysis, confidence analytics, and optionally
promotes the snapshot to baseline if no regressions are detected.

Author: Alvand Daghoghi
Date: 2023-05-10
"""

import os
import sys
import argparse
import subprocess
import logging
from datetime import datetime
from pathlib import Path
import shutil
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("phase8_ci_runner")

# Constants
SNAPSHOTS_DIR = "regression_snapshots"
BASELINE_DIR = os.path.join(SNAPSHOTS_DIR, "baselines")
CURRENT_BASELINE = os.path.join(BASELINE_DIR, "current_baseline.json")
REPORTS_DIR = "ci_reports"
ANALYTICS_DIR = "analytics_results"
CI_LOGS_DIR = "ci_logs"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ANSI colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    @staticmethod
    def success(text):
        return f"{Colors.GREEN}✅ {text}{Colors.RESET}"

    @staticmethod
    def warning(text):
        return f"{Colors.YELLOW}⚠️ {text}{Colors.RESET}"

    @staticmethod
    def error(text):
        return f"{Colors.RED}❌ {text}{Colors.RESET}"

    @staticmethod
    def bold(text):
        return f"{Colors.BOLD}{text}{Colors.RESET}"

def ensure_dir(directory):
    """Ensure a directory exists."""
    os.makedirs(directory, exist_ok=True)

def run_command(cmd, description, show_output=True, check=True, force=False, log_file=None):
    """
    Run a command and handle its output.
    
    Args:
        cmd: Command list to run
        description: Description of the command
        show_output: Whether to show command output
        check: Whether to check the return code
        force: Whether to continue on error
        log_file: Optional path to log stdout and stderr
        
    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    logger.info(f"Running: {description}")
    logger.debug(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Always log the full output if a log file is specified
    if log_file:
        ensure_dir(os.path.dirname(log_file))
        with open(log_file, 'w') as f:
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Return code: {result.returncode}\n")
            f.write(f"Stdout:\n{result.stdout}\n")
            f.write(f"Stderr:\n{result.stderr}\n")
    
    if result.returncode == 0:
        print(Colors.success(f"{description} completed successfully"))
        if show_output and result.stdout:
            print(result.stdout.strip())
    else:
        print(Colors.error(f"{description} failed with code {result.returncode}"))
        print(result.stderr)
        
        if check and not force:
            print(Colors.error("Stopping pipeline. Use --force to continue on errors."))
            sys.exit(result.returncode)
    
    return result.returncode, result.stdout, result.stderr

def generate_snapshot(output_path, force=False):
    """
    Generate a fresh snapshot using test_runner.py.
    
    Args:
        output_path: Path to save the snapshot
        force: Whether to continue on error
        
    Returns:
        True if snapshot generation was successful, False otherwise
    """
    print(Colors.bold("\n== Generating Fresh Snapshot =="))
    
    # Ensure the directory exists
    ensure_dir(os.path.dirname(output_path))
    
    # Run test_runner.py
    cmd = [
        "python3", "test_runner.py",
        "--snapshot-path", output_path
    ]
    
    log_file = os.path.join(CI_LOGS_DIR, f"test_runner_{TIMESTAMP}.log")
    return_code, _, _ = run_command(
        cmd, "Generate snapshot", force=force, log_file=log_file
    )
    
    return return_code == 0

def run_regression_monitoring(snapshot_path, output_prefix, force=False):
    """
    Run regression monitoring against the current baseline.
    
    Args:
        snapshot_path: Path to the snapshot to test
        output_prefix: Prefix for output files
        force: Whether to continue on error
        
    Returns:
        Path to the regression report
    """
    print(Colors.bold("\n== Running Regression Monitoring =="))
    
    # Check if current baseline exists
    if not os.path.exists(CURRENT_BASELINE):
        print(Colors.warning("No current baseline found - skipping regression check"))
        return None
    
    # Output paths
    report_path = os.path.join(REPORTS_DIR, f"{output_prefix}_regression_report.html")
    
    # Run regression monitor
    cmd = [
        "python3", "regression_monitor.py",
        CURRENT_BASELINE,
        snapshot_path,
        "--output-prefix", output_prefix,
        "--ci-mode"
    ]
    
    log_file = os.path.join(CI_LOGS_DIR, f"regression_monitor_{TIMESTAMP}.log")
    return_code, stdout, _ = run_command(
        cmd, "Regression monitoring", force=force, log_file=log_file
    )
    
    # Check if report was generated
    if return_code == 0:
        # Try to find the report path from stdout
        html_path = None
        for line in stdout.splitlines():
            if "HTML:" in line:
                parts = line.split("HTML:")
                if len(parts) > 1:
                    html_path = parts[1].strip()
                    break
        
        if html_path and os.path.exists(html_path):
            # Copy to the reports directory
            ensure_dir(REPORTS_DIR)
            report_copy = os.path.join(REPORTS_DIR, f"{output_prefix}_regression_report.html")
            shutil.copy(html_path, report_copy)
            print(Colors.success(f"Regression report copied to: {report_copy}"))
            return report_copy
        
    return None

def run_pattern_debt_analysis(output_prefix, force=False):
    """
    Run pattern debt analysis.
    
    Args:
        output_prefix: Prefix for output files
        force: Whether to continue on error
        
    Returns:
        Tuple of (html_path, csv_path)
    """
    print(Colors.bold("\n== Running Pattern Debt Analysis =="))
    
    # Run pattern debt analyzer
    cmd = [
        "python3", "analyze_pattern_debt.py",
        "--output-prefix", output_prefix
    ]
    
    log_file = os.path.join(CI_LOGS_DIR, f"pattern_debt_{TIMESTAMP}.log")
    return_code, stdout, _ = run_command(
        cmd, "Pattern debt analysis", force=force, log_file=log_file
    )
    
    # Try to find report paths from stdout
    html_path = None
    csv_path = None
    
    if return_code == 0:
        for line in stdout.splitlines():
            if "HTML:" in line:
                parts = line.split("HTML:")
                if len(parts) > 1:
                    html_path = parts[1].strip()
            elif "CSV:" in line:
                parts = line.split("CSV:")
                if len(parts) > 1:
                    csv_path = parts[1].strip()
        
        # Copy to reports directory
        if html_path and os.path.exists(html_path):
            ensure_dir(REPORTS_DIR)
            html_copy = os.path.join(REPORTS_DIR, f"{output_prefix}_pattern_debt.html")
            shutil.copy(html_path, html_copy)
            html_path = html_copy
            print(Colors.success(f"Pattern debt HTML report copied to: {html_path}"))
            
        if csv_path and os.path.exists(csv_path):
            ensure_dir(REPORTS_DIR)
            csv_copy = os.path.join(REPORTS_DIR, f"{output_prefix}_pattern_debt.csv")
            shutil.copy(csv_path, csv_copy)
            csv_path = csv_copy
            print(Colors.success(f"Pattern debt CSV report copied to: {csv_path}"))
    
    return html_path, csv_path

def run_confidence_analysis(output_prefix, min_receipts=3, force=False):
    """
    Run confidence vs. match rate analytics.
    
    Args:
        output_prefix: Prefix for output files
        min_receipts: Minimum number of receipts per handler to include
        force: Whether to continue on error
        
    Returns:
        Tuple of (html_path, csv_path)
    """
    print(Colors.bold("\n== Running Confidence vs. Match Rate Analytics =="))
    
    # Run insights generator
    cmd = [
        "python3", "generate_insights.py",
        "--min-receipts", str(min_receipts),
        "--output-prefix", output_prefix
    ]
    
    log_file = os.path.join(CI_LOGS_DIR, f"generate_insights_{TIMESTAMP}.log")
    return_code, stdout, _ = run_command(
        cmd, "Confidence vs. match rate analytics", force=force, log_file=log_file
    )
    
    # Try to find report paths from stdout
    html_path = None
    csv_path = None
    
    if return_code == 0:
        for line in stdout.splitlines():
            if "HTML:" in line:
                parts = line.split("HTML:")
                if len(parts) > 1:
                    html_path = parts[1].strip()
            elif "CSV:" in line:
                parts = line.split("CSV:")
                if len(parts) > 1:
                    csv_path = parts[1].strip()
        
        # Copy to reports directory
        if html_path and os.path.exists(html_path):
            ensure_dir(REPORTS_DIR)
            html_copy = os.path.join(REPORTS_DIR, f"{output_prefix}_insights.html")
            shutil.copy(html_path, html_copy)
            html_path = html_copy
            print(Colors.success(f"Insights HTML report copied to: {html_path}"))
            
        if csv_path and os.path.exists(csv_path):
            ensure_dir(REPORTS_DIR)
            csv_copy = os.path.join(REPORTS_DIR, f"{output_prefix}_insights.csv")
            shutil.copy(csv_path, csv_copy)
            csv_path = csv_copy
            print(Colors.success(f"Insights CSV report copied to: {csv_path}"))
            
        # Extract top divergent receipts
        divergent_receipts = extract_divergent_receipts(stdout)
        if divergent_receipts:
            print(Colors.bold("\nTop Divergent Receipts:"))
            for receipt in divergent_receipts[:3]:  # Top 3
                confidence = receipt.get("confidence", 0)
                match_rate = receipt.get("match_rate", 0)
                divergence = receipt.get("divergence", 0)
                
                status = "🟢"  # Good
                if abs(divergence) > 0.15:
                    status = "🔴"  # Bad
                elif abs(divergence) > 0.05:
                    status = "🟡"  # Warning
                
                print(f"{status} {receipt.get('receipt_id', 'unknown')}: Confidence: {confidence:.3f}, Match Rate: {match_rate:.3f}, Divergence: {divergence:+.3f}")
    
    return html_path, csv_path

def extract_divergent_receipts(stdout):
    """
    Extract information about divergent receipts from stdout.
    
    Args:
        stdout: Command output
        
    Returns:
        List of divergent receipt info
    """
    receipts = []
    recording = False
    
    for line in stdout.splitlines():
        if "🔴" in line or "🟡" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                receipt_info = {}
                
                # Extract receipt ID
                receipt_id_part = parts[0].strip()
                receipt_id = receipt_id_part.replace("🔴", "").replace("🟡", "").strip()
                receipt_info["receipt_id"] = receipt_id
                
                # Extract metrics
                metrics_part = parts[1].strip()
                for metric in metrics_part.split(","):
                    metric = metric.strip()
                    if "Confidence:" in metric:
                        try:
                            receipt_info["confidence"] = float(metric.replace("Confidence:", "").strip())
                        except ValueError:
                            pass
                    elif "Match Rate:" in metric:
                        try:
                            receipt_info["match_rate"] = float(metric.replace("Match Rate:", "").strip())
                        except ValueError:
                            pass
                    elif "Divergence:" in metric:
                        try:
                            receipt_info["divergence"] = float(metric.replace("Divergence:", "").strip())
                        except ValueError:
                            pass
                
                receipts.append(receipt_info)
    
    # Sort by absolute divergence
    receipts.sort(key=lambda r: abs(r.get("divergence", 0)), reverse=True)
    return receipts

def promote_snapshot(snapshot_path, author, reason, force=False):
    """
    Promote a snapshot to baseline status.
    
    Args:
        snapshot_path: Path to the snapshot to promote
        author: Author of the promotion
        reason: Reason for promotion
        force: Whether to continue on error
        
    Returns:
        True if promotion was successful, False otherwise
    """
    print(Colors.bold("\n== Promoting Snapshot to Baseline =="))
    
    # Run snapshot promotion
    cmd = [
        "python3", "promote_snapshot.py",
        "--snapshot", snapshot_path,
        "--author", author,
        "--reason", reason
    ]
    
    log_file = os.path.join(CI_LOGS_DIR, f"promote_snapshot_{TIMESTAMP}.log")
    return_code, _, _ = run_command(
        cmd, "Snapshot promotion", force=force, log_file=log_file
    )
    
    return return_code == 0

def check_for_regressions(report_path):
    """
    Check if a regression report indicates any regressions.
    
    Args:
        report_path: Path to the regression report (HTML)
        
    Returns:
        True if no critical regressions, False otherwise
    """
    if not report_path or not os.path.exists(report_path):
        return False
    
    # Look for a JSON report with the same prefix
    json_path = report_path.replace(".html", ".json")
    
    if not os.path.exists(json_path):
        logger.warning(f"JSON regression report not found: {json_path}")
        return False
    
    try:
        with open(json_path, 'r') as f:
            report_data = json.load(f)
        
        # Check regression severity
        severity = report_data.get("regression_severity", "none")
        has_regression = report_data.get("has_regression", False)
        
        if severity == "critical" or severity == "major":
            return False
        elif has_regression:
            # Check key metrics
            key_metrics = [
                "store_classification_success_rate",
                "handler_selection_success_rate",
                "item_extraction_success_rate",
                "total_extraction_success_rate"
            ]
            
            metric_diffs = report_data.get("metric_diffs", {})
            
            for metric in key_metrics:
                if metric in metric_diffs and metric_diffs[metric] < -0.05:  # 5% decrease
                    return False
        
        return True
    except Exception as e:
        logger.error(f"Error checking regression report: {str(e)}")
        return False

def print_summary(results):
    """
    Print a summary of the results.
    
    Args:
        results: Dictionary of results
    """
    print(Colors.bold("\n====== Phase 8 CI Runner Summary ======"))
    print(f"Timestamp: {TIMESTAMP}")
    print(f"Snapshot: {results.get('snapshot_path', 'N/A')}")
    
    if results.get("generated_snapshot"):
        print(Colors.success("Generated new snapshot"))
    
    if results.get("regression_report"):
        print(f"Regression Report: {results['regression_report']}")
        print(f"Regression Status: {results.get('regression_status', 'Unknown')}")
    else:
        print("Regression Check: Skipped (no baseline)")
    
    if results.get("pattern_debt_html"):
        print(f"Pattern Debt Report: {results['pattern_debt_html']}")
    
    if results.get("insights_html"):
        print(f"Insights Report: {results['insights_html']}")
    
    if results.get("promoted"):
        print(Colors.success("Snapshot was promoted to baseline"))
    elif results.get("promotion_skipped"):
        print(Colors.warning("Snapshot promotion was skipped due to regressions"))
        
    print(f"\nLogs directory: {CI_LOGS_DIR}/")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Phase 8 CI Runner for Receipt OCR")
    parser.add_argument("--snapshot", help="Path to the snapshot file (if not provided, one will be generated)")
    parser.add_argument("--author", help="Author for snapshot promotion")
    parser.add_argument("--reason", help="Reason for snapshot promotion")
    parser.add_argument("--promote-if-clean", action="store_true", help="Promote snapshot if no regressions")
    parser.add_argument("--force", action="store_true", help="Continue even on error")
    parser.add_argument("--min-receipts", type=int, default=3, help="Minimum receipts for insights")
    parser.add_argument("--no-input", action="store_true", help="Non-interactive mode for CI environments")
    
    args = parser.parse_args()
    
    print(Colors.bold(f"Starting Phase 8 CI Runner (Timestamp: {TIMESTAMP})"))
    
    # Create necessary directories
    ensure_dir(REPORTS_DIR)
    ensure_dir(SNAPSHOTS_DIR)
    ensure_dir(BASELINE_DIR)
    ensure_dir(CI_LOGS_DIR)
    ensure_dir(ANALYTICS_DIR)
    
    # Initialize results
    results = {
        "timestamp": TIMESTAMP
    }
    
    # Generate snapshot if not provided
    if not args.snapshot:
        snapshot_path = os.path.join(SNAPSHOTS_DIR, f"ci_snapshot_{TIMESTAMP}.json")
        print(f"No snapshot specified, generating one at: {snapshot_path}")
        
        if generate_snapshot(snapshot_path, force=args.force):
            args.snapshot = snapshot_path
            results["generated_snapshot"] = True
        else:
            print(Colors.error("Failed to generate snapshot"))
            return 1
    else:
        # Check if provided snapshot exists
        if not os.path.exists(args.snapshot):
            print(Colors.error(f"Snapshot file not found: {args.snapshot}"))
            return 1
    
    # Store snapshot path in results
    results["snapshot_path"] = args.snapshot
    print(f"Using snapshot: {args.snapshot}")
    
    # Run regression monitoring
    if os.path.exists(CURRENT_BASELINE):
        results["regression_report"] = run_regression_monitoring(
            args.snapshot, f"ci_{TIMESTAMP}", force=args.force
        )
        
        if results["regression_report"]:
            no_regressions = check_for_regressions(results["regression_report"])
            results["regression_status"] = "Clean" if no_regressions else "Regressions Detected"
        else:
            results["regression_status"] = "Failed to generate report"
    else:
        print(Colors.warning("No current baseline found - skipping regression check"))
        # If no baseline, consider it clean for promotion purposes
        no_regressions = True
    
    # Run pattern debt analysis
    pattern_debt_html, pattern_debt_csv = run_pattern_debt_analysis(
        f"ci_{TIMESTAMP}", force=args.force
    )
    results["pattern_debt_html"] = pattern_debt_html
    results["pattern_debt_csv"] = pattern_debt_csv
    
    # Run confidence analysis
    insights_html, insights_csv = run_confidence_analysis(
        f"ci_{TIMESTAMP}", args.min_receipts, force=args.force
    )
    results["insights_html"] = insights_html
    results["insights_csv"] = insights_csv
    
    # Promote snapshot if requested and no regressions
    if args.promote_if_clean:
        if not args.author or not args.reason:
            print(Colors.error("Author and reason are required for promotion"))
            results["promoted"] = False
            results["promotion_skipped"] = True
        elif os.path.exists(CURRENT_BASELINE) and not no_regressions:
            print(Colors.warning("Skipping promotion due to regressions"))
            results["promoted"] = False
            results["promotion_skipped"] = True
        else:
            results["promoted"] = promote_snapshot(
                args.snapshot, args.author, args.reason, force=args.force
            )
    
    # Print summary
    print_summary(results)
    
    # Return appropriate exit code
    if os.path.exists(CURRENT_BASELINE) and "regression_status" in results:
        if results["regression_status"] != "Clean":
            return 1
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(Colors.warning("\nCI Runner interrupted by user"))
        sys.exit(130)
    except Exception as e:
        logger.exception("Unhandled exception")
        print(Colors.error(f"CI Runner failed: {str(e)}"))
        sys.exit(1) 