#!/usr/bin/env python3
"""
Simple Trading Application
Builds on the working WebSocket to create a basic trading app
"""

import upstox_client
import time
import json
import logging
from datetime import datetime
from typing import Dict, List
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTradingApp:
    """Simple trading application with WebSocket data"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)
        
        # Market data
        self.market_data = {}
        self.positions = {}
        self.orders = []
        
        # WebSocket streamer
        self.streamer = None
        self.running = False
    
    def start_market_data(self, instruments: List[str]):
        """Start market data streaming"""
        logger.info(f"Starting market data for {len(instruments)} instruments")
        
        self.streamer = upstox_client.MarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=instruments,
            mode="full"
        )
        
        # Event handlers
        self.streamer.on("open", self._on_open)
        self.streamer.on("message", self._on_message)
        self.streamer.on("error", self._on_error)
        self.streamer.on("close", self._on_close)
        
        self.streamer.connect()
        self.running = True
    
    def _on_open(self):
        """Handle WebSocket open"""
        logger.info("Market data connected")
    
    def _on_message(self, message):
        """Process market data messages"""
        try:
            if 'feeds' in message:
                for instrument_key, feed_data in message['feeds'].items():
                    if 'fullFeed' in feed_data:
                        full_feed = feed_data['fullFeed']
                        if 'indexFF' in full_feed:
                            index_data = full_feed['indexFF']
                            if 'ltpc' in index_data:
                                ltpc = index_data['ltpc']
                                
                                # Update market data
                                self.market_data[instrument_key] = {
                                    'ltp': ltpc.get('ltp', 0),
                                    'ltt': ltpc.get('ltt', ''),
                                    'change_percent': ltpc.get('cp', 0),
                                    'timestamp': datetime.now()
                                }
                                
                                # Generate trading signals
                                self._generate_signals(instrument_key, ltpc.get('ltp', 0), ltpc.get('cp', 0))
                                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _on_error(self, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.running = False
    
    def _generate_signals(self, instrument_key: str, ltp: float, change_percent: float):
        """Generate simple trading signals"""
        try:
            # Simple momentum strategy
            if change_percent > 1.0:  # Positive momentum
                signal = {
                    'instrument': instrument_key,
                    'signal': 'BUY',
                    'price': ltp,
                    'confidence': min(change_percent / 2.0, 1.0),
                    'timestamp': datetime.now()
                }
                logger.info(f"📈 BUY Signal: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
            elif change_percent < -1.0:  # Negative momentum
                signal = {
                    'instrument': instrument_key,
                    'signal': 'SELL',
                    'price': ltp,
                    'confidence': min(abs(change_percent) / 2.0, 1.0),
                    'timestamp': datetime.now()
                }
                logger.info(f"📉 SELL Signal: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
    
    def get_market_data(self, instrument_key: str = None):
        """Get market data"""
        if instrument_key:
            return self.market_data.get(instrument_key)
        return self.market_data
    
    def get_positions(self):
        """Get current positions"""
        return self.positions
    
    def get_orders(self):
        """Get order history"""
        return self.orders
    
    def stop(self):
        """Stop the application"""
        self.running = False
        if self.streamer:
            self.streamer.disconnect()
        logger.info("Trading app stopped")

def main():
    """Main application"""
    print("🚀 Starting Simple Trading Application")
    
    # Your access token
    access_token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"
    
    # Create trading app
    app = SimpleTradingApp(access_token)
    
    # Instruments to track
    instruments = [
        "NSE_INDEX|Nifty 50",
        "NSE_INDEX|Nifty Bank",
        "NSE_EQ|INE020B01018",  # Reliance
        "NSE_EQ|INE467B01029"   # TCS
    ]
    
    # Start market data
    app.start_market_data(instruments)
    
    try:
        # Run for 2 minutes
        print("⏱️  Running for 2 minutes...")
        time.sleep(120)
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    finally:
        app.stop()
        print("✅ Trading app stopped")

if __name__ == "__main__":
    main()
