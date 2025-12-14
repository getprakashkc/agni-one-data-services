# OHLC Subscription Feature

## Overview

The Data Service now supports separate OHLC (Open, High, Low, Close) candle subscriptions with automatic historical data fetching and caching.

## Features

1. **Separate OHLC Subscriptions** - Subscribe to OHLC data independently from LTPC
2. **Interval Filtering** - Filter by specific intervals (1min, 5min, 15min, 30min, 1day)
3. **Historical Snapshot** - Automatically receive all completed candles from market open when subscribing mid-day
4. **Hybrid Caching** - Fast response from Redis cache with API fallback
5. **Live Updates** - Real-time OHLC candle updates via WebSocket

## WebSocket Actions

### Subscribe to OHLC

```json
{
  "action": "subscribe_ohlc",
  "instruments": ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"],
  "intervals": ["1min", "5min"],
  "include_history": true
}
```

**Parameters:**
- `instruments` (required): List of instrument keys
- `intervals` (optional): List of intervals to subscribe to. Default: `["*"]` (all intervals)
- `include_history` (optional): Whether to fetch historical candles. Default: `true`

**Supported Intervals:**
- `"1min"` - 1 minute candles
- `"5min"` - 5 minute candles
- `"15min"` - 15 minute candles
- `"30min"` - 30 minute candles
- `"1day"` - Daily candles
- `"*"` - All intervals

### Unsubscribe from OHLC

```json
{
  "action": "unsubscribe_ohlc",
  "instruments": ["NSE_INDEX|Nifty 50"],
  "intervals": ["1min"]
}
```

**Parameters:**
- `instruments` (optional): List of instrument keys. If not provided, unsubscribes from all instruments
- `intervals` (optional): List of intervals. If not provided, unsubscribes from all intervals

### Get OHLC Subscriptions

```json
{
  "action": "get_ohlc_subscriptions"
}
```

## Message Types

### 1. OHLC Snapshot (Historical Data)

Sent once when subscribing, contains all completed candles from market open:

```json
{
  "type": "ohlc_snapshot",
  "instrument_key": "NSE_INDEX|Nifty 50",
  "interval": "5min",
  "candles": [
    {
      "timestamp": 1740720000000,
      "open": 24400.0,
      "high": 24450.0,
      "low": 24380.0,
      "close": 24420.0,
      "volume": 1000000,
      "candle_status": "completed"
    },
    // ... more candles
  ],
  "snapshot_time": "2024-01-15T14:00:00",
  "candle_count": 57
}
```

### 2. OHLC Data (Live Updates)

Sent when candles are updated or completed:

```json
{
  "type": "ohlc_data",
  "data": {
    "instrument_key": "NSE_INDEX|Nifty 50",
    "interval": "5min",
    "open": 24500.0,
    "high": 24550.0,
    "low": 24480.0,
    "close": 24520.0,
    "volume": 1500000,
    "timestamp": 1740720600000,
    "candle_status": "completed"
  }
}
```

**Candle Status:**
- `"active"` - Candle is still forming (updating in real-time)
- `"completed"` - Candle is finalized

## Example Usage

### Python Client Example

```python
import asyncio
import json
import websockets

async def ohlc_client_example():
    uri = "ws://localhost:8001/ws"
    
    async with websockets.connect(uri) as websocket:
        # Receive welcome message
        welcome = await websocket.recv()
        print(f"Connected: {json.loads(welcome)}")
        
        # Subscribe to OHLC for 5-minute candles
        subscribe_msg = {
            "action": "subscribe_ohlc",
            "instruments": ["NSE_INDEX|Nifty 50"],
            "intervals": ["5min"],
            "include_history": True
        }
        await websocket.send(json.dumps(subscribe_msg))
        
        # Listen for messages
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "ohlc_snapshot":
                print(f"📊 Historical snapshot: {data['candle_count']} candles")
                for candle in data['candles'][:5]:  # Show first 5
                    print(f"  {candle['timestamp']}: O={candle['open']}, H={candle['high']}, L={candle['low']}, C={candle['close']}")
            
            elif msg_type == "ohlc_data":
                candle = data['data']
                print(f"🕯️  {candle['interval']} candle ({candle['candle_status']}): O={candle['open']}, H={candle['high']}, L={candle['low']}, C={candle['close']}")

asyncio.run(ohlc_client_example())
```

## How It Works

### Historical Data Flow

1. **Client subscribes** to OHLC mid-day (e.g., 2:00 PM)
2. **Data Service checks Redis cache** for historical candles
3. **If cache has data:**
   - Send cached candles immediately (fast)
4. **If cache is incomplete:**
   - Fetch from Upstox API
   - Cache the fetched candles
   - Send to client
5. **Continue with live updates** from WebSocket

### Live Updates Flow

1. **Upstox WebSocket** sends OHLC data in `fullFeed` messages
2. **Data Service parses** OHLC candles from `marketOHLC` field
3. **Determines candle status** (active vs completed)
4. **Caches completed candles** in Redis (24-hour TTL)
5. **Broadcasts to subscribed clients** based on instrument and interval filters

## Caching Strategy

- **Completed candles** are cached in Redis with key format: `ohlc:{instrument_key}:{interval}:{timestamp}`
- **TTL**: 24 hours (candles are historical data)
- **Cache lookup**: Fast retrieval for mid-day subscribers
- **API fallback**: If cache is incomplete, fetch from Upstox API

## Benefits

✅ **Complete Data** - Clients get all candles from market open, even when subscribing mid-day  
✅ **Fast Response** - Historical data served from cache  
✅ **Efficient** - Clients only receive data for subscribed instruments and intervals  
✅ **Reliable** - API fallback ensures data completeness  
✅ **Scalable** - Works for many clients with different subscription needs  

## Notes

- Historical candles are fetched using Upstox's `get_intra_day_candle_data` API
- Candle status detection uses timestamp-based heuristics
- Supported intervals match Upstox WebSocket capabilities (1min, 5min, 15min, 30min, 1day)
- OHLC subscriptions are independent from LTPC subscriptions
