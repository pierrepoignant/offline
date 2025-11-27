#!/usr/bin/env python3
"""
Auth blueprint for user authentication and management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from db_utils import get_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime

auth_bp = Blueprint('auth', __name__, template_folder='templates')

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login', next=request.url))
        if not session.get('is_admin'):
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def verify_user(username, password):
    """Verify user credentials against database"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT id, username, password_hash, is_admin, is_active, email
            FROM users
            WHERE username = %s AND is_active = TRUE
        """, (username,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            # Update last login
            cursor.execute("""
                UPDATE users SET last_login = NOW() WHERE id = %s
            """, (user['id'],))
            conn.commit()
            return dict(user)
        return None
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return render_template('login.html')
        
        user = verify_user(username, password)
        
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['email'] = user.get('email')
            
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/users')
@login_required
@admin_required
def users_list():
    """List all users"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT id, username, email, is_admin, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()
        return render_template('users_list.html', users=users)
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """Create a new user"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email') or None
        is_admin = 'is_admin' in request.form
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('edit_user.html')
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            cursor.execute("""
                INSERT INTO users (username, password_hash, email, is_admin)
                VALUES (%s, %s, %s, %s)
            """, (username, password_hash, email, is_admin))
            conn.commit()
            flash(f'User {username} created successfully', 'success')
            return redirect(url_for('auth.users_list'))
        except Exception as e:
            conn.rollback()
            flash(f'Error creating user: {str(e)}', 'error')
            return render_template('edit_user.html')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('auth/edit_user.html')

@auth_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit an existing user"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email') or None
            is_admin = 'is_admin' in request.form
            is_active = 'is_active' in request.form
            password = request.form.get('password')
            
            if not username:
                flash('Username is required', 'error')
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                return render_template('edit_user.html', user=dict(user))
            
            # Update user
            if password:
                password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                cursor.execute("""
                    UPDATE users 
                    SET username = %s, email = %s, is_admin = %s, is_active = %s, password_hash = %s
                    WHERE id = %s
                """, (username, email, is_admin, is_active, password_hash, user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET username = %s, email = %s, is_admin = %s, is_active = %s
                    WHERE id = %s
                """, (username, email, is_admin, is_active, user_id))
            
            conn.commit()
            flash(f'User {username} updated successfully', 'success')
            return redirect(url_for('auth.users_list'))
        
        # GET request - load user data
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('auth.users_list'))
        
        return render_template('edit_user.html', user=dict(user))
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user (soft delete by setting is_active=False)"""
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account', 'error')
        return redirect(url_for('auth.users_list'))
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE users SET is_active = FALSE WHERE id = %s
        """, (user_id,))
        conn.commit()
        flash('User deactivated successfully', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error deactivating user: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('auth.users_list'))

