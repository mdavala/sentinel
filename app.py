from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from functools import wraps
from collections import defaultdict
import sqlite3
import os
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Use absolute path for database
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dailydelights.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models - Make sure table names match exactly
class DailyBookClosingTable(db.Model):
    __tablename__ = "daily_book_closing_table"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    closing_date = db.Column(db.String, nullable=False)
    total_sales = db.Column(db.Float, nullable=True)
    number_of_transactions = db.Column(db.Integer, nullable=True)
    average_sales_per_transaction = db.Column(db.Float, nullable=True)
    nets_qr_amount = db.Column(db.Float, nullable=True)
    cash_amount = db.Column(db.Float, nullable=True)
    credit_amount = db.Column(db.Float, nullable=True)
    nets_amount = db.Column(db.Float, nullable=True)
    total_settlement = db.Column(db.Float, nullable=True)
    expected_cash_balance = db.Column(db.Float, nullable=True)
    cash_outs = db.Column(db.Text, nullable=True)
    voided_transactions = db.Column(db.Integer, nullable=True)
    voided_amount = db.Column(db.Float, nullable=True)
    processed_at = db.Column(db.String, nullable=True)

    def to_dict(self):
        result = {}
        for c in self.__table__.columns:
            value = getattr(self, c.name)
            result[c.name] = value
        return result

class PaymentsTable(db.Model):
    __tablename__ = "payments_table"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    invoice_number = db.Column(db.String)
    supplies_received_date = db.Column(db.String, nullable=True)
    supplier_name = db.Column(db.String)
    total_amount = db.Column(db.Float)
    payment_status = db.Column(db.String)
    payment_due_date = db.Column(db.String, nullable=True)
    payment_type = db.Column(db.String, nullable=True)
    reference_num = db.Column(db.String, nullable=True)
    payment_validity = db.Column(db.String, nullable=True)

    def to_dict(self):
        result = {}
        for c in self.__table__.columns:
            value = getattr(self, c.name)
            result[c.name] = value
        return result

