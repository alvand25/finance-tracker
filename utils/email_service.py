import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Union

from models.expense import BalanceSheet


class EmailService:
    """Service for sending email notifications."""
    
    def __init__(
        self,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        sender_email: Optional[str] = None,
        sender_password: Optional[str] = None,
        recipients: Optional[List[str]] = None
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipients = recipients or []
        self.logger = logging.getLogger(__name__)

    def _create_weekly_summary_html(self, balance_sheet: BalanceSheet) -> str:
        """Create HTML content for the weekly summary email."""
        summary = balance_sheet.summary()
        
        # Format expenses as a table
        expense_rows = ""
        for expense in balance_sheet.expenses:
            shared_total = expense.shared_total if expense.shared_total is not None else expense.calculate_shared_total()
            expense_rows += f"""
            <tr>
                <td>{expense.date.strftime('%Y-%m-%d')}</td>
                <td>{expense.payer.value}</td>
                <td>{expense.store}</td>
                <td>${expense.total_amount:.2f}</td>
                <td>${shared_total:.2f}</td>
                <td>${expense.amount_owed():.2f}</td>
            </tr>
            """
        
        # Create the email content
        html = f"""
        <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        color: #333;
                    }}
                    .header {{
                        background-color: #f1f1f1;
                        padding: 10px;
                        text-align: center;
                        border-radius: 5px;
                        margin-bottom: 20px;
                    }}
                    .summary {{
                        margin-bottom: 20px;
                        padding: 15px;
                        background-color: #f9f9f9;
                        border-radius: 5px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                    }}
                    th, td {{
                        padding: 8px;
                        text-align: left;
                        border-bottom: 1px solid #ddd;
                    }}
                    th {{
                        background-color: #f2f2f2;
                    }}
                    .owed {{
                        font-weight: bold;
                        font-size: 18px;
                        color: #0066cc;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>Weekly Expense Summary</h2>
                    <p>Week of {datetime.now().strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="summary">
                    <h3>Current Balance</h3>
                    <p class="owed">{summary['owed_statement']}</p>
                    <p>Total expenses this month: ${summary['total_expenses']:.2f}</p>
                    <p>Total shared expenses: ${summary['total_shared_expenses']:.2f}</p>
                    <p>Alvand has paid: ${summary['alvand_paid']:.2f}</p>
                    <p>Roni has paid: ${summary['roni_paid']:.2f}</p>
                </div>
                
                <h3>Recent Expenses</h3>
                <table>
                    <tr>
                        <th>Date</th>
                        <th>Paid By</th>
                        <th>Store</th>
                        <th>Total</th>
                        <th>Shared</th>
                        <th>Owed</th>
                    </tr>
                    {expense_rows}
                </table>
                
                <p>This is an automated email from your Shared Expenses Tracker.</p>
            </body>
        </html>
        """
        
        return html
    
    def _create_monthly_reminder_html(self, month: str) -> str:
        """Create HTML content for the monthly reminder email."""
        # Determine the month name from the YYYY-MM format
        month_obj = datetime.strptime(month, "%Y-%m")
        month_name = month_obj.strftime("%B %Y")
        
        html = f"""
        <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        color: #333;
                    }}
                    .header {{
                        background-color: #f1f1f1;
                        padding: 10px;
                        text-align: center;
                        border-radius: 5px;
                        margin-bottom: 20px;
                    }}
                    .reminder {{
                        margin-bottom: 20px;
                        padding: 15px;
                        background-color: #f9f9f9;
                        border-radius: 5px;
                    }}
                    .action {{
                        margin-top: 20px;
                        padding: 15px;
                        background-color: #e6f7ff;
                        border-radius: 5px;
                        border-left: 4px solid #0066cc;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>Monthly Expense Reminder</h2>
                    <p>{month_name}</p>
                </div>
                
                <div class="reminder">
                    <h3>Month End Approaching</h3>
                    <p>The month of {month_name} is coming to an end.</p>
                    <p>This is a friendly reminder to submit any remaining receipts that you haven't entered into the system yet.</p>
                </div>
                
                <div class="action">
                    <h3>Action Required</h3>
                    <p>Please log in to your Shared Expenses Tracker and make sure all your expenses are entered before the end of the month.</p>
                    <p>This will ensure an accurate settlement for {month_name}.</p>
                </div>
                
                <p>This is an automated email from your Shared Expenses Tracker.</p>
            </body>
        </html>
        """
        
        return html
    
    def send_email(
        self,
        subject: str,
        html_content: str,
        recipients: Optional[List[str]] = None
    ) -> bool:
        """Send an email with the given subject and HTML content."""
        if not self.sender_email or not self.sender_password:
            self.logger.warning("Sender email or password not configured. Email not sent.")
            return False
        
        # Use provided recipients or fall back to default recipients
        email_recipients = recipients if recipients else self.recipients
        if not email_recipients:
            self.logger.warning("No recipients specified. Email not sent.")
            return False
        
        # Create the email message
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"] = self.sender_email
        message["To"] = ", ".join(email_recipients)
        
        # Attach the HTML content
        message.attach(MIMEText(html_content, "html"))
        
        try:
            # Create a secure connection to the SMTP server
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
            
            self.logger.info(f"Email sent successfully to {email_recipients}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def send_weekly_summary(
        self,
        balance_sheet: BalanceSheet,
        recipients: Optional[List[str]] = None
    ) -> bool:
        """Send a weekly summary email."""
        subject = f"Weekly Expense Summary - {datetime.now().strftime('%B %d, %Y')}"
        html_content = self._create_weekly_summary_html(balance_sheet)
        
        return self.send_email(subject, html_content, recipients)
    
    def send_monthly_reminder(
        self,
        month: str,
        recipients: Optional[List[str]] = None
    ) -> bool:
        """Send a monthly reminder email to input remaining receipts."""
        month_obj = datetime.strptime(month, "%Y-%m")
        month_name = month_obj.strftime("%B %Y")
        
        subject = f"Reminder: Submit Remaining Receipts for {month_name}"
        html_content = self._create_monthly_reminder_html(month)
        
        return self.send_email(subject, html_content, recipients) 