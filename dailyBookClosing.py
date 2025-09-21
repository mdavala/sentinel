#!/usr/bin/env python3
"""
dailyBookClosing.py - Daily Book Closing Processing System
Fetches daily book closing images from Google Drive and processes them using Vision OCR
"""

import os
import time
import base64
import mimetypes
import json
import requests
from datetime import datetime
from typing import Set, List, Dict, Optional
from io import BytesIO
from collections import defaultdict

# Google Drive imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Vision OCR imports
from PIL import Image
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables
load_dotenv(override=True)

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =============================================================================
# DAILY BOOK CLOSING MODELS AND DATABASE SETUP
# =============================================================================

class DailyBookClosingData(BaseModel):
    # Required fields
    closing_date: str = Field(..., description="Date of closing in YYYY-MM-DD format")
    
    # Sales Information
    total_sales: Optional[float] = Field(None, description="Total sales amount")
    number_of_transactions: Optional[int] = Field(None, description="Number of sales transactions")
    average_sales_per_transaction: Optional[float] = Field(None, description="Average sales per transaction")
    
    # Payment Methods
    nets_qr_amount: Optional[float] = Field(None, description="NETS QR payment amount")
    cash_amount: Optional[float] = Field(None, description="Cash payment amount")
    credit_amount: Optional[float] = Field(None, description="Credit payment amount")
    nets_amount: Optional[float] = Field(None, description="NETS payment amount")
    total_settlement: Optional[float] = Field(None, description="Total settlement amount")
    
    # Cash Record
    expected_cash_balance: Optional[float] = Field(None, description="Expected cash balance")
    cash_outs: Optional[List[float]] = Field(None, description="Cash out for salary/expenses")
    
    # Additional fields
    voided_transactions: Optional[int] = Field(None, description="Number of voided transactions")
    voided_amount: Optional[float] = Field(None, description="Total amount voided")

class DailyBookClosingResponse(BaseModel):
    daily_closing: DailyBookClosingData

# SQLAlchemy setup
Base = declarative_base()

class DailyBookClosingTable(Base):
    __tablename__ = "daily_book_closing_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    closing_date = Column(String, nullable=False)
    
    # Sales Information
    total_sales = Column(Float, nullable=True)
    number_of_transactions = Column(Integer, nullable=True)
    average_sales_per_transaction = Column(Float, nullable=True)
    
    # Payment Methods
    nets_qr_amount = Column(Float, nullable=True)
    cash_amount = Column(Float, nullable=True)
    credit_amount = Column(Float, nullable=True)
    nets_amount = Column(Float, nullable=True)
    total_settlement = Column(Float, nullable=True)
    
    # Cash Record
    expected_cash_balance = Column(Float, nullable=True)
    cash_outs = Column(Text, nullable=True)  # Store as JSON string
    
    # Additional fields
    voided_transactions = Column(Integer, nullable=True)
    voided_amount = Column(Float, nullable=True)
    
    # Metadata
    processed_at = Column(DateTime, default=datetime.now)

# Create DB connection
engine = create_engine("sqlite:///dailydelights.db")
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# =============================================================================
# VISION OCR FUNCTIONS
# =============================================================================

