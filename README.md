# Agnidata Trading Services

A comprehensive financial data services platform for trading applications with real-time market data, options chain analysis, and Redis-based caching.

## 🚀 Features

- **Real-time Market Data**: WebSocket streaming for live market data
- **Options Trading**: NIFTY options chain analysis and trading
- **Redis Integration**: High-performance caching and data distribution
- **IST Timezone**: All timestamps in Indian Standard Time
- **Token Management**: Automatic token refresh and validation
- **Microservice Architecture**: Scalable and maintainable services

## 📁 Project Structure

```
agni-one-data-services/
├── src/
│   ├── services/           # Core trading services
│   │   ├── token_service.py
│   │   ├── data_service.py
│   │   ├── trading_service.py
│   │   └── trading_app.py
│   ├── utils/              # Utility functions
│   │   └── ist_utils.py
│   ├── examples/           # Example applications
│   │   ├── redis_trading_app.py
│   │   ├── options_trading_app.py
│   │   ├── futures_trading_app.py
│   │   ├── simple_trading_app.py
│   │   ├── redis_monitor.py
│   │   └── futures_redis_monitor.py
│   └── tests/              # Test suite
│       ├── test_websocket.py
│       ├── test_ist_utils.py
│       ├── test_token_service.py
│       └── test_redis_connection.py
├── docs/                   # Documentation
│   ├── README.md
│   ├── TEST_README.md
│   ├── MICROSERVICE_README.md
│   └── TOKEN_SERVICE_README.md
├── upstox_client/          # Upstox Python SDK
├── requirements.txt
├── test_requirements.txt
└── setup.py
```

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows
.\venv\Scripts\Activate.ps1
# Linux/Mac
source venv/bin/activate

# Install dependencies
pip install -r test_requirements.txt
```

### 2. Start Token Service
```bash
python services/token-service/src/token_service.py
```
Service runs on `http://localhost:8000`

### 3. Run Trading Applications
```bash
# Options trading app
python src/examples/options_trading_app.py

# Redis trading app
python src/examples/redis_trading_app.py

# Simple trading app
python src/examples/simple_trading_app.py
```

### 4. Monitor Redis Data
```bash
# Redis monitor
python src/examples/redis_monitor.py

# Options monitor
python src/examples/futures_redis_monitor.py
```

## 📊 Services

### Token Management Service
- **Endpoint**: `http://localhost:8000`
- **Features**: Automatic token refresh, manual token update, 401 error handling
- **Account**: `agnidata001`

### Data Service
- **WebSocket**: Real-time market data streaming
- **Redis**: High-performance data caching
- **Instruments**: NIFTY 50, NIFTY Bank, Reliance, TCS

### Trading Services
- **Options Trading**: 34 NIFTY options contracts
- **Futures Trading**: NIFTY futures contracts
- **Signal Generation**: Momentum-based trading signals
- **Client Management**: Multi-client subscription system

## 🔧 Configuration

### Redis Configuration
- **Host**: localhost
- **Port**: 6379
- **DB**: 0
- **TTL**: 30 seconds for market data

### Token Configuration
- **Internal API**: `http://192.168.1.206:9000/accounts/agnidata001/token`
- **Account ID**: `agnidata001`
- **TTL**: 24 hours

### Market Hours
- **Open**: 9:15 AM IST
- **Close**: 3:30 PM IST
- **Timezone**: Asia/Kolkata (IST)

## 📈 Trading Applications

### Options Trading App
- **Instruments**: 34 NIFTY options (Call & Put)
- **Strike Range**: 25400 to 26200
- **Features**: Options chain analysis, moneyness calculation
- **Signals**: Options-specific momentum strategy

### Redis Trading App
- **Instruments**: NIFTY 50, NIFTY Bank, Reliance, TCS
- **Features**: Redis caching, client management, signal generation
- **Signals**: Momentum-based trading signals

### Simple Trading App
- **Instruments**: Multiple instruments support
- **Features**: Basic trading signals, WebSocket streaming
- **Signals**: Price change-based signals

## 🔍 Monitoring

### Redis Insight
- **URL**: `http://localhost:8001`
- **Features**: Real-time data visualization, key management
- **Data**: Market data, trading signals, client subscriptions

### Health Checks
- **Token Service**: `GET /health`
- **Token Status**: `GET /token/status`
- **Token Validation**: `GET /token/validate`

## 📚 Documentation

- **[Token Service](docs/TOKEN_SERVICE_README.md)**: Token management and API endpoints
- **[Test Guide](docs/TEST_README.md)**: Testing WebSocket functionality
- **[Microservice Guide](docs/MICROSERVICE_README.md)**: Microservice architecture

## 🎯 API Endpoints

### Token Management
- `GET /health` - Service health check
- `GET /token/status` - Current token status
- `GET /token/validate` - Validate current token
- `POST /token/update` - Update token manually

### Data Service
- WebSocket streaming for real-time market data
- Redis caching for high-performance data access
- Client subscription management

## 🔄 Data Flow

### 1. Token Management
```
Startup → Fetch Token → Validate → Store in Redis → Ready
```

### 2. Market Data
```
Upstox WebSocket → Process Data → Store in Redis → Broadcast to Clients
```

### 3. Trading Signals
```
Market Data → Signal Generation → Store in Redis → Client Notifications
```

## 🚨 Error Handling

### 401 Error Handling
- **Detection**: Automatic 401 error detection
- **Retry Logic**: 3 retries with exponential backoff
- **Token Refresh**: Automatic token refresh on failure
- **Graceful Stop**: Service stops after max retries

### Token Management
- **Startup Fetch**: Automatic token fetch on startup
- **Manual Update**: Manual token update via API
- **Validation**: Token validation with Upstox API
- **Storage**: Redis-based token storage with TTL

## 🎯 Production Features

### High Availability
- **Redis Clustering**: High availability Redis setup
- **Service Monitoring**: Health checks and status monitoring
- **Error Recovery**: Automatic error recovery and retry logic

### Security
- **Token Encryption**: Secure token storage
- **Access Control**: API access control
- **Audit Logging**: Comprehensive audit logging

### Performance
- **Redis Caching**: High-performance data caching
- **WebSocket Streaming**: Real-time data streaming
- **Signal Generation**: Efficient trading signal generation

## 📞 Support

For support and questions:
- **Documentation**: Check the `docs/` directory
- **Examples**: See `src/examples/` for usage examples
- **Tests**: Run `src/tests/` for testing functionality

## 🚀 Next Steps

1. **Deploy to Production**: Set up production environment
2. **Add Monitoring**: Implement comprehensive monitoring
3. **Scale Services**: Scale services for high load
4. **Add Features**: Implement additional trading features
5. **Optimize Performance**: Optimize for high performance
