#!/usr/bin/env python3
"""
ProphetX Market Scanner API
Main FastAPI application for scanning and following high wager bets
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timezone
import asyncio


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
from app.routers.arbitrage_test import router as arbitrage_router
from app.routers.bet_placement import router as bet_placement_router

app.include_router(scanner.router, prefix="/scanner", tags=["Market Scanner"])
app.include_router(arbitrage_router, prefix="/arbitrage", tags=["Arbitrage Testing"])
app.include_router(bet_placement_router, prefix="/betting", tags=["Bet Placement"])

@app.on_event("startup")
async def startup_event():
    """Initialize ProphetX authentication on startup"""
    logger.info("🚀 Starting ProphetX Market Scanner...")
    
    try:
        # Import and initialize ProphetX service
        from app.services.prophetx_service import prophetx_service
        
        logger.info("🔐 Initializing ProphetX authentication...")
        auth_result = await prophetx_service.initialize()
        
        if auth_result.get("success"):
            logger.info("✅ ProphetX authentication initialized successfully!")
            
            # Log authentication status
            status = prophetx_service.get_auth_status()
            prod_status = status.get("production", {})
            sandbox_status = status.get("sandbox", {})
            
            logger.info(f"   📊 Production: {'✅' if prod_status.get('authenticated') else '❌'} (expires in {prod_status.get('expires_in_minutes', 0):.1f} min)")
            logger.info(f"   📊 Sandbox: {'✅' if sandbox_status.get('authenticated') else '❌'} (expires in {sandbox_status.get('expires_in_minutes', 0):.1f} min)")
            logger.info(f"   🎯 Betting environment: {status.get('betting_environment', 'unknown')}")
            
        else:
            logger.error("❌ ProphetX authentication initialization failed!")
            logger.error(f"   Results: {auth_result}")
            
    except Exception as e:
        logger.error(f"❌ Error during startup initialization: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down ProphetX Market Scanner...")
    
    try:
        from app.services.prophetx_service import prophetx_service
        # Close HTTP clients if needed
        if hasattr(prophetx_service, 'client'):
            await prophetx_service.client.aclose()
        
        if hasattr(prophetx_service.auth_manager, 'client'):
            await prophetx_service.auth_manager.client.aclose()
            
        logger.info("✅ Cleanup complete")
    except Exception as e:
        logger.warning(f"⚠️ Error during shutdown: {e}")

@app.get("/")
async def root():
    """Root endpoint with basic API information"""
    return {
        "message": "ProphetX Market Scanner API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs": "/docs",
        "new_features": [
            "High wager arbitrage detection with 3% commission adjustment",
            "Automated bet sizing ($100 plus, bet-to-win-$100 minus)",
            "Conflict resolution for opposing opportunities"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "market-scanner",
        "arbitrage_service": "loaded"
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
            "analyze_with_arbitrage": "/scanner/analyze-opportunities-with-arbitrage",
            "settings": "/scanner/settings",
            "arbitrage_tests": {
                "test_calculation": "/arbitrage/test-arbitrage-calculation",
                "test_commission": "/arbitrage/test-commission-scenarios", 
                "test_sizing": "/arbitrage/test-bet-sizing-logic"
            },
            "bet_placement": {
                "test_balance": "/betting/test-balance-integration",
                "set_dry_run": "/betting/set-dry-run-mode",
                "test_single_bet": "/betting/test-single-bet-placement",
                "test_arbitrage": "/betting/test-arbitrage-placement", 
                "place_all": "/betting/place-all-opportunities",
                "summary": "/betting/placement-summary",
                "placed_bets": "/betting/placed-bets"
            }
        }
    }

# Add authentication status endpoint
@app.get("/auth/status")
async def auth_status():
    """Get detailed authentication status for both environments"""
    try:
        from app.services.prophetx_service import prophetx_service
        status = prophetx_service.get_auth_status()
        
        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "authentication_status": status
        }
    except Exception as e:
        return {
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(), 
            "error": str(e)
        }

@app.post("/auth/refresh")
async def refresh_auth():
    """Manually refresh authentication for both environments"""
    try:
        from app.services.prophetx_service import prophetx_service
        
        logger.info("🔄 Manual authentication refresh requested...")
        result = await prophetx_service.authenticate()
        
        return {
            "success": result.get("success", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Authentication refresh complete",
            "results": result
        }
    except Exception as e:
        logger.error(f"❌ Manual auth refresh failed: {e}")
        return {
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8004, reload=True)