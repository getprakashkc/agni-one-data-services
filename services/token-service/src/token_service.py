"""
Simple Token Management Service
- Fetch token on startup
- Manual token update endpoint
- 401 error handling with retries
"""

import sys
import os
# Add shared utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared', 'utils'))

import requests
import redis
import json
import logging
import time
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ist_utils import get_ist_now, format_ist_for_redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenUpdateRequest(BaseModel):
    access_token: str
    expires_at: Optional[str] = None
    account_id: Optional[str] = None

class TokenService:
    """Simple token management service"""
    
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0, redis_password=None):
        redis_kwargs = {"host": redis_host, "port": redis_port, "db": redis_db}
        if redis_password:
            redis_kwargs["password"] = redis_password
        self.redis_client = redis.Redis(**redis_kwargs)
        self.token_url = os.getenv("INTERNAL_API_BASE_URL", "http://192.168.1.206:9000") + f"/accounts/{os.getenv('INTERNAL_API_ACCOUNT_ID', 'agnidata001')}/token"
        self.current_token = None
        self.token_expires_at = None
        self.retry_count = 0
        self.max_retries = 3
        
    def fetch_token_on_startup(self) -> bool:
        """Fetch token on startup from internal API"""
        try:
            logger.info("🔄 Fetching token on startup...")
            
            # Call internal API to get fresh token
            response = requests.get(self.token_url, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            
            if token_data.get('success', False):
                self.current_token = token_data['access_token']
                self.token_expires_at = token_data.get('expires_at')
                
                # Store token in Redis
                self._store_token_in_redis(token_data)
                
                logger.info("✅ Token fetched successfully on startup")
                logger.info(f"📅 Token expires at: {self.token_expires_at}")
                return True
            else:
                logger.error("❌ Token fetch failed: API returned success=false")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Token fetch failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during token fetch: {e}")
            return False
    
    def _store_token_in_redis(self, token_data: Dict[str, Any]):
        """Store token data in Redis"""
        try:
            # Store token with TTL (24 hours)
            self.redis_client.setex("upstox_access_token", 86400, token_data['access_token'])
            
            # Store full token data
            token_info = {
                'access_token': token_data['access_token'],
                'account_id': token_data.get('account_id', 'agnidata001'),
                'expires_at': token_data.get('expires_at'),
                'source': token_data.get('source', 'account_config'),
                'success': token_data.get('success', True),
                'updated_at': format_ist_for_redis(),
                'updated_by': 'startup_fetch'
            }
            
            self.redis_client.setex("token_info", 86400, json.dumps(token_info))
            
            logger.info("💾 Token stored in Redis successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to store token in Redis: {e}")
    
    def get_current_token(self) -> Optional[str]:
        """Get current token from Redis"""
        try:
            token = self.redis_client.get("upstox_access_token")
            if token:
                return token.decode('utf-8')
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get token from Redis: {e}")
            return None
    
    def update_token_manually(self, token_data: Dict[str, Any]) -> bool:
        """Update token manually via endpoint"""
        try:
            logger.info("🔄 Updating token manually...")
            
            # Store new token in Redis
            self._store_token_in_redis(token_data)
            
            # Update current token
            self.current_token = token_data['access_token']
            self.token_expires_at = token_data.get('expires_at')
            
            logger.info("✅ Token updated manually")
            logger.info(f"📅 New token expires at: {self.token_expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update token manually: {e}")
            return False
    
    def validate_token_with_upstox(self, token: str) -> bool:
        """Validate token by calling Upstox API"""
        try:
            # Test token with a simple Upstox API call
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Use a simple API endpoint to test token
            test_url = "https://api.upstox.com/v2/user/profile"
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Token validation successful")
                return True
            elif response.status_code == 401:
                logger.warning("⚠️ Token validation failed: 401 Unauthorized")
                return False
            else:
                logger.warning(f"⚠️ Token validation failed: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Token validation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during token validation: {e}")
            return False
    
    def handle_401_error(self) -> bool:
        """Handle 401 error with retry logic"""
        self.retry_count += 1
        
        if self.retry_count <= self.max_retries:
            logger.warning(f"⚠️ 401 Error - Retry {self.retry_count}/{self.max_retries}")
            
            # Wait before retry (exponential backoff)
            wait_time = 2 ** self.retry_count
            time.sleep(wait_time)
            
            # Try to get fresh token
            if self.fetch_token_on_startup():
                self.retry_count = 0  # Reset retry count on success
                return True
            else:
                return self.handle_401_error()  # Recursive retry
        else:
            logger.error(f"❌ Max retries ({self.max_retries}) exceeded. Stopping service.")
            return False
    
    def get_token_status(self) -> Dict[str, Any]:
        """Get current token status"""
        try:
            token_info = self.redis_client.get("token_info")
            if token_info:
                return json.loads(token_info)
            else:
                return {
                    'status': 'no_token',
                    'message': 'No token found in Redis',
                    'current_time': format_ist_for_redis()
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error getting token status: {e}',
                'current_time': format_ist_for_redis()
            }

# FastAPI app for token management
app = FastAPI(title="Token Management Service", version="1.0.0")

# Initialize token service
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_password = os.getenv("REDIS_PASSWORD", None)
token_service = TokenService(redis_host=redis_host, redis_port=redis_port, redis_password=redis_password)

@app.on_event("startup")
async def startup_event():
    """Fetch token on startup"""
    logger.info("🚀 Starting Token Management Service")
    
    # Fetch token on startup
    success = token_service.fetch_token_on_startup()
    if success:
        logger.info("✅ Token service started successfully")
    else:
        logger.warning("⚠️ Token service started but initial token fetch failed")

@app.post("/token/update")
async def update_token(request: TokenUpdateRequest):
    """Update token manually"""
    try:
        # Validate token with Upstox API
        if not token_service.validate_token_with_upstox(request.access_token):
            raise HTTPException(status_code=400, detail="Token validation failed")
        
        # Update token
        token_data = {
            'access_token': request.access_token,
            'account_id': request.account_id or os.getenv('INTERNAL_API_ACCOUNT_ID', 'agnidata001'),
            'expires_at': request.expires_at,
            'source': 'manual_update',
            'success': True
        }
        
        success = token_service.update_token_manually(token_data)
        
        if success:
            return {
                "status": "success",
                "message": "Token updated successfully",
                "token_expires_at": request.expires_at,
                "updated_at": format_ist_for_redis()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update token")
            
    except Exception as e:
        logger.error(f"❌ Token update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/token/status")
async def get_token_status():
    """Get current token status"""
    try:
        status = token_service.get_token_status()
        return status
    except Exception as e:
        logger.error(f"❌ Failed to get token status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/token/validate")
async def validate_current_token():
    """Validate current token"""
    try:
        current_token = token_service.get_current_token()
        if not current_token:
            raise HTTPException(status_code=404, detail="No token found")
        
        is_valid = token_service.validate_token_with_upstox(current_token)
        
        return {
            "token_valid": is_valid,
            "validated_at": format_ist_for_redis(),
            "status": "valid" if is_valid else "invalid"
        }
        
    except Exception as e:
        logger.error(f"❌ Token validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        current_token = token_service.get_current_token()
        return {
            "status": "healthy" if current_token else "unhealthy",
            "has_token": bool(current_token),
            "current_time": format_ist_for_redis(),
            "service": "token_management"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "current_time": format_ist_for_redis(),
            "service": "token_management"
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TOKEN_SERVICE_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
