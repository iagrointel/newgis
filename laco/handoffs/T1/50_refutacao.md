# T1 · 50 — Refutação do item L0-01-repo (adversário independente)

Veredito: **PARCIAL**. A refutação literal resistiu duas vezes (a segunda sobre o HEAD final `3b53c24`).
Três falhas reais derrubam cláusulas do portão sem derrubar o mecanismo; detalhe em `refutacao.json`.

## Objetivo
Derrubar o item contra o portão de pronto e a instrução de refutação literal, sem ler os handoffs 20/21/30/40,
sem editar o repositório e deixando `plat-api` ativo. Ordem obedecida ao gerente: ataques não destrutivos
primeiro; refutação destrutiva só depois de `40_testes.md` existir (apareceu após 120 s de espera).

## O que fiz
1. Refutação literal, cronometrada, duas vezes (HEAD `ca61ea1` às 12:53 e HEAD `3b53c24` às 12:56):
   `DROP SCHEMA plat CASCADE; DROP OWNED BY plat_app; DROP ROLE plat_app` → `sudo bash install.sh plat.iagrointel.com 8150`
   → `/saude` por HTTPS → `pytest` completo (58, inclusive o e2e) → `make check`.
2. `make check` lido e rodado (`-rs`, `--durations=0`), com leitura de todos os testes.
3. Grep de placeholder com expressão mais larga que a do `Makefile`.
4. RLS como `plat_app`: SELECT/UPDATE/DELETE/INSERT cruzados em todas as tabelas com `tenant_id` e em `tenant`;
   funções SECURITY DEFINER chamadas fora do inquilino; ACLs, BYPASSRLS, posse, membership. Tudo em transação com rollback
   (conferido: nenhum resíduo).
5. Cabeçalhos e travessia em `/`, `/saude`, `/api/docs`, `/api/openapi.json`, estáticos, `/static/../.env` e variantes,
   IP direto com SNI, http→https; `git grep` de segredos; segredos reais no histórico; `.gitignore`; permissões.
6. Leitura do `install.sh` (idempotência, senha em log, estado assumido) + journal do `sudo` + origem real dos módulos Python.
7. `/saude` contra `git rev-parse HEAD` e `plat.versao_migracao`.
8. ADR contra o código. 9. Nomes de cliente/parceiro após o commit `3b53c24`.

## Evidência literal (resumo; comandos e saídas completas no `refutacao.json`)
- Refutação: `rc_drop=0` (17 objetos) · `/saude` com schema apagado = **503** · `rc_install=0` em **6,46 s** e **6,33 s** ·
  pg_hba continua com **1** linha `plat_app` · `sites-enabled/plat.iagrointel.com` idêntico (diff vazio) ·
  `https://plat.iagrointel.com/saude` → **200**, `X-Robots-Tag: noindex, nofollow`, `git_sha` = HEAD ·
  **58 passed** · `make check` verde · `plat-api` active, `NRestarts=0`, 95 MB.
- `make check`: 2,70 s; 57 + 1 e2e; 0 skip; captura do playwright regravada (43 KB). Nenhum teste vazio.
- Placeholder: 0 em `app/ db/ web/ install.sh Makefile docs/`. Mas `ARQUITETURA.md` (3 linhas), `MANUAL.md` (3),
  `CHANGELOG.md` (2) e `docs/PARIDADE.md` (4) são cascas: "(escrita pelo laço a partir do item L0-01)".
- RLS: 15/15 operações cruzadas em tabela bloqueadas (0 linhas ou "new row violates row-level security policy");
  `log_acesso` UPDATE/DELETE = permission denied; `rolbypassrls=f`, tabelas todas de `postgres`.
  **Funções SECURITY DEFINER não checam inquilino**: no contexto do tenant 1, `plat.auth_sessao_criar(2, ...)` devolveu
  token válido que `plat.auth_sessao` resolve para `demo2/admin`; `plat.auth_falha(2,1,60)` bloqueou o admin do outro
  inquilino; `plat.auth_login('demo2','admin')` entrega `senha_hash` de outro inquilino; `plat.tenant_criar` aceita
  GUC `plat.usuario_id` forjado pelo cliente. Todas com EXECUTE para PUBLIC (hoje inalcançável só porque PUBLIC não tem USAGE no schema).
