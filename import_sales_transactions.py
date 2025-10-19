#!/usr/bin/env python3
"""
Import sales transactions from master_transaction_details.xlsx to dailydelights.db
Creates sales_transactions table and imports all 50,000+ records
"""

import pandas as pd
import sqlite3
from datetime import datetime
import os

def import_sales_transactions():
    """Import sales transactions from Excel to SQLite"""

    print("\n" + "="*80)
    print("🚀 SALES TRANSACTIONS IMPORT")
    print("="*80)

    # Paths
    excel_path = os.path.join(os.path.dirname(__file__), 'dd_transactionDetails', 'master_transaction_details.xlsx')
    db_path = os.path.join(os.path.dirname(__file__), 'dailydelights.db')

    # Verify Excel file exists
    if not os.path.exists(excel_path):
        print(f"❌ Error: Excel file not found at {excel_path}")
        return False

    print(f"📁 Excel file: {excel_path}")
    print(f"📁 Database: {db_path}")
    print("="*80)

    # Read Excel file
    print("\n📖 Reading Excel file...")
    try:
        df = pd.read_excel(excel_path)
        print(f"✅ Loaded {len(df)} rows from Excel")
        print(f"📊 Columns: {len(df.columns)}")
    except Exception as e:
        print(f"❌ Error reading Excel file: {e}")
        return False

    # Connect to database
    print("\n🔗 Connecting to database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing sales_transactions table if it exists
    print("🗑️  Dropping existing sales_transactions table (if exists)...")
    cursor.execute("DROP TABLE IF EXISTS sales_transactions")

    # Create sales_transactions table
    print("📋 Creating sales_transactions table...")
    cursor.execute("""
        CREATE TABLE sales_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATETIME NOT NULL,
            receipt_no TEXT,
            order_number REAL,
            invoice_no REAL,
            transaction_total_amount REAL,
            transaction_level_percentage_discount REAL,
            transaction_level_dollar_discount REAL,
            transaction_payment_method TEXT,
            payment_note TEXT,
            transaction_note TEXT,
            staff_name TEXT,
            customer_name TEXT,
            customer_phone_number TEXT,
            voided BOOLEAN,
            void_reason TEXT,
            transaction_item TEXT,
            transaction_item_quantity INTEGER,
            transaction_item_notes TEXT,
            transaction_item_discount REAL,
            amount_before_subsidy REAL,
            total_subsidy REAL,
            transaction_item_final_amount REAL,
            store_name TEXT,
            sku_number REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("✅ Table created successfully")

    # Prepare data for import
    print("\n🔄 Preparing data for import...")

    # Rename columns to match SQL table (replace spaces with underscores, lowercase)
    # Create clean column names mapping
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
        'Transaction Item Final Amount ($)': 'transaction_item_final_amount',
        'Store Name': 'store_name',
        'SKU Number': 'sku_number'
    }

    df = df.rename(columns=column_mapping)

    # Handle NaN values
    df = df.where(pd.notnull(df), None)

    # Convert date column to string format
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d %H:%M:%S')

    print(f"✅ Data prepared: {len(df)} rows ready for import")

    # Import data in batches
    print("\n💾 Importing data to database...")
    batch_size = 1000
    total_imported = 0

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]

        # Insert batch
        batch.to_sql('sales_transactions', conn, if_exists='append', index=False,
                     method='multi', chunksize=batch_size)

        total_imported += len(batch)
        progress = (total_imported / len(df)) * 100
        print(f"  ⏳ Progress: {total_imported}/{len(df)} rows ({progress:.1f}%)")

    conn.commit()

    # Verify import
    print("\n✅ Import complete! Verifying...")
    cursor.execute("SELECT COUNT(*) FROM sales_transactions")
    count = cursor.fetchone()[0]
    print(f"📊 Total records in sales_transactions: {count}")

    # Show sample data
    print("\n📋 Sample records (first 5):")
    print("-"*80)
    cursor.execute("""
        SELECT date, receipt_no, transaction_item, transaction_item_quantity,
               transaction_item_final_amount, staff_name, voided
        FROM sales_transactions
        LIMIT 5
    """)

    for row in cursor.fetchall():
        date, receipt, item, qty, amount, staff, voided = row
        voided_str = "VOIDED" if voided else "ACTIVE"
        print(f"{date} | {receipt} | {item[:30]:30s} | Qty: {qty} | ${amount:.2f} | {staff} | {voided_str}")

    print("-"*80)

    # Statistics
    print("\n📊 Statistics:")
    print("-"*80)

    # Count by voided status
    cursor.execute("""
        SELECT voided, COUNT(*) as count, SUM(transaction_item_final_amount) as total_amount
        FROM sales_transactions
        GROUP BY voided
    """)
    for voided, count, total in cursor.fetchall():
        status = "Voided" if voided else "Active"
        total_val = total if total else 0
        print(f"{status}: {count} transactions, ${total_val:,.2f} total")

    # Count by payment method
    print("\n💳 By Payment Method:")
    cursor.execute("""
        SELECT transaction_payment_method, COUNT(*) as count, SUM(transaction_item_final_amount) as total
        FROM sales_transactions
        WHERE voided = 0
        GROUP BY transaction_payment_method
        ORDER BY count DESC
        LIMIT 10
    """)
    for method, count, total in cursor.fetchall():
        method_name = method if method else "Unknown"
        total_val = total if total else 0
        print(f"  {method_name}: {count} transactions, ${total_val:,.2f}")

    # Top selling items
    print("\n🔥 Top 10 Selling Items (by quantity):")
    cursor.execute("""
        SELECT transaction_item, SUM(transaction_item_quantity) as total_qty,
               COUNT(*) as transaction_count, SUM(transaction_item_final_amount) as total_amount
        FROM sales_transactions
        WHERE voided = 0
        GROUP BY transaction_item
        ORDER BY total_qty DESC
        LIMIT 10
    """)
    for item, qty, txn_count, total in cursor.fetchall():
        item_name = item if item else "Unknown"
        total_val = total if total else 0
        print(f"  {item_name[:40]:40s} | Qty: {qty:5d} | Txns: {txn_count:4d} | ${total_val:,.2f}")

    # Date range
    print("\n📅 Date Range:")
    cursor.execute("""
        SELECT MIN(date) as first_date, MAX(date) as last_date
        FROM sales_transactions
    """)
    first_date, last_date = cursor.fetchone()
    print(f"  From: {first_date}")
    print(f"  To: {last_date}")

    print("\n" + "="*80)
    print("✅ IMPORT COMPLETE!")
    print("="*80)

    conn.close()
    return True

if __name__ == "__main__":
    success = import_sales_transactions()

    if success:
        print("\n🎉 Sales transactions successfully imported to dailydelights.db!")
        print("📊 Table: sales_transactions")
    else:
        print("\n❌ Import failed. Please check the errors above.")
