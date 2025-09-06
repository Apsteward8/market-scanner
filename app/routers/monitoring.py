#!/usr/bin/env python3
"""
High Wager Monitoring Router
API endpoints for monitoring and updating high wager opportunities
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/start", response_model=Dict[str, Any])
async def start_monitoring():
    """
    Start the high wager monitoring workflow
    
    This endpoint:
    1. Places initial bets using the existing place-all-opportunities logic
    2. Starts a monitoring loop that scans for opportunities every minute
    3. Compares current wagers with new recommendations
    4. Detects differences that need to be updated
    
    **This is the main endpoint to start your complete monitoring workflow.**
    """
    try:
        # Import services
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        from app.services.market_scanning_service import market_scanning_service
        from app.services.high_wager_arbitrage_service import high_wager_arbitrage_service
        from app.services.high_wager_bet_placement_service import high_wager_bet_placement_service
        from app.services.prophetx_service import prophetx_service
        
        # Initialize monitoring service
        high_wager_monitoring_service.initialize_services(
            market_scanning_service,
            high_wager_arbitrage_service,
            high_wager_bet_placement_service,
            prophetx_service
        )
        
        # Start monitoring
        result = await high_wager_monitoring_service.start_monitoring()
        
        return {
            "success": result["success"],
            "message": result["message"],
            "data": result.get("data"),
            "workflow_description": {
                "step_1": "Place initial bets via place-all-opportunities",
                "step_2": "Start monitoring loop (every 60 seconds)",
                "step_3": "Compare current wagers vs new scan results",
                "step_4": "Detect differences requiring updates",
                "step_5": "Log findings (updates to be implemented next)"
            }
        }
        
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error starting monitoring: {str(e)}")

@router.post("/stop", response_model=Dict[str, Any])
async def stop_monitoring():
    """
    Stop the high wager monitoring loop
    
    This stops the monitoring loop but does not cancel existing bets.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        result = await high_wager_monitoring_service.stop_monitoring()
        
        return {
            "success": result["success"],
            "message": result["message"],
            "data": result.get("data")
        }
        
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error stopping monitoring: {str(e)}")

