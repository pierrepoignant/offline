#!/usr/bin/env python3
"""
Standalone script to scrape ASINs and update the database.
Can be run outside of the Flask app.

Usage:
    # Scrape all unscraped ASINs using RapidAPI (default)
    python scrape_asins.py --all

    # Scrape all unscraped ASINs using Pangolin API
    python scrape_asins.py --all --api pangolin

    # Scrape specific ASIN by ID (uses RapidAPI by default)
    python scrape_asins.py --asin-id 123

    # Scrape specific ASIN by ASIN string (uses RapidAPI by default)
    python scrape_asins.py --asin B078K36RQ1

    # Use local database
    python scrape_asins.py --all --db local

    # Scrape multiple specific ASINs
    python scrape_asins.py --asin B078K36RQ1 B07XYZ1234
"""

import argparse
import sys
import os
from datetime import date

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_utils import get_db_uri
from models import db, Asin
from scraping.blueprint import (
    scrape_asin,
    scrape_asin_rapidapi,
    get_pangolin_api_key,
    get_rapidapi_credentials
)


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


def scrape_all_unscraped(api_type='rapidapi', db_type=None, delay=1):
    """Scrape all unscraped ASINs"""
    app = setup_database(db_type)
    
    with app.app_context():
        # Get API credentials
        if api_type == 'pangolin':
            api_key = get_pangolin_api_key()
            if not api_key:
                print("❌ ERROR: Pangolin API key not found in config.ini")
                return False
        else:  # rapidapi
            api_key, api_host = get_rapidapi_credentials()
            if not api_key or not api_host:
                print("❌ ERROR: RapidAPI credentials not found in config.ini")
                return False
        
        # Get unscraped ASINs based on the API type
        print(f"\n🔍 Fetching unscraped ASINs...")
        if api_type == 'pangolin':
            # For Pangolin, check if scraped_at is None
            asins = Asin.query.filter(Asin.scraped_at.is_(None)).order_by(Asin.asin).all()
        else:  # rapidapi
            # For RapidAPI, check if scraped_json_rapid is None
            asins = Asin.query.filter(Asin.scraped_json_rapid.is_(None)).order_by(Asin.asin).all()
        
        if not asins:
            print("   ✓ No unscraped ASINs found")
            return True
        
        print(f"   ✓ Found {len(asins)} unscraped ASINs")
        print(f"\n{'='*60}")
        print(f"🚀 Starting batch scrape of {len(asins)} ASINs using {api_type.upper()}")
        print(f"{'='*60}")
        
        success_count = 0
        fail_count = 0
        errors = []
        
        for idx, asin_obj in enumerate(asins, 1):
            print(f"\n[{idx}/{len(asins)}] Processing ASIN: {asin_obj.asin} (ID: {asin_obj.id})")
            
            # Double-check that ASIN hasn't been scraped already (safety check)
            if api_type == 'pangolin':
                if asin_obj.scraped_at is not None:
                    print(f"   ⚠️  ASIN already scraped (scraped_at: {asin_obj.scraped_at}), skipping...")
                    continue
            else:  # rapidapi
                if asin_obj.scraped_json_rapid is not None:
                    print(f"   ⚠️  ASIN already scraped (has scraped_json_rapid), skipping...")
                    continue
            
            if api_type == 'pangolin':
                success, error = scrape_asin(asin_obj, api_key)
            else:  # rapidapi
                success, error = scrape_asin_rapidapi(asin_obj, api_key, api_host)
            
            if success:
                success_count += 1
                print(f"   ✅ Success ({success_count} successful, {fail_count} failed)")
            else:
                fail_count += 1
                errors.append(f"ASIN {asin_obj.asin} (ID: {asin_obj.id}): {error}")
                print(f"   ❌ Failed ({success_count} successful, {fail_count} failed)")
            
            # Rate limiting: wait between requests
            if idx < len(asins):
                print(f"   ⏳ Waiting {delay} seconds before next request...")
                import time
                time.sleep(delay)
        
        print(f"\n{'='*60}")
        print(f"📊 BATCH SCRAPE COMPLETE")
        print(f"{'='*60}")
        print(f"   Total processed: {len(asins)}")
        print(f"   ✅ Successful: {success_count}")
        print(f"   ❌ Failed: {fail_count}")
        if errors:
            print(f"\n   Errors (showing first 10):")
            for error in errors[:10]:
                print(f"     - {error}")
        print(f"{'='*60}\n")
        
        return fail_count == 0


