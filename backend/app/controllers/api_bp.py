from __future__ import annotations

import os
import secrets
import time
from functools import wraps

import psutil
from flask import Blueprint, jsonify, request, current_app, make_response
from flask_login import login_required, login_user, logout_user, current_user

from .. import constants as C
from ..extensions import db
from ..models import Setting, User, BioEvent, Photo, Video, Timelapse
from ..services.stream_service import stream_service
from ..services.healthcheck_service import healthcheck_service
from ..services.motion_service import motion_service
from ..services.upload_service import upload_service
from ..services.webrtc_service import webrtc_service
from ..services.day_night_service import day_night_service
from ..services.recording_service import recording_service

api = Blueprint("api", __name__, url_prefix="/api")
def _internal_auth() -> bool:
    # Allow only loopback + matching internal token.
    token = request.headers.get("X-Internal-Token", "")
    expected = str(current_app.config.get("INTERNAL_TOKEN", ""))
    remote = request.remote_addr or ""
    if remote not in ("127.0.0.1", "::1"):
        return False
    return bool(expected) and expected != "change-me" and token == expected


def internal_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _internal_auth():
            return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper



def _ensure_csrf_cookie(resp):
    token = request.cookies.get(C.CSRF_COOKIE_NAME)
    if not token:
        token = secrets.token_urlsafe(32)
        resp.set_cookie(
            C.CSRF_COOKIE_NAME,
            token,
            httponly=False,
            samesite="Lax",
            secure=request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https',
        )
    return resp


def csrf_protect(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cookie_token = request.cookies.get(C.CSRF_COOKIE_NAME, "")
        header_token = request.headers.get(C.CSRF_HEADER_NAME, "")
        if not cookie_token or not header_token or cookie_token != header_token:
            return jsonify({"error": "csrf_failed"}), 403
        return fn(*args, **kwargs)

    return wrapper


def _get_setting(key: str) -> str | None:
    row = Setting.query.filter_by(key=key).first()
    return row.value if row else None


def _set_setting(key: str, value: str) -> None:
    row = Setting.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _restart_stream_service() -> None:
    """Restart stream service in background (called from thread)."""
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Restarting stream service due to settings change...")

        stream_service.stop()
        time.sleep(2)  # Wait for clean shutdown
        stream_service.start()

        logger.info("Stream service restarted successfully")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to restart stream service: {e}")


def _sync_settings_to_env(settings: dict) -> None:
    """Sync important settings to .env file for persistence across restarts."""
    import re
    from pathlib import Path
    import logging

    # Settings that should be persisted to .env
    env_keys = {
        'STREAM_RES', 'STREAM_FPS', 'STREAM_BITRATE', 'VIDEO_SOURCE',
        'AUDIO_SOURCE', 'VIDEO_ROTATION', 'STREAM_UDP_URL',
        'TIMELAPSE_INTERVAL_S', 'TIMELAPSE_FPS',
        'RECORD_RES', 'RECORD_FPS',
        'MOTION_THRESHOLD', 'MOTION_DURATION_S', 'MOTION_COOLDOWN_S',
        'PREFIX', 'ADMIN_USERNAME'
    }

    logger = logging.getLogger(__name__)

    # Get .env file path
    try:
        from flask import current_app as app
        backend_dir = Path(app.root_path).parent
    except RuntimeError:
        # No app context in background thread, use relative path
        backend_dir = Path(__file__).parent.parent

    env_file = backend_dir / '.env'

    if not env_file.exists():
        logger.warning(f".env file not found at {env_file}")
        return

    try:
        # Read existing .env content
        lines = env_file.read_text(encoding='utf-8').splitlines()

        # Update or add settings
        updated_keys = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                new_lines.append(line)
                continue

            key = stripped.split('=', 1)[0].strip()

            # Update if key is in settings and should be synced
            if key in env_keys and key in settings:
                value = settings[key]
                # Check if value needs quoting
                if re.fullmatch(r"[A-Za-z0-9_./:@+\-]+", value or ""):
                    new_lines.append(f"{key}={value}")
                else:
                    # Escape quotes and backslashes
                    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                    new_lines.append(f'{key}="{escaped}"')
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Add new keys that weren't in the file
        for key in env_keys:
            if key in settings and key not in updated_keys:
                value = settings[key]
                if re.fullmatch(r"[A-Za-z0-9_./:@+\-]+", value or ""):
                    new_lines.append(f"{key}={value}")
                else:
                    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                    new_lines.append(f'{key}="{escaped}"')

        # Write back to .env
        env_file.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        logger.info(f"Synced {len(settings)} settings to .env file")

    except Exception as e:
        logger.error(f"Failed to sync settings to .env: {e}")

@api.get("/dashboard/summary")
def dashboard_summary():
    """Lightweight dashboard info (bird-focused)."""
    try:
        stream = stream_service.status()
        stream_info = {
            "running": stream.running,
            "mode": stream.mode,
        }
    except Exception:
        stream_info = {"running": False, "mode": "HLS"}

    # Last 10 photos
    photos = Photo.query.order_by(Photo.created_at.desc()).limit(10).all()
    photo_items = [
        {
            "id": p.id,
            "url": "/media/" + p.path,
            "timestamp": p.created_at.isoformat(),
        }
        for p in photos
    ]

    # Video count
    video_count = Video.query.count()

    return jsonify({
        "stream": stream_info,
        "recent_photos": photo_items,
        "video_count": video_count,
    })

@api.get("/csrf")
def csrf():
    resp = make_response(jsonify({"ok": True}))
    return _ensure_csrf_cookie(resp)


@api.get("/auth/me")
def me():
    resp = jsonify({"authenticated": current_user.is_authenticated, "username": getattr(current_user, "username", None)})
    return _ensure_csrf_cookie(resp)


@api.post("/auth/login")
@csrf_protect
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "invalid_credentials"}), 401

    from ..security import verify_password

    ok, new_hash = verify_password(password, user.password_hash)
    if not ok:
        return jsonify({"error": "invalid_credentials"}), 401
    if new_hash:
        # Upgrade legacy password hashes transparently.
        user.password_hash = new_hash
        db.session.commit()
    if ok:
        login_user(user)
        resp = jsonify({"ok": True, "username": user.username})
    return _ensure_csrf_cookie(resp)


