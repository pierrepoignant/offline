#!/usr/bin/env python3
"""
Cron script to run Netsuite import
This script is called by cron to import 2025 data since last entry
"""

import os
import sys
from app import create_app
from netsuite.blueprint import _execute_netsuite_import

def main():
    """Run the automated Netsuite import"""
    # Create app context
    app = create_app(db_type=None)  # Use remote database
    
    with app.app_context():
        try:
            print("\n" + "="*60)
            print("Starting Automated Cron Import")
            print("="*60)
            
            results = _execute_netsuite_import(
                table_name='NET_REVENUE_OFFLINE_CHANNELS',
                import_method='incremental',
                dry_run=False
            )
            
            print("\n" + "="*60)
            print("Cron Import Summary:")
            print(f"  ✓ Processed: {results['processed']} rows")
            print(f"  ➕ Created: {results['created']} records")
            print(f"  ↻ Updated: {results['updated']} records")
            print(f"  ⚠ Skipped: {results['skipped']} rows")
            if results['errors']:
                print(f"  ✗ Errors: {len(results['errors'])} errors occurred")
            print("="*60 + "\n")
            
            # Exit with error code if there were errors
            if results['errors']:
                sys.exit(1)
            else:
                sys.exit(0)
                
        except Exception as e:
            print(f"\n✗ ERROR in cron import: {str(e)}")
            import traceback
            print(traceback.format_exc())
            sys.exit(1)

if __name__ == '__main__':
    main()

