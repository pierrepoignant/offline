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

def parse_yyyyww_to_monday(yyyyww_str):
    """Parse YYYYWW format (e.g., 202401) to the first Monday of that week"""
    try:
        year = int(yyyyww_str[:4])
        week = int(yyyyww_str[4:])
        
        # Get January 1st of the year
        jan1 = datetime(year, 1, 1).date()
        # ISO week 1 is the week containing Jan 4
        # Find the Monday of ISO week 1
        jan4 = datetime(year, 1, 4).date()
        days_to_monday = (jan4.weekday()) % 7  # 0 = Monday, so this gives days to subtract
        week1_monday = jan4 - timedelta(days=days_to_monday)
        
        # Calculate the Monday of the requested week
        target_monday = week1_monday + timedelta(weeks=week - 1)
        
        return target_monday
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid YYYYWW format: {yyyyww_str}") from e

def parse_dec_wk_to_monday(dec_wk_str):
    """Parse 'Dec Wk 5 2024' format to the first Monday of that week"""
    try:
        # Parse format like "Dec Wk 5 2024"
        parts = dec_wk_str.strip().split()
        if len(parts) != 4 or parts[1].lower() != 'wk':
            raise ValueError(f"Invalid format: {dec_wk_str}")
        
        month_name = parts[0]
        week_num = int(parts[2])
        year = int(parts[3])
        
        # Map month names to numbers
        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        month = months.get(month_name, None)
        if month is None:
            raise ValueError(f"Invalid month name: {month_name}")
        
        # Find the first day of the month
        first_day = datetime(year, month, 1).date()
        # Find the first Monday of the month
        days_to_monday = (7 - first_day.weekday()) % 7
        if days_to_monday == 0 and first_day.weekday() != 0:
            days_to_monday = 7
        
        first_monday = first_day + timedelta(days=days_to_monday)
        # Week 1 is the first week that contains a Monday in the month
        # Calculate the Monday of the requested week
        target_monday = first_monday + timedelta(weeks=week_num - 1)
        
        return target_monday
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid 'Dec Wk 5 2024' format: {dec_wk_str}") from e

def parse_fiscal_week_ending_to_monday(fiscal_str):
    """Parse 'Fiscal Week Ending 01-11-2025' format to the Monday of that week (minus 6 days)"""
    try:
        # Extract date from "Fiscal Week Ending 01-11-2025"
        date_part = fiscal_str.replace('Fiscal Week Ending', '').strip()
        week_ending = datetime.strptime(date_part, '%m-%d-%Y').date()
        # Monday is 6 days before the ending date (Sunday)
        monday = week_ending - timedelta(days=6)
        return monday
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid 'Fiscal Week Ending' format: {fiscal_str}") from e

def parse_excel_serial_to_monday(excel_serial_str):
    """Parse Excel serial date (first 5 digits) to the Monday of that week"""
    try:
        # Get first 5 digits
        serial_str = str(excel_serial_str).strip()[:5]
        serial_days = int(serial_str)
        
        # Excel epoch is December 30, 1899 (or January 1, 1900 depending on system)
        # Most systems use December 30, 1899
        excel_epoch = datetime(1899, 12, 30).date()
        date = excel_epoch + timedelta(days=serial_days)
        
        # Find the Monday of that week
        days_to_monday = (date.weekday()) % 7
        monday = date - timedelta(days=days_to_monday)
        
        return monday
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid Excel serial date: {excel_serial_str}") from e

def detect_csv_format(headers):
    """Detect CSV format based on headers"""
    headers_lower = [h.lower().strip() for h in headers]
    
    # Check for Walmart format
    walmart_headers = [
        'walmart_calendar_week', 'walmart_item_number', 'item_name',
        'pos_sales_this_year', 'pos_quantity_this_year',
        'dollar_per_store_per_week_or_per_day_this_year',
        'units_per_store_per_week_or_per_day_this_year',
        'traited_store_count_this_year', 'repl_instock_percentage_this_year'
    ]
    if all(h in headers_lower for h in walmart_headers):
        return 'walmart'
    
    # Check for Target format
    target_headers = ['date', 'dpci', 'item description', 'sales $', 'sales u', 'sales $ pspw', 'sales u pspw', 'oos %']
    if all(h in headers_lower for h in target_headers):
        return 'target'
    
    # Check for CVS format
    cvs_headers = ['time', 'product', 'total sales $ wtd', 'total units wtd']
    if all(h in headers_lower for h in cvs_headers):
        return 'cvs'
    
    # Check for KeHe format
    kehe_headers = ['time frame', 'geography', 'description', 'dollars', 'units',
                    'average weekly dollars per store selling per item',
                    'average weekly units per store selling per item']
    if all(h in headers_lower for h in kehe_headers):
        return 'kehe'
    
    return None

