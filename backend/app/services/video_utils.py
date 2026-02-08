"""Video utility functions."""

from __future__ import annotations


def get_rotation_filter(rotation: int | str) -> str | None:
    """Get ffmpeg transpose filter for rotation.

    Args:
        rotation: Rotation in degrees (0, 90, 180, 270)

    Returns:
        ffmpeg filter string or None if no rotation needed

    Examples:
        0 or "0" -> None (no rotation)
        90 or "90" -> "transpose=1"
        180 or "180" -> "transpose=1,transpose=1"
        270 or "270" -> "transpose=2"
    """
    try:
        rotation_deg = int(rotation)
    except (ValueError, TypeError):
        return None

    # Normalize to 0-359 range
    rotation_deg = rotation_deg % 360

    if rotation_deg == 0:
        return None
    elif rotation_deg == 90:
        # transpose=1 rotates 90 degrees clockwise
        return "transpose=1"
    elif rotation_deg == 180:
        # Two 90-degree rotations
        return "transpose=1,transpose=1"
    elif rotation_deg == 270:
        # transpose=2 rotates 90 degrees counter-clockwise (= 270 clockwise)
        return "transpose=2"
    else:
        # Unsupported rotation angle
        return None


def apply_video_filters(base_filter: str | None, rotation_filter: str | None, *additional_filters: str) -> list:
    """Combine video filters for ffmpeg.

    Args:
        base_filter: Base filter (e.g., scale)
        rotation_filter: Rotation filter from get_rotation_filter()
        *additional_filters: Additional filters to apply (e.g., grayscale)

    Returns:
        List of ffmpeg arguments ["-vf", "filter_string"] or empty list
    """
    filters = []

    if base_filter:
        filters.append(base_filter)

    if rotation_filter:
        filters.append(rotation_filter)

    # Add any additional filters
    filters.extend(additional_filters)

    if filters:
        return ["-vf", ",".join(filters)]

    return []
