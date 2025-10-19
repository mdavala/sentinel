#!/usr/bin/env python3
"""
stockSentinel.py - Complete Invoice Processing System
Fetches images from Google Drive and processes them using Vision OCR
"""

import os
import time
import base64
import mimetypes
import json
import requests
from datetime import datetime, timedelta
from typing import Set, List, Dict, Optional
from io import BytesIO

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
from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables
load_dotenv(override=True)

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =============================================================================
# VISION OCR MODELS AND DATABASE SETUP (from together_vision.py)
# =============================================================================

class InvoiceItem(BaseModel):
    # Required fields
    invoice_number: str = Field(..., description="Invoice number / bill number / receipt number")
    supplier_name: str = Field(..., description="Name of the supplier or vendor")
    item_name: str = Field(..., description="Product or item name")
    quantity: int = Field(..., description="Number of items ordered")

    # Optional fields
    invoice_date: Optional[str] = Field(None, description="Invoice date in YYYY-MM-DD format")
    supplies_received_date: Optional[str] = Field(None, description="Date when supplies were received in YYYY-MM-DD format")
    unit_price: Optional[float] = Field(None, description="Price per unit or per carton")
    carton_or_loose: Optional[str] = Field(
        None, description='"carton" or "loose" (how the item is sold)'
    )
    items_per_carton: Optional[int] = Field(
        None, description="If sold by carton, number of loose items per carton"
    )
    unit_price_item: Optional[float] = Field(
        None, description="Price per loose item (unit_price ÷ items_per_carton)"
    )
    amount_per_item: Optional[float] = Field(
        None, description="Total amount (quantity × unit_price)"
    )
    gst_amount: Optional[float] = Field(
        None, description="GST amount (9% of amount_per_item)"
    )
    total_amount_per_item: Optional[float] = Field(
        None, description="Final total = amount_per_item + gst_amount"
    )
    barcode: Optional[str] = Field(None, description="Product barcode or SKU if available")

    # Payment-related fields
    payment_status: str = Field(
        default="pending", 
        description="Payment status: 'paid' if invoice shows payment is completed, 'pending' if payment is due or not mentioned"
    )

    # Auto-calculations
    @field_validator("unit_price_item")
    def calc_unit_price_item(cls, v, values):
        if v is None and values.get("unit_price") and values.get("items_per_carton"):
            return values["unit_price"] / values["items_per_carton"]
        return v

    @field_validator("amount_per_item")
    def calc_amount_per_item(cls, v, values):
        if v is None and values.get("quantity") and values.get("unit_price"):
            return values["quantity"] * values["unit_price"]
        return v

    @field_validator("gst_amount")
    def calc_gst(cls, v, values):
        if v is None and values.get("amount_per_item"):
            return round(values["amount_per_item"] * 0.09, 2)
        return v

    @field_validator("total_amount_per_item")
    def calc_total(cls, v, values):
        if v is None and values.get("amount_per_item") is not None:
            gst = values.get("gst_amount") or 0
            return values["amount_per_item"] + gst
        return v

class InvoiceResponse(BaseModel):
    items: List[InvoiceItem]

# SQLAlchemy setup
Base = declarative_base()

class InvoiceTable(Base):
    __tablename__ = "invoice_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String)
    supplier_name = Column(String)
    item_name = Column(String)
    quantity = Column(Integer)
    total_amount = Column(Float)

    invoice_date = Column(String, nullable=True)
    unit_price = Column(Float, nullable=True)
    carton_or_loose = Column(String, nullable=True)
    items_per_carton = Column(Integer, nullable=True)
    unit_price_item = Column(Float, nullable=True)
    amount_per_item = Column(Float, nullable=True)
    gst_amount = Column(Float, nullable=True)
    total_amount_per_item = Column(Float, nullable=True)
    barcode = Column(String, nullable=True)

class PaymentsTable(Base):
    __tablename__ = "payments_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String)
    supplies_received_date = Column(Date, nullable=True)
    supplier_name = Column(String)
    total_amount = Column(Float)
    payment_status = Column(String)
    payment_due_date = Column(Date, nullable=True)

