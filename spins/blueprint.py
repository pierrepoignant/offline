#!/usr/bin/env python3
"""
SPINS blueprint for managing SPINS data
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io
import re
from sqlalchemy import func
from models import db, SpinsData, SpinsChannel, SpinsBrand, SpinsItem, ImportError
from auth.blueprint import login_required, admin_required
import json
import requests
import configparser
import os

spins_bp = Blueprint('spins', __name__, template_folder='templates')

def get_rapidapi_big_product_credentials():
    """Read RapidAPI Big Product Data credentials from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    api_key = config.get('rapidapi', 'x-rapidapi-key', fallback=None)
    api_host = config.get('rapidapi', 'x-rapidapi-big-product-host', fallback=None)
    if api_key:
        api_key = api_key.strip()
    if api_host:
        api_host = api_host.strip()
    return api_key, api_host

def check_image_url(image_url, timeout=5):
    """
    Check if an image URL is accessible.
    
    Args:
        image_url: URL to check
        timeout: Request timeout in seconds
    
    Returns:
        True if image is accessible, False otherwise
    """
    if not image_url:
        return False
    
    try:
        # First try HEAD request (faster, doesn't download image)
        try:
            response = requests.head(image_url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type:
                    return True
        except requests.exceptions.RequestException:
            pass
        
        # If HEAD fails, try GET with stream=True (only download headers)
        try:
            response = requests.get(image_url, timeout=timeout, allow_redirects=True, stream=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type:
                    response.close()  # Close the connection
                    return True
            if response:
                response.close()
        except requests.exceptions.RequestException:
            pass
        
        return False
    except Exception:
        return False

def extract_and_compute_upc(upc_string):
    """
    Extract last 11 digits from UPC string and compute check digit.
    
    Args:
        upc_string: UPC string in format like "00-00093-56859"
    
    Returns:
        Complete 12-digit UPC with check digit (e.g., "00009356859X")
    """
    # Remove all non-digit characters
    digits_only = ''.join(filter(str.isdigit, upc_string))
    
    # Get last 11 digits
    if len(digits_only) < 11:
        raise ValueError(f"UPC string must contain at least 11 digits, got: {upc_string}")
    
    last_11_digits = digits_only[-11:]
    
    # Calculate check digit (UPC-A algorithm)
    # Sum of digits in odd positions (1st, 3rd, 5th, 7th, 9th, 11th) * 3
    odd_sum = sum(int(last_11_digits[i]) for i in range(0, 11, 2)) * 3
    
    # Sum of digits in even positions (2nd, 4th, 6th, 8th, 10th)
    even_sum = sum(int(last_11_digits[i]) for i in range(1, 11, 2))
    
    # Total sum
    total = odd_sum + even_sum
    
    # Check digit is the remainder when divided by 10, then 10 - remainder (or 0 if remainder is 0)
    remainder = total % 10
    check_digit = 0 if remainder == 0 else 10 - remainder
    
    # Return complete 12-digit UPC
    computed_upc = last_11_digits + str(check_digit)
    
    return computed_upc

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
        db.session.flush()
    except Exception as e:
        print(f"  ⚠ Warning: Could not save import error to database: {str(e)}")

def _parse_time_frame(time_frame_str):
    """Parse TIME FRAME field to extract date from format like '1 Week End 12/29/2024'"""
    if not time_frame_str:
        return None
    
    # Try to extract date from patterns like "1 Week End 12/29/2024" or "Week End 12/29/2024"
    # Look for date pattern MM/DD/YYYY or M/D/YYYY
    date_pattern = r'(\d{1,2})/(\d{1,2})/(\d{4})'
    match = re.search(date_pattern, time_frame_str)
    
    if match:
        month, day, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            return None
    return None

def _parse_currency(value_str):
    """Parse currency string like '$68,126.93' to Decimal"""
    if not value_str:
        return Decimal('0')
    
    # Remove $ and commas
    cleaned = str(value_str).replace('$', '').replace(',', '').strip()
    try:
        return Decimal(cleaned)
    except:
        return Decimal('0')

def _parse_number(value_str):
    """Parse number string that might have commas and decimals"""
    if not value_str:
        return 0
    
    # Remove commas
    cleaned = str(value_str).replace(',', '').strip()
    try:
        # Try integer first
        if '.' in cleaned:
            return float(cleaned)
        return int(cleaned)
    except:
        return 0

@spins_bp.route('/')
@login_required
def index():
    """SPINS data list"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    brand_id = request.args.get('brand_id', type=int)
    item_id = request.args.get('item_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = SpinsData.query
    
    if brand_id:
        query = query.filter_by(brand_id=brand_id)
    if item_id:
        query = query.filter_by(item_id=item_id)
    if channel_id:
        query = query.filter_by(channel_id=channel_id)
    if date_from:
        query = query.filter(SpinsData.week >= datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        query = query.filter(SpinsData.week <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    spins_data = query.order_by(SpinsData.week.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get filter options
    brands = SpinsBrand.query.order_by(SpinsBrand.name).all()
    items = SpinsItem.query.order_by(SpinsItem.upc).all()
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    
    return render_template('spins/index.html', 
                         spins_data=spins_data,
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

@spins_bp.route('/dashboard')
@login_required
def dashboard():
    """SPINS dashboard with chart"""
    # Get all brands, items, and channels for filters
    brands = SpinsBrand.query.order_by(SpinsBrand.name).all()
    items = SpinsItem.query.order_by(SpinsItem.upc).all()
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    
    return render_template('spins/dashboard.html',
                         brands=brands,
                         items=items,
                         channels=channels)

@spins_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """API endpoint to get chart data based on filters"""
    try:
        # Get filter parameters
        time_period = request.args.get('time_period', 'last_12_weeks')
        metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'

        brand_ids = request.args.getlist('brand_id', type=int)  # Support multiple brands
        item_id = request.args.get('item_id', type=int)
        channel_id = request.args.get('channel_id', type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Calculate date range based on time period
        today = datetime.now().date()
        if time_period == 'last_12_weeks':
            start_date = today - timedelta(weeks=12)
            end_date = today
        elif time_period == 'last_4_weeks':
            start_date = today - timedelta(weeks=4)
            end_date = today
        elif time_period == 'year_to_date':
            start_date = datetime(today.year, 1, 1).date()
            end_date = today
        elif time_period == 'since_jan_2024':
            start_date = datetime(2024, 1, 1).date()
            end_date = today
        elif time_period == 'custom':
            if date_from:
                start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            else:
                start_date = today - timedelta(weeks=12)
            if date_to:
                end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            else:
                end_date = today
        else:
            start_date = today - timedelta(weeks=12)
            end_date = today
        
        # Build base filter for getting all weeks (apply channel/item filters if specified)
        base_week_filter = db.session.query(SpinsData.week).filter(
            SpinsData.week >= start_date,
            SpinsData.week <= end_date
        )
        
        # Apply channel and item filters to week query too
        if item_id:
            base_week_filter = base_week_filter.filter(SpinsData.item_id == item_id)
        if channel_id:
            base_week_filter = base_week_filter.filter(SpinsData.channel_id == channel_id)
        
        # Get all unique weeks in the date range (with filters applied)
        all_weeks_query = base_week_filter.distinct().order_by(SpinsData.week)
        all_weeks = [w.week for w in all_weeks_query.all()]
        dates = [week.strftime('%Y-%m-%d') for week in all_weeks]
        
        # If no brands selected, return aggregated data
        if not brand_ids:
            # Build query - group by week
            query = db.session.query(
                SpinsData.week,
                func.sum(SpinsData.units).label('total_units'),
                func.sum(SpinsData.revenues).label('total_revenues')
            ).filter(
                SpinsData.week >= start_date,
                SpinsData.week <= end_date
            )
            
            # Apply filters
            if item_id:
                query = query.filter(SpinsData.item_id == item_id)
            if channel_id:
                query = query.filter(SpinsData.channel_id == channel_id)
            
            # Group by week and order by week
            query = query.group_by(SpinsData.week).order_by(SpinsData.week)
            
            # Execute query
            results = query.all()
            
            # Create a dictionary for quick lookup
            week_data = {result.week: result for result in results}
            
            # Prepare data for chart
            if metric == 'units':
                values = [float(week_data[week].total_units) if week in week_data and week_data[week].total_units else 0 for week in all_weeks]
                metric_label = 'Units'
            else:  # revenues
                values = [float(week_data[week].total_revenues) if week in week_data and week_data[week].total_revenues else 0 for week in all_weeks]
                metric_label = 'Revenues ($)'
            
            return jsonify({
                'dates': dates,
                'values': values,
                'metric_label': metric_label,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d')
            })
        
        # Multiple brands selected - return data per brand
        # Remove duplicates from brand_ids
        brand_ids = list(dict.fromkeys(brand_ids))  # Preserves order while removing duplicates
        brands_data = []
        brand_colors = [
            'rgb(159, 122, 234)',  # Purple
            'rgb(66, 153, 225)',   # Blue
            'rgb(72, 187, 120)',   # Green
            'rgb(237, 137, 54)',   # Orange
            'rgb(245, 101, 101)',  # Red
            'rgb(156, 163, 175)',  # Gray
            'rgb(251, 191, 36)',   # Yellow
            'rgb(139, 92, 246)',   # Indigo
            'rgb(236, 72, 153)',   # Pink
            'rgb(20, 184, 166)',    # Teal
        ]
        
        for idx, brand_id in enumerate(brand_ids):
            brand = SpinsBrand.query.get(brand_id)
            if not brand:
                continue
            
            # Build query - group by week and brand
            query = db.session.query(
                SpinsData.week,
                func.sum(SpinsData.units).label('total_units'),
                func.sum(SpinsData.revenues).label('total_revenues')
            ).filter(
                SpinsData.week >= start_date,
                SpinsData.week <= end_date,
                SpinsData.brand_id == brand_id
            )
            
            # Apply filters
            if item_id:
                query = query.filter(SpinsData.item_id == item_id)
            if channel_id:
                query = query.filter(SpinsData.channel_id == channel_id)
            
            # Group by week and order by week
            query = query.group_by(SpinsData.week).order_by(SpinsData.week)
            
            # Execute query
            results = query.all()
            
            # Create a dictionary for quick lookup
            week_data = {result.week: result for result in results}
            
            # Prepare data for chart
            if metric == 'units':
                values = [float(week_data[week].total_units) if week in week_data and week_data[week].total_units else 0 for week in all_weeks]
                metric_label = 'Units'
            else:  # revenues
                values = [float(week_data[week].total_revenues) if week in week_data and week_data[week].total_revenues else 0 for week in all_weeks]
                metric_label = 'Revenues ($)'
            
            color = brand_colors[idx % len(brand_colors)]
            brands_data.append({
                'brand_id': brand_id,
                'brand_name': brand.name,
                'values': values,
                'color': color
            })
        
        return jsonify({
            'dates': dates,
            'brands_data': brands_data,
            'metric_label': metric_label,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@spins_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    """Import SPINS data from CSV file"""
    if request.method == 'GET':
        return render_template('spins/import.html')
    
    # Check for dry-run mode
    dry_run = request.form.get('dry_run') == 'true'
    max_rows = 10 if dry_run else None
    
    # Handle file upload
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return render_template('spins/import.html')
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return render_template('spins/import.html')
    
    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return render_template('spins/import.html')
    
    # Read CSV file
    try:
        mode_text = "DRY-RUN (first 10 rows only, no database changes)" if dry_run else "LIVE IMPORT"
        print("\n" + "="*60)
        print(f"Starting SPINS CSV Import Process - {mode_text}")
        print("="*60)
        
        # Read and decode file, handling BOM
        file_content = file.stream.read()
        decoded_content = file_content.decode("UTF-8-sig")  # UTF-8-sig handles BOM automatically
        stream = io.StringIO(decoded_content, newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Get column names and normalize them (strip whitespace and BOM)
        csv_columns = csv_reader.fieldnames
        if csv_columns:
            # Normalize column names: strip BOM, whitespace, and convert to standard format
            normalized_columns = {}
            for col in csv_columns:
                normalized_col = col.strip().lstrip('\ufeff')  # Remove BOM and whitespace
                if col != normalized_col:
                    normalized_columns[col] = normalized_col
            
            # If we found normalized columns, we'll need to remap them
            if normalized_columns:
                print(f"\n⚠️  Column name normalization needed:")
                for old, new in normalized_columns.items():
                    print(f"   '{old}' -> '{new}'")
        
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
        
        # Helper function to get field value with normalization
        def get_field(row, field_name):
            """Get field value, trying both original and normalized names"""
            # Try exact match first
            if field_name in row:
                return row[field_name]
            # Try with BOM prefix
            if f'\ufeff{field_name}' in row:
                return row[f'\ufeff{field_name}']
            # Try with leading/trailing spaces
            for key in row.keys():
                if key.strip().lstrip('\ufeff') == field_name:
                    return row[key]
            return None
        
        # Process each row
        for row_num, row in enumerate(rows_to_process, start=2):  # Start at 2 (header is row 1)
            if row_num % 100 == 0 or row_num == 2:
                print(f"Processing row {row_num}/{total_rows + 1}...")
            try:
                # Parse TIME FRAME to get week date
                time_frame_raw = get_field(row, 'TIME FRAME')
                time_frame = time_frame_raw.strip() if time_frame_raw else ''
                if not time_frame:
                    # Debug: show available keys
                    available_keys = list(row.keys())
                    error_msg = f"Row {row_num}: Missing 'TIME FRAME' field. Available columns: {', '.join(available_keys[:5])}..."
                    print(f"  ⚠️  {error_msg}")
                    if row_num <= 5:  # Only print first few rows for debugging
                        print(f"     Row keys: {available_keys}")
                        print(f"     Row data sample: {dict(list(row.items())[:3])}")
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                week_date = _parse_time_frame(time_frame)
                if not week_date:
                    error_msg = f"Row {row_num}: Invalid TIME FRAME format: '{time_frame}'"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                # Find or create channel (GEOGRAPHY)
                geography_raw = get_field(row, 'GEOGRAPHY')
                geography = geography_raw.strip() if geography_raw else ''
                if not geography:
                    error_msg = f"Row {row_num}: Missing 'GEOGRAPHY' field"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                channel = SpinsChannel.query.filter_by(name=geography).first()
                if not channel:
                    print(f"  ➕ Creating new channel: {geography}")
                    channel = SpinsChannel(name=geography, short_name=geography[:50] if len(geography) > 50 else geography)
                    db.session.add(channel)
                    db.session.flush()
                    results['created'] += 1
                else:
                    print(f"  ✓ Found channel: {geography}")
                
                # Find or create brand (BRAND)
                brand_name_raw = get_field(row, 'BRAND')
                brand_name = brand_name_raw.strip() if brand_name_raw else ''
                if not brand_name:
                    error_msg = f"Row {row_num}: Missing 'BRAND' field"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                brand = SpinsBrand.query.filter_by(name=brand_name).first()
                if not brand:
                    print(f"  ➕ Creating new brand: {brand_name}")
                    brand = SpinsBrand(name=brand_name, short_name=brand_name[:50] if len(brand_name) > 50 else brand_name)
                    db.session.add(brand)
                    db.session.flush()
                    results['created'] += 1
                else:
                    print(f"  ✓ Found brand: {brand_name}")
                
                # Find or create item (UPC and DESCRIPTION)
                upc_raw = get_field(row, 'UPC')
                upc = upc_raw.strip() if upc_raw else ''
                description_raw = get_field(row, 'DESCRIPTION')
                description = description_raw.strip() if description_raw else ''
                
                if not upc:
                    error_msg = f"Row {row_num}: Missing 'UPC' field"
                    results['errors'].append(error_msg)
                    _save_import_error('csv', row, error_msg, row_num)
                    results['skipped'] += 1
                    continue
                
                item = SpinsItem.query.filter_by(upc=upc).first()
                if not item:
                    print(f"  ➕ Creating new item: UPC={upc}, name={description}")
                    item = SpinsItem(
                        upc=upc,
                        name=description or 'Unknown',
                        short_name=(description[:50] if description and len(description) > 50 else description) or None
                    )
                    db.session.add(item)
                    db.session.flush()
                    results['created'] += 1
                else:
                    # Update item name if description changed
                    if description and item.name != description:
                        print(f"  ↻ Updating item name: {item.name} -> {description}")
                        item.name = description
                        if description and len(description) > 50:
                            item.short_name = description[:50]
                    print(f"  ✓ Found item: {upc}")
                
                # Parse numeric fields
                stores_total = int(_parse_number(get_field(row, '# of Stores') or '0'))
                stores_selling = Decimal(str(_parse_number(get_field(row, '# of Stores Selling') or '0')))
                revenues = _parse_currency(get_field(row, 'Dollars') or '0')
                units = int(_parse_number(get_field(row, 'Units') or '0'))
                arp_raw = get_field(row, 'ARP')
                arp = _parse_currency(arp_raw) if arp_raw else None
                avg_weekly_rev_raw = get_field(row, 'Average Weekly Dollars Per Store Selling Per Item')
                avg_weekly_rev = _parse_currency(avg_weekly_rev_raw) if avg_weekly_rev_raw else None
                avg_weekly_units_raw = get_field(row, 'Average Weekly Units Per Store Selling Per Item')
                avg_weekly_units = Decimal(str(_parse_number(avg_weekly_units_raw))) if avg_weekly_units_raw else None
                
                # Check for existing record
                existing = SpinsData.query.filter(
                    SpinsData.week == week_date,
                    SpinsData.channel_id == channel.id,
                    SpinsData.brand_id == brand.id,
                    SpinsData.item_id == item.id
                ).first()
                
                if existing:
                    # Update existing record
                    print(f"  ↻ Updating existing SPINS data (ID: {existing.id})")
                    existing.stores_total = stores_total
                    existing.stores_selling = stores_selling
                    existing.revenues = revenues
                    existing.units = units
                    existing.arp = arp
                    existing.average_weekly_revenues_per_selling_item = avg_weekly_rev
                    existing.average_weekly_units_per_selling_item = avg_weekly_units
                    results['updated'] += 1
                    results['processed'] += 1
                else:
                    # Create new record
                    print(f"  ➕ Creating new SPINS data: week={week_date}, channel={channel.name}, brand={brand.name}, item={item.upc}")
                    spins_data = SpinsData(
                        week=week_date,
                        channel_id=channel.id,
                        brand_id=brand.id,
                        item_id=item.id,
                        stores_total=stores_total,
                        stores_selling=stores_selling,
                        revenues=revenues,
                        units=units,
                        arp=arp,
                        average_weekly_revenues_per_selling_item=avg_weekly_rev,
                        average_weekly_units_per_selling_item=avg_weekly_units
                    )
                    db.session.add(spins_data)
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
                    if not dry_run:
                        db.session.commit()
                except:
                    pass
                results['skipped'] += 1
                if not dry_run:
                    db.session.begin()
                continue
        
        # Commit all changes (only if not dry-run)
        if dry_run:
            db.session.rollback()
            print("\n⚠ DRY-RUN: No changes saved to database")
        else:
            print("\n💾 Committing all changes...")
            try:
                db.session.commit()
                print("✓ All changes committed successfully")
            except Exception as e:
                print(f"✗ Error committing: {str(e)}")
                db.session.rollback()
                raise
        
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
        
        return render_template('spins/import.html', results=results, dry_run=dry_run)
        
    except Exception as e:
        db.session.rollback()
        error_msg = f'Error importing CSV: {str(e)}'
        print(f"\n✗ ERROR: {error_msg}")
        import traceback
        print(traceback.format_exc())
        flash(error_msg, 'error')
        return render_template('spins/import.html')

# ==================== SPINS Brands ====================

@spins_bp.route('/brands')
@login_required
def brands_list():
    """List all SPINS brands"""
    brands = SpinsBrand.query.order_by(SpinsBrand.name).all()
    return render_template('spins/brands_list.html', brands=brands)

@spins_bp.route('/brands/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_brand():
    """Create a new SPINS brand"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        
        if not name:
            flash('Brand name is required', 'error')
            return render_template('spins/edit_brand.html')
        
        if SpinsBrand.query.filter_by(name=name).first():
            flash('Brand with this name already exists', 'error')
            return render_template('spins/edit_brand.html')
        
        brand = SpinsBrand(name=name, short_name=short_name)
        db.session.add(brand)
        db.session.commit()
        flash(f'Brand "{name}" created successfully', 'success')
        return redirect(url_for('spins.brands_list'))
    
    return render_template('spins/edit_brand.html')

@spins_bp.route('/brands/<int:brand_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_brand(brand_id):
    """Edit a SPINS brand"""
    brand = SpinsBrand.query.get_or_404(brand_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        
        if not name:
            flash('Brand name is required', 'error')
            return render_template('spins/edit_brand.html', brand=brand)
        
        existing = SpinsBrand.query.filter_by(name=name).first()
        if existing and existing.id != brand_id:
            flash('Brand with this name already exists', 'error')
            return render_template('spins/edit_brand.html', brand=brand)
        
        brand.name = name
        brand.short_name = short_name
        db.session.commit()
        flash(f'Brand updated successfully', 'success')
        return redirect(url_for('spins.brands_list'))
    
    return render_template('spins/edit_brand.html', brand=brand)

@spins_bp.route('/brands/<int:brand_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_brand(brand_id):
    """Delete a SPINS brand"""
    brand = SpinsBrand.query.get_or_404(brand_id)
    name = brand.name
    
    # Check if brand has data
    data_count = SpinsData.query.filter_by(brand_id=brand_id).count()
    if data_count > 0:
        flash(f'Cannot delete brand "{name}" because it has {data_count} associated data record(s). Please delete data first.', 'error')
        return redirect(url_for('spins.brands_list'))
    
    db.session.delete(brand)
    db.session.commit()
    flash(f'Brand "{name}" deleted successfully', 'success')
    return redirect(url_for('spins.brands_list'))

# ==================== SPINS Items ====================

@spins_bp.route('/items')
@login_required
def items_list():
    """List all SPINS items with their most common brand"""
    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    brand_id = request.args.get('brand_id', type=int)
    search = request.args.get('search', '').strip()
    per_page = 50
    
    # Build base query
    query = SpinsItem.query
    
    # Apply search filter
    if search:
        query = query.filter(SpinsItem.name.ilike(f'%{search}%'))
    
    # Apply brand filter (filter by items that have data with this brand)
    if brand_id:
        # Get item IDs that have data with this brand
        item_ids_with_brand = db.session.query(SpinsData.item_id).filter(
            SpinsData.brand_id == brand_id
        ).distinct().subquery()
        query = query.filter(SpinsItem.id.in_(db.session.query(item_ids_with_brand.c.item_id)))
    
    # Order and paginate
    query = query.order_by(SpinsItem.upc)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # For each item, get the most common brand
    items_with_brands = []
    for item in pagination.items:
        # Query to find the brand that appears most frequently for this item
        brand_counts = db.session.query(
            SpinsBrand.id,
            SpinsBrand.name,
            func.count(SpinsData.id).label('count')
        ).join(
            SpinsData, SpinsData.brand_id == SpinsBrand.id
        ).filter(
            SpinsData.item_id == item.id
        ).group_by(
            SpinsBrand.id,
            SpinsBrand.name
        ).order_by(
            func.count(SpinsData.id).desc()
        ).first()
        
        # Get the brand object if found
        brand = None
        if brand_counts:
            brand = SpinsBrand.query.get(brand_counts.id)
        
        items_with_brands.append({
            'item': item,
            'brand': brand
        })
    
    # Get all brands for filter dropdown
    all_brands = SpinsBrand.query.order_by(SpinsBrand.name).all()
    
    return render_template('spins/items_list.html', 
                         items=items_with_brands,
                         pagination=pagination,
                         brands=all_brands,
                         current_filters={
                             'brand_id': brand_id,
                             'search': search
                         })

@spins_bp.route('/items/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_item():
    """Create a new SPINS item"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        upc = request.form.get('upc', '').strip()
        
        if not all([name, upc]):
            flash('Item name and UPC are required', 'error')
            return render_template('spins/edit_item.html')
        
        if SpinsItem.query.filter_by(upc=upc).first():
            flash('Item with this UPC already exists', 'error')
            return render_template('spins/edit_item.html')
        
        item = SpinsItem(name=name, short_name=short_name, upc=upc)
        db.session.add(item)
        db.session.commit()
        flash(f'Item "{name}" created successfully', 'success')
        return redirect(url_for('spins.items_list'))
    
    return render_template('spins/edit_item.html')

@spins_bp.route('/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_item(item_id):
    """Edit a SPINS item"""
    item = SpinsItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        upc = request.form.get('upc', '').strip()
        
        if not all([name, upc]):
            flash('Item name and UPC are required', 'error')
            return render_template('spins/edit_item.html', item=item)
        
        existing = SpinsItem.query.filter_by(upc=upc).first()
        if existing and existing.id != item_id:
            flash('Item with this UPC already exists', 'error')
            return render_template('spins/edit_item.html', item=item)
        
        item.name = name
        item.short_name = short_name
        item.upc = upc
        db.session.commit()
        flash(f'Item updated successfully', 'success')
        return redirect(url_for('spins.items_list'))
    
    return render_template('spins/edit_item.html', item=item)

@spins_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_item(item_id):
    """Delete a SPINS item"""
    item = SpinsItem.query.get_or_404(item_id)
    name = item.name
    
    # Check if item has data
    data_count = SpinsData.query.filter_by(item_id=item_id).count()
    if data_count > 0:
        flash(f'Cannot delete item "{name}" because it has {data_count} associated data record(s). Please delete data first.', 'error')
        return redirect(url_for('spins.items_list'))
    
    db.session.delete(item)
    db.session.commit()
    flash(f'Item "{name}" deleted successfully', 'success')
    return redirect(url_for('spins.items_list'))

@spins_bp.route('/items/<int:item_id>/view')
@login_required
def view_item_scraped_data(item_id):
    """View scraped data for a SPINS item"""
    item = SpinsItem.query.get_or_404(item_id)
    
    if not item.scrapped_json:
        flash('No scraped data available for this item', 'error')
        return redirect(url_for('spins.items_list'))
    
    try:
        scraped_data = json.loads(item.scrapped_json)
    except json.JSONDecodeError:
        flash('Invalid scraped data format', 'error')
        return redirect(url_for('spins.items_list'))
    
    # Get brand from most common brand in spins_data
    brand = None
    brand_counts = db.session.query(
        SpinsBrand.id,
        SpinsBrand.name,
        func.count(SpinsData.id).label('count')
    ).join(
        SpinsData, SpinsData.brand_id == SpinsBrand.id
    ).filter(
        SpinsData.item_id == item.id
    ).group_by(
        SpinsBrand.id,
        SpinsBrand.name
    ).order_by(
        func.count(SpinsData.id).desc()
    ).first()
    
    if brand_counts:
        brand = SpinsBrand.query.get(brand_counts.id)
    
    return render_template('spins/view_scraped_data.html', 
                         item=item, 
                         scraped_data=scraped_data,
                         brand=brand)

@spins_bp.route('/items/<int:item_id>/scrape', methods=['POST'])
@login_required
def scrape_item(item_id):
    """Scrape item data from RapidAPI Big Product Data"""
    item = SpinsItem.query.get_or_404(item_id)
    
    if not item.upc:
        flash(f'Item "{item.name}" does not have a UPC', 'error')
        return redirect(url_for('spins.items_list'))
    
    # Extract and compute UPC
    try:
        computed_upc = extract_and_compute_upc(item.upc)
        print(f"\n{'='*60}")
        print(f"🔄 UPC Processing for Item: {item.name}")
        print(f"   Original UPC: {item.upc}")
        print(f"   Computed UPC: {computed_upc}")
        print(f"{'='*60}")
    except ValueError as e:
        error_msg = f"Invalid UPC format: {str(e)}"
        print(f"   ✗ ERROR: {error_msg}")
        flash(error_msg, 'error')
        return redirect(url_for('spins.items_list'))
    
    # Get API credentials
    api_key, api_host = get_rapidapi_big_product_credentials()
    
    if not api_key or not api_host:
        flash('RapidAPI credentials not configured', 'error')
        return redirect(url_for('spins.items_list'))
    
    # Make API request
    url = f'https://{api_host}/gtin/{computed_upc}'
    headers = {
        'x-rapidapi-host': api_host,
        'x-rapidapi-key': api_key
    }
    
    print(f"\n🌐 Making API Request")
    print(f"   URL: {url}")
    print(f"   Host: {api_host}")
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        print(f"   Response Status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_data.get('error', error_msg))
                print(f"   ✗ API Error Response: {json.dumps(error_data, indent=2)}")
            except:
                error_text = response.text[:500] if response.text else 'No response body'
                error_msg = f"{error_msg}: {error_text}"
                print(f"   ✗ API Error Text: {error_text}")
            flash(f'Error scraping item: {error_msg}', 'error')
            return redirect(url_for('spins.items_list'))
        
        data = response.json()
        
        print(f"\n✓ API Call Successful")
        print(f"   Response Data Summary:")
        if 'gtin' in data:
            print(f"   - GTIN: {data['gtin']}")
        if 'properties' in data:
            props = data['properties']
            if 'title' in props:
                title_count = len(props['title']) if isinstance(props['title'], list) else 1
                print(f"   - Titles: {title_count}")
            if 'brand' in props:
                brand_count = len(props['brand']) if isinstance(props['brand'], list) else 1
                print(f"   - Brands: {brand_count}")
        if 'stores' in data:
            store_count = len(data['stores']) if isinstance(data['stores'], list) else 0
            print(f"   - Stores: {store_count}")
        
        print(f"\n📋 Full API Response:")
        print(json.dumps(data, indent=2))
        print(f"\n{'='*60}\n")
        
        # Extract data from response
        scrapped_name = None
        img_url = None
        scrapped_url = None
        
        # Get first title from properties.title
        if 'properties' in data and 'title' in data['properties']:
            titles = data['properties']['title']
            if isinstance(titles, list) and len(titles) > 0:
                scrapped_name = titles[0]
            elif isinstance(titles, str):
                scrapped_name = titles
        
        # Get first store data - loop through stores to find first with valid image
        if 'stores' in data and isinstance(data['stores'], list) and len(data['stores']) > 0:
            # Priority stores: Amazon, Target, Walmart
            priority_stores = ['amazon', 'target', 'walmart']
            
            # Find first store with a valid, accessible image for img_url
            # Priority: Amazon, Target, Walmart (skip eBay)
            print(f"\n🔍 Validating image URLs (prioritizing Amazon, Target, Walmart)...")
            
            # First pass: Try priority stores
            for idx, store in enumerate(data['stores'], 1):
                store_name = store.get('store', '').lower() if isinstance(store.get('store'), str) else ''
                
                # Skip eBay stores
                if 'ebay' in store_name:
                    continue
                
                # Check if it's a priority store
                is_priority = any(priority in store_name for priority in priority_stores)
                if not is_priority:
                    continue
                
                if 'image' in store and store['image']:
                    image_url = store['image']
                    print(f"   Checking priority store {store.get('store', 'Unknown')}: {image_url[:60]}...")
                    if check_image_url(image_url):
                        img_url = image_url
                        print(f"   ✓ Image is accessible from priority store")
                        break
                    else:
                        print(f"   ✗ Image is not accessible, trying next...")
            
            # Second pass: Try other stores (if no priority store image found)
            if not img_url:
                print(f"   No valid image from priority stores, trying other stores...")
                for idx, store in enumerate(data['stores'], 1):
                    store_name = store.get('store', '').lower() if isinstance(store.get('store'), str) else ''
                    
                    # Skip eBay stores
                    if 'ebay' in store_name:
                        print(f"   Skipping eBay store: {store.get('store', 'Unknown')}")
                        continue
                    
                    # Skip priority stores (already tried)
                    is_priority = any(priority in store_name for priority in priority_stores)
                    if is_priority:
                        continue
                    
                    if 'image' in store and store['image']:
                        image_url = store['image']
                        print(f"   Checking {store.get('store', 'Unknown')}: {image_url[:60]}...")
                        if check_image_url(image_url):
                            img_url = image_url
                            print(f"   ✓ Image is accessible")
                            break
                        else:
                            print(f"   ✗ Image is not accessible, trying next...")
            
            # Use first store for scrapped_url (or first store with URL)
            for store in data['stores']:
                if 'url' in store and store['url']:
                    scrapped_url = store['url']
                    break
            
            if not img_url:
                print(f"   ⚠️  No accessible images found in any store (excluding eBay)")
        
        # Update item with scraped data
        item.scrapped_name = scrapped_name
        item.img_url = img_url
        item.scrapped_url = scrapped_url
        item.scrapped_json = json.dumps(data)
        item.scrapped_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✓ Data saved to database for item: {item.name}")
        flash(f'Successfully scraped data for item "{item.name}"', 'success')
        
    except requests.exceptions.RequestException as e:
        flash(f'Error connecting to API: {str(e)}', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing response: {str(e)}', 'error')
    
    return redirect(url_for('spins.items_list'))

# ==================== SPINS Channels ====================

@spins_bp.route('/channels')
@login_required
def channels_list():
    """List all SPINS channels"""
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    return render_template('spins/channels_list.html', channels=channels)

@spins_bp.route('/channels/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_channel():
    """Create a new SPINS channel"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        
        if not name:
            flash('Channel name is required', 'error')
            return render_template('spins/edit_channel.html')
        
        if SpinsChannel.query.filter_by(name=name).first():
            flash('Channel with this name already exists', 'error')
            return render_template('spins/edit_channel.html')
        
        channel = SpinsChannel(name=name, short_name=short_name)
        db.session.add(channel)
        db.session.commit()
        flash(f'Channel "{name}" created successfully', 'success')
        return redirect(url_for('spins.channels_list'))
    
    return render_template('spins/edit_channel.html')

@spins_bp.route('/channels/<int:channel_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_channel(channel_id):
    """Edit a SPINS channel"""
    channel = SpinsChannel.query.get_or_404(channel_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        short_name = request.form.get('short_name', '').strip() or None
        
        if not name:
            flash('Channel name is required', 'error')
            return render_template('spins/edit_channel.html', channel=channel)
        
        existing = SpinsChannel.query.filter_by(name=name).first()
        if existing and existing.id != channel_id:
            flash('Channel with this name already exists', 'error')
            return render_template('spins/edit_channel.html', channel=channel)
        
        channel.name = name
        channel.short_name = short_name
        db.session.commit()
        flash(f'Channel updated successfully', 'success')
        return redirect(url_for('spins.channels_list'))
    
    return render_template('spins/edit_channel.html', channel=channel)

@spins_bp.route('/channels/<int:channel_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_channel(channel_id):
    """Delete a SPINS channel"""
    channel = SpinsChannel.query.get_or_404(channel_id)
    name = channel.name
    
    # Check if channel has data
    data_count = SpinsData.query.filter_by(channel_id=channel_id).count()
    if data_count > 0:
        flash(f'Cannot delete channel "{name}" because it has {data_count} associated data record(s). Please delete data first.', 'error')
        return redirect(url_for('spins.channels_list'))
    
    db.session.delete(channel)
    db.session.commit()
    flash(f'Channel "{name}" deleted successfully', 'success')
    return redirect(url_for('spins.channels_list'))

# ==================== SPINS Rankings ====================

@spins_bp.route('/items/ranks')
@login_required
def items_ranks():
    """SPINS items ranking by units or revenues for a specific week and channel"""
    # Get filter parameters
    week_str = request.args.get('week')
    channel_id = request.args.get('channel_id', type=int)
    metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
    
    # Get all channels and available weeks for filters
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    available_weeks = db.session.query(SpinsData.week).distinct().order_by(SpinsData.week.desc()).all()
    available_weeks = [w.week for w in available_weeks]
    
    ranks = []
    selected_week = None
    selected_channel = None
    
    if week_str and channel_id:
        try:
            selected_week = datetime.strptime(week_str, '%Y-%m-%d').date()
            selected_channel = SpinsChannel.query.get(channel_id)
            
            # Query to get aggregated data by item
            query = db.session.query(
                SpinsItem.id,
                SpinsItem.upc,
                SpinsItem.name,
                SpinsItem.short_name,
                SpinsItem.img_url,
                SpinsItem.scrapped_name,
                SpinsItem.scrapped_json,
                SpinsBrand.id.label('brand_id'),
                SpinsBrand.name.label('brand_name'),
                func.sum(SpinsData.units).label('total_units'),
                func.sum(SpinsData.revenues).label('total_revenues'),
                func.avg(SpinsData.average_weekly_units_per_selling_item).label('avg_upspw'),
                func.avg(SpinsData.average_weekly_revenues_per_selling_item).label('avg_pspw')
            ).join(
                SpinsData, SpinsData.item_id == SpinsItem.id
            ).join(
                SpinsBrand, SpinsData.brand_id == SpinsBrand.id
            ).filter(
                SpinsData.week == selected_week,
                SpinsData.channel_id == channel_id
            ).group_by(
                SpinsItem.id,
                SpinsItem.upc,
                SpinsItem.name,
                SpinsItem.short_name,
                SpinsItem.img_url,
                SpinsItem.scrapped_name,
                SpinsItem.scrapped_json,
                SpinsBrand.id,
                SpinsBrand.name
            )
            
            # Order by selected metric
            if metric == 'units':
                query = query.order_by(func.sum(SpinsData.units).desc())
            elif metric == 'revenues':
                query = query.order_by(func.sum(SpinsData.revenues).desc())
            elif metric == 'upspw':
                # Use nullslast() method for PostgreSQL compatibility
                avg_upspw = func.avg(SpinsData.average_weekly_units_per_selling_item)
                query = query.order_by(avg_upspw.desc().nullslast())
            elif metric == 'pspw':
                # Use nullslast() method for PostgreSQL compatibility
                avg_pspw = func.avg(SpinsData.average_weekly_revenues_per_selling_item)
                query = query.order_by(avg_pspw.desc().nullslast())
            
            results = query.all()
            
            # Build ranks list
            for rank, result in enumerate(results, start=1):
                ranks.append({
                    'rank': rank,
                    'item_id': result.id,
                    'upc': result.upc,
                    'name': result.name,
                    'short_name': result.short_name,
                    'img_url': result.img_url,
                    'scrapped_name': result.scrapped_name,
                    'scrapped_json': result.scrapped_json,
                    'brand_id': result.brand_id,
                    'brand_name': result.brand_name,
                    'units': float(result.total_units) if result.total_units else 0,
                    'revenues': float(result.total_revenues) if result.total_revenues else 0,
                    'upspw': float(result.avg_upspw) if result.avg_upspw is not None else None,
                    'pspw': float(result.avg_pspw) if result.avg_pspw is not None else None
                })
        except ValueError:
            flash('Invalid date format', 'error')
    
    return render_template('spins/items_ranks.html',
                         ranks=ranks,
                         channels=channels,
                         available_weeks=available_weeks,
                         selected_week=selected_week,
                         selected_channel=selected_channel,
                         selected_channel_id=channel_id,
                         selected_metric=metric)

@spins_bp.route('/brands/ranks')
@login_required
def brands_ranks():
    """SPINS brands ranking by units or revenues for a specific week and channel"""
    # Get filter parameters
    week_str = request.args.get('week')
    channel_id = request.args.get('channel_id', type=int)
    metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
    
    # Get all channels and available weeks for filters
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    available_weeks = db.session.query(SpinsData.week).distinct().order_by(SpinsData.week.desc()).all()
    available_weeks = [w.week for w in available_weeks]
    
    ranks = []
    selected_week = None
    selected_channel = None
    
    if week_str and channel_id:
        try:
            selected_week = datetime.strptime(week_str, '%Y-%m-%d').date()
            selected_channel = SpinsChannel.query.get(channel_id)
            
            # Query to get aggregated data by brand
            query = db.session.query(
                SpinsBrand.id,
                SpinsBrand.name,
                SpinsBrand.short_name,
                func.sum(SpinsData.units).label('total_units'),
                func.sum(SpinsData.revenues).label('total_revenues')
            ).join(
                SpinsData, SpinsData.brand_id == SpinsBrand.id
            ).filter(
                SpinsData.week == selected_week,
                SpinsData.channel_id == channel_id
            ).group_by(
                SpinsBrand.id,
                SpinsBrand.name,
                SpinsBrand.short_name
            )
            
            # Order by selected metric
            if metric == 'units':
                query = query.order_by(func.sum(SpinsData.units).desc())
            else:  # revenues
                query = query.order_by(func.sum(SpinsData.revenues).desc())
            
            results = query.all()
            
            # Build ranks list
            for rank, result in enumerate(results, start=1):
                ranks.append({
                    'rank': rank,
                    'brand_id': result.id,
                    'name': result.name,
                    'short_name': result.short_name,
                    'units': float(result.total_units) if result.total_units else 0,
                    'revenues': float(result.total_revenues) if result.total_revenues else 0
                })
        except ValueError:
            flash('Invalid date format', 'error')
    
    return render_template('spins/brands_ranks.html',
                         ranks=ranks,
                         channels=channels,
                         available_weeks=available_weeks,
                         selected_week=selected_week,
                         selected_channel=selected_channel,
                         selected_channel_id=channel_id,
                         selected_metric=metric)

@spins_bp.route('/brands/ranking-graph')
@login_required
def brands_ranking_graph():
    """SPINS brands ranking graph - shows top 20 brands ranking over time"""
    # Get filter parameters
    channel_id = request.args.get('channel_id', type=int)
    metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
    
    # Get all channels for filter
    channels = SpinsChannel.query.order_by(SpinsChannel.name).all()
    
    selected_channel = None
    if channel_id:
        selected_channel = SpinsChannel.query.get(channel_id)
    
    return render_template('spins/brands_ranking_graph.html',
                         channels=channels,
                         selected_channel=selected_channel,
                         selected_channel_id=channel_id,
                         selected_metric=metric)

@spins_bp.route('/api/brands-ranking-data')
@login_required
def api_brands_ranking_data():
    """API endpoint to get brand ranking data over time for the graph"""
    try:
        channel_id = request.args.get('channel_id', type=int)
        metric = request.args.get('metric', 'revenues')  # 'units' or 'revenues'
        
        if not channel_id:
            return jsonify({'error': 'Channel ID is required'}), 400
        
        # Get all weeks for this channel
        weeks_query = db.session.query(SpinsData.week).filter(
            SpinsData.channel_id == channel_id
        ).distinct().order_by(SpinsData.week)
        
        all_weeks = [w.week for w in weeks_query.all()]
        
        if not all_weeks:
            return jsonify({
                'weeks': [],
                'brands_data': [],
                'metric_label': 'Revenues' if metric == 'revenues' else 'Units'
            })
        
        # For each week, get top 20 brands and their rankings
        # We'll track all brands that appear in top 20 at least once
        all_top_brands = set()
        weekly_rankings = {}  # {week: {brand_id: rank}}
        
        for week in all_weeks:
            # Query to get aggregated data by brand for this week
            query = db.session.query(
                SpinsBrand.id,
                SpinsBrand.name,
                func.sum(SpinsData.units).label('total_units'),
                func.sum(SpinsData.revenues).label('total_revenues')
            ).join(
                SpinsData, SpinsData.brand_id == SpinsBrand.id
            ).filter(
                SpinsData.week == week,
                SpinsData.channel_id == channel_id
            ).group_by(
                SpinsBrand.id,
                SpinsBrand.name
            )
            
            # Order by selected metric
            if metric == 'units':
                query = query.order_by(func.sum(SpinsData.units).desc())
            else:  # revenues
                query = query.order_by(func.sum(SpinsData.revenues).desc())
            
            results = query.limit(20).all()
            
            # Store rankings for this week
            weekly_rankings[week] = {}
            for rank, result in enumerate(results, start=1):
                brand_id = result.id
                all_top_brands.add(brand_id)
                weekly_rankings[week][brand_id] = rank
        
        # Now build data for each brand that was in top 20 at least once
        brands_data = []
        brand_colors = [
            'rgb(66, 153, 225)',   # Blue
            'rgb(237, 137, 54)',   # Orange
            'rgb(245, 101, 101)',  # Red
            'rgb(156, 163, 175)',  # Gray
            'rgb(251, 191, 36)',   # Yellow
            'rgb(139, 92, 246)',   # Indigo
            'rgb(236, 72, 153)',   # Pink
            'rgb(20, 184, 166)',   # Teal
            'rgb(159, 122, 234)',  # Purple
            'rgb(72, 187, 120)',   # Green (but BOKA will override)
            'rgb(34, 139, 34)',    # Forest Green
            'rgb(255, 140, 0)',    # Dark Orange
            'rgb(148, 0, 211)',    # Violet
            'rgb(255, 20, 147)',   # Deep Pink
            'rgb(0, 191, 255)',    # Deep Sky Blue
            'rgb(255, 165, 0)',    # Orange
            'rgb(186, 85, 211)',   # Medium Orchid
            'rgb(60, 179, 113)',   # Medium Sea Green
            'rgb(255, 99, 71)',   # Tomato
            'rgb(106, 90, 205)',   # Slate Blue
        ]
        
        # Get the latest week and select top 20 brands from that week only
        if not all_weeks:
            return jsonify({
                'weeks': [],
                'brands_data': [],
                'metric_label': 'Revenues' if metric == 'revenues' else 'Units'
            })
        
        latest_week = all_weeks[-1]
        latest_week_rankings = weekly_rankings.get(latest_week, {})
        
        # Get top 20 brands from the latest week only
        top_20_brand_ids = []
        for rank in range(1, 21):  # Ranks 1-20
            for brand_id, brand_rank in latest_week_rankings.items():
                if brand_rank == rank:
                    top_20_brand_ids.append(brand_id)
                    break
            if len(top_20_brand_ids) >= 20:
                break
        
        # Get brand info for selected brands
        brand_info = {}
        for brand_id in top_20_brand_ids:
            brand = SpinsBrand.query.get(brand_id)
            if brand:
                brand_info[brand_id] = brand.name
        
        # Sort brands by their ranking in the latest week (rank 1 first, rank 20 last)
        sorted_by_latest_rank = sorted(
            top_20_brand_ids,
            key=lambda bid: latest_week_rankings.get(bid, 999)
        )
        
        for idx, brand_id in enumerate(sorted_by_latest_rank):
            brand_name = brand_info.get(brand_id, f'Brand {brand_id}')
            is_boka = brand_name.upper() == 'BOKA'
            
            # Build ranking data for this brand across all weeks
            rankings = []
            for week in all_weeks:
                rank = weekly_rankings.get(week, {}).get(brand_id)
                # If brand not in top 20 for this week, use None (will show as gap in graph)
                rankings.append(rank if rank is not None else None)
            
            # Use green and bolder for BOKA
            if is_boka:
                color = 'rgb(34, 197, 94)'  # Green
                border_width = 4
            else:
                color = brand_colors[idx % len(brand_colors)]
                border_width = 2
            
            brands_data.append({
                'brand_id': brand_id,
                'brand_name': brand_name,
                'rankings': rankings,
                'color': color,
                'border_width': border_width
            })
        
        # Format weeks for display
        week_labels = [week.strftime('%Y-%m-%d') for week in all_weeks]
        
        return jsonify({
            'weeks': week_labels,
            'brands_data': brands_data,
            'metric_label': 'Revenues' if metric == 'revenues' else 'Units'
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

