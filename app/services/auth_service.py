#!/usr/bin/env python3
"""
ProphetX Authentication Service
Handles ProphetX API authentication and token management for FastAPI
"""

import requests
import time
from datetime import datetime, timezone
from typing import Optional, Dict
from fastapi import HTTPException

from app.core.config import get_settings

class ProphetXAuthService:
    """Service for handling ProphetX authentication"""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.prophetx_base_url
        
        # Token storage
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_expire_time: Optional[int] = None
        self.refresh_expire_time: Optional[int] = None
        
        # Track login status
        self.is_authenticated = False
        
        # Credentials (can be overridden)
        self.access_key: Optional[str] = None
        self.secret_key: Optional[str] = None
    
    def set_credentials(self, access_key: str, secret_key: str) -> None:
        """
        Set ProphetX credentials
        
        Args:
            access_key: ProphetX access key
            secret_key: ProphetX secret key
        """
        self.access_key = access_key
        self.secret_key = secret_key
        
        # Reset authentication state when credentials change
        self.is_authenticated = False
        self.access_token = None
        self.refresh_token = None
    
    def use_default_credentials(self) -> None:
        """Use credentials from settings/environment"""
        self.access_key = self.settings.prophetx_access_key
        self.secret_key = self.settings.prophetx_secret_key
    
    async def login(self) -> Dict:
        """
        Perform initial login to get access and refresh tokens
        
        Returns:
            dict: Login result with success status and token info
        """
        if not self.access_key or not self.secret_key:
            self.use_default_credentials()
        
        if not self.access_key or not self.secret_key:
            raise HTTPException(
                status_code=400,
                detail="ProphetX credentials not configured. Set PROPHETX_ACCESS_KEY and PROPHETX_SECRET_KEY."
            )
        
        url = f"{self.base_url}/partner/auth/login"
        payload = {
            "access_key": self.access_key,
            "secret_key": self.secret_key
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract token information
                token_data = data.get('data', {})
                
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')
                self.access_expire_time = token_data.get('access_expire_time')
                self.refresh_expire_time = token_data.get('refresh_expire_time')
                
                if self.access_token and self.refresh_token:
                    self.is_authenticated = True
                    
                    # Convert timestamps to readable format
                    access_expire_dt = datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc)
                    refresh_expire_dt = datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc)
                    
                    return {
                        "success": True,
                        "message": "Login successful",
                        "access_expires_at": access_expire_dt.isoformat(),
                        "refresh_expires_at": refresh_expire_dt.isoformat(),
                        "access_token_preview": f"{self.access_token[:20]}..." if self.access_token else None
                    }
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Login failed: Missing tokens in response"
                    )
                    
            else:
                error_detail = f"Login failed: HTTP {response.status_code} - {response.text}"
                raise HTTPException(status_code=400, detail=error_detail)
                
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Network error during login: {str(e)}")
    
    async def refresh_access_token(self) -> Dict:
        """
        Refresh the access token using the refresh token
        
        Returns:
            dict: Refresh result
        """
        if not self.refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token available")
        
        url = f"{self.base_url}/partner/auth/refresh"
        payload = {
            "refresh_token": self.refresh_token
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token_data = data.get('data', {})
                
                # Update access token info
                self.access_token = token_data.get('access_token')
                self.access_expire_time = token_data.get('access_expire_time')
                
                if self.access_token:
                    access_expire_dt = datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc)
                    return {
                        "success": True,
                        "message": "Token refreshed successfully",
                        "access_expires_at": access_expire_dt.isoformat()
                    }
                else:
                    raise HTTPException(status_code=400, detail="Token refresh failed: No access token in response")
                    
            else:
                error_detail = f"Token refresh failed: HTTP {response.status_code} - {response.text}"
                raise HTTPException(status_code=400, detail=error_detail)
                
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Network error during token refresh: {str(e)}")
    
    def is_access_token_expired(self) -> bool:
        """
        Check if access token is expired or will expire soon
        
        Returns:
            bool: True if token is expired/expiring, False otherwise
        """
        if not self.access_token or not self.access_expire_time:
            return True
        
        # Consider token expired if it expires within next 60 seconds (buffer)
        current_time = int(time.time())
        return current_time >= (self.access_expire_time - 60)
    
    def is_refresh_token_expired(self) -> bool:
        """
        Check if refresh token is expired
        
        Returns:
            bool: True if refresh token is expired, False otherwise
        """
        if not self.refresh_token or not self.refresh_expire_time:
            return True
        
        current_time = int(time.time())
        return current_time >= self.refresh_expire_time
    
    async def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token, refreshing or re-logging as needed
        
        Returns:
            bool: True if we have a valid token, False otherwise
        """
        # If not authenticated at all, do initial login
        if not self.is_authenticated:
            await self.login()
            return True
        
        # If refresh token is expired, need to login again
        if self.is_refresh_token_expired():
            await self.login()
            return True
        
        # If access token is expired/expiring, refresh it
        if self.is_access_token_expired():
            try:
                await self.refresh_access_token()
                return True
            except HTTPException:
                # Refresh failed, try full login
                await self.login()
                return True
        
        # Token is still valid
        return True
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """
        Get headers with authorization token for API requests
        
        Returns:
            dict: Headers dictionary with Authorization header
        """
        await self.ensure_valid_token()
        
        if not self.access_token:
            raise HTTPException(status_code=401, detail="Failed to obtain valid authentication token")
        
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def get_token_status(self) -> Dict:
        """
        Get current token status information
        
        Returns:
            dict: Token status information
        """
        if not self.is_authenticated:
            return {
                "authenticated": False,
                "message": "Not authenticated"
            }
        
        current_time = int(time.time())
        
        access_remaining = max(0, self.access_expire_time - current_time) if self.access_expire_time else 0
        refresh_remaining = max(0, self.refresh_expire_time - current_time) if self.refresh_expire_time else 0
        
        return {
            "authenticated": True,
            "access_token_valid": not self.is_access_token_expired(),
            "refresh_token_valid": not self.is_refresh_token_expired(),
            "access_expires_in_seconds": access_remaining,
            "refresh_expires_in_seconds": refresh_remaining,
            "access_expires_at": datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc).isoformat() if self.access_expire_time else None,
            "refresh_expires_at": datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc).isoformat() if self.refresh_expire_time else None
        }

# Global authentication service instance
auth_service = ProphetXAuthService()