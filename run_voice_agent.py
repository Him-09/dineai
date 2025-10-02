#!/usr/bin/env python3
"""
Startup script for the Restaurant Voice Agent with LiveKit integration.

This script helps you run the restaurant voice agent with proper environment setup.
"""

import os
import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Change to src directory for relative imports
os.chdir(str(src_path))

if __name__ == "__main__":
    from livekit.agents import cli, WorkerOptions
    from src.voice import entrypoint
    
    print("[START] Starting Restaurant Voice Agent with LiveKit...")
    print("[INFO] Agent capabilities:")
    print("  • Menu search and recommendations")
    print("  • Table booking and reservation management")
    print("  • Restaurant FAQ and information")
    print("  • Real-time voice interaction")
    print("\n[READY] Voice agent is ready to connect to LiveKit room...")
    print("=" * 60)
    
    try:
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        print("\n👋 Restaurant Voice Agent stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] Error running voice agent: {e}")
        sys.exit(1)
