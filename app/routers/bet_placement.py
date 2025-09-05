#!/usr/bin/env python3
"""
Bet Placement Router
API endpoints for testing and using the high wager bet placement service
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging
import asyncio
import time

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

@router.post("/place-all-opportunities")
async def place_all_opportunities():
    """Place bets on all available high wager opportunities using batch API"""
    try:
        logger.info("🚀 Starting batch bet placement...")
        
        # LOCAL TRACKING for this endpoint only
        local_bet_results = []
        local_arbitrage_results = []
        local_successful_bets = 0
        local_failed_bets = 0
        local_total_stakes = 0.0
        
        # Get opportunities (existing logic)
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        if not opportunities:
            return {
                "success": True,
                "message": "No opportunities found",
                "data": {
                    "opportunities_analyzed": 0,
                    "decisions_processed": 0,
                    "results": {"single_bets": [], "arbitrage_pairs": [], "skipped": []},
                    "summary": {
                        "total_bets_attempted": 0,
                        "successful_bets": 0,
                        "failed_bets": 0,
                        "single_opportunities": 0,
                        "arbitrage_pairs": 0,
                        "total_stakes_placed": 0.0,
                        "success_rate": 0.0
                    }
                }
            }
        
        # Get betting decisions (existing logic)
        betting_decisions = high_wager_arbitrage_service.detect_conflicts_and_arbitrage(opportunities)
        
        # NEW: Collect all wagers first instead of placing individually
        wagers_to_place = []
        decision_map = {}  # Maps external_id to decision info for result processing
        
        # FIXED: Use a counter to ensure unique external IDs
        wager_counter = 0
        base_timestamp = int(time.time() * 1000)
        
        for decision in betting_decisions:
            try:
                if decision["type"] == "single_opportunity" and decision["action"] == "bet":
                    # Prepare single bet wager
                    analysis = decision.get("analysis")
                    if analysis and hasattr(analysis, 'opportunity') and hasattr(analysis, 'sizing'):
                        opportunity = analysis.opportunity
                        sizing = analysis.sizing
                        
                        # FIXED: Include counter and line_id for guaranteed uniqueness
                        wager_counter += 1
                        external_id = f"single_{opportunity.event_id}_{opportunity.line_id[:8]}_{base_timestamp}_{wager_counter:03d}"
                        
                        wager = {
                            "external_id": external_id,
                            "line_id": opportunity.line_id,
                            "odds": opportunity.our_proposed_odds,
                            "stake": sizing.stake_amount
                        }
                        
                        wagers_to_place.append(wager)
                        decision_map[external_id] = {
                            "type": "single",
                            "decision": decision,
                            "analysis": analysis
                        }
                
                elif decision["type"] == "opposing_opportunities" and decision["action"] == "bet_both":
                    # Prepare arbitrage pair wagers
                    analysis = decision.get("analysis")
                    if analysis and hasattr(analysis, 'opportunity_1') and hasattr(analysis, 'opportunity_2'):
                        opp1 = analysis.opportunity_1
                        opp2 = analysis.opportunity_2
                        sizing1 = analysis.bet_1_sizing
                        sizing2 = analysis.bet_2_sizing
                        
                        # FIXED: Include counter and line_ids for guaranteed uniqueness
                        wager_counter += 1
                        pair_base = f"arb_{opp1.event_id}_{base_timestamp}_{wager_counter:03d}"
                        external_id_1 = f"{pair_base}_bet1"
                        
                        wager_counter += 1
                        external_id_2 = f"{pair_base}_bet2"
                        
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
                        
                        wagers_to_place.extend([wager1, wager2])
                        decision_map[external_id_1] = {
                            "type": "arbitrage_1",
                            "pair_id": pair_base,
                            "decision": decision,
                            "analysis": analysis
                        }
                        decision_map[external_id_2] = {
                            "type": "arbitrage_2", 
                            "pair_id": pair_base,
                            "decision": decision,
                            "analysis": analysis
                        }
                        
            except Exception as e:
                logger.error(f"Error preparing wager for decision: {e}")
                continue
        
        # Check if we have any wagers to place
        if not wagers_to_place:
            logger.info("No wagers prepared for batch placement")
            return {
                "success": True,
                "message": "No wagers to place",
                "data": {
                    "opportunities_analyzed": len(opportunities),
                    "decisions_processed": len(betting_decisions),
                    "results": {"single_bets": [], "arbitrage_pairs": [], "skipped": []},
                    "summary": {
                        "total_bets_attempted": 0,
                        "successful_bets": 0,
                        "failed_bets": 0,
                        "single_opportunities": 0,
                        "arbitrage_pairs": 0,
                        "total_stakes_placed": 0.0,
                        "success_rate": 0.0
                    }
                }
            }
        
        logger.info(f"📋 Prepared {len(wagers_to_place)} wagers for batch placement")
        
        # Log a few external IDs to verify uniqueness
        logger.info(f"🔍 Sample external IDs: {[w['external_id'] for w in wagers_to_place[:5]]}")
        
        # NEW: Use batch placement instead of individual calls
        batch_result = await high_wager_bet_placement_service.prophetx_service.place_multiple_wagers(wagers_to_place)
        
        # Process batch results and map back to original structure
        results = {"single_bets": [], "arbitrage_pairs": [], "skipped": []}
        arbitrage_pairs = {}  # Group arbitrage results by pair_id
        
        success_wagers = batch_result.get("success_wagers", {})
        failed_wagers = batch_result.get("failed_wagers", {})
        
        # Process all results
        for external_id, decision_info in decision_map.items():
            try:
                if external_id in success_wagers:
                    # Successful bet
                    wager_result = success_wagers[external_id]
                    local_successful_bets += 1
                    local_total_stakes += wager_result.get("stake", 0)
                    
                    if decision_info["type"] == "single":
                        analysis = decision_info["analysis"]
                        results["single_bets"].append({
                            "event": analysis.opportunity.event_name,
                            "success": True,
                            "bet_id": wager_result["bet_id"],
                            "stake": wager_result.get("stake"),
                            "error": None
                        })
                        
                    elif decision_info["type"].startswith("arbitrage"):
                        pair_id = decision_info["pair_id"]
                        if pair_id not in arbitrage_pairs:
                            arbitrage_pairs[pair_id] = {
                                "event": decision_info["analysis"].opportunity_1.event_name,
                                "success": False,
                                "both_placed": False,
                                "total_stake": 0,
                                "guaranteed_profit": decision_info["analysis"].guaranteed_profit,
                                "bet_1_success": False,
                                "bet_2_success": False,
                                "error": None
                            }
                        
                        if decision_info["type"] == "arbitrage_1":
                            arbitrage_pairs[pair_id]["bet_1_success"] = True
                        else:
                            arbitrage_pairs[pair_id]["bet_2_success"] = True
                        
                        arbitrage_pairs[pair_id]["total_stake"] += wager_result.get("stake", 0)
                        
                elif external_id in failed_wagers:
                    # Failed bet
                    failure_result = failed_wagers[external_id]
                    local_failed_bets += 1
                    
                    if decision_info["type"] == "single":
                        analysis = decision_info["analysis"]
                        results["single_bets"].append({
                            "event": analysis.opportunity.event_name,
                            "success": False,
                            "bet_id": None,
                            "stake": failure_result.get("request", {}).get("stake"),
                            "error": failure_result.get("message", failure_result.get("error"))
                        })
                        
                    elif decision_info["type"].startswith("arbitrage"):
                        pair_id = decision_info["pair_id"]
                        if pair_id not in arbitrage_pairs:
                            arbitrage_pairs[pair_id] = {
                                "event": decision_info["analysis"].opportunity_1.event_name,
                                "success": False,
                                "both_placed": False,
                                "total_stake": 0,
                                "guaranteed_profit": decision_info["analysis"].guaranteed_profit,
                                "bet_1_success": False,
                                "bet_2_success": False,
                                "error": None
                            }
                        
                        error_msg = failure_result.get("message", failure_result.get("error"))
                        if arbitrage_pairs[pair_id]["error"]:
                            arbitrage_pairs[pair_id]["error"] += f"; {error_msg}"
                        else:
                            arbitrage_pairs[pair_id]["error"] = error_msg
                            
            except Exception as e:
                logger.error(f"Error processing result for {external_id}: {e}")
                local_failed_bets += 1
        
        # Finalize arbitrage pair results
        for pair_id, pair_data in arbitrage_pairs.items():
            pair_data["both_placed"] = pair_data["bet_1_success"] and pair_data["bet_2_success"]
            pair_data["success"] = pair_data["both_placed"]
            results["arbitrage_pairs"].append(pair_data)
        
        # Calculate summary (using existing logic)
        total_bets_attempted = local_successful_bets + local_failed_bets
        success_rate = (local_successful_bets / total_bets_attempted * 100) if total_bets_attempted > 0 else 0
        
        local_summary = {
            "total_bets_attempted": total_bets_attempted,
            "successful_bets": local_successful_bets,
            "failed_bets": local_failed_bets,
            "single_opportunities": len([r for r in results["single_bets"] if r["success"]]),
            "arbitrage_pairs": len([r for r in results["arbitrage_pairs"] if r["both_placed"]]),
            "total_stakes_placed": round(local_total_stakes, 2),
            "success_rate": round(success_rate, 1)
        }
        
        return {
            "success": True,
            "message": f"Batch placement complete: {local_successful_bets} placed, {local_failed_bets} failed",
            "data": {
                "opportunities_analyzed": len(opportunities),
                "decisions_processed": len(betting_decisions),
                "wagers_prepared": len(wagers_to_place),
                "batch_api_result": batch_result,
                "results": results,
                "summary": local_summary
            }
        }
        
    except Exception as e:
        logger.error(f"Error in batch placement endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch placement failed: {str(e)}")

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