# Performance Instrumentation

Transmission now includes optional runtime performance instrumentation for benchmark runs.

## Enable/Disable

Instrumentation is disabled by default and does not change normal client behavior.

Enable it with:

```bash
TR_PERF_METRICS_ENABLED=1
```

## Configuration

All configuration is done via environment variables:

- `TR_PERF_METRICS_ENABLED` (`0`/`1`): enables metric collection and emission.
- `TR_PERF_METRICS_OUTPUT_FILE`: output JSONL file path. Default: `${config-dir}/perf-metrics.jsonl`.
- `TR_PERF_METRICS_INTERVAL_SECONDS`: emission interval in seconds. Default: `5`.
- `TR_PERF_METRICS_SCENARIO_ID`: scenario label.
- `TR_PERF_METRICS_RUN_ID`: run label.
- `TR_PERF_METRICS_COMMIT_SHA`: commit label.

## Emitted metrics

Each JSON line includes:

- throughput (`download_bps`, `upload_bps`)
- piece completion latency (`p50`, `p95`, `p99`)
- request queue latency (`p50`, `p95`, `p99`)
- main loop jitter (`p50`, `p95`, `p99`)
- CPU usage (`avg`, `peak`)
- RSS (`avg`, `peak`)

It also includes:

- `schema_version`
- `timestamp` (UTC ISO-8601)
- labels: `scenario_id`, `run_id`, `commit_sha`
