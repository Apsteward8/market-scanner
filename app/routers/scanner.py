#!/usr/bin/env python3
"""
Scanner Router
API endpoints for market scanning and high wager detection
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import logging

from app.services.market_scanning_service import market_scanning_service
from app.services.prophetx_service import prophetx_service
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/authenticate", response_model=Dict[str, Any])
async def authenticate_prophetx():
    """
    Authenticate with ProphetX API for market scanning
    
    Tests production API authentication for data fetching.
    This must be called before any scanning operations.
    """
    try:
        result = await prophetx_service.authenticate()
        
        return {
            "success": True,
            "message": "ProphetX authentication successful",
            "data": result,
            "environment": "production (for data fetching)"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/auth-status", response_model=Dict[str, Any])
async def get_auth_status():
    """Get current ProphetX authentication status"""
    try:
        status = prophetx_service.get_auth_status()
        
        return {
            "success": True,
            "message": "Authentication status retrieved",
            "data": status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting auth status: {str(e)}")

@router.get("/ncaaf-events", response_model=Dict[str, Any])
async def get_ncaaf_events():
    """
    Get upcoming NCAAF events for scanning
    
    Returns all NCAAF events from ProphetX with caching.
    Used to see what games are available for market scanning.
    """
    try:
        settings = get_settings()
        
        # NCAAF tournament ID
        tournament_id = "27653"
        
        response = await prophetx_service.get_sport_events(tournament_id)
        events_data = response.get('data', {}).get('sport_events', [])
        
        # Filter for upcoming events (next 48 hours for display)
        now = datetime.now(timezone.utc)
        upcoming_events = []
        
        for event in events_data:
            try:
                scheduled_str = event.get('scheduled', '')
                scheduled_time = datetime.fromisoformat(scheduled_str.replace('Z', '+00:00'))
                
                hours_until = (scheduled_time - now).total_seconds() / 3600
                
                if 0 < hours_until <= 48:  # Next 48 hours
                    competitors = event.get('competitors', [])
                    home_team = next((c['display_name'] for c in competitors if c.get('side') == 'home'), 'TBD')
                    away_team = next((c['display_name'] for c in competitors if c.get('side') == 'away'), 'TBD')
                    
                    upcoming_events.append({
                        "event_id": event.get('event_id'),
                        "matchup": f"{away_team} @ {home_team}",
                        "scheduled": scheduled_str,
                        "hours_until": round(hours_until, 1),
                        "status": event.get('status'),
                        "tournament": event.get('tournament_name')
                    })
                    
            except Exception as e:
                logger.warning(f"Error parsing event: {e}")
                continue
        
        # Sort by scheduled time
        upcoming_events.sort(key=lambda x: x['hours_until'])
        
        return {
            "success": True,
            "message": f"Found {len(upcoming_events)} upcoming NCAAF events",
            "data": {
                "events": upcoming_events,
                "total_count": len(events_data),
                "upcoming_count": len(upcoming_events),
                "tournament_id": tournament_id,
                "cache_status": "cached" if tournament_id in prophetx_service.sport_events_cache else "fresh"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NCAAF events: {str(e)}")

@router.post("/scan-opportunities", response_model=Dict[str, Any])
async def scan_for_opportunities():
    """
    Scan for high wager opportunities in NCAAF markets
    
    This is the main scanning function that:
    1. Gets upcoming NCAAF events (next 24 hours)
    2. Fetches market data for those events
    3. Identifies high wager opportunities (stake + value >= $7500)
    4. Calculates potential undercut strategies
    """
    try:
        logger.info("🔍 Starting high wager opportunity scan...")
        
        # Run the main scanning process
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        # Format opportunities for response
        formatted_opportunities = []
        
        for opp in opportunities:
            hours_until = (opp.scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
            
            formatted_opportunities.append({
                "event": {
                    "id": opp.event_id,
                    "name": opp.event_name,
                    "hours_until": round(hours_until, 1),
                    "tournament": opp.tournament_name
                },
                "market": {
                    "id": opp.market_id,
                    "name": opp.market_name,
                    "type": opp.market_type,
                    "line_info": opp.line_info
                },
                "large_bet": {
                    "side": opp.large_bet_side,
                    "stake_amount": opp.large_bet_stake_amount,
                    "liquidity_value": opp.large_bet_liquidity_value,
                    "combined_size": opp.large_bet_combined_size,
                    "odds": opp.large_bet_odds,
                    "formatted": f"{opp.large_bet_side} @ {opp.large_bet_odds:+d} (${opp.large_bet_combined_size:,.0f})"
                },
                "opportunity": {
                    "available_side": opp.available_side,
                    "available_odds": opp.available_odds,
                    "available_liquidity": opp.available_liquidity_amount,
                    "our_proposed_odds": opp.our_proposed_odds,
                    "formatted": f"Follow with {opp.available_side} @ {opp.our_proposed_odds:+d}"
                }
            })
        
        # Sort by combined bet size (largest first)
        formatted_opportunities.sort(key=lambda x: x['large_bet']['combined_size'], reverse=True)
        
        # Calculate summary stats
        total_large_bet_volume = sum(opp.large_bet_combined_size for opp in opportunities)
        
        # Group by market type
        market_type_counts = {}
        for opp in opportunities:
            market_type = opp.market_type
            market_type_counts[market_type] = market_type_counts.get(market_type, 0) + 1
        
        return {
            "success": True,
            "message": f"Scan complete - found {len(opportunities)} opportunities",
            "data": {
                "opportunities": formatted_opportunities,
                "summary": {
                    "total_opportunities": len(opportunities),
                    "market_type_breakdown": market_type_counts,
                    "total_large_bet_volume": f"${total_large_bet_volume:,.0f}",
                    "avg_opportunity_size": f"${total_large_bet_volume / max(len(opportunities), 1):,.0f}",
                    "scan_timestamp": datetime.now(timezone.utc).isoformat(),
                    "filtering_criteria": {
                        "min_stake": "$2,500",
                        "min_value": "$2,500", 
                        "min_combined": "$10,000",
                        "max_odds": "±400"
                    },
                    "deduplication_applied": "Only best odds kept per line"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error during opportunity scan: {e}")
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

@router.get("/test-market-data/{event_id}", response_model=Dict[str, Any])
async def test_market_data(event_id: str):
    """
    Test fetching market data for a specific event
    
    Useful for debugging market data structure and identifying
    which markets have high wager activity.
    """
    try:
        logger.info(f"📊 Testing market data fetch for event {event_id}")
        
        # Fetch market data for single event
        market_data = await prophetx_service.get_multiple_markets([event_id])
        event_markets = market_data.get('data', {}).get(event_id, [])
        
        if not event_markets:
            return {
                "success": False,
                "message": f"No market data found for event {event_id}",
                "data": {"event_id": event_id}
            }
        
        # Analyze the markets
        game_line_markets = []
        high_stake_selections = []
        
        for market in event_markets:
            category_name = market.get('category_name', '')
            
            # Focus on Game Lines
            if category_name == "Game Lines":
                market_summary = {
                    "market_id": market.get('id'),
                    "category": category_name,
                    "type": market.get('type'),
                    "name": market.get('name', ''),
                    "selections": []
                }
                
                # Handle different market structures
                if market.get('type') == 'moneyline':
                    # Moneylines have selections directly
                    selections = market.get('selections', [])
                    
                    # Process moneyline selections
                    for i, selection_group in enumerate(selections):
                        if selection_group:
                            side_name = f"Side {i+1}"
                            side_selections = []
                            
                            for j, selection in enumerate(selection_group):
                                stake = float(selection.get('stake', 0))
                                value = float(selection.get('value', 0))
                                combined = stake + value
                                
                                selection_info = {
                                    "selection_index": j,
                                    "side": selection.get('display_name', ''),
                                    "odds": selection.get('odds'),
                                    "stake": stake,
                                    "value": value,
                                    "combined": combined,
                                    "meets_threshold": (stake >= 2500.0 and value >= 2500.0 and combined >= 10000.0),
                                    "stake_threshold": stake >= 2500.0,
                                    "value_threshold": value >= 2500.0,
                                    "combined_threshold": combined >= 10000.0,
                                    "odds_acceptable": abs(selection.get('odds') or 0) <= 400
                                }
                                
                                side_selections.append(selection_info)
                                
                                # Use new filtering criteria
                                if (stake >= 2500.0 and value >= 2500.0 and combined >= 10000.0):
                                    high_stake_selections.append({
                                        "market_type": market.get('type'),
                                        "side_index": i,
                                        "selection_index": j,
                                        "selection": selection_info
                                    })
                            
                            market_summary["selections"].append({
                                "side_name": side_name,
                                "selections": side_selections,
                                "total_selections": len(side_selections)
                            })
                    
                elif market.get('type') in ['spread', 'total', 'totals']:
                    # Spreads and totals have market_lines
                    market_lines = market.get('market_lines', [])
                    market_summary['market_lines_count'] = len(market_lines)
                    market_summary['structure_type'] = 'market_lines'
                    
                    if not market_lines:
                        market_summary['selections'] = []
                        market_summary['note'] = 'No market_lines found - market may be inactive'
                    else:
                        for line_idx, market_line in enumerate(market_lines):
                            line_selections = market_line.get('selections', [])
                            line_info = {
                                'line_number': line_idx + 1,
                                'line_value': market_line.get('line', 0),
                                'line_name': market_line.get('name', ''),
                                'total_selections_groups': len(line_selections),
                                'selections': []
                            }
                            
                            # Process selections for this line
                            for i, selection_group in enumerate(line_selections):
                                if selection_group:
                                    side_name = f"Line {line_idx + 1} - Side {i + 1}"
                                    side_selections = []
                                    
                                    for j, selection in enumerate(selection_group):
                                        stake = float(selection.get('stake', 0))
                                        value = float(selection.get('value', 0))
                                        combined = stake + value
                                        
                                        selection_info = {
                                            "selection_index": j,
                                            "side": selection.get('display_name', ''),
                                            "odds": selection.get('odds'),
                                            "stake": stake,
                                            "value": value,
                                            "combined": combined,
                                            "meets_threshold": (stake >= 2500.0 and value >= 2500.0 and combined >= 10000.0),
                                            "stake_threshold": stake >= 2500.0,
                                            "value_threshold": value >= 2500.0,
                                            "combined_threshold": combined >= 10000.0,
                                            "odds_acceptable": abs(selection.get('odds') or 0) <= 400
                                        }
                                        
                                        side_selections.append(selection_info)
                                        
                                        # Use new filtering criteria
                                        if (stake >= 2500.0 and value >= 2500.0 and combined >= 10000.0):
                                            high_stake_selections.append({
                                                "market_type": market.get('type'),
                                                "line_index": line_idx,
                                                "side_index": i,
                                                "selection_index": j,
                                                "selection": selection_info
                                            })
                                    
                                    line_info['selections'].append({
                                        "side_name": side_name,
                                        "selections": side_selections,
                                        "total_selections": len(side_selections)
                                    })
                            
                            market_summary['selections'].append(line_info)
                
                game_line_markets.append(market_summary)
        
        return {
            "success": True,
            "message": f"Market data analysis for event {event_id}",
            "data": {
                "event_id": event_id,
                "total_markets": len(event_markets),
                "game_line_markets": len(game_line_markets),
                "high_stake_opportunities": len(high_stake_selections),
                "markets": game_line_markets,
                "high_stakes": high_stake_selections
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing market data: {str(e)}")

@router.get("/settings", response_model=Dict[str, Any])
async def get_scanner_settings():
    """Get current scanner configuration and validate settings"""
    try:
        settings = get_settings()
        validation = settings.validate_settings()
        
        return {
            "success": True,
            "message": "Scanner settings retrieved",
            "data": {
                "strategy": {
                    "min_stake_threshold": settings.min_stake_threshold,
                    "undercut_improvement": settings.undercut_improvement,
                    "max_exposure_total": settings.max_exposure_total,
                    "commission_rate": settings.prophetx_commission_rate
                },
                "environment": {
                    "data_source": "production",
                    "betting_environment": settings.prophetx_betting_environment,
                    "betting_url": settings.betting_base_url
                },
                "validation": validation
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting settings: {str(e)}")

@router.get("/debug-markets/{event_id}", response_model=Dict[str, Any])
async def debug_market_structure(event_id: str):
    """
    Debug the exact market structure to see why spreads/totals aren't being processed
    """
    try:
        # Get market data
        market_data = await prophetx_service.get_multiple_markets([event_id])
        event_markets = market_data.get('data', {}).get(event_id, [])
        
        if not event_markets:
            return {
                "success": False,
                "message": f"No market data for event {event_id}",
                "data": {"event_id": event_id}
            }
        
        # Find Game Lines markets and analyze their structure
        game_line_markets = []
        
        for market in event_markets:
            if market.get('category_name') == 'Game Lines':
                market_info = {
                    "market_id": market.get('id'),
                    "name": market.get('name', ''),
                    "type": market.get('type', ''),
                    "has_selections": bool(market.get('selections', [])),
                    "selections_count": len(market.get('selections', [])),
                    "has_market_lines": bool(market.get('market_lines', [])),
                    "market_lines_count": len(market.get('market_lines', [])),
                }
                
                # If it's spread/total, show market_lines structure
                if market.get('type') in ['spread', 'total', 'totals']:
                    market_lines = market.get('market_lines', [])
                    market_info['market_lines_detail'] = []
                    
                    for idx, line in enumerate(market_lines[:3]):  # Show first 3 lines
                        line_info = {
                            "line_index": idx,
                            "line_value": line.get('line', 0),
                            "line_name": line.get('name', ''),
                            "has_selections": bool(line.get('selections', [])),
                            "selections_count": len(line.get('selections', [])),
                        }
                        
                        # Show selection structure
                        line_selections = line.get('selections', [])
                        if line_selections:
                            line_info['first_selection_group'] = {
                                "group_size": len(line_selections[0]) if line_selections[0] else 0,
                                "has_data": bool(line_selections[0]) if line_selections else False
                            }
                        
                        market_info['market_lines_detail'].append(line_info)
                
                game_line_markets.append(market_info)
        
        return {
            "success": True,
            "message": f"Market structure debug for event {event_id}",
            "data": {
                "event_id": event_id,
                "total_markets": len(event_markets),
                "game_line_markets": len(game_line_markets),
                "markets": game_line_markets
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug failed: {str(e)}")

@router.get("/debug-scan/{event_id}", response_model=Dict[str, Any])
async def debug_scan_single_event(event_id: str):
    """
    Debug scan for a single event to see exactly what the scanning logic finds
    
    This helps identify why the full scan might not be finding opportunities
    that the test endpoint can see.
    """
    try:
        logger.info(f"🐛 Debug scanning single event: {event_id}")
        
        # Create a fake event for this ID
        from app.services.market_scanning_service import SportEvent
        debug_event = SportEvent(
            event_id=event_id,
            display_name="Debug Event",
            scheduled_time=datetime.now(timezone.utc) + timedelta(hours=2),  # 2 hours from now
            home_team="Home Team",
            away_team="Away Team", 
            status="not_started",
            tournament_id="27653",
            tournament_name="College Football"
        )
        
        # Get market data
        market_data = await prophetx_service.get_multiple_markets([event_id])
        event_markets = market_data.get('data', {}).get(event_id, [])
        
        if not event_markets:
            return {
                "success": False,
                "message": f"No market data for event {event_id}",
                "data": {"event_id": event_id}
            }
        
        # Run through the same scanning logic
        opportunities = await market_scanning_service._scan_event_markets(debug_event, event_markets)
        
        return {
            "success": True,
            "message": f"Debug scan complete for event {event_id}",
            "data": {
                "event_id": event_id,
                "event_name": debug_event.display_name,
                "total_markets": len(event_markets),
                "game_line_markets": len([m for m in event_markets if m.get('category_name') == 'Game Lines']),
                "opportunities_found": len(opportunities),
                "opportunities": [
                    {
                        "market_type": opp.market_type,
                        "large_bet_side": opp.large_bet_side,
                        "large_bet_combined_size": opp.large_bet_combined_size,
                        "available_side": opp.available_side,
                        "available_odds": opp.available_odds,
                        "our_proposed_odds": opp.our_proposed_odds,
                        "line_info": opp.line_info
                    }
                    for opp in opportunities
                ],
                "debug_info": {
                    "min_stake_threshold": market_scanning_service.min_stake_threshold,
                    "market_categories_found": list(set(m.get('category_name', '') for m in event_markets)),
                    "market_types_found": list(set(m.get('type', '') for m in event_markets if m.get('category_name') == 'Game Lines'))
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug scan failed: {str(e)}")

@router.post("/clear-cache", response_model=Dict[str, Any])
async def clear_prophetx_cache():
    """Clear ProphetX data cache to force fresh fetches"""
    try:
        await prophetx_service.clear_cache()
        
        return {
            "success": True,
            "message": "ProphetX cache cleared successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")