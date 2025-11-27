#!/usr/bin/env python3
"""
Add oos field to sellthrough_data table and make location_id nullable
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
from models import db
from sqlalchemy import text

def update_schema():
    """Update sellthrough_data table schema"""
    print("Connecting to production database...")
    print(f"Host: {os.getenv('DB_HOST')}")
    print(f"Database: {os.getenv('DB_NAME')}")
    
    app = create_app(db_type=None)  # Use remote database by default
    
    with app.app_context():
        print("\nUpdating sellthrough_data table schema...")
        try:
            # Add oos column if it doesn't exist
            try:
                db.session.execute(text("ALTER TABLE sellthrough_data ADD COLUMN oos NUMERIC(5, 2)"))
                print("✓ Added 'oos' column")
            except Exception as e:
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    print("✓ Column 'oos' already exists")
                else:
                    raise
            
            # Make location_id nullable
            try:
                db.session.execute(text("ALTER TABLE sellthrough_data ALTER COLUMN location_id DROP NOT NULL"))
                print("✓ Made 'location_id' nullable")
            except Exception as e:
                print(f"⚠ Could not modify location_id: {e}")
            
            # Add unique constraint if it doesn't exist
            try:
                db.session.execute(text("""
                    ALTER TABLE sellthrough_data 
                    ADD CONSTRAINT uq_sellthrough_unique 
                    UNIQUE (date, channel_id, item_id, location_id)
                """))
                print("✓ Added unique constraint")
            except Exception as e:
                if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                    print("✓ Unique constraint already exists")
                else:
                    print(f"⚠ Could not add unique constraint: {e}")
            
            db.session.commit()
            print("\n✓ Schema update completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"✗ Error updating schema: {e}")
            sys.exit(1)

if __name__ == '__main__':
    update_schema()

