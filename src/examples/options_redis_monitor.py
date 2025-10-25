#!/usr/bin/env python3
"""
NIFTY Options Redis Monitor
Monitor NIFTY Options trading data in Redis in real-time
"""

import redis
import json
import time
from datetime import datetime

def monitor_options_redis():
    """Monitor NIFTY Options Redis data in real-time"""
    print("🔍 NIFTY Options Redis Monitor - Watching options data in real-time")
    print("📊 Open Redis Insight at http://localhost:8001 for visual monitoring")
    print("📈 Look for keys starting with 'options_' in Redis Insight")
    print("🎯 Options Chain Analysis: Check 'options_chain:*' keys")
    print("⏹️  Press Ctrl+C to stop\n")
    
    try:
        # Connect to Redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        print("✅ Connected to Redis\n")
        
        # Monitor for 3 minutes
        for i in range(36):  # 36 * 5 seconds = 3 minutes
            print(f"📊 NIFTY Options Redis Status - {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 70)
            
            # 1. Options instruments
            options_instruments = redis_client.smembers("options_instruments")
            print(f"📈 Options Instruments: {len(options_instruments)}")
            
            # 2. Options market data
            print(f"\n💰 Options Market Data:")
            options_data_keys = redis_client.keys("options_data:*")
            print(f"   - Active options data keys: {len(options_data_keys)}")
            
            # Show first 5 options with data
            count = 0
            for key in options_data_keys[:5]:
                instrument = key.replace("options_data:", "")
                data = redis_client.get(key)
                if data:
                    options_data = json.loads(data)
                    ttl = redis_client.ttl(key)
                    option_name = options_data.get('option_name', 'Unknown')
                    ltp = options_data.get('ltp', 0)
                    moneyness = options_data.get('moneyness', 'Unknown')
                    print(f"   - {option_name}: ₹{ltp:.2f} ({moneyness}) (TTL: {ttl}s)")
                    count += 1
            
            if len(options_data_keys) > 5:
                print(f"   - ... and {len(options_data_keys) - 5} more options")
            
            # 3. Options client subscriptions
            print(f"\n👥 Options Client Subscriptions:")
            options_client_keys = redis_client.keys("options_client:*")
            print(f"   - Total options clients: {len(options_client_keys)}")
            
            # Show client subscriptions
            for client_key in options_client_keys:
                client_id = client_key.replace("options_client:", "")
                client_data = redis_client.hgetall(client_key)
                if client_data:
                    instruments = json.loads(client_data.get('instruments', '[]'))
                    print(f"   - {client_id}: {len(instruments)} options")
            
            # 4. Options trading signals
            options_signals_count = redis_client.llen("options_signals")
            print(f"\n📊 Options Trading Signals: {options_signals_count}")
            if options_signals_count > 0:
                recent_signals = redis_client.lrange("options_signals", 0, 2)
                for signal in recent_signals:
                    signal_data = json.loads(signal)
                    option_name = signal_data.get('option_name', 'Unknown')
                    signal_type = signal_data.get('signal', 'Unknown')
                    price = signal_data.get('price', 0)
                    print(f"   - {signal_type} {option_name} at ₹{price:.2f}")
            
            # 5. Options chain analysis
            print(f"\n🎯 Options Chain Analysis:")
            options_chain_keys = redis_client.keys("options_chain:*")
            print(f"   - Active strikes: {len(options_chain_keys)}")
            
            # Show options chain for a few strikes
            for key in options_chain_keys[:3]:
                strike = key.replace("options_chain:", "")
                chain_data = redis_client.hgetall(key)
                if chain_data:
                    ce_ltp = chain_data.get('CE_ltp', 'N/A')
                    pe_ltp = chain_data.get('PE_ltp', 'N/A')
                    print(f"   - Strike {strike}: CE ₹{ce_ltp}, PE ₹{pe_ltp}")
            
            # 6. Options subscriber counts
            print(f"\n📡 Options Subscribers:")
            options_subscriber_keys = redis_client.keys("options_subscribers:*")
            total_subscribers = 0
            for key in options_subscriber_keys:
                subscribers = redis_client.smembers(key)
                total_subscribers += len(subscribers)
                if len(subscribers) > 0:
                    instrument = key.replace("options_subscribers:", "")
                    print(f"   - {instrument}: {len(subscribers)} subscribers")
            
            print(f"   - Total active subscribers: {total_subscribers}")
            
            # 7. Redis memory usage
            try:
                memory_info = redis_client.info('memory')
                used_memory = memory_info.get('used_memory_human', 'Unknown')
                print(f"\n💾 Memory Usage: {used_memory}")
            except:
                print(f"\n💾 Memory Usage: Unable to get info")
            
            # 8. Options WebSocket status
            ws_status = redis_client.get("options_websocket_status")
            if ws_status:
                print(f"\n🔗 Options WebSocket Status: {ws_status}")
            
            # 9. Key statistics
            all_options_keys = redis_client.keys("options_*")
            print(f"\n📊 Redis Key Statistics:")
            print(f"   - Total options keys: {len(all_options_keys)}")
            print(f"   - Data keys: {len(redis_client.keys('options_data:*'))}")
            print(f"   - Client keys: {len(redis_client.keys('options_client:*'))}")
            print(f"   - Signal keys: {len(redis_client.keys('options_signal:*'))}")
            print(f"   - Chain keys: {len(redis_client.keys('options_chain:*'))}")
            print(f"   - Log keys: {len(redis_client.keys('options_logs:*'))}")
            
            # 10. Options metadata
            options_metadata = redis_client.hgetall("options_metadata")
            if options_metadata:
                print(f"\n📋 Options Metadata:")
                print(f"   - Total options mapped: {len(options_metadata)}")
                # Show first 3 options
                count = 0
                for instrument, option_name in options_metadata.items():
                    if count < 3:
                        print(f"   - {instrument}: {option_name}")
                        count += 1
                if len(options_metadata) > 3:
                    print(f"   - ... and {len(options_metadata) - 3} more options")
            
            print("\n" + "="*70 + "\n")
            time.sleep(5)  # Check every 5 seconds
            
    except redis.ConnectionError:
        print("❌ Redis connection failed!")
        print("💡 Make sure Redis is running")
    except KeyboardInterrupt:
        print("\n⏹️  Options monitoring stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    monitor_options_redis()
