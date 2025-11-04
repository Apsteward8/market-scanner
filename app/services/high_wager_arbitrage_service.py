#!/usr/bin/env python3
"""
High Wager Arbitrage Service
Handles arbitrage detection, bet sizing, and commission calculations for high wager following

UPDATED: Supports player props with 0% commission
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from app.services.market_scanning_service import HighWagerOpportunity

logger = logging.getLogger(__name__)

@dataclass
class CommissionAdjustedOdds:
    """Odds adjusted for commission"""
    original_odds: int
    adjusted_odds: float
    is_plus: bool  # True if adjusted odds are positive, False if negative
    commission_rate: float

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
        from app.core.config import get_settings
        settings = get_settings()
        
        # Commission rates
        self.main_market_commission_rate = 0.01  # 1% commission on main markets
        self.player_prop_commission_rate = 0.00  # 0% commission on player props
        
        # Main markets sizing
        self.base_bet_amount = settings.base_bet_amount  # Default $100
        self.target_win_amount = settings.target_win_amount  # Default $100
        
        # Player props sizing
        self.player_prop_base_bet_amount = settings.player_prop_base_bet_amount  # Default $50
        self.player_prop_target_win_amount = settings.player_prop_target_win_amount  # Default $50
    
    def apply_commission_adjustment(self, odds: int, commission_rate: float = 0.01) -> CommissionAdjustedOdds:
        """
        Apply commission to calculate effective odds in proper American format
        
        Args:
            odds: The original odds
            commission_rate: Commission rate (0.01 for main markets, 0.00 for player props)
        
        Commission is taken from winnings AFTER we win, affecting our true return
        """
        # If no commission, odds stay the same
        if commission_rate == 0.0:
            return CommissionAdjustedOdds(
                original_odds=odds,
                adjusted_odds=float(odds),
                is_plus=odds > 0,
                commission_rate=0.0
            )
        
        if odds > 0:
            # Positive odds: we win less due to commission on winnings
            # If we bet $100 at +115, we should win $115 but only get $113.85 (with 1% commission)
            raw_adjusted = odds * (1 - commission_rate)
            
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
                commission_rate=commission_rate
            )
        else:
            # Negative odds: we need to risk more to get our target after commission
            # If we want to win $100 after commission, we need to win $101.01 before (with 1% commission)
            adjusted_odds = odds / (1 - commission_rate)
            return CommissionAdjustedOdds(
                original_odds=odds,
                adjusted_odds=adjusted_odds,
                is_plus=False,
                commission_rate=commission_rate
            )
    
    def calculate_bet_sizing(self, odds: int, is_player_prop: bool = False) -> BetSizingResult:
        """
        Calculate bet sizing based on strategy:
        - Commission-adjusted plus odds: Bet base amount
        - Commission-adjusted minus odds: Bet enough to win target amount after commission
        
        Args:
            odds: The odds to calculate sizing for
            is_player_prop: If True, use player prop sizing amounts and 0% commission
        """
        # Select the appropriate sizing amounts and commission rate
        if is_player_prop:
            base_bet = self.player_prop_base_bet_amount
            target_win = self.player_prop_target_win_amount
            commission_rate = self.player_prop_commission_rate  # 0%
        else:
            base_bet = self.base_bet_amount
            target_win = self.target_win_amount
            commission_rate = self.main_market_commission_rate  # 1%
        
        # Use commission-adjusted odds to determine strategy
        adj_odds = self.apply_commission_adjustment(odds, commission_rate)
        
        if adj_odds.is_plus:
            # Commission-adjusted odds are positive: bet base amount
            stake_amount = base_bet
            gross_winnings = stake_amount * (odds / 100.0) if odds > 0 else stake_amount * (100.0 / abs(odds))
            commission = gross_winnings * commission_rate
            net_winnings = gross_winnings - commission
            total_return = stake_amount + net_winnings
            effective_odds = net_winnings / stake_amount * 100 if stake_amount > 0 else 0
    
        else:
            # Commission-adjusted odds are negative: bet enough to win target amount after commission
            if commission_rate > 0:
                required_gross_winnings = target_win / (1 - commission_rate)
            else:
                # No commission: gross winnings = net winnings
                required_gross_winnings = target_win
            
            if odds > 0:
                stake_amount = required_gross_winnings / (odds / 100.0)
            else:
                stake_amount = required_gross_winnings * (abs(odds) / 100.0)
            
            gross_winnings = required_gross_winnings
            commission = gross_winnings * commission_rate
            net_winnings = gross_winnings - commission  # Should equal target_win
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
    
    def is_arbitrage_opportunity(self, odds1: int, odds2: int, 
                                is_prop1: bool = False, is_prop2: bool = False) -> bool:
        """
        Check if two opposing odds represent an arbitrage opportunity after commission
        
        Args:
            odds1: First odds
            odds2: Second odds
            is_prop1: If True, first bet is a player prop (0% commission)
            is_prop2: If True, second bet is a player prop (0% commission)
        
        Rules (accounting for commission with proper American odds conversion):
        1. Both positive after commission: Always arbitrage
        2. One positive, one negative: Arbitrage if abs(positive) > abs(negative) after commission
        3. Both negative after commission: Never arbitrage
        """
        commission_rate1 = self.player_prop_commission_rate if is_prop1 else self.main_market_commission_rate
        commission_rate2 = self.player_prop_commission_rate if is_prop2 else self.main_market_commission_rate
        
        adj_odds1 = self.apply_commission_adjustment(odds1, commission_rate1)
        adj_odds2 = self.apply_commission_adjustment(odds2, commission_rate2)
        
        # Both positive after commission
        if adj_odds1.is_plus and adj_odds2.is_plus:
            return True
        
        # Both negative after commission  
        if not adj_odds1.is_plus and not adj_odds2.is_plus:
            return False
        
        # One positive, one negative after commission
        if adj_odds1.is_plus and not adj_odds2.is_plus:
            return abs(adj_odds1.adjusted_odds) >= abs(adj_odds2.adjusted_odds)
        elif not adj_odds1.is_plus and adj_odds2.is_plus:
            return abs(adj_odds2.adjusted_odds) >= abs(adj_odds1.adjusted_odds)
        
        return False
    
    def calculate_arbitrage_bet_sizing(self, odds1: int, odds2: int, 
                                     is_prop1: bool = False, is_prop2: bool = False) -> Tuple[float, float, float]:
        """
        Calculate exact bet sizing for arbitrage opportunity using precise math
        
        Strategy:
        1. Bet base amount on the MORE FAVORABLE odds (regardless of sign)
        2. Calculate EXACT stake needed on less favorable odds to match total payout precisely
        3. Account for commission on all winnings with high precision
        
        Args:
            odds1: First odds
            odds2: Second odds
            is_prop1: If True, first bet is a player prop (0% commission)
            is_prop2: If True, second bet is a player prop (0% commission)
        
        Returns: (stake_on_odds1, stake_on_odds2, guaranteed_profit)
        """
        from decimal import Decimal, getcontext
        # Use high precision decimal arithmetic to avoid floating point errors
        getcontext().prec = 50
        
        # Get commission rates
        commission_rate1 = self.player_prop_commission_rate if is_prop1 else self.main_market_commission_rate
        commission_rate2 = self.player_prop_commission_rate if is_prop2 else self.main_market_commission_rate
        
        # Select the appropriate base bet amount (use prop amount if either is a prop)
        if is_prop1 or is_prop2:
            base_bet = Decimal(str(self.player_prop_base_bet_amount))
        else:
            base_bet = Decimal(str(self.base_bet_amount))
        
        # Apply commission to both odds
        adj_odds1 = self.apply_commission_adjustment(odds1, commission_rate1)
        adj_odds2 = self.apply_commission_adjustment(odds2, commission_rate2)
        
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
            better_commission_rate = commission_rate1
            worse_commission_rate = commission_rate2
        else:
            # odds2 is more favorable
            better_odds_original = odds2
            better_odds_adj = adj_odds2
            worse_odds_original = odds1
            worse_odds_adj = adj_odds1
            better_is_first = False
            better_commission_rate = commission_rate2
            worse_commission_rate = commission_rate1
        
        # Step 1: Bet exactly base amount on the more favorable odds
        better_bet = base_bet
        
        # Step 2: Calculate EXACT target payout from the base bet
        if better_odds_original > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            gross_winnings = better_bet * (Decimal(str(better_odds_original)) / Decimal('100'))
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            gross_winnings = better_bet * (Decimal('100') / Decimal(str(abs(better_odds_original))))
        
        commission = gross_winnings * Decimal(str(better_commission_rate))
        net_winnings = gross_winnings - commission
        target_payout = better_bet + net_winnings
        
        # Step 3: Calculate EXACT stake needed on worse odds to achieve target payout
        # We need: worse_bet + worse_net_winnings = target_payout
        # Where: worse_net_winnings = worse_gross_winnings * (1 - commission_rate)
        
        commission_multiplier = Decimal('1') - Decimal(str(worse_commission_rate))
        
        if worse_odds_original > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            # target_payout = worse_bet + (worse_bet * (odds/100) * commission_multiplier)
            # target_payout = worse_bet * (1 + (odds/100) * commission_multiplier)
            multiplier = Decimal('1') + (Decimal(str(worse_odds_original)) / Decimal('100')) * commission_multiplier
            worse_bet = target_payout / multiplier
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            # target_payout = worse_bet + (worse_bet * (100/abs(odds)) * commission_multiplier)
            # target_payout = worse_bet * (1 + (100/abs(odds)) * commission_multiplier)
            multiplier = Decimal('1') + (Decimal('100') / Decimal(str(abs(worse_odds_original)))) * commission_multiplier
            worse_bet = target_payout / multiplier
        
        # Step 4: Calculate guaranteed profit
        total_investment = better_bet + worse_bet
        guaranteed_profit = target_payout - total_investment
        
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
    
    def _calculate_detailed_sizing_for_arbitrage(self, odds: int, stake: float, 
                                                is_player_prop: bool = False) -> BetSizingResult:
        """
        Calculate detailed sizing information for a specific odds/stake combination in arbitrage
        Uses ORIGINAL odds for the actual bet calculations (since that's what we bet at)
        
        Args:
            odds: The odds
            stake: The stake amount
            is_player_prop: If True, use 0% commission
        """
        commission_rate = self.player_prop_commission_rate if is_player_prop else self.main_market_commission_rate
        
        if odds > 0:
            # Positive odds: gross_winnings = stake * (odds/100)
            gross_winnings = stake * (odds / 100.0)
            commission = gross_winnings * commission_rate
            net_winnings = gross_winnings - commission
            total_return = stake + net_winnings
            effective_odds = net_winnings / stake * 100 if stake > 0 else 0
        else:
            # Negative odds: gross_winnings = stake * (100/abs(odds))
            gross_winnings = stake * (100 / abs(odds))
            commission = gross_winnings * commission_rate
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
    
    def analyze_opposing_opportunities(self, opp1: HighWagerOpportunity, 
                                     opp2: HighWagerOpportunity) -> ArbitrageOpportunity:
        """Analyze two opposing opportunities for potential arbitrage"""
        
        # Check if these are player props
        is_prop1 = opp1.is_player_prop
        is_prop2 = opp2.is_player_prop
        
        # Verify they are actually opposing (same market, same line, opposite sides)
        if not self._are_opposing_opportunities(opp1, opp2):
            raise ValueError("Opportunities are not on opposing sides of the same market")
        
        # Get the odds we would bet at (our proposed odds)
        odds1 = opp1.our_proposed_odds
        odds2 = opp2.our_proposed_odds
        
        # Check if this is an arbitrage opportunity (considering commission rates)
        is_arbitrage = self.is_arbitrage_opportunity(odds1, odds2, is_prop1, is_prop2)
        
        if is_arbitrage:
            # Calculate exact arbitrage bet sizing using true arbitrage logic
            stake1, stake2, profit = self.calculate_arbitrage_bet_sizing(odds1, odds2, is_prop1, is_prop2)
            
            # Calculate detailed sizing for each side
            sizing1 = self._calculate_detailed_sizing_for_arbitrage(odds1, stake1, is_prop1)
            sizing2 = self._calculate_detailed_sizing_for_arbitrage(odds2, stake2, is_prop2)
            
            recommendation = "bet_both"
        else:
            # Not arbitrage - calculate individual sizings and recommend larger one
            sizing1 = self.calculate_bet_sizing(odds1, is_prop1)
            sizing2 = self.calculate_bet_sizing(odds2, is_prop2)
            
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
        
        # Calculate bet sizing with correct commission rate
        sizing = self.calculate_bet_sizing(
            opportunity.our_proposed_odds, 
            is_player_prop=opportunity.is_player_prop
        )
        
        # Determine recommendation
        if sizing.expected_net_winnings > 0:
            recommendation = "bet"
            commission_note = " (commission-free)" if opportunity.is_player_prop else " (after 1% commission)"
            reason = f"Positive expected value: ${sizing.expected_net_winnings:.2f} net winnings{commission_note}"
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
            if opp.market_type in ['spread', 'total', 'totals']:
                if opp.market_type in ['total', 'totals']:
                    # FIXED: For totals, extract just the number to group Over/Under together
                    # Extract number from line_info like "Under 50" or "Over 50" → "50"
                    import re
                    numbers = re.findall(r'\d+(?:\.\d+)?', opp.line_info)
                    if numbers:
                        line_value = numbers[0]  # Use just the number (50)
                        # For player props, include player_id in key to separate different players
                        if opp.is_player_prop:
                            market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:{line_value}:player_{opp.player_id}"
                        else:
                            market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:{line_value}"
                    else:
                        # Fallback if regex fails
                        if opp.is_player_prop:
                            market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:player_{opp.player_id}"
                        else:
                            market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}"
                else:
                    # For spreads, keep existing logic (different spreads ARE different markets)
                    if opp.is_player_prop:
                        market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:{opp.line_info}:player_{opp.player_id}"
                    else:
                        market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:{opp.line_info}"
            else:
                # For moneylines, no line info needed
                if opp.is_player_prop:
                    market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}:player_{opp.player_id}"
                else:
                    market_key = f"{opp.event_id}:{opp.market_id}:{opp.market_type}"
            
            if market_key not in markets:
                markets[market_key] = []
            
            markets[market_key].append(opp)
            
            # Enhanced logging to verify grouping
            prop_label = "🏀 PLAYER PROP" if opp.is_player_prop else "📊 MAIN MARKET"
            logger.debug(f"🔑 {prop_label} Grouped opportunity: {opp.event_name} | {opp.market_type} | {opp.large_bet_side} → Market key: {market_key}")
        
        # Log final grouping summary
        for market_key, opps in markets.items():
            prop_indicators = ["🏀" if o.is_player_prop else "📊" for o in opps]
            logger.info(f"📊 Market {market_key}: {len(opps)} opportunities - {list(zip(prop_indicators, [f'{o.large_bet_side}' for o in opps]))}")
        
        return markets

    def _are_opposing_opportunities(self, opp1: HighWagerOpportunity, opp2: HighWagerOpportunity) -> bool:
        """Check if two opportunities are on opposing sides of the same market"""
        
        # Basic checks
        same_event = opp1.event_id == opp2.event_id
        same_market = opp1.market_id == opp2.market_id
        same_type = opp1.market_type == opp2.market_type
        opposite_sides = opp1.large_bet_side != opp2.large_bet_side
        
        # For player props, must be the same player
        if opp1.is_player_prop or opp2.is_player_prop:
            same_player = opp1.player_id == opp2.player_id
            return same_event and same_market and same_type and opposite_sides and same_player
        
        return same_event and same_market and same_type and opposite_sides
    
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