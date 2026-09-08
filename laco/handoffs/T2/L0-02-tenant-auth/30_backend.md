# T2 · L0-02-tenant-auth · 30_backend — backend (trilha A)

## Objetivo

Construir no repositório `/home/dev/plataforma/enterprise` o que o ADR 0002 fixa para identidade e acesso: migração
003 idempotente, módulos `app/auth/*`, `app/erros.py`, `app/paginas.py`, `app/limites.py`, middleware de
`plat.log_acesso`, 54 rotas com OpenAPI, instalador, e testes que cobrem cada cláusula do portão (varredura cruzada
A→B gerada do OpenAPI, força bruta de senha/TOTP/IP, token revogado/escopo/restrição, funções `SECURITY DEFINER` por
psql, middleware, limiares), com uma única reinstalação e conferência por `curl` na URL pública.

## O que fiz

1. **Migração `db/migracoes/003_identidade_acesso.sql`** (ADR seção 12, 12.1–12.10 + funções + permissões).
   Idempotente; aplicada 3 vezes durante a construção (apagando a linha de `versao_migracao`, porque o arquivo ainda
   não tinha sido comitado) sem erro. Diferenças em relação ao texto do ADR, cada uma com motivo:
   - `grupo_membro.tenant_id` (denormalizado): a política de `grupo` consulta `grupo_membro` e a de `grupo_membro` não
     pode consultar `grupo` de volta (recursão infinita de política no PostgreSQL); gatilho
     `tg_grupo_membro_coerente` garante que membro e grupo são do mesmo inquilino.
   - Partições de `log_acesso` e `evento` nascem com `REVOKE ALL FROM plat_app`, RLS ligada e política própria (a
     prova empírica está na evidência: via pai vale a política do pai; partição sem GRANT é inacessível direto).
   - `token_servico.renovado_por` (coluna nova; o ADR 8.1 exige a rotação registrar o sucessor).
   - `plat.tenant_publico(slug)` (pré-contexto) para `GET /api/login/provedores`; `plat.contexto_confere(usuario)`
     (a checagem "contexto = inquilino do usuário" reusada pelas funções com contexto obrigatório);
     `plat.plataforma_operador(hash)` (superadmin sempre pela sessão, nunca por GUC).
   - `auth_sessao(p_hash, p_ociosa_horas numeric)`: numérico para admitir o ocioso de segundos do teste em dev;
     `config.auth.sessao_ociosa_horas` do inquilino, quando existe, prevalece (cortado a 1–24 h). Bug pego no teste:
     `greatest(NULL, 1)` devolve 1 no PostgreSQL (ignora NULL) e virava 1 h para todo inquilino sem a chave; trocado
     por `CASE`.
   - `log_registrar` e `evento_registrar` são plpgsql e, se o INSERT cair fora das partições, chamam
     `*_particao_garantir(now())` e repetem uma vez (o log nunca derruba a resposta).
   - Administrativos: a tabela da seção 3.2 tem **20** privilégios marcados `sim` (o rodapé do ADR diz 18); a
     migração e `app/auth/privilegios.py` seguem a tabela linha a linha; `test_vocabulario_python_igual_ao_banco`
     fixa 20.
   - `evento_tipo` com 3 tipos além do vocabulário: `grupos/recusar`, `usuarios/2fa_codigos`,
     `inquilinos/leitura_superadmin` (a trilha do X-Plat-Inquilino exigida pelo L0-07-f).
   - `usuario.superadmin` é zerado fora de `plataforma` ANTES de o gatilho passar a valer (o admin de `demo` tinha
     `superadmin = true` da 002/install antigo).
   - Ramo da guarda de `log_acesso`: `relkind = 'r'` e `count(*) = 0` → DROP + CREATE particionada (0 linhas
     medidas às 13:45 UTC; a suíte ainda não tinha gravado nada).
2. **`app/erros.py`** (`ErroAPI`, handlers para `starlette.exceptions.HTTPException` — o roteador levanta a do
   Starlette no 404/405, a do FastAPI é subclasse — e `RequestValidationError`), **`app/limites.py`** (seção
   `# --- identidade (L0-02)`; a trilha B acrescenta a dela abaixo), **`app/paginas.py`** (7 páginas: as 6 do ADR +
   `/admin/papeis`, pedido do frontend; arquivo ausente = 404, nunca casca).
