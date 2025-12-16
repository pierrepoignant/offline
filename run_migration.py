#!/usr/bin/env python3
"""
Run Alembic migrations for production database
This script runs Alembic migrations using the configured database
"""

import os
import sys
from alembic.config import Config
from alembic import command

# Set production database environment variables (will use remote by default)
# These can be overridden by command line or environment
if not os.getenv('DB_HOST'):
    os.environ['DB_HOST'] = 'postgresql-cfb9d8a7-o06c3efae.database.cloud.ovh.net'
    os.environ['DB_PORT'] = '20184'
    os.environ['DB_USER'] = 'avnadmin'
    os.environ['DB_PASSWORD'] = 'sX9Q1N78HgODzR6anjYV'
    os.environ['DB_NAME'] = 'offline'

def run_migrations():
    """Run Alembic migrations"""
    print("Running Alembic migrations...")
    print(f"Host: {os.getenv('DB_HOST')}")
    print(f"Database: {os.getenv('DB_NAME')}")
    
    # Get the Alembic configuration
    alembic_cfg = Config("alembic.ini")
    
    try:
        print("\nUpgrading database to head...")
        command.upgrade(alembic_cfg, "head")
        print("✓ Migrations applied successfully!")
    except Exception as e:
        print(f"✗ Error running migrations: {e}")
        sys.exit(1)

if __name__ == '__main__':
    run_migrations()

