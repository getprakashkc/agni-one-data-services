#!/usr/bin/env python3
"""
Data Service Microservice
Handles WebSocket connections, market data processing, and data distribution
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Callable
from dataclasses import dataclass
from datetime import datetime
import upstox_client
import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    """Market data structure"""
    instrument_key: str
    ltp: float
    ltt: str
    change_percent: float
    ohlc: dict
    timestamp: datetime

class DataService:
    """Core data service for market data management"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)
        
        # Redis for caching
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        
        # WebSocket connections
        self.market_streamer = None
        self.portfolio_streamer = None
        
        # Subscribers
        self.subscribers: List[WebSocket] = []
        
        # Data cache
        self.market_data_cache: Dict[str, MarketData] = {}
    
    def start_market_data_stream(self, instruments: List[str]):
        """Start market data streaming"""
        logger.info(f"Starting market data stream for {len(instruments)} instruments")
        
        self.market_streamer = upstox_client.MarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=instruments,
            mode="full"
        )
        
        # Event handlers
        self.market_streamer.on("open", self._on_market_open)
        self.market_streamer.on("message", self._on_market_message)
        self.market_streamer.on("error", self._on_market_error)
        self.market_streamer.on("close", self._on_market_close)
        
        self.market_streamer.connect()
    
    def start_portfolio_stream(self):
        """Start portfolio data streaming"""
        logger.info("Starting portfolio data stream")
        
        self.portfolio_streamer = upstox_client.PortfolioDataStreamer(
            api_client=self.api_client,
            order_update=True,
            position_update=True,
            holding_update=True,
            gtt_update=True
        )
        
        # Event handlers
        self.portfolio_streamer.on("open", self._on_portfolio_open)
        self.portfolio_streamer.on("message", self._on_portfolio_message)
        self.portfolio_streamer.on("error", self._on_portfolio_error)
        self.portfolio_streamer.on("close", self._on_portfolio_close)
        
        self.portfolio_streamer.connect()
    
    def _on_market_open(self):
        """Handle market data connection open"""
        logger.info("Market data WebSocket connected")
    
    def _on_market_message(self, message):
        """Process market data messages"""
        try:
            if 'feeds' in message:
                for instrument_key, feed_data in message['feeds'].items():
                    if 'fullFeed' in feed_data:
                        full_feed = feed_data['fullFeed']
                        if 'indexFF' in full_feed:
                            index_data = full_feed['indexFF']
                            if 'ltpc' in index_data:
                                ltpc = index_data['ltpc']
                                
                                # Create market data object
                                market_data = MarketData(
                                    instrument_key=instrument_key,
                                    ltp=ltpc.get('ltp', 0),
                                    ltt=ltpc.get('ltt', ''),
                                    change_percent=ltpc.get('cp', 0),
                                    ohlc=index_data.get('marketOHLC', {}),
                                    timestamp=datetime.now()
                                )
                                
                                # Cache the data
                                self.market_data_cache[instrument_key] = market_data
                                self.redis_client.setex(
                                    f"market_data:{instrument_key}",
                                    300,  # 5 minutes TTL
                                    json.dumps(market_data.__dict__, default=str)
                                )
                                
                                # Broadcast to subscribers
                                self._broadcast_to_subscribers({
                                    "type": "market_data",
                                    "data": market_data.__dict__
                                })
                                
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
    
    def _on_portfolio_message(self, message):
        """Process portfolio data messages"""
        try:
            # Cache portfolio data
            self.redis_client.setex(
                "portfolio_data",
                300,  # 5 minutes TTL
                json.dumps(message, default=str)
            )
            
            # Broadcast to subscribers
            self._broadcast_to_subscribers({
                "type": "portfolio_data",
                "data": message
            })
            
        except Exception as e:
            logger.error(f"Error processing portfolio data: {e}")
    
    def _on_market_error(self, error):
        """Handle market data errors"""
        logger.error(f"Market data error: {error}")
    
    def _on_portfolio_error(self, error):
        """Handle portfolio data errors"""
        logger.error(f"Portfolio data error: {error}")
    
    def _on_market_close(self, close_status_code, close_msg):
        """Handle market data connection close"""
        logger.info(f"Market data connection closed: {close_status_code} - {close_msg}")
    
    def _on_portfolio_close(self, close_status_code, close_msg):
        """Handle portfolio connection close"""
        logger.info(f"Portfolio connection closed: {close_status_code} - {close_msg}")
    
    def _on_market_open(self):
        """Handle market data connection open"""
        logger.info("Market data WebSocket connected")
    
    def _on_portfolio_open(self):
        """Handle portfolio connection open"""
        logger.info("Portfolio WebSocket connected")
    
    def _broadcast_to_subscribers(self, message):
        """Broadcast message to all WebSocket subscribers"""
        if self.subscribers:
            message_str = json.dumps(message, default=str)
            for subscriber in self.subscribers[:]:  # Copy list to avoid modification during iteration
                try:
                    asyncio.create_task(subscriber.send_text(message_str))
                except Exception as e:
                    logger.error(f"Error sending to subscriber: {e}")
                    self.subscribers.remove(subscriber)
    
    def add_subscriber(self, websocket: WebSocket):
        """Add a new WebSocket subscriber"""
        self.subscribers.append(websocket)
        logger.info(f"Added subscriber. Total subscribers: {len(self.subscribers)}")
    
    def remove_subscriber(self, websocket: WebSocket):
        """Remove a WebSocket subscriber"""
        if websocket in self.subscribers:
            self.subscribers.remove(websocket)
        logger.info(f"Removed subscriber. Total subscribers: {len(self.subscribers)}")
    
    def get_cached_data(self, instrument_key: str = None):
        """Get cached market data"""
        if instrument_key:
            return self.market_data_cache.get(instrument_key)
        return self.market_data_cache
    
    def stop(self):
        """Stop all streams"""
        if self.market_streamer:
            self.market_streamer.disconnect()
        if self.portfolio_streamer:
            self.portfolio_streamer.disconnect()

# FastAPI application
app = FastAPI(title="Data Service", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global data service instance
data_service = None

@app.on_event("startup")
async def startup_event():
    """Initialize data service on startup"""
    global data_service
    access_token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0WEJNVlAiLCJqdGkiOiI2OGZjOTg0NDZmYzliMzVhNWEwNTBjZjYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzYxMzg0NTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjE0Mjk2MDB9.PTgxNla1ZG9zJETfv4ygrem-p60IDAwC5IQPXKS-KmE"
    
    data_service = DataService(access_token)
    
    # Start market data stream
    instruments = [
        "NSE_INDEX|Nifty 50",
        "NSE_INDEX|Nifty Bank",
        "NSE_EQ|INE020B01018",  # Reliance
        "NSE_EQ|INE467B01029"    # TCS
    ]
    
    data_service.start_market_data_stream(instruments)
    data_service.start_portfolio_stream()
    
    logger.info("Data service started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if data_service:
        data_service.stop()
    logger.info("Data service stopped")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data"""
    await websocket.accept()
    data_service.add_subscriber(websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        data_service.remove_subscriber(websocket)

@app.get("/api/market-data/{instrument_key}")
async def get_market_data(instrument_key: str):
    """Get cached market data for specific instrument"""
    data = data_service.get_cached_data(instrument_key)
    if data:
        return data.__dict__
    return {"error": "No data available"}

@app.get("/api/market-data")
async def get_all_market_data():
    """Get all cached market data"""
    return {k: v.__dict__ for k, v in data_service.get_cached_data().items()}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
