"""
Order Recommendation Engine - Carton-Based Monthly Planning with Weekly Batches
Generates comprehensive monthly order plan with carton quantities and price comparisons
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from collections import defaultdict


class OrderRecommendationEngine:
    def __init__(self, db_path='dailydelights.db'):
        self.db_path = db_path
        self.monthly_sales = 15000  # Current monthly sales SGD 15K
        self.target_sales = 20000   # Target SGD 20K
        self.profit_margin = 0.30   # 30% profit margin

        # Monthly budget for orders (cost price)
        self.monthly_budget = 12000  # SGD 12K cost budget per month

        # Excluded categories
        self.excluded_categories = ['Milk Curd Yoghurt Batter', 'Bread & Spread']

        # Price comparison tolerance (10%)
        self.price_tolerance = 0.10

        # Minimum order value per supplier per week (SGD)
        self.min_order_value = 10.0  # Lowered to include more suppliers

        # Price changes tracking
        self.price_changes = []

    def get_connection(self):
        """Create database connection"""
        return sqlite3.connect(self.db_path)

    def get_carton_info_from_invoices(self) -> Dict[str, Dict]:
        """
        Get carton information from invoice_table using MOST RECENT invoice per item
        Returns: {
            item_name_lower: {
                'supplier': str,
                'carton_or_loose': str,
                'items_per_carton': int,
                'carton_price': float,
                'unit_price_item': float,
                'item_name_original': str
            }
        }
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
                barcode,
                invoice_date
            FROM invoice_table
            WHERE supplier_name IS NOT NULL
            AND item_name IS NOT NULL
            ORDER BY invoice_date DESC
        """)

        carton_info = {}
        seen_items = set()

        for row in cursor.fetchall():
            supplier = row[0]
            item_name = row[1]
            carton_or_loose = (row[2] or 'loose').lower().strip()
            items_per_carton = row[3] or 1
            carton_price = row[4] or 0.0
            unit_price_item = row[5] or 0.0
            barcode = row[6]
            invoice_date = row[7]

            # Normalize carton_or_loose
            is_carton = carton_or_loose in ['carton', 'pack', 'packet', 'bdl', 'sac']

            key = item_name.lower().strip()

            # Only store the FIRST occurrence (most recent) for each item
            if key not in seen_items:
                seen_items.add(key)
                carton_info[key] = {
                    'supplier': supplier,
                    'carton_or_loose': 'carton' if is_carton else 'loose',
                    'is_carton': is_carton,
                    'items_per_carton': int(items_per_carton) if items_per_carton else 1,
                    'carton_price': float(carton_price) if carton_price else 0.0,
                    'unit_price_item': float(unit_price_item) if unit_price_item else 0.0,
                    'item_name_original': item_name,
                    'barcode': barcode,
                    'invoice_date': invoice_date
                }

        conn.close()
        print(f"Loaded {len(carton_info)} items with carton info from invoices (most recent supplier)")
        return carton_info

    def get_product_inventory_costs(self) -> Dict[str, Dict]:
        """
        Get actual unit costs from product_inventory_table
        Returns: {item_name_lower: {'unit_cost': float, 'barcode': str, 'category': str}}
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

            # Parse unit cost (remove $ sign and convert to float)
            try:
                if isinstance(unit_cost_str, str):
                    cost = float(unit_cost_str.replace('$', '').replace(',', '').strip())
                else:
                    cost = float(unit_cost_str)

                # Store by product name (lowercase)
                key = product_name.lower().strip()
                inventory_costs[key] = {
                    'product_name': product_name,
                    'unit_cost': cost,
                    'barcode': barcode,
                    'category': category
                }

                # Also store by barcode if available
                if barcode:
                    inventory_costs[f"barcode_{barcode}"] = inventory_costs[key]

            except (ValueError, AttributeError):
                continue

        conn.close()
        print(f"Loaded {len(inventory_costs)} product costs from inventory")
        return inventory_costs

    def get_all_items_with_demand(self) -> List[Dict]:
        """
        Get ALL items from demand_forecasts to ensure complete inventory coverage
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                item_name,
                category,
                barcode,
                weekly_demand_qty,
                weekly_demand_value_sgd,
                sales_velocity
            FROM demand_forecasts
            WHERE category NOT IN ({})
            ORDER BY weekly_demand_value_sgd DESC
        """.format(','.join(['?' for _ in self.excluded_categories])), self.excluded_categories)

        items = []
        for row in cursor.fetchall():
            items.append({
                'item_name': row[0],
                'category': row[1],
                'barcode': row[2],
                'weekly_demand_qty': row[3],
                'weekly_demand_value_sgd': row[4],
                'sales_velocity': row[5]
            })

        conn.close()
        return items

    def find_unit_cost(self, item_name: str, barcode: str, inventory_costs: Dict) -> float:
        """
        Find unit cost for an item from product_inventory_table
        Priority: 1. Barcode match, 2. Exact name match, 3. Fuzzy name match
        Returns: unit_cost or None
        """
        # Priority 1: Match by barcode
        if barcode and f"barcode_{barcode}" in inventory_costs:
            return inventory_costs[f"barcode_{barcode}"]['unit_cost']

        # Priority 2: Exact name match
        item_key = item_name.lower().strip()
        if item_key in inventory_costs:
            return inventory_costs[item_key]['unit_cost']

        # Priority 3: Fuzzy name match (at least 80% word overlap)
        item_words = set(item_key.split())
        best_cost = None
        best_score = 0

        for key, data in inventory_costs.items():
            if key.startswith('barcode_'):
                continue

            key_words = set(key.split())
            if len(item_words) > 0:
                overlap = len(item_words & key_words)
                score = overlap / len(item_words)

                if score > best_score and score >= 0.8:  # 80% match
                    best_score = score
                    best_cost = data['unit_cost']

        return best_cost

    def compare_prices(self, item_name: str, invoice_unit_price: float,
                      inventory_unit_cost: float, supplier: str) -> None:
        """
        Compare prices between invoice and product_inventory
        Track if invoice price is >10% higher than inventory price
        """
        if invoice_unit_price <= 0 or inventory_unit_cost <= 0:
            return

        # Calculate percentage difference
        price_diff = invoice_unit_price - inventory_unit_cost
        percentage_change = (price_diff / inventory_unit_cost) * 100

        # Only track if invoice price is MORE than 10% higher than inventory
        if percentage_change > (self.price_tolerance * 100):
            self.price_changes.append({
                'item_name': item_name,
                'supplier': supplier,
                'inventory_price': round(inventory_unit_cost, 2),
                'invoice_price': round(invoice_unit_price, 2),
                'price_difference': round(price_diff, 2),
                'percentage_hike': round(percentage_change, 2),
                'detected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

    def save_price_changes(self) -> int:
        """Save price changes to database (with deduplication)"""
        if not self.price_changes:
            return 0

        conn = self.get_connection()
        cursor = conn.cursor()

        # Create price_changes table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_changes (
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

        # Insert new price changes (with deduplication via UNIQUE constraint)
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
        return saved_count

    def get_supplier_item_mapping(self) -> Dict[str, List[str]]:
        """
        Get mapping of which supplier supplies which items
        Returns: {supplier_name: [item_names]}
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT
                supplier_name,
                item_name
            FROM invoice_table
            WHERE supplier_name IS NOT NULL
            AND item_name IS NOT NULL
            GROUP BY supplier_name, item_name
        """)

        supplier_items = defaultdict(set)
        for row in cursor.fetchall():
            supplier = row[0]
            item_name = row[1].lower().strip()
            supplier_items[supplier].add(item_name)

        conn.close()
        return {k: list(v) for k, v in supplier_items.items()}

    def find_supplier_for_item(self, item_name: str, supplier_items_map: Dict) -> str:
        """Find which supplier supplies an item"""
        item_key = item_name.lower().strip()

        # Exact match
        for supplier, items in supplier_items_map.items():
            if item_key in items:
                return supplier

        # Fuzzy match with lower threshold for better coverage
        item_words = set(item_key.split())
        best_supplier = None
        best_score = 0

        for supplier, items in supplier_items_map.items():
            for item in items:
                item_words_supplier = set(item.split())
                if len(item_words) > 0:
                    overlap = len(item_words & item_words_supplier)
                    score = overlap / len(item_words)
                    # Lowered threshold from 0.7 to 0.5 (50% match)
                    if score > best_score and score >= 0.5:
                        best_score = score
                        best_supplier = supplier

        return best_supplier

    def generate_monthly_recommendations(self, start_date: datetime) -> List[Dict]:
        """
        Generate CARTON-BASED order recommendations for entire month with budget limits
        """
        print(f"Generating carton-based monthly recommendations for {start_date.strftime('%B %Y')}...")

        # Get all data
        all_items = self.get_all_items_with_demand()
        inventory_costs = self.get_product_inventory_costs()
        carton_info = self.get_carton_info_from_invoices()
        supplier_items_map = self.get_supplier_item_mapping()

        print(f"- Total items in demand: {len(all_items)}")
        print(f"- Products with costs: {len([k for k in inventory_costs.keys() if not k.startswith('barcode_')])}")
        print(f"- Items with carton info: {len(carton_info)}")
        print(f"- Suppliers: {len(supplier_items_map)}")
        print(f"- Monthly budget: SGD {self.monthly_budget:,.2f}")

        # Calculate weeks
        month_start = start_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

        weeks = []
        current_week_start = month_start
        week_num = 1

        while current_week_start <= month_end:
            week_end = min(current_week_start + timedelta(days=6), month_end)
            weeks.append({
                'week_num': week_num,
                'start_date': current_week_start,
                'end_date': week_end,
                'week_label': f"Week {week_num} ({current_week_start.strftime('%b %d')} - {week_end.strftime('%b %d')})"
            })
            current_week_start = week_end + timedelta(days=1)
            week_num += 1

        print(f"- Planning for {len(weeks)} weeks")

        # Weekly budget
        weekly_budget = self.monthly_budget / len(weeks)
        print(f"- Weekly budget: SGD {weekly_budget:,.2f}")

        # Match items to suppliers and costs FIRST (like before)
        # Then ENHANCE with carton info if available
        items_with_costs = []
        matched_count = 0
        unmatched_count = 0

        for item in all_items:
            item_key = item['item_name'].lower().strip()

            # Step 1: Find unit cost from product_inventory (REQUIRED)
            unit_cost = self.find_unit_cost(item['item_name'], item['barcode'], inventory_costs)
            if unit_cost is None:
                unmatched_count += 1
                continue

            # Step 2: Find supplier using original fuzzy matching logic
            supplier = self.find_supplier_for_item(item['item_name'], supplier_items_map)
            if supplier is None:
                unmatched_count += 1
                continue

            # Step 3: ENHANCE with carton info if available (OPTIONAL)
            carton_data = None

            # ONLY use EXACT match for price comparison (NO fuzzy matching)
            # Fuzzy matching causes issues like matching "JW Black 700ml" with "JW Black 200ml"
            if item_key in carton_info:
                carton_data = carton_info[item_key]

                # Step 4: Compare prices ONLY if EXACT match found
                if carton_data and carton_data['unit_price_item'] > 0:
                    # Calculate correct per-item price from invoice
                    invoice_per_item_price = carton_data['unit_price_item']

                    # CRITICAL FIX: If it's a carton, ALWAYS recalculate per-item price
                    # because invoice_table might have incorrect unit_price_item
                    if carton_data['is_carton'] and carton_data['items_per_carton'] > 1:
                        # Use carton_price (unit_price) divided by items_per_carton
                        if carton_data['carton_price'] > 0:
                            invoice_per_item_price = carton_data['carton_price'] / carton_data['items_per_carton']
                        else:
                            # Fallback: divide unit_price_item by items_per_carton
                            invoice_per_item_price = carton_data['unit_price_item'] / carton_data['items_per_carton']

                    self.compare_prices(
                        item['item_name'],
                        invoice_per_item_price,
                        unit_cost,
                        supplier
                    )
            else:
                # NO MATCH - try fuzzy match ONLY for carton ordering (not price comparison)
                item_words = set(item_key.split())
                best_match = None
                best_score = 0
                for key, data in carton_info.items():
                    key_words = set(key.split())
                    if len(item_words) > 0:
                        overlap = len(item_words & key_words)
                        score = overlap / len(item_words)
                        if score > best_score and score >= 0.7:
                            best_score = score
                            best_match = data
                if best_match:
                    carton_data = best_match
                    # DO NOT compare prices with fuzzy matches!

            matched_count += 1

            # Step 5: Determine ordering unit (carton if available, else loose)
            if carton_data and carton_data['is_carton'] and carton_data['items_per_carton'] > 1:
                # Use carton ordering
                items_with_costs.append({
                    **item,
                    'unit_cost': unit_cost,
                    'supplier': supplier,
                    'order_unit': 'carton',
                    'items_per_carton': carton_data['items_per_carton'],
                    'carton_price': carton_data['carton_price'] if carton_data['carton_price'] > 0 else unit_cost * carton_data['items_per_carton'],
                    'unit_price_item': carton_data['unit_price_item'] if carton_data['unit_price_item'] > 0 else unit_cost
                })
            else:
                # Use loose/individual item ordering (fallback)
                items_with_costs.append({
                    **item,
                    'unit_cost': unit_cost,
                    'supplier': supplier,
                    'order_unit': 'loose',
                    'items_per_carton': 1,
                    'carton_price': unit_cost,
                    'unit_price_item': unit_cost
                })

        print(f"- Items matched: {matched_count}")
        print(f"- Items unmatched: {unmatched_count}")
        print(f"- Price changes detected (>10% hike): {len(self.price_changes)}")

        # Sort by weekly demand value (prioritize high-revenue items)
        items_with_costs.sort(key=lambda x: x['weekly_demand_value_sgd'], reverse=True)

        # Generate recommendations for each week
        all_recommendations = []

        for week in weeks:
            week_recs = self._generate_week_recommendations_with_budget(
                week,
                items_with_costs,
                weekly_budget
            )
            all_recommendations.extend(week_recs)

        print(f"✓ Generated {len(all_recommendations)} recommendations across {len(weeks)} weeks")

        return all_recommendations

    def _generate_week_recommendations_with_budget(self, week: Dict, items: List[Dict],
                                                    weekly_budget: float) -> List[Dict]:
        """
        Generate CARTON-BASED recommendations for a week, respecting budget limits.
        Each supplier appears ONLY ONCE per week with all their items combined.
        Orders are placed in CARTONS (or loose for non-carton items).
        """
        # Group items by supplier (this ensures one order per supplier per week)
        by_supplier = defaultdict(list)
        for item in items:
            by_supplier[item['supplier']].append(item)

        # Create one order per supplier
        supplier_orders = []
        for supplier, supplier_items in by_supplier.items():
            order_items = []
            order_cost = 0

            # Add ALL items from this supplier (with CARTON calculations)
            for item in supplier_items:
                # Calculate weekly quantity needed (individual items)
                weekly_qty_items = max(1, round(item['weekly_demand_qty']))

                # Convert to cartons if applicable
                if item['order_unit'] == 'carton':
                    items_per_carton = item['items_per_carton']
                    # Calculate number of cartons needed (round up to full carton)
                    cartons_needed = max(1, (weekly_qty_items + items_per_carton - 1) // items_per_carton)

                    # Calculate cost using carton price (or calculate from unit price)
                    if item['carton_price'] > 0:
                        carton_cost = item['carton_price']
                    else:
                        # Fallback: calculate from unit price
                        carton_cost = item['unit_cost'] * items_per_carton

                    item_total_cost = cartons_needed * carton_cost

                    order_items.append({
                        'item_name': item['item_name'],
                        'category': item['category'],
                        'order_unit': 'carton',
                        'cartons': cartons_needed,
                        'items_per_carton': items_per_carton,
                        'total_items': cartons_needed * items_per_carton,
                        'carton_price': round(carton_cost, 2),
                        'unit_cost': round(item['unit_cost'], 2),
                        'subtotal': round(item_total_cost, 2),
                        'sales_velocity': item['sales_velocity']
                    })

                    order_cost += item_total_cost

                else:
                    # Loose items - order by piece
                    item_cost = weekly_qty_items * item['unit_cost']

                    order_items.append({
                        'item_name': item['item_name'],
                        'category': item['category'],
                        'order_unit': 'loose',
                        'quantity': weekly_qty_items,
                        'unit_cost': round(item['unit_cost'], 2),
                        'subtotal': round(item_cost, 2),
                        'sales_velocity': item['sales_velocity']
                    })

                    order_cost += item_cost

            # Store order with its cost
            if order_items:
                supplier_orders.append({
                    'supplier': supplier,
                    'cost': order_cost,
                    'items': order_items
                })

        # Sort suppliers by cost (largest first) to prioritize high-value suppliers
        supplier_orders.sort(key=lambda x: x['cost'], reverse=True)

        # Now select suppliers until we hit the weekly budget
        # BUT only include orders >= minimum order value
        week_recommendations = []
        total_week_cost = 0

        for order in supplier_orders:
            # Skip orders below minimum order value (unreasonable to place)
            if order['cost'] < self.min_order_value:
                continue

            # Check if we can afford this supplier's order
            if total_week_cost + order['cost'] <= weekly_budget:
                week_recommendations.append({
                    'supplier_name': order['supplier'],
                    'recommended_date': week['start_date'].strftime('%Y-%m-%d'),
                    'week_label': week['week_label'],
                    'week_number': week['week_num'],
                    'total_amount_sgd': round(order['cost'], 2),
                    'items': order['items'],
                    'notes': f"{week['week_label']} - {len(order['items'])} items (Min: SGD {self.min_order_value})",
                    'status': 'pending'
                })
                total_week_cost += order['cost']

        return week_recommendations

    def save_recommendations(self, recommendations: List[Dict]) -> int:
        """Save generated recommendations to database"""
        conn = self.get_connection()
        cursor = conn.cursor()

        saved_count = 0
        for rec in recommendations:
            items_json = json.dumps(rec['items'])

            cursor.execute("""
                INSERT INTO order_recommendations
                (supplier_name, recommended_date, total_amount_sgd, items_json, notes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                rec['supplier_name'],
                rec['recommended_date'],
                rec['total_amount_sgd'],
                items_json,
                rec['notes'],
                rec.get('status', 'pending')
            ))
            saved_count += 1

        conn.commit()
        conn.close()

        return saved_count

    def clear_pending_recommendations(self):
        """Clear all pending recommendations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM order_recommendations WHERE status = 'pending'")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    def run(self, target_month: str = None, clear_existing=True):
        """
        Run the recommendation engine for a specific month
        target_month format: 'YYYY-MM' (e.g., '2025-11' for November 2025)
        """
        print("="*80)
        print("ORDER RECOMMENDATION ENGINE - MONTHLY PLANNING")
        print("="*80)

        # Parse target month or use next month
        if target_month:
            year, month = map(int, target_month.split('-'))
            start_date = datetime(year, month, 1)
        else:
            # Default to next month
            today = datetime.now()
            if today.month == 12:
                start_date = datetime(today.year + 1, 1, 1)
            else:
                start_date = datetime(today.year, today.month + 1, 1)

        print(f"\nTarget Month: {start_date.strftime('%B %Y')}")
        print(f"Monthly Sales: SGD {self.monthly_sales:,.2f}")
        print(f"Monthly Cost Budget: SGD {self.monthly_budget:,.2f}")

        if clear_existing:
            deleted = self.clear_pending_recommendations()
            print(f"Cleared {deleted} existing pending recommendations\n")

        # Generate monthly recommendations
        recommendations = self.generate_monthly_recommendations(start_date)

        # Save to database
        saved = self.save_recommendations(recommendations)

        # Save price changes
        price_changes_saved = self.save_price_changes()
        if price_changes_saved > 0:
            print(f"\n⚠️  Detected {price_changes_saved} items with >10% price hikes - saved to price_changes table")

        # Calculate total
        total_cost = sum(r['total_amount_sgd'] for r in recommendations)
        print(f"\n✓ Saved {saved} weekly recommendations (CARTON-BASED)")
        print(f"✓ Total monthly cost: SGD {total_cost:,.2f} (Budget: SGD {self.monthly_budget:,.2f})")
        print("="*80)

        return recommendations


if __name__ == "__main__":
    import sys

    # Allow passing target month as command line argument
    target_month = sys.argv[1] if len(sys.argv) > 1 else '2025-11'

    engine = OrderRecommendationEngine()
    recommendations = engine.run(target_month=target_month)

    # Display summary
    print("\nMONTHLY RECOMMENDATIONS SUMMARY:")
    print("-"*80)

    # Group by week
    by_week = defaultdict(list)
    for rec in recommendations:
        by_week[rec['recommended_date']].append(rec)

    for week_date in sorted(by_week.keys()):
        week_recs = by_week[week_date]
        week_total = sum(r['total_amount_sgd'] for r in week_recs)
        print(f"\n{week_recs[0]['week_label']}: {len(week_recs)} orders, SGD {week_total:.2f}")

        for rec in sorted(week_recs, key=lambda x: x['total_amount_sgd'], reverse=True)[:5]:
            print(f"  {rec['supplier_name']}: SGD {rec['total_amount_sgd']:.2f} ({len(rec['items'])} items)")
