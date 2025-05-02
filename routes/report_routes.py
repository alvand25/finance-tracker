"""
Routes for receipt processing reports.
"""

import os
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, current_app
from typing import Dict, Any

report_routes = Blueprint('report_routes', __name__)

@report_routes.route('/report/<filename>')
def view_report(filename: str):
    """
    Display a receipt processing report.
    
    Args:
        filename: The JSON results file to display
    """
    # Construct path to results file
    results_dir = os.path.join(current_app.root_path, 'results')
    results_file = os.path.join(results_dir, filename)
    
    if not os.path.exists(results_file):
        return jsonify({
            'error': 'Report not found',
            'filename': filename
        }), 404
    
    # Load results
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Add timestamp if not present
    if 'timestamp' not in results:
        results['timestamp'] = datetime.fromtimestamp(
            os.path.getmtime(results_file)
        ).isoformat()
    
    return render_template('receipt_report.html', results=results)

@report_routes.route('/reports')
def list_reports():
    """List all available receipt processing reports."""
    results_dir = os.path.join(current_app.root_path, 'results')
    
    if not os.path.exists(results_dir):
        return jsonify([])
    
    # Get all JSON files
    reports = []
    for filename in os.listdir(results_dir):
        if not filename.endswith('.json'):
            continue
            
        filepath = os.path.join(results_dir, filename)
        try:
            with open(filepath, 'r') as f:
                results = json.load(f)
                
            reports.append({
                'filename': filename,
                'timestamp': results.get('timestamp') or datetime.fromtimestamp(
                    os.path.getmtime(filepath)
                ).isoformat(),
                'store': results.get('store', 'Unknown'),
                'confidence': results.get('confidence', {}).get('overall', 0.0),
                'items_count': len(results.get('items', [])),
                'success': not results.get('error')
            })
        except Exception as e:
            current_app.logger.error(f"Error loading report {filename}: {str(e)}")
            continue
    
    # Sort by timestamp descending
    reports.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(reports)

@report_routes.route('/reports/latest')
def latest_report():
    """Get the most recent receipt processing report."""
    results_dir = os.path.join(current_app.root_path, 'results')
    
    if not os.path.exists(results_dir):
        return jsonify({'error': 'No reports found'}), 404
    
    # Find most recent JSON file
    latest = None
    latest_time = 0
    
    for filename in os.listdir(results_dir):
        if not filename.endswith('.json'):
            continue
            
        filepath = os.path.join(results_dir, filename)
        mtime = os.path.getmtime(filepath)
        
        if mtime > latest_time:
            latest = filename
            latest_time = mtime
    
    if not latest:
        return jsonify({'error': 'No reports found'}), 404
    
    # Redirect to the report view
    return view_report(latest) 