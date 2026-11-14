"""Base utilities for downloading open datasets with local caching."""

import json
import logging
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def download_file(
    url: str,
    output_path: Path,
    force_download: bool = False,
    headers: Optional[Dict[str, str]] = None,
) -> Path:
    """Download file from URL to local path with caching."""
    if output_path.exists() and output_path.stat().st_size > 0 and not force_download:
        logger.info(f"Using cached file: {output_path} ({output_path.stat().st_size} bytes)")
        return output_path

    # Clean existing corrupted / 0-byte file
    if output_path.exists() and output_path.stat().st_size == 0:
        output_path.unlink()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading from {url} to {output_path}...")

    req = urllib.request.Request(
        url,
        headers=headers
        or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OpenDataGeo/1.0"
        },
    )

    import shutil
    import tempfile

    temporary = None
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as target:
                temporary = Path(target.name)
                shutil.copyfileobj(response, target)
        if temporary.stat().st_size == 0:
            raise ValueError("Server returned empty content")
        temporary.replace(output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    logger.info(f"Downloaded successfully: {output_path.stat().st_size} bytes")
    return output_path


def download_json(
    url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 90
) -> Dict[str, Any]:
    """Fetch JSON directly from an API endpoint."""
    req = urllib.request.Request(
        url,
        headers=headers
        or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OpenDataGeo/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def unzip_file(zip_path: Path, extract_to: Optional[Path] = None) -> Path:
    """Extract zip archive."""
    target_dir = extract_to or zip_path.parent / zip_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Extracting {zip_path} to {target_dir}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            if not (target_dir / member.filename).resolve().is_relative_to(target_dir.resolve()):
                raise ValueError("Archive contains a path outside the extraction directory")
        zip_ref.extractall(target_dir)
    return target_dir


def download_json_file(url: str, path: Path, force_download=False):
    """Reject corrupt cache entries and retry bounded transient download failures."""
    import time
    from urllib.error import URLError

    for attempt in range(3):
        try:
            download_file(url, path, force_download=force_download or attempt > 0)
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "error" in data:
                path.unlink(missing_ok=True)
                raise ValueError(f"Source rejected export: {data['error']}")
            return data
        except (json.JSONDecodeError, UnicodeError, URLError, TimeoutError):
            path.unlink(missing_ok=True)
            if attempt == 2:
                raise
            logger.warning("Retrying invalid or unavailable JSON export: %s", path)
            time.sleep(attempt + 1)
