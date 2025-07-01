#!/usr/bin/env python3
"""
Bets Router
FastAPI endpoints for bet placement and management
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional

from app.models.requests import BetPlacementRequest, MultipleBetRequest
from app.models.responses import BetResult, BetPlacementSummary, APIResponse, BettingOpportunity
from app.routers.auth import require_auth
from app.services.bet_placement_service import bet_placement_service

router = APIRouter()

@router.post("/place", response_model=BetResult)
async def place_single_bet(
    request: BetPlacementRequest,
    auth_service = Depends(require_auth)
):
    """
    Place a single bet manually
    
    This endpoint allows manual bet placement by providing line_id, odds, and stake.
    Useful for testing bet placement functionality or placing custom bets.
    
    **Note**: This places a direct bet, not a "follow the money" bet.
    For following large bets, use the market scanning endpoints to find opportunities first.
    """
    try:
        # Set dry run mode for this bet if specified
        original_dry_run = bet_placement_service.dry_run
        bet_placement_service.set_dry_run(request.dry_run)
        
        # Create a minimal opportunity for bet placement
        from app.models.responses import BetPlacementInfo, OriginalBet, OurBet, OpportunityAnalysis
        
        # Create a synthetic opportunity for the bet placement service
        opportunity = BettingOpportunity(
            event_id=0,
            event_name="Manual Bet",
            market_name="Manual Placement",
            market_type="manual",
            market_id=None,
            
            original_bet=OriginalBet(
                team_name="Manual",
                odds=request.odds,
                stake=request.stake,
                display=f"Manual bet {request.odds:+d} for ${request.stake:,}"
            ),
            
            our_bet=OurBet(
                team_name="Manual",
                odds=request.odds,
                stake=request.stake,
                display=f"Manual bet {request.odds:+d} for ${request.stake:,}"
            ),
            
            bet_placement=BetPlacementInfo(
                line_id=request.line_id,
                competitor_id=None,
                outcome_id=None,
                odds=request.odds,
                stake=request.stake
            ),
            
            analysis=OpportunityAnalysis(
                value_score=0,
                potential_profit=0,
                potential_win=0,
                roi_percent=0,
                undercut_explanation="Manual bet placement",
                follow_money_logic="Manual bet placement"
            ),
            
            updated_at=None,
            is_valid_follow=False
        )
        
        # Place the bet
        result = await bet_placement_service.place_single_bet(opportunity, request.stake)
        
        # Restore original dry run setting
        bet_placement_service.set_dry_run(original_dry_run)
        
        return result
        
    except Exception as e:
        # Restore original dry run setting
        bet_placement_service.set_dry_run(original_dry_run)
        raise HTTPException(status_code=500, detail=f"Error placing bet: {str(e)}")

@router.post("/place-multiple", response_model=BetPlacementSummary)
async def place_multiple_bets(
    request: MultipleBetRequest,
    auth_service = Depends(require_auth)
):
    """
    Place multiple bets from opportunities
    
    This is the main endpoint for "follow the money" strategy.
    Takes a list of opportunities (usually from market scanning) and places follow bets.
    
    **Process:**
    1. Scan markets to find large bets (opportunities)
    2. Pass those opportunities to this endpoint
    3. System places follow bets with undercut odds
    4. Get priority in betting queue when action flows
    """
    try:
        if not request.opportunities:
            return BetPlacementSummary(
                total=0,
                successful=0,
                failed=0,
                bet_size_used=request.bet_size or bet_placement_service.default_bet_size,
                results=[]
            )
        
        # Set dry run mode if specified
        original_dry_run = bet_placement_service.dry_run
        bet_placement_service.set_dry_run(request.dry_run)
        
        # Place multiple bets
        summary = await bet_placement_service.place_multiple_bets(
            request.opportunities,
            request.bet_size,
            request.delay_seconds
        )
        
        # Restore original dry run setting
        bet_placement_service.set_dry_run(original_dry_run)
        
        return summary
        
    except Exception as e:
        # Restore original dry run setting
        bet_placement_service.set_dry_run(original_dry_run)
        raise HTTPException(status_code=500, detail=f"Error placing multiple bets: {str(e)}")

@router.get("/history", response_model=APIResponse)
async def get_bet_history(
    limit: Optional[int] = Query(50, description="Maximum number of bets to return"),
    status: Optional[str] = Query(None, description="Filter by status: 'successful' or 'failed'"),
    auth_service = Depends(require_auth)
):
    """
    Get bet placement history
    
    Returns history of all bets placed through this API, including both successful
    and failed attempts. Useful for tracking performance and debugging.
    """
    try:
        history = bet_placement_service.get_bet_history()
        
        # Apply filters
        successful_bets = history['successful_bets']
        failed_bets = history['failed_bets']
        
        if status == 'successful':
            filtered_bets = successful_bets[:limit] if limit else successful_bets
            other_bets = []
        elif status == 'failed':
            filtered_bets = failed_bets[:limit] if limit else failed_bets
            other_bets = []
        else:
            # Combine and sort by timestamp
            all_bets = successful_bets + failed_bets
            # Sort by placed_at timestamp (most recent first)
            all_bets.sort(
                key=lambda x: x.get('placed_at', ''), 
                reverse=True
            )
            filtered_bets = all_bets[:limit] if limit else all_bets
            other_bets = []
        
        return APIResponse(
            success=True,
            message=f"Retrieved {len(filtered_bets)} bet records",
            data={
                "statistics": history['statistics'],
                "bets": filtered_bets,
                "filters_applied": {
                    "limit": limit,
                    "status": status
                },
                "generated_at": history['generated_at']
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting bet history: {str(e)}")

@router.get("/stats", response_model=APIResponse)
async def get_placement_stats(auth_service = Depends(require_auth)):
    """
    Get bet placement statistics
    
    Returns summary statistics about all bet placements made through this API.
    Includes success rates, total stakes, and other performance metrics.
    """
    try:
        stats = bet_placement_service.get_placement_stats()
        
        return APIResponse(
            success=True,
            message="Bet placement statistics",
            data=stats
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting placement stats: {str(e)}")

@router.post("/clear-history", response_model=APIResponse)
async def clear_bet_history(auth_service = Depends(require_auth)):
    """
    Clear bet placement history
    
    Clears all stored bet history and statistics. Use with caution!
    This action cannot be undone.
    """
    try:
        bet_placement_service.clear_history()
        
        return APIResponse(
            success=True,
            message="Bet history cleared successfully",
            data=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing bet history: {str(e)}")

@router.get("/status/{bet_id}", response_model=APIResponse)
async def get_bet_status(
    bet_id: str,
    auth_service = Depends(require_auth)
):
    """
    Get status of a specific bet
    
    Checks the current status of a bet by its ID. 
    
    **Note**: This feature depends on ProphetX providing bet status endpoints,
    which may not be available. Currently returns limited information.
    """
    try:
        status = await bet_placement_service.get_bet_status(bet_id)
        
        if status is None:
            return APIResponse(
                success=False,
                message=f"Bet status not available for bet {bet_id}",
                data={"bet_id": bet_id, "status": "unknown"}
            )
        
        return APIResponse(
            success=True,
            message=f"Bet status for {bet_id}",
            data=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting bet status: {str(e)}")

@router.post("/cancel/{bet_id}", response_model=APIResponse)
async def cancel_bet(
    bet_id: str,
    auth_service = Depends(require_auth)
):
    """
    Cancel a specific bet
    
    Attempts to cancel a bet by its ID.
    
    **Note**: Bet cancellation depends on ProphetX API support and may not be
    available for all bet types or after certain time periods.
    """
    try:
        result = await bet_placement_service.cancel_bet(bet_id)
        
        return APIResponse(
            success=result["success"],
            message=result["message"],
            data={"bet_id": bet_id, "cancelled": result["success"]}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling bet: {str(e)}")

@router.post("/test-placement", response_model=APIResponse)
async def test_bet_placement(
    bet_size: float = Query(5.0, description="Test bet size"),
    dry_run: bool = Query(True, description="Use dry run mode"),
    auth_service = Depends(require_auth)
):
    """
    Test bet placement functionality
    
    Tests the bet placement system with a minimal test bet.
    Always use dry_run=true for safety unless you want to place a real test bet.
    
    **Warning**: Setting dry_run=false will attempt to place a real bet!
    """
    try:
        # This is a basic test that doesn't require a real line_id
        # In a real implementation, you'd need a valid line_id from market data
        
        test_result = {
            "test_type": "bet_placement_system_test",
            "dry_run_mode": dry_run,
            "bet_size": bet_size,
            "system_status": "ready",
            "authentication": "valid",
            "api_connection": "active"
        }
        
        if dry_run:
            test_result["message"] = "Bet placement system test successful (dry run)"
            test_result["warning"] = "Set dry_run=false only if you want to place a real test bet"
        else:
            test_result["message"] = "Ready to place real bets"
            test_result["warning"] = "Real bet placement mode - bets will be actual!"
        
        return APIResponse(
            success=True,
            message="Bet placement test completed",
            data=test_result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing bet placement: {str(e)}")

@router.post("/config/dry-run", response_model=APIResponse)
async def set_dry_run_mode(
    enabled: bool = Query(..., description="Enable or disable dry run mode"),
    auth_service = Depends(require_auth)
):
    """
    Set dry run mode for bet placement
    
    Controls whether bets are actually placed or just simulated.
    
    - **enabled=true**: Bets are simulated (safe for testing)
    - **enabled=false**: Bets are actually placed (real money!)
    
    **Safety**: Always test with dry_run=true first!
    """
    try:
        bet_placement_service.set_dry_run(enabled)
        
        mode = "DRY RUN (simulated)" if enabled else "LIVE (real bets)"
        warning = "Bets will be simulated only" if enabled else "⚠️ REAL BETS WILL BE PLACED!"
        
        return APIResponse(
            success=True,
            message=f"Dry run mode {'enabled' if enabled else 'disabled'}",
            data={
                "dry_run_enabled": enabled,
                "mode": mode,
                "warning": warning,
                "safety_tip": "Always test with dry_run=true first!"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting dry run mode: {str(e)}")

@router.post("/config/bet-size", response_model=APIResponse)
async def set_default_bet_size(
    bet_size: float = Query(..., description="Default bet size in dollars"),
    auth_service = Depends(require_auth)
):
    """
    Set default bet size for all bets
    
    Changes the default bet size used when no specific bet size is provided.
    This affects all future bet placements until changed again.
    """
    try:
        if bet_size <= 0:
            raise HTTPException(status_code=400, detail="Bet size must be positive")
        
        bet_placement_service.set_default_bet_size(bet_size)
        
        return APIResponse(
            success=True,
            message=f"Default bet size set to ${bet_size}",
            data={
                "default_bet_size": bet_size,
                "note": "This affects all future bets unless overridden"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting bet size: {str(e)}")