#!/usr/bin/env python3
"""
High Wager Monitoring Service - WITH ACTION EXECUTION

Monitors high wager opportunities and executes actions to keep wagers up to date.

Core Actions:
1. Cancel wagers when opportunities disappear
2. Place new wagers when opportunities appear
3. Update wagers (cancel + place) when odds/stakes change
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)

@dataclass
class TrackedWager:
    """Represents a wager we've placed and are tracking"""
    external_id: str
    prophetx_wager_id: str
    line_id: str
    event_id: str
    market_id: str
    market_type: str
    side: str
    odds: int
    stake: float
    status: str  # "pending", "matched", "cancelled"
    placed_at: datetime
    last_updated: datetime
    # Opportunity context
    large_bet_combined_size: float
    opportunity_type: str  # "single" or "arbitrage_1" or "arbitrage_2"
    arbitrage_pair_id: Optional[str] = None

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
    # Current wager info
    current_odds: Optional[int]
    current_stake: Optional[float]
    current_status: Optional[str]
    # Recommended info
    recommended_odds: int
    recommended_stake: float
    # Analysis
    difference_type: str  # "odds_change", "stake_change", "new_opportunity", "remove_opportunity"
    action_needed: str  # "update_wager", "cancel_wager", "place_new_wager", "no_action"
    reason: str
    # ADDED: Specific wager identifiers for actions
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
    """Monitors high wager opportunities and executes actions to keep wagers up to date"""
    
    def __init__(self):
        self.monitoring_active = False
        self.tracked_wagers: Dict[str, TrackedWager] = {}  # external_id -> TrackedWager
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
        
        # Fill tracking
        self.recent_fills: Dict[str, datetime] = {}  # line_id -> fill_time
        self.line_exposure: Dict[str, float] = defaultdict(float)  # line_id -> total_stake
        
        # Action tracking
        self.action_history: List[ActionResult] = []
        self.actions_this_cycle = 0
        
    def initialize_services(self, market_scanning_service, arbitrage_service, 
                          bet_placement_service, prophetx_service):
        """Initialize required services"""
        self.market_scanning_service = market_scanning_service
        self.arbitrage_service = arbitrage_service
        self.bet_placement_service = bet_placement_service
        self.prophetx_service = prophetx_service
        logger.info("🔧 High wager monitoring services initialized")
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """Start the complete monitoring workflow with action execution"""
        if self.monitoring_active:
            return {
                "success": False,
                "message": "Monitoring already active"
            }
        
        logger.info("🚀 Starting High Wager Monitoring Service with Action Execution")
        logger.info("=" * 70)
        
        # Step 1: Place initial bets
        logger.info("📍 Step 1: Placing initial bets...")
        initial_result = await self._place_initial_bets()
        
        if not initial_result["success"]:
            return {
                "success": False,
                "message": f"Failed to place initial bets: {initial_result.get('error', 'Unknown error')}"
            }
        
        # Step 2: Start monitoring loop with actions
        self.monitoring_active = True
        asyncio.create_task(self._monitoring_loop_with_actions())
        
        return {
            "success": True,
            "message": "High wager monitoring with actions started", 
            "data": {
                "initial_bets": initial_result,
                "action_execution_enabled": True,
                "monitoring_interval": f"{self.monitoring_interval_seconds} seconds"
            }
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop the monitoring loop"""
        self.monitoring_active = False
        
        return {
            "success": True,
            "message": "High wager monitoring stopped",
            "data": {
                "monitoring_cycles_completed": self.monitoring_cycles,
                "tracked_wagers": len(self.tracked_wagers),
                "total_actions_executed": len(self.action_history)
            }
        }
    
    # ============================================================================
    # MONITORING LOOP WITH ACTION EXECUTION
    # ============================================================================
    
    async def _monitoring_loop_with_actions(self):
        """Main monitoring loop with action execution"""
        logger.info("🔄 Starting monitoring loop with action execution...")
        
        while self.monitoring_active:
            try:
                cycle_start = datetime.now(timezone.utc)
                self.monitoring_cycles += 1
                self.actions_this_cycle = 0
                
                logger.info(f"🔍 Monitoring cycle #{self.monitoring_cycles} starting...")
                
                # Step 1: Get current opportunities
                current_opportunities = await self._get_current_opportunities()
                
                # Step 2: Compare with tracked wagers
                differences = await self._detect_wager_differences(current_opportunities)
                
                # Step 3: EXECUTE ACTIONS based on differences
                if differences:
                    logger.info(f"⚡ Executing {len(differences)} actions...")
                    await self._execute_all_actions(differences)
                else:
                    logger.info("✅ No differences detected - all wagers up to date")
                
                # Step 4: Update tracking info
                self.last_scan_time = cycle_start
                
                # Step 5: Log cycle summary
                logger.info(f"📊 Cycle #{self.monitoring_cycles} complete: {self.actions_this_cycle} actions executed")
                
                # Wait for next cycle
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.monitoring_interval_seconds - cycle_duration)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
                await asyncio.sleep(self.monitoring_interval_seconds)
    
    # ============================================================================
    # ACTION EXECUTION METHODS
    # ============================================================================
    
    async def _execute_all_actions(self, differences: List[WagerDifference]) -> List[ActionResult]:
        """Execute all required actions based on detected differences"""
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
                
                # Log action result
                status = "✅" if result.success else "❌"
                logger.info(f"{status} {result.action_type.upper()}: {diff.line_id[:8]}... | {diff.reason}")
                if not result.success:
                    logger.error(f"   Error: {result.error}")
                
            except Exception as e:
                logger.error(f"Error executing action for {diff.line_id}: {e}")
                continue
        
        return results
    
    async def _execute_cancel_wager(self, diff: WagerDifference) -> ActionResult:
        """Cancel a specific wager using its identifiers"""
        try:
            # FIXED: Use specific wager identifiers from the difference
            if diff.wager_external_id and diff.wager_prophetx_id:
                external_id = diff.wager_external_id
                prophetx_wager_id = diff.wager_prophetx_id
            else:
                # Fallback: Find the tracked wager by line_id (but this is less reliable)
                tracked_wager = None
                for wager in self.tracked_wagers.values():
                    if (wager.line_id == diff.line_id and 
                        wager.side == diff.side and 
                        wager.status in ["pending", "unmatched", "active"]):
                        tracked_wager = wager
                        break
                
                if not tracked_wager:
                    return ActionResult(
                        success=False,
                        action_type="cancel",
                        line_id=diff.line_id,
                        error="No active tracked wager found for this line/side"
                    )
                
                external_id = tracked_wager.external_id
                prophetx_wager_id = tracked_wager.prophetx_wager_id
            
            # Call ProphetX cancellation API
            cancel_result = await self.prophetx_service.cancel_wager(
                external_id=external_id,
                wager_id=prophetx_wager_id
            )
            
            if cancel_result["success"]:
                # FIXED: Update tracked wager status and remove from line exposure
                if external_id in self.tracked_wagers:
                    tracked_wager = self.tracked_wagers[external_id]
                    tracked_wager.status = "cancelled"
                    tracked_wager.last_updated = datetime.now(timezone.utc)
                    
                    # Update line exposure
                    self.line_exposure[diff.line_id] -= tracked_wager.stake
                    
                    # OPTIONALLY: Remove from tracked_wagers entirely
                    # del self.tracked_wagers[external_id]
                
                return ActionResult(
                    success=True,
                    action_type="cancel",
                    line_id=diff.line_id,
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    details=cancel_result
                )
            else:
                return ActionResult(
                    success=False,
                    action_type="cancel",
                    line_id=diff.line_id,
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    error=cancel_result.get("error", "Cancellation failed")
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="cancel",
                line_id=diff.line_id,
                error=f"Exception during cancellation: {str(e)}"
            )
    
    async def _execute_place_new_wager(self, diff: WagerDifference) -> ActionResult:
        """Place a new wager for a new opportunity"""
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
            
            # Generate external ID for new wager with more entropy
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            unique_suffix = str(uuid.uuid4()).replace('-', '')[:8]
            external_id = f"monitor_{diff.event_id}_{diff.line_id[:8]}_{timestamp}_{unique_suffix}"
            
            # Place the wager
            place_result = await self.prophetx_service.place_bet(
                line_id=diff.line_id,
                odds=diff.recommended_odds,
                stake=diff.recommended_stake,
                external_id=external_id
            )
            
            if place_result["success"]:
                # FIXED: Extract ProphetX wager ID more reliably
                prophetx_wager_id = (
                    place_result.get("prophetx_bet_id") or 
                    place_result.get("bet_id") or 
                    place_result.get("data", {}).get("wager", {}).get("id") or
                    "unknown"
                )
                
                # FIXED: Create new tracked wager with proper data
                tracked_wager = TrackedWager(
                    external_id=external_id,
                    prophetx_wager_id=prophetx_wager_id,
                    line_id=diff.line_id,
                    event_id=diff.event_id,
                    market_id=diff.market_id,
                    market_type=diff.market_type,
                    side=diff.side,
                    odds=diff.recommended_odds,
                    stake=diff.recommended_stake,
                    status="pending",  # or "unmatched" based on ProphetX response
                    placed_at=datetime.now(timezone.utc),
                    last_updated=datetime.now(timezone.utc),
                    large_bet_combined_size=0,  # Will be updated from opportunity data if available
                    opportunity_type="single"  # Default for monitoring-placed bets
                )
                
                # FIXED: Add to tracking immediately
                self.tracked_wagers[external_id] = tracked_wager
                
                # Update line exposure
                self.line_exposure[diff.line_id] += diff.recommended_stake
                
                logger.info(f"✅ New wager tracked: {external_id} -> {prophetx_wager_id}")
                
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
            logger.info(f"🔄 Updating wager: {diff.line_id[:8]}... | {diff.reason}")
            
            # Step 1: Cancel the existing wager using specific identifiers
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
                logger.error(f"❌ UPDATE PARTIAL FAILURE: Cancelled wager but failed to place new one for {diff.line_id}")
                return ActionResult(
                    success=False,
                    action_type="update",
                    line_id=diff.line_id,
                    error=f"Place failed after cancel: {place_result.error}. Position lost!",
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
    # EXISTING METHODS (from previous version)
    # ============================================================================
    
    async def _place_initial_bets(self) -> Dict[str, Any]:
        """Place initial bets by replicating place-all-opportunities endpoint"""
        try:
            # Use the existing endpoint logic
            opportunities = await self.market_scanning_service.scan_for_opportunities()
            
            if not opportunities:
                return {
                    "success": True,
                    "message": "No initial opportunities found",
                    "summary": {"total_bets": 0, "successful_bets": 0}
                }
            
            # Get betting decisions
            betting_decisions = self.arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
            
            # Place bets using batch API
            result = await self.bet_placement_service.place_all_opportunities_batch(betting_decisions)
            
            # Track placed wagers
            if result["success"] and "data" in result and "results" in result["data"]:
                await self._update_tracked_wagers_from_placement_result(result, opportunities)
            
            return {
                "success": result["success"],
                "message": "Initial bets placed",
                "summary": result.get("data", {}).get("summary", {}),
                "tracked_wagers": len(self.tracked_wagers)
            }
            
        except Exception as e:
            logger.error(f"Error placing initial bets: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error placing initial bets: {str(e)}",
                "summary": {"total_bets": 0, "successful_bets": 0},
                "tracked_wagers": 0
            }
    
    async def _get_current_opportunities(self) -> List[CurrentOpportunity]:
        """Get current opportunities from scan-opportunities endpoint"""
        try:
            # Get raw opportunities using direct service import
            opportunities = await self.market_scanning_service.scan_for_opportunities()
            
            if not opportunities:
                return []
            
            # Get betting decisions using direct service import
            betting_decisions = self.arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
            
            # Convert to CurrentOpportunity objects
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
    
    async def _detect_wager_differences(self, current_opportunities: List[CurrentOpportunity]) -> List[WagerDifference]:
        """Compare current wagers with new opportunities to detect differences"""
        differences = []
        
        # FIXED: Create lookup maps using line_id but handle multiple wagers per line
        current_opps_by_line = {}
        for opp in current_opportunities:
            if opp.line_id not in current_opps_by_line:
                current_opps_by_line[opp.line_id] = []
            current_opps_by_line[opp.line_id].append(opp)
        
        # FIXED: Group active tracked wagers by line_id, but keep all wagers
        active_wagers_by_line = {}
        for external_id, wager in self.tracked_wagers.items():
            # Only consider wagers that are actually active
            if wager.status in ["pending", "unmatched", "active"]:  # NOT cancelled
                if wager.line_id not in active_wagers_by_line:
                    active_wagers_by_line[wager.line_id] = []
                active_wagers_by_line[wager.line_id].append(wager)
        
        # Get all unique line_ids
        all_line_ids = set(current_opps_by_line.keys()) | set(active_wagers_by_line.keys())
        
        for line_id in all_line_ids:
            current_opps = current_opps_by_line.get(line_id, [])
            active_wagers = active_wagers_by_line.get(line_id, [])
            
            if current_opps and active_wagers:
                # Both exist - check each active wager against recommendations
                for wager in active_wagers:
                    # Find matching opportunity for this wager's side
                    matching_opp = None
                    for opp in current_opps:
                        if self._wager_matches_opportunity(wager, opp):
                            matching_opp = opp
                            break
                    
                    if matching_opp:
                        # Check if wager needs updating
                        diff = self._compare_wager_vs_opportunity(wager, matching_opp)
                        if diff:
                            differences.append(diff)
                    else:
                        # No matching opportunity - cancel this wager
                        differences.append(WagerDifference(
                            line_id=line_id,
                            event_id=wager.event_id,
                            market_id=wager.market_id,
                            market_type=wager.market_type,
                            side=wager.side,
                            current_odds=wager.odds,
                            current_stake=wager.stake,
                            current_status=wager.status,
                            recommended_odds=0,
                            recommended_stake=0,
                            difference_type="remove_opportunity",
                            action_needed="cancel_wager",
                            reason="Opportunity no longer recommended",
                            wager_external_id=wager.external_id,  # ADDED
                            wager_prophetx_id=wager.prophetx_wager_id  # ADDED
                        ))
            
            elif current_opps and not active_wagers:
                # New opportunities - place new wagers
                for opp in current_opps:
                    differences.append(WagerDifference(
                        line_id=line_id,
                        event_id=opp.event_id,
                        market_id=opp.market_id,
                        market_type=opp.market_type,
                        side=opp.side,
                        current_odds=None,
                        current_stake=None,
                        current_status=None,
                        recommended_odds=opp.recommended_odds,
                        recommended_stake=opp.recommended_stake,
                        difference_type="new_opportunity",
                        action_needed="place_new_wager",
                        reason=f"New opportunity detected for {opp.market_type}"
                    ))
            
            elif active_wagers and not current_opps:
                # Cancel all active wagers on this line
                for wager in active_wagers:
                    differences.append(WagerDifference(
                        line_id=line_id,
                        event_id=wager.event_id,
                        market_id=wager.market_id,
                        market_type=wager.market_type,
                        side=wager.side,
                        current_odds=wager.odds,
                        current_stake=wager.stake,
                        current_status=wager.status,
                        recommended_odds=0,
                        recommended_stake=0,
                        difference_type="remove_opportunity",
                        action_needed="cancel_wager",
                        reason="Opportunity no longer recommended",
                        wager_external_id=wager.external_id,  # ADDED
                        wager_prophetx_id=wager.prophetx_wager_id  # ADDED
                    ))
        
        return differences
    
    def _wager_matches_opportunity(self, wager: TrackedWager, opportunity: CurrentOpportunity) -> bool:
        """Check if a wager matches an opportunity (same side)"""
        return (
            wager.line_id == opportunity.line_id and
            wager.side == opportunity.side and
            wager.market_type == opportunity.market_type
        )
    
    def _compare_wager_vs_opportunity(self, wager: TrackedWager, opportunity: CurrentOpportunity) -> Optional[WagerDifference]:
        """Compare a tracked wager with current opportunity to detect changes"""
        
        # Check for odds changes
        if wager.odds != opportunity.recommended_odds:
            return WagerDifference(
                line_id=wager.line_id,
                event_id=wager.event_id,
                market_id=wager.market_id,
                market_type=wager.market_type,
                side=wager.side,
                current_odds=wager.odds,
                current_stake=wager.stake,
                current_status=wager.status,
                recommended_odds=opportunity.recommended_odds,
                recommended_stake=opportunity.recommended_stake,
                difference_type="odds_change",
                action_needed="update_wager",
                reason=f"Odds changed from {wager.odds:+d} to {opportunity.recommended_odds:+d}"
            )
        
        # Check for stake changes (significant changes only)
        stake_diff = abs(wager.stake - opportunity.recommended_stake)
        if stake_diff > 10.0:  # Only care about changes > $10
            return WagerDifference(
                line_id=wager.line_id,
                event_id=wager.event_id,
                market_id=wager.market_id,
                market_type=wager.market_type,
                side=wager.side,
                current_odds=wager.odds,
                current_stake=wager.stake,
                current_status=wager.status,
                recommended_odds=opportunity.recommended_odds,
                recommended_stake=opportunity.recommended_stake,
                difference_type="stake_change",
                action_needed="update_wager",
                reason=f"Stake changed from ${wager.stake:.2f} to ${opportunity.recommended_stake:.2f}"
            )
        
        return None
    
    # ============================================================================
    # TRACKING AND UTILITY METHODS
    # ============================================================================
    
    async def _update_tracked_wagers_from_placement_result(self, placement_result: Dict[str, Any], original_opportunities: List = None):
        """Update tracked wagers from bet placement result"""
        try:
            # Navigate to results via 'data' key
            data = placement_result.get("data", {})
            batch_api_result = data.get("batch_api_result", {})
            success_wagers = batch_api_result.get("success_wagers", {})
            
            # Create opportunity lookup for enhanced context
            opportunity_lookup = {}
            if original_opportunities:
                for opp in original_opportunities:
                    opportunity_lookup[opp.line_id] = opp
            
            current_time = datetime.now(timezone.utc)
            
            # Track ALL successful wagers from batch_api_result
            for external_id, wager_details in success_wagers.items():
                try:
                    line_id = wager_details.get("line_id", "unknown")
                    opportunity = opportunity_lookup.get(line_id)
                    
                    # Extract ProphetX wager ID from wager details
                    prophetx_wager_id = (
                        wager_details.get("prophetx_bet_id") or 
                        wager_details.get("bet_id") or 
                        wager_details.get("id") or 
                        "unknown"
                    )
                    
                    # Create tracked wager
                    tracked_wager = TrackedWager(
                        external_id=external_id,
                        prophetx_wager_id=prophetx_wager_id,
                        line_id=line_id,
                        event_id=opportunity.event_id if opportunity else "unknown",
                        market_id=opportunity.market_id if opportunity else "unknown",
                        market_type=opportunity.market_type if opportunity else "unknown",
                        side=opportunity.large_bet_side if opportunity else "unknown",
                        odds=wager_details.get("odds", 0),
                        stake=wager_details.get("stake", 0),
                        status="pending",
                        placed_at=current_time,
                        last_updated=current_time,
                        large_bet_combined_size=opportunity.large_bet_combined_size if opportunity else 0,
                        opportunity_type="single",  # Simplify for now
                        arbitrage_pair_id=None
                    )
                    
                    self.tracked_wagers[external_id] = tracked_wager
                    
                    # Update line exposure
                    self.line_exposure[line_id] += tracked_wager.stake
                    
                except Exception as e:
                    logger.error(f"Error tracking wager {external_id}: {e}")
                    continue
            
            logger.info(f"📊 Tracking update complete: {len(self.tracked_wagers)} total tracked wagers")
            
        except Exception as e:
            logger.error(f"Error in tracking update: {e}", exc_info=True)
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status with action execution info"""
        return {
            "monitoring_active": self.monitoring_active,
            "monitoring_cycles": self.monitoring_cycles,
            "tracked_wagers": len(self.tracked_wagers),
            "recent_fills": len(self.recent_fills),
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
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
                    for action in self.action_history[-5:]  # Last 5 actions
                ]
            },
            "settings": {
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "fill_wait_period_seconds": self.fill_wait_period_seconds,
                "max_exposure_multiplier": self.max_exposure_multiplier
            }
        }
    
    def format_tracked_wagers_for_response(self) -> Dict[str, Any]:
        """Format tracked wagers for API response"""
        formatted_wagers = {}
        
        for external_id, wager in self.tracked_wagers.items():
            formatted_wagers[external_id] = {
                "external_id": wager.external_id,
                "prophetx_wager_id": wager.prophetx_wager_id,
                "line_id": wager.line_id,
                "event_id": wager.event_id,
                "market_id": wager.market_id,
                "market_type": wager.market_type,
                "side": wager.side,
                "odds": wager.odds,
                "stake": wager.stake,
                "status": wager.status,
                "opportunity_type": wager.opportunity_type,
                "placed_at": wager.placed_at.isoformat(),
                "last_updated": wager.last_updated.isoformat(),
                "cancellation_info": {
                    "external_id": wager.external_id,
                    "prophetx_wager_id": wager.prophetx_wager_id,
                    "can_cancel": wager.status in ["pending", "unmatched"],
                    "cancel_endpoint": "/betting/cancel-wager"
                }
            }
        
        return formatted_wagers


# Global service instance
high_wager_monitoring_service = HighWagerMonitoringService()