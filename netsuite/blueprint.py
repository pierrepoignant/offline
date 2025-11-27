#!/usr/bin/env python3
"""
Netsuite blueprint for managing netsuite revenue data
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal
from sqlalchemy import func
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os
import configparser
from models import db, NetsuiteData, Brand, Item, Channel, ChannelCustomer, NetsuiteCode, ImportError
from auth.blueprint import login_required, admin_required
import json

netsuite_bp = Blueprint('netsuite', __name__, template_folder='templates')

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

@netsuite_bp.route('/')
@login_required
def index():
    """Netsuite data list"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = NetsuiteData.query
    
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if item_id:
        query = query.filter_by(item_id=item_id)
    if channel_id:
        query = query.filter_by(channel_id=channel_id)
    if date_from:
        query = query.filter(NetsuiteData.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        query = query.filter(NetsuiteData.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    netsuite_data = query.order_by(NetsuiteData.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get filter options
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    # Only include channels where netsuite_include is True
    channels = Channel.query.filter_by(netsuite_include=True).order_by(Channel.name).all()
    
    return render_template('netsuite/index.html', 
                         netsuite_data=netsuite_data,
                         brands=brands,
                         items=items,
                         channels=channels,
                         current_filters={
                             'brand_id': brand_id,
                             'item_id': item_id,
                             'channel_id': channel_id,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@netsuite_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Create new netsuite data"""
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            if not date_str:
                flash('Date is required', 'error')
                return _render_create_form()
            
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            brand_id = int(request.form.get('brand_id'))
            item_id = int(request.form.get('item_id'))
            channel_id = int(request.form.get('channel_id'))
            revenues = Decimal(request.form.get('revenues', '0') or '0')
            units = int(request.form.get('units', '0') or '0')
            retailer_code = request.form.get('retailer_code', '').strip() or None
            
            # Validate foreign keys exist
            if not Brand.query.get(brand_id):
                flash('Invalid brand', 'error')
                return _render_create_form()
            if not Item.query.get(item_id):
                flash('Invalid item', 'error')
                return _render_create_form()
            if not Channel.query.get(channel_id):
                flash('Invalid channel', 'error')
                return _render_create_form()
            
            netsuite = NetsuiteData(
                date=date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                revenues=revenues,
                units=units,
                retailer_code=retailer_code
            )
            
            db.session.add(netsuite)
            db.session.commit()
            flash('Netsuite data created successfully', 'success')
            return redirect(url_for('netsuite.index'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
            return _render_create_form()
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating netsuite data: {str(e)}', 'error')
            return _render_create_form()
    
    return _render_create_form()

def _render_create_form():
    """Helper to render create form with all necessary data"""
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    return render_template('netsuite/edit.html', 
                         brands=brands, 
                         items=items, 
                         channels=channels)

@netsuite_bp.route('/<int:data_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(data_id):
    """Edit netsuite data"""
    netsuite = NetsuiteData.query.get_or_404(data_id)
    
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            if not date_str:
                flash('Date is required', 'error')
                return _render_edit_form(netsuite)
            
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            brand_id = int(request.form.get('brand_id'))
            item_id = int(request.form.get('item_id'))
            channel_id = int(request.form.get('channel_id'))
            revenues = Decimal(request.form.get('revenues', '0') or '0')
            units = int(request.form.get('units', '0') or '0')
            retailer_code = request.form.get('retailer_code', '').strip() or None
            
            netsuite.date = date
            netsuite.brand_id = brand_id
            netsuite.item_id = item_id
            netsuite.channel_id = channel_id
            netsuite.revenues = revenues
            netsuite.units = units
            netsuite.retailer_code = retailer_code
            
            db.session.commit()
            flash('Netsuite data updated successfully', 'success')
            return redirect(url_for('netsuite.index'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
            return _render_edit_form(netsuite)
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating netsuite data: {str(e)}', 'error')
            return _render_edit_form(netsuite)
    
    return _render_edit_form(netsuite)

def _render_edit_form(netsuite):
    """Helper to render edit form with all necessary data"""
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    return render_template('netsuite/edit.html', 
                         netsuite=netsuite,
                         brands=brands, 
                         items=items, 
                         channels=channels)

@netsuite_bp.route('/<int:data_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(data_id):
    """Delete netsuite data"""
    netsuite = NetsuiteData.query.get_or_404(data_id)
    db.session.delete(netsuite)
    db.session.commit()
    flash('Netsuite data deleted successfully', 'success')
    return redirect(url_for('netsuite.index'))

@netsuite_bp.route('/dashboard')
@login_required
def dashboard():
    """Netsuite dashboard with chart"""
    from models import NetsuiteData, db
    from sqlalchemy import func, extract
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    
    # Get all brands, items, and channels for filters
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.join(Brand).order_by(Brand.name, Item.essor_code).all()
    # Only include channels where netsuite_include is True
    channels = Channel.query.filter_by(netsuite_include=True).order_by(Channel.name).all()
    
    # Calculate total revenues for 2024 and 2025 with filters applied
    query_2024 = db.session.query(
        func.coalesce(func.sum(NetsuiteData.revenues), 0)
    ).join(Channel).filter(
        extract('year', NetsuiteData.date) == 2024,
        Channel.netsuite_include == True
    )
    
    query_2025 = db.session.query(
        func.coalesce(func.sum(NetsuiteData.revenues), 0)
    ).join(Channel).filter(
        extract('year', NetsuiteData.date) == 2025,
        Channel.netsuite_include == True
    )
    
    # Apply filters
    if brand_id:
        query_2024 = query_2024.filter(NetsuiteData.brand_id == brand_id)
        query_2025 = query_2025.filter(NetsuiteData.brand_id == brand_id)
    if item_id:
        query_2024 = query_2024.filter(NetsuiteData.item_id == item_id)
        query_2025 = query_2025.filter(NetsuiteData.item_id == item_id)
    if channel_id:
        query_2024 = query_2024.filter(NetsuiteData.channel_id == channel_id)
        query_2025 = query_2025.filter(NetsuiteData.channel_id == channel_id)
    
    rev_2024 = query_2024.scalar() or 0
    rev_2025 = query_2025.scalar() or 0
    
    total_rev_2024 = float(rev_2024)
    total_rev_2025 = float(rev_2025)
    
    return render_template('netsuite/dashboard.html',
                         brands=brands,
                         items=items,
                         channels=channels,
                         total_rev_2024=total_rev_2024,
                         total_rev_2025=total_rev_2025,
                         selected_brand_id=brand_id,
                         selected_item_id=item_id,
                         selected_channel_id=channel_id)

@netsuite_bp.route('/api/totals')
@login_required
def api_totals():
    """API endpoint to get filtered total revenues"""
    from models import NetsuiteData, db
    from sqlalchemy import func, extract
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    
    # Calculate total revenues for 2024 and 2025 with filters applied
    query_2024 = db.session.query(
        func.coalesce(func.sum(NetsuiteData.revenues), 0)
    ).join(Channel).filter(
        extract('year', NetsuiteData.date) == 2024,
        Channel.netsuite_include == True
    )
    
    query_2025 = db.session.query(
        func.coalesce(func.sum(NetsuiteData.revenues), 0)
    ).join(Channel).filter(
        extract('year', NetsuiteData.date) == 2025,
        Channel.netsuite_include == True
    )
    
    # Apply filters
    if brand_id:
        query_2024 = query_2024.filter(NetsuiteData.brand_id == brand_id)
        query_2025 = query_2025.filter(NetsuiteData.brand_id == brand_id)
    if item_id:
        query_2024 = query_2024.filter(NetsuiteData.item_id == item_id)
        query_2025 = query_2025.filter(NetsuiteData.item_id == item_id)
    if channel_id:
        query_2024 = query_2024.filter(NetsuiteData.channel_id == channel_id)
        query_2025 = query_2025.filter(NetsuiteData.channel_id == channel_id)
    
    rev_2024 = query_2024.scalar() or 0
    rev_2025 = query_2025.scalar() or 0
    
    return jsonify({
        'total_rev_2024': float(rev_2024),
        'total_rev_2025': float(rev_2025)
    })


@netsuite_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """API endpoint to get chart data based on filters - returns 12 months for 2024 and 2025"""
    try:
        from sqlalchemy import extract
        # Get filter parameters
        metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
        brand_id = request.args.get('brand_id', type=int)
        item_id = request.args.get('item_id', type=int)
        channel_id = request.args.get('channel_id', type=int)
        
        # Get data for all 12 months of 2024 and 2025
        months_2024 = {}
        months_2025 = {}
        
        # Query for 2024
        query_2024 = db.session.query(
            extract('month', NetsuiteData.date).label('month'),
            func.sum(NetsuiteData.units).label('total_units'),
            func.sum(NetsuiteData.revenues).label('total_revenues')
        ).join(Channel).filter(
            extract('year', NetsuiteData.date) == 2024,
            Channel.netsuite_include == True
        )
        
        # Query for 2025
        query_2025 = db.session.query(
            extract('month', NetsuiteData.date).label('month'),
            func.sum(NetsuiteData.units).label('total_units'),
            func.sum(NetsuiteData.revenues).label('total_revenues')
        ).join(Channel).filter(
            extract('year', NetsuiteData.date) == 2025,
            Channel.netsuite_include == True
        )
        
        # Apply filters
        if brand_id:
            query_2024 = query_2024.filter(NetsuiteData.brand_id == brand_id)
            query_2025 = query_2025.filter(NetsuiteData.brand_id == brand_id)
        if item_id:
            query_2024 = query_2024.filter(NetsuiteData.item_id == item_id)
            query_2025 = query_2025.filter(NetsuiteData.item_id == item_id)
        if channel_id:
            query_2024 = query_2024.filter(NetsuiteData.channel_id == channel_id)
            query_2025 = query_2025.filter(NetsuiteData.channel_id == channel_id)
        
        # Group by month
        query_2024 = query_2024.group_by(extract('month', NetsuiteData.date))
        query_2025 = query_2025.group_by(extract('month', NetsuiteData.date))
        
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
    """Get the latest date from NetsuiteData table"""
    last_record = NetsuiteData.query.order_by(NetsuiteData.date.desc()).first()
    if last_record:
        return last_record.date
    return None

def _execute_netsuite_import(table_name, import_method='all', dry_run=False):
    """Execute the Netsuite import with specified parameters
    
    Args:
        table_name: Name of the Snowflake table (NET_REVENUE_OFFLINE_CHANNELS or NET_REVENUE_OFFLINE_CHANNELS_2024)
        import_method: 'all' to import all data, 'incremental' to import since last entry
        dry_run: If True, only process first 10 rows and don't save to database
    
    Returns:
        dict with import results
    """
    max_rows = 10 if dry_run else None
    
    mode_text = "DRY-RUN (first 10 rows only, no database changes)" if dry_run else "LIVE IMPORT"
    print("\n" + "="*60)
    print(f"Starting Snowflake Import Process - {mode_text}")
    print(f"Table: {table_name}")
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
    
    # Build query
    base_query = """
    SELECT
        SUM(AMOUNT) AS revenues,
        SUM(QUANTITY) AS units,
        CLASS AS brand,
        REPORT_DATE AS date,
        COALESCE(NULLIF(TRIM(SPLIT_PART(ITEM, ':', 2)), ''), 'no-item') AS essor_code,
        LEFT(NAME, 5) AS retailer_code,
        NAME AS retailer
    FROM DWH.NETSUITE.{table_name}
    WHERE SPLIT_PART(ACCOUNT, ' ', 2) = 'Revenue'
    """
    
    # Add date filter for incremental import
    if import_method == 'incremental' and last_date:
        base_query += f" AND REPORT_DATE >= '{last_date.strftime('%Y-%m-%d')}'"
    
    base_query += """
    GROUP BY brand, date, essor_code, retailer_code, retailer
    """
    
    query = base_query.format(table_name=table_name)
        
    print("\n📊 Executing query...")
    print(f"Query: {query[:200]}...")  # Print first 200 chars of query
    cursor.execute(query)
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
    
    # Get column names for error logging
    column_names = ['revenues', 'units', 'brand', 'date', 'essor_code', 'retailer_code', 'retailer']
    
    print(f"\n📊 Total rows to process: {len(rows_to_process)}" + (f" (limited to {max_rows} for dry-run)" if max_rows else ""))
    print("-"*60)
    
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
                    # Parse date
                    date = row[3]  # REPORT_DATE
                    if not date:
                        error_msg = f"Row {row_num}: Missing 'date' field"
                        results['errors'].append(error_msg)
                        row_data = dict(zip(column_names, row))
                        _save_import_error('snowflake', row_data, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    # Handle different date formats from Snowflake
                    # Snowflake can return dates as strings, datetime objects, or date objects
                    if isinstance(date, str):
                        # Try multiple date formats
                        date_str = date.strip()
                        try:
                            # Try YYYY-MM-DD format first
                            date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        except ValueError:
                            try:
                                # Try YYYY-MM-DD HH:MM:SS format (split on space and take first part)
                                date = datetime.strptime(date_str.split()[0], '%Y-%m-%d').date()
                            except (ValueError, IndexError):
                                # Try other common formats
                                try:
                                    date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').date()
                                except ValueError:
                                    error_msg = f"Row {row_num}: Invalid date format '{date}'"
                                    results['errors'].append(error_msg)
                                    row_data = dict(zip(column_names, row))
                                    _save_import_error('snowflake', row_data, error_msg, row_num)
                                    results['skipped'] += 1
                                    continue
                    elif isinstance(date, datetime):
                        date = date.date()
                    elif isinstance(date, date_type):
                        # It's already a date object, use it directly
                        pass
                    else:
                        # Unknown type, try to convert
                        try:
                            # If it's a date-like object from Snowflake, try to extract date
                            if hasattr(date, 'date'):
                                date = date.date()
                            elif hasattr(date, 'year') and hasattr(date, 'month') and hasattr(date, 'day'):
                                # It's already a date-like object, use it directly
                                pass
                            else:
                                raise ValueError(f"Cannot parse date type: {type(date).__name__}")
                        except Exception as e:
                            error_msg = f"Row {row_num}: Cannot parse date '{date}' (type: {type(date).__name__}): {str(e)}"
                            results['errors'].append(error_msg)
                            row_data = dict(zip(column_names, row))
                            _save_import_error('snowflake', row_data, error_msg, row_num)
                            results['skipped'] += 1
                            continue
                    
                    # Get retailer_code first
                    retailer_code = row[5]  # LEFT(NAME, 5)
                    retailer_name = row[6]  # NAME/retailer
                    # Note: internal_id removed from query, so it's no longer available
                    
                    # First, ensure NetsuiteCode exists for retailer_code (create if it doesn't exist)
                    channel = None
                    customer_id = None
                    if retailer_code:
                        netsuite_code_mapping = NetsuiteCode.query.filter_by(netsuite_code=retailer_code).first()
                        if netsuite_code_mapping:
                            channel = netsuite_code_mapping.channel
                            customer_id = netsuite_code_mapping.customer_id
                            if channel:
                                print(f"  ✓ Found channel via netsuite_code mapping: {retailer_code} -> {channel.name}")
                            else:
                                print(f"  ⚠ NetsuiteCode {retailer_code} exists but has no channel_id mapped - will import with channel_id=null")
                        else:
                            # Create NetsuiteCode with no channel_id and no customer_id
                            print(f"  ➕ Creating new netsuite_code: {retailer_code} (no channel_id, no customer_id) - will import with channel_id=null")
                            netsuite_code_mapping = NetsuiteCode(
                                netsuite_code=retailer_code,
                                netsuite_name=retailer_name,
                                channel_id=None,
                                customer_id=None
                            )
                            db.session.add(netsuite_code_mapping)
                            db.session.flush()
                            results['created'] += 1
                    
                    # Note: channel can be None - we'll import with channel_id=null
                    # Channel mapping can be set later in Netsuite Codes
                    
                    # Find or create brand first (needed for item creation)
                    brand_name = row[2]  # CLASS
                    if not brand_name:
                        error_msg = f"Row {row_num}: Missing 'brand' field"
                        results['errors'].append(error_msg)
                        row_data = dict(zip(column_names, row))
                        _save_import_error('snowflake', row_data, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    # Try to find brand by name first
                    brand = Brand.query.filter_by(name=brand_name).first()
                    
                    # If not found by name, try to find by code
                    if not brand:
                        brand = Brand.query.filter_by(code=brand_name).first()
                        if brand:
                            print(f"  ✓ Found brand by code: {brand_name} -> {brand.name}")
                    
                    # If still not found, create new brand
                    if not brand:
                        print(f"  ➕ Creating new brand: {brand_name}")
                        brand = Brand(name=brand_name, code=brand_name)
                        db.session.add(brand)
                        db.session.flush()
                        results['created'] += 1
                    else:
                        if brand.name == brand_name:
                            print(f"  ✓ Found brand by name: {brand_name}")
                        # Already printed if found by code above
                    
                    # Find or create item by essor_code
                    essor_code = row[4]  # TRIM(SPLIT_PART(ITEM, ':', 2))
                    if not essor_code:
                        error_msg = f"Row {row_num}: Missing 'essor_code' field"
                        results['errors'].append(error_msg)
                        row_data = dict(zip(column_names, row))
                        _save_import_error('snowflake', row_data, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    item = Item.query.filter_by(essor_code=essor_code).first()
                    if not item:
                        # Create new item with essor_code and brand
                        print(f"  ➕ Creating new item: essor_code={essor_code}, brand={brand.name}")
                        item = Item(
                            essor_code=essor_code,
                            essor_name=None,  # Can be set later if needed
                            brand_id=brand.id
                        )
                        db.session.add(item)
                        db.session.flush()
                        results['created'] += 1
                    else:
                        print(f"  ✓ Found item: {essor_code}")
                    
                    # Parse numeric fields
                    revenues = Decimal(str(row[0] or 0))  # AMOUNT
                    units = int(row[1] or 0)  # QUANTITY
                    # retailer_code already extracted above
                    
                    print(f"  📊 Parsed values: units={units}, revenues=${revenues}, retailer_code={retailer_code}")
                    
                    # Get brand_id from item (use item's brand_id, not the brand from CLASS)
                    brand_id = item.brand_id
                    
                    # customer_id already determined from NetsuiteCode mapping above (or None)
                    
                    # Check for existing record
                    # Try to find by date, customer_id (if not null), channel_id (can be null), item_id
                    if customer_id:
                        if channel:
                            existing = NetsuiteData.query.filter(
                                NetsuiteData.date == date,
                                NetsuiteData.channel_id == channel.id,
                                NetsuiteData.item_id == item.id,
                                NetsuiteData.customer_id == customer_id
                            ).first()
                        else:
                            existing = NetsuiteData.query.filter(
                                NetsuiteData.date == date,
                                NetsuiteData.channel_id.is_(None),
                                NetsuiteData.item_id == item.id,
                                NetsuiteData.customer_id == customer_id
                            ).first()
                    else:
                        if channel:
                            existing = NetsuiteData.query.filter(
                                NetsuiteData.date == date,
                                NetsuiteData.channel_id == channel.id,
                                NetsuiteData.item_id == item.id,
                                NetsuiteData.customer_id.is_(None)
                            ).first()
                        else:
                            existing = NetsuiteData.query.filter(
                                NetsuiteData.date == date,
                                NetsuiteData.channel_id.is_(None),
                                NetsuiteData.item_id == item.id,
                                NetsuiteData.customer_id.is_(None)
                            ).first()
                    
                    if existing:
                        # Update existing record
                        channel_name = channel.name if channel else "None (unmapped)"
                        print(f"  ↻ Updating existing netsuite data (ID: {existing.id}, date={date}, channel={channel_name}, item={item.essor_code})")
                        existing.revenues = revenues
                        existing.units = units
                        existing.brand_id = brand_id
                        existing.retailer_code = retailer_code
                        # Update channel_id and customer_id in case mapping changed
                        existing.channel_id = channel.id if channel else None
                        existing.customer_id = customer_id
                        results['updated'] += 1
                        results['processed'] += 1
                    else:
                        # Create new record
                        channel_name = channel.name if channel else "None (unmapped)"
                        print(f"  ➕ Creating new netsuite data: date={date}, item={item.essor_code}, channel={channel_name}")
                        netsuite = NetsuiteData(
                            date=date,
                            brand_id=brand_id,
                            item_id=item.id,
                            channel_id=channel.id if channel else None,
                            customer_id=customer_id,
                            internal_id=None,  # No longer available from query
                            revenues=revenues,
                            units=units,
                            retailer_code=retailer_code
                        )
                        db.session.add(netsuite)
                        results['created'] += 1
                        results['processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Row {row_num}: {str(e)}"
                    print(f"  ✗ ERROR: {error_msg}")
                    import traceback
                    traceback_str = traceback.format_exc()
                    print(f"  Traceback: {traceback_str}")
                    results['errors'].append(error_msg)
                    # Save to ImportError table - use a separate session to avoid rollback issues
                    try:
                        row_data = dict(zip(column_names, row)) if 'column_names' in locals() else list(row)
                        # Save error in a way that won't be rolled back
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
                        # Commit error immediately in a separate transaction
                        if not dry_run:
                            db.session.commit()
                    except Exception as save_error:
                        print(f"  ⚠ Warning: Could not save error to ImportError table: {str(save_error)}")
                        import traceback
                        print(f"  Save error traceback: {traceback.format_exc()}")
                    results['skipped'] += 1
                    if not dry_run:
                        # Start a new transaction for the next row
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

@netsuite_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    """Import netsuite data from Snowflake"""
    if request.method == 'GET':
        return render_template('netsuite/import.html', import_method='incremental')
    
    # Get form parameters
    dry_run = request.form.get('dry_run') == 'true'
    table_name = request.form.get('table_name', 'NET_REVENUE_OFFLINE_CHANNELS')
    import_method = request.form.get('import_method', 'incremental')
    
    # Validate table name
    if table_name not in ['NET_REVENUE_OFFLINE_CHANNELS', 'NET_REVENUE_OFFLINE_CHANNELS_2024']:
        flash('Invalid table name', 'error')
        return render_template('netsuite/import.html', import_method=import_method, table_name=table_name)
    
    # Validate import method
    if import_method not in ['all', 'incremental']:
        flash('Invalid import method', 'error')
        return render_template('netsuite/import.html', import_method='incremental', table_name=table_name)
    
    try:
        results = _execute_netsuite_import(table_name, import_method, dry_run)
        
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
        
        return render_template('netsuite/import.html', results=results, dry_run=dry_run, table_name=table_name, import_method=import_method)
        
    except Exception as e:
        error_msg = f'Error importing from Snowflake: {str(e)}'
        print(f"\n✗ ERROR: {error_msg}")
        import traceback
        print(traceback.format_exc())
        flash(error_msg, 'error')
        return render_template('netsuite/import.html', import_method=import_method, table_name=table_name)

# ==================== Netsuite Codes ====================

@netsuite_bp.route('/netsuite-codes')
@login_required
def netsuite_codes_list():
    """List all netsuite codes"""
    from sqlalchemy import extract
    
    # Get filter parameter
    filter_no_channel = request.args.get('filter_no_channel') == '1'
    
    # Use outerjoin to include records where channel_id is null
    query = NetsuiteCode.query.outerjoin(Channel)
    
    # Apply filter if requested
    if filter_no_channel:
        query = query.filter(NetsuiteCode.channel_id.is_(None))
    
    netsuite_codes = query.order_by(NetsuiteCode.netsuite_code).all()
    
    # Get all retailer codes from the filtered netsuite codes
    retailer_codes = [code.netsuite_code for code in netsuite_codes]
    
    # Calculate revenues for all codes in a single query (2024)
    rev_2024_results = db.session.query(
        NetsuiteData.retailer_code,
        func.coalesce(func.sum(NetsuiteData.revenues), 0).label('total_rev')
    ).filter(
        NetsuiteData.retailer_code.in_(retailer_codes),
        extract('year', NetsuiteData.date) == 2024
    ).group_by(NetsuiteData.retailer_code).all()
    
    # Calculate revenues for all codes in a single query (2025)
    rev_2025_results = db.session.query(
        NetsuiteData.retailer_code,
        func.coalesce(func.sum(NetsuiteData.revenues), 0).label('total_rev')
    ).filter(
        NetsuiteData.retailer_code.in_(retailer_codes),
        extract('year', NetsuiteData.date) == 2025
    ).group_by(NetsuiteData.retailer_code).all()
    
    # Build dictionary of revenues by code
    revenues_by_code = {}
    for code in retailer_codes:
        revenues_by_code[code] = {'2024': 0.0, '2025': 0.0}
    
    # Populate 2024 revenues
    for result in rev_2024_results:
        if result.retailer_code:
            revenues_by_code[result.retailer_code]['2024'] = float(result.total_rev)
    
    # Populate 2025 revenues
    for result in rev_2025_results:
        if result.retailer_code:
            revenues_by_code[result.retailer_code]['2025'] = float(result.total_rev)
    
    return render_template('netsuite/netsuite_codes_list.html', 
                         netsuite_codes=netsuite_codes,
                         filter_no_channel=filter_no_channel,
                         revenues_by_code=revenues_by_code)

@netsuite_bp.route('/netsuite-codes/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_netsuite_code():
    """Create a new netsuite code mapping"""
    channels = Channel.query.order_by(Channel.name).all()
    customers = ChannelCustomer.query.join(Channel).order_by(Channel.name, ChannelCustomer.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    
    if request.method == 'POST':
        netsuite_code = request.form.get('netsuite_code', '').strip().upper()
        netsuite_name = request.form.get('netsuite_name', '').strip() or None
        channel_id = request.form.get('channel_id', type=int)
        customer_option = request.form.get('customer_option', 'existing')
        customer_id_str = request.form.get('customer_id', '').strip()
        customer_id = int(customer_id_str) if customer_id_str else None
        new_customer_name = request.form.get('new_customer_name', '').strip()
        
        if not netsuite_code:
            flash('Netsuite code is required', 'error')
            return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
        
        if channel_id and not Channel.query.get(channel_id):
            flash('Invalid channel', 'error')
            return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
        
        # Handle new customer creation
        if customer_option == 'new' and new_customer_name:
            if not channel_id:
                flash('Channel is required when creating a new customer', 'error')
                return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
            
            brand_id = request.form.get('new_customer_brand_id', type=int) or None
            
            # Check if customer already exists for this channel
            existing_customer = ChannelCustomer.query.filter_by(
                name=new_customer_name,
                channel_id=channel_id
            ).first()
            
            if existing_customer:
                customer_id = existing_customer.id
                flash(f'Customer "{new_customer_name}" already exists for this channel, using existing customer.', 'info')
            else:
                # Create new customer
                new_customer = ChannelCustomer(
                    name=new_customer_name,
                    channel_id=channel_id,
                    brand_id=brand_id
                )
                db.session.add(new_customer)
                db.session.flush()
                customer_id = new_customer.id
                flash(f'New customer "{new_customer_name}" created successfully.', 'success')
        elif customer_option == 'existing' and customer_id:
            if not ChannelCustomer.query.get(customer_id):
                flash('Invalid customer', 'error')
                return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
        
        # Check if netsuite code already exists
        existing = NetsuiteCode.query.filter_by(netsuite_code=netsuite_code).first()
        if existing:
            channel_name = existing.channel.name if existing.channel else 'No channel'
            flash(f'Netsuite code "{netsuite_code}" already exists and is mapped to channel "{channel_name}"', 'error')
            return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
        
        # Validate customer belongs to channel if both are provided
        if customer_id and channel_id:
            customer = ChannelCustomer.query.get(customer_id)
            if customer and customer.channel_id != channel_id:
                flash('Selected customer does not belong to the selected channel', 'error')
                return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)
        
        netsuite_code_obj = NetsuiteCode(
            netsuite_code=netsuite_code,
            netsuite_name=netsuite_name,
            channel_id=channel_id,
            customer_id=customer_id
        )
        db.session.add(netsuite_code_obj)
        db.session.flush()  # Get the ID
        
        # Update all existing netsuite_data records with this netsuite_code
        update_data = {}
        if channel_id:
            update_data['channel_id'] = channel_id
        if customer_id:
            update_data['customer_id'] = customer_id
        
        updated_count = 0
        if update_data:
            updated_count = NetsuiteData.query.filter_by(retailer_code=netsuite_code).update(
                update_data, synchronize_session=False
            )
        
        db.session.commit()
        
        channel_text = f'channel "{Channel.query.get(channel_id).name}"' if channel_id else 'no channel'
        flash(f'Netsuite code "{netsuite_code}" created and mapped to {channel_text}. Updated {updated_count} existing Netsuite records.', 'success')
        return redirect(url_for('netsuite.netsuite_codes_list'))
    
    return render_template('netsuite/edit_netsuite_code.html', channels=channels, customers=customers, brands=brands)

@netsuite_bp.route('/netsuite-codes/<int:netsuite_code_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_netsuite_code(netsuite_code_id):
    """Edit a netsuite code mapping"""
    netsuite_code_obj = NetsuiteCode.query.get_or_404(netsuite_code_id)
    channels = Channel.query.order_by(Channel.name).all()
    customers = ChannelCustomer.query.join(Channel).order_by(Channel.name, ChannelCustomer.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    
    if request.method == 'POST':
        netsuite_code = request.form.get('netsuite_code', '').strip().upper()
        netsuite_name = request.form.get('netsuite_name', '').strip() or None
        channel_id = request.form.get('channel_id', type=int)
        customer_option = request.form.get('customer_option', 'existing')
        customer_id_str = request.form.get('customer_id', '').strip()
        customer_id = int(customer_id_str) if customer_id_str else None
        new_customer_name = request.form.get('new_customer_name', '').strip()
        
        if not netsuite_code:
            flash('Netsuite code is required', 'error')
            return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
        
        if channel_id and not Channel.query.get(channel_id):
            flash('Invalid channel', 'error')
            return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
        
        # Handle new customer creation
        if customer_option == 'new' and new_customer_name:
            if not channel_id:
                flash('Channel is required when creating a new customer', 'error')
                return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
            
            brand_id = request.form.get('new_customer_brand_id', type=int) or None
            
            # Check if customer already exists for this channel
            existing_customer = ChannelCustomer.query.filter_by(
                name=new_customer_name,
                channel_id=channel_id
            ).first()
            
            if existing_customer:
                customer_id = existing_customer.id
                flash(f'Customer "{new_customer_name}" already exists for this channel, using existing customer.', 'info')
            else:
                # Create new customer
                new_customer = ChannelCustomer(
                    name=new_customer_name,
                    channel_id=channel_id,
                    brand_id=brand_id
                )
                db.session.add(new_customer)
                db.session.flush()
                customer_id = new_customer.id
                flash(f'New customer "{new_customer_name}" created successfully.', 'success')
        elif customer_option == 'existing' and customer_id:
            if not ChannelCustomer.query.get(customer_id):
                flash('Invalid customer', 'error')
                return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
        
        # Check if netsuite code already exists (and it's not this one)
        existing = NetsuiteCode.query.filter_by(netsuite_code=netsuite_code).first()
        if existing and existing.id != netsuite_code_id:
            flash(f'Netsuite code "{netsuite_code}" already exists', 'error')
            return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
        
        # Validate customer belongs to channel if both are provided (skip if we just created the customer)
        if customer_id and channel_id and customer_option == 'existing':
            customer = ChannelCustomer.query.get(customer_id)
            if customer and customer.channel_id != channel_id:
                flash('Selected customer does not belong to the selected channel', 'error')
                return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)
        
        old_channel_id = netsuite_code_obj.channel_id
        old_netsuite_code = netsuite_code_obj.netsuite_code
        
        netsuite_code_obj.netsuite_code = netsuite_code
        netsuite_code_obj.netsuite_name = netsuite_name
        netsuite_code_obj.channel_id = channel_id
        netsuite_code_obj.customer_id = customer_id
        db.session.flush()
        
        # Update all existing netsuite_data records with this netsuite_code
        update_data = {}
        if channel_id:
            update_data['channel_id'] = channel_id
        if customer_id:
            update_data['customer_id'] = customer_id
        
        updated_count = 0
        if update_data:
            # If the netsuite_code changed, update both old and new codes
            if old_netsuite_code != netsuite_code:
                # Update records with old code
                NetsuiteData.query.filter_by(retailer_code=old_netsuite_code).update(
                    update_data, synchronize_session=False
                )
                # Update records with new code
                updated_count = NetsuiteData.query.filter_by(retailer_code=netsuite_code).update(
                    update_data, synchronize_session=False
                )
            else:
                # Code didn't change, just update records with this netsuite_code
                updated_count = NetsuiteData.query.filter_by(retailer_code=netsuite_code).update(
                    update_data, synchronize_session=False
                )
        
        db.session.commit()
        
        if updated_count > 0:
            flash(f'Netsuite code updated successfully. Updated {updated_count} existing Netsuite records.', 'success')
        else:
            flash(f'Netsuite code updated successfully.', 'success')
        return redirect(url_for('netsuite.netsuite_codes_list'))
    
    return render_template('netsuite/edit_netsuite_code.html', netsuite_code=netsuite_code_obj, channels=channels, customers=customers, brands=brands)

@netsuite_bp.route('/netsuite-codes/<int:netsuite_code_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_netsuite_code(netsuite_code_id):
    """Delete a netsuite code mapping"""
    netsuite_code_obj = NetsuiteCode.query.get_or_404(netsuite_code_id)
    netsuite_code_value = netsuite_code_obj.netsuite_code
    
    db.session.delete(netsuite_code_obj)
    db.session.commit()
    
    flash(f'Netsuite code "{netsuite_code_value}" deleted successfully', 'success')
    return redirect(url_for('netsuite.netsuite_codes_list'))

@netsuite_bp.route('/api/netsuite-data-by-code')
@login_required
def api_netsuite_data_by_code():
    """API endpoint to get netsuite data by retailer_code"""
    retailer_code = request.args.get('retailer_code')
    if not retailer_code:
        return jsonify({'error': 'retailer_code parameter is required'}), 400
    
    # Get netsuite data for this retailer_code
    netsuite_data = NetsuiteData.query.filter_by(retailer_code=retailer_code).order_by(
        NetsuiteData.date.desc()
    ).all()
    
    # Format the data for JSON response
    data = []
    for record in netsuite_data:
        data.append({
            'id': record.id,
            'date': record.date.strftime('%Y-%m-%d') if record.date else None,
            'brand': record.brand.name if record.brand else None,
            'item': record.item.essor_code if record.item else None,
            'channel': record.channel.name if record.channel else None,
            'customer': record.customer.name if record.customer else None,
            'revenues': float(record.revenues) if record.revenues else 0,
            'units': record.units if record.units else 0
        })
    
    return jsonify({
        'retailer_code': retailer_code,
        'count': len(data),
        'data': data
    })

@netsuite_bp.route('/import/cron', methods=['GET', 'POST'])
def import_cron():
    """Cron endpoint for automated daily import of 2025 data since last entry
    
    This endpoint should be called by a cron job at midnight.
    It imports data from NET_REVENUE_OFFLINE_CHANNELS using incremental method.
    """
    # Check for authentication token (optional - can be set in environment)
    import os
    cron_token = os.getenv('NETSUITE_CRON_TOKEN', '')
    provided_token = request.args.get('token') or request.headers.get('X-Cron-Token', '')
    
    if cron_token and provided_token != cron_token:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        print("\n" + "="*60)
        print("Starting Automated Cron Import")
        print("="*60)
        
        results = _execute_netsuite_import(
            table_name='NET_REVENUE_OFFLINE_CHANNELS',
            import_method='incremental',
            dry_run=False
        )
        
        return jsonify({
            'status': 'success',
            'processed': results['processed'],
            'created': results['created'],
            'updated': results['updated'],
            'skipped': results['skipped'],
            'errors_count': len(results['errors']),
            'errors': results['errors'][:10]  # Return first 10 errors if any
        }), 200
        
    except Exception as e:
        error_msg = f'Error in cron import: {str(e)}'
        print(f"\n✗ ERROR: {error_msg}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'error': error_msg
        }), 500

