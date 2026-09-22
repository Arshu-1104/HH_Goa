"""
device_utils.py — Canonical device normalisation shared across the whole project.

Rules
-----
* Only import this module for device normalisation — do NOT copy the logic.
* Missing / blank DeviceInfo → returns None (not "unknown_device").
  Callers must treat None as "no device relationship".
* Identical raw strings → identical canonical IDs.
* Minor variations (build strings, patch versions, extra whitespace) → same ID.
"""

import re


def normalize_device_info(raw: str | None) -> str | None:
    """
    Normalise a raw DeviceInfo string into a stable, lowercase canonical ID.

    Returns
    -------
    str
        Canonical device ID, e.g. ``"samsung_sm-g892a"`` or ``"ios_11"``.
    None
        When *raw* is empty, None, or whitespace-only.
        Callers **must not** create a DeviceProfile vertex or USES_DEVICE edge
        when this function returns None.

    Examples
    --------
    >>> normalize_device_info("SAMSUNG SM-G892A Build/NRD90M")
    'samsung_sm-g892a'
    >>> normalize_device_info("iOS 11.1.2")
    'ios_11.1'
    >>> normalize_device_info("")
    None
    >>> normalize_device_info(None)
    None
    """
    if not raw or not raw.strip():
        return None

    s = raw.lower().strip()

    # Remove "build/XXXXX" tokens
    s = re.sub(r"\bbuild/\S+", "", s)

    # Collapse patch versions x.y.z → x.y  (keeps major.minor)
    s = re.sub(r"(\d+\.\d+)\.\d+", r"\1", s)

    # Collapse whitespace to underscore
    s = re.sub(r"\s+", "_", s.strip())

    # Drop characters that are not alphanumeric, hyphen, or underscore
    s = re.sub(r"[^a-z0-9_\-]", "", s)

    # Strip residual leading/trailing underscores / hyphens
    s = s.strip("_-")

    return s if s else None
