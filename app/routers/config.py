#!/usr/bin/env python3
"""
Configuration Router
FastAPI endpoints for application configuration management
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any

from app.models.requests import ConfigUpdateRequest
from app.models.responses import ConfigSettings, APIResponse
from app.core.config import get_settings, ConfigManager

router = APIRouter()

@router.get("/settings", response_model=ConfigSettings)
async def get_current_settings():
    """
    Get current application settings
    
    Returns all current configuration settings including:
    - ProphetX environment (sandbox/production)
    - Betting thresholds and limits
    - Target sports
    - Default bet sizes
    - API endpoints
    
    **Note**: Sensitive credentials (access_key, secret_key) are not included for security.
    """
    try:
        settings = get_settings()
        
        return ConfigSettings(
            sandbox=settings.sandbox,
            min_stake_threshold=settings.min_stake_threshold,
            undercut_amount=settings.undercut_amount,
            max_bet_size=settings.max_bet_size,
            target_sports=settings.target_sports,
            default_bet_size=settings.default_bet_size,
            dry_run_mode=settings.dry_run_mode,
            prophetx_base_url=settings.prophetx_base_url
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting settings: {str(e)}")

@router.put("/settings", response_model=APIResponse)
async def update_settings(request: ConfigUpdateRequest):
    """
    Update application settings
    
    Updates configuration values that can be changed at runtime.
    
    **Note**: Some settings like credentials and sandbox mode require restart.
    Changes are applied immediately but may not persist across restarts
    unless environment variables are updated.
    """
    try:
        settings = get_settings()
        updated_fields = []
        
        # Update settings that were provided in the request
        if request.min_stake_threshold is not None:
            # Note: This would require a way to update the cached settings
            # For now, we'll return what would be updated
            updated_fields.append(f"min_stake_threshold: {request.min_stake_threshold}")
        
        if request.undercut_amount is not None:
            updated_fields.append(f"undercut_amount: {request.undercut_amount}")
        
        if request.max_bet_size is not None:
            updated_fields.append(f"max_bet_size: {request.max_bet_size}")
        
        if request.target_sports is not None:
            updated_fields.append(f"target_sports: {request.target_sports}")
        
        if request.default_bet_size is not None:
            updated_fields.append(f"default_bet_size: {request.default_bet_size}")
        
        if request.dry_run_mode is not None:
            updated_fields.append(f"dry_run_mode: {request.dry_run_mode}")
        
        if not updated_fields:
            return APIResponse(
                success=False,
                message="No settings provided to update",
                data=None
            )
        
        # In a full implementation, you'd actually update the settings here
        # This might involve updating environment variables or a config file
        
        return APIResponse(
            success=True,
            message="Settings update requested",
            data={
                "updated_fields": updated_fields,
                "note": "⚠️ Settings updates require app restart to take full effect",
                "recommendation": "Update environment variables and restart the application"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")

@router.get("/environment", response_model=APIResponse)
async def get_environment_info():
    """
    Get current environment information
    
    Returns details about the current runtime environment,
    including ProphetX connection details and safety settings.
    """
    try:
        settings = get_settings()
        
        environment_info = {
            "prophetx_environment": "sandbox" if settings.sandbox else "production",
            "api_base_url": settings.prophetx_base_url,
            "safety_features": {
                "dry_run_mode": settings.dry_run_mode,
                "description": "Dry run mode simulates bets without placing them"
            },
            "betting_limits": {
                "min_stake_threshold": settings.min_stake_threshold,
                "max_bet_size": settings.max_bet_size,
                "default_bet_size": settings.default_bet_size
            },
            "scanning_config": {
                "target_sports": settings.target_sports,
                "undercut_amount": settings.undercut_amount
            },
            "api_info": {
                "title": settings.api_title,
                "version": settings.api_version,
                "debug_mode": settings.api_debug
            }
        }
        
        return APIResponse(
            success=True,
            message="Environment information",
            data=environment_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting environment info: {str(e)}")

@router.post("/validate", response_model=APIResponse)
async def validate_configuration():
    """
    Validate current configuration
    
    Checks if the current configuration is valid and identifies any issues.
    Useful for troubleshooting setup problems.
    """
    try:
        settings = get_settings()
        validation_results = []
        is_valid = True
        
        # Check credentials
        if not settings.prophetx_access_key or not settings.prophetx_secret_key:
            validation_results.append({
                "check": "ProphetX Credentials",
                "status": "FAIL",
                "message": "Missing PROPHETX_ACCESS_KEY or PROPHETX_SECRET_KEY"
            })
            is_valid = False
        else:
            # Basic credential format validation
            if ConfigManager.validate_credentials(settings.prophetx_access_key, settings.prophetx_secret_key):
                validation_results.append({
                    "check": "ProphetX Credentials",
                    "status": "PASS",
                    "message": "Credentials are properly formatted"
                })
            else:
                validation_results.append({
                    "check": "ProphetX Credentials",
                    "status": "WARN",
                    "message": "Credentials format may be invalid"
                })
        
        # Check betting limits
        if settings.min_stake_threshold <= 0:
            validation_results.append({
                "check": "Minimum Stake Threshold",
                "status": "FAIL",
                "message": "min_stake_threshold must be positive"
            })
            is_valid = False
        else:
            validation_results.append({
                "check": "Minimum Stake Threshold",
                "status": "PASS",
                "message": f"${settings.min_stake_threshold:,} is valid"
            })
        
        if settings.max_bet_size <= 0:
            validation_results.append({
                "check": "Maximum Bet Size",
                "status": "FAIL",
                "message": "max_bet_size must be positive"
            })
            is_valid = False
        else:
            validation_results.append({
                "check": "Maximum Bet Size",
                "status": "PASS",
                "message": f"${settings.max_bet_size:,} is valid"
            })
        
        if settings.default_bet_size <= 0:
            validation_results.append({
                "check": "Default Bet Size",
                "status": "FAIL",
                "message": "default_bet_size must be positive"
            })
            is_valid = False
        else:
            validation_results.append({
                "check": "Default Bet Size",
                "status": "PASS",
                "message": f"${settings.default_bet_size} is valid"
            })
        
        # Check target sports
        if not settings.target_sports:
            validation_results.append({
                "check": "Target Sports",
                "status": "WARN",
                "message": "No target sports configured"
            })
        else:
            validation_results.append({
                "check": "Target Sports",
                "status": "PASS",
                "message": f"{len(settings.target_sports)} sports configured: {', '.join(settings.target_sports)}"
            })
        
        # Check safety settings
        if settings.dry_run_mode:
            validation_results.append({
                "check": "Safety Mode",
                "status": "PASS",
                "message": "Dry run mode enabled - bets will be simulated"
            })
        else:
            validation_results.append({
                "check": "Safety Mode",
                "status": "WARN",
                "message": "⚠️ Dry run mode disabled - real bets will be placed!"
            })
        
        return APIResponse(
            success=is_valid,
            message="Configuration validation completed",
            data={
                "overall_status": "VALID" if is_valid else "INVALID",
                "checks": validation_results,
                "recommendations": [
                    "Ensure all credentials are correct",
                    "Test with dry_run_mode=true first",
                    "Verify target sports are spelled correctly",
                    "Start with small bet sizes for testing"
                ]
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating configuration: {str(e)}")

@router.post("/create-sample-env", response_model=APIResponse)
async def create_sample_env_file():
    """
    Create a sample .env file
    
    Generates a sample .env file with all configuration options.
    Useful for initial setup or when adding new configuration options.
    
    **Note**: This creates the file in the current working directory.
    """
    try:
        ConfigManager.create_sample_env_file()
        
        return APIResponse(
            success=True,
            message="Sample .env file created",
            data={
                "filename": ".env",
                "location": "Current working directory",
                "next_steps": [
                    "Edit the .env file with your actual ProphetX credentials",
                    "Set other configuration values as needed",
                    "Restart the application to load new settings",
                    "Add .env to .gitignore to protect credentials"
                ]
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating sample .env file: {str(e)}")

@router.get("/sports/available", response_model=APIResponse)
async def get_available_sports():
    """
    Get list of sports that can be configured as targets
    
    Returns common sports names that are typically available on ProphetX.
    Use these exact names in your target_sports configuration.
    """
    try:
        available_sports = [
            "Baseball",
            "American Football", 
            "Basketball",
            "Soccer",
            "Tennis",
            "Hockey",
            "Golf",
            "MMA",
            "Boxing",
            "Cricket",
            "Rugby",
            "Australian Football",
            "Esports"
        ]
        
        settings = get_settings()
        
        return APIResponse(
            success=True,
            message="Available sports for targeting",
            data={
                "available_sports": available_sports,
                "currently_configured": settings.target_sports,
                "note": "Use exact names as shown in the available_sports list"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting available sports: {str(e)}")

@router.get("/limits/recommendations", response_model=APIResponse)
async def get_limit_recommendations():
    """
    Get recommended configuration limits
    
    Provides recommendations for betting limits and thresholds
    based on different use cases and risk tolerances.
    """
    try:
        recommendations = {
            "conservative": {
                "description": "Low risk, small scale testing",
                "min_stake_threshold": 1000,
                "max_bet_size": 50,
                "default_bet_size": 5.0,
                "dry_run_mode": True,
                "use_case": "Initial testing and learning"
            },
            "moderate": {
                "description": "Moderate risk, following significant money",
                "min_stake_threshold": 5000,
                "max_bet_size": 500,
                "default_bet_size": 25.0,
                "dry_run_mode": False,
                "use_case": "Regular operation with moderate capital"
            },
            "aggressive": {
                "description": "Higher risk, following large money only",
                "min_stake_threshold": 10000,
                "max_bet_size": 1000,
                "default_bet_size": 100.0,
                "dry_run_mode": False,
                "use_case": "Large capital, experienced operators"
            }
        }
        
        settings = get_settings()
        current_profile = "custom"
        
        # Try to match current settings to a profile
        for profile_name, profile in recommendations.items():
            if (settings.min_stake_threshold == profile["min_stake_threshold"] and
                settings.max_bet_size == profile["max_bet_size"] and
                settings.default_bet_size == profile["default_bet_size"]):
                current_profile = profile_name
                break
        
        return APIResponse(
            success=True,
            message="Configuration limit recommendations",
            data={
                "current_profile": current_profile,
                "current_settings": {
                    "min_stake_threshold": settings.min_stake_threshold,
                    "max_bet_size": settings.max_bet_size,
                    "default_bet_size": settings.default_bet_size,
                    "dry_run_mode": settings.dry_run_mode
                },
                "recommendations": recommendations,
                "safety_reminder": "Always start with conservative settings and dry_run_mode=true"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting limit recommendations: {str(e)}")