def find_or_create_channel_item(channel_id, channel_code, channel_name):
    """Find or create ChannelItem and return the item_id"""
    # First, try to find existing ChannelItem by channel_code
    channel_item = ChannelItem.query.filter_by(
        channel_id=channel_id,
        channel_code=channel_code
    ).first()
    
    if channel_item:
        return channel_item.item_id, channel_item
    
    # If not found, we need to create both Item and ChannelItem
    # But we need a brand_id to create an Item. Since we don't have that info,
    # we'll need to handle this case - for now, we'll raise an error
    # In a real scenario, you might want to prompt for brand or have a default
    
    # Actually, let's check if we can find an item by essor_code matching channel_code
    # This is a fallback - if channel_code happens to match an essor_code
    item = Item.query.filter_by(essor_code=channel_code).first()
    
    if item:
        # Check if a channel_item already exists for this channel_id and item_id
        existing_channel_item = ChannelItem.query.filter_by(
            channel_id=channel_id,
            item_id=item.id
        ).first()
        
        if existing_channel_item:
            # Update the existing channel_item with the new channel_code and channel_name if needed
            updated = False
            if existing_channel_item.channel_code != channel_code:
                existing_channel_item.channel_code = channel_code
                updated = True
            if channel_name and existing_channel_item.channel_name != channel_name:
                existing_channel_item.channel_name = channel_name
                updated = True
            return item.id, existing_channel_item
        
        # Create ChannelItem linking to this item
        channel_item = ChannelItem(
            channel_id=channel_id,
            item_id=item.id,
            channel_code=channel_code,
            channel_name=channel_name or item.essor_name or channel_code
        )
        db.session.add(channel_item)
        db.session.flush()
        return item.id, channel_item
    
    # If we still can't find/create, return None for item_id
    # The caller will import the data without the item link, and the link can be added later
    print(f"  ⚠ Warning: No item found for channel_code '{channel_code}'. Importing without item link.")
    return None, None

def get_kehe_channel_id(geography):
    """Get channel_id for KeHe format based on GEOGRAPHY field"""
    geography_upper = geography.strip().upper()
    
    if geography_upper == "EREWHON MARKETS - TOTAL US":
        return 76
    elif geography_upper == "FRESH THYME MARKET - TOTAL US":
        return 77
    elif geography_upper == "SPROUTS FARMERS MARKET - TOTAL US W/O PL":
        return 5
    else:
        raise ValueError(f"Unknown KeHe geography: {geography}")

