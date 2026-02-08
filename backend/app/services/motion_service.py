"""Motion detection service with automatic video recording.

This service monitors the video feed for motion and automatically records
video clips when motion is detected.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from threading import Thread, Event, Lock
import cv2
from flask import current_app

from ..extensions import db
from ..models import Video
from .video_utils import get_rotation_filter, apply_video_filters

logger = logging.getLogger(__name__)


class MotionDetectionService:
    """Service for detecting motion and recording video clips.

    Supports two trigger modes:
    1. Frame difference detection (optical motion)
    2. GPIO motion sensor (PIR sensor)

    Both triggers share the same recording guard to prevent multiple concurrent recordings.
    """

    def __init__(self):
        self.running = False
        self.stop_event = Event()
        self.recording_lock = False
        self.last_motion_time = 0
        self.config = {}
        self.app = None
        self.recording_guard = Lock()
        self.gpio_available = False
        self.gpio_thread = None

    def _load_config(self) -> None:
        """Load config from database settings into thread-safe dict."""
        from ..models import Setting

        # Load settings from database
        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        # Build config dict with database values, fallback to app config
        self.config = {
            "VIDEO_SOURCE": settings.get("VIDEO_SOURCE") or current_app.config.get("VIDEO_SOURCE"),
            "AUDIO_SOURCE": settings.get("AUDIO_SOURCE") or current_app.config.get("AUDIO_SOURCE", ""),
            "MOTION_SOURCE": settings.get("MOTION_SOURCE") or current_app.config.get("MOTION_SOURCE", ""),
            "STREAM_UDP_URL": settings.get("STREAM_UDP_URL") or current_app.config.get("STREAM_UDP_URL", ""),
            "VIDEO_DIR": current_app.config.get("VIDEO_DIR"),
            "VIDEO_FPS": settings.get("RECORD_FPS") or current_app.config.get("RECORD_FPS", "30"),
            "VIDEO_RES": settings.get("RECORD_RES") or current_app.config.get("RECORD_RES", "1280x720"),
            "VIDEO_ROTATION": settings.get("VIDEO_ROTATION") or current_app.config.get("VIDEO_ROTATION", "0"),
            "MOTION_THRESHOLD": settings.get("MOTION_THRESHOLD") or current_app.config.get("MOTION_THRESHOLD", "25"),
            "MOTION_DURATION_S": settings.get("MOTION_DURATION_S") or current_app.config.get("MOTION_DURATION_S", "10"),
            "MOTION_COOLDOWN_S": settings.get("MOTION_COOLDOWN_S") or current_app.config.get("MOTION_COOLDOWN_S", "5"),
            "MOTION_SENSOR_GPIO": settings.get("MOTION_SENSOR_GPIO") or current_app.config.get("MOTION_SENSOR_GPIO", "22"),
            "MOTION_SENSOR_ENABLED": settings.get("MOTION_SENSOR_ENABLED") or current_app.config.get("MOTION_SENSOR_ENABLED", "0"),
            "MOTION_FRAMEDIFF_ENABLED": settings.get("MOTION_FRAMEDIFF_ENABLED") or current_app.config.get("MOTION_FRAMEDIFF_ENABLED", "1"),
            "FFMPEG_BIN": current_app.config.get("FFMPEG_BIN", "ffmpeg"),
            "PREFIX": settings.get("PREFIX") or current_app.config.get("PREFIX", "nest_"),
        }
    def start(self) -> dict:
        """Start the motion detection service."""
        if self.running:
            return {"ok": True, "status": "running", "info": "Motion detection already running"}

        enabled = current_app.config.get("MOTION_ENABLED", "1")
        if enabled not in ("1", "true", "True", "yes", "Yes"):
            return {"ok": False, "error": "Motion detection disabled in settings"}

        # Store app reference and config for background thread
        self.app = current_app._get_current_object()
        self._load_config()

        # Validate that at least one detection method is enabled
        framediff_enabled = self.config.get("MOTION_FRAMEDIFF_ENABLED", "1")
        sensor_enabled = self.config.get("MOTION_SENSOR_ENABLED", "0")

        framediff_on = framediff_enabled in ("1", "true", "True", "yes", "Yes")
        sensor_on = sensor_enabled in ("1", "true", "True", "yes", "Yes")

        if not framediff_on and not sensor_on:
            return {"ok": False, "error": "At least one detection method (Frame-Diff or GPIO) must be enabled"}

        self.running = True
        self.stop_event.clear()

        # Start frame-diff detection thread if enabled
        if framediff_on:
            thread = Thread(target=self._detection_loop, daemon=True)
            thread.start()
            logger.info("Motion detection (frame-diff) started")

        # Start GPIO sensor thread if enabled
        if sensor_on:
            self.gpio_thread = Thread(target=self._gpio_sensor_loop, daemon=True)
            self.gpio_thread.start()
            logger.info("Motion sensor (GPIO) monitoring started")

        # Update database setting to persist service state
        with self.app.app_context():
            from ..models import Setting
            setting = Setting.query.filter_by(key="MOTION_SERVICE_ENABLED").first()
            if setting:
                setting.value = "1"
            else:
                setting = Setting(key="MOTION_SERVICE_ENABLED", value="1")
                db.session.add(setting)
                db.session.commit()

        methods = []
        if framediff_on:
            methods.append("frame-diff")
        if sensor_on:
            methods.append("GPIO")

        logger.info(f"Motion detection service started with methods: {', '.join(methods)}")
        return {"ok": True, "status": "running", "methods": methods}

    def stop(self) -> dict:
        """Stop the motion detection service."""
        if not self.running:
            return {"ok": False, "error": "Motion detection not running"}

        self.running = False
        self.stop_event.set()

        # Update database setting to persist service state
        if self.app:
            with self.app.app_context():
                from ..models import Setting
                setting = Setting.query.filter_by(key="MOTION_SERVICE_ENABLED").first()
                if setting:
                    setting.value = "0"
                else:
                    setting = Setting(key="MOTION_SERVICE_ENABLED", value="0")
                    db.session.add(setting)
                db.session.commit()

        logger.info("Motion detection service stopped")
        return {"ok": True, "status": "stopped"}

    def status(self) -> dict:
        """Get current status."""
        framediff_enabled = self.config.get("MOTION_FRAMEDIFF_ENABLED", "1") in ("1", "true", "True", "yes", "Yes") if self.config else False
        gpio_enabled = self.config.get("MOTION_SENSOR_ENABLED", "0") in ("1", "true", "True", "yes", "Yes") if self.config else False

        return {
            "running": self.running,
            "recording": self.recording_lock,
            "last_motion": self.last_motion_time,
            "gpio_enabled": gpio_enabled,
            "framediff_enabled": framediff_enabled,
            "gpio_available": self.gpio_available
        }

    def _trigger_recording(self, source: str = "unknown", frame=None):
        """Central method to trigger recording from any source.

        This ensures only one recording runs at a time, regardless of trigger source.
        """
        current_time = time.time()
        cooldown = int(self.config.get("MOTION_COOLDOWN_S", 5))

        # Check cooldown
        if current_time - self.last_motion_time <= cooldown:
            logger.debug(f"Motion trigger from {source} ignored (cooldown active)")
            return

        # Try to acquire recording guard (non-blocking)
        if self.recording_guard.acquire(blocking=False):
            logger.info(f"Motion triggered by {source}")
            self.last_motion_time = current_time

            # Save motion snapshot if frame is provided
            if frame is not None:
                self._save_motion_snapshot(frame)

            #self.recording_lock = True

            # Start recording in background thread
            record_thread = Thread(target=self._record_video, daemon=True)
            record_thread.start()
        else:
            logger.debug(f"Motion trigger from {source} ignored (recording already in progress)")

    def _save_motion_snapshot(self, frame):
        """Save the current frame as JPG in the motion directory."""
        try:
            with self.app.app_context():
                media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
                motion_dir = media_root / "motion"
                motion_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = current_app.config.get("PREFIX", "nest_")
                filename = f"{prefix}motion_{timestamp}.jpg"
                output_path = motion_dir / filename

                # Save frame as JPG
                cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

                logger.info(f"Motion snapshot saved: {filename}")

        except Exception as e:
            logger.exception("Error saving motion snapshot")

    def _save_debug_snapshot(self, frame, gray, thresh):
        """Save debug frames to analyze motion detection (temporary for testing)."""
        try:
            with self.app.app_context():
                media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
                motion_dir = media_root / "motion"
                motion_dir.mkdir(parents=True, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = current_app.config.get("PREFIX", "nest_")

                # Save original frame
                cv2.imwrite(str(motion_dir / f"{prefix}debug_{timestamp}_original.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

                logger.info(f"Debug snapshots saved: {timestamp}")

        except Exception as e:
            logger.exception("Error saving debug snapshot")

    def _detection_loop(self):
        """Main motion detection loop using simple frame difference.

        Reads frames from UDP stream instead of direct camera access.
        """
        try:
            # Use UDP stream as motion source (shared with HLS, WebRTC, timelapse)
            udp_url = self.config.get("STREAM_UDP_URL") or self.config.get("MOTION_SOURCE")
            if not udp_url:
                logger.error("STREAM_UDP_URL/MOTION_SOURCE not configured - stopping motion detection")
                self.running = False
                return

            # Wait for UDP stream to be available (stream service starts it)
            logger.info("Waiting for UDP stream to become available...")
            max_retries = 30  # 30 seconds
            for i in range(max_retries):
                cap = cv2.VideoCapture(udp_url, cv2.CAP_FFMPEG)
                if cap.isOpened():
                    break
                cap.release()
                if i < max_retries - 1:
                    time.sleep(1)

            if not cap.isOpened():
                logger.error(f"Failed to open UDP stream: {udp_url} (timeout after {max_retries}s)")
                self.running = False
                return

            # Set buffer size to reduce latency
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Get motion detection parameters from stored config
            threshold = int(self.config.get("MOTION_THRESHOLD", 25))
            cooldown = int(self.config.get("MOTION_COOLDOWN_S", 5))

            logger.info(f"Motion detection running on UDP stream {udp_url} (threshold={threshold}, checking 2-3 fps)")

            prev_frame = None
            last_config_reload = time.time()
            consecutive_failures = 0
            max_failures = 10

            while self.running and not self.stop_event.is_set():
                # Reload config from database every 5 minutes
                current_time = time.time()
                if current_time - last_config_reload >= 300:  # 300 seconds = 5 minutes
                    with self.app.app_context():
                        self._load_config()
                        threshold = int(self.config.get("MOTION_THRESHOLD", 25))
                        cooldown = int(self.config.get("MOTION_COOLDOWN_S", 5))
                        logger.info(f"Reloaded motion detection config from database (threshold={threshold})")
                        last_config_reload = current_time

                ret, frame = cap.read()
                if not ret:
                    consecutive_failures += 1
                    logger.warning(f"Failed to read frame from UDP stream (failure {consecutive_failures}/{max_failures})")

                    if consecutive_failures >= max_failures:
                        logger.error("Too many consecutive failures, attempting to reconnect to UDP stream...")
                        cap.release()
                        time.sleep(2)

                        # Try to reconnect
                        cap = cv2.VideoCapture(udp_url, cv2.CAP_FFMPEG)
                        if not cap.isOpened():
                            logger.error("Failed to reconnect to UDP stream, stopping motion detection")
                            self.running = False
                            break

                        consecutive_failures = 0
                        logger.info("Successfully reconnected to UDP stream")

                    time.sleep(1)
                    continue

                # Reset failure counter on successful read
                consecutive_failures = 0

                # Convert to grayscale and apply light blur to reduce noise
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)  # Lighter blur for better motion detection

                # Initialize previous frame
                if prev_frame is None:
                    prev_frame = gray
                    time.sleep(0.4)  # ~2.5 fps
                    continue

                # Calculate frame difference
                frame_delta = cv2.absdiff(prev_frame, gray)
                thresh = cv2.threshold(frame_delta, threshold, 255, cv2.THRESH_BINARY)[1]

                # Dilate to fill gaps in motion regions
                thresh = cv2.dilate(thresh, None, iterations=2)

                # Find contours to detect actual motion objects
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cont in contours:
                    cont_diff = cv2.contourArea(cont)
                    if cont_diff > 35:
                        logger.info(f"${cv2.contourArea(cont)}")
                        self._trigger_recording(
                            source=f"frame-diff ({cont_diff}",
                            frame=frame
                        )
                # Filter contours by minimum area (ignore tiny movements)
                #min_area = (total_pixels if 'total_pixels' in locals() else frame.shape[0] * frame.shape[1]) * 0.001  # 0.1% of frame
                #significant_contours = [c for c in contours if cv2.contourArea(c) > min_area]

                # Calculate motion score based on significant contours
                #motion_pixels = sum(cv2.contourArea(c) for c in significant_contours)
                #total_pixels = thresh.shape[0] * thresh.shape[1]
                #motion_percent = (motion_pixels / total_pixels) * 100

                # Check if motion detected - require measurable change (> 0.5% significant movement)
                #logger.info(f"Motion check: pixels={motion_pixels:.2f}, percent={motion_percent:.2f}%, contours={len(significant_contours)}, threshold={threshold}")

                # DEBUG: Save test frame every 10 seconds to verify detection is working
                if not hasattr(self, '_last_debug_save'):
                    self._last_debug_save = 0
                if current_time - self._last_debug_save >= 10:
                    self._save_debug_snapshot(frame, gray, thresh)
                    self._last_debug_save = current_time

                #if motion_pixels > 200 and len(significant_contours) > 0:


                # Update previous frame
                prev_frame = gray

                # Check 2-3 times per second (0.33-0.4s delay)
                time.sleep(0.4)

            cap.release()

        except Exception as e:
            logger.exception("Error in motion detection loop")
            self.running = False

    def _gpio_sensor_loop(self):
        """Monitor GPIO motion sensor (PIR) for triggers."""
        try:
            # Try to import GPIO library
            try:
                import RPi.GPIO as GPIO
                self.gpio_available = True
            except (ImportError, RuntimeError):
                logger.warning("RPi.GPIO not available - GPIO motion sensor disabled")
                self.gpio_available = False
                return

            gpio_pin = int(self.config.get("MOTION_SENSOR_GPIO", 23))

            # Setup GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            logger.info(f"GPIO motion sensor monitoring on pin {gpio_pin}")

            while self.running and not self.stop_event.is_set():
                # Check sensor state
                if GPIO.input(gpio_pin):
                    self._trigger_recording(source="gpio-sensor")
                    # Wait a bit to debounce
                    time.sleep(0.5)
                else:
                    # Check sensor 2-3 times per second
                    time.sleep(0.4)

            # Cleanup GPIO
            GPIO.cleanup(gpio_pin)
            logger.info("GPIO motion sensor monitoring stopped")

        except Exception as e:
            logger.exception("Error in GPIO sensor loop")
            self.gpio_available = False

    def _record_video(self):
        """Record a video clip when motion is detected."""
        if self.recording_lock:
            logger.debug("Recording already in progress, skipping")
            return

        if self.recording_lock:
            logger.debug("Recording already in progress, skipping")
            return

        self.recording_lock = True

        try:
            # Get configuration from stored config
            duration = int(self.config.get("MOTION_DURATION_S", 10))
            resolution = self.config.get("VIDEO_RES", "640x480")
            fps = int(self.config.get("VIDEO_FPS", 30))
            video_source = self.config.get("MOTION_SOURCE") or self.config.get("VIDEO_SOURCE")
            audio_source = self.config.get("AUDIO_SOURCE", "")

            if not video_source:
                logger.error("MOTION_SOURCE/VIDEO_SOURCE not configured")
                return

            # Prepare output directory (need app context for this)
            with self.app.app_context():
                media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
                videos_dir = media_root / "videos"
                videos_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                prefix = current_app.config.get("PREFIX", "nest_")
                filename = f"{prefix}motion_{timestamp}.mp4"
                output_path = videos_dir / filename

            logger.info(f"Recording motion video: {filename} ({duration}s @ {resolution} {fps}fps)")

            # Build ffmpeg command
            #cmd = [
            #    self.config.get("FFMPEG_BIN", "ffmpeg"),
            #    "-hide_banner",
            #    "-loglevel", "error",
            #]

            # Add video source
            #if video_source.startswith("-"):
            #    cmd.extend(video_source.split())
            #else:
            #    cmd.extend(["-i", video_source])

            # Add audio source if available
            #if audio_source:
            #    if audio_source.startswith("-"):
            #        cmd.extend(audio_source.split())
            #    else:
            #        cmd.extend(["-i", audio_source])

            # Output options
            width, height = resolution.split('×')
            #cmd.extend([
            #    "-t", str(duration),  # Duration
            #])

            # Apply video filters (scale + rotation)
            rotation = self.config.get("VIDEO_ROTATION", "0")
            rotation_filter = get_rotation_filter(rotation)
            scale_filter = f"scale={width}:{height}"
            filter_args = apply_video_filters(scale_filter, rotation_filter)
            #cmd.extend(filter_args)

            #cmd.extend([
            #    "-r", str(fps),
            #    "-c:v", "libx264",
            #    "-preset", "fast",
            #    "-crf", "23",
            #    "-pix_fmt", "yuv420p",
            #])

            # Audio encoding (if audio source present)
            #if audio_source:
            #    cmd.extend([
            #        "-c:a", "aac",
            #        "-b:a", "128k",
            #    ])

            #cmd.extend([
            #    "-y",  # Overwrite if exists
            #    str(output_path)
            #])
            # Build ffmpeg command with robust UDP options
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-fflags", "+genpts+discardcorrupt+igndts",
                "-flags", "low_delay",
                "-strict", "experimental",
                "-analyzeduration", "5000000",
                "-probesize", "10000000",
                "-i", video_source,
                "-t", str(duration),
                "-c:v", "copy",
            ]

            # Add audio handling based on configuration
            if audio_source and audio_source.strip():
                # Audio is configured - try to copy it
                logger.info(f"Audio source configured: {audio_source}")
                cmd.extend(["-c:a", "copy"])
            else:
                # No audio configured - disable audio track
                logger.info("No audio source configured, disabling audio")
                cmd.extend(["-an"])

            # Add output options
            cmd.extend([
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                "-y", str(output_path)
            ])

            # Wait briefly to ensure UDP stream has sent at least one keyframe
            # This helps ffmpeg properly detect stream parameters
            #logger.info("Waiting 2 seconds for UDP stream to stabilize...")
            #time.sleep(2)

            # Execute recording
            logger.info(f"Starting recording with command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 15)

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return

            # Verify file was created
            if not output_path.exists():
                logger.error("Video file was not created")
                return

            # Get file info
            stat = output_path.stat()
            relative_path = str(output_path.relative_to(media_root))

            # Get video duration and resolution using ffprobe
            try:
                probe_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration:stream=width,height",
                    "-of", "default=noprint_wrappers=1",
                    str(output_path)
                ]
                probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=5)

                actual_duration = None
                actual_width = None
                actual_height = None

                for line in probe_result.stdout.strip().split('\n'):
                    if line.startswith("duration="):
                        actual_duration = int(float(line.split('=')[1]))
                    elif line.startswith("width="):
                        actual_width = int(line.split('=')[1])
                    elif line.startswith("height="):
                        actual_height = int(line.split('=')[1])

                actual_resolution = f"{actual_width}x{actual_height}" if actual_width and actual_height else resolution

            except Exception:
                actual_duration = duration
                actual_resolution = resolution

            # Save to database (need app context)
            with self.app.app_context():
                video = Video(
                    path=relative_path,
                    has_birds=False,  # Will be detected later
                    duration_s=actual_duration,
                    resolution=actual_resolution,
                    size_bytes=stat.st_size,
                    uploaded=False,
                    notes="Motion detected"
                )
                db.session.add(video)
                db.session.commit()

            logger.info(f"Motion video recorded: {relative_path} ({stat.st_size} bytes, {actual_duration}s)")

        except subprocess.TimeoutExpired:
            logger.error("Video recording timed out")
        except Exception as e:
            logger.exception("Error recording video")
        finally:
            self.recording_lock = False
            if self.recording_guard.locked():
                self.recording_guard.release()


# Singleton instance
motion_service = MotionDetectionService()
