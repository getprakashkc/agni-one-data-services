# Token Service

Token management service for Upstox API authentication.

## Port
- **8000**

## Endpoints
- `GET /health` - Health check
- `GET /token/status` - Get current token status
- `GET /token/validate` - Validate current token
- `POST /token/update` - Update token manually
- `GET /accounts/{account_id}/token/status` - Get token status for a specific account
- `GET /accounts/{account_id}/token/validate` - Validate token for a specific account
- `POST /accounts/{account_id}/token/update` - Update token for a specific account

## Environment Variables
- `REDIS_HOST` - Redis host (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `INTERNAL_API_BASE_URL` - Internal API base URL
- `INTERNAL_API_ACCOUNT_ID` - Account ID for token fetching
- `INTERNAL_API_ACCOUNT_IDS` - Comma-separated account IDs for multi-account startup fetch (optional)
- `TOKEN_SERVICE_PORT` - Service port (default: 8000)
