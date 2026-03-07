.PHONY: benchmark-smoke benchmark-full

BENCHMARK_HARNESS ?= ./utils/perf_benchmark_harness.py
BENCHMARK_OUTPUT_ROOT ?= artifacts
BENCHMARK_N ?= 200
BENCHMARK_NETWORK_PROFILE ?= wan
BENCHMARK_SCENARIOS_SMOKE ?= A,D
BENCHMARK_SCENARIOS_FULL ?= A,B,C,D

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
