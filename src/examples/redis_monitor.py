#!/usr/bin/env python3
"""
Redis Monitor
Monitor Redis data in real-time
"""

import redis
import json
import time
from datetime import datetime

def monitor_redis():
    """Monitor Redis data in real-time"""
    print("🔍 Redis Monitor - Watching data in real-time")
    print("📊 Open Redis Insight at http://localhost:8001 for visual monitoring")
    print("⏹️  Press Ctrl+C to stop\n")
    
    try:
        # Connect to Redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        print("✅ Connected to Redis\n")
        
        # Monitor for 2 minutes
        for i in range(24):  # 24 * 5 seconds = 2 minutes
            print(f"📊 Redis Status - {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 50)
            
            # 1. Active instruments
            instruments = redis_client.smembers("active_instruments")
            print(f"📈 Active Instruments: {len(instruments)}")
            for instrument in instruments:
                print(f"   - {instrument}")
            
            # 2. Market data
            print(f"\n💰 Market Data:")
            for instrument in instruments:
                data_key = f"market_data:{instrument}"
                data = redis_client.get(data_key)
                if data:
                    market_data = json.loads(data)
                    ttl = redis_client.ttl(data_key)
                    print(f"   - {instrument}: ₹{market_data.get('ltp', 0):.2f} (TTL: {ttl}s)")
                else:
                    print(f"   - {instrument}: No data")
            
            # 3. Client subscriptions
            print(f"\n👥 Client Subscriptions:")
            for instrument in instruments:
                subscribers = redis_client.smembers(f"subscribers:{instrument}")
                print(f"   - {instrument}: {len(subscribers)} subscribers")
                for subscriber in subscribers:
                    print(f"     * {subscriber}")
            
            # 4. Trading signals
            signals_count = redis_client.llen("trading_signals")
            print(f"\n📊 Trading Signals: {signals_count}")
            if signals_count > 0:
                recent_signals = redis_client.lrange("trading_signals", 0, 2)
                for signal in recent_signals:
                    signal_data = json.loads(signal)
                    print(f"   - {signal_data.get('signal')} {signal_data.get('instrument')} at ₹{signal_data.get('price', 0):.2f}")
            
            # 5. Redis memory usage
            try:
                memory_info = redis_client.info('memory')
                used_memory = memory_info.get('used_memory_human', 'Unknown')
                print(f"\n💾 Memory Usage: {used_memory}")
            except:
                print(f"\n💾 Memory Usage: Unable to get info")
            
            # 6. WebSocket status
            ws_status = redis_client.get("websocket_status")
            if ws_status:
                print(f"\n🔗 WebSocket Status: {ws_status}")
            
            print("\n" + "="*60 + "\n")
            time.sleep(5)  # Check every 5 seconds
            
    except redis.ConnectionError:
        print("❌ Redis connection failed!")
        print("💡 Make sure Redis is running")
    except KeyboardInterrupt:
        print("\n⏹️  Monitoring stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    monitor_redis()