# Create DB connection
engine = create_engine("sqlite:///dailydelights.db")
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# =============================================================================
# VISION OCR FUNCTIONS (from together_vision.py)
# =============================================================================

def encode_image(image_path: str) -> str:
    """Convert image file to base64 string"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def is_remote_file(file_path: str) -> bool:
    """Check if file path is a URL"""
    return file_path.startswith("http://") or file_path.startswith("https://")

def parse_date_string(date_str):
    """
    Parse date string and return datetime.date object
    Handles various date formats and returns None if parsing fails
    """
    if not date_str:
        return None
    
    # Common date formats to try
    date_formats = [
        "%Y-%m-%d",      # 2024-01-15
        "%d/%m/%Y",      # 15/01/2024
        "%d-%m-%Y",      # 15-01-2024
        "%m/%d/%Y",      # 01/15/2024
        "%m-%d-%Y",      # 01-15-2024
        "%Y/%m/%d",      # 2024/01/15
        "%d.%m.%Y",      # 15.01.2024
        "%Y.%m.%d"       # 2024.01.15
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    
    print(f"Could not parse date: {date_str}")
    return None

def ocr(file_path: str, model: str, api_key: str = TOGETHER_API_KEY):
    """
    Run OCR using Together AI Vision model and return JSON output.
    """
    if not api_key:
        raise ValueError("⚠ TOGETHER_API_KEY not set in environment")

    # Use the provided model name directly
    vision_llm = model

    # System prompt (OCR → JSON conversion)
    system_prompt = """
        You are an intelligent invoice parsing agent for Daily Delights inventory management.
        
        Analyze the invoice image and extract the following information:

        CRITICAL INSTRUCTIONS:
            1. Extract EVERY piece of information you can see in the invoice
            2. Look at EVERY part of the invoice - header, body, footer, stamps, watermarks, delivery notes
            3. If a field is not clearly visible, set it to null - DO NOT guess or assume
            4. Pay special attention to dates, amounts, and payment status indicators
        
        REQUIRED FIELDS:
        - Invoice_number: Invoice number or bill number or receipt number mentioned in the image. 
        Sometimes invoice number can be Sales Order No. Check if there is any unique number that can identify this invoice.
        - supplier_name: Name of the supplier/vendor
        - item_name: Product/item name  
        - quantity: Number of items ordered
        
        OPTIONAL FIELDS:
        - invoice_date: Invoice date in YYYY-MM-DD format (extract from invoice header/top section)
        - unit_price: Price per unit
        - carton_or_loose: "carton" or "loose" (how item is sold)
        - items_per_carton: If sold by carton, how many loose items per carton
        - unit_price_item: Calculate price per loose item (unit_price ÷ items_per_carton)
        - amount_per_item: Total amount (quantity × unit_price)
        - gst_amount: GST amount (9% of amount_per_item)
        - total_amount_per_item: amount_per_item + gst_amount
        - barcode: Product barcode/SKU if visible
        - payment_status: Set to "paid" only if you see the handwritten "paid" on invoice (OR) Default to "pending" if payment status is unclear or handwritten as "pending" or "payment pending"


        PAYMENT STATUS EXTRACTION RULES:
        - STRICT RULE: Set to "paid" only if you see the handwritten word "paid" on invoice
        - Default to "pending" if payment status is unclear or not mentioned or handwritten as "pending" or "payment pending"

        IMPORTANT RULES:
        1. If information is not clearly visible, set to null
        2. For invoice_date, look for date in the invoice header/top section, convert to YYYY-MM-DD format
        3. For calculations, use the exact values from the image
        4. If carton_or_loose is "carton" and items_per_carton is provided, calculate unit_price_item
        5. Return clean, structured JSON only
        
        STRICT RULE: Return by Each item with all fields in JSON Format. Use null for missing/unclear values.
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
                "schema": InvoiceResponse.model_json_schema(),
            }
        },
        verify=False
    )

    if response.status_code != 200:
        raise Exception(f"⚠ API Error: {response.status_code}, {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]

def save_json_to_db(json_string, session):
    """
    Convert JSON string to Python object and save each item to SQL database
    
    Args:
        json_string (str): JSON string containing items data
        session: SQLAlchemy session object
    
    Returns:
        tuple: (number of items saved, supplier_name for the first item, invoice_date for the first item)
    """
    try:
        print(f"📄 Parsing JSON response...")
        
        # Clean the JSON string if it has markdown formatting
        cleaned_json = json_string.strip()
        if cleaned_json.startswith('```json'):
            cleaned_json = cleaned_json.replace('```json', '').replace('```', '').strip()
        elif cleaned_json.startswith('```'):
            cleaned_json = cleaned_json.replace('```', '').strip()
        
        #print(f"📄 Cleaned JSON (first 200 chars): {cleaned_json[:200]}...")
        print(f"📄 Cleaned JSON (first 200 chars): {cleaned_json}...")
        
        # Parse JSON string to Python dictionary
        data = json.loads(cleaned_json)
        
        # Extract items from the parsed data
        items = data.get('items', [])
        
        if not items:
            print(f"⚠️ No 'items' found in JSON response")
            print(f"📄 Available keys: {list(data.keys())}")
            return 0, None, None
        
        print(f"📄 Found {len(items)} items to save")
        
        saved_count = 0
        supplier_name = None
        invoice_date = None
        payment_status = None
        payment_due_date = None
        current_date = datetime.now().date()
        total_amount = sum([
            item.get('total_amount_per_item') or 0 
            for item in items 
            if item.get('total_amount_per_item') is not None
        ])

        # total_amount = sum([item.get('total_amount_per_item', 0) for item in items])
        print(f"total_amount. {total_amount}")

        # Process each item
        for i, item_data in enumerate(items, 1):
            print(f"📄 Processing item {i}: {item_data.get('item_name', 'Unknown')}")
            
            # Get supplier name and invoice date from first item
            if i == 1:
                supplier_name = item_data.get('supplier_name', 'Unknown_Supplier')
                invoice_date = item_data.get('invoice_date')
                invoice_number=item_data.get('invoice_number')
                payment_status = item_data.get('payment_status', 'pending')
            
            # Create new invoice record
            invoice_item = InvoiceTable(
                invoice_number=invoice_number,
                supplier_name=supplier_name,
                total_amount= total_amount,
                item_name=item_data.get('item_name'),
                quantity=item_data.get('quantity'),
                invoice_date=invoice_date,
                unit_price=item_data.get('unit_price'),
                carton_or_loose=item_data.get('carton_or_loose'),
                items_per_carton=item_data.get('items_per_carton'),
                unit_price_item=item_data.get('unit_price_item'),
                amount_per_item=item_data.get('amount_per_item'),
                gst_amount=item_data.get('gst_amount'),
                total_amount_per_item=item_data.get('total_amount_per_item'),
                barcode=item_data.get('barcode')
            )
            
            # Add to session
            session.add(invoice_item)
            saved_count += 1
        
        # *********************  Create Payments Table ***********************

        if payment_status.lower() == "paid":
            payment_due_date = None  # No due date if already paid
            print(f"Payment status is PAID - no due date set")
        else:
            payment_due_date = current_date + timedelta(days=5)
            print(f"Payment status is PENDING - due date set to: {payment_due_date}")

        existing_payment = session.query(PaymentsTable).filter_by(
            invoice_number=invoice_number,
            supplier_name=supplier_name
        ).first()
        
        if existing_payment:
            print(f"Duplicate invoice detected: {invoice_number} already exists in payments_table")
            return 0, supplier_name, invoice_date, True
        
        payment_entry = PaymentsTable(
            invoice_number=invoice_number,
            supplies_received_date=current_date,
            supplier_name=supplier_name,
            total_amount=total_amount,
            payment_status=payment_status,
            payment_due_date=payment_due_date
        )

        print(f"final payment_entry: {payment_entry}")
        session.add(payment_entry)

        # Commit all changes
        session.commit()
        print(f"✅ Successfully saved {saved_count} items to database")
        return saved_count, supplier_name, invoice_date
        
    except json.JSONDecodeError as e:
        print(f"⚠ Error parsing JSON: {e}")
        print(f"📄 Raw JSON string: {json_string}")
        session.rollback()
        return 0, None, None
    except Exception as e:
        print(f"⚠ Error saving to database: {e}")
        print(f"📄 Exception type: {type(e).__name__}")
        session.rollback()
        return 0, None, None

# =============================================================================
# GOOGLE DRIVE FUNCTIONS (UPDATED WITH FILE MANAGEMENT)
# =============================================================================

class StockSentinel:
    """Process all invoice images from Google Drive through Vision OCR"""
    
    # Google Drive API configuration
    SCOPES = ['https://www.googleapis.com/auth/drive']  # Changed to full access for moving files
    CREDENTIALS_FILE = 'credentials.json'
    TOKEN_FILE = 'token.json'
    
    # Your invoices folder ID
    INVOICES_FOLDER_ID = '162d4TyRYwvGXdeVYkZTAY6AMpc50sJtf'
    
    def __init__(self, local_folder: str = "gdrive_invoices"):
        """
        Initialize StockSentinel
        
        Args:
            local_folder: Local folder to download images to
        """
        self.service = None
        self.local_folder = local_folder
        self.processed_folder_id = None
        self.error_folder_id = None
        
        # Create local folder if it doesn't exist
        if not os.path.exists(self.local_folder):
            os.makedirs(self.local_folder)
            print(f"✅ Created local folder: {self.local_folder}")
        else:
            print(f"📂 Using existing folder: {self.local_folder}")
        
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
        print("✅ Authentication successful")
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
                print(f"📂 Found existing folder '{folder_name}': {folder_id}")
                return folder_id
            
            # Create new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"✅ Created new folder '{folder_name}': {folder_id}")
            return folder_id
            
        except Exception as e:
            print(f"⚠ Error creating/finding folder '{folder_name}': {e}")
            raise
    
    def setup_processing_folders(self):
        """Setup processed_invoices and error_invoices folders"""
        try:
            # Get parent folder (same parent as invoices folder)
            invoices_folder = self.service.files().get(fileId=self.INVOICES_FOLDER_ID, fields='parents').execute()
            parent_folder_id = invoices_folder.get('parents', ['root'])[0]
            
            # First create or get the main 'processed' folder
            processed_main_folder_id = self.get_or_create_folder('processed', parent_folder_id)
            
            # Then create or get the 'processed_invoices' folder inside 'processed'
            self.processed_folder_id = self.get_or_create_folder('processed_invoices', processed_main_folder_id)
            
            # Create or get error_invoices folder (also inside 'processed' folder)
            self.error_folder_id = self.get_or_create_folder('error_invoices', processed_main_folder_id)
            
            print(f"📂 Processed folder ID: {self.processed_folder_id}")
            print(f"📂 Error folder ID: {self.error_folder_id}")
            
        except Exception as e:
            print(f"⚠ Error setting up processing folders: {e}")
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
            file_info = self.service.files().get(fileId=file_id, fields='parents,name').execute()
            previous_parents = ",".join(file_info.get('parents', []))
            current_name = file_info.get('name', 'unknown')
            
            print(f"📁 Moving '{current_name}' to folder {destination_folder_id}")
            print(f"📁 Renaming to: {new_name}")
            print(f"📁 Removing from parents: {previous_parents}")
            
            # Move file and rename
            file = self.service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                body={'name': new_name},
                fields='id,parents,name'
            ).execute()
            
            print(f"✅ Successfully moved and renamed file")
            print(f"📁 New file ID: {file.get('id')}")
            print(f"📁 New parents: {file.get('parents')}")
            print(f"📁 New name: {file.get('name')}")
            
            # Verify the file exists in the destination folder
            verify_query = f"'{destination_folder_id}' in parents and name='{new_name}' and trashed=false"
            verify_results = self.service.files().list(q=verify_query, fields="files(id,name)").execute()
            verify_files = verify_results.get('files', [])
            
            if verify_files:
                print(f"✅ Verification successful: File found in destination folder")
            else:
                print(f"⚠ Warning: File not found in destination folder after move")
                
        except Exception as e:
            print(f"⚠ Error moving/renaming file: {e}")
            print(f"📁 File ID: {file_id}")
            print(f"📁 Destination folder: {destination_folder_id}")
            print(f"📁 New name: {new_name}")
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
            print(f"📥 Downloading image: {file_name}")
            
            # Create safe filename (remove/replace problematic characters)
            safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            local_file_path = os.path.join(self.local_folder, safe_filename)
            
            # Skip if file already exists
            if os.path.exists(local_file_path):
                print(f"⭐️ File already exists: {safe_filename}")
                return local_file_path
            
            # Download file content
            request = self.service.files().get_media(fileId=file_id)
            file_content = request.execute()
            
            # Save to local file
            with open(local_file_path, 'wb') as f:
                f.write(file_content)
            
            print(f"✅ Downloaded: {safe_filename} ({len(file_content)} bytes)")
            return local_file_path
            
        except HttpError as e:
            error_msg = f"Google Drive API error downloading {file_name}: {e}"
            print(f"⚠ {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error downloading {file_name}: {e}"
            print(f"⚠ {error_msg}")
            raise Exception(error_msg)
    
    def get_all_images(self) -> List[Dict]:
        """Get all images in the invoices folder"""
        if not self.service:
            if not self.authenticate():
                return []
        
        try:
            # Query for all images in the invoices folder
            query = f"'{self.INVOICES_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                orderBy='modifiedTime desc',
                fields="files(id,name,mimeType,size,modifiedTime,createdTime)",
                supportsAllDrives=True,
                pageSize=1000  # Get all images
            ).execute()
            
            images = results.get('files', [])
            print(f"📂 Found {len(images)} images in invoices folder")
            return images
            
        except Exception as e:
            print(f"⚠ Error fetching images: {e}")
            return []
    
    def get_local_images(self) -> List[str]:
        """
        Get list of all image files in the local folder
        
        Returns:
            List[str]: List of file paths for images in local folder
        """
        if not os.path.exists(self.local_folder):
            return []
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        local_images = []
        
        for filename in os.listdir(self.local_folder):
            if any(filename.lower().endswith(ext) for ext in image_extensions):
                local_images.append(os.path.join(self.local_folder, filename))
        
        print(f"📂 Found {len(local_images)} local images in {self.local_folder}")
        return local_images
    
    def get_local_image_mapping(self) -> Dict[str, str]:
        """
        Create mapping between local filenames and Google Drive file IDs
        
        Returns:
            Dict[str, str]: Mapping of local filename to Drive file ID
        """
        mapping = {}
        images = self.get_all_images()
        
        for image in images:
            # Create safe filename (same logic as download_image_to_file)
            safe_filename = "".join(c for c in image['name'] if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            local_file_path = os.path.join(self.local_folder, safe_filename)
            
            if os.path.exists(local_file_path):
                mapping[local_file_path] = image['id']
                print(f"📂 Mapped: {safe_filename} -> {image['id']}")
        
        print(f"📂 Created mapping for {len(mapping)} files")
        return mapping
    
    def download_all_images(self) -> List[str]:
        """
        Download all images from Google Drive to local folder
        
        Returns:
            List[str]: List of local file paths for downloaded images
        """
        print(f"📥 Starting download of all images to {self.local_folder}")
        
        # Get all images from Google Drive
        images = self.get_all_images()
        
        if not images:
            print("🔭 No images found in Google Drive folder")
            return []
        
        downloaded_files = []
        
        for i, image in enumerate(images, 1):
            try:
                print(f"\n📊 Download Progress: {i}/{len(images)}")
                local_path = self.download_image_to_file(image['id'], image['name'])
                downloaded_files.append(local_path)
                
                # Brief pause to avoid rate limits
                if i < len(images):
                    time.sleep(2)
                    
            except Exception as e:
                print(f"⚠ Failed to download {image['name']}: {e}")
                continue
        
        print(f"\n✅ Download complete: {len(downloaded_files)} files in {self.local_folder}")
        return downloaded_files
    
    def process_single_image_file(self, file_path: str, file_id: str, model: str) -> tuple:
        """
        Process a single local image file through Vision OCR and save to database
        
        Args:
            file_path: Local file path to the image
            file_id: Google Drive file ID for moving the file
            model: Vision model to use for OCR
            
        Returns:
            tuple: (success: bool, supplier_name: str or None, invoice_date: str or None)
        """
        try:
            filename = os.path.basename(file_path)
            print(f"\n📂 Processing: {filename}")
            
            # Verify file exists
            if not os.path.exists(file_path):
                print(f"⚠ File not found: {file_path}")
                return False, None, None
            
            # Run OCR on the local file
            print(f"🔍 Running OCR on {filename}...")
            parsed_json = ocr(file_path, model=model)
            
            # Save to database
            print(f"💾 Saving to database...")
            saved_count, supplier_name, invoice_date = save_json_to_db(parsed_json, session)
            
            if saved_count > 0:
                print(f"✅ Successfully processed {filename}: {saved_count} items saved")
                return True, supplier_name, invoice_date
            else:
                print(f"⚠️ No items saved for {filename}")
                return False, None, None
                
        except Exception as e:
            print(f"⚠ Error processing {file_path}: {e}")
            return False, None, None
    
    def process_all_images(self, model: str):
        """
        Main function: Download all images as files, then process each through Vision OCR
        
        Complete Workflow:
        1. Authenticate with Google Drive
        2. Setup processing folders (processed_invoices, error_invoices)
        3. Download all images to local gdrive_invoices/ folder
        4. Create mapping between local files and Drive file IDs
        5. For each local image file:
        a. Send local file path to Together AI API
        b. Parse OCR response (JSON)
        c. Save invoice data to SQL database
        d. Move file to appropriate folder (processed/error) with new name
        
        Args:
            model: Vision model to use for OCR
        """
        print("🚀 Stock Sentinel - Complete Invoice Processing System")
        print("=" * 70)
        print(f"📂 Google Drive Folder ID: {self.INVOICES_FOLDER_ID}")
        print(f"📂 Local Download Folder: {self.local_folder}")
        print(f"🤖 Vision Model: {model}")
        print(f"🗄️ Database: dailydelights.db")
        print("=" * 70)
        print("📋 WORKFLOW:")
        print("   1. Setup processing folders in Google Drive")
        print("   2. Download images as files (NOT base64)")
        print("   3. Create file mapping for moving files later")
        print("   4. Send file paths to Together AI API")
        print("   5. Parse invoice data from OCR response")
        print("   6. Save extracted data to SQL database")
        print("   7. Move processed files to appropriate folders")
        print("=" * 70)
        
        # Authenticate with Google Drive
        if not self.authenticate():
            print("⚠ Authentication failed. Exiting.")
            return
        
        # Setup processing folders
        print(f"\n📄 Step 1: Setting up processing folders")
        self.setup_processing_folders()
        
        # Download all images to local folder
        print(f"\n📄 Step 2: Downloading images to {self.local_folder}")
        downloaded_files = self.download_all_images()
        
        # Create mapping between local files and Drive file IDs
        print(f"\n📄 Step 3: Creating file mapping")
        file_mapping = self.get_local_image_mapping()
        
        # Get all local images (including any that were already downloaded)
        print(f"\n📄 Step 4: Listing local image files")
        local_images = self.get_local_images()
        
        if not local_images:
            print("🔭 No images found in local folder")
            return
        
        # Process statistics
        total_images = len(local_images)
        processed_successfully = 0
        processed_with_errors = 0
        
        print(f"\n📄 Step 5: Processing {total_images} local images through OCR...")
        print("-" * 70)
        
        # Process each local image file
        for i, file_path in enumerate(local_images, 1):
            print(f"\n📊 OCR Progress: {i}/{total_images}")
            print(f"🎯 Processing: {os.path.basename(file_path)}")
            
            # Get file ID for this local file
            file_id = file_mapping.get(file_path)
            if not file_id:
                print(f"⚠ Warning: No Google Drive file ID found for {file_path}")
                processed_with_errors += 1
                continue
            
            success, supplier_name, invoice_date = self.process_single_image_file(file_path, file_id, model)
            
            # Generate new filename with supplier name, invoice date, and current timestamp
            current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create safe supplier name
            supplier_safe = "".join(c for c in (supplier_name or "Unknown_Supplier") if c.isalnum() or c in ('_', '-'))
            
            # Format invoice date for filename (replace hyphens with underscores or use fallback)
            if invoice_date:
                # Convert YYYY-MM-DD to YYYY_MM_DD for filename
                invoice_date_safe = invoice_date.replace('-', '_')
            else:
                invoice_date_safe = "NoDate"
            
            # Get original file extension
            original_filename = os.path.basename(file_path)
            file_extension = os.path.splitext(original_filename)[1] or '.jpg'
            
            # New filename format: <supplier>_<invoice_date>_<current_timestamp>.<extension>
            new_filename = f"{supplier_safe}_{invoice_date_safe}_{current_timestamp}{file_extension}"
            
            try:
                if success:
                    processed_successfully += 1
                    print(f"✅ Image {i} processed successfully")
                    
                    # Move to processed folder
                    print(f"📁 Moving to processed_invoices folder as: {new_filename}")
                    self.move_and_rename_file(file_id, new_filename, self.processed_folder_id)
                    
                else:
                    processed_with_errors += 1
                    print(f"⚠ Image {i} failed")
                    
                    # Move to error folder
                    print(f"📁 Moving to error_invoices folder as: {new_filename}")
                    self.move_and_rename_file(file_id, new_filename, self.error_folder_id)
                    
            except Exception as e:
                print(f"⚠ Error moving file: {e}")
                processed_with_errors += 1
            
            # Brief pause between processing to avoid rate limits
            if i < total_images:
                print(f"⏳ Waiting 2 seconds before next image...")
                time.sleep(5)
        
        # Final summary
        print("\n" + "=" * 70)
        print("📈 FINAL PROCESSING SUMMARY")
        print("=" * 70)
        print(f"📂 Total Images Found: {total_images}")
        print(f"✅ Successfully Processed: {processed_successfully}")
        print(f"⚠ Failed to Process: {processed_with_errors}")
        print(f"📊 Success Rate: {(processed_successfully/total_images)*100:.1f}%")
        print(f"📂 Downloaded Files Location: {os.path.abspath(self.local_folder)}")
        print(f"🗄️ Database: dailydelights.db")
        print(f"📁 Processed Files Moved to: processed/processed_invoices folder (ID: {self.processed_folder_id})")
        print(f"📁 Error Files Moved to: processed/error_invoices folder (ID: {self.error_folder_id})")
        print("=" * 70)
        
        if processed_successfully > 0:
            print("🎉 Processing completed! Check dailydelights.db for extracted invoice data.")
            print(f"📂 All image files saved in: {os.path.abspath(self.local_folder)}")
            print(f"📁 Successfully processed invoices moved to 'processed/processed_invoices' folder")
        else:
            print("😞 No images were processed successfully. Check errors above.")
            
        return {
            "total": total_images,
            "success": processed_successfully,
            "errors": processed_with_errors,
            "success_rate": (processed_successfully/total_images)*100 if total_images > 0 else 0
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
                    print(f"⚠ Error deleting {filename}: {e}")

        print(f"🧹 Cleanup completed: Deleted {deleted_count} local image files from {local_folder}")

    except Exception as e:
        print(f"⚠ Error during cleanup: {e}")

def main():
    """Main entry point - Automatically process with default settings"""

    # Verify environment
    if not TOGETHER_API_KEY:
        print("⚠ TOGETHER_API_KEY not found in environment variables")
        return {"success": False, "error": "API key not found"}

    # Default model and settings
    model = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"

    print("🚀 Stock Sentinel - Automatic Invoice Processing")
    print(f"🤖 Using model: {model}")

    # Start processing
    sentinel = StockSentinel()

    try:
        result = sentinel.process_all_images(model=model)

        # Cleanup local images after processing
        print(f"\n🧹 Cleaning up local images...")
        cleanup_local_images(sentinel.local_folder)

        return {
            "success": True,
            "total": result["total"],
            "processed": result["success"],
            "errors": result["errors"],
            "success_rate": result["success_rate"]
        }

    except Exception as e:
        print(f"⚠ Fatal error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    main()