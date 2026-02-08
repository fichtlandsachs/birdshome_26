from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(app, service_name: str = "birdshome") -> None:
    """Configure app logger with file and console handlers.

    Args:
        app: Flask application instance
        service_name: Name of the service for log file naming

    Logs to:
    - Console (stderr)
    - /var/log/birdshome/<service_name>.log with rotation
    """
    log_enabled = str(app.config.get("LOG_ENABLED", "1")) not in {"0", "false", "False"}
    level = str(app.config.get("LOG_LEVEL", "INFO")).upper()

    # Keep Flask's default handlers if logging disabled.
    if not log_enabled:
        app.logger.setLevel(level)
        return

    # Get log directory from config
    log_dir = Path(app.config.get("LOG_DIR", "/var/log/birdshome"))
    max_bytes = app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024)
    backup_count = app.config.get("LOG_BACKUP_COUNT", 5)

    # Create log directory if it doesn't exist
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        # Fallback to local logs directory if we can't write to /var/log
        app.logger.warning(f"Could not create {log_dir}: {e}, falling back to ./logs")
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"{service_name}.log"

    app.logger.setLevel(level)

    # Avoid duplicate handlers on reload.
    for h in list(app.logger.handlers):
        app.logger.removeHandler(h)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        app.logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        app.logger.error(f"Could not create log file {log_file}: {e}")

    # Console handler (stderr)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    app.logger.addHandler(stream_handler)

    app.logger.info(f"Logging configured: level={level}, file={log_file}")


def setup_service_logger(name: str, log_dir: str = "/var/log/birdshome", level: str = "INFO") -> logging.Logger:
    """Setup a logger for a standalone service (non-Flask).

    Args:
        name: Service name (used for logger name and filename)
        log_dir: Directory for log files
        level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    # Remove existing handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # Create log directory
    log_path = Path(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        # Fallback to local logs
        log_path = Path("logs")
        log_path.mkdir(exist_ok=True)

    log_file = log_path / f"{name}.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    try:
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level.upper())
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        print(f"ERROR: Could not create log file {log_file}: {e}")

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level.upper())
    logger.addHandler(stream_handler)

    logger.info(f"Service logger initialized: {name}")
    return logger


def log_metric(logger, name: str, **fields):
    """Structured metric-style log line."""
    payload = {"metric": name, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False))
