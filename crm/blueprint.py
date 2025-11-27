#!/usr/bin/env python3
"""
CRM blueprint for managing customer tickets
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from datetime import datetime, date
from models import db, CrmTicket, CrmTicketType, ChannelCustomer, User
from auth.blueprint import login_required, admin_required
from sqlalchemy import or_, case
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
        tickets_data.append({
            'id': ticket.id,
            'status': ticket.status,
            'description': ticket.description,
            'due_date': ticket.due_date.isoformat() if ticket.due_date else None,
            'creator': ticket.creator.username if ticket.creator else 'Unknown',
            'owner': ticket.owner.username if ticket.owner else 'Unknown',
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None
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
    db.session.commit()
    
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
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None
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


@crm_bp.route('/tickets/<int:ticket_id>/edit', methods=['POST'])
@login_required
def edit_ticket(ticket_id):
    """Edit a ticket"""
    ticket = CrmTicket.query.get_or_404(ticket_id)
    
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
    
    db.session.commit()
    
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
            'ticket_type': ticket.ticket_type.name if ticket.ticket_type else None
        }
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


@crm_bp.route('/tickets')
@login_required
def all_tickets():
    """List all tickets with filtering"""
    from models import Channel
    
    # Get filter parameters
    customer_id = request.args.get('customer_id', type=int)
    owner_id = request.args.get('owner_id', type=int)
    status = request.args.get('status', '').strip()
    
    # Build query
    query = CrmTicket.query
    
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    if owner_id:
        query = query.filter_by(owner_id=owner_id)
    if status in ['opened', 'closed']:
        query = query.filter_by(status=status)
    
    # Order by due_date DESC if not null, then by created_at DESC
    tickets = query.order_by(
        case(
            (CrmTicket.due_date.isnot(None), CrmTicket.due_date),
            else_=None
        ).desc().nullslast(),
        CrmTicket.created_at.desc()
    ).all()
    
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
    
    from datetime import date as date_type
    today = date_type.today()
    
    return render_template('crm/all_tickets.html',
                         tickets=tickets,
                         customers=customers,
                         users=users,
                         selected_customer_id=customer_id,
                         selected_owner_id=owner_id,
                         selected_status=status,
                         today=today)


@crm_bp.route('/ticket-types')
@login_required
def ticket_types_list():
    """List all ticket types"""
    ticket_types = CrmTicketType.query.order_by(CrmTicketType.name).all()
    return render_template('crm/ticket_types_list.html', ticket_types=ticket_types)


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

