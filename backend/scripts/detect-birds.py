#!/usr/bin/env python3
"""Bird detection service for video classification.

Analyzes videos in data/videos directory using YOLO model to detect birds.
Moves videos with birds to data/videos_with_birds and without birds to data/videos_no_birds.
"""

import sys
import os
from pathlib import Path
import logging
import shutil

# Change to backend directory to ensure correct working directory
script_dir = Path(__file__).parent
backend_dir = script_dir.parent
os.chdir(backend_dir)

# Add parent directory to path for imports
sys.path.insert(0, str(backend_dir))

from app import create_app
from app.models import Video, Setting

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BirdDetectionService:
    """Service for detecting birds in videos and organizing them."""

    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.videos_dir = media_root / "videos"
        self.videos_with_birds = media_root / "videos_with_birds"
        self.videos_no_birds = media_root / "videos_no_birds"

        # Ensure directories exist
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.videos_with_birds.mkdir(parents=True, exist_ok=True)
        self.videos_no_birds.mkdir(parents=True, exist_ok=True)

        self.yolo_model = None
        self.yolo_threshold = 0.5

    def load_yolo_model(self, model_path: str):
        """Load YOLO model for bird detection."""
        try:
            from ultralytics import YOLO
            logger.info(f"Loading YOLO model from {model_path}")
            self.yolo_model = YOLO(model_path)
            logger.info("YOLO model loaded successfully")
            return True
        except ImportError:
            logger.error("ultralytics package not installed. Run: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            return False

    def detect_birds_in_video(self, video_path: Path) -> tuple[bool, int]:
        """Detect birds in video using YOLO model.

        Args:
            video_path: Path to video file

        Returns:
            tuple of (has_birds: bool, bird_count: int)
        """
        if not self.yolo_model:
            logger.warning("YOLO model not loaded, skipping detection")
            return False, 0

        try:
            import cv2

            # Open video
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logger.error(f"Failed to open video: {video_path}")
                return False, 0

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))

            # Sample frames (every second or max 10 frames for short videos)
            sample_interval = max(fps, 1) if fps > 0 else 30
            frames_to_check = min(10, max(1, total_frames // sample_interval))

            bird_detections = 0
            frames_checked = 0

            logger.info(f"Analyzing {video_path.name} ({total_frames} frames, checking {frames_to_check} samples)")

            for frame_idx in range(0, total_frames, sample_interval):
                if frames_checked >= frames_to_check:
                    break

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()

                if not ret:
                    continue

                # Run YOLO detection
                results = self.yolo_model(frame, verbose=False)

                # Check for bird class (class 14 in COCO dataset is "bird")
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])

                        # Class 14 = bird in COCO dataset
                        if cls == 14 and conf >= self.yolo_threshold:
                            bird_detections += 1
                            logger.debug(f"Bird detected in frame {frame_idx} with confidence {conf:.2f}")

                frames_checked += 1

            cap.release()

            has_birds = bird_detections > 0
            logger.info(f"Video {video_path.name}: {'BIRDS' if has_birds else 'NO BIRDS'} detected ({bird_detections} detections in {frames_checked} frames)")

            return has_birds, bird_detections

        except Exception as e:
            logger.error(f"Error detecting birds in {video_path}: {e}")
            return False, 0

    def process_video(self, video_path: Path) -> dict:
        """Process a single video: detect birds and move to appropriate directory.

        Args:
            video_path: Path to video file in videos directory

        Returns:
            dict with processing result
        """
        if not video_path.exists():
            return {"ok": False, "error": "Video file not found"}

        logger.info(f"Processing video: {video_path.name}")

        # Detect birds
        has_birds, bird_count = self.detect_birds_in_video(video_path)

        # Determine target directory
        target_dir = self.videos_with_birds if has_birds else self.videos_no_birds
        target_path = target_dir / video_path.name

        # Move file
        try:
            shutil.move(str(video_path), str(target_path))
            logger.info(f"Moved {video_path.name} to {target_dir.name}")

            # Update database record
            relative_path = str(target_path.relative_to(self.media_root))
            return {
                "ok": True,
                "video": video_path.name,
                "has_birds": has_birds,
                "bird_count": bird_count,
                "moved_to": str(target_path),
                "relative_path": relative_path
            }
        except Exception as e:
            logger.error(f"Failed to move video {video_path.name}: {e}")
            return {"ok": False, "error": str(e), "video": video_path.name}

    def process_all_videos(self) -> dict:
        """Process all unprocessed videos in the videos directory.

        Returns:
            dict with summary of processing results
        """
        # Find all video files in videos directory
        video_files = list(self.videos_dir.glob("*.mp4")) + list(self.videos_dir.glob("*.avi"))

        if not video_files:
            logger.info("No videos to process")
            return {
                "ok": True,
                "processed": 0,
                "with_birds": 0,
                "without_birds": 0,
                "errors": 0
            }

        logger.info(f"Found {len(video_files)} videos to process")

        results = {
            "ok": True,
            "processed": 0,
            "with_birds": 0,
            "without_birds": 0,
            "errors": 0,
            "details": []
        }

        for video_path in video_files:
            result = self.process_video(video_path)
            results["details"].append(result)

            if result.get("ok"):
                results["processed"] += 1
                if result.get("has_birds"):
                    results["with_birds"] += 1
                else:
                    results["without_birds"] += 1

                # Update database
                try:
                    app = create_app()
                    with app.app_context():
                        # Find video record by original filename
                        video = Video.query.filter(
                            Video.path.like(f"%{video_path.name}")
                        ).first()

                        if video:
                            video.path = result["relative_path"]
                            video.has_birds = result.get("has_birds", False)
                            from app.extensions import db
                            db.session.commit()
                            logger.info(f"Updated database record for {video_path.name}")
                except Exception as e:
                    logger.error(f"Failed to update database for {video_path.name}: {e}")
            else:
                results["errors"] += 1

        logger.info(f"Processing complete: {results['processed']} videos, "
                   f"{results['with_birds']} with birds, "
                   f"{results['without_birds']} without birds, "
                   f"{results['errors']} errors")

        return results


