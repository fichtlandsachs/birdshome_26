from __future__ import annotations

from datetime import datetime, date

from flask_login import UserMixin
from sqlalchemy import Index

from .extensions import db


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(db.Text, nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def get_id(self) -> str:
        return str(self.id)


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    has_birds = db.Column(db.Boolean, default=False, nullable=False, index=True)
    duration_s = db.Column(db.Integer, nullable=True)
    resolution = db.Column(db.String(32), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=True)
    uploaded = db.Column(db.Boolean, default=False, nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)


class Photo(db.Model):
    __tablename__ = "photos"

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolution = db.Column(db.String(32), nullable=True)
    uploaded = db.Column(db.Boolean, default=False, nullable=False, index=True)


class Timelapse(db.Model):
    __tablename__ = "timelapses"

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Text, nullable=False)
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    fps = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    uploaded = db.Column(db.Boolean, default=False, nullable=False, index=True)


class Detection(db.Model):
    __tablename__ = "detections"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, index=True)
    frames_total = db.Column(db.Integer, nullable=True)
    frames_with_bird = db.Column(db.Integer, nullable=True)
    max_conf = db.Column(db.Float, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    count = db.Column(db.Integer, default=1, nullable=False)


class BioEvent(db.Model):
    __tablename__ = "bio_events"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False)  # egg|hatch|fledge|arrival
    event_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)


Index("ix_videos_uploaded_created", Video.uploaded, Video.created_at)
Index("ix_photos_uploaded_created", Photo.uploaded, Photo.created_at)
