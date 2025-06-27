#!/usr/bin/env python3
"""
ProphetX Authentication Handler
Handles login, token refresh, and automatic token management
"""

import requests
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple

class ProphetXAuth:
    def __init__(self, access_key: str, secret_key: str, sandbox: bool = True):
        """
        Initialize ProphetX authentication
        
        Args:
            access_key: Your ProphetX access key
            secret_key: Your ProphetX secret key  
            sandbox: True for sandbox environment, False for production
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.sandbox = sandbox
        
        # Set base URL based on environment
        if sandbox:
            self.base_url = "https://api-ss-sandbox.betprophet.co"
        else:
            self.base_url = "https://api-ss.betprophet.co"  # Production URL (guess)
        
        # Token storage
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_expire_time: Optional[int] = None
        self.refresh_expire_time: Optional[int] = None
        
        # Track login status
        self.is_authenticated = False
        
    def login(self) -> bool:
        """
        Perform initial login to get access and refresh tokens
        
        Returns:
            bool: True if login successful, False otherwise
        """
        print("🔐 Logging in to ProphetX...")
        
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
                    
                    # Convert timestamps to readable format for logging
                    access_expire_dt = datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc)
                    refresh_expire_dt = datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc)
                    
                    print("✅ Login successful!")
                    print(f"   Access token expires: {access_expire_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    print(f"   Refresh token expires: {refresh_expire_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    
                    return True
                else:
                    print("❌ Login failed: Missing tokens in response")
                    return False
                    
            else:
                print(f"❌ Login failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"💥 Login error: {e}")
            return False
    
    def refresh_access_token(self) -> bool:
        """
        Refresh the access token using the refresh token
        
        Returns:
            bool: True if refresh successful, False otherwise
        """
        if not self.refresh_token:
            print("❌ No refresh token available")
            return False
        
        print("🔄 Refreshing access token...")
        
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
                    print(f"✅ Token refreshed! Expires: {access_expire_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    return True
                else:
                    print("❌ Token refresh failed: No access token in response")
                    return False
                    
            else:
                print(f"❌ Token refresh failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"💥 Token refresh error: {e}")
            return False
    
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
    
    def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token, refreshing or re-logging as needed
        
        Returns:
            bool: True if we have a valid token, False otherwise
        """
        # If not authenticated at all, do initial login
        if not self.is_authenticated:
            return self.login()
        
        # If refresh token is expired, need to login again
        if self.is_refresh_token_expired():
            print("🔄 Refresh token expired, re-logging in...")
            self.is_authenticated = False
            return self.login()
        
        # If access token is expired/expiring, refresh it
        if self.is_access_token_expired():
            success = self.refresh_access_token()
            if not success:
                # Refresh failed, try full login
                print("🔄 Token refresh failed, attempting full re-login...")
                self.is_authenticated = False
                return self.login()
            return True
        
        # Token is still valid
        return True
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get headers with authorization token for API requests
        
        Returns:
            dict: Headers dictionary with Authorization header
        """
        if not self.ensure_valid_token():
            raise Exception("Failed to obtain valid authentication token")
        
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
            return {"status": "not_authenticated"}
        
        current_time = int(time.time())
        
        access_remaining = max(0, self.access_expire_time - current_time) if self.access_expire_time else 0
        refresh_remaining = max(0, self.refresh_expire_time - current_time) if self.refresh_expire_time else 0
        
        return {
            "status": "authenticated",
            "access_token_valid": not self.is_access_token_expired(),
            "refresh_token_valid": not self.is_refresh_token_expired(),
            "access_expires_in_seconds": access_remaining,
            "refresh_expires_in_seconds": refresh_remaining,
            "access_expires_at": datetime.fromtimestamp(self.access_expire_time, tz=timezone.utc).isoformat() if self.access_expire_time else None,
            "refresh_expires_at": datetime.fromtimestamp(self.refresh_expire_time, tz=timezone.utc).isoformat() if self.refresh_expire_time else None
        }

def test_authentication():
    """
    Test the authentication system
    """
    print("ProphetX Authentication Test")
    print("=" * 40)
    
    # Get credentials from user
    access_key = input("Enter your ProphetX access key: ").strip()
    secret_key = input("Enter your ProphetX secret key: ").strip()
    
    if not access_key or not secret_key:
        print("❌ Both access key and secret key are required!")
        return
    
    # Test authentication
    auth = ProphetXAuth(access_key, secret_key, sandbox=True)
    
    print("\n1️⃣ Testing initial login...")
    success = auth.login()
    
    if success:
        print("\n2️⃣ Token status:")
        status = auth.get_token_status()
        print(f"   Status: {status['status']}")
        print(f"   Access token valid: {status['access_token_valid']}")
        print(f"   Access expires in: {status['access_expires_in_seconds']} seconds")
        print(f"   Refresh expires in: {status['refresh_expires_in_seconds']} seconds")
        
        print("\n3️⃣ Testing auth headers generation:")
        try:
            headers = auth.get_auth_headers()
            print("   ✅ Auth headers generated successfully")
            print(f"   Authorization header length: {len(headers.get('Authorization', ''))}")
        except Exception as e:
            print(f"   ❌ Failed to generate auth headers: {e}")
        
        print("\n4️⃣ Testing token refresh...")
        # Force a refresh test (even if not needed)
        refresh_success = auth.refresh_access_token()
        if refresh_success:
            print("   ✅ Token refresh test passed")
        else:
            print("   ❌ Token refresh test failed")
    
    else:
        print("❌ Authentication test failed!")

if __name__ == "__main__":
    test_authentication()