- Senha em log: passo g do `install.sh` passa a senha de demonstração como argv de `sudo -u dev venv/bin/python -c ...`;
  o `sudo` registra `COMMAND=... gerar_hash(sys.argv[1])) <senha em claro>` no journal (18 linhas hoje; 3 por senha atual).
  Viola a seção 8 do próprio ADR ("segredo nunca em argumento de linha de comando"). A senha do banco NÃO vazou (0 no journal e no log do Postgres).
- Máquina nova: `fastapi 0.138.0`, `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv 1.2.2` vêm de
  `/home/dev/.local/lib/python3.12/site-packages` (pip --user do dev); não estão no dpkg nem no `requirements.txt`
  (que só lista pytest/playwright/ruff). `PYTHONNOUSERSITE=1 venv/bin/python -c 'import app.main'` →
  `ModuleNotFoundError: No module named 'fastapi'`. Em máquina ou usuário novo o `plat-api` não sobe.
- Segurança no ar: noindex/nosniff/no-store em toda rota; DENY e X-Req-Id na API; travessia 404; http→301;
  OpenAPI expõe só `/saude` e `/api/versao`; segredos fora do git (0 ocorrências no `git log -p`); `.env` e
  `tests/credenciais.txt` ignorados e 600. Faltas: sem `Strict-Transport-Security`; `/api/docs` carrega Swagger UI de CDN
  (contradiz a seção 11.4 do ADR sobre rede fechada).
- `/saude` não mente: `git_sha` = HEAD nas três leituras; migrações 2 = `count(*)` 2. Limite: lido uma vez na partida.
- ADR promete e o código não faz: alvo `medidas` no Makefile; middleware gravando `plat.log_acesso`; `install.sh` gravando
  `PLAT_GIT_SHA`; "fastapi vem do sistema"; `web/vendor/<nome>-<versão>.js`; regra de segredo em argv.
- Nomes de cliente: 0 em código/testes/web/deploy/README; **1 linha residual** em `docs/adr/0001-fundacao.md:293` ("fgrsig").

## Riscos
1. **Isolamento por inquilino nas funções `auth_*` depende só da API passar o `usuario_id` certo.** Qualquer bug de rota
   no L0-02 vira sessão cruzada; sugestão para o L0-02: as funções que recebem `p_usuario` exigirem
   `plat.tenant_atual()` quando houver contexto, ou REVOKE de PUBLIC + teste adversarial por rota.
2. `install.sh` faz `mv` do bloco novo para `sites-enabled` ANTES de `nginx -t`: se o `-t` falhar, `set -e` sai e deixa o
   arquivo quebrado no lugar (não reproduzido; leitura).
3. Estado assumido sem checagem: PG 16 em `/etc/postgresql/16`, certbot, nginx, openssl; `--register-unsafely-without-email`.
4. `make check` fica verde com skip se o nome público não resolver (e2e e cabeçalhos pulam), o que esconde falha de HTTPS em outra máquina.
5. Journal legível por root e grupos `systemd-journal`/`adm` contém as senhas de demonstração; trocar as senhas depois de corrigir o passo g.

## Pendências (para fechar o item)
- `requirements.txt` com fastapi/starlette/pydantic/python-dotenv fixados, ou instalação no sistema pelo `install.sh`; provar com `PYTHONNOUSERSITE=1`.
- Passo g: senha por stdin (`sys.stdin.read()`), nunca argv; depois trocar as senhas semeadas e, se quiser, `journalctl --vacuum`.
- ARQUITETURA/MANUAL/CHANGELOG/PARIDADE com conteúdo (cronista) e o alvo `sem-marcador` varrendo os `.md` da raiz.
- ADR: corrigir as 6 promessas ou o código; remover `fgrsig` da linha 293.
- HSTS e Swagger UI local (ou desligar `/api/docs` em produção).

## Para o próximo papel (gerente)
O mecanismo do item existe e sobrevive à refutação literal nesta máquina: instalador idempotente, migrações com sha,
role sem BYPASSRLS, RLS que segura em toda tabela, URL interna noindex e suíte que testa código real. O que impede
"PASSA" é a cláusula "máquina que nunca viu o repo" (dependências em `~/.local`), a senha em claro no journal por regra
quebrada do próprio ADR, e os quatro documentos-casca. Nenhum desses exige redesenho; os dois primeiros são correções
de 10 linhas no `install.sh`/`requirements.txt`, testáveis pelo mesmo roteiro (`scratchpad/refutacao_destrutiva.sh`).
`plat-api` ficou ativo (`NRestarts=0`).

