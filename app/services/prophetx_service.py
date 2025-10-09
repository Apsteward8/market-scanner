#!/usr/bin/env python3
"""
ProphetX Service for Market Scanner - ENHANCED WITH CANCELLATION METHODS
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
import asyncio

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

        # Import the global auth manager
        from app.services.prophetx_auth_manager import auth_manager
        self.auth_manager = auth_manager
        
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
        # self.client = httpx.AsyncClient(timeout=30.0)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0)  # 30s total, 10s connect
        )

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the service by authenticating both environments"""
        logger.info("🚀 Initializing ProphetX service...")
        return await self.auth_manager.authenticate_both()

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate with both environments"""
        return await self.auth_manager.authenticate_both()
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for data operations"""
        return await self.auth_manager.get_data_headers()
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication status"""
        return self.auth_manager.get_auth_status()
    
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
        
        try:
            # Use cached headers (no authentication call)
            headers = await self.auth_manager.get_data_headers()
            base_url = self.auth_manager.get_data_base_url()
            
            url = f"{base_url}/partner/mm/get_sport_events"
            params = {"tournament_id": tournament_id}
            
            response = await self.client.get(url, headers=headers, params=params)
            
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
        Get market data for multiple events from production data environment
        Automatically chunks requests to stay within 65-event API limit
        """
        if not event_ids:
            return {"data": {}}
            
        CHUNK_SIZE = 65  # ProphetX API limit for get_multiple_markets
        
        # Split event_ids into chunks of 65
        event_chunks = [event_ids[i:i + CHUNK_SIZE] for i in range(0, len(event_ids), CHUNK_SIZE)]
        
        logger.info(f"📊 Fetching market data for {len(event_ids)} events in {len(event_chunks)} batches of up to {CHUNK_SIZE}...")
        
        # Collect results from all chunks
        combined_data = {"data": {}}
        total_events_processed = 0
        
        try:
            # Use cached headers (no authentication call)
            headers = await self.auth_manager.get_data_headers()
            base_url = self.auth_manager.get_data_base_url()
            
            for chunk_idx, chunk in enumerate(event_chunks, 1):
                logger.info(f"📦 Processing batch {chunk_idx}/{len(event_chunks)} ({len(chunk)} events)...")
                
                url = f"{base_url}/partner/v2/mm/get_multiple_markets"
                
                # Convert event_ids to comma-separated string
                event_ids_str = ','.join(chunk)
                params = {"event_ids": event_ids_str}
                
                response = await self.client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Merge chunk data into combined results
                    if "data" in data and isinstance(data["data"], dict):
                        combined_data["data"].update(data["data"])
                        total_events_processed += len(chunk)
                    
                    # Log response size for monitoring
                    response_text = response.text
                    response_size_kb = len(response_text) / 1024
                    logger.info(f"✅ Batch {chunk_idx} complete: {response_size_kb:.1f}KB for {len(chunk)} events")
                    
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"❌ Batch {chunk_idx} failed: {error_msg}")
                    # Continue with other chunks rather than failing completely
                    continue
                
                # Small delay between chunks to be nice to the API
                if chunk_idx < len(event_chunks):
                    await asyncio.sleep(0.1)
            
            logger.info(f"✅ All batches complete: Retrieved market data for {total_events_processed}/{len(event_ids)} events")
            
            return combined_data
            
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
            
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            logger.info(f"🎯 Using {self.auth_manager.betting_environment} environment for balance check")
            
            url = f"{base_url}/partner/mm/get_balance"
            
            response = await self.client.get(url, headers=headers)
            
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
            
            # Use cached headers for betting environment (no authentication call!)
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/place_wager"
            
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
                
                # DEBUG: Log the full response to understand the structure
                logger.info(f"   📋 Full ProphetX response: {data}")
                
                # ProphetX response might not have nested "success" field
                # Check both possible structures
                if data.get("success") or (not data.get("error") and data.get("data")):
                    wager_data = data.get("data", {}).get("wager", {})
                    bet_id = wager_data.get("id")
                    
                    logger.info(f"✅ Bet placed successfully: ProphetX ID {bet_id}")
                    
                    return {
                        "success": True,
                        "bet_id": bet_id,
                        "prophetx_bet_id": bet_id,
                        "external_id": external_id,
                        "status": wager_data.get("status", "placed"),
                        "odds": odds,
                        "stake": stake,
                        "line_id": line_id,
                        "environment": self.betting_env
                    }
                else:
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    logger.error(f"   ❌ ProphetX returned error: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "environment": self.betting_env,
                        "full_response": data  # For debugging
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

    async def place_multiple_wagers(self, wagers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Place multiple wagers using ProphetX's /mm/place_multiple_wagers endpoint
        Automatically chunks requests to stay within 20-wager API limit
        
        IMPORTANT: Uses betting environment (sandbox) not data environment (production)
        
        Args:
            wagers: List of wager dicts with keys: external_id, line_id, odds, stake
            
        Returns:
            Dict with success/failed wagers mapped by external_id for easy lookup
        """
        CHUNK_SIZE = 20  # ProphetX API limit
        
        try:
            # Split wagers into chunks of 20
            wager_chunks = [wagers[i:i + CHUNK_SIZE] for i in range(0, len(wagers), CHUNK_SIZE)]
            
            logger.info(f"💰 Placing {len(wagers)} wagers in {len(wager_chunks)} batches of up to {CHUNK_SIZE}...")
            
            # Collect results from all chunks
            all_success_wagers = {}
            all_failed_wagers = {}
            total_successful = 0
            total_failed = 0
            
            for chunk_idx, chunk in enumerate(wager_chunks, 1):
                logger.info(f"📦 Processing batch {chunk_idx}/{len(wager_chunks)} ({len(chunk)} wagers)...")
                
                # FIXED: Use betting headers and betting URL (sandbox environment)
                headers = await self.auth_manager.get_betting_headers()
                url = f"{self.auth_manager.get_betting_base_url()}/partner/mm/place_multiple_wagers"
                
                logger.info(f"🎯 Using betting environment: {self.betting_env}")
                
                payload = {"data": chunk}
                
                response = await self.client.post(url, headers=headers, json=payload, timeout=30.0)
                
                if response.status_code in [200, 201]:
                    data = response.json().get("data", {})
                    
                    # Process successful wagers from this chunk
                    for wager in data.get("succeed_wagers", []):
                        external_id = wager.get("external_id")
                        if external_id:
                            all_success_wagers[external_id] = {
                                "success": True,
                                "bet_id": wager.get("id"),
                                "prophetx_bet_id": wager.get("id"),
                                "external_id": external_id,
                                "line_id": wager.get("line_id"),
                                "odds": wager.get("odds"),
                                "stake": wager.get("stake"),
                                "matched_stake": wager.get("matched_stake", 0),
                                "unmatched_stake": wager.get("unmatched_stake", 0),
                                "status": wager.get("status"),
                                "matching_status": wager.get("matching_status"),
                                "profit": wager.get("profit"),
                                "response_data": wager
                            }
                            total_successful += 1
                    
                    # Process failed wagers from this chunk
                    for failed in data.get("failed_wagers", []):
                        request_data = failed.get("request", {})
                        external_id = request_data.get("external_id")
                        if external_id:
                            all_failed_wagers[external_id] = {
                                "success": False,
                                "external_id": external_id,
                                "error": failed.get("error"),
                                "message": failed.get("message"),
                                "index": failed.get("index"),
                                "request": request_data,
                                "chunk": chunk_idx
                            }
                            total_failed += 1
                    
                    logger.info(f"✅ Batch {chunk_idx} complete: {len(data.get('succeed_wagers', []))} succeeded, {len(data.get('failed_wagers', []))} failed")
                    
                else:
                    # Entire chunk failed
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"❌ Batch {chunk_idx} failed: {error_msg}")
                    
                    # Mark all wagers in this chunk as failed
                    for i, wager in enumerate(chunk):
                        external_id = wager.get("external_id")
                        if external_id:
                            all_failed_wagers[external_id] = {
                                "success": False,
                                "external_id": external_id,
                                "error": "batch_api_error",
                                "message": error_msg,
                                "index": i,
                                "request": wager,
                                "chunk": chunk_idx
                            }
                            total_failed += 1
                
                # Small delay between chunks to be nice to the API
                if chunk_idx < len(wager_chunks):
                    await asyncio.sleep(0.1)
            
            logger.info(f"🎯 All batches complete: {total_successful} succeeded, {total_failed} failed across {len(wager_chunks)} batches")
            
            return {
                "success": True,
                "total_wagers": len(wagers),
                "successful_count": total_successful,
                "failed_count": total_failed,
                "success_wagers": all_success_wagers,
                "failed_wagers": all_failed_wagers,
                "chunks_processed": len(wager_chunks),
                "environment": self.betting_env
            }
            
        except Exception as e:
            error_msg = f"Exception during batch placement: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            
            # Return all wagers as failed
            failed_wagers = {}
            for i, wager in enumerate(wagers):
                external_id = wager.get("external_id")
                if external_id:
                    failed_wagers[external_id] = {
                        "success": False,
                        "external_id": external_id,
                        "error": "exception",
                        "message": error_msg,
                        "index": i,
                        "request": wager
                    }
            
            return {
                "success": False,
                "error": error_msg,
                "total_wagers": len(wagers),
                "successful_count": 0,
                "failed_count": len(wagers),
                "success_wagers": {},
                "failed_wagers": failed_wagers,
                "chunks_processed": 0,
                "environment": self.betting_env
            }

    # ============================================================================
    # NEW CANCELLATION METHODS
    # ============================================================================

    async def cancel_wager(self, external_id: str, wager_id: str) -> Dict[str, Any]:
        """
        Cancel a single wager using /mm/cancel_wager endpoint
        
        Args:
            external_id: The external ID used when placing the wager
            wager_id: The ProphetX wager ID returned when wager was placed
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"🗑️ Cancelling wager: external_id={external_id}, wager_id={wager_id}")
            
            # Use betting environment for cancellation
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/cancel_wager"
            
            cancel_data = {
                "external_id": external_id,
                "wager_id": wager_id
            }
            
            logger.info(f"   📤 Cancel API call: {url}")
            logger.info(f"   📋 Cancel data: {cancel_data}")
            
            response = await self.client.post(url, headers=headers, json=cancel_data, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if cancellation was successful
                if data.get("success") or not data.get("error"):
                    logger.info(f"✅ Wager cancelled successfully: {external_id}")
                    
                    return {
                        "success": True,
                        "external_id": external_id,
                        "wager_id": wager_id,
                        "message": "Wager cancelled successfully",
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
                else:
                    error_msg = data.get("error") or data.get("message") or "Unknown cancellation error"
                    logger.error(f"   ❌ ProphetX cancellation failed: {error_msg}")
                    
                    return {
                        "success": False,
                        "external_id": external_id,
                        "wager_id": wager_id,
                        "error": error_msg,
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ Cancel API returned status {response.status_code}: {error_text}")
                
                return {
                    "success": False,
                    "external_id": external_id,
                    "wager_id": wager_id,
                    "error": f"HTTP {response.status_code}: Cancel API error",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Exception cancelling wager {external_id}: {e}")
            return {
                "success": False,
                "external_id": external_id,
                "wager_id": wager_id,
                "error": f"Exception during cancellation: {str(e)}",
                "environment": self.betting_env
            }

    async def cancel_multiple_wagers(self, wagers_to_cancel: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Cancel multiple wagers using /mm/cancel_multiple_wagers endpoint
        
        Args:
            wagers_to_cancel: List of dicts with 'external_id' and 'wager_id' keys
            
        Returns:
            Dict with results for each wager cancellation
        """
        try:
            logger.info(f"🗑️ Cancelling {len(wagers_to_cancel)} wagers in batch...")
            
            # Use betting environment for cancellation
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/cancel_multiple_wagers"
            
            payload = {
                "data": wagers_to_cancel
            }
            
            logger.info(f"   📤 Batch cancel API call: {url}")
            logger.info(f"   📋 Cancelling wagers: {[w.get('external_id', 'unknown')[:8] + '...' for w in wagers_to_cancel]}")
            
            response = await self.client.post(url, headers=headers, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                
                # FIXED: Handle correct ProphetX response structure
                # ProphetX returns: {"data": [{"success": bool, "wager": {...}, "error": {...}}]}
                cancellation_results = data.get("data", [])
                
                cancelled_wagers = {}
                failed_cancellations = {}
                
                # Process each cancellation result
                for result in cancellation_results:
                    if isinstance(result, dict):
                        success = result.get("success", False)
                        wager_info = result.get("wager", {})
                        error_info = result.get("error", {})
                        
                        external_id = wager_info.get("external_id", "unknown")
                        wager_id = wager_info.get("id", "unknown")
                        
                        if success:
                            cancelled_wagers[external_id] = {
                                "success": True,
                                "external_id": external_id,
                                "wager_id": wager_id,
                                "message": "Cancelled successfully",
                                "wager_details": wager_info
                            }
                        else:
                            failed_cancellations[external_id] = {
                                "success": False,
                                "external_id": external_id,
                                "wager_id": wager_id,
                                "error": error_info.get("error", "Unknown error"),
                                "message": error_info.get("message", "Cancellation failed"),
                                "error_details": error_info
                            }
                
                total_cancelled = len(cancelled_wagers)
                total_failed = len(failed_cancellations)
                
                logger.info(f"✅ Batch cancellation complete: {total_cancelled} succeeded, {total_failed} failed")
                
                return {
                    "success": True,
                    "total_requested": len(wagers_to_cancel),
                    "cancelled_count": total_cancelled,
                    "failed_count": total_failed,
                    "cancelled_wagers": cancelled_wagers,
                    "failed_cancellations": failed_cancellations,
                    "prophetx_response": data,
                    "environment": self.betting_env
                }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ Batch cancel API returned status {response.status_code}: {error_text}")
                
                return {
                    "success": False,
                    "total_requested": len(wagers_to_cancel),
                    "error": f"HTTP {response.status_code}: Batch cancel API error",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Exception during batch cancellation: {e}")
            return {
                "success": False,
                "total_requested": len(wagers_to_cancel),
                "error": f"Exception during batch cancellation: {str(e)}",
                "environment": self.betting_env
            }

    async def cancel_all_wagers(self) -> Dict[str, Any]:
        """
        Cancel ALL wagers using /mm/cancel_all_wagers endpoint
        ⚠️ WARNING: This cancels ALL your active wagers!
        """
        try:
            logger.warning("🚨 CANCELLING ALL WAGERS - This will cancel EVERY active wager!")
            
            # Use betting environment for cancellation
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/cancel_all_wagers"
            
            logger.info(f"   📤 Cancel all API call: {url}")
            
            response = await self.client.post(url, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") or not data.get("error"):
                    cancelled_count = data.get("data", {}).get("cancelled_count", "unknown")
                    logger.info(f"✅ All wagers cancelled successfully: {cancelled_count} wagers")
                    
                    return {
                        "success": True,
                        "cancelled_count": cancelled_count,
                        "message": "All wagers cancelled successfully",
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
                else:
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    logger.error(f"   ❌ Cancel all failed: {error_msg}")
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ Cancel all API returned status {response.status_code}: {error_text}")
                
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: Cancel all API error",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Exception cancelling all wagers: {e}")
            return {
                "success": False,
                "error": f"Exception during cancel all: {str(e)}",
                "environment": self.betting_env
            }

    async def cancel_wagers_by_event(self, event_id: str) -> Dict[str, Any]:
        """
        Cancel all wagers for a specific event using /mm/cancel_wagers_by_event endpoint
        
        Args:
            event_id: The event ID to cancel wagers for
            
        Returns:
            Dict with cancellation results
        """
        try:
            logger.info(f"🗑️ Cancelling all wagers for event {event_id}...")
            
            # Use betting environment for cancellation
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/cancel_wagers_by_event"
            
            cancel_data = {
                "event_id": event_id
            }
            
            logger.info(f"   📤 Cancel by event API call: {url}")
            logger.info(f"   📋 Event ID: {event_id}")
            
            response = await self.client.post(url, headers=headers, json=cancel_data, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") or not data.get("error"):
                    cancelled_count = data.get("data", {}).get("cancelled_count", "unknown")
                    logger.info(f"✅ Event wagers cancelled successfully: {cancelled_count} wagers for event {event_id}")
                    
                    return {
                        "success": True,
                        "event_id": event_id,
                        "cancelled_count": cancelled_count,
                        "message": f"All wagers cancelled for event {event_id}",
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
                else:
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    logger.error(f"   ❌ Cancel by event failed: {error_msg}")
                    
                    return {
                        "success": False,
                        "event_id": event_id,
                        "error": error_msg,
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ Cancel by event API returned status {response.status_code}: {error_text}")
                
                return {
                    "success": False,
                    "event_id": event_id,
                    "error": f"HTTP {response.status_code}: Cancel by event API error",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Exception cancelling wagers for event {event_id}: {e}")
            return {
                "success": False,
                "event_id": event_id,
                "error": f"Exception during event cancellation: {str(e)}",
                "environment": self.betting_env
            }

    async def cancel_wagers_by_market(self, event_id: int, market_id: int) -> Dict[str, Any]:
        """
        Cancel all wagers for a specific market using /mm/cancel_wagers_by_market endpoint
        
        Args:
            event_id: The event ID (as integer)
            market_id: The market ID (as integer)
            
        Returns:
            Dict with cancellation results
        """
        try:
            logger.info(f"🗑️ Cancelling all wagers for market {market_id} in event {event_id}...")
            
            # Use betting environment for cancellation
            headers = await self.auth_manager.get_betting_headers()
            base_url = self.auth_manager.get_betting_base_url()
            
            url = f"{base_url}/partner/mm/cancel_wagers_by_market"
            
            cancel_data = {
                "event_id": event_id,
                "market_id": market_id
            }
            
            logger.info(f"   📤 Cancel by market API call: {url}")
            logger.info(f"   📋 Event ID: {event_id}, Market ID: {market_id}")
            
            response = await self.client.post(url, headers=headers, json=cancel_data, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") or not data.get("error"):
                    cancelled_count = data.get("data", {}).get("cancelled_count", "unknown")
                    logger.info(f"✅ Market wagers cancelled successfully: {cancelled_count} wagers for market {market_id}")
                    
                    return {
                        "success": True,
                        "event_id": event_id,
                        "market_id": market_id,
                        "cancelled_count": cancelled_count,
                        "message": f"All wagers cancelled for market {market_id} in event {event_id}",
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
                else:
                    error_msg = data.get("error") or data.get("message") or "Unknown error"
                    logger.error(f"   ❌ Cancel by market failed: {error_msg}")
                    
                    return {
                        "success": False,
                        "event_id": event_id,
                        "market_id": market_id,
                        "error": error_msg,
                        "prophetx_response": data,
                        "environment": self.betting_env
                    }
            else:
                error_text = response.text[:500]
                logger.error(f"   ❌ Cancel by market API returned status {response.status_code}: {error_text}")
                
                return {
                    "success": False,
                    "event_id": event_id,
                    "market_id": market_id,
                    "error": f"HTTP {response.status_code}: Cancel by market API error",
                    "response_text": error_text,
                    "environment": self.betting_env
                }
                    
        except Exception as e:
            logger.error(f"❌ Exception cancelling wagers for market {market_id}: {e}")
            return {
                "success": False,
                "event_id": event_id,
                "market_id": market_id,
                "error": f"Exception during market cancellation: {str(e)}",
                "environment": self.betting_env
            }

    # ============================================================================
    # EXISTING WAGER HISTORY METHODS
    # ============================================================================
    
    async def get_all_active_wagers(self) -> List[Dict[str, Any]]:
        """Get all active wagers from betting environment"""
        logger.info("📋 Fetching all active wagers from betting environment...")
        
        # FIXED: Use v2 API endpoint like the working example
        headers = await self.auth_manager.get_betting_headers()
        base_url = self.auth_manager.get_betting_base_url()
        url = f"{base_url}/partner/v2/mm/get_wager_histories"
        
        # Get wagers from the last 30 days
        to_timestamp = int(time.time())
        from_timestamp = to_timestamp - (30 * 24 * 60 * 60)
        
        params = {
            "from": from_timestamp,
            "to": to_timestamp,
            "limit": 1000
        }
        
        logger.info(f"🔍 Calling ProphetX API: {url}")
        logger.info(f"📊 Query params: {params}")
        
        try:
            response = await self.client.get(url, params=params, headers=headers)
            
            logger.info(f"📡 API Response: HTTP {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # FIXED: Use correct response structure like working example
                all_wagers = data.get("data", {}).get("wagers", [])
                
                logger.info(f"📊 Retrieved {len(all_wagers)} total wagers from ProphetX")
                
                # Filter to only active (unmatched) wagers
                active_wagers = [w for w in all_wagers if w.get("matching_status") == "unmatched"]
                
                logger.info(f"✅ Retrieved {len(active_wagers)} active wagers (from {len(all_wagers)} total)")
                return active_wagers
            else:
                error_text = response.text[:500]
                logger.error(f"❌ HTTP {response.status_code}: {error_text}")
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
    
    async def clear_cache(self):
        """Clear all cached data"""
        self.sport_events_cache.clear()
        logger.info("🧹 ProphetX cache cleared")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

# Create global service instance
prophetx_service = ProphetXService()