def process_walmart_row(row, row_num, results, dry_run):
    """Process a Walmart format row"""
    try:
        # Parse date
        week_str = row.get('walmart_calendar_week', '').strip()
        if not week_str:
            raise ValueError("Missing 'walmart_calendar_week' field")
        week_date = parse_yyyyww_to_monday(week_str)
        
        # Get channel_id = 2
        channel_id = 2
        channel = Channel.query.get(channel_id)
        if not channel:
            raise ValueError(f"Channel with id {channel_id} not found")
        
        # Get channel_code and channel_name
        channel_code = row.get('walmart_item_number', '').strip()
        channel_name = row.get('item_name', '').strip()
        
        if not channel_code:
            raise ValueError("Missing 'walmart_item_number' field")
        
        # Find or create channel_item
        item_id, channel_item = find_or_create_channel_item(channel_id, channel_code, channel_name)
        
        # Update channel_item name if provided
        if channel_item and channel_name and channel_item.channel_name != channel_name:
            channel_item.channel_name = channel_name
        
        # Get item to find brand_id (if item_id exists)
        brand_id = None
        if item_id:
            item = Item.query.get(item_id)
            if not item:
                raise ValueError(f"Item with id {item_id} not found")
            brand_id = item.brand_id
                
        # Parse numeric fields
        revenues = Decimal(str(parse_numeric_value(row.get('pos_sales_this_year', '0'), 0)))
        units = int(parse_numeric_value(row.get('pos_quantity_this_year', '0'), 0))
        usd_pspw = parse_numeric_value(row.get('dollar_per_store_per_week_or_per_day_this_year', ''), None)
        if usd_pspw is not None:
            usd_pspw = Decimal(str(usd_pspw))
        units_pspw = parse_numeric_value(row.get('units_per_store_per_week_or_per_day_this_year', ''), None)
        if units_pspw is not None:
            units_pspw = Decimal(str(units_pspw))
        stores = int(parse_numeric_value(row.get('traited_store_count_this_year', '0'), 0))
        instock = parse_percentage(row.get('repl_instock_percentage_this_year', ''))
        
        # Find or create/update sellthrough_data
        # Handle NULL item_id properly in query
        if item_id is None:
            existing = SellthroughData.query.filter(
                SellthroughData.date == week_date,
                SellthroughData.channel_id == channel_id,
                SellthroughData.item_id.is_(None),
                SellthroughData.customer_id.is_(None),
                SellthroughData.channel_code == channel_code
            ).first()
        else:
                    existing = SellthroughData.query.filter_by(
                        date=week_date,
                channel_id=channel_id,
                item_id=item_id,
                customer_id=None
                    ).first()
        
        if existing:
            existing.revenues = revenues
            existing.units = units
            existing.stores = stores
            existing.usd_pspw = usd_pspw
            existing.units_pspw = units_pspw
            existing.instock = instock
            existing.channel_code = channel_code
            existing.brand_id = brand_id
            results['updated'] += 1
        else:
            sellthrough = SellthroughData(
                date=week_date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                customer_id=None,
                revenues=revenues,
                units=units,
                stores=stores,
                usd_pspw=usd_pspw,
                units_pspw=units_pspw,
                instock=instock,
                channel_code=channel_code
            )
            db.session.add(sellthrough)
            results['created'] += 1
        
        results['processed'] += 1
        return True
    except Exception as e:
        error_msg = f"Row {row_num}: {str(e)}"
        print(f"  ✗ ERROR: {error_msg}")
        import traceback
        traceback_str = traceback.format_exc()
        print(f"  Traceback: {traceback_str}")
        results['errors'].append(error_msg)
        _save_import_error('csv', row, f"{error_msg}\n\n{traceback_str}", row_num)
        results['skipped'] += 1
        # Rollback the session to clear any pending changes
        try:
            db.session.rollback()
        except:
            pass
        return False

def process_target_row(row, row_num, results, dry_run):
    """Process a Target format row"""
    try:
        # Parse date
        date_str = row.get('Date', '').strip()
        if not date_str:
            raise ValueError("Missing 'Date' field")
        week_date = parse_dec_wk_to_monday(date_str)
        
        # Get channel_id = 1
        channel_id = 1
        channel = Channel.query.get(channel_id)
        if not channel:
            raise ValueError(f"Channel with id {channel_id} not found")
        
        # Get channel_code and channel_name
        channel_code = row.get('DPCI', '').strip()
        channel_name = row.get('Item Description', '').strip()
        
        if not channel_code:
            raise ValueError("Missing 'DPCI' field")
        
        # Find or create channel_item
        item_id, channel_item = find_or_create_channel_item(channel_id, channel_code, channel_name)
        
        # Update channel_item name if provided
        if channel_item and channel_name and channel_item.channel_name != channel_name:
            channel_item.channel_name = channel_name
        
        # Get item to find brand_id (if item_id exists)
        brand_id = None
        if item_id:
            item = Item.query.get(item_id)
            if not item:
                raise ValueError(f"Item with id {item_id} not found")
            brand_id = item.brand_id
        
        # Parse numeric fields
        revenues = Decimal(str(parse_numeric_value(row.get('Sales $', '0'), 0)))
        units = int(parse_numeric_value(row.get('Sales U', '0'), 0))
        usd_pspw = parse_numeric_value(row.get('Sales $ PSPW', ''), None)
        if usd_pspw is not None:
            usd_pspw = Decimal(str(usd_pspw))
        units_pspw = parse_numeric_value(row.get('Sales U PSPW', ''), None)
        if units_pspw is not None:
            units_pspw = Decimal(str(units_pspw))
        oos = parse_percentage(row.get('OOS %', ''))
        
        # Find or create/update sellthrough_data
        # Handle NULL item_id properly in query
        if item_id is None:
            existing = SellthroughData.query.filter(
                SellthroughData.date == week_date,
                SellthroughData.channel_id == channel_id,
                SellthroughData.item_id.is_(None),
                SellthroughData.customer_id.is_(None),
                SellthroughData.channel_code == channel_code
            ).first()
        else:
            existing = SellthroughData.query.filter_by(
                date=week_date,
                channel_id=channel_id,
                item_id=item_id,
                customer_id=None
            ).first()
        
        if existing:
            existing.revenues = revenues
            existing.units = units
            existing.usd_pspw = usd_pspw
            existing.units_pspw = units_pspw
            existing.oos = oos
            existing.channel_code = channel_code
            existing.brand_id = brand_id
            results['updated'] += 1
        else:
            sellthrough = SellthroughData(
                date=week_date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                customer_id=None,
                revenues=revenues,
                units=units,
                usd_pspw=usd_pspw,
                units_pspw=units_pspw,
                oos=oos,
                channel_code=channel_code
            )
            db.session.add(sellthrough)
            results['created'] += 1
        
        results['processed'] += 1
        return True
    except Exception as e:
        error_msg = f"Row {row_num}: {str(e)}"
        print(f"  ✗ ERROR: {error_msg}")
        import traceback
        traceback_str = traceback.format_exc()
        print(f"  Traceback: {traceback_str}")
        results['errors'].append(error_msg)
        _save_import_error('csv', row, f"{error_msg}\n\n{traceback_str}", row_num)
        results['skipped'] += 1
        # Rollback the session to clear any pending changes
        try:
            db.session.rollback()
        except:
            pass
        return False

