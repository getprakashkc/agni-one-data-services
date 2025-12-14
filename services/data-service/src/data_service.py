#!/usr/bin/env python3
"""
Data Service Microservice
Handles WebSocket connections, market data processing, and data distribution
"""

import sys
import os
# Add shared code to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'upstox_client'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'utils'))

import asyncio
import json
import time
import logging
import uuid
from typing import Dict, List, Callable, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager
import upstox_client
import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
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

@dataclass
class OHLCCandle:
    """OHLC candle structure"""
    instrument_key: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: int
    candle_status: str  # "active" or "completed"

class DataService:
    """Core data service for market data management"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)
        
        # Redis for caching
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)
        
        # WebSocket connections
        self.market_streamer = None
        self.portfolio_streamer = None
        
        # Subscribers: client_id -> (websocket, subscriptions_set)
        # subscriptions_set can contain "*" for all instruments, or specific instrument_keys
        self.subscribers: Dict[str, Tuple[WebSocket, Set[str]]] = {}
        
        # OHLC Subscribers: client_id -> {instrument_key: {intervals}}
        # intervals can contain "*" for all intervals, or specific intervals like ["1min", "5min"]
        self.ohlc_subscribers: Dict[str, Dict[str, Set[str]]] = {}
        
        # Data cache
        self.market_data_cache: Dict[str, MarketData] = {}
        
        # History API for fetching historical candles
        self.history_api = upstox_client.HistoryV3Api(self.api_client)
    
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
                        
                        # Handle Index feeds
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
                            
                            # Process OHLC data
                            if 'marketOHLC' in index_data:
                                self._process_ohlc_data(instrument_key, index_data['marketOHLC'])
                        
                        # Handle Market feeds (for equity/options)
                        elif 'marketFF' in full_feed:
                            market_data_feed = full_feed['marketFF']
                            
                            # Process LTPC if available
                            if 'ltpc' in market_data_feed:
                                ltpc = market_data_feed['ltpc']
                                market_data = MarketData(
                                    instrument_key=instrument_key,
                                    ltp=ltpc.get('ltp', 0),
                                    ltt=ltpc.get('ltt', ''),
                                    change_percent=ltpc.get('cp', 0),
                                    ohlc=market_data_feed.get('marketOHLC', {}),
                                    timestamp=datetime.now()
                                )
                                
                                self.market_data_cache[instrument_key] = market_data
                                self.redis_client.setex(
                                    f"market_data:{instrument_key}",
                                    300,
                                    json.dumps(market_data.__dict__, default=str)
                                )
                                
                                self._broadcast_to_subscribers({
                                    "type": "market_data",
                                    "data": market_data.__dict__
                                })
                            
                            # Process OHLC data
                            if 'marketOHLC' in market_data_feed:
                                self._process_ohlc_data(instrument_key, market_data_feed['marketOHLC'])
                                
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
            import traceback
            traceback.print_exc()
    
    def _process_ohlc_data(self, instrument_key: str, market_ohlc: dict):
        """Process OHLC data from WebSocket feed"""
        try:
            if not market_ohlc or 'ohlc' not in market_ohlc:
                return
            
            ohlc_list = market_ohlc.get('ohlc', [])
            if not isinstance(ohlc_list, list):
                return
            
            current_time = int(time.time() * 1000)  # Current timestamp in milliseconds
            
            for ohlc_item in ohlc_list:
                if not isinstance(ohlc_item, dict):
                    continue
                
                interval = ohlc_item.get('interval', '')
                if not interval:
                    continue
                
                # Determine if candle is active or completed
                candle_timestamp = ohlc_item.get('ts', 0)
                candle_status = "active"  # Default to active
                
                # Simple heuristic: if timestamp is more than 2 minutes old for 1min candles, likely completed
                # For other intervals, use interval-based logic
                if interval == "1min" and candle_timestamp > 0:
                    time_diff = (current_time - candle_timestamp) / 1000  # seconds
                    if time_diff > 120:  # More than 2 minutes old
                        candle_status = "completed"
                elif interval in ["5min", "15min", "30min"] and candle_timestamp > 0:
                    # For longer intervals, check if timestamp is significantly older than interval
                    interval_seconds = self._interval_to_seconds(interval)
                    time_diff = (current_time - candle_timestamp) / 1000
                    if time_diff > interval_seconds * 1.5:  # 1.5x the interval
                        candle_status = "completed"
                
                # Create OHLC candle object
                candle = OHLCCandle(
                    instrument_key=instrument_key,
                    interval=interval,
                    open=ohlc_item.get('open', 0),
                    high=ohlc_item.get('high', 0),
                    low=ohlc_item.get('low', 0),
                    close=ohlc_item.get('close', 0),
                    volume=ohlc_item.get('vol', 0),
                    timestamp=candle_timestamp,
                    candle_status=candle_status
                )
                
                # Cache completed candles
                if candle_status == "completed":
                    self._cache_ohlc_candle(candle)
                
                # Broadcast to OHLC subscribers
                self._broadcast_ohlc_update(candle)
                
        except Exception as e:
            logger.error(f"Error processing OHLC data for {instrument_key}: {e}")
    
    def _interval_to_seconds(self, interval: str) -> int:
        """Convert interval string to seconds"""
        interval_map = {
            "1min": 60,
            "5min": 300,
            "15min": 900,
            "30min": 1800,
            "1day": 86400
        }
        return interval_map.get(interval, 60)
    
    def _cache_ohlc_candle(self, candle: OHLCCandle):
        """Cache completed OHLC candle in Redis"""
        try:
            cache_key = f"ohlc:{candle.instrument_key}:{candle.interval}:{candle.timestamp}"
            candle_data = {
                "instrument_key": candle.instrument_key,
                "interval": candle.interval,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "timestamp": candle.timestamp,
                "candle_status": candle.candle_status
            }
            # Cache for 24 hours (candles are historical data)
            self.redis_client.setex(cache_key, 86400, json.dumps(candle_data))
        except Exception as e:
            logger.error(f"Error caching OHLC candle: {e}")
    
    def _broadcast_ohlc_update(self, candle: OHLCCandle):
        """Broadcast OHLC update to subscribed clients"""
        if not self.ohlc_subscribers:
            return
        
        message = {
            "type": "ohlc_data",
            "data": {
                "instrument_key": candle.instrument_key,
                "interval": candle.interval,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "timestamp": candle.timestamp,
                "candle_status": candle.candle_status
            }
        }
        
        message_str = json.dumps(message, default=str)
        disconnected_clients = []
        
        for client_id, instrument_intervals in list(self.ohlc_subscribers.items()):
            if client_id not in self.subscribers:
                continue
            
            websocket, _ = self.subscribers[client_id]
            
            # Check if client subscribed to this instrument and interval
            should_receive = False
            if candle.instrument_key in instrument_intervals:
                intervals = instrument_intervals[candle.instrument_key]
                if "*" in intervals or candle.interval in intervals:
                    should_receive = True
            
            if should_receive:
                try:
                    asyncio.create_task(websocket.send_text(message_str))
                except Exception as e:
                    logger.error(f"Error sending OHLC to client {client_id}: {e}")
                    disconnected_clients.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected_clients:
            self._remove_ohlc_subscriber(client_id)
    
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
        """Broadcast message to subscribed WebSocket clients only"""
        if not self.subscribers:
            return
        
        # Extract instrument_key from message for filtering
        instrument_key = None
        message_type = message.get("type", "")
        
        if message_type == "market_data":
            instrument_key = message.get("data", {}).get("instrument_key")
        elif message_type == "portfolio_data":
            # Portfolio data goes to all subscribers who want it
            instrument_key = "*"
        
        message_str = json.dumps(message, default=str)
        disconnected_clients = []
        
        for client_id, (websocket, subscriptions) in list(self.subscribers.items()):
            # Check if client should receive this message
            should_receive = (
                "*" in subscriptions or  # Subscribed to all
                instrument_key in subscriptions or  # Subscribed to this specific instrument
                (instrument_key is None and "*" in subscriptions)  # Portfolio data for all subscribers
            )
            
            if should_receive:
                try:
                    asyncio.create_task(websocket.send_text(message_str))
                except Exception as e:
                    logger.error(f"Error sending to client {client_id}: {e}")
                    disconnected_clients.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected_clients:
            self.remove_subscriber(client_id)
    
    def add_subscriber(self, websocket: WebSocket, client_id: str = None, subscriptions: Set[str] = None):
        """Add a new WebSocket subscriber"""
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        if subscriptions is None:
            subscriptions = {"*"}  # Default: subscribe to all
        
        self.subscribers[client_id] = (websocket, subscriptions)
        logger.info(f"Added subscriber {client_id} with subscriptions: {subscriptions}. Total subscribers: {len(self.subscribers)}")
        return client_id
    
    def remove_subscriber(self, client_id: str):
        """Remove a WebSocket subscriber by client_id"""
        if client_id in self.subscribers:
            del self.subscribers[client_id]
            logger.info(f"Removed subscriber {client_id}. Total subscribers: {len(self.subscribers)}")
        
        # Also remove OHLC subscriptions
        if client_id in self.ohlc_subscribers:
            del self.ohlc_subscribers[client_id]
    
    def update_subscriptions(self, client_id: str, action: str, instruments: List[str]):
        """Update subscriptions for a client
        
        Args:
            client_id: Client identifier
            action: 'subscribe' or 'unsubscribe'
            instruments: List of instrument keys (use ['*'] for all)
        """
        if client_id not in self.subscribers:
            logger.warning(f"Client {client_id} not found for subscription update")
            return False
        
        websocket, subscriptions = self.subscribers[client_id]
        
        if action == "subscribe":
            subscriptions.update(instruments)
            logger.info(f"Client {client_id} subscribed to: {instruments}")
        elif action == "unsubscribe":
            subscriptions.difference_update(instruments)
            logger.info(f"Client {client_id} unsubscribed from: {instruments}")
        else:
            logger.warning(f"Unknown subscription action: {action}")
            return False
        
        # Update the subscriber entry
        self.subscribers[client_id] = (websocket, subscriptions)
        return True
    
    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """Get current subscriptions for a client"""
        if client_id in self.subscribers:
            return self.subscribers[client_id][1].copy()
        return set()
    
    def subscribe_ohlc(self, client_id: str, instruments: List[str], intervals: List[str] = None, include_history: bool = True):
        """Subscribe client to OHLC data for specified instruments and intervals"""
        if client_id not in self.subscribers:
            return False, "Client not found"
        
        if intervals is None or not intervals:
            intervals = ["*"]  # Default to all intervals
        
        # Initialize client's OHLC subscriptions if not exists
        if client_id not in self.ohlc_subscribers:
            self.ohlc_subscribers[client_id] = {}
        
        for instrument_key in instruments:
            if instrument_key not in self.ohlc_subscribers[client_id]:
                self.ohlc_subscribers[client_id][instrument_key] = set()
            
            self.ohlc_subscribers[client_id][instrument_key].update(intervals)
        
        logger.info(f"Client {client_id} subscribed to OHLC: {instruments} with intervals: {intervals}")
        
        # Fetch and send historical candles if requested
        if include_history:
            asyncio.create_task(self._send_historical_ohlc(client_id, instruments, intervals))
        
        return True, "Subscribed successfully"
    
    def unsubscribe_ohlc(self, client_id: str, instruments: List[str] = None, intervals: List[str] = None):
        """Unsubscribe client from OHLC data"""
        if client_id not in self.ohlc_subscribers:
            return False, "No OHLC subscriptions found"
        
        if instruments is None:
            # Unsubscribe from all instruments
            del self.ohlc_subscribers[client_id]
            logger.info(f"Client {client_id} unsubscribed from all OHLC")
            return True, "Unsubscribed from all OHLC"
        
        for instrument_key in instruments:
            if instrument_key in self.ohlc_subscribers[client_id]:
                if intervals is None:
                    # Unsubscribe from all intervals for this instrument
                    del self.ohlc_subscribers[client_id][instrument_key]
                else:
                    # Unsubscribe from specific intervals
                    self.ohlc_subscribers[client_id][instrument_key].difference_update(intervals)
                    # Remove instrument entry if no intervals left
                    if not self.ohlc_subscribers[client_id][instrument_key]:
                        del self.ohlc_subscribers[client_id][instrument_key]
        
        # Clean up empty client entry
        if not self.ohlc_subscribers[client_id]:
            del self.ohlc_subscribers[client_id]
        
        logger.info(f"Client {client_id} unsubscribed from OHLC: {instruments}")
        return True, "Unsubscribed successfully"
    
    def get_client_ohlc_subscriptions(self, client_id: str) -> Dict[str, Set[str]]:
        """Get current OHLC subscriptions for a client"""
        if client_id in self.ohlc_subscribers:
            return {k: v.copy() for k, v in self.ohlc_subscribers[client_id].items()}
        return {}
    
    def _remove_ohlc_subscriber(self, client_id: str):
        """Remove OHLC subscriber (internal use)"""
        if client_id in self.ohlc_subscribers:
            del self.ohlc_subscribers[client_id]
    
    async def _send_historical_ohlc(self, client_id: str, instruments: List[str], intervals: List[str]):
        """Fetch and send historical OHLC candles to client"""
        if client_id not in self.subscribers:
            return
        
        websocket, _ = self.subscribers[client_id]
        
        # Map interval strings to API format
        interval_map = {
            "1min": ("minute", 1),
            "5min": ("minute", 5),
            "15min": ("minute", 15),
            "30min": ("minute", 30),
            "1day": ("day", 1)
        }
        
        for instrument_key in instruments:
            for interval_str in intervals:
                if interval_str == "*":
                    # Send all supported intervals
                    for iv in ["1min", "5min", "15min", "30min"]:
                        await self._fetch_and_send_historical(websocket, client_id, instrument_key, iv)
                else:
                    await self._fetch_and_send_historical(websocket, client_id, instrument_key, interval_str)
    
    async def _fetch_and_send_historical(self, websocket: WebSocket, client_id: str, instrument_key: str, interval_str: str):
        """Fetch historical candles from cache or API and send to client"""
        try:
            # First, try to get from cache
            cached_candles = self._get_cached_ohlc_candles(instrument_key, interval_str)
            
            # If cache has sufficient data, use it
            if cached_candles and len(cached_candles) > 0:
                await self._send_ohlc_snapshot(websocket, client_id, instrument_key, interval_str, cached_candles)
                logger.info(f"Sent {len(cached_candles)} cached OHLC candles to {client_id} for {instrument_key} {interval_str}")
                return
            
            # If cache is incomplete or empty, fetch from API
            try:
                # Run synchronous API call in executor to avoid blocking
                loop = asyncio.get_event_loop()
                api_candles = await loop.run_in_executor(None, self._fetch_ohlc_from_api, instrument_key, interval_str)
                if api_candles:
                    # Cache the fetched candles
                    for candle_data in api_candles:
                        self._cache_ohlc_from_api(instrument_key, interval_str, candle_data)
                    
                    await self._send_ohlc_snapshot(websocket, client_id, instrument_key, interval_str, api_candles)
                    logger.info(f"Fetched and sent {len(api_candles)} OHLC candles from API to {client_id} for {instrument_key} {interval_str}")
                else:
                    # Send empty snapshot if no data available
                    await self._send_ohlc_snapshot(websocket, client_id, instrument_key, interval_str, [])
            except Exception as api_error:
                logger.error(f"Error fetching OHLC from API for {instrument_key} {interval_str}: {api_error}")
                # Send cached data even if incomplete
                if cached_candles:
                    await self._send_ohlc_snapshot(websocket, client_id, instrument_key, interval_str, cached_candles)
        
        except Exception as e:
            logger.error(f"Error sending historical OHLC to {client_id}: {e}")
    
    def _get_cached_ohlc_candles(self, instrument_key: str, interval: str) -> List[dict]:
        """Get cached OHLC candles from Redis"""
        try:
            pattern = f"ohlc:{instrument_key}:{interval}:*"
            keys = []
            
            # Scan for matching keys
            cursor = 0
            while True:
                cursor, partial_keys = self.redis_client.scan(cursor, match=pattern, count=100)
                keys.extend(partial_keys)
                if cursor == 0:
                    break
            
            candles = []
            for key in keys:
                candle_data = self.redis_client.get(key)
                if candle_data:
                    candles.append(json.loads(candle_data))
            
            # Sort by timestamp
            candles.sort(key=lambda x: x.get('timestamp', 0))
            return candles
        
        except Exception as e:
            logger.error(f"Error getting cached OHLC candles: {e}")
            return []
    
    def _fetch_ohlc_from_api(self, instrument_key: str, interval_str: str) -> List[dict]:
        """Fetch historical OHLC candles from Upstox API"""
        try:
            # Map interval to API parameters
            interval_map = {
                "1min": ("minute", 1),
                "5min": ("minute", 5),
                "15min": ("minute", 15),
                "30min": ("minute", 30),
                "1day": ("day", 1)
            }
            
            if interval_str not in interval_map:
                logger.warning(f"Unsupported interval: {interval_str}")
                return []
            
            unit, interval = interval_map[interval_str]
            
            # Get today's date for intraday candles
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Fetch intraday candles
            response = self.history_api.get_intra_day_candle_data(
                instrument_key=instrument_key,
                unit=unit,
                interval=interval
            )
            
            if hasattr(response, 'data') and response.data:
                candles = []
                for candle in response.data.candles:
                    candles.append({
                        "timestamp": int(candle[0]) if isinstance(candle[0], (int, float)) else 0,
                        "open": float(candle[1]) if len(candle) > 1 else 0,
                        "high": float(candle[2]) if len(candle) > 2 else 0,
                        "low": float(candle[3]) if len(candle) > 3 else 0,
                        "close": float(candle[4]) if len(candle) > 4 else 0,
                        "volume": int(candle[5]) if len(candle) > 5 else 0
                    })
                return candles
            
            return []
        
        except Exception as e:
            logger.error(f"Error fetching OHLC from API: {e}")
            return []
    
    def _cache_ohlc_from_api(self, instrument_key: str, interval: str, candle_data: dict):
        """Cache OHLC candle fetched from API"""
        try:
            timestamp = candle_data.get('timestamp', 0)
            if timestamp == 0:
                return
            
            cache_key = f"ohlc:{instrument_key}:{interval}:{timestamp}"
            candle_data["instrument_key"] = instrument_key
            candle_data["interval"] = interval
            candle_data["candle_status"] = "completed"
            
            self.redis_client.setex(cache_key, 86400, json.dumps(candle_data))
        except Exception as e:
            logger.error(f"Error caching OHLC from API: {e}")
    
    async def _send_ohlc_snapshot(self, websocket: WebSocket, client_id: str, instrument_key: str, interval: str, candles: List[dict]):
        """Send OHLC snapshot message to client"""
        try:
            message = {
                "type": "ohlc_snapshot",
                "instrument_key": instrument_key,
                "interval": interval,
                "candles": candles,
                "snapshot_time": datetime.now().isoformat(),
                "candle_count": len(candles)
            }
            
            await websocket.send_text(json.dumps(message, default=str))
        
        except Exception as e:
            logger.error(f"Error sending OHLC snapshot to {client_id}: {e}")
    
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

# Global data service instance
data_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    global data_service
    
    # Get access token from Redis (set by token service)
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)
    
    # Try to get token from Redis, fallback to environment variable
    access_token = None
    try:
        token = redis_client.get("upstox_access_token")
        if token:
            access_token = token.decode('utf-8')
    except Exception as e:
        logger.warning(f"Could not get token from Redis: {e}")
    
    # Fallback to environment variable
    if not access_token:
        access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        if not access_token:
            logger.error("No access token found in Redis or environment variables!")
            raise ValueError("UPSTOX_ACCESS_TOKEN must be set or available in Redis")
    
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
    
    yield
    
    # Shutdown
    if data_service:
        data_service.stop()
    logger.info("Data service stopped")

# FastAPI application
app = FastAPI(title="Data Service", version="1.0.0", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data with selective subscriptions
    
    Usage:
        1. Connect to ws://localhost:8001/ws
        2. On connection, you'll receive a welcome message with your client_id
        3. Subscribe to specific instruments:
           {"action": "subscribe", "instruments": ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]}
        4. Subscribe to all instruments:
           {"action": "subscribe", "instruments": ["*"]}
        5. Unsubscribe from instruments:
           {"action": "unsubscribe", "instruments": ["NSE_INDEX|Nifty 50"]}
        6. Get current subscriptions:
           {"action": "get_subscriptions"}
        7. Heartbeat:
           {"action": "ping"}
    
    Messages you'll receive:
        - type: "connection" - Initial connection confirmation
        - type: "market_data" - Real-time market data updates (LTPC)
        - type: "ohlc_snapshot" - Historical OHLC candles (one-time on subscription)
        - type: "ohlc_data" - Live OHLC candle updates
        - type: "portfolio_data" - Portfolio updates
        - type: "subscription_update" - Confirmation of subscription changes
        - type: "subscriptions" - Current subscription list
        - type: "ohlc_subscriptions" - Current OHLC subscription list
        - type: "pong" - Heartbeat response
        - type: "error" - Error messages
    
    OHLC Subscription:
        8. Subscribe to OHLC:
           {"action": "subscribe_ohlc", "instruments": ["NSE_INDEX|Nifty 50"], "intervals": ["1min", "5min"], "include_history": true}
        9. Unsubscribe from OHLC:
           {"action": "unsubscribe_ohlc", "instruments": ["NSE_INDEX|Nifty 50"], "intervals": ["1min"]}
        10. Get OHLC subscriptions:
            {"action": "get_ohlc_subscriptions"}
    """
    await websocket.accept()
    
    # Generate client ID and add subscriber (default: subscribe to all)
    client_id = data_service.add_subscriber(websocket)
    
    # Send welcome message with client ID
    await websocket.send_text(json.dumps({
        "type": "connection",
        "status": "connected",
        "client_id": client_id,
        "message": "Connected to market data stream. Use 'subscribe' or 'unsubscribe' actions to filter data.",
        "current_subscriptions": list(data_service.get_client_subscriptions(client_id))
    }))
    
    try:
        while True:
            # Receive and process client messages
            message_text = await websocket.receive_text()
            
            try:
                message_data = json.loads(message_text)
                action = message_data.get("action")
                
                if action == "subscribe":
                    instruments = message_data.get("instruments", [])
                    if not instruments:
                        instruments = ["*"]  # Default to all if empty
                    
                    success = data_service.update_subscriptions(client_id, "subscribe", instruments)
                    await websocket.send_text(json.dumps({
                        "type": "subscription_update",
                        "action": "subscribe",
                        "instruments": instruments,
                        "success": success,
                        "current_subscriptions": list(data_service.get_client_subscriptions(client_id))
                    }))
                
                elif action == "unsubscribe":
                    instruments = message_data.get("instruments", [])
                    if not instruments:
                        instruments = ["*"]  # Unsubscribe from all
                    
                    success = data_service.update_subscriptions(client_id, "unsubscribe", instruments)
                    await websocket.send_text(json.dumps({
                        "type": "subscription_update",
                        "action": "unsubscribe",
                        "instruments": instruments,
                        "success": success,
                        "current_subscriptions": list(data_service.get_client_subscriptions(client_id))
                    }))
                
                elif action == "get_subscriptions":
                    # Return current subscriptions
                    await websocket.send_text(json.dumps({
                        "type": "subscriptions",
                        "current_subscriptions": list(data_service.get_client_subscriptions(client_id))
                    }))
                
                elif action == "subscribe_ohlc":
                    instruments = message_data.get("instruments", [])
                    intervals = message_data.get("intervals", ["*"])  # Default to all intervals
                    include_history = message_data.get("include_history", True)
                    
                    if not instruments:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "instruments list is required for OHLC subscription"
                        }))
                    else:
                        success, message = data_service.subscribe_ohlc(client_id, instruments, intervals, include_history)
                        await websocket.send_text(json.dumps({
                            "type": "subscription_update",
                            "action": "subscribe_ohlc",
                            "instruments": instruments,
                            "intervals": intervals,
                            "success": success,
                            "message": message,
                            "current_ohlc_subscriptions": data_service.get_client_ohlc_subscriptions(client_id)
                        }))
                
                elif action == "unsubscribe_ohlc":
                    instruments = message_data.get("instruments", None)  # None means all instruments
                    intervals = message_data.get("intervals", None)  # None means all intervals
                    
                    success, message = data_service.unsubscribe_ohlc(client_id, instruments, intervals)
                    await websocket.send_text(json.dumps({
                        "type": "subscription_update",
                        "action": "unsubscribe_ohlc",
                        "instruments": instruments,
                        "intervals": intervals,
                        "success": success,
                        "message": message,
                        "current_ohlc_subscriptions": data_service.get_client_ohlc_subscriptions(client_id)
                    }))
                
                elif action == "get_ohlc_subscriptions":
                    # Return current OHLC subscriptions
                    await websocket.send_text(json.dumps({
                        "type": "ohlc_subscriptions",
                        "current_ohlc_subscriptions": data_service.get_client_ohlc_subscriptions(client_id)
                    }))
                
                elif action == "ping":
                    # Heartbeat response
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown action: {action}. Supported actions: subscribe, unsubscribe, get_subscriptions, subscribe_ohlc, unsubscribe_ohlc, get_ohlc_subscriptions, ping"
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                logger.error(f"Error processing client message: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
                
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        data_service.remove_subscriber(client_id)
        # Also remove OHLC subscriptions
        if client_id in data_service.ohlc_subscribers:
            del data_service.ohlc_subscribers[client_id]

@app.get("/api/market-data/{instrument_key}")
async def get_market_data(instrument_key: str):
    """Get cached market data for specific instrument"""
    data = data_service.get_cached_data(instrument_key)
    if data:
        return data.__dict__
    return {"error": "No data available"}

@app.get("/api/market-data")
async def get_all_market_data(
    instrument_keys: str = Query(None, description="Comma-separated list of instrument keys to filter"),
    limit: int = Query(100, description="Maximum number of results to return")
):
    """Get cached market data with optional filtering
    
    Examples:
        - /api/market-data - Get all cached data (up to 100)
        - /api/market-data?instrument_keys=NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank - Get specific instruments
        - /api/market-data?limit=50 - Get first 50 instruments
    """
    all_data = data_service.get_cached_data()
    
    # Filter by instrument keys if provided
    if instrument_keys:
        keys_list = [k.strip() for k in instrument_keys.split(",")]
        filtered_data = {k: v.__dict__ for k, v in all_data.items() if k in keys_list}
        return filtered_data
    
    # Return limited results
    limited_data = {k: v.__dict__ for k, v in list(all_data.items())[:limit]}
    return limited_data

@app.get("/api/subscriptions")
async def get_subscriptions_info():
    """Get information about active WebSocket subscriptions"""
    subscriptions_info = {}
    for client_id, (websocket, subscriptions) in data_service.subscribers.items():
        subscriptions_info[client_id] = {
            "subscriptions": list(subscriptions),
            "subscription_count": len(subscriptions)
        }
    
    return {
        "total_clients": len(data_service.subscribers),
        "clients": subscriptions_info
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_connections": len(data_service.subscribers),
        "cached_instruments": len(data_service.market_data_cache)
    }

if __name__ == "__main__":
    port = int(os.getenv("DATA_SERVICE_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
