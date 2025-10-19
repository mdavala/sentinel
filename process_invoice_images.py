#!/usr/bin/env python3
"""
Process Invoice Images using Vision OCR from stockSentinel.py
Processes existing invoice images and saves to orders_table in dailydelights.db
"""

import os
import sys
import time
import base64
import json
import requests
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError

# Load environment variables
load_dotenv(override=True)

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# Vision model to use
VISION_MODEL = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"

# =============================================================================
# PYDANTIC MODELS (from stockSentinel.py)
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
    carton_or_loose: Optional[str] = Field(
        None, description='"carton" or "loose" (how the item is sold)'
    )
    items_per_carton: Optional[int] = Field(
        None, description="If sold by carton, number of loose items per carton"
    )
    unit_price_item: Optional[float] = Field(
        None, description="Price per individual item/piece (NOT per carton)"
    )
    amount_per_item: Optional[float] = Field(
        None, description="Total amount for this line item BEFORE GST (quantity × unit_price_item)"
    )
    gst_amount: Optional[float] = Field(
        None, description="GST amount for this line item (9% of amount_per_item)"
    )
    total_amount_per_item: Optional[float] = Field(
        None, description="Final total for this line item WITH GST (amount_per_item + gst_amount)"
    )
    barcode: Optional[str] = Field(None, description="Product barcode or SKU if available")

    # Payment-related fields
    payment_status: str = Field(
        default="pending",
        description="Payment status: 'paid' if invoice shows payment is completed, 'pending' if payment is due or not mentioned"
    )

    # Auto-calculations
    @field_validator("gst_amount")
    def calc_gst(cls, v, values):
        if v is None and values.data.get("amount_per_item"):
            return round(values.data["amount_per_item"] * 0.09, 2)
        return v

    @field_validator("total_amount_per_item")
    def calc_total(cls, v, values):
        if v is None and values.data.get("amount_per_item"):
            gst = values.data.get("gst_amount", 0) or round(values.data["amount_per_item"] * 0.09, 2)
            return values.data["amount_per_item"] + gst
        return v

class InvoiceResponse(BaseModel):
    items: List[InvoiceItem]
    total_invoice_amount: Optional[float] = Field(
        None,
        description="TOTAL AMOUNT for the entire invoice (sum of all items with GST) - Look for 'TOTAL AMOUNT:' or 'GRAND TOTAL:' at the bottom of the invoice"
    )

# =============================================================================
# SQLALCHEMY DATABASE SETUP
# =============================================================================

Base = declarative_base()

class OrdersTable(Base):
    """Orders table for June invoice data"""
    __tablename__ = "orders_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String, nullable=False)
    supplier_name = Column(String, nullable=False)
    item_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)

    invoice_date = Column(String, nullable=True)
    carton_or_loose = Column(String, nullable=True)
    items_per_carton = Column(Integer, nullable=True)
    unit_price_item = Column(Float, nullable=True)
    amount_per_item = Column(Float, nullable=True)
    gst_amount = Column(Float, nullable=True)
    total_amount_per_item = Column(Float, nullable=True)
    barcode = Column(String, nullable=True)
    payment_status = Column(String, default="pending")

    # Processing metadata
    image_filename = Column(String, nullable=True)
    processed_at = Column(DateTime, default=datetime.now)
    total_invoice_amount = Column(Float, nullable=True)  # Total for entire invoice

# Create database connection
DB_PATH = os.path.join(os.path.dirname(__file__), "dailydelights.db")
engine = create_engine(f"sqlite:///{DB_PATH}")
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

# =============================================================================
# VISION OCR FUNCTIONS (from stockSentinel.py)
# =============================================================================

