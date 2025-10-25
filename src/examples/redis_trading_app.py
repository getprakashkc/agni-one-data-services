#!/usr/bin/env python3
"""
Redis-Enhanced Trading Application
Uses Redis for caching, client management, and data distribution
"""

import upstox_client
import time
import json
import logging
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Set
import threading
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from ist_utils import (
    get_ist_now, get_ist_timestamp, get_ist_timestamp_int, 
    format_ist_for_redis, get_ist_market_status, is_market_open
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RedisTradingApp:
    """Redis-enhanced trading application"""
    
    def __init__(self, access_token: str, redis_host: str = 'localhost', redis_port: int = 6379):
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)
        
        # Redis connection
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        
        # Test Redis connection
        try:
            self.redis_client.ping()
            logger.info("✅ Connected to Redis successfully")
        except redis.ConnectionError:
            logger.error("❌ Failed to connect to Redis")
            raise
        
        # Market data
        self.market_data = {}
        self.positions = {}
        self.orders = []
        
        # WebSocket streamer
        self.streamer = None
        self.running = False
        
        # Client management
        self.clients = {}
        self.client_counter = 0
    
    def start_market_data(self, instruments: List[str]):
        """Start market data streaming with Redis caching"""
        logger.info(f"Starting market data for {len(instruments)} instruments")
        
        # Store instruments in Redis
        self.redis_client.sadd("active_instruments", *instruments)
        logger.info(f"📊 Active instruments: {instruments}")
        
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
        logger.info("🔗 Market data WebSocket connected")
        
        # Store connection status in Redis
        self.redis_client.setex("websocket_status", 60, "connected")
        self.redis_client.set("last_connection_time", format_ist_for_redis())
    
    def _on_message(self, message):
        """Process market data messages with Redis caching"""
        try:
            if 'feeds' in message:
                for instrument_key, feed_data in message['feeds'].items():
                    if 'fullFeed' in feed_data:
                        full_feed = feed_data['fullFeed']
                        if 'indexFF' in full_feed:
                            index_data = full_feed['indexFF']
                            if 'ltpc' in index_data:
                                ltpc = index_data['ltpc']
                                
                                # Create market data object
                                market_data = {
                                    'instrument_key': instrument_key,
                                    'ltp': ltpc.get('ltp', 0),
                                    'ltt': ltpc.get('ltt', ''),
                                    'change_percent': ltpc.get('cp', 0),
                                    'timestamp': format_ist_for_redis(),
                                    'ohlc': index_data.get('marketOHLC', {})
                                }
                                
                                # Cache in Redis with 30-second TTL
                                cache_key = f"market_data:{instrument_key}"
                                self.redis_client.setex(cache_key, 30, json.dumps(market_data))
                                
                                # Update local cache
                                self.market_data[instrument_key] = market_data
                                
                                # Broadcast to subscribers
                                self._broadcast_to_subscribers(instrument_key, market_data)
                                
                                # Generate trading signals
                                self._generate_signals(instrument_key, ltpc.get('ltp', 0), ltpc.get('cp', 0))
                                
                                # Log to Redis for monitoring
                                self._log_market_update(instrument_key, market_data)
                                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _broadcast_to_subscribers(self, instrument_key: str, data: dict):
        """Broadcast data to all subscribers of an instrument"""
        try:
            # Get all subscribers for this instrument
            subscribers = self.redis_client.smembers(f"subscribers:{instrument_key}")
            
            if subscribers:
                # Publish to Redis channel for real-time updates
                self.redis_client.publish(f"market_updates:{instrument_key}", json.dumps(data))
                
                # Log broadcast activity
                logger.info(f"📡 Broadcasted {instrument_key} to {len(subscribers)} subscribers")
                
        except Exception as e:
            logger.error(f"Error broadcasting to subscribers: {e}")
    
    def _log_market_update(self, instrument_key: str, data: dict):
        """Log market update to Redis for monitoring"""
        try:
            # Store in Redis list (keep last 100 updates)
            log_key = f"market_logs:{instrument_key}"
            self.redis_client.lpush(log_key, json.dumps(data))
            self.redis_client.ltrim(log_key, 0, 99)  # Keep only last 100 entries
            
            # Update instrument stats
            stats_key = f"instrument_stats:{instrument_key}"
            stats = {
                'last_update': format_ist_for_redis(),
                'ltp': data['ltp'],
                'change_percent': data['change_percent'],
                'subscriber_count': len(self.redis_client.smembers(f"subscribers:{instrument_key}"))
            }
            self.redis_client.setex(stats_key, 300, json.dumps(stats))  # 5-minute TTL
            
        except Exception as e:
            logger.error(f"Error logging market update: {e}")
    
    def _generate_signals(self, instrument_key: str, ltp: float, change_percent: float):
        """Generate trading signals and store in Redis"""
        try:
            # Simple momentum strategy
            if change_percent > 1.0:  # Positive momentum
                signal = {
                    'instrument': instrument_key,
                    'signal': 'BUY',
                    'price': ltp,
                    'confidence': min(change_percent / 2.0, 1.0),
                    'timestamp': format_ist_for_redis(),
                    'strategy': 'momentum'
                }
                
                # Store signal in Redis
                signal_key = f"signal:{instrument_key}:{get_ist_timestamp_int()}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))  # 5-minute TTL
                
                # Add to signals queue
                self.redis_client.lpush("trading_signals", json.dumps(signal))
                self.redis_client.ltrim("trading_signals", 0, 99)  # Keep last 100 signals
                
                logger.info(f"📈 BUY Signal: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
            elif change_percent < -1.0:  # Negative momentum
                signal = {
                    'instrument': instrument_key,
                    'signal': 'SELL',
                    'price': ltp,
                    'confidence': min(abs(change_percent) / 2.0, 1.0),
                    'timestamp': format_ist_for_redis(),
                    'strategy': 'momentum'
                }
                
                # Store signal in Redis
                signal_key = f"signal:{instrument_key}:{get_ist_timestamp_int()}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))
                
                # Add to signals queue
                self.redis_client.lpush("trading_signals", json.dumps(signal))
                self.redis_client.ltrim("trading_signals", 0, 99)
                
                logger.info(f"📉 SELL Signal: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
    
    def _on_error(self, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
        
        # Update Redis status
        self.redis_client.setex("websocket_status", 60, "error")
        self.redis_client.set("last_error", str(error))
    
    def _on_close(self, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.running = False
        
        # Update Redis status
        self.redis_client.setex("websocket_status", 60, "disconnected")
        self.redis_client.set("last_disconnection_time", format_ist_for_redis())
    
    def add_client(self, client_id: str, instruments: List[str]):
        """Add a new client and subscribe to instruments"""
        try:
            # Store client info
            self.redis_client.hset(f"client:{client_id}", mapping={
                "instruments": json.dumps(instruments),
                "created_at": format_ist_for_redis(),
                "status": "active"
            })
            
            # Subscribe client to instruments
            for instrument in instruments:
                self.redis_client.sadd(f"subscribers:{instrument}", client_id)
                self.redis_client.sadd(f"client_instruments:{client_id}", instrument)
            
            logger.info(f"👤 Added client {client_id} for instruments: {instruments}")
            
        except Exception as e:
            logger.error(f"Error adding client: {e}")
    
    def remove_client(self, client_id: str):
        """Remove a client and unsubscribe from instruments"""
        try:
            # Get client instruments
            instruments = self.redis_client.smembers(f"client_instruments:{client_id}")
            
            # Unsubscribe from instruments
            for instrument in instruments:
                self.redis_client.srem(f"subscribers:{instrument}", client_id)
            
            # Remove client data
            self.redis_client.delete(f"client:{client_id}")
            self.redis_client.delete(f"client_instruments:{client_id}")
            
            logger.info(f"👤 Removed client {client_id}")
            
        except Exception as e:
            logger.error(f"Error removing client: {e}")
    
    def get_market_data(self, instrument_key: str = None):
        """Get market data from Redis cache"""
        try:
            if instrument_key:
                # Get specific instrument data
                cached_data = self.redis_client.get(f"market_data:{instrument_key}")
                if cached_data:
                    return json.loads(cached_data)
                return None
            else:
                # Get all market data
                all_data = {}
                instruments = self.redis_client.smembers("active_instruments")
                for instrument in instruments:
                    cached_data = self.redis_client.get(f"market_data:{instrument}")
                    if cached_data:
                        all_data[instrument] = json.loads(cached_data)
                return all_data
                
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None
    
    def get_trading_signals(self, limit: int = 10):
        """Get recent trading signals from Redis"""
        try:
            signals = self.redis_client.lrange("trading_signals", 0, limit - 1)
            return [json.loads(signal) for signal in signals]
        except Exception as e:
            logger.error(f"Error getting trading signals: {e}")
            return []
    
    def get_redis_stats(self):
        """Get Redis statistics for monitoring"""
        try:
            stats = {
                'active_instruments': len(self.redis_client.smembers("active_instruments")),
                'total_clients': len(self.redis_client.keys("client:*")),
                'total_signals': self.redis_client.llen("trading_signals"),
                'connected_clients': len(self.redis_client.keys("client_instruments:*")),
                'redis_info': self.redis_client.info('memory')
            }
            return stats
        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            return {}
    
    def stop(self):
        """Stop the application"""
        self.running = False
        if self.streamer:
            self.streamer.disconnect()
        
        # Update Redis status
        self.redis_client.setex("websocket_status", 60, "stopped")
        logger.info("Trading app stopped")

def main():
    """Main application"""
    print("🚀 Starting Redis-Enhanced Trading Application")
    
    # Display IST market status
    market_status = get_ist_market_status()
    print(f"🕐 Current IST Time: {market_status['current_time_ist']}")
    print(f"📈 Market Status: {'OPEN' if market_status['is_market_open'] else 'CLOSED'}")
    print(f"🌍 Timezone: {market_status['timezone']}")
    if not market_status['is_market_open']:
        print(f"⏰ Next Market Open: {market_status['market_open_time']}")
    
    # Your access token
    access_token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"
    
    # Create trading app
    app = RedisTradingApp(access_token)
    
    # Instruments to track
    instruments = [
        "NSE_INDEX|Nifty 50",
        "NSE_INDEX|Nifty Bank",
        "NSE_EQ|INE020B01018",  # Reliance
        "NSE_EQ|INE467B01029"   # TCS
    ]
    
    # Add some test clients
    app.add_client("client_1", ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"])
    app.add_client("client_2", ["NSE_INDEX|Nifty 50", "NSE_EQ|INE020B01018"])
    app.add_client("client_3", ["NSE_EQ|INE467B01029"])
    
    # Start market data
    app.start_market_data(instruments)
    
    try:
        # Run for 2 minutes
        print("⏱️  Running for 2 minutes...")
        print("📊 Check Redis Insight to see data in real-time!")
        print("🔗 Redis Insight: http://localhost:8001")
        
        # Print stats every 30 seconds
        for i in range(4):
            time.sleep(30)
            stats = app.get_redis_stats()
            print(f"📈 Redis Stats: {stats}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    finally:
        app.stop()
        print("✅ Redis trading app stopped")

if __name__ == "__main__":
    main()
