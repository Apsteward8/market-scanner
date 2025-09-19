#!/usr/bin/env python3
"""
High Wager Monitoring Service - FULLY FIXED VERSION

Key Fixes:
1. Allow odds updates during fill wait periods (critical for avoiding stale prices)
2. Refill based on current strategy, not just matched amount
3. Consolidate multiple wagers on same line into single wager after wait period
4. Always use current recommended stakes from market strategy
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
    # Recommended info (ALWAYS based on current strategy)
    recommended_odds: int
    recommended_stake: float
    # Analysis
    difference_type: str  # "odds_change", "stake_change", "new_opportunity", "remove_opportunity", "consolidate_position"
    action_needed: str  # "update_wager", "cancel_wager", "place_new_wager", "consolidate_position", "no_action"
    reason: str
    # FIXED: Add stake_to_place for consolidation
    stake_to_place: Optional[float] = None
    # API wager identifiers for actions (for cancellation)
    all_wager_external_ids: Optional[List[str]] = None
    all_wager_prophetx_ids: Optional[List[str]] = None
    # Primary wager (for single wager updates)
    wager_external_id: Optional[str] = None
    wager_prophetx_id: Optional[str] = None

@dataclass
class ActionResult:
    """Result of executing an action"""
    success: bool
    action_type: str  # "cancel", "place", "update", "consolidate"
    line_id: str
    external_id: Optional[str] = None
    prophetx_wager_id: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@dataclass
class WagerState:
    """Track previous wager state to detect fills"""
    line_id: str
    external_id: str
    wager_id: str
    previous_matched_stake: float
    previous_unmatched_stake: float
    last_seen: datetime

class HighWagerMonitoringService:
    """FULLY FIXED: Proper odds updates during wait periods + position consolidation"""
    
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
        
        # Track previous wager states to detect fills
        self.previous_wager_states: Dict[str, WagerState] = {}  # external_id -> WagerState
        
        # Action tracking
        self.action_history: List[ActionResult] = []
        self.actions_this_cycle = 0
        
        # FIXED: Proper fill detection and wait periods
        self.line_fill_times: Dict[str, datetime] = {}  # line_id -> last_fill_time
        self.line_exposure: Dict[str, float] = defaultdict(float)  # line_id -> total_unmatched_stake
        
    def initialize_services(self, market_scanning_service, arbitrage_service, 
                          bet_placement_service, prophetx_service):
        """Initialize required services"""
        self.market_scanning_service = market_scanning_service
        self.arbitrage_service = arbitrage_service
        self.bet_placement_service = bet_placement_service
        self.prophetx_service = prophetx_service
        logger.info("🔧 High wager monitoring services initialized")
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """Start monitoring with fully fixed logic"""
        if self.monitoring_active:
            return {
                "success": False,
                "message": "Monitoring already active"
            }
        
        logger.info("🚀 Starting FULLY FIXED High Wager Monitoring Service")
        logger.info("=" * 70)
        
        # Step 1: Place initial bets
        logger.info("📍 Step 1: Placing initial bets...")
        initial_result = await self._place_initial_bets()
        
        if not initial_result["success"]:
            return {
                "success": False,
                "message": f"Failed to place initial bets: {initial_result.get('error', 'Unknown error')}"
            }
        
        # Step 2: Wait for ProphetX to process bets
        logger.info("⏳ Step 2: Waiting for ProphetX to process initial bets...")
        await asyncio.sleep(10)
        
        # Step 3: Initialize wager state tracking
        logger.info("📋 Step 3: Initializing wager state tracking...")
        await self._fetch_current_wagers_from_api()
        self._initialize_wager_state_tracking()
        
        # Step 4: Start monitoring loop
        self.monitoring_active = True
        self.monitoring_cycles = 0
        asyncio.create_task(self._fully_fixed_monitoring_loop())
        
        return {
            "success": True,
            "message": "FULLY FIXED monitoring started", 
            "data": {
                "initial_bets": initial_result,
                "initial_wager_states_tracked": len(self.previous_wager_states),
                "critical_fixes": [
                    "✅ Allow odds updates during fill wait periods",
                    "✅ Refill based on current strategy (not just matched amount)",
                    "✅ Consolidate multiple wagers into single position",
                    "✅ Always use current recommended stakes"
                ]
            }
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop the monitoring loop"""
        self.monitoring_active = False
        
        return {
            "success": True,
            "message": "FULLY FIXED monitoring stopped",
            "data": {
                "monitoring_cycles_completed": self.monitoring_cycles,
                "current_active_wagers": len([w for w in self.current_wagers if w.is_active]),
                "total_actions_executed": len(self.action_history)
            }
        }
    
    # ============================================================================
    # FULLY FIXED MONITORING LOOP
    # ============================================================================
    
    async def _fully_fixed_monitoring_loop(self):
        """FULLY FIXED: Main monitoring loop with proper wait period handling"""
        logger.info("🔄 Starting FULLY FIXED monitoring loop...")
        
        while self.monitoring_active:
            try:
                cycle_start = datetime.now(timezone.utc)
                self.monitoring_cycles += 1
                self.actions_this_cycle = 0
                
                logger.info(f"🔍 FULLY FIXED Monitoring cycle #{self.monitoring_cycles} starting...")
                
                # Step 1: Fetch current wagers from ProphetX API
                logger.info("📋 Fetching current wagers from ProphetX API...")
                await self._fetch_current_wagers_from_api()
                
                # Step 2: Detect fills by comparing with previous states
                fills_detected = self._detect_fills_from_state_changes()
                if fills_detected:
                    logger.info(f"🎯 FILL DETECTION: {len(fills_detected)} fills detected this cycle")
                    for fill in fills_detected:
                        logger.info(f"   💰 Fill: {fill['line_id'][:8]}... filled ${fill['amount_filled']:.2f}")
                
                # Step 3: Update previous states for next cycle
                self._update_wager_state_tracking()
                
                # Step 4: Get current market opportunities (ALWAYS current strategy)
                current_opportunities = await self._get_current_opportunities()
                
                # Step 5: FIXED - Detect differences with proper wait period logic
                differences = await self._fully_fixed_detect_differences(current_opportunities)
                
                # Step 6: Execute actions based on differences
                if differences:
                    logger.info(f"⚡ Executing {len(differences)} actions...")
                    await self._execute_all_actions(differences)
                else:
                    logger.info("✅ No differences detected - all wagers up to date")
                
                # Step 7: Update exposure tracking
                self._update_exposure_tracking()
                
                # Step 8: Log cycle summary
                active_wagers = len([w for w in self.current_wagers if w.is_active and w.is_system_bet])
                filled_wagers = len([w for w in self.current_wagers if w.is_filled and w.is_system_bet])
                
                # Count unique lines (not individual wagers)
                active_lines = len(set(w.line_id for w in self.current_wagers if w.is_active and w.is_system_bet))
                
                logger.info(f"📊 Cycle #{self.monitoring_cycles} complete:")
                logger.info(f"   🎯 {active_wagers} active system wagers on {active_lines} unique lines")
                logger.info(f"   💰 {len(fills_detected)} fills detected this cycle")
                logger.info(f"   ⏰ {len([l for l, t in self.line_fill_times.items() if (cycle_start - t).total_seconds() < self.fill_wait_period_seconds])} lines in fill wait period")
                logger.info(f"   ⚡ {self.actions_this_cycle} actions executed")
                
                # Update tracking
                self.last_scan_time = cycle_start
                
                # Wait for next cycle
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.monitoring_interval_seconds - cycle_duration)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in FULLY FIXED monitoring cycle: {e}", exc_info=True)
                await asyncio.sleep(self.monitoring_interval_seconds)
    
    # ============================================================================
    # FULLY FIXED DIFFERENCE DETECTION (Critical Fix!)
    # ============================================================================
    
    async def _fully_fixed_detect_differences(self, current_opportunities: List[CurrentOpportunity]) -> List[WagerDifference]:
        """FULLY FIXED: Allow odds updates during wait periods, block only refills"""
        differences = []
        now = datetime.now(timezone.utc)
        
        # Filter to active system wagers only
        active_system_wagers = [
            w for w in self.current_wagers 
            if w.is_system_bet and w.is_active and w.external_id and w.wager_id
        ]
        
        logger.info(f"🔍 FULLY FIXED: Comparing {len(active_system_wagers)} active system wagers vs {len(current_opportunities)} opportunities")
        
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
            
            # CRITICAL FIX: Check if line is in fill wait period
            is_in_wait_period = False
            wait_remaining = 0
            
            if line_id in self.line_fill_times:
                fill_time = self.line_fill_times[line_id]
                time_since_fill = (now - fill_time).total_seconds()
                
                if time_since_fill < self.fill_wait_period_seconds:
                    is_in_wait_period = True
                    wait_remaining = self.fill_wait_period_seconds - time_since_fill
                    logger.info(f"⏰ WAIT PERIOD: Line {line_id[:8]}... has {wait_remaining:.0f}s remaining")
                else:
                    logger.info(f"✅ WAIT PERIOD EXPIRED: Line {line_id[:8]}... can now be consolidated")
                    # Remove from wait period tracking
                    del self.line_fill_times[line_id]
            
            if opportunities and api_wagers:
                # Both exist - check for differences
                total_current_unmatched = sum(w.unmatched_stake for w in api_wagers)
                current_odds = api_wagers[0].odds  # First wager's odds
                
                # Find matching opportunity (ALWAYS uses current strategy)
                matching_opp = self._find_matching_opportunity_by_line(api_wagers[0], opportunities)
                
                if matching_opp:
                    # CRITICAL FIX: Different logic based on wait period status
                    if is_in_wait_period:
                        # During wait period: ONLY allow odds updates
                        diff = self._check_odds_changes_only(line_id, api_wagers, matching_opp, total_current_unmatched)
                        if diff:
                            logger.info(f"🔄 ODDS UPDATE during wait period: {diff.reason}")
                            differences.append(diff)
                        else:
                            logger.debug(f"⏰ No odds change needed during wait period for {line_id[:8]}...")
                    else:
                        # After wait period: Check for consolidation or normal updates
                        if len(api_wagers) > 1:
                            # Multiple wagers on same line - consolidate into one
                            diff = self._create_consolidation_action(line_id, api_wagers, matching_opp)
                            if diff:
                                logger.info(f"🔄 CONSOLIDATION needed: {len(api_wagers)} wagers → 1 wager")
                                differences.append(diff)
                        else:
                            # Single wager - normal comparison
                            diff = self._fully_fixed_compare_single_wager(line_id, api_wagers[0], matching_opp, total_current_unmatched)
                            if diff:
                                differences.append(diff)
                else:
                    # No matching opportunity - cancel all wagers on this line (regardless of wait period)
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
            
            elif opportunities and not api_wagers:
                # New opportunities - place new wagers (only if not in wait period)
                if not is_in_wait_period:
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
                            reason=f"New opportunity detected for {opp.market_type}",
                            stake_to_place=opp.recommended_stake
                        ))
                else:
                    logger.info(f"⏰ Skipping new opportunity placement during wait period: {line_id[:8]}...")
            
            elif api_wagers and not opportunities:
                # Cancel all API wagers on this line (regardless of wait period)
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
        
        logger.info(f"📊 FULLY FIXED: Detected {len(differences)} differences requiring action")
        return differences
    
    def _check_odds_changes_only(self, line_id: str, api_wagers: List[ApiWager], 
                                opportunity: CurrentOpportunity, total_current_unmatched: float) -> Optional[WagerDifference]:
        """During wait period: Only check for odds changes, ignore stake differences"""
        
        primary_wager = api_wagers[0]
        current_odds = primary_wager.odds
        recommended_odds = opportunity.recommended_odds
        
        # ONLY check for odds changes during wait period
        if current_odds != recommended_odds:
            logger.info(f"🔄 CRITICAL ODDS UPDATE during wait period: {current_odds:+d} → {recommended_odds:+d}")
            return WagerDifference(
                line_id=line_id,
                event_id=primary_wager.event_id,
                market_id=primary_wager.market_id,
                market_type=opportunity.market_type,
                side=primary_wager.side,
                current_odds=current_odds,
                current_stake=total_current_unmatched,
                current_status=primary_wager.status,
                current_matching_status=primary_wager.matching_status,
                recommended_odds=recommended_odds,
                recommended_stake=opportunity.recommended_stake,
                difference_type="odds_change",
                action_needed="update_wager",
                reason=f"CRITICAL: Odds changed from {current_odds:+d} to {recommended_odds:+d} (during wait period)",
                wager_external_id=primary_wager.external_id,
                wager_prophetx_id=primary_wager.wager_id
            )
        
        return None
    
    def _create_consolidation_action(self, line_id: str, api_wagers: List[ApiWager], 
                                   opportunity: CurrentOpportunity) -> Optional[WagerDifference]:
        """Create action to consolidate multiple wagers into single wager"""
        
        primary_wager = api_wagers[0]
        total_current_unmatched = sum(w.unmatched_stake for w in api_wagers)
        
        # Collect all wager IDs for cancellation
        all_external_ids = [w.external_id for w in api_wagers if w.external_id]
        all_prophetx_ids = [w.wager_id for w in api_wagers if w.wager_id]
        
        return WagerDifference(
            line_id=line_id,
            event_id=primary_wager.event_id,
            market_id=primary_wager.market_id,
            market_type=opportunity.market_type,
            side=primary_wager.side,
            current_odds=primary_wager.odds,
            current_stake=total_current_unmatched,
            current_status=primary_wager.status,
            current_matching_status=primary_wager.matching_status,
            recommended_odds=opportunity.recommended_odds,
            recommended_stake=opportunity.recommended_stake,
            difference_type="consolidate_position",
            action_needed="consolidate_position",
            reason=f"Consolidate {len(api_wagers)} wagers into single position (current: ${total_current_unmatched:.2f}, target: ${opportunity.recommended_stake:.2f})",
            stake_to_place=opportunity.recommended_stake,
            all_wager_external_ids=all_external_ids,
            all_wager_prophetx_ids=all_prophetx_ids
        )
    
    def _fully_fixed_compare_single_wager(self, line_id: str, wager: ApiWager, 
                                        opportunity: CurrentOpportunity, total_current_unmatched: float) -> Optional[WagerDifference]:
        """Compare single wager vs opportunity (after wait period)"""
        
        current_odds = wager.odds
        recommended_odds = opportunity.recommended_odds
        recommended_stake = opportunity.recommended_stake
        
        # Check for odds changes
        if current_odds != recommended_odds:
            logger.debug(f"📊 Odds change detected: {wager.side} {current_odds:+d} → {recommended_odds:+d}")
            return WagerDifference(
                line_id=line_id,
                event_id=wager.event_id,
                market_id=wager.market_id,
                market_type=opportunity.market_type,
                side=wager.side,
                current_odds=current_odds,
                current_stake=total_current_unmatched,
                current_status=wager.status,
                current_matching_status=wager.matching_status,
                recommended_odds=recommended_odds,
                recommended_stake=recommended_stake,
                difference_type="odds_change",
                action_needed="update_wager",
                reason=f"Odds changed from {current_odds:+d} to {recommended_odds:+d}",
                wager_external_id=wager.external_id,
                wager_prophetx_id=wager.wager_id
            )
        
        # FIXED: Check stake differences based on CURRENT strategy
        stake_difference = recommended_stake - total_current_unmatched
        
        if stake_difference > 5.0:  # Need to add more stake
            max_allowed_total = recommended_stake * self.max_exposure_multiplier
            max_additional = max_allowed_total - total_current_unmatched
            
            stake_to_add = min(stake_difference, max_additional)
            
            if stake_to_add > 5.0:  # Only add if meaningful amount
                logger.info(f"💰 REFILL NEEDED based on current strategy: {wager.side}")
                logger.info(f"   Current unmatched: ${total_current_unmatched:.2f}")
                logger.info(f"   Current strategy target: ${recommended_stake:.2f}")
                logger.info(f"   Need to add: ${stake_to_add:.2f}")
                
                # Use consolidation instead of adding to avoid multiple wagers
                return WagerDifference(
                    line_id=line_id,
                    event_id=wager.event_id,
                    market_id=wager.market_id,
                    market_type=opportunity.market_type,
                    side=wager.side,
                    current_odds=current_odds,
                    current_stake=total_current_unmatched,
                    current_status=wager.status,
                    current_matching_status=wager.matching_status,
                    recommended_odds=recommended_odds,
                    recommended_stake=recommended_stake,
                    difference_type="consolidate_position",
                    action_needed="consolidate_position",
                    reason=f"Refill based on current strategy: ${total_current_unmatched:.2f} → ${recommended_stake:.2f}",
                    stake_to_place=recommended_stake,
                    all_wager_external_ids=[wager.external_id],
                    all_wager_prophetx_ids=[wager.wager_id]
                )
        
        return None
    
    # ============================================================================
    # ENHANCED ACTION EXECUTION (Consolidation Support)
    # ============================================================================
    
    async def _execute_all_actions(self, differences: List[WagerDifference]) -> List[ActionResult]:
        """Execute all required actions with consolidation support"""
        results = []
        
        for diff in differences:
            try:
                if diff.action_needed == "cancel_wager":
                    result = await self._execute_cancel_wager(diff)
                elif diff.action_needed == "place_new_wager":
                    result = await self._execute_place_new_wager(diff)
                elif diff.action_needed == "update_wager":
                    result = await self._execute_update_wager(diff)
                elif diff.action_needed == "consolidate_position":
                    # NEW: Consolidate multiple wagers into single position
                    result = await self._execute_consolidate_position(diff)
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
    
    async def _execute_consolidate_position(self, diff: WagerDifference) -> ActionResult:
        """NEW: Consolidate multiple wagers into single position"""
        try:
            logger.info(f"🔄 CONSOLIDATING position on line {diff.line_id[:8]}...")
            logger.info(f"   Target: ${diff.stake_to_place:.2f} at {diff.recommended_odds:+d}")
            logger.info(f"   Cancelling {len(diff.all_wager_external_ids or [])} existing wagers")
            
            # Step 1: Cancel ALL existing wagers on this line
            cancelled_count = 0
            cancel_errors = []
            
            for i, (external_id, prophetx_id) in enumerate(zip(
                diff.all_wager_external_ids or [], 
                diff.all_wager_prophetx_ids or []
            )):
                try:
                    cancel_result = await self.prophetx_service.cancel_wager(
                        external_id=external_id,
                        wager_id=prophetx_id
                    )
                    
                    if cancel_result["success"]:
                        cancelled_count += 1
                        logger.info(f"   ✅ Cancelled wager {i+1}: {external_id[:12]}...")
                    else:
                        error_msg = cancel_result.get("error", "Unknown error")
                        cancel_errors.append(f"Wager {i+1}: {error_msg}")
                        logger.error(f"   ❌ Failed to cancel wager {i+1}: {error_msg}")
                
                except Exception as e:
                    cancel_errors.append(f"Wager {i+1}: {str(e)}")
                    logger.error(f"   ❌ Exception cancelling wager {i+1}: {e}")
                
                # Small delay between cancellations
                if i < len(diff.all_wager_external_ids or []) - 1:
                    await asyncio.sleep(0.2)
            
            if cancelled_count == 0:
                return ActionResult(
                    success=False,
                    action_type="consolidate",
                    line_id=diff.line_id,
                    error=f"Failed to cancel any existing wagers: {'; '.join(cancel_errors)}"
                )
            
            # Step 2: Wait for cancellations to process
            await asyncio.sleep(1.0)
            
            # Step 3: Place ONE new consolidated wager
            timestamp_ms = int(time.time() * 1000)
            unique_suffix = uuid.uuid4().hex[:8]
            external_id = f"consolidated_{timestamp_ms}_{unique_suffix}"
            
            logger.info(f"   📍 Placing consolidated wager: ${diff.stake_to_place:.2f} at {diff.recommended_odds:+d}")
            
            place_result = await self.prophetx_service.place_bet(
                line_id=diff.line_id,
                odds=diff.recommended_odds,
                stake=diff.stake_to_place,
                external_id=external_id
            )
            
            if place_result["success"]:
                prophetx_wager_id = (
                    place_result.get("prophetx_bet_id") or 
                    place_result.get("bet_id") or 
                    "unknown"
                )
                
                logger.info(f"✅ CONSOLIDATION COMPLETE: {cancelled_count} wagers → 1 wager (${diff.stake_to_place:.2f})")
                
                return ActionResult(
                    success=True,
                    action_type="consolidate",
                    line_id=diff.line_id,
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    details={
                        "wagers_cancelled": cancelled_count,
                        "cancel_errors": cancel_errors,
                        "new_stake": diff.stake_to_place,
                        "new_odds": diff.recommended_odds,
                        "place_result": place_result
                    }
                )
            else:
                return ActionResult(
                    success=False,
                    action_type="consolidate",
                    line_id=diff.line_id,
                    error=f"Cancelled {cancelled_count} wagers but failed to place new one: {place_result.get('error')}"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="consolidate",
                line_id=diff.line_id,
                error=f"Exception during consolidation: {str(e)}"
            )
    
    # ============================================================================
    # KEEP ALL EXISTING METHODS (fill detection, API fetching, etc.)
    # ============================================================================
    
    def _initialize_wager_state_tracking(self):
        """Initialize tracking of current wager states"""
        self.previous_wager_states.clear()
        
        for wager in self.current_wagers:
            if wager.is_system_bet and wager.external_id:
                self.previous_wager_states[wager.external_id] = WagerState(
                    line_id=wager.line_id,
                    external_id=wager.external_id,
                    wager_id=wager.wager_id,
                    previous_matched_stake=wager.matched_stake,
                    previous_unmatched_stake=wager.unmatched_stake,
                    last_seen=datetime.now(timezone.utc)
                )
        
        logger.info(f"📊 Initialized state tracking for {len(self.previous_wager_states)} system wagers")
    
    def _detect_fills_from_state_changes(self) -> List[Dict[str, Any]]:
        """Detect fills by comparing matched_stake changes"""
        fills_detected = []
        now = datetime.now(timezone.utc)
        
        for wager in self.current_wagers:
            if not wager.is_system_bet or not wager.external_id:
                continue
                
            # Check if we have previous state for this wager
            if wager.external_id in self.previous_wager_states:
                prev_state = self.previous_wager_states[wager.external_id]
                
                # Detect fill by checking if matched_stake increased
                if wager.matched_stake > prev_state.previous_matched_stake:
                    amount_filled = wager.matched_stake - prev_state.previous_matched_stake
                    
                    logger.info(f"🎯 FILL DETECTED: {wager.external_id[:12]}...")
                    logger.info(f"   Line: {wager.line_id[:8]}...")
                    logger.info(f"   Previous matched: ${prev_state.previous_matched_stake:.2f}")
                    logger.info(f"   Current matched: ${wager.matched_stake:.2f}")
                    logger.info(f"   Amount filled: ${amount_filled:.2f}")
                    logger.info(f"   Remaining unmatched: ${wager.unmatched_stake:.2f}")
                    
                    # Record the fill time for this line (start wait period)
                    self.line_fill_times[wager.line_id] = now
                    
                    fills_detected.append({
                        "external_id": wager.external_id,
                        "line_id": wager.line_id,
                        "amount_filled": amount_filled,
                        "current_matched": wager.matched_stake,
                        "current_unmatched": wager.unmatched_stake,
                        "fill_time": now
                    })
        
        return fills_detected
    
    def _update_wager_state_tracking(self):
        """Update previous wager states for next cycle comparison"""
        # Clear old states
        self.previous_wager_states.clear()
        
        # Record current states as previous for next cycle
        for wager in self.current_wagers:
            if wager.is_system_bet and wager.external_id:
                self.previous_wager_states[wager.external_id] = WagerState(
                    line_id=wager.line_id,
                    external_id=wager.external_id,
                    wager_id=wager.wager_id,
                    previous_matched_stake=wager.matched_stake,
                    previous_unmatched_stake=wager.unmatched_stake,
                    last_seen=datetime.now(timezone.utc)
                )
    
    def _find_matching_opportunity_by_line(self, wager: ApiWager, opportunities: List[CurrentOpportunity]) -> Optional[CurrentOpportunity]:
        """Find opportunity that matches a wager by line_id and side"""
        for opp in opportunities:
            if (wager.line_id == opp.line_id and 
                self._sides_match(wager.side, opp.side)):
                return opp
        return None
    
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
    
    def _update_exposure_tracking(self):
        """Update line exposure tracking from current wagers"""
        self.line_exposure.clear()
        
        for wager in self.current_wagers:
            if wager.is_system_bet and wager.is_active:
                self.line_exposure[wager.line_id] += wager.unmatched_stake
    
    # Keep all existing methods for API fetching, conversion, etc...
    async def _fetch_current_wagers_from_api(self):
        """Fetch current wagers from ProphetX API with pagination (unchanged)"""
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
            
            logger.info(f"📋 Fetched {len(all_wagers)} total wagers from {page_count} pages")
            logger.info(f"   🤖 {len(system_wagers)} system wagers (with external_id)")
            logger.info(f"   ✅ {len(active_wagers)} active system wagers")
            
        except Exception as e:
            logger.error(f"Error fetching current wagers: {e}", exc_info=True)
            self.current_wagers = []
    
    def _convert_to_api_wagers(self, raw_wagers: List[Dict]) -> List[ApiWager]:
        """Convert raw API response to ApiWager objects (unchanged)"""
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
                is_system_bet = bool(external_id and external_id.strip())
                is_active = (
                    status in ["open", "active", "inactive"] and
                    matching_status in ["unmatched", "partially_matched"] and
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
                
                api_wagers.append(api_wager)
                
            except Exception as e:
                logger.warning(f"Error converting wager {wager.get('id', 'unknown')}: {e}")
                continue
        
        return api_wagers
    
    # Keep other existing methods...
    async def _place_initial_bets(self) -> Dict[str, Any]:
        """Place initial bets (unchanged)"""
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
    
    # Keep other execution methods (cancel, place, update)...
    async def _execute_cancel_wager(self, diff: WagerDifference) -> ActionResult:
        """Cancel a specific wager (unchanged)"""
        try:
            if not diff.wager_external_id or not diff.wager_prophetx_id:
                return ActionResult(
                    success=False,
                    action_type="cancel",
                    line_id=diff.line_id,
                    error=f"Missing wager identifiers"
                )
            
            cancel_result = await self.prophetx_service.cancel_wager(
                external_id=diff.wager_external_id,
                wager_id=diff.wager_prophetx_id
            )
            
            return ActionResult(
                success=cancel_result["success"],
                action_type="cancel",
                line_id=diff.line_id,
                external_id=diff.wager_external_id,
                prophetx_wager_id=diff.wager_prophetx_id,
                error=cancel_result.get("error") if not cancel_result["success"] else None,
                details=cancel_result
            )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="cancel",
                line_id=diff.line_id,
                error=f"Exception during cancellation: {str(e)}"
            )
    
    async def _execute_place_new_wager(self, diff: WagerDifference) -> ActionResult:
        """Place a new wager"""
        try:
            stake_to_place = diff.stake_to_place or diff.recommended_stake
            
            # Check exposure limits
            current_exposure = self.line_exposure[diff.line_id]
            max_allowed = diff.recommended_stake * self.max_exposure_multiplier
            
            if current_exposure + stake_to_place > max_allowed:
                return ActionResult(
                    success=False,
                    action_type="place",
                    line_id=diff.line_id,
                    error=f"Would exceed exposure limit: ${current_exposure + stake_to_place:.2f} > ${max_allowed:.2f}"
                )
            
            # Generate external ID
            timestamp_ms = int(time.time() * 1000)
            unique_suffix = uuid.uuid4().hex[:8]
            external_id = f"monitor_{timestamp_ms}_{unique_suffix}"
            
            # Place the wager
            place_result = await self.prophetx_service.place_bet(
                line_id=diff.line_id,
                odds=diff.recommended_odds,
                stake=stake_to_place,
                external_id=external_id
            )
            
            return ActionResult(
                success=place_result["success"],
                action_type="place",
                line_id=diff.line_id,
                external_id=external_id if place_result["success"] else None,
                prophetx_wager_id=place_result.get("prophetx_bet_id") if place_result["success"] else None,
                error=place_result.get("error") if not place_result["success"] else None,
                details=place_result
            )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="place",
                line_id=diff.line_id,
                error=f"Exception during placement: {str(e)}"
            )
    
    async def _execute_update_wager(self, diff: WagerDifference) -> ActionResult:
        """Update a wager by canceling and replacing"""
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
            
            # Step 2: Place the new wager with current strategy amount
            # Use recommended_stake (current strategy) not current_stake
            diff.stake_to_place = diff.recommended_stake
            place_result = await self._execute_place_new_wager(diff)
            
            return ActionResult(
                success=place_result.success,
                action_type="update",
                line_id=diff.line_id,
                external_id=place_result.external_id if place_result.success else None,
                prophetx_wager_id=place_result.prophetx_wager_id if place_result.success else None,
                error=place_result.error if not place_result.success else None,
                details={
                    "cancelled_wager": cancel_result.details,
                    "new_wager": place_result.details if place_result.success else place_result.error
                }
            )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="update",
                line_id=diff.line_id,
                error=f"Exception during update: {str(e)}"
            )
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        active_wagers = [w for w in self.current_wagers if w.is_active]
        filled_wagers = [w for w in self.current_wagers if w.is_filled]
        
        # Count unique lines
        active_lines = len(set(w.line_id for w in self.current_wagers if w.is_active and w.is_system_bet))
        
        return {
            "monitoring_active": self.monitoring_active,
            "monitoring_cycles": self.monitoring_cycles,
            "version": "FULLY FIXED - Odds updates during wait + consolidation + current strategy",
            "current_wagers": {
                "total_fetched": len(self.current_wagers),
                "active_wagers": len(active_wagers),
                "active_unique_lines": active_lines,
                "filled_wagers": len(filled_wagers),
                "system_wagers": len([w for w in self.current_wagers if w.is_system_bet])
            },
            "fill_tracking": {
                "wager_states_tracked": len(self.previous_wager_states),
                "lines_in_wait_period": len(self.line_fill_times),
                "wait_period_seconds": self.fill_wait_period_seconds
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
            },
            "fully_fixed_features": [
                "✅ Allow odds updates during fill wait periods",
                "✅ Refill based on current strategy (not just matched amount)",
                "✅ Consolidate multiple wagers into single position", 
                "✅ Always use current recommended stakes from market",
                "✅ Track unique lines vs individual wagers"
            ]
        }
    
    async def get_current_wagers(self) -> Dict[str, Any]:
        """Get current wagers from API"""
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