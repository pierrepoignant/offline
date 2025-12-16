#!/usr/bin/env python3
"""
Core blueprint for managing brands, categories, channels, locations, and items
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from functools import wraps
from datetime import datetime
import csv
import io
from models import db, Brand, Category, Channel, ChannelCustomer, Item, ChannelItem, Asin, ImportError, ChannelCustomerType
from auth.blueprint import login_required, admin_required

core_bp = Blueprint('core', __name__, template_folder='templates')

# ==================== Brands ====================

@core_bp.route('/brands')
@login_required
def brands_list():
    """List all brands"""
    brands = Brand.query.order_by(Brand.name).all()
    return render_template('core/brands_list.html', brands=brands)

@core_bp.route('/brands/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_brand():
    """Create a new brand"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip() or None
        
        if not name:
            flash('Brand name is required', 'error')
            return render_template('core/edit_brand.html')
        
        if Brand.query.filter_by(name=name).first():
            flash('Brand with this name already exists', 'error')
            return render_template('core/edit_brand.html')
        
        if code and Brand.query.filter_by(code=code).first():
            flash('Brand with this code already exists', 'error')
            return render_template('core/edit_brand.html')
        
        brand = Brand(name=name, code=code)
        db.session.add(brand)
        db.session.commit()
        flash(f'Brand "{name}" created successfully', 'success')
        return redirect(url_for('core.brands_list'))
    
    return render_template('core/edit_brand.html')

