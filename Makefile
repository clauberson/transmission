.PHONY: benchmark-smoke benchmark-full benchmark-compare-baseline benchmark-dashboard baseline-update-release baseline-update-main microbench microbench-compare

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
MICROBENCH_BUILD_DIR ?= build
MICROBENCH_OUTPUT ?= artifacts/microbench-summary.json
MICROBENCH_COMPARE_JSON ?= artifacts/microbench-comparison.json
MICROBENCH_COMPARE_MD ?= artifacts/microbench-comparison.md
MICROBENCH_THRESHOLDS ?= perf-baseline/microbench-thresholds.json
MICROBENCH_BASELINE ?=
MICROBENCH_REPEATS ?= 12
MICROBENCH_ITERATIONS ?= 800

microbench:
	cmake -S . -B $(MICROBENCH_BUILD_DIR)
	cmake --build $(MICROBENCH_BUILD_DIR) --target libtransmission-microbench
	$(MICROBENCH_BUILD_DIR)/tests/libtransmission/libtransmission-microbench \
		--output $(MICROBENCH_OUTPUT) \
		--commit $(PERF_BASELINE_COMMIT) \
		--repeats $(MICROBENCH_REPEATS) \
		--iterations $(MICROBENCH_ITERATIONS)

microbench-compare:
	./utils/microbench_compare.py \
		--current $(MICROBENCH_OUTPUT) \
		--thresholds $(MICROBENCH_THRESHOLDS) \
		--output-json $(MICROBENCH_COMPARE_JSON) \
		--output-md $(MICROBENCH_COMPARE_MD) \
		$(if $(MICROBENCH_BASELINE),--baseline $(MICROBENCH_BASELINE),)

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
		--output-json $(BENCHMARK_OUTPUT_ROOT)/baseline-comparison.json \
		--output-md $(BENCHMARK_OUTPUT_ROOT)/baseline-comparison.md

benchmark-dashboard:
	./utils/perf_dashboard.py \
		--artifacts-root $(BENCHMARK_OUTPUT_ROOT) \
		--comparison $(BENCHMARK_OUTPUT_ROOT)/baseline-comparison.json \
		--output-json $(BENCHMARK_OUTPUT_ROOT)/perf-dashboard/data.json \
		--output-html $(BENCHMARK_OUTPUT_ROOT)/perf-dashboard/index.html

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
