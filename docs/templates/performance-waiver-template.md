# Template — Waiver de Performance por Release

## 1) Identificação
- **Waiver ID:** PERF-WVR-YYYY-###
- **Release alvo:**
- **Data de abertura:**
- **Data de expiração (obrigatória):**
- **Status:** Aberto | Aprovado | Expirado | Revogado | Fechado

## 2) Contexto da violação
- **Métrica impactada:**
- **Threshold violado (Must-have/Target):**
- **Valor medido:**
- **Baseline de comparação:**
- **Ambiente de medição:**
- **Evidências (links para relatório/log):**

## 3) Impacto e risco
- **Impacto no usuário final:**
- **Impacto operacional:**
- **Escopo afetado (subsistema/plataforma):**
- **Severidade:** Crítica | Alta | Média | Baixa

## 4) Justificativa para waiver
- **Motivo técnico para não bloquear release:**
- **Alternativas consideradas e por que foram descartadas:**
- **Mitigação temporária adotada:**

## 5) Plano de correção (obrigatório)
- **Owner de correção:**
- **Issue/PR vinculada:**
- **Milestone alvo:**
- **Data limite de correção:**
- **Critério objetivo de fechamento:**
- **Plano de validação pós-correção:**

## 6) Aprovações
- **Owner do subsistema:** Nome / assinatura / data
- **Release Manager:** Nome / assinatura / data
- **(Opcional) Engenharia de Qualidade:** Nome / assinatura / data

## 7) Auditoria e acompanhamento
- **Última atualização de status:**
- **Próxima revisão programada:**
- **Histórico de mudanças:**
  - Data — Autor — Alteração

---

## Regras de uso
1. Sem **data de expiração**, o waiver é inválido.
2. Waiver expirado sem correção concluída reverte release seguinte para **No-Go** até nova aprovação.
3. Renovação exige **novo documento** (novo ID) e nova justificativa.
4. Este waiver deve ficar versionado e vinculado à decisão de release.
