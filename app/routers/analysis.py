#!/usr/bin/env python3
"""
Analysis Router
FastAPI endpoints for odds validation and betting analysis
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any

from app.models.requests import OddsValidationRequest, OddsUndercutRequest
from app.models.responses import OddsValidationResponse, OddsUndercutResponse, APIResponse
from app.services.odds_validator_service import odds_validator_service

router = APIRouter()

@router.post("/odds/validate", response_model=OddsValidationResponse)
async def validate_odds(request: OddsValidationRequest):
    """
    Validate if odds are valid for ProphetX
    
    ProphetX only accepts specific odds values. This endpoint checks
    if the provided odds are in the valid odds table.
    """
    try:
        is_valid = odds_validator_service.is_valid_odd(request.odds)
        
        if is_valid:
            message = f"Odds {request.odds:+d} are valid for ProphetX"
        else:
            message = f"Odds {request.odds:+d} are NOT valid for ProphetX"
        
        return OddsValidationResponse(
            odds=request.odds,
            is_valid=is_valid,
            message=message
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating odds: {str(e)}")

@router.post("/odds/undercut", response_model=OddsUndercutResponse)
async def calculate_undercut_odds(request: OddsUndercutRequest):
    """
    Calculate undercut odds for following smart money
    
    Given original odds from a large bet, calculates the odds we should take
    to offer better odds to the market and get queue priority.
    
    **Betting Exchange Logic:**
    - Original bet -138 offers +138 to market
    - We undercut by taking -140 to offer +140 to market (better for bettors)
    - This gets us priority when action flows
    """
    try:
        undercut_odds = odds_validator_service.calculate_undercut_odds(
            request.original_odds, 
            request.undercut_amount
        )
        
        if undercut_odds is None:
            return OddsUndercutResponse(
                original_odds=request.original_odds,
                undercut_odds=None,
                explanation="No valid undercut odds found",
                profit_metrics=None
            )
        
        # Get explanation
        explanation = odds_validator_service.explain_undercut(request.original_odds, undercut_odds)
        
        # Calculate profit metrics for $1000 bet
        profit_metrics = odds_validator_service.calculate_profit_metrics(
            request.original_odds, undercut_odds, 1000.0
        )
        
        return OddsUndercutResponse(
            original_odds=request.original_odds,
            undercut_odds=undercut_odds,
            explanation=explanation,
            profit_metrics=profit_metrics
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating undercut odds: {str(e)}")

@router.get("/odds/valid-list", response_model=APIResponse)
async def get_valid_odds(
    odds_type: str = Query("all", description="Type: 'positive', 'negative', or 'all'"),
    limit: int = Query(50, description="Maximum number of odds to return")
):
    """
    Get list of valid odds for ProphetX
    
    - **odds_type**: Filter by 'positive', 'negative', or 'all' odds
    - **limit**: Maximum number of odds to return
    
    Returns the valid odds that ProphetX accepts for bet placement.
    """
    try:
        if odds_type == "positive":
            odds_list = odds_validator_service.positive_odds[:limit]
        elif odds_type == "negative":
            odds_list = odds_validator_service.negative_odds[:limit]
        else:  # all
            # Mix positive and negative, sorted by absolute value
            all_odds = sorted(odds_validator_service.VALID_ODDS, key=abs)
            odds_list = all_odds[:limit]
        
        return APIResponse(
            success=True,
            message=f"Retrieved {len(odds_list)} valid odds",
            data={
                "odds_type": odds_type,
                "count": len(odds_list),
                "odds": odds_list,
                "total_valid_odds": len(odds_validator_service.VALID_ODDS)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting valid odds: {str(e)}")

@router.get("/odds/around/{target_odds}", response_model=APIResponse)
async def get_odds_around_target(
    target_odds: int,
    count: int = Query(5, description="Number of odds to show on each side")
):
    """
    Get valid odds around a target value
    
    - **target_odds**: The target odds value
    - **count**: Number of odds to show before and after target
    
    Useful for seeing what valid odds are available near a specific value.
    """
    try:
        result = odds_validator_service.get_valid_odds_around(target_odds, count)
        
        return APIResponse(
            success=True,
            message=f"Odds around {target_odds:+d}",
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting odds around target: {str(e)}")

@router.post("/profit/calculate", response_model=APIResponse)
async def calculate_profit_metrics(
    odds: int = Query(..., description="Betting odds"),
    stake: float = Query(..., description="Stake amount in dollars"),
    bet_type: str = Query("win", description="Bet type: 'win' or 'lose'")
):
    """
    Calculate profit metrics for a bet
    
    - **odds**: The betting odds (e.g. +120, -138)
    - **stake**: Stake amount in dollars
    - **bet_type**: Calculate for 'win' or 'lose' scenario
    
    Returns detailed profit/loss calculations for the specified bet.
    """
    try:
        if not odds_validator_service.is_valid_odd(odds):
            return APIResponse(
                success=False,
                message=f"Odds {odds:+d} are not valid for ProphetX",
                data=None
            )
        
        if odds > 0:
            # Positive odds: stake * (odds / 100) = potential_win
            potential_win = stake * (odds / 100)
        else:
            # Negative odds: stake * (100 / abs(odds)) = potential_win
            potential_win = stake * (100 / abs(odds))
        
        potential_profit = potential_win - stake
        roi_percent = (potential_profit / stake) * 100 if stake > 0 else 0
        
        # Calculate loss scenario
        potential_loss = -stake
        loss_roi_percent = -100
        
        if bet_type == "win":
            result_amount = potential_profit
            result_roi = roi_percent
            scenario = "Win"
        else:  # lose
            result_amount = potential_loss
            result_roi = loss_roi_percent
            scenario = "Lose"
        
        return APIResponse(
            success=True,
            message=f"Profit calculation for {odds:+d} odds",
            data={
                "odds": odds,
                "stake": stake,
                "scenario": scenario,
                "result_amount": result_amount,
                "result_roi_percent": result_roi,
                "potential_win": potential_win,
                "potential_profit": potential_profit,
                "potential_loss": potential_loss,
                "win_roi_percent": roi_percent,
                "loss_roi_percent": loss_roi_percent,
                "break_even_win_rate": abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (100 + odds)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating profit metrics: {str(e)}")

@router.get("/strategy/explain", response_model=APIResponse)
async def explain_follow_money_strategy():
    """
    Explain the "follow the smart money" strategy
    
    Returns detailed explanation of the betting strategy, including:
    - Why large bets indicate smart money
    - How betting exchanges work
    - Why undercutting gets priority
    - Risk and reward considerations
    """
    try:
        explanation = {
            "strategy_name": "Follow the Smart Money",
            "core_concept": "Large bets often indicate sharp/informed money worth following",
            
            "betting_exchange_basics": {
                "description": "ProphetX is a peer-to-peer betting exchange",
                "how_it_works": [
                    "When someone bets -138, they offer +138 to other users",
                    "When someone bets +120, they offer -120 to other users",
                    "Users bet against each other, not the house"
                ]
            },
            
            "undercut_strategy": {
                "goal": "Get priority in the betting queue by offering better odds",
                "example": {
                    "scenario": "Someone bets $10,000 on Team A at -138",
                    "what_they_offer": "They offer +138 to the market",
                    "our_response": "We bet Team A at -140 to offer +140 to market",
                    "result": "Our +140 offer is better than their +138, so we get priority"
                }
            },
            
            "why_follow_large_bets": [
                "Large stakes suggest the bettor has an edge or inside information",
                "Sharp bettors don't risk big money on coin flips",
                "Professional betting syndicates often place large, informed bets",
                "Following smart money is a time-tested strategy"
            ],
            
            "profit_mechanism": [
                "We don't profit from 'better odds' - we accept worse odds",
                "Profit comes from being first in queue when action flows",
                "When more bettors want the same side, we get matched first",
                "We ride the wave of smart money movement"
            ],
            
            "risk_considerations": [
                "Large bets don't guarantee wins - edge doesn't mean certainty",
                "We're accepting worse odds, so we need good win rate",
                "Market movements may not always follow large bets",
                "Position sizing and bankroll management are crucial"
            ],
            
            "implementation": {
                "min_stake_threshold": "Only follow bets above $5,000 (configurable)",
                "undercut_amount": "Typically undercut by 1-2 points",
                "bet_sizing": "Bet smaller amounts to manage risk",
                "comprehensive_scanning": "Scan all markets for opportunities"
            }
        }
        
        return APIResponse(
            success=True,
            message="Follow the smart money strategy explanation",
            data=explanation
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error explaining strategy: {str(e)}")

@router.post("/odds/test-undercut-logic", response_model=APIResponse)
async def test_undercut_logic():
    """
    Test the undercut logic with various examples
    
    Returns examples showing how the undercut calculation works
    for different types of odds (positive, negative, edge cases).
    """
    try:
        test_cases = [
            {"original": 100, "description": "Edge case: +100 must cross to negative"},
            {"original": 120, "description": "Positive odds: typical underdog"},
            {"original": -110, "description": "Negative odds: typical favorite"},
            {"original": -138, "description": "Negative odds: stronger favorite"},
            {"original": 250, "description": "High positive odds: big underdog"},
            {"original": -200, "description": "Strong negative odds: heavy favorite"}
        ]
        
        results = []
        
        for case in test_cases:
            original_odds = case["original"]
            undercut_odds = odds_validator_service.calculate_undercut_odds(original_odds)
            
            if undercut_odds:
                explanation = odds_validator_service.explain_undercut(original_odds, undercut_odds)
                profit_metrics = odds_validator_service.calculate_profit_metrics(
                    original_odds, undercut_odds, 1000
                )
                
                results.append({
                    "original_odds": original_odds,
                    "undercut_odds": undercut_odds,
                    "description": case["description"],
                    "explanation": explanation,
                    "profit_for_1000_bet": profit_metrics["potential_profit"],
                    "roi_percent": profit_metrics["roi_percent"]
                })
            else:
                results.append({
                    "original_odds": original_odds,
                    "undercut_odds": None,
                    "description": case["description"],
                    "explanation": "No valid undercut found",
                    "profit_for_1000_bet": None,
                    "roi_percent": None
                })
        
        return APIResponse(
            success=True,
            message="Undercut logic test results",
            data={
                "test_cases": results,
                "key_insight": "Profit comes from queue priority, not better odds for ourselves"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing undercut logic: {str(e)}")