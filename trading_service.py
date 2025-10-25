#!/usr/bin/env python3
"""
Trading Service Microservice
Consumes market data and executes trading strategies
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import websockets
import requests
from fastapi import FastAPI, HTTPException
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TradingSignal:
    """Trading signal structure"""
    instrument_key: str
    signal_type: str  # BUY, SELL, HOLD
    price: float
    quantity: int
    strategy: str
    timestamp: datetime
    confidence: float

@dataclass
class Position:
    """Position structure"""
    instrument_key: str
    quantity: int
    avg_price: float
    current_price: float
    pnl: float
    timestamp: datetime

class TradingService:
    """Core trading service for strategy execution"""
    
    def __init__(self, data_service_url: str = "http://localhost:8001"):
        self.data_service_url = data_service_url
        self.positions: Dict[str, Position] = {}
        self.signals: List[TradingSignal] = []
        self.websocket = None
        self.running = False
    
    async def connect_to_data_service(self):
        """Connect to data service WebSocket"""
        try:
            self.websocket = await websockets.connect(f"{self.data_service_url.replace('http', 'ws')}/ws")
            logger.info("Connected to data service")
            self.running = True
            
            # Start message processing
            asyncio.create_task(self._process_messages())
            
        except Exception as e:
            logger.error(f"Failed to connect to data service: {e}")
    
    async def _process_messages(self):
        """Process incoming market data messages"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data.get("type") == "market_data":
                    await self._process_market_data(data["data"])
                elif data.get("type") == "portfolio_data":
                    await self._process_portfolio_data(data["data"])
                    
        except Exception as e:
            logger.error(f"Error processing messages: {e}")
    
    async def _process_market_data(self, market_data: dict):
        """Process market data and generate trading signals"""
        try:
            instrument_key = market_data["instrument_key"]
            ltp = market_data["ltp"]
            change_percent = market_data["change_percent"]
            
            # Simple trading strategy
            signal = await self._generate_trading_signal(instrument_key, ltp, change_percent)
            
            if signal:
                self.signals.append(signal)
                logger.info(f"Generated signal: {signal.signal_type} {instrument_key} at {ltp}")
                
                # Execute signal (in real implementation, this would call order service)
                await self._execute_signal(signal)
                
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
    
    async def _process_portfolio_data(self, portfolio_data: dict):
        """Process portfolio updates"""
        try:
            logger.info(f"Portfolio update received: {len(portfolio_data)} items")
            # Update positions based on portfolio data
            # This would update self.positions
            
        except Exception as e:
            logger.error(f"Error processing portfolio data: {e}")
    
    async def _generate_trading_signal(self, instrument_key: str, ltp: float, change_percent: float) -> Optional[TradingSignal]:
        """Generate trading signals based on market data"""
        try:
            # Simple momentum strategy
            if change_percent > 2.0:  # Strong positive momentum
                return TradingSignal(
                    instrument_key=instrument_key,
                    signal_type="BUY",
                    price=ltp,
                    quantity=1,
                    strategy="momentum",
                    timestamp=datetime.now(),
                    confidence=0.8
                )
            elif change_percent < -2.0:  # Strong negative momentum
                return TradingSignal(
                    instrument_key=instrument_key,
                    signal_type="SELL",
                    price=ltp,
                    quantity=1,
                    strategy="momentum",
                    timestamp=datetime.now(),
                    confidence=0.8
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating trading signal: {e}")
            return None
    
    async def _execute_signal(self, signal: TradingSignal):
        """Execute trading signal (placeholder for order service integration)"""
        try:
            logger.info(f"Executing signal: {signal.signal_type} {signal.instrument_key}")
            
            # In real implementation, this would:
            # 1. Call order service to place order
            # 2. Update position tracking
            # 3. Send notifications
            
            # For now, just log the signal
            logger.info(f"Signal executed: {signal.signal_type} {signal.quantity} shares of {signal.instrument_key}")
            
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
    
    async def get_market_data(self, instrument_key: str = None):
        """Get market data from data service"""
        try:
            if instrument_key:
                response = requests.get(f"{self.data_service_url}/api/market-data/{instrument_key}")
            else:
                response = requests.get(f"{self.data_service_url}/api/market-data")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get market data: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None
    
    async def stop(self):
        """Stop the trading service"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Trading service stopped")

# FastAPI application
app = FastAPI(title="Trading Service", version="1.0.0")

# Global trading service instance
trading_service = None

@app.on_event("startup")
async def startup_event():
    """Initialize trading service on startup"""
    global trading_service
    trading_service = TradingService()
    await trading_service.connect_to_data_service()
    logger.info("Trading service started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if trading_service:
        await trading_service.stop()
    logger.info("Trading service stopped")

@app.get("/api/signals")
async def get_signals():
    """Get recent trading signals"""
    if trading_service:
        return [signal.__dict__ for signal in trading_service.signals[-10:]]  # Last 10 signals
    return []

@app.get("/api/positions")
async def get_positions():
    """Get current positions"""
    if trading_service:
        return [position.__dict__ for position in trading_service.positions.values()]
    return []

@app.get("/api/market-data/{instrument_key}")
async def get_market_data(instrument_key: str):
    """Get market data for specific instrument"""
    if trading_service:
        data = await trading_service.get_market_data(instrument_key)
        if data:
            return data
        else:
            raise HTTPException(status_code=404, detail="No data available")
    raise HTTPException(status_code=500, detail="Trading service not available")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
