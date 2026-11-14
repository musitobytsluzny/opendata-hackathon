"""Pipeline failures must remain visible and preserve independently committed imports."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from etl import cli


class PipelineTests(unittest.TestCase):
    def test_failure_continues_and_report_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(cli, "DATA_DIR", Path(directory)),
                patch.object(cli, "DATASETS", ("ruian", "csu", "osm")),
                patch.object(
                    cli, "main", side_effect=[None, RuntimeError("source offline"), None]
                ) as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "Pipeline incomplete: csu"):
                    cli.run_pipeline(force=True)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(run.call_args_list[2].args[0], ["--dataset", "osm", "--force"])
            report = json.loads((Path(directory) / "pipeline-report.json").read_text())
            self.assertEqual(report["datasets"]["ruian"]["status"], "completed")
            self.assertEqual(report["datasets"]["csu"]["status"], "failed")
            self.assertEqual(report["datasets"]["osm"]["status"], "completed")

    def test_keep_going_requires_full_pipeline(self):
        with self.assertRaises(SystemExit):
            cli.main(["--dataset", "ruian", "--keep-going"])
