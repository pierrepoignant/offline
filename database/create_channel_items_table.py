#!/usr/bin/env python3
"""
Create channel_items table in the database
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set production database environment variables (will use remote by default)
if not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = 'postgresql-cfb9d8a7-o06c3efae.database.cloud.ovh.net'
    os.environ['DB_PORT'] = '20184'
    os.environ['DB_USER'] = 'avnadmin'
    os.environ['DB_PASSWORD'] = 'sX9Q1N78HgODzR6anjYV'
    os.environ['DB_NAME'] = 'offline'

# Import after setting env vars
from app import create_app
from models import db, ChannelItem

def create_table():
    """Create channel_items table"""
    print("Connecting to production database...")
    print(f"Host: {os.getenv('DB_HOST')}")
    print(f"Database: {os.getenv('DB_NAME')}")
    
    app = create_app(db_type=None)  # Use remote database by default
    
    with app.app_context():
        print("\nCreating channel_items table...")
        try:
            db.create_all()
            print("✓ channel_items table created successfully!")
        except Exception as e:
            print(f"✗ Error creating table: {e}")
            sys.exit(1)

if __name__ == '__main__':
    create_table()

