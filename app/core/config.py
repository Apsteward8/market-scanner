#!/usr/bin/env python3
"""
Configuration Management for ProphetX Market Scanner
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional, List, Dict, Any
import os

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # =============================================================================
    # ProphetX API Credentials
    # =============================================================================
    prophetx_production_access_key: str = Field(..., description="ProphetX production access key")
    prophetx_production_secret_key: str = Field(..., description="ProphetX production secret key")
    prophetx_sandbox_access_key: str = Field(..., description="ProphetX sandbox access key")
    prophetx_sandbox_secret_key: str = Field(..., description="ProphetX sandbox secret key")
    
    # =============================================================================
    # ProphetX Environment Settings
    # =============================================================================
    prophetx_betting_environment: str = Field("sandbox", description="Where to place bets: 'production' or 'sandbox'")
    
    # =============================================================================
    # Market Scanner Strategy Settings  
    # =============================================================================
    min_stake_threshold: float = Field(10000.0, description="Minimum combined stake + value to follow")
    min_individual_threshold: float = Field(2500.0, description="Minimum individual stake and value required")
    undercut_improvement: int = Field(1, description="Odds improvement points (deprecated - now uses odds ladder)")
    
    # =============================================================================
    # Risk Management Settings
    # =============================================================================
    max_exposure_total: float = Field(10000.0, description="Maximum total portfolio exposure")
    
    # =============================================================================
    # API and Performance Settings
    # =============================================================================
    api_debug: bool = Field(False, description="Enable API debug logging")
    max_concurrent_requests: int = Field(10, description="Maximum concurrent API requests")
    request_timeout_seconds: int = Field(30, description="API request timeout in seconds")
    
    # =============================================================================
    # Database and Logging Settings
    # =============================================================================
    database_url: str = Field("sqlite:///./market_scanner.db", description="Database connection URL")
    log_level: str = Field("INFO", description="Logging level")
    save_scan_history: bool = Field(True, description="Whether to save scan history to database")
    
    # =============================================================================
    # ProphetX Commission Settings
    # =============================================================================
    prophetx_commission_rate: float = Field(0.03, description="ProphetX commission rate on winning bets")
    break_even_buffer: float = Field(0.01, description="Buffer above break-even for profitability")

    # =============================================================================
    # Multi-Sport Configuration
    # =============================================================================
    target_sports: str = Field("ncaaf,mlb", description="Comma-separated list of sports to scan")
    scan_window_hours: int = Field(24, description="Hours to look ahead for events")
    
    # ProphetX Tournament IDs  
    ncaaf_tournament_id: str = Field("27653", description="ProphetX NCAAF tournament ID")
    mlb_tournament_id: Optional[str] = Field(None, description="ProphetX MLB tournament ID")
    nfl_tournament_id: Optional[str] = Field(None, description="ProphetX NFL tournament ID")
    nba_tournament_id: Optional[str] = Field(None, description="ProphetX NBA tournament ID")
    nhl_tournament_id: Optional[str] = Field(None, description="ProphetX NHL tournament ID")
    wnba_tournament_id: Optional[str] = Field(None, description="ProphetX WNBA tournament ID")
    champions_league_tournament_id: Optional[str] = Field(None, description="ProphetX Champions League tournament ID")

    # =============================================================================
    # Computed Properties
    # =============================================================================
    @property
    def production_base_url(self) -> str:
        """ProphetX production API base URL"""
        return "https://cash.api.prophetx.co"
    
    @property
    def sandbox_base_url(self) -> str:
        """ProphetX sandbox API base URL"""
        return "https://api-ss-sandbox.betprophet.co"
    
    @property
    def betting_base_url(self) -> str:
        """Base URL for betting operations"""
        return self.production_base_url if self.prophetx_betting_environment == "production" else self.sandbox_base_url
    
    @property
    def data_base_url(self) -> str:
        """Base URL for data operations (always production)"""
        return self.production_base_url
    
    @property
    def betting_credentials(self) -> tuple[str, str]:
        """Get betting credentials based on environment"""
        if self.prophetx_betting_environment == "production":
            return (self.prophetx_production_access_key, self.prophetx_production_secret_key)
        else:
            return (self.prophetx_sandbox_access_key, self.prophetx_sandbox_secret_key)
    
    @property
    def data_credentials(self) -> tuple[str, str]:
        """Get data credentials (always production)"""
        return (self.prophetx_production_access_key, self.prophetx_production_secret_key)
    
    @property
    def target_sports_list(self) -> List[str]:
        """Parse target sports from comma-separated string"""
        return [sport.strip().lower() for sport in self.target_sports.split(',') if sport.strip()]
    
    @property
    def sport_tournament_mapping(self) -> Dict[str, str]:
        """Get mapping of sport names to tournament IDs"""
        mapping = {}
        if 'ncaaf' in self.target_sports_list and self.ncaaf_tournament_id:
            mapping['ncaaf'] = self.ncaaf_tournament_id
        if 'mlb' in self.target_sports_list and self.mlb_tournament_id:
            mapping['mlb'] = self.mlb_tournament_id
        if 'nfl' in self.target_sports_list and self.nfl_tournament_id:
            mapping['nfl'] = self.nfl_tournament_id
        if 'nba' in self.target_sports_list and self.nba_tournament_id:
            mapping['nba'] = self.nba_tournament_id
        if 'nhl' in self.target_sports_list and self.nhl_tournament_id:
            mapping['nhl'] = self.nhl_tournament_id
        if 'wnba' in self.target_sports_list and self.wnba_tournament_id:
            mapping['wnba'] = self.wnba_tournament_id
        if 'champions_league' in self.target_sports_list and self.champions_league_tournament_id:
            mapping['champions_league'] = self.champions_league_tournament_id
        return mapping
    
    def get_sport_display_name(self, sport: str) -> str:
        """Get display name for a sport"""
        sport_names = {
            'ncaaf': 'NCAAF',
            'mlb': 'MLB', 
            'nfl': 'NFL',
            'nba': 'NBA',
            'nhl': 'NHL',
            'wnba': 'WNBA',
            'champions_league': 'Champions League'
        }
        return sport_names.get(sport.lower(), sport.upper())
    
    def validate_settings(self) -> dict:
        """Validate all settings and return validation results"""
        issues = []
        
        # Check API credentials
        if not self.prophetx_production_access_key or self.prophetx_production_access_key == "your_key_here":
            issues.append("Missing or invalid production access key")
        
        if not self.prophetx_production_secret_key or self.prophetx_production_secret_key == "your_secret_here":
            issues.append("Missing or invalid production secret key")
        
        if not self.prophetx_sandbox_access_key or self.prophetx_sandbox_access_key == "your_sandbox_access_key_here":
            issues.append("Missing or invalid sandbox access key")
        
        if not self.prophetx_sandbox_secret_key or self.prophetx_sandbox_secret_key == "your_sandbox_secret_key_here":
            issues.append("Missing or invalid sandbox secret key")
        
        # Check environment setting
        if self.prophetx_betting_environment not in ["production", "sandbox"]:
            issues.append(f"Invalid betting environment: {self.prophetx_betting_environment}")
        
        # Check thresholds
        if self.min_stake_threshold < 1000:
            issues.append(f"Min stake threshold too low: ${self.min_stake_threshold}")
        
        if self.min_individual_threshold < 100:
            issues.append(f"Min individual threshold too low: ${self.min_individual_threshold}")
        
        if self.min_individual_threshold * 2 > self.min_stake_threshold:
            issues.append("Individual thresholds are too high compared to combined threshold")
        
        # Check risk settings
        if self.max_exposure_total < 1000:
            issues.append(f"Max exposure too low: ${self.max_exposure_total}")
        
        # Check commission rate
        if not (0 <= self.prophetx_commission_rate <= 0.5):
            issues.append(f"Invalid commission rate: {self.prophetx_commission_rate}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "settings_summary": {
                "betting_environment": self.prophetx_betting_environment,
                "min_combined_threshold": self.min_stake_threshold,
                "min_individual_threshold": self.min_individual_threshold,
                "max_exposure": self.max_exposure_total,
                "commission_rate": f"{self.prophetx_commission_rate:.1%}"
            }
        }
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
_settings = None

def get_settings() -> Settings:
    """Get the global settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings