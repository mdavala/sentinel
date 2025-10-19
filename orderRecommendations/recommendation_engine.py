#!/usr/bin/env python3
"""
recommendation_engine.py - Core order recommendation engine
Analyzes sales patterns, supplier frequencies, and inventory to recommend orders
"""

import pandas as pd
import sqlite3
import numpy as np
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
from product_matcher import ProductMatcher
from collections import defaultdict

class OrderRecommendationEngine:
    """
    Core engine for generating order recommendations based on:
    1. Sales patterns from transaction data
    2. Supplier order frequencies from zoho forms
    3. Current inventory levels
    4. Seasonal trends and patterns
    """

    def __init__(self):
        self.product_matcher = ProductMatcher()
        self.sales_patterns = {}
        self.supplier_patterns = {}
        self.inventory_status = {}
        self._load_patterns()

    def _load_patterns(self):
        """Load sales patterns, supplier patterns, and inventory data"""
        self._load_sales_patterns()
        self._load_supplier_patterns()
        self._load_inventory_status()

    def _load_sales_patterns(self):
        """Analyze transaction data for sales patterns"""
        try:
            # Load transaction data - use absolute path
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            trans_file = os.path.join(script_dir, 'dd_transactionDetails', 'master_transaction_details.xlsx')
            df_trans = pd.read_excel(trans_file)
            df_trans['Date'] = pd.to_datetime(df_trans['Date'])

            # Analyze recent 3 months for current trends
            recent_date = df_trans['Date'].max()
            three_months_ago = recent_date - timedelta(days=90)
            recent_data = df_trans[df_trans['Date'] >= three_months_ago]

            # Calculate daily sales patterns for each product
            daily_sales = recent_data.groupby([
                recent_data['Date'].dt.date,
                'Transaction Item'
            ])['Transaction Item Quantity'].sum().reset_index()

            # Calculate patterns for each product
            for product in recent_data['Transaction Item'].unique():
                if pd.isna(product):
                    continue

                product_sales = daily_sales[daily_sales['Transaction Item'] == product]

                if len(product_sales) > 0:
                    # Calculate key metrics
                    total_sold = product_sales['Transaction Item Quantity'].sum()
                    avg_daily_sales = product_sales['Transaction Item Quantity'].mean()
                    max_daily_sales = product_sales['Transaction Item Quantity'].max()
                    days_with_sales = len(product_sales)
                    sales_frequency = days_with_sales / 90  # Frequency in last 90 days

                    # Calculate weekly pattern (day of week preferences)
                    weekly_pattern = recent_data[recent_data['Transaction Item'] == product].groupby(
                        recent_data['Date'].dt.dayofweek
                    )['Transaction Item Quantity'].mean().to_dict()

                    self.sales_patterns[product] = {
                        'total_sold_90_days': total_sold,
                        'avg_daily_sales': avg_daily_sales,
                        'max_daily_sales': max_daily_sales,
                        'sales_frequency': sales_frequency,
                        'weekly_pattern': weekly_pattern,
                        'trend': self._calculate_trend(product_sales),
                        'volatility': product_sales['Transaction Item Quantity'].std() if len(product_sales) > 1 else 0
                    }

            print(f"Loaded sales patterns for {len(self.sales_patterns)} products")

        except Exception as e:
            print(f"Error loading sales patterns: {e}")

    def _calculate_trend(self, product_sales_df):
        """Calculate trend direction for a product (increasing, decreasing, stable)"""
        if len(product_sales_df) < 10:
            return 'stable'

        # Simple linear regression on recent sales
        x = np.arange(len(product_sales_df))
        y = product_sales_df['Transaction Item Quantity'].values

        if len(x) > 1 and np.std(y) > 0:
            slope = np.polyfit(x, y, 1)[0]
            if slope > 0.1:
                return 'increasing'
            elif slope < -0.1:
                return 'decreasing'

        return 'stable'

    def _load_supplier_patterns(self):
        """Analyze supplier order patterns from zoho forms data"""
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            supplier_file = os.path.join(script_dir, 'zohoForms', 'supplier_orders_zf.csv')
            df_supplier = pd.read_csv(supplier_file)
            df_supplier['Date'] = pd.to_datetime(df_supplier['Date'], format='%d-%b-%Y')

            # Filter reliable data (Dec 2024 to June 2025)
            reliable_start = pd.to_datetime('2024-12-01')
            reliable_end = pd.to_datetime('2025-06-30')
            reliable_data = df_supplier[
                (df_supplier['Date'] >= reliable_start) &
                (df_supplier['Date'] <= reliable_end)
            ]

            # Analyze each supplier's patterns
            for supplier in reliable_data['Suppliers'].unique():
                supplier_orders = reliable_data[reliable_data['Suppliers'] == supplier].sort_values('Date')

                if len(supplier_orders) > 1:
                    # Calculate delivery frequency
                    date_diffs = supplier_orders['Date'].diff().dropna()
                    avg_days_between = date_diffs.dt.days.mean()

                    # Calculate order amount patterns
                    amounts = supplier_orders['Currency (SGD)']
                    avg_amount = amounts.mean()
                    min_amount = amounts.min()
                    max_amount = amounts.max()

                    # Determine delivery schedule
                    if avg_days_between <= 4:
                        delivery_frequency = 'high'  # 3+ times per week
                        recommended_buffer_days = 2
                    elif avg_days_between <= 7:
                        delivery_frequency = 'medium'  # 1-2 times per week
                        recommended_buffer_days = 4
                    else:
                        delivery_frequency = 'low'  # Weekly or less
                        recommended_buffer_days = 7

                    self.supplier_patterns[supplier] = {
                        'avg_days_between_orders': avg_days_between,
                        'delivery_frequency': delivery_frequency,
                        'recommended_buffer_days': recommended_buffer_days,
                        'avg_order_amount': avg_amount,
                        'min_order_amount': min_amount,
                        'max_order_amount': max_amount,
                        'total_orders': len(supplier_orders),
                        'last_order_date': supplier_orders['Date'].max()
                    }

            print(f"Loaded supplier patterns for {len(self.supplier_patterns)} suppliers")

        except Exception as e:
            print(f"Error loading supplier patterns: {e}")

    def _load_inventory_status(self):
        """Load current inventory status from database"""
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(script_dir, 'dailydelights.db')
            conn = sqlite3.connect(db_file)

            # Get current inventory
            inventory_df = pd.read_sql_query("""
                SELECT item_name, category, total_quantity, unit_price, last_updated
                FROM inventory_table
                WHERE total_quantity IS NOT NULL
            """, conn)

            # Get recent sales to estimate current stock levels
            recent_sales_df = pd.read_sql_query("""
                SELECT product_name, SUM(quantity_sold) as total_sold
                FROM sales_info
                WHERE report_date >= date('now', '-7 days')
                GROUP BY product_name
            """, conn)

            conn.close()

            # Process inventory data
            for _, row in inventory_df.iterrows():
                self.inventory_status[row['item_name']] = {
                    'current_quantity': row['total_quantity'],
                    'category': row['category'],
                    'unit_price': row['unit_price'],
                    'last_updated': row['last_updated']
                }

            # Add recent sales data
            for _, row in recent_sales_df.iterrows():
                product_name = row['product_name']
                # Try to find matching inventory item
                for inv_item in self.inventory_status:
                    if self.product_matcher.similarity_score(product_name, inv_item) > 0.7:
                        self.inventory_status[inv_item]['recent_sales_7_days'] = row['total_sold']
                        break

            print(f"Loaded inventory status for {len(self.inventory_status)} items")

        except Exception as e:
            print(f"Error loading inventory status: {e}")

    def predict_demand(self, product_name: str, days_ahead: int = 7) -> float:
        """Predict demand for a product over the next N days"""
        if product_name not in self.sales_patterns:
            return 0

        pattern = self.sales_patterns[product_name]
        base_daily_demand = pattern['avg_daily_sales']

        # Adjust for trend
        if pattern['trend'] == 'increasing':
            trend_multiplier = 1.2
        elif pattern['trend'] == 'decreasing':
            trend_multiplier = 0.8
        else:
            trend_multiplier = 1.0

        # Adjust for sales frequency (how often the product sells)
        frequency_multiplier = min(pattern['sales_frequency'] * 2, 1.0)

        predicted_demand = base_daily_demand * days_ahead * trend_multiplier * frequency_multiplier

        return max(0, predicted_demand)

    def calculate_reorder_point(self, product_name: str, supplier_name: str) -> Dict:
        """Calculate when and how much to reorder for a product"""
        # Get current inventory
        current_stock = 0
        for inv_item, inv_data in self.inventory_status.items():
            if self.product_matcher.similarity_score(product_name, inv_item) > 0.7:
                current_stock = inv_data['current_quantity']
                break

        # Get supplier pattern
        supplier_pattern = self.supplier_patterns.get(supplier_name, {
            'avg_days_between_orders': 7,
            'recommended_buffer_days': 4,
            'avg_order_amount': 100
        })

        # Calculate lead time (days until next delivery)
        lead_time = supplier_pattern['recommended_buffer_days']

        # Predict demand during lead time + safety buffer
        safety_days = 3  # Extra safety buffer
        total_days = lead_time + safety_days
        predicted_demand = self.predict_demand(product_name, total_days)

        # Calculate reorder quantity
        reorder_quantity = max(0, predicted_demand - current_stock)

        # Minimum order consideration
        if reorder_quantity > 0 and reorder_quantity < 5:
            reorder_quantity = 5  # Minimum practical order

        return {
            'current_stock': current_stock,
            'predicted_demand': predicted_demand,
            'reorder_quantity': reorder_quantity,
            'lead_time_days': lead_time,
            'urgency': self._calculate_urgency(current_stock, predicted_demand, lead_time),
            'supplier_delivery_frequency': supplier_pattern.get('delivery_frequency', 'medium')
        }

    def _calculate_urgency(self, current_stock: float, predicted_demand: float, lead_time: int) -> str:
        """Calculate urgency level for reordering"""
        if current_stock <= 0:
            return 'critical'

        days_of_stock = current_stock / (predicted_demand / lead_time) if predicted_demand > 0 else float('inf')

        if days_of_stock <= 2:
            return 'high'
        elif days_of_stock <= 5:
            return 'medium'
        else:
            return 'low'

    def generate_daily_recommendations(self, target_date: datetime) -> List[Dict]:
        """Generate order recommendations for a specific date"""
        recommendations = []

        # Get top selling products from recent data
        top_products = sorted(
            self.sales_patterns.items(),
            key=lambda x: x[1]['total_sold_90_days'],
            reverse=True
        )[:100]  # Increase to top 100 products

        # Group by potential suppliers
        supplier_recommendations = defaultdict(list)

        # First, try direct product matching
        for product_name, pattern in top_products:
            # Find supplier for this product
            supplier_matches = self.product_matcher.find_supplier_for_product(product_name)

            if supplier_matches:
                for supplier_product in supplier_matches:
                    supplier_name = self.product_matcher.get_supplier_from_invoice(supplier_product)

                    if supplier_name and supplier_name in self.supplier_patterns:
                        # Calculate reorder recommendation
                        reorder_info = self.calculate_reorder_point(product_name, supplier_name)

                        if reorder_info['reorder_quantity'] > 0:
                            recommendation = {
                                'product_name': product_name,
                                'supplier_product_name': supplier_product,
                                'supplier_name': supplier_name,
                                'recommended_quantity': round(reorder_info['reorder_quantity']),
                                'current_stock': reorder_info['current_stock'],
                                'predicted_demand': float(round(reorder_info['predicted_demand'], 1)),
                                'urgency': reorder_info['urgency'],
                                'days_of_stock': float(reorder_info['current_stock'] / max(pattern['avg_daily_sales'], 0.1)),
                                'supplier_frequency': reorder_info['supplier_delivery_frequency'],
                                'order_priority': self._calculate_priority(reorder_info, pattern)
                            }

                            supplier_recommendations[supplier_name].append(recommendation)

        # Always try category-based matching for suppliers that should order
        print(f"Found {len(supplier_recommendations)} suppliers with direct matches. Adding category-based matches...")

        # Track which products have been assigned to avoid duplicates
        assigned_products = set()
        for products in supplier_recommendations.values():
            for product in products:
                assigned_products.add(product['product_name'])

        for supplier_name, supplier_pattern in self.supplier_patterns.items():
            # Check if supplier should order today
            if self._should_order_today(supplier_name, target_date):
                # If we don't have recommendations for this supplier yet, find products by category
                if supplier_name not in supplier_recommendations:
                    potential_products = self._find_products_for_supplier(supplier_name, top_products, assigned_products)
                    if potential_products:
                        supplier_recommendations[supplier_name] = potential_products
                        # Update assigned products
                        for product in potential_products:
                            assigned_products.add(product['product_name'])

        # Enhanced fallback: If still few recommendations, create them based on high-demand products
        if len(supplier_recommendations) < 5:  # Want at least 5 suppliers
            print("Adding more recommendations based on demand patterns...")

            # Group high-demand products by category and create generic supplier recommendations
            high_demand_products = [p for p in top_products[:30] if p[1]['avg_daily_sales'] > 1.5]

            supplier_counter = 0
            active_suppliers = [s for s in self.supplier_patterns.keys()
                              if self._should_order_today(s, target_date)][:15]  # Top 15 suppliers

            for supplier_name in active_suppliers:
                # If supplier doesn't have recommendations yet, add some
                if supplier_name not in supplier_recommendations:
                    # Assign some high-demand products to this supplier
                    start_idx = supplier_counter * 3
                    end_idx = start_idx + 3
                    assigned_products = high_demand_products[start_idx:end_idx] if start_idx < len(high_demand_products) else []

                    recommendations_for_supplier = []
                    for product_name, pattern in assigned_products:
                        # Create a generic recommendation
                        predicted_demand = self.predict_demand(product_name, 7)
                        current_stock = 0  # Assume 0 stock for generic recommendations

                        if predicted_demand > 0:
                            recommendation = {
                                'product_name': product_name,
                                'supplier_product_name': f"High Demand - {product_name}",
                                'supplier_name': supplier_name,
                                'recommended_quantity': max(round(predicted_demand * 2), 5),  # 2x demand with minimum 5
                                'current_stock': current_stock,
                                'predicted_demand': float(round(predicted_demand, 1)),
                                'urgency': 'high' if predicted_demand > 5 else 'medium',
                                'days_of_stock': 0,
                                'supplier_frequency': self.supplier_patterns[supplier_name]['delivery_frequency'],
                                'order_priority': 85  # High priority for month start
                            }
                            recommendations_for_supplier.append(recommendation)

                    if recommendations_for_supplier:
                        supplier_recommendations[supplier_name] = recommendations_for_supplier

                    supplier_counter += 1

        # Format final recommendations by supplier
        final_recommendations = []
        for supplier_name, products in supplier_recommendations.items():
            if products:  # Only include suppliers with products to order
                # Sort products by priority within supplier
                products.sort(key=lambda x: x['order_priority'], reverse=True)

                total_estimated_amount = sum(p['recommended_quantity'] * 5 for p in products)  # Rough estimate

                final_recommendations.append({
                    'supplier_name': supplier_name,
                    'products': products,
                    'total_products': len(products),
                    'estimated_order_amount': total_estimated_amount,
                    'delivery_frequency': self.supplier_patterns[supplier_name]['delivery_frequency'],
                    'last_order_days_ago': (target_date - self.supplier_patterns[supplier_name]['last_order_date']).days,
                    'should_order_today': bool(self._should_order_today(supplier_name, target_date))
                })

        # Sort by urgency and importance
        final_recommendations.sort(key=lambda x: (
            sum(1 for p in x['products'] if p['urgency'] in ['critical', 'high']),
            x['total_products']
        ), reverse=True)

        return final_recommendations

    def _calculate_priority(self, reorder_info: Dict, sales_pattern: Dict) -> float:
        """Calculate priority score for ordering a product"""
        urgency_scores = {'critical': 100, 'high': 80, 'medium': 50, 'low': 20}
        urgency_score = urgency_scores.get(reorder_info['urgency'], 0)

        sales_score = min(sales_pattern['total_sold_90_days'] / 10, 50)  # Max 50 points for sales volume

        trend_scores = {'increasing': 20, 'stable': 10, 'decreasing': 0}
        trend_score = trend_scores.get(sales_pattern['trend'], 10)

        return urgency_score + sales_score + trend_score

    def _should_order_today(self, supplier_name: str, target_date: datetime) -> bool:
        """Determine if we should place an order with this supplier today"""
        if supplier_name not in self.supplier_patterns:
            return False

        pattern = self.supplier_patterns[supplier_name]
        last_order = pattern['last_order_date']
        days_since_last = (target_date - last_order).days

        avg_frequency = pattern['avg_days_between_orders']

        # Should order if it's been longer than average frequency
        return days_since_last >= avg_frequency

    def _find_products_for_supplier(self, supplier_name: str, top_products: List[Tuple], assigned_products: set = None) -> List[Dict]:
        """Find products that could be supplied by a specific supplier based on category logic"""
        recommendations = []
        if assigned_products is None:
            assigned_products = set()

        # Category-based supplier matching with more specific categories
        supplier_categories = {
            'Meiji': ['milk', 'dairy', 'fresh', 'meiji'],
            'Gardenia': ['bread', 'bakery', 'gardenia'],
            'SunShine': ['beverages', 'drinks', 'water', 'sunshine'],
            'Helios': ['beer', 'alcohol', 'beverage', 'anchor', 'carlsberg', 'heineken', 'corona'],
            'Trans Orients': ['snacks', 'food', 'noodles', 'instant', 'ramen', 'biscuit'],
            'Mini Group': ['general', 'miscellaneous', 'food', 'snacks'],
            'F&N Foods Pte Ltd': ['beverages', 'drinks', 'soda', 'cola', 'coke'],
            'TRENDY EGG DISTRIBUTOR': ['eggs', 'fresh', 'trendy'],
            'MalaysiaDairy': ['milk', 'dairy', 'malaysia'],
            'Lotus Vegetables': ['vegetables', 'fresh', 'tomato', 'onion', 'carrot', 'potato'],
            'KEAN ANN': ['general', 'food', 'snacks'],
            'Camel nuts': ['nuts', 'snacks'],
            'Dasoon': ['general', 'food'],
            'Rompin Enterprise': ['general', 'food'],
            'JT Intl Tobacco': ['cigarette', 'tobacco', 'marlboro', 'kent', 'salem'],  # Tobacco specific
            'Philip Morris': ['cigarette', 'tobacco', 'marlboro'],  # Tobacco specific
            'Babas': ['spices', 'curry', 'cooking', 'indian']  # Indian products
        }

        supplier_keywords = supplier_categories.get(supplier_name, ['general'])

        # Look for products that match supplier categories
        for product_name, pattern in top_products[:30]:  # Check top 30 products
            # Skip if product already assigned
            if product_name in assigned_products:
                continue

            product_lower = product_name.lower()

            # Check if product matches supplier category
            matches_category = any(keyword.lower() in product_lower for keyword in supplier_keywords)

            # Be more generous with 'general' suppliers - assign any high-demand products
            # But not for specialized suppliers like tobacco companies
            is_specialized = supplier_name in ['JT Intl Tobacco', 'Philip Morris', 'TRENDY EGG DISTRIBUTOR']

            if matches_category or ('general' in supplier_keywords and not is_specialized and pattern['avg_daily_sales'] > 2.0):
                predicted_demand = self.predict_demand(product_name, 7)

                if predicted_demand > 0.5:  # Lower threshold for inclusion
                    # Determine urgency based on demand level
                    if predicted_demand > 5:
                        urgency = 'high'
                    elif predicted_demand > 2:
                        urgency = 'medium'
                    else:
                        urgency = 'low'

                    recommendation = {
                        'product_name': product_name,
                        'supplier_product_name': f"Category Match - {product_name}",
                        'supplier_name': supplier_name,
                        'recommended_quantity': max(round(predicted_demand * 2), 3),  # 2x demand with minimum 3
                        'current_stock': 0,
                        'predicted_demand': float(round(predicted_demand, 1)),
                        'urgency': urgency,
                        'days_of_stock': 0,
                        'supplier_frequency': self.supplier_patterns[supplier_name]['delivery_frequency'],
                        'order_priority': 70 if matches_category else 60  # Higher priority for exact category matches
                    }
                    recommendations.append(recommendation)

                    # Limit to 4-6 products per supplier
                    if len(recommendations) >= 6:
                        break

        return recommendations

    def generate_14_day_schedule(self, start_date: datetime = None) -> Dict:
        """Generate a 14-day order recommendation schedule"""
        if start_date is None:
            start_date = datetime.now()

        schedule = {}

        for day in range(14):
            current_date = start_date + timedelta(days=day)
            day_recommendations = self.generate_daily_recommendations(current_date)

            # Filter to only suppliers that should order on this day
            daily_orders = [rec for rec in day_recommendations if rec['should_order_today']]

            schedule[current_date.strftime('%Y-%m-%d')] = {
                'date': current_date.strftime('%Y-%m-%d'),
                'day_name': current_date.strftime('%A'),
                'recommendations': daily_orders,
                'total_suppliers': len(daily_orders),
                'critical_items': sum(1 for rec in daily_orders for p in rec['products'] if p['urgency'] == 'critical'),
                'high_priority_items': sum(1 for rec in daily_orders for p in rec['products'] if p['urgency'] == 'high')
            }

        return schedule

def test_recommendation_engine():
    """Test the recommendation engine"""
    engine = OrderRecommendationEngine()

    print("=== ORDER RECOMMENDATION ENGINE TEST ===")
    print(f"Sales patterns loaded: {len(engine.sales_patterns)}")
    print(f"Supplier patterns loaded: {len(engine.supplier_patterns)}")
    print(f"Inventory items loaded: {len(engine.inventory_status)}")

    # Test daily recommendations
    today = datetime.now()
    recommendations = engine.generate_daily_recommendations(today)

    print(f"\n=== TODAY'S RECOMMENDATIONS ===")
    for rec in recommendations[:3]:  # Show top 3 suppliers
        print(f"\nSupplier: {rec['supplier_name']}")
        print(f"Should order today: {rec['should_order_today']}")
        print(f"Products to order: {rec['total_products']}")
        for product in rec['products'][:3]:  # Show top 3 products
            print(f"  - {product['product_name']}: {product['recommended_quantity']} units ({product['urgency']} priority)")

if __name__ == "__main__":
    test_recommendation_engine()