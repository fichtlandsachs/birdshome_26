"""Timelapse video generation service.

This service generates timelapse videos from captured snapshots.
"""

from __future__ import annotations

import logging
import os
import shlex
import socket
import subprocess
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urlparse
from flask import current_app

from ..extensions import db
from .. import constants as C
from ..models import Photo, Timelapse

logger = logging.getLogger(__name__)


def _is_udp_url(url: str) -> bool:
    try:
        return urlparse(url).scheme.lower() == "udp"
    except Exception:
        return False


def build_ffmpeg_cmd(stream_url: str, output_path: str, ffmpeg_bin: str = "ffmpeg") -> list[str]:
    is_udp = _is_udp_url(stream_url)
    default_probesize = "1000000" if is_udp else "32"
    default_analyzeduration = "1000000" if is_udp else "0"

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-xerror",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-probesize", os.getenv("FFMPEG_PROBESIZE", default_probesize),
        "-analyzeduration", os.getenv("FFMPEG_ANALYZEDURATION", default_analyzeduration),
    ]

    # Verhindert Hängenbleiben bei UDP ohne Daten: Socket-Read-Timeout (in Mikrosekunden).
    # Default: 2 Sekunden. Über ENV anpassbar.
    if is_udp:
        rw_timeout_us = int(os.getenv("FFMPEG_RW_TIMEOUT_US", "2000000"))
        cmd += ["-rw_timeout", str(rw_timeout_us)]

    # Harte interne Begrenzung: ffmpeg beendet sich nach N Sekunden Input-Zeit
    # (so wartet es nicht ewig auf einen decodierbaren Frame)
    cmd += ["-t", os.getenv("FFMPEG_SNAPSHOT_T", "2")]

    cmd += [
        "-i", stream_url,
        "-frames:v", "1",
        "-y",
        output_path,
    ]
    return cmd


