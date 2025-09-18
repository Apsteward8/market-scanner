#!/usr/bin/env python3
"""
Bet Placement Router - ENHANCED WITH CANCELLATION ENDPOINTS
API endpoints for testing and using the high wager bet placement service
"""

import uuid
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
                        
                        # FIXED: Better unique external ID generation
                        wager_counter += 1
                        timestamp_ms = int(time.time() * 1000)
                        unique_suffix = uuid.uuid4().hex[:8]
                        
                        external_id = f"single_{opportunity.event_id}_{opportunity.line_id[:8]}_{timestamp_ms}_{wager_counter:04d}_{unique_suffix}"
                        
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
                        
                        # FIXED: Better unique external IDs for arbitrage pairs
                        wager_counter += 1
                        base_timestamp_ms = int(time.time() * 1000)
                        pair_uuid = str(uuid.uuid4()).hex[:8]
                        
                        pair_base = f"arb_{opp1.event_id}_{base_timestamp_ms}_{wager_counter:04d}_{pair_uuid}"
                        external_id_1 = f"{pair_base}_bet1_{uuid.uuid4().hex[:6]}"
                        
                        wager_counter += 1
                        external_id_2 = f"{pair_base}_bet2_{uuid.uuid4().hex[:6]}"
                        
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

# ============================================================================
# NEW CANCELLATION ENDPOINTS
# ============================================================================

