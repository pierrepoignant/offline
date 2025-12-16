#!/usr/bin/env python3
"""
Targets blueprint for managing revenue targets
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime, date
from models import db, TargetData, Brand, Channel
from auth.blueprint import login_required
from sqlalchemy import extract, and_
from calendar import month_name

targets_bp = Blueprint('targets', __name__, template_folder='templates')


@targets_bp.route('/brands')
@login_required
def brands_list():
    """List all brands with option to view/edit targets"""
    brands = Brand.query.order_by(Brand.name).all()
    return render_template('targets/brands_list.html', brands=brands)


@targets_bp.route('/brands/<int:brand_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_brand_targets(brand_id):
    """Edit targets for a brand by year and month"""
    brand = Brand.query.get_or_404(brand_id)
    
    # Get year from query parameter or default to current year
    year = request.args.get('year', type=int)
    if not year:
        year = datetime.now().year
    
    if request.method == 'POST':
        # Get all channels
        channels = Channel.query.order_by(Channel.name).all()
        
        # Process form data
        form_year = request.form.get('year', type=int)
        if not form_year:
            flash('Year is required', 'error')
            return redirect(url_for('targets.edit_brand_targets', brand_id=brand_id, year=year))
        
        # Get all months data from form
        # Form fields are: revenue_<channel_id>_<month>
        saved_count = 0
        for channel in channels:
            for month in range(1, 13):
                field_name = f'revenue_{channel.id}_{month}'
                revenue_value = request.form.get(field_name, '').strip()
                
                if revenue_value:
                    try:
                        revenue = float(revenue_value)
                        if revenue < 0:
                            continue
                    except ValueError:
                        continue
                else:
                    revenue = 0
                
                # Create date for first day of the month
                target_date = date(form_year, month, 1)
                
                # Check if target already exists
                target = TargetData.query.filter_by(
                    date=target_date,
                    brand_id=brand_id,
                    channel_id=channel.id
                ).first()
                
                if target:
                    # Update existing target
                    if revenue > 0:
                        target.revenue = revenue
                        target.updated_at = datetime.utcnow()
                        saved_count += 1
                    else:
                        # Delete target if revenue is 0
                        db.session.delete(target)
                else:
                    # Create new target only if revenue > 0
                    if revenue > 0:
                        target = TargetData(
                            date=target_date,
                            brand_id=brand_id,
                            channel_id=channel.id,
                            revenue=revenue
                        )
                        db.session.add(target)
                        saved_count += 1
        
        db.session.commit()
        flash(f'Successfully saved {saved_count} target(s) for {brand.name} in {form_year}', 'success')
        return redirect(url_for('targets.edit_brand_targets', brand_id=brand_id, year=form_year))
    
    # GET request - show edit form
    # Get all channels
    channels = Channel.query.order_by(Channel.name).all()
    
    # Get existing targets for this brand and year
    targets = TargetData.query.filter(
        and_(
            TargetData.brand_id == brand_id,
            extract('year', TargetData.date) == year
        )
    ).all()
    
    # Create a dictionary for easy lookup: {(channel_id, month): revenue}
    targets_dict = {}
    for target in targets:
        month = target.date.month
        targets_dict[(target.channel_id, month)] = float(target.revenue)
    
    # Get available years (years that have targets, current year, and future years)
    years_with_targets = db.session.query(
        extract('year', TargetData.date).label('year')
    ).filter(
        TargetData.brand_id == brand_id
    ).distinct().all()
    
    current_year = datetime.now().year
    # Include current year, next year (2026), and any years with existing targets
    available_years = sorted(set([int(row.year) for row in years_with_targets] + [current_year, current_year + 1]), reverse=True)
    
    return render_template('targets/edit_brand_targets.html',
                         brand=brand,
                         channels=channels,
                         year=year,
                         targets_dict=targets_dict,
                         available_years=available_years,
                         month_names=list(month_name[1:]))  # Skip index 0


@targets_bp.route('/brands/<int:brand_id>/view', methods=['GET'])
@login_required
def view_brand_targets(brand_id):
    """View targets for a brand - table with channels as rows, months as columns"""
    brand = Brand.query.get_or_404(brand_id)
    
    # Get year from query parameter or default to current year
    year = request.args.get('year', type=int)
    if not year:
        year = datetime.now().year
    
    # Get all channels that have targets for this brand and year
    channels_with_targets = db.session.query(Channel).join(
        TargetData,
        and_(
            TargetData.channel_id == Channel.id,
            TargetData.brand_id == brand_id,
            extract('year', TargetData.date) == year
        )
    ).distinct().order_by(Channel.name).all()
    
    # Get all targets for this brand and year
    targets = TargetData.query.filter(
        and_(
            TargetData.brand_id == brand_id,
            extract('year', TargetData.date) == year
        )
    ).all()
    
    # Create a dictionary for easy lookup: {(channel_id, month): revenue}
    targets_dict = {}
    for target in targets:
        month = target.date.month
        targets_dict[(target.channel_id, month)] = float(target.revenue)
    
    # Get available years (years that have targets, current year, and future years)
    years_with_targets = db.session.query(
        extract('year', TargetData.date).label('year')
    ).filter(
        TargetData.brand_id == brand_id
    ).distinct().all()
    
    current_year = datetime.now().year
    # Include current year, next year (2026), and any years with existing targets
    available_years = sorted(set([int(row.year) for row in years_with_targets] + [current_year, current_year + 1]), reverse=True)
    
    return render_template('targets/view_brand_targets.html',
                         brand=brand,
                         channels=channels_with_targets,
                         year=year,
                         targets_dict=targets_dict,
                         available_years=available_years,
                         month_names=list(month_name[1:]))  # Skip index 0

