#!/usr/bin/env python3
"""
Data Service Microservice
Handles WebSocket connections, market data processing, and data distribution
"""

import sys
import os
# Add shared code to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'upstox_client'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'utils'))

import asyncio
import json
import time
import logging
import uuid
import requests
from typing import Dict, List, Callable, Set, Tuple, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from decimal import Decimal
import upstox_client
import redis
import asyncpg
from ist_utils import get_ist_now, get_ist_datetime, get_ist_date_string, format_ist_for_redis, IST
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    # Additional fields from full mode
    ltq: str = None  # Last traded quantity
    market_level: dict = None  # Bid/ask quotes (marketLevel)
    option_greeks: dict = None  # Option Greeks (delta, theta, gamma, vega, rho)
    atp: float = None  # Average traded price
    vtt: str = None  # Volume traded today
    oi: float = None  # Open interest
    iv: float = None  # Implied volatility
    tbq: float = None  # Total buy quantity
    tsq: float = None  # Total sell quantity

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
    # Additional fields from full mode (for market feeds)
    ltq: str = None  # Last traded quantity
    market_level: dict = None  # Bid/ask quotes (marketLevel)
    option_greeks: dict = None  # Option Greeks (delta, theta, gamma, vega, rho)
    atp: float = None  # Average traded price
    vtt: str = None  # Volume traded today
    oi: float = None  # Open interest
    iv: float = None  # Implied volatility
    tbq: float = None  # Total buy quantity
    tsq: float = None  # Total sell quantity

class InstrumentSubscribeRequest(BaseModel):
    """Request model for subscribing to instruments"""
    instruments: List[str]

class InstrumentUnsubscribeRequest(BaseModel):
    """Request model for unsubscribing from instruments"""
    instruments: List[str]

class InstrumentChangeModeRequest(BaseModel):
    """Request model for changing instrument subscription mode"""
    instruments: List[str]
    mode: str  # "full", "ltpc", "option_greeks", or "full_d30"

