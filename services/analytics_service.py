"""
Analytics Service Module

This module provides data aggregation and analysis services for the finance tracker
analytics dashboard. It processes receipt data to generate insights about spending
patterns, store frequencies, and expense categories.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

class AnalyticsService:
    def __init__(self, data_dir: str = "data/receipts"):
        """Initialize the analytics service with the data directory."""
        self.data_dir = data_dir
        
    def get_spending_by_period(self, start_date: datetime, end_date: datetime,
                             group_by: str = "month") -> Dict[str, float]:
        """
        Get total spending grouped by time period.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            group_by: Time grouping ('day', 'week', 'month', 'year')
            
        Returns:
            Dictionary mapping time periods to total spending
        """
        spending = defaultdict(float)
        
        # Load all receipt data within the date range
        for receipt in self._load_receipts(start_date, end_date):
            period_key = self._get_period_key(receipt["date"], group_by)
            spending[period_key] += receipt.get("total", 0.0)
            
        return dict(spending)
    
    def get_store_analytics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Get analytics grouped by store.
        
        Returns:
            Dictionary containing store-specific analytics:
            - visit_count: Number of visits per store
            - total_spent: Total amount spent at each store
            - average_basket: Average basket size
            - popular_items: Most frequently purchased items
        """
        store_stats = defaultdict(lambda: {
            "visit_count": 0,
            "total_spent": 0.0,
            "basket_sizes": [],
            "items": defaultdict(int)
        })
        
        for receipt in self._load_receipts(start_date, end_date):
            store = receipt.get("store", "Unknown")
            store_stats[store]["visit_count"] += 1
            store_stats[store]["total_spent"] += receipt.get("total", 0.0)
            store_stats[store]["basket_sizes"].append(len(receipt.get("items", [])))
            
            # Track item frequencies
            for item in receipt.get("items", []):
                store_stats[store]["items"][item["name"]] += 1
        
        # Calculate averages and get popular items
        results = {}
        for store, stats in store_stats.items():
            basket_sizes = stats["basket_sizes"]
            avg_basket = sum(basket_sizes) / len(basket_sizes) if basket_sizes else 0
            
            # Get top 5 popular items
            popular_items = sorted(
                stats["items"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            results[store] = {
                "visit_count": stats["visit_count"],
                "total_spent": stats["total_spent"],
                "average_basket": avg_basket,
                "popular_items": dict(popular_items)
            }
        
        return results
    
    def get_category_breakdown(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """
        Get spending breakdown by category.
        
        Returns:
            Dictionary mapping categories to total amounts
        """
        categories = defaultdict(float)
        
        for receipt in self._load_receipts(start_date, end_date):
            for item in receipt.get("items", []):
                category = item.get("category", "Uncategorized")
                categories[category] += item.get("price", 0.0)
                
        return dict(categories)
    
    def get_payment_methods(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Get analytics about payment methods used.
        
        Returns:
            Dictionary containing payment method statistics:
            - usage_count: Number of times each method was used
            - total_amount: Total amount paid with each method
        """
        payment_stats = defaultdict(lambda: {
            "usage_count": 0,
            "total_amount": 0.0
        })
        
        for receipt in self._load_receipts(start_date, end_date):
            method = receipt.get("payment_method", "Unknown")
            payment_stats[method]["usage_count"] += 1
            payment_stats[method]["total_amount"] += receipt.get("total", 0.0)
            
        return dict(payment_stats)
    
    def get_trends_analysis(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Analyze spending trends and patterns.
        
        Returns:
            Dictionary containing trend analysis:
            - spending_trend: Month-over-month spending changes
            - frequent_stores: Most frequently visited stores
            - largest_expenses: Largest individual expenses
            - busy_days: Busiest shopping days
        """
        monthly_spending = defaultdict(float)
        store_visits = defaultdict(int)
        large_expenses = []
        day_counts = defaultdict(int)
        
        for receipt in self._load_receipts(start_date, end_date):
            # Track monthly spending
            month_key = receipt["date"].strftime("%Y-%m")
            monthly_spending[month_key] += receipt.get("total", 0.0)
            
            # Track store visits
            store = receipt.get("store", "Unknown")
            store_visits[store] += 1
            
            # Track large expenses
            total = receipt.get("total", 0.0)
            if len(large_expenses) < 5:
                large_expenses.append((store, total, receipt["date"]))
                large_expenses.sort(key=lambda x: x[1], reverse=True)
            elif total > large_expenses[-1][1]:
                large_expenses[-1] = (store, total, receipt["date"])
                large_expenses.sort(key=lambda x: x[1], reverse=True)
            
            # Track busy days
            day_key = receipt["date"].strftime("%A")
            day_counts[day_key] += 1
        
        # Calculate month-over-month changes
        spending_trend = []
        months = sorted(monthly_spending.keys())
        for i in range(1, len(months)):
            prev_month = monthly_spending[months[i-1]]
            curr_month = monthly_spending[months[i]]
            if prev_month > 0:
                change = ((curr_month - prev_month) / prev_month) * 100
            else:
                change = 100
            spending_trend.append({
                "month": months[i],
                "change": change
            })
        
        return {
            "spending_trend": spending_trend,
            "frequent_stores": dict(sorted(store_visits.items(), key=lambda x: x[1], reverse=True)[:5]),
            "largest_expenses": [
                {"store": store, "amount": amount, "date": date.strftime("%Y-%m-%d")}
                for store, amount, date in large_expenses
            ],
            "busy_days": dict(sorted(day_counts.items(), key=lambda x: x[1], reverse=True))
        }
    
    def _load_receipts(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Load all receipt data within the given date range."""
        receipts = []
        
        # Walk through the data directory
        for root, _, files in os.walk(self.data_dir):
            for file in files:
                if not file.endswith('.json'):
                    continue
                    
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        receipt = json.load(f)
                        
                    # Convert date string to datetime
                    receipt["date"] = datetime.strptime(receipt["date"], "%Y-%m-%d")
                    
                    # Check if receipt is within date range
                    if start_date <= receipt["date"] <= end_date:
                        receipts.append(receipt)
                except Exception as e:
                    print(f"Error loading receipt {file}: {str(e)}")
                    continue
        
        return receipts
    
    def _get_period_key(self, date: datetime, group_by: str) -> str:
        """Get the period key for a date based on grouping."""
        if group_by == "day":
            return date.strftime("%Y-%m-%d")
        elif group_by == "week":
            return f"{date.year}-W{date.isocalendar()[1]}"
        elif group_by == "month":
            return date.strftime("%Y-%m")
        elif group_by == "year":
            return str(date.year)
        else:
            raise ValueError(f"Invalid group_by value: {group_by}") 