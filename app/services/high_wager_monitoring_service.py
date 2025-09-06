#!/usr/bin/env python3
"""
High Wager Monitoring Service

Monitors high wager opportunities and keeps wagers up to date with market changes.

Workflow:
1. Place initial bets via place-all-opportunities
2. Monitor scan-opportunities every minute
3. Compare current wagers with new recommendations
4. Update wagers when differences are detected
5. Handle filled bets with 5-minute wait periods and exposure limits
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class TrackedWager:
    """Represents a wager we've placed and are tracking"""
    external_id: str
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

class HighWagerMonitoringService:
    """Monitors high wager opportunities and keeps wagers up to date"""
    
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
        
    def initialize_services(self, market_scanning_service, arbitrage_service, 
                          bet_placement_service, prophetx_service):
        """Initialize required services"""
        self.market_scanning_service = market_scanning_service
        self.arbitrage_service = arbitrage_service
        self.bet_placement_service = bet_placement_service
        self.prophetx_service = prophetx_service
        logger.info("🔧 High wager monitoring services initialized")
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """
        Start the complete monitoring workflow
        
        1. Place initial bets
        2. Start monitoring loop
        """
        if self.monitoring_active:
            return {
                "success": False,
                "message": "Monitoring already active"
            }
        
        logger.info("🚀 Starting High Wager Monitoring Service")
        logger.info("=" * 60)
        
        # Step 1: Place initial bets
        logger.info("📍 Step 1: Placing initial bets...")
        initial_result = await self._place_initial_bets()
        
        if not initial_result["success"]:
            return {
                "success": False,
                "message": f"Failed to place initial bets: {initial_result.get('error', 'Unknown error')}"
            }
        
        # Step 2: Start monitoring loop
        self.monitoring_active = True
        asyncio.create_task(self._monitoring_loop())
        
        return {
            "success": True,
            "message": "High wager monitoring started",
            "data": {
                "initial_bets": initial_result["summary"],
                "monitoring_interval": self.monitoring_interval_seconds,
                "fill_wait_period": self.fill_wait_period_seconds,
                "max_exposure_multiplier": self.max_exposure_multiplier
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
                "recent_fills": len(self.recent_fills)
            }
        }
    
    async def _place_initial_bets(self) -> Dict[str, Any]:
        """Place initial bets using the existing place-all-opportunities endpoint"""
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
            if result["success"] and "results" in result:
                await self._update_tracked_wagers_from_placement_result(result)
            
            return {
                "success": result["success"],
                "message": "Initial bets placed",
                "summary": result.get("summary", {}),
                "tracked_wagers": len(self.tracked_wagers)
            }
            
        except Exception as e:
            logger.error(f"Error placing initial bets: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to place initial bets: {str(e)}"
            }
    
    async def _monitoring_loop(self):
        """Main monitoring loop - runs every minute"""
        logger.info("🔄 Starting monitoring loop...")
        
        while self.monitoring_active:
            try:
                cycle_start = datetime.now(timezone.utc)
                self.monitoring_cycles += 1
                
                logger.info(f"🔍 Monitoring cycle #{self.monitoring_cycles} starting...")
                
                # Step 1: Get current opportunities
                current_opportunities = await self._get_current_opportunities()
                
                # Step 2: Compare with tracked wagers
                differences = await self._detect_wager_differences(current_opportunities)
                
                # Step 3: Log findings (for now, we'll implement updates later)
                await self._log_monitoring_results(current_opportunities, differences)
                
                # Step 4: Update tracking info
                self.last_scan_time = cycle_start
                
                # Wait for next cycle
                cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(0, self.monitoring_interval_seconds - cycle_duration)
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
                await asyncio.sleep(self.monitoring_interval_seconds)
    
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
        
        # Create lookup maps
        current_opps_by_line = {opp.line_id: opp for opp in current_opportunities}
        tracked_wagers_by_line = {w.line_id: w for w in self.tracked_wagers.values()}
        
        # Find differences
        all_line_ids = set(current_opps_by_line.keys()) | set(tracked_wagers_by_line.keys())
        
        for line_id in all_line_ids:
            current_opp = current_opps_by_line.get(line_id)
            tracked_wager = tracked_wagers_by_line.get(line_id)
            
            if current_opp and tracked_wager:
                # Both exist - check for changes
                diff = self._compare_wager_vs_opportunity(tracked_wager, current_opp)
                if diff:
                    differences.append(diff)
            
            elif current_opp and not tracked_wager:
                # New opportunity - should place wager
                differences.append(WagerDifference(
                    line_id=line_id,
                    event_id=current_opp.event_id,
                    market_id=current_opp.market_id,
                    market_type=current_opp.market_type,
                    side=current_opp.side,
                    current_odds=None,
                    current_stake=None,
                    current_status=None,
                    recommended_odds=current_opp.recommended_odds,
                    recommended_stake=current_opp.recommended_stake,
                    difference_type="new_opportunity",
                    action_needed="place_new_wager",
                    reason=f"New opportunity detected for {current_opp.market_type}"
                ))
            
            elif tracked_wager and not current_opp:
                # Opportunity no longer recommended - should cancel
                differences.append(WagerDifference(
                    line_id=line_id,
                    event_id=tracked_wager.event_id,
                    market_id=tracked_wager.market_id,
                    market_type=tracked_wager.market_type,
                    side=tracked_wager.side,
                    current_odds=tracked_wager.odds,
                    current_stake=tracked_wager.stake,
                    current_status=tracked_wager.status,
                    recommended_odds=0,
                    recommended_stake=0,
                    difference_type="remove_opportunity",
                    action_needed="cancel_wager",
                    reason="Opportunity no longer recommended"
                ))
        
        return differences
    
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
    
    async def _log_monitoring_results(self, opportunities: List[CurrentOpportunity], differences: List[WagerDifference]):
        """Log the results of monitoring cycle"""
        logger.info(f"📊 Monitoring Results:")
        logger.info(f"   Current opportunities: {len(opportunities)}")
        logger.info(f"   Tracked wagers: {len(self.tracked_wagers)}")
        logger.info(f"   Differences detected: {len(differences)}")
        
        if differences:
            logger.info("🔍 Differences Details:")
            for diff in differences:
                logger.info(f"   {diff.line_id[:8]}... | {diff.difference_type} | {diff.action_needed}")
                logger.info(f"      {diff.reason}")
        else:
            logger.info("✅ No differences detected - all wagers up to date")
    
    async def _update_tracked_wagers_from_placement_result(self, placement_result: Dict[str, Any]):
        """Update tracked wagers from bet placement result"""
        try:
            results = placement_result.get("results", {})
            current_time = datetime.now(timezone.utc)
            
            # Track single bets
            for bet_result in results.get("single_bets", []):
                if bet_result.get("success"):
                    external_id = bet_result.get("external_id")
                    if external_id and external_id in bet_result.get("bet_details", {}):
                        bet_details = bet_result["bet_details"][external_id]
                        
                        tracked_wager = TrackedWager(
                            external_id=external_id,
                            line_id=bet_details.get("line_id", ""),
                            event_id=bet_details.get("event_id", ""),
                            market_id=bet_details.get("market_id", ""),
                            market_type=bet_details.get("market_type", ""),
                            side=bet_details.get("side", ""),
                            odds=bet_details.get("odds", 0),
                            stake=bet_details.get("stake", 0.0),
                            status="pending",
                            placed_at=current_time,
                            last_updated=current_time,
                            large_bet_combined_size=bet_details.get("large_bet_combined_size", 0.0),
                            opportunity_type="single"
                        )
                        
                        self.tracked_wagers[external_id] = tracked_wager
                        logger.info(f"📝 Tracking single bet: {external_id} - {tracked_wager.side} @ {tracked_wager.odds:+d} for ${tracked_wager.stake}")
            
            # Track arbitrage bets
            for arb_result in results.get("arbitrage_pairs", []):
                if arb_result.get("success"):
                    arbitrage_pair_id = arb_result.get("pair_id", "")
                    
                    for bet_key in ["bet_1", "bet_2"]:
                        bet_info = arb_result.get(bet_key, {})
                        if bet_info.get("success"):
                            external_id = bet_info.get("external_id")
                            if external_id and external_id in bet_info.get("bet_details", {}):
                                bet_details = bet_info["bet_details"][external_id]
                                
                                tracked_wager = TrackedWager(
                                    external_id=external_id,
                                    line_id=bet_details.get("line_id", ""),
                                    event_id=bet_details.get("event_id", ""),
                                    market_id=bet_details.get("market_id", ""),
                                    market_type=bet_details.get("market_type", ""),
                                    side=bet_details.get("side", ""),
                                    odds=bet_details.get("odds", 0),
                                    stake=bet_details.get("stake", 0.0),
                                    status="pending",
                                    placed_at=current_time,
                                    last_updated=current_time,
                                    large_bet_combined_size=bet_details.get("large_bet_combined_size", 0.0),
                                    opportunity_type=f"arbitrage_{bet_key[-1]}",  # "arbitrage_1" or "arbitrage_2"
                                    arbitrage_pair_id=arbitrage_pair_id
                                )
                                
                                self.tracked_wagers[external_id] = tracked_wager
                                logger.info(f"📝 Tracking arbitrage bet: {external_id} - {tracked_wager.side} @ {tracked_wager.odds:+d} for ${tracked_wager.stake}")
            
            logger.info(f"📊 Now tracking {len(self.tracked_wagers)} total wagers")
            
        except Exception as e:
            logger.error(f"Error updating tracked wagers: {e}", exc_info=True)
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        return {
            "monitoring_active": self.monitoring_active,
            "monitoring_cycles": self.monitoring_cycles,
            "tracked_wagers": len(self.tracked_wagers),
            "recent_fills": len(self.recent_fills),
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "settings": {
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "fill_wait_period_seconds": self.fill_wait_period_seconds,
                "max_exposure_multiplier": self.max_exposure_multiplier
            }
        }


# Global service instance
high_wager_monitoring_service = HighWagerMonitoringService()