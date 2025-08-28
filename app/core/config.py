#!/usr/bin/env python3
"""
Configuration Management for ProphetX Market Scanner
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional
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
    undercut_improvement: int = Field(1, description="Odds improvement points")
    
    # =============================================================================
    # Risk Management
    # =============================================================================
    max_exposure_total: float = Field(10000.0, description="Maximum total portfolio exposure")
    
    # =============================================================================
    # API and Performance Settings
    # =============================================================================
    api_debug: bool = Field(False, description="Enable API debug logging")
    max_concurrent_requests: int = Field(10, description="Maximum concurrent API requests")
    request_timeout_seconds: int = Field(30, description="API request timeout in seconds")
    
    # =============================================================================
    # Database and Logging
    # =============================================================================
    database_url: str = Field("sqlite:///./market_scanner.db", description="Database connection string")
    log_level: str = Field("INFO", description="Logging level")
    save_scan_history: bool = Field(True, description="Save scan history to database")
    
    # =============================================================================
    # ProphetX Commission Settings
    # =============================================================================
    prophetx_commission_rate: float = Field(0.03, description="ProphetX commission rate (3%)")
    break_even_buffer: float = Field(0.01, description="Buffer above break-even for profitability")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    @property
    def is_production_betting(self) -> bool:
        """Check if we're betting in production environment"""
        return self.prophetx_betting_environment.lower() == "production"
    
    @property
    def betting_access_key(self) -> str:
        """Get the appropriate access key for betting environment"""
        if self.is_production_betting:
            return self.prophetx_production_access_key
        else:
            return self.prophetx_sandbox_access_key
    
    @property
    def betting_secret_key(self) -> str:
        """Get the appropriate secret key for betting environment"""  
        if self.is_production_betting:
            return self.prophetx_production_secret_key
        else:
            return self.prophetx_sandbox_secret_key
    
    @property
    def betting_base_url(self) -> str:
        """Get the appropriate base URL for betting environment"""
        if self.is_production_betting:
            return "https://cash.api.prophetx.co"
        else:
            return "https://api-ss-sandbox.betprophet.co"
    
    def validate_settings(self) -> dict:
        """Validate critical settings and return status"""
        issues = []
        
        # Check required API keys
        if not self.prophetx_production_access_key:
            issues.append("Missing PROPHETX_PRODUCTION_ACCESS_KEY")
        if not self.prophetx_production_secret_key:
            issues.append("Missing PROPHETX_PRODUCTION_SECRET_KEY")
            
        # Check betting environment keys
        if self.is_production_betting:
            if not self.prophetx_production_access_key or not self.prophetx_production_secret_key:
                issues.append("Production betting enabled but missing production credentials")
        else:
            if not self.prophetx_sandbox_access_key or not self.prophetx_sandbox_secret_key:
                issues.append("Sandbox betting enabled but missing sandbox credentials")
        
        # Check thresholds
        if self.min_stake_threshold < 1000:
            issues.append("MIN_STAKE_THRESHOLD should be at least $1000 for meaningful signals")
            
        if self.prophetx_commission_rate <= 0 or self.prophetx_commission_rate >= 0.1:
            issues.append("PROPHETX_COMMISSION_RATE should be between 0 and 10%")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "environment": {
                "data_fetching": "production",
                "betting": self.prophetx_betting_environment,
                "commission_rate": f"{self.prophetx_commission_rate*100:.1f}%",
                "min_threshold": f"${self.min_stake_threshold:,.0f}"
            }
        }

# Global settings instance
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get application settings (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

def reload_settings() -> Settings:
    """Reload settings from environment"""
    global _settings
    _settings = Settings()
    return _settings