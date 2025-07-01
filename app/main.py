#!/usr/bin/env python3
"""
ProphetX FastAPI Application
Main application file for the ProphetX betting tool API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from app.core.config import get_settings
from app.routers import auth, markets, bets, analysis, config

# Global settings
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print("🚀 ProphetX API starting up...")
    print(f"📝 Environment: {'SANDBOX' if settings.sandbox else 'PRODUCTION'}")
    print(f"🎯 Target sports: {', '.join(settings.target_sports)}")
    
    yield
    
    # Shutdown
    print("🛑 ProphetX API shutting down...")

# Create FastAPI app
app = FastAPI(
    title="ProphetX Betting Tool API",
    description="""
    API for following smart money on ProphetX betting exchange.
    
    ## Features
    
    * **Authentication** - Manage ProphetX API credentials and tokens
    * **Market Scanning** - Find large bets worth following
    * **Bet Analysis** - Analyze opportunities and calculate undercut odds  
    * **Bet Placement** - Place follow bets with proper odds
    * **History & Tracking** - Track bet performance and results
    
    ## Strategy
    
    This tool implements a "follow the smart money" strategy:
    1. Scan ProphetX markets for large bets (>$5k)
    2. Assume large bets indicate sharp/informed money
    3. Place follow bets with slightly worse odds to get queue priority
    4. Profit from being first in line when action flows
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(markets.router, prefix="/markets", tags=["Market Scanning"])
app.include_router(bets.router, prefix="/bets", tags=["Bet Placement"])
app.include_router(analysis.router, prefix="/analysis", tags=["Bet Analysis"])
app.include_router(config.router, prefix="/config", tags=["Configuration"])

@app.get("/", tags=["Health"])
async def root():
    """API health check"""
    return {
        "status": "healthy",
        "service": "ProphetX Betting Tool API",
        "version": "1.0.0",
        "environment": "sandbox" if settings.sandbox else "production",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "environment": "sandbox" if settings.sandbox else "production",
        "settings": {
            "min_stake_threshold": settings.min_stake_threshold,
            "target_sports": settings.target_sports,
            "max_bet_size": settings.max_bet_size
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )