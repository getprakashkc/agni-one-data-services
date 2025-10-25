#!/usr/bin/env python3
"""
Simple WebSocket test for Upstox API
"""

import upstox_client
import time
import json

# Your access token
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"

def main():
    print("🚀 Testing Upstox WebSocket with your access token")
    
    # Configure the client
    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    
    # Create API client
    api_client = upstox_client.ApiClient(configuration)
    
    # Create market data streamer for multiple instruments
    streamer = upstox_client.MarketDataStreamerV3(
        api_client=api_client,
        instrumentKeys=[
            "NSE_INDEX|Nifty 50",      # Nifty 50
            "NSE_INDEX|Nifty Bank",    # Bank Nifty
            "NSE_EQ|INE020B01018",     # Reliance
            "NSE_EQ|INE467B01029"      # TCS
        ],
        mode="full"  # Get full market data
    )
    
    # Event handlers
    def on_open():
        print("✅ WebSocket connected successfully!")
        print("📊 Streaming market data for:")
        print("   - Nifty 50")
        print("   - Bank Nifty") 
        print("   - Reliance")
        print("   - TCS")
    
    def on_message(message):
        # Print only essential data to avoid spam
        if 'feed' in message and message['feed']:
            feed_data = message['feed']
            for instrument_key, data in feed_data.items():
                if 'ltp' in data:
                    print(f"📈 {instrument_key}: ₹{data['ltp']}")
    
    def on_error(error):
        print(f"❌ WebSocket Error: {error}")
    
    def on_close(close_status_code, close_msg):
        print(f"🔌 Connection closed: {close_status_code} - {close_msg}")
    
    # Register event handlers
    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)
    
    # Connect to WebSocket
    print("🔗 Connecting to Upstox WebSocket...")
    streamer.connect()
    
    try:
        # Keep the connection alive for 60 seconds
        print("⏱️  Streaming for 60 seconds...")
        time.sleep(60)
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    finally:
        print("🔌 Disconnecting...")
        streamer.disconnect()
        print("✅ Test completed")

if __name__ == "__main__":
    main()
