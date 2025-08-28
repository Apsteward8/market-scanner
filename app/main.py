#!/usr/bin/env python3
"""
ProphetX Market Scanner API
Main FastAPI application for scanning and following high wager bets
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ProphetX Market Scanner",
    description="Automated betting system that follows high-value wagers on ProphetX",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from app.routers import scanner
app.include_router(scanner.router, prefix="/scanner", tags=["Market Scanner"])

@app.get("/")
async def root():
    """Root endpoint with basic API information"""
    return {
        "message": "ProphetX Market Scanner API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "market-scanner"
    }

@app.get("/quick-test")
async def quick_test():
    """Quick test endpoint to verify everything is working"""
    from app.core.config import get_settings
    
    settings = get_settings()
    validation = settings.validate_settings()
    
    return {
        "status": "API is running",
        "message": "Use /scanner endpoints for market scanning functionality",
        "settings_valid": validation["valid"],
        "settings_issues": validation.get("issues", []),
        "endpoints": {
            "authenticate": "/scanner/authenticate",
            "scan_opportunities": "/scanner/scan-opportunities",
            "ncaaf_events": "/scanner/ncaaf-events",
            "settings": "/scanner/settings"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004, reload=True)