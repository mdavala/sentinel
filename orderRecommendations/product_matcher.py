#!/usr/bin/env python3
"""
product_matcher.py - Product name matching system for order recommendations
Handles mapping between POS product names, supplier invoice names, and sales data
"""

import pandas as pd
import sqlite3
import os
from difflib import SequenceMatcher
from fuzzywuzzy import fuzz, process
import re
from typing import Dict, List, Tuple, Optional

class ProductMatcher:
    """
    Handles product name matching across different data sources
    """

    def __init__(self):
        self.pos_to_supplier_map = {}
        self.supplier_to_pos_map = {}
        self.product_patterns = {}
        self._load_product_mappings()

    def _load_product_mappings(self):
        """Load and create product mappings from database and transaction data"""
        try:
            # Load data from database
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(script_dir, 'dailydelights.db')
            conn = sqlite3.connect(db_file)

            # Get sales products (POS names)
            sales_df = pd.read_sql_query("""
                SELECT DISTINCT product_name, category, barcode
                FROM sales_info
            """, conn)

            # Get invoice products (supplier names)
            invoice_df = pd.read_sql_query("""
                SELECT DISTINCT item_name, supplier_name, barcode
                FROM invoice_table
            """, conn)

            conn.close()

            # Load transaction data for additional POS names
            trans_file = os.path.join(script_dir, 'dd_transactionDetails', 'master_transaction_details.xlsx')
            trans_df = pd.read_excel(trans_file)
            pos_products = set(trans_df['Transaction Item'].dropna().unique())

            # Create manual mappings for common products
            self._create_manual_mappings()

            # Auto-match similar product names
            self._auto_match_products(pos_products, invoice_df)

        except Exception as e:
            print(f"Error loading product mappings: {e}")
            # Create some basic manual mappings as fallback
            self._create_manual_mappings()

    def _create_manual_mappings(self):
        """Create manual mappings for known product matches"""
        manual_mappings = {
            # Common drinks
            'MEIJI FRESH MILK 2LTR': ['MEIJI FRESH MILK 2L', 'MEIJI 2L', '2L FRESH'],
            'MEIJI FRESH MILK 830ML': ['MEIJI FRESH MILK 1L', 'MEIJI 1L'],
            'Coke 320ml': ['COCA COLA 320ML', 'COKE CAN 320ML'],
            'Coke 1.5L': ['COCA COLA 1.5L', 'COKE BOTTLE 1.5L'],
            'Coke Zero 320ml': ['COCA COLA ZERO 320ML'],
            'DASANI WATER 600ML': ['DASANI WATER 600ML', 'WATER 600ML'],

            # Beer products
            'ANCHOR STRONG BEER 490ML': ['ANCHOR BEER 490ML', 'ANCHOR STRONG'],
            'CARLSBERG DANISH PILSNER UK 500ML': ['CARLSBERG 500ML', 'CARLSBERG BEER'],
            'HEINEKEN BEER 490ML': ['HEINEKEN 490ML', 'HEINEKEN BEER'],
            'Corona Extra Pint 355ml': ['CORONA BEER 330ML', 'CORONA EXTRA'],

            # Bread and dairy
            'GARDENIA WHITE BREAD 400G': ['GARDENIA BREAD 400G', 'WHITE BREAD 400G'],
            'GARDENIA WHITE BREAD 600G': ['GARDENIA BREAD 600G', 'WHITE BREAD 600G'],
            'TRENDY PREMIUM FRESH EGGS 10s': ['FRESH EGGS 10S', 'EGGS 10PCS'],

            # Vegetables and fresh items
            'Tomato': ['TOMATOES', 'FRESH TOMATO'],
            'Red Onion': ['ONIONS', 'RED ONIONS'],

            # Cigarettes
            'MARLBORO BLACK MENTHOL': ['MARLBORO BLACK', 'MARLBORO MENTHOL'],
            'LD Blue Longs': ['LD BLUE', 'LD CIGARETTES']
        }

        for pos_name, supplier_names in manual_mappings.items():
            self.pos_to_supplier_map[pos_name] = supplier_names
            for supplier_name in supplier_names:
                if supplier_name not in self.supplier_to_pos_map:
                    self.supplier_to_pos_map[supplier_name] = []
                self.supplier_to_pos_map[supplier_name].append(pos_name)

    def _auto_match_products(self, pos_products: set, invoice_df: pd.DataFrame):
        """Automatically match similar product names using fuzzy matching"""
        invoice_products = set(invoice_df['item_name'].dropna().unique())

        for pos_product in pos_products:
            if pos_product in self.pos_to_supplier_map:
                continue  # Skip if already manually mapped

            # Find best matches using fuzzy matching
            matches = process.extract(pos_product, invoice_products, limit=3, scorer=fuzz.token_sort_ratio)

            good_matches = []
            for match, score in matches:
                if score >= 70:  # 70% similarity threshold
                    good_matches.append(match)

            if good_matches:
                self.pos_to_supplier_map[pos_product] = good_matches
                for match in good_matches:
                    if match not in self.supplier_to_pos_map:
                        self.supplier_to_pos_map[match] = []
                    self.supplier_to_pos_map[match].append(pos_product)

    def find_supplier_for_product(self, pos_product_name: str) -> Optional[List[str]]:
        """Find potential supplier product names for a POS product name"""
        if pos_product_name in self.pos_to_supplier_map:
            return self.pos_to_supplier_map[pos_product_name]

        # Try fuzzy matching if no direct match
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(script_dir, 'dailydelights.db')
            conn = sqlite3.connect(db_file)
            invoice_df = pd.read_sql_query("SELECT DISTINCT item_name FROM invoice_table", conn)
            conn.close()

            invoice_products = invoice_df['item_name'].dropna().tolist()
            matches = process.extract(pos_product_name, invoice_products, limit=2, scorer=fuzz.token_sort_ratio)

            good_matches = [match[0] for match in matches if match[1] >= 60]
            return good_matches if good_matches else None

        except Exception:
            return None

    def find_pos_for_supplier_product(self, supplier_product_name: str) -> Optional[List[str]]:
        """Find POS product names for a supplier product name"""
        if supplier_product_name in self.supplier_to_pos_map:
            return self.supplier_to_pos_map[supplier_product_name]
        return None

    def get_supplier_from_invoice(self, product_name: str) -> Optional[str]:
        """Get supplier name for a product from invoice data"""
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(script_dir, 'dailydelights.db')
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT supplier_name FROM invoice_table
                WHERE item_name = ?
                ORDER BY id DESC LIMIT 1
            """, (product_name,))

            result = cursor.fetchone()
            conn.close()

            return result[0] if result else None

        except Exception:
            return None

    def similarity_score(self, str1: str, str2: str) -> float:
        """Calculate similarity score between two strings"""
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def normalize_product_name(self, name: str) -> str:
        """Normalize product name for better matching"""
        # Remove extra spaces, convert to uppercase
        name = re.sub(r'\s+', ' ', name.strip().upper())

        # Remove common suffixes that don't affect matching
        suffixes_to_remove = ['PTE LTD', 'LTD', 'PCS', 'PC', 'PACK']
        for suffix in suffixes_to_remove:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()

        return name

    def get_mapping_stats(self) -> Dict:
        """Get statistics about current mappings"""
        return {
            'pos_to_supplier_mappings': len(self.pos_to_supplier_map),
            'supplier_to_pos_mappings': len(self.supplier_to_pos_map),
            'total_pos_products': len(self.pos_to_supplier_map),
            'sample_mappings': dict(list(self.pos_to_supplier_map.items())[:5])
        }

def test_product_matcher():
    """Test the product matcher functionality"""
    matcher = ProductMatcher()

    print("=== PRODUCT MATCHER TEST ===")
    print(f"Mapping stats: {matcher.get_mapping_stats()}")

    # Test some product lookups
    test_products = [
        'MEIJI FRESH MILK 2LTR',
        'ANCHOR STRONG BEER 490ML',
        'Coke 320ml',
        'GARDENIA WHITE BREAD 400G'
    ]

    print("\nProduct mapping tests:")
    for product in test_products:
        supplier_matches = matcher.find_supplier_for_product(product)
        print(f"{product} -> {supplier_matches}")

if __name__ == "__main__":
    test_product_matcher()