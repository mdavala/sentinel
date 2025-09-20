import base64
import os
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PaymentsTable(Base):
    __tablename__ = "payments_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String)
    supplies_received_date = Column(Date, nullable=True)
    supplier_name = Column(String)
    total_amount = Column(Float)
    payment_status = Column(String)
    payment_due_date = Column(Date, nullable=True)
    # New columns for payment tracking
    payment_type = Column(String, nullable=True)
    reference_num = Column(String, nullable=True)
    payment_validity = Column(String, nullable=True)

class UOBPaymentData(BaseModel):
    """Pydantic model to parse UOB email payment information"""
    payment_type: str
    reference_num: str
    customer_reference: Optional[str] = None
    supplier_name: str
    amount: float
    currency: str = "SGD"
    
    @field_validator('amount')
    def parse_amount(cls, v):
        """Parse amount from string format like 'SGD 321.99'"""
        if isinstance(v, str):
            # Extract numeric value from currency format
            amount_match = re.search(r'[\d,]+\.?\d*', v.replace(',', ''))
            if amount_match:
                return float(amount_match.group())
        return float(v)
    
    @field_validator('supplier_name')
    def clean_supplier_name(cls, v):
        """Clean supplier name for better matching"""
        return v.strip().upper()

class CompleteEmailProcessor:
    def __init__(self, credentials_file="credentials_sg_daily_delights_email.json", token_file="token_sg_daily_delights_email.json", db_path=None):
        """
        Complete Email Processor for UOB payments and other emails
        
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
            self._add_new_columns()
        
        self.authenticate_gmail()
    
    def authenticate_gmail(self):
        """Authenticate with Gmail using OAuth2"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('gmail', 'v1', credentials=creds)
        print("Successfully connected to Gmail")
    
    def _add_new_columns(self):
        """Add new columns to existing payments_table if they don't exist"""
        if not self.db_path:
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments_table'")
        if not cursor.fetchone():
            print("payments_table does not exist in the database")
            conn.close()
            return
        
        # Check if columns exist and add them if they don't
        cursor.execute("PRAGMA table_info(payments_table)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            ("payment_type", "TEXT"),
            ("reference_num", "TEXT"),
            ("payment_validity", "TEXT")
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE payments_table ADD COLUMN {col_name} {col_type}")
                    print(f"Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"Column {col_name} might already exist: {e}")
        
        conn.commit()
        conn.close()
    
    def parse_email_content(self, email_content: str) -> Optional[UOBPaymentData]:
        """Parse UOB email content to extract payment information"""
        try:
            print(f"DEBUG: Parsing email content:\n{email_content[:500]}...")
            
            # Extract transaction type
            transaction_match = re.search(r'Transaction:\s*(.+)', email_content)
            payment_type = transaction_match.group(1).strip() if transaction_match else ""
            print(f"DEBUG: Found payment_type: '{payment_type}'")
            
            # Extract FT Reference
            ft_ref_match = re.search(r'FT Reference:\s*(.+)', email_content)
            reference_num = ft_ref_match.group(1).strip() if ft_ref_match else ""
            print(f"DEBUG: Found reference_num: '{reference_num}'")
            
            # Extract Customer Reference (optional)
            cust_ref_match = re.search(r'Customer Reference:\s*(.+)', email_content)
            customer_reference = cust_ref_match.group(1).strip() if cust_ref_match and cust_ref_match.group(1).strip() else None
            print(f"DEBUG: Found customer_reference: '{customer_reference}'")
            
            # Extract Payer/Payee Name
            payee_match = re.search(r'Payer / Payee Name:\s*(.+)', email_content)
            supplier_name = payee_match.group(1).strip() if payee_match else ""
            print(f"DEBUG: Found supplier_name: '{supplier_name}'")
            
            # Extract Currency and Amount
            amount_match = re.search(r'Currency and Amount:\s*(.+)', email_content)
            currency_amount = amount_match.group(1).strip() if amount_match else ""
            print(f"DEBUG: Found currency_amount: '{currency_amount}'")
            
            # Parse currency and amount
            currency = "SGD"  # Default
            amount = 0.0
            if currency_amount:
                currency_match = re.match(r'([A-Z]{3})\s*([\d,]+\.?\d*)', currency_amount)
                if currency_match:
                    currency = currency_match.group(1)
                    amount = float(currency_match.group(2).replace(',', ''))
            
            print(f"DEBUG: Parsed amount: {amount}, currency: {currency}")
            
            if not all([payment_type, reference_num, supplier_name, amount]):
                print(f"Missing required fields: payment_type={payment_type}, reference_num={reference_num}, supplier_name={supplier_name}, amount={amount}")
                return None
            
            return UOBPaymentData(
                payment_type=payment_type,
                reference_num=reference_num,
                customer_reference=customer_reference,
                supplier_name=supplier_name,
                amount=amount,
                currency=currency
            )
            
        except Exception as e:
            print(f"Error parsing email content: {e}")
            return None
    
    def find_matching_payment(self, payment_data: UOBPaymentData):
        """Find matching payment in database based on supplier name and amount tolerance"""
        if not self.db_path:
            print("No database path provided")
            return []
            
        session = self.SessionLocal()
        try:
            # Search for payments with matching supplier name and amount within ±2 tolerance
            min_amount = payment_data.amount - 2.0
            max_amount = payment_data.amount + 2.0
            
            print(f"DEBUG: Searching for supplier '{payment_data.supplier_name}' with amount between {min_amount} and {max_amount}")
            
            # Try exact supplier name match first
            matching_payments = session.query(PaymentsTable).filter(
                PaymentsTable.supplier_name.ilike(f"%{payment_data.supplier_name}%"),
                PaymentsTable.total_amount >= min_amount,
                PaymentsTable.total_amount <= max_amount
            ).all()
            
            print(f"DEBUG: Found {len(matching_payments)} exact matches")
            
            if not matching_payments:
                # Try partial matching by removing common suffixes/prefixes
                cleaned_supplier = re.sub(r'\s+(PTE\.?\s*LTD\.?|LTD\.?|PTE\.?)\s*$', '', payment_data.supplier_name, flags=re.IGNORECASE)
                print(f"DEBUG: Trying cleaned supplier name: '{cleaned_supplier}'")
                matching_payments = session.query(PaymentsTable).filter(
                    PaymentsTable.supplier_name.ilike(f"%{cleaned_supplier}%"),
                    PaymentsTable.total_amount >= min_amount,
                    PaymentsTable.total_amount <= max_amount
                ).all()
                print(f"DEBUG: Found {len(matching_payments)} partial matches")
            
            # Debug: Show all suppliers in database for comparison
            all_suppliers = session.query(PaymentsTable.supplier_name, PaymentsTable.total_amount).all()
            print(f"DEBUG: All suppliers in database: {[(s.supplier_name, s.total_amount) for s in all_suppliers]}")
            
            return matching_payments
            
        except Exception as e:
            print(f"Error searching for matching payments: {e}")
            return []
        finally:
            session.close()
    
    def process_payment(self, payment_data: UOBPaymentData):
        """Process the payment and update database accordingly"""
        if not self.db_path:
            print("No database path provided - cannot process payments")
            return False
            
        # Use direct SQLite connection instead of SQLAlchemy ORM for updates
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Find matching payments using SQLAlchemy (for search logic)
            session = self.SessionLocal()
            matching_payments = self.find_matching_payment(payment_data)
            session.close()
            
            if not matching_payments:
                print(f"No matching payment found for supplier: {payment_data.supplier_name}, amount: {payment_data.amount}")
                return False
            
            # Process each matching payment using direct SQL
            for payment in matching_payments:
                print(f"Processing payment ID: {payment.id}, Supplier: {payment.supplier_name}, Amount: {payment.total_amount}, Status: {payment.payment_status}")
                
                # Check if reference number already exists (duplicate check)
                cursor.execute(
                    "SELECT id FROM payments_table WHERE reference_num = ? AND id != ?",
                    (payment_data.reference_num, payment.id)
                )
                existing_payment = cursor.fetchone()
                
                if existing_payment:
                    # Duplicate reference number found
                    cursor.execute("""
                        UPDATE payments_table 
                        SET payment_validity = ?, payment_type = ?, reference_num = ?
                        WHERE id = ?
                    """, ("duplicate", payment_data.payment_type, payment_data.reference_num, payment.id))
                    print(f"Duplicate payment detected for reference: {payment_data.reference_num}")
                    
                elif payment.payment_status and payment.payment_status.lower() == "pending":
                    # Valid payment - update to paid
                    cursor.execute("""
                        UPDATE payments_table 
                        SET payment_status = ?, payment_type = ?, reference_num = ?, payment_validity = ?
                        WHERE id = ?
                    """, ("paid", payment_data.payment_type, payment_data.reference_num, "valid", payment.id))
                    print(f"Payment marked as paid for supplier: {payment.supplier_name}")
                    
                elif payment.payment_status and payment.payment_status.lower() == "paid":
                    # Already paid - mark as duplicate
                    cursor.execute("""
                        UPDATE payments_table 
                        SET payment_validity = ?, payment_type = ?, reference_num = ?
                        WHERE id = ?
                    """, ("duplicate", payment_data.payment_type, payment_data.reference_num, payment.id))
                    print(f"Payment already paid - marked as duplicate for supplier: {payment.supplier_name}")
                    
                else:
                    # Unknown status - mark as valid but keep original status
                    cursor.execute("""
                        UPDATE payments_table 
                        SET payment_type = ?, reference_num = ?, payment_validity = ?
                        WHERE id = ?
                    """, (payment_data.payment_type, payment_data.reference_num, "valid", payment.id))
                    print(f"Payment processed with unknown status: {payment.payment_status}")
            
            conn.commit()
            
            # Verify the updates worked
            for payment in matching_payments:
                cursor.execute("SELECT payment_status, payment_type, reference_num, payment_validity FROM payments_table WHERE id = ?", (payment.id,))
                updated_row = cursor.fetchone()
                print(f"Verified update for ID {payment.id}: Status={updated_row[0]}, Type={updated_row[1]}, Ref={updated_row[2]}, Validity={updated_row[3]}")
            
            return True
            
        except Exception as e:
            print(f"Error processing payment: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def fetch_and_process_uob_emails_24h(self):
        """Fetch UOB emails from last 24 hours and process payments"""
        yesterday = (datetime.now() - timedelta(hours=24)).strftime("%Y/%m/%d")
        query = f'from:uobgroup.com after:{yesterday}'
        
        try:
            result = self.service.users().messages().list(
                userId='me', q=query, maxResults=50).execute()
            
            messages = result.get('messages', [])
            print(f"\n=== Found {len(messages)} UOB emails from last 24 hours ===\n")
            
            if not messages:
                print("No UOB emails found in the last 24 hours.")
                return
            
            processed_payments = 0
            
            for i, message in enumerate(messages, 1):
                try:
                    msg = self.service.users().messages().get(
                        userId='me', id=message['id'], format='full').execute()
                    
                    headers = msg['payload']['headers']
                    subject = self.get_header_value(headers, 'Subject')
                    sender = self.get_header_value(headers, 'From')
                    date = self.get_header_value(headers, 'Date')
                    content = self.extract_email_content(msg['payload'])
                    
                    print(f"UOB EMAIL {i}")
                    print(f"From: {sender}")
                    print(f"Subject: {subject}")
                    print(f"Date: {date}")
                    print("-" * 60)
                    
                    # FIXED: Check for multiple possible text patterns
                    payment_indicators = [
                        "transaction has been submitted for processing",
                        "has been released to the bank for processing",
                        "transaction has been released",
                        "FT Reference:"
                    ]
                    
                    is_payment_email = any(indicator in content.lower() for indicator in payment_indicators)
                    
                    if is_payment_email:
                        print("🔄 Processing payment notification...")
                        
                        # Parse and process the payment
                        payment_data = self.parse_email_content(content)
                        
                        if payment_data:
                            print(f"Parsed payment: {payment_data.supplier_name} - ${payment_data.amount}")
                            success = self.process_payment(payment_data)
                            if success:
                                processed_payments += 1
                                print("✅ Payment processed successfully!")
                            else:
                                print("❌ Failed to process payment")
                        else:
                            print("❌ Failed to parse payment data")
                    else:
                        print("📧 Regular email (not a payment notification)")
                        print(f"Content preview: {content[:100]}...")
                    
                    print("=" * 80)
                    print()
                    
                except Exception as e:
                    print(f"Error processing UOB email {i}: {e}")
                    continue
            
            print(f"\n🎯 Summary: Processed {processed_payments} payment notifications out of {len(messages)} emails")
            
            # Show payment summary
            if processed_payments > 0:
                self.get_payment_summary()
                    
        except Exception as e:
            print(f"Error fetching UOB emails: {e}")
    
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
    
    def get_payment_summary(self):
        """Get summary of recent payments"""
        if not self.db_path:
            print("No database path provided")
            return
            
        session = self.SessionLocal()
        try:
            payments = session.query(PaymentsTable).filter(
                PaymentsTable.reference_num.isnot(None)
            ).order_by(PaymentsTable.id.desc()).limit(10).all()
            
            print("\n=== RECENT PROCESSED PAYMENTS ===")
            for payment in payments:
                print(f"ID: {payment.id}, Supplier: {payment.supplier_name}, "
                      f"Amount: ${payment.total_amount:.2f}, Status: {payment.payment_status}, "
                      f"Validity: {payment.payment_validity}, Ref: {payment.reference_num}")
            
        except Exception as e:
            print(f"Error getting payment summary: {e}")
        finally:
            session.close()

def main():
    """Main function to fetch and process UOB emails"""
    
    # Database path - UPDATE THIS TO YOUR ACTUAL PATH
    db_path = "/Users/mdavala/Desktop/MacbookPro2023Backup/Personal/Projects/Artificial_Intelligence/Pallava/AgenticAI Operations/DailyDelights/InventoryManagement/dailydelights.db"
    
    # Initialize the email processor
    processor = CompleteEmailProcessor(
        credentials_file="credentials_sg_daily_delights_email.json",
        token_file="token_sg_daily_delights_email.json",
        db_path=db_path
    )
    
    print("🚀 Starting UOB email processing...")
    
    # Fetch and process UOB emails with payment processing
    processor.fetch_and_process_uob_emails_24h()
    
    print("✅ UOB email processing completed!")

if __name__ == "__main__":
    main()