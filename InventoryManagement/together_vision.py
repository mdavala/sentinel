import os
import json
import base64
import requests
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
load_dotenv(override=True)

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, Table, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

class InvoiceItem(BaseModel):
    # Required fields
    invoice_number: str = Field(..., description="Invoice number / bill number / receipt number")
    supplier_name: str = Field(..., description="Name of the supplier or vendor")
    item_name: str = Field(..., description="Product or item name")
    quantity: int = Field(..., description="Number of items ordered")

    # Optional fields
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

# -----------------
# 2. SQLAlchemy setup
# -----------------
Base = declarative_base()

class InventoryTable(Base):
    __tablename__ = "inventory_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String)
    supplier_name = Column(String)
    item_name = Column(String)
    quantity = Column(Integer)

    unit_price = Column(Float, nullable=True)
    carton_or_loose = Column(String, nullable=True)
    items_per_carton = Column(Integer, nullable=True)
    unit_price_item = Column(Float, nullable=True)
    amount_per_item = Column(Float, nullable=True)
    gst_amount = Column(Float, nullable=True)
    total_amount_per_item = Column(Float, nullable=True)
    barcode = Column(String, nullable=True)

# Create DB connection
engine = create_engine("sqlite:///dailydelights.db")
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()


def fetch_gdrive_image(file_id):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url, verify=False)
    return Image.open(BytesIO(response.content))

def encode_image(image_path: str) -> str:
    """Convert image file to base64 string"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def is_remote_file(file_path: str) -> bool:
    """Check if file path is a URL"""
    return file_path.startswith("http://") or file_path.startswith("https://")

def ocr(file_path: str, model: str = "Llama-3.2-90B-Vision", api_key: str = TOGETHER_API_KEY):
    """
    Run OCR using Together AI Vision model and return Markdown output.
    """
    if not api_key:
        raise ValueError("❌ TOGETHER_API_KEY not set in environment")

    # Choose correct Together Vision model
    vision_llm = (
        "meta-llama/Llama-Vision-Free"
        if model == "free"
        else f"meta-llama/{model}"
    )

    # System prompt (OCR → Markdown conversion)
    system_prompt = """
        You are an intelligent invoice parsing agent for Daily Delights inventory management.
        
        Analyze the invoice image and extract the following information:
        
        REQUIRED FIELDS:
        - Invoice_number: Invoice number or bill number or receipt number mentioned in the image
        - supplier_name: Name of the supplier/vendor
        - item_name: Product/item name  
        - quantity: Number of items ordered
        
        OPTIONAL FIELDS:
        - unit_price: Price per unit
        - carton_or_loose: "carton" or "loose" (how item is sold)
        - items_per_carton: If sold by carton, how many loose items per carton
        - unit_price_item: Calculate price per loose item (unit_price ÷ items_per_carton)
        - amount_per_item: Total amount (quantity × unit_price)
        - gst_amount: GST amount (9% of amount_per_item)
        - total_amount_per_item: amount_per_item + gst_amount
        - barcode: Product barcode/SKU if visible
        
        IMPORTANT RULES:
        1. If information is not clearly visible, set to null
        2. For calculations, use the exact values from the image
        3. If carton_or_loose is "carton" and items_per_carton is provided, calculate unit_price_item
        4. Return clean, structured JSON only
        
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
        raise Exception(f"❌ API Error: {response.status_code}, {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]
def save_json_to_db(json_string, session):
    """
    Convert JSON string to Python object and save each item to SQL database
    
    Args:
        json_string (str): JSON string containing items data
        session: SQLAlchemy session object
    
    Returns:
        int: Number of items successfully saved
    """
    try:
        # Parse JSON string to Python dictionary
        data = json.loads(json_string)
        
        # Extract items from the parsed data
        items = data.get('items', [])
        
        saved_count = 0
        
        # Process each item
        for item_data in items:
            # Create new inventory record
            inventory_item = InventoryTable(
                invoice_number=item_data.get('invoice_number'),
                supplier_name=item_data.get('supplier_name'),
                item_name=item_data.get('item_name'),
                quantity=item_data.get('quantity'),
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
            session.add(inventory_item)
            saved_count += 1
        
        # Commit all changes
        session.commit()
        print(f"Successfully saved {saved_count} items to database")
        return saved_count
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        session.rollback()
        return 0
    except Exception as e:
        print(f"Error saving to database: {e}")
        session.rollback()
        return 0

# Example usage:
if __name__ == "__main__":
    parsed_raw = ocr("invoices/test.jpeg", model="Llama-4-Maverick-17B-128E-Instruct-FP8")
    print(parsed_raw)
    saved_count = save_json_to_db(parsed_raw, session)

    print(f"✅ All items {saved_count} saved to dailydelights.db in inventory_table")
