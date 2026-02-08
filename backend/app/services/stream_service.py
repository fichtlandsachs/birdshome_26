from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
import signal

import psutil
from flask import current_app

from .. import constants as C
from .logging_service import log_metric
from .video_utils import get_rotation_filter, apply_video_filters
from .day_night_service import day_night_service
import logging
logger = logging.getLogger(__name__)

@dataclass
class StreamStatus:
    running: bool
    mode: str
    pid: int | None
    started_at: float | None


class StreamService:
    """Single-pipeline streaming manager."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._udp_proc: subprocess.Popen | None = None
        self._started_at: float | None = None
        self._pidfile = Path("/tmp/birdshome-stream.pid")
        self._config = {}
        self._last_config_reload = 0
        self._reload_thread = None
        self._app = None

    def is_running(self) -> bool:
        """Check if stream is currently running.

        Returns:
            bool: True if stream process is active, False otherwise
        """
        return self.status().running

    def status(self) -> StreamStatus:
        with self._lock:
            # Primär: Prüfe ob Prozess läuft
            process_running = self._proc is not None and self._proc.poll() is None

            # Sekundär: Prüfe ob die Playlist kürzlich aktualisiert wurde (Fallback)
            # Das ist zuverlässiger, da der Stream auch nach Prozessabsturz kurz weiterlaufen kann
            playlist_fresh = False
            try:
                import os
                import time
                from flask import has_app_context
                if has_app_context():
                    playlist_path = Path(current_app.static_folder) / "hls" / "index.m3u8"
                    if playlist_path.exists():
                        # Prüfe ob Datei in den letzten 10 Sekunden aktualisiert wurde
                        mtime = os.path.getmtime(playlist_path)
                        age = time.time() - mtime
                        playlist_fresh = age < 10
            except Exception:
                pass

            # Der Stream läuft wenn ENTWEDER der Prozess läuft ODER die Playlist frisch ist
            is_running = process_running or playlist_fresh

            # Get mode safely
            mode = C.MODE_HLS
            try:
                from flask import has_app_context
                if has_app_context():
                    mode = str(current_app.config.get(C.STREAM_MODE, C.MODE_HLS))
            except Exception:
                pass

            return StreamStatus(
                running=is_running,
                mode=mode,
                pid=self._proc.pid if self._proc else None,
                started_at=self._started_at,
            )

    def _load_config(self) -> None:
        """Load configuration from database settings."""
        from ..models import Setting

        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        self._config = {
            C.STREAM_MODE: settings.get(C.STREAM_MODE) or current_app.config.get(C.STREAM_MODE, C.MODE_HLS),
            C.VIDEO_SOURCE: settings.get(C.VIDEO_SOURCE) or current_app.config.get(C.VIDEO_SOURCE),
            C.AUDIO_SOURCE: settings.get(C.AUDIO_SOURCE) or current_app.config.get(C.AUDIO_SOURCE),
            C.STREAM_RES: settings.get(C.STREAM_RES) or current_app.config.get(C.STREAM_RES, "1280x720"),
            C.STREAM_FPS: settings.get(C.STREAM_FPS) or current_app.config.get(C.STREAM_FPS, "30"),
            C.HLS_SEGMENT_SECONDS: settings.get(C.HLS_SEGMENT_SECONDS) or current_app.config.get(C.HLS_SEGMENT_SECONDS, "3"),
            C.HLS_PLAYLIST_SIZE: settings.get(C.HLS_PLAYLIST_SIZE) or current_app.config.get(C.HLS_PLAYLIST_SIZE, "6"),
            C.VIDEO_ROTATION: settings.get(C.VIDEO_ROTATION) or current_app.config.get(C.VIDEO_ROTATION, "0"),
            C.STREAM_UDP_URL: settings.get(C.STREAM_UDP_URL) or current_app.config.get(C.STREAM_UDP_URL),
        }
        self._last_config_reload = time.time()

    def _config_reload_loop(self):
        """Periodically reload configuration from database every 5 minutes."""
        while self._proc and self._proc.poll() is None:
            time.sleep(300)  # 5 minutes
            if self._app and self._proc and self._proc.poll() is None:
                with self._app.app_context():
                    self._load_config()
                    current_app.logger.info("Reloaded stream config from database")

    def _load_existing_proc(self) -> subprocess.Popen | None:
        """Try to attach to an existing ffmpeg process via pidfile."""
        if not self._pidfile.exists():
            return None
        try:
            pid = int(self._pidfile.read_text().strip())
        except Exception:
            self._pidfile.unlink(missing_ok=True)
            return None

        if not psutil.pid_exists(pid):
            self._pidfile.unlink(missing_ok=True)
            return None

        try:
            p = psutil.Process(pid)
            # Optional: ensure it's ffmpeg
            if "ffmpeg" not in (p.name() or "").lower():
                return None
            return p
        except Exception:
            return None

    def _start_udp_source(self, force_restart: bool = False) -> bool:
        """Start the master UDP stream by restarting the systemd service.

        Args:
            force_restart: If True, restart the service even if it's already running

        Returns:
            bool: True if service is running, False on error
        """
        try:
            # Check if service is already running
            if not force_restart:
                result = subprocess.run(
                    ["systemctl", "is-active", "birdshome-stream.service"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    logger.info("birdshome-stream.service is already active")
                    return True

            # Restart the systemd service
            logger.info("Restarting birdshome-stream.service")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "birdshome-stream.service"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.error(f"Failed to restart service: {result.stderr}")
                return False

            # Wait a moment for service to start
            time.sleep(2)

            # Verify service is running
            result = subprocess.run(
                ["systemctl", "is-active", "birdshome-stream.service"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info("birdshome-stream.service started successfully")
                return True
            else:
                logger.error("Service failed to start")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Service restart timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to restart service: {e}")
            return False

    def start(self) -> StreamStatus:
        # Load config from database
        self._app = current_app._get_current_object()
        self._load_config()

        mode = str(self._config.get(C.STREAM_MODE, C.MODE_HLS)).upper()

        # Ensure UDP source is running (needed for both HLS and WebRTC)
        if not self._start_udp_source():
            return StreamStatus(
                running=False,
                mode=mode,
                pid=None,
                started_at=None
            )

        if mode == C.MODE_WEBRTC:
            # WebRTC uses the UDP stream via aiortc
            return StreamStatus(
                running=True,
                mode=C.MODE_WEBRTC,
                pid=None,
                started_at=time.time()
            )

        with self._lock:
            # 1) If we already have a running process, return status
            if self._proc and self._proc.poll() is None:
                return self.status()

            # 2) If a previous ffmpeg is still running, attach and return
            existing = self._load_existing_proc()
            if existing:
                self._proc = existing  # type: ignore[assignment]
                return self.status()

            hls_dir = Path(self._app.static_folder) / "hls"
            hls_dir.mkdir(parents=True, exist_ok=True)

            # Sicherstellen, dass Nginx (andere) die Dateien lesen kann
            try:
                os.chmod(hls_dir, 0o775)
            except OSError:
                pass
            # Clean stale playlist/segments mit Fehlerbehandlung
            for p in hls_dir.glob("*.ts"):
                try:
                    p.unlink(missing_ok=True)
                except OSError as e:
                    self._app.logger.warning(f"Could not remove stale segment {p}: {e}")

            try:
                (hls_dir / "index.m3u8").unlink(missing_ok=True)
            except OSError:
                pass

            ffmpeg = self._app.config.get("FFMPEG_BIN", "ffmpeg")
            udp_url = self._config.get(C.STREAM_UDP_URL, "udp://127.0.0.1:5004?pkt_size=1316&reuse=1&overrun_nonfatal=1&fifo_size=5000000")
            seg_s = str(self._config.get(C.HLS_SEGMENT_SECONDS, "3"))
            list_size = str(self._config.get(C.HLS_PLAYLIST_SIZE, "6"))

            # HLS consumer: read from UDP stream and create HLS segments
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "warning",
                "-fflags", "+genpts",
                "-i", udp_url,
                "-c:v", "copy",  # Copy video codec from UDP stream
                "-c:a", "copy",  # Copy audio codec from UDP stream
                "-f", "hls",
                "-hls_time", seg_s,
                "-hls_list_size", list_size,
                "-hls_flags", "delete_segments+append_list",
                "-hls_segment_filename", str(hls_dir / "segment_%05d.ts"),
                str(hls_dir / "index.m3u8"),
            ]

            self._app.logger.info("Starting HLS pipeline: %s", " ".join(cmd))
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,  # start new process group
            )
            self._started_at = time.time()
            self._pidfile.write_text(str(self._proc.pid))

            # Start config reload thread
            self._reload_thread = threading.Thread(target=self._config_reload_loop, daemon=True)
            self._reload_thread.start()

            log_metric(self._app.logger, "stream_start", mode=C.MODE_HLS, pid=self._proc.pid)
            return self.status()

    def stop(self) -> StreamStatus:
        """Stop streaming.

        Stops HLS process but keeps UDP source running (needed for motion/timelapse).
        UDP source is only stopped when explicitly requested.
        """
        with self._lock:
            # Stop HLS process
            if not self._proc:
                # Try to kill lingering process from pidfile
                existing = self._load_existing_proc()
                if existing:
                    try:
                        os.killpg(existing.pid, signal.SIGTERM)
                    except Exception:
                        pass
                self._pidfile.unlink(missing_ok=True)
            else:
                if self._proc.poll() is None:
                    try:
                        from flask import has_app_context
                        if has_app_context():
                            log_metric(current_app.logger, "stream_stop", pid=self._proc.pid)
                    except Exception:
                        pass
                    try:
                        os.killpg(self._proc.pid, signal.SIGTERM)
                    except Exception:
                        self._proc.terminate()
                    try:
                        self._proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(self._proc.pid, signal.SIGKILL)
                        except Exception:
                            self._proc.kill()

                self._proc = None
                self._started_at = None
                self._pidfile.unlink(missing_ok=True)

            # Note: UDP source stays running for motion/timelapse services
            # To completely stop: call stop_udp_source()
            return self.status()

    def _stop_udp_source(self) -> bool:
        """Stop the master UDP source stream (internal method)."""
        if not self._udp_proc:
            return True

        try:
            if self._udp_proc.poll() is None:
                self._udp_proc.terminate()
                try:
                    self._udp_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._udp_proc.kill()
            self._udp_proc = None
            logger.info("Stopped UDP source stream")
            return True
        except Exception as e:
            logger.error(f"Error stopping UDP source: {e}")
            self._udp_proc = None
            return False

    def restart_udp_source(self) -> bool:
        """Restart the UDP source stream with current settings.

        This is useful when day/night mode changes and stream parameters need to be updated.
        """
        logger.info("Restarting UDP source stream with updated settings")
        self._load_config()
        return self._start_udp_source(force_restart=True)


stream_service = StreamService()
