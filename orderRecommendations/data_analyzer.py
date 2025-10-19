#!/usr/bin/env python3
"""
data_analyzer.py - Analyze data sources for order recommendation engine
"""

import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def analyze_transaction_data():
    """Analyze master transaction data for sales patterns"""
    print('\n1. MASTER TRANSACTION DATA ANALYSIS:')
    try:
        df_trans = pd.read_excel('../dd_transactionDetails/master_transaction_details.xlsx')
        df_trans['Date'] = pd.to_datetime(df_trans['Date'])

        # Recent 3 months data for current patterns
        recent_date = df_trans['Date'].max()
        three_months_ago = recent_date - timedelta(days=90)
        recent_data = df_trans[df_trans['Date'] >= three_months_ago]

        print(f'Total transactions: {len(df_trans)}')
        print(f'Recent 3 months: {len(recent_data)} transactions')
        print(f'Date range: {df_trans["Date"].min()} to {df_trans["Date"].max()}')

        # Top selling products in recent 3 months
        recent_products = recent_data.groupby('Transaction Item')['Transaction Item Quantity'].sum().sort_values(ascending=False)
        print(f'\nTop 10 products (last 3 months):')
        for i, (product, qty) in enumerate(recent_products.head(10).items(), 1):
            print(f'  {i:2d}. {product}: {qty} units')

        # Daily sales pattern
        daily_sales = recent_data.groupby(recent_data['Date'].dt.date)['Transaction Item Quantity'].sum()
        avg_daily_sales = daily_sales.mean()
        print(f'\nAverage daily sales: {avg_daily_sales:.1f} items')

        return {
            'total_transactions': len(df_trans),
            'recent_transactions': len(recent_data),
            'top_products': recent_products.head(20).to_dict(),
            'avg_daily_sales': avg_daily_sales,
            'date_range': (df_trans['Date'].min(), df_trans['Date'].max())
        }

    except Exception as e:
        print(f'Error analyzing transaction data: {e}')
        return None

def analyze_supplier_data():
    """Analyze supplier order patterns"""
    print('\n2. SUPPLIER ORDER DATA ANALYSIS:')
    try:
        df_supplier = pd.read_csv('../zohoForms/supplier_orders_zf.csv')
        df_supplier['Date'] = pd.to_datetime(df_supplier['Date'], format='%d-%b-%Y')

        # Filter reliable data (Dec 2024 to June 2025)
        reliable_start = pd.to_datetime('2024-12-01')
        reliable_end = pd.to_datetime('2025-06-30')
        reliable_data = df_supplier[(df_supplier['Date'] >= reliable_start) & (df_supplier['Date'] <= reliable_end)]

        print(f'Total supplier orders: {len(df_supplier)}')
        print(f'Reliable period orders (Dec 2024 - Jun 2025): {len(reliable_data)}')

        # Supplier frequency analysis
        supplier_analysis = reliable_data.groupby('Suppliers').agg({
            'Date': 'count',
            'Currency (SGD)': ['sum', 'mean']
        }).round(2)

        supplier_analysis.columns = ['Order_Count', 'Total_Amount', 'Avg_Amount']
        supplier_analysis = supplier_analysis.sort_values('Order_Count', ascending=False)

        print(f'\nTop 10 suppliers by order frequency:')
        for i, (supplier, data) in enumerate(supplier_analysis.head(10).iterrows(), 1):
            print(f'  {i:2d}. {supplier}: {data["Order_Count"]} orders, Avg: ${data["Avg_Amount"]:.2f}')

        # Calculate delivery frequency for each supplier
        supplier_frequency = {}
        for supplier in reliable_data['Suppliers'].unique():
            supplier_orders = reliable_data[reliable_data['Suppliers'] == supplier]['Date'].sort_values()
            if len(supplier_orders) > 1:
                # Calculate average days between orders
                date_diffs = supplier_orders.diff().dropna()
                avg_days_between = date_diffs.dt.days.mean()
                supplier_frequency[supplier] = avg_days_between

        print(f'\nSupplier delivery frequency (days between orders):')
        for supplier, days in sorted(supplier_frequency.items(), key=lambda x: x[1])[:10]:
            print(f'  {supplier}: Every {days:.1f} days')

        return {
            'supplier_analysis': supplier_analysis.to_dict('index'),
            'delivery_frequency': supplier_frequency,
            'reliable_period_count': len(reliable_data)
        }

    except Exception as e:
        print(f'Error analyzing supplier data: {e}')
        return None

def analyze_database_data():
    """Analyze database tables"""
    print('\n3. DATABASE ANALYSIS:')
    try:
        conn = sqlite3.connect('../dailydelights.db')

        # Check tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f'Available tables: {[t[0] for t in tables]}')

        # Invoice table analysis
        cursor.execute('SELECT COUNT(*) FROM invoice_table')
        invoice_count = cursor.fetchone()[0]
        print(f'Invoice records: {invoice_count}')

        # Sales info analysis
        cursor.execute('SELECT COUNT(*) FROM sales_info')
        sales_count = cursor.fetchone()[0]
        print(f'Sales records: {sales_count}')

        # Recent sales analysis
        cursor.execute('''
            SELECT item_name, SUM(quantity) as total_qty
            FROM sales_info
            WHERE date >= date('now', '-30 days')
            GROUP BY item_name
            ORDER BY total_qty DESC
            LIMIT 10
        ''')
        recent_sales = cursor.fetchall()
        print(f'\nTop 10 items sold (last 30 days):')
        for i, (item, qty) in enumerate(recent_sales, 1):
            print(f'  {i:2d}. {item}: {qty} units')

        # Get sample product names for mapping
        cursor.execute('SELECT DISTINCT item_name FROM sales_info LIMIT 20')
        sales_products = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT item_name FROM invoice_table LIMIT 20')
        invoice_products = [row[0] for row in cursor.fetchall()]

        conn.close()

        return {
            'invoice_count': invoice_count,
            'sales_count': sales_count,
            'recent_sales': dict(recent_sales),
            'sales_products_sample': sales_products,
            'invoice_products_sample': invoice_products
        }

    except Exception as e:
        print(f'Error analyzing database: {e}')
        return None

def main():
    """Main analysis function"""
    print('=== ORDER RECOMMENDATION DATA ANALYSIS ===')

    results = {
        'transaction_analysis': analyze_transaction_data(),
        'supplier_analysis': analyze_supplier_data(),
        'database_analysis': analyze_database_data()
    }

    print('\n=== SUMMARY FOR ORDER RECOMMENDATION ENGINE ===')

    if results['transaction_analysis']:
        print(f"✓ Transaction data: {results['transaction_analysis']['total_transactions']} records available")

    if results['supplier_analysis']:
        print(f"✓ Supplier data: {results['supplier_analysis']['reliable_period_count']} reliable orders")

    if results['database_analysis']:
        print(f"✓ Database: {results['database_analysis']['sales_count']} sales records")

    return results

if __name__ == "__main__":
    main()