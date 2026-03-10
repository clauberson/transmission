# Benchmark Harness (A/B/C/D)

Harness reproduzível para execução de cenários de benchmark do Transmission com fases de **warm-up** e **medição**.

## Script principal

- `utils/perf_benchmark_harness.py`

### Parâmetros CLI

```bash
./utils/perf_benchmark_harness.py \
  --mode smoke|full \
  --scenarios A,B,C,D \
  -N 200 \
  --warmup-seconds 120 \
  --measure-seconds 480 \
  --network-profile lan|wan|lossy \
  --output-root artifacts \
  --run-id run-20260101T000000Z \
  --seed 7 \
  --phase-command '<cmd>' \
  --phase-timeout-seconds 1800 \
  --force
```

#### Comportamento por cenário

- Cenário `A`: carga base `N`
- Cenário `B`: carga `2N`
- Cenário `C`: carga `3N`
- Cenário `D`: carga `4N`

### Perfis de rede

- `lan`: baixa latência e alta banda
- `wan`: perfil padrão balanceado
- `lossy`: maior latência e perda

O perfil selecionado é exposto para o comando de fase via `TR_BENCH_NETWORK_PROFILE` e `TR_BENCH_NETWORK_PROFILE_JSON`.


### Netem/tc para cenário D

Use `utils/tc_netem_profiles.py` para aplicar perfis de rede apenas no cenário `D` com setup/teardown seguro:

```bash
./utils/perf_benchmark_harness.py \
  --mode smoke \
  --scenarios D \
  --scenario-d-netem-profile profile_2 \
  --tc-interface eth0
```

Perfis disponíveis:

- `profile_1`: 80 mbit, RTT 70 ms, jitter 6 ms, perda 0.2%
- `profile_2`: 25 mbit, RTT 140 ms, jitter 16 ms, perda 1.0%
- `profile_3`: 8 mbit, RTT 260 ms, jitter 35 ms, perda 2.2%

Cada execução de cenário `D` gera logs dedicados com os parâmetros esperados e medidos:

- `netem-setup.log` / `netem-setup.err`
- `netem-teardown.log` / `netem-teardown.err`

### Validação automatizada dos parâmetros ativos

Aplicar + validar:

```bash
sudo ./utils/tc_netem_profiles.py apply --profile profile_1 --interface eth0
```

Validação isolada:

```bash
sudo ./utils/tc_netem_profiles.py validate --profile profile_1 --interface eth0
```

Reversão segura:

```bash
sudo ./utils/tc_netem_profiles.py teardown --interface eth0
```

O comando `validate` compara banda, RTT, jitter e perda com tolerâncias pequenas e retorna código não-zero em divergência.

### Troubleshooting (runners sem privilégios)

Erros comuns em CI sem privilégios:

1. `tc` ausente (`iproute2` não instalado).
2. runner sem `root`/`CAP_NET_ADMIN`.
3. kernel sem suporte a `netem`.

Fallback recomendado:

- Execute o benchmark sem `--scenario-d-netem-profile`; os cenários continuam rodando com o perfil lógico (`TR_BENCH_NETWORK_PROFILE`) sem alteração real de qdisc.
- Em pipelines sem privilégios, mantenha a validação de performance ativa e marque a etapa de netem como `skipped`/`informational`.
- Para validação real de `tc/netem`, use runner self-hosted com `CAP_NET_ADMIN` e interface dedicada para teste.

## Estrutura de saída

Para cada cenário executado:

- `artifacts/<scenario>/<run_id>/metrics.json`
- `artifacts/<scenario>/<run_id>/warmup.log`
- `artifacts/<scenario>/<run_id>/warmup.err`
- `artifacts/<scenario>/<run_id>/measurement.log`
- `artifacts/<scenario>/<run_id>/measurement.err`

Resumo consolidado:

- `artifacts/summary.json`

## Entrypoints Make

- Smoke (A e D):

```bash
make benchmark-smoke
```

- Full (A/B/C/D):

```bash
make benchmark-full
```

- Dashboard consolidado (fonte + HTML):

```bash
make benchmark-dashboard
```

Variáveis úteis:

