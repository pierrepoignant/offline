#!/usr/bin/env python3
"""
Sellthrough blueprint for managing sellthrough data
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import db, SellthroughData, Brand, Item, Channel, ChannelCustomer, ChannelItem, Category, ImportError
from auth.blueprint import login_required, admin_required
import json

sellthrough_bp = Blueprint('sellthrough', __name__, template_folder='templates')

def _save_import_error(import_channel, row_data, error_message, row_number=None):
    """Helper function to save import errors to the database"""
    try:
        # Convert row_data to JSON string
        if isinstance(row_data, dict):
            error_data_json = json.dumps(row_data)
        elif isinstance(row_data, (list, tuple)):
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
        # Don't commit here - let the batch commit handle it
    except Exception as e:
        # If we can't save the error, at least log it
        print(f"  ⚠ Warning: Could not save import error to database: {str(e)}")

@sellthrough_bp.route('/')
@login_required
def index():
    """Sellthrough data list"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = SellthroughData.query
    
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if item_id:
        query = query.filter_by(item_id=item_id)
    if channel_id:
        query = query.filter_by(channel_id=channel_id)
    if date_from:
        query = query.filter(SellthroughData.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        query = query.filter(SellthroughData.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    sellthrough_data = query.order_by(SellthroughData.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get filter options
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    
    return render_template('sellthrough/index.html', 
                         sellthrough_data=sellthrough_data,
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

@sellthrough_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Create new sellthrough data"""
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
            customer_id_str = request.form.get('customer_id', '').strip()
            customer_id = int(customer_id_str) if customer_id_str else None
            revenues = Decimal(request.form.get('revenues', '0') or '0')
            units = int(request.form.get('units', '0') or '0')
            stores = int(request.form.get('stores', '0') or '0')
            oos_str = request.form.get('oos', '').strip()
            oos = Decimal(str(oos_str)) if oos_str else None
            
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
            if customer_id and not ChannelCustomer.query.get(customer_id):
                flash('Invalid customer', 'error')
                return _render_create_form()
            
            sellthrough = SellthroughData(
                date=date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                customer_id=customer_id,
                revenues=revenues,
                units=units,
                stores=stores,
                oos=oos
            )
            
            db.session.add(sellthrough)
            db.session.commit()
            flash('Sellthrough data created successfully', 'success')
            return redirect(url_for('sellthrough.index'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
            return _render_create_form()
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating sellthrough data: {str(e)}', 'error')
            return _render_create_form()
    
    return _render_create_form()

def _render_create_form():
    """Helper to render create form with all necessary data"""
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    customers = ChannelCustomer.query.join(Channel).order_by(Channel.name, ChannelCustomer.name).all()
    return render_template('sellthrough/edit.html', 
                         brands=brands, 
                         items=items, 
                         channels=channels, 
                         customers=customers)

@sellthrough_bp.route('/<int:data_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(data_id):
    """Edit sellthrough data"""
    sellthrough = SellthroughData.query.get_or_404(data_id)
    
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            if not date_str:
                flash('Date is required', 'error')
                return _render_edit_form(sellthrough)
            
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            brand_id = int(request.form.get('brand_id'))
            item_id = int(request.form.get('item_id'))
            channel_id = int(request.form.get('channel_id'))
            customer_id_str = request.form.get('customer_id', '').strip()
            customer_id = int(customer_id_str) if customer_id_str else None
            revenues = Decimal(request.form.get('revenues', '0') or '0')
            units = int(request.form.get('units', '0') or '0')
            stores = int(request.form.get('stores', '0') or '0')
            oos_str = request.form.get('oos', '').strip()
            oos = Decimal(str(oos_str)) if oos_str else None
            
            sellthrough.date = date
            sellthrough.brand_id = brand_id
            sellthrough.item_id = item_id
            sellthrough.channel_id = channel_id
            sellthrough.customer_id = customer_id
            sellthrough.revenues = revenues
            sellthrough.units = units
            sellthrough.stores = stores
            sellthrough.oos = oos
            
            db.session.commit()
            flash('Sellthrough data updated successfully', 'success')
            return redirect(url_for('sellthrough.index'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
            return _render_edit_form(sellthrough)
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating sellthrough data: {str(e)}', 'error')
            return _render_edit_form(sellthrough)
    
    return _render_edit_form(sellthrough)

def _render_edit_form(sellthrough):
    """Helper to render edit form with all necessary data"""
    brands = Brand.query.order_by(Brand.name).all()
    items = Item.query.order_by(Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    customers = ChannelCustomer.query.join(Channel).order_by(Channel.name, ChannelCustomer.name).all()
    return render_template('sellthrough/edit.html', 
                         sellthrough=sellthrough,
                         brands=brands, 
                         items=items, 
                         channels=channels, 
                         customers=customers)

@sellthrough_bp.route('/<int:data_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(data_id):
    """Delete sellthrough data"""
    sellthrough = SellthroughData.query.get_or_404(data_id)
    db.session.delete(sellthrough)
    db.session.commit()
    flash('Sellthrough data deleted successfully', 'success')
    return redirect(url_for('sellthrough.index'))

@sellthrough_bp.route('/api/customers')
@login_required
def api_customers():
    """API endpoint to get customers for a channel"""
    channel_id = request.args.get('channel_id', type=int)
    if not channel_id:
        return jsonify([])
    
    customers = ChannelCustomer.query.filter_by(channel_id=channel_id).order_by(ChannelCustomer.name).all()
    return jsonify([{'id': cust.id, 'name': cust.name} for cust in customers])

@sellthrough_bp.route('/dashboard')
@login_required
def dashboard():
    """Sellthrough dashboard with chart"""
    # Get brands that have sell-through data with revenues > 0
    brands = Brand.query.join(SellthroughData).filter(
        SellthroughData.revenues > 0
    ).distinct().order_by(Brand.name).all()
    
    categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
    items = Item.query.join(Brand).order_by(Brand.name, Item.essor_code).all()
    channels = Channel.query.order_by(Channel.name).all()
    
    return render_template('sellthrough/dashboard.html',
                         brands=brands,
                         categories=categories,
                         items=items,
                         channels=channels)

@sellthrough_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """API endpoint to get chart data based on filters"""
    try:
        # Get filter parameters
        time_period = request.args.get('time_period', 'last_12_months')
        metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
        brand_id = request.args.get('brand_id', type=int)
        category_id = request.args.get('category_id', type=int)
        item_id = request.args.get('item_id', type=int)
        channel_id = request.args.get('channel_id', type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Calculate date range based on time period
        today = datetime.now().date()
        if time_period == 'last_12_months':
            start_date = today - timedelta(days=365)
            end_date = today
        elif time_period == 'last_3_months':
            start_date = today - timedelta(days=90)
            end_date = today
        elif time_period == 'year_to_date':
            start_date = datetime(today.year, 1, 1).date()
            end_date = today
        elif time_period == 'custom':
            if date_from:
                start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            else:
                start_date = today - timedelta(days=365)
            if date_to:
                end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            else:
                end_date = today
        else:
            start_date = today - timedelta(days=365)
            end_date = today
        
        # Build query - join Item if we need to filter by category
        needs_item_join = category_id is not None
        
        base_query = db.session.query(
            SellthroughData.date,
            func.sum(SellthroughData.units).label('total_units'),
            func.sum(SellthroughData.revenues).label('total_revenues')
        ).filter(
            SellthroughData.date >= start_date,
            SellthroughData.date <= end_date
        )
        
        # Join Item if filtering by category
        if needs_item_join:
            base_query = base_query.join(Item, SellthroughData.item_id == Item.id)
        
        query = base_query
        
        # Apply filters
        if brand_id:
            query = query.filter(SellthroughData.brand_id == brand_id)
        if category_id:
            # Item join already done above
            query = query.filter(Item.category_id == category_id)
        if item_id:
            query = query.filter(SellthroughData.item_id == item_id)
        if channel_id:
            query = query.filter(SellthroughData.channel_id == channel_id)
        
        # Group by date and order by date
        query = query.group_by(SellthroughData.date).order_by(SellthroughData.date)
        
        # Execute query
        results = query.all()
        
        # Prepare data for chart
        dates = [result.date.strftime('%Y-%m-%d') for result in results]
        if metric == 'units':
            values = [float(result.total_units) if result.total_units else 0 for result in results]
            metric_label = 'Units'
        else:  # revenues
            values = [float(result.total_revenues) if result.total_revenues else 0 for result in results]
            metric_label = 'Revenues ($)'
        
        return jsonify({
            'dates': dates,
            'values': values,
            'metric_label': metric_label,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sellthrough_bp.route('/api/categories')
@login_required
def api_categories():
    """API endpoint to get categories for a brand"""
    brand_id = request.args.get('brand_id', type=int)
    if not brand_id:
        return jsonify([])
    
    categories = Category.query.filter_by(brand_id=brand_id).order_by(Category.name).all()
    return jsonify([{'id': cat.id, 'name': cat.name} for cat in categories])

@sellthrough_bp.route('/api/items')
@login_required
def api_items():
    """API endpoint to get items for a brand and/or category"""
    brand_id = request.args.get('brand_id', type=int)
    category_id = request.args.get('category_id', type=int)
    
    query = Item.query
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    items = query.order_by(Item.essor_code).all()
    return jsonify([{
        'id': item.id,
        'essor_code': item.essor_code or '',
        'essor_name': item.essor_name or '',
        'display': f"{item.essor_code or 'N/A'} - {item.essor_name or 'N/A'}"
    } for item in items])

def parse_numeric_value(value_str, default=0):
    """Parse numeric value, handling commas, dollar signs, and negative signs"""
    if not value_str:
        return default
    
    # Convert to string and strip whitespace
    value_str = str(value_str).strip()
    
    # Handle empty strings
    if not value_str or value_str == '-':
        return default
    
    # Remove dollar signs, commas, and spaces
    cleaned = value_str.replace('$', '').replace(',', '').replace(' ', '').strip()
    
    # Handle negative values
    is_negative = cleaned.startswith('-')
    if is_negative:
        cleaned = cleaned[1:]
    
    try:
        value = float(cleaned)
        if is_negative:
            value = -value
        return value
    except (ValueError, TypeError):
        return default

def parse_percentage(value_str):
    """Parse percentage value, handling % sign"""
    if not value_str:
        return None
    
    value_str = str(value_str).strip()
    if not value_str or value_str == '-':
        return None
    
    # Remove % sign and spaces
    cleaned = value_str.replace('%', '').replace(' ', '').strip()
    
    try:
        return Decimal(cleaned)
    except (ValueError, TypeError):
        return None

@sellthrough_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    """Import sellthrough data from CSV file"""
    if request.method == 'GET':
        return render_template('sellthrough/import.html')
    
    # Check for dry-run mode
    dry_run = request.form.get('dry_run') == 'true'
    max_rows = 10 if dry_run else None
    
    # Handle file upload
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return render_template('sellthrough/import.html')
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return render_template('sellthrough/import.html')
    
    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return render_template('sellthrough/import.html')
    
    # Read CSV file
    try:
        mode_text = "DRY-RUN (first 10 rows only, no database changes)" if dry_run else "LIVE IMPORT"
        print("\n" + "="*60)
        print(f"Starting CSV Import Process - {mode_text}")
        print("="*60)
        
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Get column names
        csv_columns = csv_reader.fieldnames
        print(f"\n📋 CSV Columns detected: {', '.join(csv_columns)}")
        
        results = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': []
        }
        
        total_rows = 0
        rows_to_process = []
        for row in csv_reader:
            rows_to_process.append(row)
            total_rows += 1
            if max_rows and total_rows >= max_rows:
                break
        
        print(f"\n📊 Total rows to process: {len(rows_to_process)}" + (f" (limited to {max_rows} for dry-run)" if max_rows else ""))
        print("-"*60)
        
        # Process each row
        for row_num, row in enumerate(rows_to_process, start=2):  # Start at 2 (header is row 1)
            if row_num % 10 == 0 or row_num == 2:
                print(f"Processing row {row_num}/{total_rows + 1}...")
            try:
                # Parse week (date)
                week_str = row.get('week', '').strip()
                if not week_str:
                    error_msg = f"Row {row_num}: Missing 'week' field"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                try:
                    week_date = datetime.strptime(week_str, '%Y-%m-%d').date()
                except ValueError:
                    error_msg = f"Row {row_num}: Invalid date format for 'week' (expected YYYY-MM-DD): {week_str}"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                # Find or create channel
                channel_name = row.get('channel', '').strip()
                if not channel_name:
                    error_msg = f"Row {row_num}: Missing 'channel' field"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                channel = Channel.query.filter_by(name=channel_name).first()
                if not channel:
                    print(f"  ➕ Creating new channel: {channel_name}")
                    channel = Channel(name=channel_name)
                    db.session.add(channel)
                    db.session.flush()  # Get the ID
                    results['created'] += 1
                else:
                    print(f"  ✓ Found channel: {channel_name}")
                
                # Find or create item
                item = None
                # Get fields - convert empty strings to None for proper null handling
                essor_item_code = row.get('essor_item_code', '').strip() or None
                essor_item_name = row.get('essor_item_name', '').strip() or None
                channel_item_code = row.get('channel_item_code', '').strip() or None
                channel_item_name = row.get('channel_item_name', '').strip() or None
                
                # Try to find item by essor_code first, then essor_name
                if essor_item_code:
                    item = Item.query.filter_by(essor_code=essor_item_code).first()
                    if item:
                        print(f"  ✓ Found item by essor_code: {essor_item_code}")
                if not item and essor_item_name:
                    item = Item.query.filter_by(essor_name=essor_item_name).first()
                    if item:
                        print(f"  ✓ Found item by essor_name: {essor_item_name}")
                
                # If not found, try channel_items
                if not item:
                    channel_item = None
                    if channel_item_code:
                        channel_item = ChannelItem.query.filter_by(
                            channel_id=channel.id,
                            channel_code=channel_item_code
                        ).first()
                        if channel_item:
                            print(f"  ✓ Found item by channel_item_code: {channel_item_code}")
                    if not channel_item and channel_item_name:
                        channel_item = ChannelItem.query.filter_by(
                            channel_id=channel.id,
                            channel_name=channel_item_name
                        ).first()
                        if channel_item:
                            print(f"  ✓ Found item by channel_item_name: {channel_item_name}")
                    
                    if channel_item:
                        item = channel_item.item
                
                # If still not found, create item
                if not item:
                    print(f"  ➕ Creating new item...")
                    # Get or create brand from CSV - check both name and code
                    brand_name = row.get('brand', '').strip()
                    brand_code = row.get('brand_code', '').strip() or None
                    
                    if not brand_name and not brand_code:
                        error_msg = f"Row {row_num}: Missing 'brand' or 'brand_code' field (required for item creation)"
                        results['errors'].append(error_msg)
                        _save_import_error('csv', row, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    # Try to find brand - check brand field against both name and code
                    # Also check brand_code field against both name and code
                    brand = None
                    if brand_name:
                        # Check brand field against both name and code
                        brand = Brand.query.filter(
                            (Brand.name == brand_name) | (Brand.code == brand_name)
                        ).first()
                    if not brand and brand_code:
                        # Check brand_code field against both name and code
                        brand = Brand.query.filter(
                            (Brand.name == brand_code) | (Brand.code == brand_code)
                        ).first()
                    
                    if not brand:
                        print(f"    ➕ Creating new brand: {brand_name or brand_code}")
                        brand = Brand(name=brand_name or brand_code, code=brand_code)
                        db.session.add(brand)
                        db.session.flush()
                        results['created'] += 1
                    else:
                        # Update brand code if we have one and it's missing
                        if brand_code and not brand.code:
                            brand.code = brand_code
                            print(f"    ↻ Updated brand code: {brand_name} -> {brand_code}")
                        print(f"    ✓ Found brand: {brand_name or brand.code}")
                    
                    # Create item - must have at least essor_code or essor_name, or channel fields
                    if not essor_item_code and not essor_item_name and not channel_item_code and not channel_item_name:
                        error_msg = f"Row {row_num}: Cannot create item - no essor_item_code, essor_item_name, channel_item_code, or channel_item_name provided"
                        results['errors'].append(error_msg)
                        _save_import_error('csv', row, error_msg, row_num)
                        results['skipped'] += 1
                        continue
                    
                    # Don't copy between essor_code and essor_name - leave null if not provided
                    # Only use channel fields as fallback if we have absolutely nothing
                    if not essor_item_code and not essor_item_name:
                        if channel_item_code:
                            essor_item_code = channel_item_code
                        elif channel_item_name:
                            essor_item_name = channel_item_name
                    
                    print(f"    ➕ Creating item: code={essor_item_code or 'NULL'}, name={essor_item_name or 'NULL'}")
                    item = Item(
                        essor_code=essor_item_code,
                        essor_name=essor_item_name,
                        brand_id=brand.id,
                        category_id=None  # Optional - can be null
                    )
                    
                    db.session.add(item)
                    db.session.flush()
                    results['created'] += 1
                
                # Always ensure channel_item exists (create or update)
                # Only create/update if we have channel fields OR if this is a newly created item
                channel_item = ChannelItem.query.filter_by(
                    channel_id=channel.id,
                    item_id=item.id
                ).first()
                
                # Determine if we should create/update channel_item
                should_create_channel_item = False
                if channel_item_code or channel_item_name:
                    # We have channel info, so we should have a channel_item
                    should_create_channel_item = True
                elif not channel_item:
                    # Item was just created and we don't have a channel_item yet
                    # Create one with channel fields (even if null) or essor fields as fallback
                    should_create_channel_item = True
                
                if should_create_channel_item:
                    if channel_item:
                        # Update existing channel_item with channel info (only if provided)
                        updated = False
                        if channel_item_code is not None and channel_item.channel_code != channel_item_code:
                            channel_item.channel_code = channel_item_code
                            updated = True
                        if channel_item_name is not None and channel_item.channel_name != channel_item_name:
                            channel_item.channel_name = channel_item_name
                            updated = True
                        if updated:
                            print(f"  ↻ Updated channel_item: code={channel_item_code}, name={channel_item_name}")
                    else:
                        # Create new channel_item entry
                        # IMPORTANT: Don't mix code and name fields
                        # channel_code should come from: channel_item_code > essor_item_code > item.essor_code
                        # channel_name should come from: channel_item_name > essor_item_name > item.essor_name
                        # Never use a name field as a code field
                        channel_code = channel_item_code if channel_item_code is not None else (essor_item_code if essor_item_code is not None else item.essor_code)
                        channel_name = channel_item_name if channel_item_name is not None else (essor_item_name if essor_item_name is not None else item.essor_name)
                        
                        print(f"  ➕ Creating channel_item: code={channel_code}, name={channel_name}")
                        channel_item = ChannelItem(
                            channel_id=channel.id,
                            item_id=item.id,
                            channel_code=channel_code,
                            channel_name=channel_name
                        )
                        db.session.add(channel_item)
                        results['created'] += 1
                
                # Find or create customer (optional)
                customer = None
                customer_name = row.get('location', '').strip()  # Keep CSV column name as 'location' for backward compatibility
                if customer_name:
                    customer = ChannelCustomer.query.filter_by(
                        channel_id=channel.id,
                        name=customer_name
                    ).first()
                    
                    if not customer:
                        print(f"  ➕ Creating new customer: {customer_name}")
                        customer = ChannelCustomer(
                            channel_id=channel.id,
                            name=customer_name
                        )
                        db.session.add(customer)
                        db.session.flush()
                        results['created'] += 1
                    else:
                        print(f"  ✓ Found customer: {customer_name}")
                
                # Parse numeric fields with proper handling of commas, dollar signs, etc.
                units_raw = row.get('unit', '0') or '0'
                units = int(parse_numeric_value(units_raw, 0))
                
                sales_raw = row.get('sales', '0') or '0'
                revenues = Decimal(str(parse_numeric_value(sales_raw, 0)))
                
                # Skip rows with zero sales
                if revenues == 0:
                    print(f"  ⏭ Skipping row {row_num}: sales is 0")
                    results['skipped'] += 1
                    continue
                
                stores_raw = row.get('stores', '0') or '0'
                stores = int(parse_numeric_value(stores_raw, 0))
                
                oos_raw = row.get('oos', '').strip()
                oos = parse_percentage(oos_raw)
                
                print(f"  📊 Parsed values: units={units}, revenues=${revenues}, stores={stores}, oos={oos}%")
                
                # Get brand_id from item
                brand_id = item.brand_id
                
                # Check for existing record (unique constraint: date, channel_id, item_id, customer_id)
                # Handle NULL customer_id properly
                if customer:
                    existing = SellthroughData.query.filter_by(
                        date=week_date,
                        channel_id=channel.id,
                        item_id=item.id,
                        customer_id=customer.id
                    ).first()
                else:
                    existing = SellthroughData.query.filter(
                        SellthroughData.date == week_date,
                        SellthroughData.channel_id == channel.id,
                        SellthroughData.item_id == item.id,
                        SellthroughData.customer_id.is_(None)
                    ).first()
                
                if existing:
                    # Update existing record
                    print(f"  ↻ Updating existing sellthrough data")
                    existing.units = units
                    existing.revenues = revenues
                    existing.stores = stores
                    existing.oos = oos
                    existing.brand_id = brand_id
                    results['updated'] += 1
                else:
                    # Create new record
                    print(f"  ➕ Creating new sellthrough data: {week_date}, {item.essor_code}, {channel.name}")
                    sellthrough = SellthroughData(
                        date=week_date,
                        brand_id=brand_id,
                        item_id=item.id,
                        channel_id=channel.id,
                        customer_id=customer.id if customer else None,
                        units=units,
                        revenues=revenues,
                        stores=stores,
                        oos=oos
                    )
                    db.session.add(sellthrough)
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
                    _save_import_error('csv', row, f"{error_msg}\n\n{traceback_str}", row_num)
                except:
                    pass  # Don't fail if we can't save the error
                results['skipped'] += 1
                if not dry_run:
                    db.session.rollback()
                continue
        
        # Commit all changes (only if not dry-run)
        if dry_run:
            print("\n" + "-"*60)
            print("⚠ DRY-RUN MODE: Rolling back all changes (no data was saved)")
            db.session.rollback()
        else:
            print("\n" + "-"*60)
            print("Committing changes to database...")
            db.session.commit()
            print("✓ Changes committed successfully")
        
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
        
        summary = f"{mode_text} completed: {results['processed']} rows processed, {results['created']} records created, {results['updated']} records updated"
        if results['skipped'] > 0:
            summary += f", {results['skipped']} rows skipped"
        if dry_run:
            summary += " (DRY-RUN: no changes saved)"
        
        flash(summary, 'success' if results['errors'] == [] else 'info')
        
        if results['errors']:
            flash(f"Errors: {len(results['errors'])} errors occurred. Check details below.", 'error')
        
        return render_template('sellthrough/import.html', results=results, dry_run=dry_run)
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing CSV file: {str(e)}', 'error')
        return render_template('sellthrough/import.html')