def encode_image(image_path: str) -> str:
    """Convert image file to base64 string"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def is_remote_file(file_path: str) -> bool:
    """Check if file path is a URL"""
    return file_path.startswith("http://") or file_path.startswith("https://")

def ocr_daily_closing(file_path: str, model: str, api_key: str = TOGETHER_API_KEY):
    """
    Run OCR using Together AI Vision model and return JSON output for daily book closing.
    """
    if not api_key:
        raise ValueError("TOGETHER_API_KEY not set in environment")

    vision_llm = model

    # System prompt for daily book closing extraction
    system_prompt = """
        You are an intelligent daily book closing analysis agent for Daily Delights retail store.
        
        Analyze the POS system screenshots and extract daily closing information:
        
        REQUIRED FIELDS:
        - closing_date: Date of closing in YYYY-MM-DD format (extract from image timestamps or headers)
        
        OPTIONAL FIELDS - Sales Information:
        - total_sales: Total sales amount for the day
        - number_of_transactions: Number of sales transactions
        - average_sales_per_transaction: Average sales per transaction
        
        OPTIONAL FIELDS - Payment Methods:
        - nets_qr_amount: NETS QR payment amount
        - cash_amount: Cash payment amount  
        - credit_amount: Total Credit payment amount - AhaCredit + ParthibanCredit + NaveenCredit
        - nets_amount: NETS payment amount
        - total_settlement: Total settlement amount
        
        OPTIONAL FIELDS - Cash Record:
        - expected_cash_balance: Expected cash balance
        - cash_outs: Check for "Cash In / Out History" column in image. Extract only "Cash Out" entries with amounts. This can be single or multiple cash out entries. DO NOT extract from "Cash Sales History" column.
        
        OPTIONAL FIELDS - Additional:
        - voided_transactions: Number of voided transactions
        - voided_amount: Total amount voided
        
        IMPORTANT RULES:
        1. If information is not clearly visible, set to null
        2. For closing_date, extract from timestamps visible in the image (format: YYYY-MM-DD)
        3. Look for payment settlement information in "Total Settlement by Payment Method" section
        4. For cash_outs, ONLY look in "Cash In / Out History" column, NOT "Cash Sales History"
        5. Cash out entries typically show amounts with "Cash Out" or salary-related text
        6. Extract exact numerical values as shown in the POS system
        7. Return clean, structured JSON only
        
        STRICT RULE: Return single daily_closing object with all fields in JSON Format. Use null for missing/unclear values.
