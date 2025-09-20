#!/usr/bin/env python3
"""
High Wager Monitoring Service - ENHANCED WITH COMPREHENSIVE EXPOSURE LIMITS

Key Enhancements:
1. Calculate total exposure per line from API wager history (matched + unmatched)
2. Check 3x exposure limits before ALL wager placements
3. Adjust stake amounts when hitting limits
4. Apply exposure checking to initial placement, monitoring, and consolidation

CRITICAL FILL WAIT PERIOD LOGIC:
📍 When fills are detected → Start 5-minute wait period
⏰ During wait period → ONLY allow odds changes (no stake changes)
✅ After wait period → Consolidate ALL wagers into ONE wager with CURRENT strategy amount

Fill Logic Flow:
1. _detect_fills_from_state_changes() → Sets line_fill_times[line_id] = now
2. During monitoring → Check if line_id in line_fill_times with < 300 seconds
3. If in wait period → _check_odds_changes_only() (NO stake changes)
4. If wait expired → Consolidate to single wager with current recommended_stake
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
class LineExposure:
    """Track total exposure for a specific line"""
    line_id: str
    total_stake: float  # Total stake placed (matched + unmatched)
    matched_stake: float  # Amount that has been matched
    unmatched_stake: float  # Amount still unmatched
    wager_count: int  # Number of wagers on this line
    latest_recommended_stake: float  # Most recent recommended stake from strategy
    max_allowed_exposure: float  # 3x the latest recommended stake
    current_exposure_ratio: float  # current_total / max_allowed
    can_add_more: bool  # Whether we can place additional wagers
    max_additional_stake: float  # Maximum additional stake we can place

@dataclass
class ExposureCheckResult:
    """Result of checking exposure limits before placing a wager"""
    can_place: bool
    original_stake: float
    adjusted_stake: float
    reason: str
    line_exposure: LineExposure
    would_exceed: bool
    max_additional_allowed: float

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
    # ENHANCED: Exposure-adjusted stake amounts
    stake_to_place: Optional[float] = None
    exposure_adjusted: bool = False
    exposure_check_result: Optional[ExposureCheckResult] = None
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
    # ENHANCED: Exposure tracking
    exposure_before: Optional[LineExposure] = None
    exposure_after: Optional[LineExposure] = None

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
    """ENHANCED: Comprehensive exposure limit checking with 3x recommended stake limits"""
    
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
        self.max_exposure_multiplier = 3.0    # NEW: Max 3x recommended amount per line
        
        # API-based tracking
        self.current_wagers: List[ApiWager] = []
        self.last_wager_fetch_time: Optional[datetime] = None
        self.wager_fetch_duration: Optional[float] = None
        
        # Track previous wager states to detect fills
        self.previous_wager_states: Dict[str, WagerState] = {}  # external_id -> WagerState
        
        # Action tracking
        self.action_history: List[ActionResult] = []
        self.actions_this_cycle = 0
        
        # Fill detection and wait periods
        self.line_fill_times: Dict[str, datetime] = {}  # line_id -> last_fill_time
        
        # ENHANCED: Comprehensive exposure tracking
        self.line_exposures: Dict[str, LineExposure] = {}  # line_id -> LineExposure
        self.exposure_violations: List[Dict[str, Any]] = []  # Track when we hit limits
        
    def initialize_services(self, market_scanning_service, arbitrage_service, 
                          bet_placement_service, prophetx_service):
        """Initialize required services"""
        self.market_scanning_service = market_scanning_service
        self.arbitrage_service = arbitrage_service
        self.bet_placement_service = bet_placement_service
        self.prophetx_service = prophetx_service
        logger.info("🔧 Enhanced monitoring services initialized with exposure limits")
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """Start monitoring with enhanced exposure limit checking"""
        if self.monitoring_active:
            return {
                "success": False,
                "message": "Monitoring already active"
            }
        
        logger.info("🚀 Starting ENHANCED High Wager Monitoring Service with Exposure Limits")
        logger.info("=" * 80)
        
        # Step 1: Place initial bets with exposure checking
        logger.info("📍 Step 1: Placing initial bets with exposure limits...")
        initial_result = await self._place_initial_bets_with_exposure_limits()
        
        if not initial_result["success"]:
            return {
                "success": False,
                "message": f"Failed to place initial bets: {initial_result.get('error', 'Unknown error')}"
            }
        
        # Step 2: Wait for ProphetX to process bets
        logger.info("⏳ Step 2: Waiting for ProphetX to process initial bets...")
        await asyncio.sleep(10)
        
        # Step 3: Initialize wager state tracking and exposure calculation
        logger.info("📋 Step 3: Initializing exposure tracking and wager state...")
        await self._fetch_current_wagers_from_api()
        self._initialize_wager_state_tracking()
        await self._calculate_comprehensive_exposure_tracking()
        
        # Step 4: Start monitoring loop
        self.monitoring_active = True
        self.monitoring_cycles = 0
        asyncio.create_task(self._enhanced_monitoring_loop())
        
        return {
            "success": True,
            "message": "ENHANCED monitoring started with exposure limits", 
            "data": {
                "initial_bets": initial_result,
                "initial_wager_states_tracked": len(self.previous_wager_states),
                "initial_line_exposures": len(self.line_exposures),
                "enhancement_features": [
                    "✅ 3x exposure limits per line (matched + unmatched stakes)",
                    "✅ Automatic stake adjustment when hitting limits",
                    "✅ Comprehensive exposure checking before all placements",
                    "✅ Exposure-aware difference detection and action execution"
                ]
            }
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop the monitoring loop"""
        self.monitoring_active = False
        
        return {
            "success": True,
            "message": "ENHANCED monitoring stopped",
            "data": {
                "monitoring_cycles_completed": self.monitoring_cycles,
                "current_active_wagers": len([w for w in self.current_wagers if w.is_active]),
                "total_actions_executed": len(self.action_history),
                "lines_tracked": len(self.line_exposures),
                "exposure_violations": len(self.exposure_violations)
            }
        }
    
    # ============================================================================
    # ENHANCED EXPOSURE TRACKING AND CHECKING
    # ============================================================================
    
    async def _calculate_comprehensive_exposure_tracking(self):
        """
        CRITICAL FIX: Calculate TOTAL exposure per line including ALL matched + unmatched stakes
        
        This is the foundation of exposure checking - must be 100% accurate to prevent over-exposure
        """
        self.line_exposures.clear()
        
        # Group ALL system wagers by line_id (active, filled, partially filled)
        wagers_by_line = defaultdict(list)
        for wager in self.current_wagers:
            if wager.is_system_bet:  # Only count our system bets
                wagers_by_line[wager.line_id].append(wager)
        
        # Calculate comprehensive exposure for each line
        for line_id, wagers in wagers_by_line.items():
            # CRITICAL: Count TOTAL stakes (matched + unmatched) for true exposure
            total_stake = sum(w.stake for w in wagers)  # Original stake amounts placed
            matched_stake = sum(w.matched_stake for w in wagers)  # Amount that got filled
            unmatched_stake = sum(w.unmatched_stake for w in wagers)  # Amount still pending
            wager_count = len(wagers)
            
            # Sanity check: total_stake should equal matched_stake + unmatched_stake
            calculated_total = matched_stake + unmatched_stake
            if abs(total_stake - calculated_total) > 1.0:  # Allow $1 tolerance for rounding
                logger.warning(f"⚠️ Exposure calculation mismatch for {line_id[:8]}...: total_stake=${total_stake:.2f} vs calculated=${calculated_total:.2f}")
                # Use the calculated total as it's more reliable
                total_stake = calculated_total
            
            # We'll update the recommended stake when we get current opportunities
            # For now, use a reasonable default based on current exposure
            latest_recommended_stake = max(100.0, total_stake / 2.0)  # Default estimate
            max_allowed_exposure = latest_recommended_stake * self.max_exposure_multiplier
            
            current_exposure_ratio = total_stake / max_allowed_exposure if max_allowed_exposure > 0 else 0
            can_add_more = total_stake < max_allowed_exposure
            max_additional_stake = max(0, max_allowed_exposure - total_stake)
            
            line_exposure = LineExposure(
                line_id=line_id,
                total_stake=total_stake,  # This is the KEY number - total money committed to this line
                matched_stake=matched_stake,
                unmatched_stake=unmatched_stake,
                wager_count=wager_count,
                latest_recommended_stake=latest_recommended_stake,
                max_allowed_exposure=max_allowed_exposure,
                current_exposure_ratio=current_exposure_ratio,
                can_add_more=can_add_more,
                max_additional_stake=max_additional_stake
            )
            
            self.line_exposures[line_id] = line_exposure
        
        logger.info(f"📊 EXPOSURE TRACKING: Calculated exposure for {len(self.line_exposures)} lines")
        
        # Log lines that are at or near limits with detailed breakdown
        for line_id, exposure in self.line_exposures.items():
            if exposure.current_exposure_ratio >= 0.8:  # 80% or more of limit
                status = "🔴 AT LIMIT" if exposure.current_exposure_ratio >= 1.0 else "🟡 NEAR LIMIT"
                logger.info(f"   {status}: {line_id[:8]}... Total: ${exposure.total_stake:.0f} (matched: ${exposure.matched_stake:.0f}, unmatched: ${exposure.unmatched_stake:.0f}) | Limit: ${exposure.max_allowed_exposure:.0f} ({exposure.current_exposure_ratio:.1%})")

    
    def _update_line_exposure_with_current_strategy(self, line_id: str, recommended_stake: float):
        """Update line exposure with current strategy's recommended stake"""
        if line_id in self.line_exposures:
            exposure = self.line_exposures[line_id]
            
            # Update with current strategy
            exposure.latest_recommended_stake = recommended_stake
            exposure.max_allowed_exposure = recommended_stake * self.max_exposure_multiplier
            exposure.current_exposure_ratio = exposure.total_stake / exposure.max_allowed_exposure if exposure.max_allowed_exposure > 0 else 0
            exposure.can_add_more = exposure.total_stake < exposure.max_allowed_exposure
            exposure.max_additional_stake = max(0, exposure.max_allowed_exposure - exposure.total_stake)
        else:
            # Create new exposure tracking for this line
            self.line_exposures[line_id] = LineExposure(
                line_id=line_id,
                total_stake=0.0,
                matched_stake=0.0,
                unmatched_stake=0.0,
                wager_count=0,
                latest_recommended_stake=recommended_stake,
                max_allowed_exposure=recommended_stake * self.max_exposure_multiplier,
                current_exposure_ratio=0.0,
                can_add_more=True,
                max_additional_stake=recommended_stake * self.max_exposure_multiplier
            )
    
    def check_exposure_limits_before_placing(self, line_id: str, intended_stake: float, 
                                           recommended_stake: float) -> ExposureCheckResult:
        """
        CRITICAL FIX: Check exposure limits accounting for ALL existing stakes (matched + unmatched)
        
        This is the KEY method that prevents over-exposure. Must account for:
        1. ALL existing matched stakes on the line (filled portions)
        2. ALL existing unmatched stakes on the line (pending portions)  
        3. The new stake we're about to place
        
        The user's scenario:
        - Had $375 matched + $50 unmatched = $425 total exposure
        - Recommended = $150 (3x limit = $450)
        - When updating odds, should only place $25 more (to stay at $450 total)
        """
        
        # Update exposure tracking with current strategy
        self._update_line_exposure_with_current_strategy(line_id, recommended_stake)
        
        # Get current exposure for this line (INCLUDING MATCHED STAKES!)
        line_exposure = self.line_exposures.get(line_id, LineExposure(
            line_id=line_id,
            total_stake=0.0,
            matched_stake=0.0,
            unmatched_stake=0.0,
            wager_count=0,
            latest_recommended_stake=recommended_stake,
            max_allowed_exposure=recommended_stake * self.max_exposure_multiplier,
            current_exposure_ratio=0.0,
            can_add_more=True,
            max_additional_stake=recommended_stake * self.max_exposure_multiplier
        ))
        
        # CRITICAL: Current total exposure includes BOTH matched and unmatched stakes
        current_total_exposure = line_exposure.total_stake  # matched + unmatched
        max_allowed_total = line_exposure.max_allowed_exposure  # 3x recommended
        
        # Check if we can place the full intended stake
        total_after_placing = current_total_exposure + intended_stake
        would_exceed = total_after_placing > max_allowed_total
        
        # Calculate how much additional stake we can actually place
        max_additional_allowed = max(0, max_allowed_total - current_total_exposure)
        
        logger.debug(f"💰 EXPOSURE CHECK: {line_id[:8]}...")
        logger.debug(f"   Current exposure: ${current_total_exposure:.0f} (matched: ${line_exposure.matched_stake:.0f}, unmatched: ${line_exposure.unmatched_stake:.0f})")
        logger.debug(f"   Max allowed total: ${max_allowed_total:.0f} (3x ${recommended_stake:.0f})")
        logger.debug(f"   Intended stake: ${intended_stake:.0f}")
        logger.debug(f"   Would exceed: {would_exceed}")
        logger.debug(f"   Max additional allowed: ${max_additional_allowed:.0f}")
        
        if not would_exceed:
            # Can place full amount
            return ExposureCheckResult(
                can_place=True,
                original_stake=intended_stake,
                adjusted_stake=intended_stake,
                reason=f"Within limits: ${total_after_placing:.0f} <= ${max_allowed_total:.0f} (current: ${current_total_exposure:.0f})",
                line_exposure=line_exposure,
                would_exceed=False,
                max_additional_allowed=max_additional_allowed
            )
        
        elif max_additional_allowed > 5.0:  # Can place partial amount
            adjusted_stake = max_additional_allowed
            logger.info(f"💰 EXPOSURE ADJUSTMENT: {line_id[:8]}... ${intended_stake:.0f} → ${adjusted_stake:.0f}")
            logger.info(f"   Reason: Current total exposure ${current_total_exposure:.0f} + intended ${intended_stake:.0f} would exceed limit ${max_allowed_total:.0f}")
            
            return ExposureCheckResult(
                can_place=True,
                original_stake=intended_stake,
                adjusted_stake=adjusted_stake,
                reason=f"Adjusted to stay within limit: ${intended_stake:.0f} → ${adjusted_stake:.0f} (total exposure: ${current_total_exposure:.0f} + ${adjusted_stake:.0f} = ${current_total_exposure + adjusted_stake:.0f} <= ${max_allowed_total:.0f})",
                line_exposure=line_exposure,
                would_exceed=True,
                max_additional_allowed=max_additional_allowed
            )
        
        else:  # Already at or over limit
            logger.warning(f"💰 EXPOSURE LIMIT REACHED: {line_id[:8]}... cannot place any additional stake")
            logger.warning(f"   Current: ${current_total_exposure:.0f}, Limit: ${max_allowed_total:.0f}, Intended: ${intended_stake:.0f}")
            
            return ExposureCheckResult(
                can_place=False,
                original_stake=intended_stake,
                adjusted_stake=0.0,
                reason=f"Already at/over limit: ${current_total_exposure:.0f} >= ${max_allowed_total:.0f} (matched: ${line_exposure.matched_stake:.0f}, unmatched: ${line_exposure.unmatched_stake:.0f})",
                line_exposure=line_exposure,
                would_exceed=True,
                max_additional_allowed=0.0
            )
    
    # ============================================================================
    # ENHANCED MONITORING LOOP WITH EXPOSURE-AWARE LOGIC
    # ============================================================================
    
    async def _enhanced_monitoring_loop(self):
        """ENHANCED: Main monitoring loop with comprehensive exposure checking"""
        logger.info("🔄 Starting ENHANCED monitoring loop with exposure limits...")
        
        while self.monitoring_active:
            try:
                cycle_start = datetime.now(timezone.utc)
                self.monitoring_cycles += 1
                self.actions_this_cycle = 0
                
                logger.info(f"🔍 ENHANCED Monitoring cycle #{self.monitoring_cycles} starting...")
                
                # Step 1: Fetch current wagers from ProphetX API
                logger.info("📋 Fetching current wagers from ProphetX API...")
                await self._fetch_current_wagers_from_api()
                
                # Step 2: Update comprehensive exposure tracking
                await self._calculate_comprehensive_exposure_tracking()
                
                # Step 3: Detect fills by comparing with previous states
                fills_detected = self._detect_fills_from_state_changes()
                if fills_detected:
                    logger.info(f"🎯 FILL DETECTION: {len(fills_detected)} fills detected this cycle")
                    for fill in fills_detected:
                        logger.info(f"   💰 Fill: {fill['line_id'][:8]}... filled ${fill['amount_filled']:.2f}")
                
                # Step 4: Update previous states for next cycle
                self._update_wager_state_tracking()
                
                # Step 5: Get current market opportunities (ALWAYS current strategy)
                current_opportunities = await self._get_current_opportunities()
                
                # Step 6: Update exposure tracking with current strategy recommendations
                self._update_exposure_with_current_opportunities(current_opportunities)
                
                # Step 7: ENHANCED - Detect differences with exposure-aware logic
                differences = await self._exposure_aware_detect_differences(current_opportunities)
                
                # Step 8: Execute actions with exposure checking
                if differences:
                    logger.info(f"⚡ Executing {len(differences)} exposure-checked actions...")
                    await self._execute_all_actions_with_exposure_checks(differences)
                else:
                    logger.info("✅ No differences detected - all wagers up to date")
                
                # Step 9: Log exposure summary
                self._log_exposure_summary()
                
                # Step 10: Log cycle summary
                active_wagers = len([w for w in self.current_wagers if w.is_active and w.is_system_bet])
                filled_wagers = len([w for w in self.current_wagers if w.is_filled and w.is_system_bet])
                active_lines = len([e for e in self.line_exposures.values() if e.unmatched_stake > 0])
                
                logger.info(f"📊 Cycle #{self.monitoring_cycles} complete:")
                logger.info(f"   🎯 {active_wagers} active system wagers on {active_lines} unique lines")
                logger.info(f"   💰 {len(fills_detected)} fills detected this cycle")
                logger.info(f"   ⚡ {self.actions_this_cycle} actions executed")
                logger.info(f"   📏 {len([e for e in self.line_exposures.values() if e.current_exposure_ratio >= 0.8])} lines near/at exposure limits")
                
                # Update tracking
                self.last_scan_time = cycle_start
                
                # Wait for next cycle
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.monitoring_interval_seconds - cycle_duration)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in ENHANCED monitoring cycle: {e}", exc_info=True)
                await asyncio.sleep(self.monitoring_interval_seconds)
    
    def _update_exposure_with_current_opportunities(self, opportunities: List[CurrentOpportunity]):
        """Update exposure tracking with current strategy recommendations"""
        for opp in opportunities:
            self._update_line_exposure_with_current_strategy(opp.line_id, opp.recommended_stake)
    
    def _log_exposure_summary(self):
        """Log a summary of current exposure levels"""
        if not self.line_exposures:
            return
        
        total_lines = len(self.line_exposures)
        near_limit_lines = [e for e in self.line_exposures.values() if 0.8 <= e.current_exposure_ratio < 1.0]
        at_limit_lines = [e for e in self.line_exposures.values() if e.current_exposure_ratio >= 1.0]
        
        if near_limit_lines or at_limit_lines:
            logger.info(f"📏 EXPOSURE SUMMARY: {len(near_limit_lines)} near limit, {len(at_limit_lines)} at/over limit")
            
            for exposure in near_limit_lines[:3]:  # Show first 3
                logger.info(f"   🟡 {exposure.line_id[:8]}... ${exposure.total_stake:.0f}/${exposure.max_allowed_exposure:.0f} ({exposure.current_exposure_ratio:.1%})")
            
            for exposure in at_limit_lines[:3]:  # Show first 3
                logger.info(f"   🔴 {exposure.line_id[:8]}... ${exposure.total_stake:.0f}/${exposure.max_allowed_exposure:.0f} ({exposure.current_exposure_ratio:.1%})")
    
    # ============================================================================
    # ENHANCED DIFFERENCE DETECTION WITH EXPOSURE AWARENESS
    # ============================================================================
    
    async def _exposure_aware_detect_differences(self, current_opportunities: List[CurrentOpportunity]) -> List[WagerDifference]:
        """ENHANCED: Detect differences with comprehensive exposure limit checking"""
        differences = []
        now = datetime.now(timezone.utc)
        
        # Filter to active system wagers only
        active_system_wagers = [
            w for w in self.current_wagers 
            if w.is_system_bet and w.is_active and w.external_id and w.wager_id
        ]
        
        logger.info(f"🔍 EXPOSURE-AWARE: Comparing {len(active_system_wagers)} active system wagers vs {len(current_opportunities)} opportunities")
        
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
            
            # Check if line is in fill wait period
            is_in_wait_period = False
            wait_remaining = 0
            
            if line_id in self.line_fill_times:
                fill_time = self.line_fill_times[line_id]
                time_since_fill = (now - fill_time).total_seconds()
                
                if time_since_fill < self.fill_wait_period_seconds:
                    is_in_wait_period = True
                    wait_remaining = self.fill_wait_period_seconds - time_since_fill
                    logger.debug(f"⏰ WAIT PERIOD: Line {line_id[:8]}... has {wait_remaining:.0f}s remaining")
                else:
                    # Remove from wait period tracking
                    del self.line_fill_times[line_id]
            
            if opportunities and api_wagers:
                # Both exist - check for differences with exposure limits
                total_current_unmatched = sum(w.unmatched_stake for w in api_wagers)
                current_odds = api_wagers[0].odds
                
                # Find matching opportunity
                matching_opp = self._find_matching_opportunity_by_line(api_wagers[0], opportunities)
                
                if matching_opp:
                    # Check exposure before determining action
                    exposure_check = self.check_exposure_limits_before_placing(
                        line_id, matching_opp.recommended_stake, matching_opp.recommended_stake
                    )
                    
                    # ============================================================================
                    # CRITICAL FILL WAIT PERIOD LOGIC
                    # ============================================================================
                    if is_in_wait_period:
                        # 🕒 DURING 5-MINUTE WAIT PERIOD: ONLY ODDS CHANGES ALLOWED
                        # - NO stake changes
                        # - NO additional wagers  
                        # - NO refills
                        # - ONLY monitor for odds changes to keep competitive
                        logger.debug(f"⏰ WAIT PERIOD ACTIVE: {line_id[:8]}... ({wait_remaining:.0f}s remaining) - ONLY odds changes allowed")
                        
                        diff = self._check_odds_changes_only(line_id, api_wagers, matching_opp, total_current_unmatched)
                        if diff:
                            diff.exposure_check_result = exposure_check
                            differences.append(diff)
                            logger.info(f"🔄 ODDS UPDATE during wait period: {diff.reason}")
                        else:
                            logger.debug(f"⏰ No odds changes needed during wait period for {line_id[:8]}...")
                    
                    else:
                        # ✅ AFTER WAIT PERIOD: CONSOLIDATE TO CURRENT STRATEGY
                        # - Cancel ALL existing wagers on this line
                        # - Place ONE new wager with current strategy amount (not original)
                        # - Use current recommended_stake from fresh market scan
                        logger.debug(f"🔄 WAIT PERIOD EXPIRED: {line_id[:8]}... - consolidation/updates allowed")
                        
                        if len(api_wagers) > 1:
                            # Multiple wagers detected → ALWAYS consolidate after wait period
                            logger.info(f"🔄 CONSOLIDATION NEEDED: {len(api_wagers)} wagers on {line_id[:8]}... → consolidate to 1 wager with CURRENT strategy (${matching_opp.recommended_stake:.0f})")
                            
                            diff = self._create_exposure_aware_consolidation_action(
                                line_id, api_wagers, matching_opp, exposure_check
                            )
                            if diff:
                                differences.append(diff)
                        else:
                            # Single wager - check if it matches current strategy
                            diff = self._exposure_aware_compare_single_wager(
                                line_id, api_wagers[0], matching_opp, total_current_unmatched, exposure_check
                            )
                            if diff:
                                differences.append(diff)
                else:
                    # No matching opportunity - cancel all wagers on this line
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
                # New opportunities - check exposure before placing
                if not is_in_wait_period:
                    for opp in opportunities:
                        exposure_check = self.check_exposure_limits_before_placing(
                            line_id, opp.recommended_stake, opp.recommended_stake
                        )
                        
                        if exposure_check.can_place:
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
                                stake_to_place=exposure_check.adjusted_stake,
                                exposure_adjusted=exposure_check.adjusted_stake != exposure_check.original_stake,
                                exposure_check_result=exposure_check
                            ))
                        else:
                            logger.info(f"💰 EXPOSURE LIMIT: Skipping new opportunity on {line_id[:8]}... - {exposure_check.reason}")
                            
                            # Track this as an exposure violation
                            self.exposure_violations.append({
                                "timestamp": now.isoformat(),
                                "line_id": line_id,
                                "action": "skip_new_opportunity",
                                "reason": exposure_check.reason,
                                "intended_stake": opp.recommended_stake,
                                "current_exposure": exposure_check.line_exposure.total_stake,
                                "max_allowed": exposure_check.line_exposure.max_allowed_exposure
                            })
                else:
                    logger.debug(f"⏰ Skipping new opportunity placement during wait period: {line_id[:8]}...")
            
            elif api_wagers and not opportunities:
                # Cancel all API wagers on this line (regardless of wait period or exposure)
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
        
        logger.info(f"📊 EXPOSURE-AWARE: Detected {len(differences)} differences requiring action")
        return differences
    
    def _create_exposure_aware_consolidation_action(self, line_id: str, api_wagers: List[ApiWager], 
                                                   opportunity: CurrentOpportunity, 
                                                   exposure_check: ExposureCheckResult) -> Optional[WagerDifference]:
        """
        Create consolidation action with exposure limit awareness
        
        CRITICAL: Uses CURRENT strategy amount, not original wager amounts
        - Cancels ALL existing wagers on the line
        - Places ONE new wager with current recommended_stake from fresh market scan
        - This ensures we adapt to current market conditions, not stale original strategy
        """
        
        primary_wager = api_wagers[0]
        total_current_unmatched = sum(w.unmatched_stake for w in api_wagers)
        
        # Collect all wager IDs for cancellation
        all_external_ids = [w.external_id for w in api_wagers if w.external_id]
        all_prophetx_ids = [w.wager_id for w in api_wagers if w.wager_id]
        
        # Use exposure-checked stake
        if not exposure_check.can_place:
            logger.info(f"💰 EXPOSURE LIMIT: Cannot consolidate {line_id[:8]}... - {exposure_check.reason}")
            return None
        
        # CRITICAL: Use current strategy amount (opportunity.recommended_stake)
        # NOT the sum of existing wagers or original amounts
        current_strategy_amount = opportunity.recommended_stake
        target_stake = exposure_check.adjusted_stake  # May be limited by exposure
        exposure_adjusted = exposure_check.adjusted_stake != exposure_check.original_stake
        
        logger.info(f"🔄 CONSOLIDATION STRATEGY: {line_id[:8]}...")
        logger.info(f"   Current total unmatched: ${total_current_unmatched:.0f}")
        logger.info(f"   Current strategy target: ${current_strategy_amount:.0f}")  
        logger.info(f"   Exposure-adjusted target: ${target_stake:.0f}")
        logger.info(f"   Will cancel {len(api_wagers)} wagers → place 1 new wager")
        
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
            recommended_stake=current_strategy_amount,  # Current strategy, not original
            difference_type="consolidate_position",
            action_needed="consolidate_position",
            reason=f"POST-FILL CONSOLIDATION: {len(api_wagers)} wagers → 1 wager with CURRENT strategy (${current_strategy_amount:.0f})" + (f" exposure-adjusted to ${target_stake:.0f}" if exposure_adjusted else ""),
            stake_to_place=target_stake,
            exposure_adjusted=exposure_adjusted,
            exposure_check_result=exposure_check,
            all_wager_external_ids=all_external_ids,
            all_wager_prophetx_ids=all_prophetx_ids
        )
    
    def _exposure_aware_compare_single_wager(self, line_id: str, wager: ApiWager, 
                                           opportunity: CurrentOpportunity, total_current_unmatched: float,
                                           exposure_check: ExposureCheckResult) -> Optional[WagerDifference]:
        """Compare single wager vs opportunity with exposure awareness"""
        
        current_odds = wager.odds
        recommended_odds = opportunity.recommended_odds
        recommended_stake = opportunity.recommended_stake
        
        # Check for odds changes
        if current_odds != recommended_odds:
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
                stake_to_place=exposure_check.adjusted_stake,
                exposure_adjusted=exposure_check.adjusted_stake != exposure_check.original_stake,
                exposure_check_result=exposure_check,
                wager_external_id=wager.external_id,
                wager_prophetx_id=wager.wager_id
            )
        
        # Check stake differences based on current strategy with exposure limits
        stake_difference = recommended_stake - total_current_unmatched
        
        if stake_difference > 5.0 and exposure_check.can_place:  # Need to add more stake and can do so
            target_stake = exposure_check.adjusted_stake
            exposure_adjusted = exposure_check.adjusted_stake != exposure_check.original_stake
            
            logger.info(f"💰 REFILL NEEDED (exposure-aware): {wager.side}")
            logger.info(f"   Current unmatched: ${total_current_unmatched:.2f}")
            logger.info(f"   Strategy target: ${recommended_stake:.2f}")
            logger.info(f"   Exposure-adjusted target: ${target_stake:.2f}")
            
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
                reason=f"Refill with exposure limits: ${total_current_unmatched:.2f} → ${target_stake:.2f}" + (" (exposure-adjusted)" if exposure_adjusted else ""),
                stake_to_place=target_stake,
                exposure_adjusted=exposure_adjusted,
                exposure_check_result=exposure_check,
                all_wager_external_ids=[wager.external_id],
                all_wager_prophetx_ids=[wager.wager_id]
            )
        
        elif stake_difference > 5.0 and not exposure_check.can_place:
            # Would need to add stake but can't due to exposure limits
            logger.info(f"💰 EXPOSURE LIMIT: Cannot refill {line_id[:8]}... - {exposure_check.reason}")
            
            # Track this as an exposure violation
            self.exposure_violations.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "line_id": line_id,
                "action": "skip_refill",
                "reason": exposure_check.reason,
                "intended_additional_stake": stake_difference,
                "current_exposure": exposure_check.line_exposure.total_stake,
                "max_allowed": exposure_check.line_exposure.max_allowed_exposure
            })
        
        return None
    
    # Keep the existing methods that don't need exposure changes
    def _check_odds_changes_only(self, line_id: str, api_wagers: List[ApiWager], 
                                opportunity: CurrentOpportunity, total_current_unmatched: float) -> Optional[WagerDifference]:
        """
        During 5-minute wait period: ONLY check for odds changes, absolutely no stake differences
        
        CRITICAL FILL WAIT PERIOD RULES:
        - ✅ Allow odds updates to stay competitive
        - ❌ NO stake increases/decreases  
        - ❌ NO additional wagers
        - ❌ NO consolidation
        - ❌ NO refills
        
        This prevents over-betting immediately after fills while still allowing us to adjust
        to market odds changes to remain competitive.
        """
        
        primary_wager = api_wagers[0]
        current_odds = primary_wager.odds
        recommended_odds = opportunity.recommended_odds
        
        # ONLY check for odds changes during wait period - ignore all stake differences
        if current_odds != recommended_odds:
            logger.info(f"🔄 ODDS UPDATE NEEDED during wait period: {current_odds:+d} → {recommended_odds:+d}")
            logger.info(f"   Stake changes ignored during wait period: current ${total_current_unmatched:.0f}, strategy ${opportunity.recommended_stake:.0f}")
            
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
                reason=f"CRITICAL ODDS UPDATE (wait period): {current_odds:+d} → {recommended_odds:+d} | Stakes unchanged during 5min wait",
                wager_external_id=primary_wager.external_id,
                wager_prophetx_id=primary_wager.wager_id
            )
        
        # No odds changes needed during wait period
        logger.debug(f"⏰ No odds changes needed during wait period for {line_id[:8]}... (current: {current_odds:+d}, recommended: {recommended_odds:+d})")
        return None
    
    # ============================================================================
    # ENHANCED ACTION EXECUTION WITH EXPOSURE UPDATES
    # ============================================================================
    
    async def _execute_all_actions_with_exposure_checks(self, differences: List[WagerDifference]) -> List[ActionResult]:
        """Execute all actions with exposure tracking updates"""
        results = []
        
        for diff in differences:
            try:
                # Capture exposure before action
                exposure_before = self.line_exposures.get(diff.line_id)
                
                # Execute the action
                if diff.action_needed == "cancel_wager":
                    result = await self._execute_cancel_wager(diff)
                elif diff.action_needed == "place_new_wager":
                    result = await self._execute_place_new_wager_with_exposure(diff)
                elif diff.action_needed == "update_wager":
                    result = await self._execute_update_wager_with_exposure(diff)
                elif diff.action_needed == "consolidate_position":
                    result = await self._execute_consolidate_position_with_exposure(diff)
                else:
                    logger.warning(f"Unknown action: {diff.action_needed}")
                    continue
                
                # Update exposure tracking after action
                if result.success:
                    await self._update_exposure_after_action(diff.line_id)
                
                # Capture exposure after action
                exposure_after = self.line_exposures.get(diff.line_id)
                
                # Add exposure info to result
                result.exposure_before = exposure_before
                result.exposure_after = exposure_after
                
                results.append(result)
                self.action_history.append(result)
                self.actions_this_cycle += 1
                
                # Enhanced logging with exposure info
                status = "✅" if result.success else "❌"
                exposure_info = ""
                if exposure_after and exposure_before:
                    if exposure_after.total_stake != exposure_before.total_stake:
                        exposure_info = f" [Exposure: ${exposure_before.total_stake:.0f} → ${exposure_after.total_stake:.0f}]"
                
                logger.info(f"{status} {result.action_type.upper()}: {diff.line_id[:8]}... | {diff.reason}{exposure_info}")
                if not result.success:
                    logger.error(f"   Error: {result.error}")
                elif diff.exposure_adjusted:
                    logger.info(f"   💰 Exposure-adjusted: ${diff.exposure_check_result.original_stake:.0f} → ${diff.exposure_check_result.adjusted_stake:.0f}")
                
            except Exception as e:
                logger.error(f"Error executing action for {diff.line_id}: {e}")
                continue
        
        return results
    
    async def _update_exposure_after_action(self, line_id: str):
        """
        CRITICAL: Update exposure tracking after an action is executed
        
        Must recalculate from fresh API data to ensure accuracy after bet placements/cancellations
        """
        # Refresh wager data from API to get latest state
        await self._fetch_current_wagers_from_api()
        
        # Recalculate exposure for this specific line
        line_wagers = [w for w in self.current_wagers if w.line_id == line_id and w.is_system_bet]
        
        if line_wagers:
            total_stake = sum(w.stake for w in line_wagers)
            matched_stake = sum(w.matched_stake for w in line_wagers)
            unmatched_stake = sum(w.unmatched_stake for w in line_wagers)
            wager_count = len(line_wagers)
            
            logger.info(f"📊 EXPOSURE UPDATE: {line_id[:8]}...")
            logger.info(f"   Updated totals: ${total_stake:.0f} total (${matched_stake:.0f} matched + ${unmatched_stake:.0f} unmatched)")
            logger.info(f"   Wager count: {wager_count}")
            
            if line_id in self.line_exposures:
                exposure = self.line_exposures[line_id]
                
                # Update the exposure object
                old_total = exposure.total_stake
                exposure.total_stake = total_stake
                exposure.matched_stake = matched_stake
                exposure.unmatched_stake = unmatched_stake
                exposure.wager_count = wager_count
                exposure.current_exposure_ratio = total_stake / exposure.max_allowed_exposure if exposure.max_allowed_exposure > 0 else 0
                exposure.can_add_more = total_stake < exposure.max_allowed_exposure
                exposure.max_additional_stake = max(0, exposure.max_allowed_exposure - total_stake)
                
                logger.info(f"   Exposure change: ${old_total:.0f} → ${total_stake:.0f}")
                logger.info(f"   Limit: ${exposure.max_allowed_exposure:.0f} ({exposure.current_exposure_ratio:.1%})")
                logger.info(f"   Can add more: ${exposure.max_additional_stake:.0f}")
        else:
            # No wagers left on this line
            if line_id in self.line_exposures:
                logger.info(f"📊 EXPOSURE CLEARED: {line_id[:8]}... (no remaining wagers)")
                del self.line_exposures[line_id]
    
    # Enhanced action execution methods
    async def _execute_place_new_wager_with_exposure(self, diff: WagerDifference) -> ActionResult:
        """Place a new wager with exposure checking"""
        try:
            stake_to_place = diff.stake_to_place or diff.recommended_stake
            
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
                details={
                    **place_result,
                    "exposure_adjusted": diff.exposure_adjusted,
                    "original_stake": diff.exposure_check_result.original_stake if diff.exposure_check_result else stake_to_place,
                    "adjusted_stake": stake_to_place
                }
            )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="place",
                line_id=diff.line_id,
                error=f"Exception during placement: {str(e)}"
            )
    
    async def _execute_update_wager_with_exposure(self, diff: WagerDifference) -> ActionResult:
        """
        CRITICAL FIX: Update a wager with proper exposure checking
        
        When updating odds, we must be careful not to exceed exposure limits.
        The user's scenario: Had $375 matched + $50 unmatched, odds changed.
        Should cancel the $50 and only place back amount that keeps total ≤ $450.
        """
        try:
            logger.info(f"🔄 UPDATING WAGER with exposure awareness: {diff.line_id[:8]}...")
            logger.info(f"   Odds change: {diff.current_odds:+d} → {diff.recommended_odds:+d}")
            
            # CRITICAL: Before canceling, calculate what we can actually place back
            # Get current exposure BEFORE canceling the wager
            current_exposure = self.line_exposures.get(diff.line_id)
            if current_exposure:
                # After canceling this wager, our exposure will decrease
                wager_being_canceled_stake = diff.current_stake or 0
                exposure_after_cancel = current_exposure.total_stake - wager_being_canceled_stake
                
                # Now check how much we can place back
                max_allowed = current_exposure.max_allowed_exposure
                max_can_place_back = max(0, max_allowed - exposure_after_cancel)
                
                logger.info(f"   Current total exposure: ${current_exposure.total_stake:.0f}")
                logger.info(f"   Canceling wager: ${wager_being_canceled_stake:.0f}")
                logger.info(f"   Exposure after cancel: ${exposure_after_cancel:.0f}")
                logger.info(f"   Max can place back: ${max_can_place_back:.0f}")
                logger.info(f"   Strategy wants: ${diff.recommended_stake:.0f}")
                
                # Use the smaller of what strategy wants vs what exposure allows
                stake_to_place_back = min(diff.recommended_stake, max_can_place_back)
                
                if stake_to_place_back < 5.0:
                    logger.warning(f"💰 EXPOSURE LIMIT: Cannot update wager - would exceed limit after cancel/replace")
                    return ActionResult(
                        success=False,
                        action_type="update",
                        line_id=diff.line_id,
                        error=f"Cannot place replacement wager - exposure limit reached (can only place ${stake_to_place_back:.0f})"
                    )
                
                logger.info(f"   Will place back: ${stake_to_place_back:.0f} (exposure-limited)")
            else:
                # No existing exposure tracking - use recommended stake
                stake_to_place_back = diff.recommended_stake
                logger.info(f"   No exposure tracking found - using recommended: ${stake_to_place_back:.0f}")
            
            # Step 1: Cancel the existing wager
            logger.info(f"   🗑️ Canceling existing wager...")
            cancel_result = await self._execute_cancel_wager(diff)
            
            if not cancel_result.success:
                return ActionResult(
                    success=False,
                    action_type="update",
                    line_id=diff.line_id,
                    error=f"Cancel failed during update: {cancel_result.error}"
                )
            
            # Step 2: Small delay between cancel and place
            await asyncio.sleep(0.5)
            
            # Step 3: Update our exposure tracking after the cancel
            await self._update_exposure_after_action(diff.line_id)
            
            # Step 4: Place the new wager with exposure-limited amount
            logger.info(f"   📍 Placing replacement wager: ${stake_to_place_back:.0f} at {diff.recommended_odds:+d}")
            
            # Create a modified diff for placement with the exposure-limited stake
            placement_diff = diff
            placement_diff.stake_to_place = stake_to_place_back
            placement_diff.exposure_adjusted = stake_to_place_back != diff.recommended_stake
            
            place_result = await self._execute_place_new_wager_with_exposure(placement_diff)
            
            # Enhanced result with exposure info
            return ActionResult(
                success=place_result.success,
                action_type="update",
                line_id=diff.line_id,
                external_id=place_result.external_id if place_result.success else None,
                prophetx_wager_id=place_result.prophetx_wager_id if place_result.success else None,
                error=place_result.error if not place_result.success else None,
                details={
                    "cancelled_wager": cancel_result.details,
                    "new_wager": place_result.details if place_result.success else place_result.error,
                    "exposure_limited": stake_to_place_back != diff.recommended_stake,
                    "original_recommended_stake": diff.recommended_stake,
                    "actual_stake_placed": stake_to_place_back,
                    "exposure_reason": f"Limited by 3x exposure rule" if stake_to_place_back != diff.recommended_stake else "Within exposure limits"
                }
            )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="update",
                line_id=diff.line_id,
                error=f"Exception during exposure-aware update: {str(e)}"
            )
    
    async def _execute_consolidate_position_with_exposure(self, diff: WagerDifference) -> ActionResult:
        """
        Consolidate position with exposure checking
        
        CRITICAL POST-FILL CONSOLIDATION LOGIC:
        1. Cancel ALL existing wagers on the line (regardless of original amounts)
        2. Place ONE new wager with CURRENT strategy amount (from fresh market scan)
        3. This ensures we adapt to current market conditions after fills
        """
        try:
            current_strategy_amount = diff.recommended_stake
            target_stake = diff.stake_to_place
            
            logger.info(f"🔄 POST-FILL CONSOLIDATION: {diff.line_id[:8]}...")
            logger.info(f"   🎯 Strategy: Cancel ALL wagers → Place 1 wager with CURRENT strategy")
            logger.info(f"   💰 Current strategy amount: ${current_strategy_amount:.0f}")
            logger.info(f"   💰 Exposure-adjusted target: ${target_stake:.0f}")
            logger.info(f"   🗑️ Cancelling {len(diff.all_wager_external_ids or [])} existing wagers")
            
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
            
            # Step 3: Place ONE new consolidated wager with CURRENT STRATEGY amount
            timestamp_ms = int(time.time() * 1000)
            unique_suffix = uuid.uuid4().hex[:8]
            external_id = f"post_fill_consolidated_{timestamp_ms}_{unique_suffix}"
            
            logger.info(f"   📍 Placing NEW consolidated wager:")
            logger.info(f"      💰 Amount: ${target_stake:.0f} (CURRENT strategy, not original)")
            logger.info(f"      🎯 Odds: {diff.recommended_odds:+d}")
            if diff.exposure_adjusted:
                logger.info(f"      ⚠️ Exposure-adjusted from ${current_strategy_amount:.0f}")
            
            place_result = await self.prophetx_service.place_bet(
                line_id=diff.line_id,
                odds=diff.recommended_odds,
                stake=target_stake,
                external_id=external_id
            )
            
            if place_result["success"]:
                prophetx_wager_id = (
                    place_result.get("prophetx_bet_id") or 
                    place_result.get("bet_id") or 
                    "unknown"
                )
                
                logger.info(f"✅ POST-FILL CONSOLIDATION COMPLETE:")
                logger.info(f"   📊 {cancelled_count} old wagers → 1 new wager")
                logger.info(f"   💰 Amount: ${target_stake:.0f} (CURRENT strategy)")
                logger.info(f"   🎯 Odds: {diff.recommended_odds:+d}")
                logger.info(f"   🆔 New external_id: {external_id}")
                
                return ActionResult(
                    success=True,
                    action_type="consolidate",
                    line_id=diff.line_id,
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    details={
                        "consolidation_type": "post_fill_current_strategy",
                        "wagers_cancelled": cancelled_count,
                        "cancel_errors": cancel_errors,
                        "new_stake": target_stake,
                        "current_strategy_amount": current_strategy_amount,
                        "new_odds": diff.recommended_odds,
                        "exposure_adjusted": diff.exposure_adjusted,
                        "place_result": place_result
                    }
                )
            else:
                return ActionResult(
                    success=False,
                    action_type="consolidate",
                    line_id=diff.line_id,
                    error=f"Cancelled {cancelled_count} wagers but failed to place new consolidated wager: {place_result.get('error')}"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="consolidate",
                line_id=diff.line_id,
                error=f"Exception during post-fill consolidation: {str(e)}"
            )
    
    # ============================================================================
    # ENHANCED INITIAL BET PLACEMENT WITH EXPOSURE LIMITS
    # ============================================================================
    
    async def _place_initial_bets_with_exposure_limits(self) -> Dict[str, Any]:
        """Place initial bets with comprehensive exposure checking"""
        try:
            opportunities = await self.market_scanning_service.scan_for_opportunities()
            
            if not opportunities:
                return {
                    "success": True,
                    "message": "No initial opportunities found",
                    "summary": {"total_bets": 0, "successful_bets": 0, "exposure_adjusted": 0}
                }
            
            betting_decisions = self.arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
            
            # ENHANCED: Apply exposure checking to initial bets
            exposure_adjusted_decisions = []
            exposure_adjustments = 0
            exposure_skips = 0
            
            for decision in betting_decisions:
                if decision["action"] == "bet" and decision["type"] == "single_opportunity":
                    analysis = decision["analysis"]
                    opp = analysis.opportunity
                    
                    # Check exposure for this line
                    exposure_check = self.check_exposure_limits_before_placing(
                        opp.line_id, analysis.sizing.stake_amount, analysis.sizing.stake_amount
                    )
                    
                    if exposure_check.can_place:
                        if exposure_check.adjusted_stake != exposure_check.original_stake:
                            exposure_adjustments += 1
                            logger.info(f"💰 INITIAL BET EXPOSURE ADJUSTMENT: {opp.event_name[:30]}... ${exposure_check.original_stake:.0f} → ${exposure_check.adjusted_stake:.0f}")
                        
                        # Modify the decision to use adjusted stake
                        decision["exposure_adjusted"] = exposure_check.adjusted_stake != exposure_check.original_stake
                        decision["adjusted_stake"] = exposure_check.adjusted_stake
                        exposure_adjusted_decisions.append(decision)
                    else:
                        exposure_skips += 1
                        logger.info(f"💰 INITIAL BET EXPOSURE SKIP: {opp.event_name[:30]}... - {exposure_check.reason}")
                
                elif decision["action"] == "bet_both" and decision["type"] == "opposing_opportunities":
                    analysis = decision["analysis"]
                    opp1 = analysis.opportunity_1
                    opp2 = analysis.opportunity_2
                    
                    # Check exposure for both sides
                    exposure_check_1 = self.check_exposure_limits_before_placing(
                        opp1.line_id, analysis.bet_1_sizing.stake_amount, analysis.bet_1_sizing.stake_amount
                    )
                    exposure_check_2 = self.check_exposure_limits_before_placing(
                        opp2.line_id, analysis.bet_2_sizing.stake_amount, analysis.bet_2_sizing.stake_amount
                    )
                    
                    if exposure_check_1.can_place and exposure_check_2.can_place:
                        adjustments_made = (
                            exposure_check_1.adjusted_stake != exposure_check_1.original_stake or
                            exposure_check_2.adjusted_stake != exposure_check_2.original_stake
                        )
                        
                        if adjustments_made:
                            exposure_adjustments += 1
                            logger.info(f"💰 INITIAL ARBITRAGE EXPOSURE ADJUSTMENT: {opp1.event_name[:30]}...")
                        
                        decision["exposure_adjusted"] = adjustments_made
                        decision["adjusted_stake_1"] = exposure_check_1.adjusted_stake
                        decision["adjusted_stake_2"] = exposure_check_2.adjusted_stake
                        exposure_adjusted_decisions.append(decision)
                    else:
                        exposure_skips += 1
                        logger.info(f"💰 INITIAL ARBITRAGE EXPOSURE SKIP: {opp1.event_name[:30]}... - exposure limits")
                else:
                    # Keep non-betting decisions as-is
                    exposure_adjusted_decisions.append(decision)
            
            # Place the exposure-adjusted decisions
            result = await self.bet_placement_service.place_all_opportunities_batch(exposure_adjusted_decisions)
            
            # Enhance the result with exposure info
            if "data" in result and "summary" in result["data"]:
                result["data"]["summary"]["exposure_adjusted"] = exposure_adjustments
                result["data"]["summary"]["exposure_skipped"] = exposure_skips
                result["data"]["summary"]["total_decisions_original"] = len(betting_decisions)
                result["data"]["summary"]["total_decisions_after_exposure"] = len(exposure_adjusted_decisions)
            
            return {
                "success": result["success"],
                "message": f"Initial bets placed with exposure limits (adjusted: {exposure_adjustments}, skipped: {exposure_skips})",
                "summary": result.get("data", {}).get("summary", {})
            }
            
        except Exception as e:
            logger.error(f"Error placing initial bets with exposure limits: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error placing initial bets: {str(e)}",
                "summary": {"total_bets": 0, "successful_bets": 0, "exposure_adjusted": 0}
            }
    
    # ============================================================================
    # KEEP ALL EXISTING HELPER METHODS (mostly unchanged)
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
    
    # Keep existing API fetching and conversion methods (unchanged)
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
            
            logger.info(f"📋 Fetched {len(all_wagers)} total wagers from {page_count} pages")
            logger.info(f"   🤖 {len(system_wagers)} system wagers (with external_id)")
            logger.info(f"   ✅ {len(active_wagers)} active system wagers")
            
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
    
    # Keep existing methods for opportunities and action execution
    async def _get_current_opportunities(self) -> List[CurrentOpportunity]:
        """Get current opportunities from scan-opportunities endpoint"""
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
    
    # Keep simple action execution methods
    async def _execute_cancel_wager(self, diff: WagerDifference) -> ActionResult:
        """Cancel a specific wager"""
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
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get enhanced monitoring status with exposure info"""
        active_wagers = [w for w in self.current_wagers if w.is_active]
        filled_wagers = [w for w in self.current_wagers if w.is_filled]
        
        # Count unique lines
        active_lines = len(set(w.line_id for w in self.current_wagers if w.is_active and w.is_system_bet))
        
        # Exposure summary
        exposure_summary = {
            "total_lines_tracked": len(self.line_exposures),
            "lines_near_limit": len([e for e in self.line_exposures.values() if 0.8 <= e.current_exposure_ratio < 1.0]),
            "lines_at_limit": len([e for e in self.line_exposures.values() if e.current_exposure_ratio >= 1.0]),
            "total_exposure_violations": len(self.exposure_violations),
            "max_exposure_multiplier": self.max_exposure_multiplier
        }
        
        return {
            "monitoring_active": self.monitoring_active,
            "monitoring_cycles": self.monitoring_cycles,
            "version": "ENHANCED with 3x Exposure Limits",
            "current_wagers": {
                "total_fetched": len(self.current_wagers),
                "active_wagers": len(active_wagers),
                "active_unique_lines": active_lines,
                "filled_wagers": len(filled_wagers),
                "system_wagers": len([w for w in self.current_wagers if w.is_system_bet])
            },
            "exposure_tracking": exposure_summary,
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
                        "error": action.error,
                        "exposure_changed": bool(action.exposure_before != action.exposure_after)
                    }
                    for action in self.action_history[-5:]
                ]
            },
            "settings": {
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "fill_wait_period_seconds": self.fill_wait_period_seconds,
                "max_exposure_multiplier": self.max_exposure_multiplier
            },
            "enhanced_features": [
                "✅ 3x exposure limits per line (matched + unmatched stakes)",
                "✅ Automatic stake adjustment when hitting limits",
                "✅ Comprehensive exposure checking before all placements",
                "✅ Exposure-aware difference detection and action execution",
                "✅ Enhanced logging with exposure change tracking"
            ]
        }
    
    async def get_current_wagers(self) -> Dict[str, Any]:
        """Get current wagers from API with exposure info"""
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
                ],
                "exposure_summary": {
                    "lines_tracked": len(self.line_exposures),
                    "exposure_violations": len(self.exposure_violations),
                    "lines_at_or_near_limit": len([e for e in self.line_exposures.values() if e.current_exposure_ratio >= 0.8])
                }
            }
        }


    async def debug_exposure_for_line(self, line_id: str) -> Dict[str, Any]:
        """
        DEBUG METHOD: Get detailed exposure breakdown for a specific line
        
        Use this to troubleshoot exposure limit issues
        """
        # Refresh wager data
        await self._fetch_current_wagers_from_api()
        
        # Find all wagers for this line
        line_wagers = [w for w in self.current_wagers if w.line_id == line_id and w.is_system_bet]
        
        if not line_wagers:
            return {
                "line_id": line_id,
                "error": "No system wagers found for this line",
                "total_wagers": len([w for w in self.current_wagers if w.line_id == line_id])
            }
        
        # Calculate totals
        total_stake = sum(w.stake for w in line_wagers)
        matched_stake = sum(w.matched_stake for w in line_wagers)
        unmatched_stake = sum(w.unmatched_stake for w in line_wagers)
        
        # Get exposure tracking
        exposure = self.line_exposures.get(line_id)
        
        # Detailed wager breakdown
        wager_details = []
        for i, wager in enumerate(line_wagers):
            wager_details.append({
                "wager_index": i + 1,
                "external_id": wager.external_id[:12] + "..." if wager.external_id else None,
                "side": wager.side,
                "odds": wager.odds,
                "stake": wager.stake,
                "matched_stake": wager.matched_stake,
                "unmatched_stake": wager.unmatched_stake,
                "status": wager.status,
                "matching_status": wager.matching_status,
                "is_active": wager.is_active,
                "fill_percentage": (wager.matched_stake / wager.stake * 100) if wager.stake > 0 else 0
            })
        
        return {
            "line_id": line_id,
            "debug_timestamp": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "wager_count": len(line_wagers),
                "total_stake": total_stake,
                "matched_stake": matched_stake,
                "unmatched_stake": unmatched_stake,
                "calculated_total": matched_stake + unmatched_stake
            },
            "exposure_tracking": {
                "has_tracking": exposure is not None,
                "latest_recommended_stake": exposure.latest_recommended_stake if exposure else None,
                "max_allowed_exposure": exposure.max_allowed_exposure if exposure else None,
                "current_exposure_ratio": exposure.current_exposure_ratio if exposure else None,
                "can_add_more": exposure.can_add_more if exposure else None,
                "max_additional_stake": exposure.max_additional_stake if exposure else None
            } if exposure else {"error": "No exposure tracking found"},
            "wager_details": wager_details,
            "analysis": {
                "total_exposure_check": f"${total_stake:.2f} total exposure",
                "limit_check": f"Limit: ${exposure.max_allowed_exposure:.2f} (3x ${exposure.latest_recommended_stake:.2f})" if exposure else "No limit tracking",
                "status": ("🔴 OVER LIMIT" if exposure and exposure.current_exposure_ratio > 1.0 else
                          "🟡 NEAR LIMIT" if exposure and exposure.current_exposure_ratio >= 0.8 else
                          "✅ WITHIN LIMITS" if exposure else "❓ NO TRACKING"),
                "can_place_more": f"Can place up to ${exposure.max_additional_stake:.2f} more" if exposure and exposure.can_add_more else "Cannot place more"
            }
        }


# Global service instance
high_wager_monitoring_service = HighWagerMonitoringService()