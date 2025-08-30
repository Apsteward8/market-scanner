#!/usr/bin/env python3
"""
ProphetX Service for Market Scanner
Handles authentication and API calls for fetching games and market data
DUAL ENVIRONMENT SUPPORT:
- Data operations (market scanning) → Production environment
- Betting operations → Configurable environment (sandbox/production)
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
    """ProphetX API service for market scanning with dual environment support"""
    
    def __init__(self):
        from app.core.config import get_settings
        self.settings = get_settings()
        
        # DUAL ENVIRONMENT SETUP - FIXED
        # Data operations (scanning, market data) - Always Production
        self.data_base_url = self.settings.data_base_url
        self.data_access_key, self.data_secret_key = self.settings.data_credentials
        
        # Betting operations - Configurable (sandbox/production)  
        self.betting_base_url = self.settings.betting_base_url
        self.betting_access_key, self.betting_secret_key = self.settings.betting_credentials
        
        # For backwards compatibility with existing code
        self.base_url = self.data_base_url  # Default to data URL for most calls
        self.access_key = self.data_access_key
        self.secret_key = self.data_secret_key
        
        # Environment info
        self.data_env = "production"
        self.betting_env = self.settings.prophetx_betting_environment
        
        logger.info(f"🔧 ProphetX environments: Data={self.data_env}, Betting={self.betting_env}")
        
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
        """Authenticate with ProphetX API - authenticate both environments"""
        logger.info(f"🔐 Authenticating with ProphetX environments...")
        
        # For simplicity, authenticate with production for data operations
        # This maintains compatibility with existing scanning functionality
        url = f"{self.data_base_url}/partner/auth/login"
        payload = {
            "access_key": self.data_access_key,
            "secret_key": self.data_secret_key
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
                        "refresh_expires_at": datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc).isoformat(),
                        "environment": f"{self.data_env} (primary)"
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
        
        url = f"{self.data_base_url}/partner/auth/refresh"  # Use data environment for refresh
        payload = {"refresh_token": self.refresh_token}
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                self.access_token = token_data.get('access_token')
                self.access_expire_time = token_data.get('access_expire_time')
                
                logger.info("✅ Token refresh successful!")
                return {"success": True}
            else:
                logger.warning("🔄 Refresh failed, re-authenticating...")
                return await self.authenticate()
                
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return await self.authenticate()
    
    async def authenticate_betting_environment(self) -> Dict[str, str]:
        """Get authentication headers specifically for betting operations"""
        logger.info(f"🎯 Authenticating for betting environment ({self.betting_env})...")
        
        url = f"{self.betting_base_url}/partner/auth/login"
        payload = {
            "access_key": self.betting_access_key,
            "secret_key": self.betting_secret_key
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                betting_token = token_data.get('access_token')
                
                if betting_token:
                    logger.info(f"✅ Betting environment authenticated: {self.betting_env}")
                    return {
                        'Authorization': f'Bearer {betting_token}',
                        'Content-Type': 'application/json'
                    }
                else:
                    raise Exception("Missing betting token in response")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Betting authentication failed: {e}")
            raise Exception(f"Betting authentication failed: {e}")
    
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
        """Get market data for multiple events from production data environment"""
        if not event_ids:
            return {"data": {}}
            
        logger.info(f"📊 Fetching market data for {len(event_ids)} events from production...")
        
        # FIXED: Use data environment for market data
        url = f"{self.data_base_url}/partner/v2/mm/get_multiple_markets"
        params = {"event_ids": ",".join(event_ids)}
        headers = await self.get_auth_headers()  # This will use the data environment token
        
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
    
    async def get_account_balance(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get current account balance from betting environment"""
        try:
            logger.info("💰 Fetching account balance from betting environment...")
            
            # Make sure we're authenticated
            if not self.is_authenticated:
                auth_result = await self.authenticate()
                if not auth_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to authenticate with ProphetX",
                        "auth_error": auth_result.get("error")
                    }
            
            # FIXED: Use betting environment for balance checks
            url = f"{self.betting_base_url}/partner/mm/get_balance"
            headers = await self.authenticate_betting_environment()  # Get betting environment auth
            
            response = await self.client.get(url, headers=headers, timeout=30.0)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Balance API returned status {response.status_code}",
                    "response_text": response.text[:500] if response.text else None
                }
            
            data = response.json()
            balance_data = data.get('data', {})
            
            # Parse balance information properly
            available_balance = float(balance_data.get('balance', 0))
            unmatched_wager_balance = float(balance_data.get('unmatched_wager_balance', 0))
            total_balance = available_balance + unmatched_wager_balance
            
            balance_info = BalanceInfo(
                total=total_balance,
                available=available_balance,
                unmatched_wager_balance=unmatched_wager_balance,
                unmatched_wager_balance_status=balance_data.get('unmatched_wager_balance_status', 'unknown'),
                unmatched_wager_last_synced_at=balance_data.get('unmatched_wager_last_synced_at', ''),
                retrieved_at=datetime.now(timezone.utc)
            )
            
            logger.info(f"✅ Balance retrieved: ${balance_info.available:.2f} available, ${balance_info.unmatched_wager_balance:.2f} tied up in unmatched bets")
            
            return {
                "success": True,
                "data": {
                    "total": balance_info.total,
                    "available": balance_info.available,
                    "unmatched_wager_balance": balance_info.unmatched_wager_balance,
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
        """Check if we have sufficient funds for a wager"""
        try:
            # Get current balance
            balance_result = await self.get_account_balance()
            
            if not balance_result.get("success"):
                return {
                    "sufficient_funds": False,
                    "error": f"Failed to get balance: {balance_result.get('error')}"
                }
            
            balance_data = balance_result["data"]
            available_balance = balance_data["available"]
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
                "total_balance": balance_data["total"],
                "available_balance": available_balance,
                "unmatched_balance": balance_data["unmatched_wager_balance"],
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
    
    async def place_bet(self, line_id: str, odds: int, stake: float, external_id: str) -> Dict[str, Any]:
        """
        Place bet using correct endpoint and betting environment
        FIXED: Uses /partner/mm/place_wager (not place_bet) and betting environment
        """
        try:
            logger.info(f"🎯 ProphetX: Placing bet on line {line_id} @ {odds:+d} for ${stake} in {self.betting_env}")
            
            # Make sure we're authenticated
            if not self.is_authenticated:
                auth_result = await self.authenticate()
                if not auth_result.get("success"):
                    return {
                        "success": False,
                        "error": "Failed to authenticate with ProphetX"
                    }
            
            # FIXED: Use correct endpoint and betting environment
            url = f"{self.betting_base_url}/partner/mm/place_wager"
            headers = await self.authenticate_betting_environment()  # Get betting environment auth
            
            bet_data = {
                "line_id": line_id,
                "odds": odds,
                "stake": stake,
                "external_id": external_id
            }
            
            logger.info(f"   📤 Betting API call: {url}")
            logger.info(f"   📋 Bet data: line_id={line_id}, odds={odds:+d}, stake=${stake}, external_id={external_id}")
            
            response = await self.client.post(url, headers=headers, json=bet_data, timeout=30.0)
            
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
                        "line_id": line_id,
                        "environment": self.betting_env
                    }
                else:
                    logger.error(f"   ❌ ProphetX returned success=false: {data.get('error', 'Unknown error')}")
                    return {
                        "success": False,
                        "error": data.get("error", "ProphetX returned success=false"),
                        "environment": self.betting_env
                    }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ ProphetX API returned status {response.status_code}: {error_text}")
                return {
                    "success": False,
                    "error": f"ProphetX API returned status {response.status_code}",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Error placing bet: {e}")
            return {
                "success": False,
                "error": f"Exception placing bet: {str(e)}",
                "environment": self.betting_env
            }
    
    # Wager history methods - use betting environment since that's where our bets are
    async def get_all_active_wagers(self) -> List[Dict[str, Any]]:
        """Get all active wagers from betting environment"""
        logger.info("📋 Fetching all active wagers from betting environment...")
        
        url = f"{self.betting_base_url}/partner/mm/get_wager_histories"
        headers = await self.authenticate_betting_environment()  # Get betting environment auth
        
        # Get wagers from the last 30 days
        to_timestamp = int(time.time())
        from_timestamp = to_timestamp - (30 * 24 * 60 * 60)
        
        params = {
            "from": from_timestamp,
            "to": to_timestamp,
            "limit": 1000
        }
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    all_wagers = data.get("wager_histories", [])
                    # Filter to only active (unmatched) wagers
                    active_wagers = [w for w in all_wagers if w.get("matching_status") == "unmatched"]
                    
                    logger.info(f"✅ Retrieved {len(active_wagers)} active wagers (from {len(all_wagers)} total)")
                    return active_wagers
                else:
                    logger.error(f"❌ Error getting wager histories: {data.get('error')}")
                    return []
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching active wagers: {e}")
            return []
    
    async def get_matched_bets(self) -> List[Dict[str, Any]]:
        """Get matched bets from betting environment"""
        logger.info("🎯 Fetching matched bets from betting environment...")
        
        url = f"{self.betting_base_url}/partner/mm/get_matched_bets"
        headers = await self.authenticate_betting_environment()  # Get betting environment auth
        
        # Get matches from the last 7 days
        to_timestamp = int(time.time())
        from_timestamp = to_timestamp - (7 * 24 * 60 * 60)
        
        params = {
            "from": from_timestamp,
            "to": to_timestamp,
            "limit": 500
        }
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    matches = data.get("matched_bets", [])
                    logger.info(f"✅ Retrieved {len(matches)} matched bets")
                    return matches
                else:
                    logger.error(f"❌ Error getting matched bets: {data.get('error')}")
                    return []
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching matched bets: {e}")
            return []
    
    async def get_wager_by_id(self, wager_id: str) -> Optional[Dict[str, Any]]:
        """Get specific wager by ID from betting environment"""
        logger.info(f"🔍 Fetching wager {wager_id} from betting environment...")
        
        url = f"{self.betting_base_url}/partner/mm/get_wager_by_id"
        headers = await self.authenticate_betting_environment()  # Get betting environment auth
        
        params = {"wager_id": wager_id}
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    wager = data.get("wager")
                    logger.info(f"✅ Retrieved wager {wager_id}")
                    return wager
                else:
                    logger.warning(f"⚠️ Wager {wager_id} not found: {data.get('error')}")
                    return None
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error fetching wager {wager_id}: {e}")
            return None
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication status"""
        if not self.is_authenticated:
            return {"authenticated": False, "message": "Not authenticated"}
            
        now = time.time()
        access_expires_in = self.access_expire_time - now if self.access_expire_time else 0
        refresh_expires_in = self.refresh_expire_time - now if self.refresh_expire_time else 0
        
        return {
            "authenticated": True,
            "environment": f"{self.betting_env} (betting)",
            "data_environment": f"{self.data_env}",
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

# Create global service instance
prophetx_service = ProphetXService()