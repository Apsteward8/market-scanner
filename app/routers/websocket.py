#!/usr/bin/env python3
"""
WebSocket Router
FastAPI endpoints for real-time WebSocket functionality
"""

import asyncio
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Dict, Any

from app.models.responses import APIResponse
from app.routers.auth import require_auth
from app.services.websocket_service import websocket_service

router = APIRouter()

@router.post("/connect", response_model=APIResponse)
async def start_websocket_connection(
    background_tasks: BackgroundTasks,
    auth_service = Depends(require_auth)
):
    """
    Start WebSocket connection for real-time event monitoring
    
    This starts a background WebSocket connection that will:
    - Monitor all selection changes (large bet detection)
    - Track your own bet status updates
    - Provide real-time market activity
    
    **Note**: Connection runs in background until stopped.
    """
    try:
        if websocket_service.is_connected:
            return APIResponse(
                success=False,
                message="WebSocket is already connected",
                data=websocket_service.get_connection_stats()
            )
        
        # Start WebSocket connection in background
        background_tasks.add_task(websocket_service.start_websocket_connection)
        
        return APIResponse(
            success=True,
            message="WebSocket connection starting in background",
            data={
                "status": "connecting",
                "note": "Use /websocket/status to check connection status",
                "large_bet_threshold": websocket_service.min_stake_for_alert
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting WebSocket: {str(e)}")

@router.post("/disconnect", response_model=APIResponse)
async def stop_websocket_connection(auth_service = Depends(require_auth)):
    """
    Stop WebSocket connection
    
    Stops the real-time event monitoring and closes the WebSocket connection.
    """
    try:
        await websocket_service.stop_connection()
        
        return APIResponse(
            success=True,
            message="WebSocket connection stopped",
            data=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping WebSocket: {str(e)}")

@router.get("/status", response_model=APIResponse)
async def get_websocket_status(auth_service = Depends(require_auth)):
    """
    Get WebSocket connection status and statistics
    
    Returns current connection status, event counts, and recent activity statistics.
    """
    try:
        stats = websocket_service.get_connection_stats()
        
        return APIResponse(
            success=True,
            message="WebSocket status retrieved",
            data=stats
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting WebSocket status: {str(e)}")

@router.get("/large-bets", response_model=APIResponse)
async def get_recent_large_bets(
    limit: int = Query(20, description="Maximum number of recent alerts to return"),
    auth_service = Depends(require_auth)
):
    """
    Get recent large bet alerts detected via WebSocket
    
    Returns the most recent large bets detected through real-time monitoring.
    These are potential opportunities for the "follow the money" strategy.
    """
    try:
        recent_bets = websocket_service.get_recent_large_bets(limit)
        
        return APIResponse(
            success=True,
            message=f"Retrieved {len(recent_bets)} recent large bet alerts",
            data={
                "large_bets": recent_bets,
                "threshold": websocket_service.min_stake_for_alert,
                "total_detected": websocket_service.large_bets_detected
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting large bets: {str(e)}")

@router.post("/config/auto-betting", response_model=APIResponse)
async def configure_auto_betting(
    enabled: bool = Query(..., description="Enable or disable auto-betting"),
    auth_service = Depends(require_auth)
):
    """
    Configure auto-betting on large bet alerts
    
    When enabled, the system will automatically analyze large bets detected
    via WebSocket and potentially place follow bets.
    
    **WARNING**: This will place real bets automatically! Use with caution.
    """
    try:
        websocket_service.set_auto_betting(enabled)
        
        warning = "⚠️ Auto-betting ENABLED - real bets may be placed automatically!" if enabled else ""
        
        return APIResponse(
            success=True,
            message=f"Auto-betting {'enabled' if enabled else 'disabled'}",
            data={
                "auto_betting_enabled": enabled,
                "warning": warning,
                "note": "Auto-betting respects dry_run_mode and bet size limits"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configuring auto-betting: {str(e)}")

@router.post("/config/alert-threshold", response_model=APIResponse)
async def set_alert_threshold(
    threshold: int = Query(..., description="Minimum stake amount for large bet alerts"),
    auth_service = Depends(require_auth)
):
    """
    Set minimum stake threshold for large bet alerts
    
    Only bets with stakes above this threshold will trigger alerts.
    Lower values = more alerts, higher values = fewer but more significant alerts.
    """
    try:
        if threshold <= 0:
            raise HTTPException(status_code=400, detail="Threshold must be positive")
        
        websocket_service.set_min_stake_threshold(threshold)
        
        return APIResponse(
            success=True,
            message=f"Alert threshold set to ${threshold:,}",
            data={
                "threshold": threshold,
                "note": "Only bets above this amount will trigger alerts"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting alert threshold: {str(e)}")

@router.post("/test-connection", response_model=APIResponse)
async def test_websocket_connection(auth_service = Depends(require_auth)):
    """
    Test WebSocket connection capability
    
    Tests whether WebSocket connection can be established without starting
    the full monitoring service.
    """
    try:
        # Test getting WebSocket config
        config = await websocket_service.get_websocket_config()
        
        return APIResponse(
            success=True,
            message="WebSocket connection test successful",
            data={
                "websocket_config": config,
                "status": "ready_to_connect",
                "note": "Use /websocket/connect to start full monitoring"
            }
        )
        
    except Exception as e:
        return APIResponse(
            success=False,
            message="WebSocket connection test failed",
            data={"error": str(e)}
        )

@router.post("/simulate-large-bet", response_model=APIResponse)
async def simulate_large_bet_alert(
    selection_name: str = Query("Test Selection", description="Name of the selection"),
    odds: int = Query(-110, description="Odds of the bet"),
    stake: float = Query(5000.0, description="Stake amount"),
    auth_service = Depends(require_auth)
):
    """
    Simulate a large bet alert for testing
    
    Creates a fake large bet alert to test the opportunity detection
    and auto-betting logic without waiting for real large bets.
    
    **Use for testing only!**
    """
    try:
        from app.services.websocket_service import LargeBetAlert
        import time
        
        # Create a simulated alert
        alert = LargeBetAlert(
            sport_event_id=99999,
            market_id=99999,
            selection_name=selection_name,
            odds=odds,
            stake=stake,
            line_id="simulated_line_id",
            competitor_id=None,
            timestamp=int(time.time() * 1000000),
            alert_score=stake / 1000
        )
        
        # Process the simulated alert
        await websocket_service.process_large_bet_opportunity(alert)
        
        # Add to alerts list
        websocket_service.large_bet_alerts.append(alert)
        websocket_service.large_bets_detected += 1
        
        return APIResponse(
            success=True,
            message="Simulated large bet alert processed",
            data={
                "simulated_alert": {
                    "selection_name": selection_name,
                    "odds": odds,
                    "stake": stake,
                    "alert_score": alert.alert_score
                },
                "note": "Check /websocket/large-bets to see the simulated alert"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error simulating large bet: {str(e)}")

@router.get("/debug", response_model=APIResponse)
async def debug_websocket_connection(auth_service = Depends(require_auth)):
    """
    Debug WebSocket connection issues
    
    Provides detailed information about WebSocket configuration and connection status.
    """
    try:
        # Get WebSocket config
        try:
            config = await websocket_service.get_websocket_config()
            config_status = "✅ Success"
        except Exception as e:
            config = None
            config_status = f"❌ Failed: {str(e)}"
        
        # Check connection status
        stats = websocket_service.get_connection_stats()
        
        debug_info = {
            "websocket_config_test": config_status,
            "websocket_config": config,
            "connection_status": stats,
            "pusher_info": {
                "note": "ProphetX uses Pusher for WebSocket connections",
                "expected_url_format": "wss://ws-{cluster}.pusher.com/app/{key}",
                "connection_steps": [
                    "1. Get config from /websocket/connection-config",
                    "2. Connect to Pusher WebSocket using config",
                    "3. Register subscriptions with /mm/pusher",
                    "4. Listen for events"
                ]
            }
        }
        
        return APIResponse(
            success=True,
            message="WebSocket debug information",
            data=debug_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting debug info: {str(e)}")
async def get_websocket_help():
    """
    Get WebSocket functionality help and usage guide
    
    Explains how to use the WebSocket features for real-time opportunity detection.
    """
    try:
        help_info = {
            "overview": "WebSocket functionality provides real-time monitoring of ProphetX for instant large bet detection",
            
            "getting_started": [
                "1. Connect: POST /websocket/connect",
                "2. Monitor: GET /websocket/large-bets (poll every few seconds)",
                "3. Configure: POST /websocket/config/alert-threshold?threshold=5000",
                "4. Optional: Enable auto-betting with POST /websocket/config/auto-betting?enabled=true"
            ],
            
            "key_benefits": [
                "Instant notification when large bets (smart money) appear",
                "Real-time tracking of your own bet status",
                "Much faster than polling REST API endpoints",
                "Optional auto-betting for immediate response"
            ],
            
            "safety_features": [
                "Configurable stake thresholds for alerts",
                "Auto-betting respects dry_run_mode",
                "Bet size limits still apply",
                "Can be disabled at any time"
            ],
            
            "event_types_monitored": {
                "selections": "Individual bet placements - triggers large bet alerts",
                "wager": "Your own bet status updates",
                "matched_bet": "Market-wide betting activity",
                "market_selections": "Market liquidity changes"
            }
        }
        
        return APIResponse(
            success=True,
            message="WebSocket help information",
            data=help_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting help: {str(e)}")