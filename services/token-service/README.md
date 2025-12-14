# Token Service

Token management service for Upstox API authentication.

## Port
- **8000**

## Endpoints
- `GET /health` - Health check
- `GET /token/status` - Get current token status
- `GET /token/validate` - Validate current token
- `POST /token/update` - Update token manually

## Environment Variables
- `REDIS_HOST` - Redis host (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `INTERNAL_API_BASE_URL` - Internal API base URL
- `INTERNAL_API_ACCOUNT_ID` - Account ID for token fetching
- `TOKEN_SERVICE_PORT` - Service port (default: 8000)
