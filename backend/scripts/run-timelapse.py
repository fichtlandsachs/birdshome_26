#!/usr/bin/env python3
"""Timelapse generation job.

Run this script periodically (e.g., daily via systemd timer) to generate
timelapse videos from captured snapshots.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.services.timelapse_service import timelapse_service
from app.services.logging_service import setup_service_logger


def main():
    """Generate timelapse and cleanup old snapshots."""
    # Setup dedicated logger for timelapse service
    logger = setup_service_logger("timelapse")

    app = create_app()

    with app.app_context():
        logger.info("Starting timelapse generation")
        # Generate timelapse
        print("Generating timelapse...")
        result = timelapse_service.generate_timelapse()

        if result["ok"]:
            if result.get("skipped"):
                # No screenshots available - this is normal
                logger.info(f"Timelapse skipped: {result.get('message', 'No screenshots available')}")
                print(f"⊘ Timelapse skipped: {result.get('message', 'No screenshots available')}")
                timelapse_success = True
            else:
                # Successfully created timelapse
                logger.info(f"Timelapse created: {result['path']}, frames={result['frame_count']}, range={result['from_date']} to {result['to_date']}")
                print(f"✓ Timelapse created: {result['path']}")
                print(f"  Frames: {result['frame_count']}")
                print(f"  Date range: {result['from_date']} to {result['to_date']}")
                timelapse_success = True
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Timelapse failed: {error_msg}")
            print(f"✗ Timelapse failed: {error_msg}", file=sys.stderr)
            timelapse_success = False

        # Cleanup old snapshots (always run, even if timelapse failed)
        logger.info("Starting snapshot cleanup")
        print("\nCleaning up old snapshots...")
        cleanup_result = timelapse_service.cleanup_old_snapshots()

        if cleanup_result["ok"]:
            if cleanup_result['deleted_count'] > 0:
                logger.info(f"Cleanup complete: {cleanup_result['deleted_count']} snapshots removed, {cleanup_result['deleted_bytes']} bytes freed")
                print(f"✓ Cleanup complete: {cleanup_result['deleted_count']} snapshots removed")
                print(f"  Space freed: {cleanup_result['deleted_bytes']} bytes")
            else:
                logger.info("No old snapshots to clean up")
                print("⊘ No old snapshots to clean up")
        else:
            logger.error(f"Cleanup failed: {cleanup_result.get('error', 'Unknown error')}")
            print(f"✗ Cleanup failed: {cleanup_result.get('error', 'Unknown error')}", file=sys.stderr)

        # Return success if timelapse succeeded or was skipped (no snapshots yet)
        return 0 if timelapse_success else 1


if __name__ == "__main__":
    sys.exit(main())
