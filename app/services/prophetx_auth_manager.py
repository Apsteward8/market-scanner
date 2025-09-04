#!/usr/bin/env python3
"""
Enhanced ProphetX Authentication Manager
Handles token caching and automatic refresh to prevent session limit issues
"""

import asyncio
import time
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ProphetXAuthManager:
    """
    Enhanced authentication manager with token caching and automatic refresh
    
    Features:
    - Separate authentication for production (data) and sandbox (betting) environments
    - Token caching to avoid re-authentication on every call
    - Automatic token refresh before expiration
    - Session management to prevent "session_num_exceed" errors
    """
    
    def __init__(self):
        from app.core.config import get_settings
        self.settings = get_settings()
        
        # Environment URLs
        self.production_base_url = "https://cash.api.prophetx.co"  # Production for data
        self.sandbox_base_url = "https://api-ss-sandbox.betprophet.co"  # Sandbox for betting
        
        # Credentials
        self.production_access_key = self.settings.prophetx_production_access_key
        self.production_secret_key = self.settings.prophetx_production_secret_key
        self.sandbox_access_key = self.settings.prophetx_sandbox_access_key
        self.sandbox_secret_key = self.settings.prophetx_sandbox_secret_key
        
        # Determine betting environment
        self.betting_environment = self.settings.prophetx_betting_environment
        
        # Authentication state for PRODUCTION (data operations)
        self.production_token: Optional[str] = None
        self.production_refresh_token: Optional[str] = None
        self.production_expire_time: Optional[int] = None
        self.production_authenticated = False
        
        # Authentication state for SANDBOX (betting operations) 
        self.sandbox_token: Optional[str] = None
        self.sandbox_refresh_token: Optional[str] = None
        self.sandbox_expire_time: Optional[int] = None
        self.sandbox_authenticated = False
        
        # Refresh settings
        self.refresh_buffer_seconds = 60  # Refresh 1 minute before expiry
        self.max_retries = 3
        
        # HTTP client
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def authenticate_production(self) -> Dict[str, Any]:
        """Authenticate with production environment for data operations"""
        logger.info("🔐 Authenticating with ProphetX Production (for data)...")
        
        url = f"{self.production_base_url}/partner/auth/login"
        payload = {
            "access_key": self.production_access_key,
            "secret_key": self.production_secret_key
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                self.production_token = token_data.get('access_token')
                self.production_refresh_token = token_data.get('refresh_token')
                self.production_expire_time = token_data.get('access_expire_time')
                
                if self.production_token:
                    self.production_authenticated = True
                    expire_dt = datetime.fromtimestamp(self.production_expire_time, tz=timezone.utc)
                    logger.info(f"✅ Production authenticated! Expires: {expire_dt}")
                    
                    return {
                        "success": True,
                        "environment": "production",
                        "expires_at": expire_dt.isoformat()
                    }
                else:
                    raise Exception("No access token in response")
            else:
                error_text = await response.aread()
                raise Exception(f"HTTP {response.status_code}: {error_text.decode()}")
                
        except Exception as e:
            logger.error(f"❌ Production authentication failed: {e}")
            self.production_authenticated = False
            raise
    
    async def authenticate_sandbox(self) -> Dict[str, Any]:
        """Authenticate with sandbox environment for betting operations"""
        logger.info("🔐 Authenticating with ProphetX Sandbox (for betting)...")
        
        url = f"{self.sandbox_base_url}/partner/auth/login"
        payload = {
            "access_key": self.sandbox_access_key,
            "secret_key": self.sandbox_secret_key
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                self.sandbox_token = token_data.get('access_token')
                self.sandbox_refresh_token = token_data.get('refresh_token')
                self.sandbox_expire_time = token_data.get('access_expire_time')
                
                if self.sandbox_token:
                    self.sandbox_authenticated = True
                    expire_dt = datetime.fromtimestamp(self.sandbox_expire_time, tz=timezone.utc)
                    logger.info(f"✅ Sandbox authenticated! Expires: {expire_dt}")
                    
                    return {
                        "success": True,
                        "environment": "sandbox", 
                        "expires_at": expire_dt.isoformat()
                    }
                else:
                    raise Exception("No access token in response")
            else:
                error_text = await response.aread()
                raise Exception(f"HTTP {response.status_code}: {error_text.decode()}")
                
        except Exception as e:
            logger.error(f"❌ Sandbox authentication failed: {e}")
            self.sandbox_authenticated = False
            raise
    
    async def authenticate_both(self) -> Dict[str, Any]:
        """Authenticate with both environments"""
        logger.info("🔐 Authenticating with both ProphetX environments...")
        
        results = {}
        
        try:
            # Authenticate production (for data operations)
            prod_result = await self.authenticate_production()
            results["production"] = prod_result
        except Exception as e:
            results["production"] = {"success": False, "error": str(e)}
        
        try:
            # Authenticate sandbox (for betting operations)
            sandbox_result = await self.authenticate_sandbox() 
            results["sandbox"] = sandbox_result
        except Exception as e:
            results["sandbox"] = {"success": False, "error": str(e)}
        
        both_successful = (
            results.get("production", {}).get("success", False) and
            results.get("sandbox", {}).get("success", False)
        )
        
        logger.info(f"🎯 Authentication complete - Both environments: {'✅' if both_successful else '⚠️'}")
        
        return {
            "success": both_successful,
            "results": results,
            "message": "Both environments authenticated" if both_successful else "Some authentication failures"
        }
    
    def _is_token_expired(self, expire_time: Optional[int], buffer_seconds: int = None) -> bool:
        """Check if token is expired or will expire soon"""
        if not expire_time:
            return True
        
        buffer = buffer_seconds or self.refresh_buffer_seconds
        current_time = time.time()
        return current_time >= (expire_time - buffer)
    
    async def get_production_headers(self) -> Dict[str, str]:
        """Get production auth headers, refreshing token if needed"""
        
        # Check if we need to authenticate
        if not self.production_authenticated or self._is_token_expired(self.production_expire_time):
            logger.info("🔄 Production token expired or missing - re-authenticating...")
            await self.authenticate_production()
        
        return {
            'Authorization': f'Bearer {self.production_token}',
            'Content-Type': 'application/json'
        }
    
    async def get_sandbox_headers(self) -> Dict[str, str]:
        """Get sandbox auth headers, refreshing token if needed"""
        
        # Check if we need to authenticate
        if not self.sandbox_authenticated or self._is_token_expired(self.sandbox_expire_time):
            logger.info("🔄 Sandbox token expired or missing - re-authenticating...")
            await self.authenticate_sandbox()
        
        return {
            'Authorization': f'Bearer {self.sandbox_token}',
            'Content-Type': 'application/json'
        }
    
    async def get_data_headers(self) -> Dict[str, str]:
        """Get headers for data operations (always production)"""
        return await self.get_production_headers()
    
    async def get_betting_headers(self) -> Dict[str, str]:
        """Get headers for betting operations (based on PROPHETX_BETTING_ENVIRONMENT)"""
        if self.betting_environment == "production":
            return await self.get_production_headers()
        else:
            return await self.get_sandbox_headers()
    
    def get_data_base_url(self) -> str:
        """Get base URL for data operations (always production)"""
        return self.production_base_url
    
    def get_betting_base_url(self) -> str:
        """Get base URL for betting operations (based on environment setting)"""
        if self.betting_environment == "production":
            return self.production_base_url
        else:
            return self.sandbox_base_url
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication status for both environments"""
        now = time.time()
        
        production_status = {
            "authenticated": self.production_authenticated,
            "expires_at": datetime.fromtimestamp(self.production_expire_time, tz=timezone.utc).isoformat() if self.production_expire_time else None,
            "expires_in_minutes": (self.production_expire_time - now) / 60 if self.production_expire_time else 0,
            "is_expired": self._is_token_expired(self.production_expire_time)
        }
        
        sandbox_status = {
            "authenticated": self.sandbox_authenticated,
            "expires_at": datetime.fromtimestamp(self.sandbox_expire_time, tz=timezone.utc).isoformat() if self.sandbox_expire_time else None,
            "expires_in_minutes": (self.sandbox_expire_time - now) / 60 if self.sandbox_expire_time else 0,
            "is_expired": self._is_token_expired(self.sandbox_expire_time)
        }
        
        return {
            "production": production_status,
            "sandbox": sandbox_status,
            "betting_environment": self.betting_environment,
            "data_environment": "production"
        }

# Global authentication manager instance
auth_manager = ProphetXAuthManager()