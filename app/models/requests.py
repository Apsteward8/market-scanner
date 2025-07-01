#!/usr/bin/env python3
"""
Request Models for ProphetX FastAPI
Pydantic models for incoming API requests
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

# =============================================================================
# Enums
# =============================================================================

class ScanType(str, Enum):
    """Types of market scans"""
    TOURNAMENT = "tournament"
    EVENT = "event"
    COMPREHENSIVE = "comprehensive"

class BetStatus(str, Enum):
    """Bet placement status"""
    PENDING = "pending"
    PLACED = "placed"
    MATCHED = "matched"
    FAILED = "failed"
    CANCELLED = "cancelled"

# =============================================================================
# Authentication Request Models
# =============================================================================

class AuthCredentials(BaseModel):
    """ProphetX authentication credentials"""
    access_key: str = Field(..., description="ProphetX access key")
    secret_key: str = Field(..., description="ProphetX secret key")
    sandbox: bool = Field(True, description="Use sandbox environment")

# =============================================================================
# Market Scanning Request Models
# =============================================================================

class ScanRequest(BaseModel):
    """Market scan request"""
    scan_type: ScanType = Field(..., description="Type of scan to perform")
    tournament_id: Optional[int] = Field(None, description="Specific tournament ID")
    event_id: Optional[int] = Field(None, description="Specific event ID")
    limit_events: Optional[int] = Field(None, description="Limit number of events to scan")

# =============================================================================
# Bet Placement Request Models
# =============================================================================

class BetPlacementRequest(BaseModel):
    """Request to place a single bet"""
    opportunity_id: Optional[str] = Field(None, description="Opportunity identifier")
    line_id: str = Field(..., description="Line ID")
    odds: int = Field(..., description="Bet odds")
    stake: float = Field(..., description="Bet stake amount")
    dry_run: bool = Field(True, description="Whether to simulate the bet")

class MultipleBetRequest(BaseModel):
    """Request to place multiple bets"""
    opportunities: List['BettingOpportunity'] = Field(..., description="List of opportunities")
    bet_size: Optional[float] = Field(None, description="Override bet size for all bets")
    dry_run: bool = Field(True, description="Whether to simulate bets")
    delay_seconds: float = Field(1.0, description="Delay between bet placements")

# =============================================================================
# Analysis Request Models
# =============================================================================

class OddsValidationRequest(BaseModel):
    """Request to validate odds"""
    odds: int = Field(..., description="Odds to validate")

class OddsUndercutRequest(BaseModel):
    """Request to calculate undercut odds"""
    original_odds: int = Field(..., description="Original odds to undercut")
    undercut_amount: int = Field(1, description="How aggressively to undercut")

# =============================================================================
# Configuration Request Models
# =============================================================================

class ConfigUpdateRequest(BaseModel):
    """Request to update configuration"""
    min_stake_threshold: Optional[int] = Field(None, description="Minimum stake threshold")
    undercut_amount: Optional[int] = Field(None, description="Undercut amount")
    max_bet_size: Optional[int] = Field(None, description="Maximum bet size")
    target_sports: Optional[List[str]] = Field(None, description="Target sports")
    default_bet_size: Optional[float] = Field(None, description="Default bet size")
    dry_run_mode: Optional[bool] = Field(None, description="Dry run mode")

# Forward reference resolution for MultipleBetRequest
# This will be resolved when responses.py is imported
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.responses import BettingOpportunity