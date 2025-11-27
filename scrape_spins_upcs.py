#!/usr/bin/env python3
"""
Standalone script to scrape SPINS UPCs and update the database.
Can be run outside of the Flask app.

Usage:
    # Scrape all unscraped SPINS items
    python scrape_spins_upcs.py --all

    # Scrape specific item by ID
    python scrape_spins_upcs.py --item-id 123

    # Scrape specific item by UPC
    python scrape_spins_upcs.py --upc 00-00093-56859

    # Scrape multiple items by UPC
    python scrape_spins_upcs.py --upc 00-00093-56859 00-00094-12345

    # Use local database
    python scrape_spins_upcs.py --all --db local

    # Custom delay between requests (default: 1 second)
    python scrape_spins_upcs.py --all --delay 5
"""

import argparse
import sys
import os
import json
import requests
import configparser
from datetime import datetime

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_utils import get_db_uri
from models import db, SpinsItem


def setup_database(db_type=None):
    """Initialize database connection"""
    db_uri = get_db_uri(db_type)
    # Create a minimal Flask-like app context for SQLAlchemy
    from flask import Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def get_rapidapi_big_product_credentials():
    """Read RapidAPI Big Product Data credentials from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    config.read(config_path)
    api_key = config.get('rapidapi', 'x-rapidapi-key', fallback=None)
    api_host = config.get('rapidapi', 'x-rapidapi-big-product-host', fallback=None)
    if api_key:
        api_key = api_key.strip()
    if api_host:
        api_host = api_host.strip()
    return api_key, api_host


def extract_and_compute_upc(upc_string):
    """
    Extract last 11 digits from UPC string and compute check digit.
    
    Args:
        upc_string: UPC string in format like "00-00093-56859"
    
    Returns:
        Complete 12-digit UPC with check digit (e.g., "00009356859X")
    """
    # Remove all non-digit characters
    digits_only = ''.join(filter(str.isdigit, upc_string))
    
    # Get last 11 digits
    if len(digits_only) < 11:
        raise ValueError(f"UPC string must contain at least 11 digits, got: {upc_string}")
    
    last_11_digits = digits_only[-11:]
    
    # Calculate check digit (UPC-A algorithm)
    # Sum of digits in odd positions (1st, 3rd, 5th, 7th, 9th, 11th) * 3
    odd_sum = sum(int(last_11_digits[i]) for i in range(0, 11, 2)) * 3
    
    # Sum of digits in even positions (2nd, 4th, 6th, 8th, 10th)
    even_sum = sum(int(last_11_digits[i]) for i in range(1, 11, 2))
    
    # Total sum
    total = odd_sum + even_sum
    
    # Check digit is the remainder when divided by 10, then 10 - remainder (or 0 if remainder is 0)
    remainder = total % 10
    check_digit = 0 if remainder == 0 else 10 - remainder
    
    # Return complete 12-digit UPC
    computed_upc = last_11_digits + str(check_digit)
    
    return computed_upc


def check_image_url(image_url, timeout=5):
    """
    Check if an image URL is accessible.
    
    Args:
        image_url: URL to check
        timeout: Request timeout in seconds
    
    Returns:
        True if image is accessible, False otherwise
    """
    if not image_url:
        return False
    
    try:
        # First try HEAD request (faster, doesn't download image)
        try:
            response = requests.head(image_url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type:
                    return True
        except requests.exceptions.RequestException:
            pass
        
        # If HEAD fails, try GET with stream=True (only download headers)
        try:
            response = requests.get(image_url, timeout=timeout, allow_redirects=True, stream=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type:
                    response.close()  # Close the connection
                    return True
            if response:
                response.close()
        except requests.exceptions.RequestException:
            pass
        
        return False
    except Exception:
        return False


def scrape_spins_item(item, api_key, api_host):
    """
    Scrape SPINS item data from RapidAPI Big Product Data.
    
    Args:
        item: SpinsItem object
        api_key: RapidAPI key
        api_host: RapidAPI host
    
    Returns:
        (success: bool, error: str or None)
    """
    if not item.upc:
        return False, "Item does not have a UPC"
    
    # Extract and compute UPC
    try:
        computed_upc = extract_and_compute_upc(item.upc)
        print(f"   Original UPC: {item.upc}")
        print(f"   Computed UPC: {computed_upc}")
    except ValueError as e:
        return False, f"Invalid UPC format: {str(e)}"
    
    # Make API request
    url = f'https://{api_host}/gtin/{computed_upc}'
    headers = {
        'x-rapidapi-host': api_host,
        'x-rapidapi-key': api_key
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_data.get('error', error_msg))
            except:
                error_text = response.text[:200] if response.text else 'No response body'
                error_msg = f"{error_msg}: {error_text}"
            return False, error_msg
        
        data = response.json()
        
        # Extract data from response
        scrapped_name = None
        img_url = None
        scrapped_url = None
        
        # Get first title from properties.title
        if 'properties' in data and 'title' in data['properties']:
            titles = data['properties']['title']
            if isinstance(titles, list) and len(titles) > 0:
                scrapped_name = titles[0]
            elif isinstance(titles, str):
                scrapped_name = titles
        
        # Get first store data - loop through stores to find first with valid image
        if 'stores' in data and isinstance(data['stores'], list) and len(data['stores']) > 0:
            # Priority stores: Amazon, Target, Walmart
            priority_stores = ['amazon', 'target', 'walmart']
            
            # Find first store with a valid, accessible image for img_url
            # Priority: Amazon, Target, Walmart (skip eBay)
            print(f"   🔍 Validating image URLs (prioritizing Amazon, Target, Walmart)...")
            
            # First pass: Try priority stores
            for idx, store in enumerate(data['stores'], 1):
                store_name = store.get('store', '').lower() if isinstance(store.get('store'), str) else ''
                
                # Skip eBay stores
                if 'ebay' in store_name:
                    continue
                
                # Check if it's a priority store
                is_priority = any(priority in store_name for priority in priority_stores)
                if not is_priority:
                    continue
                
                if 'image' in store and store['image']:
                    image_url = store['image']
                    print(f"      Checking priority store {store.get('store', 'Unknown')}: {image_url[:60]}...")
                    if check_image_url(image_url):
                        img_url = image_url
                        print(f"      ✓ Image is accessible from priority store")
                        break
                    else:
                        print(f"      ✗ Image is not accessible, trying next...")
            
            # Second pass: Try other stores (if no priority store image found)
            if not img_url:
                print(f"      No valid image from priority stores, trying other stores...")
                for idx, store in enumerate(data['stores'], 1):
                    store_name = store.get('store', '').lower() if isinstance(store.get('store'), str) else ''
                    
                    # Skip eBay stores
                    if 'ebay' in store_name:
                        print(f"      Skipping eBay store: {store.get('store', 'Unknown')}")
                        continue
                    
                    # Skip priority stores (already tried)
                    is_priority = any(priority in store_name for priority in priority_stores)
                    if is_priority:
                        continue
                    
                    if 'image' in store and store['image']:
                        image_url = store['image']
                        print(f"      Checking {store.get('store', 'Unknown')}: {image_url[:60]}...")
                        if check_image_url(image_url):
                            img_url = image_url
                            print(f"      ✓ Image is accessible")
                            break
                        else:
                            print(f"      ✗ Image is not accessible, trying next...")
            
            # Use first store for scrapped_url (or first store with URL)
            for store in data['stores']:
                if 'url' in store and store['url']:
                    scrapped_url = store['url']
                    break
            
            if not img_url:
                print(f"      ⚠️  No accessible images found in any store (excluding eBay)")
        
        # Update item with scraped data
        item.scrapped_name = scrapped_name
        item.img_url = img_url
        item.scrapped_url = scrapped_url
        item.scrapped_json = json.dumps(data)
        item.scrapped_at = datetime.utcnow()
        
        db.session.commit()
        
        return True, None
        
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        db.session.rollback()
        return False, f"Error processing response: {str(e)}"


def scrape_all_unscraped(db_type=None, delay=1):
    """Scrape all unscraped SPINS items"""
    app = setup_database(db_type)
    
    with app.app_context():
        # Get API credentials
        api_key, api_host = get_rapidapi_big_product_credentials()
        if not api_key or not api_host:
            print("❌ ERROR: RapidAPI credentials not found in config.ini")
            return False
        
        # Get unscraped items (items without scrapped_json)
        print(f"\n🔍 Fetching unscraped SPINS items...")
        items = SpinsItem.query.filter(SpinsItem.scrapped_json.is_(None)).order_by(SpinsItem.upc).all()
        
        if not items:
            print("   ✓ No unscraped items found")
            return True
        
        print(f"   ✓ Found {len(items)} unscraped items")
        print(f"\n{'='*60}")
        print(f"🚀 Starting batch scrape of {len(items)} SPINS items")
        print(f"{'='*60}")
        
        success_count = 0
        fail_count = 0
        skipped_count = 0
        errors = []
        
        for idx, item in enumerate(items, 1):
            print(f"\n[{idx}/{len(items)}] Processing Item: {item.name} (ID: {item.id}, UPC: {item.upc})")
            
            # Double-check that item hasn't been scraped already (safety check)
            # Refresh the item from database to get latest state
            db.session.refresh(item)
            if item.scrapped_json is not None:
                skipped_count += 1
                print(f"   ⚠️  Item already scraped (has scrapped_json), skipping...")
                continue
            
            success, error = scrape_spins_item(item, api_key, api_host)
            
            if success:
                success_count += 1
                print(f"   ✅ Success ({success_count} successful, {fail_count} failed)")
            else:
                fail_count += 1
                errors.append(f"Item {item.name} (ID: {item.id}, UPC: {item.upc}): {error}")
                print(f"   ❌ Failed: {error}")
                print(f"   ({success_count} successful, {fail_count} failed)")
            
            # Rate limiting: wait between requests
            if idx < len(items):
                print(f"   ⏳ Waiting {delay} seconds before next request...")
                import time
                time.sleep(delay)
        
        print(f"\n{'='*60}")
        print(f"📊 BATCH SCRAPE COMPLETE")
        print(f"{'='*60}")
        print(f"   Total items in query: {len(items)}")
        print(f"   ✅ Successful: {success_count}")
        print(f"   ❌ Failed: {fail_count}")
        if skipped_count > 0:
            print(f"   ⏭️  Skipped (already scraped): {skipped_count}")
        if errors:
            print(f"\n   Errors (showing first 10):")
            for error in errors[:10]:
                print(f"     - {error}")
        print(f"{'='*60}\n")
        
        return fail_count == 0


def scrape_by_id(item_id, db_type=None):
    """Scrape a specific SPINS item by ID"""
    app = setup_database(db_type)
    
    with app.app_context():
        item = SpinsItem.query.get(item_id)
        if not item:
            print(f"❌ ERROR: SPINS item with ID {item_id} not found")
            return False
        
        # Get API credentials
        api_key, api_host = get_rapidapi_big_product_credentials()
        if not api_key or not api_host:
            print("❌ ERROR: RapidAPI credentials not found in config.ini")
            return False
        
        print(f"\n🔄 Scraping Item: {item.name} (ID: {item_id}, UPC: {item.upc})")
        success, error = scrape_spins_item(item, api_key, api_host)
        
        if success:
            print(f"\n✅ Item {item.name} (ID: {item_id}, UPC: {item.upc}) scraped successfully!")
            return True
        else:
            print(f"\n❌ Failed to scrape item {item.name} (ID: {item_id}, UPC: {item.upc}): {error}")
            return False


def scrape_by_upc(upc_string, db_type=None):
    """Scrape a specific SPINS item by UPC"""
    app = setup_database(db_type)
    
    with app.app_context():
        item = SpinsItem.query.filter_by(upc=upc_string).first()
        if not item:
            print(f"❌ ERROR: SPINS item with UPC '{upc_string}' not found in database")
            print(f"   Tip: You may need to add the item to the database first")
            return False
        
        # Get API credentials
        api_key, api_host = get_rapidapi_big_product_credentials()
        if not api_key or not api_host:
            print("❌ ERROR: RapidAPI credentials not found in config.ini")
            return False
        
        print(f"\n🔄 Scraping Item: {item.name} (ID: {item.id}, UPC: {item.upc})")
        success, error = scrape_spins_item(item, api_key, api_host)
        
        if success:
            print(f"\n✅ Item {item.name} (ID: {item.id}, UPC: {item.upc}) scraped successfully!")
            return True
        else:
            print(f"\n❌ Failed to scrape item {item.name} (ID: {item.id}, UPC: {item.upc}): {error}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Scrape SPINS UPCs and update the database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all unscraped SPINS items
  python scrape_spins_upcs.py --all

  # Scrape specific item by ID
  python scrape_spins_upcs.py --item-id 123

  # Scrape specific item by UPC
  python scrape_spins_upcs.py --upc 00-00093-56859

  # Scrape multiple items by UPC
  python scrape_spins_upcs.py --upc 00-00093-56859 00-00094-12345

  # Use local database
  python scrape_spins_upcs.py --all --db local

  # Custom delay between requests (default: 1 second)
  python scrape_spins_upcs.py --all --delay 5
        """
    )
    
    # Action arguments (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('--all', action='store_true',
                             help='Scrape all unscraped SPINS items')
    action_group.add_argument('--item-id', type=int, metavar='ID',
                             help='Scrape item by database ID')
    action_group.add_argument('--upc', nargs='+', metavar='UPC',
                             help='Scrape item(s) by UPC string (e.g., 00-00093-56859)')
    
    # Database selection
    parser.add_argument('--db', choices=['local', 'remote'], default='remote',
                       help='Database to use: local or remote (default: remote)')
    
    # Delay between requests (for batch scraping)
    parser.add_argument('--delay', type=int, default=1,
                       help='Delay in seconds between requests when scraping all (default: 1)')
    
    args = parser.parse_args()
    
    # Determine database type
    db_type = 'local' if args.db == 'local' else None
    
    try:
        if args.all:
            success = scrape_all_unscraped(db_type=db_type, delay=args.delay)
        elif args.item_id:
            success = scrape_by_id(args.item_id, db_type=db_type)
        elif args.upc:
            # Scrape multiple items if provided
            all_success = True
            for upc_string in args.upc:
                if not scrape_by_upc(upc_string, db_type=db_type):
                    all_success = False
            success = all_success
        else:
            parser.print_help()
            return 1
        
        return 0 if success else 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

