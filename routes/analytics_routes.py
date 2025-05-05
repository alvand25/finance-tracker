"""Analytics routes for the finance tracker."""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request
from services.analytics_service import AnalyticsService

analytics_bp = Blueprint('analytics', __name__)
analytics_service = AnalyticsService()

@analytics_bp.route('/analytics')
def analytics_dashboard():
    """Render the analytics dashboard."""
    return render_template('analytics/dashboard.html')

@analytics_bp.route('/api/analytics/spending', methods=['GET'])
def get_spending_analytics():
    """Get spending analytics data."""
    # Parse date range from request
    end_date = datetime.now()
    period = request.args.get('period', 'month')
    months = int(request.args.get('months', '12'))
    start_date = end_date - timedelta(days=30*months)
    
    # Get analytics data
    spending_data = analytics_service.get_spending_by_period(
        start_date=start_date,
        end_date=end_date,
        group_by=period
    )
    
    store_data = analytics_service.get_store_analytics(
        start_date=start_date,
        end_date=end_date
    )
    
    category_data = analytics_service.get_category_breakdown(
        start_date=start_date,
        end_date=end_date
    )
    
    payment_data = analytics_service.get_payment_methods(
        start_date=start_date,
        end_date=end_date
    )
    
    trends_data = analytics_service.get_trends_analysis(
        start_date=start_date,
        end_date=end_date
    )
    
    return jsonify({
        'spending_by_period': spending_data,
        'store_analytics': store_data,
        'category_breakdown': category_data,
        'payment_methods': payment_data,
        'trends': trends_data
    }) 