def process_cvs_row(row, row_num, results, dry_run):
    """Process a CVS format row"""
    try:
        # Parse date
        time_str = row.get('Time', '').strip()
        if not time_str:
            raise ValueError("Missing 'Time' field")
        week_date = parse_fiscal_week_ending_to_monday(time_str)
        
        # Get channel_id = 3
        channel_id = 3
        channel = Channel.query.get(channel_id)
        if not channel:
            raise ValueError(f"Channel with id {channel_id} not found")
        
        # Get channel_code
        channel_code = row.get('Product', '').strip()
        if not channel_code:
            raise ValueError("Missing 'Product' field")
        
        # Find or create channel_item (no channel_name for CVS)
        item_id, channel_item = find_or_create_channel_item(channel_id, channel_code, None)
        
        # Get item to find brand_id (if item_id exists)
        brand_id = None
        if item_id:
            item = Item.query.get(item_id)
            if not item:
                raise ValueError(f"Item with id {item_id} not found")
            brand_id = item.brand_id
        
        # Parse numeric fields
        revenues = Decimal(str(parse_numeric_value(row.get('Total Sales $ WTD', '0'), 0)))
        units = int(parse_numeric_value(row.get('Total Units WTD', '0'), 0))
        
        # Find or create/update sellthrough_data
        existing = SellthroughData.query.filter_by(
            date=week_date,
            channel_id=channel_id,
            item_id=item_id,
            customer_id=None
        ).first()
        
        if existing:
            existing.revenues = revenues
            existing.units = units
            existing.channel_code = channel_code
            existing.brand_id = brand_id
            results['updated'] += 1
        else:
            sellthrough = SellthroughData(
                date=week_date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                customer_id=None,
                revenues=revenues,
                units=units,
                channel_code=channel_code
            )
            db.session.add(sellthrough)
            results['created'] += 1
        
        results['processed'] += 1
        return True
    except Exception as e:
        error_msg = f"Row {row_num}: {str(e)}"
        print(f"  ✗ ERROR: {error_msg}")
        import traceback
        traceback_str = traceback.format_exc()
        print(f"  Traceback: {traceback_str}")
        results['errors'].append(error_msg)
        _save_import_error('csv', row, f"{error_msg}\n\n{traceback_str}", row_num)
        results['skipped'] += 1
        return False

