#!/usr/bin/env python3
"""
Test script for auto-open last story feature
Tests the new API endpoints and database columns
"""

import requests
import json
import sys
import sqlite3

# Configuration
BASE_URL = "http://localhost:8000"
DB_PATH = "/Users/nishant/apps/kahani/backend/data/kahani.db"

def test_database_columns():
    """Test that the new database columns exist"""
    print("Testing database columns...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the columns exist
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'auto_open_last_story' in column_names:
            print("✅ auto_open_last_story column exists")
        else:
            print("❌ auto_open_last_story column missing")
            return False
            
        if 'last_accessed_story_id' in column_names:
            print("✅ last_accessed_story_id column exists")
        else:
            print("❌ last_accessed_story_id column missing")
            return False
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_last_story_endpoint():
    """Test the new /api/settings/last-story endpoint"""
    print("\nTesting /api/settings/last-story endpoint...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/settings/last-story")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 401:
            print("✅ Endpoint exists and requires authentication (as expected)")
            return True
        elif response.status_code == 403:
            print("✅ Endpoint exists and requires authentication (as expected)")
            return True
        elif response.status_code == 200:
            print("✅ Endpoint accessible")
            data = response.json()
            print(f"Response: {data}")
            return True
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Endpoint test failed: {e}")
        return False

def test_api_docs():
    """Test that the API documentation includes our new endpoint"""
    print("\nTesting API documentation...")
    
    try:
        response = requests.get(f"{BASE_URL}/openapi.json")
        if response.status_code == 200:
            openapi_spec = response.json()
            paths = openapi_spec.get('paths', {})
            
            if '/api/settings/last-story' in paths:
                print("✅ /api/settings/last-story endpoint documented")
                return True
            else:
                print("❌ /api/settings/last-story endpoint not in documentation")
                print("Available settings endpoints:")
                for path in paths:
                    if '/settings/' in path:
                        print(f"  - {path}")
                return False
        else:
            print(f"❌ Failed to get API docs: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ API docs test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Auto-Open Last Story Feature\n")
    
    tests_passed = 0
    total_tests = 3
    
    # Test 1: Database columns
    if test_database_columns():
        tests_passed += 1
    
    # Test 2: Endpoint exists
    if test_last_story_endpoint():
        tests_passed += 1
    
    # Test 3: API documentation
    if test_api_docs():
        tests_passed += 1
    
    print(f"\n📊 Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Auto-open last story feature is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())