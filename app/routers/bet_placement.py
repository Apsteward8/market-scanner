#!/usr/bin/env python3
"""
Bet Placement Router
API endpoints for testing and using the high wager bet placement service
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging
import asyncio

from app.services.high_wager_bet_placement_service import high_wager_bet_placement_service
from app.services.market_scanning_service import market_scanning_service
from app.services.high_wager_arbitrage_service import high_wager_arbitrage_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/test-balance-integration", response_model=Dict[str, Any])
async def test_balance_integration():
    """Test the balance checking integration with ProphetX service"""
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info("🧪 Testing balance integration...")
        
        # Test get_account_balance method
        balance_result = await prophetx_service.get_account_balance()
        
        if balance_result.get("success"):
            balance_data = balance_result["data"]
            
            # Test check_sufficient_funds method with a small amount
            funds_check = await prophetx_service.check_sufficient_funds(50.0, 10.0)
            
            return {
                "success": True,
                "message": "Balance integration test successful",
                "data": {
                    "balance_check": {
                        "total_balance": balance_data["total"],
                        "available_balance": balance_data["available"],
                        "unmatched_wagers": balance_data["unmatched_wager_balance"],
                        "retrieved_at": balance_data["retrieved_at"]
                    },
                    "funds_check": {
                        "sufficient_for_50_dollar_bet": funds_check["sufficient_funds"],
                        "remaining_after_bet": funds_check.get("remaining_after_wager"),
                        "shortfall": funds_check.get("shortfall", 0)
                    },
                    "integration_status": "✅ Both get_account_balance() and check_sufficient_funds() working"
                }
            }
        else:
            return {
                "success": False,
                "message": "Balance integration test failed",
                "data": {
                    "error": balance_result.get("error"),
                    "integration_status": "❌ get_account_balance() method failed",
                    "possible_issues": [
                        "Missing balance methods in ProphetX service",
                        "Authentication issues",
                        "ProphetX API endpoint not available"
                    ]
                }
            }
        
    except AttributeError as e:
        if "get_account_balance" in str(e):
            return {
                "success": False,
                "message": "Balance methods not found in ProphetX service",
                "data": {
                    "error": str(e),
                    "solution": "Add the balance methods to your ProphetX service using the integration instructions",
                    "missing_methods": ["get_account_balance", "check_sufficient_funds"]
                }
            }
        else:
            raise
    
    except Exception as e:
        logger.error(f"Balance integration test error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Balance integration test failed: {str(e)}")

@router.post("/set-dry-run-mode", response_model=Dict[str, Any])
async def set_dry_run_mode(enabled: bool = True):
    """Enable/disable dry run mode for testing bet placement without real money"""
    try:
        high_wager_bet_placement_service.set_dry_run_mode(enabled)
        
        return {
            "success": True,
            "message": f"Dry run mode {'enabled' if enabled else 'disabled'}",
            "data": {
                "dry_run_mode": enabled,
                "warning": "Bets will be simulated only" if enabled else "Bets will use REAL MONEY"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting dry run mode: {str(e)}")

@router.post("/test-single-bet-placement", response_model=Dict[str, Any])
async def test_single_bet_placement():
    """Test placing a single bet with the first available opportunity"""
    try:
        logger.info("🧪 Testing single bet placement...")
        
        # Get opportunities
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        if not opportunities:
            return {
                "success": False,
                "message": "No opportunities found for testing",
                "data": {"opportunities_scanned": 0}
            }
        
        # Analyze first opportunity
        betting_decisions = high_wager_arbitrage_service.detect_conflicts_and_arbitrage(opportunities[:1])
        
        if not betting_decisions:
            return {
                "success": False, 
                "message": "No betting decisions generated",
                "data": {"opportunities_found": len(opportunities)}
            }
        
        decision = betting_decisions[0]
        
        if decision["type"] != "single_opportunity" or decision["action"] != "bet":
            return {
                "success": False,
                "message": f"First opportunity not suitable for single bet: {decision['action']}",
                "data": {"decision_type": decision["type"], "action": decision["action"]}
            }
        
        # Place the bet
        logger.info(f"🎯 Placing test bet for: {decision['analysis'].opportunity.event_name}")
        result = await high_wager_bet_placement_service.place_single_opportunity(decision)
        
        return {
            "success": result.success,
            "message": "Single bet placement test complete",
            "data": {
                "bet_result": {
                    "success": result.success,
                    "bet_id": result.bet_id,
                    "external_id": result.external_id,
                    "error": result.error,
                    "stake": result.actual_stake,
                    "balance_before": result.balance_before,
                    "balance_after": result.balance_after,
                    "balance_verified": result.balance_verified,
                    "placement_duration_ms": result.placement_duration_ms
                },
                "bet_details": {
                    "event": result.request.event_name if result.request else None,
                    "side": result.request.side if result.request else None,
                    "odds": result.request.odds if result.request else None,
                    "strategy": result.request.strategy_explanation if result.request else None
                } if result.request else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error in single bet test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Single bet test failed: {str(e)}")

@router.post("/test-arbitrage-placement", response_model=Dict[str, Any])
async def test_arbitrage_placement():
    """Test placing an arbitrage pair with the first available arbitrage opportunity"""
    try:
        logger.info("🧪 Testing arbitrage pair placement...")
        
        # Get opportunities
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        if not opportunities:
            return {
                "success": False,
                "message": "No opportunities found for testing",
                "data": {"opportunities_scanned": 0}
            }
        
        # Analyze for arbitrage
        betting_decisions = high_wager_arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
        
        # Find first arbitrage opportunity
        arbitrage_decision = None
        for decision in betting_decisions:
            if (decision["type"] == "opposing_opportunities" and 
                decision["action"] == "bet_both"):
                arbitrage_decision = decision
                break
        
        if not arbitrage_decision:
            return {
                "success": False,
                "message": "No arbitrage opportunities found for testing",
                "data": {
                    "total_decisions": len(betting_decisions),
                    "decision_types": [d["type"] for d in betting_decisions]
                }
            }
        
        # Place the arbitrage pair
        logger.info("🎯 Placing test arbitrage pair...")
        result = await high_wager_bet_placement_service.place_arbitrage_pair(arbitrage_decision)
        
        return {
            "success": result.success,
            "message": "Arbitrage placement test complete",
            "data": {
                "arbitrage_result": {
                    "success": result.success,
                    "both_placed": result.both_placed,
                    "total_stake": result.total_stake,
                    "guaranteed_profit": result.guaranteed_profit,
                    "error": result.error,
                    "rollback_attempted": result.rollback_attempted,
                    "rollback_success": result.rollback_success
                },
                "bet_1": {
                    "success": result.bet_1_result.success,
                    "bet_id": result.bet_1_result.bet_id,
                    "stake": result.bet_1_result.actual_stake,
                    "error": result.bet_1_result.error
                },
                "bet_2": {
                    "success": result.bet_2_result.success,
                    "bet_id": result.bet_2_result.bet_id,
                    "stake": result.bet_2_result.actual_stake,
                    "error": result.bet_2_result.error
                },
                "profit_analysis": {
                    "guaranteed_profit": result.guaranteed_profit,
                    "total_investment": result.total_stake,
                    "profit_margin": (result.guaranteed_profit / result.total_stake * 100) if result.total_stake > 0 else 0
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in arbitrage test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Arbitrage test failed: {str(e)}")

@router.post("/place-all-opportunities", response_model=Dict[str, Any])
async def place_all_opportunities():
    """
    Scan for opportunities and place all recommended bets
    
    This is the main endpoint for production use
    """
    try:
        logger.info("🚀 Starting comprehensive bet placement...")
        
        # Get opportunities
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        if not opportunities:
            return {
                "success": True,
                "message": "No opportunities found",
                "data": {
                    "opportunities_scanned": 0,
                    "bets_placed": 0
                }
            }
        
        # Analyze for conflicts and arbitrage
        betting_decisions = high_wager_arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
        
        # Process each decision
        results = {
            "single_bets": [],
            "arbitrage_pairs": [],
            "skipped": []
        }
        
        for decision in betting_decisions:
            try:
                if decision["type"] == "single_opportunity" and decision["action"] == "bet":
                    # Place single bet
                    result = await high_wager_bet_placement_service.place_single_opportunity(decision)
                    results["single_bets"].append({
                        "opportunity_id": decision["analysis"].opportunity.event_name,
                        "success": result.success,
                        "bet_id": result.bet_id,
                        "stake": result.actual_stake,
                        "error": result.error
                    })
                
                elif decision["type"] == "opposing_opportunities" and decision["action"] == "bet_both":
                    # Place arbitrage pair
                    result = await high_wager_bet_placement_service.place_arbitrage_pair(decision)
                    results["arbitrage_pairs"].append({
                        "event": decision["analysis"].opportunity_1.event_name,
                        "success": result.success,
                        "both_placed": result.both_placed,
                        "total_stake": result.total_stake,
                        "guaranteed_profit": result.guaranteed_profit,
                        "error": result.error
                    })
                
                else:
                    # Skipped opportunity
                    results["skipped"].append({
                        "type": decision["type"],
                        "action": decision["action"],
                        "reason": decision.get("analysis", {}).get("reason", "Not recommended")
                    })
                
                # Small delay between bets
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing decision: {e}")
                results["skipped"].append({
                    "type": decision["type"],
                    "error": str(e)
                })
        
        # Get summary
        summary = high_wager_bet_placement_service.get_placement_summary()
        
        return {
            "success": True,
            "message": f"Bet placement complete: {summary['successful_bets']} placed, {summary['failed_bets']} failed",
            "data": {
                "opportunities_analyzed": len(opportunities),
                "decisions_processed": len(betting_decisions),
                "results": results,
                "summary": summary
            }
        }
        
    except Exception as e:
        logger.error(f"Error in comprehensive placement: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comprehensive placement failed: {str(e)}")

@router.get("/placement-summary", response_model=Dict[str, Any])
async def get_placement_summary():
    """Get summary of all bet placements made by the service"""
    try:
        summary = high_wager_bet_placement_service.get_placement_summary()
        
        return {
            "success": True,
            "message": "Placement summary retrieved",
            "data": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting summary: {str(e)}")

@router.get("/placed-bets", response_model=Dict[str, Any])
async def get_placed_bets():
    """Get details of all placed bets"""
    try:
        placed_bets = []
        
        for bet_id, result in high_wager_bet_placement_service.placed_bets.items():
            placed_bets.append({
                "bet_id": bet_id,
                "success": result.success,
                "prophetx_bet_id": result.prophetx_bet_id,
                "external_id": result.external_id,
                "stake": result.actual_stake,
                "status": result.status,
                "placed_at": result.placed_at.isoformat() if result.placed_at else None,
                "event_name": result.request.event_name if result.request else None,
                "side": result.request.side if result.request else None,
                "odds": result.request.odds if result.request else None,
                "bet_type": result.request.bet_type if result.request else None,
                "error": result.error
            })
        
        arbitrage_pairs = []
        for pair_id, pair_result in high_wager_bet_placement_service.arbitrage_pairs.items():
            arbitrage_pairs.append({
                "pair_id": pair_id,
                "success": pair_result.success,
                "both_placed": pair_result.both_placed,
                "total_stake": pair_result.total_stake,
                "guaranteed_profit": pair_result.guaranteed_profit,
                "bet_1_id": pair_result.bet_1_result.bet_id,
                "bet_2_id": pair_result.bet_2_result.bet_id,
                "error": pair_result.error
            })
        
        return {
            "success": True,
            "message": "Placed bets retrieved",
            "data": {
                "single_bets": placed_bets,
                "arbitrage_pairs": arbitrage_pairs,
                "total_bets": len(placed_bets),
                "total_arbitrage_pairs": len(arbitrage_pairs)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting placed bets: {str(e)}")