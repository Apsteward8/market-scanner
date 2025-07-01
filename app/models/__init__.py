#!/usr/bin/env python3
"""
Models Package
Exports commonly used Pydantic models for the ProphetX API
"""

# Request models
from .requests import (
    AuthCredentials,
    ScanRequest,
    BetPlacementRequest,
    MultipleBetRequest,
    OddsValidationRequest,
    OddsUndercutRequest,
    ConfigUpdateRequest,
    ScanType,
    BetStatus
)

# Response models
from .responses import (
    AuthStatus,
    TournamentInfo,
    EventInfo,
    MarketInfo,
    BettingOpportunity,
    OriginalBet,
    OurBet,
    BetPlacementInfo,
    OpportunityAnalysis,
    BetResult,
    BetPlacementSummary,
    OddsValidationResponse,
    OddsUndercutResponse,
    ConfigSettings,
    APIResponse,
    ScanResponse,
    HealthResponse
)

__all__ = [
    # Request models
    "AuthCredentials",
    "ScanRequest", 
    "BetPlacementRequest",
    "MultipleBetRequest",
    "OddsValidationRequest",
    "OddsUndercutRequest",
    "ConfigUpdateRequest",
    "ScanType",
    "BetStatus",
    
    # Response models
    "AuthStatus",
    "TournamentInfo",
    "EventInfo", 
    "MarketInfo",
    "BettingOpportunity",
    "OriginalBet",
    "OurBet",
    "BetPlacementInfo",
    "OpportunityAnalysis",
    "BetResult",
    "BetPlacementSummary", 
    "OddsValidationResponse",
    "OddsUndercutResponse",
    "ConfigSettings",
    "APIResponse",
    "ScanResponse",
    "HealthResponse"
]