3. **`app/auth/`**: `politica.py` (faixas, corte com aviso, 12 senhas inválidas nomeadas, `HASH_FANTASMA`,
   `validar_config_auth` para o L0-07-a), `totp.py` (vetor RFC 6238 T=59 → 287082, janela ±1, anti-replay, AES-GCM
   `enc:v1:`, 8 códigos de recuperação, QR SVG por `qrcode==8.2`), `redigir.py`, `escopos.py`, `privilegios.py`
   (46 nomes, `perfil_minimo()`), `sessao.py` (`Auth`, `autenticado()`: cookie OU Bearer, CSRF por Origin + JSON,
   pendências, escopo, `X-Plat-Inquilino`, superadmin = 404), `comum.py`, `middleware.py` (X-Req-Id, linha JSON
   redigida, `plat.log_acesso` com bytes contados no `body_iterator`, gravado em `run_in_threadpool` depois do
   último byte), `modelos.py` (pydantic de entrada e `response_model` de saída), e as 7 famílias de rotas
   (`rotas_login`, `rotas_eu`, `rotas_usuarios` com privilégios e papéis, `rotas_grupos`, `rotas_tokens`,
   `rotas_log`, `rotas_plataforma`). `app/main.py` monta tudo pela lista `ROUTERS` (o router da trilha B já está
   nela, a pedido do gerente). `app/db.py` ganhou `somente_leitura` (`SET LOCAL transaction_read_only = on`).
4. **Instalador**: passo f confere `python3-cryptography`; passo g semeia `plataforma/admin` (superadmin) e
   `demo`/`demo2` sem superadmin, reseta 2FA/`trocar_senha`/bloqueio dos semeados e apaga
   `tests/credenciais_totp.txt`; garante partições do mês e dos 3 seguintes; escreve
   `/etc/nginx/conf.d/plat_limites.conf` (zona `plat_login` 10 r/min) e o modelo `deploy/nginx.conf` ganhou
   `location = /api/login` e `= /api/login/2fa` com `limit_req burst=10 nodelay; limit_req_status 429`.
5. **Testes**: 5 arquivos em `tests/unit` (política, TOTP, redação, escopos, erros) e 17 em `tests/api`
   (`conftest.py` com sessões A/B/superadmin e usuários temporários; `cruzado_casos.py` + `test_cruzado.py`;
   `eventos_esperados.py` + `test_eventos.py`; `test_login`, `test_sessao`, `test_eu`, `test_tokens`,
   `test_usuarios`, `test_grupos`, `test_log_consulta`, `test_log_acesso`, `test_plataforma`, `test_paginas`,
   `test_funcoes_seguras`, `test_privilegios_declarados`). `test_instalador.py` ganhou 2 testes e a contagem de
   `location` passou a 4. `docs/openapi.json` regerado da aplicação completa (54 caminhos, 73 rotas).
6. **Commits** (por caminho, nunca `-A`; `main.py` inteiro com a linha `rotas_jobs` da trilha B, a pedido do
   gerente): `9be4a04` (migração + base), `2ffe8b4` (sessão, rotas, main, openapi), `b5c336b` (instalador, nginx),
   `ae6ec45` (testes do portão).
7. **Reinstalação única**: `sudo bash install.sh plat.iagrointel.com 8150` de **15:40:26 a 15:40:34 UTC**
   (8 s; `plat-api` e `plat-worker` ativos; `/saude` 200 com `noindex` e HSTS). Conferência por `curl` abaixo.

## Evidência (comando + saída literal)

Prova empírica que decidiu a forma das partições (psql como postgres, transação revertida):

```
 via pai (politica do pai, sem grant na particao) |     1
ERROR:  permission denied for table p_a                       <- SELECT direto na partição sem GRANT
 via pai, particao com RLS propria tenant2 e sem grant |     1  <- via pai vale a política do PAI
```

Migração aplicada e funções sem PUBLIC (consulta correta: entrada de ACL que começa por `=`; a do ADR, `LIKE
'%=X/%'`, casa também `plat_app=X/` e conta 54):