def process_kehe_row(row, row_num, results, dry_run):
    """Process a KeHe format row"""
    try:
        # Parse date
        time_frame = row.get('TIME FRAME', '').strip()
        if not time_frame:
            raise ValueError("Missing 'TIME FRAME' field")
        week_date = parse_excel_serial_to_monday(time_frame)
        
        # Get channel_id from GEOGRAPHY
        geography = row.get('GEOGRAPHY', '').strip()
        if not geography:
            raise ValueError("Missing 'GEOGRAPHY' field")
        channel_id = get_kehe_channel_id(geography)
        channel = Channel.query.get(channel_id)
        if not channel:
            raise ValueError(f"Channel with id {channel_id} not found")
        
        # Get channel_code
        channel_code = row.get('DESCRIPTION', '').strip()
        if not channel_code:
            raise ValueError("Missing 'DESCRIPTION' field")
        
        # Find or create channel_item (no channel_name for KeHe)
        item_id, channel_item = find_or_create_channel_item(channel_id, channel_code, None)
        
        # Get item to find brand_id (if item_id exists)
        brand_id = None
        if item_id:
            item = Item.query.get(item_id)
            if not item:
                raise ValueError(f"Item with id {item_id} not found")
            brand_id = item.brand_id
        
        # Parse numeric fields
        revenues = Decimal(str(parse_numeric_value(row.get('Dollars', '0'), 0)))
        units = int(parse_numeric_value(row.get('Units', '0'), 0))
        usd_pspw = parse_numeric_value(row.get('Average Weekly Dollars Per Store Selling Per Item', ''), None)
        if usd_pspw is not None:
            usd_pspw = Decimal(str(usd_pspw))
        units_pspw = parse_numeric_value(row.get('Average Weekly Units Per Store Selling Per Item', ''), None)
        if units_pspw is not None:
            units_pspw = Decimal(str(units_pspw))
        
        # Find or create/update sellthrough_data
        # Handle NULL item_id properly in query
        if item_id is None:
            existing = SellthroughData.query.filter(
                SellthroughData.date == week_date,
                SellthroughData.channel_id == channel_id,
                SellthroughData.item_id.is_(None),
                SellthroughData.customer_id.is_(None),
                SellthroughData.channel_code == channel_code
            ).first()
        else:
            existing = SellthroughData.query.filter_by(
                date=week_date,
                channel_id=channel_id,
                item_id=item_id,
                customer_id=None
            ).first()
        
        if existing:
            existing.revenues = revenues
            existing.units = units
            existing.usd_pspw = usd_pspw
            existing.units_pspw = units_pspw
            existing.channel_code = channel_code
            existing.brand_id = brand_id
            results['updated'] += 1
        else:
            sellthrough = SellthroughData(
                date=week_date,
                brand_id=brand_id,
                item_id=item_id,
                channel_id=channel_id,
                customer_id=None,
                revenues=revenues,
                units=units,
                usd_pspw=usd_pspw,
                units_pspw=units_pspw,
                channel_code=channel_code
            )
            db.session.add(sellthrough)
            results['created'] += 1
        
        results['processed'] += 1
        return True
    except Exception as e:
        error_msg = f"Row {row_num}: {str(e)}"
        print(f"  ✗ ERROR: {error_msg}")
        import traceback
        traceback_str = traceback.format_exc()
        print(f"  Traceback: {traceback_str}")
        results['errors'].append(error_msg)
        _save_import_error('csv', row, f"{error_msg}\n\n{traceback_str}", row_num)
        results['skipped'] += 1
        return False

@sellthrough_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    """Import sellthrough data from CSV file with format detection"""
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
        
        # Get column names and detect format
        csv_columns = csv_reader.fieldnames
        print(f"\n📋 CSV Columns detected: {', '.join(csv_columns)}")
        
        csv_format = detect_csv_format(csv_columns)
        if not csv_format:
            flash('Unrecognized CSV format. Please ensure the CSV matches one of the supported formats (Walmart, Target, CVS, or KeHe).', 'error')
            return render_template('sellthrough/import.html')
        
        print(f"✓ Detected format: {csv_format.upper()}")
        print("-"*60)
        
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
        
        # Process each row based on format
        for row_num, row in enumerate(rows_to_process, start=2):  # Start at 2 (header is row 1)
            if row_num % 10 == 0 or row_num == 2:
                print(f"Processing row {row_num}/{total_rows + 1}...")
            
            # Route to appropriate format processor
            if csv_format == 'walmart':
                process_walmart_row(row, row_num, results, dry_run)
            elif csv_format == 'target':
                process_target_row(row, row_num, results, dry_run)
            elif csv_format == 'cvs':
                process_cvs_row(row, row_num, results, dry_run)
            elif csv_format == 'kehe':
                process_kehe_row(row, row_num, results, dry_run)
            else:
                error_msg = f"Row {row_num}: Unknown format {csv_format}"
                results['errors'].append(error_msg)
                _save_import_error('csv', row, error_msg, row_num)
                results['skipped'] += 1
        
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

