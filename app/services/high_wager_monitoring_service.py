#!/usr/bin/env python3
"""
High Wager Monitoring Service - API-Based Wager Tracking

Updated to fetch current wagers from ProphetX API instead of maintaining local TrackedWagers.
This allows real-time detection of fills, status changes, and accurate position tracking.

Key Changes:
1. Fetches active wagers from API at start of each monitoring cycle
2. Compares API wagers with current market opportunities  
3. Detects fills, cancellations, and status changes automatically
4. Maintains all existing action execution functionality
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
import uuid
import time

logger = logging.getLogger(__name__)

@dataclass
class ApiWager:
    """Represents a wager from ProphetX API response"""
    wager_id: str
    external_id: str
    line_id: str
    event_id: str
    market_id: str
    side: str
    odds: int
    stake: float
    matched_stake: float
    unmatched_stake: float
    status: str
    matching_status: str
    created_at: str
    updated_at: str
    # Derived fields
    is_system_bet: bool
    is_active: bool
    is_filled: bool

@dataclass
class CurrentOpportunity:
    """Current opportunity from scan-opportunities endpoint"""
    event_id: str
    market_id: str
    market_type: str
    side: str
    recommended_odds: int
    recommended_stake: float
    large_bet_combined_size: float
    line_id: str
    opportunity_type: str  # "single" or "arbitrage"
    arbitrage_pair_id: Optional[str] = None

@dataclass
class WagerDifference:
    """Detected difference between current wager and recommended opportunity"""
    line_id: str
    event_id: str
    market_id: str
    market_type: str
    side: str
    # Current wager info (from API)
    current_odds: Optional[int]
    current_stake: Optional[float]
    current_status: Optional[str]
    current_matching_status: Optional[str]
    # Recommended info
    recommended_odds: int
    recommended_stake: float
    # Analysis
    difference_type: str  # "odds_change", "stake_change", "new_opportunity", "remove_opportunity", "wager_filled"
    action_needed: str  # "update_wager", "cancel_wager", "place_new_wager", "no_action"
    reason: str
    # API wager identifiers for actions
    wager_external_id: Optional[str] = None
    wager_prophetx_id: Optional[str] = None

@dataclass
class ActionResult:
    """Result of executing an action"""
    success: bool
    action_type: str  # "cancel", "place", "update"
    line_id: str
    external_id: Optional[str] = None
    prophetx_wager_id: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class HighWagerMonitoringService:
    """API-based high wager monitoring with real-time wager tracking"""
    
    def __init__(self):
        self.monitoring_active = False
        self.last_scan_time: Optional[datetime] = None
        self.monitoring_cycles = 0
        
        # Services (to be injected)
        self.market_scanning_service = None
        self.arbitrage_service = None
        self.bet_placement_service = None
        self.prophetx_service = None
        
        # Settings
        self.monitoring_interval_seconds = 60  # 1 minute
        self.fill_wait_period_seconds = 300   # 5 minutes
        self.max_exposure_multiplier = 3.0    # Max 3x recommended amount per line
        
        # API-based tracking
        self.current_wagers: List[ApiWager] = []
        self.last_wager_fetch_time: Optional[datetime] = None
        self.wager_fetch_duration: Optional[float] = None
        
        # Action tracking
        self.action_history: List[ActionResult] = []
        self.actions_this_cycle = 0
        
        # Fill detection
        self.recent_fills: Dict[str, datetime] = {}  # line_id -> last_fill_time
        self.line_exposure: Dict[str, float] = defaultdict(float)  # line_id -> total_stake
        
        # Anti-duplicate protection (will be set during start_monitoring)
        # self._first_cycle_delay will be added dynamically
        
    def initialize_services(self, market_scanning_service, arbitrage_service, 
                          bet_placement_service, prophetx_service):
        """Initialize required services"""
        self.market_scanning_service = market_scanning_service
        self.arbitrage_service = arbitrage_service
        self.bet_placement_service = bet_placement_service
        self.prophetx_service = prophetx_service
        logger.info("🔧 High wager monitoring services initialized")
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """Start the complete monitoring workflow with API-based tracking"""
        if self.monitoring_active:
            return {
                "success": False,
                "message": "Monitoring already active"
            }
        
        logger.info("🚀 Starting API-Based High Wager Monitoring Service")
        logger.info("=" * 70)
        
        # Step 1: Place initial bets (no local tracking needed)
        logger.info("📍 Step 1: Placing initial bets...")
        initial_result = await self._place_initial_bets()
        
        if not initial_result["success"]:
            return {
                "success": False,
                "message": f"Failed to place initial bets: {initial_result.get('error', 'Unknown error')}"
            }
        
        # Step 2: CRITICAL - Wait and refresh API data after placing initial bets
        logger.info("⏳ Step 2: Waiting for ProphetX to process initial bets...")
        await asyncio.sleep(10)  # Give ProphetX 10 seconds to process the bets
        
        logger.info("🔄 Step 3: Fetching just-placed bets from API to prevent duplicates...")
        await self._fetch_current_wagers_from_api()
        
        # Log what we found
        initial_wagers = [w for w in self.current_wagers if w.is_system_bet and w.is_active]
        logger.info(f"✅ Found {len(initial_wagers)} initial system wagers in API")
        
        # Step 3: Start monitoring loop with API-based tracking (with delay for first cycle)
        self.monitoring_active = True
        self.monitoring_cycles = 0  # Reset cycle count when starting monitoring
        self._first_cycle_delay = 30  # Additional 30 second delay for first cycle
        asyncio.create_task(self._api_based_monitoring_loop())
        
        return {
            "success": True,
            "message": "API-based high wager monitoring started with anti-duplicate protection", 
            "data": {
                "initial_bets": initial_result,
                "initial_wagers_detected": len(initial_wagers),
                "api_based_tracking": True,
                "monitoring_interval": f"{self.monitoring_interval_seconds} seconds",
                "first_cycle_delay": "60 seconds total (30s extra for first cycle)"
            }
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop the monitoring loop"""
        self.monitoring_active = False
        
        # Clean up any timing attributes
        if hasattr(self, '_first_cycle_delay'):
            delattr(self, '_first_cycle_delay')
        
        return {
            "success": True,
            "message": "API-based monitoring stopped",
            "data": {
                "monitoring_cycles_completed": self.monitoring_cycles,
                "current_active_wagers": len([w for w in self.current_wagers if w.is_active]),
                "total_actions_executed": len(self.action_history)
            }
        }
    
    # ============================================================================
    # API-BASED MONITORING LOOP
    # ============================================================================
    
    async def _api_based_monitoring_loop(self):
        """Main monitoring loop with API-based wager tracking and anti-duplicate protection"""
        logger.info("🔄 Starting API-based monitoring loop...")
        
        # Handle first cycle delay to prevent duplicates
        if hasattr(self, '_first_cycle_delay'):
            logger.info(f"⏳ Delaying first monitoring cycle by {self._first_cycle_delay} seconds to prevent duplicates...")
            await asyncio.sleep(self._first_cycle_delay)
            delattr(self, '_first_cycle_delay')  # Remove the delay attribute after use
        
        while self.monitoring_active:
            try:
                cycle_start = datetime.now(timezone.utc)
                self.monitoring_cycles += 1
                self.actions_this_cycle = 0
                
                logger.info(f"🔍 API Monitoring cycle #{self.monitoring_cycles} starting...")
                
                # Step 1: Fetch current wagers from ProphetX API
                logger.info("📋 Fetching current wagers from ProphetX API...")
                await self._fetch_current_wagers_from_api()
                
                # Step 2: Get current market opportunities
                current_opportunities = await self._get_current_opportunities()
                
                # Step 3: ANTI-DUPLICATE PROTECTION - On first cycle, be extra careful
                if self.monitoring_cycles == 1:
                    logger.info("🛡️ First monitoring cycle - applying extra duplicate protection...")
                    current_opportunities = await self._filter_opportunities_against_recent_bets(current_opportunities)
                
                # Step 4: Compare API wagers with opportunities
                differences = await self._detect_api_wager_differences(current_opportunities)
                
                # Step 5: Execute actions based on differences
                if differences:
                    logger.info(f"⚡ Executing {len(differences)} actions...")
                    await self._execute_all_actions(differences)
                else:
                    logger.info("✅ No differences detected - all wagers up to date")
                
                # Step 6: Update fill tracking from API data
                self._update_fill_tracking_from_api()
                
                # Step 7: Log cycle summary
                active_wagers = len([w for w in self.current_wagers if w.is_active])
                filled_wagers = len([w for w in self.current_wagers if w.is_filled])
                
                logger.info(f"📊 Cycle #{self.monitoring_cycles} complete:")
                logger.info(f"   🎯 {active_wagers} active wagers, {filled_wagers} filled wagers")
                logger.info(f"   ⚡ {self.actions_this_cycle} actions executed")
                logger.info(f"   ⏱️ Wager fetch took {self.wager_fetch_duration:.2f}s")
                
                # Update tracking
                self.last_scan_time = cycle_start
                
                # Wait for next cycle
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.monitoring_interval_seconds - cycle_duration)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in API monitoring cycle: {e}", exc_info=True)
                await asyncio.sleep(self.monitoring_interval_seconds)
    
    # ============================================================================
    # API WAGER FETCHING
    # ============================================================================
    
    async def _fetch_current_wagers_from_api(self):
        """Fetch current wagers from ProphetX API with pagination"""
        fetch_start = time.time()
        
        try:
            all_wagers = []
            page_count = 0
            next_cursor = None
            
            # Calculate time window (last 7 days to catch all recent bets)
            now_timestamp = int(time.time())
            week_ago_timestamp = now_timestamp - (7 * 24 * 60 * 60)
            
            # Use the existing prophetx_service auth headers
            headers = await self.prophetx_service.auth_manager.get_betting_headers()
            base_url = self.prophetx_service.auth_manager.get_betting_base_url()
            
            while True:
                page_count += 1
                
                # Build query parameters
                params = {
                    "from": week_ago_timestamp,
                    "to": now_timestamp,
                    "limit": 1000  # Maximum allowed
                }
                
                if next_cursor:
                    params["next_cursor"] = next_cursor
                
                # Make API call
                url = f"{base_url}/partner/v2/mm/get_wager_histories"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract wagers and pagination info
                            wagers_data = data.get("data", {})
                            page_wagers = wagers_data.get("wagers", [])
                            next_cursor = wagers_data.get("next_cursor")
                            
                            all_wagers.extend(page_wagers)
                            
                            # Check if we're done
                            if not next_cursor or len(page_wagers) < 1000:
                                break
                                
                            # Small delay between pages to be respectful
                            await asyncio.sleep(0.1)
                            
                        else:
                            error_text = await response.text()
                            logger.error(f"API error fetching wagers: HTTP {response.status} - {error_text}")
                            break
            
            # Convert raw wagers to ApiWager objects
            self.current_wagers = self._convert_to_api_wagers(all_wagers)
            self.last_wager_fetch_time = datetime.now(timezone.utc)
            self.wager_fetch_duration = time.time() - fetch_start
            
            # Filter to system bets only (with external_id)
            system_wagers = [w for w in self.current_wagers if w.is_system_bet]
            active_wagers = [w for w in system_wagers if w.is_active]
            valid_for_cancellation = [w for w in active_wagers if w.external_id and w.wager_id]
            
            logger.info(f"📋 Fetched {len(all_wagers)} total wagers from {page_count} pages")
            logger.info(f"   🤖 {len(system_wagers)} system wagers (with external_id)")
            logger.info(f"   ✅ {len(active_wagers)} active system wagers")
            logger.info(f"   🗑️ {len(valid_for_cancellation)} wagers valid for cancellation (have both IDs)")
            
            if len(active_wagers) != len(valid_for_cancellation):
                missing_ids_count = len(active_wagers) - len(valid_for_cancellation)
                logger.warning(f"⚠️ {missing_ids_count} active wagers missing identifiers for cancellation")
                
                # Debug log wagers with missing identifiers
                for wager in active_wagers:
                    if not wager.external_id or not wager.wager_id:
                        logger.debug(f"Missing ID: line_id={wager.line_id}, external_id={bool(wager.external_id)}, wager_id={bool(wager.wager_id)}")
            
        except Exception as e:
            logger.error(f"Error fetching current wagers: {e}", exc_info=True)
            self.current_wagers = []
    
    def _convert_to_api_wagers(self, raw_wagers: List[Dict]) -> List[ApiWager]:
        """Convert raw API response to ApiWager objects"""
        api_wagers = []
        
        for wager in raw_wagers:
            try:
                # Extract basic fields with better error handling
                wager_id = str(wager.get("id", "")) or str(wager.get("wager_id", ""))
                external_id = wager.get("external_id", "") or ""
                line_id = wager.get("line_id", "") or ""
                event_id = str(wager.get("event_id", "") or wager.get("sport_event_id", ""))
                market_id = str(wager.get("market_id", ""))
                
                # Skip wagers without essential fields
                if not wager_id or not line_id:
                    logger.debug(f"Skipping wager due to missing essential fields: wager_id={wager_id}, line_id={line_id}")
                    continue
                
                # Extract bet details
                side = wager.get("display_name", "") or wager.get("selection_name", "") or ""
                odds = int(wager.get("odds", 0))
                stake = float(wager.get("stake", 0))
                matched_stake = float(wager.get("matched_stake", 0))
                unmatched_stake = float(wager.get("unmatched_stake", 0))
                
                # Extract status info
                status = wager.get("status", "")
                matching_status = wager.get("matching_status", "")
                created_at = wager.get("created_at", "")
                updated_at = wager.get("updated_at", "")
                
                # Derive computed fields
                is_system_bet = bool(external_id and external_id.strip())  # Has non-empty external_id = system bet
                is_active = (
                    status in ["open", "active", "inactive"] and  # Added "inactive" as it appears in logs
                    matching_status == "unmatched" and
                    unmatched_stake > 0
                )
                is_filled = matched_stake > 0
                
                api_wager = ApiWager(
                    wager_id=wager_id,
                    external_id=external_id,
                    line_id=line_id,
                    event_id=event_id,
                    market_id=market_id,
                    side=side,
                    odds=odds,
                    stake=stake,
                    matched_stake=matched_stake,
                    unmatched_stake=unmatched_stake,
                    status=status,
                    matching_status=matching_status,
                    created_at=created_at,
                    updated_at=updated_at,
                    is_system_bet=is_system_bet,
                    is_active=is_active,
                    is_filled=is_filled
                )
                
                # Debug logging for system bets
                if is_system_bet:
                    logger.debug(f"System wager: {external_id[:12]}... | ID: {wager_id[:12]}... | Active: {is_active}")
                
                api_wagers.append(api_wager)
                
            except Exception as e:
                logger.warning(f"Error converting wager {wager.get('id', 'unknown')}: {e}")
                continue
        
        return api_wagers
    
    def _update_fill_tracking_from_api(self):
        """Update fill tracking and line exposure from API data"""
        self.line_exposure.clear()
        
        for wager in self.current_wagers:
            if not wager.is_system_bet:
                continue
                
            # Update line exposure with active stakes
            if wager.is_active:
                self.line_exposure[wager.line_id] += wager.unmatched_stake
            
            # Track recent fills for wait periods
            if wager.is_filled and wager.updated_at:
                try:
                    # Parse updated_at timestamp
                    if isinstance(wager.updated_at, str):
                        updated_dt = datetime.fromisoformat(wager.updated_at.replace('Z', '+00:00'))
                        
                        # If this fill is newer than what we have tracked, update it
                        if (wager.line_id not in self.recent_fills or 
                            updated_dt > self.recent_fills[wager.line_id]):
                            self.recent_fills[wager.line_id] = updated_dt
                            
                except (ValueError, TypeError):
                    pass  # Skip if we can't parse the timestamp
    
    # ============================================================================
    # API-BASED DIFFERENCE DETECTION
    # ============================================================================
    
    async def _detect_api_wager_differences(self, current_opportunities: List[CurrentOpportunity]) -> List[WagerDifference]:
        """Compare current API wagers with market opportunities"""
        differences = []
        
        # Filter to active system wagers only (with external_id and active status)
        active_system_wagers = [
            w for w in self.current_wagers 
            if w.is_system_bet and w.is_active and w.external_id and w.wager_id
        ]
        
        logger.info(f"🔍 Comparing {len(active_system_wagers)} active system wagers vs {len(current_opportunities)} opportunities")
        
        # Group by line_id for comparison
        api_wagers_by_line = defaultdict(list)
        opportunities_by_line = defaultdict(list)
        
        for wager in active_system_wagers:
            api_wagers_by_line[wager.line_id].append(wager)
            
        for opp in current_opportunities:
            opportunities_by_line[opp.line_id].append(opp)
        
        # Get all unique line_ids
        all_line_ids = set(api_wagers_by_line.keys()) | set(opportunities_by_line.keys())
        
        for line_id in all_line_ids:
            api_wagers = api_wagers_by_line.get(line_id, [])
            opportunities = opportunities_by_line.get(line_id, [])
            
            if api_wagers and opportunities:
                # Both exist - check each API wager against recommendations
                for wager in api_wagers:
                    matching_opp = self._find_matching_opportunity(wager, opportunities)
                    
                    if matching_opp:
                        # Check if wager needs updating
                        diff = self._compare_api_wager_vs_opportunity(wager, matching_opp)
                        if diff:
                            differences.append(diff)
                    else:
                        # No matching opportunity - cancel this wager (with proper validation)
                        if wager.external_id and wager.wager_id:
                            differences.append(WagerDifference(
                                line_id=line_id,
                                event_id=wager.event_id,
                                market_id=wager.market_id,
                                market_type="unknown",  # We don't have this in API response
                                side=wager.side,
                                current_odds=wager.odds,
                                current_stake=wager.unmatched_stake,
                                current_status=wager.status,
                                current_matching_status=wager.matching_status,
                                recommended_odds=0,
                                recommended_stake=0,
                                difference_type="remove_opportunity",
                                action_needed="cancel_wager",
                                reason="Opportunity no longer recommended",
                                wager_external_id=wager.external_id,
                                wager_prophetx_id=wager.wager_id
                            ))
                        else:
                            logger.warning(f"⚠️ Cannot cancel wager {line_id} - missing identifiers: external_id={wager.external_id}, wager_id={wager.wager_id}")
            
            elif opportunities and not api_wagers:
                # New opportunities - place new wagers
                for opp in opportunities:
                    differences.append(WagerDifference(
                        line_id=line_id,
                        event_id=opp.event_id,
                        market_id=opp.market_id,
                        market_type=opp.market_type,
                        side=opp.side,
                        current_odds=None,
                        current_stake=None,
                        current_status=None,
                        current_matching_status=None,
                        recommended_odds=opp.recommended_odds,
                        recommended_stake=opp.recommended_stake,
                        difference_type="new_opportunity",
                        action_needed="place_new_wager",
                        reason=f"New opportunity detected for {opp.market_type}"
                    ))
            
            elif api_wagers and not opportunities:
                # Cancel all API wagers on this line (with proper validation)
                for wager in api_wagers:
                    if wager.external_id and wager.wager_id:
                        differences.append(WagerDifference(
                            line_id=line_id,
                            event_id=wager.event_id,
                            market_id=wager.market_id,
                            market_type="unknown",
                            side=wager.side,
                            current_odds=wager.odds,
                            current_stake=wager.unmatched_stake,
                            current_status=wager.status,
                            current_matching_status=wager.matching_status,
                            recommended_odds=0,
                            recommended_stake=0,
                            difference_type="remove_opportunity",
                            action_needed="cancel_wager",
                            reason="Opportunity no longer recommended",
                            wager_external_id=wager.external_id,
                            wager_prophetx_id=wager.wager_id
                        ))
                    else:
                        logger.warning(f"⚠️ Cannot cancel wager {line_id} - missing identifiers: external_id={wager.external_id}, wager_id={wager.wager_id}")
        
        logger.info(f"📊 Detected {len(differences)} differences requiring action")
        return differences
    
    def _find_matching_opportunity(self, wager: ApiWager, opportunities: List[CurrentOpportunity]) -> Optional[CurrentOpportunity]:
        """Find opportunity that matches an API wager"""
        for opp in opportunities:
            if self._wager_matches_opportunity_api(wager, opp):
                return opp
        return None
    
    def _wager_matches_opportunity_api(self, wager: ApiWager, opportunity: CurrentOpportunity) -> bool:
        """Check if an API wager matches an opportunity"""
        return (
            wager.line_id == opportunity.line_id and
            self._sides_match(wager.side, opportunity.side)
        )
    
    def _sides_match(self, wager_side: str, opportunity_side: str) -> bool:
        """Check if wager side matches opportunity side (with flexible matching)"""
        # Simple exact match first
        if wager_side.lower().strip() == opportunity_side.lower().strip():
            return True
        
        # Extract key words for more flexible matching
        wager_words = set(wager_side.lower().split())
        opp_words = set(opportunity_side.lower().split())
        
        # If most significant words match, consider it a match
        if len(wager_words & opp_words) >= min(2, len(wager_words), len(opp_words)):
            return True
        
        return False
    
    def _compare_api_wager_vs_opportunity(self, wager: ApiWager, opportunity: CurrentOpportunity) -> Optional[WagerDifference]:
        """Compare an API wager with current opportunity to detect changes"""
        
        # Validate wager has required identifiers for potential actions
        if not wager.external_id or not wager.wager_id:
            logger.warning(f"⚠️ Skipping comparison for wager {wager.line_id} - missing identifiers")
            return None
        
        # Check for odds changes
        if wager.odds != opportunity.recommended_odds:
            logger.debug(f"📊 Odds change detected: {wager.side} {wager.odds:+d} → {opportunity.recommended_odds:+d}")
            return WagerDifference(
                line_id=wager.line_id,
                event_id=wager.event_id,
                market_id=wager.market_id,
                market_type=opportunity.market_type,
                side=wager.side,
                current_odds=wager.odds,
                current_stake=wager.unmatched_stake,
                current_status=wager.status,
                current_matching_status=wager.matching_status,
                recommended_odds=opportunity.recommended_odds,
                recommended_stake=opportunity.recommended_stake,
                difference_type="odds_change",
                action_needed="update_wager",
                reason=f"Odds changed from {wager.odds:+d} to {opportunity.recommended_odds:+d}",
                wager_external_id=wager.external_id,
                wager_prophetx_id=wager.wager_id
            )
        
        # Check for significant stake changes (> $10)
        stake_diff = abs(wager.unmatched_stake - opportunity.recommended_stake)
        if stake_diff > 10.0:
            logger.debug(f"💰 Stake change detected: {wager.side} ${wager.unmatched_stake:.2f} → ${opportunity.recommended_stake:.2f}")
            return WagerDifference(
                line_id=wager.line_id,
                event_id=wager.event_id,
                market_id=wager.market_id,
                market_type=opportunity.market_type,
                side=wager.side,
                current_odds=wager.odds,
                current_stake=wager.unmatched_stake,
                current_status=wager.status,
                current_matching_status=wager.matching_status,
                recommended_odds=opportunity.recommended_odds,
                recommended_stake=opportunity.recommended_stake,
                difference_type="stake_change",
                action_needed="update_wager",
                reason=f"Stake changed from ${wager.unmatched_stake:.2f} to ${opportunity.recommended_stake:.2f}",
                wager_external_id=wager.external_id,
                wager_prophetx_id=wager.wager_id
            )
        
        return None
    
    async def _filter_opportunities_against_recent_bets(self, opportunities: List[CurrentOpportunity]) -> List[CurrentOpportunity]:
        """
        Anti-duplicate protection: Filter out opportunities that match recently placed bets
        
        This prevents the first monitoring cycle from duplicating bets that were just placed
        during initialization but might not be fully reflected in the API yet.
        """
        try:
            if not opportunities:
                return opportunities
            
            logger.info(f"🛡️ Applying anti-duplicate filter to {len(opportunities)} opportunities...")
            
            # Get recent system wagers (within last 5 minutes)
            now = datetime.now(timezone.utc)
            recent_cutoff = now - timedelta(minutes=5)
            
            recent_wagers = []
            for wager in self.current_wagers:
                if wager.is_system_bet and wager.created_at:
                    try:
                        # Parse created_at timestamp
                        if isinstance(wager.created_at, str):
                            created_dt = datetime.fromisoformat(wager.created_at.replace('Z', '+00:00'))
                            if created_dt >= recent_cutoff:
                                recent_wagers.append(wager)
                    except (ValueError, TypeError):
                        pass  # Skip if timestamp parsing fails
            
            logger.info(f"🔍 Found {len(recent_wagers)} recent system wagers (last 5 minutes)")
            
            # Filter opportunities against recent wagers
            filtered_opportunities = []
            duplicates_found = 0
            
            for opp in opportunities:
                # Check if this opportunity matches any recent wager
                is_duplicate = False
                
                for wager in recent_wagers:
                    if self._opportunity_matches_recent_wager(opp, wager):
                        logger.info(f"🚫 DUPLICATE DETECTED: Skipping {opp.side} @ {opp.recommended_odds:+d} (matches recent wager {wager.external_id[:12]}...)")
                        is_duplicate = True
                        duplicates_found += 1
                        break
                
                if not is_duplicate:
                    filtered_opportunities.append(opp)
            
            logger.info(f"🛡️ Anti-duplicate filter complete: {duplicates_found} duplicates removed, {len(filtered_opportunities)} opportunities remain")
            
            return filtered_opportunities
            
        except Exception as e:
            logger.error(f"Error in anti-duplicate filter: {e}")
            # If filter fails, return original opportunities to avoid breaking the system
            return opportunities
    
    def _opportunity_matches_recent_wager(self, opportunity: CurrentOpportunity, wager: ApiWager) -> bool:
        """Check if an opportunity matches a recent wager (indicates potential duplicate)"""
        try:
            # Primary match: same line_id
            if opportunity.line_id == wager.line_id:
                # Check if sides match (with flexible matching)
                if self._sides_match(opportunity.side, wager.side):
                    # Check if odds are close (within 2 points to account for market movement)
                    odds_diff = abs(opportunity.recommended_odds - wager.odds)
                    if odds_diff <= 2:
                        # Check if stakes are close (within $20 to account for sizing differences)
                        stake_diff = abs(opportunity.recommended_stake - wager.stake)
                        if stake_diff <= 20.0:
                            return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error comparing opportunity vs wager: {e}")
            return False
    
    # ============================================================================
    # EXISTING METHODS (unchanged but compatible with new anti-duplicate system)
    # ============================================================================
    
    async def _place_initial_bets(self) -> Dict[str, Any]:
        """Place initial bets (no local tracking needed)"""
        try:
            opportunities = await self.market_scanning_service.scan_for_opportunities()
            
            if not opportunities:
                return {
                    "success": True,
                    "message": "No initial opportunities found",
                    "summary": {"total_bets": 0, "successful_bets": 0}
                }
            
            betting_decisions = self.arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
            result = await self.bet_placement_service.place_all_opportunities_batch(betting_decisions)
            
            return {
                "success": result["success"],
                "message": "Initial bets placed (will be tracked via API)",
                "summary": result.get("data", {}).get("summary", {})
            }
            
        except Exception as e:
            logger.error(f"Error placing initial bets: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error placing initial bets: {str(e)}",
                "summary": {"total_bets": 0, "successful_bets": 0}
            }
    
    async def _get_current_opportunities(self) -> List[CurrentOpportunity]:
        """Get current opportunities from scan-opportunities endpoint (unchanged)"""
        try:
            opportunities = await self.market_scanning_service.scan_for_opportunities()
            
            if not opportunities:
                return []
            
            betting_decisions = self.arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
            current_opportunities = []
            
            for decision in betting_decisions:
                if decision["action"] == "bet" and decision["type"] == "single_opportunity":
                    analysis = decision["analysis"]
                    opp = analysis.opportunity
                    
                    current_opportunities.append(CurrentOpportunity(
                        event_id=opp.event_id,
                        market_id=opp.market_id,
                        market_type=opp.market_type,
                        side=opp.large_bet_side,
                        recommended_odds=opp.our_proposed_odds,
                        recommended_stake=analysis.sizing.stake_amount,
                        large_bet_combined_size=opp.large_bet_combined_size,
                        line_id=opp.line_id,
                        opportunity_type="single"
                    ))
                
                elif decision["action"] == "bet_both" and decision["type"] == "opposing_opportunities":
                    analysis = decision["analysis"]
                    opp1 = analysis.opportunity_1
                    opp2 = analysis.opportunity_2
                    pair_id = f"arb_{opp1.event_id}_{opp1.market_id}"
                    
                    current_opportunities.extend([
                        CurrentOpportunity(
                            event_id=opp1.event_id,
                            market_id=opp1.market_id,
                            market_type=opp1.market_type,
                            side=opp1.large_bet_side,
                            recommended_odds=opp1.our_proposed_odds,
                            recommended_stake=analysis.bet_1_sizing.stake_amount,
                            large_bet_combined_size=opp1.large_bet_combined_size,
                            line_id=opp1.line_id,
                            opportunity_type="arbitrage",
                            arbitrage_pair_id=pair_id
                        ),
                        CurrentOpportunity(
                            event_id=opp2.event_id,
                            market_id=opp2.market_id,
                            market_type=opp2.market_type,
                            side=opp2.large_bet_side,
                            recommended_odds=opp2.our_proposed_odds,
                            recommended_stake=analysis.bet_2_sizing.stake_amount,
                            large_bet_combined_size=opp2.large_bet_combined_size,
                            line_id=opp2.line_id,
                            opportunity_type="arbitrage",
                            arbitrage_pair_id=pair_id
                        )
                    ])
            
            return current_opportunities
            
        except Exception as e:
            logger.error(f"Error getting current opportunities: {e}", exc_info=True)
            return []
    
    async def _execute_all_actions(self, differences: List[WagerDifference]) -> List[ActionResult]:
        """Execute all required actions based on detected differences (unchanged)"""
        results = []
        
        for diff in differences:
            try:
                if diff.action_needed == "cancel_wager":
                    result = await self._execute_cancel_wager(diff)
                elif diff.action_needed == "place_new_wager":
                    result = await self._execute_place_new_wager(diff)
                elif diff.action_needed == "update_wager":
                    result = await self._execute_update_wager(diff)
                else:
                    logger.warning(f"Unknown action: {diff.action_needed}")
                    continue
                
                results.append(result)
                self.action_history.append(result)
                self.actions_this_cycle += 1
                
                status = "✅" if result.success else "❌"
                logger.info(f"{status} {result.action_type.upper()}: {diff.line_id[:8]}... | {diff.reason}")
                if not result.success:
                    logger.error(f"   Error: {result.error}")
                
            except Exception as e:
                logger.error(f"Error executing action for {diff.line_id}: {e}")
                continue
        
        return results
    
    async def _execute_cancel_wager(self, diff: WagerDifference) -> ActionResult:
        """Cancel a specific wager (improved error handling)"""
        try:
            # Validate identifiers
            if not diff.wager_external_id or not diff.wager_prophetx_id:
                logger.error(f"❌ Cannot cancel wager {diff.line_id} - missing identifiers:")
                logger.error(f"   external_id: {diff.wager_external_id}")
                logger.error(f"   prophetx_id: {diff.wager_prophetx_id}")
                return ActionResult(
                    success=False,
                    action_type="cancel",
                    line_id=diff.line_id,
                    error=f"Missing wager identifiers - external_id: {bool(diff.wager_external_id)}, prophetx_id: {bool(diff.wager_prophetx_id)}"
                )
            
            # Validate identifier format
            if diff.wager_external_id.strip() == "" or diff.wager_prophetx_id.strip() == "":
                logger.error(f"❌ Cannot cancel wager {diff.line_id} - empty identifiers:")
                logger.error(f"   external_id: '{diff.wager_external_id}'")
                logger.error(f"   prophetx_id: '{diff.wager_prophetx_id}'")
                return ActionResult(
                    success=False,
                    action_type="cancel",
                    line_id=diff.line_id,
                    error="Empty wager identifiers"
                )
            
            logger.info(f"🗑️ Cancelling wager: external_id={diff.wager_external_id[:12]}..., prophetx_id={diff.wager_prophetx_id[:12]}...")
            
            cancel_result = await self.prophetx_service.cancel_wager(
                external_id=diff.wager_external_id,
                wager_id=diff.wager_prophetx_id
            )
            
            if cancel_result["success"]:
                logger.info(f"✅ Wager cancelled successfully: {diff.wager_external_id[:12]}...")
                return ActionResult(
                    success=True,
                    action_type="cancel",
                    line_id=diff.line_id,
                    external_id=diff.wager_external_id,
                    prophetx_wager_id=diff.wager_prophetx_id,
                    details=cancel_result
                )
            else:
                error_msg = cancel_result.get("error", "Cancellation failed")
                logger.error(f"❌ ProphetX cancellation failed: {error_msg}")
                return ActionResult(
                    success=False,
                    action_type="cancel",
                    line_id=diff.line_id,
                    external_id=diff.wager_external_id,
                    prophetx_wager_id=diff.wager_prophetx_id,
                    error=error_msg
                )
                
        except Exception as e:
            logger.error(f"❌ Exception during cancellation: {e}", exc_info=True)
            return ActionResult(
                success=False,
                action_type="cancel",
                line_id=diff.line_id,
                error=f"Exception during cancellation: {str(e)}"
            )
    
    async def _execute_place_new_wager(self, diff: WagerDifference) -> ActionResult:
        """Place a new wager with exposure and wait period checks"""
        try:
            # Check exposure limits
            current_exposure = self.line_exposure[diff.line_id]
            max_allowed = diff.recommended_stake * self.max_exposure_multiplier
            
            if current_exposure + diff.recommended_stake > max_allowed:
                return ActionResult(
                    success=False,
                    action_type="place",
                    line_id=diff.line_id,
                    error=f"Would exceed exposure limit: ${current_exposure + diff.recommended_stake:.2f} > ${max_allowed:.2f}"
                )
            
            # Check fill wait period
            if diff.line_id in self.recent_fills:
                fill_time = self.recent_fills[diff.line_id]
                time_since_fill = (datetime.now(timezone.utc) - fill_time).total_seconds()
                if time_since_fill < self.fill_wait_period_seconds:
                    wait_remaining = self.fill_wait_period_seconds - time_since_fill
                    return ActionResult(
                        success=False,
                        action_type="place",
                        line_id=diff.line_id,
                        error=f"Fill wait period: {wait_remaining:.0f}s remaining"
                    )
            
            # Generate external ID
            timestamp_ms = int(time.time() * 1000)
            unique_suffix = uuid.uuid4().hex[:8]
            external_id = f"monitor_{timestamp_ms}_{unique_suffix}"
            
            # Place the wager
            place_result = await self.prophetx_service.place_bet(
                line_id=diff.line_id,
                odds=diff.recommended_odds,
                stake=diff.recommended_stake,
                external_id=external_id
            )
            
            if place_result["success"]:
                prophetx_wager_id = (
                    place_result.get("prophetx_bet_id") or 
                    place_result.get("bet_id") or 
                    "unknown"
                )
                
                return ActionResult(
                    success=True,
                    action_type="place",
                    line_id=diff.line_id,
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    details=place_result
                )
            else:
                return ActionResult(
                    success=False,
                    action_type="place",
                    line_id=diff.line_id,
                    error=place_result.get("error", "Placement failed")
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="place",
                line_id=diff.line_id,
                error=f"Exception during placement: {str(e)}"
            )
    
    async def _execute_update_wager(self, diff: WagerDifference) -> ActionResult:
        """Update a wager by canceling the old one and placing a new one"""
        try:
            # Step 1: Cancel the existing wager
            cancel_result = await self._execute_cancel_wager(diff)
            
            if not cancel_result.success:
                return ActionResult(
                    success=False,
                    action_type="update",
                    line_id=diff.line_id,
                    error=f"Cancel failed during update: {cancel_result.error}"
                )
            
            # Small delay between cancel and place
            await asyncio.sleep(0.5)
            
            # Step 2: Place the new wager
            place_result = await self._execute_place_new_wager(diff)
            
            if place_result.success:
                return ActionResult(
                    success=True,
                    action_type="update",
                    line_id=diff.line_id,
                    external_id=place_result.external_id,
                    prophetx_wager_id=place_result.prophetx_wager_id,
                    details={
                        "cancelled_wager": cancel_result.details,
                        "new_wager": place_result.details
                    }
                )
            else:
                return ActionResult(
                    success=False,
                    action_type="update",
                    line_id=diff.line_id,
                    error=f"Place failed after cancel: {place_result.error}",
                    details={
                        "cancelled_wager": cancel_result.details,
                        "place_error": place_result.error
                    }
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="update",
                line_id=diff.line_id,
                error=f"Exception during update: {str(e)}"
            )
    
    # ============================================================================
    # API STATUS AND REPORTING
    # ============================================================================
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status with API-based info"""
        active_wagers = [w for w in self.current_wagers if w.is_active]
        filled_wagers = [w for w in self.current_wagers if w.is_filled]
        
        return {
            "monitoring_active": self.monitoring_active,
            "monitoring_cycles": self.monitoring_cycles,
            "api_based_tracking": True,
            "current_wagers": {
                "total_fetched": len(self.current_wagers),
                "active_wagers": len(active_wagers),
                "filled_wagers": len(filled_wagers),
                "system_wagers": len([w for w in self.current_wagers if w.is_system_bet])
            },
            "last_api_fetch": {
                "fetch_time": self.last_wager_fetch_time.isoformat() if self.last_wager_fetch_time else None,
                "fetch_duration": self.wager_fetch_duration,
                "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None
            },
            "action_execution": {
                "total_actions_executed": len(self.action_history),
                "actions_this_cycle": self.actions_this_cycle,
                "recent_actions": [
                    {
                        "action_type": action.action_type,
                        "line_id": action.line_id[:8] + "...",
                        "success": action.success,
                        "error": action.error
                    }
                    for action in self.action_history[-5:]
                ]
            },
            "settings": {
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "fill_wait_period_seconds": self.fill_wait_period_seconds,
                "max_exposure_multiplier": self.max_exposure_multiplier
            }
        }
    
    async def get_current_wagers(self) -> Dict[str, Any]:
        """Get current wagers from API (for manual inspection)"""
        return {
            "success": True,
            "message": f"Retrieved {len(self.current_wagers)} current wagers from API",
            "data": {
                "total_wagers": len(self.current_wagers),
                "active_wagers": len([w for w in self.current_wagers if w.is_active]),
                "filled_wagers": len([w for w in self.current_wagers if w.is_filled]),
                "wagers": [
                    {
                        "external_id": w.external_id,
                        "wager_id": w.wager_id,
                        "line_id": w.line_id,
                        "side": w.side,
                        "odds": w.odds,
                        "stake": w.stake,
                        "matched_stake": w.matched_stake,
                        "unmatched_stake": w.unmatched_stake,
                        "status": w.status,
                        "matching_status": w.matching_status,
                        "is_active": w.is_active,
                        "is_filled": w.is_filled
                    }
                    for w in self.current_wagers if w.is_system_bet
                ]
            }
        }


# Global service instance
high_wager_monitoring_service = HighWagerMonitoringService()