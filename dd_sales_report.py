import base64
import os
import sqlite3
import csv
import re
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class SalesSummaryTable(Base):
    """SQLAlchemy model for sales_summary table"""
    __tablename__ = "sales_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date)
    date_range = Column(String)  # "19/09/2025 00:00:00 - 19/09/2025 23:59:59"
    gross_sales = Column(Float)
    total_discount_given = Column(Float)
    total_service_fee = Column(Float)
    net_sales = Column(Float)
    total_gst = Column(Float)
    total_payment_fee_surcharge = Column(Float)
    total_redeemed_point_amount = Column(Float)
    total_cash_rounding = Column(Float)
    total_sales = Column(Float)
    tipping_amount = Column(Float)
    total_cost = Column(Float)
    gross_profit = Column(Float)
    number_of_sales_transactions = Column(Integer)
    average_sales_per_transaction = Column(Float)
    number_of_voided_transactions = Column(Integer)
    total_voided_amount = Column(Float)
    dine_in_takeaway_ratio = Column(String)  # "100.0%/0.0%"
    total_pax = Column(Integer)
    total_customer_sign_ups = Column(Integer)
    member_non_member_sales = Column(String)  # "0.00/516.45"
    member_non_member_sales_quantity = Column(String)  # "0/65"
    total_ent_sales = Column(Float)
    unpaid = Column(Float)
    processed_at = Column(DateTime, default=datetime.utcnow)

class SalesInfoTable(Base):
    """SQLAlchemy model for sales_info table (Sales by Product details)"""
    __tablename__ = "sales_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date)
    product_name = Column(String)
    category = Column(String)
    gross_sales = Column(Float)
    barcode = Column(String)
    quantity_sold = Column(Integer)
    total_cost = Column(Float)
    total_discount_given = Column(Float)
    total_profit = Column(Float)
    processed_at = Column(DateTime, default=datetime.utcnow)

class SalesReportData(BaseModel):
    """Pydantic model for parsing sales report data"""
    report_date: str
    date_range: str
    sales_summary: Dict[str, str]
    sales_by_product: List[Dict[str, str]]

    @field_validator('sales_summary')
    def validate_sales_summary(cls, v):
        """Ensure required fields are present in sales summary"""
        required_fields = ['Gross Sales', 'Net Sales', 'Total Sales']
        for field in required_fields:
            if field not in v:
                raise ValueError(f"Missing required field: {field}")
        return v