---

# Rodada 2 (HEAD `8ffe950`, 13:11) — veredito final: **PASSA**

## Objetivo
Repetir a refutação literal sobre as correções do backend e reatacar os quatro achados da rodada 1. Handoff
`32_backend_correcao.md` lido só depois dos ataques; o diff `3b53c24..8ffe950` foi lido antes (é código, não raciocínio).

## O que fiz
`scratchpad/refutacao_r2.sh`: journal antes → DROP SCHEMA/DROP OWNED/DROP ROLE → `install.sh` cronometrado → journal
depois → pg_hba/nginx → HSTS por bloco no arquivo vivo → cabeçalhos em 4 rotas + `:80` → `/api/docs` (HTML e recursos) →
unidade viva (`Environment`, `/proc/<pid>/environ`, `maps` do worker) → import com `PYTHONNOUSERSITE=1` → `/saude` × HEAD ×
`.env` → pytest completo → `make check`. Depois: ADR × código, nomes de parceiro, `make vendor`, `make sem-marcador` nos
`.md`, leitura dos 24 testes novos, e chromium real em `/api/docs` listando toda requisição.

## Evidência literal (resumo; completa no `refutacao.json`, chave `evidencia` da rodada 2)
- Refutação: `rc_install=0` em **9,66 s**; `/saude` → 200, `X-Robots-Tag: noindex, nofollow`, `Strict-Transport-Security:
  max-age=31536000`, `git_sha 8ffe950516f5` = HEAD; **82 passed** (81 + 1 e2e); `make check` verde; pg_hba 1 linha;
  nginx idêntico, sem cópia residual; `plat-api` active, `NRestarts=0`, 90 MB.
- Achado 1 (dependências): `PYTHONNOUSERSITE=1 ./venv/bin/python -c 'import app.main, fastapi, ...'` → fastapi e dotenv
  em `venv/lib/python3.12/site-packages`; unidade viva `Environment=PYTHONNOUSERSITE=1`; `/proc/<MainPID>/environ` tem a
  variável; `/proc/<worker>/maps` sem `/home/dev/.local`; `install.sh` confere dpkg e aborta se `app.main` não importar.
- Achado 2 (senha no journal): 0 ocorrências de cada senha de `tests/credenciais.txt` antes e depois; o `COMMAND=` do sudo
  agora termina em `gerar_hash(sys.stdin.read())`, sem segredo; senha do banco 0 no journal e no log do Postgres.
- Achado 3 (ADR × código): `make medidas` e `make vendor` existem (sha 4/4 OK); `PLAT_GIT_SHA` gravado no `.env` = HEAD;
  vendor `maplibre-gl-4.7.1.*`, `swagger-ui-*-5.32.15.*`; nomes de parceiro fora de vendor = **0** (a única ocorrência é
  `cbre` numa lista de TLDs no bundle minificado do Swagger); `log_acesso` adiado ao L0-02 por decisão explícita no ADR.
- Achado 4 (HSTS e docs): 3 `add_header` HSTS todos no bloco `listen 443`; `:80` → 301 sem HSTS; chromium real em
  `/api/docs`: 4 pedidos, **0 externo**, 0 erro de console, 2 operações renderizadas.
- `make sem-marcador` inclui `*.md`; grep largo do adversário = 0; ARQUITETURA 475 / MANUAL 157 / CHANGELOG 82 linhas.

## Riscos que ficam (não derrubam o item)
1. Funções `auth_*` SECURITY DEFINER sem checagem de inquilino (rodada 1, ataque 4; migrações inalteradas) — tratar no L0-02.
2. "Máquina nova" provada por simulação (`PYTHONNOUSERSITE=1`), não em segunda máquina; caminhos `.env` inexistente,
   certbot e `nginx -t` reprovando não exercitados.
3. `tests/medidas/L0-01-repo.json` está modificado e não comitado (gerado 13:10:39 pelo testador) — comitar ou descartar.
4. `docs/PARIDADE.md` continua tabela vazia (coerente: nenhuma capacidade Esri entregue; fora do portão deste item).

## Para o próximo papel (gerente)
Portão cláusula a cláusula: 10/10 passam. A refutação literal resistiu três vezes no dia (12:53, 12:56, 13:11) e os quatro
achados fecharam com reprodução, não com promessa. Falta só decidir a árvore suja do `tests/medidas` antes do commit do turno.
`plat-api` ativo.
