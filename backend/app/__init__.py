from __future__ import annotations

import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import db, migrate, login_manager
from .models import User, Setting, BioEvent
from .services.logging_service import configure_logging
from .services.scheduler import init_scheduler

def _ensure_default_settings_app(app: Flask) -> None:
    from os import getenv
    env_settings = {
        'STREAM_FPS': getenv('STREAM_FPS'),
        'STREAM_RES': getenv('STREAM_RES'),
        'VIDEO_SOURCE': getenv('VIDEO_SOURCE'),
        'AUDIO_SOURCE': getenv('AUDIO_SOURCE'),
    }
    for k, v in app.config.get("DEFAULT_SETTINGS", {}).items():
        app.config[k] = env_settings.get(k)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static")
    app.config.from_object(Config)
    _ensure_default_settings_app(app)
    # Trust X-Forwarded-* headers from the local reverse proxy (nginx).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Convenience: expose default settings and allow runtime overrides.
    app.config.update(Config.DEFAULT_SETTINGS)
    app.config["DEFAULT_SETTINGS"] = Config.DEFAULT_SETTINGS

    # Set MEDIA_ROOT to an absolute path (defaults to backend/data in development, can be overridden)
    media_root = os.getenv("MEDIA_ROOT", "data")
    if not os.path.isabs(media_root):
        # Make relative paths absolute (relative to backend directory)
        media_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", media_root))
    app.config["MEDIA_ROOT"] = media_root

    # Logging
    configure_logging(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from .controllers.main_bp import main
    from .controllers.api_bp import api

    app.register_blueprint(main)
    app.register_blueprint(api)

    with app.app_context():
        # Create tables if migrations haven't been run yet (dev convenience).
        db.create_all()
        _bootstrap_admin(app)
        _ensure_default_settings(app)
        _seed_bio_events()

    # Scheduler (optional; recommended to run in birdshome-jobs.service)
    try:
        enabled = str(app.config.get("SCHEDULER_ENABLED", "1")).lower() in ("1","true","yes","on")
    except Exception:
        enabled = True
    if enabled:
        init_scheduler(app)
    else:
        app.logger.info("Scheduler disabled (SCHEDULER_ENABLED=0)")

    # Start a background CPU monitoring thread for a fast status endpoint
    _start_cpu_monitor()

    # Autostart stream if enabled
    try:
        autostart = str(app.config.get("STREAM_AUTOSTART", "1")).lower() in ("1","true","yes","on")
    except Exception:
        autostart = False
    if autostart:
        _autostart_stream(app)

    return app


@login_manager.user_loader

def load_user(user_id: str):
    try:
        uid = int(user_id)
    except ValueError:
        return None
    return User.query.get(uid)


def _bootstrap_admin(app: Flask) -> None:
    """Ensure an admin user exists (username from config, password managed via an installation script)."""
    from .security import hash_password

    username = app.config.get("ADMIN_USERNAME")

    if not username:
        return

    # Check if the admin user exists, create if missing (password will be set by an installation script)
    user = User.query.filter_by(username=username).first()
    if user:
        # Ensure the user is admin
        if not user.is_admin:
            user.is_admin = True
            db.session.commit()
        return

    existing_admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if existing_admin:
        # Rename existing admin to new username
        existing_admin.username = username
        db.session.commit()
        return

    # Create new admin user with temporary password (will be overwritten by an installation script)
    user = User(username=username, password_hash=hash_password("change-me-now"), is_admin=True)
    db.session.add(user)
    db.session.commit()


def _ensure_default_settings(app: Flask) -> None:
    for k, v in app.config.get("DEFAULT_SETTINGS", {}).items():
        row = Setting.query.filter_by(key=k).first()
        if not row:
            db.session.add(Setting(key=k, value=str(v)))
        # Always keep effective config updated.
        app.config[k] = row.value if row else str(v)
    db.session.commit()


def _seed_bio_events() -> None:
    # Only seed if empty.
    if BioEvent.query.count() > 0:
        return
    from datetime import date

    demo = [
        BioEvent(kind="arrival", event_date=date(2024, 3, 5), notes="Pair of blue tits arrived."),
        BioEvent(kind="egg", event_date=date(2024, 3, 15), notes="First egg laid."),
        BioEvent(kind="hatch", event_date=date(2024, 3, 29), notes="First chick hatched."),
    ]
    db.session.add_all(demo)
    db.session.commit()


def _start_cpu_monitor() -> None:
    """Start background thread to keep CPU percentage cache updated."""
    import threading
    import time
    import psutil

    def _monitor_cpu():
        """Background thread that updates CPU percentage every 2 seconds."""
        while True:
            try:
                # This call updates the internal cache that cpu_percent(interval=0) uses
                psutil.cpu_percent(interval=1)
                time.sleep(1)
            except Exception:
                time.sleep(5)

    thread = threading.Thread(target=_monitor_cpu, daemon=True, name="cpu-monitor")
    thread.start()


def _autostart_stream(app: Flask) -> None:
    """Autostart stream service in background thread after app initialization.

    Uses a lock file to ensure only one worker starts the stream.
    """
    import threading
    import time
    from pathlib import Path
    import fcntl

    def _start_stream():
        # Wait for app to be fully initialized
        time.sleep(3)

        # Use user-specific lock file to avoid permission issues
        import os
        import tempfile
        lock_dir = Path(tempfile.gettempdir())
        lock_file = lock_dir / f"birdshome-stream-autostart-{os.getuid()}.lock"

        fd = None
        try:
            # Remove stale lock file if it exists
            if lock_file.exists():
                try:
                    # Check if the lock file is stale (older than 60 seconds)
                    import time as time_module
                    if time_module.time() - lock_file.stat().st_mtime > 60:
                        lock_file.unlink()
                        app.logger.info(f"Removed stale lock file {lock_file}")
                except (PermissionError, OSError) as e:
                    app.logger.warning(f"Cannot access lock file {lock_file}: {e}")
                    # Continue anyway - we'll try to create our own

            # Try to acquire exclusive lock with proper permissions
            fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # We got the lock, start the stream
            try:
                with app.app_context():
                    from .services.stream_service import stream_service

                    # Check if already running
                    if stream_service.is_running():
                        app.logger.info("Stream already running, skipping autostart")
                        return

                    app.logger.info("Autostarting stream service...")
                    status = stream_service.start()
                    if status.running:
                        app.logger.info(f"Stream autostarted successfully (mode: {status.mode}, PID: {status.pid})")
                    else:
                        app.logger.warning("Stream autostart failed - service not running")
            except Exception as e:
                app.logger.error(f"Failed to autostart stream: {e}")

        except FileExistsError:
            # Another worker is already starting the stream
            app.logger.info("Another worker is starting the stream, skipping autostart")
        except BlockingIOError:
            # Another worker is already starting the stream
            app.logger.info("Lock already held by another process, skipping autostart")
        except Exception as e:
            app.logger.error(f"Error in stream autostart lock handling: {e}")
        finally:
            # Cleanup
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    lock_file.unlink(missing_ok=True)
                except Exception:
                    pass

    thread = threading.Thread(target=_start_stream, daemon=True, name="stream-autostart")
    thread.start()