class DailySalesReportProcessor:
    def __init__(self, credentials_file="credentials.json", token_file="token.json", db_path=None):
        """
        Daily Sales Report Processor for Qashier sales reports

        Args:
            credentials_file: Path to Google OAuth2 credentials file
            token_file: Path to token file
            db_path: Path to the database file
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        self.db_path = db_path

        # Initialize database connection
        if db_path:
            self.engine = create_engine(f'sqlite:///{db_path}')
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            self._create_tables()

        self.authenticate_gmail()

    def authenticate_gmail(self):
        """Authenticate with Gmail using OAuth2"""
        creds = None

        # Load existing token
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
            except Exception as e:
                print(f"Error loading token file: {e}")
                creds = None

        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("Attempting to refresh existing token...")
                    creds.refresh(Request())
                    print("Token refreshed successfully")
                except Exception as e:
                    print(f"Token refresh failed: {e}")
                    print("Getting new authorization...")
                    creds = None

            if not creds:
                # Need to get fresh authorization
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            try:
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                print(f"Credentials saved to {self.token_file}")
            except Exception as e:
                print(f"Warning: Could not save token file: {e}")

        self.service = build('gmail', 'v1', credentials=creds)
        print("Successfully connected to Gmail")

    def _create_tables(self):
        """Create sales tables if they don't exist"""
        if not self.db_path:
            return

        try:
            # Create tables using SQLAlchemy
            Base.metadata.create_all(bind=self.engine)
            print("Sales tables created/verified successfully")

        except Exception as e:
            print(f"Error creating tables: {e}")

    def parse_csv_content(self, csv_content: str) -> Optional[SalesReportData]:
        """Parse CSV content to extract sales information and sales by product data"""
        try:
            print("Parsing CSV content...")

            # Split content into lines
            lines = csv_content.strip().split('\n')

            # Extract report info from first few lines
            store_name = lines[0].strip('"') if len(lines) > 0 else ""
            date_range = lines[1].strip('"') if len(lines) > 1 else ""

            print(f"Store: {store_name}")
            print(f"Date Range: {date_range}")

            # Extract report date from date range (first date)
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', date_range)
            report_date = date_match.group(1) if date_match else ""

            # Parse sales summary information
            sales_summary = {}
            sales_info_start = -1

            for i, line in enumerate(lines):
                line = line.strip()

                # Find sales information section
                if line == '"Sales Information"':
                    continue
                elif line == '"Sales by Product"':
                    sales_info_start = i + 1
                    break
                elif ',' in line and not line.startswith('"Sales'):
                    # Parse key-value pairs
                    parts = [part.strip('"') for part in line.split('","')]
                    if len(parts) >= 2:
                        key = parts[0]
                        value = parts[1]
                        sales_summary[key] = value

            print(f"Parsed {len(sales_summary)} sales summary items")

            # Parse sales by product data
            sales_by_product = []
            if sales_info_start > 0 and sales_info_start < len(lines):
                # Find header line
                header_line = None
                data_start = sales_info_start

                for i in range(sales_info_start, len(lines)):
                    if 'Product Name' in lines[i]:
                        header_line = lines[i]
                        data_start = i + 1
                        break

                if header_line:
                    # Parse header
                    headers = [h.strip('"') for h in header_line.split('","')]
                    print(f"Product data headers: {headers}")

                    # Parse product data rows
                    for i in range(data_start, len(lines)):
                        line = lines[i].strip()
                        if not line:
                            continue

                        # Skip empty sections or new section headers
                        if line in ['"Sales by Product"', '"Credit Information"', '"Payment Information"', '"Discount Information"']:
                            break

                        # Parse CSV row
                        try:
                            # Use csv.reader to properly parse the CSV line
                            reader = csv.reader([line])
                            row = next(reader)

                            if len(row) >= len(headers):
                                product_data = {}
                                for j, header in enumerate(headers):
                                    product_data[header] = row[j] if j < len(row) else ""
                                sales_by_product.append(product_data)
                            else:
                                print(f"Skipping row with insufficient columns: {row}")
                        except Exception as e:
                            print(f"Error parsing product row: {line[:50]}... - {e}")
                            continue

            print(f"Parsed {len(sales_by_product)} product records")

            if not sales_summary:
                print("No sales summary data found")
                return None

            return SalesReportData(
                report_date=report_date,
                date_range=date_range,
                sales_summary=sales_summary,
                sales_by_product=sales_by_product
            )

        except Exception as e:
            print(f"Error parsing CSV content: {e}")
            return None

    def save_sales_data(self, sales_data: SalesReportData) -> bool:
        """Save sales data to database"""
        if not self.db_path:
            print("No database path provided")
            return False

        session = self.SessionLocal()
        try:
            # Parse report date
            report_date = datetime.strptime(sales_data.report_date, '%d/%m/%Y').date()

            # Check if data for this date already exists
            existing_summary = session.query(SalesSummaryTable).filter(
                SalesSummaryTable.report_date == report_date
            ).first()

            if existing_summary:
                print(f"Sales data for {report_date} already exists, updating...")
                session.delete(existing_summary)

            # Delete existing sales info for this date
            session.query(SalesInfoTable).filter(
                SalesInfoTable.report_date == report_date
            ).delete()

            # Helper function to safely convert to float
            def safe_float(value):
                try:
                    return float(str(value).replace(',', '')) if value else 0.0
                except:
                    return 0.0

            # Helper function to safely convert to int
            def safe_int(value):
                try:
                    return int(str(value).replace(',', '')) if value else 0
                except:
                    return 0

            # Create sales summary record
            summary = SalesSummaryTable(
                report_date=report_date,
                date_range=sales_data.date_range,
                gross_sales=safe_float(sales_data.sales_summary.get('Gross Sales')),
                total_discount_given=safe_float(sales_data.sales_summary.get('Total Discount Given')),
                total_service_fee=safe_float(sales_data.sales_summary.get('Total Service Fee')),
                net_sales=safe_float(sales_data.sales_summary.get('Net Sales')),
                total_gst=safe_float(sales_data.sales_summary.get('Total GST')),
                total_payment_fee_surcharge=safe_float(sales_data.sales_summary.get('Total Payment Fee Surcharge')),
                total_redeemed_point_amount=safe_float(sales_data.sales_summary.get('Total Redeemed Point Amount')),
                total_cash_rounding=safe_float(sales_data.sales_summary.get('Total Cash Rounding')),
                total_sales=safe_float(sales_data.sales_summary.get('Total Sales')),
                tipping_amount=safe_float(sales_data.sales_summary.get('Tipping Amount')),
                total_cost=safe_float(sales_data.sales_summary.get('Total Cost')),
                gross_profit=safe_float(sales_data.sales_summary.get('Gross Profit')),
                number_of_sales_transactions=safe_int(sales_data.sales_summary.get('Number of Sales Transactions')),
                average_sales_per_transaction=safe_float(sales_data.sales_summary.get('Average Sales/Transaction')),
                number_of_voided_transactions=safe_int(sales_data.sales_summary.get('Number of Voided Transactions')),
                total_voided_amount=safe_float(sales_data.sales_summary.get('Total Voided Amount')),
                dine_in_takeaway_ratio=sales_data.sales_summary.get('Dine In/Takeaway', ''),
                total_pax=safe_int(sales_data.sales_summary.get('Total Pax')),
                total_customer_sign_ups=safe_int(sales_data.sales_summary.get('Total Customer Sign Ups')),
                member_non_member_sales=sales_data.sales_summary.get('Member/Non-Member Sales', ''),
                member_non_member_sales_quantity=sales_data.sales_summary.get('Member/Non-Member Sales Quantity', ''),
                total_ent_sales=safe_float(sales_data.sales_summary.get('Total Ent Sales')),
                unpaid=safe_float(sales_data.sales_summary.get('Unpaid')),
            )

            session.add(summary)

            # Create sales info records for each product
            for product in sales_data.sales_by_product:
                sales_info = SalesInfoTable(
                    report_date=report_date,
                    product_name=product.get('Product Name', ''),
                    category=product.get('Category', ''),
                    gross_sales=safe_float(product.get('Gross Sales')),
                    barcode=product.get('Barcode', ''),
                    quantity_sold=safe_int(product.get('Quantity Sold')),
                    total_cost=safe_float(product.get('Total Cost')),
                    total_discount_given=safe_float(product.get('Total Discount Given')),
                    total_profit=safe_float(product.get('Total Profit'))
                )
                session.add(sales_info)

            session.commit()
            print(f"✅ Sales data saved successfully for {report_date}")
            print(f"   - Summary: 1 record")
            print(f"   - Products: {len(sales_data.sales_by_product)} records")
            return True

        except Exception as e:
            print(f"Error saving sales data: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def get_header_value(self, headers, name):
        """Get header value by name"""
        for header in headers:
            if header['name'].lower() == name.lower():
                return header['value']
        return ""

    def extract_email_content(self, payload):
        """Extract text content from email payload"""
        content = ""

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        content = base64.urlsafe_b64decode(
                            part['body']['data']).decode('utf-8', errors='ignore')
                        break
                elif part['mimeType'] == 'multipart/alternative':
                    content = self.extract_email_content(part)
                    if content:
                        break
        else:
            if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
                content = base64.urlsafe_b64decode(
                    payload['body']['data']).decode('utf-8', errors='ignore')

        return content

    def extract_csv_attachment(self, payload):
        """Extract CSV attachment from email payload"""
        if 'parts' in payload:
            for part in payload['parts']:
                # Check if this part is an attachment
                if part.get('filename', '').endswith('.csv'):
                    if 'data' in part['body']:
                        # Direct attachment data
                        attachment_data = base64.urlsafe_b64decode(part['body']['data'])
                        return attachment_data.decode('utf-8', errors='ignore')
                    elif 'attachmentId' in part['body']:
                        # Need to fetch attachment separately
                        attachment_id = part['body']['attachmentId']
                        attachment = self.service.users().messages().attachments().get(
                            userId='me',
                            messageId=part.get('messageId', ''),
                            id=attachment_id
                        ).execute()
                        attachment_data = base64.urlsafe_b64decode(attachment['data'])
                        return attachment_data.decode('utf-8', errors='ignore')

                # Recursively check nested parts
                if part.get('mimeType', '').startswith('multipart/'):
                    nested_csv = self.extract_csv_attachment(part)
                    if nested_csv:
                        return nested_csv

        return None

    def fetch_and_process_sales_reports_24h(self):
        """Fetch Daily Delights sales report emails from last 24 hours and process them"""
        yesterday = (datetime.now() - timedelta(hours=24)).strftime("%Y/%m/%d")
        query = f'from:noreply@qashier.com subject:"Sales Report for Daily Delights" after:{yesterday}'

        try:
            result = self.service.users().messages().list(
                userId='me', q=query, maxResults=50).execute()

            messages = result.get('messages', [])
            print(f"\n=== Found {len(messages)} Daily Delights sales report emails from last 24 hours ===\n")

            if not messages:
                print("No sales report emails found in the last 24 hours.")
                return

            processed_reports = 0

            for i, message in enumerate(messages, 1):
                try:
                    msg = self.service.users().messages().get(
                        userId='me', id=message['id'], format='full').execute()

                    headers = msg['payload']['headers']
                    subject = self.get_header_value(headers, 'Subject')
                    sender = self.get_header_value(headers, 'From')
                    date = self.get_header_value(headers, 'Date')

                    print(f"SALES REPORT EMAIL {i}")
                    print(f"From: {sender}")
                    print(f"Subject: {subject}")
                    print(f"Date: {date}")
                    print("-" * 60)

                    # Extract CSV attachment
                    csv_content = self.extract_csv_attachment(msg['payload'])

                    if csv_content:
                        print("🔄 Processing sales report CSV...")

                        # Parse CSV content
                        sales_data = self.parse_csv_content(csv_content)

                        if sales_data:
                            print(f"Parsed sales report for {sales_data.report_date}")
                            success = self.save_sales_data(sales_data)
                            if success:
                                processed_reports += 1
                                print("✅ Sales report processed successfully!")
                            else:
                                print("❌ Failed to save sales data")
                        else:
                            print("❌ Failed to parse sales data")
                    else:
                        print("❌ No CSV attachment found")

                    print("=" * 80)
                    print()

                except Exception as e:
                    print(f"Error processing sales report email {i}: {e}")
                    continue

            print(f"\n🎯 Summary: Processed {processed_reports} sales reports out of {len(messages)} emails")

            # Show summary
            if processed_reports > 0:
                self.get_sales_summary()

        except Exception as e:
            print(f"Error fetching sales report emails: {e}")

    def get_sales_summary(self):
        """Get summary of recent sales data"""
        if not self.db_path:
            print("No database path provided")
            return

        session = self.SessionLocal()
        try:
            # Get recent sales summaries
            summaries = session.query(SalesSummaryTable).order_by(
                SalesSummaryTable.report_date.desc()
            ).limit(5).all()

            print("\n=== RECENT SALES SUMMARIES ===")
            for summary in summaries:
                print(f"Date: {summary.report_date}, Total Sales: ${summary.total_sales:.2f}, "
                      f"Transactions: {summary.number_of_sales_transactions}, "
                      f"Gross Profit: ${summary.gross_profit:.2f}")

            # Get product count
            product_count = session.query(SalesInfoTable).count()
            print(f"\nTotal Product Records: {product_count}")

        except Exception as e:
            print(f"Error getting sales summary: {e}")
        finally:
            session.close()

def main():
    """Main function to fetch and process Daily Delights sales reports"""

    # Database path - UPDATE THIS TO YOUR ACTUAL PATH
    db_path = "/Users/mdavala/Desktop/MacbookPro2023Backup/Personal/Projects/Artificial_Intelligence/Pallava/AgenticAI Operations/DailyDelights/InventoryManagement/dailydelights.db"

    # Initialize the sales report processor
    processor = DailySalesReportProcessor(
        credentials_file="credentials_sg_daily_delights_email.json",
        token_file="token_sg_daily_delights_email.json",
        db_path=db_path
    )

    print("🚀 Starting Daily Delights sales report processing...")

    # Fetch and process sales report emails
    processor.fetch_and_process_sales_reports_24h()

    print("✅ Sales report processing completed!")

if __name__ == "__main__":
    main()