#!/usr/bin/env python3
"""
merge_zoho_csv.py - Merge Zoho Forms CSV Files
Merges all zoho_forms1-7.csv files into a single supplier_orders_zf.csv
Sorted by date from latest to oldest
"""

import pandas as pd
import os
from datetime import datetime
from typing import List
import glob

def parse_date(date_str: str) -> datetime:
    """
    Parse date string in DD-MMM-YYYY format to datetime object

    Args:
        date_str: Date string in format like "20-Aug-2025"

    Returns:
        datetime object
    """
    try:
        return datetime.strptime(date_str, "%d-%b-%Y")
    except ValueError:
        # Fallback for any unexpected date formats
        try:
            return datetime.strptime(date_str, "%d-%m-%Y")
        except ValueError:
            print(f"Warning: Could not parse date '{date_str}', using default date")
            return datetime(1900, 1, 1)

def merge_zoho_csv_files():
    """
    Merge all zoho_forms1-7.csv files into supplier_orders_zf.csv
    Sorted by date from latest to oldest
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Find all zoho_forms CSV files
    csv_pattern = os.path.join(script_dir, "zoho_forms*.csv")
    csv_files = sorted(glob.glob(csv_pattern))

    if not csv_files:
        print("No zoho_forms CSV files found!")
        return

    print(f"Found {len(csv_files)} CSV files to merge:")
    for file in csv_files:
        print(f"  - {os.path.basename(file)}")

    # List to store all dataframes
    all_dataframes = []
    total_records = 0

    # Read each CSV file
    for file_path in csv_files:
        try:
            print(f"\nProcessing {os.path.basename(file_path)}...")

            # Read the CSV file
            df = pd.read_csv(file_path)
            print(f"  Records found: {len(df)}")

            # Add source file column for tracking
            df['Source_File'] = os.path.basename(file_path)

            all_dataframes.append(df)
            total_records += len(df)

        except Exception as e:
            print(f"  Error reading {file_path}: {e}")
            continue

    if not all_dataframes:
        print("No valid CSV data found!")
        return

    # Combine all dataframes
    print(f"\nCombining {len(all_dataframes)} dataframes...")
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"Total records before deduplication: {len(combined_df)}")

    # Convert Date column to datetime for sorting
    print("Converting dates for sorting...")
    combined_df['Date_Parsed'] = combined_df['Date'].apply(parse_date)

    # Sort by date from latest to oldest
    print("Sorting by date (latest to oldest)...")
    combined_df_sorted = combined_df.sort_values('Date_Parsed', ascending=False)

    # Remove duplicates based on all columns except Source_File and Date_Parsed
    columns_for_dedup = [col for col in combined_df_sorted.columns
                        if col not in ['Source_File', 'Date_Parsed']]

    print("Removing duplicates...")
    before_dedup = len(combined_df_sorted)
    combined_df_sorted = combined_df_sorted.drop_duplicates(subset=columns_for_dedup, keep='first')
    after_dedup = len(combined_df_sorted)

    print(f"Records after deduplication: {after_dedup}")
    print(f"Duplicates removed: {before_dedup - after_dedup}")

    # Drop the temporary columns
    final_df = combined_df_sorted.drop(['Source_File', 'Date_Parsed'], axis=1)

    # Save the merged and sorted CSV
    output_file = os.path.join(script_dir, "supplier_orders_zf.csv")
    final_df.to_csv(output_file, index=False)

    # Summary
    print(f"\n✅ Successfully merged CSV files!")
    print(f"📁 Output file: {output_file}")
    print(f"📊 Total records: {len(final_df)}")

    # Show date range
    if len(final_df) > 0:
        latest_date = final_df.iloc[0]['Date']
        oldest_date = final_df.iloc[-1]['Date']
        print(f"📅 Date range: {oldest_date} to {latest_date}")

        # Show breakdown by supplier
        print(f"\n📋 Records by supplier:")
        supplier_counts = final_df['Suppliers'].value_counts()
        for supplier, count in supplier_counts.head(10).items():
            print(f"  - {supplier}: {count} records")

        if len(supplier_counts) > 10:
            print(f"  ... and {len(supplier_counts) - 10} more suppliers")

    return output_file

def main():
    """Main function"""
    print("🚀 Zoho Forms CSV Merger")
    print("=" * 50)

    try:
        output_file = merge_zoho_csv_files()
        if output_file:
            print(f"\n🎉 Merge completed successfully!")
            print(f"📁 Check the output file: supplier_orders_zf.csv")
        else:
            print("\n❌ Merge failed!")

    except Exception as e:
        print(f"\n❌ Error during merge: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()