class TimelapseService:
    """Service for generating timelapse videos from snapshots."""

    def __init__(self):
        self._config = {}

    def _load_config(self) -> None:
        """Load configuration from database settings."""
        from ..models import Setting

        settings = {}
        for setting in Setting.query.all():
            settings[setting.key] = setting.value

        self._config = {
            "PREFIX": settings.get("PREFIX") or current_app.config.get("PREFIX", "nest_"),
            "STREAM_UDP_URL": settings.get(C.STREAM_UDP_URL) or current_app.config.get(C.STREAM_UDP_URL),
            "TIMELAPSE_FPS": settings.get(C.TIMELAPSE_FPS) or current_app.config.get(C.TIMELAPSE_FPS, "30"),
            "TIMELAPSE_DAYS": settings.get(C.TIMELAPSE_DAYS) or current_app.config.get(C.TIMELAPSE_DAYS, "7"),
        }

    def capture_udp_snapshot(self) -> dict:
        """Capture a single screenshot from UDP stream into static/timelapse_screens."""
        try:
            # Load config from database
            self._load_config()

            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            screens_dir = media_root / "timelapse_screens"
            screens_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            prefix = self._config.get("PREFIX", "nest_")
            filename = f"{prefix}screen_{timestamp}.jpg"
            output_path = screens_dir / filename

            udp_url = self._config.get("STREAM_UDP_URL", "udp://127.0.0.1:5004?pkt_size=1316")

            if udp_url.startswith("udp://") and "reuse=" not in udp_url:
                joiner = "&" if "?" in udp_url else "?"
                udp_url = f"{udp_url}{joiner}reuse=1&overrun_nonfatal=1&fifo_size=5000000"
            ffmpeg_bin = current_app.config.get("FFMPEG_BIN", "ffmpeg")
            cmd = build_ffmpeg_cmd(udp_url, str(output_path.absolute()), ffmpeg_bin=ffmpeg_bin)

            ok, msg = ffprobe_stream_ok(udp_url, ffprobe_bin=current_app.config.get("FFPROBE_BIN", "ffprobe"), timeout_s=3.0)
            if not ok:
                logger.warning(f"ffprobe check failed for {udp_url}: {msg}")
                # We still try to run ffmpeg, as ffprobe might be too strict or fail on transient issues

            logger.info(f"Capturing timelapse screen: {shlex.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=float(os.getenv("SNAPSHOT_TIMEOUT_S", "6")))

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return {"ok": False, "error": f"ffmpeg failed: {result.stderr}"}

            if not output_path.exists():
                return {"ok": False, "error": "Screenshot not created"}

            return {"ok": True, "path": str(output_path)}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout"}
        except Exception as e:
            logger.exception("Error capturing timelapse screenshot")
            return {"ok": False, "error": str(e)}

    def generate_timelapse(self, days: int | None = None, from_date: date | None = None, to_date: date | None = None) -> dict:
        """Generate a timelapse video from screenshots in static/timelapse_screens.

        Args:
            days: Number of days to include (from today backwards). If None, uses config.
            from_date: Start date (inclusive). If None, calculated from days.
            to_date: End date (inclusive). If None, uses today.

        Returns:
            dict with status and path information
        """
        try:
            # Load config from database
            self._load_config()

            if days is None:
                days = int(self._config.get("TIMELAPSE_DAYS", "7"))

            if to_date is None:
                to_date = date.today()

            if from_date is None:
                from_date = to_date - timedelta(days=days - 1)

            fps = int(self._config.get("TIMELAPSE_FPS", "30"))

            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            screens_dir = media_root / "timelapse_screens"
            videos_dir = media_root / "timelapse_video"
            screens_dir.mkdir(parents=True, exist_ok=True)
            videos_dir.mkdir(parents=True, exist_ok=True)

            images = sorted(screens_dir.glob("*.jpg"))
            if not images:
                logger.info("No screenshots found for timelapse generation - skipping")
                return {"ok": True, "skipped": True, "message": "No screenshots available"}

            prefix = current_app.config.get("PREFIX", "nest_")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}timelapse_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}_{timestamp}.mp4"
            output_path = videos_dir / filename

            file_list_path = videos_dir / f"_filelist_{timestamp}.txt"
            with open(file_list_path, "w") as f:
                for img in images:
                    escaped = str(img).replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")
                    f.write(f"duration {1.0/fps}\n")
                if images:
                    last_img = images[-1]
                    escaped = str(last_img).replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")

            cmd = [
                current_app.config.get("FFMPEG_BIN", "ffmpeg"),
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", str(file_list_path),
                "-vf", f"fps={fps}",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-y",
                str(output_path),
            ]

            logger.info(f"Running ffmpeg: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            file_list_path.unlink(missing_ok=True)

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return {"ok": False, "error": f"ffmpeg failed: {result.stderr}"}

            if not output_path.exists():
                return {"ok": False, "error": "Timelapse file was not created"}

            # Save to DB (path relative to static)
            timelapse = Timelapse(
                path=f"timelapse_video/{filename}",
                from_date=from_date,
                to_date=to_date,
                fps=fps,
                uploaded=False
            )
            db.session.add(timelapse)
            db.session.commit()

            # Delete all screenshots after successful video creation
            for img in images:
                img.unlink(missing_ok=True)

            return {
                "ok": True,
                "path": str(output_path),
                "frame_count": len(images),
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat()
            }

        except subprocess.TimeoutExpired:
            file_list_path.unlink(missing_ok=True)
            return {"ok": False, "error": "Timeout"}
        except Exception as e:
            logger.exception("Error generating timelapse")
            if 'file_list_path' in locals():
                Path(file_list_path).unlink(missing_ok=True)
            return {"ok": False, "error": str(e)}

    def cleanup_old_snapshots(self, retention_days: int | None = None) -> dict:
        """Remove old timelapse screenshots from static/timelapse_screens."""
        try:
            if retention_days is None:
                retention_days = int(current_app.config.get("RETENTION_DAYS", 14))

            cutoff = datetime.utcnow() - timedelta(days=retention_days)
            media_root = Path(current_app.config.get("MEDIA_ROOT", "data"))
            screens_dir = media_root / "timelapse_screens"
            screens_dir.mkdir(parents=True, exist_ok=True)

            deleted_count = 0
            deleted_bytes = 0

            for img in screens_dir.glob("*.jpg"):
                mtime = datetime.utcfromtimestamp(img.stat().st_mtime)
                if mtime < cutoff:
                    size = img.stat().st_size
                    img.unlink(missing_ok=True)
                    deleted_count += 1
                    deleted_bytes += size

            return {"ok": True, "deleted_count": deleted_count, "deleted_bytes": deleted_bytes}
        except Exception as e:
            logger.exception("Error cleaning up timelapse screenshots")
            return {"ok": False, "error": str(e)}


def udp_packets_arrive(udp_url: str, timeout_s: float = 2.0) -> bool:
    """True, wenn innerhalb timeout_s mindestens 1 UDP-Paket empfangen wird."""
    u = urlparse(udp_url)
    if u.scheme.lower() != "udp":
        raise ValueError("Not a udp:// URL")

    host = u.hostname or "127.0.0.1"
    port = u.port
    if port is None:
        raise ValueError("UDP URL has no port")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout_s)
        # Standardmäßig nur an die im URL angegebene Schnittstelle binden.
        sock.bind((host, port))
        _data, _addr = sock.recvfrom(2048)
        return True
    except socket.timeout:
        return False
    finally:
        sock.close()


def ffprobe_stream_ok(stream_url: str, ffprobe_bin: str = "ffprobe", timeout_s: float = 3.0) -> tuple[bool, str]:
    """True, wenn ffprobe innerhalb timeout_s einen Videostream erkennt."""
    cmd = [
        ffprobe_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        # Increase probesize and analyzeduration to give ffprobe enough data to correctly identify the stream
        "-probesize", os.getenv("FFMPEG_PROBESIZE", "1000000"),
        "-analyzeduration", os.getenv("FFMPEG_ANALYZEDURATION", "1000000"),
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height",
        "-of", "default=nw=1",
        stream_url,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        ok = (p.returncode == 0) and ("codec_name" in (p.stdout or ""))
        msg = (p.stdout or "").strip() or (p.stderr or "").strip()
        return ok, msg
    except subprocess.TimeoutExpired:
        return False, "ffprobe timeout"
# Singleton instance
timelapse_service = TimelapseService()
