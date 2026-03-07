# LEIAME (Português)

Este documento resume as principais informações para desenvolvimento e o fluxo da aplicação **Transmission**.

## Visão geral

O Transmission é um cliente BitTorrent livre com múltiplas interfaces:

- Aplicação nativa para macOS
- Interfaces gráficas em GTK e Qt para Linux/BSD
- Interface Qt compatível com Windows
- Daemon/headless para servidores e roteadores
- Interface Web para controle remoto

A ideia central do projeto é compartilhar o mesmo núcleo de torrent e expor experiências diferentes para cada plataforma.

## Fluxo da aplicação (alto nível)

De forma simplificada, o fluxo acontece assim:

1. **Entrada do usuário**
   - Pode vir da GUI (Qt/GTK/macOS), da Web UI ou da linha de comando (`transmission-remote`).
2. **Camada de controle**
   - As interfaces enviam comandos (adicionar torrent, pausar, remover, configurar limites etc.) para o núcleo, normalmente via RPC quando há daemon/web.
3. **Núcleo BitTorrent**
   - O núcleo gerencia sessão, pares, trackers, filas, verificação de peças, leitura/escrita de dados e políticas de upload/download.
4. **Persistência e estado**
   - Configurações e metadados são salvos para manter estado entre reinicializações.
5. **Saída/observabilidade**
   - Progresso, velocidade, status de pares e estatísticas retornam para as interfaces.

## Estrutura útil do repositório

- `libtransmission/`: núcleo e lógica principal do protocolo/engine.
- `daemon/`: serviço headless e endpoint RPC.
- `web/`: aplicação Web para controle remoto.
- `qt/`, `gtk/`, `macosx/`: interfaces gráficas por plataforma.
- `utils/`: ferramentas auxiliares (`transmission-remote`, `transmission-show`, `transmission-create`, `transmission-edit`).
- `docs/`: documentação técnica e guias.

## Ambiente de desenvolvimento

### Pré-requisitos

- Compilador C/C++ moderno
- CMake
- Dependências de sistema conforme plataforma (veja `docs/Building-Transmission.md`)

### Build rápido

```bash
cmake -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build
```

### Instalação local

```bash
cmake --install build
```

## Fluxo recomendado para contribuir

1. **Criar branch de trabalho**
   - Ex.: `git checkout -b feat/minha-melhoria`
2. **Implementar mudanças pequenas e focadas**
   - Evite misturar refatoração grande com correção funcional.
3. **Validar build e testes locais**
   - Rode build completo e testes aplicáveis antes do commit.
4. **Padronizar estilo**
   - Respeite `.clang-format` e regras JS (`web/package.json`); quando necessário, use `./code_style.sh`.
5. **Commit com mensagem clara**
   - Explique o “o quê” e o “por quê”.
6. **Abrir PR**
   - Inclua contexto, impacto, e como validar.

## Fluxo operacional comum (daemon + Web)

1. Subir `transmission-daemon`.
2. Abrir a Web UI.
3. Adicionar torrent/URL magnet.
4. Acompanhar progresso e ajustar limites/fila.
5. Concluir download e continuar semeando conforme política.

## Referências internas importantes

- README principal: `README.md`
- Guia de build: `docs/Building-Transmission.md`
- Protocolo RPC: `docs/rpc-spec.md`
- Uso sem GUI: `docs/Headless-Usage.md`
- Interface Web: `docs/Web-Interface.md`

---

Se você está começando, foque primeiro no fluxo `daemon + Web` e na leitura do guia de build. Depois, aprofunde na interface/plataforma que pretende alterar.