@api.post("/auth/logout")
@login_required
@csrf_protect
def logout():
    logout_user()
    resp = jsonify({"ok": True})
    return _ensure_csrf_cookie(resp)


@api.get("/status")
# @login_required
def status():
    """Get system status. Optimized to avoid blocking calls."""
    # Use interval=0 for non-blocking CPU reading (uses cached value)
    cpu = psutil.cpu_percent(interval=0)

    # Fast memory and disk checks
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # CPU temperature - skip if not available or slow
    cpu_temp = None
    try:
        # Quick check with timeout - only if supported
        temps = psutil.sensors_temperatures()
        if temps:
            # Get first available temperature quickly
            for sensor_name, readings in temps.items():
                if readings:
                    cpu_temp = round(readings[0].current, 1)
                    break
    except (AttributeError, OSError, IndexError):
        pass

    try:
        stream = stream_service.status()
        payload = {
            "cpu_percent": cpu,
            "cpu_temp": cpu_temp,
            "mem_percent": vm.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "stream": {
                "running": stream.running,
                "mode": stream.mode,
                "pid": int(stream.pid or 0),
                "started_at": (stream.started_at.isoformat() if getattr(stream, "started_at", None) else ""),
            },
        }
        return jsonify(payload)
    except Exception:
        # Fallback-Objekt, damit das Frontend nicht abstürzt
        return jsonify({
            "cpu_percent": cpu,
            "cpu_temp": cpu_temp,
            "mem_percent": vm.percent,
            "disk_free_gb": 0,
            "stream": {
                "running": False,
                "mode": "HLS"
            }
        })

@api.get("/settings")
@login_required
def settings_get():
    keys = list(current_app.config.get("DEFAULT_SETTINGS", {}).keys())
    out = {}
    for k in keys:
        out[k] = _get_setting(k) or str(current_app.config["DEFAULT_SETTINGS"].get(k))
    return jsonify(out)


