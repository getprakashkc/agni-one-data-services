#!/usr/bin/env python3
"""
Futures Redis Monitor
Monitor futures trading data in Redis in real-time
"""

import redis
import json
import time
from datetime import datetime

def monitor_futures_redis():
    """Monitor futures Redis data in real-time"""
    print("🔍 Futures Redis Monitor - Watching futures data in real-time")
    print("📊 Open Redis Insight at http://localhost:8001 for visual monitoring")
    print("📈 Look for keys starting with 'futures_' in Redis Insight")
    print("⏹️  Press Ctrl+C to stop\n")
    
    try:
        # Connect to Redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        print("✅ Connected to Redis\n")
        
        # Monitor for 3 minutes
        for i in range(36):  # 36 * 5 seconds = 3 minutes
            print(f"📊 Futures Redis Status - {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 60)
            
            # 1. Futures instruments
            futures_instruments = redis_client.smembers("futures_instruments")
            print(f"📈 Futures Instruments: {len(futures_instruments)}")
            
            # 2. Futures market data
            print(f"\n💰 Futures Market Data:")
            futures_data_keys = redis_client.keys("futures_data:*")
            print(f"   - Active futures data keys: {len(futures_data_keys)}")
            
            # Show first 5 instruments with data
            count = 0
            for key in futures_data_keys[:5]:
                instrument = key.replace("futures_data:", "")
                data = redis_client.get(key)
                if data:
                    futures_data = json.loads(data)
                    ttl = redis_client.ttl(key)
                    print(f"   - {instrument}: ₹{futures_data.get('ltp', 0):.2f} (TTL: {ttl}s)")
                    count += 1
            
            if len(futures_data_keys) > 5:
                print(f"   - ... and {len(futures_data_keys) - 5} more instruments")
            
            # 3. Futures client subscriptions
            print(f"\n👥 Futures Client Subscriptions:")
            futures_client_keys = redis_client.keys("futures_client:*")
            print(f"   - Total futures clients: {len(futures_client_keys)}")
            
            # Show client subscriptions
            for client_key in futures_client_keys:
                client_id = client_key.replace("futures_client:", "")
                client_data = redis_client.hgetall(client_key)
                if client_data:
                    instruments = json.loads(client_data.get('instruments', '[]'))
                    print(f"   - {client_id}: {len(instruments)} instruments")
            
            # 4. Futures trading signals
            futures_signals_count = redis_client.llen("futures_signals")
            print(f"\n📊 Futures Trading Signals: {futures_signals_count}")
            if futures_signals_count > 0:
                recent_signals = redis_client.lrange("futures_signals", 0, 2)
                for signal in recent_signals:
                    signal_data = json.loads(signal)
                    print(f"   - {signal_data.get('signal')} {signal_data.get('instrument')} at ₹{signal_data.get('price', 0):.2f}")
            
            # 5. Futures subscriber counts
            print(f"\n📡 Futures Subscribers:")
            futures_subscriber_keys = redis_client.keys("futures_subscribers:*")
            total_subscribers = 0
            for key in futures_subscriber_keys:
                subscribers = redis_client.smembers(key)
                total_subscribers += len(subscribers)
                if len(subscribers) > 0:
                    instrument = key.replace("futures_subscribers:", "")
                    print(f"   - {instrument}: {len(subscribers)} subscribers")
            
            print(f"   - Total active subscribers: {total_subscribers}")
            
            # 6. Redis memory usage
            try:
                memory_info = redis_client.info('memory')
                used_memory = memory_info.get('used_memory_human', 'Unknown')
                print(f"\n💾 Memory Usage: {used_memory}")
            except:
                print(f"\n💾 Memory Usage: Unable to get info")
            
            # 7. Futures WebSocket status
            ws_status = redis_client.get("futures_websocket_status")
            if ws_status:
                print(f"\n🔗 Futures WebSocket Status: {ws_status}")
            
            # 8. Key statistics
            all_futures_keys = redis_client.keys("futures_*")
            print(f"\n📊 Redis Key Statistics:")
            print(f"   - Total futures keys: {len(all_futures_keys)}")
            print(f"   - Data keys: {len(redis_client.keys('futures_data:*'))}")
            print(f"   - Client keys: {len(redis_client.keys('futures_client:*'))}")
            print(f"   - Signal keys: {len(redis_client.keys('futures_signal:*'))}")
            print(f"   - Log keys: {len(redis_client.keys('futures_logs:*'))}")
            
            print("\n" + "="*60 + "\n")
            time.sleep(5)  # Check every 5 seconds
            
    except redis.ConnectionError:
        print("❌ Redis connection failed!")
        print("💡 Make sure Redis is running")
    except KeyboardInterrupt:
        print("\n⏹️  Futures monitoring stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    monitor_futures_redis()
