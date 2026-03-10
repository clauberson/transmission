# Microbenchmarks de hot paths

Esta suíte cobre microbenchmarks determinísticos para cinco caminhos críticos:

1. `piece_picker.wishlist_next`
2. `peer_selection.from_compact_ipv4`
3. `buffers.stackbuffer_rw`
4. `crypto.sha1_16k`
5. `rpc.json_parse_method_lookup`

## Objetivos de medição

Cada benchmark mede por operação:

- custo temporal (`ns/op`)
- número de alocações (`alloc/op`)
- bytes alocados (`bytes/op`)
- variância intra-run (desvio padrão entre repetições)

O dataset é sintético e determinístico (seeds fixas e payloads fixos), para reduzir ruído.

## Execução

```bash
make microbench \
  PERF_BASELINE_COMMIT=$(git rev-parse --short HEAD) \
  MICROBENCH_REPEATS=12 \
  MICROBENCH_ITERATIONS=800
```

Saída padrão: `artifacts/microbench-summary.json`.

## Comparação por commit

Compare a execução atual com um baseline de outro commit:

```bash
./utils/microbench_compare.py \
  --current artifacts/microbench-summary.json \
  --baseline /caminho/summary-commit-anterior.json \
  --thresholds perf-baseline/microbench-thresholds.json \
  --output-json artifacts/microbench-comparison.json \
  --output-md artifacts/microbench-comparison.md
```

O relatório markdown aponta regressões localizadas por benchmark/função.

## Thresholds locais de regressão

Os limites por benchmark estão em:

- `perf-baseline/microbench-thresholds.json`

Cada benchmark aceita limites locais para:

- `max_ns_per_op`
- `max_allocations_per_op`
- `max_bytes_per_op`
- `max_commit_delta_pct` (comparação com baseline de commit)

## CI noturno

Recomendação para CI noturno:

- manter `MICROBENCH_REPEATS` entre `10..16`
- manter `MICROBENCH_ITERATIONS` entre `600..1200`
- publicar `artifacts/microbench-summary.json` e `artifacts/microbench-comparison.md`

Isso mantém tempo de execução viável e melhora estabilidade estatística.
