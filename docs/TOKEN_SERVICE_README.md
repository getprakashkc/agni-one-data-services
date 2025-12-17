# Token Management Service

Simple token management service for Upstox API tokens with automatic startup fetch and manual update capabilities.

## 🚀 Features

- **Startup Token Fetch**: Automatically fetches token from internal API on startup
- **Manual Token Update**: REST API endpoint to update token manually
- **Token Validation**: Validates tokens with Upstox API
- **401 Error Handling**: Retry logic with exponential backoff
- **Redis Storage**: Stores tokens in Redis with TTL
- **IST Timezone**: All timestamps in Indian Standard Time

## 📋 API Endpoints

### 1. Health Check
```
GET /health
```
Returns service health status.

### 2. Token Status
```
GET /token/status
```
Returns current token information and status.

### 2b. Token Status (per account)
```
GET /accounts/{account_id}/token/status
```
Returns token information for a specific `account_id`.

### 3. Token Validation
```
GET /token/validate
```
Validates current token with Upstox API.

### 3b. Token Validation (per account)
```
GET /accounts/{account_id}/token/validate
```
Validates the token for a specific `account_id` with Upstox API.

### 4. Manual Token Update
```
POST /token/update
```
Update token manually with new token.

### 4b. Manual Token Update (per account)
```
POST /accounts/{account_id}/token/update
```
Update token manually for a specific `account_id`.

**Request Body:**
```json
{
  "access_token": "your_new_token_here",
  "expires_at": "2025-10-26T23:59:59Z",
  "account_id": "agnidata001"
}
```

## 🔧 Configuration

### Internal API
- **Base URL Env**: `TOKEN_REFRESH_SERVICE_URL`
- **Example**: `TOKEN_REFRESH_SERVICE_URL=http://agni-upstox-auth-server:8000`
- **Token Fetch Endpoint**: `GET {TOKEN_REFRESH_SERVICE_URL}/accounts/{account_id}/token`
- **Token Refresh Endpoint**: `POST {TOKEN_REFRESH_SERVICE_URL}/accounts/{account_id}/refresh`
- **Response**: JSON with `access_token`, `expires_at`, etc.

### Multiple Accounts
- **Env**: `UPSTOX_ACCOUNT_IDS`
- **Example**: `UPSTOX_ACCOUNT_IDS=agnidata001,agnidata002`
- Token-service will fetch and store tokens for **each account** on startup.

### Redis Configuration
- **Host**: localhost
- **Port**: 6379
- **DB**: 0
- **TTL**: 24 hours (86400 seconds)

## 🚀 Usage

### 1. Start Token Service
```bash
python token_service.py
```
Service runs on `http://localhost:8000`

### 2. Test Token Service
```bash
python test_token_service.py
```

### 3. Update Token Manually
```bash
curl -X POST "http://localhost:8000/token/update" \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "your_new_token_here",
    "expires_at": "2025-10-26T23:59:59Z",
    "account_id": "agnidata001"
  }'
```

## 🔄 Token Flow

### Startup Flow
1. **Service Starts** → Calls internal API
2. **Token Fetched** → Validates with Upstox API
3. **Token Stored** → Stores in Redis with TTL
4. **Service Ready** → All services can use token

### Manual Update Flow
1. **POST /token/update** → You provide new token
2. **Token Validation** → Validates with Upstox API
3. **Token Stored** → Updates Redis
4. **Services Updated** → All services use new token

### 401 Error Handling
1. **401 Detected** → Upstox API returns 401
2. **Retry Logic** → 3 retries with exponential backoff
3. **Token Refresh** → Tries to get fresh token
4. **Success/Failure** → Continues or stops gracefully

## 📊 Redis Keys

- `upstox_access_token` - Current access token
- `token_info` - Full token information with metadata

### Per-account Redis Keys (multi-account)
- `upstox_access_token:{account_id}` - Access token for that account
- `token_info:{account_id}` - Token info/metadata for that account

**Backward compatibility:** for the default account (`INTERNAL_API_ACCOUNT_ID`), token-service also continues to write `upstox_access_token` and `token_info`.

## 🎯 Integration with Trading Services

### 1. Get Token from Redis
```python
import redis
redis_client = redis.Redis()
token = redis_client.get("upstox_access_token")
```

### 2. Use Token in Upstox Client
```python
import upstox_client
configuration = upstox_client.Configuration()
configuration.access_token = token
api_client = upstox_client.ApiClient(configuration)
```

### 3. Handle 401 Errors
```python
if response.status_code == 401:
    # Token is invalid, get new token from Redis
    new_token = redis_client.get("upstox_access_token")
    if new_token:
        # Update configuration and retry
        configuration.access_token = new_token
    else:
        # No valid token available, stop service
        stop_service()
```

## 🔍 Monitoring

### Health Check
- **Endpoint**: `GET /health`
- **Returns**: Service status, token availability, current time

### Token Status
- **Endpoint**: `GET /token/status`
- **Returns**: Token information, expiry, source, etc.

### Token Validation
- **Endpoint**: `GET /token/validate`
- **Returns**: Token validity status with Upstox API

## 🚨 Error Handling

### 1. Startup Failures
- **Internal API Down**: Service starts but no token available
- **Network Issues**: Retry logic with exponential backoff
- **Invalid Response**: Log error and continue without token

### 2. 401 Error Handling
- **Detect 401**: When Upstox API returns 401
- **Retry Logic**: 3 retries with exponential backoff
- **Token Refresh**: Try to get fresh token from internal API
- **Graceful Stop**: Stop service after max retries

### 3. Manual Update Failures
- **Invalid Token**: Validation fails with Upstox API
- **Network Issues**: Request timeout or connection errors
- **Redis Errors**: Failed to store token in Redis

## 📈 Production Considerations

### 1. High Availability
- **Multiple Instances**: Run multiple token service instances
- **Load Balancer**: Use load balancer for token service
- **Health Checks**: Monitor token service health

### 2. Security
- **Token Encryption**: Encrypt tokens in Redis
- **Access Control**: Restrict access to token endpoints
- **Audit Logging**: Log all token operations

### 3. Monitoring
- **Token Expiry**: Monitor token expiry time
- **Service Health**: Monitor token service health
- **API Calls**: Monitor Upstox API call success rates

## 🎯 Next Steps

1. **Test Token Service**: Run and test all endpoints
2. **Integrate with Trading Services**: Update trading services to use token service
3. **Add Monitoring**: Add comprehensive monitoring and alerting
4. **Production Deployment**: Deploy to production environment
5. **Scheduled Refresh**: Add scheduled token refresh at 8:00 AM IST
