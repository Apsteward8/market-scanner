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
                market_id=opportunity.market_id,
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
                market_id=opp1.market_id,
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
                market_id=opp2.market_id,
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
            
            # Check balance
            logger.info(f"💰 Checking balance for ${request.stake} bet on {request.side}")
            balance_check = await self._check_balance_sufficiency(request.stake)
            
            if not balance_check["sufficient_funds"]:
                return BetPlacementResult(
                    success=False,
                    request=request,
                    error=f"Insufficient funds: {balance_check.get('error', 'Unknown balance error')}",
                    balance_before=balance_check.get("total_balance")
                )
            
            balance_before = balance_check["total_balance"]
            
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