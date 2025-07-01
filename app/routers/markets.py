#!/usr/bin/env python3
"""
Markets Router
FastAPI endpoints for market scanning and opportunity discovery
"""

import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional

from app.models.requests import ScanRequest
from app.models.responses import (
    TournamentInfo, EventInfo, ScanResponse, APIResponse, BettingOpportunity
)
from app.routers.auth import require_auth
from app.services.scanner_service import scanner_service

router = APIRouter()

@router.get("/tournaments", response_model=List[TournamentInfo])
async def get_tournaments(auth_service = Depends(require_auth)):
    """
    Get all available tournaments in target sports
    
    Returns list of tournaments with their IDs, names, and sport information.
    Only tournaments for configured target sports are returned.
    """
    try:
        tournaments = await scanner_service.get_tournaments()
        return tournaments
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tournaments: {str(e)}")

@router.get("/tournaments/{tournament_id}/events", response_model=List[EventInfo])
async def get_tournament_events(
    tournament_id: int,
    auth_service = Depends(require_auth)
):
    """
    Get all upcoming events for a specific tournament
    
    - **tournament_id**: The ID of the tournament to get events for
    
    Returns list of upcoming events (status = 'not_started') with scheduling information.
    """
    try:
        events = await scanner_service.get_events_for_tournament(tournament_id)
        return events
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching events for tournament {tournament_id}: {str(e)}"
        )

@router.get("/events/{event_id}/markets")
async def get_event_markets(
    event_id: int,
    auth_service = Depends(require_auth)
):
    """
    Get raw market data for a specific event
    
    - **event_id**: The ID of the event to get markets for
    
    Returns the raw market data structure from ProphetX API.
    This is useful for debugging market structure and understanding data format.
    """
    try:
        markets_data = await scanner_service.get_markets_for_event(event_id)
        
        if not markets_data:
            raise HTTPException(status_code=404, detail=f"No markets found for event {event_id}")
        
        return markets_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching markets for event {event_id}: {str(e)}"
        )

@router.post("/scan/tournament/{tournament_id}", response_model=ScanResponse)
async def scan_tournament(
    tournament_id: int,
    limit_events: Optional[int] = Query(None, description="Maximum number of events to scan"),
    auth_service = Depends(require_auth)
):
    """
    Scan a specific tournament for betting opportunities
    
    - **tournament_id**: The ID of the tournament to scan
    - **limit_events**: Optional limit on number of events to scan (useful for testing)
    
    Scans all upcoming events in the tournament and analyzes markets for large bets worth following.
    Returns detailed opportunities with follow-the-money analysis.
    """
    try:
        start_time = time.time()
        
        # Get tournament info for better response
        tournaments = await scanner_service.get_tournaments()
        tournament_name = "Unknown Tournament"
        for t in tournaments:
            if t.id == tournament_id:
                tournament_name = t.name
                break
        
        # Scan the tournament
        opportunities = await scanner_service.scan_tournament(tournament_id, limit_events)
        
        scan_duration = time.time() - start_time
        
        # Count events scanned
        events = await scanner_service.get_events_for_tournament(tournament_id)
        events_scanned = min(len(events), limit_events) if limit_events else len(events)
        
        return ScanResponse(
            scan_type=f"tournament_{tournament_id}",
            opportunities_found=len(opportunities),
            opportunities=opportunities,
            scan_duration_seconds=scan_duration,
            events_scanned=events_scanned,
            markets_scanned=events_scanned  # Rough estimate
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error scanning tournament {tournament_id}: {str(e)}"
        )

@router.post("/scan/event/{event_id}", response_model=ScanResponse)
async def scan_event(
    event_id: int,
    auth_service = Depends(require_auth)
):
    """
    Scan a specific event for betting opportunities
    
    - **event_id**: The ID of the event to scan
    
    Analyzes all markets for the specified event and identifies opportunities where
    large bets (above threshold) indicate smart money worth following.
    """
    try:
        start_time = time.time()
        
        # Scan the event
        opportunities = await scanner_service.scan_event(event_id)
        
        scan_duration = time.time() - start_time
        
        return ScanResponse(
            scan_type=f"event_{event_id}",
            opportunities_found=len(opportunities),
            opportunities=opportunities,
            scan_duration_seconds=scan_duration,
            events_scanned=1,
            markets_scanned=1  # Will have multiple markets per event
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error scanning event {event_id}: {str(e)}"
        )

