"""Corrupt downloads cannot become persistent valid cache entries."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from etl.downloaders.base import download_json_file


class DownloadTests(unittest.TestCase):
    def test_corrupt_json_is_removed_and_downloaded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.json"
            path.write_text('{"features": [')

            def download(url, target, force_download=False):
                if force_download:
                    self.assertFalse(target.exists())
                    target.write_text('{"features": []}')
                return target

            with (
                patch("etl.downloaders.base.download_file", side_effect=download) as fetch,
                patch("time.sleep"),
            ):
                self.assertEqual(
                    download_json_file("https://example.test/page", path), {"features": []}
                )
                self.assertEqual(fetch.call_count, 2)

    def test_source_error_is_not_cached_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.json"
            path.write_text('{"error": {"code": 400}}')
            with patch("etl.downloaders.base.download_file", return_value=path):
                with self.assertRaisesRegex(ValueError, "Source rejected export"):
                    download_json_file("https://example.test/page", path)
            self.assertFalse(path.exists())
