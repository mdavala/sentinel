#!/usr/bin/env python3
"""
Inventory Update Script for Daily Delights
Fetches data from invoice_table and updates inventory_table with calculated item amounts
"""

import sqlite3
import os
from datetime import datetime, timedelta

class InventoryUpdater:
    def __init__(self, db_path="dailydelights.db"):
        """
        Initialize InventoryUpdater with database path

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.ensure_inventory_table()

    def ensure_inventory_table(self):
        """Create inventory_table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL UNIQUE,
                category TEXT,
                total_quantity INTEGER DEFAULT 0,
                unit_price REAL DEFAULT 0.0,
                calculated_price REAL DEFAULT 0.0,
                barcode TEXT,
                last_updated DATE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        print("✅ Inventory table created/verified successfully")

    def calculate_inventory_from_invoices(self):
        """
        Calculate inventory data from invoice_table
        Formula: calculated_price = (amount_per_item / quantity) * 1.09
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Query to aggregate invoice data by item
            query = """
            SELECT
                item_name,
                'General' as category,
                SUM(quantity) as total_quantity,
                AVG(CASE
                    WHEN quantity > 0 AND amount_per_item > 0
                    THEN amount_per_item / quantity
                    ELSE unit_price_item
                END) as avg_unit_price,
                MAX(barcode) as barcode,
                COUNT(*) as invoice_count
            FROM invoice_table
            WHERE item_name IS NOT NULL
              AND item_name != ''
              AND quantity > 0
            GROUP BY item_name
            ORDER BY item_name
            """

            cursor.execute(query)
            invoice_items = cursor.fetchall()

            print(f"📊 Found {len(invoice_items)} unique items in invoice table")

            # Get current date for last_updated
            current_date = datetime.now().strftime('%Y-%m-%d')

            updated_count = 0
            inserted_count = 0

            for item in invoice_items:
                item_name, category, total_quantity, avg_unit_price, barcode, invoice_count = item

                # Calculate the price with 9% markup
                if avg_unit_price and avg_unit_price > 0:
                    calculated_price = round(avg_unit_price * 1.09, 2)
                else:
                    calculated_price = 0.0

                # Check if item already exists in inventory
                cursor.execute(
                    "SELECT id, total_quantity FROM inventory_table WHERE item_name = ?",
                    (item_name,)
                )
                existing_item = cursor.fetchone()

                if existing_item:
                    # Update existing item
                    cursor.execute("""
                        UPDATE inventory_table
                        SET category = ?,
                            total_quantity = ?,
                            unit_price = ?,
                            calculated_price = ?,
                            barcode = ?,
                            last_updated = ?
                        WHERE item_name = ?
                    """, (category, total_quantity, avg_unit_price, calculated_price,
                          barcode, current_date, item_name))
                    updated_count += 1

                    print(f"📝 Updated: {item_name} - Qty: {total_quantity}, Price: ${calculated_price:.2f}")

                else:
                    # Insert new item
                    cursor.execute("""
                        INSERT INTO inventory_table
                        (item_name, category, total_quantity, unit_price, calculated_price, barcode, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (item_name, category, total_quantity, avg_unit_price,
                          calculated_price, barcode, current_date))
                    inserted_count += 1

                    print(f"➕ Added: {item_name} - Qty: {total_quantity}, Price: ${calculated_price:.2f}")

            conn.commit()

            print(f"\n✅ Inventory update completed!")
            print(f"   📊 Total items processed: {len(invoice_items)}")
            print(f"   ➕ New items added: {inserted_count}")
            print(f"   📝 Existing items updated: {updated_count}")

            return True

        except Exception as e:
            print(f"❌ Error updating inventory: {e}")
            conn.rollback()
            return False

        finally:
            conn.close()

    def get_inventory_summary(self):
        """Get a summary of current inventory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get total items and total value
            cursor.execute("""
                SELECT
                    COUNT(*) as total_items,
                    SUM(total_quantity) as total_quantity,
                    SUM(total_quantity * calculated_price) as total_value,
                    AVG(calculated_price) as avg_price
                FROM inventory_table
            """)

            summary = cursor.fetchone()
            total_items, total_quantity, total_value, avg_price = summary

            # Get top 5 items by quantity
            cursor.execute("""
                SELECT item_name, total_quantity, calculated_price
                FROM inventory_table
                ORDER BY total_quantity DESC
                LIMIT 5
            """)

            top_items = cursor.fetchall()

            # Get categories breakdown
            cursor.execute("""
                SELECT category, COUNT(*) as item_count, SUM(total_quantity) as category_quantity
                FROM inventory_table
                GROUP BY category
                ORDER BY category_quantity DESC
            """)

            categories = cursor.fetchall()

            print(f"\n📋 INVENTORY SUMMARY")
            print(f"   Total Items: {total_items or 0}")
            print(f"   Total Quantity: {total_quantity or 0}")
            print(f"   Total Value: ${total_value or 0:.2f}")
            print(f"   Average Price: ${avg_price or 0:.2f}")

            print(f"\n🔝 TOP 5 ITEMS BY QUANTITY:")
            for item in top_items:
                print(f"   {item[0]}: {item[1]} units @ ${item[2]:.2f}")

            print(f"\n📂 CATEGORIES:")
            for category in categories:
                cat_name = category[0] or "Uncategorized"
                print(f"   {cat_name}: {category[1]} items, {category[2]} total quantity")

        except Exception as e:
            print(f"❌ Error getting inventory summary: {e}")

        finally:
            conn.close()

    def clean_obsolete_items(self, days_old=30):
        """
        Remove items from inventory that haven't been updated in X days
        (items no longer appearing in recent invoices)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT COUNT(*) FROM inventory_table
                WHERE last_updated < ?
            """, (cutoff_date,))

            obsolete_count = cursor.fetchone()[0]

            if obsolete_count > 0:
                print(f"🗑️  Found {obsolete_count} items not updated in {days_old} days")

                # Show which items would be removed
                cursor.execute("""
                    SELECT item_name, last_updated FROM inventory_table
                    WHERE last_updated < ?
                    ORDER BY last_updated
                """, (cutoff_date,))

                obsolete_items = cursor.fetchall()
                for item in obsolete_items:
                    print(f"   - {item[0]} (last updated: {item[1]})")

                # Uncomment the next lines if you want to actually delete old items
                # cursor.execute("DELETE FROM inventory_table WHERE last_updated < ?", (cutoff_date,))
                # conn.commit()
                # print(f"✅ Removed {obsolete_count} obsolete items")
            else:
                print(f"✅ No obsolete items found (older than {days_old} days)")

        except Exception as e:
            print(f"❌ Error cleaning obsolete items: {e}")

        finally:
            conn.close()

def main():
    """Main function to update inventory"""
    print("🚀 Starting inventory update process...")

    # Get database path
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dailydelights.db')

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return

    # Initialize updater
    updater = InventoryUpdater(db_path)

    # Update inventory from invoices
    success = updater.calculate_inventory_from_invoices()

    if success:
        # Show summary
        updater.get_inventory_summary()

        # Check for obsolete items (but don't delete them)
        updater.clean_obsolete_items()

        print("\n✅ Inventory update process completed successfully!")
    else:
        print("\n❌ Inventory update process failed!")

if __name__ == "__main__":
    main()