"""

    # Prepare image input
    final_image_url = (
        file_path
        if is_remote_file(file_path)
        else f"data:image/jpeg;base64,{encode_image(file_path)}"
    )

    # Make request to Together AI
    response = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": vision_llm,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": final_image_url}},
                    ],
                }
            ],
            "response_format":{
                "type": "json_object",
                "schema": DailyBookClosingResponse.model_json_schema(),
            }
        },
        verify=False
    )

    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code}, {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]

def merge_daily_closing_data(json_outputs: List[str]) -> Dict:
    """
    Merge multiple JSON outputs from different images into a single daily closing record
    
    Args:
        json_outputs: List of JSON strings from different images
        
    Returns:
        Dict: Merged daily closing data
    """
    merged_data = {
        "closing_date": None,
        "total_sales": None,
        "number_of_transactions": None,
        "average_sales_per_transaction": None,
        "nets_qr_amount": None,
        "cash_amount": None,
        "credit_amount": None,
        "nets_amount": None,
        "total_settlement": None,
        "expected_cash_balance": None,
        "cash_outs": [],
        "voided_transactions": None,
        "voided_amount": None
    }
    
    print(f"Merging {len(json_outputs)} JSON outputs...")
    
    for i, json_string in enumerate(json_outputs, 1):
        try:
            # Clean the JSON string
            cleaned_json = json_string.strip()
            if cleaned_json.startswith('```json'):
                cleaned_json = cleaned_json.replace('```json', '').replace('```', '').strip()
            elif cleaned_json.startswith('```'):
                cleaned_json = cleaned_json.replace('```', '').strip()
            
            # Parse JSON
            data = json.loads(cleaned_json)
            daily_closing = data.get('daily_closing', {})
            
            print(f"Processing JSON {i}: {json.dumps(daily_closing, indent=2)[:200]}...")
            
            # Merge each field - use the first non-null value found
            for key, value in daily_closing.items():
                if key == 'cash_outs' and value:
                    # For cash_outs, extend the list
                    if isinstance(value, list):
                        merged_data['cash_outs'].extend(value)
                    else:
                        merged_data['cash_outs'].append(value)
                elif value is not None and merged_data.get(key) is None:
                    merged_data[key] = value
            
        except Exception as e:
            print(f"Error processing JSON {i}: {e}")
            continue
    
    # Clean up cash_outs - remove duplicates and keep only valid numbers
    if merged_data['cash_outs']:
        cash_outs_clean = []
        for amount in merged_data['cash_outs']:
            if isinstance(amount, (int, float)) and amount > 0:
                cash_outs_clean.append(float(amount))
        merged_data['cash_outs'] = cash_outs_clean if cash_outs_clean else None
    else:
        merged_data['cash_outs'] = None
    
    print(f"Merged data: {json.dumps(merged_data, indent=2)}")
    return merged_data

def save_daily_closing_to_db(merged_data: Dict, session):
    """
    Save merged daily closing data to SQL database
    
    Args:
        merged_data (Dict): Merged daily closing data
        session: SQLAlchemy session object
    
    Returns:
        tuple: (success: bool, closing_date: str or None)
    """
    try:
        print(f"Saving merged daily closing data to database...")
        
        closing_date = merged_data.get('closing_date')
        if not closing_date:
            print("Warning: No closing_date found in merged data")
            return False, None
        
        # Handle cash_outs conversion
        cash_outs_data = merged_data.get('cash_outs')
        cash_outs_json = json.dumps(cash_outs_data) if cash_outs_data else None
        
        # Check if record already exists for this date
        existing_record = session.query(DailyBookClosingTable).filter_by(closing_date=closing_date).first()
        if existing_record:
            print(f"Record already exists for date {closing_date}, updating...")
            # Update existing record
            existing_record.total_sales = merged_data.get('total_sales') or existing_record.total_sales
            existing_record.number_of_transactions = merged_data.get('number_of_transactions') or existing_record.number_of_transactions
            existing_record.average_sales_per_transaction = merged_data.get('average_sales_per_transaction') or existing_record.average_sales_per_transaction
            existing_record.nets_qr_amount = merged_data.get('nets_qr_amount') or existing_record.nets_qr_amount
            existing_record.cash_amount = merged_data.get('cash_amount') or existing_record.cash_amount
            existing_record.credit_amount = merged_data.get('credit_amount') or existing_record.credit_amount
            existing_record.nets_amount = merged_data.get('nets_amount') or existing_record.nets_amount
            existing_record.total_settlement = merged_data.get('total_settlement') or existing_record.total_settlement
            existing_record.expected_cash_balance = merged_data.get('expected_cash_balance') or existing_record.expected_cash_balance
            existing_record.cash_outs = cash_outs_json or existing_record.cash_outs
            existing_record.voided_transactions = merged_data.get('voided_transactions') or existing_record.voided_transactions
            existing_record.voided_amount = merged_data.get('voided_amount') or existing_record.voided_amount
            existing_record.processed_at = datetime.now()
        else:
            # Create new daily closing record
            daily_closing_record = DailyBookClosingTable(
                closing_date=closing_date,
                total_sales=merged_data.get('total_sales'),
                number_of_transactions=merged_data.get('number_of_transactions'),
                average_sales_per_transaction=merged_data.get('average_sales_per_transaction'),
                nets_qr_amount=merged_data.get('nets_qr_amount'),
                cash_amount=merged_data.get('cash_amount'),
                credit_amount=merged_data.get('credit_amount'),
                nets_amount=merged_data.get('nets_amount'),
                total_settlement=merged_data.get('total_settlement'),
                expected_cash_balance=merged_data.get('expected_cash_balance'),
                cash_outs=cash_outs_json,
                voided_transactions=merged_data.get('voided_transactions'),
                voided_amount=merged_data.get('voided_amount')
            )
            
            # Add to session
            session.add(daily_closing_record)
        
        # Commit changes
        session.commit()
        print(f"Successfully saved daily closing data for {closing_date}")
        return True, closing_date
        
    except Exception as e:
        print(f"Error saving to database: {e}")
        print(f"Exception type: {type(e).__name__}")
        session.rollback()
        return False, None

# =============================================================================
# GOOGLE DRIVE FUNCTIONS FOR DAILY BOOK CLOSING
# =============================================================================

class DailyBookClosingSentinel:
    """Process daily book closing images from Google Drive through Vision OCR"""
    
    # Google Drive API configuration
    SCOPES = ['https://www.googleapis.com/auth/drive']
    CREDENTIALS_FILE = 'credentials.json'
    TOKEN_FILE = 'token.json'
    
    # Daily book closing folder ID - UPDATE THIS WITH YOUR ACTUAL FOLDER ID
    DAILY_BOOK_CLOSING_FOLDER_ID = '1sxtFv5mgGSafgWQ3UufW1D2c9f4xE7-Y'
    
    def __init__(self, local_folder: str = "daily_book_closing_images"):
        """
        Initialize DailyBookClosingSentinel
        
        Args:
            local_folder: Local folder to download images to
        """
        self.service = None
        self.local_folder = local_folder
        self.processed_folder_id = None
        
        # Create local folder if it doesn't exist
        if not os.path.exists(self.local_folder):
            os.makedirs(self.local_folder)
            print(f"Created local folder: {self.local_folder}")
        else:
            print(f"Using existing folder: {self.local_folder}")
        
    def authenticate(self) -> bool:
        """Authenticate with Google Drive API"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(self.TOKEN_FILE, self.SCOPES)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.CREDENTIALS_FILE):
                    print(f"Error: {self.CREDENTIALS_FILE} not found")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next time
            with open(self.TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        print("Authentication successful")
        return True
    
    def get_or_create_folder(self, folder_name: str, parent_folder_id: str) -> str:
        """
        Get folder ID if exists, otherwise create new folder
        
        Args:
            folder_name: Name of the folder to find/create
            parent_folder_id: Parent folder ID where to create the folder
            
        Returns:
            str: Folder ID
        """
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(q=query, fields="files(id,name)").execute()
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                print(f"Found existing folder '{folder_name}': {folder_id}")
                return folder_id
            
            # Create new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"Created new folder '{folder_name}': {folder_id}")
            return folder_id
            
        except Exception as e:
            print(f"Error creating/finding folder '{folder_name}': {e}")
            raise
    
    def setup_processing_folders(self):
        """Setup processed_daily_book_closing folder"""
        try:
            # Get parent folder (same parent as daily_book_closing folder)
            daily_folder = self.service.files().get(fileId=self.DAILY_BOOK_CLOSING_FOLDER_ID, fields='parents').execute()
            parent_folder_id = daily_folder.get('parents', ['root'])[0]

            # First create or get the main 'processed' folder
            processed_main_folder_id = self.get_or_create_folder('processed', parent_folder_id)
            
            # Create or get processed_daily_book_closing folder
            self.processed_folder_id = self.get_or_create_folder('processed_daily_book_closing', processed_main_folder_id)

            print(f"Processed folder ID: {self.processed_folder_id}")
            
        except Exception as e:
            print(f"Error setting up processing folders: {e}")
            raise
    
    def move_and_rename_file(self, file_id: str, new_name: str, destination_folder_id: str):
        """
        Move file to destination folder and rename it
        
        Args:
            file_id: Google Drive file ID
            new_name: New name for the file
            destination_folder_id: Destination folder ID
        """
        try:
            # Get current file info
            file_info = self.service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file_info.get('parents'))
            
            # Move file and rename
            file = self.service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                body={'name': new_name},
                fields='id,parents'
            ).execute()
            
            print(f"Moved and renamed file to: {new_name}")
            
        except Exception as e:
            print(f"Error moving/renaming file: {e}")
            raise
    
    def download_image_to_file(self, file_id: str, file_name: str) -> str:
        """
        Download image from Google Drive and save to local file
        
        Args:
            file_id: Google Drive file ID
            file_name: Original file name
            
        Returns:
            str: Local file path where image was saved
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Authentication failed")
        
        try:
            print(f"Downloading image: {file_name}")
            
            # Create safe filename
            safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            local_file_path = os.path.join(self.local_folder, safe_filename)
            
            # Skip if file already exists
            if os.path.exists(local_file_path):
                print(f"File already exists: {safe_filename}")
                return local_file_path
            
            # Download file content
            request = self.service.files().get_media(fileId=file_id)
            file_content = request.execute()
            
            # Save to local file
            with open(local_file_path, 'wb') as f:
                f.write(file_content)
            
            print(f"Downloaded: {safe_filename} ({len(file_content)} bytes)")
            return local_file_path
            
        except HttpError as e:
            error_msg = f"Google Drive API error downloading {file_name}: {e}"
            print(f"Error: {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error downloading {file_name}: {e}"
            print(f"Error: {error_msg}")
            raise Exception(error_msg)
    
    def get_all_images(self) -> List[Dict]:
        """Get all images in the daily book closing folder"""
        if not self.service:
            if not self.authenticate():
                return []
        
        try:
            # Query for all images in the daily book closing folder
            query = f"'{self.DAILY_BOOK_CLOSING_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                orderBy='modifiedTime desc',
                fields="files(id,name,mimeType,size,modifiedTime,createdTime)",
                supportsAllDrives=True,
                pageSize=1000
            ).execute()
            
            images = results.get('files', [])
            print(f"Found {len(images)} images in daily book closing folder")
            return images
            
        except Exception as e:
            print(f"Error fetching images: {e}")
            return []
    
    def group_images_by_date(self, images: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group images by date based on their names or timestamps
        
        Args:
            images: List of image file info from Google Drive
            
        Returns:
            Dict[str, List[Dict]]: Dictionary mapping dates to lists of images
        """
        date_groups = defaultdict(list)
        
        for image in images:
            # Extract date from filename or creation date
            file_name = image['name']
            created_time = image.get('createdTime', '')
            
            # Try to extract date from filename first (common format: YYYY-MM-DD)
            date_str = None
            
            # Look for date patterns in filename
            import re
            date_patterns = [
                r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
                r'(\d{4}_\d{2}_\d{2})',  # YYYY_MM_DD
                r'(\d{2}-\d{2}-\d{4})',  # DD-MM-YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, file_name)
                if match:
                    date_str = match.group(1)
                    # Convert to standard format
                    if '_' in date_str:
                        date_str = date_str.replace('_', '-')
                    elif len(date_str.split('-')[0]) == 2:  # DD-MM-YYYY format
                        parts = date_str.split('-')
                        date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    break
            
            # If no date in filename, use creation date
            if not date_str and created_time:
                try:
                    from datetime import datetime
                    created_dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                    date_str = created_dt.strftime('%Y-%m-%d')
                except:
                    date_str = "unknown"
            
            if not date_str:
                date_str = "unknown"
            
            date_groups[date_str].append(image)
            print(f"Grouped {file_name} under date: {date_str}")
        
        return dict(date_groups)
    
    def process_image_group(self, date: str, images: List[Dict], model: str) -> tuple:
        """
        Process a group of images for the same date
        
        Args:
            date: Date string
            images: List of image file info for this date
            model: Vision model to use for OCR
            
        Returns:
            tuple: (success: bool, processed_files: List[str])
        """
        print(f"\nProcessing {len(images)} images for date: {date}")
        print("=" * 50)
        
        json_outputs = []
        processed_files = []
        file_mappings = []
        
        # Download and process each image
        for i, image in enumerate(images, 1):
            try:
                print(f"\nImage {i}/{len(images)}: {image['name']}")
                
                # Download image
                local_path = self.download_image_to_file(image['id'], image['name'])
                
                # Run OCR
                print(f"Running OCR on {image['name']}...")
                parsed_json = ocr_daily_closing(local_path, model=model)
                
                json_outputs.append(parsed_json)
                processed_files.append(local_path)
                file_mappings.append({
                    'file_id': image['id'],
                    'file_name': image['name'],
                    'local_path': local_path
                })
                
                print(f"OCR completed for {image['name']}")
                
                # Brief pause between OCR calls
                if i < len(images):
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Error processing {image['name']}: {e}")
                continue
        
        if not json_outputs:
            print(f"No successful OCR results for date {date}")
            return False, []
        
        # Merge all JSON outputs
        print(f"\nMerging {len(json_outputs)} JSON outputs for date {date}...")
        merged_data = merge_daily_closing_data(json_outputs)
        
        # Save merged data to database
        print(f"Saving merged data to database for date {date}...")
        success, closing_date = save_daily_closing_to_db(merged_data, session)
        
        if success:
            print(f"Successfully saved merged data for {closing_date}")
            
            # Move and rename files
            for i, file_info in enumerate(file_mappings, 1):
                try:
                    date_safe = closing_date.replace('-', '')
                    new_filename = f"{date_safe}_dbc_{i}.jpg"
                    
                    print(f"Moving {file_info['file_name']} to processed folder as: {new_filename}")
                    self.move_and_rename_file(file_info['file_id'], new_filename, self.processed_folder_id)
                    
                except Exception as e:
                    print(f"Error moving file {file_info['file_name']}: {e}")
            
            return True, processed_files
        else:
            print(f"Failed to save data for date {date}")
            return False, processed_files
    
    def process_all_images(self, model: str):
        """
        Main function: Download all images, group by date, process each group, and save to DB
        
        Args:
            model: Vision model to use for OCR
        """
        print("Daily Book Closing Sentinel - Processing System")
        print("=" * 70)
        print(f"Google Drive Folder ID: {self.DAILY_BOOK_CLOSING_FOLDER_ID}")
        print(f"Local Download Folder: {self.local_folder}")
        print(f"Vision Model: {model}")
        print(f"Database: dailydelights.db")
        print("=" * 70)
        
        # Authenticate with Google Drive
        if not self.authenticate():
            print("Authentication failed. Exiting.")
            return
        
        # Setup processing folders
        print(f"\nStep 1: Setting up processing folders")
        self.setup_processing_folders()
        
        # Get all images from Google Drive
        print(f"\nStep 2: Fetching images from Google Drive")
        images = self.get_all_images()
        
        if not images:
            print("No images found in Google Drive folder")
            return
        
        # Group images by date
        print(f"\nStep 3: Grouping images by date")
        date_groups = self.group_images_by_date(images)
        
        print(f"Found {len(date_groups)} date groups:")
        for date, imgs in date_groups.items():
            print(f"  - {date}: {len(imgs)} images")
        
        # Process each date group
        print(f"\nStep 4: Processing each date group")
        total_groups = len(date_groups)
        processed_successfully = 0
        processed_with_errors = 0
        
        for group_num, (date, imgs) in enumerate(date_groups.items(), 1):
            print(f"\n{'='*70}")
            print(f"Processing Group {group_num}/{total_groups}: {date}")
            print(f"{'='*70}")
            
            try:
                success, processed_files = self.process_image_group(date, imgs, model)
                
                if success:
                    processed_successfully += 1
                    print(f"Successfully processed date group: {date}")
                else:
                    processed_with_errors += 1
                    print(f"Failed to process date group: {date}")
                    
                # Pause between date groups
                if group_num < total_groups:
                    print(f"Waiting 5 seconds before next date group...")
                    time.sleep(5)
                    
            except Exception as e:
                processed_with_errors += 1
                print(f"Error processing date group {date}: {e}")
                continue
        
        # Final summary
        print("\n" + "=" * 70)
        print("FINAL PROCESSING SUMMARY")
        print("=" * 70)
        print(f"Total Date Groups Found: {total_groups}")
        print(f"Successfully Processed: {processed_successfully}")
        print(f"Failed to Process: {processed_with_errors}")
        print(f"Success Rate: {(processed_successfully/total_groups)*100:.1f}%")
        print(f"Downloaded Files Location: {os.path.abspath(self.local_folder)}")
        print(f"Database: dailydelights.db")
        print(f"Processed Files Moved to: processed_daily_book_closing folder")
        print("=" * 70)
        
        if processed_successfully > 0:
            print("Processing completed! Check dailydelights.db for daily closing data.")
            print("Each date's images were merged into a single database record.")
        else:
            print("No date groups were processed successfully. Check errors above.")
            
        return {
            "total_groups": total_groups,
            "success": processed_successfully,
            "errors": processed_with_errors,
            "success_rate": (processed_successfully/total_groups)*100 if total_groups > 0 else 0
        }

def cleanup_local_images(local_folder: str):
    """
    Delete all downloaded images from local folder after processing

    Args:
        local_folder: Path to the local folder containing downloaded images
    """
    if not os.path.exists(local_folder):
        return

    try:
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        deleted_count = 0

        for filename in os.listdir(local_folder):
            if any(filename.lower().endswith(ext) for ext in image_extensions):
                file_path = os.path.join(local_folder, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")

        print(f"Cleanup completed: Deleted {deleted_count} local image files from {local_folder}")

    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    """Main entry point - Automatically process with default settings"""

    # Verify environment
    if not TOGETHER_API_KEY:
        print("TOGETHER_API_KEY not found in environment variables")
        return {"success": False, "error": "API key not found"}

    # Default model and settings
    model = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"

    print("🚀 Daily Book Closing Sentinel - Automatic Processing")
    print(f"🤖 Using model: {model}")

    # Start processing
    sentinel = DailyBookClosingSentinel()

    try:
        result = sentinel.process_all_images(model=model)

        # Cleanup local images after processing
        print(f"\n🧹 Cleaning up local images...")
        cleanup_local_images(sentinel.local_folder)

        return {
            "success": True,
            "total_groups": result["total_groups"],
            "processed": result["success"],
            "errors": result["errors"],
            "success_rate": result["success_rate"]
        }

    except Exception as e:
        print(f"Fatal error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    main()