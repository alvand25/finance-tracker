import datetime
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from models.expense import BalanceSheet
from storage.base import StorageBase
from utils.email_service import EmailService


class Scheduler:
    """Scheduler for running tasks at specified intervals."""
    
    def __init__(self, storage: StorageBase, email_service: EmailService):
        self.storage = storage
        self.email_service = email_service
        self.running = False
        self.thread = None
        self.logger = logging.getLogger(__name__)
        
    def _get_current_month(self) -> str:
        """Get the current month in YYYY-MM format."""
        now = datetime.datetime.now()
        return now.strftime("%Y-%m")
    
    def _is_last_week_of_month(self) -> bool:
        """Check if it's the last week of the month."""
        now = datetime.datetime.now()
        # Get the last day of the month
        next_month = now.replace(day=28) + datetime.timedelta(days=4)
        last_day = next_month - datetime.timedelta(days=next_month.day)
        
        # If we're within 7 days of the last day, it's the last week
        return (last_day.day - now.day) <= 7
    
    def _is_sunday(self) -> bool:
        """Check if today is Sunday."""
        return datetime.datetime.now().weekday() == 6
    
    def _run_scheduler(self) -> None:
        """Main scheduler loop."""
        self.logger.info("Scheduler started")
        
        while self.running:
            try:
                now = datetime.datetime.now()
                current_month = self._get_current_month()
                
                # Weekly summary on Sunday
                if self._is_sunday():
                    self.logger.info("Sending weekly summary email")
                    balance_sheet = self.storage.get_balance_sheet(current_month)
                    self.email_service.send_weekly_summary(balance_sheet)
                
                # Monthly reminder during the last week of the month
                if self._is_last_week_of_month() and now.day >= 25:
                    self.logger.info("Sending monthly reminder email")
                    self.email_service.send_monthly_reminder(current_month)
                
                # Sleep for a day
                time.sleep(86400)  # 24 hours in seconds
                
            except Exception as e:
                self.logger.error(f"Error in scheduler: {str(e)}")
                # Sleep for an hour before retrying
                time.sleep(3600)
    
    def start(self) -> None:
        """Start the scheduler in a separate thread."""
        if self.running:
            self.logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()
        self.logger.info("Scheduler thread started")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if not self.running:
            self.logger.warning("Scheduler is not running")
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.logger.info("Scheduler stopped") 