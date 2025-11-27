#!/usr/bin/env python3
"""
Import blueprint for managing import errors
"""

from flask import Blueprint, render_template, request, redirect, url_for
from models import db, ImportError
from auth.blueprint import login_required, admin_required
from datetime import datetime, timedelta
import json

import_bp = Blueprint('imports', __name__, template_folder='templates')

@import_bp.route('/errors')
@login_required
@admin_required
def import_errors_list():
    """List all import errors"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    import_channel = request.args.get('import_channel')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = ImportError.query
    
    if import_channel:
        query = query.filter_by(import_channel=import_channel)
    if date_from:
        query = query.filter(ImportError.import_date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(ImportError.import_date <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    
    import_errors = query.order_by(ImportError.import_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get unique import channels for filter
    import_channels = db.session.query(ImportError.import_channel).distinct().all()
    import_channels = [ch[0] for ch in import_channels]
    
    return render_template('imports/errors_list.html',
                         import_errors=import_errors,
                         import_channels=import_channels,
                         current_filters={
                             'import_channel': import_channel,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@import_bp.route('/errors/<int:error_id>')
@login_required
@admin_required
def import_error_detail(error_id):
    """View details of a specific import error"""
    import_error = ImportError.query.get_or_404(error_id)
    
    # Try to parse error_data as JSON for better display
    try:
        error_data = json.loads(import_error.error_data)
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, just use the raw string
        error_data = import_error.error_data
    
    return render_template('imports/error_detail.html',
                         import_error=import_error,
                         error_data=error_data)

@import_bp.route('/errors/<int:error_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_import_error(error_id):
    """Delete an import error"""
    import_error = ImportError.query.get_or_404(error_id)
    db.session.delete(import_error)
    db.session.commit()
    return redirect(url_for('imports.import_errors_list'))

