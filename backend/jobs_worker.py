"""Birdshome jobs worker.

Runs APScheduler jobs in a dedicated process, managed by systemd.

This avoids running scheduled jobs inside the gunicorn web workers.
"""

from __future__ import annotations

import signal
import time

from app import create_app
from app.services.scheduler import scheduler, init_scheduler


def main() -> None:
    app = create_app()

    # Ensure scheduler is started (create_app may have it gated by config).
    with app.app_context():
        init_scheduler(app)

    stop = False

    def _handle(_sig, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    # Keep the process alive while APScheduler runs in background thread.
    try:
        while not stop:
            time.sleep(1)
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
