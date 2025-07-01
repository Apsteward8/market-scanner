#!/usr/bin/env python3
"""
FastAPI Configuration Module
Handles application settings and ProphetX credentials
"""

import os
import json
from functools import lru_cache
from typing import List, Optional, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings using Pydantic BaseSettings"""
    
    # ProphetX API Credentials
    prophetx_access_key: str = Field(...)
    prophetx_secret_key: str = Field(...)
    
    # ProphetX Settings
    prophetx_sandbox: bool = Field(True)
    prophetx_min_stake: int = Field(5000)
    prophetx_undercut_amount: int = Field(1)
    prophetx_max_bet_size: int = Field(1000)
    prophetx_target_sports: str = Field("Baseball,American Football,Basketball")
    
    # API Settings
    api_title: str = "ProphetX Betting Tool API"
    api_version: str = "1.0.0"
    api_debug: bool = Field(False)
    
    # Database (SQLite for bet history)
    database_url: str = Field("sqlite:///./prophetx_bets.db")
    
    # Rate limiting
    rate_limit_calls_per_minute: int = Field(60)
    
    # Bet placement defaults
    default_bet_size: float = Field(5.0)
    dry_run_mode: bool = Field(True)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    @property
    def sandbox(self) -> bool:
        """Alias for prophetx_sandbox"""
        return self.prophetx_sandbox
    
    @property
    def min_stake_threshold(self) -> int:
        """Alias for prophetx_min_stake"""
        return self.prophetx_min_stake
    
    @property
    def undercut_amount(self) -> int:
        """Alias for prophetx_undercut_amount"""
        return self.prophetx_undercut_amount
    
    @property
    def max_bet_size(self) -> int:
        """Alias for prophetx_max_bet_size"""
        return self.prophetx_max_bet_size
    
    @property
    def target_sports(self) -> List[str]:
        """Parse target sports from comma-separated string"""
        return [sport.strip() for sport in self.prophetx_target_sports.split(',') if sport.strip()]
    
    @property
    def prophetx_base_url(self) -> str:
        """Get ProphetX API base URL based on environment"""
        if self.sandbox:
            return "https://api-ss-sandbox.betprophet.co"
        else:
            return "https://api-ss.betprophet.co"
    
    def to_dict(self) -> dict:
        """Convert settings to dictionary (safe for API responses)"""
        return {
            "sandbox": self.sandbox,
            "min_stake_threshold": self.min_stake_threshold,
            "undercut_amount": self.undercut_amount,
            "max_bet_size": self.max_bet_size,
            "target_sports": self.target_sports,
            "default_bet_size": self.default_bet_size,
            "dry_run_mode": self.dry_run_mode,
            "prophetx_base_url": self.prophetx_base_url
        }

@lru_cache()
def get_settings() -> Settings:
    """
    Get application settings (cached)
    This function is cached so settings are loaded once per app lifecycle
    """
    return Settings()

class ConfigManager:
    """Configuration management utilities"""
    
    @staticmethod
    def validate_credentials(access_key: str, secret_key: str) -> bool:
        """Validate that credentials are properly formatted"""
        if not access_key or not secret_key:
            return False
        
        # Basic validation - ProphetX keys should be hex strings
        if len(access_key) < 10 or len(secret_key) < 10:
            return False
            
        return True
    
    @staticmethod
    def create_sample_env_file(filepath: str = ".env") -> None:
        """Create a sample .env file with all configuration options"""
        sample_env = """# ProphetX API Credentials
PROPHETX_ACCESS_KEY=your_access_key_here
PROPHETX_SECRET_KEY=your_secret_key_here

# ProphetX Settings
PROPHETX_SANDBOX=true
PROPHETX_MIN_STAKE=5000
PROPHETX_UNDERCUT_AMOUNT=1
PROPHETX_MAX_BET_SIZE=1000
PROPHETX_TARGET_SPORTS=Baseball,American Football,Basketball

# API Settings
API_DEBUG=false

# Database
DATABASE_URL=sqlite:///./prophetx_bets.db

# Rate Limiting
RATE_LIMIT_CALLS_PER_MINUTE=60

# Bet Placement
DEFAULT_BET_SIZE=5.0
DRY_RUN_MODE=true
"""
        
        with open(filepath, 'w') as f:
            f.write(sample_env)
    
    @staticmethod
    def load_from_json(filepath: str) -> Optional[dict]:
        """Load configuration from JSON file"""
        try:
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    @staticmethod
    def save_to_json(config_dict: dict, filepath: str) -> bool:
        """Save configuration to JSON file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(config_dict, f, indent=2)
            return True
        except Exception:
            return False

# Global settings instance
settings = get_settings()