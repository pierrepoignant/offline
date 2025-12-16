#!/usr/bin/env python3
"""
CRM blueprint for managing customer tickets
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from datetime import datetime, date, timedelta
from calendar import monthrange
from models import db, CrmTicket, CrmTicketType, CrmTicketFlag, ChannelCustomer, User, crm_tickets_x_flags, Brand
from auth.blueprint import login_required, admin_required
from sqlalchemy import or_, case, and_
from db_utils import get_connection
from psycopg2.extras import RealDictCursor

crm_bp = Blueprint('crm', __name__, template_folder='templates')


@crm_bp.route('/customers/<int:customer_id>/tickets')
@login_required
def customer_tickets(customer_id):
    """Get tickets for a customer - API endpoint"""
    customer = ChannelCustomer.query.get_or_404(customer_id)
    
    # Order by due_date DESC if not null, then by created_at DESC
    tickets = CrmTicket.query.filter_by(customer_id=customer_id).order_by(
        case(
            (CrmTicket.due_date.isnot(None), CrmTicket.due_date),
            else_=None
        ).desc().nullslast(),
        CrmTicket.created_at.desc()
    ).all()
    
    tickets_data = []
    for ticket in tickets:
        flag_data = [{'id': f.id, 'name': f.name, 'color': f.color, 'text_color': f.text_color} for f in ticket.flags]
        tickets_data.append({
            'id': ticket.id,
            'status': ticket.status,
            'description': ticket.description,
            'due_date': ticket.due_date.isoformat() if ticket.due_date else None,
            'creator': ticket.creator.username if ticket.creator else 'Unknown',
            'owner': ticket.owner.username if ticket.owner else 'Unknown',
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None,
            'flags': flag_data
        })
    
    return jsonify({'tickets': tickets_data})


@crm_bp.route('/tickets/create', methods=['POST'])
@login_required
def create_ticket():
    """Create a new ticket"""
    customer_id = request.form.get('customer_id', type=int)
    description = request.form.get('description', '').strip()
    due_date_str = request.form.get('due_date', '').strip()
    owner_id = request.form.get('owner_id', type=int)
    ticket_type_id = request.form.get('ticket_type_id', type=int) or None
    
    if not customer_id or not description:
        return jsonify({'error': 'Customer ID and description are required'}), 400
    
    customer = ChannelCustomer.query.get_or_404(customer_id)
    
    # Parse due_date
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    
    # Use current user as creator if not provided
    creator_id = session.get('user_id')
    if not creator_id:
        return jsonify({'error': 'User not logged in'}), 401
    
    # Use creator as owner if owner not provided
    if not owner_id:
        owner_id = creator_id
    
    # Verify owner exists
    owner = User.query.get(owner_id)
    if not owner:
        return jsonify({'error': 'Invalid owner'}), 400
    
    # Get flag IDs from form
    flag_ids = request.form.getlist('flag_ids', type=int)
    
    # Create ticket
    ticket = CrmTicket(
        customer_id=customer_id,
        ticket_type_id=ticket_type_id,
        status='opened',
        description=description,
        due_date=due_date,
        creator_id=creator_id,
        owner_id=owner_id
    )
    
    db.session.add(ticket)
    db.session.flush()  # Flush to get ticket.id
    
    # Add flags
    if flag_ids:
        flags = CrmTicketFlag.query.filter(CrmTicketFlag.id.in_(flag_ids)).all()
        ticket.flags.extend(flags)
    
    db.session.commit()
    
    # Get flag data for response
    flag_data = [{'id': f.id, 'name': f.name, 'color': f.color} for f in ticket.flags]
    
    return jsonify({
        'success': True,
        'ticket': {
            'id': ticket.id,
            'status': ticket.status,
            'description': ticket.description,
            'due_date': ticket.due_date.isoformat() if ticket.due_date else None,
            'creator': ticket.creator.username if ticket.creator else 'Unknown',
            'owner': ticket.owner.username if ticket.owner else 'Unknown',
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None,
            'flags': flag_data
        }
    })


@crm_bp.route('/tickets/<int:ticket_id>/toggle-status', methods=['POST'])
@login_required
def toggle_ticket_status(ticket_id):
    """Toggle ticket status between opened and closed"""
    ticket = CrmTicket.query.get_or_404(ticket_id)
    
    if ticket.status == 'opened':
        ticket.status = 'closed'
    else:
        ticket.status = 'opened'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'status': ticket.status
    })


@crm_bp.route('/tickets/<int:ticket_id>/data')
@login_required
def get_ticket_data(ticket_id):
    """Get ticket data for overlay"""
    ticket = CrmTicket.query.get_or_404(ticket_id)
    
    flag_data = [{'id': f.id, 'name': f.name, 'color': f.color} for f in ticket.flags]
    
    return jsonify({
        'ticket': {
            'id': ticket.id,
            'status': ticket.status,
            'description': ticket.description,
            'due_date': ticket.due_date.isoformat() if ticket.due_date else None,
            'creator': ticket.creator.username if ticket.creator else 'Unknown',
            'owner': ticket.owner.username if ticket.owner else 'Unknown',
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None,
            'ticket_type_id': ticket.ticket_type_id,
            'customer': f"{ticket.customer.channel.name} - {ticket.customer.name}",
            'flags': flag_data,
            'flag_ids': [f.id for f in ticket.flags]
        }
    })


@crm_bp.route('/tickets/<int:ticket_id>/edit', methods=['POST'])
@login_required
def edit_ticket(ticket_id):
    """Edit a ticket"""
    ticket = CrmTicket.query.get_or_404(ticket_id)
    
    # Support both form and JSON requests
    if request.is_json:
        data = request.get_json()
        description = data.get('description', '').strip()
        due_date_str = data.get('due_date', '').strip() if data.get('due_date') else ''
        owner_id = data.get('owner_id')
        ticket_type_id = data.get('ticket_type_id') or None
    else:
        description = request.form.get('description', '').strip()
        due_date_str = request.form.get('due_date', '').strip()
        owner_id = request.form.get('owner_id', type=int)
        ticket_type_id = request.form.get('ticket_type_id', type=int) or None
    
    if not description:
        return jsonify({'error': 'Description is required'}), 400
    
    # Parse due_date
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    
    # Verify owner exists
    if owner_id:
        owner = User.query.get(owner_id)
        if not owner:
            return jsonify({'error': 'Invalid owner'}), 400
        ticket.owner_id = owner_id
    
    ticket.description = description
    ticket.due_date = due_date
    ticket.ticket_type_id = ticket_type_id
    ticket.updated_at = datetime.utcnow()
    
    # Handle flags - support both form and JSON
    if request.is_json:
        flag_ids = data.get('flag_ids', [])
    else:
        flag_ids = request.form.getlist('flag_ids', type=int)
    
    # Update flags
    ticket.flags = []
    if flag_ids:
        flags = CrmTicketFlag.query.filter(CrmTicketFlag.id.in_(flag_ids)).all()
        ticket.flags.extend(flags)
    
    db.session.commit()
    
    flag_data = [{'id': f.id, 'name': f.name, 'color': f.color} for f in ticket.flags]
    
    return jsonify({
        'success': True,
        'ticket': {
            'id': ticket.id,
            'status': ticket.status,
            'description': ticket.description,
            'due_date': ticket.due_date.isoformat() if ticket.due_date else None,
            'creator': ticket.creator.username if ticket.creator else 'Unknown',
            'owner': ticket.owner.username if ticket.owner else 'Unknown',
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None,
            'ticket_type_id': ticket.ticket_type_id,
            'flags': flag_data
        }
    })


@crm_bp.route('/tickets/<int:ticket_id>/delete', methods=['POST'])
@login_required
def delete_ticket(ticket_id):
    """Delete a ticket"""
    ticket = CrmTicket.query.get_or_404(ticket_id)
    ticket_id_val = ticket.id
    
    db.session.delete(ticket)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Ticket {ticket_id_val} deleted successfully'
    })


@crm_bp.route('/api/users')
@login_required
def api_users():
    """Get list of users for dropdowns"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT id, username, email
            FROM users
            WHERE is_active = TRUE
            ORDER BY username
        """)
        users = cursor.fetchall()
        return jsonify({'users': [dict(u) for u in users]})
    finally:
        cursor.close()
        conn.close()


@crm_bp.route('/api/ticket-types')
@login_required
def api_ticket_types():
    """Get list of ticket types for dropdowns"""
    ticket_types = CrmTicketType.query.order_by(CrmTicketType.name).all()
    return jsonify({
        'ticket_types': [{'id': tt.id, 'name': tt.name} for tt in ticket_types]
    })


@crm_bp.route('/api/ticket-flags')
@login_required
def api_ticket_flags():
    """Get list of ticket flags for checkboxes"""
    flags = CrmTicketFlag.query.order_by(CrmTicketFlag.name).all()
    return jsonify({
        'flags': [{'id': f.id, 'name': f.name, 'color': f.color, 'text_color': f.text_color} for f in flags]
    })


@crm_bp.route('/tickets')
@login_required
def all_tickets():
    """List all tickets with filtering"""
    from models import Channel
    
    # Get filter parameters
    customer_id = request.args.get('customer_id', type=int)
    owner_id = request.args.get('owner_id', type=int)
    status = request.args.get('status', '').strip()
    due_date_filter = request.args.get('due_date_filter', '').strip()
    ticket_type_id = request.args.get('ticket_type_id', type=int)
    flag_id = request.args.get('flag_id', type=int)
    brand_id = request.args.get('brand_id', type=int)
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 30
    
    # Build query
    query = CrmTicket.query
    
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    if owner_id:
        query = query.filter_by(owner_id=owner_id)
    if status in ['opened', 'closed']:
        query = query.filter_by(status=status)
    if ticket_type_id:
        query = query.filter_by(ticket_type_id=ticket_type_id)
    if flag_id:
        # Filter by flag using the many-to-many relationship
        query = query.join(crm_tickets_x_flags).filter(crm_tickets_x_flags.c.flag_id == flag_id).group_by(CrmTicket.id)
    
    # Handle brand filter and search together (both need ChannelCustomer join)
    needs_customer_join = brand_id or search_query
    if needs_customer_join:
        from models import Channel
        query = query.join(ChannelCustomer)
        
        if brand_id:
            query = query.filter(ChannelCustomer.brand_id == brand_id)
        
        if search_query:
            query = query.join(Channel)
            search_pattern = f'%{search_query}%'
            query = query.filter(
                or_(
                    CrmTicket.description.ilike(search_pattern),
                    ChannelCustomer.name.ilike(search_pattern),
                    Channel.name.ilike(search_pattern)
                )
            )
    
    # Due date filtering
    today = date.today()
    
    def get_month_range(year, month):
        """Get first and last day of a month"""
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        return first_day, last_day
    
    def get_week_range(start_date):
        """Get the week range from start_date to next Sunday (inclusive)"""
        # Get the day of week (0=Monday, 6=Sunday)
        # Calculate days until next Sunday
        current_weekday = start_date.weekday()  # 0=Monday, 6=Sunday
        if current_weekday == 6:
            # If it's Sunday, the week ends today
            end_date = start_date
        else:
            # Calculate days until next Sunday
            # Sunday is day 6, so if today is Tuesday (1), we need 5 more days (6-1=5)
            days_until_sunday = 6 - current_weekday
            end_date = start_date + timedelta(days=days_until_sunday)
        return start_date, end_date
    
    def get_next_week_range():
        """Get next week's Monday to Sunday"""
        # Find next Monday
        current_weekday = today.weekday()  # 0=Monday, 6=Sunday
        if current_weekday == 0:
            # If today is Monday, next Monday is in 7 days
            next_monday = today + timedelta(days=7)
        else:
            # Calculate days until next Monday
            # If today is Tuesday (1), next Monday is in 6 days (7-1=6)
            days_until_monday = 7 - current_weekday
            next_monday = today + timedelta(days=days_until_monday)
        # Next Sunday is 6 days after next Monday
        next_sunday = next_monday + timedelta(days=6)
        return next_monday, next_sunday
    
    if due_date_filter == 'past_due':
        # Past due: ticket is opened and (no due date OR due date < today)
        query = query.filter(
            CrmTicket.status == 'opened',
            or_(
                CrmTicket.due_date.is_(None),
                CrmTicket.due_date < today
            )
        )
    elif due_date_filter == 'current_month':
        # Current month: due date is in the current month
        first_day, last_day = get_month_range(today.year, today.month)
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'next_month':
        # Next month: due date is in the next month
        if today.month == 12:
            next_year, next_month = today.year + 1, 1
        else:
            next_year, next_month = today.year, today.month + 1
        first_day, last_day = get_month_range(next_year, next_month)
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'month_2':
        # Month +2: due date is in 2 months from now
        month_2 = today.month + 2
        year_2 = today.year
        if month_2 > 12:
            month_2 -= 12
            year_2 += 1
        first_day, last_day = get_month_range(year_2, month_2)
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'month_3':
        # Month +3: due date is in 3 months from now
        month_3 = today.month + 3
        year_3 = today.year
        if month_3 > 12:
            month_3 -= 12
            year_3 += 1
        first_day, last_day = get_month_range(year_3, month_3)
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'current_week':
        # Current week: from today to next Sunday
        first_day, last_day = get_week_range(today)
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'next_week':
        # Next week: Monday to Sunday of next week
        first_day, last_day = get_next_week_range()
        query = query.filter(
            and_(
                CrmTicket.due_date >= first_day,
                CrmTicket.due_date <= last_day
            )
        )
    elif due_date_filter == 'current_and_next_week':
        # Current & Next week: from today to end of next week
        current_start, current_end = get_week_range(today)
        next_start, next_end = get_next_week_range()
        # Combine both ranges
        query = query.filter(
            or_(
                and_(
                    CrmTicket.due_date >= current_start,
                    CrmTicket.due_date <= current_end
                ),
                and_(
                    CrmTicket.due_date >= next_start,
                    CrmTicket.due_date <= next_end
                )
            )
        )
    
    # Order by due_date DESC if not null, then by created_at DESC
    # Use pagination
    tickets_pagination = query.order_by(
        case(
            (CrmTicket.due_date.isnot(None), CrmTicket.due_date),
            else_=None
        ).desc().nullslast(),
        CrmTicket.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    tickets = tickets_pagination.items
    
    # Get all customers and users for filters
    customers = ChannelCustomer.query.join(Channel).order_by(Channel.name, ChannelCustomer.name).all()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT id, username, email
            FROM users
            WHERE is_active = TRUE
            ORDER BY username
        """)
        users = [dict(u) for u in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()
    
    # Get ticket types, flags, and brands for the overlay and filters
    ticket_types = CrmTicketType.query.order_by(CrmTicketType.name).all()
    flags = CrmTicketFlag.query.order_by(CrmTicketFlag.name).all()
    brands = Brand.query.order_by(Brand.name).all()
    
    return render_template('crm/all_tickets.html',
                         tickets=tickets,
                         pagination=tickets_pagination,
                         customers=customers,
                         users=users,
                         ticket_types=ticket_types,
                         flags=flags,
                         brands=brands,
                         selected_customer_id=customer_id,
                         selected_owner_id=owner_id,
                         selected_status=status,
                         selected_due_date_filter=due_date_filter,
                         selected_ticket_type_id=ticket_type_id,
                         selected_flag_id=flag_id,
                         selected_brand_id=brand_id,
                         search_query=search_query,
                         today=today)


@crm_bp.route('/ticket-types')
@login_required
def ticket_types_list():
    """List all ticket types and flags"""
    ticket_types = CrmTicketType.query.order_by(CrmTicketType.name).all()
    flags = CrmTicketFlag.query.order_by(CrmTicketFlag.name).all()
    return render_template('crm/ticket_types_list.html', ticket_types=ticket_types, flags=flags)


@crm_bp.route('/ticket-types/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_ticket_type():
    """Create a new ticket type"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('Ticket type name is required', 'error')
            return render_template('crm/edit_ticket_type.html')
        
        if CrmTicketType.query.filter_by(name=name).first():
            flash('Ticket type with this name already exists', 'error')
            return render_template('crm/edit_ticket_type.html')
        
        ticket_type = CrmTicketType(name=name)
        db.session.add(ticket_type)
        db.session.commit()
        flash(f'Ticket type "{name}" created successfully', 'success')
        return redirect(url_for('crm.ticket_types_list'))
    
    return render_template('crm/edit_ticket_type.html')


@crm_bp.route('/ticket-types/<int:ticket_type_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_ticket_type(ticket_type_id):
    """Edit a ticket type"""
    ticket_type = CrmTicketType.query.get_or_404(ticket_type_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('Ticket type name is required', 'error')
            return render_template('crm/edit_ticket_type.html', ticket_type=ticket_type)
        
        existing = CrmTicketType.query.filter_by(name=name).first()
        if existing and existing.id != ticket_type_id:
            flash('Ticket type with this name already exists', 'error')
            return render_template('crm/edit_ticket_type.html', ticket_type=ticket_type)
        
        ticket_type.name = name
        db.session.commit()
        flash(f'Ticket type updated successfully', 'success')
        return redirect(url_for('crm.ticket_types_list'))
    
    return render_template('crm/edit_ticket_type.html', ticket_type=ticket_type)


@crm_bp.route('/ticket-types/<int:ticket_type_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_ticket_type(ticket_type_id):
    """Delete a ticket type"""
    ticket_type = CrmTicketType.query.get_or_404(ticket_type_id)
    name = ticket_type.name
    
    # Check if ticket type has tickets
    tickets_count = CrmTicket.query.filter_by(ticket_type_id=ticket_type_id).count()
    if tickets_count > 0:
        flash(f'Cannot delete ticket type "{name}" because it has {tickets_count} associated ticket(s).', 'error')
        return redirect(url_for('crm.ticket_types_list'))
    
    db.session.delete(ticket_type)
    db.session.commit()
    flash(f'Ticket type "{name}" deleted successfully', 'success')
    return redirect(url_for('crm.ticket_types_list'))


# Flag management routes
@crm_bp.route('/ticket-flags/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_ticket_flag():
    """Create a new ticket flag"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '#667eea').strip()
        text_color = request.form.get('text_color', '#FFFFFF').strip()
        
        if not name:
            flash('Flag name is required', 'error')
            return render_template('crm/edit_ticket_flag.html')
        
        if CrmTicketFlag.query.filter_by(name=name).first():
            flash('Flag with this name already exists', 'error')
            return render_template('crm/edit_ticket_flag.html')
        
        flag = CrmTicketFlag(name=name, color=color, text_color=text_color)
        db.session.add(flag)
        db.session.commit()
        flash(f'Flag "{name}" created successfully', 'success')
        return redirect(url_for('crm.ticket_types_list'))
    
    return render_template('crm/edit_ticket_flag.html')


@crm_bp.route('/ticket-flags/<int:flag_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_ticket_flag(flag_id):
    """Edit a ticket flag"""
    flag = CrmTicketFlag.query.get_or_404(flag_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '#667eea').strip()
        text_color = request.form.get('text_color', '#FFFFFF').strip()
        
        if not name:
            flash('Flag name is required', 'error')
            return render_template('crm/edit_ticket_flag.html', flag=flag)
        
        existing = CrmTicketFlag.query.filter_by(name=name).first()
        if existing and existing.id != flag_id:
            flash('Flag with this name already exists', 'error')
            return render_template('crm/edit_ticket_flag.html', flag=flag)
        
        flag.name = name
        flag.color = color
        flag.text_color = text_color
        db.session.commit()
        flash(f'Flag updated successfully', 'success')
        return redirect(url_for('crm.ticket_types_list'))
    
    return render_template('crm/edit_ticket_flag.html', flag=flag)


@crm_bp.route('/ticket-flags/<int:flag_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_ticket_flag(flag_id):
    """Delete a ticket flag"""
    flag = CrmTicketFlag.query.get_or_404(flag_id)
    name = flag.name
    
    # Check if flag has tickets (optional - flags can be removed from tickets)
    tickets_count = flag.tickets.count()
    if tickets_count > 0:
        flash(f'Flag "{name}" is currently used by {tickets_count} ticket(s). It will be removed from those tickets.', 'info')
    
    db.session.delete(flag)
    db.session.commit()
    flash(f'Flag "{name}" deleted successfully', 'success')
    return redirect(url_for('crm.ticket_types_list'))

