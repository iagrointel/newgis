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
- nginx em `https://plat.iagrointel.com` com `X-Robots-Tag: noindex, nofollow` e
  `Strict-Transport-Security` em toda `location`, `/static/` servido do disco com `no-store`,
  redirecionamento de HTTP para HTTPS.
- Schema `plat` no banco `iagro_sat`: role `plat_app` (sem BYPASSRLS, sem posse), tabelas
  `versao_migracao`, `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS em toda tabela com
  `tenant_id` (USING e WITH CHECK); 9 funções `SECURITY DEFINER` para autenticação, sessão, token e log;
  inquilinos de demonstração `demo` e `demo2`.
- Migrações `001_fundacao` e `002_identidade`, aplicadas por `db/migrar.sh` com sha256 por arquivo,
  uma transação por arquivo e recusa (código 3) de arquivo aplicado que tenha mudado.
- `install.sh` idempotente (extensões, migrações, `.env` 600 com senha da role e `PLAT_GIT_SHA`, linha
  no `pg_hba.conf`, venv com `PYTHONNOUSERSITE=1` e prova de importação sem o diretório do usuário,
  administradores de demonstração com senha por stdin, unidade systemd, nginx com troca atômica
  preservando certbot, certbot na primeira vez, conferência pública de 200 + noindex + HSTS).
- `requirements.txt` com toda dependência da aplicação e da suíte fixada com `==` (`fastapi 0.138.0`,
  `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv 1.2.2`, `httpx 0.28.1`, ...); `uvicorn` e
  `psycopg2` do sistema, conferidos por nome de pacote dpkg.
- `make check`: ruff, varredura de marcador de pendência (inclui os `.md`), 81 testes rápidos (unit,
  instalador, dependências, vendor, contrato de `/saude`, `/api/docs`, banco, migrações, RLS, cabeçalhos
  HTTP reais) e 1 e2e playwright com captura; `make medidas` e `make vendor`.
- Front mínimo em módulos ES sem bundler; MapLibre GL JS 4.7.1 (ainda não carregado por nenhuma tela) e
  Swagger UI 5.32.15 (serve `/api/docs` sem CDN) em `web/vendor/`, versão no nome, sha256 e licença em
  `VERSOES.txt`; `favicon.svg`.
- Documentos: `docs/adr/0001-fundacao.md` (13 seções), `docs/openapi.json` gerado e comitado,
  `ARQUITETURA.md`, `MANUAL.md`, este arquivo, `README.md`; `docs/PARIDADE.md` só com cabeçalho (nenhuma
  capacidade de usuário para comparar ainda).

### Medições (`tests/medidas/L0-01-repo.json`, rodada 2 do testador sobre `8ffe950`, commit `3083366`; instalação e RLS da rodada 1)

| medida | valor | comando |
|---|---|---|
| instalação do zero (schema e role apagados) | 6,24 s | `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` (rodada 1) |
| reinstalação do zero pelo adversário sobre `8ffe950` | 9,66 s | `refutacao.json`, rodada 2, ataque 1 |
| instalação com `.env`, credenciais e linha do pg_hba também apagados | 9,14 s | idem; o script imprimiu `.env criado`, `linha acrescentada`, `tests/credenciais.txt criado` |
| instalação repetida em seguida | 4,69 s | idem; 0 migrações novas, 1 linha no pg_hba, NRestarts=0 |
| testes coletados / rápidos passando / e2e passando | 82 / 81 / 1 | `venv/bin/pytest --collect-only -q` (unit 31, api 50, e2e 1); `make check` |
| `make check` | rc=0, 2,86 s | `/usr/bin/time -f %e make check` |
| árvore suja depois de `make check` | 0 arquivos | `git status --short` |
| marcadores de pendência no código e nos documentos | 0 linhas | grep com a expressão do driver em `app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md` |
| nomes de cliente/parceiro no repositório | 0 linhas | `grep -rniE` com a lista do testador, fora de venv/.git/vendor |
| `/saude` pela URL pública | HTTP 200, `git_sha` = HEAD `8ffe950516f5`, 2 migrações, 0 pendentes | `curl -sSI` e `curl -sS https://plat.iagrointel.com/saude` |
| `X-Robots-Tag` com noindex | 11 de 11 rotas | `curl -sI` em API, estático, docs e 404 |
| `Strict-Transport-Security` | 11 de 11 rotas HTTPS; ausente no 301 de http | `curl -sI` |
| `/api/docs` sem URL externa; `make vendor` | 0 URLs; 4 arquivos OK | leitura do HTML; `sha256sum -c` |
| latência `/saude` pública, conexão nova (mediana / p95) | 19,8 / 21,0 ms | 20 × `curl -s -o /dev/null -w %{time_total}` |
| latência `/saude` pública, conexão reaproveitada (mediana / p95) | 1,9 / 2,8 ms | 20 URLs numa invocação de curl |
| memória do serviço (cgroup) | 88,5 MB | `systemctl show plat-api -p MemoryCurrent` |
| tabelas com `tenant_id` e RLS | 4 (mais `tenant` por `id`) | `pg_class × pg_attribute` |
| linhas visíveis a `plat_app` sem contexto | 0 | `psql` como `plat_app` sem `set_config` |
| página pronta / primeira pintura (chromium) | 62,6 / 48 ms | e2e `tests/e2e/test_saude_pagina.py` |

### Adversário (`laco/handoffs/T1/refutacao.json`): veredito final PASSA (rodada 2, HEAD `8ffe950`)

Rodada 1 (sobre `3b53c24`): PARCIAL. A refutação literal resistiu (apagar schema e role, reinstalar em
6,46 s, `/saude` 200 com noindex, 58 testes verdes), mas caíram: dependências `fastapi`, `starlette`,
`pydantic`, `python-dotenv` fora do `requirements.txt` (máquina nova não subia); senha de demonstração
em argumento de `sudo` (ficava no journal); documentos de topo vazios; sem `Strict-Transport-Security`;
Swagger de CDN externo; promessas do ADR sem código.

Rodada 2 (sobre `8ffe950`): PASSA. Reinstalação do zero em 9,66 s, 82 testes verdes, `/saude` 200 com
noindex e HSTS; os quatro achados reatacados e fechados com reprodução: aplicação importa e roda sem o
diretório do usuário (`PYTHONNOUSERSITE=1` na unidade viva); 0 senha no journal durante e depois da
reinstalação; ADR e código batem (`make medidas`, vendor com versão no nome, `PLAT_GIT_SHA` gravado,
`requirements.txt` completo, gravação em `log_acesso` adiada explicitamente ao L0-02); HSTS só no bloco
443 e `/api/docs` com 0 requisição externa em chromium real. Ressalvas que não derrubam o item: prova de
"máquina nova" por simulação; funções `SECURITY DEFINER` sem checagem de inquilino (regra para o L0-02);
caminhos do `install.sh` só lidos (`.env` inexistente, certbot emitindo, `nginx -t` reprovando).

### Commits

| sha | mensagem |
|---|---|
| `a1d0c20` | Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0) |
| `904a849` | Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes |
| `b22761e` | Medidas do item L0-01-repo regeneradas sobre o commit 904a849 |
| `ca61ea1` | Medidas do item L0-01-repo assinadas pelo testador (turno T1) |
| `3b53c24` | P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1 |
| `7092755` | Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0 |
| `8ffe950` | L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA |
| `3083366` | Medidas do item L0-01-repo, rodada 2 do testador sobre 8ffe950 |
| (este) | Documentação atualizada sobre 8ffe950 e 3083366 (passe curto do cronista) |
