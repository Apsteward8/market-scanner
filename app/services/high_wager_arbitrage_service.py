#!/usr/bin/env python3
"""
High Wager Arbitrage Service
Handles arbitrage detection, bet sizing, and commission calculations for high wager following
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from app.services.market_scanning_service import HighWagerOpportunity

logger = logging.getLogger(__name__)

@dataclass
class CommissionAdjustedOdds:
    """Odds adjusted for ProphetX's 3% commission"""
    original_odds: int
    adjusted_odds: float
    is_plus: bool  # True if adjusted odds are positive, False if negative
    commission_rate: float = 0.03

@dataclass
class BetSizingResult:
    """Result of bet sizing calculation"""
    stake_amount: float
    expected_gross_winnings: float
    expected_commission: float
    expected_net_winnings: float
    expected_total_return: float  # stake + net winnings
    effective_odds_after_commission: float

@dataclass
class ArbitrageOpportunity:
    """Two opposing high wagers that may be arbitrage"""
    opportunity_1: HighWagerOpportunity
    opportunity_2: HighWagerOpportunity
    is_arbitrage: bool
    bet_1_sizing: BetSizingResult
    bet_2_sizing: BetSizingResult
    total_stake: float
    guaranteed_profit: float
    profit_margin: float
    recommendation: str  # "bet_both", "bet_larger", "bet_neither"

@dataclass
class SingleOpportunityAnalysis:
    """Analysis of a single high wager opportunity"""
    opportunity: HighWagerOpportunity
    sizing: BetSizingResult
    recommendation: str  # "bet", "skip" 
    reason: str