```
$ bash db/migrar.sh
aplicada   003_identidade_acesso (7964 ms)
migracoes: aplicadas 1 · reaplicadas 0 · iguais 3 · pendentes 0
$ sudo -u postgres psql -d iagro_sat -tAc "SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM unnest(proacl) a WHERE a::text LIKE '=%')) AS com_public, count(*) AS total FROM pg_proc WHERE pronamespace='plat'::regnamespace"
0|54
auth_login|{postgres=X/postgres,plat_app=X/postgres}
```

Chamadas cruzadas por psql como `plat_app` (contexto de `demo`, usuário de `demo2`):

```
1 auth_sessao_criar cruzada  -> ERROR:  contexto_de_outro_inquilino
2 auth_falha cruzada         -> ERROR:  contexto_de_outro_inquilino
3 auth_ok cruzada            -> ERROR:  contexto_de_outro_inquilino
4 tenant_criar por GUC forjado (set_config plat.usuario_id=1 + hash inválido) -> ERROR:  so_superadmin
5 evento_registrar sem contexto -> ERROR:  evento_sem_contexto
6 insert direto em evento    -> ERROR:  permission denied for table evento
7 insert em privilegio       -> ERROR:  permission denied for table privilegio
8 log_registrar contexto divergente -> ERROR:  contexto_de_outro_inquilino
```

Tabelas e partições (`relname|relrowsecurity|relkind`): `evento|t|p`, `evento_y2026m09..12|t|r`, `grupo|t|r`,
`grupo_membro|t|r`, `log_acesso|t|p`, `log_acesso_y2026m09..12|t|r`, `papel_personalizado|t|r`,
`papel_privilegio|t|r`, `senha_historico|t|r`; `privilegio|f|r`, `perfil_privilegio|f|r`, `evento_tipo|f|r`
(vocabulário sem `tenant_id`, só leitura para `plat_app`).

Suíte (árvore de trabalho compartilhada; `make lint` reprova em `app/jobs/worker.py` e
`tests/api/jobs/test_jobs_transicoes.py`, da trilha B; os meus caminhos: `ruff check ... && echo "meus: limpos"` →
`meus: limpos`; `make sem-marcador` reprova em `docs/adr/0005-ingestao-vetorial.md`, arquivo não comitado de outra
trilha, linha 634 com a palavra da expressão):

```
$ make teste   (15:42–15:44 UTC)
25 failed, 384 passed, 21 deselected, 4 warnings in 118.63s
FAILED tests/api/test_cruzado.py::test_cobertura_100_por_cento                     \
FAILED tests/api/test_cruzado.py::test_rota_nao_cruza[...17 rotas /api/jobs e /api/agendas...]  | 20 = rotas da trilha B sem
FAILED tests/api/test_eventos.py::test_toda_rota_de_escrita_tem_evento_declarado   | caso/declaração (ver Pendências 1)
FAILED tests/api/test_privilegios_declarados.py::test_toda_rota_declara_auth_e_privilegio /
FAILED tests/api/jobs/test_jobs_transicoes.py::... (2, trilha B)
FAILED tests/api/test_saude.py::test_saude_200_com_json_do_contrato (espera ultima_migracao = 004_jobs; a 006 da B foi aplicada às 15:44:38)
FAILED tests/api/test_funcoes_seguras.py::test_nenhuma_funcao_com_execute_para_public (transitório: a 006 da B entrou
       durante a rodada; consulta repetida às 15:5x: 0 funções com PUBLIC de 57 -> o teste passa no estado atual)
$ PLAT_OPENAPI_ARQUIVO=<cópia só com os routers da trilha A> pytest tests/api -m "not lento" --ignore=tests/api/jobs
(rodada anterior aos commits, 15:37 UTC) 1 failed -> corrigido (contagem de falhas do 2FA) -> 0 failed
```

`curl` na URL pública depois da reinstalação (senha por arquivo 600, nunca em argv):

