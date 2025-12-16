#!/usr/bin/env python3
"""
Sync blueprint for syncing item status & ASINs from Snowflake
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os
import configparser
from models import db, Asin, Item
from auth.blueprint import login_required, admin_required

sync_bp = Blueprint('sync', __name__, template_folder='templates')

def get_snowflake_config():
    """Get Snowflake configuration from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    
    snowflake_config = config['snowflake']
    return {
        'account': snowflake_config.get('account'),
        'user': snowflake_config.get('user'),
        'private_key_path': os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            snowflake_config.get('private_key_path')
        ),
        'warehouse': snowflake_config.get('warehouse', ''),
        'database': snowflake_config.get('database', 'DWH'),
        'schema': snowflake_config.get('schema', 'NETSUITE')
    }

def get_snowflake_connection():
    """Create Snowflake connection using private key authentication"""
    config = get_snowflake_config()
    
    # Read private key - handle both PEM and PKCS8 formats
    with open(config['private_key_path'], 'rb') as key_file:
        key_data = key_file.read()
        
        # Try to load as PEM first
        try:
            p_key = serialization.load_pem_private_key(
                key_data,
                password=None,
                backend=default_backend()
            )
        except ValueError:
            # If PEM fails, try DER format
            try:
                p_key = serialization.load_der_private_key(
                    key_data,
                    password=None,
                    backend=default_backend()
                )
            except ValueError:
                raise ValueError("Unable to load private key. Ensure it's in PEM or DER format.")
    
    # Convert to DER format for Snowflake connector
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Create connection parameters
    conn_params = {
        'account': config['account'],
        'user': config['user'],
        'private_key': pkb,
        'database': config['database'],
        'schema': config['schema']
    }
    
    # Add warehouse if specified
    if config['warehouse']:
        conn_params['warehouse'] = config['warehouse']
    
    # Create connection
    conn = snowflake.connector.connect(**conn_params)
    
    return conn

def _load_asin_status_query():
    """Load the ASIN status query from asin_status.sql"""
    query_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'snowflake', 'asin_status.sql')
    with open(query_path, 'r') as f:
        return f.read()

@sync_bp.route('/')
@login_required
@admin_required
def index():
    """Sync status & ASINs page"""
    return render_template('sync/index.html')

@sync_bp.route('/update', methods=['POST'])
@login_required
@admin_required
def update():
    """Execute the sync process"""
    try:
        print("\n" + "="*60)
        print("Starting Item Status & ASIN Sync Process")
        print("="*60)
        
        # Step 1: Get latest items information from Snowflake
        print("\n📊 Step 1: Fetching data from Snowflake...")
        conn = get_snowflake_connection()
        cursor = conn.cursor()
        
        query = _load_asin_status_query()
        cursor.execute(query)
        
        # Fetch all results
        columns = [desc[0] for desc in cursor.description]
        snowflake_data = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            snowflake_data.append(row_dict)
        
        cursor.close()
        conn.close()
        
        print(f"✓ Fetched {len(snowflake_data)} records from Snowflake")
        
        # Create a mapping of ASIN -> status for quick lookup
        asin_status_map = {}
        # Create a mapping of NETSUITE_ITEM_NUMBER -> (ASIN, status) for items
        item_asin_map = {}
        
        for row in snowflake_data:
            asin = row.get('ASIN')
            status = row.get('ALIAS_PRODUCT_STATUS')
            netsuite_item_number = row.get('NETSUITE_ITEM_NUMBER')
            
            if asin and status:
                asin_status_map[asin] = status
            
            if netsuite_item_number and asin and status:
                item_asin_map[netsuite_item_number] = {
                    'asin': asin,
                    'status': status
                }
        
        print(f"✓ Created mappings: {len(asin_status_map)} ASINs, {len(item_asin_map)} items")
        
        # Step 2: Get all ASINs from database and update their status
        print("\n📦 Step 2: Updating ASIN status...")
        all_asins = Asin.query.all()
        asins_updated = 0
        
        for asin_obj in all_asins:
            if asin_obj.asin in asin_status_map:
                new_status = asin_status_map[asin_obj.asin]
                if asin_obj.status != new_status:
                    asin_obj.status = new_status
                    asins_updated += 1
        
        db.session.commit()
        print(f"✓ Updated {asins_updated} ASINs")
        
        # Step 3: Get all items from database
        print("\n📋 Step 3: Processing items...")
        all_items = Item.query.all()
        items_updated = 0
        items_linked = 0
        asins_created = 0
        
        for item in all_items:
            item_updated = False
            
            # Step 3.1: If item doesn't have asin_id, try to get ASIN from Snowflake data
            if not item.asin_id and item.essor_code:
                if item.essor_code in item_asin_map:
                    asin_data = item_asin_map[item.essor_code]
                    asin_value = asin_data['asin']
                    
                    # Look up ASIN in database
                    asin_obj = Asin.query.filter_by(asin=asin_value).first()
                    
                    # If ASIN doesn't exist, create it
                    if not asin_obj:
                        asin_obj = Asin(asin=asin_value, status=asin_data['status'])
                        db.session.add(asin_obj)
                        db.session.flush()  # Get the ID
                        asins_created += 1
                        print(f"  ➕ Created new ASIN: {asin_value}")
                    
                    # Link item to ASIN
                    item.asin_id = asin_obj.id
                    item_updated = True
                    items_linked += 1
                    print(f"  🔗 Linked item {item.essor_code} to ASIN {asin_value}")
            
            # Step 3.2: Update item status using status from Step 1
            # Prioritize status from item_asin_map (more specific, tied to essor_code)
            if item.essor_code and item.essor_code in item_asin_map:
                new_status = item_asin_map[item.essor_code]['status']
                if item.status != new_status:
                    item.status = new_status
                    item_updated = True
            # Fallback: update status from ASIN if item has an ASIN linked but no essor_code match
            elif item.asin_id and item.asin_obj:
                asin_value = item.asin_obj.asin
                if asin_value in asin_status_map:
                    new_status = asin_status_map[asin_value]
                    if item.status != new_status:
                        item.status = new_status
                        item_updated = True
            
            if item_updated:
                items_updated += 1
        
        db.session.commit()
        
        print(f"✓ Updated {items_updated} items")
        print(f"✓ Linked {items_linked} items to ASINs")
        print(f"✓ Created {asins_created} new ASINs")
        
        print("\n" + "="*60)
        print("Sync completed successfully!")
        print("="*60)
        
        flash(f'Sync completed successfully! Updated {asins_updated} ASINs, {items_updated} items, linked {items_linked} items, and created {asins_created} new ASINs.', 'success')
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error during sync: {str(e)}"
        print(f"\n❌ {error_msg}")
        import traceback
        traceback.print_exc()
        flash(error_msg, 'error')
    
    return redirect(url_for('sync.index'))