class InvoiceTable(db.Model):
    __tablename__ = "invoice_table"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    invoice_number = db.Column(db.String)
    supplier_name = db.Column(db.String)
    item_name = db.Column(db.String)
    quantity = db.Column(db.Integer)
    total_amount = db.Column(db.Float)
    invoice_date = db.Column(db.String, nullable=True)
    unit_price = db.Column(db.Float, nullable=True)
    carton_or_loose = db.Column(db.String, nullable=True)
    items_per_carton = db.Column(db.Integer, nullable=True)
    unit_price_item = db.Column(db.Float, nullable=True)
    amount_per_item = db.Column(db.Float, nullable=True)
    gst_amount = db.Column(db.Float, nullable=True)
    total_amount_per_item = db.Column(db.Float, nullable=True)
    barcode = db.Column(db.String, nullable=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# Inventory model removed - to be implemented later

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Direct database functions using SQLite
def get_direct_data(table_name):
    """Get data directly from SQLite database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        data = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                row_dict[columns[i]] = value
            data.append(row_dict)
        
        return data
    except Exception as e:
        print(f"Direct database error for {table_name}: {e}")
        return []

def execute_direct_query(query, params=None):
    """Execute direct SQL query"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        result = cursor.rowcount
        conn.close()
        return result
    except Exception as e:
        print(f"Direct query error: {e}")
        return False

def get_record_by_id(table_name, record_id):
    """Get single record by ID"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()

        if row:
            row_dict = {}
            for i, value in enumerate(row):
                row_dict[columns[i]] = value
            return row_dict
        return None
    except Exception as e:
        print(f"Error getting record by ID: {e}")
        return None

def calculate_analytics():
    """Calculate comprehensive analytics from all database tables"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        analytics = {
            'summary': {},
            'counts': {},
            'daily_sales': [],
            'monthly_revenue': [],
            'payment_methods': {},
            'top_suppliers': [],
            'top_items': [],
            'unpaid_invoices': [],
            'payment_status': []
        }

        # Basic counts
        cursor.execute("SELECT COUNT(*) FROM daily_book_closing_table")
        analytics['counts']['daily_book_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM payments_table")
        analytics['counts']['payments_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT invoice_number) FROM invoice_table")
        analytics['counts']['invoice_count'] = cursor.fetchone()[0]

        # Total revenue from daily book closing
        cursor.execute("SELECT SUM(total_sales) FROM daily_book_closing_table WHERE total_sales IS NOT NULL")
        result = cursor.fetchone()[0]
        analytics['summary']['total_revenue'] = result if result else 0.0

        # Outstanding payments (pending)
        cursor.execute("SELECT SUM(total_amount) FROM payments_table WHERE payment_status = 'pending'")
        result = cursor.fetchone()[0]
        analytics['summary']['total_outstanding'] = result if result else 0.0

        # Daily sales data (last 30 days)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT closing_date, total_sales
            FROM daily_book_closing_table
            WHERE closing_date >= ? AND total_sales IS NOT NULL
            ORDER BY closing_date DESC LIMIT 30
        """, (thirty_days_ago,))

        for row in cursor.fetchall():
            analytics['daily_sales'].append({
                'date': row[0],
                'sales': row[1] if row[1] else 0
            })

        # Monthly revenue
        cursor.execute("""
            SELECT strftime('%Y', closing_date) as year,
                   strftime('%m', closing_date) as month,
                   SUM(total_sales) as revenue
            FROM daily_book_closing_table
            WHERE total_sales IS NOT NULL
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT 12
        """)

        for row in cursor.fetchall():
            analytics['monthly_revenue'].append({
                'year': int(row[0]),
                'month': int(row[1]),
                'revenue': row[2] if row[2] else 0
            })

        # Payment methods distribution
        cursor.execute("""
            SELECT SUM(cash_amount), SUM(credit_amount), SUM(nets_amount), SUM(nets_qr_amount)
            FROM daily_book_closing_table
        """)

        payment_totals = cursor.fetchone()
        analytics['payment_methods'] = {
            'cash': payment_totals[0] if payment_totals[0] else 0,
            'credit': payment_totals[1] if payment_totals[1] else 0,
            'nets': payment_totals[2] if payment_totals[2] else 0,
            'nets_qr': payment_totals[3] if payment_totals[3] else 0
        }

        # Top suppliers by total amount (one entry per invoice)
        cursor.execute("""
            SELECT supplier_name,
                   SUM(total_amount) as total,
                   COUNT(DISTINCT invoice_number) as invoice_count
            FROM (
                SELECT DISTINCT invoice_number, supplier_name, total_amount
                FROM invoice_table
                WHERE supplier_name IS NOT NULL
            ) unique_invoices
            GROUP BY supplier_name
            ORDER BY total DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            analytics['top_suppliers'].append({
                'name': row[0],
                'amount': row[1] if row[1] else 0,
                'count': row[2]
            })

        # Top items by quantity (sum actual quantities and their amounts)
        cursor.execute("""
            SELECT item_name,
                   SUM(quantity) as total_qty,
                   SUM(COALESCE(total_amount_per_item, amount_per_item, 0)) as total_value
            FROM invoice_table
            WHERE item_name IS NOT NULL
            GROUP BY item_name
            ORDER BY total_qty DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            analytics['top_items'].append({
                'name': row[0],
                'quantity': row[1] if row[1] else 0,
                'amount': row[2] if row[2] else 0
            })

        # Pending invoices (unpaid)
        cursor.execute("""
            SELECT invoice_number, supplier_name, total_amount, payment_due_date
            FROM payments_table
            WHERE payment_status = 'pending'
            ORDER BY payment_due_date ASC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            analytics['unpaid_invoices'].append({
                'invoice_number': row[0],
                'supplier_name': row[1] if row[1] else 'Unknown',
                'amount': row[2] if row[2] else 0,
                'due_date': row[3] if row[3] else 'N/A'
            })

        # Payment status distribution
        cursor.execute("""
            SELECT payment_status, COUNT(*) as count, SUM(total_amount) as amount
            FROM payments_table
            GROUP BY payment_status
        """)

        for row in cursor.fetchall():
            analytics['payment_status'].append({
                'status': row[0] if row[0] else 'unknown',
                'count': row[1],
                'amount': row[2] if row[2] else 0
            })

        conn.close()
        return analytics

    except Exception as e:
        print(f"Analytics calculation error: {e}")
        return {
            'summary': {'total_revenue': 0, 'total_outstanding': 0},
            'counts': {'daily_book_count': 0, 'payments_count': 0, 'invoice_count': 0},
            'daily_sales': [],
            'monthly_revenue': [],
            'payment_methods': {'cash': 0, 'credit': 0, 'nets': 0, 'nets_qr': 0},
            'top_suppliers': [],
            'top_items': [],
            'unpaid_invoices': [],
            'payment_status': []
        }

# Routes
@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'dailydelights' and password == '1P@llava':
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        analytics = calculate_analytics()
        return render_template('dashboard.html', analytics=analytics)

    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')

        # Return empty analytics structure on error
        empty_analytics = {
            'summary': {'total_revenue': 0, 'total_outstanding': 0},
            'counts': {'daily_book_count': 0, 'payments_count': 0, 'invoice_count': 0},
            'daily_sales': [],
            'monthly_revenue': [],
            'payment_methods': {'cash': 0, 'credit': 0, 'nets': 0, 'nets_qr': 0},
            'top_suppliers': [],
            'top_items': [],
            'unpaid_invoices': [],
            'payment_status': []
        }
        return render_template('dashboard.html', analytics=empty_analytics)

@app.route('/daily-book-closing')
@login_required
def daily_book_closing():
    return render_template('daily_book_closing.html')

@app.route('/payments')
@login_required
def payments():
    return render_template('payments.html')

@app.route('/invoices')
@login_required
def invoices():
    return render_template('invoices.html')

# Inventory route removed - to be implemented later

# ==========================================
# Order Recommendations Routes
# ==========================================

@app.route('/order-recommendations')
@login_required
def order_recommendations():
    """Display order recommendations dashboard"""
    return render_template('order_recommendations.html')

@app.route('/api/order-recommendations')
@login_required
def api_order_recommendations():
    """Get all order recommendations with optional filters"""
    try:
        supplier_filter = request.args.get('supplier', 'all')
        status_filter = request.args.get('status', 'all')

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                id,
                supplier_name,
                recommended_date,
                total_amount_sgd,
                status,
                items_json,
                notes,
                created_at,
                ordered_at,
                delivered_at
            FROM order_recommendations
            WHERE 1=1
        """

        params = []

        if supplier_filter != 'all':
            query += " AND supplier_name = ?"
            params.append(supplier_filter)

        if status_filter != 'all':
            query += " AND status = ?"
            params.append(status_filter)

        query += " ORDER BY recommended_date DESC, created_at DESC"

        cursor.execute(query, params)

        recommendations = []
        for row in cursor.fetchall():
            items = json.loads(row[5]) if row[5] else []
            recommendations.append({
                'id': row[0],
                'supplier_name': row[1],
                'recommended_date': row[2],
                'total_amount_sgd': row[3],
                'status': row[4],
                'items': items,
                'items_count': len(items),
                'notes': row[6],
                'created_at': row[7],
                'ordered_at': row[8],
                'delivered_at': row[9]
            })

        conn.close()
        return jsonify({'success': True, 'recommendations': recommendations})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/order-recommendations/suppliers')
@login_required
def api_order_recommendations_suppliers():
    """Get list of all suppliers for filter dropdown"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT supplier_name
            FROM order_recommendations
            ORDER BY supplier_name
        """)

        suppliers = [row[0] for row in cursor.fetchall()]
        conn.close()

        return jsonify({'success': True, 'suppliers': suppliers})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/order-recommendations/<int:rec_id>/status', methods=['POST'])
@login_required
def api_update_recommendation_status(rec_id):
    """Update status of an order recommendation"""
    try:
        data = request.get_json()
        new_status = data.get('status')

        if not new_status or new_status not in ['pending', 'ordered', 'delivered']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Update status and timestamps
        update_query = "UPDATE order_recommendations SET status = ?, updated_at = CURRENT_TIMESTAMP"
        params = [new_status]

        if new_status == 'ordered':
            update_query += ", ordered_at = CURRENT_TIMESTAMP"
        elif new_status == 'delivered':
            update_query += ", delivered_at = CURRENT_TIMESTAMP"

        update_query += " WHERE id = ?"
        params.append(rec_id)

        cursor.execute(update_query, params)

        # If status is delivered, update supplier_order_patterns
        if new_status == 'delivered':
            cursor.execute("SELECT supplier_name FROM order_recommendations WHERE id = ?", (rec_id,))
            result = cursor.fetchone()
            if result:
                supplier_name = result[0]
                cursor.execute("""
                    UPDATE supplier_order_patterns
                    SET last_order_date = DATE('now'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE supplier_name = ?
                """, (supplier_name,))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Status updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/order-recommendations/<int:rec_id>', methods=['PUT'])
@login_required
def api_update_recommendation(rec_id):
    """Update an order recommendation (edit items and quantities)"""
    try:
        data = request.get_json()
        items = data.get('items', [])

        # Recalculate total
        total_amount = sum(item.get('subtotal', 0) for item in items)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE order_recommendations
            SET items_json = ?,
                total_amount_sgd = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (json.dumps(items), round(total_amount, 2), rec_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Recommendation updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/order-recommendations/<int:rec_id>', methods=['DELETE'])
@login_required
def api_delete_recommendation(rec_id):
    """Delete an order recommendation"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM order_recommendations WHERE id = ?", (rec_id,))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Recommendation deleted successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/order-recommendations/generate', methods=['POST'])
@login_required
def api_generate_recommendations():
    """Generate new order recommendations on demand for a specific month"""
    try:
        data = request.get_json() or {}
        target_month = data.get('target_month')  # Format: 'YYYY-MM'

        from order_recommendation_engine import OrderRecommendationEngine

        engine = OrderRecommendationEngine(db_path)
        recommendations = engine.run(target_month=target_month, clear_existing=True)

        # Group by week for summary
        from collections import defaultdict
        by_week = defaultdict(list)
        for rec in recommendations:
            by_week[rec['recommended_date']].append(rec)

        weeks_summary = []
        for week_date in sorted(by_week.keys()):
            week_recs = by_week[week_date]
            weeks_summary.append({
                'week_label': week_recs[0]['week_label'] if week_recs else '',
                'orders_count': len(week_recs),
                'total_value': sum(r['total_amount_sgd'] for r in week_recs)
            })

        return jsonify({
            'success': True,
            'message': f'Generated {len(recommendations)} recommendations for {len(weeks_summary)} weeks',
            'count': len(recommendations),
            'weeks': weeks_summary
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# Price Changes Routes
# ==========================================

@app.route('/price-changes')
@login_required
def price_changes():
    """Display price changes page - items with >10% price hikes"""
    return render_template('price_changes.html')

@app.route('/api/price-changes')
@login_required
def api_price_changes():
    """Get all detected price changes"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get filters
        reviewed = request.args.get('reviewed')  # 'true', 'false', or None for all

        query = "SELECT * FROM price_changes WHERE 1=1"
        params = []

        if reviewed == 'true':
            query += " AND reviewed = 1"
        elif reviewed == 'false':
            query += " AND reviewed = 0"

        query += " ORDER BY percentage_hike DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        price_changes_list = []
        for row in rows:
            price_changes_list.append({
                'id': row['id'],
                'item_name': row['item_name'],
                'supplier': row['supplier'],
                'inventory_price': row['inventory_price'],
                'invoice_price': row['invoice_price'],
                'price_difference': row['price_difference'],
                'percentage_hike': row['percentage_hike'],
                'detected_at': row['detected_at'],
                'reviewed': bool(row['reviewed'])
            })

        conn.close()

        return jsonify({
            'success': True,
            'price_changes': price_changes_list,
            'count': len(price_changes_list)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/price-changes/<int:change_id>/review', methods=['POST'])
@login_required
def api_mark_price_change_reviewed(change_id):
    """Mark a price change as reviewed"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE price_changes
            SET reviewed = 1
            WHERE id = ?
        """, (change_id,))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Marked as reviewed'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/price-changes/<int:change_id>', methods=['DELETE'])
@login_required
def api_delete_price_change(change_id):
    """Delete a price change record"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM price_changes WHERE id = ?", (change_id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Deleted successfully'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/price-changes/refresh', methods=['POST'])
@login_required
def api_refresh_price_changes():
    """Refresh price changes by comparing invoice_table with product_inventory_table"""
    try:
        from refresh_price_changes import PriceChangeDetector

        detector = PriceChangeDetector(db_path)
        count = detector.refresh()

        return jsonify({
            'success': True,
            'message': f'Price changes refreshed successfully',
            'price_changes_detected': count
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# Cash Management Routes
# ==========================================

@app.route('/cash-management')
@login_required
def cash_management():
    """Display cash management page"""
    today = date.today().strftime('%Y-%m-%d')
    selected_date = request.args.get('date', today)
    return render_template('cash_management.html',
                         selected_date=selected_date,
                         today=today)

@app.route('/api/cash-denomination')
@login_required
def api_cash_denomination():
    """Get cash denomination data for a specific date or date range"""
    try:
        selected_date = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if start_date and end_date:
            # Date range query
            cursor.execute("""
                SELECT * FROM cash_denomination_table
                WHERE entry_date BETWEEN ? AND ?
                ORDER BY entry_date DESC
            """, (start_date, end_date))

            rows = cursor.fetchall()

            if rows:
                columns = [desc[0] for desc in cursor.description]
                data = [dict(zip(columns, row)) for row in rows]

                # Calculate totals for the date range
                total_grand_total = sum(row.get('grand_total', 0) or 0 for row in data)
                total_bills = sum((row.get('dollar_100_total', 0) or 0) +
                                (row.get('dollar_50_total', 0) or 0) +
                                (row.get('dollar_10_total', 0) or 0) +
                                (row.get('dollar_5_total', 0) or 0) +
                                (row.get('dollar_2_total', 0) or 0) for row in data)
                total_coins = sum((row.get('dollar_1_total', 0) or 0) +
                                (row.get('cent_50_total', 0) or 0) +
                                (row.get('cent_20_total', 0) or 0) +
                                (row.get('cent_10_total', 0) or 0) +
                                (row.get('cent_5_total', 0) or 0) for row in data)

                conn.close()
                return jsonify({
                    'success': True,
                    'data': data,
                    'is_range': True,
                    'summary': {
                        'total_amount': total_grand_total,
                        'bills_total': total_bills,
                        'coins_total': total_coins,
                        'total_entries': len(data),
                        'start_date': start_date,
                        'end_date': end_date
                    }
                })
            else:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'No cash denomination data found for date range {start_date} to {end_date}'
                })

        else:
            # Single date query (default to today if no date provided)
            if not selected_date:
                selected_date = date.today().strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT * FROM cash_denomination_table
                WHERE entry_date = ?
            """, (selected_date,))

            row = cursor.fetchone()

            if row:
                # Convert row to dictionary
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                conn.close()

                return jsonify({
                    'success': True,
                    'data': data,
                    'is_range': False
                })
            else:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'No cash denomination data found for {selected_date}'
                })

    except Exception as e:
        print(f"Error fetching cash denomination data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Cash Management Delete Routes
@app.route('/api/cash-denomination/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_cash_denomination(record_id):
    """Delete a cash denomination entry"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if record exists first
        cursor.execute('SELECT * FROM cash_denomination_table WHERE id = ?', (record_id,))
        record = cursor.fetchone()

        if not record:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Cash denomination record not found'
            }), 404

        # Delete the record
        cursor.execute('DELETE FROM cash_denomination_table WHERE id = ?', (record_id,))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Cash denomination record for {record[1]} deleted successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cash-denomination/save', methods=['POST'])
@login_required
def api_save_cash_denomination():
    """Save or update cash denomination data"""
    try:
        data = request.get_json()

        # Extract data from request
        entry_date = data.get('entry_date')
        entry_time = data.get('entry_time', datetime.now().strftime('%H:%M:%S'))

        # Get quantities
        dollar_100_qty = int(data.get('dollar_100_qty', 0))
        dollar_50_qty = int(data.get('dollar_50_qty', 0))
        dollar_10_qty = int(data.get('dollar_10_qty', 0))
        dollar_5_qty = int(data.get('dollar_5_qty', 0))
        dollar_2_qty = int(data.get('dollar_2_qty', 0))
        dollar_1_qty = int(data.get('dollar_1_qty', 0))
        cent_50_qty = int(data.get('cent_50_qty', 0))
        cent_20_qty = int(data.get('cent_20_qty', 0))
        cent_10_qty = int(data.get('cent_10_qty', 0))
        cent_5_qty = int(data.get('cent_5_qty', 0))

        # Calculate totals
        dollar_100_total = dollar_100_qty * 100.0
        dollar_50_total = dollar_50_qty * 50.0
        dollar_10_total = dollar_10_qty * 10.0
        dollar_5_total = dollar_5_qty * 5.0
        dollar_2_total = dollar_2_qty * 2.0
        dollar_1_total = dollar_1_qty * 1.0
        cent_50_total = cent_50_qty * 0.50
        cent_20_total = cent_20_qty * 0.20
        cent_10_total = cent_10_qty * 0.10
        cent_5_total = cent_5_qty * 0.05

        grand_total = (dollar_100_total + dollar_50_total + dollar_10_total +
                      dollar_5_total + dollar_2_total + dollar_1_total +
                      cent_50_total + cent_20_total + cent_10_total + cent_5_total)

        # Get current user info
        telegram_username = session.get('username', 'web_user')
        telegram_user_id = session.get('user_id', 'web')

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if entry exists for this date
        cursor.execute("SELECT id FROM cash_denomination_table WHERE entry_date = ?", (entry_date,))
        existing = cursor.fetchone()

        if existing:
            # Update existing entry
            cursor.execute("""
                UPDATE cash_denomination_table
                SET entry_time = ?,
                    dollar_100_qty = ?, dollar_50_qty = ?, dollar_10_qty = ?, dollar_5_qty = ?, dollar_2_qty = ?,
                    dollar_1_qty = ?, cent_50_qty = ?, cent_20_qty = ?, cent_10_qty = ?, cent_5_qty = ?,
                    dollar_100_total = ?, dollar_50_total = ?, dollar_10_total = ?, dollar_5_total = ?, dollar_2_total = ?,
                    dollar_1_total = ?, cent_50_total = ?, cent_20_total = ?, cent_10_total = ?, cent_5_total = ?,
                    grand_total = ?,
                    telegram_username = ?, telegram_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE entry_date = ?
            """, (entry_time,
                  dollar_100_qty, dollar_50_qty, dollar_10_qty, dollar_5_qty, dollar_2_qty,
                  dollar_1_qty, cent_50_qty, cent_20_qty, cent_10_qty, cent_5_qty,
                  dollar_100_total, dollar_50_total, dollar_10_total, dollar_5_total, dollar_2_total,
                  dollar_1_total, cent_50_total, cent_20_total, cent_10_total, cent_5_total,
                  grand_total,
                  telegram_username, telegram_user_id,
                  entry_date))
        else:
            # Insert new entry
            cursor.execute("""
                INSERT INTO cash_denomination_table (
                    entry_date, entry_time,
                    dollar_100_qty, dollar_50_qty, dollar_10_qty, dollar_5_qty, dollar_2_qty,
                    dollar_1_qty, cent_50_qty, cent_20_qty, cent_10_qty, cent_5_qty,
                    dollar_100_total, dollar_50_total, dollar_10_total, dollar_5_total, dollar_2_total,
                    dollar_1_total, cent_50_total, cent_20_total, cent_10_total, cent_5_total,
                    grand_total,
                    telegram_username, telegram_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry_date, entry_time,
                  dollar_100_qty, dollar_50_qty, dollar_10_qty, dollar_5_qty, dollar_2_qty,
                  dollar_1_qty, cent_50_qty, cent_20_qty, cent_10_qty, cent_5_qty,
                  dollar_100_total, dollar_50_total, dollar_10_total, dollar_5_total, dollar_2_total,
                  dollar_1_total, cent_50_total, cent_20_total, cent_10_total, cent_5_total,
                  grand_total,
                  telegram_username, telegram_user_id))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Cash denomination saved successfully',
            'grand_total': round(grand_total, 2)
        })

    except Exception as e:
        print(f"Error saving cash denomination: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bulk-delete/cash-denomination', methods=['POST'])
@login_required
def bulk_delete_cash_denomination():
    """Bulk delete cash denomination entries"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])

        if not ids:
            return jsonify({'success': False, 'error': 'No record IDs provided'}), 400

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Build the SQL for bulk delete
        placeholders = ','.join(['?' for _ in ids])
        query = f'DELETE FROM cash_denomination_table WHERE id IN ({placeholders})'

        cursor.execute(query, ids)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted_count} cash denomination record(s)',
            'deleted_count': deleted_count
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===========================================================================
# ===========================================================================
# ORDER RECOMMENDATIONS - PLACEHOLDER (Logic to be implemented)
# ===========================================================================
# TODO: Implement new order recommendation logic here

# CRUD Routes for Daily Book Closing
@app.route('/daily-book-closing/add', methods=['GET', 'POST'])
@login_required
def add_daily_book_closing():
    if request.method == 'POST':
        try:
            # Get form data
            data = request.form.to_dict()
            
            # Convert empty strings to None and handle numeric fields
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key in ['total_sales', 'average_sales_per_transaction', 'nets_qr_amount',
                           'cash_amount', 'credit_amount', 'nets_amount', 'total_settlement',
                           'expected_cash_balance', 'voided_amount']:
                    processed_data[key] = float(value) if value else None
                elif key in ['number_of_transactions', 'voided_transactions']:
                    processed_data[key] = int(value) if value else None
                else:
                    processed_data[key] = value
            
            # Add processed_at timestamp
            processed_data['processed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            
            # Build INSERT query
            columns = list(processed_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            query = f"INSERT INTO daily_book_closing_table ({', '.join(columns)}) VALUES ({placeholders})"
            
            if execute_direct_query(query, list(processed_data.values())):
                flash('Daily book closing record added successfully!', 'success')
                return redirect(url_for('daily_book_closing'))
            else:
                flash('Error adding record', 'error')
                
        except Exception as e:
            flash(f'Error adding record: {str(e)}', 'error')
    
    return render_template('add_daily_book_closing.html')

@app.route('/daily-book-closing/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_daily_book_closing(record_id):
    record = get_record_by_id('daily_book_closing_table', record_id)
    if not record:
        flash('Record not found', 'error')
        return redirect(url_for('daily_book_closing'))
    
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            # Process data similar to add function
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key in ['total_sales', 'average_sales_per_transaction', 'nets_qr_amount',
                           'cash_amount', 'credit_amount', 'nets_amount', 'total_settlement',
                           'expected_cash_balance', 'voided_amount']:
                    processed_data[key] = float(value) if value else None
                elif key in ['number_of_transactions', 'voided_transactions']:
                    processed_data[key] = int(value) if value else None
                else:
                    processed_data[key] = value
            
            # Build UPDATE query
            set_clause = ', '.join([f"{key} = ?" for key in processed_data.keys()])
            query = f"UPDATE daily_book_closing_table SET {set_clause} WHERE id = ?"
            params = list(processed_data.values()) + [record_id]
            
            if execute_direct_query(query, params):
                flash('Record updated successfully!', 'success')
                return redirect(url_for('daily_book_closing'))
            else:
                flash('Error updating record', 'error')
                
        except Exception as e:
            flash(f'Error updating record: {str(e)}', 'error')
    
    return render_template('edit_daily_book_closing.html', record=record)

@app.route('/daily-book-closing/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_daily_book_closing(record_id):
    try:
        query = "DELETE FROM daily_book_closing_table WHERE id = ?"
        if execute_direct_query(query, (record_id,)):
            flash('Record deleted successfully!', 'success')
        else:
            flash('Error deleting record', 'error')
    except Exception as e:
        flash(f'Error deleting record: {str(e)}', 'error')
    
    return redirect(url_for('daily_book_closing'))

@app.route('/daily-book-closing/update', methods=['POST'])
@login_required
def update_daily_book_closing():
    """Process daily book closing images from Google Drive using dailyBookClosing.py"""
    try:
        import subprocess
        import os

        # Run the dailyBookClosing processing script
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dailyBookClosing.py')
        result = subprocess.run(['python3', script_path],
                              capture_output=True, text=True, timeout=1800)  # 30 minutes timeout

        if result.returncode == 0:
            # Parse output for summary information
            output_lines = result.stdout.strip().split('\n')

            # Look for processing summary
            summary_found = False
            for line in output_lines:
                if 'Successfully Processed:' in line and 'Total Date Groups Found:' in line:
                    summary_found = True
                    break

            if summary_found:
                # Extract key metrics from the output
                total_groups = 0
                success_count = 0

                for line in output_lines:
                    if 'Successfully Processed:' in line:
                        try:
                            success_count = int(line.split(':')[1].strip())
                        except:
                            pass
                    elif 'Total Date Groups Found:' in line:
                        try:
                            total_groups = int(line.split(':')[1].strip())
                        except:
                            pass

                if total_groups > 0:
                    flash(f'Daily book closing update completed! Processed {success_count} out of {total_groups} date groups successfully.', 'success')
                else:
                    flash('Daily book closing update completed! No new images found to process.', 'info')
            else:
                flash('Daily book closing update completed successfully!', 'success')
        else:
            error_msg = result.stderr if result.stderr else "Unknown error occurred"
            flash(f'Daily book closing update failed: {error_msg}', 'error')

    except subprocess.TimeoutExpired:
        flash('Daily book closing update timed out. The process may still be running in the background.', 'warning')
    except Exception as e:
        flash(f'Error updating daily book closing: {str(e)}', 'error')

    return redirect(url_for('daily_book_closing'))

# CRUD Routes for Payments
@app.route('/payments/add', methods=['GET', 'POST'])
@login_required
def add_payment():
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key == 'total_amount':
                    processed_data[key] = float(value) if value else None
                else:
                    processed_data[key] = value
            
            columns = list(processed_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            query = f"INSERT INTO payments_table ({', '.join(columns)}) VALUES ({placeholders})"
            
            if execute_direct_query(query, list(processed_data.values())):
                flash('Payment record added successfully!', 'success')
                return redirect(url_for('payments'))
            else:
                flash('Error adding payment record', 'error')
                
        except Exception as e:
            flash(f'Error adding payment: {str(e)}', 'error')
    
    return render_template('add_payment.html')

@app.route('/payments/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_payment(record_id):
    record = get_record_by_id('payments_table', record_id)
    if not record:
        flash('Payment record not found', 'error')
        return redirect(url_for('payments'))
    
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key == 'total_amount':
                    processed_data[key] = float(value) if value else None
                else:
                    processed_data[key] = value
            
            set_clause = ', '.join([f"{key} = ?" for key in processed_data.keys()])
            query = f"UPDATE payments_table SET {set_clause} WHERE id = ?"
            params = list(processed_data.values()) + [record_id]
            
            if execute_direct_query(query, params):
                flash('Payment updated successfully!', 'success')
                return redirect(url_for('payments'))
            else:
                flash('Error updating payment', 'error')
                
        except Exception as e:
            flash(f'Error updating payment: {str(e)}', 'error')
    
    return render_template('edit_payment.html', record=record)

@app.route('/payments/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_payment(record_id):
    try:
        query = "DELETE FROM payments_table WHERE id = ?"
        if execute_direct_query(query, (record_id,)):
            flash('Payment deleted successfully!', 'success')
        else:
            flash('Error deleting payment', 'error')
    except Exception as e:
        flash(f'Error deleting payment: {str(e)}', 'error')
    
    return redirect(url_for('payments'))

@app.route('/payments/update', methods=['POST'])
@login_required
def update_payments():
    """Process UOB payment emails and update payment statuses"""
    try:
        import subprocess
        import os

        # Run the UOB payment processing script
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uob_payment_emails.py')
        result = subprocess.run(['python3', script_path],
                              capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            # Extract summary from output
            output_lines = result.stdout.strip().split('\n')
            summary_line = [line for line in output_lines if '🎯 Summary:' in line]

            if summary_line:
                summary = summary_line[-1].replace('🎯 Summary: ', '')
                flash(f'Payment update completed! {summary}', 'success')
            else:
                flash('Payment update completed successfully!', 'success')
        else:
            flash(f'Payment update failed: {result.stderr}', 'error')

    except subprocess.TimeoutExpired:
        flash('Payment update timed out. Please try again.', 'error')
    except Exception as e:
        flash(f'Error updating payments: {str(e)}', 'error')

    return redirect(url_for('payments'))

# CRUD Routes for Invoices
@app.route('/invoices/add', methods=['GET', 'POST'])
@login_required
def add_invoice():
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key in ['quantity', 'items_per_carton']:
                    processed_data[key] = int(value) if value else None
                elif key in ['total_amount', 'unit_price', 'unit_price_item', 'amount_per_item', 
                           'gst_amount', 'total_amount_per_item']:
                    processed_data[key] = float(value) if value else None
                else:
                    processed_data[key] = value
            
            columns = list(processed_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            query = f"INSERT INTO invoice_table ({', '.join(columns)}) VALUES ({placeholders})"
            
            if execute_direct_query(query, list(processed_data.values())):
                flash('Invoice record added successfully!', 'success')
                return redirect(url_for('invoices'))
            else:
                flash('Error adding invoice record', 'error')
                
        except Exception as e:
            flash(f'Error adding invoice: {str(e)}', 'error')
    
    return render_template('add_invoice.html')

@app.route('/invoices/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_invoice(record_id):
    record = get_record_by_id('invoice_table', record_id)
    if not record:
        flash('Invoice record not found', 'error')
        return redirect(url_for('invoices'))
    
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            
            processed_data = {}
            for key, value in data.items():
                if value == '':
                    processed_data[key] = None
                elif key in ['quantity', 'items_per_carton']:
                    processed_data[key] = int(value) if value else None
                elif key in ['total_amount', 'unit_price', 'unit_price_item', 'amount_per_item', 
                           'gst_amount', 'total_amount_per_item']:
                    processed_data[key] = float(value) if value else None
                else:
                    processed_data[key] = value
            
            set_clause = ', '.join([f"{key} = ?" for key in processed_data.keys()])
            query = f"UPDATE invoice_table SET {set_clause} WHERE id = ?"
            params = list(processed_data.values()) + [record_id]
            
            if execute_direct_query(query, params):
                flash('Invoice updated successfully!', 'success')
                return redirect(url_for('invoices'))
            else:
                flash('Error updating invoice', 'error')
                
        except Exception as e:
            flash(f'Error updating invoice: {str(e)}', 'error')
    
    return render_template('edit_invoice.html', record=record)

@app.route('/invoices/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_invoice(record_id):
    try:
        query = "DELETE FROM invoice_table WHERE id = ?"
        if execute_direct_query(query, (record_id,)):
            flash('Invoice deleted successfully!', 'success')
        else:
            flash('Error deleting invoice', 'error')
    except Exception as e:
        flash(f'Error deleting invoice: {str(e)}', 'error')
    
    return redirect(url_for('invoices'))

@app.route('/api/upload-invoices', methods=['POST'])
@login_required
def api_upload_invoices():
    """Upload invoice images to Google Drive"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import tempfile
        import time

        SCOPES = ['https://www.googleapis.com/auth/drive']
        INVOICES_FOLDER_ID = "162d4TyRYwvGXdeVYkZTAY6AMpc50sJtf"
        TOKEN_FILE = 'token.json'
        CREDENTIALS_FILE = 'credentials.json'

        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if len(files) == 0:
            return jsonify({'success': False, 'error': 'No files selected'}), 400

        # Authenticate with Google Drive
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    return jsonify({'success': False, 'error': 'Google Drive credentials not found'}), 500
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

        service = build('drive', 'v3', credentials=creds)

        # Upload files
        uploaded_count = 0
        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue

            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            try:
                # Generate filename with timestamp
                timestamp = int(time.time())
                filename = f"invoice_{timestamp}_{uploaded_count + 1}.jpg"

                # Upload to Google Drive
                file_metadata = {
                    'name': filename,
                    'parents': [INVOICES_FOLDER_ID]
                }
                media = MediaFileUpload(temp_file_path, mimetype='image/jpeg', resumable=True)
                uploaded_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name'
                ).execute()

                uploaded_files.append(uploaded_file.get('name'))
                uploaded_count += 1

            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        # After successful upload, automatically trigger processing
        import subprocess
        processing_started = False
        processing_error = None

        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stockSentinel.py')
            # Run in background without waiting for completion
            subprocess.Popen(['python3', script_path],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
            processing_started = True
            print(f"Invoice processing started automatically after upload")
        except Exception as proc_error:
            print(f"Error starting invoice processing: {proc_error}")
            processing_error = str(proc_error)

        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {uploaded_count} file(s)',
            'uploaded_count': uploaded_count,
            'uploaded_files': uploaded_files,
            'processing_started': processing_started,
            'processing_error': processing_error
        })

    except Exception as e:
        print(f"Error uploading invoices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-dailybookclosing', methods=['POST'])
@login_required
def api_upload_dailybookclosing():
    """Upload daily book closing images to Google Drive"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import tempfile
        import time

        SCOPES = ['https://www.googleapis.com/auth/drive']
        DAILY_BOOK_CLOSING_FOLDER_ID = "1sxtFv5mgGSafgWQ3UufW1D2c9f4xE7-Y"
        TOKEN_FILE = 'token.json'
        CREDENTIALS_FILE = 'credentials.json'

        # Check if files were uploaded
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        if len(files) == 0:
            return jsonify({'success': False, 'error': 'No files selected'}), 400

        # Authenticate with Google Drive
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    return jsonify({'success': False, 'error': 'Google Drive credentials not found'}), 500
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

        service = build('drive', 'v3', credentials=creds)

        # Upload files
        uploaded_count = 0
        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue

            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name

            try:
                # Generate filename with timestamp
                timestamp = int(time.time())
                filename = f"dailybook_{timestamp}_{uploaded_count + 1}.jpg"

                # Upload to Google Drive
                file_metadata = {
                    'name': filename,
                    'parents': [DAILY_BOOK_CLOSING_FOLDER_ID]
                }
                media = MediaFileUpload(temp_file_path, mimetype='image/jpeg', resumable=True)
                uploaded_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name'
                ).execute()

                uploaded_files.append(uploaded_file.get('name'))
                uploaded_count += 1

            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        # After successful upload, automatically trigger processing
        import subprocess
        processing_started = False
        processing_error = None

        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dailyBookClosing.py')
            # Run in background without waiting for completion
            subprocess.Popen(['python3', script_path],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
            processing_started = True
            print(f"Daily book closing processing started automatically after upload")
        except Exception as proc_error:
            print(f"Error starting daily book closing processing: {proc_error}")
            processing_error = str(proc_error)

        return jsonify({
            'success': True,
            'message': f'Successfully uploaded {uploaded_count} file(s)',
            'uploaded_count': uploaded_count,
            'uploaded_files': uploaded_files,
            'processing_started': processing_started,
            'processing_error': processing_error
        })

    except Exception as e:
        print(f"Error uploading daily book closing images: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/invoices/update', methods=['POST'])
@login_required
def update_invoices():
    """Process invoice images from Google Drive using stockSentinel.py"""
    try:
        import subprocess
        import os

        # Run the stockSentinel processing script
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stockSentinel.py')
        result = subprocess.run(['python3', script_path],
                              capture_output=True, text=True, timeout=1800)  # 30 minutes timeout

        if result.returncode == 0:
            # Parse output for summary information
            output_lines = result.stdout.strip().split('\n')

            # Look for processing summary
            summary_found = False
            for line in output_lines:
                if 'Successfully Processed:' in line and 'Total Images Found:' in line:
                    # Extract numbers from summary
                    summary_found = True
                    break

            if summary_found:
                # Extract key metrics from the output
                total_processed = 0
                success_count = 0

                for line in output_lines:
                    if '✅ Successfully Processed:' in line:
                        try:
                            success_count = int(line.split(':')[1].strip())
                        except:
                            pass
                    elif '📂 Total Images Found:' in line:
                        try:
                            total_processed = int(line.split(':')[1].strip())
                        except:
                            pass

                if total_processed > 0:
                    flash(f'Invoice update completed! Processed {success_count} out of {total_processed} invoices successfully.', 'success')
                else:
                    flash('Invoice update completed! No new invoices found to process.', 'info')
            else:
                flash('Invoice update completed successfully!', 'success')
        else:
            error_msg = result.stderr if result.stderr else "Unknown error occurred"
            flash(f'Invoice update failed: {error_msg}', 'error')

    except subprocess.TimeoutExpired:
        flash('Invoice update timed out. The process may still be running in the background.', 'warning')
    except Exception as e:
        flash(f'Error updating invoices: {str(e)}', 'error')

    return redirect(url_for('invoices'))

# Inventory CRUD routes removed - to be implemented later

# API endpoints (existing code)
@app.route('/api/daily-book-closing')
@login_required
def api_daily_book_closing():
    try:
        # Get data sorted by closing_date DESC (latest first)
        # Use DATE() function to properly sort text dates in YYYY-MM-DD format
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_book_closing_table ORDER BY DATE(closing_date) DESC, id DESC")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        data = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                row_dict[columns[i]] = value
            data.append(row_dict)

        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payments')
@login_required
def api_payments():
    try:
        data = get_direct_data('payments_table')
        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/invoices')
@login_required
def api_invoices():
    try:
        data = get_direct_data('invoice_table')
        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Inventory API endpoint removed - to be implemented later

# Search endpoints (existing)
@app.route('/api/search/daily-book-closing')
@login_required
def search_daily_book_closing():
    try:
        search_term = request.args.get('q', '').strip().lower()
        data = get_direct_data('daily_book_closing_table')
        
        if search_term:
            filtered_data = []
            for record in data:
                if (search_term in str(record.get('closing_date', '')).lower() or
                    search_term in str(record.get('cash_outs', '')).lower()):
                    filtered_data.append(record)
            data = filtered_data
        
        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search/payments')
@login_required
def search_payments():
    try:
        search_term = request.args.get('q', '').strip().lower()
        data = get_direct_data('payments_table')
        
        if search_term:
            filtered_data = []
            for record in data:
                if (search_term in str(record.get('supplier_name', '')).lower() or
                    search_term in str(record.get('invoice_number', '')).lower() or
                    search_term in str(record.get('payment_status', '')).lower()):
                    filtered_data.append(record)
            data = filtered_data
        
        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search/invoices')
@login_required
def search_invoices():
    try:
        search_term = request.args.get('q', '').strip().lower()
        data = get_direct_data('invoice_table')
        
        if search_term:
            filtered_data = []
            for record in data:
                if (search_term in str(record.get('supplier_name', '')).lower() or
                    search_term in str(record.get('item_name', '')).lower() or
                    search_term in str(record.get('invoice_number', '')).lower()):
                    filtered_data.append(record)
            data = filtered_data
        
        return jsonify({
            'draw': request.args.get('draw', type=int, default=1),
            'recordsTotal': len(data),
            'recordsFiltered': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Analytics API endpoint
@app.route('/api/analytics')
@login_required
def api_analytics():
    try:
        analytics = calculate_analytics()
        return jsonify(analytics)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Inventory search API removed - to be implemented later

# Bulk Delete Routes
@app.route('/api/bulk-delete/invoices', methods=['POST'])
@login_required
def bulk_delete_invoices():
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'success': False, 'error': 'No IDs provided'}), 400

        ids = data['ids']
        if not ids:
            return jsonify({'success': False, 'error': 'Empty ID list'}), 400

        # Create placeholders for SQL IN clause
        placeholders = ', '.join(['?' for _ in ids])
        query = f"DELETE FROM invoice_table WHERE id IN ({placeholders})"

        if execute_direct_query(query, ids):
            return jsonify({'success': True, 'deleted_count': len(ids)})
        else:
            return jsonify({'success': False, 'error': 'Database error'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Bulk delete inventory endpoint removed - to be implemented later

@app.route('/api/bulk-delete/payments', methods=['POST'])
@login_required
def bulk_delete_payments():
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'success': False, 'error': 'No IDs provided'}), 400

        ids = data['ids']
        if not ids:
            return jsonify({'success': False, 'error': 'Empty ID list'}), 400

        # Create placeholders for SQL IN clause
        placeholders = ', '.join(['?' for _ in ids])
        query = f"DELETE FROM payments_table WHERE id IN ({placeholders})"

        if execute_direct_query(query, ids):
            return jsonify({'success': True, 'deleted_count': len(ids)})
        else:
            return jsonify({'success': False, 'error': 'Database error'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bulk-delete/daily-book-closing', methods=['POST'])
@login_required
def bulk_delete_daily_book_closing():
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'success': False, 'error': 'No IDs provided'}), 400

        ids = data['ids']
        if not ids:
            return jsonify({'success': False, 'error': 'Empty ID list'}), 400

        # Create placeholders for SQL IN clause
        placeholders = ', '.join(['?' for _ in ids])
        query = f"DELETE FROM daily_book_closing_table WHERE id IN ({placeholders})"

        if execute_direct_query(query, ids):
            return jsonify({'success': True, 'deleted_count': len(ids)})
        else:
            return jsonify({'success': False, 'error': 'Database error'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Debug routes (existing)
@app.route('/debug-db')
@login_required
def debug_db():
    try:
        result = {}
        result['db_path'] = db_path
        result['db_exists'] = os.path.exists(db_path)
        
        if os.path.exists(db_path):
            result['db_size'] = os.path.getsize(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        result['tables_found'] = [table[0] for table in tables]
        
        for table_name in ['daily_book_closing_table', 'payments_table', 'invoice_table']:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                result[f'{table_name}_count'] = count
                
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                result[f'{table_name}_columns'] = [col[1] for col in columns]
                
                sample_data = get_direct_data(table_name)
                result[f'{table_name}_sample'] = sample_data[:2]
                
            except Exception as e:
                result[f'{table_name}_error'] = str(e)
        
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Database path: {db_path}")
    print(f"Database exists: {os.path.exists(db_path)}")
    app.run(debug=True, host='0.0.0.0', port=5002)