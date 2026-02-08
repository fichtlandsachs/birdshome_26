"""Manual recording service for on-demand stream recording.

This service allows users to manually start/stop video recordings
from the live stream via the web UI.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import Video

logger = logging.getLogger(__name__)


@dataclass
class RecordingStatus:
    """Current recording status."""
    recording: bool
    started_at: float | None
    output_path: str | None
    duration: float  # seconds
    pid: int | None


class RecordingService:
    """Service for manual stream recording."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._started_at: float | None = None
        self._output_path: Path | None = None
        self._pidfile = Path("/tmp/birdshome-recording.pid")
        self._app = None  # Flask app reference for background thread

    def status(self) -> RecordingStatus:
        """Get current recording status."""
        with self._lock:
            is_recording = self._proc is not None and self._proc.poll() is None
            duration = 0.0

            if is_recording and self._started_at:
                duration = time.time() - self._started_at

            return RecordingStatus(
                recording=is_recording,
                started_at=self._started_at,
                output_path=str(self._output_path) if self._output_path else None,
                duration=duration,
                pid=self._proc.pid if self._proc else None
            )

    def _monitor_recording(self):
        """Monitor recording process and auto-save when finished."""
        try:
            while True:
                time.sleep(1)

                with self._lock:
                    # Check if process is still running
                    if not self._proc or self._proc.poll() is not None:
                        # Process finished, save to database
                        logger.info("Recording finished automatically, saving to database...")
                        self._finalize_recording()
                        break
        except Exception as e:
            logger.error(f"Error in recording monitor: {e}")

    def _finalize_recording(self):
        """Finalize recording and save to database (called with lock held)."""
        try:
            if not self._output_path or not self._output_path.exists():
                logger.warning("Recording file not found after finishing")
                return

            # Calculate duration
            duration = 0.0
            if self._started_at:
                duration = time.time() - self._started_at

            # Get file info
            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            file_size = self._output_path.stat().st_size
            relative_path = str(self._output_path.relative_to(media_root))

            # Save to database
            if self._app:
                with self._app.app_context():
                    video = Video(
                        path=relative_path,
                        resolution=None,
                        has_birds=False,
                        uploaded=False
                    )
                    db.session.add(video)
                    db.session.commit()
                    logger.info(f"Recording saved: {relative_path} ({file_size} bytes, {duration:.1f}s)")
            else:
                logger.warning("No Flask app context available, skipping database save")

        except Exception as e:
            logger.error(f"Error finalizing recording: {e}")
        finally:
            # Cleanup
            self._proc = None
            self._started_at = None
            self._output_path = None
            self._pidfile.unlink(missing_ok=True)

    def start(self) -> dict:
        """Start manual recording from UDP stream.

        Returns:
            dict with status and error information
        """
        with self._lock:
            # Check if already recording
            if self._proc and self._proc.poll() is None:
                return {
                    "ok": False,
                    "error": "Recording already in progress",
                    "recording": True
                }

            try:
                # Store Flask app reference for background thread
                self._app = current_app._get_current_object()

                # Load configuration
                from ..models import Setting

                media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
                video_dir = media_root / "motion_video"
                video_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = Setting.query.filter_by(key="PREFIX").first()
                prefix_str = prefix.value if prefix else "nest_"
                filename = f"{prefix_str}manual_{timestamp}.mp4"
                self._output_path = video_dir / filename

                # Get UDP stream URL
                udp_url_setting = Setting.query.filter_by(key="STREAM_UDP_URL").first()
                udp_url = udp_url_setting.value if udp_url_setting else "udp://127.0.0.1:5004?pkt_size=1316&reuse=1"

                # Get recording resolution and FPS
                record_res_setting = Setting.query.filter_by(key="RECORD_RES").first()
                record_res = record_res_setting.value if record_res_setting else "640x480"

                record_fps_setting = Setting.query.filter_by(key="RECORD_FPS").first()
                record_fps = record_fps_setting.value if record_fps_setting else "30"

                # Get recording duration (in seconds)
                duration_setting = Setting.query.filter_by(key="MOTION_DURATION_S").first()
                duration = int(duration_setting.value) if duration_setting else 10

                # Build ffmpeg command to record from UDP stream
                ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")

                # Check if audio source is configured
                audio_source_setting = Setting.query.filter_by(key="AUDIO_SOURCE").first()
                has_audio = audio_source_setting and audio_source_setting.value and audio_source_setting.value.strip()

                cmd = [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel", "warning",
                    "-fflags", "+genpts+discardcorrupt",
                    "-analyzeduration", "2000000",
                    "-probesize", "10000000",
                    "-i", udp_url,
                    "-t", str(duration),  # Limit recording duration
                    "-c:v", "copy",  # Copy video stream without re-encoding
                ]

                # Only add audio encoding if audio source is configured
                if has_audio:
                    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
                else:
                    cmd.extend(["-an"])  # No audio

                cmd.extend([
                    "-movflags", "+faststart",
                    "-avoid_negative_ts", "make_zero",
                    "-y",
                    str(self._output_path)
                ])

                logger.info(f"Starting manual recording: {filename}")

                # Start recording process
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )

                self._started_at = time.time()
                self._pidfile.write_text(str(self._proc.pid))

                # Start a monitor thread to auto-save when ffmpeg finishes
                monitor_thread = threading.Thread(target=self._monitor_recording, daemon=True)
                monitor_thread.start()

                return {
                    "ok": True,
                    "recording": True,
                    "output": str(self._output_path.relative_to(media_root)),
                    "pid": self._proc.pid,
                    "duration": duration
                }

            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                self._proc = None
                self._started_at = None
                self._output_path = None
                return {
                    "ok": False,
                    "error": str(e),
                    "recording": False
                }

    def stop(self) -> dict:
        """Stop current recording.

        Returns:
            dict with status and recorded video information
        """
        with self._lock:
            if not self._proc:
                return {
                    "ok": False,
                    "error": "No recording in progress",
                    "recording": False
                }

            try:
                # Stop ffmpeg gracefully with SIGTERM
                if self._proc.poll() is None:
                    logger.info("Stopping recording...")
                    try:
                        if hasattr(os, 'killpg'):
                            os.killpg(self._proc.pid, 15)  # SIGTERM
                        else:
                            self._proc.terminate()
                    except Exception:
                        self._proc.terminate()

                    # Wait for process to finish
                    try:
                        self._proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning("Recording process did not stop gracefully, killing...")
                        try:
                            if hasattr(os, 'killpg'):
                                os.killpg(self._proc.pid, 9)  # SIGKILL
                            else:
                                self._proc.kill()
                        except Exception:
                            pass

                # Calculate duration
                duration = 0.0
                if self._started_at:
                    duration = time.time() - self._started_at

                # Get file info
                media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
                file_size = 0
                relative_path = None

                if self._output_path and self._output_path.exists():
                    file_size = self._output_path.stat().st_size
                    relative_path = str(self._output_path.relative_to(media_root))

                    # Save to database
                    video = Video(
                        path=relative_path,
                        resolution=None,
                        has_birds=False,  # Manual recordings are not automatically analyzed
                        uploaded=False
                    )
                    db.session.add(video)
                    db.session.commit()

                    logger.info(f"Recording saved: {relative_path} ({file_size} bytes, {duration:.1f}s)")

                    result = {
                        "ok": True,
                        "recording": False,
                        "path": relative_path,
                        "duration": duration,
                        "size_bytes": file_size,
                        "video_id": video.id
                    }
                else:
                    logger.warning("Recording file not found after stopping")
                    result = {
                        "ok": True,
                        "recording": False,
                        "warning": "Recording file not found"
                    }

                # Cleanup
                self._proc = None
                self._started_at = None
                self._output_path = None
                self._pidfile.unlink(missing_ok=True)

                return result

            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")
                return {
                    "ok": False,
                    "error": str(e),
                    "recording": False
                }


# Singleton instance
recording_service = RecordingService()
