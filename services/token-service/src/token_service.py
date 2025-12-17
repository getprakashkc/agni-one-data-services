"""
Simple Token Management Service
- Fetch token on startup
- Manual token update endpoint
- 401 error handling with retries
"""

import sys
import os
# Add shared utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared', 'utils'))

import asyncio
import requests
import redis
import json
import logging
import time
from datetime import timedelta
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

        # Base URL for the Upstox auth/internal API.
        # Single canonical env var for both refresh and token fetch.
        base_url = os.getenv("TOKEN_REFRESH_SERVICE_URL", "http://agni-upstox-auth-server:8000")
        # Used to fetch the actual token payload after refresh
        self.internal_api_base_url = base_url

        # Account IDs (shared convention with data-service)
        # Required: comma-separated list like "agnidata001,agnidata002"
        account_ids_env = os.getenv("UPSTOX_ACCOUNT_IDS", "").strip()
        if not account_ids_env:
            raise ValueError("UPSTOX_ACCOUNT_IDS must be set (comma-separated list of Upstox account IDs)")

        self.account_ids = [x.strip() for x in account_ids_env.split(",") if x.strip()]
        if not self.account_ids:
            raise ValueError("UPSTOX_ACCOUNT_IDS must contain at least one non-empty account ID")

        # Default account is the first in the list; used when no account_id is specified
        self.default_account_id = self.account_ids[0]

        # Upstox auth-server base URL used for refresh (same as internal_api_base_url)
        # Example: http://agni-upstox-auth-server:8000
        self.token_refresh_base_url = base_url

        # Optional: data-service URL so we can notify it to reload tokens
        # after we have refreshed and written new tokens to Redis.
        # Example: http://data-service:8001
        self.data_service_url = os.getenv("DATA_SERVICE_URL", "http://data-service:8001")

        # Control whether the daily 8 AM IST scheduler is enabled
        self.enable_refresh_scheduler = os.getenv(
            "ENABLE_TOKEN_REFRESH_SCHEDULER",
            "true",
        ).lower() in ("1", "true", "yes")

        self.current_token = None
        self.token_expires_at = None
        self.retry_count = 0
        self.max_retries = 3

    def _token_key(self, account_id: str) -> str:
        return f"upstox_access_token:{account_id}"

    def _token_info_key(self, account_id: str) -> str:
        return f"token_info:{account_id}"

    def _internal_token_url(self, account_id: str) -> str:
        return f"{self.internal_api_base_url}/accounts/{account_id}/token"

    def fetch_token(self, account_id: str) -> bool:
        """Fetch token for a specific account from internal API"""
        try:
            logger.info(f"🔄 Fetching token for account_id={account_id} ...")

            response = requests.get(self._internal_token_url(account_id), timeout=10)
            response.raise_for_status()

            token_data = response.json()

            if token_data.get('success', False):
                # Normalize account_id (internal API may or may not return it)
                token_data.setdefault('account_id', account_id)
                token_data.setdefault('updated_by', 'startup_fetch')
                token_data.setdefault('source', 'account_config')

                self.current_token = token_data['access_token']
                self.token_expires_at = token_data.get('expires_at')

                self._store_token_in_redis(token_data, account_id=account_id)

                logger.info(f"✅ Token fetched successfully for account_id={account_id}")
                logger.info(f"📅 Token expires at: {self.token_expires_at}")
                return True

            logger.error(f"❌ Token fetch failed for account_id={account_id}: API returned success=false")
            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Token fetch failed for account_id={account_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during token fetch for account_id={account_id}: {e}")
            return False
        
    def fetch_token_on_startup(self) -> bool:
        """Fetch token(s) on startup from internal API (supports multiple accounts)"""
        logger.info(f"🔄 Fetching token(s) on startup for {len(self.account_ids)} account(s)...")
        ok_any = False
        for account_id in self.account_ids:
            ok_any = self.fetch_token(account_id) or ok_any
        return ok_any

    def refresh_token_for_account(self, account_id: str) -> Dict[str, Any]:
        """
        Ask the Upstox auth server to refresh the token for a specific account,
        then fetch and store the updated token via the existing internal token API.
        """
        refresh_url = f"{self.token_refresh_base_url}/accounts/{account_id}/refresh"
        result: Dict[str, Any] = {
            "account_id": account_id,
            "status": "error",
            "refresh_http_status": None,
            "fetch_ok": False,
            "error": None,
        }

        try:
            logger.info(f"🔄 Refreshing token via auth server for account_id={account_id} ...")
            response = requests.post(refresh_url, timeout=15)
            result["refresh_http_status"] = response.status_code

            if response.status_code >= 400:
                logger.error(
                    f"❌ Token refresh failed for account_id={account_id}: "
                    f"HTTP {response.status_code} - {response.text}"
                )
                result["error"] = f"http_{response.status_code}"
                return result

            # Try to read response JSON (may or may not contain useful fields)
            try:
                result["refresh_response"] = response.json()
            except ValueError:
                result["refresh_response"] = {}

            # After refresh, fetch the latest token from the internal API and store it in Redis
            fetch_ok = self.fetch_token(account_id)
            result["fetch_ok"] = fetch_ok
            if fetch_ok:
                result["status"] = "success"
                logger.info(f"✅ Token refreshed and stored for account_id={account_id}")
            else:
                result["status"] = "fetch_failed"
                logger.error(f"❌ Token refresh succeeded but fetch_token() failed for account_id={account_id}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Token refresh HTTP error for account_id={account_id}: {e}")
            result["error"] = str(e)
            return result
        except Exception as e:
            logger.error(f"❌ Unexpected error during token refresh for account_id={account_id}: {e}")
            result["error"] = str(e)
            return result

    def refresh_tokens_for_all_accounts(self, triggered_by: str = "manual") -> Dict[str, Any]:
        """
        Refresh tokens for all configured accounts via the auth server and
        update Redis. Returns a summary of per-account results.
        """
        logger.info(f"🔄 Starting token refresh for {len(self.account_ids)} account(s) (triggered_by={triggered_by})")
        results: Dict[str, Any] = {}
        success_count = 0

        for account_id in self.account_ids:
            account_result = self.refresh_token_for_account(account_id)
            results[account_id] = account_result
            if account_result.get("status") == "success":
                success_count += 1

        if success_count == len(self.account_ids):
            overall_status = "success"
        elif success_count == 0:
            overall_status = "failed"
        else:
            overall_status = "partial"

        summary = {
            "status": overall_status,
            "triggered_by": triggered_by,
            "results": results,
            "refreshed_at": format_ist_for_redis(),
            "success_count": success_count,
            "total_accounts": len(self.account_ids),
        }

        logger.info(
            f"🔁 Token refresh summary: status={overall_status}, "
            f"success_count={success_count}, total_accounts={len(self.account_ids)}"
        )
        return summary

    def _notify_data_service_reload(self) -> None:
        """
        Notify data-service (if configured) to reload tokens in memory after
        we have refreshed and written new tokens to Redis.
        """
        if not self.data_service_url:
            # Nothing to do
            return

        try:
            url = f"{self.data_service_url.rstrip('/')}/api/admin/reload-tokens"
            logger.info(f"📣 Notifying data-service to reload tokens via {url} ...")
            response = requests.post(url, timeout=5)
            if 200 <= response.status_code < 300:
                logger.info("✅ data-service reload notification succeeded")
            else:
                logger.warning(
                    f"⚠️ data-service reload notification returned HTTP "
                    f"{response.status_code}: {response.text}"
                )
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Failed to notify data-service to reload tokens: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error while notifying data-service: {e}")

    async def daily_refresh_scheduler(self) -> None:
        """
        Background task: refresh tokens once per day at 8:00 AM IST.

        This does NOT crash the service on failure; it logs errors and tries
        again the next day.
        """
        if not self.enable_refresh_scheduler:
            logger.info("⏸ Token refresh scheduler disabled via ENABLE_TOKEN_REFRESH_SCHEDULER")
            return

        logger.info("🕒 Starting daily token refresh scheduler (8:00 AM IST)")

        while True:
            try:
                now = get_ist_now()
                target = now.replace(hour=8, minute=0, second=0, microsecond=0)
                if now >= target:
                    # If we've already passed today's 8 AM, schedule for tomorrow
                    target = target + timedelta(days=1)

                sleep_seconds = (target - now).total_seconds()
                logger.info(
                    f"⏰ Next scheduled token refresh at {target.isoformat()} "
                    f"(in {int(sleep_seconds)} seconds)"
                )

                await asyncio.sleep(sleep_seconds)

                # Perform refresh for all accounts
                summary = self.refresh_tokens_for_all_accounts(triggered_by="scheduler")

                # Notify data-service so it can reload tokens in-memory
                self._notify_data_service_reload()

                logger.info(f"✅ Scheduled token refresh completed with status={summary.get('status')}")

            except asyncio.CancelledError:
                logger.info("⏹ Token refresh scheduler task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in daily_refresh_scheduler loop: {e}")
                # In case of unexpected error, wait a bit before retrying loop iteration
                await asyncio.sleep(60)
    
    def _store_token_in_redis(self, token_data: Dict[str, Any], account_id: str):
        """Store token data in Redis (per account_id, plus backward-compatible default keys)"""
        try:
            ttl_seconds = 86400  # 24h
            access_token = token_data['access_token']

            # Per-account keys
            self.redis_client.setex(self._token_key(account_id), ttl_seconds, access_token)
            
            # Store full token data
            token_info = {
                'access_token': access_token,
                'account_id': account_id,
                'expires_at': token_data.get('expires_at'),
                'source': token_data.get('source', 'account_config'),
                'success': token_data.get('success', True),
                'updated_at': format_ist_for_redis(),
                'updated_by': token_data.get('updated_by', 'startup_fetch')
            }
            
            self.redis_client.setex(self._token_info_key(account_id), ttl_seconds, json.dumps(token_info))

            # Backward compatibility: keep existing single-token keys for default account_id
            if account_id == self.default_account_id:
                self.redis_client.setex("upstox_access_token", ttl_seconds, access_token)
                self.redis_client.setex("token_info", ttl_seconds, json.dumps(token_info))
            
            logger.info(f"💾 Token stored in Redis successfully for account_id={account_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to store token in Redis for account_id={account_id}: {e}")
    
    def get_current_token(self, account_id: Optional[str] = None) -> Optional[str]:
        """Get current token from Redis (per account_id; defaults to INTERNAL_API_ACCOUNT_ID)"""
        try:
            aid = account_id or self.default_account_id
            token = self.redis_client.get(self._token_key(aid))
            if token:
                return token.decode('utf-8')

            # Backward compatibility fallback for default account
            if aid == self.default_account_id:
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
            account_id = token_data.get('account_id') or self.default_account_id
            token_data.setdefault('account_id', account_id)
            token_data.setdefault('updated_by', 'manual_update')
            token_data.setdefault('source', 'manual_update')
            self._store_token_in_redis(token_data, account_id=account_id)
            
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
    
    def get_token_status(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current token status (per account_id; defaults to INTERNAL_API_ACCOUNT_ID)"""
        try:
            aid = account_id or self.default_account_id
            token_info = self.redis_client.get(self._token_info_key(aid))
            if token_info:
                return json.loads(token_info)

            # Backward compatibility fallback for default account
            if aid == self.default_account_id:
                token_info = self.redis_client.get("token_info")
                if token_info:
                    return json.loads(token_info)
            else:
                return {
                    'status': 'no_token',
                    'message': f'No token found in Redis for account_id={aid}',
                    'account_id': aid,
                    'current_time': format_ist_for_redis()
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error getting token status: {e}',
                'account_id': (account_id or self.default_account_id),
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
    
    # Fetch token(s) on startup
    success = token_service.fetch_token_on_startup()
    if success:
        logger.info("✅ Token service started successfully")
    else:
        logger.warning("⚠️ Token service started but initial token fetch failed")

    # Start background scheduler for daily token refresh at 8 AM IST
    if token_service.enable_refresh_scheduler:
        try:
            asyncio.create_task(token_service.daily_refresh_scheduler())
        except RuntimeError as e:
            # In some environments there may be no running loop yet; log and skip scheduler
            logger.warning(f"⚠️ Could not start daily refresh scheduler: {e}")

@app.post("/token/update")
async def update_token(request: TokenUpdateRequest):
    """Update token manually"""
    try:
        # Validate token with Upstox API
        if not token_service.validate_token_with_upstox(request.access_token):
            raise HTTPException(status_code=400, detail="Token validation failed")
        
        # Update token
        account_id = request.account_id or os.getenv('INTERNAL_API_ACCOUNT_ID', 'agnidata001')
        token_data = {
            'access_token': request.access_token,
            'account_id': account_id,
            'expires_at': request.expires_at,
            'source': 'manual_update',
            'updated_by': 'manual_update',
            'success': True
        }
        
        success = token_service.update_token_manually(token_data)
        
        if success:
            return {
                "status": "success",
                "message": "Token updated successfully",
                "account_id": account_id,
                "token_expires_at": request.expires_at,
                "updated_at": format_ist_for_redis()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update token")
            
    except Exception as e:
        logger.error(f"❌ Token update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/token/refresh")
async def refresh_tokens():
    """
    Refresh tokens for all configured accounts via the Upstox auth server
    and update Redis. Also notifies data-service to reload tokens in-memory.
    """
    try:
        summary = token_service.refresh_tokens_for_all_accounts(triggered_by="endpoint")
        # Notify data-service so it can pick up the new tokens without restart
        token_service._notify_data_service_reload()

        if summary.get("status") == "failed":
            raise HTTPException(status_code=500, detail="Token refresh failed for all accounts")

        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Token refresh endpoint failed: {e}")
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

# Account-scoped endpoints (multi-account support)
@app.get("/accounts/{account_id}/token/status")
async def get_token_status_for_account(account_id: str):
    """Get token status for a specific account_id"""
    return token_service.get_token_status(account_id=account_id)


@app.get("/accounts/{account_id}/token/validate")
async def validate_token_for_account(account_id: str):
    """Validate token for a specific account_id"""
    current_token = token_service.get_current_token(account_id=account_id)
    if not current_token:
        raise HTTPException(status_code=404, detail=f"No token found for account_id={account_id}")

    is_valid = token_service.validate_token_with_upstox(current_token)
    return {
        "account_id": account_id,
        "token_valid": is_valid,
        "validated_at": format_ist_for_redis(),
        "status": "valid" if is_valid else "invalid"
    }


@app.post("/accounts/{account_id}/token/refresh")
async def refresh_token_for_account(account_id: str):
    """
    Refresh token for a specific account_id via the Upstox auth server and
    update Redis. Also notifies data-service to reload tokens.
    """
    try:
        result = token_service.refresh_token_for_account(account_id)
        # Notify data-service regardless; if this account is one of the
        # configured accounts, it will pick up the new token.
        token_service._notify_data_service_reload()

        status = result.get("status")
        if status != "success":
            error_msg = result.get("error") or f"Token refresh status={status}"
            raise HTTPException(status_code=500, detail=error_msg)

        return {
            "status": "success",
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Token refresh failed for account_id={account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/accounts/{account_id}/token/update")
async def update_token_for_account(account_id: str, request: TokenUpdateRequest):
    """Update token manually for a specific account_id"""
    try:
        if not token_service.validate_token_with_upstox(request.access_token):
            raise HTTPException(status_code=400, detail="Token validation failed")

        token_data = {
            'access_token': request.access_token,
            'account_id': account_id,
            'expires_at': request.expires_at,
            'source': 'manual_update',
            'updated_by': 'manual_update',
            'success': True
        }

        success = token_service.update_token_manually(token_data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update token")

        return {
            "status": "success",
            "message": "Token updated successfully",
            "account_id": account_id,
            "token_expires_at": request.expires_at,
            "updated_at": format_ist_for_redis()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Token update failed for account_id={account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("TOKEN_SERVICE_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