```
== /saude                 ok 5 006_jobs_transicoes ae6ec458dfff
== provedores             {"inquilino":{"slug":"demo","nome":"Inquilino de demonstração"},"provedores":[],"login_local":true}
== login                  HTTP 200 · ok True login admin perfil admin privilegios 46 pendencias []  · cookies no jar: 1
== /api/eu com cookie     demo {'criado_em': '2026-09-05T15:41:50Z', 'expira_em': '2026-09-12T15:41:50Z', 'ociosa_ate': '2026-09-06T03:41:50Z', 'ip': '216.238.123.14'}
== /api/eu sem cookie     HTTP 401
== /api/usuarios (cookie) total 1
== /api/log (cookie)      total 13794 [('GET', '/api/usuarios?limite=2', 200, 379, '216.238.123.14'), ('GET', '/api/eu', 200, 1729, '216.238.123.14')]
== páginas                /entrar /conta /admin/usuarios /admin/grupos /admin/papeis /admin/tokens /admin/log -> 200 text/html
== POST /api/login (HEAD) HTTP/1.1 422 · x-req-id · Strict-Transport-Security: max-age=31536000 · X-Robots-Tag: noindex, nofollow
== logout                 HTTP 204 · eu depois: HTTP 401
== 25 POST /api/login em usuário inexistente (limite por IP do nginx)
401 401 401 401 401 401 401 401 401 429 429 429 429 429 429 429 429 429 429 429 429 429 429 429 429
```

SIG de teste interno (banco compartilhado): `cd /home/dev/fgr/sig && bash pipeline/testar.sh` → `9 passed in 43.69s`.

Instalação: `== instalado em 8 s: https://plat.iagrointel.com (serviços plat-api :8150 e plat-worker :8153)`.

## Riscos

1. **Árvore de trabalho compartilhada por três agentes.** Durante a construção o `docs/openapi.json` foi regravado
   pela trilha B entre uma rodada e outra, `app/main.py` ganhou 3 linhas dela e a 006 entrou no banco no meio de
   uma rodada. Os testes que leem o OpenAPI aceitam `PLAT_OPENAPI_ARQUIVO` (cópia alternativa) só para verificar a
   trilha A de forma determinística; o padrão continua `docs/openapi.json` e é o que o portão usa.
2. **20 testes vermelhos em HEAD até a trilha B declarar as rotas dela** (Pendências 1). Não afrouxei: o ADR 16.1
   diz "rota sem caso = teste falha" e o D20 quer isso para todo item futuro.
3. **Anti-replay do TOTP contra a própria suíte**: duas rodadas no mesmo passo de 30 s reusam o código do superadmin;
   `entrar()` no `conftest` espera a fronteira do passo e refaz uma vez. Cada instalação reseta o 2FA do admin
   semeado e apaga `tests/credenciais_totp.txt` (modo 600, no `.gitignore`); a suíte liga de novo e guarda o segredo.
4. Teste de tempo constante e de força bruta usam usuários temporários; a primeira versão bloqueou o admin de
   `demo2` (5 senhas erradas) e o bloqueio foi limpo à mão no banco durante a construção.
5. `install.sh` aplica também migrações não comitadas presentes na árvore (a 006 da B entrou na minha reinstalação).
6. `qrcode==8.2` foi instalado na venv com `pip install` antes de o `install.sh` rodar (o instalador o reinstala do
   `requirements.txt`; a linha está comitada).

## Pendências

1. **Trilha B (17 rotas `/api/jobs*`, `/api/agendas*`)**: `openapi_extra={"x-auth": ..., "x-privilegio": ...}` em
   cada rota (ADR 3.4), entrada para as 8 rotas de escrita em `tests/api/eventos_esperados.py` (lista vazia com
   motivo é admitida) e um caso por rota em `tests/api/cruzado_casos.py` (recurso criado em B, URL para A). Sem isso
   `test_cobertura_100_por_cento`, 17 `test_rota_nao_cruza`, `test_toda_rota_de_escrita_tem_evento_declarado` e
   `test_toda_rota_declara_auth_e_privilegio` ficam vermelhos.
2. Trilha B: `test_saude` cita `004_jobs` como última migração; `ruff` em `app/jobs/worker.py` e
   `tests/api/jobs/test_jobs_transicoes.py`; `docs/adr/0005-ingestao-vetorial.md` (outra trilha) reprova em
   `sem-marcador` (linha 634).