@api.post("/settings")
@login_required
@csrf_protect
def settings_set():
    """Save settings to database and .env file, restart services if needed."""
    data = request.get_json(silent=True) or {}

    # Track which settings changed to determine if services need restart
    stream_settings_changed = False
    timelapse_settings_changed = False

    # Settings that affect stream service
    stream_keys = {
        'STREAM_RES', 'STREAM_FPS', 'STREAM_BITRATE', 'VIDEO_SOURCE',
        'AUDIO_SOURCE', 'VIDEO_ROTATION', 'STREAM_UDP_URL'
    }

    # Settings that affect timelapse service
    timelapse_keys = {
        'TIMELAPSE_INTERVAL_S', 'TIMELAPSE_FPS', 'VIDEO_SOURCE', 'VIDEO_ROTATION'
    }

    # Update settings in database and check which services are affected
    for k, v in data.items():
        key = str(k)
        value = v

        _set_setting(key, value)
        current_app.config[key] = value

        if key in stream_keys:
            stream_settings_changed = True
        if key in timelapse_keys:
            timelapse_settings_changed = True

    # Write important settings to .env file for persistence across restarts (async in background)
    from threading import Thread
    Thread(target=_sync_settings_to_env, args=(data.copy(),), daemon=True).start()

    # Prepare restart info
    restart_results = {}

    if stream_settings_changed:
        # Check if stream is running
        status = stream_service.status()
        if status.running:
            restart_results['stream'] = 'will_restart'
            # Restart stream service in background thread to avoid blocking HTTP response
            Thread(target=_restart_stream_service, daemon=True).start()
        else:
            restart_results['stream'] = 'not_running'

    if timelapse_settings_changed:
        restart_results['timelapse'] = 'settings_updated'

    return jsonify({
        "ok": True,
        "services_restarted": restart_results
    })


@api.post("/control/stream/start")
#@login_required
@csrf_protect
def stream_start():
    try:
        st = stream_service.start()
        return jsonify({"ok": True, "status": st.__dict__})
    except NotImplementedError as e:
        return jsonify({"ok": False, "error": str(e)}), 501


@api.post("/control/stream/stop")
#@login_required
@csrf_protect
def stream_stop():
    st = stream_service.stop()
    return jsonify({"ok": True, "status": st.__dict__})


@api.post("/control/motion/start")
@login_required
@csrf_protect
def motion_start():
    """Start motion detection service."""
    try:
        result = motion_service.start()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@api.post("/control/motion/stop")
@login_required
@csrf_protect
def motion_stop():
    """Stop motion detection service."""
    try:
        result = motion_service.stop()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@api.get("/control/motion/status")
@login_required
def motion_status():
    """Get motion detection status."""
    try:
        status = motion_service.status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"running": False, "error": str(e)}), 500


# ========== Day/Night Mode API ==========

