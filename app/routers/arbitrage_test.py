#!/usr/bin/env python3
"""
Arbitrage Testing Router
Test the arbitrage logic with real examples
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging

from app.services.high_wager_arbitrage_service import high_wager_arbitrage_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/test-arbitrage-calculation", response_model=Dict[str, Any])
async def test_arbitrage_calculation():
    """Test arbitrage calculation with your Western Michigan example using corrected logic"""
    try:
        # Test the Western Michigan vs Michigan State example
        # Our strategy: bet Western Michigan +21 @ -101 AND Michigan State -21 @ +115
        
        odds1 = -102  # Western Michigan +21 (our bet)
        odds2 = 115   # Michigan State -21 (our bet) 
        
        # Check if this is arbitrage
        is_arbitrage = high_wager_arbitrage_service.is_arbitrage_opportunity(odds1, odds2)
        
        # Calculate commission-adjusted odds (FIXED for American odds format)
        adj_odds1 = high_wager_arbitrage_service.apply_commission_adjustment(odds1)
        adj_odds2 = high_wager_arbitrage_service.apply_commission_adjustment(odds2)
        
        result = {
            "example": "Western Michigan vs Michigan State -21 spread",
            "our_bet_1": {
                "side": "Western Michigan +21",
                "original_odds": odds1,
                "adjusted_odds_after_commission": adj_odds1.adjusted_odds,
                "adjusted_odds_is_plus": adj_odds1.is_plus
            },
            "our_bet_2": {
                "side": "Michigan State -21", 
                "original_odds": odds2,
                "adjusted_odds_after_commission": adj_odds2.adjusted_odds,
                "adjusted_odds_is_plus": adj_odds2.is_plus
            },
            "arbitrage_analysis": {
                "is_arbitrage": is_arbitrage,
                "arbitrage_rule": f"Mixed odds: abs({adj_odds2.adjusted_odds:.2f}) > abs({adj_odds1.adjusted_odds:.2f})",
                "rule_result": abs(adj_odds2.adjusted_odds) > abs(adj_odds1.adjusted_odds) if is_arbitrage else "Not arbitrage"
            }
        }
        
        if is_arbitrage:
            # Calculate CORRECTED arbitrage stakes using new logic
            # Bet $100 on more favorable odds, calculate matching stake on other side
            stake1, stake2, profit = high_wager_arbitrage_service.calculate_arbitrage_bet_sizing(odds1, odds2)
            
            # Calculate detailed sizing for verification
            sizing1 = high_wager_arbitrage_service._calculate_detailed_sizing_for_arbitrage(odds1, stake1)
            sizing2 = high_wager_arbitrage_service._calculate_detailed_sizing_for_arbitrage(odds2, stake2)
            
            result["corrected_arbitrage_calculation"] = {
                "strategy": "Bet $100 on more favorable odds, calculate matching stake",
                "more_favorable_side": "Michigan State -21 (+115)" if stake2 == 100.0 else "Western Michigan +21 (-101)",
                "bet_1_western_michigan": {
                    "stake": stake1,
                    "gross_winnings": sizing1.expected_gross_winnings,
                    "commission": sizing1.expected_commission,
                    "net_winnings": sizing1.expected_net_winnings,
                    "total_payout": sizing1.expected_total_return
                },
                "bet_2_michigan_state": {
                    "stake": stake2,
                    "gross_winnings": sizing2.expected_gross_winnings, 
                    "commission": sizing2.expected_commission,
                    "net_winnings": sizing2.expected_net_winnings,
                    "total_payout": sizing2.expected_total_return
                },
                "verification": {
                    "total_investment": round(stake1 + stake2, 2),
                    "payout_scenario_1": sizing1.expected_total_return,
                    "payout_scenario_2": sizing2.expected_total_return,
                    "payout_difference": abs(sizing1.expected_total_return - sizing2.expected_total_return),
                    "payouts_match": abs(sizing1.expected_total_return - sizing2.expected_total_return) < 0.01,
                    "guaranteed_profit_calculation": "payout - total_investment",
                    "guaranteed_profit": round(sizing1.expected_total_return - (stake1 + stake2), 2),
                    "profit_margin": round(((sizing1.expected_total_return - (stake1 + stake2)) / (stake1 + stake2)) * 100, 4) if (stake1 + stake2) > 0 else 0
                }
            }
            
            # Add precision verification  
            result["precision_verification"] = {
                "decimal_precision_used": "50 digits",
                "floating_point_errors_avoided": "Yes",
                "exact_payout_matching": abs(sizing1.expected_total_return - sizing2.expected_total_return) < 0.01,
                "calculation_method": "High precision decimal arithmetic for stake calculation"
            }
            
            # Verify the calculation manually
            result["manual_verification"] = {
                "explanation": f"""
                CORRECTED CALCULATION:
                1. +115 becomes +{adj_odds2.adjusted_odds:.2f} after commission (more favorable)
                2. Bet $100.00 on +115 → Payout = ${sizing2.expected_total_return:.2f}
                3. -101 becomes -{abs(adj_odds1.adjusted_odds):.2f} after commission
                4. Need ${stake1:.2f} on -101 to match ${sizing2.expected_total_return:.2f} payout
                5. Total investment = ${stake1 + stake2:.2f}
                6. Guaranteed profit = ${sizing1.expected_total_return:.2f} - ${stake1 + stake2:.2f} = ${sizing1.expected_total_return - (stake1 + stake2):.2f}
                
                PRECISION IMPROVEMENTS:
                - Used decimal arithmetic to avoid floating point errors
                - Exact payout matching within 1 cent
                - Fixed guaranteed profit calculation
                """.strip(),
                "key_fixes": [
                    "Decimal precision for exact calculations", 
                    "Guaranteed profit = payout - total_investment",
                    "Fixed rounding issues"
                ]
            }
        
        return {
            "success": True,
            "message": "Corrected arbitrage calculation test complete",
            "data": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arbitrage test failed: {str(e)}")

@router.post("/test-commission-scenarios", response_model=Dict[str, Any])
async def test_commission_scenarios():
    """Test various commission scenarios including edge cases"""
    try:
        test_cases = [
            {
                "name": "Your Western Michigan Example",
                "odds1": -101,
                "odds2": 115,
                "description": "Should be arbitrage: 111.55 vs 104.03"
            },
            {
                "name": "Both Positive (Always Arbitrage)",
                "odds1": 105,
                "odds2": 110, 
                "description": "Should be arbitrage: both positive after commission"
            },
            {
                "name": "American Odds Conversion Test",
                "odds1": 101,
                "odds2": 101,
                "description": "FIXED: +101 → 97.97 → should convert to ~-102 (not stay at 97.97)"
            },
            {
                "name": "Both Negative (Never Arbitrage)", 
                "odds1": -110,
                "odds2": -105,
                "description": "Should not be arbitrage: both negative after commission"
            },
            {
                "name": "Close Call",
                "odds1": -103,
                "odds2": 105,
                "description": "Check if 101.85 > 106.19 (should not be arbitrage)"
            }
        ]
        
        results = []
        
        for case in test_cases:
            odds1, odds2 = case["odds1"], case["odds2"]
            
            # Apply commission adjustment
            adj1 = high_wager_arbitrage_service.apply_commission_adjustment(odds1)
            adj2 = high_wager_arbitrage_service.apply_commission_adjustment(odds2)
            
            # Check arbitrage
            is_arb = high_wager_arbitrage_service.is_arbitrage_opportunity(odds1, odds2)
            
            # Calculate sizing
            sizing1 = high_wager_arbitrage_service.calculate_bet_sizing(odds1)
            sizing2 = high_wager_arbitrage_service.calculate_bet_sizing(odds2)
            
            results.append({
                "case": case["name"],
                "original_odds": [odds1, odds2],
                "adjusted_odds": [round(adj1.adjusted_odds, 2), round(adj2.adjusted_odds, 2)],
                "adjusted_odds_signs": ["++" if adj1.is_plus else "--", "++" if adj2.is_plus else "--"],
                "is_arbitrage": is_arb,
                "description": case["description"],
                "bet_sizing": {
                    "stake_1": sizing1.stake_amount,
                    "stake_2": sizing2.stake_amount,
                    "total_investment": sizing1.stake_amount + sizing2.stake_amount
                },
                "verification": {
                    "both_positive_after_commission": adj1.adjusted_odds > 0 and adj2.adjusted_odds > 0,
                    "both_negative_after_commission": adj1.adjusted_odds < 0 and adj2.adjusted_odds < 0,
                    "arbitrage_rule_check": f"abs({adj1.adjusted_odds:.2f}) vs abs({adj2.adjusted_odds:.2f})",
                    "american_odds_conversion": {
                        "odds1": f"{odds1} → {adj1.adjusted_odds:.2f} ({'positive' if adj1.is_plus else 'negative'})",
                        "odds2": f"{odds2} → {adj2.adjusted_odds:.2f} ({'positive' if adj2.is_plus else 'negative'})"
                    }
                }
            })
        
        return {
            "success": True,
            "message": "Commission scenario testing complete with FIXES", 
            "data": {
                "commission_rate": "1%",
                "test_results": results,
                "arbitrage_rules": {
                    "both_positive": "Always arbitrage",
                    "both_negative": "Never arbitrage", 
                    "mixed": "Arbitrage if abs(positive) > abs(negative) after commission"
                },
                "fixes_applied": {
                    "american_odds_conversion": "Positive odds < 100 after commission now convert to proper negative odds",
                    "example": "+101 → 97.97 → converted to ~-102 (not 97.97)",
                    "arbitrage_bet_sizing": "Now bets $100 on more favorable odds, calculates matching stake on other side"
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commission test failed: {str(e)}")

@router.post("/test-bet-sizing-logic", response_model=Dict[str, Any])
async def test_bet_sizing_logic():
    """Test the bet sizing logic for plus and minus odds"""
    try:
        test_odds = [115, -101, -110, 150, -150, 200, -200, 101]
        results = []
        
        for odds in test_odds:
            sizing = high_wager_arbitrage_service.calculate_bet_sizing(odds)
            
            # Get commission-adjusted odds to explain the strategy
            adj_odds = high_wager_arbitrage_service.apply_commission_adjustment(odds)
            
            # Verify the logic
            if adj_odds.is_plus:
                # Commission-adjusted odds are positive: should bet $100
                expected_stake = 100.0
                verification = f"Commission-adjusted odds (+{adj_odds.adjusted_odds:.2f}) are positive → Bet $100"
            else:
                # Commission-adjusted odds are negative: should bet to win ~$100 after commission  
                verification = f"Commission-adjusted odds ({adj_odds.adjusted_odds:.2f}) are negative → Bet to win $100 after commission. Net winnings: ${sizing.expected_net_winnings}"
            
            results.append({
                "original_odds": odds,
                "commission_adjusted_odds": round(adj_odds.adjusted_odds, 2),
                "adjusted_is_plus": adj_odds.is_plus,
                "strategy_explanation": f"Original {odds:+d} → Adjusted {adj_odds.adjusted_odds:+.2f} → {'Plus' if adj_odds.is_plus else 'Minus'} strategy",
                "sizing": {
                    "stake_amount": sizing.stake_amount,
                    "gross_winnings": sizing.expected_gross_winnings,
                    "commission": sizing.expected_commission,
                    "net_winnings": sizing.expected_net_winnings,
                    "total_return": sizing.expected_total_return,
                    "effective_odds": sizing.effective_odds_after_commission
                },
                "verification": verification,
                "target_achieved": (
                    abs(sizing.stake_amount - 100.0) < 0.01 if adj_odds.is_plus
                    else abs(sizing.expected_net_winnings - 100.0) < 0.50  # Within 50 cents of $100
                )
            })
        
        return {
            "success": True,
            "message": "FIXED bet sizing logic test complete",
            "data": {
                "strategy": {
                    "commission_adjusted_plus_odds": "Bet $100",
                    "commission_adjusted_minus_odds": "Bet to win $100 after 1% commission",
                    "key_improvement": "Strategy now determined by commission-adjusted odds, not original odds"
                },
                "test_results": results,
                "examples": {
                    "plus_101_case": "+101 → commission-adjusted -102.07 → Uses MINUS strategy (bet to win $100)",
                    "minus_110_case": "-110 → commission-adjusted -113.40 → Uses MINUS strategy (bet to win $100)",
                    "plus_150_case": "+150 → commission-adjusted +145.50 → Uses PLUS strategy (bet $100)"
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bet sizing test failed: {str(e)}")