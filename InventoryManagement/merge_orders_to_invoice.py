#!/usr/bin/env python3
"""
Merge orders_table entries into invoice_table
Keeps orders_table intact, adds all its data to invoice_table
"""

import sqlite3
import os

def merge_orders_to_invoice():
    """Copy all orders_table data into invoice_table"""

    print("\n" + "="*80)
    print("🔄 MERGE ORDERS_TABLE INTO INVOICE_TABLE")
    print("="*80)

    # Database path
    db_path = os.path.join(os.path.dirname(__file__), 'dailydelights.db')

    print(f"📁 Database: {db_path}")
    print("="*80)

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get counts before merge
    print("\n📊 Current Status:")
    print("-"*80)

    cursor.execute("SELECT COUNT(*) FROM orders_table")
    orders_count = cursor.fetchone()[0]
    print(f"Orders Table: {orders_count} records")

    cursor.execute("SELECT COUNT(*) FROM invoice_table")
    invoice_count_before = cursor.fetchone()[0]
    print(f"Invoice Table (before): {invoice_count_before} records")

    # Check for potential duplicates (same invoice_number, item_name, supplier_name)
    print("\n🔍 Checking for potential duplicates...")
    cursor.execute("""
        SELECT COUNT(*)
        FROM orders_table o
        WHERE EXISTS (
            SELECT 1 FROM invoice_table i
            WHERE i.invoice_number = o.invoice_number
            AND i.item_name = o.item_name
            AND i.supplier_name = o.supplier_name
        )
    """)
    potential_duplicates = cursor.fetchone()[0]

    if potential_duplicates > 0:
        print(f"⚠️  Found {potential_duplicates} potential duplicate records")
        print("   These will be skipped to avoid duplicates")
    else:
        print("✅ No duplicates found - all records will be inserted")

    # Map orders_table columns to invoice_table columns
    # orders_table has: invoice_number, supplier_name, item_name, quantity,
    #                   invoice_date, unit_price, carton_or_loose, items_per_carton,
    #                   unit_price_item, amount_per_item, gst_amount, total_amount_per_item,
    #                   barcode, payment_status, image_filename, processed_at
    #
    # invoice_table has: invoice_number, supplier_name, item_name, quantity, total_amount,
    #                    invoice_date, unit_price, carton_or_loose, items_per_carton,
    #                    unit_price_item, amount_per_item, gst_amount, total_amount_per_item,
    #                    barcode
    #
    # Note: invoice_table has 'total_amount' field but orders_table doesn't
    #       We'll use total_amount_per_item for this field

    print("\n💾 Inserting orders_table data into invoice_table...")
    print("-"*80)

    # Insert query - skip duplicates using WHERE NOT EXISTS
    insert_query = """
        INSERT INTO invoice_table (
            invoice_number, supplier_name, item_name, quantity, total_amount,
            invoice_date, unit_price, carton_or_loose, items_per_carton,
            unit_price_item, amount_per_item, gst_amount, total_amount_per_item, barcode
        )
        SELECT
            o.invoice_number,
            o.supplier_name,
            o.item_name,
            o.quantity,
            o.total_amount_per_item as total_amount,
            o.invoice_date,
            o.unit_price,
            o.carton_or_loose,
            o.items_per_carton,
            o.unit_price_item,
            o.amount_per_item,
            o.gst_amount,
            o.total_amount_per_item,
            o.barcode
        FROM orders_table o
        WHERE NOT EXISTS (
            SELECT 1 FROM invoice_table i
            WHERE i.invoice_number = o.invoice_number
            AND i.item_name = o.item_name
            AND i.supplier_name = o.supplier_name
        )
    """

    try:
        cursor.execute(insert_query)
        inserted_count = cursor.rowcount
        conn.commit()

        print(f"✅ Successfully inserted {inserted_count} new records")

    except Exception as e:
        print(f"❌ Error during merge: {e}")
        conn.rollback()
        return False

    # Get counts after merge
    cursor.execute("SELECT COUNT(*) FROM invoice_table")
    invoice_count_after = cursor.fetchone()[0]

    print("\n📊 Merge Complete:")
    print("-"*80)
    print(f"Orders Table: {orders_count} records (unchanged)")
    print(f"Invoice Table (before): {invoice_count_before} records")
    print(f"Invoice Table (after): {invoice_count_after} records")
    print(f"New records added: {invoice_count_after - invoice_count_before}")
    print(f"Duplicates skipped: {orders_count - (invoice_count_after - invoice_count_before)}")

    # Show sample merged data
    print("\n📋 Sample merged records (latest 10 from orders_table):")
    print("-"*80)
    cursor.execute("""
        SELECT i.invoice_number, i.supplier_name, i.item_name, i.quantity, i.total_amount_per_item
        FROM invoice_table i
        WHERE EXISTS (
            SELECT 1 FROM orders_table o
            WHERE o.invoice_number = i.invoice_number
            AND o.item_name = i.item_name
            AND o.supplier_name = i.supplier_name
        )
        ORDER BY i.id DESC
        LIMIT 10
    """)

    for inv_num, supplier, item, qty, amount in cursor.fetchall():
        supplier_short = supplier[:30] if supplier else "N/A"
        item_short = item[:35] if item else "N/A"
        amount_str = f"${amount:.2f}" if amount else "N/A"
        print(f"{inv_num:20s} | {supplier_short:30s} | {item_short:35s} | Qty: {qty:3d} | {amount_str}")

    # Statistics by supplier
    print("\n📊 Merged Data by Supplier:")
    print("-"*80)
    cursor.execute("""
        SELECT i.supplier_name, COUNT(*) as count, SUM(i.total_amount_per_item) as total
        FROM invoice_table i
        WHERE EXISTS (
            SELECT 1 FROM orders_table o
            WHERE o.invoice_number = i.invoice_number
            AND o.item_name = i.item_name
            AND o.supplier_name = i.supplier_name
        )
        GROUP BY i.supplier_name
        ORDER BY count DESC
        LIMIT 10
    """)

    for supplier, count, total in cursor.fetchall():
        supplier_name = supplier[:40] if supplier else "Unknown"
        total_str = f"${total:,.2f}" if total else "$0.00"
        print(f"  {supplier_name:40s}: {count:3d} items, {total_str}")

    print("\n" + "="*80)
    print("✅ MERGE COMPLETE!")
    print("="*80)
    print("\n📝 Summary:")
    print(f"  • orders_table: {orders_count} records (kept intact)")
    print(f"  • invoice_table: {invoice_count_after} records (was {invoice_count_before})")
    print(f"  • New additions: {invoice_count_after - invoice_count_before} records")
    print("="*80)

    conn.close()
    return True

if __name__ == "__main__":
    success = merge_orders_to_invoice()

    if success:
        print("\n🎉 Orders successfully merged into invoice_table!")
        print("📊 Both tables are intact and invoice_table now includes all orders_table data")
    else:
        print("\n❌ Merge failed. Please check the errors above.")
