"""
IST (Indian Standard Time) utilities for financial data
"""

import pytz
from datetime import datetime, time
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

# IST timezone
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)

def get_ist_datetime(dt: Union[datetime, str, None] = None) -> datetime:
    """Convert any datetime to IST"""
    if dt is None:
        return get_ist_now()
    
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    
    if dt.tzinfo is None:
        # Assume it's already in IST if no timezone info
        return IST.localize(dt)
    else:
        # Convert to IST
        return dt.astimezone(IST)

def format_ist_datetime(dt: Union[datetime, str, None] = None, format_str: str = "%Y-%m-%d %H:%M:%S IST") -> str:
    """Format datetime in IST with timezone info"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.strftime(format_str)

def get_ist_date_string(dt: Union[datetime, str, None] = None) -> str:
    """Get date string in YYYY-MM-DD format in IST"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.strftime("%Y-%m-%d")

def get_ist_time_string(dt: Union[datetime, str, None] = None) -> str:
    """Get time string in HH:MM:SS format in IST"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.strftime("%H:%M:%S")

def is_market_hours(dt: Union[datetime, str, None] = None) -> bool:
    """Check if current time is within Indian market hours (9:15 AM - 3:30 PM IST)"""
    ist_dt = get_ist_datetime(dt)
    
    # Market hours: 9:15 AM to 3:30 PM IST
    market_start = time(9, 15)  # 9:15 AM
    market_end = time(15, 30)   # 3:30 PM
    
    current_time = ist_dt.time()
    current_weekday = ist_dt.weekday()  # 0 = Monday, 6 = Sunday
    
    # Market is closed on weekends
    if current_weekday >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    return market_start <= current_time <= market_end

def is_market_open(dt: Union[datetime, str, None] = None) -> bool:
    """Check if market is currently open"""
    return is_market_hours(dt)

def format_ist_for_redis(dt: Union[datetime, str, None] = None) -> str:
    """Format datetime in IST for Redis storage (ISO format with timezone)"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.isoformat()
