#!/usr/bin/env python3
"""
Script to flush (delete) all items and sellthrough_data from the database
This will also delete related channel_items due to cascade relationships
"""

import sys
import os
from flask import Flask

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Item, SellthroughData, ChannelItem

def flush_items_and_sellthrough():
    """Delete all items and sellthrough_data from the database"""
    app = create_app()
    
    with app.app_context():
        print("="*60)
        print("⚠ WARNING: This will delete ALL items and sellthrough data!")
        print("="*60)
        
        # Count records before deletion
        item_count = Item.query.count()
        sellthrough_count = SellthroughData.query.count()
        channel_item_count = ChannelItem.query.count()
        
        print(f"\n📊 Current database state:")
        print(f"  - Items: {item_count}")
        print(f"  - Channel Items: {channel_item_count}")
        print(f"  - Sellthrough Data: {sellthrough_count}")
        
        if item_count == 0 and sellthrough_count == 0:
            print("\n✓ Database is already empty. Nothing to delete.")
            return
        
        # Confirm deletion
        response = input("\n⚠ Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return
        
        print("\n🗑️  Starting deletion...")
        
        try:
            # Delete sellthrough_data first (due to foreign key constraints)
            print(f"  Deleting {sellthrough_count} sellthrough_data records...")
            SellthroughData.query.delete()
            print("  ✓ Sellthrough data deleted")
            
            # Delete channel_items (will be deleted automatically due to cascade, but let's be explicit)
            print(f"  Deleting {channel_item_count} channel_item records...")
            ChannelItem.query.delete()
            print("  ✓ Channel items deleted")
            
            # Delete items (this will also cascade delete channel_items)
            print(f"  Deleting {item_count} item records...")
            Item.query.delete()
            print("  ✓ Items deleted")
            
            # Commit changes
            db.session.commit()
            print("\n✅ Successfully flushed all items and sellthrough data from the database!")
            
            # Verify deletion
            remaining_items = Item.query.count()
            remaining_sellthrough = SellthroughData.query.count()
            remaining_channel_items = ChannelItem.query.count()
            
            print(f"\n📊 Verification:")
            print(f"  - Remaining Items: {remaining_items}")
            print(f"  - Remaining Channel Items: {remaining_channel_items}")
            print(f"  - Remaining Sellthrough Data: {remaining_sellthrough}")
            
            if remaining_items == 0 and remaining_sellthrough == 0:
                print("\n✓ Database successfully flushed!")
            else:
                print("\n⚠ Warning: Some records may still exist. Check for foreign key constraints.")
                
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error during deletion: {str(e)}")
            import traceback
            print(traceback.format_exc())
            raise

if __name__ == '__main__':
    flush_items_and_sellthrough()

