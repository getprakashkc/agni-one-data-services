# Data Service

Market data streaming service with WebSocket support and OHLC subscriptions.

## Port
- **8001**

## Endpoints
- `GET /api/health` - Health check
- `GET /api/market-data` - Get all cached market data
- `GET /api/market-data/{instrument_key}` - Get specific instrument data
- `GET /api/subscriptions` - Get active WebSocket subscriptions
- `WebSocket /ws` - Real-time market data stream

## Environment Variables
- `REDIS_HOST` - Redis host (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `UPSTOX_ACCESS_TOKEN` - Upstox access token (or fetched from Redis)
- `DATA_SERVICE_PORT` - Service port (default: 8001)

## Features
- Real-time market data streaming
- Selective WebSocket subscriptions
- OHLC candle subscriptions with historical data
- Redis caching
