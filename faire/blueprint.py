#!/usr/bin/env python3
"""
Faire blueprint for managing Faire revenue data
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal
from sqlalchemy import func, extract
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os
import re
import configparser
from models import db, FaireData, Brand, Item, Channel, ChannelCustomer, ImportError
from auth.blueprint import login_required, admin_required
import json

faire_bp = Blueprint('faire', __name__, template_folder='templates')

def get_snowflake_config():
    """Get Snowflake configuration from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    
    snowflake_config = config['snowflake']
    return {
        'account': snowflake_config.get('account'),
        'user': snowflake_config.get('user'),
        'private_key_path': os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            snowflake_config.get('private_key_path')
        ),
        'warehouse': snowflake_config.get('warehouse', ''),
        'database': snowflake_config.get('database', 'DWH'),
        'schema': snowflake_config.get('schema', 'NETSUITE')
    }

def get_snowflake_connection():
    """Create Snowflake connection using private key authentication"""
    config = get_snowflake_config()
    
    # Read private key - handle both PEM and PKCS8 formats
    with open(config['private_key_path'], 'rb') as key_file:
        key_data = key_file.read()
        
        # Try to load as PEM first
        try:
            p_key = serialization.load_pem_private_key(
                key_data,
                password=None,
                backend=default_backend()
            )
        except ValueError:
            # If PEM fails, try DER format
            try:
                p_key = serialization.load_der_private_key(
                    key_data,
                    password=None,
                    backend=default_backend()
                )
            except ValueError:
                raise ValueError("Unable to load private key. Ensure it's in PEM or DER format.")
    
    # Convert to DER format for Snowflake connector
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Create connection parameters
    conn_params = {
        'account': config['account'],
        'user': config['user'],
        'private_key': pkb,
        'database': config['database'],
        'schema': config['schema']
    }
    
    # Add warehouse if specified
    if config['warehouse']:
        conn_params['warehouse'] = config['warehouse']
    
    # Create connection
    conn = snowflake.connector.connect(**conn_params)
    
    return conn

