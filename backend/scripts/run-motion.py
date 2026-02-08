#!/usr/bin/env python3
"""Motion detection service runner.

This script runs the motion detection service as a daemon process.
It monitors the video feed and automatically records clips when motion is detected.
"""

import sys
import signal
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services.motion_service import motion_service


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    print("\nShutting down motion detection service...")
    motion_service.stop()
    sys.exit(0)


def main():
    """Run motion detection service."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app = create_app()

    with app.app_context():
        print("Starting motion detection service...")
        result = motion_service.start()

        if not result["ok"]:
            print(f"✗ Failed to start: {result.get('error', 'Unknown error')}", file=sys.stderr)
            return 1

        print("✓ Motion detection service running")
        print("  - Monitoring video feed for motion")
        print("  - Will record video clips automatically")
        print("  - Press Ctrl+C to stop")

        # Keep running until interrupted
        try:
            while motion_service.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        print("Motion detection service stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
