#!/bin/bash
# Script to organize media files into proper directory structure
# Creates directories for photos/videos with and without birds

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATIC_DIR="${BACKEND_DIR}/app/static"

echo "=== Birdshome Media Organization Script ==="
echo "Creating directory structure..."

# Create directories if they don't exist
mkdir -p "${STATIC_DIR}/photos_with_birds"
mkdir -p "${STATIC_DIR}/photos_without_birds"
mkdir -p "${STATIC_DIR}/videos_with_birds"
mkdir -p "${STATIC_DIR}/videos_without_birds"
mkdir -p "${STATIC_DIR}/timelapse_video"
mkdir -p "${STATIC_DIR}/timelapse_screens"

echo "✓ Directory structure created:"
echo "  - ${STATIC_DIR}/photos_with_birds"
echo "  - ${STATIC_DIR}/photos_without_birds"
echo "  - ${STATIC_DIR}/videos_with_birds"
echo "  - ${STATIC_DIR}/videos_without_birds"
echo "  - ${STATIC_DIR}/timelapse_video"
echo "  - ${STATIC_DIR}/timelapse_screens"

# Set permissions (if running as root or with sudo)
if [ "$EUID" -eq 0 ]; then
    APP_USER="${APP_USER:-birdshome}"
    APP_GROUP="${APP_GROUP:-birdshome}"

    if id "$APP_USER" &>/dev/null; then
        echo "Setting permissions for user ${APP_USER}:${APP_GROUP}..."
        chown -R "${APP_USER}:${APP_GROUP}" "${STATIC_DIR}"
        chmod -R 775 "${STATIC_DIR}"
        echo "✓ Permissions set"
    fi
fi

echo ""
echo "=== Organization Complete ==="
echo ""
echo "Directory structure is ready. The application will now organize files as follows:"
echo "  • Photos with birds    → photos_with_birds/"
echo "  • Photos without birds → photos_without_birds/"
echo "  • Videos with birds    → videos_with_birds/"
echo "  • Videos (unvalidated) → videos_without_birds/"
echo "  • Timelapse videos     → timelapse_video/"
echo "  • Timelapse frames     → timelapse_screens/"
echo ""
