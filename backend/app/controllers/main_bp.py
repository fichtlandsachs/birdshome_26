from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, send_from_directory

main = Blueprint("main", __name__)


@main.get("/assets/<path:filename>")
def spa_assets(filename: str):
    """Serve Vite build assets at /assets/... (needed when SPA is served at '/')."""
    assets_dir = Path(current_app.static_folder) / "app" / "assets"
    if not assets_dir.exists():
        abort(404)
    return send_from_directory(assets_dir, filename, conditional=True)

@main.get("/media/<path:relpath>")
def media(relpath: str):
    """Serve gallery assets stored under MEDIA_ROOT."""
    media_root = Path(current_app.config.get("MEDIA_ROOT", "data")).resolve()
    full = (media_root / relpath).resolve()
    if not str(full).startswith(str(media_root)):
        abort(404)
    if not full.exists():
        abort(404)
    return send_from_directory(media_root, relpath, conditional=True)


def _spa_index_path() -> Path | None:
    static_app_dir = Path(current_app.static_folder) / "app"
    index = static_app_dir / "index.html"
    return index if index.exists() else None



@main.get("/")
@main.get("/<path:path>")
def spa(path: str = ""):
    """Serve SPA for all non-API routes."""
    index = _spa_index_path()
    if not index:
        return (
            "Frontend build missing. Build it via: cd frontend && npm install && npm run build, "
            "then copy dist to backend/app/static/app.",
            503,
        )
    return send_from_directory(index.parent, "index.html")
