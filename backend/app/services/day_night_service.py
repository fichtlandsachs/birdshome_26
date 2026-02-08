"""Day/Night mode service for automatic camera switching.

This service analyzes image brightness to automatically switch between day and night modes.
In night mode, images are converted to grayscale and streaming parameters are adjusted.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from flask import current_app

logger = logging.getLogger(__name__)


@dataclass
class DayNightStatus:
    """Current day/night mode status."""
    mode: Literal["DAY", "NIGHT"]
    brightness: float  # 0-100
    last_check: float  # timestamp
    threshold: float  # configured threshold


class DayNightService:
    """Service for automatic day/night mode switching based on brightness."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current_mode: Literal["DAY", "NIGHT"] = "DAY"
        self._last_brightness = 50.0
        self._last_check = 0.0
        self._brightness_threshold = 30.0  # Default threshold
        self._check_interval = 60.0  # Check every 60 seconds
        self._monitor_thread = None
        self._running = False

    def get_status(self) -> DayNightStatus:
        """Get current day/night status."""
        with self._lock:
            return DayNightStatus(
                mode=self._current_mode,
                brightness=self._last_brightness,
                last_check=self._last_check,
                threshold=self._brightness_threshold
            )

    def analyze_brightness(self, image_path: Path) -> float:
        """Analyze brightness of an image using ffmpeg.

        Args:
            image_path: Path to the image file

        Returns:
            Brightness value between 0 (dark) and 100 (bright)
        """
        try:
            ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")

            # Use ffmpeg to analyze brightness
            # We use the signalstats filter to get mean luminance
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-i", str(image_path),
                "-vf", "signalstats",
                "-f", "null",
                "-"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            # Parse YAVG (average luminance) from output
            # Format: [Parsed_signalstats_0 @ ...] YAVG:123.456
            for line in result.stderr.split('\n'):
                if 'YAVG:' in line:
                    yavg_str = line.split('YAVG:')[1].split()[0]
                    yavg = float(yavg_str)
                    # Convert from 0-255 range to 0-100 percentage
                    brightness = (yavg / 255.0) * 100.0
                    return brightness

            logger.warning(f"Could not parse brightness from ffmpeg output")
            return 50.0  # Default to mid-range

        except subprocess.TimeoutExpired:
            logger.error("Brightness analysis timed out")
            return self._last_brightness
        except Exception as e:
            logger.error(f"Error analyzing brightness: {e}")
            return self._last_brightness

    def capture_test_frame(self) -> Path | None:
        """Capture a test frame for brightness analysis.

        Returns:
            Path to captured frame or None on error
        """
        try:
            from ..models import Setting

            # Get video source configuration
            video_source_setting = Setting.query.filter_by(key="VIDEO_SOURCE").first()
            if not video_source_setting:
                video_source = current_app.config.get("VIDEO_SOURCE")
            else:
                video_source = video_source_setting.value

            if not video_source:
                logger.warning("VIDEO_SOURCE not configured")
                return None

            # Create temp directory for test frames
            temp_dir = Path("/tmp/birdshome")
            temp_dir.mkdir(parents=True, exist_ok=True)

            output_path = temp_dir / "brightness_test.jpg"

            # Capture single frame
            ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
            ]

            # Add video source
            if video_source.startswith("-"):
                cmd.extend(video_source.split())
            else:
                cmd.extend(["-i", video_source])

            cmd.extend([
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                str(output_path)
            ])

            result = subprocess.run(cmd, capture_output=True, timeout=15)

            if result.returncode != 0:
                logger.error(f"Failed to capture test frame: {result.stderr.decode()}")
                return None

            if not output_path.exists():
                logger.error("Test frame was not created")
                return None

            return output_path

        except Exception as e:
            logger.error(f"Error capturing test frame: {e}")
            return None

    def check_and_update_mode(self) -> bool:
        """Check brightness and update mode if needed.

        Returns:
            True if mode was changed, False otherwise
        """
        with self._lock:
            # Capture test frame
            test_frame = self.capture_test_frame()
            if not test_frame:
                logger.warning("Could not capture test frame for brightness check")
                return False

            # Analyze brightness
            brightness = self.analyze_brightness(test_frame)
            self._last_brightness = brightness
            self._last_check = time.time()

            # Clean up test frame
            try:
                test_frame.unlink()
            except:
                pass

            # Determine mode based on brightness with hysteresis
            # Use hysteresis to avoid flickering:
            # - Switch to NIGHT when brightness < threshold
            # - Switch to DAY when brightness > threshold + 10
            old_mode = self._current_mode

            if self._current_mode == "DAY":
                if brightness < self._brightness_threshold:
                    self._current_mode = "NIGHT"
                    logger.info(f"Switching to NIGHT mode (brightness: {brightness:.1f})")
            else:  # NIGHT
                if brightness > self._brightness_threshold + 10:
                    self._current_mode = "DAY"
                    logger.info(f"Switching to DAY mode (brightness: {brightness:.1f})")

            return old_mode != self._current_mode

    def _monitor_loop(self):
        """Background thread that periodically checks brightness and updates mode."""
        logger.info("Day/Night monitor thread started")

        while self._running:
            try:
                if self.check_and_update_mode():
                    # Mode changed - restart UDP source stream with new settings
                    try:
                        from .stream_service import stream_service
                        logger.info("Restarting UDP source stream with new day/night mode settings")
                        # Restart only the UDP source, not the entire stream service
                        # This ensures motion detection and other services continue working
                        stream_service.restart_udp_source()
                    except Exception as e:
                        logger.error(f"Error restarting UDP source after mode change: {e}")

            except Exception as e:
                logger.error(f"Error in day/night monitor loop: {e}")

            # Sleep for check interval
            time.sleep(self._check_interval)

        logger.info("Day/Night monitor thread stopped")

    def start_monitoring(self, threshold: float = 30.0, interval: float = 60.0):
        """Start background brightness monitoring.

        Args:
            threshold: Brightness threshold for switching to night mode (0-100)
            interval: Check interval in seconds
        """
        with self._lock:
            if self._running:
                logger.warning("Day/Night monitoring already running")
                return

            self._brightness_threshold = threshold
            self._check_interval = interval
            self._running = True

            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="DayNightMonitor"
            )
            self._monitor_thread.start()
            logger.info(f"Started day/night monitoring (threshold: {threshold}, interval: {interval}s)")

    def stop_monitoring(self):
        """Stop background brightness monitoring."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            logger.info("Stopping day/night monitoring")

        # Wait for thread to finish
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def get_mode(self) -> Literal["DAY", "NIGHT"]:
        """Get current mode."""
        with self._lock:
            return self._current_mode

    def set_mode(self, mode: Literal["DAY", "NIGHT"]):
        """Manually set day/night mode.

        Args:
            mode: Mode to set ("DAY" or "NIGHT")
        """
        with self._lock:
            if mode not in ("DAY", "NIGHT"):
                raise ValueError(f"Invalid mode: {mode}. Must be 'DAY' or 'NIGHT'")

            old_mode = self._current_mode
            self._current_mode = mode

            if old_mode != mode:
                logger.info(f"Manually switched from {old_mode} to {mode} mode")

    def get_stream_params(self, fps: int) -> dict:
        """Get streaming parameters for current mode.

        Args:
            fps: Stream framerate

        Returns:
            Dictionary with ffmpeg parameters
        """
        mode = self.get_mode()

        if mode == "NIGHT":
            return {
                "crf": "22",
                "gop_size": str(fps * 2),
                "keyint_min": str(fps),
                "sc_threshold": "0",
                "grayscale": True
            }
        else:  # DAY
            return {
                "crf": "23",
                "gop_size": str(fps * 2),
                "keyint_min": str(fps),
                "sc_threshold": "0",
                "grayscale": False
            }


# Singleton instance
day_night_service = DayNightService()
