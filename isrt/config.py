"""
Configuration management for ISRT.

Profiles are stored in ``~/.isrt/config.json`` so that connection details
do not have to be typed on every invocation.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".isrt"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_PORT = 27015
DEFAULT_TIMEOUT = 10.0


def _load_raw() -> Dict[str, Any]:
    """Return the raw config dict from disk, or an empty dict."""
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_raw(data: Dict[str, Any]) -> None:
    """Persist *data* to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_profiles() -> Dict[str, Any]:
    """Return a mapping of profile_name -> profile_dict."""
    return _load_raw().get("profiles", {})


def get_profile(name: str) -> Optional[Dict[str, Any]]:
    """Return a single profile dict, or None if it does not exist."""
    return list_profiles().get(name)


def save_profile(
    name: str,
    host: str,
    port: int,
    password: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Create or update a named connection profile."""
    data = _load_raw()
    data.setdefault("profiles", {})[name] = {
        "host": host,
        "port": port,
        "password": password,
        "timeout": timeout,
    }
    _save_raw(data)


def delete_profile(name: str) -> bool:
    """
    Remove a profile.

    Returns:
        True if the profile existed and was removed, False otherwise.
    """
    data = _load_raw()
    profiles = data.get("profiles", {})
    if name not in profiles:
        return False
    del profiles[name]
    data["profiles"] = profiles
    _save_raw(data)
    return True


def get_default_profile() -> Optional[str]:
    """Return the name of the default profile, or None."""
    return _load_raw().get("default_profile")


def set_default_profile(name: str) -> None:
    """Set the default profile used when no ``--profile`` flag is given."""
    data = _load_raw()
    data["default_profile"] = name
    _save_raw(data)
