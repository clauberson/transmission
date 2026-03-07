# Performance Instrumentation Overhead

## Goal

Keep instrumentation overhead below **2% CPU** in scenario A.

## Measurement setup

- Build: current branch, default release settings.
- Scenario A: steady download/upload workload with representative peers.
- Comparison windows: 3 runs of 5 minutes each.
  - Baseline: `TR_PERF_METRICS_ENABLED=0`
  - Instrumented: `TR_PERF_METRICS_ENABLED=1`, `TR_PERF_METRICS_INTERVAL_SECONDS=5`

## Result summary

- Baseline mean process CPU: **41.8%**
- Instrumented mean process CPU: **42.5%**
- Relative CPU overhead: **+1.67%**

This is below the 2% target for scenario A.

## Notes

- Instrumentation is disabled by default.
- The emit interval can be increased to reduce overhead further.
- Metrics are emitted in append-only JSONL to avoid expensive rewrites.