3. Testador: `make medidas` regrava `tests/medidas/L0-02-tenant-auth.json` (as medidas deste handoff estão na seção
   abaixo); reinstalar do zero (`DROP SCHEMA plat CASCADE; DROP OWNED BY plat_app; DROP ROLE plat_app` →
   `install.sh`) e repetir a lista da seção 16 do ADR.
4. Cronista: `docs/PARIDADE.md` recebe a seção 17 do ADR só depois do testador.
5. L0-05-d: registrar como periódicos `plat.sessoes_expurgar()`, `plat.log_particao_garantir(mês seguinte)`,
   `plat.evento_particao_garantir(mês seguinte)`, `plat.log_expurgar(12)`, `plat.evento_expurgar(12)`.

## Para o próximo papel (testador, 40)

Rodar `make check` inteiro na árvore comitada; reinstalar do zero; repetir a seção 16 do ADR; medir e gravar. O que
mudou em relação ao ADR e o frontend/testador precisam saber (nenhuma rota, método ou código de erro do ADR foi
removido; tudo abaixo é acréscimo ou precisão):

| rota / campo | o que difere do texto do ADR |
|---|---|
| todo `usuario` (`/api/eu`, `/api/usuarios*`, login) | `papel` vem sempre (`null` quando não há); campo que a rota não pôs no objeto não aparece (`response_model_exclude_unset`): sob cookie há `sessao` e não há `token`; para `membros.ver` só os campos V; **`codigos_recuperacao_restantes`** é campo novo (int) |
| `/api/eu` → `inquilino.config_publica` | traz `centro`, `zoom`, `basemap`, `srid_padrao`, `cor`, `logo` do `config` e **`auth`** = `{senha_min, senha_maiuscula, senha_minuscula, senha_simbolo, exigir_2fa, token_max_dias, token_padrao_dias, dominios_email}` |
| `POST /api/login` | `inquilino` e `login` são normalizados (`strip`, minúsculas); `503 inquilino_suspenso` só no login; usuário desabilitado = `401 credenciais_invalidas` (mesma mensagem) |
| `POST /api/login/2fa` | desafio inexistente OU expirado = `410 desafio_expirado`; sem `codigo` nem `codigo_recuperacao` = `422 validacao`; falha conta no MESMO contador de senha |
| `POST /api/logout` | `204` sempre; com sessão registra `usuarios/sair`; sob Bearer não faz nada (204) |
| `DELETE /api/eu/sessoes` | exige `?outras=1`; sem ele `400 pedido_invalido` |
| `POST /api/eu/2fa/confirmar` e `/desativar` | código errado = `401 codigo_invalido` **sem contar** no bloqueio (o bloqueio conta só no login); `desativar` com senha errada = `401 senha_incorreta`; inquilino `plataforma` = `409 2fa_obrigatorio` sempre |
| `POST /api/papeis`, `PUT` | nome fora do vocabulário = `422 privilegio_desconhecido` (antes do `privilegio_fora_do_teto`); `perfil_minimo` calculado (privilégio administrativo ⇒ `admin`); `PUT` com usuários abaixo do novo teto = `422 papel_incompativel {usuarios, perfil_minimo}` |
| `POST /api/usuarios` | `login` só `^[a-z0-9][a-z0-9._@-]*$` (maiúscula = 422 do esquema); `papel_id` inexistente = `404 papel_inexistente` |
| `PUT /api/usuarios/{id}` | `ativo:false` no próprio = `409 proprio_usuario`; desabilitar apaga sessões; `nome`/`email`/`ativo` exigem `membros.gerir`, `perfil`/`papel_id` exigem `membros.papel` (`403 sem_privilegio {exigido}`) |
| `POST /api/usuarios/lote` | `recusados[]` traz `{id, erro, mensagem}`; `acao=perfil` sem `perfil` (ou `papel` sem `papel_id`) = 422 |
| `POST /api/grupos` | `id` é gerado no servidor e devolvido no objeto; `entrar` em grupo já vinculado = `409 ja_membro`; membro que pede/aceita além de 512 grupos = `422 limite_grupos` |
| `PUT /api/grupos/{id}` | `dono_id`/`administrativo` só o dono (`403 so_dono`); novo dono sem `grupos.atualizacao_compartilhada` em grupo com atualização = `422 novo_dono_sem_privilegio` |
| `DELETE /api/grupos/{id}/membros/{uid}` | dono = `409 dono_nao_sai` (o ADR punha o código no `/membros`); `grupos.gerir_todos` sai de grupo administrativo |
| `POST /api/tokens` | `restricao` inválida = `422 restricao_invalida`; `validade_dias=0` só em dev (`400 validade_invalida` em producao); resposta traz `expira_em` |
| `GET /api/tokens/{id}` | `acessos_30d` e `ultimo_status` vêm do `log_acesso`; `renovar` por não dono = `403 so_dono_renova` |
| `GET /api/log` | itens têm também `usuario` (login) e `token_prefixo`; `status` aceita `401` ou `4xx`; `formato=csv` até 100 mil linhas |
| `X-Plat-Inquilino` | não superadmin = `403 so_superadmin`; rota não marcada = `400 cabecalho_nao_aceito`; inquilino inexistente = `404`; cada uso gera `inquilinos/leitura_superadmin` no inquilino lido |
| `/api/plataforma/*` | sem sessão ou sem superadmin = `404 nao_encontrado`; `admin_login` só minúsculas; `409 slug_reservado` vem do banco |
| páginas | `/admin/papeis` além das 6 do ADR |
| variáveis de teste | `PLAT_TESTE_BLOQUEIO_MIN`, `PLAT_TESTE_OCIOSA_S` lidas do ambiente do processo só em dev (não são chaves do `settings`); `PLAT_OPENAPI_ARQUIVO` é da suíte |

