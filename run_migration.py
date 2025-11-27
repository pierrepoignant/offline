#!/usr/bin/env python3
"""
Run Alembic migrations for production database
This script creates all database tables using SQLAlchemy
"""

import os
import sys

# Set production database environment variables (will use remote by default)
# These can be overridden by command line or environment
if not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = 'postgresql-cfb9d8a7-o06c3efae.database.cloud.ovh.net'
    os.environ['DB_PORT'] = '20184'
    os.environ['DB_USER'] = 'avnadmin'
    os.environ['DB_PASSWORD'] = 'sX9Q1N78HgODzR6anjYV'
    os.environ['DB_NAME'] = 'offline'

# Import after setting env vars
from app import create_app
from models import db, Brand, Category, Channel, ChannelCustomer, Item, SellthroughData

def create_tables():
    """Create all tables using SQLAlchemy"""
    print("Connecting to production database...")
    print(f"Host: {os.getenv('DB_HOST')}")
    print(f"Database: {os.getenv('DB_NAME')}")
    
    app = create_app(db_type=None)  # Use remote database by default
    
    with app.app_context():
        print("\nCreating database tables...")
        try:
            db.create_all()
            print("✓ All tables created successfully!")
            print("\nCreated tables:")
            print("  - brands")
            print("  - categories")
            print("  - channels")
            print("  - channel_locations")
            print("  - items")
            print("  - sellthrough_data")
        except Exception as e:
            print(f"✗ Error creating tables: {e}")
            sys.exit(1)

if __name__ == '__main__':
    create_tables()