def encode_image(image_path: str) -> str:
    """Convert image file to base64 string"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def is_remote_file(file_path: str) -> bool:
    """Check if file path is a URL"""
    return file_path.startswith("http://") or file_path.startswith("https://")

def ocr(file_path: str, model: str, api_key: str = TOGETHER_API_KEY):
    """
    Run OCR using Together AI Vision model and return JSON output.
    """
    if not api_key:
        raise ValueError("⚠ TOGETHER_API_KEY not set in environment")

    vision_llm = model

    # System prompt (from stockSentinel.py)
    system_prompt = """
    You are an intelligent invoice parsing agent for Daily Delights inventory management.

    Analyze the invoice image and extract the following information:

    CRITICAL INSTRUCTIONS:
        1. Extract EVERY piece of information you can see in the invoice
        2. Look at EVERY part of the invoice - header, body, footer, stamps, watermarks, delivery notes
        3. If a field is not clearly visible, set it to null - DO NOT guess or assume
        4. Pay special attention to dates, amounts, and payment status indicators

    REQUIRED FIELDS (for each line item):
    - Invoice_number: Invoice number or bill number or receipt number mentioned in the image.
    Sometimes invoice number can be Sales Order No. Check if there is any unique number that can identify this invoice.
    - supplier_name: Name of the supplier/vendor
    - item_name: Product/item name
    - quantity: Number of items ordered

    OPTIONAL FIELDS (for each line item):
    - invoice_date: Invoice date in YYYY-MM-DD format (extract from invoice header/top section)
    - carton_or_loose: "carton" or "loose" (how item is sold)
    - items_per_carton: If sold by carton, how many loose items per carton
    - unit_price_item: Price per INDIVIDUAL ITEM/PIECE (NOT per carton, NOT total)
    - amount_per_item: Total amount for THIS LINE ITEM BEFORE GST (quantity × unit_price_item)
    - gst_amount: GST amount for THIS LINE ITEM (9% of amount_per_item)
    - total_amount_per_item: Final total for THIS LINE ITEM WITH GST (amount_per_item + gst_amount)
    - barcode: Product barcode/SKU if visible
    - payment_status: Set to "paid" only if you see the handwritten "paid" on invoice (OR) Default to "pending" if payment status is unclear or handwritten as "pending" or "payment pending"

    INVOICE-LEVEL FIELD (separate from line items):
    - total_invoice_amount: The TOTAL AMOUNT for the ENTIRE INVOICE (look for "TOTAL AMOUNT:", "GRAND TOTAL:", or "TOTAL:" at the bottom of the invoice - this is the sum of ALL line items with GST included)

    CRITICAL: DO NOT confuse "total_amount_per_item" (per line) with "total_invoice_amount" (entire invoice)!
    - "total_amount_per_item" = amount for ONE line item
    - "total_invoice_amount" = sum of ALL line items (usually at bottom of invoice)

    PAYMENT STATUS EXTRACTION RULES:
    - STRICT RULE: Set to "paid" only if you see the handwritten word "paid" on invoice
    - Default to "pending" if payment status is unclear or not mentioned or handwritten as "pending" or "payment pending"

    IMPORTANT RULES:
    1. If information is not clearly visible, set to null
    2. For invoice_date, look for date in the invoice header/top section, convert to YYYY-MM-DD format
    3. For calculations, use the exact values from the image
    4. For unit_price_item, extract the price per INDIVIDUAL item/piece (NOT per carton)
    5. Return clean, structured JSON only

    STRICT RULE: Return each item with all fields in JSON Format. Use null for missing/unclear values.
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

def save_json_to_db(json_string: str, session, image_filename: str) -> int:
    """
    Convert JSON string to Python object and save each item to orders_table

    Args:
        json_string: JSON string containing items data
        session: SQLAlchemy session object
        image_filename: Name of the processed image file

    Returns:
        Number of items saved
    """
    try:
        # Clean the JSON string if it has markdown formatting
        cleaned_json = json_string.strip()
        if cleaned_json.startswith('```json'):
            cleaned_json = cleaned_json.replace('```json', '').replace('```', '').strip()
        elif cleaned_json.startswith('```'):
            cleaned_json = cleaned_json.replace('```', '').strip()

        # Parse JSON
        data = json.loads(cleaned_json)

        if "items" not in data or not data["items"]:
            print(f"  ⚠️  No items found in JSON response")
            return 0

        items_saved = 0

        # Get invoice-level total amount (if present)
        total_invoice_amount = data.get("total_invoice_amount")

        # Process each item
        for item_data in data["items"]:
            # Create OrdersTable entry
            order = OrdersTable(
                invoice_number=item_data.get("invoice_number", "UNKNOWN"),
                supplier_name=item_data.get("supplier_name", "UNKNOWN"),
                item_name=item_data.get("item_name", "UNKNOWN"),
                quantity=item_data.get("quantity", 0),
                invoice_date=item_data.get("invoice_date"),
                carton_or_loose=item_data.get("carton_or_loose"),
                items_per_carton=item_data.get("items_per_carton"),
                unit_price_item=item_data.get("unit_price_item"),
                amount_per_item=item_data.get("amount_per_item"),
                gst_amount=item_data.get("gst_amount"),
                total_amount_per_item=item_data.get("total_amount_per_item"),
                barcode=item_data.get("barcode"),
                payment_status=item_data.get("payment_status", "pending"),
                image_filename=image_filename,
                total_invoice_amount=total_invoice_amount  # Store invoice total for all line items
            )

            session.add(order)
            items_saved += 1

        session.commit()

        # Print summary
        if total_invoice_amount:
            print(f"  ℹ️  Invoice Total: ${total_invoice_amount:.2f}")

        return items_saved

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parsing error: {e}")
        print(f"  Raw JSON: {json_string[:200]}...")
        return 0
    except Exception as e:
        print(f"  ❌ Error saving to database: {e}")
        session.rollback()
        return 0

# =============================================================================
# IMAGE PROCESSING FUNCTIONS
# =============================================================================

def process_single_image(image_path: str, session) -> bool:
    """
    Process a single invoice image using Vision OCR

    Args:
        image_path: Full path to the image file
        session: SQLAlchemy session

    Returns:
        True if successful, False otherwise
    """
    image_filename = os.path.basename(image_path)

    try:
        print(f"  🔍 Running Vision OCR...")

        # Run OCR
        json_output = ocr(image_path, VISION_MODEL)

        # Save to database
        items_saved = save_json_to_db(json_output, session, image_filename)

        if items_saved > 0:
            print(f"  ✅ Saved {items_saved} items to orders_table")
            return True
        else:
            print(f"  ⚠️  No items saved")
            return False

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return False

