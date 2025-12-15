# Data Service

Market data streaming service with WebSocket support and OHLC subscriptions.

## Port
- **8001**

## Endpoints

### REST API
- `GET /api/health` - Health check
- `GET /api/market-data` - Get all cached market data
- `GET /api/market-data/{instrument_key}` - Get specific instrument data
- `GET /api/subscriptions` - Get active WebSocket subscriptions
- `GET /api/instruments` - Get list of currently subscribed instruments
- `POST /api/instruments/subscribe` - Subscribe to new instruments dynamically
- `POST /api/instruments/unsubscribe` - Unsubscribe from instruments dynamically

### WebSocket
- `WebSocket /ws` - Real-time market data stream

## Environment Variables
- `REDIS_HOST` - Redis host (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `REDIS_PASSWORD` - Redis password (optional)
- `UPSTOX_ACCESS_TOKEN` - Upstox access token (or fetched from Redis)
- `DATA_SERVICE_PORT` - Service port (default: 8001)
- `INSTRUMENTS` - Comma-separated list of default instruments (e.g., "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank,BSE_INDEX|SENSEX")

## Features
- Real-time market data streaming
- Selective WebSocket subscriptions
- OHLC candle subscriptions with historical data
- Redis caching
