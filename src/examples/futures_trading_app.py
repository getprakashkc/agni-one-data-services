#!/usr/bin/env python3
"""
Futures Trading Application with Redis
Customized for NSE Futures instruments
"""

import upstox_client
import time
import json
import logging
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Set
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FuturesTradingApp:
    """Futures trading application with Redis caching"""
    
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
        
        # Futures-specific settings
        self.futures_instruments = [
            "NSE_FO|58934", "NSE_FO|58935", "NSE_FO|58936", "NSE_FO|58937", "NSE_FO|58938",
            "NSE_FO|58939", "NSE_FO|58946", "NSE_FO|58949", "NSE_FO|58951", "NSE_FO|58952",
            "NSE_FO|58953", "NSE_FO|58954", "NSE_FO|58956", "NSE_FO|58959", "NSE_FO|58960",
            "NSE_FO|58962", "NSE_FO|58963", "NSE_FO|58965", "NSE_FO|58970", "NSE_FO|58973",
            "NSE_FO|58974", "NSE_FO|58997", "NSE_FO|58998", "NSE_FO|59003", "NSE_FO|59004",
            "NSE_FO|59005", "NSE_FO|59010", "NSE_FO|59011", "NSE_FO|59022", "NSE_FO|59023",
            "NSE_FO|59026", "NSE_FO|59027", "NSE_FO|59033", "NSE_FO|59034"
        ]
    
    def start_futures_data(self):
        """Start futures data streaming with Redis caching"""
        logger.info(f"🚀 Starting futures data for {len(self.futures_instruments)} instruments")
        
        # Store instruments in Redis
        self.redis_client.sadd("futures_instruments", *self.futures_instruments)
        logger.info(f"📊 Futures instruments: {len(self.futures_instruments)}")
        
        # Create market data streamer
        self.streamer = upstox_client.MarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=self.futures_instruments,
            mode="full"  # Full data for futures trading
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
        logger.info("🔗 Futures WebSocket connected")
        
        # Store connection status in Redis
        self.redis_client.setex("futures_websocket_status", 60, "connected")
        self.redis_client.set("futures_last_connection", datetime.now().isoformat())
    
    def _on_message(self, message):
        """Process futures market data messages with Redis caching"""
        try:
            if 'feeds' in message:
                for instrument_key, feed_data in message['feeds'].items():
                    if 'fullFeed' in feed_data:
                        full_feed = feed_data['fullFeed']
                        if 'indexFF' in full_feed:
                            index_data = full_feed['indexFF']
                            if 'ltpc' in index_data:
                                ltpc = index_data['ltpc']
                                
                                # Create futures market data object
                                futures_data = {
                                    'instrument_key': instrument_key,
                                    'ltp': ltpc.get('ltp', 0),
                                    'ltt': ltpc.get('ltt', ''),
                                    'change_percent': ltpc.get('cp', 0),
                                    'timestamp': datetime.now().isoformat(),
                                    'ohlc': index_data.get('marketOHLC', {}),
                                    'instrument_type': 'FUTURES',
                                    'exchange': 'NSE_FO'
                                }
                                
                                # Cache in Redis with 30-second TTL
                                cache_key = f"futures_data:{instrument_key}"
                                self.redis_client.setex(cache_key, 30, json.dumps(futures_data))
                                
                                # Update local cache
                                self.market_data[instrument_key] = futures_data
                                
                                # Broadcast to futures subscribers
                                self._broadcast_to_futures_subscribers(instrument_key, futures_data)
                                
                                # Generate futures trading signals
                                self._generate_futures_signals(instrument_key, ltpc.get('ltp', 0), ltpc.get('cp', 0))
                                
                                # Log futures update
                                self._log_futures_update(instrument_key, futures_data)
                                
        except Exception as e:
            logger.error(f"Error processing futures message: {e}")
    
    def _broadcast_to_futures_subscribers(self, instrument_key: str, data: dict):
        """Broadcast futures data to all subscribers"""
        try:
            # Get all subscribers for this futures instrument
            subscribers = self.redis_client.smembers(f"futures_subscribers:{instrument_key}")
            
            if subscribers:
                # Publish to Redis channel for real-time updates
                self.redis_client.publish(f"futures_updates:{instrument_key}", json.dumps(data))
                
                # Log broadcast activity
                logger.info(f"📡 Futures broadcast: {instrument_key} to {len(subscribers)} subscribers")
                
        except Exception as e:
            logger.error(f"Error broadcasting futures data: {e}")
    
    def _log_futures_update(self, instrument_key: str, data: dict):
        """Log futures update to Redis for monitoring"""
        try:
            # Store in Redis list (keep last 100 updates)
            log_key = f"futures_logs:{instrument_key}"
            self.redis_client.lpush(log_key, json.dumps(data))
            self.redis_client.ltrim(log_key, 0, 99)  # Keep only last 100 entries
            
            # Update futures instrument stats
            stats_key = f"futures_stats:{instrument_key}"
            stats = {
                'last_update': datetime.now().isoformat(),
                'ltp': data['ltp'],
                'change_percent': data['change_percent'],
                'subscriber_count': len(self.redis_client.smembers(f"futures_subscribers:{instrument_key}")),
                'instrument_type': 'FUTURES'
            }
            self.redis_client.setex(stats_key, 300, json.dumps(stats))  # 5-minute TTL
            
        except Exception as e:
            logger.error(f"Error logging futures update: {e}")
    
    def _generate_futures_signals(self, instrument_key: str, ltp: float, change_percent: float):
        """Generate futures trading signals"""
        try:
            # Futures-specific trading strategy (more sensitive to changes)
            if change_percent > 0.5:  # Lower threshold for futures
                signal = {
                    'instrument': instrument_key,
                    'signal': 'BUY',
                    'price': ltp,
                    'confidence': min(change_percent / 1.0, 1.0),
                    'timestamp': datetime.now().isoformat(),
                    'strategy': 'futures_momentum',
                    'instrument_type': 'FUTURES'
                }
                
                # Store futures signal in Redis
                signal_key = f"futures_signal:{instrument_key}:{int(time.time())}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))
                
                # Add to futures signals queue
                self.redis_client.lpush("futures_signals", json.dumps(signal))
                self.redis_client.ltrim("futures_signals", 0, 199)  # Keep last 200 signals
                
                logger.info(f"📈 FUTURES BUY: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
            elif change_percent < -0.5:  # Lower threshold for futures
                signal = {
                    'instrument': instrument_key,
                    'signal': 'SELL',
                    'price': ltp,
                    'confidence': min(abs(change_percent) / 1.0, 1.0),
                    'timestamp': datetime.now().isoformat(),
                    'strategy': 'futures_momentum',
                    'instrument_type': 'FUTURES'
                }
                
                # Store futures signal in Redis
                signal_key = f"futures_signal:{instrument_key}:{int(time.time())}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))
                
                # Add to futures signals queue
                self.redis_client.lpush("futures_signals", json.dumps(signal))
                self.redis_client.ltrim("futures_signals", 0, 199)
                
                logger.info(f"📉 FUTURES SELL: {instrument_key} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
        except Exception as e:
            logger.error(f"Error generating futures signals: {e}")
    
    def _on_error(self, error):
        """Handle WebSocket errors"""
        logger.error(f"Futures WebSocket error: {error}")
        
        # Update Redis status
        self.redis_client.setex("futures_websocket_status", 60, "error")
        self.redis_client.set("futures_last_error", str(error))
    
    def _on_close(self, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"Futures WebSocket closed: {close_status_code} - {close_msg}")
        self.running = False
        
        # Update Redis status
        self.redis_client.setex("futures_websocket_status", 60, "disconnected")
        self.redis_client.set("futures_last_disconnection", datetime.now().isoformat())
    
    def add_futures_client(self, client_id: str, instruments: List[str]):
        """Add a new futures client and subscribe to instruments"""
        try:
            # Store futures client info
            self.redis_client.hset(f"futures_client:{client_id}", mapping={
                "instruments": json.dumps(instruments),
                "created_at": datetime.now().isoformat(),
                "status": "active",
                "client_type": "futures"
            })
            
            # Subscribe client to futures instruments
            for instrument in instruments:
                self.redis_client.sadd(f"futures_subscribers:{instrument}", client_id)
                self.redis_client.sadd(f"futures_client_instruments:{client_id}", instrument)
            
            logger.info(f"👤 Added futures client {client_id} for instruments: {instruments}")
            
        except Exception as e:
            logger.error(f"Error adding futures client: {e}")
    
    def get_futures_data(self, instrument_key: str = None):
        """Get futures data from Redis cache"""
        try:
            if instrument_key:
                # Get specific futures instrument data
                cached_data = self.redis_client.get(f"futures_data:{instrument_key}")
                if cached_data:
                    return json.loads(cached_data)
                return None
            else:
                # Get all futures data
                all_data = {}
                instruments = self.redis_client.smembers("futures_instruments")
                for instrument in instruments:
                    cached_data = self.redis_client.get(f"futures_data:{instrument}")
                    if cached_data:
                        all_data[instrument] = json.loads(cached_data)
                return all_data
                
        except Exception as e:
            logger.error(f"Error getting futures data: {e}")
            return None
    
    def get_futures_signals(self, limit: int = 20):
        """Get recent futures trading signals from Redis"""
        try:
            signals = self.redis_client.lrange("futures_signals", 0, limit - 1)
            return [json.loads(signal) for signal in signals]
        except Exception as e:
            logger.error(f"Error getting futures signals: {e}")
            return []
    
    def get_futures_stats(self):
        """Get futures trading statistics"""
        try:
            stats = {
                'total_futures_instruments': len(self.futures_instruments),
                'active_futures_data': len([k for k in self.redis_client.keys("futures_data:*")]),
                'total_futures_clients': len(self.redis_client.keys("futures_client:*")),
                'total_futures_signals': self.redis_client.llen("futures_signals"),
                'futures_websocket_status': self.redis_client.get("futures_websocket_status"),
                'redis_memory_usage': self.redis_client.info('memory').get('used_memory_human', 'Unknown')
            }
            return stats
        except Exception as e:
            logger.error(f"Error getting futures stats: {e}")
            return {}
    
    def stop(self):
        """Stop the futures trading application"""
        self.running = False
        if self.streamer:
            self.streamer.disconnect()
        
        # Update Redis status
        self.redis_client.setex("futures_websocket_status", 60, "stopped")
        logger.info("Futures trading app stopped")

def main():
    """Main futures trading application"""
    print("🚀 Starting Futures Trading Application")
    print("📊 Trading 34 NSE Futures instruments")
    
    # Your access token
    access_token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"
    
    # Create futures trading app
    app = FuturesTradingApp(access_token)
    
    # Add some test futures clients
    app.add_futures_client("futures_client_1", ["NSE_FO|58934", "NSE_FO|58935", "NSE_FO|58936"])
    app.add_futures_client("futures_client_2", ["NSE_FO|58937", "NSE_FO|58938", "NSE_FO|58939"])
    app.add_futures_client("futures_client_3", ["NSE_FO|58946", "NSE_FO|58949", "NSE_FO|58951"])
    
    # Start futures data
    app.start_futures_data()
    
    try:
        # Run for 3 minutes
        print("⏱️  Running futures trading for 3 minutes...")
        print("📊 Check Redis Insight to see futures data in real-time!")
        print("🔗 Redis Insight: http://localhost:8001")
        print("📈 Look for keys starting with 'futures_' in Redis Insight")
        
        # Print stats every 30 seconds
        for i in range(6):
            time.sleep(30)
            stats = app.get_futures_stats()
            print(f"📈 Futures Stats: {stats}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    finally:
        app.stop()
        print("✅ Futures trading app stopped")

if __name__ == "__main__":
    main()
