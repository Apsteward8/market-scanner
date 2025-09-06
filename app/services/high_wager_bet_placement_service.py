#!/usr/bin/env python3
"""
High Wager Bet Placement Service
Places bets based on arbitrage analysis results with proper balance checking and verification
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
import time

logger = logging.getLogger(__name__)

@dataclass
class BetPlacementRequest:
    """Request to place a single bet"""
    opportunity_id: str  # Unique ID for this opportunity
    event_id: str
    event_name: str
    market_id: str
    market_type: str
    line_info: str
    
    # Bet details
    side: str  # What we're betting on (e.g., "Michigan State -21")
    odds: int  # ProphetX odds we're betting at
    stake: float  # Amount to wager
    
    # Context
    bet_type: str  # "single", "arbitrage_primary", "arbitrage_secondary"
    expected_gross_winnings: float
    expected_commission: float
    expected_net_winnings: float
    
    # Metadata for tracking
    large_bet_combined_size: float  # Size of the large bet we're following
    strategy_explanation: str

@dataclass
class BetPlacementResult:
    """Result of attempting to place a bet"""
    success: bool
    bet_id: Optional[str] = None
    external_id: Optional[str] = None
    prophetx_bet_id: Optional[str] = None
    error: Optional[str] = None
    
    # Bet details
    request: Optional[BetPlacementRequest] = None
    actual_stake: Optional[float] = None
    status: Optional[str] = None
    
    # Balance info
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    balance_verified: bool = False
    
    # Timing
    placed_at: Optional[datetime] = None
    placement_duration_ms: Optional[float] = None

@dataclass
class ArbitragePairResult:
    """Result of placing an arbitrage pair"""
    success: bool
    bet_1_result: BetPlacementResult
    bet_2_result: BetPlacementResult
    total_stake: float
    guaranteed_profit: float
    both_placed: bool
    error: Optional[str] = None
    rollback_attempted: bool = False
    rollback_success: bool = False

class HighWagerBetPlacementService:
    """Service for placing high wager following bets with proper verification"""
    
    def __init__(self):
        from app.services.prophetx_service import prophetx_service
        from app.core.config import get_settings
        
        self.prophetx_service = prophetx_service
        self.settings = get_settings()
        
        # Bet tracking
        self.placed_bets: Dict[str, BetPlacementResult] = {}
        self.arbitrage_pairs: Dict[str, ArbitragePairResult] = {}
        
        # Safety settings
        self.balance_buffer = 10.0  # $10 buffer for balance checks
        self.max_stake_per_bet = 500.0  # Maximum stake per individual bet
        self.dry_run_mode = False  # Set to True for testing
        
        # External ID prefix for tracking our bets
        self.external_id_prefix = "high_wager_follow"
        
    def set_dry_run_mode(self, enabled: bool):
        """Enable/disable dry run mode for testing"""
        self.dry_run_mode = enabled
        logger.info(f"🧪 Dry run mode: {'ENABLED' if enabled else 'DISABLED'}")

    async def place_all_opportunities_batch(self, betting_decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Place all betting opportunities using batch API
        
        Args:
            betting_decisions: List of betting decisions from arbitrage service
            
        Returns:
            Detailed results with individual bet outcomes
        """
        try:
            logger.info(f"🚀 Starting batch placement for {len(betting_decisions)} decisions...")
            
            # Collect all wagers to place
            wagers_to_place = []
            decision_map = {}  # Maps external_id to decision info
            
            for decision in betting_decisions:
                if decision["type"] == "single_opportunity" and decision["action"] == "bet":
                    wager, decision_info = await self._prepare_single_opportunity_wager(decision)
                    if wager:
                        wagers_to_place.append(wager)
                        decision_map[wager["external_id"]] = decision_info
                        
                elif decision["type"] == "opposing_opportunities" and decision["action"] == "bet_both":
                    wagers, decision_infos = await self._prepare_arbitrage_pair_wagers(decision)
                    if wagers:
                        wagers_to_place.extend(wagers)
                        for wager, info in zip(wagers, decision_infos):
                            decision_map[wager["external_id"]] = info
            
            if not wagers_to_place:
                return {
                    "success": True,
                    "message": "No wagers to place",
                    "summary": {
                        "total_decisions": len(betting_decisions),
                        "wagers_prepared": 0,
                        "successful_bets": 0,
                        "failed_bets": 0,
                        "total_stakes_placed": 0.0
                    },
                    "results": {"single_bets": [], "arbitrage_pairs": [], "skipped": []}
                }
            
            logger.info(f"📋 Prepared {len(wagers_to_place)} wagers for batch placement")
            
            # Check if we have sufficient funds for all wagers
            total_stake_required = sum(w["stake"] for w in wagers_to_place)
            funds_check = await self.prophetx_service.check_sufficient_funds(total_stake_required)
            
            if not funds_check.get("sufficient_funds"):
                return {
                    "success": False,
                    "error": f"Insufficient funds: need ${total_stake_required:.2f}, have ${funds_check.get('available_balance', 0):.2f}",
                    "funds_check": funds_check,
                    "summary": {"total_decisions": len(betting_decisions), "wagers_prepared": len(wagers_to_place)},
                    "results": {"single_bets": [], "arbitrage_pairs": [], "skipped": []}
                }
            
            # Place all wagers in batch
            batch_result = await self.prophetx_service.place_multiple_wagers(wagers_to_place)
            
            # Process results and map back to original decisions
            results = await self._process_batch_results(batch_result, decision_map)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch placement: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Batch placement exception: {str(e)}",
                "summary": {"total_decisions": len(betting_decisions)},
                "results": {"single_bets": [], "arbitrage_pairs": [], "skipped": []}
            }

    async def _prepare_single_opportunity_wager(self, decision: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Prepare a single opportunity for batch placement
        
        Returns:
            Tuple of (wager_dict, decision_info) or (None, None) if can't prepare
        """
        try:
            analysis = decision.get("analysis")
            if not analysis or analysis.recommendation != "bet":
                return None, None
            
            opportunity = analysis.opportunity
            sizing = analysis.sizing
            
            # Create external ID
            external_id = f"single_{opportunity.event_id}_{opportunity.line_id}_{int(time.time() * 1000)}"
            
            # Prepare wager for batch API
            wager = {
                "external_id": external_id,
                "line_id": opportunity.line_id,
                "odds": opportunity.our_proposed_odds,
                "stake": sizing.stake_amount
            }
            
            # Store decision info for result mapping
            decision_info = {
                "type": "single",
                "external_id": external_id,
                "event_name": opportunity.event_name,
                "side": opportunity.large_bet_side,
                "stake": sizing.stake_amount,
                "expected_net_winnings": sizing.expected_net_winnings,
                "opportunity": opportunity,
                "analysis": analysis
            }
            
            return wager, decision_info
            
        except Exception as e:
            logger.error(f"Error preparing single opportunity wager: {e}")
            return None, None

    async def _prepare_arbitrage_pair_wagers(self, decision: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """
        Prepare an arbitrage pair for batch placement
        
        Returns:
            Tuple of (wagers_list, decision_infos_list) or ([], []) if can't prepare
        """
        try:
            analysis = decision.get("analysis")
            if not analysis or analysis.recommendation != "bet_both":
                return [], []
            
            opp1 = analysis.opportunity_1
            opp2 = analysis.opportunity_2
            sizing1 = analysis.bet_1_sizing
            sizing2 = analysis.bet_2_sizing
            
            # Generate pair ID and external IDs
            pair_id = self._generate_arbitrage_pair_id(opp1.event_id, opp1.market_id)
            external_id_1 = f"arb_{pair_id}_bet1_{int(time.time() * 1000)}"
            external_id_2 = f"arb_{pair_id}_bet2_{int(time.time() * 1000) + 1}"
            
            # Prepare wagers for batch API
            wager1 = {
                "external_id": external_id_1,
                "line_id": opp1.line_id,
                "odds": opp1.our_proposed_odds,
                "stake": sizing1.stake_amount
            }
            
            wager2 = {
                "external_id": external_id_2,
                "line_id": opp2.line_id,
                "odds": opp2.our_proposed_odds,
                "stake": sizing2.stake_amount
            }
            
            # Store decision info for result mapping
            decision_info_1 = {
                "type": "arbitrage",
                "pair_id": pair_id,
                "bet_number": 1,
                "external_id": external_id_1,
                "paired_external_id": external_id_2,
                "event_name": opp1.event_name,
                "side": opp1.large_bet_side,
                "stake": sizing1.stake_amount,
                "guaranteed_profit": analysis.guaranteed_profit,
                "total_stake": sizing1.stake_amount + sizing2.stake_amount,
                "opportunity": opp1,
                "analysis": analysis
            }
            
            decision_info_2 = {
                "type": "arbitrage",
                "pair_id": pair_id,
                "bet_number": 2,
                "external_id": external_id_2,
                "paired_external_id": external_id_1,
                "event_name": opp2.event_name,
                "side": opp2.large_bet_side,
                "stake": sizing2.stake_amount,
                "guaranteed_profit": analysis.guaranteed_profit,
                "total_stake": sizing1.stake_amount + sizing2.stake_amount,
                "opportunity": opp2,
                "analysis": analysis
            }
            
            return [wager1, wager2], [decision_info_1, decision_info_2]
            
        except Exception as e:
            logger.error(f"Error preparing arbitrage pair wagers: {e}")
            return [], []

    async def _process_batch_results(self, batch_result: Dict[str, Any], decision_map: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Process batch placement results and map back to original decision structure
        """
        try:
            success_wagers = batch_result.get("success_wagers", {})
            failed_wagers = batch_result.get("failed_wagers", {})
            
            # Track results
            single_bets = []
            arbitrage_pairs = {}  # Group by pair_id
            skipped = []
            
            successful_bets = 0
            failed_bets = 0
            total_stakes = 0.0
            
            # Process all decisions (successful and failed)
            all_external_ids = set(decision_map.keys())
            
            for external_id in all_external_ids:
                decision_info = decision_map[external_id]
                
                if external_id in success_wagers:
                    # Successful bet
                    wager_result = success_wagers[external_id]
                    successful_bets += 1
                    total_stakes += decision_info["stake"]
                    
                    if decision_info["type"] == "single":
                        single_bets.append({
                            "event": decision_info["event_name"],
                            "success": True,
                            "bet_id": wager_result["bet_id"],
                            "external_id": external_id,
                            "stake": decision_info["stake"],
                            "side": decision_info["side"],
                            "error": None
                        })
                        
                    elif decision_info["type"] == "arbitrage":
                        pair_id = decision_info["pair_id"]
                        if pair_id not in arbitrage_pairs:
                            arbitrage_pairs[pair_id] = {
                                "event": decision_info["event_name"],
                                "guaranteed_profit": decision_info["guaranteed_profit"],
                                "total_stake": decision_info["total_stake"],
                                "bet_1_success": False,
                                "bet_2_success": False,
                                "bet_1_error": None,
                                "bet_2_error": None
                            }
                        
                        if decision_info["bet_number"] == 1:
                            arbitrage_pairs[pair_id]["bet_1_success"] = True
                        else:
                            arbitrage_pairs[pair_id]["bet_2_success"] = True
                            
                elif external_id in failed_wagers:
                    # Failed bet
                    failure_result = failed_wagers[external_id]
                    failed_bets += 1
                    
                    if decision_info["type"] == "single":
                        single_bets.append({
                            "event": decision_info["event_name"],
                            "success": False,
                            "bet_id": None,
                            "external_id": external_id,
                            "stake": decision_info["stake"],
                            "side": decision_info["side"],
                            "error": failure_result.get("message", failure_result.get("error"))
                        })
                        
                    elif decision_info["type"] == "arbitrage":
                        pair_id = decision_info["pair_id"]
                        if pair_id not in arbitrage_pairs:
                            arbitrage_pairs[pair_id] = {
                                "event": decision_info["event_name"],
                                "guaranteed_profit": decision_info["guaranteed_profit"],
                                "total_stake": decision_info["total_stake"],
                                "bet_1_success": False,
                                "bet_2_success": False,
                                "bet_1_error": None,
                                "bet_2_error": None
                            }
                        
                        error_msg = failure_result.get("message", failure_result.get("error"))
                        if decision_info["bet_number"] == 1:
                            arbitrage_pairs[pair_id]["bet_1_error"] = error_msg
                        else:
                            arbitrage_pairs[pair_id]["bet_2_error"] = error_msg
            
            # Convert arbitrage pairs to final format
            arbitrage_results = []
            for pair_id, pair_data in arbitrage_pairs.items():
                both_placed = pair_data["bet_1_success"] and pair_data["bet_2_success"]
                success = both_placed
                
                error = None
                if not both_placed:
                    errors = []
                    if pair_data["bet_1_error"]:
                        errors.append(f"Bet 1: {pair_data['bet_1_error']}")
                    if pair_data["bet_2_error"]:
                        errors.append(f"Bet 2: {pair_data['bet_2_error']}")
                    error = "; ".join(errors) if errors else "One or both bets failed"
                
                arbitrage_results.append({
                    "event": pair_data["event"],
                    "success": success,
                    "both_placed": both_placed,
                    "total_stake": pair_data["total_stake"],
                    "guaranteed_profit": pair_data["guaranteed_profit"],
                    "error": error
                })
            
            # Calculate summary
            success_rate = (successful_bets / (successful_bets + failed_bets) * 100) if (successful_bets + failed_bets) > 0 else 0
            
            summary = {
                "total_bets_attempted": successful_bets + failed_bets,
                "successful_bets": successful_bets,
                "failed_bets": failed_bets,
                "single_opportunities": len([sb for sb in single_bets if sb["success"]]),
                "arbitrage_pairs": len([ar for ar in arbitrage_results if ar["both_placed"]]),
                "total_stakes_placed": round(total_stakes, 2),
                "success_rate": round(success_rate, 1)
            }
            
            return {
                "success": batch_result.get("success", False),
                "message": f"Batch placement complete: {successful_bets} placed, {failed_bets} failed",
                "data": {
                    "batch_api_result": batch_result,
                    "summary": summary,
                    "results": {
                        "single_bets": single_bets,
                        "arbitrage_pairs": arbitrage_results,
                        "skipped": skipped
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing batch results: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error processing batch results: {str(e)}",
                "data": {"batch_api_result": batch_result}
            }
    
    async def place_single_opportunity(self, opportunity_analysis: Dict[str, Any]) -> BetPlacementResult:
        """
        Place a bet for a single opportunity (not arbitrage)
        
        Args:
            opportunity_analysis: Analysis result from arbitrage service
            
        Returns:
            BetPlacementResult with success/failure details
        """
        try:
            analysis = opportunity_analysis.get("analysis")
            if not analysis or analysis.recommendation != "bet":
                return BetPlacementResult(
                    success=False,
                    error=f"Opportunity not recommended for betting: {analysis.recommendation if analysis else 'No analysis'}"
                )
            
            # Create bet placement request
            opportunity = analysis.opportunity
            sizing = analysis.sizing
            
            request = BetPlacementRequest(
                opportunity_id=self._generate_opportunity_id(opportunity.event_id, opportunity.market_id),
                event_id=opportunity.event_id,
                event_name=opportunity.event_name,
                market_id=opportunity.line_id,
                market_type=opportunity.market_type,
                line_info=opportunity.line_info,
                side=opportunity.large_bet_side,  # We bet the same side as large bettor
                odds=opportunity.our_proposed_odds,
                stake=sizing.stake_amount,
                bet_type="single",
                expected_gross_winnings=sizing.expected_gross_winnings,
                expected_commission=sizing.expected_commission,
                expected_net_winnings=sizing.expected_net_winnings,
                large_bet_combined_size=opportunity.large_bet_combined_size,
                strategy_explanation=f"Following ${opportunity.large_bet_combined_size:,.0f} large bet on {opportunity.large_bet_side}"
            )
            
            # Place the bet
            result = await self._place_single_bet(request)
            
            # Track the result
            if result.success:
                self.placed_bets[request.opportunity_id] = result
                logger.info(f"✅ Single opportunity bet placed: {request.side} @ {request.odds:+d} for ${request.stake}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error placing single opportunity: {e}", exc_info=True)
            return BetPlacementResult(
                success=False,
                error=f"Exception in place_single_opportunity: {str(e)}"
            )
    
    async def place_arbitrage_pair(self, arbitrage_analysis: Dict[str, Any]) -> ArbitragePairResult:
        """
        Place both bets for an arbitrage opportunity with rollback on failure
        
        Args:
            arbitrage_analysis: Arbitrage analysis result
            
        Returns:
            ArbitragePairResult with detailed success/failure info
        """
        try:
            analysis = arbitrage_analysis.get("analysis")
            if not analysis or analysis.recommendation != "bet_both":
                return ArbitragePairResult(
                    success=False,
                    bet_1_result=BetPlacementResult(success=False, error="Not recommended for arbitrage"),
                    bet_2_result=BetPlacementResult(success=False, error="Not recommended for arbitrage"),
                    total_stake=0,
                    guaranteed_profit=0,
                    both_placed=False,
                    error=f"Arbitrage not recommended: {analysis.recommendation if analysis else 'No analysis'}"
                )
            
            # Create requests for both bets
            opp1 = analysis.opportunity_1
            opp2 = analysis.opportunity_2
            sizing1 = analysis.bet_1_sizing
            sizing2 = analysis.bet_2_sizing
            
            pair_id = self._generate_arbitrage_pair_id(opp1.event_id, opp1.market_id)
            
            request1 = BetPlacementRequest(
                opportunity_id=f"{pair_id}_bet1",
                event_id=opp1.event_id,
                event_name=opp1.event_name,
                market_id=opp1.line_id,
                market_type=opp1.market_type,
                line_info=opp1.line_info,
                side=opp1.large_bet_side,
                odds=opp1.our_proposed_odds,
                stake=sizing1.stake_amount,
                bet_type="arbitrage_primary",
                expected_gross_winnings=sizing1.expected_gross_winnings,
                expected_commission=sizing1.expected_commission,
                expected_net_winnings=sizing1.expected_net_winnings,
                large_bet_combined_size=opp1.large_bet_combined_size,
                strategy_explanation=f"Arbitrage bet 1: {opp1.large_bet_side} @ {opp1.our_proposed_odds:+d}"
            )
            
            request2 = BetPlacementRequest(
                opportunity_id=f"{pair_id}_bet2",
                event_id=opp2.event_id,
                event_name=opp2.event_name,
                market_id=opp2.line_id,
                market_type=opp2.market_type,
                line_info=opp2.line_info,
                side=opp2.large_bet_side,
                odds=opp2.our_proposed_odds,
                stake=sizing2.stake_amount,
                bet_type="arbitrage_secondary",
                expected_gross_winnings=sizing2.expected_gross_winnings,
                expected_commission=sizing2.expected_commission,
                expected_net_winnings=sizing2.expected_net_winnings,
                large_bet_combined_size=opp2.large_bet_combined_size,
                strategy_explanation=f"Arbitrage bet 2: {opp2.large_bet_side} @ {opp2.our_proposed_odds:+d}"
            )
            
            logger.info(f"🎯 Placing arbitrage pair: ${request1.stake} + ${request2.stake} = ${request1.stake + request2.stake} total")
            
            # Place first bet
            result1 = await self._place_single_bet(request1)
            
            if not result1.success:
                return ArbitragePairResult(
                    success=False,
                    bet_1_result=result1,
                    bet_2_result=BetPlacementResult(success=False, error="First bet failed, second bet not attempted"),
                    total_stake=request1.stake + request2.stake,
                    guaranteed_profit=analysis.guaranteed_profit,
                    both_placed=False,
                    error=f"First bet failed: {result1.error}"
                )
            
            logger.info(f"✅ First arbitrage bet placed: {request1.side} @ {request1.odds:+d}")
            
            # Place second bet
            result2 = await self._place_single_bet(request2)
            
            if not result2.success:
                # First bet succeeded but second failed - attempt rollback
                logger.error(f"❌ Second arbitrage bet failed: {result2.error}")
                logger.info("🔄 Attempting to cancel first bet to avoid unbalanced position...")
                
                rollback_success = await self._attempt_rollback(result1)
                
                return ArbitragePairResult(
                    success=False,
                    bet_1_result=result1,
                    bet_2_result=result2,
                    total_stake=request1.stake + request2.stake,
                    guaranteed_profit=analysis.guaranteed_profit,
                    both_placed=False,
                    error=f"Second bet failed: {result2.error}",
                    rollback_attempted=True,
                    rollback_success=rollback_success
                )
            
            # Both bets succeeded!
            logger.info(f"✅ Arbitrage pair complete: Guaranteed profit ${analysis.guaranteed_profit:.2f}")
            
            # Track both bets
            self.placed_bets[request1.opportunity_id] = result1
            self.placed_bets[request2.opportunity_id] = result2
            
            pair_result = ArbitragePairResult(
                success=True,
                bet_1_result=result1,
                bet_2_result=result2,
                total_stake=request1.stake + request2.stake,
                guaranteed_profit=analysis.guaranteed_profit,
                both_placed=True
            )
            
            self.arbitrage_pairs[pair_id] = pair_result
            return pair_result
            
        except Exception as e:
            logger.error(f"Error placing arbitrage pair: {e}", exc_info=True)
            return ArbitragePairResult(
                success=False,
                bet_1_result=BetPlacementResult(success=False, error=str(e)),
                bet_2_result=BetPlacementResult(success=False, error=str(e)),
                total_stake=0,
                guaranteed_profit=0,
                both_placed=False,
                error=f"Exception in place_arbitrage_pair: {str(e)}"
            )
    
    async def _place_single_bet(self, request: BetPlacementRequest) -> BetPlacementResult:
        """
        Place a single bet with full verification and error handling
        """
        start_time = time.time()
        
        try:
            # Validate request
            validation_error = self._validate_bet_request(request)
            if validation_error:
                return BetPlacementResult(
                    success=False,
                    request=request,
                    error=validation_error
                )
            
            # Check balance BEFORE placing bet
            logger.info(f"💰 Checking balance for ${request.stake} bet on {request.side}")
            balance_check = await self.prophetx_service.check_sufficient_funds(
                required_amount=request.stake,
                safety_buffer=self.balance_buffer
            )
            
            if not balance_check.get("sufficient_funds"):
                return BetPlacementResult(
                    success=False,
                    request=request,
                    error=f"Insufficient funds: Need ${balance_check.get('total_required', request.stake):.2f}, have ${balance_check.get('available_balance', 0):.2f}",
                    balance_before=balance_check.get("available_balance")
                )
            
            # IMPORTANT: Store AVAILABLE balance only, not total balance
            balance_before = balance_check["available_balance"]
                        
            # Generate external ID for tracking
            external_id = self._generate_external_id(request)
            
            if self.dry_run_mode:
                # Simulate bet placement in dry run mode
                logger.info(f"🧪 DRY RUN: Would place bet {request.side} @ {request.odds:+d} for ${request.stake}")
                return BetPlacementResult(
                    success=True,
                    bet_id="DRY_RUN_BET_ID",
                    external_id=external_id,
                    prophetx_bet_id="DRY_RUN_PROPHETX_ID",
                    request=request,
                    actual_stake=request.stake,
                    status="DRY_RUN_PLACED",
                    balance_before=balance_before,
                    balance_after=balance_before - request.stake,
                    balance_verified=True,
                    placed_at=datetime.now(timezone.utc),
                    placement_duration_ms=(time.time() - start_time) * 1000
                )
            
            # Place actual bet via ProphetX API
            logger.info(f"🎯 Placing bet: {request.side} @ {request.odds:+d} for ${request.stake}")
            
            # This would need to call your actual ProphetX bet placement method
            # I'm using a placeholder - you'll need to integrate with your prophetx_service
            bet_result = await self._call_prophetx_place_bet(
                market_id=request.market_id,
                odds=request.odds,
                stake=request.stake,
                external_id=external_id,
                selection_name=request.side
            )
            
            if not bet_result.get("success"):
                return BetPlacementResult(
                    success=False,
                    request=request,
                    error=f"ProphetX API error: {bet_result.get('error', 'Unknown error')}",
                    balance_before=balance_before
                )
            
            # Verify bet was placed and check balance
            balance_after = await self._verify_bet_placement(bet_result, balance_before, request.stake)
            
            duration_ms = (time.time() - start_time) * 1000
            
            result = BetPlacementResult(
                success=True,
                bet_id=bet_result.get("bet_id"),
                external_id=external_id,
                prophetx_bet_id=bet_result.get("prophetx_bet_id"),
                request=request,
                actual_stake=bet_result.get("actual_stake", request.stake),
                status=bet_result.get("status", "placed"),
                balance_before=balance_before,
                balance_after=balance_after["balance"],
                balance_verified=balance_after["verified"],
                placed_at=datetime.now(timezone.utc),
                placement_duration_ms=duration_ms
            )
            
            logger.info(f"✅ Bet placed successfully: {external_id} (${request.stake} @ {request.odds:+d})")
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ Error placing bet: {e}", exc_info=True)
            return BetPlacementResult(
                success=False,
                request=request,
                error=f"Placement exception: {str(e)}",
                placement_duration_ms=duration_ms
            )
    
    async def _call_prophetx_place_bet(self, market_id: str, odds: int, stake: float, 
                                     external_id: str, selection_name: str) -> Dict[str, Any]:
        """
        Call ProphetX API to place bet - integrated with your existing prophetx_service
        """
        try:
            logger.info(f"🎯 ProphetX API: Placing bet {selection_name} @ {odds:+d} for ${stake}")
            
            # Use your existing prophetx_service place_bet method
            # This integrates with the patterns I see in your market maker project
            result = await self.prophetx_service.place_bet(
                line_id=market_id,
                odds=odds,
                stake=stake,
                external_id=external_id
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "bet_id": result.get("bet_id"),
                    "prophetx_bet_id": result.get("prophetx_bet_id", external_id),
                    "actual_stake": stake,
                    "status": result.get("status", "placed")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "ProphetX bet placement failed")
                }
            
        except Exception as e:
            logger.error(f"❌ ProphetX bet placement error: {e}")
            return {
                "success": False,
                "error": f"ProphetX API exception: {str(e)}"
            }
    
    async def _check_balance_sufficiency(self, required_stake: float) -> Dict[str, Any]:
        """Check if we have sufficient balance for the bet"""
        try:
            # Use ProphetX service's balance checking method
            result = await self.prophetx_service.check_sufficient_funds(
                required_amount=required_stake, 
                safety_buffer=self.balance_buffer
            )
            
            if result.get("sufficient_funds"):
                logger.info(f"✅ Balance check passed: ${result['available_balance']:.2f} available for ${required_stake} bet")
            else:
                logger.warning(f"❌ Balance check failed: Need ${result.get('shortfall', 0):.2f} more funds")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Balance check exception: {e}")
            return {
                "sufficient_funds": False,
                "error": f"Balance check exception: {str(e)}"
            }
    
    async def _verify_bet_placement(self, bet_result: Dict[str, Any], 
                                  balance_before: float, stake: float) -> Dict[str, Any]:
        """Verify bet was placed and balance was deducted correctly"""
        try:
            # Small delay to allow ProphetX to update balance
            await asyncio.sleep(0.5)
            
            balance_check = await self.prophetx_service.get_account_balance()
            
            if balance_check.get("success"):
                current_balance = balance_check["data"]["available"]
                expected_balance = balance_before - stake
                tolerance = 1.0  # $1 tolerance for fees, etc.
                
                balance_diff = abs(current_balance - expected_balance)
                verified = balance_diff <= tolerance
                
                if not verified:
                    logger.warning(f"⚠️ Balance verification failed: Expected ~${expected_balance:.2f}, got ${current_balance:.2f}")
                
                return {
                    "balance": current_balance,
                    "verified": verified,
                    "expected": expected_balance,
                    "difference": balance_diff
                }
            else:
                return {
                    "balance": None,
                    "verified": False,
                    "error": "Failed to get updated balance"
                }
                
        except Exception as e:
            return {
                "balance": None,
                "verified": False,
                "error": f"Balance verification exception: {str(e)}"
            }
    
    async def _attempt_rollback(self, bet_result: BetPlacementResult) -> bool:
        """Attempt to cancel a bet to rollback a failed arbitrage pair"""
        try:
            if not bet_result.prophetx_bet_id:
                logger.error("Cannot rollback bet - no ProphetX bet ID available")
                return False
            
            logger.info(f"🔄 Attempting to cancel ProphetX bet {bet_result.prophetx_bet_id}")
            
            # Use your existing prophetx_service cancel method
            cancel_result = await self.prophetx_service.cancel_bet(bet_result.prophetx_bet_id)
            
            if cancel_result.get("success"):
                logger.info(f"✅ Successfully cancelled bet {bet_result.prophetx_bet_id}")
                return True
            else:
                logger.error(f"❌ Failed to cancel bet: {cancel_result.get('error')}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Rollback attempt failed: {e}")
            return False
    
    def _validate_bet_request(self, request: BetPlacementRequest) -> Optional[str]:
        """Validate bet request parameters"""
        if request.stake <= 0:
            return f"Invalid stake amount: ${request.stake}"
        
        if request.stake > self.max_stake_per_bet:
            return f"Stake ${request.stake} exceeds maximum ${self.max_stake_per_bet}"
        
        if abs(request.odds) > 2500:
            return f"Odds {request.odds} are outside reasonable range"
        
        if not request.side or not request.event_name:
            return "Missing required bet details"
        
        return None
    
    def _generate_opportunity_id(self, event_id: str, market_id: str) -> str:
        """Generate unique opportunity ID"""
        timestamp = int(time.time())
        return f"{event_id}_{market_id}_{timestamp}"
    
    def _generate_arbitrage_pair_id(self, event_id: str, market_id: str) -> str:
        """Generate unique arbitrage pair ID"""
        timestamp = int(time.time())
        return f"arb_{event_id}_{market_id}_{timestamp}"
    
    def _generate_external_id(self, request: BetPlacementRequest) -> str:
        """Generate external ID for ProphetX tracking"""
        unique_suffix = str(uuid.uuid4()).replace('-', '')[:8]
        return f"{self.external_id_prefix}_{request.opportunity_id}_{unique_suffix}"
    
    def get_placement_summary(self) -> Dict[str, Any]:
        """Get summary of all bet placements"""
        single_bets = [bet for bet in self.placed_bets.values() 
                      if bet.request and bet.request.bet_type == "single"]
        arbitrage_bets = [bet for bet in self.placed_bets.values() 
                         if bet.request and bet.request.bet_type.startswith("arbitrage")]
        
        successful_bets = [bet for bet in self.placed_bets.values() if bet.success]
        failed_bets = [bet for bet in self.placed_bets.values() if not bet.success]
        
        total_stakes = sum(bet.actual_stake or 0 for bet in successful_bets)
        
        return {
            "total_bets_attempted": len(self.placed_bets),
            "successful_bets": len(successful_bets),
            "failed_bets": len(failed_bets),
            "single_opportunities": len(single_bets),
            "arbitrage_pairs": len(self.arbitrage_pairs),
            "total_stakes_placed": round(total_stakes, 2),
            "dry_run_mode": self.dry_run_mode,
            "success_rate": len(successful_bets) / len(self.placed_bets) * 100 if self.placed_bets else 0
        }


# Global service instance
high_wager_bet_placement_service = HighWagerBetPlacementService()