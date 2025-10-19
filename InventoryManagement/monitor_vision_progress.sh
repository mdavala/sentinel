#!/bin/bash
# Monitor Vision OCR processing progress

DB_PATH="/Users/mdavala/Desktop/MacbookPro2023Backup/Personal/Projects/Artificial_Intelligence/Pallava/AgenticAI Operations/DailyDelights/InventoryManagement/dailydelights.db"

echo "=================================="
echo "VISION OCR PROCESSING MONITOR"
echo "=================================="
echo ""

# Count total items in orders_table
TOTAL_ITEMS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM orders_table;")
echo "✅ Total items extracted: $TOTAL_ITEMS"

# Count unique invoices
UNIQUE_INVOICES=$(sqlite3 "$DB_PATH" "SELECT COUNT(DISTINCT invoice_number) FROM orders_table;")
echo "📄 Unique invoices processed: $UNIQUE_INVOICES"

# Count unique suppliers
UNIQUE_SUPPLIERS=$(sqlite3 "$DB_PATH" "SELECT COUNT(DISTINCT supplier_name) FROM orders_table;")
echo "🏢 Unique suppliers: $UNIQUE_SUPPLIERS"

# Count processed images
PROCESSED_IMAGES=$(sqlite3 "$DB_PATH" "SELECT COUNT(DISTINCT image_filename) FROM orders_table;")
echo "🖼️  Images processed: $PROCESSED_IMAGES / 81"

# Calculate progress percentage
PROGRESS=$((PROCESSED_IMAGES * 100 / 81))
echo "📊 Progress: $PROGRESS%"

echo ""
echo "Latest 5 invoices:"
echo "----------------------------------"
sqlite3 "$DB_PATH" "SELECT invoice_number || ' | ' || supplier_name || ' | ' || invoice_date || ' | $' || COALESCE(total_amount_per_item, 0) FROM orders_table ORDER BY id DESC LIMIT 5;"

echo ""
echo "----------------------------------"
echo "To view full log: tail -f vision_processing.log"
echo "To re-run this monitor: ./monitor_vision_progress.sh"
