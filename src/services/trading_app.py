#!/usr/bin/env python3
"""
Trading Application
Frontend application that consumes data and trading services
"""

import asyncio
import json
import logging
from typing import Dict, List
from datetime import datetime
import websockets
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingApp:
    """Main trading application"""
    
    def __init__(self, data_service_url: str, trading_service_url: str):
        self.data_service_url = data_service_url
        self.trading_service_url = trading_service_url
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
                logger.info(f"Received data: {data.get('type', 'unknown')}")
                
        except Exception as e:
            logger.error(f"Error processing messages: {e}")
    
    async def get_market_data(self):
        """Get market data from data service"""
        try:
            response = requests.get(f"{self.data_service_url}/api/market-data")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None
    
    async def get_trading_signals(self):
        """Get trading signals from trading service"""
        try:
            response = requests.get(f"{self.trading_service_url}/api/signals")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error getting trading signals: {e}")
            return None
    
    async def stop(self):
        """Stop the application"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Trading app stopped")

# FastAPI application
app = FastAPI(title="Trading Application", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="templates")

# Global app instance
trading_app = None

@app.on_event("startup")
async def startup_event():
    """Initialize trading app on startup"""
    global trading_app
    trading_app = TradingApp(
        data_service_url="http://localhost:8001",
        trading_service_url="http://localhost:8002"
    )
    await trading_app.connect_to_data_service()
    logger.info("Trading app started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if trading_app:
        await trading_app.stop()
    logger.info("Trading app stopped")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Trading Application", "status": "running"}

@app.get("/api/market-data")
async def get_market_data():
    """Get market data"""
    if trading_app:
        data = await trading_app.get_market_data()
        if data:
            return data
        else:
            return {"error": "No data available"}
    return {"error": "App not available"}

@app.get("/api/signals")
async def get_signals():
    """Get trading signals"""
    if trading_app:
        signals = await trading_app.get_trading_signals()
        if signals:
            return signals
        else:
            return {"error": "No signals available"}
    return {"error": "App not available"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
