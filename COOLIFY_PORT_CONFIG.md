# Port Configuration in Coolify

## ✅ Yes, Ports are Fully Configurable in Coolify!

In Coolify, you can configure ports in **two ways**:

### Method 1: Environment Variables (Container Port)

Set the port the service listens on via environment variable in Coolify UI:
- `TOKEN_SERVICE_PORT=8000` (or any port you want)
- `DATA_SERVICE_PORT=8001` (or any port you want)
- `TRADING_SERVICE_PORT=8002` (or any port you want)
- `TRADING_APP_PORT=8003` (or any port you want)

The Dockerfiles use these environment variables with defaults, so the service will listen on the port you specify.

### Method 2: Coolify Port Mapping (Public Port)

In Coolify resource settings → **Ports** section:
1. Configure **Port Mapping**:
   - **Container Port**: The port the service listens on (from env var or default)
   - **Public Port**: The port exposed to the internet (can be different!)
   - **Protocol**: `HTTP` or `HTTPS`

### Example: Custom Ports

**Token Service:**
- Environment Variable: `TOKEN_SERVICE_PORT=9000` (service listens on 9000)
- Coolify Port Mapping: Container `9000` → Public `80` (exposed as port 80)

**Data Service:**
- Environment Variable: `DATA_SERVICE_PORT=9001` (service listens on 9001)
- Coolify Port Mapping: Container `9001` → Public `443` (exposed as HTTPS port 443)

### Benefits

✅ **Flexible Port Assignment** - Use any ports you want  
✅ **No Code Changes** - Ports configured in Coolify UI  
✅ **Easy Updates** - Change ports without rebuilding  
✅ **Multiple Environments** - Different ports per environment  
✅ **Port Separation** - Container port ≠ Public port  

## How It Works

1. **Container Port** (from env var): What port the service listens on inside the container
2. **Public Port** (Coolify UI): What port is exposed to the internet
3. **Port Mapping**: Coolify maps Public Port → Container Port

## Recommended Setup

**For simplicity, use default ports:**
- Token Service: `8000` (both container and public)
- Data Service: `8001` (both container and public)
- Trading Service: `8002` (both container and public)
- Trading App: `8003` (both container and public)

**Or customize as needed:**
- Set environment variables for container ports
- Configure public ports in Coolify UI
- Use different ports for different environments (dev/staging/prod)

## Dockerfile EXPOSE Directive

The `EXPOSE` directive in Dockerfiles is just **documentation**. It doesn't actually publish the port. Coolify handles all port mapping through its UI configuration.