def is_detection_time_window(start_hour: int, end_hour: int) -> tuple[bool, str]:
    """Check if current time is within configured detection window.

    Args:
        start_hour: Start hour (0-23)
        end_hour: End hour (0-23)

    Returns:
        tuple of (is_allowed, reason_message)
    """
    from datetime import datetime

    now = datetime.now()
    current_hour = now.hour

    # Handle time window that spans midnight (e.g., 14:00 to 6:00)
    if start_hour > end_hour:
        is_allowed = current_hour >= start_hour or current_hour < end_hour
    else:
        # Handle time window within same day (e.g., 8:00 to 18:00)
        is_allowed = start_hour <= current_hour < end_hour

    if is_allowed:
        return True, f"Detection allowed (current hour: {current_hour}, window: {start_hour}-{end_hour})"
    else:
        return False, f"Detection outside time window (current hour: {current_hour}, window: {start_hour}-{end_hour})"


def main():
    """Main bird detection processing."""
    logger.info("Starting bird detection service...")

    # Load settings
    try:
        app = create_app()
        with app.app_context():
            settings = {s.key: s.value for s in Setting.query.all()}

            media_root = Path(app.config.get("MEDIA_ROOT", "data"))
            model_path = settings.get("YOLO_MODEL_PATH", "/opt/birdshome/models/yolo.pt")
            threshold = float(settings.get("YOLO_THRESH", "0.5"))
            start_hour = int(settings.get("DETECTION_START_HOUR", "14"))
            end_hour = int(settings.get("DETECTION_END_HOUR", "6"))

            logger.info(f"Media root: {media_root}")
            logger.info(f"YOLO model: {model_path}")
            logger.info(f"Detection threshold: {threshold}")
            logger.info(f"Detection time window: {start_hour}:00 - {end_hour}:00")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1

    # Check if we're in the detection time window
    is_allowed, time_msg = is_detection_time_window(start_hour, end_hour)
    if not is_allowed:
        logger.info(time_msg)
        logger.info("Bird detection service skipped (outside time window)")
        return 0

    # Initialize detection service
    service = BirdDetectionService(media_root)
    service.yolo_threshold = threshold

    # Check if there are videos to process first
    video_files = list(service.videos_dir.glob("*.mp4")) + list(service.videos_dir.glob("*.avi"))

    if not video_files:
        logger.info("No videos to process, skipping YOLO model load")
        logger.info("Bird detection service completed successfully (no work)")
        return 0

    # Load YOLO model only if there are videos to process
    if not service.load_yolo_model(model_path):
        logger.error("Cannot proceed without YOLO model")
        return 1

    # Process all videos
    results = service.process_all_videos()

    if results["errors"] > 0:
        logger.warning(f"Completed with {results['errors']} errors")
        return 1

    logger.info("Bird detection service completed successfully")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.exception(f"Bird detection service failed: {e}")
        sys.exit(1)
