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
