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
    min_stake_threshold: float = Field(12500.0, description="Global minimum combined threshold")
    min_individual_threshold: float = Field(5000.0, description="Global minimum individual threshold")
    undercut_improvement: int = Field(1, description="Odds improvement points (deprecated - now uses odds ladder)")
    
    # Sport-specific defaults (new)
    nfl_min_stake_threshold: Optional[float] = Field(None, description="NFL default minimum combined")
    nfl_min_individual_threshold: Optional[float] = Field(None, description="NFL default minimum individual")
    
    wnba_min_stake_threshold: Optional[float] = Field(None, description="WNBA default minimum combined")
    wnba_min_individual_threshold: Optional[float] = Field(None, description="WNBA default minimum individual")
    
    mlb_min_stake_threshold: Optional[float] = Field(None, description="MLB default minimum combined")
    mlb_min_individual_threshold: Optional[float] = Field(None, description="MLB default minimum individual")

    ncaaf_min_stake_threshold: Optional[float] = Field(None, description="NCAAF default minimum combined")
    ncaaf_min_individual_threshold: Optional[float] = Field(None, description="NCAAF default minimum individual")

    nhl_min_stake_threshold: Optional[float] = Field(None, description="NHL default minimum combined")
    nhl_min_individual_threshold: Optional[float] = Field(None, description="NHL default minimum individual")

    nba_min_stake_threshold: Optional[float] = Field(None, description="NBA default minimum combined")
    nba_min_individual_threshold: Optional[float] = Field(None, description="NBA default minimum individual")
    
    champions_league_min_stake_threshold: Optional[float] = Field(None, description="Champions League default minimum combined")
    champions_league_min_individual_threshold: Optional[float] = Field(None, description="Champions League default minimum individual")
    
    europa_league_min_stake_threshold: Optional[float] = Field(None, description="Europa League default minimum combined")
    europa_league_min_individual_threshold: Optional[float] = Field(None, description="Europa League default minimum individual")

    laliga_min_stake_threshold: Optional[float] = Field(None, description="LaLiga default minimum combined")
    laliga_min_individual_threshold: Optional[float] = Field(None, description="LaLiga default minimum individual")
    
    premier_league_min_stake_threshold: Optional[float] = Field(None, description="Premier League default minimum combined")
    premier_league_min_individual_threshold: Optional[float] = Field(None, description="Premier League default minimum individual")
    
    bundesliga_min_stake_threshold: Optional[float] = Field(None, description="Bundesliga default minimum combined")
    bundesliga_min_individual_threshold: Optional[float] = Field(None, description="Bundesliga default minimum individual")
    
    serie_a_min_stake_threshold: Optional[float] = Field(None, description="Serie A default minimum combined")
    serie_a_min_individual_threshold: Optional[float] = Field(None, description="Serie A default minimum individual")
    
    ligue_1_min_stake_threshold: Optional[float] = Field(None, description="Ligue 1 default minimum combined")
    ligue_1_min_individual_threshold: Optional[float] = Field(None, description="Ligue 1 default minimum individual")

    mls_min_stake_threshold: Optional[float] = Field(None, description="MLS default minimum combined")
    mls_min_individual_threshold: Optional[float] = Field(None, description="MLS default minimum individual")

    english_championship_min_stake_threshold: Optional[float] = Field(None, description="English Championship default minimum combined")
    english_championship_min_individual_threshold: Optional[float] = Field(None, description="English Championship default minimum individual")

    cfl_min_stake_threshold: Optional[float] = Field(None, description="CFL default minimum combined")
    cfl_min_individual_threshold: Optional[float] = Field(None, description="CFL default minimum individual")

    ufc_min_stake_threshold: Optional[float] = Field(None, description="UFC default minimum combined")
    ufc_min_individual_threshold: Optional[float] = Field(None, description="UFC default minimum individual")

    # Market-specific thresholds (new)
    nfl_spread_min_stake_threshold: Optional[float] = Field(None)
    nfl_spread_min_individual_threshold: Optional[float] = Field(None)
    nfl_total_min_stake_threshold: Optional[float] = Field(None)
    nfl_total_min_individual_threshold: Optional[float] = Field(None)
    nfl_moneyline_min_stake_threshold: Optional[float] = Field(None)
    nfl_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    wnba_spread_min_stake_threshold: Optional[float] = Field(None)
    wnba_spread_min_individual_threshold: Optional[float] = Field(None)
    wnba_total_min_stake_threshold: Optional[float] = Field(None)
    wnba_total_min_individual_threshold: Optional[float] = Field(None)
    wnba_moneyline_min_stake_threshold: Optional[float] = Field(None)
    wnba_moneyline_min_individual_threshold: Optional[float] = Field(None)

    ncaaf_spread_min_stake_threshold: Optional[float] = Field(None)
    ncaaf_spread_min_individual_threshold: Optional[float] = Field(None)
    ncaaf_total_min_stake_threshold: Optional[float] = Field(None)
    ncaaf_total_min_individual_threshold: Optional[float] = Field(None)
    ncaaf_moneyline_min_stake_threshold: Optional[float] = Field(None)
    ncaaf_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    mlb_spread_min_stake_threshold: Optional[float] = Field(None)
    mlb_spread_min_individual_threshold: Optional[float] = Field(None)
    mlb_total_min_stake_threshold: Optional[float] = Field(None)
    mlb_total_min_individual_threshold: Optional[float] = Field(None)
    mlb_moneyline_min_stake_threshold: Optional[float] = Field(None)
    mlb_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    nba_spread_min_stake_threshold: Optional[float] = Field(None)
    nba_spread_min_individual_threshold: Optional[float] = Field(None)
    nba_total_min_stake_threshold: Optional[float] = Field(None)
    nba_total_min_individual_threshold: Optional[float] = Field(None)
    nba_moneyline_min_stake_threshold: Optional[float] = Field(None)
    nba_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    nhl_spread_min_stake_threshold: Optional[float] = Field(None)
    nhl_spread_min_individual_threshold: Optional[float] = Field(None)
    nhl_total_min_stake_threshold: Optional[float] = Field(None)
    nhl_total_min_individual_threshold: Optional[float] = Field(None)
    nhl_moneyline_min_stake_threshold: Optional[float] = Field(None)
    nhl_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    champions_league_spread_min_stake_threshold: Optional[float] = Field(None)
    champions_league_spread_min_individual_threshold: Optional[float] = Field(None)
    champions_league_total_min_stake_threshold: Optional[float] = Field(None)
    champions_league_total_min_individual_threshold: Optional[float] = Field(None)
    champions_league_moneyline_min_stake_threshold: Optional[float] = Field(None)
    champions_league_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    europa_league_spread_min_stake_threshold: Optional[float] = Field(None)
    europa_league_spread_min_individual_threshold: Optional[float] = Field(None)
    europa_league_total_min_stake_threshold: Optional[float] = Field(None)
    europa_league_total_min_individual_threshold: Optional[float] = Field(None)
    europa_league_moneyline_min_stake_threshold: Optional[float] = Field(None)
    europa_league_moneyline_min_individual_threshold: Optional[float] = Field(None)

    laliga_spread_min_stake_threshold: Optional[float] = Field(None)
    laliga_spread_min_individual_threshold: Optional[float] = Field(None)
    laliga_total_min_stake_threshold: Optional[float] = Field(None)
    laliga_total_min_individual_threshold: Optional[float] = Field(None)
    laliga_moneyline_min_stake_threshold: Optional[float] = Field(None)
    laliga_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    premier_league_spread_min_stake_threshold: Optional[float] = Field(None)
    premier_league_spread_min_individual_threshold: Optional[float] = Field(None)
    premier_league_total_min_stake_threshold: Optional[float] = Field(None)
    premier_league_total_min_individual_threshold: Optional[float] = Field(None)
    premier_league_moneyline_min_stake_threshold: Optional[float] = Field(None)
    premier_league_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    bundesliga_spread_min_stake_threshold: Optional[float] = Field(None)
    bundesliga_spread_min_individual_threshold: Optional[float] = Field(None)
    bundesliga_total_min_stake_threshold: Optional[float] = Field(None)
    bundesliga_total_min_individual_threshold: Optional[float] = Field(None)
    bundesliga_moneyline_min_stake_threshold: Optional[float] = Field(None)
    bundesliga_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    serie_a_spread_min_stake_threshold: Optional[float] = Field(None)
    serie_a_spread_min_individual_threshold: Optional[float] = Field(None)
    serie_a_total_min_stake_threshold: Optional[float] = Field(None)
    serie_a_total_min_individual_threshold: Optional[float] = Field(None)
    serie_a_moneyline_min_stake_threshold: Optional[float] = Field(None)
    serie_a_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    ligue_1_spread_min_stake_threshold: Optional[float] = Field(None)
    ligue_1_spread_min_individual_threshold: Optional[float] = Field(None)
    ligue_1_total_min_stake_threshold: Optional[float] = Field(None)
    ligue_1_total_min_individual_threshold: Optional[float] = Field(None)
    ligue_1_moneyline_min_stake_threshold: Optional[float] = Field(None)
    ligue_1_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
    cfl_spread_min_stake_threshold: Optional[float] = Field(None)
    cfl_spread_min_individual_threshold: Optional[float] = Field(None)
    cfl_total_min_stake_threshold: Optional[float] = Field(None)
    cfl_total_min_individual_threshold: Optional[float] = Field(None)
    cfl_moneyline_min_stake_threshold: Optional[float] = Field(None)
    cfl_moneyline_min_individual_threshold: Optional[float] = Field(None)

    ufc_spread_min_stake_threshold: Optional[float] = Field(None)
    ufc_spread_min_individual_threshold: Optional[float] = Field(None)
    ufc_total_min_stake_threshold: Optional[float] = Field(None)
    ufc_total_min_individual_threshold: Optional[float] = Field(None)
    ufc_moneyline_min_stake_threshold: Optional[float] = Field(None)
    ufc_moneyline_min_individual_threshold: Optional[float] = Field(None)

    mls_spread_min_stake_threshold: Optional[float] = Field(None)
    mls_spread_min_individual_threshold: Optional[float] = Field(None)
    mls_total_min_stake_threshold: Optional[float] = Field(None)
    mls_total_min_individual_threshold: Optional[float] = Field(None)
    mls_moneyline_min_stake_threshold: Optional[float] = Field(None)
    mls_moneyline_min_individual_threshold: Optional[float] = Field(None)

    english_championship_spread_min_stake_threshold: Optional[float] = Field(None)
    english_championship_spread_min_individual_threshold: Optional[float] = Field(None)
    english_championship_total_min_stake_threshold: Optional[float] = Field(None)
    english_championship_total_min_individual_threshold: Optional[float] = Field(None)
    english_championship_moneyline_min_stake_threshold: Optional[float] = Field(None)
    english_championship_moneyline_min_individual_threshold: Optional[float] = Field(None)
    
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
    prophetx_commission_rate: float = Field(0.01, description="ProphetX commission rate on winning bets")
    break_even_buffer: float = Field(0.01, description="Buffer above break-even for profitability")

    # =============================================================================
    # Multi-Sport Configuration
    # =============================================================================
    target_sports: str = Field("ncaaf,mlb", description="Comma-separated list of sports to scan")
    scan_window_hours: int = Field(12, description="Hours to look ahead for events")
    
    # ProphetX Tournament IDs  
    ncaaf_tournament_id: str = Field("27653", description="ProphetX NCAAF tournament ID")
    mlb_tournament_id: Optional[str] = Field(None, description="ProphetX MLB tournament ID")
    nfl_tournament_id: Optional[str] = Field(None, description="ProphetX NFL tournament ID")
    nba_tournament_id: Optional[str] = Field(None, description="ProphetX NBA tournament ID")
    nhl_tournament_id: Optional[str] = Field(None, description="ProphetX NHL tournament ID")
    wnba_tournament_id: Optional[str] = Field(None, description="ProphetX WNBA tournament ID")
    champions_league_tournament_id: Optional[str] = Field(None, description="ProphetX Champions League tournament ID")
    europa_league_tournament_id: Optional[str] = Field(None, description="ProphetX Europa League tournament ID")
    laliga_tournament_id: Optional[str] = Field(None, description="ProphetX LaLiga tournament ID")
    premier_league_tournament_id: Optional[str] = Field(None, description="ProphetX Premier League tournament ID")
    bundesliga_tournament_id: Optional[str] = Field(None, description="ProphetX Bundesliga tournament ID")
    serie_a_tournament_id: Optional[str] = Field(None, description="ProphetX Serie A tournament ID")
    ligue_1_tournament_id: Optional[str] = Field(None, description="ProphetX Ligue 1 tournament ID")
    cfl_tournament_id: Optional[str] = Field(None, description="ProphetX CFL tournament ID")
    ufc_tournament_id: Optional[str] = Field(None, description="ProphetX UFC tournament ID")
    mls_tournament_id: Optional[str] = Field(None, description="ProphetX MLS tournament ID")
    english_championship_tournament_id: Optional[str] = Field(None, description="ProphetX English Championship tournament ID")

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
        if 'europa_league' in self.target_sports_list and self.europa_league_tournament_id:
            mapping['europa_league'] = self.europa_league_tournament_id
        if 'laliga' in self.target_sports_list and self.laliga_tournament_id:
            mapping['laliga'] = self.laliga_tournament_id
        if 'premier_league' in self.target_sports_list and self.premier_league_tournament_id:
            mapping['premier_league'] = self.premier_league_tournament_id
        if 'bundesliga' in self.target_sports_list and self.bundesliga_tournament_id:
            mapping['bundesliga'] = self.bundesliga_tournament_id
        if 'serie_a' in self.target_sports_list and self.serie_a_tournament_id:
            mapping['serie_a'] = self.serie_a_tournament_id
        if 'ligue_1' in self.target_sports_list and self.ligue_1_tournament_id:
            mapping['ligue_1'] = self.ligue_1_tournament_id
        if 'cfl' in self.target_sports_list and self.cfl_tournament_id:
            mapping['cfl'] = self.cfl_tournament_id
        if 'ufc' in self.target_sports_list and self.ufc_tournament_id:
            mapping['ufc'] = self.ufc_tournament_id
        if 'mls' in self.target_sports_list and self.mls_tournament_id:
            mapping['mls'] = self.mls_tournament_id
        if 'english_championship' in self.target_sports_list and self.english_championship_tournament_id:
            mapping['english_championship'] = self.english_championship_tournament_id
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
            'champions_league': 'Champions League',
            'europa_league': 'Europa League',
            'laliga': 'LaLiga',
            'premier_league': 'Premier League',
            'bundesliga': 'Bundesliga',
            'serie_a': 'Serie A',
            'ligue_1': 'Ligue 1',
            'cfl': 'CFL',
            'ufc': 'UFC',
            'mls': 'MLS',
            'english_championship': 'English Championship'
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
        
    def get_threshold(self, sport: str, market_type: str, threshold_type: str) -> float:
        """
        Get the appropriate threshold using hierarchical priority:
        1. Market-specific for sport (highest priority)
        2. Sport-specific default (medium priority)  
        3. Global default (lowest priority)
        """
        sport_key = sport.lower()
        market_key = market_type.lower()
        
        # Normalize market type names
        if market_key in ['total', 'totals']:
            market_key = 'total'
        
        # 1. Try market-specific threshold first (highest priority)
        market_specific_attr = f"{sport_key}_{market_key}_{threshold_type.lower()}"
        market_specific_value = getattr(self, market_specific_attr, None)
        if market_specific_value is not None:
            return market_specific_value
        
        # 2. Try sport-specific default (medium priority)
        sport_specific_attr = f"{sport_key}_{threshold_type.lower()}"  
        sport_specific_value = getattr(self, sport_specific_attr, None)
        if sport_specific_value is not None:
            return sport_specific_value
        
        # 3. Fall back to global default (lowest priority)
        global_attr = threshold_type.lower()
        return getattr(self, global_attr)
    
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