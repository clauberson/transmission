.PHONY: benchmark-smoke benchmark-full benchmark-compare-baseline baseline-update-release baseline-update-main

BENCHMARK_HARNESS ?= ./utils/perf_benchmark_harness.py
BENCHMARK_OUTPUT_ROOT ?= artifacts
BENCHMARK_N ?= 200
BENCHMARK_NETWORK_PROFILE ?= wan
BENCHMARK_SCENARIOS_SMOKE ?= A,D
BENCHMARK_SCENARIOS_FULL ?= A,B,C,D
PERF_BASELINE_ROOT ?= perf-baseline
PERF_BASELINE_AUTHOR ?= ci
PERF_BASELINE_REASON ?= rotina
PERF_BASELINE_COMMIT ?= unknown
PERF_BASELINE_RELEASE ?= v0.0.0
PERF_BASELINE_RUN_ID ?= manual

benchmark-smoke:
	$(BENCHMARK_HARNESS) \
		--mode smoke \
		--scenarios $(BENCHMARK_SCENARIOS_SMOKE) \
		-N $(BENCHMARK_N) \
		--network-profile $(BENCHMARK_NETWORK_PROFILE) \
		--output-root $(BENCHMARK_OUTPUT_ROOT)

benchmark-full:
	$(BENCHMARK_HARNESS) \
		--mode full \
		--scenarios $(BENCHMARK_SCENARIOS_FULL) \
		-N $(BENCHMARK_N) \
		--network-profile $(BENCHMARK_NETWORK_PROFILE) \
		--output-root $(BENCHMARK_OUTPUT_ROOT)

benchmark-compare-baseline:
	./utils/perf_compare_baseline.py \
		--summary $(BENCHMARK_OUTPUT_ROOT)/summary.json \
		--baseline-root $(PERF_BASELINE_ROOT) \
		--output $(BENCHMARK_OUTPUT_ROOT)/baseline-comparison.json

baseline-update-release:
	./utils/update_perf_baseline.py \
		--summary $(BENCHMARK_OUTPUT_ROOT)/summary.json \
		--baseline-root $(PERF_BASELINE_ROOT) \
		--kind release \
		--release $(PERF_BASELINE_RELEASE) \
		--commit $(PERF_BASELINE_COMMIT) \
		--author "$(PERF_BASELINE_AUTHOR)" \
		--reason "$(PERF_BASELINE_REASON)" \
		--run-id $(PERF_BASELINE_RUN_ID)

baseline-update-main:
	./utils/update_perf_baseline.py \
		--summary $(BENCHMARK_OUTPUT_ROOT)/summary.json \
		--baseline-root $(PERF_BASELINE_ROOT) \
		--kind moving-average-main \
		--commit $(PERF_BASELINE_COMMIT) \
		--author "$(PERF_BASELINE_AUTHOR)" \
		--reason "$(PERF_BASELINE_REASON)" \
		--run-id $(PERF_BASELINE_RUN_ID)
