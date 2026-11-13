"""Base utilities for downloading open datasets with local caching."""
import os
import logging
import urllib.request
import json
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any

from etl.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)


def download_file(url: str, output_path: Path, force_download: bool = False, headers: Optional[Dict[str, str]] = None) -> Path:
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
        headers=headers or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OpenDataGeo/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            content = response.read()
            if not content:
                raise ValueError("Server returned empty content")
            with open(output_path, "wb") as out_file:
                out_file.write(content)
    except Exception as e:
        # If download failed, ensure we don't leave an empty 0-byte file
        if output_path.exists() and output_path.stat().st_size == 0:
            output_path.unlink()
        raise e

    logger.info(f"Downloaded successfully: {output_path.stat().st_size} bytes")
    return output_path


def download_json(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Fetch JSON directly from an API endpoint."""
    req = urllib.request.Request(
        url,
        headers=headers or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OpenDataGeo/1.0",
            "Accept": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def unzip_file(zip_path: Path, extract_to: Optional[Path] = None) -> Path:
    """Extract zip archive."""
    target_dir = extract_to or zip_path.parent / zip_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Extracting {zip_path} to {target_dir}...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(target_dir)
    return target_dir