class HighWagerArbitrageService:
    """Service for analyzing arbitrage opportunities in high wager following"""
    
    def __init__(self):
        self.commission_rate = 0.03  # ProphetX's 3% commission
        self.base_bet_amount = 100.0  # $100 base bet for plus odds
        self.target_win_amount = 100.0  # Target $100 win for minus odds (after commission)
    
    def apply_commission_adjustment(self, odds: int) -> CommissionAdjustedOdds:
        """
        Apply 3% commission to calculate effective odds in proper American format
        
        Commission is taken from winnings AFTER we win, affecting our true return
        """
        if odds > 0:
            # Positive odds: we win less due to commission on winnings
            # If we bet $100 at +115, we should win $115 but only get $111.55
            raw_adjusted = odds * (1 - self.commission_rate)
            
            # FIXED: Handle American odds conversion properly
            if raw_adjusted < 100:
                # Convert to negative American odds format
                # If effective return is less than 100%, convert to negative odds
                adjusted_odds = -100 / (raw_adjusted / 100)
                is_plus = False
            else:
                adjusted_odds = raw_adjusted
                is_plus = True
                
            return CommissionAdjustedOdds(
                original_odds=odds,
                adjusted_odds=adjusted_odds,
                is_plus=is_plus,
                commission_rate=self.commission_rate
            )
        else:
            # Negative odds: we need to risk more to get our target after commission
            # If we want to win $100 after commission, we need to win $103.09 before
            adjusted_odds = odds / (1 - self.commission_rate)
            return CommissionAdjustedOdds(
                original_odds=odds,
                adjusted_odds=adjusted_odds,
                is_plus=False,
                commission_rate=self.commission_rate
            )
    
    def calculate_bet_sizing(self, odds: int, betting_strategy: str = "standard") -> BetSizingResult:
        """
        Calculate bet sizing based on strategy:
        - Commission-adjusted plus odds: Bet $100
        - Commission-adjusted minus odds: Bet enough to win $100 after commission
        """
        # FIXED: Use commission-adjusted odds to determine strategy
        adj_odds = self.apply_commission_adjustment(odds)
        
        if adj_odds.is_plus:
            # Commission-adjusted odds are positive: bet $100
            stake_amount = self.base_bet_amount
            gross_winnings = stake_amount * (odds / 100.0) if odds > 0 else stake_amount * (100.0 / abs(odds))
            commission = gross_winnings * self.commission_rate
            net_winnings = gross_winnings - commission
            total_return = stake_amount + net_winnings
            effective_odds = net_winnings / stake_amount * 100 if stake_amount > 0 else 0
            
        else:
            # Commission-adjusted odds are negative: bet enough to win $100 after commission
            # We need gross winnings of target_win / (1 - commission_rate) to net $100
            required_gross_winnings = self.target_win_amount / (1 - self.commission_rate)
            if odds > 0:
                stake_amount = required_gross_winnings / (odds / 100.0)
            else:
                stake_amount = required_gross_winnings * (abs(odds) / 100.0)
            
            gross_winnings = required_gross_winnings
            commission = gross_winnings * self.commission_rate
            net_winnings = gross_winnings - commission  # Should be ~$100
            total_return = stake_amount + net_winnings
            effective_odds = -(stake_amount / net_winnings * 100) if net_winnings > 0 else 0
        
        return BetSizingResult(
            stake_amount=round(stake_amount, 2),
            expected_gross_winnings=round(gross_winnings, 2),
            expected_commission=round(commission, 2),
            expected_net_winnings=round(net_winnings, 2),
            expected_total_return=round(total_return, 2),
            effective_odds_after_commission=round(effective_odds, 2)
        )
    
    def is_arbitrage_opportunity(self, odds1: int, odds2: int) -> bool:
        """
        Check if two opposing odds represent an arbitrage opportunity after commission
        
        Rules (accounting for 3% commission with proper American odds conversion):
        1. Both positive after commission: Always arbitrage
        2. One positive, one negative: Arbitrage if abs(positive) > abs(negative) after commission
        3. Both negative after commission: Never arbitrage
        """
        adj_odds1 = self.apply_commission_adjustment(odds1)
        adj_odds2 = self.apply_commission_adjustment(odds2)
        
        # Both positive after commission
        if adj_odds1.is_plus and adj_odds2.is_plus:
            return True
        
        # Both negative after commission  
        if not adj_odds1.is_plus and not adj_odds2.is_plus:
            return False
        
        # One positive, one negative after commission
        if adj_odds1.is_plus and not adj_odds2.is_plus:
            return abs(adj_odds1.adjusted_odds) > abs(adj_odds2.adjusted_odds)
        elif not adj_odds1.is_plus and adj_odds2.is_plus:
            return abs(adj_odds2.adjusted_odds) > abs(adj_odds1.adjusted_odds)
        
        return False
    
    def calculate_arbitrage_bet_sizing(self, odds1: int, odds2: int) -> Tuple[float, float, float]:
        """
        Calculate exact bet sizing for arbitrage opportunity using precise math
        
        Strategy:
        1. Bet $100 on the MORE FAVORABLE odds (regardless of sign)
        2. Calculate EXACT stake needed on less favorable odds to match total payout precisely
        3. Account for 3% commission on all winnings with high precision
        
        Returns: (stake_on_odds1, stake_on_odds2, guaranteed_profit)
        """
        from decimal import Decimal, getcontext
        # Use high precision decimal arithmetic to avoid floating point errors
        getcontext().prec = 50
        
        # Apply commission to both odds
        adj_odds1 = self.apply_commission_adjustment(odds1)
        adj_odds2 = self.apply_commission_adjustment(odds2)
        
        # Calculate expected return per dollar for each side to determine which is more favorable
        def calculate_return_per_dollar_precise(adjusted_odds_obj):
            if adjusted_odds_obj.is_plus:
                # Positive odds: return = 1 + (odds/100)
                return Decimal('1') + (Decimal(str(adjusted_odds_obj.adjusted_odds)) / Decimal('100'))
            else:
                # Negative odds: return = 1 + (100/abs(odds))
                return Decimal('1') + (Decimal('100') / Decimal(str(abs(adjusted_odds_obj.adjusted_odds))))
        
        return_per_dollar_1 = calculate_return_per_dollar_precise(adj_odds1)
        return_per_dollar_2 = calculate_return_per_dollar_precise(adj_odds2)
        
        # Determine which is more favorable
        if return_per_dollar_1 >= return_per_dollar_2:
            # odds1 is more favorable
            better_odds_original = odds1
            better_odds_adj = adj_odds1
            worse_odds_original = odds2
            worse_odds_adj = adj_odds2
            better_is_first = True
        else:
            # odds2 is more favorable
            better_odds_original = odds2
            better_odds_adj = adj_odds2
            worse_odds_original = odds1
            worse_odds_adj = adj_odds1
            better_is_first = False
        
        # Step 1: Bet exactly $100 on the more favorable odds
        better_bet = Decimal('100.00')
        
        # Step 2: Calculate EXACT target payout from the $100 bet
        if better_odds_original > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            gross_winnings = better_bet * (Decimal(str(better_odds_original)) / Decimal('100'))
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            gross_winnings = better_bet * (Decimal('100') / Decimal(str(abs(better_odds_original))))
        
        commission = gross_winnings * Decimal('0.03')
        net_winnings = gross_winnings - commission
        target_payout = better_bet + net_winnings
        
        # Step 3: Calculate EXACT stake needed on worse odds to achieve target payout
        # We need: worse_bet + worse_net_winnings = target_payout
        # Where: worse_net_winnings = worse_gross_winnings * (1 - 0.03)
        
        if worse_odds_original > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            # target_payout = worse_bet + (worse_bet * (odds/100) * 0.97)
            # target_payout = worse_bet * (1 + (odds/100) * 0.97)
            multiplier = Decimal('1') + (Decimal(str(worse_odds_original)) / Decimal('100')) * Decimal('0.97')
            worse_bet = target_payout / multiplier
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            # target_payout = worse_bet + (worse_bet * (100/abs(odds)) * 0.97)
            # target_payout = worse_bet * (1 + (100/abs(odds)) * 0.97)
            multiplier = Decimal('1') + (Decimal('100') / Decimal(str(abs(worse_odds_original)))) * Decimal('0.97')
            worse_bet = target_payout / multiplier
        
        # Step 4: Verify the calculation by computing actual payouts
        # Better bet payout (already calculated)
        better_payout = target_payout
        
        # Worse bet payout
        if worse_odds_original > 0:
            worse_gross = worse_bet * (Decimal(str(worse_odds_original)) / Decimal('100'))
        else:
            worse_gross = worse_bet * (Decimal('100') / Decimal(str(abs(worse_odds_original))))
        
        worse_commission = worse_gross * Decimal('0.03')
        worse_net = worse_gross - worse_commission
        worse_payout = worse_bet + worse_net
        
        # Step 5: Calculate guaranteed profit
        total_investment = better_bet + worse_bet
        guaranteed_profit = target_payout - total_investment  # Should be the same regardless of outcome
        
        # Convert back to float with proper precision
        if better_is_first:
            stake_on_odds1 = float(better_bet)
            stake_on_odds2 = float(worse_bet)
        else:
            stake_on_odds1 = float(worse_bet)
            stake_on_odds2 = float(better_bet)
        
        return (
            round(stake_on_odds1, 2),
            round(stake_on_odds2, 2), 
            round(float(guaranteed_profit), 2)
        )
    
    def _calculate_detailed_sizing_for_arbitrage(self, odds: int, stake: float) -> BetSizingResult:
        """
        Calculate detailed sizing information for a specific odds/stake combination in arbitrage
        Uses ORIGINAL odds for the actual bet calculations (since that's what we bet at)
        """
        if odds > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            gross_winnings = stake * (odds / 100.0)
            commission = gross_winnings * self.commission_rate
            net_winnings = gross_winnings - commission
            total_return = stake + net_winnings
            effective_odds = net_winnings / stake * 100 if stake > 0 else 0
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            gross_winnings = stake * (100 / abs(odds))
            commission = gross_winnings * self.commission_rate
            net_winnings = gross_winnings - commission
            total_return = stake + net_winnings
            effective_odds = -(stake / net_winnings * 100) if net_winnings > 0 else 0
        
        return BetSizingResult(
            stake_amount=round(stake, 2),
            expected_gross_winnings=round(gross_winnings, 2),
            expected_commission=round(commission, 2),
            expected_net_winnings=round(net_winnings, 2),
            expected_total_return=round(total_return, 2),
            effective_odds_after_commission=round(effective_odds, 2)
        )
    
    def analyze_opposing_opportunities(self, opp1: HighWagerOpportunity, opp2: HighWagerOpportunity) -> ArbitrageOpportunity:
        """
        Analyze two opposing high wager opportunities for arbitrage potential
        """
        # Verify they are actually opposing (same market, same line, opposite sides)
        if not self._are_opposing_opportunities(opp1, opp2):
            raise ValueError("Opportunities are not on opposing sides of the same market")
        
        # Get the odds we would bet at (our proposed odds)
        odds1 = opp1.our_proposed_odds
        odds2 = opp2.our_proposed_odds
        
        # Check if this is an arbitrage opportunity  
        is_arbitrage = self.is_arbitrage_opportunity(odds1, odds2)
        
        if is_arbitrage:
            # Calculate exact arbitrage bet sizing using true arbitrage logic
            stake1, stake2, profit = self.calculate_arbitrage_bet_sizing(odds1, odds2)
            
            # Calculate detailed sizing information for each bet
            sizing1 = self._calculate_detailed_sizing_for_arbitrage(odds1, stake1)
            sizing2 = self._calculate_detailed_sizing_for_arbitrage(odds2, stake2)
            
            recommendation = "bet_both"
        else:
            # Not arbitrage - calculate individual sizings and recommend larger one
            sizing1 = self.calculate_bet_sizing(odds1)
            sizing2 = self.calculate_bet_sizing(odds2)
            
            # Recommend the opportunity with larger combined size if difference > $2500
            size_diff = abs(opp1.large_bet_combined_size - opp2.large_bet_combined_size)
            if size_diff > 2500:
                if opp1.large_bet_combined_size > opp2.large_bet_combined_size:
                    recommendation = "bet_first_only"
                else:
                    recommendation = "bet_second_only"
            else:
                recommendation = "bet_neither"
            
            profit = 0.0
        
        return ArbitrageOpportunity(
            opportunity_1=opp1,
            opportunity_2=opp2,
            is_arbitrage=is_arbitrage,
            bet_1_sizing=sizing1,
            bet_2_sizing=sizing2,
            total_stake=sizing1.stake_amount + sizing2.stake_amount,
            guaranteed_profit=profit,
            profit_margin=(profit / (sizing1.stake_amount + sizing2.stake_amount)) * 100 if (sizing1.stake_amount + sizing2.stake_amount) > 0 else 0,
            recommendation=recommendation
        )
    
    def analyze_single_opportunity(self, opportunity: HighWagerOpportunity) -> SingleOpportunityAnalysis:
        """Analyze a single high wager opportunity"""
        
        # Calculate bet sizing
        sizing = self.calculate_bet_sizing(opportunity.our_proposed_odds)
        
        # Determine recommendation
        if sizing.expected_net_winnings > 0:
            recommendation = "bet"
            reason = f"Positive expected value: ${sizing.expected_net_winnings:.2f} net winnings"
        else:
            recommendation = "skip"
            reason = f"Negative expected value after commission"
        
        return SingleOpportunityAnalysis(
            opportunity=opportunity,
            sizing=sizing,
            recommendation=recommendation,
            reason=reason
        )
    
    def group_opportunities_by_market(self, opportunities: List[HighWagerOpportunity]) -> Dict[str, List[HighWagerOpportunity]]:
        """Group opportunities by market for conflict detection"""
        markets = {}
        
        for opp in opportunities:
            # FIXED: Remove line_info from market key since opposing sides have different line_info
            market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}"
            
            if market_key not in markets:
                markets[market_key] = []
            
            markets[market_key].append(opp)
        
        return markets

    def _are_opposing_opportunities(self, opp1: HighWagerOpportunity, opp2: HighWagerOpportunity) -> bool:
        """Check if two opportunities are on opposing sides of the same market"""
        return (
            opp1.event_id == opp2.event_id and
            opp1.market_id == opp2.market_id and  
            opp1.market_type == opp2.market_type and
            # FIXED: Remove line_info check - opposing opportunities will have different line_info
            opp1.large_bet_side != opp2.large_bet_side  # Different sides
        )
    
    def detect_conflicts_and_arbitrage(self, opportunities: List[HighWagerOpportunity]) -> List[Dict[str, Any]]:
        """
        Detect conflicts and arbitrage opportunities across all opportunities
        
        Returns list of betting decisions with analysis
        """
        grouped_markets = self.group_opportunities_by_market(opportunities)
        betting_decisions = []
        
        for market_key, market_opportunities in grouped_markets.items():
            if len(market_opportunities) == 1:
                # Single opportunity - analyze independently
                analysis = self.analyze_single_opportunity(market_opportunities[0])
                betting_decisions.append({
                    "type": "single_opportunity",
                    "market_key": market_key,
                    "analysis": analysis,
                    "action": analysis.recommendation
                })
            
            elif len(market_opportunities) == 2:
                # Two opportunities - check for arbitrage
                arbitrage_analysis = self.analyze_opposing_opportunities(
                    market_opportunities[0], 
                    market_opportunities[1]
                )
                betting_decisions.append({
                    "type": "opposing_opportunities", 
                    "market_key": market_key,
                    "analysis": arbitrage_analysis,
                    "action": arbitrage_analysis.recommendation
                })
            
            else:
                # More than 2 opportunities - this shouldn't happen but handle gracefully
                logger.warning(f"Found {len(market_opportunities)} opportunities for market {market_key}")
                # Analyze each individually for now
                for opp in market_opportunities:
                    analysis = self.analyze_single_opportunity(opp)
                    betting_decisions.append({
                        "type": "multiple_conflict",
                        "market_key": market_key, 
                        "analysis": analysis,
                        "action": "skip"  # Skip when there's ambiguity
                    })
        
        return betting_decisions


# Global service instance  
high_wager_arbitrage_service = HighWagerArbitrageService()