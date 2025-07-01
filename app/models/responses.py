#!/usr/bin/env python3
"""
Response Models for ProphetX FastAPI
Pydantic models for outgoing API responses
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# =============================================================================
# Authentication Response Models
# =============================================================================

class AuthStatus(BaseModel):
    """Authentication status response"""
    authenticated: bool = Field(..., description="Whether user is authenticated")
    access_token_valid: bool = Field(..., description="Access token validity")
    refresh_token_valid: bool = Field(..., description="Refresh token validity")
    access_expires_in_seconds: int = Field(..., description="Access token expiry time")
    refresh_expires_in_seconds: int = Field(..., description="Refresh token expiry time")
    access_expires_at: Optional[str] = Field(None, description="Access token expiry timestamp")
    refresh_expires_at: Optional[str] = Field(None, description="Refresh token expiry timestamp")

# =============================================================================
# Market Data Response Models
# =============================================================================

class TournamentInfo(BaseModel):
    """Tournament information"""
    id: int = Field(..., description="Tournament ID")
    name: str = Field(..., description="Tournament name")
    sport_name: str = Field(..., description="Sport name")
    category_name: Optional[str] = Field(None, description="Category name")

class EventInfo(BaseModel):
    """Event information"""
    event_id: int = Field(..., description="Event ID")
    display_name: str = Field(..., description="Event display name")
    tournament_name: Optional[str] = Field(None, description="Tournament name")
    scheduled: Optional[str] = Field(None, description="Scheduled time")
    status: Optional[str] = Field(None, description="Event status")

class MarketInfo(BaseModel):
    """Market information"""
    market_id: int = Field(..., description="Market ID")
    market_name: str = Field(..., description="Market name")
    market_type: str = Field(..., description="Market type")
    status: str = Field(..., description="Market status")

# =============================================================================
# Betting Opportunity Models
# =============================================================================

class OriginalBet(BaseModel):
    """Information about the original bet we're following"""
    team_name: str = Field(..., description="Team/selection name")
    odds: int = Field(..., description="Original bet odds")
    stake: float = Field(..., description="Original bet stake amount")
    display: str = Field(..., description="Human-readable bet description")

class OurBet(BaseModel):
    """Information about our follow bet"""
    team_name: str = Field(..., description="Team/selection name")
    odds: int = Field(..., description="Our bet odds")
    stake: float = Field(..., description="Our bet stake amount")
    display: str = Field(..., description="Human-readable bet description")

class BetPlacementInfo(BaseModel):
    """Information needed for bet placement"""
    line_id: str = Field(..., description="Line ID for bet placement")
    competitor_id: Optional[int] = Field(None, description="Competitor ID")
    outcome_id: Optional[int] = Field(None, description="Outcome ID")
    odds: int = Field(..., description="Odds for bet placement")
    stake: float = Field(..., description="Stake amount")

class OpportunityAnalysis(BaseModel):
    """Analysis of the betting opportunity"""
    value_score: float = Field(..., description="Value score based on stake size")
    potential_profit: float = Field(..., description="Potential profit")
    potential_win: float = Field(..., description="Potential win amount")
    roi_percent: float = Field(..., description="Return on investment percentage")
    undercut_explanation: str = Field(..., description="Explanation of undercut strategy")
    follow_money_logic: str = Field(..., description="Follow the money logic")

class BettingOpportunity(BaseModel):
    """Complete betting opportunity"""
    event_id: int = Field(..., description="Event ID")
    event_name: str = Field(..., description="Event name")
    market_name: str = Field(..., description="Market name")
    market_type: str = Field(..., description="Market type")
    market_id: Optional[int] = Field(None, description="Market ID")
    
    original_bet: OriginalBet = Field(..., description="Original bet information")
    our_bet: OurBet = Field(..., description="Our follow bet information")
    bet_placement: BetPlacementInfo = Field(..., description="Bet placement details")
    analysis: OpportunityAnalysis = Field(..., description="Opportunity analysis")
    
    updated_at: Optional[int] = Field(None, description="Last updated timestamp")
    is_valid_follow: bool = Field(True, description="Whether this is a valid follow opportunity")

# =============================================================================
# Bet Placement Response Models
# =============================================================================

class BetResult(BaseModel):
    """Result of a bet placement"""
    success: bool = Field(..., description="Whether bet was successful")
    bet_id: Optional[str] = Field(None, description="Bet ID from ProphetX")
    external_id: str = Field(..., description="Our external bet ID")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    bet_data: Optional[Dict[str, Any]] = Field(None, description="Original bet data sent")
    placed_at: Optional[str] = Field(None, description="Timestamp when bet was placed")

class BetPlacementSummary(BaseModel):
    """Summary of multiple bet placements"""
    total: int = Field(..., description="Total number of bet attempts")
    successful: int = Field(..., description="Number of successful bets")
    failed: int = Field(..., description="Number of failed bets")
    bet_size_used: float = Field(..., description="Bet size used")
    results: List[BetResult] = Field(..., description="Individual bet results")

# =============================================================================
# Analysis Response Models
# =============================================================================

class OddsValidationResponse(BaseModel):
    """Response for odds validation"""
    odds: int = Field(..., description="Original odds")
    is_valid: bool = Field(..., description="Whether odds are valid")
    message: str = Field(..., description="Validation message")

class OddsUndercutResponse(BaseModel):
    """Response for odds undercut calculation"""
    original_odds: int = Field(..., description="Original odds")
    undercut_odds: Optional[int] = Field(None, description="Calculated undercut odds")
    explanation: Optional[str] = Field(None, description="Undercut explanation")
    profit_metrics: Optional[Dict[str, float]] = Field(None, description="Profit calculations")

# =============================================================================
# Configuration Response Models
# =============================================================================

class ConfigSettings(BaseModel):
    """Configuration settings"""
    sandbox: bool = Field(..., description="Sandbox mode")
    min_stake_threshold: int = Field(..., description="Minimum stake threshold")
    undercut_amount: int = Field(..., description="Undercut amount")
    max_bet_size: int = Field(..., description="Maximum bet size")
    target_sports: List[str] = Field(..., description="Target sports")
    default_bet_size: float = Field(..., description="Default bet size")
    dry_run_mode: bool = Field(..., description="Dry run mode")
    prophetx_base_url: str = Field(..., description="ProphetX base URL")

# =============================================================================
# Generic Response Models
# =============================================================================

class APIResponse(BaseModel):
    """Generic API response"""
    success: bool = Field(..., description="Whether request was successful")
    message: str = Field(..., description="Response message")
    data: Optional[Any] = Field(None, description="Response data")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Response timestamp")

class ScanResponse(BaseModel):
    """Market scan response"""
    scan_type: str = Field(..., description="Type of scan performed")
    opportunities_found: int = Field(..., description="Number of opportunities found")
    opportunities: List[BettingOpportunity] = Field(..., description="List of opportunities")
    scan_duration_seconds: float = Field(..., description="Scan duration")
    events_scanned: int = Field(..., description="Number of events scanned")
    markets_scanned: int = Field(..., description="Number of markets scanned")

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    timestamp: str = Field(..., description="Response timestamp")
    environment: str = Field(..., description="Environment (sandbox/production)")
    settings: ConfigSettings = Field(..., description="Current settings")

# Fix the forward reference in MultipleBetRequest
# This allows the circular import to work properly
from app.models.requests import MultipleBetRequest
MultipleBetRequest.model_rebuild()