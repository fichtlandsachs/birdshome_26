#!/usr/bin/env python3
"""Run upload job to sync media to HiDrive."""

import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from app import create_app
from app.services.upload_service import upload_service
from app.services.logging_service import setup_service_logger
from app.models import Setting

def main():
    """Run upload job."""
    # Setup dedicated logger for upload service
    logger = setup_service_logger("upload")

    app = create_app()

    # Debug: Print database path
    logger.info(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    print(f"[upload] Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")

    with app.app_context():
        logger.info("Starting upload service")
        # Debug: Check if Settings table has data
        settings_count = Setting.query.count()
        logger.info(f"Found {settings_count} settings in database")
        print(f"[upload] Found {settings_count} settings in database")

        if settings_count == 0:
            logger.warning("No settings found in database. Upload may fail.")
            print("[upload] WARNING: No settings found in database. Upload may fail.")
            print("[upload] Please configure HiDrive credentials in Admin UI first.")
        else:
            # Print some key settings (without passwords)
            user_setting = Setting.query.filter_by(key="HIDRIVE_USER").first()
            target_setting = Setting.query.filter_by(key="HIDRIVE_TARGET_DIR").first()

            if user_setting:
                logger.info(f"HiDrive User: {user_setting.value}")
                print(f"[upload] HiDrive User: {user_setting.value}")
            if target_setting:
                logger.info(f"Target Directory: {target_setting.value}")
                print(f"[upload] Target Directory: {target_setting.value}")

        logger.info("Starting upload to HiDrive")
        print("[upload] Starting upload to HiDrive...")
        result = upload_service.upload_all()

        if result.get("ok"):
            logger.info(f"Upload successful: {result.get('success_count')}/{result.get('total_count')} directories")
            print(f"[upload] Upload successful: {result.get('success_count')}/{result.get('total_count')} directories")
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Upload failed: {error_msg}")
            print(f"[upload] Upload failed: {error_msg}")

            # Don't exit with error if credentials are not configured
            if "not configured" in error_msg.lower():
                logger.warning("Upload skipped - not configured yet")
                print("[upload] Skipping upload - not configured yet")
                sys.exit(0)

            sys.exit(1)

        # Print details
        for detail in result.get("details", []):
            status = "✓" if detail.get("ok") else "✗"
            detail_info = detail.get('remote', detail.get('error', 'N/A'))
            log_msg = f"{detail.get('type')}: {detail_info}"
            if detail.get("ok"):
                logger.info(log_msg)
            else:
                logger.error(log_msg)
            print(f"[upload]   {status} {log_msg}")

if __name__ == "__main__":
    main()
