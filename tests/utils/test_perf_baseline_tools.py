from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_module(name: str, relpath: str):
    module_path = ROOT / relpath
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COMPARE = load_module("perf_compare_baseline", "utils/perf_compare_baseline.py")
UPDATE = load_module("update_perf_baseline", "utils/update_perf_baseline.py")


class PerfBaselineToolingTests(unittest.TestCase):
    def test_extract_metrics_from_summary(self) -> None:
        summary = {
            "runs": [
                {"scenario": "A", "download_bps": 100.0, "upload_bps": 20.0, "cpu_avg": 3.0, "cpu_peak": 4.0, "rss_avg": 5.0, "rss_peak": 6.0},
                {"scenario": "D", "download_bps": 200.0, "upload_bps": 40.0, "cpu_avg": 7.0, "cpu_peak": 8.0, "rss_avg": 9.0, "rss_peak": 10.0},
            ]
        }
        metrics = UPDATE.extract_metrics(summary)
        self.assertEqual(metrics["A"]["download_bps"], 100.0)
        self.assertEqual(metrics["D"]["rss_peak"], 10.0)

    def test_compare_classifies_regression_improvement_and_inconclusive(self) -> None:
        current = {
            "A": {"download_bps": [80.0] * 8},
            "B": {"cpu_avg": [8.0] * 8},
            "C": {"rss_avg": [110.0]},
        }
        baseline = {
            "metrics": {
                "A": {"download_bps": [100.0] * 8},
                "B": {"cpu_avg": [10.0] * 8},
                "C": {"rss_avg": [100.0]},
            }
        }

        report = COMPARE.compare_source(source_name="primary", current=current, baseline=baseline, rules=COMPARE.DEFAULT_RULES)
        by_key = {(row["scenario"], row["metric"]): row for row in report["rows"]}

        self.assertEqual(by_key[("A", "download_bps")]["severity"], "Critical")
        self.assertEqual(by_key[("A", "download_bps")]["decision"], "regression")

        self.assertEqual(by_key[("B", "cpu_avg")]["severity"], "Info")
        self.assertEqual(by_key[("B", "cpu_avg")]["decision"], "improvement")

        self.assertEqual(by_key[("C", "rss_avg")]["severity"], "Info")
        self.assertEqual(by_key[("C", "rss_avg")]["decision"], "inconclusive")

    def test_update_main_keeps_commit_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            baseline_root = pathlib.Path(tmp) / "perf-baseline"
            baseline_root.mkdir(parents=True, exist_ok=True)

            args = type(
                "Args",
                (),
                {
                    "summary": "artifacts/summary.json",
                    "source_workflow": "benchmark-harness",
                    "run_id": "run-1",
                    "author": "dev",
                    "reason": "refresh",
                    "window": 2,
                    "commit": "commit-2",
                },
            )()
            summary = {"generated_at": "2026-01-01T00:00:00Z"}
            metrics = {"A": {"download_bps": 1.0}}

            existing = baseline_root / "main" / "moving-average.json"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text('{"sampled_commits": ["commit-1"]}\n')

            UPDATE.update_moving_average(args=args, baseline_root=baseline_root, summary=summary, metrics=metrics)
            updated = COMPARE.load_json(existing)
            self.assertEqual(updated["sampled_commits"], ["commit-2", "commit-1"])


if __name__ == "__main__":
    unittest.main()
