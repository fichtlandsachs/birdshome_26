#!/usr/bin/env python3
"""Snapshot capture job for timelapse.

Run this script periodically (e.g., via systemd timer) to capture snapshots
for timelapse generation.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services.snapshot_service import snapshot_service
from app.services.timelapse_service import timelapse_service
from app.services.logging_service import setup_service_logger


def main():
    """Capture a single snapshot."""
    # Setup dedicated logger for snapshot service
    logger = setup_service_logger("snapshot")

    app = create_app()

    with app.app_context():
        logger.info("Starting snapshot capture")
        result = timelapse_service.capture_udp_snapshot()

        if result["ok"]:
            logger.info(f"Screenshot captured: {result['path']}")
            print(f"✓ Screenshot captured: {result['path']}")
            return 0
        else:
            if result.get("skip"):
                logger.warning(f"Snapshot skipped: {result.get('error', 'Unknown error')}")
                print(f"⊘ Snapshot skipped: {result.get('error', 'Unknown error')}")
                return 0
            else:
                logger.error(f"Snapshot failed: {result.get('error', 'Unknown error')}")
                print(f"✗ Snapshot failed: {result.get('error', 'Unknown error')}", file=sys.stderr)
                return 1


if __name__ == "__main__":
    sys.exit(main())
