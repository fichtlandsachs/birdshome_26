from __future__ import annotations

import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from .logging_service import log_metric


scheduler = BackgroundScheduler(daemon=True)


def init_scheduler(app) -> None:
    """Initialize background jobs.

    Baseline jobs:
      - photo_capture_job: creates placeholder files unless real camera integration is added
      - retention_job: placeholder

    For production on Pi, you may prefer systemd timers instead.
    """

    if scheduler.running:
        return

    def photo_capture_job():
        t0 = time.time()
        # placeholder - no-op
        log_metric(app.logger, "job_photo", status="noop", duration_ms=int((time.time() - t0) * 1000))

    scheduler.add_job(photo_capture_job, "interval", seconds=300, id="photo_capture", replace_existing=True)

    scheduler.start()
    app.logger.info("APScheduler started with %d job(s)", len(scheduler.get_jobs()))