@sellthrough_bp.route('/unlinked')
@login_required
def unlinked():
    """List sellthrough data without item_id and brand_id, grouped by channel_code"""
    channel_id = request.args.get('channel_id', type=int)
    
    # Query for sellthrough data without item_id and brand_id
    query = SellthroughData.query.filter(
        SellthroughData.item_id.is_(None),
        SellthroughData.brand_id.is_(None)
    )
    
    if channel_id:
        query = query.filter(SellthroughData.channel_id == channel_id)
    
    # Get all unlinked data
    unlinked_data = query.order_by(SellthroughData.channel_id, SellthroughData.channel_code, SellthroughData.date.desc()).all()
    
    # Group by channel_code and channel_id (use composite key)
    grouped_data = {}
    for data in unlinked_data:
        channel_code = data.channel_code or 'NO_CODE'
        # Create a composite key to handle same channel_code in different channels
        group_key = f"{data.channel_id}_{channel_code}"
        
        if group_key not in grouped_data:
            grouped_data[group_key] = {
                'channel_code': channel_code,
                'channel_id': data.channel_id,
                'channel_name': data.channel.name if data.channel else 'Unknown',
                'count': 0,
                'first_date': data.date,
                'last_date': data.date,
                'total_revenues': Decimal('0'),
                'total_units': 0
            }
        
        grouped_data[group_key]['count'] += 1
        if data.date < grouped_data[group_key]['first_date']:
            grouped_data[group_key]['first_date'] = data.date
        if data.date > grouped_data[group_key]['last_date']:
            grouped_data[group_key]['last_date'] = data.date
        grouped_data[group_key]['total_revenues'] += data.revenues or Decimal('0')
        grouped_data[group_key]['total_units'] += data.units or 0
    
    # Get channels for filter
    channels = Channel.query.order_by(Channel.name).all()
    
    return render_template('sellthrough/unlinked.html',
                         grouped_data=grouped_data,
                         channels=channels,
                         selected_channel_id=channel_id)

@sellthrough_bp.route('/api/search-items')
@login_required
def api_search_items():
    """API endpoint to search items by code and name"""
    search_term = request.args.get('q', '').strip()
    if not search_term:
        return jsonify([])
    
    # Search in essor_code and essor_name
    search_pattern = f'%{search_term}%'
    items = Item.query.filter(
        db.or_(
            Item.essor_code.ilike(search_pattern),
            Item.essor_name.ilike(search_pattern)
        )
    ).order_by(Item.essor_code).limit(50).all()
    
    return jsonify([{
        'id': item.id,
        'essor_code': item.essor_code or '',
        'essor_name': item.essor_name or '',
        'brand_id': item.brand_id,
        'brand_name': item.brand.name if item.brand else '',
        'display': f"{item.essor_code or 'N/A'} - {item.essor_name or 'N/A'}"
    } for item in items])

@sellthrough_bp.route('/link-item', methods=['POST'])
@login_required
def link_item():
    """Link a channel_code to an item - updates sellthrough_data and creates channel_item"""
    try:
        data = request.get_json()
        channel_code = data.get('channel_code')
        item_id = data.get('item_id')
        channel_id = data.get('channel_id')
        
        if not channel_code or not item_id or not channel_id:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Get the item to get brand_id
        item = Item.query.get(item_id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        brand_id = item.brand_id
        
        # Get all sellthrough_data entries with this channel_code and channel_id that don't have item_id
        sellthrough_entries = SellthroughData.query.filter(
            SellthroughData.channel_code == channel_code,
            SellthroughData.channel_id == channel_id,
            SellthroughData.item_id.is_(None),
            SellthroughData.brand_id.is_(None)
        ).all()
        
        if not sellthrough_entries:
            return jsonify({'error': 'No unlinked sellthrough data found for this channel_code'}), 404
        
        # Check if channel_item already exists
        channel_item = ChannelItem.query.filter_by(
            channel_id=channel_id,
            item_id=item_id
        ).first()
        
        # Get channel_name from item
        channel_name = item.essor_name or item.essor_code or channel_code
        
        # If channel_item doesn't exist, create it
        if not channel_item:
            channel_item = ChannelItem(
                channel_id=channel_id,
                item_id=item_id,
                channel_code=channel_code,
                channel_name=channel_name
            )
            db.session.add(channel_item)
        else:
            # Update channel_code and channel_name if they're different
            if channel_item.channel_code != channel_code:
                channel_item.channel_code = channel_code
            if channel_item.channel_name != channel_name:
                channel_item.channel_name = channel_name
        
        # Update all sellthrough_data entries
        for entry in sellthrough_entries:
            entry.item_id = item_id
            entry.brand_id = brand_id
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'updated_count': len(sellthrough_entries),
            'message': f'Successfully linked {len(sellthrough_entries)} entries to item {item.essor_code}'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

