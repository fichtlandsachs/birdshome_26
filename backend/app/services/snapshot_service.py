"""Snapshot service for timelapse photo capture.

This service captures periodic snapshots from the video source for timelapse generation.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import Photo
from .video_utils import get_rotation_filter
from .day_night_service import day_night_service

logger = logging.getLogger(__name__)


class SnapshotService:
    """Service for capturing periodic snapshots for timelapse."""

    def __init__(self):
        self._config = {}

    def _load_config(self) -> None:
        """Load configuration from database settings."""
        from ..models import Setting

        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        self._config = {
            "VIDEO_SOURCE": settings.get("VIDEO_SOURCE") or current_app.config.get("VIDEO_SOURCE"),
            "VIDEO_ROTATION": settings.get("VIDEO_ROTATION") or current_app.config.get("VIDEO_ROTATION", "0"),
            "PREFIX": settings.get("PREFIX") or current_app.config.get("PREFIX", "nest_"),
        }

    def capture_snapshot(self) -> dict:
        """Capture a single snapshot from the video source.

        Returns:
            dict with status and path information
        """
        try:
            # Load config from database
            self._load_config()

            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            snapshots_dir = media_root / "snapshots"
            snapshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            prefix = self._config.get("PREFIX", "nest_")
            filename = f"{prefix}snapshot_{timestamp}.jpg"
            output_path = snapshots_dir / filename

            # Get video source configuration
            video_source = self._config.get("VIDEO_SOURCE")
            if not video_source:
                logger.warning("VIDEO_SOURCE not configured - skipping snapshot")
                return {"ok": False, "error": "VIDEO_SOURCE not configured", "skip": True}

            # Capture snapshot using ffmpeg
            # -frames:v 1 = capture only 1 frame
            # -q:v 2 = high quality JPEG (1-31, lower is better)
            cmd = [
                current_app.config.get("FFMPEG_BIN", "ffmpeg"),
                "-hide_banner",
                "-loglevel", "error",
            ]

            # Add video source
            if video_source.startswith("-"):
                cmd.extend(video_source.split())
            else:
                cmd.extend(["-i", video_source])

            # Apply rotation filter if configured
            rotation = self._config.get("VIDEO_ROTATION", "0")
            rotation_filter = get_rotation_filter(rotation)

            # Apply grayscale filter for night mode
            filters = []
            if rotation_filter:
                filters.append(rotation_filter)

            if day_night_service.get_mode() == "NIGHT":
                filters.append("hue=s=0")

            if filters:
                cmd.extend(["-vf", ",".join(filters)])

            # Output options
            cmd.extend([
                "-frames:v", "1",
                "-q:v", "2",
                "-y",  # overwrite if exists
                str(output_path)
            ])

            logger.info(f"Capturing snapshot: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return {"ok": False, "error": f"ffmpeg failed: {result.stderr}"}

            # Verify file was created
            if not output_path.exists():
                logger.error("Snapshot file was not created")
                return {"ok": False, "error": "Snapshot file was not created"}

            # Get file info
            stat = output_path.stat()
            relative_path = str(output_path.relative_to(media_root))

            # Save to database
            photo = Photo(
                path=relative_path,
                resolution=None,  # Could extract from ffprobe if needed
                uploaded=False
            )
            db.session.add(photo)
            db.session.commit()

            logger.info(f"Snapshot captured: {relative_path} ({stat.st_size} bytes)")
            return {
                "ok": True,
                "path": relative_path,
                "size_bytes": stat.st_size,
                "photo_id": photo.id
            }

        except subprocess.TimeoutExpired:
            logger.error("Snapshot capture timed out")
            return {"ok": False, "error": "Timeout"}
        except Exception as e:
            logger.exception("Error capturing snapshot")
            return {"ok": False, "error": str(e)}


# Singleton instance
snapshot_service = SnapshotService()