@router.post("/cancel-wager", response_model=Dict[str, Any])
async def cancel_single_wager(external_id: str, wager_id: str):
    """
    Cancel a single wager
    
    Args:
        external_id: External ID used when placing the wager
        wager_id: ProphetX wager ID returned when wager was placed
    """
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info(f"🗑️ Manual cancellation request: external_id={external_id}, wager_id={wager_id}")
        
        result = await prophetx_service.cancel_wager(external_id, wager_id)
        
        return {
            "success": result["success"],
            "message": "Wager cancellation attempt complete",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error in cancel wager endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {str(e)}")

@router.post("/cancel-multiple-wagers", response_model=Dict[str, Any])
async def cancel_multiple_wagers(wagers: List[Dict[str, str]]):
    """
    Cancel multiple wagers in batch
    
    Args:
        wagers: List of {"external_id": "...", "wager_id": "..."} objects
    """
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info(f"🗑️ Batch cancellation request for {len(wagers)} wagers")
        
        result = await prophetx_service.cancel_multiple_wagers(wagers)
        
        return {
            "success": result["success"],
            "message": f"Batch cancellation complete: {len(wagers)} wagers processed",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error in batch cancel endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch cancellation failed: {str(e)}")

@router.post("/cancel-all-wagers", response_model=Dict[str, Any])
async def cancel_all_wagers(confirm: bool = False):
    """
    Cancel ALL active wagers - USE WITH EXTREME CAUTION!
    
    Args:
        confirm: Must be True to proceed (safety check)
    """
    try:
        if not confirm:
            return {
                "success": False,
                "message": "Cancellation not confirmed",
                "warning": "This endpoint cancels ALL your active wagers. Set confirm=true to proceed.",
                "data": None
            }
        
        from app.services.prophetx_service import prophetx_service
        
        logger.warning("🚨 CANCEL ALL WAGERS requested - proceeding with confirmation")
        
        result = await prophetx_service.cancel_all_wagers()
        
        return {
            "success": result["success"],
            "message": "Cancel all wagers attempt complete",
            "data": result,
            "warning": "ALL WAGERS WERE CANCELLED" if result["success"] else "Cancellation attempt failed"
        }
        
    except Exception as e:
        logger.error(f"Error in cancel all endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cancel all failed: {str(e)}")

@router.post("/cancel-wagers-by-event", response_model=Dict[str, Any])
async def cancel_wagers_by_event(event_id: str):
    """
    Cancel all wagers for a specific event
    
    Args:
        event_id: Event ID to cancel wagers for
    """
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info(f"🗑️ Event cancellation request for event_id={event_id}")
        
        result = await prophetx_service.cancel_wagers_by_event(event_id)
        
        return {
            "success": result["success"],
            "message": f"Event cancellation complete for event {event_id}",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error in cancel by event endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Event cancellation failed: {str(e)}")

@router.post("/cancel-wagers-by-market", response_model=Dict[str, Any])
async def cancel_wagers_by_market(event_id: int, market_id: int):
    """
    Cancel all wagers for a specific market
    
    Args:
        event_id: Event ID (integer)
        market_id: Market ID (integer)
    """
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info(f"🗑️ Market cancellation request for event_id={event_id}, market_id={market_id}")
        
        result = await prophetx_service.cancel_wagers_by_market(event_id, market_id)
        
        return {
            "success": result["success"],
            "message": f"Market cancellation complete for market {market_id} in event {event_id}",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error in cancel by market endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Market cancellation failed: {str(e)}")

@router.get("/active-wagers", response_model=Dict[str, Any])
async def get_active_wagers():
    """Get all currently active (unmatched) wagers from ProphetX"""
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info("📋 Fetching active wagers for manual inspection")
        
        active_wagers = await prophetx_service.get_all_active_wagers()
        
        # Format for easy inspection and cancellation
        formatted_wagers = []
        for wager in active_wagers:
            formatted_wagers.append({
                "external_id": wager.get("external_id"),
                "wager_id": wager.get("id") or wager.get("wager_id"),
                "line_id": wager.get("line_id"),
                "odds": wager.get("odds"),
                "stake": wager.get("stake"),
                "status": wager.get("status"),
                "matching_status": wager.get("matching_status"),
                "created_at": wager.get("created_at"),
                "event_info": {
                    "event_id": wager.get("event_id"),
                    "market_id": wager.get("market_id")
                }
            })
        
        return {
            "success": True,
            "message": f"Retrieved {len(active_wagers)} active wagers",
            "data": {
                "total_active": len(active_wagers),
                "wagers": formatted_wagers
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting active wagers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get active wagers: {str(e)}")

# Add this new endpoint for getting tracked wagers with ProphetX IDs
@router.get("/tracked-wagers", response_model=Dict[str, Any])
async def get_tracked_wagers():
    """Get all tracked wagers from the monitoring service (includes ProphetX wager IDs)"""
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        if not hasattr(high_wager_monitoring_service, 'tracked_wagers'):
            return {
                "success": False,
                "message": "Monitoring service not initialized or no tracked wagers",
                "data": {"tracked_wagers": {}}
            }
        
        formatted_wagers = high_wager_monitoring_service.format_tracked_wagers_for_response()
        
        return {
            "success": True,
            "message": f"Retrieved {len(formatted_wagers)} tracked wagers with ProphetX IDs",
            "data": {
                "total_tracked": len(formatted_wagers),
                "tracked_wagers": formatted_wagers
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting tracked wagers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get tracked wagers: {str(e)}")

# Enhanced wager lookup with both external_id and prophetx_wager_id support  
@router.get("/wager-by-id/{wager_id}", response_model=Dict[str, Any])
async def get_wager_by_id(wager_id: str):
    """Get specific wager details by ProphetX wager ID or external ID"""
    try:
        from app.services.prophetx_service import prophetx_service
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        logger.info(f"🔍 Fetching wager details for ID={wager_id}")
        
        # First try to get from ProphetX directly
        wager = await prophetx_service.get_wager_by_id(wager_id)
        
        # Also check if it's in our tracked wagers
        tracked_wager = None
        for ext_id, tracked in high_wager_monitoring_service.tracked_wagers.items():
            if tracked.prophetx_wager_id == wager_id or tracked.external_id == wager_id:
                tracked_wager = tracked
                break
        
        if wager or tracked_wager:
            result = {
                "success": True,
                "message": f"Wager {wager_id} retrieved",
                "data": {
                    "prophetx_wager": wager,
                    "tracked_wager": {
                        "external_id": tracked_wager.external_id,
                        "prophetx_wager_id": tracked_wager.prophetx_wager_id,
                        "line_id": tracked_wager.line_id,
                        "odds": tracked_wager.odds,
                        "stake": tracked_wager.stake,
                        "status": tracked_wager.status,
                        "opportunity_type": tracked_wager.opportunity_type
                    } if tracked_wager else None,
                    "cancellation_info": {
                        "external_id": tracked_wager.external_id if tracked_wager else wager.get("external_id"),
                        "prophetx_wager_id": tracked_wager.prophetx_wager_id if tracked_wager else (wager.get("id") or wager_id),
                        "can_cancel": (tracked_wager and tracked_wager.status in ["pending", "unmatched"]) or 
                                     (wager and wager.get("matching_status") == "unmatched"),
                        "cancel_endpoint": "/betting/cancel-wager"
                    }
                }
            }
            return result
        else:
            return {
                "success": False,
                "message": f"Wager {wager_id} not found in ProphetX or tracked wagers",
                "data": None
            }
        
    except Exception as e:
        logger.error(f"Error getting wager by ID: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get wager: {str(e)}")