Roteiro do adversário (50): o mesmo da seção 16 do ADR; acrescento que `tests/api/cruzado_casos.py` é a lista
viva do que cada rota aceita de A sobre B, e que `test_cruzado` confere também que nenhuma rota derruba a sessão de
quem chama (invariante além do ADR).

## Complemento: e2e e medidas (15:44–15:59 UTC)

```
$ make e2e   (15:44:xx–15:58 UTC; `venv/bin/pytest -m lento --base-url https://plat.iagrointel.com`)
8 failed, 13 passed, 409 deselected, 1 warning in 807.77s (0:13:27)
FAILED tests/api/jobs/test_jobs_reinicio.py::... (3, trilha B: job não chegou a estado final em 60/90 s; job_transicao())
FAILED tests/e2e/test_tarefas.py::... (5, trilha B: locator da lista de tarefas não apareceu em 25 s)
passaram: tests/e2e/test_saude_pagina.py, os 7 e2e de identidade do frontend (login, 2fa, conta, usuarios, grupos,
tokens, log — papeis salta até o frontend recapturar), tests/api/test_login.py::test_bloqueio_expira_com_o_tempo (lento,
PLAT_TESTE_BLOQUEIO_MIN=1: 7ª tentativa certa entra depois de 61 s), e os lentos da trilha B que não dependem do worker

$ PLAT_GRAVAR_MEDIDAS=1 PLAT_OPENAPI_ARQUIVO=<cópia só trilha A> pytest tests/api tests/unit -m "not lento" --ignore=tests/api/jobs
exit=0 (nenhuma falha; coleta: 349 testes, tests/api + tests/unit sem jobs e sem lento)   -> tests/medidas/L0-02-tenant-auth.json (git_sha 441069ca6475, gerado_em 2026-09-05T15:58:50Z)
  rotas_total = 56 rotas · rotas_cobertas = 56 rotas   (100 % das rotas da trilha A + /saude + /api/versao)
  latencia_login_ms = 129.0 ms                        (mediana de 3 POST /api/login; inclui pbkdf2 600k ≈ 118 ms; alvo < 400)
  login_inexistente_vs_senha_errada_ms = [124.0, 124.7] ms  (tempo constante: usuário inexistente × senha errada)
  latencia_auth_token_ms = 2.94 ms                    (GET /api/eu com Bearer menos GET /api/versao; alvo < 5)
  custo_log_acesso_ms = 0.98 ms                       (GET /api/eu com e sem plat.log_registrar; alvo < 2)
  tempo_revogacao_s = 0.01 s                          (DELETE /api/tokens/{id} até o 401 token_revogado; alvo ≤ 1)
  funcoes_com_public = 0 de 54 (psql, seção Evidência)   testes_total = 384 passed na rodada `make teste` (25 failed, todos das
  rotas/arquivos da trilha B ou transitórios da 006; ver Evidência)
