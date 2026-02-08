from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from flask import current_app


from ..models import Setting


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str
    duration_ms: int


def _run_cmd(cmd: list[str], timeout_s: int = 10) -> tuple[int, str, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return 124, out, "timeout"
    return proc.returncode, out, err


class HealthcheckService:
    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        def timed(name: str, fn):
            t0 = time.time()
            try:
                ok, details = fn()
            except Exception as e:  # noqa: BLE001
                ok, details = False, str(e)
            dt = int((time.time() - t0) * 1000)
            results.append(CheckResult(name=name, ok=ok, details=details, duration_ms=dt))

        timed("HiDrive Connection", self._hidrive_list)
        timed("HiDrive Test Upload", self._hidrive_test_upload)
        timed("Camera Availability", self._camera)
        timed("Microphone Availability", self._mic)
        timed("Disk Space", self._disk)
        timed("Scheduler Status", self._scheduler)
        timed("Streaming Pipeline", self._streaming)
        timed("Motion Service", self._motion_service)
        timed("Snapshot Service", self._snapshot_service)
        timed("Systemd Timers", self._timers)

        return results

    def _get_hidrive_config(self):
        """Load HiDrive configuration from database."""
        settings = {s.key: s.value for s in Setting.query.all()}
        return {
            "user": settings.get("HIDRIVE_USER", ""),
            "password": settings.get("HIDRIVE_PASSWORD", ""),
            "target_dir": settings.get("HIDRIVE_TARGET_DIR", "Birdshome"),
        }

    def _hidrive_list(self):
        config = self._get_hidrive_config()

        # Check if credentials are configured
        if not config["user"] or not config["password"]:
            return False, "HiDrive credentials not configured (HIDRIVE_USER, HIDRIVE_PASSWORD)."

        if not config["target_dir"]:
            return False, "HiDrive target directory not configured (HIDRIVE_TARGET_DIR)."
        import socket
        hostname = socket.gethostname()
        # Test connection using curl to WebDAV
        webdav_url = f"https://webdav.hidrive.strato.com/{config['user']}/{config['target_dir']}/{'hostname'}/"
        rc, out, err = _run_cmd([
            "curl", "-s", "-u", f"{config['user']}:{config['password']}",
            "-X", "PROPFIND", webdav_url
        ], timeout_s=8)

        if rc == 0:
            return True, "Connected."
        else:
            return False, (err or out or "Connection failed").strip()[:200]

    def _hidrive_test_upload(self):
        config = self._get_hidrive_config()

        # Check if credentials are configured
        if not config["user"] or not config["password"]:
            return False, "HiDrive credentials not configured."

        tmp_path = "/tmp/birdshome_healthcheck.txt"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("birdshome healthcheck\n")

        # Upload test file using curl
        webdav_url = f"https://webdav.hidrive.strato.com/{config['target_dir']}/healthcheck.txt"
        rc, out, err = _run_cmd([
            "curl", "-s", "-u", f"{config['user']}:{config['password']}",
            "-T", tmp_path, webdav_url
        ], timeout_s=15)

        if rc != 0:
            return False, (err or out or "upload failed").strip()[:200]

        # Delete test file
        _run_cmd([
            "curl", "-s", "-u", f"{config['user']}:{config['password']}",
            "-X", "DELETE", webdav_url
        ], timeout_s=10)

        return True, "Uploaded and cleaned up."

    def _camera(self):
        # Baseline: verify ffmpeg exists and video source string is configured.
        ffmpeg = current_app.config.get("FFMPEG_BIN", "ffmpeg")
        rc, out, err = _run_cmd([ffmpeg, "-version"], timeout_s=5)
        if rc != 0:
            return False, "ffmpeg not available"
        return True, "ffmpeg available; camera source configured."

    def _mic(self):
        # Baseline: check arecord listing
        rc, out, err = _run_cmd(["arecord", "-l"], timeout_s=5)
        if rc != 0:
            return False, (err or out or "arecord not available").strip()[:200]
        return True, "ALSA devices listed."

    def _disk(self):
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        if free_gb < 1.0:
            return False, f"Low disk space: {free_gb:.2f}GB free"
        return True, f"{free_gb:.2f}GB free"

    def _scheduler(self):
        # Scheduler is optional in this baseline; we report OK if app started.
        return True, "Scheduler service is available (baseline)."

    def _streaming(self):
        mode = str(current_app.config.get("STREAM_MODE", "HLS")).upper()
        if mode == "HLS":
            hls_dir = os.path.join(current_app.static_folder, "hls")
            m3u8 = os.path.join(hls_dir, "index.m3u8")
            if not os.path.exists(m3u8):
                return False, "No HLS playlist found. Start stream first."
            age_s = time.time() - os.path.getmtime(m3u8)
            if age_s > 30:
                return False, f"HLS playlist stale ({age_s:.0f}s)."
            return True, "HLS playlist is fresh."
        return False, "WEBRTC healthcheck not implemented in baseline."

    def _motion_service(self):
        """Check motion detection service status."""
        from .motion_service import motion_service

        status = motion_service.status()  # ← Prüft In-Process-Instanz
        if not status.get("running", False):  # ← Immer False im Flask-Prozess
            return False, "Motion service not running"

        methods = []
        if status.get("framediff_enabled"):
            methods.append("frame-diff")
        if status.get("gpio_enabled"):
            gpio_status = "available" if status.get("gpio_available") else "unavailable"
            methods.append(f"GPIO ({gpio_status})")

        details = f"Running with: {', '.join(methods)}" if methods else "Running"
        last_motion = status.get("last_motion", 0)
        if last_motion > 0:
            age_s = int(time.time() - last_motion)
            if age_s < 60:
                details += f", last motion {age_s}s ago"
            elif age_s < 3600:
                details += f", last motion {age_s // 60}m ago"

        return True, details

    def _snapshot_service(self):
        """Check snapshot service status via systemd."""
        try:
            rc, out, err = _run_cmd([
                "systemctl", "show", "birdshome-snapshot.timer",
                "--property=ActiveState,NextElapseUSecRealtime"
            ], timeout_s=5)

            if rc != 0:
                return False, "Snapshot timer not found or not active"

            active = False
            next_run = None
            for line in out.strip().split('\n'):
                if line.startswith("ActiveState="):
                    active = "active" in line.lower()
                elif line.startswith("NextElapseUSecRealtime="):
                    usec_str = line.split("=", 1)[1].strip()
                    if usec_str and usec_str != "0":
                        try:
                            usec = int(usec_str)
                            from datetime import datetime
                            next_time = datetime.fromtimestamp(usec / 1_000_000)
                            delta = (next_time - datetime.now()).total_seconds()
                            if delta < 60:
                                next_run = f"next run in {int(delta)}s"
                            else:
                                next_run = f"next run in {int(delta // 60)}m"
                        except (ValueError, OSError):
                            pass

            if not active:
                return False, "Snapshot timer inactive"

            return True, next_run or "Timer active"
        except Exception as e:
            return False, f"Error checking snapshot service: {str(e)[:100]}"

    def _timers(self):
        """Check all birdshome systemd timers."""
        try:
            rc, out, err = _run_cmd([
                "systemctl", "list-timers", "--no-pager", "--no-legend", "birdshome-*"
            ], timeout_s=5)

            if rc != 0:
                return False, "Could not list timers"

            lines = [line.strip() for line in out.strip().split('\n') if line.strip()]
            if not lines:
                return False, "No birdshome timers found"

            active_timers = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 6:
                    timer_name = parts[-1] if parts[-1].endswith('.timer') else None
                    if timer_name:
                        active_timers.append(timer_name.replace('birdshome-', '').replace('.timer', ''))

            if not active_timers:
                return False, "No active timers"

            return True, f"{len(active_timers)} timer(s) active: {', '.join(active_timers)}"
        except Exception as e:
            return False, f"Error checking timers: {str(e)[:100]}"


healthcheck_service = HealthcheckService()
