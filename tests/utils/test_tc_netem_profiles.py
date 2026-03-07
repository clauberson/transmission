from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[2] / "utils" / "tc_netem_profiles.py"
SPEC = importlib.util.spec_from_file_location("tc_netem_profiles", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TcNetemProfilesTests(unittest.TestCase):
    def test_parse_netem_line_with_all_parameters(self) -> None:
        line = "qdisc netem 8001: root refcnt 2 limit 1000 delay 140.0ms 16.0ms loss 1.0% rate 25Mbit"
        parsed = MODULE.parse_netem_line(line)
        assert parsed is not None
        self.assertAlmostEqual(parsed.bandwidth_mbit or 0.0, 25.0)
        self.assertAlmostEqual(parsed.rtt_ms or 0.0, 140.0)
        self.assertAlmostEqual(parsed.jitter_ms or 0.0, 16.0)
        self.assertAlmostEqual(parsed.loss_percent or 0.0, 1.0)

    def test_parse_netem_line_with_gigabit_rate(self) -> None:
        line = "qdisc netem 1: root delay 70.0ms 6.0ms loss 0.2% rate 1Gbit"
        parsed = MODULE.parse_netem_line(line)
        assert parsed is not None
        self.assertAlmostEqual(parsed.bandwidth_mbit or 0.0, 1000.0)

    def test_parse_non_netem_line(self) -> None:
        line = "qdisc fq_codel 0: root refcnt 2"
        self.assertIsNone(MODULE.parse_netem_line(line))

    def test_within_tolerance(self) -> None:
        self.assertTrue(MODULE.within(140, 140.6, "rtt_ms"))
        self.assertFalse(MODULE.within(140, 142.0, "rtt_ms"))


if __name__ == "__main__":
    unittest.main()
