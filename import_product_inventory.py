#!/usr/bin/env python3
"""
Import product inventory from Product_inventory_dd.csv to dailydelights.db
Creates product_inventory table and imports all product records
"""

import pandas as pd
import sqlite3
import os
import re

def clean_price_string(price_str):
    """Convert price string like '$ 13.45' to float"""
    if pd.isna(price_str) or price_str is None:
        return None
    try:
        # Remove $ and spaces, convert to float
        cleaned = str(price_str).replace('$', '').strip()
        return float(cleaned) if cleaned else None
    except:
        return None

def import_product_inventory():
    """Import product inventory from CSV to SQLite"""

    print("\n" + "="*80)
    print("🚀 PRODUCT INVENTORY IMPORT")
    print("="*80)

    # Paths
    csv_path = os.path.join(os.path.dirname(__file__), 'product_inventory', 'Product_inventory_dd.csv')
    db_path = os.path.join(os.path.dirname(__file__), 'dailydelights.db')

    # Verify CSV file exists
    if not os.path.exists(csv_path):
        print(f"❌ Error: CSV file not found at {csv_path}")
        return False

    print(f"📁 CSV file: {csv_path}")
    print(f"📁 Database: {db_path}")
    print("="*80)

    # Read CSV file
    print("\n📖 Reading CSV file...")
    try:
        df = pd.read_csv(csv_path)
        print(f"✅ Loaded {len(df)} rows from CSV")
        print(f"📊 Columns: {len(df.columns)}")
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return False

    # Connect to database
    print("\n🔗 Connecting to database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing product_inventory table if it exists
    print("🗑️  Dropping existing product_inventory table (if exists)...")
    cursor.execute("DROP TABLE IF EXISTS product_inventory")

    # Create product_inventory table
    print("📋 Creating product_inventory table...")
    cursor.execute("""
        CREATE TABLE product_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            tab TEXT,
            category TEXT,
            barcode BIGINT,
            sku_number TEXT,
            in_stock REAL,
            low_stock_threshold INTEGER,
            unit_price REAL,
            unit_cost REAL,
            stock_value REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("✅ Table created successfully")

    # Prepare data for import
    print("\n🔄 Preparing data for import...")

    # Clean column names
    df.columns = [col.strip().replace(' ', '_').lower() for col in df.columns]

    # Clean price columns
    print("  💰 Converting price columns...")
    if 'unit_price' in df.columns:
        df['unit_price'] = df['unit_price'].apply(clean_price_string)
    if 'unit_cost' in df.columns:
        df['unit_cost'] = df['unit_cost'].apply(clean_price_string)

    # Handle NaN values
    df = df.where(pd.notnull(df), None)

    # Convert sku_number to string (handle mixed types - numbers and text)
    if 'sku_number' in df.columns:
        def safe_convert_sku(x):
            if pd.isna(x):
                return None
            # If already string, keep as is
            if isinstance(x, str):
                return x
            # If number, convert to string
            try:
                return str(int(x))
            except:
                return str(x)

        df['sku_number'] = df['sku_number'].apply(safe_convert_sku)

    print(f"✅ Data prepared: {len(df)} rows ready for import")

    # Import data
    print("\n💾 Importing data to database...")

    try:
        # Insert data
        df.to_sql('product_inventory', conn, if_exists='append', index=False, method='multi')

        conn.commit()
        print(f"✅ Import complete!")

    except Exception as e:
        print(f"❌ Error during import: {e}")
        conn.rollback()
        return False

    # Verify import
    print("\n✅ Verifying import...")
    cursor.execute("SELECT COUNT(*) FROM product_inventory")
    count = cursor.fetchone()[0]
    print(f"📊 Total records in product_inventory: {count}")

    # Show sample data
    print("\n📋 Sample records (first 10):")
    print("-"*80)
    cursor.execute("""
        SELECT product_name, category, barcode, in_stock, unit_price, stock_value
        FROM product_inventory
        LIMIT 10
    """)

    for row in cursor.fetchall():
        name, cat, barcode, stock, price, value = row
        stock_str = f"{stock:.1f}" if stock is not None else "N/A"
        price_str = f"${price:.2f}" if price is not None else "N/A"
        value_str = f"${value:.2f}" if value is not None else "N/A"
        print(f"{name[:40]:40s} | {cat[:15]:15s} | Stock: {stock_str:6s} | Price: {price_str:8s} | Value: {value_str}")

    print("-"*80)

    # Statistics
    print("\n📊 Statistics:")
    print("-"*80)

    # Count by category
    print("\n📦 By Category:")
    cursor.execute("""
        SELECT category, COUNT(*) as count,
               SUM(CASE WHEN in_stock > 0 THEN 1 ELSE 0 END) as in_stock_count,
               SUM(stock_value) as total_value
        FROM product_inventory
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
        LIMIT 15
    """)
    for cat, count, in_stock_count, total_value in cursor.fetchall():
        cat_name = cat if cat else "Unknown"
        value_str = f"${total_value:,.2f}" if total_value else "$0.00"
        print(f"  {cat_name[:30]:30s}: {count:4d} products | {in_stock_count:3d} in stock | {value_str}")

    # Stock statistics
    print("\n📊 Stock Status:")
    cursor.execute("""
        SELECT
            COUNT(*) as total_products,
            SUM(CASE WHEN in_stock > 0 THEN 1 ELSE 0 END) as products_in_stock,
            SUM(CASE WHEN in_stock = 0 OR in_stock IS NULL THEN 1 ELSE 0 END) as out_of_stock,
            SUM(CASE WHEN in_stock <= low_stock_threshold AND in_stock > 0 THEN 1 ELSE 0 END) as low_stock
        FROM product_inventory
    """)
    total, in_stock, out_stock, low = cursor.fetchone()
    print(f"  Total products: {total}")
    print(f"  In stock: {in_stock} ({(in_stock/total*100):.1f}%)")
    print(f"  Out of stock: {out_stock} ({(out_stock/total*100):.1f}%)")
    print(f"  Low stock: {low} ({(low/total*100):.1f}%)")

    # Total inventory value
    cursor.execute("""
        SELECT SUM(stock_value) as total_value
        FROM product_inventory
        WHERE stock_value IS NOT NULL
    """)
    total_value = cursor.fetchone()[0]
    if total_value:
        print(f"\n💰 Total Inventory Value: ${total_value:,.2f}")

    # Top 10 products by stock value
    print("\n🔥 Top 10 Products by Stock Value:")
    cursor.execute("""
        SELECT product_name, in_stock, unit_price, stock_value
        FROM product_inventory
        WHERE stock_value > 0
        ORDER BY stock_value DESC
        LIMIT 10
    """)
    for name, stock, price, value in cursor.fetchall():
        stock_str = f"{stock:.1f}" if stock else "0"
        price_str = f"${price:.2f}" if price else "$0.00"
        value_str = f"${value:.2f}" if value else "$0.00"
        print(f"  {name[:45]:45s} | Stock: {stock_str:6s} | Price: {price_str:8s} | Value: {value_str}")

    # Products with low stock
    print("\n⚠️  Products with Low Stock (need reorder):")
    cursor.execute("""
        SELECT product_name, in_stock, low_stock_threshold, category
        FROM product_inventory
        WHERE in_stock > 0
        AND in_stock <= low_stock_threshold
        ORDER BY (in_stock - low_stock_threshold)
        LIMIT 10
    """)
    low_stock_products = cursor.fetchall()
    if low_stock_products:
        for name, stock, threshold, cat in low_stock_products:
            stock_str = f"{stock:.1f}" if stock else "0"
            cat_str = cat if cat else "N/A"
            print(f"  {name[:45]:45s} | Current: {stock_str:6s} | Threshold: {threshold:3d} | {cat_str}")
    else:
        print("  ✅ No products currently at low stock levels")

    print("\n" + "="*80)
    print("✅ IMPORT COMPLETE!")
    print("="*80)

    conn.close()
    return True

if __name__ == "__main__":
    success = import_product_inventory()

    if success:
        print("\n🎉 Product inventory successfully imported to dailydelights.db!")
        print("📊 Table: product_inventory")
    else:
        print("\n❌ Import failed. Please check the errors above.")
