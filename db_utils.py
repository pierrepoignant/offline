#!/usr/bin/env python3
"""
Shared database utilities for the offline project
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
import configparser

def get_config():
    """Read configuration from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    config.read(config_path)
    return config

def get_db_params(db_type=None):
    """Get database parameters from config.ini with environment variable fallbacks
    
    Args:
        db_type: 'local' to use postgre-local section, None or 'remote' to use postgre section (default)
    """
    config = get_config()
    
    # Default to remote database unless explicitly set to local
    # Check for DB_TYPE environment variable or use db_type parameter
    env_db_type = os.getenv('DB_TYPE', db_type)
    
    if env_db_type == 'local':
        section = 'postgre-local'
    else:
        # Default to remote (postgre section)
        section = 'postgre'
    
    return {
        'host': os.getenv('DB_HOST', config.get(section, 'host', fallback='127.0.0.1')),
        'port': int(os.getenv('DB_PORT', config.get(section, 'port', fallback='5432'))),
        'user': os.getenv('DB_USER', config.get(section, 'user', fallback='postgres')),
        'password': os.getenv('DB_PASSWORD', config.get(section, 'password', fallback='')),
        'database': os.getenv('DB_NAME', config.get(section, 'database', fallback='offline'))
    }

def get_db_uri(db_type=None):
    """Get SQLAlchemy database URI
    
    Args:
        db_type: 'local' to use postgre-local section, None or 'remote' to use postgre section (default)
    """
    params = get_db_params(db_type)
    return f"postgresql://{params['user']}:{params['password']}@{params['host']}:{params['port']}/{params['database']}"

def get_connection():
    """Create PostgreSQL database connection"""
    try:
        params = get_db_params()
        connection = psycopg2.connect(
            host=params['host'],
            port=params['port'],
            user=params['user'],
            password=params['password'],
            database=params['database']
        )
        return connection
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        raise

def create_database():
    """Create the offline database if it doesn't exist"""
    try:
        params = get_db_params()
        
        # First, try to connect directly to the target database
        try:
            test_conn = psycopg2.connect(
                host=params['host'],
                port=params['port'],
                user=params['user'],
                password=params['password'],
                database=params['database']
            )
            test_conn.close()
            print(f"✓ Database '{params['database']}' already exists and is accessible")
            return
        except psycopg2.OperationalError:
            # Database doesn't exist, try to create it
            pass
        
        # Try to connect to postgres database to create the offline database
        # This might fail in managed databases where we don't have permission
        try:
            connection = psycopg2.connect(
                host=params['host'],
                port=params['port'],
                user=params['user'],
                password=params['password'],
                database='postgres'  # Connect to default postgres database
            )
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{params['database']}'")
            exists = cursor.fetchone()
            if not exists:
                cursor.execute(f"CREATE DATABASE {params['database']}")
                print(f"✓ Database '{params['database']}' created")
            else:
                print(f"✓ Database '{params['database']}' already exists")
            cursor.close()
            connection.close()
        except (psycopg2.OperationalError, psycopg2.Error) as e:
            # In managed databases, we might not have permission to create databases
            # or connect to the postgres database. Assume the database already exists.
            print(f"⚠ Could not verify/create database (this is normal in managed databases): {e}")
            print(f"⚠ Assuming database '{params['database']}' exists and continuing...")
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