```

Commits finais: `9be4a04`, `2ffe8b4`, `b5c336b`, `ae6ec45` (código, instalador, testes) e `38430b2` (medidas).

## Correção T2 (achados do testador, 40_testes.md) — commit `abbb03d`

O que fiz:
1. **Resíduo de teste / `GrupoB`**: `test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga` roda agora num inquilino
   temporário (`InquilinoTemporario`, slug `zt-inq-*`, apagado no `teardown`), não em `demo2`; não depende de estado
   limpo nem da ordem `possui_grupos` × `ultimo_admin`. Fixture de fim de sessão (`limpeza_de_residuos`, autouse)
   revoga tokens, apaga grupos, papéis, usuários `zt-*` de `demo`/`demo2` e apaga inquilinos `zt-inq-*`; todo token
   criado por teste passou a chamar-se `zt-*`; senha de teste com dígito fixo (o hex aleatório podia sair só letras).
2. **Apagar inquilino** (não havia rota): migração `009_inquilino_apagar.sql` com `plat.tenant_apagar_interno(id)`
   (EXECUTE só postgres; desliga o gatilho `usuario_ultimo_admin` dentro da própria transação, porque ele recusava
   apagar o admin do inquilino que está sendo apagado; nunca por GUC, que `plat_app` poderia forjar; apaga toda tabela
   com `tenant_id` em passes até as FKs fecharem, inclusive `job`/`agenda`) e `plat.tenant_apagar(hash, id)` para o
   superadmin; rota `DELETE /api/plataforma/inquilinos/{id}` (204; `409 plataforma_nao_apaga`; 404), evento
   `inquilinos/apagar`, caso cruzado e entrada em `eventos_esperados`. `install.sh` em `PLAT_AMBIENTE=dev` apaga
   resíduos `zt-*` (inquilinos, tokens, grupos, usuários, papéis); em `producao` não toca em nada.
3. **Contagem de `log_acesso` sob concorrência**: `test_log_acesso` passou a identificar as próprias chamadas por um
   `User-Agent` único (`plat-teste-<hex>`, coluna `agente`), sem contagem global.
4. **`Referrer-Policy`**: repetido nas 4 `location` de `deploy/nginx.conf` (5 ocorrências = locations + server);
   `test_instalador.test_referrer_policy_em_todo_bloco_de_add_header_do_modelo` e
   `test_cabecalhos.test_referrer_policy_em_toda_rota` (HTTP vivo, 7 rotas). CSP fica para o L7-03.

Evidência:
```
$ bash db/migrar.sh                       aplicada   009_inquilino_apagar (43 ms) · pendentes 0
$ pytest tests/api tests/unit -m "not lento" --ignore=tests/api/jobs   (376 coletados)
  exit=1: 7 FAILED = test_cabecalhos::test_referrer_policy_em_toda_rota[...]  -> esperado até a próxima install.sh
  (o modelo de nginx só chega a /etc/nginx pelo instalador; não reinstalei, por ordem do gerente: o adversário estava
  reinstalando). Os demais 369: verdes, inclusive test_ultimo_admin, test_log_acesso, test_plataforma (criar, suspender,
  reativar, APAGAR: sessão do admin do inquilino morre, slug fica livre, 409 para plataforma).
$ psql: inquilinos zt-* restantes: 0 · funções com EXECUTE para PUBLIC: 0
$ sudo systemctl restart plat-api          2026-09-05T17:23:35Z · active
$ curl https://plat.iagrointel.com/api/openapi.json   rotas vivas: 74 | DELETE inquilino: True
$ curl -X DELETE .../api/plataforma/inquilinos/1 (sem sessão) -> HTTP 404
$ curl -I .../api/eu | grep referrer-policy  -> ausente ao vivo (modelo só entra na próxima install.sh)
```
Durante a construção da correção, duas rodadas caíram no meio do `DROP SCHEMA` + `install.sh` do adversário (falsos
negativos em `test_funcoes_seguras` e `test_plataforma`, repetidos verdes logo depois).
