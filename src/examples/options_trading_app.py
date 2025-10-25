#!/usr/bin/env python3
"""
NIFTY Options Trading Application with Redis
Specialized for NIFTY Options Chain (Call & Put options)
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

class OptionsTradingApp:
    """NIFTY Options trading application with Redis caching"""
    
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
        
        # NIFTY Options Chain
        self.options_instruments = {
            "NSE_FO|58934": "NIFTY 25400 CE 28 OCT 25",
            "NSE_FO|58935": "NIFTY 25400 PE 28 OCT 25",
            "NSE_FO|58936": "NIFTY 25450 CE 28 OCT 25",
            "NSE_FO|58937": "NIFTY 25450 PE 28 OCT 25",
            "NSE_FO|58938": "NIFTY 25500 CE 28 OCT 25",
            "NSE_FO|58939": "NIFTY 25500 PE 28 OCT 25",
            "NSE_FO|58946": "NIFTY 25550 CE 28 OCT 25",
            "NSE_FO|58949": "NIFTY 25550 PE 28 OCT 25",
            "NSE_FO|58951": "NIFTY 25600 CE 28 OCT 25",
            "NSE_FO|58952": "NIFTY 25600 PE 28 OCT 25",
            "NSE_FO|58953": "NIFTY 25650 CE 28 OCT 25",
            "NSE_FO|58954": "NIFTY 25650 PE 28 OCT 25",
            "NSE_FO|58956": "NIFTY 25700 CE 28 OCT 25",
            "NSE_FO|58959": "NIFTY 25700 PE 28 OCT 25",
            "NSE_FO|58960": "NIFTY 25750 CE 28 OCT 25",
            "NSE_FO|58962": "NIFTY 25750 PE 28 OCT 25",
            "NSE_FO|58963": "NIFTY 25800 CE 28 OCT 25",
            "NSE_FO|58965": "NIFTY 25800 PE 28 OCT 25",
            "NSE_FO|58970": "NIFTY 25850 CE 28 OCT 25",
            "NSE_FO|58973": "NIFTY 25850 PE 28 OCT 25",
            "NSE_FO|58974": "NIFTY 25900 CE 28 OCT 25",
            "NSE_FO|58997": "NIFTY 25900 PE 28 OCT 25",
            "NSE_FO|58998": "NIFTY 25950 CE 28 OCT 25",
            "NSE_FO|59003": "NIFTY 25950 PE 28 OCT 25",
            "NSE_FO|59004": "NIFTY 26000 CE 28 OCT 25",
            "NSE_FO|59005": "NIFTY 26000 PE 28 OCT 25",
            "NSE_FO|59010": "NIFTY 26050 CE 28 OCT 25",
            "NSE_FO|59011": "NIFTY 26050 PE 28 OCT 25",
            "NSE_FO|59022": "NIFTY 26100 CE 28 OCT 25",
            "NSE_FO|59023": "NIFTY 26100 PE 28 OCT 25",
            "NSE_FO|59026": "NIFTY 26150 CE 28 OCT 25",
            "NSE_FO|59027": "NIFTY 26150 PE 28 OCT 25",
            "NSE_FO|59033": "NIFTY 26200 CE 28 OCT 25",
            "NSE_FO|59034": "NIFTY 26200 PE 28 OCT 25"
        }
        
        # Options chain analysis
        self.strike_prices = [25400, 25450, 25500, 25550, 25600, 25650, 25700, 25750, 25800, 25850, 25900, 25950, 26000, 26050, 26100, 26150, 26200]
        self.current_strike = 25800  # Assume current NIFTY is around 25800
    
    def start_options_data(self):
        """Start NIFTY options data streaming with Redis caching"""
        logger.info(f"🚀 Starting NIFTY Options data for {len(self.options_instruments)} options")
        
        # Store options instruments in Redis
        self.redis_client.sadd("options_instruments", *self.options_instruments.keys())
        
        # Store options metadata
        for instrument_key, option_name in self.options_instruments.items():
            self.redis_client.hset("options_metadata", instrument_key, option_name)
        
        logger.info(f"📊 NIFTY Options Chain: {len(self.options_instruments)} options")
        
        # Create market data streamer
        self.streamer = upstox_client.MarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=list(self.options_instruments.keys()),
            mode="full"  # Full data for options trading
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
        logger.info("🔗 NIFTY Options WebSocket connected")
        
        # Store connection status in Redis
        self.redis_client.setex("options_websocket_status", 60, "connected")
        self.redis_client.set("options_last_connection", format_ist_for_redis())
    
    def _on_message(self, message):
        """Process NIFTY options market data messages with Redis caching"""
        try:
            if 'feeds' in message:
                for instrument_key, feed_data in message['feeds'].items():
                    if 'fullFeed' in feed_data:
                        full_feed = feed_data['fullFeed']
                        if 'indexFF' in full_feed:
                            index_data = full_feed['indexFF']
                            if 'ltpc' in index_data:
                                ltpc = index_data['ltpc']
                                
                                # Get option name
                                option_name = self.options_instruments.get(instrument_key, "Unknown")
                                
                                # Parse option details
                                option_details = self._parse_option_name(option_name)
                                
                                # Create options market data object
                                options_data = {
                                    'instrument_key': instrument_key,
                                    'option_name': option_name,
                                    'strike_price': option_details['strike'],
                                    'option_type': option_details['type'],  # CE or PE
                                    'expiry': option_details['expiry'],
                                    'ltp': ltpc.get('ltp', 0),
                                    'ltt': ltpc.get('ltt', ''),
                                    'change_percent': ltpc.get('cp', 0),
                                    'timestamp': format_ist_for_redis(),
                                    'ohlc': index_data.get('marketOHLC', {}),
                                    'instrument_type': 'OPTIONS',
                                    'exchange': 'NSE_FO',
                                    'moneyness': self._calculate_moneyness(option_details['strike'], option_details['type'])
                                }
                                
                                # Cache in Redis with 30-second TTL
                                cache_key = f"options_data:{instrument_key}"
                                self.redis_client.setex(cache_key, 30, json.dumps(options_data))
                                
                                # Update local cache
                                self.market_data[instrument_key] = options_data
                                
                                # Broadcast to options subscribers
                                self._broadcast_to_options_subscribers(instrument_key, options_data)
                                
                                # Generate options trading signals
                                self._generate_options_signals(instrument_key, options_data)
                                
                                # Update options chain analysis
                                self._update_options_chain_analysis(instrument_key, options_data)
                                
                                # Log options update
                                self._log_options_update(instrument_key, options_data)
                                
        except Exception as e:
            logger.error(f"Error processing options message: {e}")
    
    def _parse_option_name(self, option_name: str):
        """Parse option name to extract details"""
        try:
            # Example: "NIFTY 25400 CE 28 OCT 25"
            parts = option_name.split()
            if len(parts) >= 4:
                strike = int(parts[1])
                option_type = parts[2]  # CE or PE
                expiry = f"{parts[3]} {parts[4]} {parts[5]}"  # "28 OCT 25"
                return {
                    'strike': strike,
                    'type': option_type,
                    'expiry': expiry
                }
        except:
            pass
        
        return {'strike': 0, 'type': 'UNKNOWN', 'expiry': 'UNKNOWN'}
    
    def _calculate_moneyness(self, strike: int, option_type: str):
        """Calculate moneyness of the option"""
        try:
            if option_type == 'CE':
                if strike < self.current_strike:
                    return 'ITM'  # In The Money
                elif strike == self.current_strike:
                    return 'ATM'  # At The Money
                else:
                    return 'OTM'  # Out of The Money
            elif option_type == 'PE':
                if strike > self.current_strike:
                    return 'ITM'  # In The Money
                elif strike == self.current_strike:
                    return 'ATM'  # At The Money
                else:
                    return 'OTM'  # Out of The Money
        except:
            pass
        
        return 'UNKNOWN'
    
    def _broadcast_to_options_subscribers(self, instrument_key: str, data: dict):
        """Broadcast options data to all subscribers"""
        try:
            # Get all subscribers for this options instrument
            subscribers = self.redis_client.smembers(f"options_subscribers:{instrument_key}")
            
            if subscribers:
                # Publish to Redis channel for real-time updates
                self.redis_client.publish(f"options_updates:{instrument_key}", json.dumps(data))
                
                # Log broadcast activity
                logger.info(f"📡 Options broadcast: {data['option_name']} to {len(subscribers)} subscribers")
                
        except Exception as e:
            logger.error(f"Error broadcasting options data: {e}")
    
    def _generate_options_signals(self, instrument_key: str, options_data: dict):
        """Generate options trading signals"""
        try:
            ltp = options_data['ltp']
            change_percent = options_data['change_percent']
            option_type = options_data['option_type']
            moneyness = options_data['moneyness']
            
            # Options-specific trading strategy
            signal_threshold = 2.0  # Higher threshold for options
            
            if change_percent > signal_threshold:
                signal = {
                    'instrument': instrument_key,
                    'option_name': options_data['option_name'],
                    'signal': 'BUY',
                    'price': ltp,
                    'confidence': min(change_percent / 3.0, 1.0),
                    'timestamp': format_ist_for_redis(),
                    'strategy': 'options_momentum',
                    'instrument_type': 'OPTIONS',
                    'option_type': option_type,
                    'moneyness': moneyness,
                    'strike_price': options_data['strike_price']
                }
                
                # Store options signal in Redis
                signal_key = f"options_signal:{instrument_key}:{get_ist_timestamp_int()}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))
                
                # Add to options signals queue
                self.redis_client.lpush("options_signals", json.dumps(signal))
                self.redis_client.ltrim("options_signals", 0, 199)  # Keep last 200 signals
                
                logger.info(f"📈 OPTIONS BUY: {options_data['option_name']} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
            elif change_percent < -signal_threshold:
                signal = {
                    'instrument': instrument_key,
                    'option_name': options_data['option_name'],
                    'signal': 'SELL',
                    'price': ltp,
                    'confidence': min(abs(change_percent) / 3.0, 1.0),
                    'timestamp': format_ist_for_redis(),
                    'strategy': 'options_momentum',
                    'instrument_type': 'OPTIONS',
                    'option_type': option_type,
                    'moneyness': moneyness,
                    'strike_price': options_data['strike_price']
                }
                
                # Store options signal in Redis
                signal_key = f"options_signal:{instrument_key}:{get_ist_timestamp_int()}"
                self.redis_client.setex(signal_key, 300, json.dumps(signal))
                
                # Add to options signals queue
                self.redis_client.lpush("options_signals", json.dumps(signal))
                self.redis_client.ltrim("options_signals", 0, 199)
                
                logger.info(f"📉 OPTIONS SELL: {options_data['option_name']} at ₹{ltp:.2f} (Change: {change_percent:.2f}%)")
                
        except Exception as e:
            logger.error(f"Error generating options signals: {e}")
    
    def _update_options_chain_analysis(self, instrument_key: str, options_data: dict):
        """Update options chain analysis in Redis"""
        try:
            strike = options_data['strike_price']
            option_type = options_data['option_type']
            
            # Store by strike price
            strike_key = f"options_chain:{strike}"
            self.redis_client.hset(strike_key, f"{option_type}_ltp", options_data['ltp'])
            self.redis_client.hset(strike_key, f"{option_type}_change", options_data['change_percent'])
            self.redis_client.hset(strike_key, f"{option_type}_timestamp", options_data['timestamp'])
            
            # Set TTL for options chain data
            self.redis_client.expire(strike_key, 60)  # 1 minute TTL
            
        except Exception as e:
            logger.error(f"Error updating options chain: {e}")
    
    def _log_options_update(self, instrument_key: str, data: dict):
        """Log options update to Redis for monitoring"""
        try:
            # Store in Redis list (keep last 100 updates)
            log_key = f"options_logs:{instrument_key}"
            self.redis_client.lpush(log_key, json.dumps(data))
            self.redis_client.ltrim(log_key, 0, 99)  # Keep only last 100 entries
            
            # Update options instrument stats
            stats_key = f"options_stats:{instrument_key}"
            stats = {
                'last_update': format_ist_for_redis(),
                'ltp': data['ltp'],
                'change_percent': data['change_percent'],
                'subscriber_count': len(self.redis_client.smembers(f"options_subscribers:{instrument_key}")),
                'instrument_type': 'OPTIONS',
                'option_name': data['option_name'],
                'moneyness': data['moneyness']
            }
            self.redis_client.setex(stats_key, 300, json.dumps(stats))  # 5-minute TTL
            
        except Exception as e:
            logger.error(f"Error logging options update: {e}")
    
    def _on_error(self, error):
        """Handle WebSocket errors"""
        logger.error(f"Options WebSocket error: {error}")
        
        # Update Redis status
        self.redis_client.setex("options_websocket_status", 60, "error")
        self.redis_client.set("options_last_error", str(error))
    
    def _on_close(self, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.info(f"Options WebSocket closed: {close_status_code} - {close_msg}")
        self.running = False
        
        # Update Redis status
        self.redis_client.setex("options_websocket_status", 60, "disconnected")
        self.redis_client.set("options_last_disconnection", format_ist_for_redis())
    
    def add_options_client(self, client_id: str, instruments: List[str]):
        """Add a new options client and subscribe to instruments"""
        try:
            # Store options client info
            self.redis_client.hset(f"options_client:{client_id}", mapping={
                "instruments": json.dumps(instruments),
                "created_at": format_ist_for_redis(),
                "status": "active",
                "client_type": "options"
            })
            
            # Subscribe client to options instruments
            for instrument in instruments:
                self.redis_client.sadd(f"options_subscribers:{instrument}", client_id)
                self.redis_client.sadd(f"options_client_instruments:{client_id}", instrument)
            
            logger.info(f"👤 Added options client {client_id} for instruments: {instruments}")
            
        except Exception as e:
            logger.error(f"Error adding options client: {e}")
    
    def get_options_data(self, instrument_key: str = None):
        """Get options data from Redis cache"""
        try:
            if instrument_key:
                # Get specific options instrument data
                cached_data = self.redis_client.get(f"options_data:{instrument_key}")
                if cached_data:
                    return json.loads(cached_data)
                return None
            else:
                # Get all options data
                all_data = {}
                instruments = self.redis_client.smembers("options_instruments")
                for instrument in instruments:
                    cached_data = self.redis_client.get(f"options_data:{instrument}")
                    if cached_data:
                        all_data[instrument] = json.loads(cached_data)
                return all_data
                
        except Exception as e:
            logger.error(f"Error getting options data: {e}")
            return None
    
    def get_options_chain(self, strike_price: int = None):
        """Get options chain data for a specific strike"""
        try:
            if strike_price:
                chain_key = f"options_chain:{strike_price}"
                return self.redis_client.hgetall(chain_key)
            else:
                # Get all strikes
                all_chains = {}
                for strike in self.strike_prices:
                    chain_key = f"options_chain:{strike}"
                    chain_data = self.redis_client.hgetall(chain_key)
                    if chain_data:
                        all_chains[strike] = chain_data
                return all_chains
                
        except Exception as e:
            logger.error(f"Error getting options chain: {e}")
            return {}
    
    def get_options_signals(self, limit: int = 20):
        """Get recent options trading signals from Redis"""
        try:
            signals = self.redis_client.lrange("options_signals", 0, limit - 1)
            return [json.loads(signal) for signal in signals]
        except Exception as e:
            logger.error(f"Error getting options signals: {e}")
            return []
    
    def get_options_stats(self):
        """Get options trading statistics"""
        try:
            stats = {
                'total_options_instruments': len(self.options_instruments),
                'active_options_data': len([k for k in self.redis_client.keys("options_data:*")]),
                'total_options_clients': len(self.redis_client.keys("options_client:*")),
                'total_options_signals': self.redis_client.llen("options_signals"),
                'options_websocket_status': self.redis_client.get("options_websocket_status"),
                'options_chain_strikes': len(self.redis_client.keys("options_chain:*")),
                'redis_memory_usage': self.redis_client.info('memory').get('used_memory_human', 'Unknown')
            }
            return stats
        except Exception as e:
            logger.error(f"Error getting options stats: {e}")
            return {}
    
    def stop(self):
        """Stop the options trading application"""
        self.running = False
        if self.streamer:
            self.streamer.disconnect()
        
        # Update Redis status
        self.redis_client.setex("options_websocket_status", 60, "stopped")
        logger.info("Options trading app stopped")

def main():
    """Main options trading application"""
    print("🚀 Starting NIFTY Options Trading Application")
    print("📊 Trading 34 NIFTY Options (Call & Put options)")
    print("🎯 Options Chain: 25400 to 26200 strikes")
    
    # Display IST market status
    market_status = get_ist_market_status()
    print(f"🕐 Current IST Time: {market_status['current_time_ist']}")
    print(f"📈 Market Status: {'OPEN' if market_status['is_market_open'] else 'CLOSED'}")
    print(f"🌍 Timezone: {market_status['timezone']}")
    if not market_status['is_market_open']:
        print(f"⏰ Next Market Open: {market_status['market_open_time']}")
    
    # Your access token
    access_token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"
    
    # Create options trading app
    app = OptionsTradingApp(access_token)
    
    # Add some test options clients
    app.add_options_client("options_client_1", ["NSE_FO|58934", "NSE_FO|58935", "NSE_FO|58936"])  # 25400 CE/PE
    app.add_options_client("options_client_2", ["NSE_FO|58956", "NSE_FO|58959", "NSE_FO|58960"])  # 25700 CE/PE
    app.add_options_client("options_client_3", ["NSE_FO|59004", "NSE_FO|59005", "NSE_FO|59010"])  # 26000 CE/PE
    
    # Start options data
    app.start_options_data()
    
    try:
        # Run for 3 minutes
        print("⏱️  Running options trading for 3 minutes...")
        print("📊 Check Redis Insight to see options data in real-time!")
        print("🔗 Redis Insight: http://localhost:8001")
        print("📈 Look for keys starting with 'options_' in Redis Insight")
        print("🎯 Options Chain Analysis: Check 'options_chain:*' keys")
        
        # Print stats every 30 seconds
        for i in range(6):
            time.sleep(30)
            stats = app.get_options_stats()
            print(f"📈 Options Stats: {stats}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
    finally:
        app.stop()
        print("✅ Options trading app stopped")

if __name__ == "__main__":
    main()
