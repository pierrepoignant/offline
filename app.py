#!/usr/bin/env python3
"""
Flask app for offline team utilities
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, session, render_template, redirect, url_for, request
import argparse
from auth.blueprint import login_required

def create_app(db_type=None):
    """Create and configure the Flask app
    
    Args:
        db_type: 'local' to use local database, None or 'remote' to use remote database (default)
    """
    app = Flask(__name__)
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this-for-production')
    
    # Configure database
    from db_utils import get_db_uri
    app.config['SQLALCHEMY_DATABASE_URI'] = get_db_uri(db_type)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize SQLAlchemy
    from models import db
    db.init_app(app)
    
    # Import blueprints after app is created
    from auth.blueprint import auth_bp
    from core.blueprint import core_bp
    from sellthrough.blueprint import sellthrough_bp
    from netsuite.blueprint import netsuite_bp
    from spins.blueprint import spins_bp
    from imports.blueprint import import_bp
    from scraping.blueprint import scraping_bp
    from crm.blueprint import crm_bp
    from targets.blueprint import targets_bp
    from faire.blueprint import faire_bp
    from sync.blueprint import sync_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(core_bp, url_prefix='/core')
    app.register_blueprint(sellthrough_bp, url_prefix='/sellthrough')
    app.register_blueprint(netsuite_bp, url_prefix='/netsuite')
    app.register_blueprint(spins_bp, url_prefix='/spins')
    app.register_blueprint(import_bp, url_prefix='/imports')
    app.register_blueprint(scraping_bp, url_prefix='/scraping')
    app.register_blueprint(crm_bp, url_prefix='/crm')
    app.register_blueprint(targets_bp, url_prefix='/targets')
    app.register_blueprint(faire_bp, url_prefix='/faire')
    app.register_blueprint(sync_bp, url_prefix='/sync')
    
    @app.route('/')
    def index():
        """Home page"""
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        
        return render_template('home.html',
                             username=session.get('username'))
    
    @app.route('/products')
    @login_required
    def products():
        """Products dashboard - display all products as cards with search, filter, and pagination"""
        from models import Item, Brand
        from sqlalchemy import or_
        
        # Get query parameters
        search_query = request.args.get('search', '').strip()
        brand_id = request.args.get('brand_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = 24  # Items per page
        
        # Build base query
        query = Item.query.join(Brand)
        
        # Apply search filter (search in essor_name and essor_code)
        if search_query:
            query = query.filter(
                or_(
                    Item.essor_name.ilike(f'%{search_query}%'),
                    Item.essor_code.ilike(f'%{search_query}%')
                )
            )
        
        # Apply brand filter
        if brand_id:
            query = query.filter(Item.brand_id == brand_id)
        
        # Order by brand name and item code
        query = query.order_by(Brand.name, Item.essor_code)
        
        # Paginate results
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        # Get all brands for the filter dropdown
        brands = Brand.query.order_by(Brand.name).all()
        
        return render_template('products.html', 
                             items=pagination.items,
                             pagination=pagination,
                             brands=brands,
                             search_query=search_query,
                             selected_brand_id=brand_id)
    
    return app

# Create app instance for gunicorn (will be overridden if run as main)
app = None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Offline Team Utilities Flask App')
    parser.add_argument('--db', choices=['local', 'remote'], default='remote',
                       help='Database to use: local or remote (default: remote)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode (default: False)')
    parser.add_argument('--port', type=int, default=None,
                       help='Port to run on (default: 5000 or FLASK_PORT env var)')
    
    args = parser.parse_args()
    
    # Determine database type
    db_type = 'local' if args.db == 'local' else None
    
    # Create app with specified database
    app = create_app(db_type=db_type)
    
    # Get port
    port = args.port or int(os.getenv('FLASK_PORT', 5000))
    
    # Run with debug mode based on argument
    app.run(host='0.0.0.0', port=port, debug=args.debug)
else:
    # For gunicorn, use remote database by default
    app = create_app(db_type=None)

