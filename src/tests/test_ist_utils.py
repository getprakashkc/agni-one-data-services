"""
Test IST utilities for financial data
"""

from ist_utils import (
    get_ist_now, get_ist_timestamp, get_ist_market_status, 
    is_market_open, format_ist_for_redis, get_ist_timestamp_int
)

def test_ist_utilities():
    """Test IST utility functions"""
    print("🧪 Testing IST Utilities")
    print("=" * 50)
    
    # Test current IST time
    ist_now = get_ist_now()
    print(f"🕐 Current IST Time: {ist_now}")
    print(f"📅 IST Date: {ist_now.strftime('%Y-%m-%d')}")
    print(f"⏰ IST Time: {ist_now.strftime('%H:%M:%S')}")
    print(f"🌍 Timezone: {ist_now.tzinfo}")
    
    # Test IST timestamp
    ist_timestamp = get_ist_timestamp()
    print(f"📊 IST Timestamp: {ist_timestamp}")
    
    # Test IST timestamp int
    ist_timestamp_int = get_ist_timestamp_int()
    print(f"🔢 IST Timestamp Int: {ist_timestamp_int}")
    
    # Test market status
    market_status = get_ist_market_status()
    print(f"\n📈 Market Status:")
    print(f"   Current Time: {market_status['current_time_ist']}")
    print(f"   Market Open: {market_status['is_market_open']}")
    print(f"   Market Hours: {market_status['is_market_hours']}")
    print(f"   Timezone: {market_status['timezone']}")
    print(f"   Date: {market_status['date']}")
    print(f"   Time: {market_status['time']}")
    print(f"   Weekday: {market_status['weekday']}")
    print(f"   Weekend: {market_status['is_weekend']}")
    
    if not market_status['is_market_open']:
        print(f"   Next Market Open: {market_status['market_open_time']}")
        print(f"   Next Market Close: {market_status['market_close_time']}")
    
    # Test market open check
    is_open = is_market_open()
    print(f"\n🎯 Market Open Check: {is_open}")
    
    # Test Redis format
    redis_format = format_ist_for_redis()
    print(f"📦 Redis Format: {redis_format}")
    
    print("\n✅ IST Utilities Test Complete!")

if __name__ == "__main__":
    test_ist_utilities()
