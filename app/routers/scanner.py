#!/usr/bin/env python3
"""
Scanner Router
API endpoints for market scanning functionality
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import logging

from app.services.market_scanning_service import market_scanning_service
from app.services.prophetx_service import prophetx_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/authenticate")
async def authenticate():
    """Authenticate with ProphetX API"""
    try:
        result = await prophetx_service.authenticate()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/scan-opportunities", response_model=Dict[str, Any])
async def scan_opportunities():
    """
    Scan for high wager opportunities and group them by event
    
    This endpoint:
    1. Gets upcoming NCAAF events (next 24 hours)
    2. Fetches market data for those events
    3. Identifies high wager opportunities (stake >= $2500, value >= $2500, combined >= $10000)
    4. Groups opportunities by event and sorts by game time
    5. Calculates potential undercut strategies using ProphetX odds ladder
    """
    try:
        logger.info("🔍 Starting high wager opportunity scan...")
        
        # Run the main scanning process
        opportunities = await market_scanning_service.scan_for_opportunities()
        
        if not opportunities:
            return {
                "success": True,
                "message": "Scan complete - no opportunities found",
                "data": {
                    "events": [],
                    "summary": {
                        "total_events": 0,
                        "total_opportunities": 0,
                        "total_volume": 0,
                        "market_type_breakdown": {}
                    }
                }
            }
        
        # Group opportunities by event
        events_map = {}
        total_volume = 0
        market_type_counts = {}
        
        for opp in opportunities:
            event_id = opp.event_id
            total_volume += opp.large_bet_combined_size
            
            # Track market type counts
            market_type = opp.market_type
            market_type_counts[market_type] = market_type_counts.get(market_type, 0) + 1
            
            # Group by event
            if event_id not in events_map:
                hours_until = (opp.scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
                events_map[event_id] = {
                    "event": {
                        "id": opp.event_id,
                        "name": opp.event_name,
                        "scheduled_time": opp.scheduled_time.isoformat(),
                        "hours_until": round(hours_until, 1),
                        "tournament": opp.tournament_name
                    },
                    "opportunities": [],
                    "summary": {
                        "total_opportunities": 0,
                        "total_volume": 0,
                        "market_types": set()
                    }
                }
            
            # Add opportunity to event
            events_map[event_id]["opportunities"].append({
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
                "available_liquidity": {
                    "side": opp.available_side,
                    "odds": opp.available_odds,
                    "amount": opp.available_liquidity_amount,
                    "formatted": f"{opp.available_side} @ {opp.available_odds:+d} (${opp.available_liquidity_amount:,.0f} available)"
                },
                "our_strategy": {
                    "side": opp.large_bet_side,  # We bet the same side as large bettor
                    "our_odds": opp.our_proposed_odds,  # Worse odds for us
                    "creates_liquidity_at": -opp.our_proposed_odds,  # Always opposite sign
                    "formatted": f"Bet {opp.large_bet_side} @ {opp.our_proposed_odds:+d} → Creates {opp.available_side} @ {(-opp.our_proposed_odds):+d}",
                    "explanation": f"By betting {opp.large_bet_side} at worse odds ({opp.our_proposed_odds:+d} vs {opp.large_bet_odds:+d}), we create better odds for {opp.available_side} bettors"
                }
            })
            
            # Update event summary
            events_map[event_id]["summary"]["total_opportunities"] += 1
            events_map[event_id]["summary"]["total_volume"] += opp.large_bet_combined_size
            events_map[event_id]["summary"]["market_types"].add(opp.market_type)
        
        # Convert sets to lists for JSON serialization and sort opportunities within each event
        formatted_events = []
        for event_data in events_map.values():
            # Convert market_types set to list
            event_data["summary"]["market_types"] = list(event_data["summary"]["market_types"])
            
            # Sort opportunities within event by market type, then by combined size
            event_data["opportunities"].sort(
                key=lambda x: (x["market"]["type"], -x["large_bet"]["combined_size"])
            )
            
            formatted_events.append(event_data)
        
        # Sort events by hours until game start, then by event ID
        formatted_events.sort(key=lambda x: (x["event"]["hours_until"], x["event"]["id"]))
        
        # Calculate summary stats
        summary = {
            "total_events": len(formatted_events),
            "total_opportunities": len(opportunities),
            "total_volume": total_volume,
            "market_type_breakdown": market_type_counts,
            "average_opportunity_size": round(total_volume / len(opportunities), 0) if opportunities else 0
        }
        
        return {
            "success": True,
            "message": f"Scan complete - found {len(opportunities)} opportunities across {len(formatted_events)} events",
            "data": {
                "events": formatted_events,
                "summary": summary
            }
        }
        
    except Exception as e:
        logger.error(f"Error during opportunity scan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

@router.get("/ncaaf-events", response_model=Dict[str, Any])
async def get_ncaaf_events():
    """Get upcoming NCAAF events for the next 24 hours"""
    try:
        logger.info("📅 Fetching upcoming NCAAF events...")
        
        # Use the market scanning service to get events (reuse existing logic)
        events = await market_scanning_service._get_upcoming_events()
        
        formatted_events = []
        for event in events:
            hours_until = (event.scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
            
            formatted_events.append({
                "id": event.event_id,
                "name": event.display_name,
                "home_team": event.home_team,
                "away_team": event.away_team,
                "scheduled_time": event.scheduled_time.isoformat(),
                "hours_until": round(hours_until, 1),
                "status": event.status,
                "tournament": event.tournament_name
            })
        
        # Sort by scheduled time
        formatted_events.sort(key=lambda x: x["hours_until"])
        
        return {
            "success": True,
            "message": f"Found {len(formatted_events)} upcoming NCAAF events",
            "data": {
                "events": formatted_events,
                "scan_window_hours": 24,
                "current_time": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching NCAAF events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {str(e)}")

@router.get("/test-market-data/{event_id}", response_model=Dict[str, Any])
async def test_market_data(event_id: str):
    """Test market data retrieval and analysis for a specific event"""
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

@router.get("/debug-scan/{event_id}", response_model=Dict[str, Any])
async def debug_single_event_scan(event_id: str):
    """Debug the scanning process for a single event"""
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
                ]
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug scan failed: {str(e)}")

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
                
                # Show structure details
                if market.get('type') == 'moneyline':
                    market_info['structure'] = 'moneyline - uses selections directly'
                    market_info['selections_preview'] = [
                        {
                            "side_index": i,
                            "selections_in_side": len(side) if side else 0,
                            "first_selection_preview": side[0].get('display_name') if side and len(side) > 0 else None
                        }
                        for i, side in enumerate(market.get('selections', [])[:2])  # Show first 2 sides
                    ]
                else:
                    market_info['structure'] = f'{market.get("type")} - should use market_lines'
                    if market.get('market_lines'):
                        market_info['market_lines_preview'] = [
                            {
                                "line_index": i,
                                "line_value": line.get('line', 'No line value'),
                                "line_name": line.get('name', 'No name'),
                                "selections_groups": len(line.get('selections', [])),
                                "first_group_size": len(line.get('selections', [])[0]) if line.get('selections') and len(line.get('selections')) > 0 else 0
                            }
                            for i, line in enumerate(market.get('market_lines', [])[:2])  # Show first 2 lines
                        ]
                
                game_line_markets.append(market_info)
        
        return {
            "success": True,
            "message": f"Market structure analysis for event {event_id}",
            "data": {
                "event_id": event_id,
                "game_line_markets_found": len(game_line_markets),
                "markets": game_line_markets
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing market structure: {str(e)}")

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
                    "min_individual_threshold": 2500.0,  # Hardcoded value from service
                    "undercut_improvement": settings.undercut_improvement,
                    "max_exposure_total": settings.max_exposure_total,
                    "commission_rate": settings.prophetx_commission_rate
                },
                "environment": {
                    "data_source": "production",
                    "betting_environment": settings.prophetx_betting_environment,
                    "betting_url": settings.betting_base_url
                },
                "validation": validation,
                "odds_ladder_info": {
                    "total_valid_odds": len(market_scanning_service.PROPHETX_ODDS_LADDER) if hasattr(market_scanning_service, 'PROPHETX_ODDS_LADDER') else "Not loaded",
                    "sample_negative_odds": [-110, -109, -108, -107, -106, -105],
                    "sample_positive_odds": [100, 101, 102, 103, 104, 105]
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting settings: {str(e)}")

@router.get("/test-odds-ladder")
async def test_odds_ladder():
    """Test the ProphetX odds ladder functionality for both better and worse odds"""
    try:
        test_cases = [
            (-140, "Large bettor got -140, we should take worse odds (e.g., -142)"),
            (-110, "Large bettor got -110, we should take worse odds (e.g., -111)"), 
            (140, "Large bettor got +140, we should take worse odds (e.g., +138)"),
            (150, "Large bettor got +150, we should take worse odds (e.g., +148)"),
            (-188, "Test -188 → should go to -190 (worse for us)")
        ]
        
        results = []
        for odds, description in test_cases:
            # Test worse odds for us (what we want for undercutting)
            worse_odds = market_scanning_service._find_next_valid_odds(odds, better_for_bettor=False)
            better_odds = market_scanning_service._find_next_valid_odds(odds, better_for_bettor=True)
            
            # Calculate what liquidity odds we create
            our_liquidity_odds = -worse_odds  # Always opposite sign
            their_liquidity_odds = -odds      # Always opposite sign
            
            results.append({
                "large_bettor_odds": odds,
                "our_odds_worse": worse_odds,
                "our_odds_better": better_odds,
                "description": description,
                "liquidity_comparison": {
                    "their_liquidity_odds": their_liquidity_odds,
                    "our_liquidity_odds": our_liquidity_odds,
                    "improvement": our_liquidity_odds - their_liquidity_odds,
                    "better_for_other_bettors": (our_liquidity_odds > their_liquidity_odds) if their_liquidity_odds > 0 else (our_liquidity_odds < their_liquidity_odds)
                },
                "example": f"Large bet: {odds:+d} → We bet: {worse_odds:+d} → Creates liquidity at {our_liquidity_odds:+d} vs their {their_liquidity_odds:+d}"
            })
        
        return {
            "success": True,
            "message": "Odds ladder testing complete",
            "data": {
                "test_results": results,
                "total_valid_odds": len(market_scanning_service.PROPHETX_ODDS_LADDER),
                "strategy_explanation": "We take WORSE odds than the large bettor to create BETTER liquidity odds for other bettors, ensuring our bet gets filled first"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Odds ladder test failed: {str(e)}")