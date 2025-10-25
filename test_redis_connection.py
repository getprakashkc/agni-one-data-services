#!/usr/bin/env python3
"""
Test Redis Connection
Simple script to test Redis connection and basic operations
"""

import redis
import json
from datetime import datetime

def test_redis_connection():
    """Test Redis connection and basic operations"""
    print("🔍 Testing Redis Connection...")
    
    try:
        # Connect to Redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Test connection
        redis_client.ping()
        print("✅ Redis connection successful!")
        
        # Test basic operations
        print("\n📊 Testing Redis Operations...")
        
        # 1. String operations
        redis_client.set("test_key", "Hello Redis!")
        value = redis_client.get("test_key")
        print(f"✅ String test: {value}")
        
        # 2. JSON operations
        test_data = {
            "instrument": "NSE_INDEX|Nifty 50",
            "ltp": 25795.15,
            "timestamp": datetime.now().isoformat()
        }
        redis_client.setex("test_market_data", 30, json.dumps(test_data))
        cached_data = json.loads(redis_client.get("test_market_data"))
        print(f"✅ JSON test: {cached_data}")
        
        # 3. Set operations
        redis_client.sadd("test_instruments", "NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank")
        instruments = redis_client.smembers("test_instruments")
        print(f"✅ Set test: {instruments}")
        
        # 4. List operations
        redis_client.lpush("test_signals", json.dumps({"signal": "BUY", "price": 100}))
        redis_client.lpush("test_signals", json.dumps({"signal": "SELL", "price": 200}))
        signals = redis_client.lrange("test_signals", 0, -1)
        print(f"✅ List test: {[json.loads(s) for s in signals]}")
        
        # 5. Hash operations
        redis_client.hset("test_client", mapping={
            "name": "client_1",
            "instruments": json.dumps(["NSE_INDEX|Nifty 50"]),
            "status": "active"
        })
        client_data = redis_client.hgetall("test_client")
        print(f"✅ Hash test: {client_data}")
        
        # 6. TTL operations
        redis_client.setex("test_ttl", 10, "This will expire in 10 seconds")
        ttl = redis_client.ttl("test_ttl")
        print(f"✅ TTL test: {ttl} seconds remaining")
        
        # 7. Memory usage
        memory_usage = redis_client.memory_usage("test_key")
        print(f"✅ Memory test: {memory_usage} bytes")
        
        # Cleanup
        redis_client.delete("test_key", "test_market_data", "test_instruments", 
                           "test_signals", "test_client", "test_ttl")
        print("\n🧹 Cleaned up test data")
        
        print("\n🎉 All Redis tests passed!")
        return True
        
    except redis.ConnectionError:
        print("❌ Redis connection failed!")
        print("💡 Make sure Redis is running on localhost:6379")
        print("💡 If using Redis Insight, make sure it's started")
        return False
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
        return False

if __name__ == "__main__":
    test_redis_connection()
