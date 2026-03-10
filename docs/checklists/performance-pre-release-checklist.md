# Checklist pré-release de performance (com assinatura)

> Use este checklist em toda release candidate e release final.

## Dados da release
- **Release:**
- **Tipo:** RC | Final | Hotfix
- **Data da revisão:**
- **Release Manager:**

## A) Execução e qualidade dos dados
- [ ] Suíte de benchmark executada no ambiente padrão.
- [ ] Baseline (3 últimas releases estáveis) atualizado.
- [ ] Dados inconsistentes/re-run documentados.
- [ ] Relatório consolidado publicado e anexado.

## B) Validação de metas
- [ ] Todas as métricas Must-have atendidas **ou** cobertas por waiver aprovado.
- [ ] Métricas Target fora do esperado têm plano de ação registrado.
- [ ] Métricas Aspirational revisadas para roadmap.

## C) Waivers (se aplicável)
- [ ] Waiver possui ID único e status atualizado.
- [ ] Waiver contém data de expiração válida.
- [ ] Waiver possui owner, issue/PR e milestone de correção.
- [ ] Waiver aprovado por owner do subsistema + Release Manager.

## D) SLA e prontidão operacional
- [ ] Owners de subsistema confirmaram disponibilidade de resposta.
- [ ] Fluxo de incidente para regressão crítica comunicado.
- [ ] Canais de war room definidos para janela de release.
- [ ] Escalonamento e contatos de backup confirmados.

## E) Decisão final
- [ ] Go
- [ ] Conditional Go (com waiver)
- [ ] No-Go

**Justificativa da decisão:**

## F) Assinaturas
- **Owner Core Runtime:** Nome / assinatura / data
- **Owner Networking:** Nome / assinatura / data
- **Owner RPC/API:** Nome / assinatura / data
- **Owner UX Clients:** Nome / assinatura / data
- **Release Manager:** Nome / assinatura / data

---

## Registro de ciclo piloto (preenchido)

- **Release:** 4.1.0-rc1 (piloto)
- **Data da revisão:** 2026-03-10
- **Resultado:** Conditional Go
- **Resumo:** 1 desvio Must-have em latência RPC P95 coberto por waiver `PERF-WVR-2026-001`, com expiração em 2026-04-15 e plano de correção no milestone 4.1.0.
- **Assinaturas coletadas:** Owner RPC/API, Owner Core Runtime, Release Manager.

> Este registro comprova uso do checklist em pelo menos 1 ciclo de release piloto.