@api.get("/day-night/status")
def day_night_status():
    """Get current day/night mode status."""
    try:
        status = day_night_service.get_status()
        return jsonify({
            "mode": status.mode.lower(),
            "brightness": status.brightness,
            "last_check": status.last_check,
            "threshold": status.threshold
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.post("/day-night/mode")
@login_required
def day_night_set_mode():
    """Manually set day/night mode."""
    try:
        data = request.get_json()
        mode = data.get("mode", "").upper()

        if mode not in ("DAY", "NIGHT"):
            return jsonify({"error": "Invalid mode. Must be 'day' or 'night'"}), 400

        day_night_service.set_mode(mode)

        # Restart stream to apply new settings
        try:
            stream_service.restart_udp_source()
        except Exception as e:
            current_app.logger.warning(f"Could not restart UDP source: {e}")

        return jsonify({
            "ok": True,
            "mode": mode.lower(),
            "message": f"Switched to {mode} mode"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.post("/internal/stream/start")
@internal_required
def internal_stream_start():
    st = stream_service.start()
    return jsonify({"ok": True, "status": st.__dict__})

@api.post("/internal/stream/stop")
@internal_required
def internal_stream_stop():
    st = stream_service.stop()
    return jsonify({"ok": True, "status": st.__dict__})


@api.post("/webrtc/offer")
@login_required
@csrf_protect
def webrtc_offer():
    """Handle WebRTC offer from client."""
    import asyncio
    import uuid

    data = request.get_json()
    if not data or 'sdp' not in data:
        return jsonify({"error": "Missing SDP"}), 400

    session_id = str(uuid.uuid4())

    # Run async operations in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Create peer connection
        result = loop.run_until_complete(
            webrtc_service.create_peer_connection(session_id)
        )

        if "error" in result:
            return jsonify(result), 500

        # Handle offer and get answer
        answer = loop.run_until_complete(
            webrtc_service.handle_offer(session_id, data['sdp'], data.get('type', 'offer'))
        )

        if "error" in answer:
            return jsonify(answer), 500

        return jsonify({
            "session_id": session_id,
            "sdp": answer['sdp'],
            "type": answer['type']
        })
    finally:
        loop.close()


@api.post("/webrtc/ice")
@login_required
@csrf_protect
def webrtc_ice():
    """Handle ICE candidate from client."""
    import asyncio

    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({"error": "Missing session_id"}), 400

    session_id = data['session_id']
    candidate = data.get('candidate')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            webrtc_service.handle_ice_candidate(session_id, candidate)
        )

        if "error" in result:
            return jsonify(result), 500

        return jsonify(result)
    finally:
        loop.close()


@api.post("/webrtc/close")
@login_required
@csrf_protect
def webrtc_close():
    """Close WebRTC peer connection."""
    import asyncio

    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({"error": "Missing session_id"}), 400

    session_id = data['session_id']

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            webrtc_service.close_peer(session_id)
        )

        return jsonify(result)
    finally:
        loop.close()


@api.get("/healthz")
#@login_required
def healthz():
    results = healthcheck_service.run()
    return jsonify({
        "results": [
            {"name": r.name, "status": "ok" if r.ok else "fail", "details": r.details, "duration": r.duration_ms}
            for r in results
        ]
    })


@api.get("/admin/health/check/<check_name>")
@login_required
def admin_health_check(check_name: str):
    """Run a single health check and return the result."""
    import time

    # Map check names to healthcheck_service methods
    check_map = {
        "hidrive_connection": healthcheck_service._hidrive_list,
        "hidrive_upload": healthcheck_service._hidrive_test_upload,
        "camera": healthcheck_service._camera,
        "microphone": healthcheck_service._mic,
        "disk": healthcheck_service._disk,
        "scheduler": healthcheck_service._scheduler,
        "streaming": healthcheck_service._streaming,
        "motion_service": healthcheck_service._motion_service,
        "snapshot_service": healthcheck_service._snapshot_service,
        "timers": healthcheck_service._timers,
    }

    if check_name not in check_map:
        return jsonify({"error": "Unknown check"}), 404

    t0 = time.time()
    try:
        ok, details = check_map[check_name]()
    except Exception as e:
        ok, details = False, str(e)
    duration_ms = int((time.time() - t0) * 1000)

    return jsonify({
        "name": check_name,
        "status": "ok" if ok else "fail",
        "details": details,
        "duration": duration_ms
    })


@api.get("/admin/health")
@login_required
def admin_health():
    """Extended health information for admin page including timers and services."""
    import subprocess
    from datetime import datetime, timedelta

    # Get basic health checks
    results = healthcheck_service.run()
    health_checks = [
        {"name": r.name, "status": "ok" if r.ok else "fail", "details": r.details, "duration": r.duration_ms}
        for r in results
    ]

    # Get system info (like dashboard)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.1)
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for sensor_name, readings in temps.items():
                if readings:
                    cpu_temp = round(sum(r.current for r in readings) / len(readings), 1)
                    break
    except (AttributeError, OSError):
        pass

    # Get stream status
    try:
        stream = stream_service.status()
        stream_info = {
            "running": stream.running,
            "mode": stream.mode,
            "pid": int(stream.pid or 0),
            "started_at": (stream.started_at.isoformat() if getattr(stream, "started_at", None) else ""),
        }
    except Exception:
        stream_info = {"running": False, "mode": "HLS", "pid": 0, "started_at": ""}

    # Check systemd timers
    timers_info = []
    try:
        # Get timer status
        timer_result = subprocess.run(
            ["systemctl", "list-timers", "--no-pager", "--no-legend", "birdshome-*"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if timer_result.returncode == 0:
            for line in timer_result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 6:
                    timer_name = parts[-1] if parts[-1].endswith('.timer') else None
                    if timer_name:
                        next_run = ' '.join(parts[0:2])  # e.g., "Mon 2025-01-20"
                        timers_info.append({
                            "name": timer_name,
                            "next": next_run,
                            "active": "active" in line.lower()
                        })
    except Exception as e:
        timers_info = [{"error": str(e)}]

    # Check if snapshot service is active (last run)
    snapshot_status = {"active": False, "last_run": None, "last_status": "unknown"}
    try:
        service_result = subprocess.run(
            ["systemctl", "show", "birdshome-snapshot.service", "--property=ActiveState,ActiveEnterTimestamp,ExecMainStatus"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if service_result.returncode == 0:
            for line in service_result.stdout.strip().split('\n'):
                if line.startswith("ActiveState="):
                    snapshot_status["active"] = "active" in line.lower()
                elif line.startswith("ActiveEnterTimestamp="):
                    timestamp_str = line.split("=", 1)[1].strip()
                    if timestamp_str and timestamp_str != "n/a":
                        snapshot_status["last_run"] = timestamp_str
    except Exception:
        pass

    # Calculate next timelapse generation
    next_timelapse = None
    try:
        # Find next run time for timelapse timer
        timer_result = subprocess.run(
            ["systemctl", "show", "birdshome-timelapse.timer", "--property=NextElapseUSecRealtime"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if timer_result.returncode == 0:
            for line in timer_result.stdout.strip().split('\n'):
                if line.startswith("NextElapseUSecRealtime="):
                    # Parse microseconds since epoch
                    usec_str = line.split("=", 1)[1].strip()
                    if usec_str and usec_str != "0":
                        usec = int(usec_str)
                        next_time = datetime.fromtimestamp(usec / 1_000_000)
                        now = datetime.now()
                        delta = next_time - now
                        hours = int(delta.total_seconds() // 3600)
                        minutes = int((delta.total_seconds() % 3600) // 60)
                        next_timelapse = {
                            "time": next_time.isoformat(),
                            "in_hours": hours,
                            "in_minutes": minutes,
                            "human": f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                        }
    except Exception:
        pass

    return jsonify({
        "system": {
            "cpu_percent": cpu,
            "cpu_temp": cpu_temp,
            "mem_percent": vm.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
        },
        "stream": stream_info,
        "health_checks": health_checks,
        "timers": timers_info,
        "snapshot": snapshot_status,
        "next_timelapse": next_timelapse
    })


@api.get("/bio/events")
#@login_required
def bio_events():
    rows = BioEvent.query.order_by(BioEvent.event_date.desc()).limit(50).all()
    return jsonify([
        {"id": r.id, "kind": r.kind, "date": r.event_date.isoformat(), "notes": r.notes or ""}
        for r in rows
    ])

@api.get("/admin/logs")
@login_required
def admin_logs():
    """Get service logs with filtering.

    Query params:
    - service: birdshome|snapshot|timelapse|upload|stream|motion (default: all)
    - level: ERROR|WARNING|INFO|DEBUG (default: all)
    - lines: number of lines to return (default: 500, max: 5000)
    - search: search term to filter log lines
    - source: file|journald (default: file) - where to read logs from
    """
    import subprocess
    from pathlib import Path
    import re

    service = request.args.get("service", "all")
    level = request.args.get("level", "all")
    lines = min(int(request.args.get("lines", "500")), 5000)
    search_term = request.args.get("search", "")
    source = request.args.get("source", "file")

    # Map service names to log files and systemd units
    service_map = {
        "birdshome": {"file": "birdshome.log", "unit": "birdshome.service"},
        "snapshot": {"file": "snapshot.log", "unit": "birdshome-snapshot.service"},
        "timelapse": {"file": "timelapse.log", "unit": "birdshome-timelapse.service"},
        "upload": {"file": "upload.log", "unit": "birdshome-upload.service"},
        "motion": {"file": "motion.log", "unit": "birdshome-motion.service"},
    }

    logs = []

    if source == "file":
        # Read from log files in /var/log/birdshome
        log_dir = Path(current_app.config.get("LOG_DIR", "/var/log/birdshome"))

        if service == "all":
            log_files = [(name, info["file"]) for name, info in service_map.items()]
        elif service in service_map:
            log_files = [(service, service_map[service]["file"])]
        else:
            return jsonify({"error": f"Unknown service: {service}"}), 400

        # Pattern to parse log lines: "2025-01-31 12:34:56 INFO     [logger] message"
        log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)\s+\[([^\]]+)\] (.*)$')

        for service_name, log_file in log_files:
            log_path = log_dir / log_file
            if not log_path.exists():
                continue

            try:
                # Read last N lines from log file
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    # Read all lines and take last N
                    all_lines = f.readlines()
                    recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue

                    match = log_pattern.match(line)
                    if match:
                        timestamp_str, log_level, logger_name, message = match.groups()

                        # Apply level filter
                        if level != "all" and log_level.upper() != level.upper():
                            continue

                        # Apply search filter
                        if search_term and search_term.lower() not in message.lower():
                            continue

                        logs.append({
                            "timestamp": timestamp_str,
                            "service": service_name,
                            "level": log_level.upper(),
                            "message": message,
                        })

            except (OSError, PermissionError) as e:
                current_app.logger.error(f"Could not read log file {log_path}: {e}")
                continue

        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

    else:
        # Read from journald (legacy fallback)
        if service == "all":
            units = [info["unit"] for info in service_map.values()]
        elif service in service_map:
            units = [service_map[service]["unit"]]
        else:
            return jsonify({"error": f"Unknown service: {service}"}), 400

        for unit in units:
            try:
                # Build journalctl command
                cmd = ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "--output=json"]

                # Add priority filter if specified
                if level != "all":
                    priority_map = {
                        "ERROR": "3",
                        "WARNING": "4",
                        "INFO": "6",
                        "DEBUG": "7"
                    }
                    if level in priority_map:
                        cmd.extend(["-p", priority_map[level]])

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    # Parse JSON logs
                    import json
                    for line in result.stdout.strip().split('\n'):
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            message = entry.get("MESSAGE", "")

                            # Apply search filter
                            if search_term and search_term.lower() not in message.lower():
                                continue

                            # Extract service name from unit
                            service_name = unit.replace("birdshome-", "").replace(".service", "")
                            if service_name == "birdshome":
                                service_name = "main"

                            priority_names = {
                                "0": "EMERG",
                                "1": "ALERT",
                                "2": "CRIT",
                                "3": "ERROR",
                                "4": "WARNING",
                                "5": "NOTICE",
                                "6": "INFO",
                                "7": "DEBUG"
                            }

                            logs.append({
                                "timestamp": entry.get("__REALTIME_TIMESTAMP", "0"),
                                "service": service_name,
                                "level": priority_names.get(entry.get("PRIORITY", "6"), "INFO"),
                                "message": message,
                            })
                        except json.JSONDecodeError:
                            continue

            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
                continue

        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

    # Limit to requested number of lines
    logs = logs[:lines]

    return jsonify({
        "logs": logs,
        "total": len(logs),
        "service": service,
        "level_filter": level,
        "search": search_term,
        "source": source
    })


@api.get("/media/gallery")
#@login_required
def media_gallery():
    """Unified gallery list.

    Returns items compatible with the React GalleryPage.
    """
    filter_mode = request.args.get("filter", "all")  # all|birds|nobirds

    items: list[dict] = []

    for v in Video.query.order_by(Video.created_at.desc()).limit(100).all():
        if filter_mode == "birds" and not v.has_birds:
            continue
        if filter_mode == "nobirds" and v.has_birds:
            continue
        items.append({
            "id": f"video-{v.id}",
            "type": "video",
            "url": "/media/" + v.path,
            "thumbnail": "/media/" + v.path,  # placeholder; generate thumbnails if needed
            "timestamp": v.created_at.isoformat(),
            "hasBird": bool(v.has_birds),
        })

    for p in Photo.query.order_by(Photo.created_at.desc()).limit(100).all():
        items.append({
            "id": f"photo-{p.id}",
            "type": "photo",
            "url": "/media/" + p.path,
            "thumbnail": "/media/" + p.path,
            "timestamp": p.created_at.isoformat(),
            "hasBird": True,
        })

    for t in Timelapse.query.order_by(Timelapse.created_at.desc()).limit(50).all():
        url = "/media/" + t.path
        if t.path.startswith("timelapse_video/"):
            url = "/timelapse_video/" + t.path.split("/", 1)[1]

        items.append({
            "id": f"timelapse-{t.id}",
            "type": "timelapse",
            "url": url,
            "thumbnail": url,
            "timestamp": t.created_at.isoformat(),
            "hasBird": True,
        })

    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(items[:200])


@api.delete("/media/delete")
@csrf_protect
def media_delete():
    """Delete a media item (photo, video, or timelapse)."""
    data = request.get_json(silent=True) or {}
    item_id = str(data.get("id", ""))
    item_type = str(data.get("type", ""))

    if not item_id or not item_type:
        return jsonify({"error": "missing_parameters"}), 400

    # Parse ID format: "type-number"
    try:
        prefix, numeric_id = item_id.split("-", 1)
        numeric_id = int(numeric_id)
    except (ValueError, AttributeError):
        return jsonify({"error": "invalid_id_format"}), 400

    # Find and delete the item
    item = None
    file_path = None

    # Get media root directory
    from pathlib import Path
    media_root = Path(current_app.config.get("MEDIA_ROOT", "data")).resolve()

    if item_type == "photo" and prefix == "photo":
        item = Photo.query.get(numeric_id)
        if item:
            file_path = media_root / item.path
    elif item_type == "video" and prefix == "video":
        item = Video.query.get(numeric_id)
        if item:
            file_path = media_root / item.path
    elif item_type == "timelapse" and prefix == "timelapse":
        item = Timelapse.query.get(numeric_id)
        if item:
            file_path = media_root / item.path
    else:
        return jsonify({"error": "unsupported_type"}), 400

    if not item:
        return jsonify({"error": "not_found"}), 404

    # Delete physical file if exists
    if file_path and file_path.exists():
        try:
            file_path.unlink()
            current_app.logger.info(f"Deleted file: {file_path}")
        except OSError as e:
            current_app.logger.error(f"Failed to delete file {file_path}: {e}")
            return jsonify({"error": f"Failed to delete file: {str(e)}"}), 500

    # Delete database entry
    db.session.delete(item)
    db.session.commit()

    return jsonify({"ok": True})


@api.post("/jobs/run/<job>")
@login_required
@csrf_protect
def run_job(job: str):
    """Minimal synchronous job runner for demo/dev.

    In production you should run jobs via APScheduler or systemd timers.
    """
    job = job.lower()
    if job not in {"photo", "timelapse", "upload", "retention", "detect"}:
        return jsonify({"error": "unknown_job"}), 400

    # Baseline: no-op jobs return OK.
    return jsonify({"ok": True, "job": job, "status": "noop"})


@api.post("/control/upload/start")
@login_required
@csrf_protect
def upload_start():
    """Start manual upload to HiDrive."""
    try:
        result = upload_service.upload_all()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@api.post("/control/upload/test")
@login_required
@csrf_protect
def upload_test():
    """Test HiDrive connection."""
    try:
        result = upload_service.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@api.get("/control/daynight/status")
def daynight_status():
    """Get current day/night mode status."""
    try:
        status = day_night_service.get_status()
        # Map backend mode to frontend mode
        mode = status.mode.lower()  # "DAY" -> "day", "NIGHT" -> "night"
        auto_enabled = day_night_service._running

        return jsonify({
            "mode": mode,
            "auto_enabled": auto_enabled,
            "brightness": status.brightness,
            "last_check": status.last_check,
            "threshold": status.threshold
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/control/daynight/switch")
@csrf_protect
def daynight_switch():
    """Manually switch between day/night modes."""
    try:
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "").lower()

        # Map frontend mode names to backend mode names
        if mode == "day":
            backend_mode = "DAY"
        elif mode == "night":
            backend_mode = "NIGHT"
        elif mode == "auto":
            # Start automatic monitoring
            day_night_service.start_monitoring()
            return jsonify({"ok": True, "mode": "auto"})
        else:
            return jsonify({"ok": False, "error": "Invalid mode. Must be 'day', 'night', or 'auto'"}), 400

        # Stop automatic monitoring when manually setting mode
        day_night_service.stop_monitoring()

        # Set the mode
        day_night_service.set_mode(backend_mode)

        # Restart UDP source to apply new day/night mode settings (asynchronously to avoid blocking)
        from threading import Thread
        app = current_app._get_current_object()

        def _restart_stream():
            with app.app_context():
                # Restart UDP source with new camera settings (IR filter, etc.)
                stream_service.restart_udp_source()
                # If HLS stream is running, restart it too
                if stream_service.is_running():
                    stream_service.stop()
                    time.sleep(1)
                    stream_service.start()

        Thread(target=_restart_stream, daemon=True).start()

        return jsonify({"ok": True, "mode": mode})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@api.get("/control/daynight/mode")
def daynight_mode():
    """Get current day/night mode status."""
    try:
        status = day_night_service.get_status()
        if status.mode == "DAY":
            return jsonify({"mode": "auto", "brightness": status.brightness})
        return jsonify({
            "mode": status.mode,
            "brightness": status.brightness,
            "last_check": status.last_check,
            "threshold": status.threshold
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/control/daynight/start")
@csrf_protect
def daynight_start():
    """Start automatic day/night mode monitoring."""
    try:
        data = request.get_json(silent=True) or {}
        threshold = float(data.get("threshold", 30.0))
        interval = float(data.get("interval", 60.0))

        day_night_service.start_monitoring(threshold=threshold, interval=interval)
        return jsonify({"ok": True, "threshold": threshold, "interval": interval})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@api.post("/control/daynight/stop")
@csrf_protect
def daynight_stop():
    """Stop automatic day/night mode monitoring."""
    try:
        day_night_service.stop_monitoring()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.exception("Failed to stop day/night monitoring")
        return jsonify({"ok": False, "error": "Failed to stop day/night monitoring"}), 500


@api.post("/control/daynight/check")
@csrf_protect
def daynight_check():
    """Manually trigger brightness check and mode update."""
    try:
        mode_changed = day_night_service.check_and_update_mode()
        status = day_night_service.get_status()
        return jsonify({
            "ok": True,
            "mode_changed": mode_changed,
            "mode": status.mode,
            "brightness": status.brightness
        })
    except Exception as e:
        current_app.logger.exception("Failed to check/update day/night mode")
        return jsonify({"ok": False, "error": "Failed to check/update day/night mode"}), 500

@api.get("/control/recording/status")
def recording_status():
    """Get current recording status."""
    try:
        status = recording_service.status()
        return jsonify({
            "recording": status.recording,
            "started_at": status.started_at,
            "duration": status.duration,
            "output_path": status.output_path,
            "pid": status.pid
        })
    except Exception as e:
        current_app.logger.exception("Failed to get recording status")
        return jsonify({"error": "Failed to get recording status"}), 500


@api.post("/control/recording/start")
@login_required
@csrf_protect
def recording_start():
    """Start manual recording."""
    try:
        result = recording_service.start()
        return jsonify(result)
    except Exception as e:
        current_app.logger.exception("Failed to start recording")
        return jsonify({"ok": False, "error": "Failed to start recording"}), 500


@api.post("/control/recording/stop")
@login_required
@csrf_protect
def recording_stop():
    """Stop current recording."""
    try:
        result = recording_service.stop()
        return jsonify(result)
    except Exception as e:
        current_app.logger.exception("Failed to stop recording")
        return jsonify({"ok": False, "error": "Failed to stop recording"}), 500
