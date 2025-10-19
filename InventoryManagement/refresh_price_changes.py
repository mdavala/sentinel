#!/usr/bin/env python3
"""
Refresh Price Changes Table
Compares invoice_table prices with product_inventory_table prices
Automatically detects items with >10% price increases
"""

import sqlite3
from datetime import datetime
from typing import Dict, List


class PriceChangeDetector:
    def __init__(self, db_path='dailydelights.db'):
        self.db_path = db_path
        self.price_tolerance = 0.10  # 10% tolerance
        self.price_changes = []

    def get_connection(self):
        """Create database connection"""
        return sqlite3.connect(self.db_path)

    def get_invoice_items_with_prices(self) -> Dict[str, Dict]:
        """
        Get most recent invoice data for each item
        Returns: {item_name_lower: {supplier, unit_price_item, is_carton, items_per_carton, ...}}
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get most recent invoice for each item (by invoice_date)
        cursor.execute("""
            SELECT
                supplier_name,
                item_name,
                carton_or_loose,
                items_per_carton,
                unit_price,
                unit_price_item,
                invoice_date
            FROM invoice_table
            WHERE supplier_name IS NOT NULL
            AND item_name IS NOT NULL
            AND unit_price_item IS NOT NULL
            AND unit_price_item > 0
            ORDER BY invoice_date DESC
        """)

        invoice_items = {}
        seen_items = set()

        for row in cursor.fetchall():
            supplier = row[0]
            item_name = row[1]
            carton_or_loose = (row[2] or 'loose').lower().strip()
            items_per_carton = row[3] or 1
            unit_price = row[4] or 0.0
            unit_price_item = row[5] or 0.0
            invoice_date = row[6]

            # Normalize
            is_carton = carton_or_loose in ['carton', 'pack', 'packet', 'bdl', 'sac']
            key = item_name.lower().strip()

            # Only store the FIRST occurrence (most recent) for each item
            if key not in seen_items:
                seen_items.add(key)

                # Calculate correct per-item price
                per_item_price = unit_price_item

                # CRITICAL: If carton, recalculate per-item price
                if is_carton and items_per_carton > 1:
                    if unit_price > 0:
                        # Use unit_price (carton price) divided by items_per_carton
                        per_item_price = unit_price / items_per_carton
                    else:
                        # Fallback: divide unit_price_item by items_per_carton
                        per_item_price = unit_price_item / items_per_carton

                invoice_items[key] = {
                    'supplier': supplier,
                    'invoice_per_item_price': per_item_price,
                    'is_carton': is_carton,
                    'items_per_carton': items_per_carton,
                    'invoice_date': invoice_date,
                    'item_name_original': item_name
                }

        conn.close()
        print(f"✓ Loaded {len(invoice_items)} items from invoice_table")
        return invoice_items

    def get_product_inventory_costs(self) -> Dict[str, Dict]:
        """
        Get unit costs from product_inventory_table
        Returns: {item_name_lower: {'unit_cost': float, 'product_name': str}}
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                product_name,
                unit_cost,
                barcode,
                category
            FROM product_inventory_table
            WHERE unit_cost IS NOT NULL
            AND unit_cost != ''
        """)

        inventory_costs = {}
        for row in cursor.fetchall():
            product_name = row[0]
            unit_cost_str = row[1]
            barcode = row[2]
            category = row[3]

            # Parse unit cost (remove $ sign)
            try:
                if isinstance(unit_cost_str, str):
                    cost = float(unit_cost_str.replace('$', '').replace(',', '').strip())
                else:
                    cost = float(unit_cost_str)

                key = product_name.lower().strip()
                inventory_costs[key] = {
                    'product_name': product_name,
                    'unit_cost': cost,
                    'barcode': barcode,
                    'category': category
                }

            except (ValueError, AttributeError):
                continue

        conn.close()
        print(f"✓ Loaded {len(inventory_costs)} items from product_inventory_table")
        return inventory_costs

    def compare_prices(self):
        """
        Compare invoice prices with inventory prices
        Detect items with >10% price increases
        """
        print("\n" + "="*80)
        print("PRICE CHANGE DETECTION - Comparing Invoice vs Inventory")
        print("="*80)

        # Get data
        invoice_items = self.get_invoice_items_with_prices()
        inventory_items = self.get_product_inventory_costs()

        # Compare prices - EXACT MATCH ONLY
        matches_found = 0
        price_increases = 0

        for item_key, invoice_data in invoice_items.items():
            # EXACT match only (no fuzzy matching)
            if item_key not in inventory_items:
                continue

            inventory_data = inventory_items[item_key]
            matches_found += 1

            # Get prices
            invoice_price = invoice_data['invoice_per_item_price']
            inventory_price = inventory_data['unit_cost']

            # Calculate percentage difference
            price_diff = invoice_price - inventory_price
            percentage_change = (price_diff / inventory_price) * 100

            # Only track if invoice price is MORE than 10% higher than inventory
            if percentage_change > (self.price_tolerance * 100):
                price_increases += 1
                self.price_changes.append({
                    'item_name': invoice_data['item_name_original'],
                    'supplier': invoice_data['supplier'],
                    'inventory_price': round(inventory_price, 2),
                    'invoice_price': round(invoice_price, 2),
                    'price_difference': round(price_diff, 2),
                    'percentage_hike': round(percentage_change, 2),
                    'detected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

        print(f"\n✓ Items compared: {matches_found}")
        print(f"✓ Price increases detected (>10%): {price_increases}")

    def clear_price_changes_table(self):
        """Clear all existing price changes"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Drop and recreate table to ensure fresh data
        cursor.execute("DROP TABLE IF EXISTS price_changes")

        cursor.execute("""
            CREATE TABLE price_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name VARCHAR NOT NULL,
                supplier VARCHAR,
                inventory_price FLOAT,
                invoice_price FLOAT,
                price_difference FLOAT,
                percentage_hike FLOAT,
                detected_at DATETIME,
                reviewed BOOLEAN DEFAULT 0,
                UNIQUE(item_name, supplier, inventory_price, invoice_price)
            )
        """)

        conn.commit()
        conn.close()
        print("✓ Cleared price_changes table")

    def save_price_changes(self) -> int:
        """Save price changes to database"""
        if not self.price_changes:
            print("✓ No price changes to save")
            return 0

        conn = self.get_connection()
        cursor = conn.cursor()

        saved_count = 0
        for change in self.price_changes:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO price_changes
                    (item_name, supplier, inventory_price, invoice_price,
                     price_difference, percentage_hike, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    change['item_name'],
                    change['supplier'],
                    change['inventory_price'],
                    change['invoice_price'],
                    change['price_difference'],
                    change['percentage_hike'],
                    change['detected_at']
                ))
                if cursor.rowcount > 0:
                    saved_count += 1
            except Exception as e:
                print(f"Warning: Could not save price change for {change['item_name']}: {e}")
                continue

        conn.commit()
        conn.close()

        print(f"✓ Saved {saved_count} price changes to database")
        return saved_count

    def display_price_changes(self):
        """Display detected price changes"""
        if not self.price_changes:
            return

        print("\n" + "-"*80)
        print("PRICE CHANGES DETECTED (>10% increase):")
        print("-"*80)

        for change in sorted(self.price_changes, key=lambda x: x['percentage_hike'], reverse=True):
            print(f"\n{change['item_name']}")
            print(f"  Supplier: {change['supplier']}")
            print(f"  Inventory: ${change['inventory_price']:.2f}")
            print(f"  Invoice:   ${change['invoice_price']:.2f}")
            print(f"  Increase:  +${change['price_difference']:.2f} (+{change['percentage_hike']:.1f}%)")

    def refresh(self):
        """
        Main refresh function - clear and rebuild price_changes table
        """
        print(f"\n{'='*80}")
        print(f"REFRESH PRICE CHANGES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # Step 1: Clear existing data
        self.clear_price_changes_table()

        # Step 2: Compare prices
        self.compare_prices()

        # Step 3: Save new price changes
        self.save_price_changes()

        # Step 4: Display results
        self.display_price_changes()

        print(f"\n{'='*80}")
        print(f"✓ Price changes refresh completed successfully!")
        print(f"{'='*80}\n")

        return len(self.price_changes)


if __name__ == "__main__":
    import sys

    # Allow passing database path as argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'dailydelights.db'

    detector = PriceChangeDetector(db_path)
    detector.refresh()
