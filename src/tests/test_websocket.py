#!/usr/bin/env python3
"""
Test script for Upstox WebSocket functionality
Replace the ACCESS_TOKEN with your actual token
"""

import upstox_client
import time
import json

# Your access token
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"

def test_market_data_streamer():
    """Test Market Data WebSocket streaming"""
    print("=== Testing Market Data Streamer ===")
    
    # Configure the client
    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    
    # Create API client
    api_client = upstox_client.ApiClient(configuration)
    
    # Create market data streamer
    streamer = upstox_client.MarketDataStreamerV3(
        api_client=api_client,
        instrumentKeys=[
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|Nifty Bank"
        ],
        mode="full"
    )
    
    # Event handlers
    def on_open():
        print("✅ WebSocket connection opened")
    
    def on_message(message):
        print(f"📊 Market Data: {json.dumps(message, indent=2)}")
    
    def on_error(error):
        print(f"❌ Error: {error}")
    
    def on_close(close_status_code, close_msg):
        print(f"🔌 Connection closed: {close_status_code} - {close_msg}")
    
    # Register event handlers
    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)
    
    # Connect
    print("🔗 Connecting to market data feed...")
    streamer.connect()
    
    # Keep the connection alive for 30 seconds
    time.sleep(30)
    
    # Disconnect
    print("🔌 Disconnecting...")
    streamer.disconnect()

def test_portfolio_streamer():
    """Test Portfolio Data WebSocket streaming"""
    print("\n=== Testing Portfolio Streamer ===")
    
    # Configure the client
    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    
    # Create API client
    api_client = upstox_client.ApiClient(configuration)
    
    # Create portfolio streamer
    streamer = upstox_client.PortfolioDataStreamer(
        api_client=api_client,
        order_update=True,
        position_update=True,
        holding_update=True,
        gtt_update=True
    )
    
    # Event handlers
    def on_open():
        print("✅ Portfolio WebSocket connection opened")
    
    def on_message(message):
        print(f"💼 Portfolio Update: {json.dumps(message, indent=2)}")
    
    def on_error(error):
        print(f"❌ Error: {error}")
    
    def on_close(close_status_code, close_msg):
        print(f"🔌 Portfolio connection closed: {close_status_code} - {close_msg}")
    
    # Register event handlers
    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)
    
    # Connect
    print("🔗 Connecting to portfolio feed...")
    streamer.connect()
    
    # Keep the connection alive for 30 seconds
    time.sleep(30)
    
    # Disconnect
    print("🔌 Disconnecting...")
    streamer.disconnect()

def test_rest_api():
    """Test REST API endpoints"""
    print("\n=== Testing REST API ===")
    
    # Configure the client
    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    
    # Create API client
    api_client = upstox_client.ApiClient(configuration)
    
    try:
        # Test user profile
        user_api = upstox_client.UserApi(api_client)
        profile = user_api.get_profile()
        print(f"👤 User Profile: {profile}")
        
        # Test market status
        market_api = upstox_client.MarketHolidaysAndTimingsApi(api_client)
        market_status = market_api.get_market_status("NSE")
        print(f"📈 Market Status: {market_status}")
        
        # Test holdings
        portfolio_api = upstox_client.PortfolioApi(api_client)
        holdings = portfolio_api.get_holdings()
        print(f"💼 Holdings: {holdings}")
        
    except Exception as e:
        print(f"❌ REST API Error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Upstox API Tests")
    print(f"🔑 Using Access Token: {ACCESS_TOKEN[:20]}...")
    
    try:
        # Test REST API first
        test_rest_api()
        
        # Test Market Data WebSocket
        test_market_data_streamer()
        
        # Test Portfolio WebSocket
        test_portfolio_streamer()
        
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    print("✅ Tests completed")