def scrape_by_id(asin_id, api_type='rapidapi', db_type=None):
    """Scrape a specific ASIN by ID"""
    app = setup_database(db_type)
    
    with app.app_context():
        asin_obj = Asin.query.get(asin_id)
        if not asin_obj:
            print(f"❌ ERROR: ASIN with ID {asin_id} not found")
            return False
        
        # Get API credentials
        if api_type == 'pangolin':
            api_key = get_pangolin_api_key()
            if not api_key:
                print("❌ ERROR: Pangolin API key not found in config.ini")
                return False
            success, error = scrape_asin(asin_obj, api_key)
        else:  # rapidapi
            api_key, api_host = get_rapidapi_credentials()
            if not api_key or not api_host:
                print("❌ ERROR: RapidAPI credentials not found in config.ini")
                return False
            success, error = scrape_asin_rapidapi(asin_obj, api_key, api_host)
        
        if success:
            print(f"\n✅ ASIN {asin_obj.asin} (ID: {asin_id}) scraped successfully!")
            return True
        else:
            print(f"\n❌ Failed to scrape ASIN {asin_obj.asin} (ID: {asin_id}): {error}")
            return False


def scrape_by_asin(asin_string, api_type='rapidapi', db_type=None):
    """Scrape a specific ASIN by ASIN string"""
    app = setup_database(db_type)
    
    with app.app_context():
        asin_obj = Asin.query.filter_by(asin=asin_string).first()
        if not asin_obj:
            print(f"❌ ERROR: ASIN '{asin_string}' not found in database")
            print(f"   Tip: You may need to add the ASIN to the database first")
            return False
        
        # Get API credentials
        if api_type == 'pangolin':
            api_key = get_pangolin_api_key()
            if not api_key:
                print("❌ ERROR: Pangolin API key not found in config.ini")
                return False
            success, error = scrape_asin(asin_obj, api_key)
        else:  # rapidapi
            api_key, api_host = get_rapidapi_credentials()
            if not api_key or not api_host:
                print("❌ ERROR: RapidAPI credentials not found in config.ini")
                return False
            success, error = scrape_asin_rapidapi(asin_obj, api_key, api_host)
        
        if success:
            print(f"\n✅ ASIN {asin_obj.asin} (ID: {asin_obj.id}) scraped successfully!")
            return True
        else:
            print(f"\n❌ Failed to scrape ASIN {asin_obj.asin} (ID: {asin_obj.id}): {error}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Scrape ASINs and update the database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all unscraped ASINs using RapidAPI (default)
  python scrape_asins.py --all

  # Scrape all unscraped ASINs using Pangolin API
  python scrape_asins.py --all --api pangolin

  # Scrape specific ASIN by ID (uses RapidAPI by default)
  python scrape_asins.py --asin-id 123

  # Scrape specific ASIN by ASIN string (uses RapidAPI by default)
  python scrape_asins.py --asin B078K36RQ1

  # Scrape multiple ASINs by string
  python scrape_asins.py --asin B078K36RQ1 B07XYZ1234

  # Use local database
  python scrape_asins.py --all --db local

  # Custom delay between requests (default: 1 second)
  python scrape_asins.py --all --delay 5
        """
    )
    
    # Action arguments (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('--all', action='store_true',
                             help='Scrape all unscraped ASINs')
    action_group.add_argument('--asin-id', type=int, metavar='ID',
                             help='Scrape ASIN by database ID')
    action_group.add_argument('--asin', nargs='+', metavar='ASIN',
                             help='Scrape ASIN(s) by ASIN string (e.g., B078K36RQ1)')
    
    # API selection
    parser.add_argument('--api', choices=['pangolin', 'rapidapi'], default='rapidapi',
                       help='API to use for scraping (default: rapidapi)')
    
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
            success = scrape_all_unscraped(api_type=args.api, db_type=db_type, delay=args.delay)
        elif args.asin_id:
            success = scrape_by_id(args.asin_id, api_type=args.api, db_type=db_type)
        elif args.asin:
            # Scrape multiple ASINs if provided
            all_success = True
            for asin_string in args.asin:
                if not scrape_by_asin(asin_string, api_type=args.api, db_type=db_type):
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