@router.get("/status", response_model=Dict[str, Any])
async def get_monitoring_status():
    """
    Get current monitoring status
    
    Shows:
    - Whether monitoring is active
    - Number of monitoring cycles completed
    - Number of tracked wagers
    - Last scan time
    - Settings
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        status = high_wager_monitoring_service.get_monitoring_status()
        
        return {
            "success": True,
            "message": "Monitoring status retrieved",
            "data": status
        }
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting monitoring status: {str(e)}")

@router.get("/tracked-wagers", response_model=Dict[str, Any])
async def get_tracked_wagers():
    """
    Get all currently tracked wagers
    
    Shows details of all wagers we're monitoring including:
    - External ID, line ID, event details
    - Current odds and stakes
    - Status and placement time
    - Opportunity context
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        tracked_wagers = {}
        
        for external_id, wager in high_wager_monitoring_service.tracked_wagers.items():
            tracked_wagers[external_id] = {
                "external_id": wager.external_id,
                "line_id": wager.line_id,
                "event_id": wager.event_id,
                "market_id": wager.market_id,
                "market_type": wager.market_type,
                "side": wager.side,
                "odds": wager.odds,
                "stake": wager.stake,
                "status": wager.status,
                "placed_at": wager.placed_at.isoformat(),
                "last_updated": wager.last_updated.isoformat(),
                "large_bet_combined_size": wager.large_bet_combined_size,
                "opportunity_type": wager.opportunity_type,
                "arbitrage_pair_id": wager.arbitrage_pair_id
            }
        
        return {
            "success": True,
            "message": f"Retrieved {len(tracked_wagers)} tracked wagers",
            "data": {
                "total_tracked": len(tracked_wagers),
                "wagers": tracked_wagers
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting tracked wagers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting tracked wagers: {str(e)}")

@router.get("/current-opportunities", response_model=Dict[str, Any])
async def get_current_opportunities():
    """
    Get current opportunities from the latest scan
    
    This runs the scan-opportunities endpoint and shows what the
    monitoring service sees as current recommendations.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Get current opportunities using the monitoring service's logic
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        
        formatted_opportunities = []
        for opp in current_opportunities:
            formatted_opportunities.append({
                "event_id": opp.event_id,
                "market_id": opp.market_id,
                "market_type": opp.market_type,
                "side": opp.side,
                "recommended_odds": opp.recommended_odds,
                "recommended_stake": opp.recommended_stake,
                "large_bet_combined_size": opp.large_bet_combined_size,
                "line_id": opp.line_id,
                "opportunity_type": opp.opportunity_type,
                "arbitrage_pair_id": opp.arbitrage_pair_id
            })
        
        return {
            "success": True,
            "message": f"Retrieved {len(current_opportunities)} current opportunities",
            "data": {
                "total_opportunities": len(current_opportunities),
                "opportunities": formatted_opportunities,
                "scan_time": high_wager_monitoring_service.last_scan_time.isoformat() if high_wager_monitoring_service.last_scan_time else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting current opportunities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting current opportunities: {str(e)}")

@router.get("/differences", response_model=Dict[str, Any])
async def get_current_differences():
    """
    Compare current wagers vs current opportunities and show differences
    
    This is the core comparison logic that detects what needs to be updated.
    Shows:
    - Odds changes
    - Stake changes  
    - New opportunities
    - Opportunities to remove
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Get current opportunities
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        
        # Detect differences
        differences = await high_wager_monitoring_service._detect_wager_differences(current_opportunities)
        
        formatted_differences = []
        for diff in differences:
            formatted_differences.append({
                "line_id": diff.line_id,
                "event_id": diff.event_id,
                "market_id": diff.market_id,
                "market_type": diff.market_type,
                "side": diff.side,
                "current_odds": diff.current_odds,
                "current_stake": diff.current_stake,
                "current_status": diff.current_status,
                "recommended_odds": diff.recommended_odds,
                "recommended_stake": diff.recommended_stake,
                "difference_type": diff.difference_type,
                "action_needed": diff.action_needed,
                "reason": diff.reason
            })
        
        return {
            "success": True,
            "message": f"Detected {len(differences)} differences",
            "data": {
                "total_differences": len(differences),
                "differences": formatted_differences,
                "summary": {
                    "odds_changes": len([d for d in differences if d.difference_type == "odds_change"]),
                    "stake_changes": len([d for d in differences if d.difference_type == "stake_change"]),
                    "new_opportunities": len([d for d in differences if d.difference_type == "new_opportunity"]),
                    "remove_opportunities": len([d for d in differences if d.difference_type == "remove_opportunity"])
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting differences: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting differences: {str(e)}")

@router.post("/test-cycle", response_model=Dict[str, Any])
async def test_monitoring_cycle():
    """
    Run a single monitoring cycle for testing
    
    This runs one iteration of the monitoring loop without starting
    the continuous monitoring. Useful for debugging.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Run one monitoring cycle (no service initialization needed)
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        differences = await high_wager_monitoring_service._detect_wager_differences(current_opportunities)
        await high_wager_monitoring_service._log_monitoring_results(current_opportunities, differences)
        
        return {
            "success": True,
            "message": "Test monitoring cycle complete",
            "data": {
                "current_opportunities": len(current_opportunities),
                "tracked_wagers": len(high_wager_monitoring_service.tracked_wagers),
                "differences_detected": len(differences),
                "differences": [
                    {
                        "line_id": d.line_id[:12] + "...",
                        "type": d.difference_type,
                        "action": d.action_needed,
                        "reason": d.reason
                    }
                    for d in differences
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error in test cycle: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in test cycle: {str(e)}")

@router.post("/settings/monitoring-interval", response_model=Dict[str, Any])
async def update_monitoring_interval(interval_seconds: int):
    """
    Update the monitoring interval
    
    Default is 60 seconds (1 minute). You can adjust this for testing
    or different monitoring frequencies.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        if interval_seconds < 10:
            raise ValueError("Monitoring interval must be at least 10 seconds")
        
        high_wager_monitoring_service.monitoring_interval_seconds = interval_seconds
        
        return {
            "success": True,
            "message": f"Monitoring interval updated to {interval_seconds} seconds",
            "data": {
                "new_interval_seconds": interval_seconds,
                "warning": "Change takes effect on next monitoring cycle" if high_wager_monitoring_service.monitoring_active else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error updating monitoring interval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating monitoring interval: {str(e)}")

@router.post("/settings/max-exposure", response_model=Dict[str, Any])
async def update_max_exposure_multiplier(multiplier: float):
    """
    Update the maximum exposure multiplier
    
    Default is 3.0 (max 3x recommended amount per line).
    For example, if recommended stake is $100, max exposure would be $300.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        if multiplier < 1.0 or multiplier > 10.0:
            raise ValueError("Exposure multiplier must be between 1.0 and 10.0")
        
        high_wager_monitoring_service.max_exposure_multiplier = multiplier
        
        return {
            "success": True,
            "message": f"Max exposure multiplier updated to {multiplier}x",
            "data": {
                "new_multiplier": multiplier,
                "explanation": f"Maximum stake per line will be {multiplier}x the recommended amount"
            }
        }
        
    except Exception as e:
        logger.error(f"Error updating max exposure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating max exposure: {str(e)}")