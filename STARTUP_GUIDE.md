# 🚀 Startup Guide - Agnidata Trading Services

## Quick Start

### 1. Activate Virtual Environment
```bash
.\venv\Scripts\Activate.ps1
```

### 2. Start Token Service (Required First)
```bash
python src/services/token_service.py
```
**Wait for:** `✅ Token service started successfully`

### 3. Start Trading Application
```bash
# Choose one:
python src/examples/options_trading_app.py    # NIFTY Options
python src/examples/redis_trading_app.py      # General Trading
python src/examples/simple_trading_app.py    # Basic Trading
```

### 4. Monitor (Optional)
```bash
python src/examples/redis_monitor.py
```

## 🔧 Service URLs

- **Token Service:** http://localhost:8000
- **Redis Insight:** http://localhost:8001

## 📋 API Endpoints

- `GET /health` - Service health check
- `GET /token/status` - Token status
- `GET /token/validate` - Validate token
- `POST /token/update` - Update token manually

## 🎯 Recommended Startup Sequence

### Terminal 1: Token Service
```bash
python src/services/token_service.py
```

### Terminal 2: Trading App
```bash
python src/examples/options_trading_app.py
```

### Terminal 3: Monitor (Optional)
```bash
python src/examples/redis_monitor.py
```

## 🚨 Troubleshooting

### If Token Service Fails:
```bash
# Check Redis connection
python src/tests/test_redis_connection.py

# Check IST utilities
python src/tests/test_ist_utils.py
```

### If Trading App Fails:
```bash
# Test WebSocket
python src/tests/test_websocket.py

# Test token service
python src/tests/test_token_service.py
```

## 📊 What You'll See

### Token Service Output:
```
🚀 Starting Token Management Service
✅ Token service started successfully
🔄 Fetching token on startup...
✅ Token fetched successfully on startup
```

### Trading App Output:
```
🚀 Starting NIFTY Options Trading Application
📊 Trading 34 NIFTY Options (Call & Put options)
🕐 Current IST Time: 2025-10-25 16:30:12 IST
📈 Market Status: OPEN
✅ Connected to Redis successfully
```

## 🛑 Stop Services

Press `Ctrl+C` in each terminal to stop services.

## 📞 Support

- **Documentation:** Check `docs/` directory
- **Examples:** See `src/examples/` for usage examples
- **Tests:** Run `src/tests/` for testing functionality