class DataService:
    """Core data service for market data management with support for multiple Upstox accounts for redundancy"""
    
    def __init__(self, access_tokens: List[str]):
        """
        Initialize DataService with multiple access tokens for redundancy
        
        Args:
            access_tokens: List of Upstox access tokens (at least one required)
        """
        if not access_tokens:
            raise ValueError("At least one access token is required")
        
        self.access_tokens = access_tokens
        self.loop = asyncio.get_event_loop()
        
        # Redis for caching
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_password = os.getenv("REDIS_PASSWORD", None)
        redis_kwargs = {"host": redis_host, "port": redis_port, "db": 0}
        if redis_password:
            redis_kwargs["password"] = redis_password
        self.redis_client = redis.Redis(**redis_kwargs)
        
        # PostgreSQL connection pool for master data
        # DATABASE_URL format: postgresql+asyncpg://user:password@host:port/database
        # or postgresql://user:password@host:port/database
        self.db_pool: Optional[asyncpg.Pool] = None
        database_url = os.getenv("DATABASE_URL", "")
        if database_url:
            # Parse postgresql+asyncpg:// format to asyncpg connection string
            # Remove the +asyncpg part and convert to asyncpg format
            if "+asyncpg://" in database_url:
                database_url = database_url.replace("+asyncpg://", "://")
            # asyncpg uses postgresql:// format (also accepts postgres://)
            if database_url.startswith(("postgresql://", "postgres://")):
                self.database_url = database_url
            else:
                # Try to parse and reconstruct
                parsed = urlparse(database_url)
                if parsed.scheme in ["postgresql", "postgres"]:
                    # Reconstruct with postgresql:// scheme for asyncpg
                    self.database_url = f"postgresql://{parsed.netloc}{parsed.path}"
                    if parsed.query:
                        self.database_url += f"?{parsed.query}"
                else:
                    logger.warning(f"⚠️ Unsupported database URL format: {database_url}")
                    self.database_url = None
        else:
            self.database_url = None
            logger.info("ℹ️ DATABASE_URL not set, FNO underlying master data will be skipped")
        
        # Create API clients for each token
        self.api_clients: List[upstox_client.ApiClient] = []
        self.history_apis: List[upstox_client.HistoryV3Api] = []
        
        for token in access_tokens:
            configuration = upstox_client.Configuration()
            configuration.access_token = token
            api_client = upstox_client.ApiClient(configuration)
            self.api_clients.append(api_client)
            self.history_apis.append(upstox_client.HistoryV3Api(api_client))
        
        # Use first API client as primary for operations that need a single client
        self.api_client = self.api_clients[0] if self.api_clients else None
        self.history_api = self.history_apis[0] if self.history_apis else None
        
        # WebSocket connections - list of streamers for redundancy
        self.market_streamers: List[upstox_client.MarketDataStreamerV3] = []
        self.portfolio_streamers: List[upstox_client.PortfolioDataStreamer] = []
        
        # Track connection status for each streamer
        self.market_streamer_status: List[Dict[str, Any]] = []  # [{"connected": bool, "last_error": str, "token_index": int, "reconnecting": bool}]
        self.portfolio_streamer_status: List[Dict[str, Any]] = []
        
        # Track instrument modes: instrument_key -> mode (default: "full")
        self.instrument_modes: Dict[str, str] = {}
        
        # Subscribers: client_id -> (websocket, subscriptions_set)
        # subscriptions_set can contain "*" for all instruments, or specific instrument_keys
        self.subscribers: Dict[str, Tuple[WebSocket, Set[str]]] = {}
        
        # OHLC Subscribers: client_id -> {instrument_key: {intervals}}
        # intervals can contain "*" for all intervals, or specific intervals like ["1min", "5min"]
        self.ohlc_subscribers: Dict[str, Dict[str, Set[str]]] = {}
        
        # Data cache
        self.market_data_cache: Dict[str, MarketData] = {}
        
        # Track currently subscribed instruments from Upstox
        self.subscribed_instruments: Set[str] = set()
        
        # Track last candle state for transition detection (I1 candles)
        # Format: {instrument_key: {interval: {last_timestamp: int, last_candle: OHLCCandle}}}
        self.last_candle_state: Dict[str, Dict[str, Dict]] = {}
        
        # Master data: trading date (cached in memory, updated daily at 8 AM)
        # This avoids Redis lookups for every candle - trading date only changes once per day
        self.current_trading_date: str = None

    def reload_tokens(self, access_tokens: List[str]):
        """
        Reload Upstox access tokens in-memory and restart all Upstox streams.

        This keeps existing WebSocket subscribers and OHLC subscriptions intact;
        only the upstream connections to Upstox are restarted.
        """
        if not access_tokens:
            raise ValueError("access_tokens cannot be empty when reloading tokens")

        logger.info(f"🔄 Reloading Upstox tokens (count={len(access_tokens)})")

        # Stop current streams (best-effort)
        try:
            self.stop()
        except Exception as e:
            logger.warning(f"Error while stopping existing streams during token reload: {e}")

        # Replace tokens and API clients
        self.access_tokens = access_tokens
        self.api_clients = []
        self.history_apis = []

        for token in access_tokens:
            configuration = upstox_client.Configuration()
            configuration.access_token = token
            api_client = upstox_client.ApiClient(configuration)
            self.api_clients.append(api_client)
            self.history_apis.append(upstox_client.HistoryV3Api(api_client))

        # Use first API client as primary for history API
        self.api_client = self.api_clients[0] if self.api_clients else None
        self.history_api = self.history_apis[0] if self.history_apis else None

        # Reset streamers and their status tracking
        self.market_streamers = []
        self.portfolio_streamers = []
        self.market_streamer_status = []
        self.portfolio_streamer_status = []
        # Note: instrument_modes are preserved during token reload

        # Restart streams with the current subscribed instruments
        instruments = self.get_subscribed_instruments()
        if instruments:
            logger.info(
                f"Restarting market data streams with {len(instruments)} instruments after token reload"
            )
            self.start_market_data_stream(instruments)
        else:
            logger.warning(
                "No subscribed instruments found when reloading tokens; "
                "market data stream will be idle until instruments are added"
            )

        # Portfolio stream does not depend on instrument list
        self.start_portfolio_stream()
    
    def start_market_data_stream(self, instruments: List[str]):
        """Start market data streaming with multiple streamers for redundancy"""
        logger.info(f"Starting market data stream for {len(instruments)} instruments with {len(self.api_clients)} streamers")
        
        # Track initial subscribed instruments
        self.subscribed_instruments.update(instruments)
        
        # Initialize streamer for each access token
        for idx, api_client in enumerate(self.api_clients):
            try:
                streamer = upstox_client.MarketDataStreamerV3(
                    api_client=api_client,
                    instrumentKeys=instruments,
                    mode="full"
                )
                
                # Create unique handlers for each streamer to track which one sent the data
                def make_open_handler(token_idx):
                    def handler():
                        self._on_market_open(token_idx)
                    return handler
                
                def make_message_handler(token_idx):
                    def handler(message):
                        self._on_market_message(message, token_idx)
                    return handler
                
                def make_error_handler(token_idx):
                    def handler(error):
                        self._on_market_error(error, token_idx)
                    return handler
                
                def make_close_handler(token_idx):
                    def handler(close_status_code, close_msg):
                        self._on_market_close(close_status_code, close_msg, token_idx)
                    return handler
                
                def make_reconnecting_handler(token_idx):
                    def handler(message):
                        self._on_market_reconnecting(message, token_idx)
                    return handler
                
                def make_auto_reconnect_stopped_handler(token_idx):
                    def handler(message):
                        self._on_market_auto_reconnect_stopped(message, token_idx)
                    return handler
                
                # Set event handlers
                streamer.on("open", make_open_handler(idx))
                streamer.on("message", make_message_handler(idx))
                streamer.on("error", make_error_handler(idx))
                streamer.on("close", make_close_handler(idx))
                streamer.on("reconnecting", make_reconnecting_handler(idx))
                streamer.on("autoReconnectStopped", make_auto_reconnect_stopped_handler(idx))
                
                # Enable auto-reconnect (10 second interval, 5 retries)
                streamer.auto_reconnect(True, interval=10, retry_count=5)
                
                # Initialize status tracking
                self.market_streamer_status.append({
                    "connected": False,
                    "last_error": None,
                    "token_index": idx,
                    "last_connected_at": None,
                    "reconnecting": False,
                    "reconnect_attempts": 0
                })
                
                # Initialize instrument modes to "full" (default)
                for inst in instruments:
                    self.instrument_modes[inst] = "full"
                
                # Connect streamer
                streamer.connect()
                self.market_streamers.append(streamer)
                
                logger.info(f"Initialized market data streamer {idx + 1}/{len(self.api_clients)}")
                
            except Exception as e:
                logger.error(f"Failed to initialize market data streamer {idx + 1}: {e}")
                # Still add status tracking even if connection fails
                self.market_streamer_status.append({
                    "connected": False,
                    "last_error": str(e),
                    "token_index": idx,
                    "last_connected_at": None,
                    "reconnecting": False,
                    "reconnect_attempts": 0
                })
                self.market_streamers.append(None)
    
    def add_instruments(self, instruments: List[str]) -> Tuple[bool, str]:
        """Add instruments to Upstox stream dynamically across all active streamers
        
        Args:
            instruments: List of instrument keys to subscribe to
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        active_streamers = [s for s in self.market_streamers if s is not None]
        if not active_streamers:
            return False, "No active market data streamers available"
        
        if not instruments:
            return False, "No instruments provided"
        
        try:
            # Filter out already subscribed instruments
            new_instruments = [inst for inst in instruments if inst not in self.subscribed_instruments]
            
            if not new_instruments:
                return True, f"All instruments already subscribed: {instruments}"
            
            # Subscribe to new instruments on all active streamers
            success_count = 0
            errors = []
            
            for idx, streamer in enumerate(active_streamers):
                try:
                    # Use default mode "full" for new instruments
                    streamer.subscribe(new_instruments, "full")
                    success_count += 1
                except Exception as e:
                    error_msg = f"Streamer {idx + 1}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(f"Failed to subscribe on streamer {idx + 1}: {e}")
            
            # Update tracked subscriptions if at least one streamer succeeded
            if success_count > 0:
                self.subscribed_instruments.update(new_instruments)
                # Initialize instrument modes to "full" (default)
                for inst in new_instruments:
                    self.instrument_modes[inst] = "full"
                logger.info(f"Successfully subscribed to {len(new_instruments)} new instruments on {success_count}/{len(active_streamers)} streamers: {new_instruments}")
                
                message = f"Successfully subscribed to {len(new_instruments)} instruments on {success_count}/{len(active_streamers)} streamers"
                if errors:
                    message += f". Errors: {', '.join(errors)}"
                return True, message
            else:
                return False, f"Failed to subscribe on all streamers: {', '.join(errors)}"
            
        except Exception as e:
            logger.error(f"Error subscribing to instruments {instruments}: {e}")
            return False, f"Failed to subscribe: {str(e)}"
    
    def remove_instruments(self, instruments: List[str]) -> Tuple[bool, str]:
        """Remove instruments from Upstox stream dynamically across all active streamers
        
        Args:
            instruments: List of instrument keys to unsubscribe from
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        active_streamers = [s for s in self.market_streamers if s is not None]
        if not active_streamers:
            return False, "No active market data streamers available"
        
        if not instruments:
            return False, "No instruments provided"
        
        try:
            # Filter to only instruments that are actually subscribed
            instruments_to_remove = [inst for inst in instruments if inst in self.subscribed_instruments]
            
            if not instruments_to_remove:
                return True, f"None of the instruments were subscribed: {instruments}"
            
            # Unsubscribe from all active streamers
            success_count = 0
            errors = []
            
            for idx, streamer in enumerate(active_streamers):
                try:
                    streamer.unsubscribe(instruments_to_remove)
                    success_count += 1
                except Exception as e:
                    error_msg = f"Streamer {idx + 1}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(f"Failed to unsubscribe on streamer {idx + 1}: {e}")
            
            # Update tracked subscriptions if at least one streamer succeeded
            if success_count > 0:
                self.subscribed_instruments.difference_update(instruments_to_remove)
                # Remove instrument modes for unsubscribed instruments
                for inst in instruments_to_remove:
                    self.instrument_modes.pop(inst, None)
                logger.info(f"Successfully unsubscribed from {len(instruments_to_remove)} instruments on {success_count}/{len(active_streamers)} streamers: {instruments_to_remove}")
                
                message = f"Successfully unsubscribed from {len(instruments_to_remove)} instruments on {success_count}/{len(active_streamers)} streamers"
                if errors:
                    message += f". Errors: {', '.join(errors)}"
                return True, message
            else:
                return False, f"Failed to unsubscribe on all streamers: {', '.join(errors)}"
            
        except Exception as e:
            logger.error(f"Error unsubscribing from instruments {instruments}: {e}")
            return False, f"Failed to unsubscribe: {str(e)}"
    
    def get_subscribed_instruments(self) -> List[str]:
        """Get list of currently subscribed instruments"""
        return sorted(list(self.subscribed_instruments))
    
    def change_instrument_mode(self, instruments: List[str], mode: str) -> Tuple[bool, str]:
        """Change subscription mode for instruments dynamically across all active streamers
        
        Args:
            instruments: List of instrument keys to change mode for
            mode: New mode ("full", "ltpc", "option_greeks", or "full_d30")
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        active_streamers = [s for s in self.market_streamers if s is not None]
        if not active_streamers:
            return False, "No active market data streamers available"
        
        if not instruments:
            return False, "No instruments provided"
        
        # Validate mode
        valid_modes = ["full", "ltpc", "option_greeks", "full_d30"]
        if mode not in valid_modes:
            return False, f"Invalid mode: {mode}. Valid modes: {', '.join(valid_modes)}"
        
        # Check if all instruments are subscribed
        missing_instruments = [inst for inst in instruments if inst not in self.subscribed_instruments]
        if missing_instruments:
            return False, f"Instruments not subscribed: {missing_instruments}"
        
        try:
            # Change mode on all active streamers
            success_count = 0
            errors = []
            
            for idx, streamer in enumerate(active_streamers):
                try:
                    streamer.change_mode(instruments, mode)
                    success_count += 1
                except Exception as e:
                    error_msg = f"Streamer {idx + 1}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(f"Failed to change mode on streamer {idx + 1}: {e}")
            
            # Update tracked modes if at least one streamer succeeded
            if success_count > 0:
                for inst in instruments:
                    self.instrument_modes[inst] = mode
                logger.info(f"Successfully changed mode to '{mode}' for {len(instruments)} instruments on {success_count}/{len(active_streamers)} streamers: {instruments}")
                
                message = f"Successfully changed mode to '{mode}' for {len(instruments)} instruments on {success_count}/{len(active_streamers)} streamers"
                if errors:
                    message += f". Errors: {', '.join(errors)}"
                return True, message
            else:
                return False, f"Failed to change mode on all streamers: {', '.join(errors)}"
            
        except Exception as e:
            logger.error(f"Error changing mode for instruments {instruments}: {e}")
            return False, f"Failed to change mode: {str(e)}"
    
    def get_instrument_modes(self) -> Dict[str, str]:
        """Get current mode for all subscribed instruments"""
        return self.instrument_modes.copy()
    
    def start_portfolio_stream(self):
        """Start portfolio data streaming with multiple streamers for redundancy"""
        logger.info(f"Starting portfolio data stream with {len(self.api_clients)} streamers")
        
        # Initialize streamer for each access token
        for idx, api_client in enumerate(self.api_clients):
            try:
                streamer = upstox_client.PortfolioDataStreamer(
                    api_client=api_client,
                    order_update=True,
                    position_update=True,
                    holding_update=True,
                    gtt_update=True
                )
                
                # Create unique handlers for each streamer
                def make_portfolio_open_handler(token_idx):
                    def handler():
                        self._on_portfolio_open(token_idx)
                    return handler
                
                def make_portfolio_message_handler(token_idx):
                    def handler(message):
                        self._on_portfolio_message(message, token_idx)
                    return handler
                
                def make_portfolio_error_handler(token_idx):
                    def handler(error):
                        self._on_portfolio_error(error, token_idx)
                    return handler
                
                def make_portfolio_close_handler(token_idx):
                    def handler(close_status_code, close_msg):
                        self._on_portfolio_close(close_status_code, close_msg, token_idx)
                    return handler
                
                def make_portfolio_reconnecting_handler(token_idx):
                    def handler(message):
                        self._on_portfolio_reconnecting(message, token_idx)
                    return handler
                
                def make_portfolio_auto_reconnect_stopped_handler(token_idx):
                    def handler(message):
                        self._on_portfolio_auto_reconnect_stopped(message, token_idx)
                    return handler
                
                # Set event handlers
                streamer.on("open", make_portfolio_open_handler(idx))
                streamer.on("message", make_portfolio_message_handler(idx))
                streamer.on("error", make_portfolio_error_handler(idx))
                streamer.on("close", make_portfolio_close_handler(idx))
                streamer.on("reconnecting", make_portfolio_reconnecting_handler(idx))
                streamer.on("autoReconnectStopped", make_portfolio_auto_reconnect_stopped_handler(idx))
                
                # Enable auto-reconnect (10 second interval, 5 retries)
                streamer.auto_reconnect(True, interval=10, retry_count=5)
                
                # Initialize status tracking
                self.portfolio_streamer_status.append({
                    "connected": False,
                    "last_error": None,
                    "token_index": idx,
                    "last_connected_at": None,
                    "reconnecting": False,
                    "reconnect_attempts": 0
                })
                
                # Connect streamer
                streamer.connect()
                self.portfolio_streamers.append(streamer)
                
                logger.info(f"Initialized portfolio data streamer {idx + 1}/{len(self.api_clients)}")
                
            except Exception as e:
                logger.error(f"Failed to initialize portfolio data streamer {idx + 1}: {e}")
                # Still add status tracking even if connection fails
                self.portfolio_streamer_status.append({
                    "connected": False,
                    "last_error": str(e),
                    "token_index": idx,
                    "last_connected_at": None,
                    "reconnecting": False,
                    "reconnect_attempts": 0
                })
                self.portfolio_streamers.append(None)
    
    def _on_market_open(self, streamer_index: int = 0):
        """Handle market data connection open"""
        logger.info(f"Market data WebSocket connected (streamer {streamer_index + 1}/{len(self.market_streamers)})")
        if streamer_index < len(self.market_streamer_status):
            self.market_streamer_status[streamer_index]["connected"] = True
            self.market_streamer_status[streamer_index]["last_error"] = None
            self.market_streamer_status[streamer_index]["last_connected_at"] = format_ist_for_redis()
            self.market_streamer_status[streamer_index]["reconnecting"] = False
            self.market_streamer_status[streamer_index]["reconnect_attempts"] = 0
    
    def _on_market_reconnecting(self, message, streamer_index: int = 0):
        """Handle market data reconnecting event"""
        logger.warning(f"Market data reconnecting (streamer {streamer_index + 1}/{len(self.market_streamers)}): {message}")
        if streamer_index < len(self.market_streamer_status):
            self.market_streamer_status[streamer_index]["reconnecting"] = True
            self.market_streamer_status[streamer_index]["connected"] = False
            # Extract attempt number from message if possible
            if isinstance(message, str) and "/" in message:
                try:
                    parts = message.split("/")
                    if len(parts) >= 2:
                        self.market_streamer_status[streamer_index]["reconnect_attempts"] = int(parts[0].split()[-1])
                except (ValueError, IndexError):
                    pass
    
    def _on_market_auto_reconnect_stopped(self, message, streamer_index: int = 0):
        """Handle market data auto-reconnect stopped event"""
        logger.error(f"Market data auto-reconnect stopped (streamer {streamer_index + 1}/{len(self.market_streamers)}): {message}")
        if streamer_index < len(self.market_streamer_status):
            self.market_streamer_status[streamer_index]["reconnecting"] = False
            self.market_streamer_status[streamer_index]["connected"] = False
            self.market_streamer_status[streamer_index]["last_error"] = f"Auto-reconnect stopped: {message}"
    
    def _on_market_message(self, message, streamer_index: int = 0):
        """Process market data messages from any streamer"""
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
                                
                                # Create market data object (index feeds have limited fields)
                                market_data = MarketData(
                                    instrument_key=instrument_key,
                                    ltp=ltpc.get('ltp', 0),
                                    ltt=ltpc.get('ltt', ''),
                                    change_percent=ltpc.get('cp', 0),
                                    ltq=ltpc.get('ltq', None),  # Last traded quantity
                                    ohlc=index_data.get('marketOHLC', {}),
                                    timestamp=get_ist_now()
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
                            
                            # Process OHLC data (pass full index_data for context)
                            if 'marketOHLC' in index_data:
                                self._process_ohlc_data(instrument_key, index_data['marketOHLC'], index_data)
                        
                        # Handle Market feeds (for equity/options)
                        elif 'marketFF' in full_feed:
                            market_data_feed = full_feed['marketFF']
                            
                            # Process LTPC if available
                            if 'ltpc' in market_data_feed:
                                ltpc = market_data_feed['ltpc']
                                
                                # Extract all available fields from marketFF
                                market_data = MarketData(
                                    instrument_key=instrument_key,
                                    ltp=ltpc.get('ltp', 0),
                                    ltt=ltpc.get('ltt', ''),
                                    change_percent=ltpc.get('cp', 0),
                                    ltq=ltpc.get('ltq', None),  # Last traded quantity
                                    ohlc=market_data_feed.get('marketOHLC', {}),
                                    market_level=market_data_feed.get('marketLevel', None),  # Bid/ask quotes
                                    option_greeks=market_data_feed.get('optionGreeks', None),  # Option Greeks
                                    atp=market_data_feed.get('atp', None),  # Average traded price
                                    vtt=market_data_feed.get('vtt', None),  # Volume traded today
                                    oi=market_data_feed.get('oi', None),  # Open interest
                                    iv=market_data_feed.get('iv', None),  # Implied volatility
                                    tbq=market_data_feed.get('tbq', None),  # Total buy quantity
                                    tsq=market_data_feed.get('tsq', None),  # Total sell quantity
                                    timestamp=get_ist_now()
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
                            
                            # Process OHLC data (pass full market_data_feed for context)
                            if 'marketOHLC' in market_data_feed:
                                self._process_ohlc_data(instrument_key, market_data_feed['marketOHLC'], market_data_feed)
                                
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
            import traceback
            traceback.print_exc()
    
    def _process_ohlc_data(self, instrument_key: str, market_ohlc: dict, feed_context: dict = None):
        """Process OHLC data from WebSocket feed
        
        Args:
            instrument_key: Instrument identifier
            market_ohlc: OHLC data dictionary
            feed_context: Full feed context (marketFF or indexFF) for additional fields
        """
        try:
            if not market_ohlc or 'ohlc' not in market_ohlc:
                return
            
            ohlc_list = market_ohlc.get('ohlc', [])
            if not isinstance(ohlc_list, list):
                return
            
            # Extract additional fields from feed context (if available)
            # For market feeds (marketFF), extract all fields; for index feeds (indexFF), only ltq is available
            ltq = None
            market_level = None
            option_greeks = None
            atp = None
            vtt = None
            oi = None
            iv = None
            tbq = None
            tsq = None
            
            if feed_context:
                # Extract ltq from ltpc if available
                if 'ltpc' in feed_context:
                    ltq = feed_context['ltpc'].get('ltq', None)
                
                # Extract additional fields (only available in marketFF, not indexFF)
                market_level = feed_context.get('marketLevel', None)
                option_greeks = feed_context.get('optionGreeks', None)
                atp = feed_context.get('atp', None)
                vtt = feed_context.get('vtt', None)
                oi = feed_context.get('oi', None)
                iv = feed_context.get('iv', None)
                tbq = feed_context.get('tbq', None)
                tsq = feed_context.get('tsq', None)
            
            # Interval mapping: Upstox format -> Internal format
            interval_map = {
                "I1": "1min",   # 1-minute candle
                "1d": "1day"    # Daily candle
            }
            
            for ohlc_item in ohlc_list:
                if not isinstance(ohlc_item, dict):
                    continue
                
                upstox_interval = ohlc_item.get('interval', '')
                if not upstox_interval:
                    continue
                
                # Map interval (skip if not I1 or 1d)
                interval = interval_map.get(upstox_interval)
                if not interval:
                    continue
                
                # Get timestamp (handle string format from Upstox)
                ts_str = ohlc_item.get('ts', '0')
                if isinstance(ts_str, str):
                    current_timestamp = int(ts_str) if ts_str.isdigit() else 0
                else:
                    current_timestamp = int(ts_str) if ts_str else 0
                
                if current_timestamp == 0:
                    continue
                
                # Handle volume (can be string or number)
                vol = ohlc_item.get('vol', 0)
                if isinstance(vol, str):
                    volume = int(vol) if vol.isdigit() else 0
                else:
                    volume = int(vol) if vol else 0
                
                # Handle I1 (1-minute) candles: track transitions
                if interval == "1min":
                    # Initialize tracking if needed
                    if instrument_key not in self.last_candle_state:
                        self.last_candle_state[instrument_key] = {}
                    if interval not in self.last_candle_state[instrument_key]:
                        self.last_candle_state[instrument_key][interval] = {
                            'last_timestamp': 0,
                            'last_candle': None
                        }
                    
                    last_state = self.last_candle_state[instrument_key][interval]
                    last_timestamp = last_state['last_timestamp']
                    
                    # Detect new candle: timestamp changed
                    if last_timestamp > 0 and current_timestamp != last_timestamp:
                        # New candle detected! Cache the previous one
                        if last_state['last_candle']:
                            last_candle = last_state['last_candle']
                            last_candle.candle_status = "completed"
                            self._cache_ohlc_candle(last_candle)
                            logger.info(f"Cached completed 1min candle: {instrument_key} ts={last_timestamp}")
                    
                    # Create current candle object (active) with additional fields
                    candle = OHLCCandle(
                        instrument_key=instrument_key,
                        interval=interval,
                        open=float(ohlc_item.get('open', 0)),
                        high=float(ohlc_item.get('high', 0)),
                        low=float(ohlc_item.get('low', 0)),
                        close=float(ohlc_item.get('close', 0)),
                        volume=volume,
                        timestamp=current_timestamp,
                        candle_status="active",  # Current candle is always active
                        ltq=ltq,
                        market_level=market_level,
                        option_greeks=option_greeks,
                        atp=atp,
                        vtt=vtt,
                        oi=oi,
                        iv=iv,
                        tbq=tbq,
                        tsq=tsq
                    )
                    
                    # Update tracking
                    last_state['last_timestamp'] = current_timestamp
                    last_state['last_candle'] = candle
                
                # Handle 1d (daily) candles: always cache (updates throughout the day) with additional fields
                elif interval == "1day":
                    candle = OHLCCandle(
                        instrument_key=instrument_key,
                        interval=interval,
                        open=float(ohlc_item.get('open', 0)),
                        high=float(ohlc_item.get('high', 0)),
                        low=float(ohlc_item.get('low', 0)),
                        close=float(ohlc_item.get('close', 0)),
                        volume=volume,
                        timestamp=current_timestamp,
                        candle_status="completed",  # Daily candles are always completed
                        ltq=ltq,
                        market_level=market_level,
                        option_greeks=option_greeks,
                        atp=atp,
                        vtt=vtt,
                        oi=oi,
                        iv=iv,
                        tbq=tbq,
                        tsq=tsq
                    )
                    
                    # Cache daily candle every time (updates throughout the day)
                    self._cache_ohlc_candle(candle)
                    logger.debug(f"Cached daily candle: {instrument_key} ts={current_timestamp}")
                
                # Broadcast to subscribers
                self._broadcast_ohlc_update(candle)
                
        except Exception as e:
            logger.error(f"Error processing OHLC data for {instrument_key}: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    def _get_trading_date_from_redis(self) -> str:
        """Get current trading date from Redis master data
        
        Returns:
            Trading date string in YYYY-MM-DD format, or None if not found
        """
        try:
            trading_date = self.redis_client.get("master_data:trading_date")
            if trading_date:
                return trading_date.decode('utf-8')
        except Exception as e:
            logger.warning(f"Error getting trading date from Redis: {e}")
        return None
    
    def _update_trading_date_in_redis(self, trading_date: str):
        """Update trading date in Redis master data
        
        Args:
            trading_date: Trading date string in YYYY-MM-DD format
        """
        try:
            # Store trading date with no expiration (master data)
            self.redis_client.set("master_data:trading_date", trading_date)
            # Store update timestamp
            self.redis_client.set("master_data:trading_date:updated_at", format_ist_for_redis())
            logger.info(f"✅ Updated trading date in Redis: {trading_date}")
        except Exception as e:
            logger.error(f"Error updating trading date in Redis: {e}")
    
    def _calculate_trading_date(self, timestamp_ms: int) -> str:
        """Calculate trading date from timestamp
        
        Simply converts the timestamp to IST and returns the date.
        The date refresh in the morning (8 AM scheduler) or on restart ensures correct trading date.
        
        Args:
            timestamp_ms: Timestamp in milliseconds since epoch (UTC)
            
        Returns:
            Trading date string in YYYY-MM-DD format
        """
        # Convert UTC timestamp to IST datetime and return the date
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=IST)
        return dt.strftime("%Y-%m-%d")
    
    def _get_trading_date(self, timestamp_ms: int) -> str:
        """Get trading date in YYYY-MM-DD format from timestamp
        
        Always returns the calculated trading date from the timestamp (no manipulation).
        This ensures OHLC candles are stored under the correct trading date based on their timestamp.
        The global cache is updated separately for master data purposes only.
        
        Args:
            timestamp_ms: Timestamp in milliseconds since epoch (UTC)
            
        Returns:
            Trading date string in YYYY-MM-DD format (calculated directly from timestamp)
        """
        # Calculate trading date directly from timestamp (no manipulation)
        calculated_date = self._calculate_trading_date(timestamp_ms)
        
        # Update global cache only if:
        # 1. Cache is missing, OR
        # 2. Calculated date is newer or equal to cached date (current day's candles)
        # Note: This cache update is for master data only, doesn't affect the returned date
        if (self.current_trading_date is None) or (calculated_date >= self.current_trading_date):
            self.current_trading_date = calculated_date
            self._update_trading_date_in_redis(calculated_date)
        
        # Always return the calculated date for this timestamp (used for Redis key)
        return calculated_date
    
    def _get_or_init_trading_date(self) -> str:
        """Get current trading date from Redis or calculate and store if missing
        
        Used during startup to initialize in-memory cache.
        Updates both memory cache and Redis.
        
        Returns:
            Trading date string in YYYY-MM-DD format
        """
        # Try to get from Redis first
        cached_date = self._get_trading_date_from_redis()
        
        if cached_date:
            # Load into memory cache
            self.current_trading_date = cached_date
            logger.info(f"✅ Loaded trading date from Redis: {cached_date}")
            return cached_date
        
        # Calculate current trading date
        current_timestamp = int(time.time() * 1000)
        calculated_date = self._calculate_trading_date(current_timestamp)
        
        # Store in both memory cache and Redis
        self.current_trading_date = calculated_date
        self._update_trading_date_in_redis(calculated_date)
        logger.info(f"✅ Calculated and stored trading date: {calculated_date}")
        
        return calculated_date
    
    async def _get_db_pool(self) -> Optional[asyncpg.Pool]:
        """Get or create database connection pool
        
        Returns:
            asyncpg.Pool instance or None if database URL not configured
        """
        if not self.database_url:
            return None
        
        if self.db_pool is None:
            try:
                # Parse connection string for asyncpg
                # asyncpg expects: postgresql://user:password@host:port/database
                self.db_pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=60
                )
                logger.info("✅ Created PostgreSQL connection pool")
            except Exception as e:
                logger.error(f"❌ Error creating database connection pool: {e}")
                return None
        
        return self.db_pool
    
    async def _fetch_fno_underlying_data(self) -> List[Dict]:
        """Fetch FNO underlying data from PostgreSQL database
        
        Returns:
            List of dictionaries with instrument_key, trading_symbol, name, 
            segment, instrument_type, tick_size
        """
        pool = await self._get_db_pool()
        if not pool:
            logger.warning("⚠️ Database pool not available, skipping FNO underlying data fetch")
            return []
        
        try:
            async with pool.acquire() as conn:
                query = """
                    SELECT 
                        i.instrument_key, 
                        i.trading_symbol, 
                        i.name, 
                        i.segment, 
                        i.instrument_type, 
                        i.tick_size 
                    FROM public.instruments i 
                    WHERE i.exchange = 'NSE' 
                    AND EXISTS (
                        SELECT 1 
                        FROM public.instruments f 
                        WHERE f.segment = 'NSE_FO' 
                        AND f.underlying_symbol = i.trading_symbol
                    ) 
                    ORDER BY i.trading_symbol;
                """
                
                rows = await conn.fetch(query)
                
                # Convert asyncpg.Record to dict
                data = [dict(row) for row in rows]
                
                logger.info(f"✅ Fetched {len(data)} FNO underlying instruments from database")
                return data
                
        except Exception as e:
            logger.error(f"❌ Error fetching FNO underlying data from database: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _convert_decimal_to_float(self, obj: Any) -> Any:
        """Recursively convert Decimal values to float for JSON serialization
        
        Args:
            obj: Object that may contain Decimal values
            
        Returns:
            Object with Decimal values converted to float
        """
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_decimal_to_float(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimal_to_float(item) for item in obj]
        else:
            return obj
    
    def _cache_fno_underlying_data(self, fno_data: List[Dict]) -> None:
        """Cache FNO underlying data in Redis
        
        Stores data with key format: fno_und:{trading_symbol}
        
        Args:
            fno_data: List of dictionaries with FNO underlying instrument data
        """
        try:
            cached_count = 0
            skipped_count = 0
            sample_keys = []
            
            for item in fno_data:
                trading_symbol = item.get('trading_symbol')
                if not trading_symbol:
                    skipped_count += 1
                    continue
                
                # Redis key: fno_und:{trading_symbol}
                redis_key = f"fno_und:{trading_symbol}"
                
                # Convert Decimal values to float for JSON serialization
                item_serializable = self._convert_decimal_to_float(item)
                
                # Store as JSON string
                self.redis_client.set(
                    redis_key,
                    json.dumps(item_serializable),
                    ex=86400 * 7  # 7 days TTL (master data, refresh daily)
                )
                cached_count += 1
                
                # Collect sample keys for logging (first 5)
                if len(sample_keys) < 5:
                    sample_keys.append(redis_key)
            
            # Store update timestamp
            self.redis_client.set(
                "master_data:fno_underlying:updated_at",
                format_ist_for_redis()
            )
            
            logger.info(
                f"✅ Cached {cached_count} FNO underlying instruments in Redis "
                f"(skipped {skipped_count} with missing trading_symbol)"
            )
            if sample_keys:
                logger.info(f"📋 Sample Redis keys: {', '.join(sample_keys)}")
            
            # Verify a sample key exists in Redis
            if sample_keys:
                test_key = sample_keys[0]
                test_value = self.redis_client.get(test_key)
                if test_value:
                    logger.info(f"✅ Verified: Key '{test_key}' exists in Redis (length: {len(test_value)} bytes)")
                else:
                    logger.warning(f"⚠️ Warning: Key '{test_key}' not found in Redis after caching!")
            
        except Exception as e:
            logger.error(f"❌ Error caching FNO underlying data: {e}")
            import traceback
            traceback.print_exc()
    
    async def _update_fno_underlying_master_data(self) -> None:
        """Update FNO underlying master data from database and cache in Redis"""
        try:
            logger.info("🔄 Updating FNO underlying master data...")
            fno_data = await self._fetch_fno_underlying_data()
            if fno_data:
                self._cache_fno_underlying_data(fno_data)
                logger.info(f"✅ FNO underlying master data update completed: {len(fno_data)} instruments")
            else:
                logger.warning("⚠️ No FNO underlying data fetched from database")
        except Exception as e:
            logger.error(f"❌ Error updating FNO underlying master data: {e}")
            import traceback
            traceback.print_exc()
    
    async def daily_master_data_scheduler(self) -> None:
        """
        Background task: update master data (trading date) once per day at 8:00 AM IST.
        
        This ensures trading date is ready before premarket starts at 9:00 AM IST.
        """
        logger.info("🕒 Starting daily master data scheduler (8:00 AM IST)")
        
        while True:
            try:
                now = get_ist_now()
                target = now.replace(hour=8, minute=0, second=0, microsecond=0)
                if now >= target:
                    # If we've already passed today's 8 AM, schedule for tomorrow
                    target = target + timedelta(days=1)
                
                sleep_seconds = (target - now).total_seconds()
                logger.info(
                    f"⏰ Next scheduled master data update at {target.isoformat()} "
                    f"(in {int(sleep_seconds)} seconds)"
                )
                
                await asyncio.sleep(sleep_seconds)
                
                # Update trading date for today (both memory cache and Redis)
                current_timestamp = int(time.time() * 1000)
                trading_date = self._calculate_trading_date(current_timestamp)
                self.current_trading_date = trading_date
                self._update_trading_date_in_redis(trading_date)
                
                # Update FNO underlying master data
                await self._update_fno_underlying_master_data()
                
                logger.info(f"✅ Scheduled master data update completed: trading_date={trading_date}")
                
            except asyncio.CancelledError:
                logger.info("⏹ Master data scheduler task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in daily_master_data_scheduler loop: {e}")
                # In case of unexpected error, wait a bit before retrying loop iteration
                await asyncio.sleep(60)
    
    def _cache_ohlc_candle(self, candle: OHLCCandle):
        """Cache completed OHLC candle in Redis using ZSET structure"""
        try:
            # Get trading date from timestamp
            trading_date = self._get_trading_date(candle.timestamp)
            
            # ZSET key: ohlc:{trading_date}:{instrument_key}:{interval}
            zset_key = f"ohlc:{trading_date}:{candle.instrument_key}:{candle.interval}"
            latest_key = f"ohlc:{trading_date}:{candle.instrument_key}:{candle.interval}:latest"
            
            candle_data = {
                "instrument_key": candle.instrument_key,
                "interval": candle.interval,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "timestamp": candle.timestamp,
                "candle_status": candle.candle_status,
                # Additional fields from full mode
                "ltq": candle.ltq,
                "market_level": candle.market_level,
                "option_greeks": candle.option_greeks,
                "atp": candle.atp,
                "vtt": candle.vtt,
                "oi": candle.oi,
                "iv": candle.iv,
                "tbq": candle.tbq,
                "tsq": candle.tsq
            }
            
            candle_json = json.dumps(candle_data)
            
            # Add to ZSET with timestamp as score (for automatic sorting)
            # ZADD will update if member already exists (same timestamp)
            self.redis_client.zadd(zset_key, {candle_json: candle.timestamp})
            
            # Set TTL on ZSET (24 hours) - only set if key is new
            if self.redis_client.ttl(zset_key) == -1:  # -1 means no TTL set
                self.redis_client.expire(zset_key, 86400)
            
            # Update latest candle key
            self.redis_client.setex(latest_key, 86400, candle_json)
            
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
                    asyncio.run_coroutine_threadsafe(websocket.send_text(message_str), self.loop)
                except Exception as e:
                    logger.error(f"Error sending OHLC to client {client_id}: {e}")
                    disconnected_clients.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected_clients:
            self._remove_ohlc_subscriber(client_id)
    
    def _on_portfolio_message(self, message, streamer_index: int = 0):
        """Process portfolio data messages from any streamer"""
        try:
            # Cache portfolio data (last write wins - both streamers can update)
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
            logger.error(f"Error processing portfolio data (streamer {streamer_index + 1}): {e}")
    
    def _on_market_error(self, error, streamer_index: int = 0):
        """Handle market data errors"""
        logger.error(f"Market data error (streamer {streamer_index + 1}): {error}")
        if streamer_index < len(self.market_streamer_status):
            self.market_streamer_status[streamer_index]["last_error"] = str(error)
            self.market_streamer_status[streamer_index]["connected"] = False
    
    def _on_portfolio_error(self, error, streamer_index: int = 0):
        """Handle portfolio data errors"""
        logger.error(f"Portfolio data error (streamer {streamer_index + 1}): {error}")
        if streamer_index < len(self.portfolio_streamer_status):
            self.portfolio_streamer_status[streamer_index]["last_error"] = str(error)
            self.portfolio_streamer_status[streamer_index]["connected"] = False
    
    def _on_market_close(self, close_status_code, close_msg, streamer_index: int = 0):
        """Handle market data connection close"""
        logger.info(f"Market data connection closed (streamer {streamer_index + 1}): {close_status_code} - {close_msg}")
        if streamer_index < len(self.market_streamer_status):
            self.market_streamer_status[streamer_index]["connected"] = False
            self.market_streamer_status[streamer_index]["last_error"] = f"Connection closed: {close_msg}"
    
    def _on_portfolio_close(self, close_status_code, close_msg, streamer_index: int = 0):
        """Handle portfolio connection close"""
        logger.info(f"Portfolio connection closed (streamer {streamer_index + 1}): {close_status_code} - {close_msg}")
        if streamer_index < len(self.portfolio_streamer_status):
            self.portfolio_streamer_status[streamer_index]["connected"] = False
            self.portfolio_streamer_status[streamer_index]["last_error"] = f"Connection closed: {close_msg}"
    
    def _on_portfolio_open(self, streamer_index: int = 0):
        """Handle portfolio connection open"""
        logger.info(f"Portfolio WebSocket connected (streamer {streamer_index + 1}/{len(self.portfolio_streamers)})")
        if streamer_index < len(self.portfolio_streamer_status):
            self.portfolio_streamer_status[streamer_index]["connected"] = True
            self.portfolio_streamer_status[streamer_index]["last_error"] = None
            self.portfolio_streamer_status[streamer_index]["last_connected_at"] = format_ist_for_redis()
            self.portfolio_streamer_status[streamer_index]["reconnecting"] = False
            self.portfolio_streamer_status[streamer_index]["reconnect_attempts"] = 0
    
    def _on_portfolio_reconnecting(self, message, streamer_index: int = 0):
        """Handle portfolio reconnecting event"""
        logger.warning(f"Portfolio reconnecting (streamer {streamer_index + 1}/{len(self.portfolio_streamers)}): {message}")
        if streamer_index < len(self.portfolio_streamer_status):
            self.portfolio_streamer_status[streamer_index]["reconnecting"] = True
            self.portfolio_streamer_status[streamer_index]["connected"] = False
            # Extract attempt number from message if possible
            if isinstance(message, str) and "/" in message:
                try:
                    parts = message.split("/")
                    if len(parts) >= 2:
                        self.portfolio_streamer_status[streamer_index]["reconnect_attempts"] = int(parts[0].split()[-1])
                except (ValueError, IndexError):
                    pass
    
    def _on_portfolio_auto_reconnect_stopped(self, message, streamer_index: int = 0):
        """Handle portfolio auto-reconnect stopped event"""
        logger.error(f"Portfolio auto-reconnect stopped (streamer {streamer_index + 1}/{len(self.portfolio_streamers)}): {message}")
        if streamer_index < len(self.portfolio_streamer_status):
            self.portfolio_streamer_status[streamer_index]["reconnecting"] = False
            self.portfolio_streamer_status[streamer_index]["connected"] = False
            self.portfolio_streamer_status[streamer_index]["last_error"] = f"Auto-reconnect stopped: {message}"
    
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
                    asyncio.run_coroutine_threadsafe(websocket.send_text(message_str), self.loop)
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
    
    def _get_cached_ohlc_candles(self, instrument_key: str, interval: str, trading_date: str = None) -> List[dict]:
        """Get cached OHLC candles from Redis using ZSET
        
        Args:
            instrument_key: Instrument identifier
            interval: Time interval (1min, 5min, etc.)
            trading_date: Optional trading date in YYYY-MM-DD format. If None, uses current trading date.
        """
        try:
            # If trading_date not provided, use current trading date
            if trading_date is None:
                current_timestamp = int(time.time() * 1000)
                trading_date = self._get_trading_date(current_timestamp)
            
            zset_key = f"ohlc:{trading_date}:{instrument_key}:{interval}"
            
            # Get all candles from ZSET (already sorted by timestamp/score)
            # ZRANGE returns members in ascending order by score
            candle_strings = self.redis_client.zrange(zset_key, 0, -1)
            
            candles = []
            for candle_str in candle_strings:
                try:
                    candle_data = json.loads(candle_str)
                    candles.append(candle_data)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse candle data from ZSET: {candle_str[:50]}")
                    continue
            
            # ZSET is already sorted by timestamp (score), but ensure it's sorted
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
            today = get_ist_date_string()
            
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
        """Cache OHLC candle fetched from API using ZSET structure"""
        try:
            timestamp = candle_data.get('timestamp', 0)
            if timestamp == 0:
                return
            
            # Ensure required fields are set
            candle_data["instrument_key"] = instrument_key
            candle_data["interval"] = interval
            candle_data["candle_status"] = "completed"
            
            # Get trading date from timestamp
            trading_date = self._get_trading_date(timestamp)
            
            # ZSET key: ohlc:{trading_date}:{instrument_key}:{interval}
            zset_key = f"ohlc:{trading_date}:{instrument_key}:{interval}"
            latest_key = f"ohlc:{trading_date}:{instrument_key}:{interval}:latest"
            
            candle_json = json.dumps(candle_data)
            
            # Add to ZSET with timestamp as score
            self.redis_client.zadd(zset_key, {candle_json: timestamp})
            
            # Set TTL on ZSET (24 hours) - only set if key is new
            if self.redis_client.ttl(zset_key) == -1:  # -1 means no TTL set
                self.redis_client.expire(zset_key, 86400)
            
            # Update latest candle if this is the most recent
            # Check current latest timestamp
            latest_candle_str = self.redis_client.get(latest_key)
            if latest_candle_str:
                try:
                    latest_candle = json.loads(latest_candle_str)
                    latest_timestamp = latest_candle.get('timestamp', 0)
                    if timestamp > latest_timestamp:
                        self.redis_client.setex(latest_key, 86400, candle_json)
                except (json.JSONDecodeError, KeyError):
                    # If latest is invalid, update it
                    self.redis_client.setex(latest_key, 86400, candle_json)
            else:
                # No latest exists, set it
                self.redis_client.setex(latest_key, 86400, candle_json)
                
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
                "snapshot_time": format_ist_for_redis(),
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
    
    async def _close_db_pool(self):
        """Close database connection pool"""
        if self.db_pool:
            try:
                await self.db_pool.close()
                logger.info("✅ Closed PostgreSQL connection pool")
            except Exception as e:
                logger.error(f"❌ Error closing database pool: {e}")
            finally:
                self.db_pool = None
    
    def stop(self):
        """Stop all streams across all streamers"""
        logger.info("Stopping all market data streamers...")
        for idx, streamer in enumerate(self.market_streamers):
            if streamer:
                try:
                    streamer.disconnect()
                    logger.info(f"Disconnected market data streamer {idx + 1}")
                except Exception as e:
                    logger.error(f"Error disconnecting market data streamer {idx + 1}: {e}")
        
        logger.info("Stopping all portfolio data streamers...")
        for idx, streamer in enumerate(self.portfolio_streamers):
            if streamer:
                try:
                    streamer.disconnect()
                    logger.info(f"Disconnected portfolio data streamer {idx + 1}")
                except Exception as e:
                    logger.error(f"Error disconnecting portfolio data streamer {idx + 1}: {e}")
    
    def get_streamer_status(self) -> Dict:
        """Get status of all streamers"""
        active_market = sum(1 for s in self.market_streamers if s is not None)
        connected_market = sum(1 for status in self.market_streamer_status if status.get("connected", False))
        
        active_portfolio = sum(1 for s in self.portfolio_streamers if s is not None)
        connected_portfolio = sum(1 for status in self.portfolio_streamer_status if status.get("connected", False))
        
        return {
            "market_streamers": {
                "total": len(self.market_streamers),
                "active": active_market,
                "connected": connected_market,
                "status": self.market_streamer_status
            },
            "portfolio_streamers": {
                "total": len(self.portfolio_streamers),
                "active": active_portfolio,
                "connected": connected_portfolio,
                "status": self.portfolio_streamer_status
            }
        }

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
    redis_password = os.getenv("REDIS_PASSWORD", None)
    redis_kwargs = {"host": redis_host, "port": redis_port, "db": 0}
    if redis_password:
        redis_kwargs["password"] = redis_password
    redis_client = redis.Redis(**redis_kwargs)
    
    # Collect multiple access tokens for redundancy
    access_tokens = []

    # Optional: load tokens for specific Upstox accounts (comma-separated)
    # If set, we will look for per-account keys written by token-service:
    #   upstox_access_token:{account_id}
    account_ids_env = os.getenv("UPSTOX_ACCOUNT_IDS", "").strip()
    account_ids = [x.strip() for x in account_ids_env.split(",") if x.strip()] if account_ids_env else []

    # Method 1: Get tokens from Redis (primary source)
    try:
        # Preferred: per-account tokens (multi-account mode)
        if account_ids:
            for account_id in account_ids:
                token = redis_client.get(f"upstox_access_token:{account_id}")
                if token:
                    access_tokens.append(token.decode('utf-8'))
                    logger.info(f"✅ Token retrieved from Redis for account_id={account_id}")
                else:
                    logger.warning(f"⚠️ No Redis token found for account_id={account_id} (expected key upstox_access_token:{account_id})")
        else:
            # Backward-compatible single-token keys
            token = redis_client.get("upstox_access_token")
            if token:
                access_tokens.append(token.decode('utf-8'))
                logger.info("✅ Primary token retrieved from Redis")

            # Optional legacy secondary token
            token2 = redis_client.get("upstox_access_token_secondary")
            if token2:
                access_tokens.append(token2.decode('utf-8'))
                logger.info("✅ Secondary token retrieved from Redis")
    except Exception as e:
        logger.warning(f"Could not get tokens from Redis: {e}")
    
    # Method 2: Try token-service API if Redis fails
    if not access_tokens:
        try:
            token_service_url = os.getenv("TOKEN_SERVICE_URL", "http://token-service:8000")
            if account_ids:
                for account_id in account_ids:
                    response = requests.get(f"{token_service_url}/accounts/{account_id}/token/status", timeout=5)
                    if response.status_code == 200:
                        token_data = response.json()
                        if token_data.get('access_token'):
                            access_tokens.append(token_data['access_token'])
                            logger.info(f"✅ Token retrieved from token-service API for account_id={account_id}")
                        else:
                            logger.warning(f"Token service returned status but no access_token for account_id={account_id}")
                    else:
                        logger.warning(f"Token service status call failed for account_id={account_id}: {response.status_code}")
            else:
                response = requests.get(f"{token_service_url}/token/status", timeout=5)
                if response.status_code == 200:
                    token_data = response.json()
                    if token_data.get('access_token'):
                        access_tokens.append(token_data['access_token'])
                        logger.info("✅ Token retrieved from token-service API")
                    else:
                        logger.warning("Token service returned status but no access_token")
        except Exception as e:
            logger.warning(f"Could not get token from token-service API: {e}")
    
    # Method 3: Environment variables (fallback)
    # Support both single token and multiple tokens (comma-separated)
    env_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if env_token:
        # Check if it's comma-separated (multiple tokens)
        if ',' in env_token:
            tokens = [t.strip() for t in env_token.split(',') if t.strip()]
            access_tokens.extend(tokens)
            logger.info(f"⚠️ Using {len(tokens)} tokens from UPSTOX_ACCESS_TOKEN environment variable (fallback mode)")
        else:
            if not access_tokens:
                access_tokens.append(env_token)
                logger.warning("⚠️ Using token from UPSTOX_ACCESS_TOKEN environment variable (fallback mode)")
    
    # Also check for secondary token in environment
    env_token_secondary = os.getenv("UPSTOX_ACCESS_TOKEN_SECONDARY")
    if env_token_secondary and env_token_secondary not in access_tokens:
        access_tokens.append(env_token_secondary)
        logger.info("⚠️ Using secondary token from UPSTOX_ACCESS_TOKEN_SECONDARY environment variable")
    
    if not access_tokens:
        logger.error("No access tokens found in Redis, token-service API, or environment variables!")
        raise ValueError("At least one UPSTOX_ACCESS_TOKEN must be available from token-service (Redis/API) or environment variable")
    
    logger.info(f"Initializing DataService with {len(access_tokens)} access token(s) for redundancy")
    data_service = DataService(access_tokens)
    
    # Initialize master data (trading date) - load from Redis or calculate
    data_service._get_or_init_trading_date()
    
    # Initialize FNO underlying master data
    try:
        await data_service._update_fno_underlying_master_data()
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize FNO underlying master data on startup: {e}")
    
    # Get initial instruments from environment variable or use default
    instruments_env = os.getenv("INSTRUMENTS", "").strip()
    
    if instruments_env:
        # Parse comma-separated list from environment variable
        instruments = [inst.strip() for inst in instruments_env.split(",") if inst.strip()]
        logger.info(f"Using instruments from INSTRUMENTS environment variable: {len(instruments)} instruments")
    else:
        # Fallback to default hardcoded list
        instruments = [
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|Nifty Bank",
            "NSE_EQ|INE020B01018",  # Reliance
            "NSE_EQ|INE467B01029"    # TCS
        ]
        logger.info(f"Using default instruments: {len(instruments)} instruments")
    
    if not instruments:
        logger.warning("No instruments configured! Service will start but won't receive market data.")
    else:
        data_service.start_market_data_stream(instruments)
    data_service.start_portfolio_stream()
    
    # Start background scheduler for daily master data updates at 8 AM IST
    try:
        asyncio.create_task(data_service.daily_master_data_scheduler())
        logger.info("✅ Started daily master data scheduler (8:00 AM IST)")
    except RuntimeError as e:
        # In some environments there may be no running loop yet; log and skip scheduler
        logger.warning(f"⚠️ Could not start daily master data scheduler: {e}")
    
    logger.info("Data service started")
    
    yield
    
    # Shutdown
    if data_service:
        # Close database pool
        try:
            await data_service._close_db_pool()
        except Exception as e:
            logger.warning(f"⚠️ Error closing database pool during shutdown: {e}")
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
                        "timestamp": format_ist_for_redis()
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

@app.get("/api/instruments")
async def get_subscribed_instruments():
    """Get list of currently subscribed instruments from Upstox"""
    return {
        "subscribed_instruments": data_service.get_subscribed_instruments(),
        "count": len(data_service.subscribed_instruments),
        "timestamp": format_ist_for_redis()
    }

@app.get("/api/fno-underlying")
async def get_fno_underlying(
    trading_symbol: str = Query(None, description="Specific trading symbol to retrieve"),
    limit: int = Query(50, description="Maximum number of results to return (when listing all)")
):
    """Get FNO underlying master data from Redis
    
    Returns data stored with key format: fno_und:{trading_symbol}
    """
    try:
        if trading_symbol:
            # Get specific trading symbol
            redis_key = f"fno_und:{trading_symbol}"
            data = data_service.redis_client.get(redis_key)
            if data:
                return json.loads(data.decode('utf-8'))
            return {"error": f"No data found for trading_symbol: {trading_symbol}"}
        else:
            # List all FNO underlying keys
            pattern = "fno_und:*"
            keys = data_service.redis_client.keys(pattern)
            
            result = {
                "count": len(keys),
                "keys": [key.decode('utf-8') for key in keys[:limit]],
                "sample_data": {}
            }
            
            # Get sample data for first few keys
            for key in keys[:min(5, limit)]:
                key_str = key.decode('utf-8')
                data = data_service.redis_client.get(key_str)
                if data:
                    result["sample_data"][key_str] = json.loads(data.decode('utf-8'))
            
            return result
    except Exception as e:
        logger.error(f"Error getting FNO underlying data: {e}")
        return {"error": str(e)}

@app.post("/api/instruments/subscribe")
async def subscribe_instruments(request: InstrumentSubscribeRequest):
    """Subscribe to new instruments dynamically
    
    Adds instruments to the Upstox stream without disconnecting.
    Supports bulk operations - can subscribe to multiple instruments at once.
    
    Example:
        POST /api/instruments/subscribe
        {
            "instruments": ["NSE_INDEX|Nifty 50", "BSE_INDEX|SENSEX"]
        }
    """
    if not request.instruments:
        raise HTTPException(status_code=400, detail="instruments list cannot be empty")
    
    success, message = data_service.add_instruments(request.instruments)
    
    if success:
        return {
            "status": "success",
            "message": message,
            "subscribed_instruments": data_service.get_subscribed_instruments(),
            "count": len(data_service.subscribed_instruments),
            "timestamp": format_ist_for_redis()
        }
    else:
        raise HTTPException(status_code=500, detail=message)

@app.post("/api/instruments/unsubscribe")
async def unsubscribe_instruments(request: InstrumentUnsubscribeRequest):
    """Unsubscribe from instruments dynamically
    
    Removes instruments from the Upstox stream without disconnecting.
    Supports bulk operations - can unsubscribe from multiple instruments at once.
    
    Example:
        POST /api/instruments/unsubscribe
        {
            "instruments": ["NSE_INDEX|Nifty 50"]
        }
    """
    if not request.instruments:
        raise HTTPException(status_code=400, detail="instruments list cannot be empty")
    
    success, message = data_service.remove_instruments(request.instruments)
    
    if success:
        return {
            "status": "success",
            "message": message,
            "subscribed_instruments": data_service.get_subscribed_instruments(),
            "count": len(data_service.subscribed_instruments),
            "timestamp": format_ist_for_redis()
        }
    else:
        raise HTTPException(status_code=500, detail=message)

@app.post("/api/instruments/change-mode")
async def change_instrument_mode(request: InstrumentChangeModeRequest):
    """Change subscription mode for instruments dynamically
    
    Changes the subscription mode for already subscribed instruments without disconnecting.
    Default mode is "full". Available modes:
    - "full": Comprehensive information including latest trade prices, D5 depth, candlestick data
    - "ltpc": Last trade price, time, quantity, and closing price
    - "option_greeks": Option Greeks only (delta, theta, gamma, vega, rho)
    - "full_d30": Full mode plus 30 market level quotes
    
    Example:
        POST /api/instruments/change-mode
        {
            "instruments": ["NSE_OPT|...", "NSE_OPT|..."],
            "mode": "option_greeks"
        }
    """
    if not request.instruments:
        raise HTTPException(status_code=400, detail="instruments list cannot be empty")
    
    if not request.mode:
        raise HTTPException(status_code=400, detail="mode cannot be empty")
    
    success, message = data_service.change_instrument_mode(request.instruments, request.mode)
    
    if success:
        return {
            "status": "success",
            "message": message,
            "instruments": request.instruments,
            "mode": request.mode,
            "instrument_modes": data_service.get_instrument_modes(),
            "timestamp": format_ist_for_redis()
        }
    else:
        raise HTTPException(status_code=500, detail=message)

@app.get("/api/instruments/modes")
async def get_instrument_modes():
    """Get current subscription modes for all instruments
    
    Returns a mapping of instrument_key -> mode for all subscribed instruments.
    """
    return {
        "instrument_modes": data_service.get_instrument_modes(),
        "count": len(data_service.instrument_modes),
        "timestamp": format_ist_for_redis()
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint with streamer status"""
    streamer_status = data_service.get_streamer_status()
    
    # Determine overall health
    market_connected = streamer_status["market_streamers"]["connected"] > 0
    portfolio_connected = streamer_status["portfolio_streamers"]["connected"] > 0
    
    overall_status = "healthy" if (market_connected or portfolio_connected) else "degraded"
    
    return {
        "status": overall_status,
        "timestamp": format_ist_for_redis(),
        "active_connections": len(data_service.subscribers),
        "cached_instruments": len(data_service.market_data_cache),
        "subscribed_instruments_count": len(data_service.subscribed_instruments),
        "streamers": streamer_status
    }