@router.post("/scan/comprehensive", response_model=ScanResponse)
async def scan_all_markets(
    background_tasks: BackgroundTasks,
    max_events_per_tournament: Optional[int] = Query(None, description="Limit events per tournament"),
    auth_service = Depends(require_auth)
):
    """
    🚨 COMPREHENSIVE SCAN - All tournaments, all events, all markets
    
    - **max_events_per_tournament**: Optional limit to prevent extremely long scans
    
    **WARNING**: This scans ALL tournaments in target sports and ALL their events.
    This can take 10+ minutes and generate hundreds of API calls.
    
    Use with caution! Consider using tournament-specific or event-specific scans for testing.
    """
    try:
        start_time = time.time()
        
        # For comprehensive scans, we might want to run in background
        # For now, run synchronously but with limits
        
        tournaments = await scanner_service.get_tournaments()
        all_opportunities = []
        total_events_scanned = 0
        total_markets_scanned = 0
        
        for tournament in tournaments:
            try:
                # Get events for this tournament
                events = await scanner_service.get_events_for_tournament(tournament.id)
                
                # Apply limit if specified
                if max_events_per_tournament:
                    events = events[:max_events_per_tournament]
                
                # Scan each event
                for event in events:
                    try:
                        opportunities = await scanner_service.analyze_market_for_opportunities(
                            await scanner_service.get_markets_for_event(event.event_id),
                            event
                        )
                        all_opportunities.extend(opportunities)
                        total_events_scanned += 1
                        total_markets_scanned += 1  # Rough estimate
                        
                        # Rate limiting
                        time.sleep(0.5)
                        
                    except Exception as e:
                        # Continue with other events if one fails
                        print(f"Error scanning event {event.event_id}: {e}")
                        continue
                
                # Rate limiting between tournaments
                time.sleep(1)
                
            except Exception as e:
                # Continue with other tournaments if one fails
                print(f"Error scanning tournament {tournament.id}: {e}")
                continue
        
        scan_duration = time.time() - start_time
        
        return ScanResponse(
            scan_type="comprehensive",
            opportunities_found=len(all_opportunities),
            opportunities=all_opportunities,
            scan_duration_seconds=scan_duration,
            events_scanned=total_events_scanned,
            markets_scanned=total_markets_scanned
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error during comprehensive scan: {str(e)}"
        )

@router.get("/scan/status", response_model=APIResponse)
async def get_scan_status():
    """
    Get current scanning status and configuration
    
    Returns information about current scan settings, thresholds, and target sports.
    """
    try:
        from app.core.config import get_settings
        settings = get_settings()
        
        return APIResponse(
            success=True,
            message="Scan status retrieved",
            data={
                "min_stake_threshold": settings.min_stake_threshold,
                "max_bet_size": settings.max_bet_size,
                "target_sports": settings.target_sports,
                "undercut_amount": settings.undercut_amount,
                "environment": "sandbox" if settings.sandbox else "production",
                "base_url": settings.prophetx_base_url
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scan status: {str(e)}")

@router.get("/opportunities/filter", response_model=List[BettingOpportunity])
async def filter_opportunities(
    min_stake: Optional[int] = Query(None, description="Minimum original stake amount"),
    max_stake: Optional[int] = Query(None, description="Maximum original stake amount"),
    sport: Optional[str] = Query(None, description="Filter by sport name"),
    market_type: Optional[str] = Query(None, description="Filter by market type"),
    min_roi: Optional[float] = Query(None, description="Minimum ROI percentage"),
    limit: Optional[int] = Query(10, description="Maximum number of results"),
    auth_service = Depends(require_auth)
):
    """
    Filter and search betting opportunities (placeholder)
    
    This endpoint is a placeholder for future functionality to filter
    previously found opportunities based on various criteria.
    
    Currently returns empty list - implement with database storage for full functionality.
    """
    # This would require storing opportunities in a database
    # For now, return empty list as this is a placeholder
    return []

@router.get("/opportunities/top", response_model=List[BettingOpportunity])
async def get_top_opportunities(
    limit: int = Query(5, description="Number of top opportunities to return"),
    sort_by: str = Query("value_score", description="Sort by: value_score, stake, roi_percent"),
    auth_service = Depends(require_auth)
):
    """
    Get top betting opportunities (placeholder)
    
    This endpoint is a placeholder for future functionality to get
    the best current opportunities across all markets.
    
    Currently returns empty list - implement with database storage for full functionality.
    """
    # This would require storing opportunities in a database
    # For now, return empty list as this is a placeholder
    return []