@core_bp.route('/brands/<int:brand_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_brand(brand_id):
    """Edit a brand"""
    brand = Brand.query.get_or_404(brand_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip() or None
        
        if not name:
            flash('Brand name is required', 'error')
            return render_template('core/edit_brand.html', brand=brand)
        
        existing = Brand.query.filter_by(name=name).first()
        if existing and existing.id != brand_id:
            flash('Brand with this name already exists', 'error')
            return render_template('core/edit_brand.html', brand=brand)
        
        if code:
            existing_code = Brand.query.filter_by(code=code).first()
            if existing_code and existing_code.id != brand_id:
                flash('Brand with this code already exists', 'error')
                return render_template('core/edit_brand.html', brand=brand)
        
        brand.name = name
        brand.code = code
        db.session.commit()
        flash(f'Brand updated successfully', 'success')
        return redirect(url_for('core.brands_list'))
    
    return render_template('core/edit_brand.html', brand=brand)

@core_bp.route('/brands/<int:brand_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_brand(brand_id):
    """Delete a brand"""
    brand = Brand.query.get_or_404(brand_id)
    name = brand.name
    db.session.delete(brand)
    db.session.commit()
    flash(f'Brand "{name}" deleted successfully', 'success')
    return redirect(url_for('core.brands_list'))

# ==================== Categories ====================

@core_bp.route('/categories')
@login_required
def categories_list():
    """List all categories"""
    categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
    return render_template('core/categories_list.html', categories=categories)

@core_bp.route('/categories/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_category():
    """Create a new category"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand_id = request.form.get('brand_id')
        
        if not name or not brand_id:
            flash('Category name and brand are required', 'error')
            brands = Brand.query.order_by(Brand.name).all()
            return render_template('core/edit_category.html', brands=brands)
        
        if Category.query.filter_by(name=name, brand_id=brand_id).first():
            flash('Category with this name already exists for this brand', 'error')
            brands = Brand.query.order_by(Brand.name).all()
            return render_template('core/edit_category.html', brands=brands)
        
        category = Category(name=name, brand_id=brand_id)
        db.session.add(category)
        db.session.commit()
        flash(f'Category "{name}" created successfully', 'success')
        return redirect(url_for('core.categories_list'))
    
    brands = Brand.query.order_by(Brand.name).all()
    return render_template('core/edit_category.html', brands=brands)

@core_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    """Edit a category"""
    category = Category.query.get_or_404(category_id)
    brands = Brand.query.order_by(Brand.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand_id = request.form.get('brand_id')
        
        if not name or not brand_id:
            flash('Category name and brand are required', 'error')
            return render_template('core/edit_category.html', category=category, brands=brands)
        
        existing = Category.query.filter_by(name=name, brand_id=brand_id).first()
        if existing and existing.id != category_id:
            flash('Category with this name already exists for this brand', 'error')
            return render_template('core/edit_category.html', category=category, brands=brands)
        
        category.name = name
        category.brand_id = brand_id
        db.session.commit()
        flash(f'Category updated successfully', 'success')
        return redirect(url_for('core.categories_list'))
    
    return render_template('core/edit_category.html', category=category, brands=brands)

@core_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    """Delete a category"""
    category = Category.query.get_or_404(category_id)
    
    # Check if category has items - count items with this category
    items_count = Item.query.filter_by(category_id=category_id).count()
    if items_count > 0:
        flash(f'Cannot delete category "{category.name}" because it has {items_count} associated item(s). Please reassign or delete items first.', 'error')
        return redirect(url_for('core.categories_list'))
    
    db.session.delete(category)
    db.session.commit()
    flash(f'Category "{category.name}" deleted successfully', 'success')
    return redirect(url_for('core.categories_list'))

# ==================== Channels ====================

@core_bp.route('/channels')
@login_required
def channels_list():
    """List all channels"""
    channels = Channel.query.order_by(Channel.name).all()
    return render_template('core/channels_list.html', channels=channels)

@core_bp.route('/channels/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_channel():
    """Create a new channel"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        netsuite_include = request.form.get('netsuite_include') == '1'
        
        if not name:
            flash('Channel name is required', 'error')
            return render_template('core/edit_channel.html')
        
        if Channel.query.filter_by(name=name).first():
            flash('Channel with this name already exists', 'error')
            return render_template('core/edit_channel.html')
        
        channel = Channel(name=name, netsuite_include=netsuite_include)
        db.session.add(channel)
        db.session.commit()
        flash(f'Channel "{name}" created successfully', 'success')
        return redirect(url_for('core.channels_list'))
    
    return render_template('core/edit_channel.html')

@core_bp.route('/channels/<int:channel_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_channel(channel_id):
    """Edit a channel"""
    channel = Channel.query.get_or_404(channel_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        netsuite_include = request.form.get('netsuite_include') == '1'
        
        if not name:
            flash('Channel name is required', 'error')
            return render_template('core/edit_channel.html', channel=channel)
        
        existing = Channel.query.filter_by(name=name).first()
        if existing and existing.id != channel_id:
            flash('Channel with this name already exists', 'error')
            return render_template('core/edit_channel.html', channel=channel)
        
        channel.name = name
        channel.netsuite_include = netsuite_include
        db.session.commit()
        flash(f'Channel updated successfully', 'success')
        return redirect(url_for('core.channels_list'))
    
    return render_template('core/edit_channel.html', channel=channel)

@core_bp.route('/channels/<int:channel_id>/items')
@login_required
def channel_items(channel_id):
    """View items for a channel"""
    channel = Channel.query.get_or_404(channel_id)
    channel_items_list = ChannelItem.query.filter_by(channel_id=channel_id).join(Item).order_by(ChannelItem.channel_code).all()
    # Get all items for the dropdown (excluding items already in this channel)
    existing_item_ids = [ci.item_id for ci in channel_items_list]
    if existing_item_ids:
        items = Item.query.join(Brand).filter(~Item.id.in_(existing_item_ids)).order_by(Brand.name, Item.essor_code).all()
    else:
        items = Item.query.join(Brand).order_by(Brand.name, Item.essor_code).all()
    return render_template('core/channel_items.html', channel=channel, channel_items=channel_items_list, items=items)

@core_bp.route('/channels/<int:channel_id>/items/create', methods=['POST'])
@login_required
@admin_required
def create_channel_item(channel_id):
    """Create a new channel item"""
    channel = Channel.query.get_or_404(channel_id)
    
    item_id = request.form.get('item_id')
    channel_code = request.form.get('channel_code', '').strip()
    channel_name = request.form.get('channel_name', '').strip()
    
    if not all([item_id, channel_code, channel_name]):
        flash('Item, channel code, and channel name are required', 'error')
        return redirect(url_for('core.channel_items', channel_id=channel_id))
    
    # Check if item already exists for this channel
    existing = ChannelItem.query.filter_by(channel_id=channel_id, item_id=item_id).first()
    if existing:
        flash('This item is already linked to this channel', 'error')
        return redirect(url_for('core.channel_items', channel_id=channel_id))
    
    channel_item = ChannelItem(
        channel_id=channel_id,
        item_id=item_id,
        channel_code=channel_code,
        channel_name=channel_name
    )
    
    db.session.add(channel_item)
    db.session.commit()
    flash('Item added to channel successfully', 'success')
    return redirect(url_for('core.channel_items', channel_id=channel_id))

@core_bp.route('/channels/<int:channel_id>/items/<int:channel_item_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_channel_item(channel_id, channel_item_id):
    """Edit a channel item"""
    channel_item = ChannelItem.query.get_or_404(channel_item_id)
    
    if channel_item.channel_id != channel_id:
        flash('Invalid channel item', 'error')
        return redirect(url_for('core.channel_items', channel_id=channel_id))
    
    channel_code = request.form.get('channel_code', '').strip()
    channel_name = request.form.get('channel_name', '').strip()
    
    if not all([channel_code, channel_name]):
        flash('Channel code and channel name are required', 'error')
        return redirect(url_for('core.channel_items', channel_id=channel_id))
    
    channel_item.channel_code = channel_code
    channel_item.channel_name = channel_name
    db.session.commit()
    flash('Channel item updated successfully', 'success')
    return redirect(url_for('core.channel_items', channel_id=channel_id))

@core_bp.route('/channels/<int:channel_id>/items/<int:channel_item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_channel_item(channel_id, channel_item_id):
    """Delete a channel item"""
    channel_item = ChannelItem.query.get_or_404(channel_item_id)
    
    if channel_item.channel_id != channel_id:
        flash('Invalid channel item', 'error')
        return redirect(url_for('core.channel_items', channel_id=channel_id))
    
    db.session.delete(channel_item)
    db.session.commit()
    flash('Item removed from channel successfully', 'success')
    return redirect(url_for('core.channel_items', channel_id=channel_id))

# ==================== Channel Customers ====================

@core_bp.route('/customers')
@login_required
def customers_list():
    """List all channel customers"""
    from models import SellthroughData, NetsuiteData, FaireData, db
    from sqlalchemy import func, extract
    
    # Get filter parameters
    channel_id = request.args.get('channel_id', type=int)
    customer_type_id = request.args.get('customer_type_id', type=int)
    brand_id = request.args.get('brand_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 30
    
    # Get all options for filters
    channels = Channel.query.order_by(Channel.name).all()
    customer_types = ChannelCustomerType.query.order_by(ChannelCustomerType.name).all()
    # Only show brands that have at least one customer
    brands = Brand.query.join(ChannelCustomer).distinct().order_by(Brand.name).all()
    
    # Don't load customers until a channel is selected
    customers = []
    customer_revenues = {}
    pagination = None
    
    if channel_id:
        # Build query with filters
        query = ChannelCustomer.query.join(Channel).outerjoin(Brand)
        
        query = query.filter(ChannelCustomer.channel_id == channel_id)
        if customer_type_id:
            query = query.filter(ChannelCustomer.customer_type_id == customer_type_id)
        if brand_id:
            query = query.filter(ChannelCustomer.brand_id == brand_id)
        
        # Paginate the query
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        customers = pagination.items
        
        # Check if this is Faire channel (id=11)
        is_faire_channel = (channel_id == 11)
        
        # Calculate revenues for each customer
        for customer in customers:
            if is_faire_channel:
                # For Faire channel, use FaireData
                rev_2024 = db.session.query(
                    func.coalesce(func.sum(FaireData.revenues), 0)
                ).filter(
                    FaireData.customer_id == customer.id,
                    extract('year', FaireData.date) == 2024
                ).scalar() or 0
                
                rev_2025 = db.session.query(
                    func.coalesce(func.sum(FaireData.revenues), 0)
                ).filter(
                    FaireData.customer_id == customer.id,
                    extract('year', FaireData.date) == 2025
                ).scalar() or 0
            else:
                # For other channels, use SellthroughData and NetsuiteData
                # Get 2024 revenues from SellthroughData
                rev_2024_sellthrough = db.session.query(
                    func.coalesce(func.sum(SellthroughData.revenues), 0)
                ).filter(
                    SellthroughData.customer_id == customer.id,
                    extract('year', SellthroughData.date) == 2024
                ).scalar() or 0
                
                # Get 2024 revenues from NetsuiteData
                rev_2024_netsuite = db.session.query(
                    func.coalesce(func.sum(NetsuiteData.revenues), 0)
                ).filter(
                    NetsuiteData.customer_id == customer.id,
                    extract('year', NetsuiteData.date) == 2024
                ).scalar() or 0
                
                # Get 2025 revenues from SellthroughData
                rev_2025_sellthrough = db.session.query(
                    func.coalesce(func.sum(SellthroughData.revenues), 0)
                ).filter(
                    SellthroughData.customer_id == customer.id,
                    extract('year', SellthroughData.date) == 2025
                ).scalar() or 0
                
                # Get 2025 revenues from NetsuiteData
                rev_2025_netsuite = db.session.query(
                    func.coalesce(func.sum(NetsuiteData.revenues), 0)
                ).filter(
                    NetsuiteData.customer_id == customer.id,
                    extract('year', NetsuiteData.date) == 2025
                ).scalar() or 0
                
                # Combine revenues from both sources
                rev_2024 = float(rev_2024_sellthrough) + float(rev_2024_netsuite)
                rev_2025 = float(rev_2025_sellthrough) + float(rev_2025_netsuite)
            
            # Calculate YoY growth
            yoy_growth = None
            if rev_2024 > 0:
                yoy_growth = ((rev_2025 - rev_2024) / rev_2024) * 100
            elif rev_2025 > 0:
                yoy_growth = 100  # Infinite growth (from 0 to positive)
            else:
                yoy_growth = 0  # No growth (both 0)
            
            customer_revenues[customer.id] = {
                '2024': float(rev_2024),
                '2025': float(rev_2025),
                'yoy_growth': yoy_growth
            }
        
        # Sort customers by 2025 revenues (decreasing)
        customers = sorted(customers, key=lambda c: customer_revenues[c.id]['2025'], reverse=True)
    
    return render_template('core/customers_list.html', 
                         customers=customers,
                         customer_revenues=customer_revenues,
                         channels=channels,
                         customer_types=customer_types,
                         brands=brands,
                         selected_channel_id=channel_id,
                         selected_customer_type_id=customer_type_id,
                         selected_brand_id=brand_id,
                         pagination=pagination)

@core_bp.route('/customers/<int:customer_id>')
@login_required
def customer_detail(customer_id):
    """View customer detail with tabs"""
    from models import SellthroughData, NetsuiteData, FaireData, db
    from sqlalchemy import func, extract
    
    customer = ChannelCustomer.query.get_or_404(customer_id)
    
    # Check if this is Faire channel (id=11)
    is_faire_channel = (customer.channel_id == 11)
    
    # Calculate total revenues for 2024 and 2025
    if is_faire_channel:
        # For Faire channel, use FaireData
        total_rev_2024 = db.session.query(
            func.coalesce(func.sum(FaireData.revenues), 0)
        ).filter(
            FaireData.customer_id == customer_id,
            extract('year', FaireData.date) == 2024
        ).scalar() or 0
        
        total_rev_2025 = db.session.query(
            func.coalesce(func.sum(FaireData.revenues), 0)
        ).filter(
            FaireData.customer_id == customer_id,
            extract('year', FaireData.date) == 2025
        ).scalar() or 0
        
        total_rev_2024 = float(total_rev_2024)
        total_rev_2025 = float(total_rev_2025)
    else:
        # From SellthroughData
        rev_2024_sellthrough = db.session.query(
            func.coalesce(func.sum(SellthroughData.revenues), 0)
        ).filter(
            SellthroughData.customer_id == customer_id,
            extract('year', SellthroughData.date) == 2024
        ).scalar() or 0
        
        rev_2025_sellthrough = db.session.query(
            func.coalesce(func.sum(SellthroughData.revenues), 0)
        ).filter(
            SellthroughData.customer_id == customer_id,
            extract('year', SellthroughData.date) == 2025
        ).scalar() or 0
        
        # From NetsuiteData
        rev_2024_netsuite = db.session.query(
            func.coalesce(func.sum(NetsuiteData.revenues), 0)
        ).filter(
            NetsuiteData.customer_id == customer_id,
            extract('year', NetsuiteData.date) == 2024
        ).scalar() or 0
        
        rev_2025_netsuite = db.session.query(
            func.coalesce(func.sum(NetsuiteData.revenues), 0)
        ).filter(
            NetsuiteData.customer_id == customer_id,
            extract('year', NetsuiteData.date) == 2025
        ).scalar() or 0
        
        total_rev_2024 = float(rev_2024_sellthrough) + float(rev_2024_netsuite)
        total_rev_2025 = float(rev_2025_sellthrough) + float(rev_2025_netsuite)
    
    return render_template('core/customer_detail.html', 
                         customer=customer,
                         total_rev_2024=total_rev_2024,
                         total_rev_2025=total_rev_2025)

@core_bp.route('/customers/<int:customer_id>/api/assortment')
@login_required
def api_customer_assortment(customer_id):
    """API endpoint for customer assortment data"""
    from models import Item, SellthroughData, NetsuiteData, FaireData, db
    from sqlalchemy import func, extract
    
    customer = ChannelCustomer.query.get_or_404(customer_id)
    
    # Check if this is Faire channel (id=11)
    is_faire_channel = (customer.channel_id == 11)
    
    revenues_2024 = {}
    revenues_2025 = {}
    
    if is_faire_channel:
        # For Faire channel, use FaireData
        faire_items_2024 = db.session.query(
            FaireData.item_id,
            func.sum(FaireData.revenues).label('revenues')
        ).filter(
            FaireData.customer_id == customer_id,
            extract('year', FaireData.date) == 2024
        ).group_by(FaireData.item_id).all()
        
        faire_items_2025 = db.session.query(
            FaireData.item_id,
            func.sum(FaireData.revenues).label('revenues')
        ).filter(
            FaireData.customer_id == customer_id,
            extract('year', FaireData.date) == 2025
        ).group_by(FaireData.item_id).all()
        
        for row in faire_items_2024:
            item_id = row.item_id
            revenues_2024[item_id] = float(row.revenues or 0)
        
        for row in faire_items_2025:
            item_id = row.item_id
            revenues_2025[item_id] = float(row.revenues or 0)
    else:
        # Get all items that have data for this customer
        # Query from SellthroughData
        sellthrough_items_2024 = db.session.query(
            SellthroughData.item_id,
            func.sum(SellthroughData.revenues).label('revenues')
        ).filter(
            SellthroughData.customer_id == customer_id,
            extract('year', SellthroughData.date) == 2024
        ).group_by(SellthroughData.item_id).all()
        
        sellthrough_items_2025 = db.session.query(
            SellthroughData.item_id,
            func.sum(SellthroughData.revenues).label('revenues')
        ).filter(
            SellthroughData.customer_id == customer_id,
            extract('year', SellthroughData.date) == 2025
        ).group_by(SellthroughData.item_id).all()
        
        # Query from NetsuiteData
        netsuite_items_2024 = db.session.query(
            NetsuiteData.item_id,
            func.sum(NetsuiteData.revenues).label('revenues')
        ).filter(
            NetsuiteData.customer_id == customer_id,
            extract('year', NetsuiteData.date) == 2024
        ).group_by(NetsuiteData.item_id).all()
        
        netsuite_items_2025 = db.session.query(
            NetsuiteData.item_id,
            func.sum(NetsuiteData.revenues).label('revenues')
        ).filter(
            NetsuiteData.customer_id == customer_id,
            extract('year', NetsuiteData.date) == 2025
        ).group_by(NetsuiteData.item_id).all()
        
        # Combine revenues by item_id
        for row in sellthrough_items_2024:
            item_id = row.item_id
            revenues_2024[item_id] = revenues_2024.get(item_id, 0) + float(row.revenues or 0)
        
        for row in netsuite_items_2024:
            item_id = row.item_id
            revenues_2024[item_id] = revenues_2024.get(item_id, 0) + float(row.revenues or 0)
        
        for row in sellthrough_items_2025:
            item_id = row.item_id
            revenues_2025[item_id] = revenues_2025.get(item_id, 0) + float(row.revenues or 0)
        
        for row in netsuite_items_2025:
            item_id = row.item_id
            revenues_2025[item_id] = revenues_2025.get(item_id, 0) + float(row.revenues or 0)
    
    # Get all unique item IDs
    all_item_ids = set(revenues_2024.keys()) | set(revenues_2025.keys())
    
    # Build response
    items_data = []
    for item_id in all_item_ids:
        item = Item.query.get(item_id)
        if item:
            rev_2024 = revenues_2024.get(item_id, 0)
            rev_2025 = revenues_2025.get(item_id, 0)
            
            # Calculate YoY growth percentage
            yoy_growth = None
            if rev_2024 > 0:
                yoy_growth = ((rev_2025 - rev_2024) / rev_2024) * 100
            elif rev_2025 > 0:
                yoy_growth = 100  # Infinite growth (from 0 to positive)
            else:
                yoy_growth = 0  # No growth (both 0)
            
            # Get ASIN image URL if available
            asin_img_url = None
            if item.asin_obj and item.asin_obj.img_url:
                asin_img_url = item.asin_obj.img_url
            
            # Get ASIN status (prefer ASIN status, fallback to item status)
            asin_status = None
            if item.asin_obj and item.asin_obj.status:
                asin_status = item.asin_obj.status
            elif item.status:
                asin_status = item.status
            
            items_data.append({
                'item_id': item_id,
                'essor_code': item.essor_code or '',
                'essor_name': item.essor_name or '',
                'revenues_2024': rev_2024,
                'revenues_2025': rev_2025,
                'yoy_growth': yoy_growth,
                'asin_img_url': asin_img_url,
                'asin_status': asin_status
            })
    
    # Sort by revenues_2025 DESC
    items_data.sort(key=lambda x: x['revenues_2025'], reverse=True)
    
    return jsonify({'items': items_data})

@core_bp.route('/customers/<int:customer_id>/api/monthly-revenues')
@login_required
def api_customer_monthly_revenues(customer_id):
    """API endpoint for customer monthly revenues"""
    from models import SellthroughData, NetsuiteData, FaireData, db
    from sqlalchemy import func, extract
    from datetime import datetime
    
    customer = ChannelCustomer.query.get_or_404(customer_id)
    
    # Check if this is Faire channel (id=11)
    is_faire_channel = (customer.channel_id == 11)
    
    # Get monthly revenues for 2024 and 2025
    months = []
    for year in [2024, 2025]:
        for month in range(1, 13):
            if is_faire_channel:
                # For Faire channel, use FaireData
                total_rev = db.session.query(
                    func.coalesce(func.sum(FaireData.revenues), 0)
                ).filter(
                    FaireData.customer_id == customer_id,
                    extract('year', FaireData.date) == year,
                    extract('month', FaireData.date) == month
                ).scalar() or 0
                total_rev = float(total_rev)
            else:
                # Query SellthroughData
                sellthrough_rev = db.session.query(
                    func.coalesce(func.sum(SellthroughData.revenues), 0)
                ).filter(
                    SellthroughData.customer_id == customer_id,
                    extract('year', SellthroughData.date) == year,
                    extract('month', SellthroughData.date) == month
                ).scalar() or 0
                
                # Query NetsuiteData
                netsuite_rev = db.session.query(
                    func.coalesce(func.sum(NetsuiteData.revenues), 0)
                ).filter(
                    NetsuiteData.customer_id == customer_id,
                    extract('year', NetsuiteData.date) == year,
                    extract('month', NetsuiteData.date) == month
                ).scalar() or 0
                
                total_rev = float(sellthrough_rev) + float(netsuite_rev)
            
            months.append({
                'year': year,
                'month': month,
                'month_name': datetime(year, month, 1).strftime('%b'),
                'revenues': total_rev
            })
    
    return jsonify({'months': months})

@core_bp.route('/customers/assortment-by-channel')
@login_required
def customers_assortment_by_channel():
    """View assortment by channel and brand for all customers"""
    channels = Channel.query.order_by(Channel.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    
    return render_template('core/customers_assortment_by_channel.html', 
                         channels=channels,
                         brands=brands)

@core_bp.route('/customers/api/assortment-by-channel')
@login_required
def api_assortment_by_channel():
    """API endpoint for assortment filtered by channel and brand"""
    from models import Item, NetsuiteData, FaireData, Asin, db
    from sqlalchemy import func, extract, or_, case
    import math
    import traceback
    
    print(f"[ASSORTMENT API] Request received: {request.args}")
    
    channel_id = request.args.get('channel_id', type=int)
    brand_id = request.args.get('brand_id', type=int)
    
    print(f"[ASSORTMENT API] channel_id={channel_id}, brand_id={brand_id}")
    
    # Get sorting parameters
    sort_by = request.args.get('sort_by', 'revenues_2025')
    sort_order = request.args.get('sort_order', 'desc').lower()
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 30
    
    print(f"[ASSORTMENT API] sort_by={sort_by}, sort_order={sort_order}, page={page}")
    
    # Validate sort_by
    if sort_by not in ['revenues_2024', 'revenues_2025']:
        sort_by = 'revenues_2025'
    
    # Validate sort_order
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    if not channel_id or not brand_id:
        print(f"[ASSORTMENT API] ERROR: Missing channel_id or brand_id")
        return jsonify({'error': 'channel_id and brand_id are required'}), 400
    
    try:
        # Verify channel and brand exist
        Channel.query.get_or_404(channel_id)
        Brand.query.get_or_404(brand_id)
        print(f"[ASSORTMENT API] Channel and Brand verified")
    except Exception as e:
        print(f"[ASSORTMENT API] ERROR verifying channel/brand: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Channel or Brand not found: {str(e)}'}), 404
    
    # Get all customers matching the channel and brand
    try:
        customers = ChannelCustomer.query.filter_by(
            channel_id=channel_id,
            brand_id=brand_id
        ).all()
        print(f"[ASSORTMENT API] Found {len(customers)} customers")
    except Exception as e:
        print(f"[ASSORTMENT API] ERROR querying customers: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error querying customers: {str(e)}'}), 500
    
    if not customers:
        print(f"[ASSORTMENT API] No customers found, returning empty result")
        return jsonify({
            'items': [],
            'pagination': {
                'total': 0,
                'page': page,
                'per_page': per_page,
                'total_pages': 0
            }
        })
    
    customer_ids = [c.id for c in customers]
    print(f"[ASSORTMENT API] Customer IDs: {customer_ids}")
    
    try:
        # Check if this is Faire channel (id=11)
        is_faire_channel = (channel_id == 11)
        
        # Single SQL query with joins to get all data at once
        print(f"[ASSORTMENT API] Executing single SQL query with joins... (Faire channel: {is_faire_channel})")
        
        from sqlalchemy import case
        
        if is_faire_channel:
            # For Faire channel, use FaireData
            query = db.session.query(
                Item.id.label('item_id'),
                Item.essor_code,
                Item.essor_name,
                Item.status.label('item_status'),
                Asin.img_url.label('asin_img_url'),
                Asin.status.label('asin_status'),
                func.coalesce(
                    func.sum(
                        case(
                            (extract('year', FaireData.date) == 2024, FaireData.revenues),
                            else_=0
                        )
                    ),
                    0
                ).label('revenues_2024'),
                func.coalesce(
                    func.sum(
                        case(
                            (extract('year', FaireData.date) == 2025, FaireData.revenues),
                            else_=0
                        )
                    ),
                    0
                ).label('revenues_2025')
            ).join(
                FaireData, Item.id == FaireData.item_id
            ).outerjoin(
                Asin, Item.asin_id == Asin.id
            ).filter(
                FaireData.customer_id.in_(customer_ids),
                FaireData.brand_id == brand_id
            ).group_by(
                Item.id,
                Item.essor_code,
                Item.essor_name,
                Item.status,
                Asin.img_url,
                Asin.status
            )
        else:
            # For other channels, use NetsuiteData
            query = db.session.query(
                Item.id.label('item_id'),
                Item.essor_code,
                Item.essor_name,
                Item.status.label('item_status'),
                Asin.img_url.label('asin_img_url'),
                Asin.status.label('asin_status'),
                func.coalesce(
                    func.sum(
                        case(
                            (extract('year', NetsuiteData.date) == 2024, NetsuiteData.revenues),
                            else_=0
                        )
                    ),
                    0
                ).label('revenues_2024'),
                func.coalesce(
                    func.sum(
                        case(
                            (extract('year', NetsuiteData.date) == 2025, NetsuiteData.revenues),
                            else_=0
                        )
                    ),
                    0
                ).label('revenues_2025')
            ).join(
                NetsuiteData, Item.id == NetsuiteData.item_id
            ).outerjoin(
                Asin, Item.asin_id == Asin.id
            ).filter(
                NetsuiteData.customer_id.in_(customer_ids),
                or_(NetsuiteData.channel_id == channel_id, NetsuiteData.channel_id.is_(None)),
                NetsuiteData.brand_id == brand_id
            ).group_by(
                Item.id,
                Item.essor_code,
                Item.essor_name,
                Item.status,
                Asin.img_url,
                Asin.status
            )
        
        print(f"[ASSORTMENT API] Query built, executing...")
        results = query.all()
        print(f"[ASSORTMENT API] Query returned {len(results)} items")
        
        # Build items data from query results
        items_data = []
        for row in results:
            rev_2024 = float(row.revenues_2024 or 0)
            rev_2025 = float(row.revenues_2025 or 0)
            
            # Only include items with revenue in at least one year
            if rev_2024 == 0 and rev_2025 == 0:
                continue
            
            # Calculate YoY growth percentage
            yoy_growth = None
            if rev_2024 > 0:
                yoy_growth = ((rev_2025 - rev_2024) / rev_2024) * 100
            elif rev_2025 > 0:
                yoy_growth = 100  # Infinite growth (from 0 to positive)
            else:
                yoy_growth = 0  # No growth (both 0)
            
            # Get ASIN status (prefer ASIN status, fallback to item status)
            asin_status = row.asin_status if row.asin_status else (row.item_status if row.item_status else None)
            
            items_data.append({
                'item_id': row.item_id,
                'essor_code': row.essor_code or '',
                'essor_name': row.essor_name or '',
                'revenues_2024': rev_2024,
                'revenues_2025': rev_2025,
                'yoy_growth': yoy_growth,
                'asin_img_url': row.asin_img_url,
                'asin_status': asin_status
            })
        
        print(f"[ASSORTMENT API] Built {len(items_data)} items (filtered to items with revenue)")
        
        # Sort based on sort_by and sort_order
        reverse_sort = (sort_order == 'desc')
        items_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse_sort)
        print(f"[ASSORTMENT API] Sorted by {sort_by} {sort_order}")
        
        # Pagination
        total_items = len(items_data)
        total_pages = math.ceil(total_items / per_page) if total_items > 0 else 0
        
        # Validate page number
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # Get paginated items
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = items_data[start_idx:end_idx]
        
        print(f"[ASSORTMENT API] Returning {len(paginated_items)} items (page {page} of {total_pages})")
        
        response = {
            'items': paginated_items,
            'pagination': {
                'total': total_items,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"[ASSORTMENT API] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error querying data: {str(e)}'}), 500

# ==================== ASIN Management ====================

@core_bp.route('/asins')
@login_required
def asins_list():
    """List all ASINs"""
    asins = Asin.query.order_by(Asin.asin).all()
    return render_template('core/asins_list.html', asins=asins)

@core_bp.route('/asin/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_asin_mapping():
    """Upload CSV to map items to ASINs"""
    if request.method == 'GET':
        return render_template('core/upload_asin.html')
    
    if 'file' not in request.files:
        flash('No file provided', 'error')
        return render_template('core/upload_asin.html')
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return render_template('core/upload_asin.html')
    
    if not file.filename.endswith('.csv'):
        flash('File must be a CSV', 'error')
        return render_template('core/upload_asin.html')
    
    import csv
    import io
    import json
    
    results = {
        'processed': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': []
    }
    
    try:
        # Read CSV file
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (1 is header)
            results['processed'] += 1
            
            try:
                item_code = row.get('item', '').strip()
                asin_value = row.get('asin', '').strip()
                title = row.get('title', '').strip()
                
                if not item_code:
                    results['skipped'] += 1
                    results['errors'].append(f"Row {row_num}: Missing item code")
                    continue
                
                # Find item by essor_code
                item = Item.query.filter_by(essor_code=item_code).first()
                if not item:
                    results['skipped'] += 1
                    results['errors'].append(f"Row {row_num}: Item with code '{item_code}' not found")
                    continue
                
                # If no ASIN but item exists, update essor_name with title if provided
                if not asin_value:
                    if title:
                        item.essor_name = title
                        results['updated'] += 1
                    else:
                        results['skipped'] += 1
                        results['errors'].append(f"Row {row_num}: No ASIN and no title provided")
                    continue
                
                # Check if ASIN exists
                asin_obj = Asin.query.filter_by(asin=asin_value).first()
                if not asin_obj:
                    # Create new ASIN
                    asin_obj = Asin(
                        asin=asin_value,
                        title=title if title else None
                    )
                    db.session.add(asin_obj)
                    db.session.flush()
                    results['created'] += 1
                
                # Update item with asin_id
                item.asin_id = asin_obj.id
                
                # Also update essor_name with title if provided
                if title:
                    item.essor_name = title
                
                results['updated'] += 1
                
            except Exception as e:
                error_msg = f"Row {row_num}: {str(e)}"
                results['errors'].append(error_msg)
                results['skipped'] += 1
                
                # Save import error
                try:
                    import_error = ImportError(
                        import_channel='asin_mapping',
                        import_date=datetime.utcnow(),
                        error_data=json.dumps(row),
                        error_message=error_msg,
                        row_number=row_num
                    )
                    db.session.add(import_error)
                    db.session.commit()
                except:
                    db.session.rollback()
        
        db.session.commit()
        flash(f'Import completed: {results["processed"]} processed, {results["created"]} ASINs created, {results["updated"]} items updated, {results["skipped"]} skipped', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'error')
        results['errors'].append(f"File processing error: {str(e)}")
    
    return render_template('core/upload_asin.html', results=results)

# ==================== Channel Locations (Legacy - kept for backward compatibility) ====================

@core_bp.route('/locations')
@login_required
def locations_list():
    """List all channel locations (legacy route - redirects to customers)"""
    return redirect(url_for('core.customers_list'))

@core_bp.route('/locations/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_location():
    """Create a new channel location"""
    channels = Channel.query.order_by(Channel.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    customer_types = ChannelCustomerType.query.order_by(ChannelCustomerType.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        channel_id = request.form.get('channel_id')
        
        if not name or not channel_id:
            flash('Location name and channel are required', 'error')
            return render_template('core/edit_location.html', channels=channels, brands=brands, customer_types=customer_types)
        
        if ChannelCustomer.query.filter_by(name=name, channel_id=channel_id).first():
            flash('Location with this name already exists for this channel', 'error')
            return render_template('core/edit_location.html', channels=channels, brands=brands, customer_types=customer_types)
        
        description = request.form.get('description', '').strip() or None
        brand_id = request.form.get('brand_id', type=int) or None
        customer_type_id = request.form.get('customer_type_id', type=int) or None
        location = ChannelCustomer(name=name, channel_id=channel_id, brand_id=brand_id, customer_type_id=customer_type_id, description=description)
        db.session.add(location)
        db.session.commit()
        flash(f'Location "{name}" created successfully', 'success')
        return redirect(url_for('core.locations_list'))
    
    return render_template('core/edit_location.html', channels=channels, brands=brands, customer_types=customer_types)

@core_bp.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_location(location_id):
    """Edit a channel location"""
    location = ChannelCustomer.query.get_or_404(location_id)
    channels = Channel.query.order_by(Channel.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    customer_types = ChannelCustomerType.query.order_by(ChannelCustomerType.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        channel_id = request.form.get('channel_id')
        
        if not name or not channel_id:
            flash('Location name and channel are required', 'error')
            return render_template('core/edit_location.html', location=location, channels=channels, brands=brands, customer_types=customer_types)
        
        existing = ChannelCustomer.query.filter_by(name=name, channel_id=channel_id).first()
        if existing and existing.id != location_id:
            flash('Location with this name already exists for this channel', 'error')
            return render_template('core/edit_location.html', location=location, channels=channels, brands=brands, customer_types=customer_types)
        
        description = request.form.get('description', '').strip() or None
        brand_id = request.form.get('brand_id', type=int) or None
        customer_type_id = request.form.get('customer_type_id', type=int) or None
        location.name = name
        location.channel_id = channel_id
        location.brand_id = brand_id
        location.customer_type_id = customer_type_id
        location.description = description
        db.session.commit()
        flash(f'Location updated successfully', 'success')
        return redirect(url_for('core.locations_list'))
    
    return render_template('core/edit_location.html', location=location, channels=channels, brands=brands, customer_types=customer_types)

# ==================== Items ====================

@core_bp.route('/items')
@login_required
def items_list():
    """List all items"""
    items = Item.query.join(Brand).outerjoin(Category).order_by(Brand.name, Category.name, Item.essor_code).all()
    return render_template('core/items_list.html', items=items)

@core_bp.route('/items/export')
@login_required
def items_export():
    """Export all items to CSV"""
    items = Item.query.join(Brand).outerjoin(Category).order_by(Brand.name, Category.name, Item.essor_code).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Essor Code', 'Essor Name', 'Brand', 'Category'])
    
    # Write data
    for item in items:
        writer.writerow([
            item.essor_code or '',
            item.essor_name or '',
            item.brand.name if item.brand else '',
            item.category.name if item.category else ''
        ])
    
    output.seek(0)
    
    # Create response with CSV
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=items_export.csv'}
    )
    
    return response

@core_bp.route('/items/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_item():
    """Create a new item"""
    if request.method == 'POST':
        essor_code = request.form.get('essor_code', '').strip()
        essor_name = request.form.get('essor_name', '').strip()
        brand_id = request.form.get('brand_id')
        category_id_str = request.form.get('category_id', '').strip()
        category_id = int(category_id_str) if category_id_str else None
        
        if not all([essor_code, essor_name, brand_id]):
            flash('Essor Code, Essor Name, and Brand are required', 'error')
            brands = Brand.query.order_by(Brand.name).all()
            categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
            return render_template('core/edit_item.html', brands=brands, categories=categories)
        
        if Item.query.filter_by(essor_code=essor_code).first():
            flash('Item with this Essor code already exists', 'error')
            brands = Brand.query.order_by(Brand.name).all()
            categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
            return render_template('core/edit_item.html', brands=brands, categories=categories)
        
        item = Item(essor_code=essor_code, essor_name=essor_name, brand_id=brand_id, category_id=category_id)
        db.session.add(item)
        db.session.commit()
        flash(f'Item "{essor_code}" created successfully', 'success')
        return redirect(url_for('core.items_list'))
    
    brands = Brand.query.order_by(Brand.name).all()
    categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
    return render_template('core/edit_item.html', brands=brands, categories=categories)

@core_bp.route('/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_item(item_id):
    """Edit an item"""
    item = Item.query.get_or_404(item_id)
    brands = Brand.query.order_by(Brand.name).all()
    categories = Category.query.join(Brand).order_by(Brand.name, Category.name).all()
    
    # Get channel items for this item
    channel_items = ChannelItem.query.filter_by(item_id=item_id).join(Channel).order_by(Channel.name).all()
    
    if request.method == 'POST':
        essor_code = request.form.get('essor_code', '').strip()
        essor_name = request.form.get('essor_name', '').strip()
        brand_id = request.form.get('brand_id')
        category_id_str = request.form.get('category_id', '').strip()
        category_id = int(category_id_str) if category_id_str else None
        
        if not all([essor_code, essor_name, brand_id]):
            flash('Essor Code, Essor Name, and Brand are required', 'error')
            return render_template('core/edit_item.html', item=item, brands=brands, categories=categories, channel_items=channel_items)
        
        existing = Item.query.filter_by(essor_code=essor_code).first()
        if existing and existing.id != item_id:
            flash('Item with this Essor code already exists', 'error')
            return render_template('core/edit_item.html', item=item, brands=brands, categories=categories, channel_items=channel_items)
        
        item.essor_code = essor_code
        item.essor_name = essor_name
        item.brand_id = brand_id
        item.category_id = category_id
        db.session.commit()
        flash(f'Item updated successfully', 'success')
        return redirect(url_for('core.items_list'))
    
    return render_template('core/edit_item.html', item=item, brands=brands, categories=categories, channel_items=channel_items)

@core_bp.route('/api/item-channels')
@login_required
def api_item_channels():
    """API endpoint to get channel codes and names for an item, plus ASIN image and title"""
    item_id = request.args.get('item_id', type=int)
    if not item_id:
        return jsonify({'error': 'item_id is required'}), 400
    
    item = Item.query.get_or_404(item_id)
    channel_items = ChannelItem.query.filter_by(item_id=item_id).join(Channel).order_by(Channel.name).all()
    
    channels_data = []
    for ci in channel_items:
        channels_data.append({
            'channel_name': ci.channel.name,
            'channel_code': ci.channel_code,
            'channel_item_name': ci.channel_name
        })
    
    # Get ASIN image and title if available
    asin_data = None
    if item.asin_obj:
        asin_data = {
            'asin': item.asin_obj.asin,
            'img_url': item.asin_obj.img_url,
            'title': item.asin_obj.title
        }
    
    return jsonify({
        'item': {
            'id': item.id,
            'essor_code': item.essor_code,
            'essor_name': item.essor_name
        },
        'asin': asin_data,
        'channels': channels_data
    })

# ==================== Customer Types ====================

@core_bp.route('/customer-types')
@login_required
def customer_types_list():
    """List all customer types"""
    customer_types = ChannelCustomerType.query.order_by(ChannelCustomerType.name).all()
    return render_template('core/customer_types_list.html', customer_types=customer_types)


@core_bp.route('/customer-types/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_customer_type():
    """Create a new customer type"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '').strip() or None
        
        if not name:
            flash('Customer type name is required', 'error')
            return render_template('core/edit_customer_type.html')
        
        if ChannelCustomerType.query.filter_by(name=name).first():
            flash('Customer type with this name already exists', 'error')
            return render_template('core/edit_customer_type.html')
        
        customer_type = ChannelCustomerType(name=name, color=color)
        db.session.add(customer_type)
        db.session.commit()
        flash(f'Customer type "{name}" created successfully', 'success')
        return redirect(url_for('core.customer_types_list'))
    
    return render_template('core/edit_customer_type.html')


@core_bp.route('/customer-types/<int:customer_type_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_customer_type(customer_type_id):
    """Edit a customer type"""
    customer_type = ChannelCustomerType.query.get_or_404(customer_type_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '').strip() or None
        
        if not name:
            flash('Customer type name is required', 'error')
            return render_template('core/edit_customer_type.html', customer_type=customer_type)
        
        existing = ChannelCustomerType.query.filter_by(name=name).first()
        if existing and existing.id != customer_type_id:
            flash('Customer type with this name already exists', 'error')
            return render_template('core/edit_customer_type.html', customer_type=customer_type)
        
        customer_type.name = name
        customer_type.color = color
        db.session.commit()
        flash(f'Customer type updated successfully', 'success')
        return redirect(url_for('core.customer_types_list'))
    
    return render_template('core/edit_customer_type.html', customer_type=customer_type)


@core_bp.route('/customer-types/<int:customer_type_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_customer_type(customer_type_id):
    """Delete a customer type"""
    customer_type = ChannelCustomerType.query.get_or_404(customer_type_id)
    name = customer_type.name
    
    # Check if customer type has customers
    customers_count = ChannelCustomer.query.filter_by(customer_type_id=customer_type_id).count()
    if customers_count > 0:
        flash(f'Cannot delete customer type "{name}" because it has {customers_count} associated customer(s).', 'error')
        return redirect(url_for('core.customer_types_list'))
    
    db.session.delete(customer_type)
    db.session.commit()
    flash(f'Customer type "{name}" deleted successfully', 'success')
    return redirect(url_for('core.customer_types_list'))

