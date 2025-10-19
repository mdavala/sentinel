#!/usr/bin/env python3
"""
Import supplier orders frequency from supplier_orders_zf.csv to dailydelights.db
Creates supplier_orders_frequency_table and imports all payment records
"""

import pandas as pd
import sqlite3
import os
from datetime import datetime

def import_supplier_orders_frequency():
    """Import supplier orders frequency from CSV to SQLite"""

    print("\n" + "="*80)
    print("🚀 SUPPLIER ORDERS FREQUENCY IMPORT")
    print("="*80)

    # Paths
    csv_path = os.path.join(os.path.dirname(__file__), 'zohoForms', 'supplier_orders_zf.csv')
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

    # Drop existing supplier_orders_frequency_table if it exists
    print("🗑️  Dropping existing supplier_orders_frequency_table (if exists)...")
    cursor.execute("DROP TABLE IF EXISTS supplier_orders_frequency_table")

    # Create supplier_orders_frequency_table
    print("📋 Creating supplier_orders_frequency_table...")
    cursor.execute("""
        CREATE TABLE supplier_orders_frequency_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            supplier_name TEXT NOT NULL,
            amount REAL NOT NULL,
            mode_of_payment TEXT,
            added_time DATETIME,
            referrer_name TEXT,
            task_owner TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("✅ Table created successfully")

    # Prepare data for import
    print("\n🔄 Preparing data for import...")

    # Rename columns to match SQL table
    column_mapping = {
        'Date': 'date',
        'Suppliers': 'supplier_name',
        'Currency (SGD)': 'amount',
        'Mode of payment': 'mode_of_payment',
        'Added Time': 'added_time',
        'Referrer Name': 'referrer_name',
        'Task Owner': 'task_owner'
    }

    df = df.rename(columns=column_mapping)

    # Convert date column to proper format (DD-MMM-YYYY or DD-MMM-YY to YYYY-MM-DD)
    def parse_date(date_str):
        if pd.isna(date_str):
            return None
        try:
            # First try format like "13-Sep-2025" (4-digit year)
            dt = pd.to_datetime(date_str, format='%d-%b-%Y')
            return dt.strftime('%Y-%m-%d')
        except:
            try:
                # Try format like "13-Sep-25" (2-digit year)
                dt = pd.to_datetime(date_str, format='%d-%b-%y')
                return dt.strftime('%Y-%m-%d')
            except:
                return None

    df['date'] = df['date'].apply(parse_date)

    # Convert added_time to proper datetime format
    def parse_datetime(dt_str):
        if pd.isna(dt_str):
            return None
        try:
            # First try format like "13-Sep-2025 18:18:38" (4-digit year)
            dt = pd.to_datetime(dt_str, format='%d-%b-%Y %H:%M:%S')
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            try:
                # Try format like "13-Sep-25 18:18:38" (2-digit year)
                dt = pd.to_datetime(dt_str, format='%d-%b-%y %H:%M:%S')
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                return None

    df['added_time'] = df['added_time'].apply(parse_datetime)

    # Handle NaN values
    df = df.where(pd.notnull(df), None)

    # Select only the columns we need
    df = df[['date', 'supplier_name', 'amount', 'mode_of_payment', 'added_time', 'referrer_name', 'task_owner']]

    print(f"✅ Data prepared: {len(df)} rows ready for import")

    # Import data
    print("\n💾 Importing data to database...")

    try:
        # Insert data
        df.to_sql('supplier_orders_frequency_table', conn, if_exists='append', index=False, method='multi')

        conn.commit()
        print(f"✅ Import complete!")

    except Exception as e:
        print(f"❌ Error during import: {e}")
        conn.rollback()
        return False

    # Verify import
    print("\n✅ Verifying import...")
    cursor.execute("SELECT COUNT(*) FROM supplier_orders_frequency_table")
    count = cursor.fetchone()[0]
    print(f"📊 Total records in supplier_orders_frequency_table: {count}")

    # Show sample data
    print("\n📋 Sample records (first 10):")
    print("-"*80)
    cursor.execute("""
        SELECT date, supplier_name, amount, mode_of_payment
        FROM supplier_orders_frequency_table
        LIMIT 10
    """)

    for date, supplier, amount, payment_mode in cursor.fetchall():
        payment_str = payment_mode if payment_mode else "N/A"
        print(f"{date} | {supplier:30s} | ${amount:7.2f} | {payment_str}")

    print("-"*80)

    # Statistics
    print("\n📊 Statistics:")
    print("-"*80)

    # Total amount
    cursor.execute("SELECT SUM(amount) FROM supplier_orders_frequency_table")
    total_amount = cursor.fetchone()[0]
    print(f"💰 Total payments: ${total_amount:,.2f}")

    # Count by supplier
    print("\n🏢 By Supplier:")
    cursor.execute("""
        SELECT supplier_name, COUNT(*) as count, SUM(amount) as total
        FROM supplier_orders_frequency_table
        GROUP BY supplier_name
        ORDER BY count DESC
        LIMIT 15
    """)
    for supplier, count, total in cursor.fetchall():
        supplier_name = supplier if supplier else "Unknown"
        total_str = f"${total:,.2f}" if total else "$0.00"
        print(f"  {supplier_name:35s}: {count:3d} payments, {total_str}")

    # Count by payment method
    print("\n💳 By Payment Method:")
    cursor.execute("""
        SELECT mode_of_payment, COUNT(*) as count, SUM(amount) as total
        FROM supplier_orders_frequency_table
        GROUP BY mode_of_payment
        ORDER BY count DESC
    """)
    for method, count, total in cursor.fetchall():
        method_name = method if method else "Unknown"
        total_str = f"${total:,.2f}" if total else "$0.00"
        print(f"  {method_name:30s}: {count:3d} payments, {total_str}")

    # Date range
    print("\n📅 Date Range:")
    cursor.execute("""
        SELECT MIN(date) as first_date, MAX(date) as last_date
        FROM supplier_orders_frequency_table
    """)
    first_date, last_date = cursor.fetchone()
    print(f"  From: {first_date}")
    print(f"  To: {last_date}")

    # Monthly breakdown
    print("\n📈 Monthly Breakdown:")
    cursor.execute("""
        SELECT strftime('%Y-%m', date) as month, COUNT(*) as count, SUM(amount) as total
        FROM supplier_orders_frequency_table
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """)
    for month, count, total in cursor.fetchall():
        month_name = month if month else "Unknown"
        total_str = f"${total:,.2f}" if total else "$0.00"
        print(f"  {month_name}: {count:3d} payments, {total_str}")

    print("\n" + "="*80)
    print("✅ IMPORT COMPLETE!")
    print("="*80)

    conn.close()
    return True

if __name__ == "__main__":
    success = import_supplier_orders_frequency()

    if success:
        print("\n🎉 Supplier orders frequency successfully imported to dailydelights.db!")
        print("📊 Table: supplier_orders_frequency_table")
    else:
        print("\n❌ Import failed. Please check the errors above.")