@app.post("/api/admin/reload-tokens")
async def admin_reload_tokens():
    """
    Admin endpoint: reload Upstox access tokens from Redis / token-service
    and restart upstream streams without restarting this service.
    """
    global data_service

    if data_service is None:
        raise HTTPException(status_code=503, detail="DataService is not initialized")

    # Recreate Redis client (same config as in lifespan)
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", None)
    redis_kwargs = {"host": redis_host, "port": redis_port, "db": 0}
    if redis_password:
        redis_kwargs["password"] = redis_password
    redis_client = redis.Redis(**redis_kwargs)

    access_tokens: List[str] = []

    # Optional list of specific Upstox account IDs whose tokens we expect in Redis
    account_ids_env = os.getenv("UPSTOX_ACCOUNT_IDS", "").strip()
    account_ids = [x.strip() for x in account_ids_env.split(",") if x.strip()] if account_ids_env else []

    # Method 1: Get tokens from Redis (primary source)
    try:
        if account_ids:
            for account_id in account_ids:
                token = redis_client.get(f"upstox_access_token:{account_id}")
                if token:
                    access_tokens.append(token.decode("utf-8"))
                    logger.info(f"✅ Reload: token retrieved from Redis for account_id={account_id}")
                else:
                    logger.warning(
                        f"⚠️ Reload: no Redis token found for account_id={account_id} "
                        f"(expected key upstox_access_token:{account_id})"
                    )
        else:
            # Backward-compatible single-token keys
            token = redis_client.get("upstox_access_token")
            if token:
                access_tokens.append(token.decode("utf-8"))
                logger.info("✅ Reload: primary token retrieved from Redis")

            token2 = redis_client.get("upstox_access_token_secondary")
            if token2:
                access_tokens.append(token2.decode("utf-8"))
                logger.info("✅ Reload: secondary token retrieved from Redis")
    except Exception as e:
        logger.warning(f"Reload: could not get tokens from Redis: {e}")

    # Method 2: token-service API (fallback)
    if not access_tokens:
        try:
            token_service_url = os.getenv("TOKEN_SERVICE_URL", "http://token-service:8000")
            if account_ids:
                for account_id in account_ids:
                    response = requests.get(
                        f"{token_service_url}/accounts/{account_id}/token/status",
                        timeout=5,
                    )
                    if response.status_code == 200:
                        token_data = response.json()
                        if token_data.get("access_token"):
                            access_tokens.append(token_data["access_token"])
                            logger.info(
                                f"✅ Reload: token retrieved from token-service API for account_id={account_id}"
                            )
                        else:
                            logger.warning(
                                f"Reload: token-service returned status but no access_token "
                                f"for account_id={account_id}"
                            )
                    else:
                        logger.warning(
                            f"Reload: token-service status call failed for account_id={account_id}: "
                            f"{response.status_code}"
                        )
            else:
                response = requests.get(f"{token_service_url}/token/status", timeout=5)
                if response.status_code == 200:
                    token_data = response.json()
                    if token_data.get("access_token"):
                        access_tokens.append(token_data["access_token"])
                        logger.info("✅ Reload: token retrieved from token-service API")
                    else:
                        logger.warning("Reload: token-service returned status but no access_token")
        except Exception as e:
            logger.warning(f"Reload: could not get token from token-service API: {e}")

    # Method 3: Environment variables (fallback)
    env_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if env_token:
        if "," in env_token:
            tokens = [t.strip() for t in env_token.split(",") if t.strip()]
            access_tokens.extend(tokens)
            logger.info(
                f"⚠️ Reload: using {len(tokens)} tokens from UPSTOX_ACCESS_TOKEN environment variable (fallback mode)"
            )
        else:
            if not access_tokens:
                access_tokens.append(env_token)
                logger.warning(
                    "⚠️ Reload: using token from UPSTOX_ACCESS_TOKEN environment variable (fallback mode)"
                )

    env_token_secondary = os.getenv("UPSTOX_ACCESS_TOKEN_SECONDARY")
    if env_token_secondary and env_token_secondary not in access_tokens:
        access_tokens.append(env_token_secondary)
        logger.info("⚠️ Reload: using secondary token from UPSTOX_ACCESS_TOKEN_SECONDARY environment variable")

    if not access_tokens:
        raise HTTPException(
            status_code=500,
            detail="No access tokens found in Redis, token-service API, or environment variables during reload",
        )

    # Deduplicate tokens while preserving order
    seen = set()
    deduped_tokens: List[str] = []
    for token in access_tokens:
        if token not in seen:
            seen.add(token)
            deduped_tokens.append(token)

    try:
        data_service.reload_tokens(deduped_tokens)
    except Exception as e:
        logger.error(f"Error while reloading tokens in DataService: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload tokens: {e}")

    return {
        "status": "success",
        "token_count": len(deduped_tokens),
        "timestamp": format_ist_for_redis(),
    }

if __name__ == "__main__":
    port = int(os.getenv("DATA_SERVICE_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
