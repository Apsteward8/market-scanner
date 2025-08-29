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
import httpx

logger = logging.getLogger(__name__)

@dataclass
class CachedData:
    """Represents cached data with expiration"""
    data: Any
    cached_at: datetime
    expires_at: datetime
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at
    
@dataclass
class BalanceInfo:
    """Account balance information from ProphetX"""
    total: float
    available: float
    unmatched_wager_balance: float
    unmatched_wager_balance_status: str
    unmatched_wager_last_synced_at: str
    retrieved_at: datetime

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

    async def get_account_balance(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get current account balance from ProphetX
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh balance
            
        Returns:
            Dict with balance information and success status
        """
        try:
            logger.info("💰 Fetching account balance from ProphetX...")
            
            # Make sure we're authenticated
            if not self.is_authenticated:
                auth_result = await self.authenticate()
                if not auth_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to authenticate with ProphetX",
                        "auth_error": auth_result.get("error")
                    }
            
            # Make API call to get balance
            url = f"{self.base_url}/partner/mm/get_balance"
            headers = await self.get_auth_headers()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30.0)
                
                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Balance API returned status {response.status_code}",
                        "response_text": response.text[:500] if response.text else None
                    }
                
                data = response.json()
                balance_data = data.get('data', {})
                
                # CORRECTED: Parse balance information properly
                # The 'balance' field from ProphetX IS the available balance
                available_balance = float(balance_data.get('balance', 0))
                unmatched_wager_balance = float(balance_data.get('unmatched_wager_balance', 0))
                # Total balance would be available + unmatched (but ProphetX doesn't provide this)
                total_balance = available_balance + unmatched_wager_balance
                
                balance_info = BalanceInfo(
                    total=total_balance,
                    available=available_balance,  # This is what we can actually bet with
                    unmatched_wager_balance=unmatched_wager_balance,
                    unmatched_wager_balance_status=balance_data.get('unmatched_wager_balance_status', 'unknown'),
                    unmatched_wager_last_synced_at=balance_data.get('unmatched_wager_last_synced_at', ''),
                    retrieved_at=datetime.now(timezone.utc)
                )
                
                logger.info(f"✅ Balance retrieved: ${balance_info.available:.2f} available, ${balance_info.unmatched_wager_balance:.2f} tied up in unmatched bets")
                
                return {
                    "success": True,
                    "data": {
                        "total": balance_info.total,                    # Available + Unmatched (calculated)
                        "available": balance_info.available,           # What we can bet with
                        "unmatched_wager_balance": balance_info.unmatched_wager_balance,  # Tied up in bets
                        "unmatched_status": balance_info.unmatched_wager_balance_status,
                        "last_synced": balance_info.unmatched_wager_last_synced_at,
                        "retrieved_at": balance_info.retrieved_at.isoformat()
                    },
                    "balance_info": balance_info
                }
                
        except Exception as e:
            logger.error(f"❌ Error getting account balance: {e}")
            return {
                "success": False,
                "error": f"Balance check exception: {str(e)}"
            }

    async def check_sufficient_funds(self, required_amount: float, safety_buffer: float = 10.0) -> Dict[str, Any]:
        """
        Check if we have sufficient funds for a wager
        
        Args:
            required_amount: Amount needed for the wager
            safety_buffer: Additional buffer to maintain
            
        Returns:
            Dict with fund sufficiency check results
        """
        try:
            # Get current balance
            balance_result = await self.get_account_balance()
            
            if not balance_result.get("success"):
                return {
                    "sufficient_funds": False,
                    "error": f"Failed to get balance: {balance_result.get('error')}"
                }
            
            balance_data = balance_result["data"]
            available_balance = balance_data["available"]  # This is what we can actually bet with
            total_required = required_amount + safety_buffer
            
            sufficient = available_balance >= total_required
            
            logger.info(f"💰 Funds check: ${available_balance:.2f} available, ${total_required:.2f} required (${required_amount:.2f} + ${safety_buffer:.2f} buffer)")
            logger.info(f"   📊 Additional info: ${balance_data['unmatched_wager_balance']:.2f} tied up in unmatched bets")
            
            if sufficient:
                logger.info("✅ FUNDS CHECK PASSED: Sufficient funds available")
            else:
                logger.warning(f"❌ FUNDS CHECK FAILED: Need ${total_required - available_balance:.2f} more")
            
            return {
                "sufficient_funds": sufficient,
                "total_balance": balance_data["total"],                    # Available + unmatched
                "available_balance": available_balance,                   # What we can bet with
                "unmatched_balance": balance_data["unmatched_wager_balance"],  # Tied up in bets
                "required_amount": required_amount,
                "safety_buffer": safety_buffer,
                "total_required": total_required,
                "remaining_after_wager": available_balance - required_amount if sufficient else None,
                "shortfall": total_required - available_balance if not sufficient else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking sufficient funds: {e}")
            return {
                "sufficient_funds": False,
                "error": f"Funds check exception: {str(e)}"
            }

# ============================================================================  
# IF YOU DON'T ALREADY HAVE place_bet and cancel_bet methods, add these:
# (If you already have these methods, just ensure they return the expected format)
# ============================================================================

    async def place_bet(self, line_id: str, odds: int, stake: float, external_id: str) -> Dict[str, Any]:
        """
        Place a bet on ProphetX
        
        Args:
            line_id: ProphetX line/market ID
            odds: Odds to bet at
            stake: Amount to wager
            external_id: External tracking ID
            
        Returns:
            Dict with bet placement results
        """
        try:
            logger.info(f"🎯 ProphetX: Placing bet on line {line_id} @ {odds:+d} for ${stake}")
            
            # Make sure we're authenticated
            if not self.is_authenticated:
                auth_result = await self.authenticate()
                if not auth_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to authenticate with ProphetX"
                    }
            
            # Prepare bet placement data
            url = f"{self.base_url}/partner/v2/mm/place_bet"
            headers = await self.get_auth_headers()
            
            bet_data = {
                "line_id": line_id,
                "odds": odds,
                "stake": stake,
                "external_id": external_id
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=bet_data, timeout=30.0)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("success"):
                        bet_info = data.get("data", {})
                        logger.info(f"✅ Bet placed successfully: ProphetX ID {bet_info.get('bet_id')}")
                        
                        return {
                            "success": True,
                            "bet_id": bet_info.get("bet_id"),
                            "prophetx_bet_id": bet_info.get("bet_id"),
                            "external_id": external_id,
                            "status": bet_info.get("status", "placed"),
                            "odds": odds,
                            "stake": stake,
                            "line_id": line_id
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("error", "ProphetX returned success=false")
                        }
                else:
                    return {
                        "success": False,
                        "error": f"ProphetX API returned status {response.status_code}",
                        "response_text": response.text[:500]
                    }
                    
        except Exception as e:
            logger.error(f"❌ Error placing bet: {e}")
            return {
                "success": False,
                "error": f"Bet placement exception: {str(e)}"
            }

    async def cancel_bet(self, bet_id: str) -> Dict[str, Any]:
        """
        Cancel a bet on ProphetX
        
        Args:
            bet_id: ProphetX bet ID to cancel
            
        Returns:
            Dict with cancellation results
        """
        try:
            logger.info(f"🔄 ProphetX: Attempting to cancel bet {bet_id}")
            
            # Make sure we're authenticated
            if not self.is_authenticated:
                auth_result = await self.authenticate()
                if not auth_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to authenticate with ProphetX"
                    }
            
            # Cancel the bet
            url = f"{self.base_url}/partner/v2/mm/cancel_bet"
            headers = await self.get_auth_headers()
            
            cancel_data = {"bet_id": bet_id}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=cancel_data, timeout=30.0)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("success"):
                        logger.info(f"✅ Bet {bet_id} cancelled successfully")
                        return {
                            "success": True,
                            "bet_id": bet_id,
                            "status": data.get("data", {}).get("status", "cancelled")
                        }
                    else:
                        return {
                            "success": False,
                            "error": data.get("error", "ProphetX returned success=false")
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Cancel API returned status {response.status_code}",
                        "response_text": response.text[:500]
                    }
                    
        except Exception as e:
            logger.error(f"❌ Error cancelling bet: {e}")
            return {
                "success": False,
                "error": f"Bet cancellation exception: {str(e)}"
            }

# Global instance
prophetx_service = ProphetXService()