#!/usr/bin/env python3
"""
Simple endpoint checker for all trading services
"""

import requests
import json
from datetime import datetime

def check_endpoint(url: str, name: str) -> dict:
    """Check if an endpoint is accessible"""
    try:
        response = requests.get(url, timeout=5)
        return {
            "name": name,
            "url": url,
            "status": "✅ Running" if response.status_code == 200 else f"❌ HTTP {response.status_code}",
            "response_time": f"{response.elapsed.total_seconds():.3f}s",
            "data": response.json() if response.status_code == 200 else None
        }
    except requests.exceptions.ConnectionError:
        return {
            "name": name,
            "url": url,
            "status": "❌ Not Running",
            "response_time": "N/A",
            "data": None
        }
    except Exception as e:
        return {
            "name": name,
            "url": url,
            "status": f"❌ Error: {str(e)}",
            "response_time": "N/A",
            "data": None
        }

def main():
    """Check all service endpoints"""
    print("🔍 Agnidata Trading Services - Endpoint Checker")
    print("=" * 60)
    print(f"🕐 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Define all endpoints to check
    endpoints = [
        ("http://localhost:8000/health", "Token Service Health"),
        ("http://localhost:8000/token/status", "Token Status"),
        ("http://localhost:8000/token/validate", "Token Validation"),
        ("http://localhost:8001/health", "Data Service Health"),
        ("http://localhost:8001/api/market-data", "Market Data API"),
        ("http://localhost:8002/health", "Trading Service Health"),
        ("http://localhost:8002/api/signals", "Trading Signals API"),
        ("http://localhost:8003/health", "Trading App Health"),
        ("http://localhost:8003/api/market-data", "Trading App Market Data"),
    ]
    
    # Check each endpoint
    for url, name in endpoints:
        result = check_endpoint(url, name)
        print(f"{result['status']} {result['name']}")
        print(f"   URL: {result['url']}")
        print(f"   Response Time: {result['response_time']}")
        if result['data']:
            print(f"   Data: {json.dumps(result['data'], indent=2)}")
        print()
    
    print("📚 Documentation URLs:")
    print("  🔗 Token Service Docs: http://localhost:8000/docs")
    print("  🔗 Data Service Docs: http://localhost:8001/docs")
    print("  🔗 Trading Service Docs: http://localhost:8002/docs")
    print("  🔗 Trading App Docs: http://localhost:8003/docs")
    print()
    
    print("🔌 WebSocket Endpoints:")
    print("  🔗 Data Service WS: ws://localhost:8001/ws")
    print("  🔗 Trading App WS: ws://localhost:8003/ws")
    print()
    
    print("🎯 Quick Test Commands:")
    print("  curl http://localhost:8000/health")
    print("  curl http://localhost:8000/token/status")
    print("  curl http://localhost:8001/api/market-data")
    print("  curl http://localhost:8002/api/signals")

if __name__ == "__main__":
    main()


