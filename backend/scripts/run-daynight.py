#!/usr/bin/env python3
"""Day/Night mode automatic monitoring service runner.

This script runs the day/night monitoring service as a daemon process.
It periodically checks brightness and automatically switches between day and night modes.
"""

import sys
import signal
import time
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services.day_night_service import day_night_service
from app.models import Setting


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    print("\nShutting down day/night monitoring service...")
    day_night_service.stop_monitoring()
    sys.exit(0)


def main():
    """Run day/night monitoring service."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app = create_app()

    with app.app_context():
        print("Starting day/night monitoring service...")

        # Get threshold and interval from settings
        threshold_setting = Setting.query.filter_by(key="DAY_NIGHT_THRESHOLD").first()
        threshold = float(threshold_setting.value) if threshold_setting else 30.0

        interval_setting = Setting.query.filter_by(key="DAY_NIGHT_CHECK_INTERVAL").first()
        interval = float(interval_setting.value) if interval_setting else 60.0

        # Start monitoring
        day_night_service.start_monitoring(threshold=threshold, interval=interval)

        print("✓ Day/Night monitoring service running")
        print(f"  - Brightness threshold: {threshold}")
        print(f"  - Check interval: {interval}s")
        print("  - Press Ctrl+C to stop")

        # Keep running until interrupted
        try:
            while day_night_service._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        day_night_service.stop_monitoring()
        print("Day/Night monitoring service stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
