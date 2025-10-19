#!/usr/bin/env python3
"""
Complete PDF Invoice Processor
- Processes all 81 PDFs one by one
- Moves processed files to invoice_processed folder
- Detailed logging for each file
- Handles errors gracefully
- Creates supplierOrders.db with accurate data
"""

import os
import sys
import base64
import json
import sqlite3
import re
import shutil
from datetime import datetime
from typing import List, Dict, Optional
import PyPDF2
from pdf2image import convert_from_path
from PIL import Image
import io
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import time

# Load environment variables
load_dotenv(override=True)
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# Directories
INVOICES_DIR = "Invoices/June_invoices"
PROCESSED_DIR = "Invoices/invoice_processed"

# Ensure processed directory exists
os.makedirs(PROCESSED_DIR, exist_ok=True)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class InvoiceItem(BaseModel):
    item_name: str = Field(..., description="Product or item name")
    quantity: float = Field(..., description="Quantity ordered")
    unit_price: Optional[float] = Field(None, description="Price per unit")
    total_amount: Optional[float] = Field(None, description="Total amount for this item")
    unit: Optional[str] = Field(None, description="Unit of measurement")

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
        images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1, dpi=150)
        if not images:
            return None

        img = images[0]
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_bytes = buffered.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return img_base64
    except Exception as e:
        print(f"❌ Error converting PDF to image: {e}")
        return None

# =============================================================================
# VISION OCR
# =============================================================================

