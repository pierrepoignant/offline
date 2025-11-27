#!/usr/bin/env python3
"""
Scraping blueprint for ASIN scraping functionality
"""

from flask import Blueprint, request, jsonify, flash, current_app
import requests
import configparser
import json
import os
import time
from datetime import date
from models import db, Asin
from auth.blueprint import login_required, admin_required

scraping_bp = Blueprint('scraping', __name__, template_folder='templates')

def get_pangolin_api_key():
    """Read Pangolin API key from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    api_key = config.get('pangolin', 'api_key', fallback=None)
    if api_key:
        api_key = api_key.strip()  # Remove any whitespace
    return api_key

def get_rapidapi_credentials():
    """Read RapidAPI credentials from config.ini"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    api_key = config.get('rapidapi', 'x-rapidapi-key', fallback=None)
    api_host = config.get('rapidapi', 'x-rapidapi-amazon-host', fallback=None)
    if api_key:
        api_key = api_key.strip()
    if api_host:
        api_host = api_host.strip()
    return api_key, api_host

def scrape_asin(asin_obj, api_key, max_retries=5):
    """Scrape ASIN data from Pangolin and save to database with retry logic"""
    
    print(f"\n{'='*60}")
    print(f"🔄 Starting ASIN Scrape")
    print(f"   ASIN: {asin_obj.asin}")
    print(f"   ASIN ID: {asin_obj.id}")
    print(f"{'='*60}")
    
    # Pangolin API endpoint
    pangolin_url = 'https://scrapeapi.pangolinfo.com/api/v1/scrape'
    
    # Amazon URL
    amazon_url = f'https://www.amazon.com/dp/{asin_obj.asin}'
    
    # Verify API key format
    if not api_key or len(api_key.strip()) == 0:
        print(f"   ✗ ERROR: API key is empty")
        return False, "API key is empty"
    
    # According to Pangolin docs: Authorization header should be "Bearer {token}"
    api_key_clean = api_key.strip()
    headers = {
        'Authorization': f'Bearer {api_key_clean}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'url': amazon_url,
        'parserName': 'amzProductDetail',
        'format': 'json',
        'bizContext': {
            'zipcode': '10041'
        }
    }
    
    print(f"\n🌐 Preparing API call to Pangolin...")
    print(f"   Endpoint: {pangolin_url}")
    print(f"   Target URL: {amazon_url}")
    print(f"   Parser: amzProductDetail")
    print(f"   Format: json")
    print(f"   Zipcode: 10041")
    print(f"   Auth token: {api_key_clean[:30]}... (first 30 chars)")
    print(f"   Headers: Authorization=Bearer {api_key_clean[:20]}..., Content-Type=application/json")
    
    # Retry logic for rate limiting and system busy errors
    last_error = None
    data = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n   ⏳ Retry attempt {attempt + 1}/{max_retries}")
        else:
            print(f"\n   📡 Making API call (attempt {attempt + 1}/{max_retries})...")
        try:
            response = requests.post(pangolin_url, json=payload, headers=headers, timeout=90)
            print(f"   ✓ API call completed. Status: {response.status_code}")
            
            # Check HTTP status
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', error_data.get('error', error_msg))
                    if error_data.get('code'):
                        error_msg = f"Code {error_data.get('code')}: {error_msg}"
                    print(f"   Response JSON: {error_data}")
                except:
                    error_text = response.text[:500] if response.text else 'No response body'
                    error_msg = f"{error_msg} - {error_text}"
                    print(f"   Response text: {error_text}")
                
                last_error = f"API Error: {error_msg}"
                
                # Retry on 429 (rate limit), 500 (server error), 502 (bad gateway), 503 (service unavailable), 504 (gateway timeout)
                retryable_statuses = [429, 500, 502, 503, 504]
                if response.status_code in retryable_statuses and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3  # Exponential backoff: 3s, 6s, 12s, 24s, 48s
                    print(f"   ⚠ HTTP {response.status_code} error (retryable), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                
                print(f"   ✗ HTTP {response.status_code} error (not retryable or max retries reached)")
                return False, last_error
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return False, f"API Error: Invalid JSON response - {str(e)}"
            
            # Check API response code (0 means success according to docs)
            api_code = data.get('code')
            if api_code != 0:
                error_msg = data.get('message', 'Unknown error')
                last_error = f"API Error (code {api_code}): {error_msg}"
                print(f"   ✗ API returned error code {api_code}: {error_msg}")
                
                # Retry on system busy (1002) or rate limit errors
                if api_code in [1002, 429] and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3  # Exponential backoff: 3s, 6s, 12s, 24s, 48s
                    print(f"   ⏳ System busy (code {api_code}), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                
                print(f"   ✗ Failed after {attempt + 1} attempt(s)")
                return False, last_error
            
            # Success - break out of retry loop
            print(f"   ✓ API call successful (code: {api_code})")
            break
            
        except requests.exceptions.RequestException as e:
            last_error = f"API Error: {str(e)}"
            print(f"   ✗ Network/Request error: {str(e)}")
            # Retry on network errors
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 3
                print(f"   ⏳ Network error, waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            print(f"   ✗ Failed after {attempt + 1} attempt(s) due to network error")
            return False, last_error
    
    # If we exhausted all retries without success
    if data is None or (data and data.get('code') != 0):
        error_msg = last_error or "API Error: Failed after all retries"
        if last_error and "1002" in last_error:
            error_msg += f" (attempted {max_retries} retries with exponential backoff)"
        return False, error_msg
    
    # Extract image URL and title from the response
    print(f"\n📦 Parsing response data...")
    # According to docs: data.json is string[] - array of JSON strings
    img_url = None
    title = None
    
    data_obj = data.get('data', {})
    if data_obj and data_obj.get('json'):
        json_array = data_obj.get('json', [])
        if json_array and len(json_array) > 0:
            # Parse the first JSON string in the array
            try:
                # json_array[0] is a JSON string, parse it
                json_str = json_array[0]
                if isinstance(json_str, str):
                    parsed_json = json.loads(json_str)
                else:
                    # If it's already a dict, use it directly
                    parsed_json = json_str
                
                # Navigate to the product data
                # Based on docs example, the structure can vary
                product_data = None
                
                # Try: parsed_json is a dict with 'data' -> 'results' -> [0]
                if isinstance(parsed_json, dict):
                    inner_data = parsed_json.get('data', {})
                    if isinstance(inner_data, dict):
                        results = inner_data.get('results', [])
                        if results and len(results) > 0:
                            product_data = results[0]
                    # Try: parsed_json is directly the product data
                    elif parsed_json.get('asin'):
                        product_data = parsed_json
                
                # Try: parsed_json is a list
                elif isinstance(parsed_json, list) and len(parsed_json) > 0:
                    product_data = parsed_json[0]
                
                if product_data and isinstance(product_data, dict):
                    img_url = product_data.get('image')
                    title = product_data.get('title')
                    if img_url:
                        print(f"   ✓ Extracted image URL: {img_url[:50]}...")
                    if title:
                        print(f"   ✓ Extracted title: {title[:50]}...")
                    else:
                        print(f"   ⚠ No title found in response")
                else:
                    print(f"   ⚠ Could not extract product data from response")
                    
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                # Log the error but continue - we'll save the raw data anyway
                print(f"   ⚠ Warning: Error parsing product data: {str(e)}")
                print(f"   JSON string preview: {json_array[0][:200] if json_array else 'None'}")
    
    # Update the database with scraped data
    print(f"\n💾 Saving to database...")
    try:
        asin_obj.scraped_json = json.dumps(data)
        asin_obj.img_url = img_url
        if title:
            # Truncate title to 512 characters if needed
            asin_obj.title = title[:512] if len(title) > 512 else title
        asin_obj.scraped_at = date.today()
        
        db.session.commit()
        print(f"   ✓ Data committed to database")
        print(f"   ✓ Data saved successfully")
        print(f"{'='*60}")
        print(f"✅ ASIN {asin_obj.asin} scraped successfully!")
        print(f"{'='*60}\n")
        return True, None
    except Exception as e:
        db.session.rollback()
        print(f"   ✗ Database error: {str(e)}")
        print(f"{'='*60}")
        print(f"❌ Failed to save ASIN {asin_obj.asin}")
        print(f"{'='*60}\n")
        return False, f"Database Error: {str(e)}"

def scrape_asin_rapidapi(asin_obj, api_key, api_host, max_retries=5):
    """Scrape ASIN data from RapidAPI and save to database with retry logic"""
    
    print(f"\n{'='*60}")
    print(f"🔄 Starting RapidAPI ASIN Scrape")
    print(f"   ASIN: {asin_obj.asin}")
    print(f"   ASIN ID: {asin_obj.id}")
    print(f"{'='*60}")
    
    # RapidAPI endpoint
    rapidapi_url = f'https://real-time-amazon-data.p.rapidapi.com/product-details?asin={asin_obj.asin}&country=US'
    
    # Verify API credentials
    if not api_key or len(api_key.strip()) == 0:
        print(f"   ✗ ERROR: RapidAPI key is empty")
        return False, "RapidAPI key is empty"
    
    if not api_host or len(api_host.strip()) == 0:
        print(f"   ✗ ERROR: RapidAPI host is empty")
        return False, "RapidAPI host is empty"
    
    headers = {
        'X-RapidAPI-Key': api_key.strip(),
        'X-RapidAPI-Host': api_host.strip()
    }
    
    print(f"\n🌐 Preparing API call to RapidAPI...")
    print(f"   Endpoint: {rapidapi_url}")
    print(f"   ASIN: {asin_obj.asin}")
    print(f"   Country: US")
    print(f"   Auth headers: X-RapidAPI-Key={api_key[:30]}..., X-RapidAPI-Host={api_host}")
    
    # Retry logic
    last_error = None
    data = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n   ⏳ Retry attempt {attempt + 1}/{max_retries}")
        else:
            print(f"\n   📡 Making API call (attempt {attempt + 1}/{max_retries})...")
        try:
            response = requests.get(rapidapi_url, headers=headers, timeout=90)
            print(f"   ✓ API call completed. Status: {response.status_code}")
            
            # Check HTTP status
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    print(f"   Response JSON: {json.dumps(error_data, indent=2)[:500]}")
                    error_msg = error_data.get('message', error_data.get('error', error_msg))
                except Exception as e:
                    error_text = response.text[:500] if response.text else 'No response body'
                    error_msg = f"{error_msg} - {error_text}"
                    print(f"   Response text (first 500 chars): {error_text}")
                    print(f"   Could not parse JSON: {str(e)}")
                
                last_error = f"API Error: {error_msg}"
                
                # Retry on 429 (rate limit), 500 (server error), 502 (bad gateway), 503 (service unavailable), 504 (gateway timeout)
                retryable_statuses = [429, 500, 502, 503, 504]
                if response.status_code in retryable_statuses and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3  # Exponential backoff: 3s, 6s, 12s, 24s, 48s
                    print(f"   ⚠ HTTP {response.status_code} error (retryable), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                
                print(f"   ✗ HTTP {response.status_code} error (not retryable or max retries reached)")
                return False, last_error
            
            try:
                data = response.json()
                print(f"   ✓ Response parsed successfully")
            except json.JSONDecodeError as e:
                return False, f"API Error: Invalid JSON response - {str(e)}"
            
            # If we got here, the request was successful
            break
            
        except requests.exceptions.Timeout:
            last_error = "API Error: Request timeout"
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 3
                print(f"   ⚠ Timeout, waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            return False, last_error
        except requests.exceptions.RequestException as e:
            last_error = f"API Error: Request failed - {str(e)}"
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 3
                print(f"   ⚠ Request error, waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            return False, last_error
    
    if data is None:
        return False, last_error or "API Error: No data received"
    
    # Extract image URL and title from response if available
    img_url = None
    title = None
    
    try:
        # Parse RapidAPI response structure
        if isinstance(data, dict):
            # Extract product_photo from data.product_photo (RapidAPI structure)
            data_obj = data.get('data', {})
            if isinstance(data_obj, dict):
                img_url = data_obj.get('product_photo')
                title = data_obj.get('product_title')
            
            # Fallback: Try other possible paths if not found
            if not img_url:
                img_url = (data.get('mainImage') or 
                          data.get('image') or 
                          data.get('images', [{}])[0].get('url') if isinstance(data.get('images'), list) and len(data.get('images', [])) > 0 else None)
            
            if not title:
                title = (data.get('title') or 
                        data.get('productTitle') or
                        data.get('name'))
            
            if img_url:
                print(f"   ✓ Extracted image URL: {img_url[:50]}...")
            else:
                print(f"   ⚠ No image URL found in response")
            if title:
                print(f"   ✓ Extracted title: {title[:50]}...")
            else:
                print(f"   ⚠ No title found in response")
        else:
            print(f"   ⚠ Response is not a dictionary")
    except (KeyError, TypeError, AttributeError) as e:
        print(f"   ⚠ Warning: Error parsing product data: {str(e)}")
    
    # Update the database with scraped data
    print(f"\n💾 Saving to database...")
    try:
        asin_obj.scraped_json_rapid = json.dumps(data)
        # Always update img_url with product_photo from RapidAPI response
        if img_url:
            asin_obj.img_url = img_url
            print(f"   ✓ Updated img_url with product_photo")
        # Only update title if it doesn't already exist
        if title and not asin_obj.title:
            # Truncate title to 512 characters if needed
            asin_obj.title = title[:512] if len(title) > 512 else title
            print(f"   ✓ Updated title")
        elif title and asin_obj.title:
            print(f"   ⚠ Title already exists, keeping existing title: {asin_obj.title[:50]}...")
        # Don't update scraped_at for RapidAPI scrapes (keep it separate from Pangolin)
        
        db.session.commit()
        print(f"   ✓ Data committed to database")
        print(f"   ✓ Data saved successfully to scraped_json_rapid")
        print(f"{'='*60}")
        print(f"✅ ASIN {asin_obj.asin} scraped successfully with RapidAPI!")
        print(f"{'='*60}\n")
        return True, None
    except Exception as e:
        db.session.rollback()
        print(f"   ✗ Database error: {str(e)}")
        print(f"{'='*60}")
        print(f"❌ Failed to save ASIN {asin_obj.asin}")
        print(f"{'='*60}\n")
        return False, f"Database Error: {str(e)}"

@scraping_bp.route('/scrape/<int:asin_id>', methods=['POST'])
@login_required
@admin_required
def scrape_single_asin(asin_id):
    """Scrape a single ASIN"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 Received scrape request for ASIN ID: {asin_id}")
        print(f"{'='*60}")
        
        asin_obj = Asin.query.get_or_404(asin_id)
        
        api_key = get_pangolin_api_key()
        if not api_key:
            print(f"   ✗ ERROR: Pangolin API key not found in config.ini")
            return jsonify({'success': False, 'message': 'Pangolin API key not found in config.ini'}), 500
        
        print(f"   ✓ API key loaded")
        success, error = scrape_asin(asin_obj, api_key)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'ASIN {asin_obj.asin} scraped successfully',
                'img_url': asin_obj.img_url,
                'scraped_at': asin_obj.scraped_at.strftime('%Y-%m-%d') if asin_obj.scraped_at else None
            })
        else:
            return jsonify({'success': False, 'message': error}), 500
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in scrape_single_asin: {str(e)}")
        print(f"Traceback: {error_trace}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}',
            'traceback': error_trace if current_app.config.get('DEBUG') else None
        }), 500

@scraping_bp.route('/scrape-rapidapi/<int:asin_id>', methods=['POST'])
@login_required
@admin_required
def scrape_single_asin_rapidapi(asin_id):
    """Scrape a single ASIN using RapidAPI"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 Received RapidAPI scrape request for ASIN ID: {asin_id}")
        print(f"{'='*60}")
        
        asin_obj = Asin.query.get_or_404(asin_id)
        
        api_key, api_host = get_rapidapi_credentials()
        if not api_key or not api_host:
            print(f"   ✗ ERROR: RapidAPI credentials not found in config.ini")
            return jsonify({'success': False, 'message': 'RapidAPI credentials not found in config.ini'}), 500
        
        print(f"   ✓ RapidAPI credentials loaded")
        success, error = scrape_asin_rapidapi(asin_obj, api_key, api_host)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'ASIN {asin_obj.asin} scraped successfully with RapidAPI',
                'img_url': asin_obj.img_url,
                'scraped_at': asin_obj.scraped_at.strftime('%Y-%m-%d') if asin_obj.scraped_at else None
            })
        else:
            return jsonify({'success': False, 'message': error}), 500
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in scrape_single_asin_rapidapi: {str(e)}")
        print(f"Traceback: {error_trace}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}',
            'traceback': error_trace if current_app.config.get('DEBUG') else None
        }), 500

@scraping_bp.route('/scrape/all', methods=['POST'])
@login_required
@admin_required
def scrape_all_unscraped():
    """Scrape all unscraped ASINs"""
    print(f"\n{'='*60}")
    print(f"📥 Received scrape all request")
    print(f"{'='*60}")
    
    api_key = get_pangolin_api_key()
    if not api_key:
        print(f"   ✗ ERROR: Pangolin API key not found in config.ini")
        return jsonify({'success': False, 'message': 'Pangolin API key not found in config.ini'}), 500
    
    print(f"   ✓ API key loaded")
    
    # Get unscraped ASINs
    print(f"\n🔍 Fetching unscraped ASINs...")
    asins = Asin.query.filter(Asin.scraped_at.is_(None)).order_by(Asin.asin).all()
    
    if not asins:
        print(f"   ✓ No unscraped ASINs found")
        return jsonify({
            'success': True,
            'message': 'No unscraped ASINs found',
            'processed': 0,
            'success_count': 0,
            'fail_count': 0
        })
    
    print(f"   ✓ Found {len(asins)} unscraped ASINs")
    print(f"\n{'='*60}")
    print(f"🚀 Starting batch scrape of {len(asins)} ASINs")
    print(f"{'='*60}")
    
    success_count = 0
    fail_count = 0
    errors = []
    
    for idx, asin_obj in enumerate(asins, 1):
        print(f"\n[{idx}/{len(asins)}] Processing ASIN: {asin_obj.asin}")
        success, error = scrape_asin(asin_obj, api_key)
        if success:
            success_count += 1
            print(f"   ✅ Success ({success_count} successful, {fail_count} failed)")
        else:
            fail_count += 1
            errors.append(f"ASIN {asin_obj.asin}: {error}")
            print(f"   ❌ Failed ({success_count} successful, {fail_count} failed)")
        
        # Rate limiting: wait 5 seconds between requests to avoid overwhelming the API
        if idx < len(asins):
            print(f"   ⏳ Waiting 5 seconds before next request...")
            time.sleep(5)
    
    print(f"\n{'='*60}")
    print(f"📊 BATCH SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"   Total processed: {len(asins)}")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Failed: {fail_count}")
    if errors:
        print(f"   Errors: {len(errors)} (showing first 10)")
    print(f"{'='*60}\n")
    
    return jsonify({
        'success': True,
        'message': f'Scraping complete: {success_count} successful, {fail_count} failed',
        'processed': len(asins),
        'success_count': success_count,
        'fail_count': fail_count,
        'errors': errors[:10]  # Limit to first 10 errors
    })

@scraping_bp.route('/scrape-rapidapi/all', methods=['POST'])
@login_required
@admin_required
def scrape_all_unscraped_rapidapi():
    """Scrape all unscraped ASINs using RapidAPI"""
    print(f"\n{'='*60}")
    print(f"📥 Received RapidAPI scrape all request")
    print(f"{'='*60}")
    
    api_key, api_host = get_rapidapi_credentials()
    if not api_key or not api_host:
        print(f"   ✗ ERROR: RapidAPI credentials not found in config.ini")
        return jsonify({'success': False, 'message': 'RapidAPI credentials not found in config.ini'}), 500
    
    print(f"   ✓ RapidAPI credentials loaded")
    
    # Get unscraped ASINs
    print(f"\n🔍 Fetching unscraped ASINs...")
    asins = Asin.query.filter(Asin.scraped_at.is_(None)).order_by(Asin.asin).all()
    
    if not asins:
        print(f"   ✓ No unscraped ASINs found")
        return jsonify({
            'success': True,
            'message': 'No unscraped ASINs found',
            'processed': 0,
            'success_count': 0,
            'fail_count': 0
        })
    
    print(f"   ✓ Found {len(asins)} unscraped ASINs")
    print(f"\n{'='*60}")
    print(f"🚀 Starting batch scrape of {len(asins)} ASINs with RapidAPI")
    print(f"{'='*60}")
    
    success_count = 0
    fail_count = 0
    errors = []
    
    for idx, asin_obj in enumerate(asins, 1):
        print(f"\n[{idx}/{len(asins)}] Processing ASIN: {asin_obj.asin}")
        success, error = scrape_asin_rapidapi(asin_obj, api_key, api_host)
        if success:
            success_count += 1
            print(f"   ✅ Success ({success_count} successful, {fail_count} failed)")
        else:
            fail_count += 1
            errors.append(f"ASIN {asin_obj.asin}: {error}")
            print(f"   ❌ Failed ({success_count} successful, {fail_count} failed)")
        
        # Rate limiting: wait 5 seconds between requests to avoid overwhelming the API
        if idx < len(asins):
            print(f"   ⏳ Waiting 5 seconds before next request...")
            time.sleep(5)
    
    print(f"\n{'='*60}")
    print(f"📊 BATCH SCRAPE COMPLETE (RapidAPI)")
    print(f"{'='*60}")
    print(f"   Total processed: {len(asins)}")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Failed: {fail_count}")
    if errors:
        print(f"   Errors: {len(errors)} (showing first 10)")
    print(f"{'='*60}\n")
    
    return jsonify({
        'success': True,
        'message': f'RapidAPI scraping complete: {success_count} successful, {fail_count} failed',
        'processed': len(asins),
        'success_count': success_count,
        'fail_count': fail_count,
        'errors': errors[:10]  # Limit to first 10 errors
    })

