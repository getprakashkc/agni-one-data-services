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

def get_market_open_time(dt: Union[datetime, str, None] = None) -> datetime:
    """Get next market open time in IST"""
    ist_dt = get_ist_datetime(dt)
    
    # Market opens at 9:15 AM IST
    market_open = ist_dt.replace(hour=9, minute=15, second=0, microsecond=0)
    
    # If market is already open today, return today's open time
    if is_market_hours(ist_dt):
        return market_open
    
    # If it's after market hours today, get tomorrow's open time
    if ist_dt.time() > time(15, 30):
        market_open = market_open.replace(day=market_open.day + 1)
    
    # Skip weekends
    while market_open.weekday() >= 5:  # Saturday = 5, Sunday = 6
        market_open = market_open.replace(day=market_open.day + 1)
    
    return market_open

def get_market_close_time(dt: Union[datetime, str, None] = None) -> datetime:
    """Get next market close time in IST"""
    ist_dt = get_ist_datetime(dt)
    
    # Market closes at 3:30 PM IST
    market_close = ist_dt.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # If market is already closed today, get tomorrow's close time
    if not is_market_hours(ist_dt) and ist_dt.time() > time(15, 30):
        market_close = market_close.replace(day=market_close.day + 1)
    
    # Skip weekends
    while market_close.weekday() >= 5:  # Saturday = 5, Sunday = 6
        market_close = market_close.replace(day=market_close.day + 1)
    
    return market_close

def get_trading_session_info(dt: Union[datetime, str, None] = None) -> dict:
    """Get comprehensive trading session information"""
    ist_dt = get_ist_datetime(dt)
    
    return {
        "current_time_ist": format_ist_datetime(ist_dt),
        "is_market_open": is_market_open(ist_dt),
        "is_market_hours": is_market_hours(ist_dt),
        "market_open_time": format_ist_datetime(get_market_open_time(ist_dt)),
        "market_close_time": format_ist_datetime(get_market_close_time(ist_dt)),
        "timezone": "Asia/Kolkata (IST)",
        "date": get_ist_date_string(ist_dt),
        "time": get_ist_time_string(ist_dt)
    }

def convert_to_ist_iso(dt: Union[datetime, str, None] = None) -> str:
    """Convert datetime to IST and return as ISO format string"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.isoformat()

def parse_ist_date(date_str: str) -> datetime:
    """Parse date string assuming it's in IST"""
    try:
        # Try parsing as ISO format first
        if 'T' in date_str or ' ' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            # Assume YYYY-MM-DD format
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        
        # Convert to IST
        return get_ist_datetime(dt)
    except ValueError as e:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD or ISO format. Error: {e}")

def get_ist_timestamp() -> str:
    """Get current IST timestamp as string"""
    return get_ist_now().isoformat()

def validate_ist_datetime(dt: Union[datetime, str, None]) -> bool:
    """Validate if datetime is properly in IST"""
    try:
        if dt is None:
            return False
        if isinstance(dt, str):
            # Parse the string and check if it's in IST
            parsed_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            return parsed_dt.tzinfo is not None
        elif isinstance(dt, datetime):
            return dt.tzinfo is not None and dt.tzinfo.zone == 'Asia/Kolkata'
        return False
    except Exception:
        return False

def get_ist_timestamp_int() -> int:
    """Get current IST timestamp as integer (for Redis keys)"""
    return int(get_ist_now().timestamp())

def format_ist_for_redis(dt: Union[datetime, str, None] = None) -> str:
    """Format datetime in IST for Redis storage (ISO format with timezone)"""
    ist_dt = get_ist_datetime(dt)
    return ist_dt.isoformat()

def get_ist_market_status() -> dict:
    """Get current market status in IST"""
    ist_dt = get_ist_now()
    
    return {
        "current_time_ist": format_ist_datetime(ist_dt),
        "is_market_open": is_market_open(ist_dt),
        "is_market_hours": is_market_hours(ist_dt),
        "market_open_time": format_ist_datetime(get_market_open_time(ist_dt)),
        "market_close_time": format_ist_datetime(get_market_close_time(ist_dt)),
        "timezone": "Asia/Kolkata (IST)",
        "date": get_ist_date_string(ist_dt),
        "time": get_ist_time_string(ist_dt),
        "weekday": ist_dt.strftime("%A"),
        "is_weekend": ist_dt.weekday() >= 5
    }