@faire_bp.route('/')
@login_required
def index():
    """Faire data list"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = FaireData.query
    
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if item_id:
        query = query.filter_by(item_id=item_id)
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    if date_from:
        query = query.filter(FaireData.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        query = query.filter(FaireData.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    faire_data = query.order_by(FaireData.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get filter options
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    # Get Faire customers (channel_id = 11)
    faire_channel = Channel.query.filter_by(id=11).first()
    customers = []
    if faire_channel:
        customers = ChannelCustomer.query.filter_by(channel_id=11).order_by(ChannelCustomer.name).all()
    
    return render_template('faire/index.html', 
                         faire_data=faire_data,
                         brands=brands,
                         items=items,
                         customers=customers,
                         current_filters={
                             'brand_id': brand_id,
                             'item_id': item_id,
                             'customer_id': customer_id,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@faire_bp.route('/dashboard')
@login_required
def dashboard():
    """Faire dashboard with chart"""
    from models import FaireData, db
    from sqlalchemy import func, extract
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    
    # Get all brands, items, and customers for filters
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.join(Brand).order_by(Brand.name, Item.essor_code).all()
    faire_channel = Channel.query.filter_by(id=11).first()
    customers = []
    if faire_channel:
        customers = ChannelCustomer.query.filter_by(channel_id=11).order_by(ChannelCustomer.name).all()
    
    # Calculate total revenues for 2024 and 2025 with filters applied
    query_2024 = db.session.query(
        func.coalesce(func.sum(FaireData.revenues), 0)
    ).filter(
        extract('year', FaireData.date) == 2024
    )
    
    query_2025 = db.session.query(
        func.coalesce(func.sum(FaireData.revenues), 0)
    ).filter(
        extract('year', FaireData.date) == 2025
    )
    
    # Apply filters
    if brand_id:
        query_2024 = query_2024.filter(FaireData.brand_id == brand_id)
        query_2025 = query_2025.filter(FaireData.brand_id == brand_id)
    if item_id:
        query_2024 = query_2024.filter(FaireData.item_id == item_id)
        query_2025 = query_2025.filter(FaireData.item_id == item_id)
    if customer_id:
        query_2024 = query_2024.filter(FaireData.customer_id == customer_id)
        query_2025 = query_2025.filter(FaireData.customer_id == customer_id)
    
    rev_2024 = query_2024.scalar() or 0
    rev_2025 = query_2025.scalar() or 0
    
    total_rev_2024 = float(rev_2024)
    total_rev_2025 = float(rev_2025)
    
    return render_template('faire/dashboard.html',
                         brands=brands,
                         items=items,
                         customers=customers,
                         total_rev_2024=total_rev_2024,
                         total_rev_2025=total_rev_2025,
                         selected_brand_id=brand_id,
                         selected_item_id=item_id,
                         selected_customer_id=customer_id)

@faire_bp.route('/api/totals')
@login_required
def api_totals():
    """API endpoint to get filtered total revenues"""
    from models import FaireData, db
    from sqlalchemy import func, extract
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    
    # Calculate total revenues for 2024 and 2025 with filters applied
    query_2024 = db.session.query(
        func.coalesce(func.sum(FaireData.revenues), 0)
    ).filter(
        extract('year', FaireData.date) == 2024
    )
    
    query_2025 = db.session.query(
        func.coalesce(func.sum(FaireData.revenues), 0)
    ).filter(
        extract('year', FaireData.date) == 2025
    )
    
    # Apply filters
    if brand_id:
        query_2024 = query_2024.filter(FaireData.brand_id == brand_id)
        query_2025 = query_2025.filter(FaireData.brand_id == brand_id)
    if item_id:
        query_2024 = query_2024.filter(FaireData.item_id == item_id)
        query_2025 = query_2025.filter(FaireData.item_id == item_id)
    if customer_id:
        query_2024 = query_2024.filter(FaireData.customer_id == customer_id)
        query_2025 = query_2025.filter(FaireData.customer_id == customer_id)
    
    rev_2024 = query_2024.scalar() or 0
    rev_2025 = query_2025.scalar() or 0
    
    return jsonify({
        'total_rev_2024': float(rev_2024),
        'total_rev_2025': float(rev_2025)
    })

@faire_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """API endpoint to get chart data based on filters - returns 12 months for 2024 and 2025"""
    try:
        from sqlalchemy import extract
        # Get filter parameters
        metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
        brand_id = request.args.get('brand_id', type=int)
        item_id = request.args.get('item_id', type=int)
        customer_id = request.args.get('customer_id', type=int)
        
        # Get data for all 12 months of 2024 and 2025
        months_2024 = {}
        months_2025 = {}
        
        # Query for 2024
        query_2024 = db.session.query(
            extract('month', FaireData.date).label('month'),
            func.sum(FaireData.units).label('total_units'),
            func.sum(FaireData.revenues).label('total_revenues')
        ).filter(
            extract('year', FaireData.date) == 2024
        )
        
        # Query for 2025
        query_2025 = db.session.query(
            extract('month', FaireData.date).label('month'),
            func.sum(FaireData.units).label('total_units'),
            func.sum(FaireData.revenues).label('total_revenues')
        ).filter(
            extract('year', FaireData.date) == 2025
        )
        
        # Apply filters
        if brand_id:
            query_2024 = query_2024.filter(FaireData.brand_id == brand_id)
            query_2025 = query_2025.filter(FaireData.brand_id == brand_id)
        if item_id:
            query_2024 = query_2024.filter(FaireData.item_id == item_id)
            query_2025 = query_2025.filter(FaireData.item_id == item_id)
        if customer_id:
            query_2024 = query_2024.filter(FaireData.customer_id == customer_id)
            query_2025 = query_2025.filter(FaireData.customer_id == customer_id)
        
        # Group by month
        query_2024 = query_2024.group_by(extract('month', FaireData.date))
        query_2025 = query_2025.group_by(extract('month', FaireData.date))
        
        # Execute queries
        results_2024 = query_2024.all()
        results_2025 = query_2025.all()
        
        # Build month dictionaries
        for result in results_2024:
            month = int(result.month)
            if metric == 'units':
                months_2024[month] = float(result.total_units) if result.total_units else None
            else:
                months_2024[month] = float(result.total_revenues) if result.total_revenues else None
        
        for result in results_2025:
            month = int(result.month)
            if metric == 'units':
                months_2025[month] = float(result.total_units) if result.total_units else None
            else:
                months_2025[month] = float(result.total_revenues) if result.total_revenues else None
        
        # Build arrays for all 12 months
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        values_2024 = []
        values_2025 = []
        
        for month in range(1, 13):
            # Use None for missing data (Chart.js will skip these points)
            values_2024.append(months_2024.get(month))
            values_2025.append(months_2025.get(month))
        
        if metric == 'units':
            metric_label = 'Units'
        else:
            metric_label = 'Revenues ($)'
        
        return jsonify({
            'labels': month_names,
            'values_2024': values_2024,
            'values_2025': values_2025,
            'metric_label': metric_label
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _save_import_error(import_channel, row_data, error_message, row_number=None):
    """Helper function to save import errors to the database"""
    try:
        # Convert row_data to JSON string
        if isinstance(row_data, dict):
            error_data_json = json.dumps(row_data)
        elif isinstance(row_data, (list, tuple)):
            # Convert tuple/list to dict with column names if available
            error_data_json = json.dumps(list(row_data))
        else:
            error_data_json = json.dumps(str(row_data))
        
        import_error = ImportError(
            import_channel=import_channel,
            error_data=error_data_json,
            error_message=error_message,
            row_number=row_number
        )
        db.session.add(import_error)
        # Flush to ensure it's in the session (will be committed with batch)
        db.session.flush()
    except Exception as e:
        # If we can't save the error, at least log it
        print(f"  ⚠ Warning: Could not save import error to database: {str(e)}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")

def _get_last_import_date():
    """Get the latest date from FaireData table"""
    last_record = FaireData.query.order_by(FaireData.date.desc()).first()
    if last_record:
        return last_record.date
    return None

def _load_faire_query():
    """Load the Faire SQL query from faire.sql"""
    query_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'snowflake', 'faire.sql')
    with open(query_path, 'r') as f:
        return f.read()

def _execute_faire_import(import_method='all', dry_run=False):
    """Execute the Faire import with specified parameters
    
    Args:
        import_method: 'all' to import all data, 'incremental' to import since last entry
        dry_run: If True, only process first 10 rows and don't save to database
    
    Returns:
        dict with import results
    """
    max_rows = 10 if dry_run else None
    
    mode_text = "DRY-RUN (first 10 rows only, no database changes)" if dry_run else "LIVE IMPORT"
    print("\n" + "="*60)
    print(f"Starting Snowflake Import Process - {mode_text}")
    print(f"Method: {import_method}")
    print("="*60)
    
    # Connect to Snowflake
    print("\n🔌 Connecting to Snowflake...")
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    print("✓ Connected to Snowflake")
    
    # Get last import date if using incremental method
    last_date = None
    if import_method == 'incremental':
        last_date = _get_last_import_date()
        if last_date:
            print(f"\n📅 Last import date: {last_date}")
            print(f"   Will import data from {last_date} onwards")
        else:
            print(f"\n📅 No previous data found, importing all data")
            import_method = 'all'  # Fallback to import all if no previous data
    
    # Load the query from faire.sql
    base_query = _load_faire_query()
    
    # Replace the date filter in the query
    # The query has: WHERE date >= '2025-01-01'
    # Use regex to match the date pattern more robustly
    # This will match: WHERE date >= 'YYYY-MM-DD' (case insensitive, flexible whitespace)
    date_pattern = re.compile(
        r"WHERE\s+date\s*>=\s*'[0-9]{4}-[0-9]{2}-[0-9]{2}'",
        re.IGNORECASE
    )
    
    if import_method == 'incremental' and last_date:
        # For incremental import, use the last import date
        replacement_date = last_date.strftime('%Y-%m-%d')
        if date_pattern.search(base_query):
            base_query = date_pattern.sub(
                f"WHERE date >= '{replacement_date}'",
                base_query
            )
            print(f"✓ Updated query date filter to: date >= '{replacement_date}' (incremental)")
        else:
            # Fallback to simple string replace if regex doesn't match
            base_query = base_query.replace(
                "WHERE date >= '2025-01-01'",
                f"WHERE date >= '{replacement_date}'"
            )
            print(f"⚠ Using fallback date replacement: date >= '{replacement_date}' (incremental)")
    else:
        # For "all" import, start from 2024-01-01
        replacement_date = '2024-01-01'
        if date_pattern.search(base_query):
            base_query = date_pattern.sub(
                f"WHERE date >= '{replacement_date}'",
                base_query
            )
            print(f"✓ Updated query date filter to: date >= '{replacement_date}' (import all)")
        else:
            # Fallback to simple string replace if regex doesn't match
            base_query = base_query.replace(
                "WHERE date >= '2025-01-01'",
                f"WHERE date >= '{replacement_date}'"
            )
            print(f"⚠ Using fallback date replacement: date >= '{replacement_date}' (import all)")
    
    print("\n📊 Executing query...")
    print(f"Query: {base_query[:200]}...")  # Print first 200 chars of query
    cursor.execute(base_query)
    print("✓ Query executed successfully")
    
    results = {
        'processed': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': []
    }
    
    rows = cursor.fetchall()
    total_rows = len(rows)
    rows_to_process = rows[:max_rows] if max_rows else rows
    
    # Get column names from cursor description
    column_names = [desc[0] for desc in cursor.description]
    
    print(f"\n📊 Total rows to process: {len(rows_to_process)}" + (f" (limited to {max_rows} for dry-run)" if max_rows else ""))
    print("-"*60)
    
    # Load all brands into memory for faster lookup
    print("\n📦 Loading brands into memory...")
    all_brands = {brand.code: brand for brand in Brand.query.all() if brand.code}
    all_brands_by_name = {brand.name: brand for brand in Brand.query.all()}
    print(f"✓ Loaded {len(all_brands)} brands with codes, {len(all_brands_by_name)} total brands")
    
    # Load Faire channel (id=11)
    faire_channel = Channel.query.filter_by(id=11).first()
    if not faire_channel:
        error_msg = "Faire channel (id=11) does not exist. Please create it first."
        print(f"✗ ERROR: {error_msg}")
        results['errors'].append(error_msg)
        cursor.close()
        conn.close()
        return results
    
    try:
        # Process rows in batches of 100
        BATCH_SIZE = 100
        total_batches = (len(rows_to_process) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_num in range(total_batches):
            batch_start = batch_num * BATCH_SIZE
            batch_end = min(batch_start + BATCH_SIZE, len(rows_to_process))
            batch_rows = rows_to_process[batch_start:batch_end]
            
            print(f"\n📦 Processing batch {batch_num + 1}/{total_batches} (rows {batch_start + 1}-{batch_end} of {len(rows_to_process)})...")
            print("-"*60)
        
            # Process each row in the batch
            for row_num_in_batch, row in enumerate(batch_rows, start=1):
                row_num = batch_start + row_num_in_batch
                if row_num_in_batch % 100 == 0 or row_num_in_batch == 1:
                    print(f"Processing row {row_num}/{len(rows_to_process)}...")
                
                try:
                    # Convert row to dict for easier access
                    row_dict = dict(zip(column_names, row))
                    
                    # Parse month (DATE_TRUNC result) - convert to first day of month
                    month = row_dict.get('MONTH')
                    if not month:
                        error_msg = f"Row {row_num}: Missing 'MONTH' field"
                        results['errors'].append(error_msg)
                        _save_import_error('snowflake', row_dict, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    # Handle different date formats from Snowflake
                    if isinstance(month, str):
                        month_str = month.strip()
                        try:
                            month = datetime.strptime(month_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                month = datetime.strptime(month_str.split()[0], '%Y-%m-%d').date()
                            except (ValueError, IndexError):
                                error_msg = f"Row {row_num}: Invalid date format '{month}'"
                                results['errors'].append(error_msg)
                                _save_import_error('snowflake', row_dict, error_msg, row_num)
                                results['skipped'] += 1
                                continue
                    elif isinstance(month, datetime):
                        month = month.date()
                    elif isinstance(month, date_type):
                        pass
                    else:
                        if hasattr(month, 'date'):
                            month = month.date()
                        else:
                            error_msg = f"Row {row_num}: Cannot parse date '{month}' (type: {type(month).__name__})"
                            results['errors'].append(error_msg)
                            _save_import_error('snowflake', row_dict, error_msg, row_num)
                            results['skipped'] += 1
                            continue
                    
                    # Ensure it's the first day of the month
                    date = month.replace(day=1)
                    
                    # Find brand by code
                    brand_code = row_dict.get('BRAND')
                    if not brand_code:
                        error_msg = f"Row {row_num}: Missing 'BRAND' field"
                        results['errors'].append(error_msg)
                        _save_import_error('snowflake', row_dict, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    brand = all_brands.get(brand_code)
                    if not brand:
                        # Try by name
                        brand = all_brands_by_name.get(brand_code)
                        if not brand:
                            error_msg = f"Row {row_num}: Brand '{brand_code}' not found"
                            results['errors'].append(error_msg)
                            _save_import_error('snowflake', row_dict, error_msg, row_num)
                            results['skipped'] += 1
                            continue
                    
                    # Find or create item by netsuite_item_number (matching essor_code)
                    netsuite_item_number = row_dict.get('NETSUITE_ITEM_NUMBER')
                    item_name = row_dict.get('ITEM_NAME', '')
                    
                    item = None
                    if netsuite_item_number:
                        item = Item.query.filter_by(essor_code=netsuite_item_number).first()
                    
                    if not item:
                        # Create new item
                        print(f"  ➕ Creating new item: essor_code={netsuite_item_number}, essor_name={item_name}, brand={brand.name}")
                        item = Item(
                            essor_code=netsuite_item_number,
                            essor_name=item_name,
                            brand_id=brand.id
                        )
                        db.session.add(item)
                        db.session.flush()
                        results['created'] += 1
                    else:
                        print(f"  ✓ Found item: {netsuite_item_number}")
                    
                    # Find or create customer by name (channel_id = 11)
                    faire_customer_name = row_dict.get('FAIRE_CUSTOMER_NAME')
                    customer = None
                    if faire_customer_name:
                        customer = ChannelCustomer.query.filter_by(
                            name=faire_customer_name,
                            channel_id=11
                        ).first()
                    
                    if not customer and faire_customer_name:
                        # Create new customer
                        print(f"  ➕ Creating new customer: name={faire_customer_name}, channel_id=11, brand_id={brand.id}")
                        customer = ChannelCustomer(
                            name=faire_customer_name,
                            channel_id=11,
                            brand_id=brand.id
                        )
                        db.session.add(customer)
                        db.session.flush()
                        results['created'] += 1
                    elif customer:
                        print(f"  ✓ Found customer: {faire_customer_name}")
                    
                    # Parse numeric fields
                    faire_net_rev = Decimal(str(row_dict.get('FAIRE_NET_REV', 0) or 0))
                    faire_net_units_sold = int(row_dict.get('FAIRE_NET_UNITS_SOLD', 0) or 0)
                    
                    print(f"  📊 Parsed values: units={faire_net_units_sold}, revenues=${faire_net_rev}")
                    
                    # Check for existing record
                    if customer:
                        existing = FaireData.query.filter(
                            FaireData.date == date,
                            FaireData.item_id == item.id,
                            FaireData.customer_id == customer.id
                        ).first()
                    else:
                        existing = FaireData.query.filter(
                            FaireData.date == date,
                            FaireData.item_id == item.id,
                            FaireData.customer_id.is_(None)
                        ).first()
                    
                    if existing:
                        # Update existing record
                        print(f"  ↻ Updating existing faire data (ID: {existing.id}, date={date}, item={item.essor_code})")
                        existing.revenues = faire_net_rev
                        existing.units = faire_net_units_sold
                        existing.brand_id = brand.id
                        results['updated'] += 1
                        results['processed'] += 1
                    else:
                        # Create new record
                        print(f"  ➕ Creating new faire data: date={date}, item={item.essor_code}")
                        faire = FaireData(
                            date=date,
                            brand_id=brand.id,
                            item_id=item.id,
                            customer_id=customer.id if customer else None,
                            revenues=faire_net_rev,
                            units=faire_net_units_sold
                        )
                        db.session.add(faire)
                        results['created'] += 1
                        results['processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Row {row_num}: {str(e)}"
                    print(f"  ✗ ERROR: {error_msg}")
                    import traceback
                    traceback_str = traceback.format_exc()
                    print(f"  Traceback: {traceback_str}")
                    results['errors'].append(error_msg)
                    # Save to ImportError table
                    try:
                        row_data = dict(zip(column_names, row)) if 'column_names' in locals() else list(row)
                        if isinstance(row_data, dict):
                            error_data_json = json.dumps(row_data)
                        elif isinstance(row_data, (list, tuple)):
                            error_data_json = json.dumps(list(row_data))
                        else:
                            error_data_json = json.dumps(str(row_data))
                        
                        import_error = ImportError(
                            import_channel='snowflake',
                            error_data=error_data_json,
                            error_message=f"{error_msg}\n\n{traceback_str}",
                            row_number=row_num
                        )
                        db.session.add(import_error)
                        if not dry_run:
                            db.session.commit()
                    except Exception as save_error:
                        print(f"  ⚠ Warning: Could not save error to ImportError table: {str(save_error)}")
                    results['skipped'] += 1
                    if not dry_run:
                        db.session.begin()
                    continue
            
            # Commit batch (only if not dry-run)
            if dry_run:
                print(f"\n⚠ Batch {batch_num + 1} completed (DRY-RUN: no changes saved)")
            else:
                print(f"\n💾 Committing batch {batch_num + 1}/{total_batches}...")
                try:
                    db.session.commit()
                    print(f"✓ Batch {batch_num + 1} committed successfully")
                    print(f"   Progress: {results['processed']} rows processed, {results['created']} created, {results['updated']} updated")
                except Exception as e:
                    print(f"✗ Error committing batch {batch_num + 1}: {str(e)}")
                    db.session.rollback()
                    raise
        
        # Close Snowflake connection
        cursor.close()
        conn.close()
        print("\n✓ Snowflake connection closed")
        
        # Prepare summary message
        mode_text = "DRY-RUN" if dry_run else "IMPORT"
        print("\n" + "="*60)
        print(f"{mode_text} Summary:")
        print(f"  ✓ Processed: {results['processed']} rows")
        print(f"  ➕ Created: {results['created']} records")
        print(f"  ↻ Updated: {results['updated']} records")
        if results['skipped'] > 0:
            print(f"  ⚠ Skipped: {results['skipped']} rows")
        if results['errors']:
            print(f"  ✗ Errors: {len(results['errors'])} errors occurred")
        print("="*60 + "\n")
        
        return results
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Error importing from Snowflake: {str(e)}'
        print(f"\n✗ ERROR: {error_msg}")
        import traceback
        print(traceback.format_exc())
        results['errors'].append(error_msg)
        return results
    finally:
        # Ensure connection is closed
        try:
            cursor.close()
            conn.close()
        except:
            pass

@faire_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    """Import faire data from Snowflake"""
    if request.method == 'GET':
        return render_template('faire/import.html', import_method='incremental')
    
    # Get form parameters
    dry_run = request.form.get('dry_run') == 'true'
    import_method = request.form.get('import_method', 'incremental')
    
    # Validate import method
    if import_method not in ['all', 'incremental']:
        flash('Invalid import method', 'error')
        return render_template('faire/import.html', import_method='incremental')
    
    try:
        results = _execute_faire_import(import_method, dry_run)
        
        # Prepare summary message
        mode_text = "DRY-RUN" if dry_run else "IMPORT"
        summary = f"{mode_text} completed: {results['processed']} rows processed, {results['created']} records created, {results['updated']} records updated"
        if results['skipped'] > 0:
            summary += f", {results['skipped']} rows skipped"
        if dry_run:
            summary += " (DRY-RUN: no changes saved)"
        
        flash(summary, 'success' if results['errors'] == [] else 'info')
        
        if results['errors']:
            flash(f"Errors: {len(results['errors'])} errors occurred. Check details below.", 'error')
        
        return render_template('faire/import.html', results=results, dry_run=dry_run, import_method=import_method)
        
    except Exception as e:
        error_msg = f'Error importing from Snowflake: {str(e)}'
        print(f"\n✗ ERROR: {error_msg}")
        import traceback
        print(traceback.format_exc())
        flash(error_msg, 'error')
        return render_template('faire/import.html', import_method=import_method)

