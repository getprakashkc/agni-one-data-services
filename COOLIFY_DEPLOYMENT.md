# Coolify Deployment Guide

This guide explains how to deploy each service as separate resources in Coolify with watch paths for efficient CI/CD.

## Project Structure

```
agni-one-data-services/
├── services/
│   ├── token-service/     # Watch Path: services/token-service/**
│   ├── data-service/       # Watch Path: services/data-service/**
│   ├── trading-service/    # Watch Path: services/trading-service/**
│   └── trading-app/        # Watch Path: services/trading-app/**
├── shared/
│   ├── upstox_client/      # Watch Path: shared/**
│   └── utils/               # Watch Path: shared/**
└── templates/              # Watch Path: templates/**
```

## Setting Up Services in Coolify

### 1. Token Service

**Resource Configuration:**
- **Name**: `token-service`
- **Port**: `8000`
- **Dockerfile Path**: `services/token-service/Dockerfile`
- **Build Context**: `.` (project root)
- **Watch Path**: `services/token-service/**`
- **Watch Path**: `shared/**` (for shared utilities)

**Environment Variables:**
```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<your-redis-password-if-set>
INTERNAL_API_BASE_URL=http://192.168.1.206:9000
INTERNAL_API_ACCOUNT_ID=agnidata001
TOKEN_SERVICE_PORT=8000
```

**Health Check:**
- Endpoint: `http://localhost:8000/health`

### 2. Data Service

**Resource Configuration:**
- **Name**: `data-service`
- **Port**: `8001`
- **Dockerfile Path**: `services/data-service/Dockerfile`
- **Build Context**: `.` (project root)
- **Watch Path**: `services/data-service/**`
- **Watch Path**: `shared/**` (for shared code)

**Environment Variables:**
```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<your-redis-password-if-set>
UPSTOX_ACCESS_TOKEN=<token-from-redis-or-env>
DATA_SERVICE_PORT=8001
```

**Health Check:**
- Endpoint: `http://localhost:8001/api/health`

**Dependencies:**
- Requires `token-service` to be running (for token access)
- Requires `redis` to be running

### 3. Trading Service

**Resource Configuration:**
- **Name**: `trading-service`
- **Port**: `8002`
- **Dockerfile Path**: `services/trading-service/Dockerfile`
- **Build Context**: `.` (project root)
- **Watch Path**: `services/trading-service/**`
- **Watch Path**: `shared/**` (for shared utilities)

**Environment Variables:**
```
DATA_SERVICE_URL=http://data-service:8001
TRADING_SERVICE_PORT=8002
```

**Health Check:**
- Endpoint: `http://localhost:8002/api/health`

**Dependencies:**
- Requires `data-service` to be running

### 4. Trading App

**Resource Configuration:**
- **Name**: `trading-app`
- **Port**: `8003`
- **Dockerfile Path**: `services/trading-app/Dockerfile`
- **Build Context**: `.` (project root)
- **Watch Path**: `services/trading-app/**`
- **Watch Path**: `templates/**` (for frontend templates)
- **Watch Path**: `shared/**` (for shared utilities)

**Environment Variables:**
```
DATA_SERVICE_URL=http://data-service:8001
TRADING_SERVICE_URL=http://trading-service:8002
TRADING_APP_PORT=8003
```

**Health Check:**
- Endpoint: `http://localhost:8003/api/health`

**Dependencies:**
- Requires `data-service` to be running
- Requires `trading-service` to be running

### 5. Redis (Shared Resource)

**Resource Configuration:**
- **Name**: `redis`
- **Port**: `6379`
- **Image**: `redis:7-alpine`
- **Watch Path**: `shared/**` (if Redis config changes)

**Environment Variables:**
```
REDIS_PASSWORD=<optional-password>
```

## Watch Paths Configuration

In Coolify, configure watch paths for each service:

### Token Service Watch Paths:
- `services/token-service/**`
- `shared/utils/**`

### Data Service Watch Paths:
- `services/data-service/**`
- `shared/upstox_client/**`
- `shared/utils/**`

### Trading Service Watch Paths:
- `services/trading-service/**`
- `shared/utils/**`

### Trading App Watch Paths:
- `services/trading-app/**`
- `templates/**`
- `shared/utils/**`

### Shared Code Changes:
When code in `shared/**` changes, all services should be redeployed:
- `shared/upstox_client/**` → Redeploy `data-service`
- `shared/utils/**` → Redeploy all services

## Deployment Order

1. **Redis** - Start first (required by all services)
2. **Token Service** - Provides authentication tokens
3. **Data Service** - Requires token service
4. **Trading Service** - Requires data service
5. **Trading App** - Requires both data and trading services

## Service URLs

After deployment:
- Token Service: `http://your-domain:8000`
- Data Service: `http://your-domain:8001`
- Trading Service: `http://your-domain:8002`
- Trading App: `http://your-domain:8003`

## Internal Service Communication

Services communicate using internal Docker network names:
- `data-service:8001` (from trading-service or trading-app)
- `trading-service:8002` (from trading-app)
- `redis:6379` (from all services)

## Benefits of This Structure

✅ **Independent Deployments** - Only redeploy what changed  
✅ **Watch Paths** - Automatic redeployment on code changes  
✅ **Clear Separation** - Each service in its own folder  
✅ **Better Scaling** - Scale services independently  
✅ **Easier Debugging** - Isolated logs and resources per service  
✅ **Resource Management** - Allocate resources per service needs  

## Example: Deploying Only Token Service Changes

If you modify `services/token-service/src/token_service.py`:
1. Coolify detects change via watch path `services/token-service/**`
2. Only `token-service` resource rebuilds and redeploys
3. Other services continue running unaffected
4. Fast deployment (~2-3 minutes vs 10+ minutes for all services)

## Example: Shared Code Change

If you modify `shared/utils/ist_utils.py`:
1. Coolify detects change via watch path `shared/**`
2. All services that use shared utils are redeployed
3. Services rebuild with updated shared code
4. Coordinated deployment ensures compatibility
