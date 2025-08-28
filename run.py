#!/usr/bin/env python3
"""
ProphetX Market Scanner - Application Runner
Simple script to start the FastAPI server
"""

import uvicorn
import os
from pathlib import Path

if __name__ == "__main__":
    # Load environment variables if .env exists
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