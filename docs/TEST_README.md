# Upstox WebSocket Testing Guide

## Quick Start

### 1. Install Dependencies
```bash
pip install -r test_requirements.txt
```

### 2. Run the Simple Test
```bash
python simple_websocket_test.py
```

### 3. Run the Comprehensive Test
```bash
python test_websocket.py
```

## What Each Test Does

### Simple WebSocket Test (`simple_websocket_test.py`)
- Connects to Upstox WebSocket
- Subscribes to multiple instruments:
  - Nifty 50
  - Bank Nifty
  - Reliance
  - TCS
- Shows real-time LTP (Last Traded Price)
- Runs for 60 seconds

### Comprehensive Test (`test_websocket.py`)
- Tests REST API endpoints
- Tests Market Data WebSocket
- Tests Portfolio WebSocket
- Shows detailed JSON responses

## Expected Output

### Successful Connection
```
🚀 Testing Upstox WebSocket with your access token
🔗 Connecting to Upstox WebSocket...
✅ WebSocket connected successfully!
📊 Streaming market data for:
   - Nifty 50
   - Bank Nifty
   - Reliance
   - TCS
📈 NSE_INDEX|Nifty 50: ₹24500.50
📈 NSE_INDEX|Nifty Bank: ₹52000.25
📈 NSE_EQ|INE020B01018: ₹2850.75
📈 NSE_EQ|INE467B01029: ₹3850.50
```

### Error Handling
If you see errors like:
- `401 Unauthorized`: Check your access token
- `WebSocket connection failed`: Check your internet connection
- `Invalid mode`: Check the mode parameter

## Troubleshooting

### 1. Token Issues
- Make sure your token is valid and not expired
- Check if you have the right permissions for WebSocket access

### 2. Connection Issues
- Ensure you have a stable internet connection
- Check if your firewall allows WebSocket connections

### 3. Data Issues
- Market data is only available during market hours
- Some instruments might not have live data

## WebSocket Modes

- `ltpc`: Last trade price and time only
- `full`: Complete market data (OHLC, depth, etc.)
- `option_greeks`: Options Greeks data
- `full_d30`: Full data + 30 market level quotes

## Multiple Instrument Subscription

You can subscribe to multiple instruments in one request:

```python
streamer = upstox_client.MarketDataStreamerV3(
    api_client=api_client,
    instrumentKeys=[
        "NSE_INDEX|Nifty 50",
        "NSE_INDEX|Nifty Bank",
        "NSE_EQ|INE020B01018",  # Reliance
        "NSE_EQ|INE467B01029"   # TCS
    ],
    mode="full"
)
```

## Auto-Reconnect

The WebSocket automatically reconnects on connection loss:
- Default retry count: 5
- Default interval: 1 second
- Can be customized with `auto_reconnect()` method

## Security Notes

- Never commit your access token to version control
- Use environment variables for production
- The token in the test files is for demonstration only
