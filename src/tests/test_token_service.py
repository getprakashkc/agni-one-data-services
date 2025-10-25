"""
Test Token Service
"""

import requests
import json
import time

def test_token_service():
    """Test token service endpoints"""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Token Service")
    print("=" * 50)
    
    # Test health check
    print("1. Testing Health Check...")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n2. Testing Token Status...")
    try:
        response = requests.get(f"{base_url}/token/status")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n3. Testing Token Validation...")
    try:
        response = requests.get(f"{base_url}/token/validate")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n4. Testing Manual Token Update...")
    try:
        # Test with a dummy token (this will fail validation)
        test_token = "test_token_123"
        payload = {
            "access_token": test_token,
            "expires_at": "2025-10-26T23:59:59Z",
            "account_id": "999999999"
        }
        
        response = requests.post(f"{base_url}/token/update", json=payload)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n✅ Token Service Test Complete!")

if __name__ == "__main__":
    test_token_service()