def extract_invoice_data_from_pdf(pdf_path: str, model: str = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8") -> Optional[InvoiceData]:
    """Extract invoice data from PDF using Together AI Vision API"""
    if not TOGETHER_API_KEY:
        raise ValueError("TOGETHER_API_KEY not set in environment")

    img_base64 = pdf_to_base64_image(pdf_path)
    if not img_base64:
        return None

    system_prompt = """
You are an intelligent invoice parser. Extract ALL information from this invoice.

REQUIRED FIELDS:
- supplier_name: Company name at top of invoice
- invoice_number: Invoice/bill number
- items: Extract EVERY item with:
  * item_name: Product name (clean, no codes)
  * quantity: Number ordered
  * unit_price: Price per unit
  * total_amount: Total for that item
  * unit: Unit (carton, pcs, kg, box, etc.)

OPTIONAL:
- invoice_date: Date in YYYY-MM-DD format
- total_amount: Grand total

RULES:
1. Extract EVERY item from invoice
2. Skip milk, bread, meiji items
3. Clean product names
4. Use null for missing values
5. Return ONLY valid JSON

Return complete invoice object in JSON format.
"""

    image_url = f"data:image/jpeg;base64,{img_base64}"

    try:
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
            print(f"❌ API Error: {response.status_code}, {response.text[:200]}")
            return None

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Clean JSON
        cleaned_json = content.strip()
        if cleaned_json.startswith('```json'):
            cleaned_json = cleaned_json.replace('```json', '').replace('```', '').strip()
        elif cleaned_json.startswith('```'):
            cleaned_json = cleaned_json.replace('```', '').strip()

        invoice_response = json.loads(cleaned_json)
        invoice_data = invoice_response.get('invoice')

        if invoice_data:
            return InvoiceData(**invoice_data)

    except Exception as e:
        print(f"❌ OCR Error: {e}")

    return None

# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def create_supplier_orders_db():
    """Create supplierOrders.db database"""
    db_path = 'supplierOrders.db'

    # If exists, don't recreate
    if os.path.exists(db_path):
        print(f"📊 Using existing supplierOrders.db")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_id TEXT UNIQUE,
            supplier_name TEXT NOT NULL,
            supplier_table TEXT NOT NULL,
            order_date TEXT NOT NULL,
            order_number TEXT NOT NULL,
            items_json TEXT NOT NULL,
            estimated_amount REAL,
            status TEXT DEFAULT 'pending',
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ordered_at TIMESTAMP
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
    conn = sqlite3.connect(db_path, timeout=30.0)  # 30 second timeout
    cursor = conn.cursor()

    # Extract month and year
    month = None
    year = None
    if invoice_data.invoice_date:
        try:
            dt = datetime.strptime(invoice_data.invoice_date, "%Y-%m-%d")
            month = dt.strftime("%B")
            year = dt.year
        except:
            pass

    # Check if already exists
    cursor.execute('SELECT id FROM orders_master WHERE invoice_number = ?', (invoice_data.invoice_number,))
    if cursor.fetchone():
        print(f"⏭️  Duplicate: {invoice_data.invoice_number} already in database")
        conn.close()
        return False

    # Insert into orders_master
    try:
        cursor.execute('''
            INSERT INTO orders_master
            (invoice_number, supplier_name, invoice_date, total_amount, month, year)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (invoice_data.invoice_number, invoice_data.supplier_name,
              invoice_data.invoice_date, invoice_data.total_amount, month, year))
    except Exception as e:
        print(f"⚠️ Error inserting to orders_master: {e}")
        conn.rollback()
        conn.close()
        return False

    # Create supplier table
    table_name = create_supplier_table(invoice_data.supplier_name)

    # Insert items
    items_saved = 0
    for item in invoice_data.items:
        # Skip milk/bread
        item_lower = item.item_name.lower()
        if 'milk' in item_lower or 'bread' in item_lower or 'meiji' in item_lower:
            continue

        cursor.execute(f'''
            INSERT INTO {table_name}
            (invoice_number, invoice_date, item_name, quantity, unit, unit_price, total_amount, month, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_data.invoice_number, invoice_data.invoice_date, item.item_name,
              item.quantity, item.unit, item.unit_price, item.total_amount, month, year))
        items_saved += 1

    conn.commit()
    conn.close()

    if items_saved > 0:
        print(f"✅ Saved: {invoice_data.invoice_number} ({invoice_data.supplier_name}) - {items_saved} items")
        return True
    else:
        print(f"⚠️ No items saved for {invoice_data.invoice_number}")
        return False

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_all_pdfs():
    """Process all PDFs in June_invoices folder"""
    print("=" * 80)
    print("🚀 COMPLETE PDF INVOICE PROCESSOR")
    print("=" * 80)
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📂 Source: {INVOICES_DIR}")
    print(f"📁 Processed files will move to: {PROCESSED_DIR}")
    print("=" * 80)

    # Create database
    create_supplier_orders_db()

    # Get all PDFs
    if not os.path.exists(INVOICES_DIR):
        print(f"❌ Directory not found: {INVOICES_DIR}")
        return

    all_files = [f for f in os.listdir(INVOICES_DIR) if f.endswith('.pdf')]
    all_files.sort()

    total_pdfs = len(all_files)
    print(f"\n📊 Found {total_pdfs} PDF files to process")
    print("=" * 80)

    processed = 0
    failed = 0
    skipped = 0
    start_time = time.time()

    for i, pdf_file in enumerate(all_files, 1):
        pdf_path = os.path.join(INVOICES_DIR, pdf_file)

        print(f"\n📄 [{i}/{total_pdfs}] Processing: {pdf_file}")
        print(f"⏱️  Elapsed: {int(time.time() - start_time)}s | Remaining: ~{int((total_pdfs - i) * 10)}s")

        try:
            # Extract invoice data
            invoice_data = extract_invoice_data_from_pdf(pdf_path)

            if invoice_data:
                # Save to database
                success = save_invoice_to_db(invoice_data)

                if success:
                    processed += 1
                    # Move to processed folder
                    dest_path = os.path.join(PROCESSED_DIR, pdf_file)
                    shutil.move(pdf_path, dest_path)
                    print(f"📦 Moved to: {PROCESSED_DIR}/{pdf_file}")
                else:
                    skipped += 1
            else:
                failed += 1
                print(f"❌ Failed to extract data")

            # Sleep between requests (10 seconds to be safe)
            if i < total_pdfs:
                print(f"⏳ Waiting 10 seconds before next PDF...")
                time.sleep(10)

        except Exception as e:
            failed += 1
            print(f"❌ Error: {e}")
            continue

    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("🎉 PROCESSING COMPLETE!")
    print("=" * 80)
    print(f"📊 Total PDFs: {total_pdfs}")
    print(f"✅ Successfully Processed: {processed}")
    print(f"⏭️  Skipped (Duplicates): {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(processed/total_pdfs)*100:.1f}%")
    print(f"⏱️  Total Time: {int(elapsed/60)}m {int(elapsed%60)}s")
    print(f"🗄️  Database: supplierOrders.db")
    print(f"📁 Processed Files: {PROCESSED_DIR}")
    print("=" * 80)
    print(f"⏰ Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

if __name__ == "__main__":
    process_all_pdfs()
