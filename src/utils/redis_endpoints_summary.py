#!/usr/bin/env python3
"""
Redis Endpoints Summary - All Redis operations in the trading system
"""

def get_redis_endpoints_summary():
    """Get comprehensive summary of all Redis endpoints and operations"""
    
    return {
        "trading_apps": {
            "options_trading_app": {
                "description": "NIFTY Options Trading Application",
                "redis_operations": {
                    "connection": {
                        "ping": "Test Redis connection",
                        "info": "Get Redis server information"
                    },
                    "instruments": {
                        "sadd options_instruments": "Store options instruments set",
                        "hset options_metadata": "Store options metadata (instrument_key -> option_name)",
                        "smembers options_instruments": "Get all options instruments"
                    },
                    "websocket_status": {
                        "setex options_websocket_status": "Store WebSocket connection status (60s TTL)",
                        "set options_last_connection": "Store last connection time",
                        "set options_last_disconnection": "Store last disconnection time",
                        "set options_last_error": "Store last error message"
                    },
                    "market_data": {
                        "setex options_data:{instrument_key}": "Cache options data (30s TTL)",
                        "get options_data:{instrument_key}": "Get cached options data",
                        "keys options_data:*": "Get all options data keys"
                    },
                    "trading_signals": {
                        "setex options_signal:{instrument_key}:{timestamp}": "Store trading signals (5min TTL)",
                        "lpush options_signals": "Add signal to signals queue",
                        "ltrim options_signals": "Keep last 200 signals",
                        "lrange options_signals": "Get recent signals"
                    },
                    "options_chain": {
                        "hset options_chain:{strike}": "Store options chain data by strike",
                        "expire options_chain:{strike}": "Set 1 minute TTL for chain data",
                        "hgetall options_chain:{strike}": "Get options chain data",
                        "keys options_chain:*": "Get all options chain keys"
                    },
                    "clients": {
                        "hset options_client:{client_id}": "Store client information",
                        "sadd options_subscribers:{instrument}": "Subscribe client to instrument",
                        "sadd options_client_instruments:{client_id}": "Store client instruments",
                        "smembers options_subscribers:{instrument}": "Get instrument subscribers",
                        "keys options_client:*": "Get all options clients"
                    },
                    "statistics": {
                        "setex options_stats:{instrument_key}": "Store instrument stats (5min TTL)",
                        "lpush options_logs:{instrument_key}": "Store activity logs",
                        "ltrim options_logs:{instrument_key}": "Keep last 100 log entries"
                    },
                    "publishing": {
                        "publish options_updates:{instrument_key}": "Publish real-time updates"
                    }
                }
            },
            "redis_trading_app": {
                "description": "General Redis Trading Application",
                "redis_operations": {
                    "connection": {
                        "ping": "Test Redis connection"
                    },
                    "instruments": {
                        "sadd active_instruments": "Store active instruments set"
                    },
                    "websocket_status": {
                        "setex websocket_status": "Store WebSocket status (60s TTL)",
                        "set last_connection_time": "Store connection time",
                        "set last_disconnection_time": "Store disconnection time",
                        "set last_error": "Store error message"
                    },
                    "market_data": {
                        "setex market_data:{instrument_key}": "Cache market data (30s TTL)",
                        "get market_data:{instrument_key}": "Get cached market data",
                        "keys market_data:*": "Get all market data keys"
                    },
                    "trading_signals": {
                        "setex signal:{instrument_key}:{timestamp}": "Store trading signals (5min TTL)",
                        "lpush signals": "Add signal to signals queue",
                        "ltrim signals": "Keep last 200 signals",
                        "lrange signals": "Get recent signals"
                    },
                    "clients": {
                        "hset client:{client_id}": "Store client information",
                        "sadd subscribers:{instrument}": "Subscribe client to instrument",
                        "sadd client_instruments:{client_id}": "Store client instruments",
                        "smembers subscribers:{instrument}": "Get instrument subscribers",
                        "keys client:*": "Get all clients"
                    },
                    "statistics": {
                        "setex stats:{instrument_key}": "Store instrument stats (5min TTL)",
                        "lpush logs:{instrument_key}": "Store activity logs",
                        "ltrim logs:{instrument_key}": "Keep last 100 log entries"
                    },
                    "publishing": {
                        "publish updates:{instrument_key}": "Publish real-time updates"
                    }
                }
            },
            "futures_trading_app": {
                "description": "Futures Trading Application",
                "redis_operations": {
                    "connection": {
                        "ping": "Test Redis connection"
                    },
                    "websocket_status": {
                        "setex futures_websocket_status": "Store WebSocket status (60s TTL)",
                        "set futures_last_connection": "Store connection time",
                        "set futures_last_disconnection": "Store disconnection time",
                        "set futures_last_error": "Store error message"
                    },
                    "market_data": {
                        "setex futures_data:{instrument_key}": "Cache futures data (30s TTL)",
                        "get futures_data:{instrument_key}": "Get cached futures data"
                    },
                    "trading_signals": {
                        "setex futures_signal:{instrument_key}:{timestamp}": "Store futures signals (5min TTL)",
                        "lpush futures_signals": "Add signal to signals queue",
                        "ltrim futures_signals": "Keep last 200 signals"
                    },
                    "statistics": {
                        "setex futures_stats:{instrument_key}": "Store futures stats (5min TTL)"
                    }
                }
            }
        },
        "services": {
            "token_service": {
                "description": "Token Management Service",
                "redis_operations": {
                    "token_storage": {
                        "setex upstox_access_token": "Store access token (24h TTL)",
                        "get upstox_access_token": "Get access token",
                        "setex token_info": "Store token metadata (24h TTL)",
                        "get token_info": "Get token information"
                    }
                }
            },
            "data_service": {
                "description": "Data Service for market data streaming",
                "redis_operations": {
                    "market_data": {
                        "setex market_data:{instrument_key}": "Cache market data (5min TTL)",
                        "setex portfolio_data": "Cache portfolio data (5min TTL)"
                    }
                }
            }
        },
        "monitoring": {
            "redis_monitor": {
                "description": "Redis monitoring and statistics",
                "redis_operations": {
                    "statistics": {
                        "info memory": "Get memory usage statistics",
                        "info stats": "Get Redis server statistics",
                        "keys *": "Get all Redis keys",
                        "dbsize": "Get database size"
                    }
                }
            }
        },
        "data_types": {
            "strings": [
                "upstox_access_token",
                "token_info", 
                "websocket_status",
                "options_websocket_status",
                "futures_websocket_status",
                "last_connection_time",
                "last_disconnection_time",
                "last_error",
                "options_last_connection",
                "options_last_disconnection",
                "options_last_error",
                "futures_last_connection",
                "futures_last_disconnection",
                "futures_last_error"
            ],
            "hashes": [
                "options_metadata",
                "options_chain:{strike}",
                "options_client:{client_id}",
                "client:{client_id}",
                "options_stats:{instrument_key}",
                "stats:{instrument_key}",
                "futures_stats:{instrument_key}"
            ],
            "sets": [
                "options_instruments",
                "active_instruments",
                "options_subscribers:{instrument}",
                "subscribers:{instrument}",
                "options_client_instruments:{client_id}",
                "client_instruments:{client_id}"
            ],
            "lists": [
                "options_signals",
                "signals",
                "futures_signals",
                "options_logs:{instrument_key}",
                "logs:{instrument_key}"
            ],
            "channels": [
                "options_updates:{instrument_key}",
                "updates:{instrument_key}"
            ]
        },
        "ttl_settings": {
            "short_term": {
                "websocket_status": "60 seconds",
                "options_websocket_status": "60 seconds",
                "futures_websocket_status": "60 seconds"
            },
            "medium_term": {
                "market_data": "30 seconds",
                "options_data": "30 seconds",
                "futures_data": "30 seconds",
                "options_chain": "60 seconds"
            },
            "long_term": {
                "trading_signals": "300 seconds (5 minutes)",
                "options_signals": "300 seconds (5 minutes)",
                "futures_signals": "300 seconds (5 minutes)",
                "statistics": "300 seconds (5 minutes)"
            },
            "very_long_term": {
                "access_token": "86400 seconds (24 hours)",
                "token_info": "86400 seconds (24 hours)"
            }
        }
    }

