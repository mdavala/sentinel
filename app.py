from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from functools import wraps
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
    aha_credit_amount = db.Column(db.Float, nullable=True)
    nets_amount = db.Column(db.Float, nullable=True)
    total_settlement = db.Column(db.Float, nullable=True)
    expected_cash_balance = db.Column(db.Float, nullable=True)
    cash_outs = db.Column(db.Text, nullable=True)
    total_credit_given = db.Column(db.Float, nullable=True)
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
        daily_book_data = get_direct_data('daily_book_closing_table')
        payments_data = get_direct_data('payments_table')
        invoice_data = get_direct_data('invoice_table')
        
        daily_book_count = len(daily_book_data)
        payments_count = len(payments_data)
        invoice_count = len(invoice_data)
        
        latest_daily_book = daily_book_data[0] if daily_book_data else None
        latest_payment = payments_data[0] if payments_data else None
        latest_invoice = invoice_data[0] if invoice_data else None
        
        template_data = {
            'daily_book_count': daily_book_count,
            'payments_count': payments_count,
            'invoice_count': invoice_count,
            'latest_daily_book': latest_daily_book,
            'latest_payment': latest_payment,
            'latest_invoice': latest_invoice
        }
        
        return render_template('dashboard.html', **template_data)
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('dashboard.html', 
                             daily_book_count=0,
                             payments_count=0,
                             invoice_count=0,
                             latest_daily_book=None,
                             latest_payment=None,
                             latest_invoice=None)

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
                           'cash_amount', 'aha_credit_amount', 'nets_amount', 'total_settlement', 
                           'expected_cash_balance', 'total_credit_given', 'voided_amount']:
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
                           'cash_amount', 'aha_credit_amount', 'nets_amount', 'total_settlement', 
                           'expected_cash_balance', 'total_credit_given', 'voided_amount']:
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

# API endpoints (existing code)
@app.route('/api/daily-book-closing')
@login_required
def api_daily_book_closing():
    try:
        data = get_direct_data('daily_book_closing_table')
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
    app.run(debug=True, host='0.0.0.0', port=5001)