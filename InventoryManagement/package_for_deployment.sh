#!/bin/bash
# Package DailyDelights Flask App for AWS EC2 Deployment
# This script creates a tar.gz file with all necessary files for Docker deployment

echo "📦 Packaging DailyDelights Flask App for deployment..."

# Remove old tar file if exists
rm -f dailydelights-app.tar.gz

# Create tar.gz with all necessary files, excluding unnecessary directories
tar -czf dailydelights-app.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='venv' \
  --exclude='.dd' \
  --exclude='Product_Inventory_Backup_Original' \
  --exclude='logs/*.log' \
  --exclude='*.pid' \
  --exclude='dd_transactionDetails' \
  --exclude='Invoices' \
  --exclude='product_inventory' \
  --exclude='Suppliers Contact' \
  --exclude='zohoForms' \
  --exclude='docs' \
  --exclude='daily_book_closing_images' \
  --exclude='dailydelights-app.tar.gz' \
  .

if [ -f dailydelights-app.tar.gz ]; then
    SIZE=$(ls -lh dailydelights-app.tar.gz | awk '{print $5}')
    echo "✅ Package created successfully: dailydelights-app.tar.gz ($SIZE)"
    echo ""
    echo "📋 What's included:"
    echo "   ✓ app.py (Flask application)"
    echo "   ✓ templates/ (HTML files)"
    echo "   ✓ static/ (CSS, JS, images)"
    echo "   ✓ dailydelights.db (SQLite database)"
    echo "   ✓ Dockerfile & docker-compose.yml"
    echo "   ✓ requirements.txt"
    echo "   ✓ .env (environment variables)"
    echo "   ✓ credentials*.json (Google Drive credentials)"
    echo "   ✓ token*.json (OAuth tokens)"
    echo "   ✓ All Python scripts (.py files)"
    echo ""
    echo "📤 Next step: Transfer to EC2"
    echo "   scp -i your-key.pem dailydelights-app.tar.gz ubuntu@YOUR-EC2-IP:~/"
else
    echo "❌ Failed to create package"
    exit 1
fi
