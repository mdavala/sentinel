#!/usr/bin/env python3
"""
Process June Invoice PDFs and extract order information
Uses Together AI Vision API to extract invoice data from PDF files
"""

import os
import base64
import json
import sqlite3
import re
from datetime import datetime
from typing import List, Dict, Optional
import PyPDF2
from pdf2image import convert_from_path
from PIL import Image
import io
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv(override=True)
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =============================================================================
# PYDANTIC MODELS FOR INVOICE EXTRACTION
# =============================================================================

class InvoiceItem(BaseModel):
    item_name: str = Field(..., description="Product or item name")
    quantity: float = Field(..., description="Quantity ordered")
    unit_price: Optional[float] = Field(None, description="Price per unit")
    total_amount: Optional[float] = Field(None, description="Total amount for this item")
    unit: Optional[str] = Field(None, description="Unit of measurement (carton, piece, kg, etc.)")

class InvoiceData(BaseModel):
    supplier_name: str = Field(..., description="Name of the supplier/vendor")
    invoice_number: str = Field(..., description="Invoice number or order number")
    invoice_date: Optional[str] = Field(None, description="Invoice date in YYYY-MM-DD format")
    total_amount: Optional[float] = Field(None, description="Total invoice amount")
    items: List[InvoiceItem] = Field(..., description="List of items in the invoice")

class InvoiceResponse(BaseModel):
    invoice: InvoiceData

# =============================================================================
# PDF TO IMAGE CONVERSION
# =============================================================================

def pdf_to_base64_image(pdf_path: str, page_num: int = 0) -> str:
    """Convert first page of PDF to base64 encoded image"""
    try:
        # Convert PDF page to image
        images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1, dpi=150)

        if not images:
            return None

        # Convert PIL Image to base64
        img = images[0]
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_bytes = buffered.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')

        return img_base64
    except Exception as e:
        print(f"Error converting PDF to image: {e}")
        return None

# =============================================================================
# VISION OCR FOR INVOICE EXTRACTION
# =============================================================================

def extract_invoice_data_from_pdf(pdf_path: str, model: str = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8") -> Optional[InvoiceData]:
    """
    Extract invoice data from PDF using Together AI Vision API
    """
    if not TOGETHER_API_KEY:
        raise ValueError("TOGETHER_API_KEY not set in environment")

    # Convert PDF to base64 image
    print(f"📄 Converting PDF to image: {os.path.basename(pdf_path)}")
    img_base64 = pdf_to_base64_image(pdf_path)

    if not img_base64:
        print(f"❌ Failed to convert PDF to image")
        return None

    # System prompt for invoice extraction
    system_prompt = """
    You are an intelligent invoice parser for supplier order analysis.

    Extract the following information from this invoice:

    REQUIRED FIELDS:
    - supplier_name: Name of the supplier/vendor (look for company name at top)
    - invoice_number: Invoice number, order number, or bill number
    - items: List of ALL items with:
      * item_name: Product name
      * quantity: Quantity ordered (number only)
      * unit_price: Price per unit if visible
      * total_amount: Total amount for that item
      * unit: Unit of measurement (carton, pcs, kg, box, etc.)

    OPTIONAL FIELDS:
    - invoice_date: Date in YYYY-MM-DD format
    - total_amount: Grand total amount

    IMPORTANT RULES:
    1. Extract EVERY item from the invoice
    2. Do NOT include milk or bread items
    3. Clean product names (remove extra codes/symbols)
    4. If quantity has unit (e.g., "10 cartons"), separate into quantity=10, unit="carton"
    5. Use null for missing values
    6. Return clean JSON only

    STRICT RULE: Return complete invoice object with all items in JSON Format.
    """

    # Prepare image URL
    image_url = f"data:image/jpeg;base64,{img_base64}"

    # Make request to Together AI
    print(f"🔍 Running OCR on invoice...")
    response = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "response_format": {
                "type": "json_object",
                "schema": InvoiceResponse.model_json_schema(),
            }
        },
        verify=False,
        timeout=120
    )

    if response.status_code != 200:
        print(f"❌ API Error: {response.status_code}, {response.text}")
        return None

    # Parse response
    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Clean JSON
    cleaned_json = content.strip()
    if cleaned_json.startswith('```json'):
        cleaned_json = cleaned_json.replace('```json', '').replace('```', '').strip()
    elif cleaned_json.startswith('```'):
        cleaned_json = cleaned_json.replace('```', '').strip()

    # Parse to Pydantic model
    invoice_response = json.loads(cleaned_json)
    invoice_data = invoice_response.get('invoice')

    if invoice_data:
        return InvoiceData(**invoice_data)

    return None

# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def create_supplier_orders_db():
    """Create supplierOrders.db database"""
    db_path = 'supplierOrders.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create main orders tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE,
            supplier_name TEXT NOT NULL,
            invoice_date TEXT,
            total_amount REAL,
            month TEXT,
            year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print(f"✅ Created supplierOrders.db")

def create_supplier_table(supplier_name: str):
    """Create a table for specific supplier"""
    db_path = 'supplierOrders.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Clean supplier name for table name (remove spaces, special chars)
    table_name = re.sub(r'[^a-zA-Z0-9]', '_', supplier_name).lower()
    table_name = f"supplier_{table_name}"

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            invoice_date TEXT,
            item_name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            total_amount REAL,
            month TEXT,
            year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_number) REFERENCES orders_master(invoice_number)
        )
    ''')

    conn.commit()
    conn.close()
    return table_name

def save_invoice_to_db(invoice_data: InvoiceData):
    """Save invoice data to supplier-specific table"""
    db_path = 'supplierOrders.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Extract month and year from invoice date
    month = None
    year = None
    if invoice_data.invoice_date:
        try:
            dt = datetime.strptime(invoice_data.invoice_date, "%Y-%m-%d")
            month = dt.strftime("%B")  # Full month name
            year = dt.year
        except:
            pass

    # Insert into orders_master
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO orders_master
            (invoice_number, supplier_name, invoice_date, total_amount, month, year)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (invoice_data.invoice_number, invoice_data.supplier_name,
              invoice_data.invoice_date, invoice_data.total_amount, month, year))
    except sqlite3.IntegrityError:
        print(f"⚠️ Invoice {invoice_data.invoice_number} already exists, skipping...")
        conn.close()
        return False

    # Create supplier table if not exists
    table_name = create_supplier_table(invoice_data.supplier_name)

    # Insert items into supplier table
    for item in invoice_data.items:
        # Skip milk and bread
        item_lower = item.item_name.lower()
        if 'milk' in item_lower or 'bread' in item_lower or 'meiji' in item_lower:
            print(f"⏭️  Skipping: {item.item_name}")
            continue

        cursor.execute(f'''
            INSERT INTO {table_name}
            (invoice_number, invoice_date, item_name, quantity, unit, unit_price, total_amount, month, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_data.invoice_number, invoice_data.invoice_date, item.item_name,
              item.quantity, item.unit, item.unit_price, item.total_amount, month, year))

    conn.commit()
    conn.close()
    print(f"✅ Saved invoice {invoice_data.invoice_number} to {table_name}")
    return True

# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================

def process_all_june_invoices(invoices_dir: str = "Invoices/June_invoices"):
    """Process all June invoice PDFs"""
    print("🚀 Starting June Invoices Processing")
    print("=" * 70)

    # Create database
    create_supplier_orders_db()

    # Get all PDF files
    pdf_files = [f for f in os.listdir(invoices_dir) if f.endswith('.pdf')]
    pdf_files.sort()

    print(f"📂 Found {len(pdf_files)} PDF files")
    print("=" * 70)

    processed = 0
    failed = 0
    skipped = 0

    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(invoices_dir, pdf_file)

        print(f"\n📊 Processing {i}/{len(pdf_files)}: {pdf_file}")

        try:
            # Extract invoice data
            invoice_data = extract_invoice_data_from_pdf(pdf_path)

            if invoice_data:
                # Save to database
                success = save_invoice_to_db(invoice_data)
                if success:
                    processed += 1
                else:
                    skipped += 1
            else:
                failed += 1
                print(f"❌ Failed to extract data from {pdf_file}")

            # Brief pause to avoid rate limits (8 seconds = max 7.5 requests/minute, well under 10/minute limit)
            if i < len(pdf_files):
                import time
                time.sleep(8)

        except Exception as e:
            failed += 1
            print(f"❌ Error processing {pdf_file}: {e}")
            continue

    # Final summary
    print("\n" + "=" * 70)
    print("📈 PROCESSING SUMMARY")
    print("=" * 70)
    print(f"📂 Total PDFs: {len(pdf_files)}")
    print(f"✅ Successfully Processed: {processed}")
    print(f"⏭️  Skipped (Duplicates): {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Success Rate: {(processed/(len(pdf_files)))*100:.1f}%")
    print(f"🗄️ Database: supplierOrders.db")
    print("=" * 70)

if __name__ == "__main__":
    process_all_june_invoices()
