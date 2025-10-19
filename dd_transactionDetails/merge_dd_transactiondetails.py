#!/usr/bin/env python3
"""
merge_dd_transactiondetails.py - Merge Daily Delights Transaction Details Excel Files
Merges all transaction details xlsx files from Sep 2024 to Sep 2025 into a single master file
for order recommendation system analysis.
"""

import pandas as pd
import os
from datetime import datetime
from typing import List
import glob

def parse_month_year_from_filename(filename: str) -> tuple:
    """
    Extract month and year from filename for sorting purposes

    Args:
        filename: Filename like "Transaction Details (Daily Delights) Sep2025.xlsx"

    Returns:
        Tuple of (year, month_num) for sorting
    """
    try:
        # Extract month and year from filename
        parts = filename.replace("Transaction Details (Daily Delights) ", "").replace(".xlsx", "")

        month_year_mapping = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
        }

        month_str = parts[:3]
        year_str = parts[3:]

        year = int(year_str)
        month = month_year_mapping.get(month_str, 0)

        return (year, month)
    except Exception as e:
        print(f"Warning: Could not parse month/year from '{filename}': {e}")
        return (1900, 1)

def clean_and_standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize column names and data types

    Args:
        df: Raw dataframe from excel file

    Returns:
        Cleaned dataframe with proper column names
    """
    # Use the first row as column headers if it contains header names
    if len(df) > 0 and df.iloc[0, 0] == 'Date':
        # First row contains headers
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)

    # Clean column names - remove extra spaces and standardize
    df.columns = df.columns.astype(str).str.strip()

    # Convert date column to datetime
    if 'Date' in df.columns:
        try:
            df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        except:
            try:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            except:
                print("Warning: Could not parse dates properly")

    # Convert numeric columns
    numeric_columns = [
        'Transaction Total Amount',
        'Transaction Level Percentage Discount',
        'Transaction Level Dollar Discount',
        'Transaction Item Quantity',
        'Transaction Item Discount',
        'Amount Before Subsidy $',
        'Total Subsidy $',
        'Transaction Item Final Amount ($)'
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def merge_transaction_details():
    """
    Merge all transaction details xlsx files into a single master file
    Sorted chronologically from oldest to newest for pattern analysis
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Find all Transaction Details xlsx files
    xlsx_pattern = os.path.join(script_dir, "Transaction Details (Daily Delights)*.xlsx")
    xlsx_files = glob.glob(xlsx_pattern)

    if not xlsx_files:
        print("No Transaction Details xlsx files found!")
        return

    # Sort files by month/year for chronological processing
    xlsx_files_sorted = sorted(xlsx_files, key=lambda x: parse_month_year_from_filename(os.path.basename(x)))

    print(f"Found {len(xlsx_files_sorted)} xlsx files to merge:")
    for file in xlsx_files_sorted:
        print(f"  - {os.path.basename(file)}")

    # List to store all dataframes
    all_dataframes = []
    total_records = 0

    # Read each xlsx file
    for file_path in xlsx_files_sorted:
        try:
            print(f"\nProcessing {os.path.basename(file_path)}...")

            # Read the xlsx file
            df = pd.read_excel(file_path, header=1)  # Start from row 1, row 0 has headers

            # Clean and standardize the dataframe
            df = clean_and_standardize_columns(df)

            print(f"  Records found: {len(df)}")

            # Add source file column for tracking
            df['Source_File'] = os.path.basename(file_path)

            # Filter out rows where essential data is missing
            df_filtered = df.dropna(subset=['Date', 'Transaction Item'], how='any')
            print(f"  Records after filtering: {len(df_filtered)}")

            if len(df_filtered) > 0:
                all_dataframes.append(df_filtered)
                total_records += len(df_filtered)

        except Exception as e:
            print(f"  Error reading {file_path}: {e}")
            continue

    if not all_dataframes:
        print("No valid xlsx data found!")
        return

    # Combine all dataframes
    print(f"\nCombining {len(all_dataframes)} dataframes...")
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"Total records before deduplication: {len(combined_df)}")

    # Remove duplicates based on key transaction identifiers
    key_columns = ['Date', 'Receipt No.', 'Transaction Item', 'Transaction Item Quantity']
    available_key_columns = [col for col in key_columns if col in combined_df.columns]

    if available_key_columns:
        print("Removing duplicates based on key transaction identifiers...")
        before_dedup = len(combined_df)
        combined_df = combined_df.drop_duplicates(subset=available_key_columns, keep='first')
        after_dedup = len(combined_df)
        print(f"Records after deduplication: {after_dedup}")
        print(f"Duplicates removed: {before_dedup - after_dedup}")

    # Sort by date chronologically (oldest to newest for pattern analysis)
    print("Sorting by date (oldest to newest)...")
    combined_df_sorted = combined_df.sort_values('Date', ascending=True)

    # Remove the temporary source file column for final output
    final_df = combined_df_sorted.drop(['Source_File'], axis=1)

    # Save the merged xlsx file
    output_file = os.path.join(script_dir, "master_transaction_details.xlsx")
    final_df.to_excel(output_file, index=False)

    # Summary
    print(f"\n✅ Successfully merged transaction details!")
    print(f"📁 Output file: {output_file}")
    print(f"📊 Total records: {len(final_df)}")

    # Show date range
    if len(final_df) > 0 and 'Date' in final_df.columns:
        valid_dates = final_df['Date'].dropna()
        if len(valid_dates) > 0:
            oldest_date = valid_dates.min().strftime('%d/%m/%Y %H:%M')
            latest_date = valid_dates.max().strftime('%d/%m/%Y %H:%M')
            print(f"📅 Date range: {oldest_date} to {latest_date}")

    # Show transaction statistics
    if 'Transaction Total Amount' in final_df.columns:
        total_sales = final_df['Transaction Total Amount'].sum()
        avg_transaction = final_df['Transaction Total Amount'].mean()
        print(f"💰 Total sales: ${total_sales:,.2f}")
        print(f"💰 Average transaction: ${avg_transaction:.2f}")

    # Show top products
    if 'Transaction Item' in final_df.columns:
        print(f"\n📋 Top 10 products by transaction frequency:")
        product_counts = final_df['Transaction Item'].value_counts()
        for i, (product, count) in enumerate(product_counts.head(10).items(), 1):
            print(f"  {i:2d}. {product}: {count} transactions")

    # Show payment method breakdown
    if 'Transaction Payment Method' in final_df.columns:
        print(f"\n💳 Payment method breakdown:")
        payment_counts = final_df['Transaction Payment Method'].value_counts()
        for method, count in payment_counts.head(10).items():
            percentage = (count / len(final_df)) * 100
            print(f"  - {method}: {count} transactions ({percentage:.1f}%)")

    return output_file

def main():
    """Main function"""
    print("🚀 Daily Delights Transaction Details Merger")
    print("=" * 60)
    print("📝 Purpose: Create master transaction file for order recommendation system")
    print("=" * 60)

    try:
        output_file = merge_transaction_details()
        if output_file:
            print(f"\n🎉 Merge completed successfully!")
            print(f"📁 Master file ready for order recommendation analysis: master_transaction_details.xlsx")
            print(f"\n💡 This file contains 1 year of transaction data for building order recommendations")
        else:
            print("\n❌ Merge failed!")

    except Exception as e:
        print(f"\n❌ Error during merge: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()