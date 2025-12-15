# Quick Start: Coolify Deployment

## 🚀 Quick Setup Guide

### Step 1: Create Resources in Coolify

For each service, create a new resource in Coolify:

#### Token Service
1. **Name**: `token-service`
2. **Build Pack**: Dockerfile
3. **Dockerfile Path**: `services/token-service/Dockerfile`
4. **Build Context**: `.` (project root)
5. **Port**: `8000`
6. **Watch Paths**:
   - `services/token-service/**`
   - `shared/utils/**`

#### Data Service
1. **Name**: `data-service`
2. **Build Pack**: Dockerfile
3. **Dockerfile Path**: `services/data-service/Dockerfile`
4. **Build Context**: `.` (project root)
5. **Port**: `8001`
6. **Watch Paths**:
   - `services/data-service/**`
   - `shared/upstox_client/**`
   - `shared/utils/**`

#### Trading Service
1. **Name**: `trading-service`
2. **Build Pack**: Dockerfile
3. **Dockerfile Path**: `services/trading-service/Dockerfile`
4. **Build Context**: `.` (project root)
5. **Port**: `8002`
6. **Watch Paths**:
   - `services/trading-service/**`
   - `shared/utils/**`

#### Trading App
1. **Name**: `trading-app`
2. **Build Pack**: Dockerfile
3. **Dockerfile Path**: `services/trading-app/Dockerfile`
4. **Build Context**: `.` (project root)
5. **Port**: `8003`
6. **Watch Paths**:
   - `services/trading-app/**`
   - `templates/**`
   - `shared/utils/**`

### Step 2: Set Environment Variables

#### Token Service
```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<your-redis-password-if-set>
INTERNAL_API_BASE_URL=http://192.168.1.206:9000
INTERNAL_API_ACCOUNT_ID=agnidata001
TOKEN_SERVICE_PORT=8000
```

#### Data Service
```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<your-redis-password-if-set>
DATA_SERVICE_PORT=8001
INSTRUMENTS=NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank,BSE_INDEX|SENSEX
# UPSTOX_ACCESS_TOKEN will be fetched from Redis (set by token-service)
```

#### Trading Service
```
DATA_SERVICE_URL=http://data-service:8001
TRADING_SERVICE_PORT=8002
```

#### Trading App
```
DATA_SERVICE_URL=http://data-service:8001
TRADING_SERVICE_URL=http://trading-service:8002
TRADING_APP_PORT=8003
```

### Step 3: Deploy Order

1. Deploy **Redis** first
2. Deploy **Token Service** (provides tokens)
3. Deploy **Data Service** (requires token)
4. Deploy **Trading Service** (requires data service)
5. Deploy **Trading App** (requires both services)

### Step 4: Verify

Check health endpoints:
- Token Service: `http://your-domain:8000/health`
- Data Service: `http://your-domain:8001/api/health`
- Trading Service: `http://your-domain:8002/api/health`
- Trading App: `http://your-domain:8003/api/health`

## 📋 Watch Paths Summary

| Service | Watch Paths |
|---------|-------------|
| token-service | `services/token-service/**`, `shared/utils/**` |
| data-service | `services/data-service/**`, `shared/**` |
| trading-service | `services/trading-service/**`, `shared/utils/**` |
| trading-app | `services/trading-app/**`, `templates/**`, `shared/utils/**` |

## 🔄 How Watch Paths Work

- **Change in `services/token-service/src/token_service.py`** → Only `token-service` redeploys
- **Change in `shared/utils/ist_utils.py`** → All services redeploy (they all use it)
- **Change in `shared/upstox_client/`** → Only `data-service` redeploys (only it uses it)
- **Change in `templates/index.html`** → Only `trading-app` redeploys

## ✅ Benefits

- **Fast Deployments**: Only rebuild what changed
- **Independent Scaling**: Scale services based on load
- **Clear Separation**: Easy to understand and maintain
- **Efficient CI/CD**: Automatic redeployment on changes
