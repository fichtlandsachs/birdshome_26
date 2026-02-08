import os

from dotenv import load_dotenv

from . import constants as C

load_dotenv()


def _env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


class Config:
    # Flask
    SECRET_KEY = _env("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL", "sqlite:///birdshome.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_NAME = C.SESSION_COOKIE_NAME
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("TLS_MODE", "letsencrypt") != "none"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    PREFERRED_URL_SCHEME = "https"

    # CSRF
    CSRF_COOKIE_NAME = C.CSRF_COOKIE_NAME

    # Streaming / ffmpeg
    FFMPEG_BIN = _env("FFMPEG_BIN", "ffmpeg")
    VIDEO_SOURCE = _env("VIDEO_SOURCE")
    AUDIO_SOURCE = _env("AUDIO_SOURCE", "-f alsa -i plughw:3,0")

    # Bootstrap admin (password is managed in database, not in .env)
    ADMIN_USERNAME = _env("ADMIN_USERNAME", "admin")

    # Internal control token (used by local system services to call internal endpoints)
    INTERNAL_TOKEN = _env("INTERNAL_TOKEN", "change-me")

    # Scheduler
    SCHEDULER_ENABLED = _env("SCHEDULER_ENABLED", "1")

    # Logging
    # Use local logs directory in development, /var/log/birdshome in production
    default_log_dir = "/var/log/birdshome" if _env("FLASK_ENV") == "production" else "logs"
    LOG_DIR = _env("LOG_DIR", default_log_dir)
    LOG_FILE = _env("LOG_FILE", "birdshome.log")
    LOG_MAX_BYTES = int(_env("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB
    LOG_BACKUP_COUNT = int(_env("LOG_BACKUP_COUNT", "5"))

# Feature toggles
    LOG_ENABLED_DEFAULT = _env("LOG_ENABLED", "1")
    LOG_LEVEL_DEFAULT = _env("LOG_LEVEL", "INFO")

    DEFAULT_SETTINGS = {
        C.STREAM_MODE: _env(C.STREAM_MODE, C.MODE_HLS),
        C.STREAM_RES: _env(C.STREAM_RES, "640x480"),
        C.STREAM_FPS: _env(C.STREAM_FPS, "30"),
        C.RECORD_RES: _env(C.RECORD_RES, "640x480"),
        C.RECORD_FPS: _env(C.RECORD_FPS, "30"),
        C.VIDEO_ROTATION: _env(C.VIDEO_ROTATION, "0"),
        C.VIDEO_SOURCE: _env(C.VIDEO_SOURCE, "v4l2 -i /dev/video0"),
        C.AUDIO_SOURCE: _env(C.AUDIO_SOURCE, "-f alsa -i plughw:3,0"),
        C.STREAM_UDP_URL: _env(C.STREAM_UDP_URL, "udp://127.0.0.1:5004?pkt_size=1316&reuse=1&overrun_nonfatal=1&fifo_size=5000000"),
        C.MOTION_SOURCE: _env(C.MOTION_SOURCE, "udp://127.0.0.1:5004?pkt_size=1316&reuse=1&overrun_nonfatal=1&fifo_size=5000000"),

        C.HLS_SEGMENT_SECONDS: _env(C.HLS_SEGMENT_SECONDS, "3"),
        C.HLS_PLAYLIST_SIZE: _env(C.HLS_PLAYLIST_SIZE, "6"),
        C.PREFIX: _env(C.PREFIX, "nest_"),
        C.PHOTO_INTERVAL_S: _env(C.PHOTO_INTERVAL_S, "60"),
        C.TIMELAPSE_FPS: _env(C.TIMELAPSE_FPS, "30"),
        C.TIMELAPSE_DAYS: _env(C.TIMELAPSE_DAYS, "7"),
        C.UPLOAD_INTERVAL_MIN: _env(C.UPLOAD_INTERVAL_MIN, "30"),
        C.RETENTION_DAYS: _env(C.RETENTION_DAYS, "14"),
        C.YOLO_MODEL_PATH: _env(C.YOLO_MODEL_PATH, "/opt/birdshome/models/yolo.pt"),
        C.YOLO_THRESH: _env(C.YOLO_THRESH, "0.5"),
        C.IR_GPIO: _env(C.IR_GPIO, "17"),
        C.LUX_GPIO: _env(C.LUX_GPIO, "27"),
        C.LUX_THRESHOLD: _env(C.LUX_THRESHOLD, "0.5"),
        C.LOG_ENABLED: _env(C.LOG_ENABLED, "1"),
        C.LOG_LEVEL: _env(C.LOG_LEVEL, "INFO"),
        C.MOTION_ENABLED: _env(C.MOTION_ENABLED, "1"),
        C.MOTION_THRESHOLD: _env(C.MOTION_THRESHOLD, "25"),
        C.MOTION_DURATION_S: _env(C.MOTION_DURATION_S, "10"),
        C.MOTION_COOLDOWN_S: _env(C.MOTION_COOLDOWN_S, "5"),
        C.MOTION_SENSOR_GPIO: _env(C.MOTION_SENSOR_GPIO, "22"),
        C.MOTION_SENSOR_ENABLED: _env(C.MOTION_SENSOR_ENABLED, "0"),
        C.MOTION_FRAMEDIFF_ENABLED: _env(C.MOTION_FRAMEDIFF_ENABLED, "1"),
        C.MOTION_SERVICE_ENABLED: _env(C.MOTION_SERVICE_ENABLED, "0"),
        C.HIDRIVE_USER: _env(C.HIDRIVE_USER, ""),
        C.HIDRIVE_PASSWORD: _env(C.HIDRIVE_PASSWORD, ""),
        C.HIDRIVE_TARGET_DIR: _env(C.HIDRIVE_TARGET_DIR, "Birdshome"),
        C.UPLOAD_PHOTOS: _env(C.UPLOAD_PHOTOS, "1"),
        C.UPLOAD_VIDEOS: _env(C.UPLOAD_VIDEOS, "1"),
        C.UPLOAD_TIMELAPSES: _env(C.UPLOAD_TIMELAPSES, "1"),
        C.UPLOAD_RETENTION_DAYS: _env(C.UPLOAD_RETENTION_DAYS, "30"),
        C.UPLOAD_START_HOUR: _env(C.UPLOAD_START_HOUR, "22"),
        C.UPLOAD_END_HOUR: _env(C.UPLOAD_END_HOUR, "6"),
        C.WIFI_SSID: _env(C.WIFI_SSID, ""),
        C.WIFI_PASSWORD: _env(C.WIFI_PASSWORD, ""),
        C.DETECTION_START_HOUR: _env(C.DETECTION_START_HOUR, "14"),
        C.DETECTION_END_HOUR: _env(C.DETECTION_END_HOUR, "6"),
        C.DAY_NIGHT_ENABLED: _env(C.DAY_NIGHT_ENABLED, "0"),
        C.DAY_NIGHT_THRESHOLD: _env(C.DAY_NIGHT_THRESHOLD, "30.0"),
        C.DAY_NIGHT_CHECK_INTERVAL: _env(C.DAY_NIGHT_CHECK_INTERVAL, "60.0"),
    }
