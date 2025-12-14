# Trading Service

Trading strategy execution service that consumes market data and generates trading signals.

## Port
- **8002**

## Endpoints
- `GET /api/health` - Health check
- `GET /api/signals` - Get recent trading signals
- `GET /api/positions` - Get current positions
- `GET /api/market-data/{instrument_key}` - Get market data for specific instrument

## Environment Variables
- `DATA_SERVICE_URL` - Data service URL (default: http://localhost:8001)
- `TRADING_SERVICE_PORT` - Service port (default: 8002)