def process_all_images(images_dir: str, delay_seconds: float = 2.0):
    """
    Process all invoice images in the specified directory

    Args:
        images_dir: Directory containing invoice images
        delay_seconds: Delay between API calls to avoid rate limiting
    """
    # Get all image files
    image_files = [
        f for f in os.listdir(images_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]

    if not image_files:
        print(f"❌ No images found in {images_dir}")
        return

    print(f"\n{'='*80}")
    print(f"🚀 INVOICE IMAGE PROCESSOR - Vision OCR Edition")
    print(f"{'='*80}")
    print(f"📁 Images directory: {images_dir}")
    print(f"📊 Total images: {len(image_files)}")
    print(f"🤖 Model: {VISION_MODEL}")
    print(f"⏱️  Delay between calls: {delay_seconds}s")
    print(f"📊 Estimated time: {len(image_files)} × 30-60s = {(len(image_files) * 45)/60:.0f} minutes")
    print(f"{'='*80}\n")

    # Create database session
    session = Session()

    processed_count = 0
    failed_count = 0
    skipped_count = 0
    total_items = 0

    start_time = time.time()

    for i, image_file in enumerate(sorted(image_files), 1):
        image_path = os.path.join(images_dir, image_file)

        print(f"[{i}/{len(image_files)}] 📄 {image_file}")

        # Check if already processed
        existing = session.query(OrdersTable).filter_by(image_filename=image_file).first()
        if existing:
            print(f"  ⏭️  Already processed (skipping)")
            skipped_count += 1
            print(f"{'-'*80}")
            continue

        # Process image
        success = process_single_image(image_path, session)

        if success:
            processed_count += 1
            # Count items for this invoice
            items_count = session.query(OrdersTable).filter_by(image_filename=image_file).count()
            total_items += items_count
        else:
            failed_count += 1

        print(f"{'-'*80}")

        # Rate limiting delay (except for last image)
        if i < len(image_files):
            print(f"⏳ Waiting {delay_seconds}s before next request...\n")
            time.sleep(delay_seconds)

    session.close()

    # Summary
    elapsed_time = time.time() - start_time

    print(f"\n{'='*80}")
    print(f"🎯 PROCESSING COMPLETE")
    print(f"{'='*80}")
    print(f"📊 Total images: {len(image_files)}")
    print(f"✅ Successfully processed: {processed_count}")
    print(f"⏭️  Skipped (already processed): {skipped_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📦 Total items extracted: {total_items}")
    print(f"⏱️  Total time: {elapsed_time/60:.1f} minutes")
    print(f"⚡ Average time per image: {elapsed_time/len(image_files):.1f}s")
    print(f"{'='*80}")

    # Show sample data
    show_sample_data()

def show_sample_data(limit=10):
    """Display sample data from orders_table"""
    session = Session()

    try:
        # Get total count
        total_count = session.query(OrdersTable).count()

        if total_count == 0:
            print("\n📋 No data in orders_table yet")
            session.close()
            return

        print(f"\n📋 Sample data from orders_table (showing {min(limit, total_count)} of {total_count} items):")
        print(f"{'-'*80}")

        # Get latest items
        orders = session.query(OrdersTable).order_by(OrdersTable.processed_at.desc()).limit(limit).all()

        for order in orders:
            print(f"Invoice: {order.invoice_number} | Supplier: {order.supplier_name[:30]}")
            print(f"  Item: {order.item_name[:50]} | Qty: {order.quantity}")
            print(f"  Date: {order.invoice_date} | Amount: ${order.total_amount_per_item or 0:.2f}")
            print(f"  Status: {order.payment_status} | Image: {order.image_filename}")
            print(f"{'-'*40}")

        # Count by supplier
        print(f"\n📊 Orders by supplier:")
        print(f"{'-'*80}")

        from sqlalchemy import func
        supplier_stats = session.query(
            OrdersTable.supplier_name,
            func.count(OrdersTable.id).label('count'),
            func.sum(OrdersTable.total_amount_per_item).label('total')
        ).group_by(OrdersTable.supplier_name).order_by(func.count(OrdersTable.id).desc()).all()

        for supplier, count, total in supplier_stats:
            total_val = total if total else 0
            print(f"{supplier[:40]}: {count} items, ${total_val:.2f} total")

        print(f"{'-'*80}")

    except Exception as e:
        print(f"❌ Error showing sample data: {e}")
    finally:
        session.close()

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main function"""
    # Paths
    images_dir = os.path.join(os.path.dirname(__file__), "Invoices", "June_invoices_images")

    # Verify paths
    if not os.path.exists(images_dir):
        print(f"❌ Error: Images directory not found: {images_dir}")
        sys.exit(1)

    if not TOGETHER_API_KEY:
        print(f"❌ Error: TOGETHER_API_KEY not set in environment")
        sys.exit(1)

    # Process all images
    process_all_images(images_dir, delay_seconds=2.0)

    print(f"\n✅ Processing complete! Check dailydelights.db -> orders_table")

if __name__ == "__main__":
    main()
