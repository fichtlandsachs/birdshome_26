"""Upload service for syncing media to Strato HiDrive via rclone."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import Photo, Video, Timelapse

logger = logging.getLogger(__name__)


class UploadService:
    """Service for uploading media files to HiDrive using rclone."""

    def __init__(self):
        self._config = {}

    def _load_config(self) -> dict:
        """Load configuration from database settings."""
        from ..models import Setting

        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        self._config = {
            "HIDRIVE_USER": settings.get("HIDRIVE_USER", ""),
            "HIDRIVE_PASSWORD": settings.get("HIDRIVE_PASSWORD", ""),
            "HIDRIVE_TARGET_DIR": settings.get("HIDRIVE_TARGET_DIR", "Birdshome"),
            "UPLOAD_PHOTOS": settings.get("UPLOAD_PHOTOS", "1"),
            "UPLOAD_VIDEOS": settings.get("UPLOAD_VIDEOS", "1"),
            "UPLOAD_TIMELAPSES": settings.get("UPLOAD_TIMELAPSES", "1"),
            "UPLOAD_RETENTION_DAYS": settings.get("UPLOAD_RETENTION_DAYS", "30"),
            "UPLOAD_START_HOUR": settings.get("UPLOAD_START_HOUR", "22"),
            "UPLOAD_END_HOUR": settings.get("UPLOAD_END_HOUR", "6"),
        }
        return self._config

    def _obscure_password(self, password: str) -> str | None:
        """Obscure password using rclone obscure command.

        Returns:
            Obscured password or None on error
        """
        try:
            result = subprocess.run(
                ["rclone", "obscure", password],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error(f"rclone obscure failed: {result.stderr}")
                return None

            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to obscure password: {e}")
            return None

    def _create_rclone_config(self) -> str | None:
        """Create temporary rclone config file with HiDrive credentials.

        Returns:
            Path to temporary config file or None if credentials are missing
        """
        config = self._load_config()

        user = config.get("HIDRIVE_USER", "").strip()
        password = config.get("HIDRIVE_PASSWORD", "").strip()

        if not user or not password:
            logger.warning("HiDrive credentials not configured")
            return None

        # Obscure the password for rclone
        obscured_password = self._obscure_password(password)
        if not obscured_password:
            logger.error("Failed to obscure password")
            return None

        # Create temporary config file
        fd, config_path = tempfile.mkstemp(suffix=".conf", text=True)

        try:
            with os.fdopen(fd, 'w') as f:
                f.write("[hidrive]\n")
                f.write("type = webdav\n")
                f.write("url = https://my.hidrive.com/share/j2xe9clh4t#$\n")
                f.write("vendor = other\n")
                f.write(f"user = {user}\n")
                f.write(f"pass = {obscured_password}\n")
                # Additional WebDAV settings for better compatibility
                f.write("pacer_min_sleep = 10ms\n")

            logger.debug(f"Created temporary rclone config for user: {user}")
            return config_path
        except Exception as e:
            logger.error(f"Failed to create rclone config: {e}")
            if os.path.exists(config_path):
                os.unlink(config_path)
            return None

    def _ensure_remote_directory(self, remote_path: str, config_path: str) -> bool:
        """Ensure remote directory exists on HiDrive, create if needed.

        Creates parent directories recursively if needed.

        Args:
            remote_path: Full remote path (e.g. 'hidrive:/birdie/Birdshome/hostname/photos')
            config_path: Path to rclone config file

        Returns:
            True if directory exists or was created, False on error
        """
        try:
            logger.info(f"Ensuring remote directory exists: {remote_path}")

            # Parse remote path: "hidrive:/birdie/Birdshome/hostname/photos"
            # Split into parts: ["hidrive:", "birdie", "Birdshome", "hostname", "photos"]
            parts = remote_path.split("/")
            if len(parts) < 2:
                logger.error(f"Invalid remote path format: {remote_path}")
                return False

            # Build path incrementally starting from remote root
            # Start with "hidrive:" then add each part
            current_path = parts[0]  # "hidrive:"

            for i in range(1, len(parts)):
                if not parts[i]:  # Skip empty parts
                    continue

                current_path = f"{current_path}/{parts[i]}"

                # Try to create this level
                mkdir_cmd = [
                    "rclone",
                    "mkdir",
                    current_path,
                    f"--config={config_path}"
                ]

                result = subprocess.run(
                    mkdir_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                # Ignore errors if directory already exists (409 Conflict is okay)
                if result.returncode != 0:
                    # Check if error is "directory already exists" (which is okay)
                    if "already exists" in result.stderr.lower() or "409" in result.stderr:
                        logger.debug(f"Directory already exists: {current_path}")
                        continue
                    # 405 Method Not Allowed can occur when directory exists in WebDAV
                    elif "405" in result.stderr:
                        logger.debug(f"Directory might already exist (405): {current_path}")
                        continue
                    # Check for 401 Unauthorized
                    elif "401" in result.stderr or "unauthorized" in result.stderr.lower():
                        logger.error(f"Authentication failed for {current_path}: {result.stderr}")
                        return False
                    else:
                        logger.warning(f"mkdir returned non-zero for {current_path}: {result.stderr}")
                        # Continue anyway, might be okay
                        continue
                else:
                    logger.debug(f"Created directory: {current_path}")

            logger.info(f"Successfully ensured remote directory exists: {remote_path}")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout while checking/creating remote directory: {remote_path}")
            return False
        except Exception as e:
            logger.exception(f"Error ensuring remote directory exists: {remote_path}")
            return False

    def _upload_directory(self, source_dir: Path, remote_subdir: str, config_path: str) -> dict:
        """Upload a directory to HiDrive using rclone.

        Args:
            source_dir: Local directory to upload
            remote_subdir: Subdirectory on remote (e.g. 'photos', 'videos')
            config_path: Path to rclone config file

        Returns:
            dict with status information
        """
        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")
            return {"ok": True, "skip": True, "info": f"Directory {source_dir} does not exist yet"}

        if not source_dir.is_dir():
            logger.warning(f"Source path is not a directory: {source_dir}")
            return {"ok": False, "error": "Source path is not a directory", "skip": True}

        # Check if directory is empty
        if not any(source_dir.iterdir()):
            logger.info(f"Source directory is empty: {source_dir}")
            return {"ok": True, "skip": True, "info": f"Directory {source_dir} is empty"}

        config = self._config
        target_base = "hidrive:/birdie/Birdshome"
        # Get hostname for organizing uploads by device
        import socket
        hostname = socket.gethostname()

        # HiDrive WebDAV paths don't include username - it's in the credentials
        # Path structure: /birdie/Birdshome/hostname/photos
        remote_path = f"{target_base}/{hostname}/{remote_subdir}"

        # Ensure remote directory exists before upload
        if not self._ensure_remote_directory(remote_path, config_path):
            logger.error(f"Failed to ensure remote directory exists: {remote_path}")
            return {
                "ok": False,
                "error": "Failed to create remote directory - check credentials and path"
            }

        cmd = [
            "rclone",
            "sync",
            str(source_dir),
            remote_path,
            f"--config={config_path}",
            "--verbose",
            "--stats=10s",
            "--transfers=4",
            "--checkers=8",
            "--ignore-times",
        ]

        logger.info(f"Uploading {source_dir} to {remote_path}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )

            if result.returncode != 0:
                logger.error(f"rclone sync failed: {result.stderr}")
                return {
                    "ok": False,
                    "error": f"rclone failed: {result.stderr[:200]}",
                    "returncode": result.returncode
                }

            logger.info(f"Successfully uploaded {source_dir} to {remote_path}")
            return {
                "ok": True,
                "source": str(source_dir),
                "remote": remote_path,
                "stdout": result.stdout[:500]
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Upload timeout for {source_dir}")
            return {"ok": False, "error": "Upload timeout"}
        except FileNotFoundError:
            logger.error("rclone not found - please install rclone")
            return {"ok": False, "error": "rclone not installed"}
        except Exception as e:
            logger.exception(f"Upload error for {source_dir}")
            return {"ok": False, "error": str(e)}

    def cleanup_old_files(self) -> dict:
        """Delete successfully uploaded files older than retention days.

        Returns:
            dict with cleanup summary
        """
        from datetime import datetime, timedelta

        try:
            config = self._load_config()
            retention_days = int(config.get("UPLOAD_RETENTION_DAYS", "30"))
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            deleted = {"photos": 0, "videos": 0, "timelapses": 0}
            errors = []

            # Cleanup photos
            old_photos = Photo.query.filter(
                Photo.uploaded == True,
                Photo.created_at < cutoff_date
            ).all()

            for photo in old_photos:
                try:
                    file_path = media_root / photo.path
                    if file_path.exists():
                        file_path.unlink()
                    db.session.delete(photo)
                    deleted["photos"] += 1
                except Exception as e:
                    logger.error(f"Failed to delete photo {photo.path}: {e}")
                    errors.append(f"Photo {photo.path}: {str(e)}")

            # Cleanup videos
            old_videos = Video.query.filter(
                Video.uploaded == True,
                Video.created_at < cutoff_date
            ).all()

            for video in old_videos:
                try:
                    file_path = media_root / video.path
                    if file_path.exists():
                        file_path.unlink()
                    db.session.delete(video)
                    deleted["videos"] += 1
                except Exception as e:
                    logger.error(f"Failed to delete video {video.path}: {e}")
                    errors.append(f"Video {video.path}: {str(e)}")

            # Cleanup timelapses
            old_timelapses = Timelapse.query.filter(
                Timelapse.uploaded == True,
                Timelapse.created_at < cutoff_date
            ).all()

            for timelapse in old_timelapses:
                try:
                    file_path = media_root / timelapse.path
                    if file_path.exists():
                        file_path.unlink()
                    db.session.delete(timelapse)
                    deleted["timelapses"] += 1
                except Exception as e:
                    logger.error(f"Failed to delete timelapse {timelapse.path}: {e}")
                    errors.append(f"Timelapse {timelapse.path}: {str(e)}")

            db.session.commit()

            total_deleted = sum(deleted.values())
            logger.info(f"Cleanup complete: deleted {total_deleted} files older than {retention_days} days")

            return {
                "ok": True,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "deleted": deleted,
                "total_deleted": total_deleted,
                "errors": errors
            }

        except Exception as e:
            logger.exception("Cleanup failed")
            return {"ok": False, "error": str(e)}

    def _is_upload_time_window(self) -> tuple[bool, str]:
        """Check if current time is within configured upload window.

        Returns:
            tuple of (is_allowed, reason_message)
        """
        config = self._load_config()
        start_hour = int(config.get("UPLOAD_START_HOUR", "22"))
        end_hour = int(config.get("UPLOAD_END_HOUR", "6"))

        now = datetime.now()
        current_hour = now.hour

        # Handle time window that spans midnight (e.g., 22:00 to 6:00)
        if start_hour > end_hour:
            is_allowed = current_hour >= start_hour or current_hour < end_hour
        else:
            # Handle time window within same day (e.g., 8:00 to 18:00)
            is_allowed = start_hour <= current_hour < end_hour

        if is_allowed:
            return True, f"Upload allowed (current hour: {current_hour}, window: {start_hour}-{end_hour})"
        else:
            return False, f"Upload outside time window (current hour: {current_hour}, window: {start_hour}-{end_hour})"

    def upload_all(self) -> dict:
        """Upload all configured media directories to HiDrive.

        Returns:
            dict with overall status and details for each directory
        """
        try:
            # Check if we're in the upload time window
            is_allowed, time_msg = self._is_upload_time_window()
            if not is_allowed:
                logger.info(time_msg)
                return {
                    "ok": False,
                    "skip": True,
                    "reason": "outside_time_window",
                    "message": time_msg
                }

            # Load config and create rclone config
            config = self._load_config()
            config_path = self._create_rclone_config()

            if not config_path:
                return {
                    "ok": False,
                    "error": "HiDrive credentials not configured",
                    "details": []
                }

            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            results = []

            # Upload photos
            if config.get("UPLOAD_PHOTOS") == "1":
                photos_dir = media_root / "snapshots"
                result = self._upload_directory(photos_dir, "snapshots", config_path)
                results.append({"type": "photos", **result})

                # Mark photos as uploaded
                if result.get("ok"):
                    Photo.query.filter_by(uploaded=False).update({"uploaded": True})
                    db.session.commit()

            # Upload videos
            if config.get("UPLOAD_VIDEOS") == "1":
                videos_dir = media_root / "motion_video"
                result = self._upload_directory(videos_dir, "motion_video", config_path)
                results.append({"type": "videos", **result})

                # Mark videos as uploaded
                if result.get("ok"):
                    Video.query.filter_by(uploaded=False).update({"uploaded": True})
                    db.session.commit()

            # Upload timelapses
            if config.get("UPLOAD_TIMELAPSES") == "1":
                timelapse_dir = media_root / "timelapse_video"
                result = self._upload_directory(timelapse_dir, "timelapse_video", config_path)
                results.append({"type": "timelapses", **result})

                # Mark timelapses as uploaded
                if result.get("ok"):
                    Timelapse.query.filter_by(uploaded=False).update({"uploaded": True})
                    db.session.commit()

            # Clean up config file
            try:
                os.unlink(config_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp config: {e}")

            # Cleanup old uploaded files
            cleanup_result = self.cleanup_old_files()

            # Determine overall status
            success_count = sum(1 for r in results if r.get("ok"))
            total_count = len(results)

            return {
                "ok": success_count == total_count and total_count > 0,
                "success_count": success_count,
                "total_count": total_count,
                "details": results,
                "cleanup": cleanup_result
            }

        except Exception as e:
            logger.exception("Upload failed")
            return {"ok": False, "error": str(e)}

    def test_connection(self) -> dict:
        """Test HiDrive connection and credentials.

        Returns:
            dict with connection status
        """
        try:
            config = self._load_config()
            config_path = self._create_rclone_config()

            if not config_path:
                return {"ok": False, "error": "Credentials not configured"}

            # Test with lsd (list directories)
            cmd = [
                "rclone",
                "lsd",
                "hidrive:/",
                f"--config={config_path}",
                "--verbose",
            ]

            logger.info(f"Testing HiDrive connection for user: {config.get('HIDRIVE_USER')}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            # Clean up config
            try:
                os.unlink(config_path)
            except Exception:
                pass

            if result.returncode != 0:
                error_msg = result.stderr

                # Provide helpful error messages
                if "403" in error_msg or "Forbidden" in error_msg:
                    return {
                        "ok": False,
                        "error": "Access denied (403 Forbidden). Check username and password.",
                        "details": error_msg[:300]
                    }
                elif "401" in error_msg or "Unauthorized" in error_msg:
                    return {
                        "ok": False,
                        "error": "Authentication failed (401 Unauthorized). Invalid credentials.",
                        "details": error_msg[:300]
                    }
                elif "timeout" in error_msg.lower():
                    return {
                        "ok": False,
                        "error": "Connection timeout. Check network and HiDrive availability.",
                        "details": error_msg[:300]
                    }
                else:
                    return {
                        "ok": False,
                        "error": f"Connection failed: {error_msg[:200]}"
                    }

            return {
                "ok": True,
                "message": "Connection successful",
                "output": result.stdout[:200]
            }

        except FileNotFoundError:
            return {"ok": False, "error": "rclone not installed"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Connection timeout"}
        except Exception as e:
            logger.exception("Connection test failed")
            return {"ok": False, "error": str(e)}


# Singleton instance
upload_service = UploadService()
