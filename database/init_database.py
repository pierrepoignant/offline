#!/usr/bin/env python3
"""
Initialize the offline database
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import create_database, get_connection

def init_database():
    """Initialize the database with required tables"""
    print("Initializing offline database...")
    
    # Create database if it doesn't exist
    create_database()
    
    # Connect to the database
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Read and execute SQL file
        sql_file = os.path.join(os.path.dirname(__file__), 'create_users_table.sql')
        with open(sql_file, 'r') as f:
            sql = f.read()
            cursor.execute(sql)
        
        conn.commit()
        print("✓ Database tables created successfully")
        
        # Create initial admin user if it doesn't exist
        from werkzeug.security import generate_password_hash
        import configparser
        
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
        config.read(config_path)
        
        admin_username = config.get('auth', 'username', fallback='admin')
        admin_password = config.get('auth', 'password', fallback='12345678')
        
        cursor.execute("SELECT id FROM users WHERE username = %s", (admin_username,))
        if not cursor.fetchone():
            password_hash = generate_password_hash(admin_password, method='pbkdf2:sha256')
            cursor.execute("""
                INSERT INTO users (username, password_hash, is_admin, is_active)
                VALUES (%s, %s, TRUE, TRUE)
            """, (admin_username, password_hash))
            conn.commit()
            print(f"✓ Initial admin user '{admin_username}' created")
        else:
            print(f"✓ Admin user '{admin_username}' already exists")
        
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()
    
    print("Database initialization complete!")

if __name__ == '__main__':
    init_database()

