#!/usr/bin/env python3

import sqlite3
from datetime import datetime

def create_cash_denomination_table():
    """Create the cash denomination table in the database"""

    try:
        conn = sqlite3.connect('dailydelights.db')
        cursor = conn.cursor()

        # Create cash denomination table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cash_denomination_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date DATE NOT NULL,
                entry_time TIME NOT NULL,

                -- Currency denominations and their quantities
                dollar_100_qty INTEGER DEFAULT 0,
                dollar_50_qty INTEGER DEFAULT 0,
                dollar_10_qty INTEGER DEFAULT 0,
                dollar_5_qty INTEGER DEFAULT 0,
                dollar_2_qty INTEGER DEFAULT 0,
                dollar_1_qty INTEGER DEFAULT 0,

                -- Coin denominations
                cent_50_qty INTEGER DEFAULT 0,
                cent_20_qty INTEGER DEFAULT 0,
                cent_10_qty INTEGER DEFAULT 0,
                cent_5_qty INTEGER DEFAULT 0,

                -- Calculated totals
                dollar_100_total DECIMAL(10,2) DEFAULT 0.00,
                dollar_50_total DECIMAL(10,2) DEFAULT 0.00,
                dollar_10_total DECIMAL(10,2) DEFAULT 0.00,
                dollar_5_total DECIMAL(10,2) DEFAULT 0.00,
                dollar_2_total DECIMAL(10,2) DEFAULT 0.00,
                dollar_1_total DECIMAL(10,2) DEFAULT 0.00,
                cent_50_total DECIMAL(10,2) DEFAULT 0.00,
                cent_20_total DECIMAL(10,2) DEFAULT 0.00,
                cent_10_total DECIMAL(10,2) DEFAULT 0.00,
                cent_5_total DECIMAL(10,2) DEFAULT 0.00,

                -- Grand total
                grand_total DECIMAL(10,2) DEFAULT 0.00,

                -- Metadata
                telegram_user_id TEXT,
                telegram_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Unique constraint to prevent duplicate entries per day
                UNIQUE(entry_date)
            )
        ''')

        # Create index for faster date queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cash_denomination_date
            ON cash_denomination_table(entry_date)
        ''')

        # Create index for faster user queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cash_denomination_user
            ON cash_denomination_table(telegram_user_id)
        ''')

        conn.commit()
        print("✅ Cash denomination table created successfully!")

        # Display table structure
        cursor.execute("PRAGMA table_info(cash_denomination_table)")
        columns = cursor.fetchall()

        print("\n📋 Table Structure:")
        print("-" * 60)
        for col in columns:
            print(f"  {col[1]:20} {col[2]:15} {'NOT NULL' if col[3] else 'NULL'}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error creating cash denomination table: {e}")

if __name__ == "__main__":
    create_cash_denomination_table()