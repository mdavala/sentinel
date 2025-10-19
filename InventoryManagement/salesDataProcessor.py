import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Google Drive API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# SQLAlchemy setup
Base = declarative_base()

class SalesTable(Base):
    __tablename__ = "sales_table"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String)
    receipt_no = Column(String)
    order_number = Column(String)
    invoice_no = Column(String)
    transaction_total_amount = Column(Float, nullable=True)
    transaction_level_percentage_discount = Column(Float, nullable=True)
    transaction_level_dollar_discount = Column(Float, nullable=True)
    transaction_payment_method = Column(String)
    payment_note = Column(String)
    transaction_note = Column(String)
    staff_name = Column(String)
    customer_name = Column(String)
    customer_phone_number = Column(String)
    voided = Column(String)
    void_reason = Column(String)
    transaction_item = Column(String)
    transaction_item_quantity = Column(Float, nullable=True)
    transaction_item_notes = Column(String)
    transaction_item_discount = Column(Float, nullable=True)
    amount_before_subsidy = Column(Float, nullable=True)
    total_subsidy = Column(Float, nullable=True)
    transaction_item_final_amount = Column(Float, nullable=True)
    processed_date = Column(String, default=lambda: datetime.now().isoformat())

class SalesDataProcessor:
    def __init__(self, db_path="dailydelights.db", credentials_file="credentials.json", token_file="token.json", dailydelights_folder_id="1UNvs6JiWNMBgqAB4-RROsbPWKJa02Ufm"):
        self.db_path = db_path
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.dailydelights_folder_id = dailydelights_folder_id
        self.service = None
        self.engine = None
        self.session = None
        
        # Initialize database
        self.setup_database()
        
        # Initialize Google Drive service
        self.setup_drive_service()
    
    def setup_database(self):
        """Initialize database connection and create tables"""
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        logger.info("Database connection established")
    
    def setup_drive_service(self):
        """Set up Google Drive API service"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        logger.info("Google Drive service initialized")
    
    def get_folder_id(self, folder_name, parent_folder_id=None):
        """Get folder ID by name, create if doesn't exist"""
        # If no parent specified, use dailydelights folder as parent
        if parent_folder_id is None:
            parent_folder_id = self.dailydelights_folder_id
        
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
        
        try:
            results = self.service.files().list(q=query, fields="files(id, name, parents)").execute()
            items = results.get('files', [])
            
            if items:
                logger.info(f"Found existing folder '{folder_name}' with ID: {items[0]['id']}")
                return items[0]['id']
            else:
                # Create folder if it doesn't exist
                return self.create_folder(folder_name, parent_folder_id)
        except Exception as e:
            logger.error(f"Error searching for folder '{folder_name}': {str(e)}")
            return None
    
    def create_folder(self, folder_name, parent_folder_id=None):
        """Create a new folder in Google Drive"""
        # If no parent specified, use dailydelights folder as parent
        if parent_folder_id is None:
            parent_folder_id = self.dailydelights_folder_id
            
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = self.service.files().create(body=folder_metadata, fields='id,name,parents').execute()
            folder_id = folder.get('id')
            
            logger.info(f"Created folder '{folder_name}' with ID: {folder_id} in parent {parent_folder_id}")
            
            # Verify the folder was created in the right place
            verify_folder = self.service.files().get(fileId=folder_id, fields='id,name,parents').execute()
            if parent_folder_id in verify_folder.get('parents', []):
                logger.info(f"Verified: Folder '{folder_name}' is correctly placed in parent {parent_folder_id}")
            else:
                logger.warning(f"Warning: Folder '{folder_name}' parents are {verify_folder.get('parents', [])}")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Error creating folder '{folder_name}': {str(e)}")
            return None
    
    def get_files_in_folder(self, folder_name, parent_folder_id=None):
        """Get all XLSX files from specified folder"""
        folder_id = self.get_folder_id(folder_name, parent_folder_id)
        
        if not folder_id:
            logger.error(f"Folder '{folder_name}' not found")
            return []
        
        query = f"'{folder_id}' in parents and (mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or name contains '.xlsx') and trashed=false"
        
        try:
            results = self.service.files().list(q=query, fields="files(id, name, parents)").execute()
            files = results.get('files', [])
            
            logger.info(f"Found {len(files)} XLSX files in '{folder_name}' folder")
            return files
        except Exception as e:
            logger.error(f"Error listing files in folder '{folder_name}': {str(e)}")
            return []
    
    def download_file(self, file_id, file_name):
        """Download file from Google Drive"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Save to local file
            with open(file_name, 'wb') as f:
                f.write(file_io.getvalue())
            
            logger.info(f"Downloaded file: {file_name}")
            return file_name
        except Exception as e:
            logger.error(f"Error downloading file {file_name}: {str(e)}")
            return None
    
    def move_file_to_folder(self, file_id, source_folder_id, target_folder_name):
        """Move file from source folder to target folder"""
        try:
            # Get target folder ID (it will be created under dailydelights if it doesn't exist)
            target_folder_id = self.get_folder_id(target_folder_name, self.dailydelights_folder_id)
            
            if not target_folder_id:
                logger.error(f"Failed to get or create target folder '{target_folder_name}'")
                return False
            
            # Remove file from source folder and add to target folder
            self.service.files().update(
                fileId=file_id,
                addParents=target_folder_id,
                removeParents=source_folder_id,
                fields='id, parents'
            ).execute()
            
            logger.info(f"Moved file to '{target_folder_name}' folder (ID: {target_folder_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error moving file to '{target_folder_name}': {str(e)}")
            return False
    
    def process_xlsx_file(self, file_path):
        """Process XLSX file and extract sales data"""
        try:
            # Read XLSX file
            df = pd.read_excel(file_path, sheet_name='Transactions', header=2)  # Headers are in row 3
            
            # Clean column names to match database schema
            column_mapping = {
                'Date': 'date',
                'Receipt No.': 'receipt_no',
                'Order Number': 'order_number',
                'Invoice No.': 'invoice_no',
                'Transaction Total Amount': 'transaction_total_amount',
                'Transaction Level Percentage Discount': 'transaction_level_percentage_discount',
                'Transaction Level Dollar Discount': 'transaction_level_dollar_discount',
                'Transaction Payment Method': 'transaction_payment_method',
                'Payment Note': 'payment_note',
                'Transaction Note': 'transaction_note',
                'Staff Name': 'staff_name',
                'Customer Name': 'customer_name',
                'Customer Phone Number': 'customer_phone_number',
                'Voided': 'voided',
                'Void Reason': 'void_reason',
                'Transaction Item': 'transaction_item',
                'Transaction Item Quantity': 'transaction_item_quantity',
                'Transaction Item Notes': 'transaction_item_notes',
                'Transaction Item Discount': 'transaction_item_discount',
                'Amount Before Subsidy $': 'amount_before_subsidy',
                'Total Subsidy $': 'total_subsidy',
                'Transaction Item Final Amount ($)': 'transaction_item_final_amount'
            }
            
            # Select only the columns we need
            available_columns = [col for col in column_mapping.keys() if col in df.columns]
            df_filtered = df[available_columns].copy()
            
            # Rename columns
            df_filtered.rename(columns={col: column_mapping[col] for col in available_columns}, inplace=True)
            
            # Handle NaN values
            df_filtered = df_filtered.replace({np.nan: None})
            
            # Convert date column to string format
            if 'date' in df_filtered.columns:
                df_filtered['date'] = pd.to_datetime(df_filtered['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            
            logger.info(f"Successfully processed XLSX file with {len(df_filtered)} records")
            return df_filtered
            
        except Exception as e:
            logger.error(f"Error processing XLSX file {file_path}: {str(e)}")
            return None
    
    def insert_sales_data(self, df):
        """Insert sales data into database"""
        try:
            records_inserted = 0
            
            for index, row in df.iterrows():
                # Create SalesTable object
                sales_record = SalesTable(**row.to_dict())
                self.session.add(sales_record)
                records_inserted += 1
            
            # Commit all records
            self.session.commit()
            logger.info(f"Successfully inserted {records_inserted} sales records into database")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting sales data: {str(e)}")
            self.session.rollback()
            return False
    
    def process_sales_files(self):
        """Main function to process all sales files"""
        try:
            # Verify dailydelights folder exists
            try:
                dailydelights_folder = self.service.files().get(fileId=self.dailydelights_folder_id, fields='id,name').execute()
                logger.info(f"✅ Verified dailydelights folder: '{dailydelights_folder['name']}' (ID: {self.dailydelights_folder_id})")
            except Exception as e:
                logger.error(f"❌ Cannot access dailydelights folder {self.dailydelights_folder_id}: {str(e)}")
                return
            
            # Get sales_data folder ID (under dailydelights)
            sales_folder_id = self.get_folder_id("sales_data", self.dailydelights_folder_id)
            if not sales_folder_id:
                logger.error("❌ Could not find or create sales_data folder")
                return
            logger.info(f"✅ Sales data folder ID: {sales_folder_id}")
            
            # Ensure processed and error folders exist (under dailydelights) and get their IDs
            processed_folder_id = self.get_folder_id("processed_sales_data", self.dailydelights_folder_id)
            error_folder_id = self.get_folder_id("error_sales_data", self.dailydelights_folder_id)
            
            if not processed_folder_id or not error_folder_id:
                logger.error("❌ Could not create required folders")
                return
            
            logger.info(f"✅ Processed folder ID: {processed_folder_id}")
            logger.info(f"✅ Error folder ID: {error_folder_id}")
            
            # Get all XLSX files from sales_data folder
            files = self.get_files_in_folder("sales_data", self.dailydelights_folder_id)
            
            if not files:
                logger.info("ℹ️ No XLSX files found in sales_data folder")
                return
            
            processed_count = 0
            error_count = 0
            
            for file in files:
                file_id = file['id']
                file_name = file['name']
                
                logger.info(f"🔄 Processing file: {file_name} (ID: {file_id})")
                
                try:
                    # Download file
                    local_file_path = f"temp_{file_name}"
                    downloaded_file = self.download_file(file_id, local_file_path)
                    
                    if not downloaded_file:
                        logger.error(f"❌ Failed to download file: {file_name}")
                        self.move_file_to_folder(file_id, sales_folder_id, "error_sales_data")
                        error_count += 1
                        continue
                    
                    # Process XLSX file
                    df = self.process_xlsx_file(local_file_path)
                    
                    if df is not None and len(df) > 0:
                        # Insert data into database
                        if self.insert_sales_data(df):
                            # Move file to processed folder
                            if self.move_file_to_folder(file_id, sales_folder_id, "processed_sales_data"):
                                processed_count += 1
                                logger.info(f"✅ Successfully processed: {file_name}")
                            else:
                                logger.error(f"❌ Failed to move processed file: {file_name}")
                                # Try to move to error folder as fallback
                                self.move_file_to_folder(file_id, sales_folder_id, "error_sales_data")
                                error_count += 1
                        else:
                            # Move file to error folder
                            self.move_file_to_folder(file_id, sales_folder_id, "error_sales_data")
                            error_count += 1
                    else:
                        # Move file to error folder if no data found
                        self.move_file_to_folder(file_id, sales_folder_id, "error_sales_data")
                        error_count += 1
                        logger.error(f"❌ No data found in file: {file_name}")
                    
                    # Clean up local file
                    if os.path.exists(local_file_path):
                        os.remove(local_file_path)
                        logger.info(f"🧹 Cleaned up temporary file: {local_file_path}")
                
                except Exception as e:
                    logger.error(f"❌ Error processing file {file_name}: {str(e)}")
                    # Move file to error folder
                    try:
                        self.move_file_to_folder(file_id, sales_folder_id, "error_sales_data")
                    except Exception as move_error:
                        logger.error(f"❌ Failed to move error file {file_name}: {str(move_error)}")
                    error_count += 1
                    
                    # Clean up local file if it exists
                    local_file_path = f"temp_{file_name}"
                    if os.path.exists(local_file_path):
                        os.remove(local_file_path)
                        logger.info(f"🧹 Cleaned up temporary file: {local_file_path}")
            
            logger.info(f"📊 Processing complete. ✅ Processed: {processed_count}, ❌ Errors: {error_count}")
            
        except Exception as e:
            logger.error(f"❌ Error in main processing function: {str(e)}")
        finally:
            # Close database session
            if self.session:
                self.session.close()
                logger.info("🔒 Database session closed")

# Main execution
if __name__ == "__main__":
    # Initialize processor with dailydelights folder ID
    processor = SalesDataProcessor(dailydelights_folder_id="1UNvs6JiWNMBgqAB4-RROsbPWKJa02Ufm")
    
    # Process all sales files
    processor.process_sales_files()
    
    print("Sales data processing completed!")