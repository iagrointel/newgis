# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json`, com o
comando que os gerou.

## 0.1.0 — turno 1, setembro de 2026 (item L0-01-repo: fundação)

Primeira versão. O repositório instala, sobe um serviço, responde saúde por HTTPS e isola inquilinos no
banco. Não há login, catálogo, camada nem mapa.

### O que entrou

- API FastAPI `plat-api` em 127.0.0.1:8150 (2 workers uvicorn, `MemoryMax=1G`), com `GET/HEAD /saude`
  (200 só com banco atualizado; 503 em `desatualizado`/`erro`), `GET/HEAD /api/versao`, página inicial
  `/` e `/api/docs`.
- nginx em `https://plat.iagrointel.com` com `X-Robots-Tag: noindex, nofollow` em toda `location`,
  `/static/` servido do disco com `no-store`, redirecionamento de HTTP para HTTPS.
- Schema `plat` no banco `iagro_sat`: role `plat_app` (sem BYPASSRLS, sem posse), tabelas
  `versao_migracao`, `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS em toda tabela com
  `tenant_id` (USING e WITH CHECK); 9 funções `SECURITY DEFINER` para autenticação, sessão, token e log;
  inquilinos de demonstração `demo` e `demo2`.
- Migrações `001_fundacao` e `002_identidade`, aplicadas por `db/migrar.sh` com sha256 por arquivo,
  uma transação por arquivo e recusa (código 3) de arquivo aplicado que tenha mudado.
- `install.sh` idempotente (extensões, migrações, `.env` 600, senha da role, linha no `pg_hba.conf`,
  venv, administradores de demonstração, unidade systemd, nginx preservando certbot, certbot na primeira
  vez, conferência pública de 200 + noindex).
- `make check`: ruff, varredura de marcador de pendência, 57 testes rápidos (unit, contrato de
  `/saude`, banco, migrações, RLS, cabeçalhos HTTP reais) e 1 e2e playwright com captura.
- Front mínimo em módulos ES sem bundler; MapLibre GL JS 4.7.1 em `web/vendor/` com sha256 e licença
  em `VERSOES.txt` (ainda não carregado por nenhuma tela).
- Documentos: `docs/adr/0001-fundacao.md` (13 seções), `docs/openapi.json` gerado e comitado,
  `ARQUITETURA.md`, `MANUAL.md`, este arquivo, `README.md`; `docs/PARIDADE.md` só com cabeçalho (nenhuma
  capacidade de usuário para comparar ainda).

### Medições (`tests/medidas/L0-01-repo.json`, assinado pelo testador em `ca61ea1`)

| medida | valor | comando |
|---|---|---|
| instalação do zero (schema e role apagados) | 6,24 s | `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` |
| instalação com `.env`, credenciais e linha do pg_hba também apagados | 9,14 s | idem; o script imprimiu `.env criado`, `linha acrescentada`, `tests/credenciais.txt criado` |
| instalação repetida em seguida | 4,69 s | idem; 0 migrações novas, 1 linha no pg_hba, NRestarts=0 |
| testes coletados / rápidos passando / e2e passando | 58 / 57 / 1 | `venv/bin/pytest --collect-only -q`; `make check` |
| `make check` | rc=0, 2,72 s | `/usr/bin/time -f %e make check`, 3 rodadas |
| marcadores de pendência no código entregue | 0 linhas | grep com a expressão do driver do laço |
| `/saude` pela URL pública | HTTP 200, `git_sha` = HEAD, 2 migrações, 0 pendentes | `curl -sSI` e `curl -sS https://plat.iagrointel.com/saude` |
| `X-Robots-Tag` com noindex | 11 de 11 rotas | `curl -sI` em API, estático, docs e 404 |
| latência `/saude` pública, conexão nova (mediana / p95) | 19,9 / 22,4 ms | 20 × `curl -s -o /dev/null -w %{time_total}` |
| latência `/saude` pública, conexão reaproveitada (mediana / p95) | 1,7 / 2,7 ms | 20 URLs numa invocação de curl |
| memória do serviço (cgroup) | 90,0 MB | `systemctl show plat-api -p MemoryCurrent` |
| tabelas com `tenant_id` e RLS | 4 (mais `tenant` por `id`) | `pg_class × pg_attribute` |
| linhas visíveis a `plat_app` sem contexto | 0 | `psql` como `plat_app` sem `set_config` |
| página pronta / primeira pintura (chromium) | 50,9 / 36 ms | e2e `tests/e2e/test_saude_pagina.py` |

### Adversário (`laco/handoffs/T1/refutacao.json`): veredito PARCIAL

A refutação literal resistiu (apagar schema e role, reinstalar em 6,46 s, `/saude` 200 com noindex,
58 testes verdes). Cláusulas derrubadas e registradas como pendência: dependências `fastapi`,
`starlette`, `pydantic`, `python-dotenv` fora do `requirements.txt` (máquina nova não sobe); senha de
demonstração em argumento de `sudo` (fica no journal); documentos de topo vazios no momento do teste
(resolvido nesta entrada). Achados menores: sem `Strict-Transport-Security`; Swagger de CDN externo;
funções `SECURITY DEFINER` obedecem a qualquer `usuario_id` (regra para o L0-02).

### Correções pós-refutação em curso (árvore de trabalho em 05/09/2026 13:05 UTC, commit pendente)

Vistas na árvore de trabalho, com `make check` verde sobre elas, ainda sem commit no momento desta
entrada; entram no histórico quando o gerente as comitar (ver `ARQUITETURA.md` seção 12):
`requirements.txt` com `fastapi`, `starlette`, `pydantic`, `python-dotenv`, `httpx` fixados e
`PYTHONNOUSERSITE=1` no Makefile, na unidade e no `install.sh`; `PLAT_GIT_SHA` gravado no `.env`;
senha de demonstração por stdin; troca atômica do bloco nginx com `Strict-Transport-Security`;
Swagger servido de `web/vendor/` (5.32.15, Apache-2.0); bibliotecas de `vendor/` com versão no nome;
alvos `make medidas` e `make vendor`; varredura de marcador estendida aos `.md` da raiz.

### Commits

| sha | mensagem |
|---|---|
| `a1d0c20` | Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0) |
| `904a849` | Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes |
| `b22761e` | Medidas do item L0-01-repo regeneradas sobre o commit 904a849 |
| `ca61ea1` | Medidas do item L0-01-repo assinadas pelo testador (turno T1) |
| `3b53c24` | P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1 |
| (este) | Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG, README |
