#!/usr/bin/env python3
"""
Authentication Router
FastAPI endpoints for ProphetX authentication
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict

from app.models.requests import AuthCredentials
from app.models.responses import AuthStatus, APIResponse
from app.services.auth_service import auth_service

router = APIRouter()

@router.post("/login", response_model=APIResponse)
async def login(credentials: AuthCredentials = None):
    """
    Login to ProphetX API
    
    If credentials are provided, they will be used for this login.
    Otherwise, default credentials from environment will be used.
    """
    try:
        if credentials:
            # Use provided credentials
            auth_service.set_credentials(credentials.access_key, credentials.secret_key)
        else:
            # Use default credentials from environment
            auth_service.use_default_credentials()
        
        # Attempt login
        result = await auth_service.login()
        
        return APIResponse(
            success=True,
            message=result["message"],
            data={
                "access_expires_at": result["access_expires_at"],
                "refresh_expires_at": result["refresh_expires_at"],
                "environment": "sandbox" if auth_service.settings.sandbox else "production"
            }
        )
        
    except HTTPException as e:
        return APIResponse(
            success=False,
            message=f"Login failed: {e.detail}",
            data=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during login: {str(e)}")

@router.post("/refresh", response_model=APIResponse)
async def refresh_token():
    """
    Refresh the access token using the refresh token
    """
    try:
        result = await auth_service.refresh_access_token()
        
        return APIResponse(
            success=True,
            message=result["message"],
            data={
                "access_expires_at": result["access_expires_at"]
            }
        )
        
    except HTTPException as e:
        return APIResponse(
            success=False,
            message=f"Token refresh failed: {e.detail}",
            data=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during token refresh: {str(e)}")

@router.get("/status", response_model=AuthStatus)
async def get_auth_status():
    """
    Get current authentication status and token information
    """
    try:
        status = auth_service.get_token_status()
        
        if not status.get("authenticated", False):
            return AuthStatus(
                authenticated=False,
                access_token_valid=False,
                refresh_token_valid=False,
                access_expires_in_seconds=0,
                refresh_expires_in_seconds=0,
                access_expires_at=None,
                refresh_expires_at=None
            )
        
        return AuthStatus(
            authenticated=status["authenticated"],
            access_token_valid=status["access_token_valid"],
            refresh_token_valid=status["refresh_token_valid"],
            access_expires_in_seconds=status["access_expires_in_seconds"],
            refresh_expires_in_seconds=status["refresh_expires_in_seconds"],
            access_expires_at=status.get("access_expires_at"),
            refresh_expires_at=status.get("refresh_expires_at")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting auth status: {str(e)}")

@router.post("/test", response_model=APIResponse)
async def test_authentication():
    """
    Test the current authentication by making a simple API call to ProphetX
    """
    try:
        # Ensure we have valid authentication
        await auth_service.ensure_valid_token()
        
        # Get auth headers
        headers = await auth_service.get_auth_headers()
        
        # Make a simple test call to ProphetX API
        import requests
        test_url = f"{auth_service.base_url}/partner/mm/get_tournaments"
        
        response = requests.get(test_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            tournaments = data.get('data', {}).get('tournaments', [])
            
            return APIResponse(
                success=True,
                message="Authentication test successful",
                data={
                    "status_code": response.status_code,
                    "tournaments_found": len(tournaments),
                    "sample_tournament": tournaments[0].get('name', 'N/A') if tournaments else None,
                    "api_base_url": auth_service.base_url
                }
            )
        else:
            return APIResponse(
                success=False,
                message=f"Authentication test failed: HTTP {response.status_code}",
                data={
                    "status_code": response.status_code,
                    "response_text": response.text[:200]  # First 200 chars of error
                }
            )
            
    except HTTPException as e:
        return APIResponse(
            success=False,
            message=f"Authentication test failed: {e.detail}",
            data=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during auth test: {str(e)}")

@router.post("/logout", response_model=APIResponse)
async def logout():
    """
    Logout and clear authentication tokens
    """
    try:
        # Clear authentication state
        auth_service.is_authenticated = False
        auth_service.access_token = None
        auth_service.refresh_token = None
        auth_service.access_expire_time = None
        auth_service.refresh_expire_time = None
        
        return APIResponse(
            success=True,
            message="Logged out successfully",
            data=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during logout: {str(e)}")

# Dependency to ensure authentication
async def require_auth():
    """
    FastAPI dependency to ensure the user is authenticated
    """
    try:
        await auth_service.ensure_valid_token()
        return auth_service
    except HTTPException:
        raise HTTPException(status_code=401, detail="Authentication required. Please login first.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

# Dependency to get auth headers
async def get_auth_headers() -> Dict[str, str]:
    """
    FastAPI dependency to get authentication headers
    """
    try:
        return await auth_service.get_auth_headers()
    except HTTPException:
        raise HTTPException(status_code=401, detail="Authentication required. Please login first.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting auth headers: {str(e)}")