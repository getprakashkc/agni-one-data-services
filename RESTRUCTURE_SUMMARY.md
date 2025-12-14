# Project Restructure Summary

## ✅ Completed Restructuring

The project has been restructured for Coolify deployment with separate services and watch paths.

## New Structure

```
agni-one-data-services/
├── services/
│   ├── token-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── README.md
│   │   └── src/
│   │       └── token_service.py
│   ├── data-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── README.md
│   │   └── src/
│   │       └── data_service.py
│   ├── trading-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── README.md
│   │   └── src/
│   │       └── trading_service.py
│   └── trading-app/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── README.md
│       └── src/
│           └── trading_app.py
├── shared/
│   ├── upstox_client/      # Upstox Python SDK
│   └── utils/               # Shared utilities (ist_utils.py)
├── coolify.yml              # Updated with separate resources
└── COOLIFY_DEPLOYMENT.md    # Deployment guide
```

## Services Overview

### 1. Token Service (Port 8000)
- **Location**: `services/token-service/`
- **Watch Path**: `services/token-service/**`, `shared/utils/**`
- **Dependencies**: Redis
- **Purpose**: Token management and validation

### 2. Data Service (Port 8001)
- **Location**: `services/data-service/`
- **Watch Path**: `services/data-service/**`, `shared/**`
- **Dependencies**: Redis, Token Service (for token access)
- **Purpose**: Market data streaming, WebSocket, OHLC subscriptions

### 3. Trading Service (Port 8002)
- **Location**: `services/trading-service/`
- **Watch Path**: `services/trading-service/**`, `shared/utils/**`
- **Dependencies**: Data Service
- **Purpose**: Trading strategy execution, signal generation

### 4. Trading App (Port 8003)
- **Location**: `services/trading-app/`
- **Watch Path**: `services/trading-app/**`, `templates/**`, `shared/utils/**`
- **Dependencies**: Data Service, Trading Service
- **Purpose**: Frontend application, API aggregation

## Key Changes

### 1. Service Isolation
- Each service in its own folder
- Service-specific Dockerfiles
- Service-specific requirements.txt
- Independent deployment capability

### 2. Shared Code
- `shared/upstox_client/` - Upstox SDK (used by data-service)
- `shared/utils/` - Common utilities (ist_utils.py)

### 3. Environment Variables
- All services use environment variables for configuration
- Redis connection configurable
- Service URLs configurable
- Ports configurable

### 4. Import Paths
- Services import from `shared/` using sys.path
- Updated to work with new structure
- Maintains backward compatibility

## Coolify Configuration

### Watch Paths (Configure in Coolify UI)

**Token Service:**
- `services/token-service/**`
- `shared/utils/**`

**Data Service:**
- `services/data-service/**`
- `shared/upstox_client/**`
- `shared/utils/**`

**Trading Service:**
- `services/trading-service/**`
- `shared/utils/**`

**Trading App:**
- `services/trading-app/**`
- `templates/**`
- `shared/utils/**`

### Benefits

✅ **Selective Redeployment** - Only changed services rebuild  
✅ **Faster CI/CD** - Smaller build contexts  
✅ **Better Resource Management** - Independent scaling  
✅ **Clear Separation** - Easier to understand and maintain  
✅ **Watch Path Efficiency** - Automatic detection of changes  

## Migration Notes

### Original Structure (Still Available)
- `src/services/` - Original service files (preserved)
- Can be removed after verification

### New Structure (Active)
- `services/` - New service structure
- `shared/` - Shared code

## Next Steps

1. **Test Each Service Locally:**
   ```bash
   # Test token-service
   cd services/token-service
   docker build -f Dockerfile -t token-service ..
   docker run -p 8000:8000 token-service
   
   # Test data-service
   cd services/data-service
   docker build -f Dockerfile -t data-service ..
   docker run -p 8001:8001 data-service
   ```

2. **Configure in Coolify:**
   - Create separate resources for each service
   - Set watch paths as documented
   - Configure environment variables
   - Set up health checks

3. **Verify Deployments:**
   - Test each service independently
   - Verify service-to-service communication
   - Test watch path triggers

## Files Created/Modified

### Created:
- `services/token-service/` (complete)
- `services/data-service/` (complete)
- `services/trading-service/` (complete)
- `services/trading-app/` (complete)
- `shared/utils/` (ist_utils.py)
- `shared/upstox_client/` (copied)
- `coolify.yml` (updated)
- `COOLIFY_DEPLOYMENT.md` (new)
- `RESTRUCTURE_SUMMARY.md` (this file)

### Modified:
- Service files updated with new import paths
- Environment variable support added
- Port configuration via environment variables

## Backward Compatibility

- Original `src/services/` structure preserved
- Can run both old and new structure during transition
- Gradual migration possible
