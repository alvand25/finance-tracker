#!/usr/bin/env python
"""
Batch testing script for OCR improvements.
Runs tests on multiple receipt images and generates aggregate statistics.
"""

import os
import logging
import argparse
import json
import glob
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
import matplotlib.pyplot as plt
from test_ocr_improvements import test_ocr_improvements

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("batch_ocr_test.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def analyze_batch_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze results from multiple test runs and generate aggregate statistics.
    
    Args:
        results: List of test results from individual images
        
    Returns:
        Dictionary containing aggregate statistics and analysis
    """
    # Extract metrics for analysis
    confidence_improvements = []
    item_improvements = []
    text_similarities = []
    completeness_improvements = []
    
    for result in results:
        improvements = result['improvements']
        if improvements['confidence'] is not None:
            confidence_improvements.append(improvements['confidence'])
        item_improvements.append(improvements['items'])
        if improvements['text_similarity'] is not None:
            text_similarities.append(improvements['text_similarity'])
            
        orig_completeness = result['original']['metrics']['completeness']
        impr_completeness = result['improved']['metrics']['completeness']
        completeness_change = ((impr_completeness - orig_completeness) / max(0.01, orig_completeness)) * 100
        completeness_improvements.append(completeness_change)
    
    # Calculate aggregate statistics
    stats = {
        'confidence': {
            'mean': pd.Series(confidence_improvements).mean(),
            'std': pd.Series(confidence_improvements).std(),
            'median': pd.Series(confidence_improvements).median(),
            'min': min(confidence_improvements) if confidence_improvements else None,
            'max': max(confidence_improvements) if confidence_improvements else None
        },
        'items': {
            'mean': pd.Series(item_improvements).mean(),
            'std': pd.Series(item_improvements).std(),
            'median': pd.Series(item_improvements).median(),
            'min': min(item_improvements),
            'max': max(item_improvements)
        },
        'text_similarity': {
            'mean': pd.Series(text_similarities).mean(),
            'std': pd.Series(text_similarities).std(),
            'median': pd.Series(text_similarities).median(),
            'min': min(text_similarities) if text_similarities else None,
            'max': max(text_similarities) if text_similarities else None
        },
        'completeness': {
            'mean': pd.Series(completeness_improvements).mean(),
            'std': pd.Series(completeness_improvements).std(),
            'median': pd.Series(completeness_improvements).median(),
            'min': min(completeness_improvements),
            'max': max(completeness_improvements)
        }
    }
    
    return stats

def generate_plots(results: List[Dict[str, Any]], output_dir: str):
    """Generate visualization plots for the test results."""
    # Create plots directory
    plots_dir = os.path.join(output_dir, "plots")
    if not os.path.exists(plots_dir):
        os.makedirs(plots_dir)
        
    # Prepare data
    data = {
        'confidence': [],
        'items': [],
        'completeness': [],
        'image_names': []
    }
    
    for result in results:
        image_name = os.path.basename(result['image_path'])
        data['image_names'].append(image_name)
        
        # Get improvements
        data['confidence'].append(result['improvements']['confidence'] or 0)
        data['items'].append(result['improvements']['items'])
        
        # Calculate completeness improvement
        orig_comp = result['original']['metrics']['completeness']
        impr_comp = result['improved']['metrics']['completeness']
        comp_change = ((impr_comp - orig_comp) / max(0.01, orig_comp)) * 100
        data['completeness'].append(comp_change)
    
    # Create bar plots
    metrics = ['confidence', 'items', 'completeness']
    for metric in metrics:
        plt.figure(figsize=(12, 6))
        plt.bar(range(len(data[metric])), data[metric])
        plt.title(f'{metric.title()} Improvement by Image')
        plt.xlabel('Image')
        plt.ylabel('Improvement (%)')
        plt.xticks(range(len(data['image_names'])), data['image_names'], rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(plots_dir, f'{metric}_improvements.png'))
        plt.close()
    
    # Create box plots
    plt.figure(figsize=(10, 6))
    plt.boxplot([data[m] for m in metrics], labels=[m.title() for m in metrics])
    plt.title('Distribution of Improvements')
    plt.ylabel('Improvement (%)')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'improvements_distribution.png'))
    plt.close()

def run_batch_tests(image_dir: str, output_dir: str = "batch_test_output", 
                   ground_truth_dir: str = None) -> Dict[str, Any]:
    """
    Run OCR tests on all images in the specified directory.
    
    Args:
        image_dir: Directory containing receipt images
        output_dir: Directory for test output
        ground_truth_dir: Optional directory containing ground truth JSON files
        
    Returns:
        Dictionary containing test results and statistics
    """
    # Create output directory
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Get list of image files
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_files.extend(glob.glob(os.path.join(image_dir, ext)))
    
    if not image_files:
        logger.error(f"No image files found in: {image_dir}")
        return None
    
    logger.info(f"Found {len(image_files)} images to process")
    
    # Process each image
    results = []
    for image_file in image_files:
        logger.info(f"\nProcessing: {image_file}")
        
        # Look for ground truth file if directory provided
        ground_truth = None
        if ground_truth_dir:
            base_name = os.path.splitext(os.path.basename(image_file))[0]
            truth_file = os.path.join(ground_truth_dir, f"{base_name}.json")
            if os.path.exists(truth_file):
                with open(truth_file, 'r') as f:
                    ground_truth = json.load(f)
        
        # Run test
        test_output_dir = os.path.join(output_dir, 
                                      os.path.splitext(os.path.basename(image_file))[0])
        result = test_ocr_improvements(image_file, test_output_dir, ground_truth)
        results.append(result)
    
    # Analyze results
    stats = analyze_batch_results(results)
    
    # Generate plots
    generate_plots(results, output_dir)
    
    # Save aggregate results
    aggregate_results = {
        'timestamp': datetime.now().isoformat(),
        'image_dir': image_dir,
        'num_images': len(image_files),
        'statistics': stats,
        'individual_results': results
    }
    
    results_file = os.path.join(output_dir, 
                               f"batch_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(results_file, 'w') as f:
        json.dump(aggregate_results, f, indent=2, default=str)
    
    # Log summary statistics
    logger.info("\n" + "=" * 80)
    logger.info("BATCH TEST SUMMARY")
    logger.info("=" * 80)
    
    for metric, values in stats.items():
        logger.info(f"\n{metric.title()} Improvements:")
        logger.info(f"  Mean: {values['mean']:+.1f}%")
        logger.info(f"  Median: {values['median']:+.1f}%")
        logger.info(f"  Std Dev: {values['std']:.1f}%")
        if values['min'] is not None and values['max'] is not None:
            logger.info(f"  Range: {values['min']:+.1f}% to {values['max']:+.1f}%")
    
    logger.info(f"\nDetailed results saved to: {results_file}")
    logger.info(f"Plots saved in: {os.path.join(output_dir, 'plots')}")
    
    return aggregate_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run batch OCR improvement tests")
    parser.add_argument("image_dir", help="Directory containing receipt images")
    parser.add_argument("--output-dir", default="batch_test_output",
                       help="Directory for test output")
    parser.add_argument("--ground-truth-dir",
                       help="Directory containing ground truth JSON files")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_dir):
        logger.error(f"Image directory not found: {args.image_dir}")
    else:
        run_batch_tests(args.image_dir, args.output_dir, args.ground_truth_dir) 