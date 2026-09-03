"""Version comparison and GitHub release-response parsing."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import urlparse


_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    page_url: str
    download_url: str


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(current: str, available: str) -> bool:
    """Return False for malformed versions instead of showing a bad update."""
    current_parts = _version_tuple(current)
    available_parts = _version_tuple(available)
    return bool(
        current_parts is not None
        and available_parts is not None
        and available_parts > current_parts
    )


def _github_https_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return ""
    return value


def _installer_url(assets: Any, asset_name: str) -> str:
    if not isinstance(assets, list):
        return ""
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != asset_name:
            continue
        return _github_https_url(asset.get("browser_download_url"))
    return ""


def parse_release_payload(payload: bytes, asset_name: str) -> ReleaseInfo:
    """Parse only the fields the update UI needs from GitHub's response."""
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("release response must be an object")

    version = str(document.get("tag_name", "")).removeprefix("v")
    if _version_tuple(version) is None:
        raise ValueError("release tag is not a semantic version")

    page_url = _github_https_url(document.get("html_url"))
    if not page_url:
        raise ValueError("release page URL is invalid")

    notes = document.get("body")
    return ReleaseInfo(
        version=version,
        notes=notes.strip() if isinstance(notes, str) else "",
        page_url=page_url,
        download_url=_installer_url(document.get("assets"), asset_name) or page_url,
    )
