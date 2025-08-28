#!/usr/bin/env python3
"""
ProphetX Service for Market Scanner
Handles authentication and API calls for fetching games and market data
"""

import httpx
import time
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CachedData:
    """Represents cached data with expiration"""
    data: Any
    cached_at: datetime
    expires_at: datetime
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

class ProphetXService:
    """ProphetX API service for market scanning"""
    
    def __init__(self):
        from app.core.config import get_settings
        self.settings = get_settings()
        
        # API Configuration - Always use production for data fetching
        self.base_url = "https://cash.api.prophetx.co"
        
        # Use production credentials for data fetching
        self.access_key = self.settings.prophetx_production_access_key
        self.secret_key = self.settings.prophetx_production_secret_key
        
        # Authentication state
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_expire_time: Optional[int] = None
        self.refresh_expire_time: Optional[int] = None
        self.is_authenticated = False
        
        # Caching for sport events (1 hour cache)
        self.sport_events_cache: Dict[str, CachedData] = {}
        
        # HTTP client with timeout
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate with ProphetX API using production credentials"""
        logger.info("🔐 Authenticating with ProphetX (Production for data fetching)...")
        
        url = f"{self.base_url}/partner/auth/login"
        payload = {
            "access_key": self.access_key,
            "secret_key": self.secret_key
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')
                self.access_expire_time = token_data.get('access_expire_time')
                self.refresh_expire_time = token_data.get('refresh_expire_time')
                
                if self.access_token and self.refresh_token:
                    self.is_authenticated = True
                    
                    access_expire_dt = datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc)
                    logger.info(f"✅ ProphetX authentication successful! Token expires: {access_expire_dt}")
                    
                    return {
                        "success": True,
                        "access_expires_at": access_expire_dt.isoformat(),
                        "refresh_expires_at": datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc).isoformat()
                    }
                else:
                    raise Exception("Missing tokens in response")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ ProphetX authentication failed: {e}")
            self.is_authenticated = False
            raise Exception(f"Authentication failed: {e}")
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers, refreshing token if needed"""
        
        # Check if we need to authenticate or refresh
        now = time.time()
        
        if not self.is_authenticated or not self.access_token:
            await self.authenticate()
        elif self.access_expire_time and now >= (self.access_expire_time - 120):  # Refresh 2 min early
            await self.refresh_access_token()
            
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            await self.authenticate()
            return {"success": True, "refreshed": True}
            
        logger.info("🔄 Refreshing ProphetX access token...")
        
        url = f"{self.base_url}/partner/auth/refresh"
        payload = {"refresh_token": self.refresh_token}
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                self.access_token = token_data.get('access_token')
                self.access_expire_time = token_data.get('access_expire_time')
                
                logger.info("✅ Token refresh successful!")
                return {"success": True, "refreshed": True}
            else:
                # Refresh failed, re-authenticate
                logger.warning("Token refresh failed, re-authenticating...")
                await self.authenticate()
                return {"success": True, "refreshed": True}
                
        except Exception as e:
            logger.error(f"Token refresh error: {e}, re-authenticating...")
            await self.authenticate()
            return {"success": True, "refreshed": True}
    
    async def get_sport_events(self, tournament_id: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get sport events for a tournament with 1-hour caching
        
        Args:
            tournament_id: Tournament ID (27653 for NCAAF)
            use_cache: Whether to use cached data if available
            
        Returns:
            Dict with sport events data
        """
        cache_key = f"sport_events_{tournament_id}"
        
        # Check cache first
        if use_cache and cache_key in self.sport_events_cache:
            cached = self.sport_events_cache[cache_key]
            if not cached.is_expired():
                logger.info(f"📋 Using cached sport events for tournament {tournament_id}")
                return cached.data
        
        logger.info(f"🏈 Fetching sport events for tournament {tournament_id}...")
        
        url = f"{self.base_url}/partner/mm/get_sport_events"
        params = {"tournament_id": tournament_id}
        headers = await self.get_auth_headers()
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Cache for 1 hour
                now = datetime.now(timezone.utc)
                cached_data = CachedData(
                    data=data,
                    cached_at=now,
                    expires_at=now + timedelta(hours=1)
                )
                self.sport_events_cache[cache_key] = cached_data
                
                events_count = len(data.get('data', {}).get('sport_events', []))
                logger.info(f"✅ Retrieved {events_count} sport events for tournament {tournament_id}")
                
                return data
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Error fetching sport events: {e}")
            raise Exception(f"Failed to fetch sport events: {e}")
    
    async def get_multiple_markets(self, event_ids: List[str]) -> Dict[str, Any]:
        """
        Get market data for multiple events
        
        Args:
            event_ids: List of event IDs to fetch markets for
            
        Returns:
            Dict with market data for each event
        """
        if not event_ids:
            return {"data": {}}
            
        logger.info(f"📊 Fetching market data for {len(event_ids)} events...")
        
        url = f"{self.base_url}/partner/v2/mm/get_multiple_markets"
        params = {"event_ids": ",".join(event_ids)}
        headers = await self.get_auth_headers()
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Log response size for monitoring
                response_text = response.text
                response_size_kb = len(response_text) / 1024
                logger.info(f"✅ Retrieved market data: {response_size_kb:.1f}KB for {len(event_ids)} events")
                
                return data
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Error fetching market data: {e}")
            raise Exception(f"Failed to fetch market data: {e}")
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication status"""
        if not self.is_authenticated:
            return {"authenticated": False, "message": "Not authenticated"}
            
        now = time.time()
        access_expires_in = self.access_expire_time - now if self.access_expire_time else 0
        refresh_expires_in = self.refresh_expire_time - now if self.refresh_expire_time else 0
        
        return {
            "authenticated": True,
            "environment": "production",
            "access_expires_in_seconds": int(access_expires_in),
            "refresh_expires_in_seconds": int(refresh_expires_in),
            "needs_refresh_soon": access_expires_in < 300,  # Less than 5 minutes
            "cache_stats": {
                "sport_events_cached": len(self.sport_events_cache),
                "cache_keys": list(self.sport_events_cache.keys())
            }
        }
    
    async def clear_cache(self):
        """Clear all cached data"""
        self.sport_events_cache.clear()
        logger.info("🧹 ProphetX cache cleared")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

# Global instance
prophetx_service = ProphetXService()