- `BENCHMARK_N`
- `BENCHMARK_NETWORK_PROFILE`
- `BENCHMARK_OUTPUT_ROOT`
- `BENCHMARK_SCENARIOS_SMOKE`
- `BENCHMARK_SCENARIOS_FULL`

## Entrypoint CI

Workflow: `.github/workflows/benchmark-harness.yml`

- PR (paths do harness): executa `make benchmark-smoke`
- `workflow_dispatch`:
  - `mode=smoke` → `make benchmark-smoke`
  - `mode=full` → `make benchmark-full`


## Baseline versionado de performance

Diretório raiz: `perf-baseline/`

- `perf-baseline/manifest.json`: resolve baseline **primário** (último release estável) e **secundário** (média móvel da `main`).
- `perf-baseline/releases/<tag>.json`: baseline por release com rastreabilidade de tag e commit.
- `perf-baseline/main/moving-average.json`: baseline secundário da branch `main`.

### Atualização com trilha de auditoria

Script: `utils/update_perf_baseline.py`

Campos obrigatórios de auditoria:

- `--author`
- `--reason`
- `--commit`

Exemplo para release:

```bash
make baseline-update-release \
  PERF_BASELINE_RELEASE=v4.0.7 \
  PERF_BASELINE_COMMIT=<sha> \
  PERF_BASELINE_AUTHOR="nome" \
  PERF_BASELINE_REASON="release estável"
```

Exemplo para média móvel da `main`:

```bash
make baseline-update-main \
  PERF_BASELINE_COMMIT=<sha> \
  PERF_BASELINE_AUTHOR="nome" \
  PERF_BASELINE_REASON="atualização periódica"
```

### Comparação automática no pipeline

Script: `utils/perf_compare_baseline.py`

- Lê `perf-baseline/manifest.json`.
- Resolve baseline primário/secundário automaticamente.
- Compara o `artifacts/summary.json` contra ambos usando:
  - variação percentual por KPI (mediana current vs mediana baseline);
  - teste não-paramétrico de Mann-Whitney (two-sided) para significância.
- Classifica cada KPI em `Info`/`Warn`/`Critical` com regras configuráveis em `perf-baseline/kpi-rules.json` (`thresholds` + `alpha`).
- Gera dois artefatos para CI/comentário automático em PR:
  - `artifacts/baseline-comparison.json`
  - `artifacts/baseline-comparison.md`

No workflow de benchmark (`.github/workflows/benchmark-harness.yml`) essa comparação roda após o benchmark.

## Dashboard de performance por cenário/KPI

Script: `utils/perf_dashboard.py`

- Consolida os artefatos de benchmark (`**/summary.json`) em uma fonte única (`artifacts/perf-dashboard/data.json`).
- Publica dashboard estático (`artifacts/perf-dashboard/index.html`) com:
  - painéis para throughput, latência, CPU e memória;
  - distribuição por KPI (mediana, IQR, P95, P99);
  - tendência por cenário/KPI;
  - comparação baseline vs branch com alertas visuais `Info`/`Warn`/`Critical`;
  - filtros por `branch` e `hardware_profile`.

No workflow `.github/workflows/benchmark-harness.yml`, o dashboard é atualizado automaticamente após cada execução do benchmark.

### Bloqueio contra atualização acidental em PR

Workflow: `.github/workflows/perf-baseline-guard.yml`

Quando houver mudança em `perf-baseline/**`, o PR só passa se:

1. contiver label `perf-baseline-approved`; e
2. tiver ao menos 1 review com estado `APPROVED`.

Isso força um fluxo explícito de aprovação para qualquer alteração de baseline.

## Códigos de erro distintos

- `2`: argumentos inválidos
- `10`: falha de setup/diretórios
- `20`: falha na fase de warm-up
- `30`: falha na fase de medição
- `40`: falha ao gravar resumo
- `50`: timeout de fase

## Reprodutibilidade e idempotência

- Use `--run-id` fixo e `--force` para sobrescrever a mesma run de forma determinística.
- O `--seed` controla os resultados sintéticos padrão do `--phase-command`.
- O harness cria todo o diretório de saída automaticamente, compatível com runner limpo.