def display_redis_summary():
    """Display comprehensive Redis endpoints summary"""
    summary = get_redis_endpoints_summary()
    
    print("🔍 Redis Endpoints Summary - Agnidata Trading System")
    print("=" * 60)
    
    for category, services in summary.items():
        if category == "data_types":
            continue
            
        print(f"\n📊 {category.upper().replace('_', ' ')}")
        print("-" * 40)
        
        for service_name, service_info in services.items():
            print(f"\n🔧 {service_name.replace('_', ' ').title()}")
            if 'description' in service_info:
                print(f"   Description: {service_info['description']}")
            
            if 'redis_operations' in service_info:
                for operation_type, operations in service_info['redis_operations'].items():
                    print(f"   📋 {operation_type.replace('_', ' ').title()}:")
                    for operation, description in operations.items():
                        print(f"      • {operation}: {description}")
    
    print(f"\n📊 DATA TYPES")
    print("-" * 40)
    for data_type, keys in summary["data_types"].items():
        print(f"\n🔹 {data_type.upper()}:")
        for key in keys:
            print(f"   • {key}")
    
    print(f"\n⏰ TTL SETTINGS")
    print("-" * 40)
    for ttl_category, settings in summary["ttl_settings"].items():
        print(f"\n🔹 {ttl_category.replace('_', ' ').title()}:")
        for key, ttl in settings.items():
            print(f"   • {key}: {ttl}")

if __name__ == "__main__":
    display_redis_summary()
