# Trading App

Frontend trading application that aggregates data from data service and trading service.

## Port
- **8003**

## Endpoints
- `GET /` - Root endpoint
- `GET /api/health` - Health check
- `GET /api/market-data` - Get market data
- `GET /api/signals` - Get trading signals
- `WebSocket /ws` - Real-time updates

## Environment Variables
- `DATA_SERVICE_URL` - Data service URL (default: http://localhost:8001)
- `TRADING_SERVICE_URL` - Trading service URL (default: http://localhost:8002)
- `TRADING_APP_PORT` - Service port (default: 8003)
