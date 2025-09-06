#!/usr/bin/env python3
"""
ProphetX Market Scanner - Application Runner
Simple script to start the FastAPI server
"""

import uvicorn
import os
from pathlib import Path
import atexit
import signal
import sys

def setup_logging():
    """Initialize enhanced logging for the entire application"""
    try:
        from app.utils.enhanced_logging import initialize_enhanced_logging, cleanup_logging
        
        logging_setup = initialize_enhanced_logging(
            log_dir="logs",
            app_name="market_making"
        )
        
        # Setup cleanup on exit
        atexit.register(cleanup_logging)
        
        # Handle CTRL+C gracefully
        def signal_handler(sig, frame):
            print("\n🛑 Shutting down gracefully...")
            cleanup_logging()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        return logging_setup
        
    except Exception as e:
        print(f"❌ Failed to setup logging: {e}")
        return None

if __name__ == "__main__":
    # Initialize enhanced logging FIRST (before importing FastAPI)
    logging_setup = setup_logging()
    
    if logging_setup:
        print("📝 All output will be logged to both terminal and file")
        print(f"📁 Log files location: {logging_setup.log_dir.absolute()}")

    env_file = Path(".env")
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print(f"✅ Loaded environment variables from {env_file}")
    
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8004))
    host = os.getenv("HOST", "127.0.0.1")
    
    print(f"🚀 Starting ProphetX Market Scanner API")
    print(f"🌐 Server: http://{host}:{port}")
    print(f"📖 Docs: http://{host}:{port}/docs")
    print(f"🔍 Health: http://{host}:{port}/health")
    print(f"🧪 Test: http://{host}:{port}/test-scan")
    
    # Start the server (disable reload to avoid timezone file watching issues)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,  # Disabled to prevent timezone file reloading issues
        reload_dirs=["app"]
    )