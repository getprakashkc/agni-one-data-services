# Trading Application - Microservice Architecture

## 🏗️ Architecture Overview

This trading application uses a microservice architecture with three main services:

```
┌─────────────────────────────────────────────────────────┐
│                    Trading Application                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Data Service   │  │  Trading Service│  │  Trading    │ │
│  │  - WebSocket    │  │  - Strategies   │  │  App        │ │
│  │  - Market Data  │  │  - Risk Mgmt    │  │  - Frontend │ │
│  │  - Caching      │  │  - Analytics    │  │  - API      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Services

### 1. Data Service (Port 8001)
- **Purpose**: Handles WebSocket connections and market data processing
- **Features**:
  - WebSocket management for market data
  - Real-time data processing
  - Redis caching
  - WebSocket broadcasting to subscribers
- **Endpoints**:
  - `GET /api/market-data` - Get all market data
  - `GET /api/market-data/{instrument_key}` - Get specific instrument data
  - `WebSocket /ws` - Real-time data stream

### 2. Trading Service (Port 8002)
- **Purpose**: Executes trading strategies and manages positions
- **Features**:
  - Strategy execution
  - Signal generation
  - Position management
  - Risk management
- **Endpoints**:
  - `GET /api/signals` - Get trading signals
  - `GET /api/positions` - Get current positions
  - `GET /api/market-data/{instrument_key}` - Get market data

### 3. Trading App (Port 8000)
- **Purpose**: Frontend application and API gateway
- **Features**:
  - Web interface
  - API aggregation
  - Real-time updates
  - User interface
- **Endpoints**:
  - `GET /` - Main application
  - `GET /api/market-data` - Market data
  - `GET /api/signals` - Trading signals
  - `WebSocket /ws` - Real-time updates

## 🛠️ Setup and Installation

### Prerequisites
- Docker and Docker Compose
- Python 3.11+
- Redis (included in Docker Compose)

### Quick Start

1. **Clone and setup**:
```bash
git clone <your-repo>
cd agni-one-data-services
```

2. **Start all services**:
```bash
docker-compose up -d
```

3. **Check services**:
```bash
# Data Service
curl http://localhost:8001/api/health

# Trading Service  
curl http://localhost:8002/api/health

# Trading App
curl http://localhost:8000/api/health
```

### Manual Setup (Development)

1. **Install dependencies**:
```bash
pip install -r microservice_requirements.txt
```

2. **Start Redis**:
```bash
redis-server
```

3. **Start services** (in separate terminals):
```bash
# Terminal 1 - Data Service
python data_service.py

# Terminal 2 - Trading Service
python trading_service.py

# Terminal 3 - Trading App
python trading_app.py
```

## 📊 Data Flow

### Market Data Flow
```
Upstox WebSocket → Data Service → Redis Cache → Trading Service → Trading App
```

### Trading Signal Flow
```
Market Data → Strategy Engine → Trading Signals → Order Execution → Portfolio Update
```

## 🔧 Configuration

### Environment Variables
- `REDIS_URL`: Redis connection URL
- `DATA_SERVICE_URL`: Data service URL
- `TRADING_SERVICE_URL`: Trading service URL
- `UPSTOX_ACCESS_TOKEN`: Your Upstox access token

### Service Configuration
- **Data Service**: Handles WebSocket connections and data processing
- **Trading Service**: Executes strategies and manages positions
- **Trading App**: Provides user interface and API aggregation

## 📈 Features

### Real-time Data
- Live market data streaming
- Multiple instrument subscription
- WebSocket-based real-time updates
- Redis caching for performance

### Trading Capabilities
- Strategy execution
- Signal generation
- Position management
- Risk management
- Portfolio tracking

### Scalability
- Microservice architecture
- Independent scaling
- Load balancing
- Fault tolerance

## 🚀 Deployment

### Production Deployment
```bash
# Build and deploy
docker-compose -f docker-compose.prod.yml up -d

# Scale services
docker-compose up -d --scale data-service=3
docker-compose up -d --scale trading-service=2
```

### Monitoring
- Health checks on all services
- Logging and metrics
- Error tracking
- Performance monitoring

## 🔍 API Documentation

### Data Service API
- **Base URL**: `http://localhost:8001`
- **WebSocket**: `ws://localhost:8001/ws`
- **Endpoints**:
  - `GET /api/market-data` - All market data
  - `GET /api/market-data/{instrument_key}` - Specific instrument
  - `GET /api/health` - Health check

### Trading Service API
- **Base URL**: `http://localhost:8002`
- **Endpoints**:
  - `GET /api/signals` - Trading signals
  - `GET /api/positions` - Current positions
  - `GET /api/health` - Health check

### Trading App API
- **Base URL**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/ws`
- **Endpoints**:
  - `GET /` - Main application
  - `GET /api/market-data` - Market data
  - `GET /api/signals` - Trading signals
  - `GET /api/health` - Health check

## 🧪 Testing

### Test Individual Services
```bash
# Test data service
python data_service.py

# Test trading service
python trading_service.py

# Test trading app
python trading_app.py
```

### Test WebSocket Connections
```bash
# Test data service WebSocket
wscat -c ws://localhost:8001/ws

# Test trading app WebSocket
wscat -c ws://localhost:8000/ws
```

## 🔒 Security

### Authentication
- Access token validation
- WebSocket authentication
- API key management

### Data Protection
- Encrypted connections
- Secure data transmission
- Access control

## 📝 Development

### Adding New Strategies
1. Create strategy class in `trading_service.py`
2. Implement signal generation logic
3. Add to strategy registry
4. Test with market data

### Adding New Data Sources
1. Extend `data_service.py`
2. Add new WebSocket connections
3. Implement data processing
4. Update caching logic

### Adding New Features
1. Create new service or extend existing
2. Add API endpoints
3. Update Docker Compose
4. Test integration

## 🚨 Troubleshooting

### Common Issues
- **WebSocket connection failed**: Check access token
- **No market data**: Check market hours
- **Service not responding**: Check health endpoints
- **Redis connection failed**: Check Redis service

### Debug Commands
```bash
# Check service logs
docker-compose logs data-service
docker-compose logs trading-service
docker-compose logs trading-app

# Check service status
docker-compose ps

# Restart services
docker-compose restart
```

## 📚 Next Steps

1. **Add more trading strategies**
2. **Implement order management**
3. **Add user authentication**
4. **Create web dashboard**
5. **Add monitoring and alerting**
6. **Implement backtesting**
7. **Add risk management**
8. **Create mobile app**

This microservice architecture provides a solid foundation for building a production-ready trading application! 🚀
