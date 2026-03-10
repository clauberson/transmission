# Playbook de decisão de release baseado em performance

## 1) Objetivo e escopo
Este playbook define como decidir **Go / No-Go** de releases com base em performance para os componentes:
- `libtransmission`
- Daemons (`transmission-daemon`, RPC)
- Clientes (`gtk`, `qt`, `web`)
- Pipeline de build e testes de performance

O processo é aplicável a releases estáveis, release candidates (RC) e hotfixes.

## 2) Modelo de metas por métrica
Cada métrica crítica deve ser classificada em três níveis:

- **Must-have (gate de release)**: se não atender, release é bloqueada, exceto com waiver aprovado.
- **Target (objetivo padrão)**: esperado para release saudável; desvios exigem plano de correção priorizado.
- **Aspirational (melhoria contínua)**: meta de evolução; não bloqueia release.

### 2.1 Catálogo mínimo de métricas
| Métrica | Must-have | Target | Aspirational | Dono |
|---|---:|---:|---:|---|
| Tempo de startup daemon (P95) | <= 1500 ms | <= 1100 ms | <= 900 ms | Owner Core Runtime |
| Latência de RPC `session-get` (P95) | <= 250 ms | <= 180 ms | <= 120 ms | Owner RPC/API |
| Throughput de download em cenário padrão | >= baseline -5% | >= baseline -2% | >= baseline +3% | Owner Networking |
| Uso de CPU em seed estável | <= baseline +12% | <= baseline +7% | <= baseline +3% | Owner Core Runtime |
| Uso de memória RSS (daemon com 200 torrents) | <= baseline +15% | <= baseline +8% | <= baseline +3% | Owner Storage/Metadata |
| Tempo de render da UI principal (P95) | <= 300 ms | <= 220 ms | <= 160 ms | Owner UX Clients |

> **Regra de baseline:** baseline é a média móvel das últimas 3 releases estáveis no mesmo ambiente de benchmark.

## 3) Ownership por subsistema
| Subsistema | Owner primário | Backup | Métricas sob responsabilidade |
|---|---|---|---|
| Core Runtime (`libtransmission`) | Maintainer Core | Maintainer Build | CPU, memória, startup |
| Networking / Peer IO | Maintainer Network | Maintainer Core | throughput, latência de handshake |
| RPC/API | Maintainer RPC | Maintainer Web | latência P95/P99, erros 5xx |
| Storage/Metadata | Maintainer Storage | Maintainer Core | IO, RSS, tempo de verificação |
| UI GTK/Qt/Web | Maintainer UX | Maintainer RPC | tempo de render, responsividade |
| CI/Benchmark Harness | Maintainer Infra | Maintainer Release | estabilidade de benchmark e coleta |

### 3.1 Responsabilidades do owner
1. Validar qualidade dos dados de benchmark.
2. Classificar regressões (crítica, alta, média, baixa).
3. Aprovar ou rejeitar waiver no seu domínio.
4. Entregar plano de correção com prazo e milestone.

## 4) Processo de decisão de release

### 4.1 Fluxo
1. **Congelamento de código** (T-7 dias).
2. **Execução de suíte de performance** em ambiente padronizado.
3. **Comparação com baseline e metas** (Must-have/Target/Aspirational).
4. **Triagem de desvios** por owner.
5. **Decisão:**
   - **Go**: todos os Must-have atendidos.
   - **Conditional Go**: Must-have violado com waiver aprovado e válido.
   - **No-Go**: Must-have violado sem waiver aprovado.
6. **Publicação de ata** com decisão, evidências, e responsáveis.

### 4.2 Política de waiver (auditável e com expiração)
Um waiver só é válido se:
- estiver no template oficial,
- tiver ID único,
- tiver justificativa técnica,
- tiver prazo de expiração explícito,
- tiver plano de correção com owner, milestone e data,
- tiver aprovação de Release Manager + owner do subsistema.

**Auditoria mínima**:
- armazenar waiver no repositório (ou sistema de change management),
- vincular issue/PR de correção,
- registrar status quinzenal até fechamento,
- expirar automaticamente na data definida (renovação exige novo waiver).

## 5) SLA de resposta a regressões críticas

| Severidade | Critério | SLA de triagem | SLA de mitigação | SLA de correção definitiva |
|---|---|---|---|---|
| Crítica | quebra Must-have com impacto em usuários/infra | <= 4h úteis | <= 24h | <= 7 dias corridos |
| Alta | degradação > Target e risco de escalar | <= 1 dia útil | <= 3 dias úteis | <= 14 dias corridos |
| Média | fora de Target sem risco imediato | <= 2 dias úteis | <= 7 dias úteis | <= 1 release |
| Baixa | apenas desvio Aspirational | <= 5 dias úteis | conforme capacidade | backlog |

**Mitigação aceitável**: rollback, feature flag, limitação temporária documentada ou patch de baixo risco.

## 6) Ritos e governança
- **Daily de regressões** durante RC: 15 minutos.
- **War room** para severidade crítica até estabilização.
- **Post-mortem obrigatório** para qualquer waiver de Must-have em release final.
- **Review mensal de thresholds** para calibrar metas.

## 7) Evidências e artefatos obrigatórios por release
1. Relatório de benchmark com comparação ao baseline.
2. Checklist pré-release assinado (ver template).
3. Waivers aprovados (se houver), com validade e plano de correção.
4. Ata de decisão Go/No-Go.

## 8) Critérios de aceite deste playbook
- Processo de waiver **auditável e com expiração**.
- Donos por métrica/subsistema **definidos**.
- Checklist pré-release **utilizado em pelo menos 1 ciclo piloto**.
