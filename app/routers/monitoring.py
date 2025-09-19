#!/usr/bin/env python3
"""
High Wager Monitoring Router - Updated for API-Based Tracking
API endpoints for monitoring and updating high wager opportunities with real-time API data
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/start", response_model=Dict[str, Any])
async def start_monitoring():
    """
    Start the high wager monitoring workflow with API-based tracking
    
    This endpoint:
    1. Places initial bets using the existing place-all-opportunities logic
    2. Starts a monitoring loop that fetches current wagers from ProphetX API every minute
    3. Compares API wagers with new scan results to detect changes
    4. Executes actions (cancel, place, update) based on differences
    
    **NEW: Uses real-time API data instead of local tracking - can detect fills!**
    """
    try:
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
        
        # Start API-based monitoring
        result = await high_wager_monitoring_service.start_monitoring()
        
        return {
            "success": result["success"],
            "message": result["message"],
            "data": result.get("data"),
            "api_based_features": {
                "real_time_wager_status": "✅ Fetches wager status from ProphetX API every cycle",
                "fill_detection": "✅ Automatically detects when bets get filled",
                "accurate_position_tracking": "✅ No stale local state - always current",
                "workflow": [
                    "1. Place initial bets via place-all-opportunities",
                    "2. Start monitoring loop (every 60 seconds)",
                    "3. Fetch current wagers from ProphetX API",
                    "4. Compare API wagers vs new scan results", 
                    "5. Execute actions (cancel/place/update)",
                    "6. Detect fills and status changes automatically"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error starting API-based monitoring: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error starting monitoring: {str(e)}")

@router.post("/stop", response_model=Dict[str, Any])
async def stop_monitoring():
    """Stop the high wager monitoring loop"""
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
    Get current monitoring status with API-based tracking info
    
    Shows:
    - Whether monitoring is active
    - Number of monitoring cycles completed
    - Current wagers from API (active, filled, etc.)
    - Last API fetch time and duration
    - Settings
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        status = high_wager_monitoring_service.get_monitoring_status()
        
        return {
            "success": True,
            "message": "API-based monitoring status retrieved",
            "data": status
        }
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting monitoring status: {str(e)}")

@router.get("/current-wagers", response_model=Dict[str, Any])
async def get_current_wagers():
    """
    Get all current wagers from ProphetX API
    
    **NEW: Shows real-time wager status including fills, matching status, etc.**
    This replaces the old tracked-wagers endpoint with live API data.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        current_wagers = await high_wager_monitoring_service.get_current_wagers()
        
        return {
            "success": current_wagers["success"],
            "message": current_wagers["message"],
            "data": current_wagers["data"],
            "api_features": {
                "real_time_data": "✅ Fresh data from ProphetX API",
                "fill_detection": "✅ Shows matched_stake for filled bets",
                "status_tracking": "✅ Real matching_status from ProphetX"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting current wagers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting current wagers: {str(e)}")

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
    Compare current API wagers vs current opportunities and show differences
    
    **NEW: Uses real-time API wager data instead of stale local tracking**
    Shows:
    - Odds changes
    - Stake changes  
    - New opportunities
    - Opportunities to remove
    - Fills detected from API
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Fetch fresh wager data from API
        await high_wager_monitoring_service._fetch_current_wagers_from_api()
        
        # Get current opportunities
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        
        # Detect differences using API data
        differences = await high_wager_monitoring_service._detect_api_wager_differences(current_opportunities)
        
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
                "current_matching_status": diff.current_matching_status,
                "recommended_odds": diff.recommended_odds,
                "recommended_stake": diff.recommended_stake,
                "difference_type": diff.difference_type,
                "action_needed": diff.action_needed,
                "reason": diff.reason,
                "wager_identifiers": {
                    "external_id": diff.wager_external_id,
                    "prophetx_wager_id": diff.wager_prophetx_id
                }
            })
        
        return {
            "success": True,
            "message": f"Detected {len(differences)} differences using API data",
            "data": {
                "total_differences": len(differences),
                "differences": formatted_differences,
                "summary": {
                    "odds_changes": len([d for d in differences if d.difference_type == "odds_change"]),
                    "stake_changes": len([d for d in differences if d.difference_type == "stake_change"]),
                    "new_opportunities": len([d for d in differences if d.difference_type == "new_opportunity"]),
                    "remove_opportunities": len([d for d in differences if d.difference_type == "remove_opportunity"])
                },
                "api_based_features": {
                    "real_time_comparison": "✅ Uses fresh API wager data",
                    "fill_aware": "✅ Accounts for filled/matched stakes",
                    "status_aware": "✅ Considers current matching status"
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
    
    **NEW: Uses API-based wager fetching**
    This runs one iteration of the monitoring loop without starting
    the continuous monitoring. Shows the full API-based workflow.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        logger.info("🧪 Running test API-based monitoring cycle...")
        
        # Step 1: Fetch current wagers from API
        await high_wager_monitoring_service._fetch_current_wagers_from_api()
        
        # Step 2: Get current opportunities
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        
        # Step 3: Detect differences
        differences = await high_wager_monitoring_service._detect_api_wager_differences(current_opportunities)
        
        # Step 4: Update fill tracking from API data
        high_wager_monitoring_service._update_fill_tracking_from_api()
        
        # Get summary info
        current_wagers = high_wager_monitoring_service.current_wagers
        active_wagers = [w for w in current_wagers if w.is_active]
        filled_wagers = [w for w in current_wagers if w.is_filled]
        
        return {
            "success": True,
            "message": "Test API-based monitoring cycle complete",
            "data": {
                "api_wager_fetch": {
                    "total_wagers_fetched": len(current_wagers),
                    "system_wagers": len([w for w in current_wagers if w.is_system_bet]),
                    "active_wagers": len(active_wagers),
                    "filled_wagers": len(filled_wagers),
                    "fetch_duration": high_wager_monitoring_service.wager_fetch_duration
                },
                "opportunity_scan": {
                    "current_opportunities": len(current_opportunities)
                },
                "difference_detection": {
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
                },
                "fill_tracking": {
                    "recent_fills_detected": len(high_wager_monitoring_service.recent_fills),
                    "line_exposures": dict(high_wager_monitoring_service.line_exposure)
                },
                "anti_duplicate_note": "This test cycle doesn't apply first-cycle anti-duplicate protection. Real monitoring has additional safeguards."
            }
        }
        
    except Exception as e:
        logger.error(f"Error in test cycle: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in test cycle: {str(e)}")

@router.post("/force-api-refresh", response_model=Dict[str, Any])
async def force_api_refresh():
    """
    Force an immediate refresh of wager data from ProphetX API
    
    **NEW ENDPOINT: Manually trigger API data refresh**
    Useful after placing bets or when you want fresh data immediately.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        logger.info("🔄 Force refreshing wager data from ProphetX API...")
        
        # Fetch fresh data
        await high_wager_monitoring_service._fetch_current_wagers_from_api()
        
        # Update tracking
        high_wager_monitoring_service._update_fill_tracking_from_api()
        
        current_wagers = high_wager_monitoring_service.current_wagers
        active_wagers = [w for w in current_wagers if w.is_active]
        filled_wagers = [w for w in current_wagers if w.is_filled]
        
        return {
            "success": True,
            "message": "API data refreshed successfully",
            "data": {
                "refresh_time": high_wager_monitoring_service.last_wager_fetch_time.isoformat(),
                "fetch_duration": high_wager_monitoring_service.wager_fetch_duration,
                "wager_summary": {
                    "total_wagers": len(current_wagers),
                    "system_wagers": len([w for w in current_wagers if w.is_system_bet]),
                    "active_wagers": len(active_wagers),
                    "filled_wagers": len(filled_wagers)
                },
                "fills_detected": {
                    "recent_fills": len(high_wager_monitoring_service.recent_fills),
                    "line_exposures_updated": len(high_wager_monitoring_service.line_exposure)
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error forcing API refresh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error forcing API refresh: {str(e)}")

@router.get("/debug-anti-duplicate", response_model=Dict[str, Any])
async def debug_anti_duplicate():
    """
    DEBUG ENDPOINT: Test anti-duplicate protection logic
    
    This endpoint shows how the anti-duplicate filter would work on current
    opportunities vs recent wagers to prevent duplicate bet placement.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Fetch current data
        await high_wager_monitoring_service._fetch_current_wagers_from_api()
        current_opportunities = await high_wager_monitoring_service._get_current_opportunities()
        
        # Get recent wagers (last 5 minutes)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(minutes=5)
        
        recent_wagers = []
        for wager in high_wager_monitoring_service.current_wagers:
            if wager.is_system_bet and wager.created_at:
                try:
                    if isinstance(wager.created_at, str):
                        created_dt = datetime.fromisoformat(wager.created_at.replace('Z', '+00:00'))
                        if created_dt >= recent_cutoff:
                            recent_wagers.append(wager)
                except (ValueError, TypeError):
                    pass
        
        # Test the anti-duplicate filter
        filtered_opportunities = await high_wager_monitoring_service._filter_opportunities_against_recent_bets(current_opportunities)
        
        # Analyze what would be filtered
        original_count = len(current_opportunities)
        filtered_count = len(filtered_opportunities)
        duplicates_removed = original_count - filtered_count
        
        # Show matching details
        duplicate_analysis = []
        for opp in current_opportunities:
            if opp not in filtered_opportunities:
                # This opportunity was filtered as duplicate
                matching_wager = None
                for wager in recent_wagers:
                    if high_wager_monitoring_service._opportunity_matches_recent_wager(opp, wager):
                        matching_wager = wager
                        break
                
                duplicate_analysis.append({
                    "opportunity": {
                        "line_id": opp.line_id,
                        "side": opp.side,
                        "odds": opp.recommended_odds,
                        "stake": opp.recommended_stake
                    },
                    "matching_wager": {
                        "external_id": matching_wager.external_id if matching_wager else None,
                        "line_id": matching_wager.line_id if matching_wager else None,
                        "side": matching_wager.side if matching_wager else None,
                        "odds": matching_wager.odds if matching_wager else None,
                        "stake": matching_wager.stake if matching_wager else None,
                        "created_at": matching_wager.created_at if matching_wager else None
                    },
                    "match_reason": "Same line_id, similar side, close odds/stakes"
                })
        
        return {
            "success": True,
            "message": f"Anti-duplicate analysis complete - {duplicates_removed} duplicates would be prevented",
            "data": {
                "current_state": {
                    "total_opportunities": original_count,
                    "recent_wagers": len(recent_wagers),
                    "after_filter": filtered_count,
                    "duplicates_removed": duplicates_removed
                },
                "recent_wagers_summary": [
                    {
                        "external_id": w.external_id[:12] + "..." if w.external_id else None,
                        "line_id": w.line_id[:12] + "..." if w.line_id else None,
                        "side": w.side,
                        "odds": w.odds,
                        "stake": w.stake,
                        "created_at": w.created_at
                    }
                    for w in recent_wagers[:10]  # Show first 10
                ],
                "duplicate_analysis": duplicate_analysis,
                "filter_effectiveness": {
                    "protection_rate": f"{(duplicates_removed / original_count * 100):.1f}%" if original_count > 0 else "0%",
                    "would_prevent_duplicates": duplicates_removed > 0,
                    "remaining_safe_opportunities": filtered_count
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in anti-duplicate debug: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Anti-duplicate debug failed: {str(e)}")

@router.get("/debug-api-wagers", response_model=Dict[str, Any])
async def debug_api_wagers():
    """
    DEBUG ENDPOINT: Inspect raw API wager data to troubleshoot identifier issues
    
    This endpoint helps identify why some wagers don't have the identifiers
    needed for cancellation.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Force fresh API fetch
        await high_wager_monitoring_service._fetch_current_wagers_from_api()
        
        current_wagers = high_wager_monitoring_service.current_wagers
        
        # Analyze the wagers
        all_wagers = current_wagers
        system_wagers = [w for w in all_wagers if w.is_system_bet]
        active_wagers = [w for w in system_wagers if w.is_active]
        missing_ids = [w for w in active_wagers if not w.external_id or not w.wager_id]
        valid_for_actions = [w for w in active_wagers if w.external_id and w.wager_id]
        
        # Sample data for inspection
        sample_wagers = []
        for wager in all_wagers[:10]:  # First 10 wagers for inspection
            sample_wagers.append({
                "wager_id": wager.wager_id,
                "external_id": wager.external_id,
                "line_id": wager.line_id,
                "side": wager.side,
                "odds": wager.odds,
                "stake": wager.stake,
                "unmatched_stake": wager.unmatched_stake,
                "status": wager.status,
                "matching_status": wager.matching_status,
                "is_system_bet": wager.is_system_bet,
                "is_active": wager.is_active,
                "has_external_id": bool(wager.external_id),
                "has_wager_id": bool(wager.wager_id),
                "valid_for_actions": bool(wager.external_id and wager.wager_id)
            })
        
        # Detailed analysis of problematic wagers
        problematic_wagers = []
        for wager in missing_ids:
            problematic_wagers.append({
                "line_id": wager.line_id,
                "side": wager.side,
                "external_id": f"'{wager.external_id}'" if wager.external_id else None,
                "wager_id": f"'{wager.wager_id}'" if wager.wager_id else None,
                "external_id_length": len(wager.external_id) if wager.external_id else 0,
                "wager_id_length": len(wager.wager_id) if wager.wager_id else 0,
                "issue": "missing_external_id" if not wager.external_id else "missing_wager_id"
            })
        
        return {
            "success": True,
            "message": f"Debug analysis complete - {len(missing_ids)} wagers have identifier issues",
            "data": {
                "summary": {
                    "total_wagers": len(all_wagers),
                    "system_wagers": len(system_wagers),
                    "active_system_wagers": len(active_wagers),
                    "missing_identifiers": len(missing_ids),
                    "valid_for_actions": len(valid_for_actions),
                    "fetch_duration": high_wager_monitoring_service.wager_fetch_duration
                },
                "identifier_issues": {
                    "count": len(missing_ids),
                    "problematic_wagers": problematic_wagers
                },
                "sample_wagers": sample_wagers,
                "troubleshooting": {
                    "possible_causes": [
                        "Old wagers placed before external_id tracking",
                        "Manual bets placed outside the system",
                        "API response format changes",
                        "ProphetX ID field name variations"
                    ],
                    "next_steps": [
                        "Check if missing wagers are old/manual bets",
                        "Verify API response field names match expectations",
                        "Consider filtering out wagers without proper IDs"
                    ]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in debug API wagers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Debug failed: {str(e)}")

@router.get("/fill-detection", response_model=Dict[str, Any])
async def get_fill_detection_info():
    """
    Get information about detected fills from API data
    
    **NEW ENDPOINT: Shows fill detection capabilities**
    This endpoint shows fills detected from the API, which wasn't possible
    with the old TrackedWagers system.
    """
    try:
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        
        # Get filled wagers from current API data
        filled_wagers = [w for w in high_wager_monitoring_service.current_wagers 
                        if w.is_filled and w.is_system_bet]
        
        fill_summary = []
        for wager in filled_wagers:
            fill_summary.append({
                "external_id": wager.external_id,
                "line_id": wager.line_id,
                "side": wager.side,
                "odds": wager.odds,
                "original_stake": wager.stake,
                "matched_stake": wager.matched_stake,
                "unmatched_stake": wager.unmatched_stake,
                "fill_percentage": (wager.matched_stake / wager.stake * 100) if wager.stake > 0 else 0,
                "status": wager.status,
                "matching_status": wager.matching_status,
                "updated_at": wager.updated_at
            })
        
        return {
            "success": True,
            "message": f"Fill detection info for {len(filled_wagers)} filled wagers",
            "data": {
                "total_filled_wagers": len(filled_wagers),
                "recent_fills_tracked": len(high_wager_monitoring_service.recent_fills),
                "filled_wagers": fill_summary,
                "fill_detection_features": {
                    "automatic_detection": "✅ Detects fills from API matched_stake field",
                    "wait_period_tracking": "✅ Tracks last fill time per line for wait periods",
                    "exposure_updates": "✅ Updates line exposure based on unmatched stakes",
                    "real_time_status": "✅ Shows current matching_status from ProphetX"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting fill detection info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting fill detection info: {str(e)}")

# Keep existing settings endpoints unchanged
@router.post("/settings/monitoring-interval", response_model=Dict[str, Any])
async def update_monitoring_interval(interval_seconds: int):
    """Update the monitoring interval"""
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
    """Update the maximum exposure multiplier"""
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

# ============================================================================
# BACKWARD COMPATIBILITY ENDPOINTS (for transition period)
# ============================================================================

@router.get("/tracked-wagers", response_model=Dict[str, Any])
async def get_tracked_wagers():
    """
    DEPRECATED: Get tracked wagers (backward compatibility)
    
    This endpoint now redirects to /current-wagers which uses API data.
    Kept for backward compatibility during transition.
    """
    try:
        logger.warning("⚠️ /tracked-wagers endpoint is deprecated, use /current-wagers instead")
        
        # Redirect to current-wagers endpoint
        from app.services.high_wager_monitoring_service import high_wager_monitoring_service
        current_wagers = await high_wager_monitoring_service.get_current_wagers()
        
        return {
            "success": current_wagers["success"],
            "message": "DEPRECATED: Use /current-wagers endpoint. This now shows API data instead of tracked wagers.",
            "data": current_wagers["data"],
            "deprecation_notice": {
                "old_endpoint": "/tracked-wagers",
                "new_endpoint": "/current-wagers", 
                "change": "Now uses real-time API data instead of local tracking",
                "benefits": ["Real-time status", "Fill detection", "No stale data"]
            }
        }
        
    except Exception as e:
        logger.error(f"Error in deprecated tracked-wagers endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting tracked wagers: {str(e)}")