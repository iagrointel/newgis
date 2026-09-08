# T2 · L0-02-tenant-auth · 20_arquitetura — arquiteto+dados (trilha A)

## Objetivo

Fixar, antes de qualquer código, o modelo de identidade e acesso do produto inteiro (inquilino → usuário → perfil →
privilégios → papéis personalizados → grupos → sessão → 2FA → token → log → superadmin) e o contrato de API, de modo
que backend (30) e frontend (31) trabalhem em paralelo sem colidir, e que o item passe as cláusulas herdadas do T1
(funções `SECURITY DEFINER` com checagem de inquilino, `EXECUTE` só `plat_app`, middleware gravando
`plat.log_acesso`, limiares declarados). Incorporar o `L0_CONCEITO.md` para não refazer depois.

## O que fiz

1. Esperei o `laco/decomposicao/L0_CONCEITO.md` (regra do dono): laço de `sleep 30` iniciado 13:23:07 UTC; o arquivo
   apareceu às 13:25:07 UTC (38.682 bytes). Não houve ausência a registrar. Li D1, D5, D6, D7, D14, D18, D19, D20
   e incorporei; as duas divergências (senha ≥ 8 do portão × ≥ 10 do conceito; `qrcode` "presente" × ausente na
   venv com `PYTHONNOUSERSITE=1`) estão marcadas no ADR com o motivo.
2. Li: SKILL, `00_plano.md`, item L0-02 no `estado.json`, ADR 0001 (seções 1-3, 6, 8-13), `001`/`002` da migração,
   `21_esri.md` seções 1 e 3.1, `refutacao.json` e `32_backend_correcao.md` do T1, `L0.json` (itens L0-02-a..g,
   L0-03-d/e, L0-07-b/f, L0-08-e, L0-10, L0-12, L0-14), `L3L6_CONCEITO.md` (A14, B1), o código atual de `app/`,
   `tests/conftest.py`, `web/`, `deploy/`, `install.sh` passo g, e o código de autenticação do SIG de teste interno
   (só leitura).
3. Medi nesta máquina o que sustenta as decisões (tabela no cabeçalho do ADR): pbkdf2 600k = 117,9 ms; sha256 =
   0,0012 ms; TOTP de biblioteca padrão bate o vetor da RFC 6238; `qrcode` 8.2 só em `~/.local`; `cryptography`
   41.0.7 é dpkg e importa na venv; `proacl` das 11 funções `plat` tem `=X/` (PUBLIC); `pg_cron` configurado e sem
   jobs; `pgaudit.log = none`; zonas `limit_req` já existem em `/etc/nginx` para outros serviços; `log_acesso`,
   `sessao` com 0 linhas.
4. Escrevi `docs/adr/0002-identidade-e-acesso.md` (18 seções, 1.151 linhas): modelo, 46 privilégios com tetos
   por perfil, grupos, contrato de compartilhamento para o L0-03-e, sessão, senha/bloqueio, TOTP, token, log +
   eventos, superadmin, `config.auth`, migração 003 normativa, gancho SSO, contrato de API (54 rotas), 6 telas em
   wireframe, testes obrigatórios, paridade, custo de mudar.
5. Escrevi este handoff com a lista arquivo por arquivo para 30 e 31.

## Evidência (comando + saída literal)

```
$ ls -la /home/dev/plataforma/laco/decomposicao/L0_CONCEITO.md
-rw-rw-r-- 1 dev dev 38741 Sep  5 13:25 /home/dev/plataforma/laco/decomposicao/L0_CONCEITO.md
$ cat scratchpad/tasks/bcua5ndcy.output
inicio 2026-09-05T13:23:07+00:00
APARECEU 2026-09-05T13:25:07+00:00 38682 bytes

$ venv/bin/python  (pbkdf2 5×, sha256 1000×, TOTP vetor RFC)
pbkdf2_600k_ms mediana=117.9 min=117.1 max=118.3
sha256_1000x_ms=1.21
totp_rfc6238_T59 = 287082 (esperado 94287082 com 8 dígitos; 6 dígitos = 287082)
$ PYTHONNOUSERSITE=1 venv/bin/python -c "import qrcode"
ModuleNotFoundError: No module named 'qrcode'
$ python3 -c "import qrcode; print(qrcode.__file__)"; pip3 show qrcode | grep -E 'Version|License'
/home/dev/.local/lib/python3.12/site-packages/qrcode/__init__.py
Version: 8.2
License: BSD
$ dpkg -s python3-cryptography | grep Version; PYTHONNOUSERSITE=1 venv/bin/python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import cryptography; print(cryptography.__version__, cryptography.__file__)"
Version: 41.0.7-4ubuntu0.4
41.0.7 /usr/lib/python3/dist-packages/cryptography/__init__.py

$ sudo -u postgres psql -d iagro_sat -tAc "SELECT proname, prosecdef, proacl FROM pg_proc WHERE pronamespace='plat'::regnamespace ORDER BY 1"
auth_falha|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_login|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_ok|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_sessao|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_sessao_criar|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_sessao_encerrar|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
auth_token|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
log_registrar|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
tenant_atual|f|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
tenant_criar|t|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
usuario_atual|f|{=X/postgres,postgres=X/postgres,plat_app=X/postgres}
$ sudo -u postgres psql -d iagro_sat -tAc "SHOW cron.database_name; SELECT count(*) FROM cron.job; SHOW pgaudit.log"
iagro_sat
0
none
$ grep -rn 'limit_req_zone' /etc/nginx/nginx.conf /etc/nginx/conf.d/ | wc -l
4
$ sudo -u postgres psql -d iagro_sat -tAc "SELECT count(*) FROM plat.log_acesso; SELECT count(*) FROM plat.usuario; SELECT count(*) FROM plat.sessao"
0
2
0
$ python3 -c "import json;print(list(json.load(open('docs/openapi.json'))['paths']))"
['/saude', '/api/versao']
$ git log --oneline | head -1
6678cf6 Documentação do L0-01 atualizada sobre 8ffe950 e 3083366 (passe curto do cronista)
$ wc -l docs/adr/0002-identidade-e-acesso.md; grep -c -E -f tests/marcadores.regex docs/adr/0002-identidade-e-acesso.md; grep -c -i -E '<os seis nomes de parceiro que o adversário do T1 varreu>' docs/adr/0002-identidade-e-acesso.md
1151 docs/adr/0002-identidade-e-acesso.md
0
0
$ df -h / | tail -1; free -g | sed -n 2p
/dev/vda2  469G  451G   13G  98% /
Mem: 23 20 0 6 9 3
```

## Riscos

1. **Tamanho do item.** O ADR cobre o produto inteiro; o portão do item pede login/logout/2FA/senha/usuários no
   navegador, teste cruzado, token no log e as cláusulas herdadas. Grupos, papéis pela API, tela Log e rotas de
   plataforma estão na lista abaixo porque o dono pediu telas de grupos/tokens/log e porque o teste cruzado precisa
   de rotas para varrer; se não couberem, a regra é: rota sem teste cruzado não entra no OpenAPI (não se comita
   metade), e botão sem rota não aparece. A ordem da lista do backend já é a ordem de prioridade do portão.
2. **`log_acesso` recriada particionada na 003** (0 linhas medidas). Se entre este handoff e a migração alguém
   gravar linhas, a 003 tem guarda que só recria quando `count(*) = 0`; caso contrário aborta com mensagem e o
   backend decide copiar. Registrar no handoff 30 qual ramo rodou.
3. **`install.sh` muda em três pontos** (semeia `plataforma/admin`; `demo`/`demo2` sem superadmin; escreve
   `/etc/nginx/conf.d/plat_limites.conf` e a `location = /api/login` com `limit_req`; confere dpkg
   `python3-cryptography`). O adversário do T1 provou que `install.sh` errado passa despercebido; o testador tem de
   reinstalar do zero. `tests/credenciais.txt` ganha a linha `plataforma admin <senha>`; `test_rls.ids_por_slug`
   continua válido (usa `demo`/`demo2`).
4. **Superadmin obrigado a 2FA** (inquilino `plataforma` com `exigir_2fa = true`): o e2e do superadmin precisa ligar
   o 2FA no primeiro acesso; a CLI do L0-14 não passa por sessão. Aceito: é o comportamento desejado.
5. **`?token=` em `/api/` ignorado**: cliente que hoje usa `/svc/<token>/` do SIG de teste interno terá de trocar
   quando o L2-04 nascer; registrado em PARIDADE como "fora" até lá.
6. **Colisões com a trilha B**: `app/main.py` (montagem de routers e middleware), `app/paginas.py` (uma linha),
   `app/limites.py` (seção própria), `app/erros.py` (B importa, não cria). Regra do plano: quem comita primeiro
   fica; o segundo rebase-a e roda `make check`. A trilha A cria `erros.py`, `paginas.py` e `limites.py`; B não os
   cria de novo.
7. **RAM 3 GB disponíveis**: backend e frontend juntos são 2 subagentes em processo (ok); o e2e (chromium) do
   testador não pode correr junto com o `make check` de B.
8. **D24 (público) e D18 (nome público)**: `compartilhar_publico` nasce `false`; o rótulo do TOTP usa `plat`.
   Nenhuma decisão do dono é exigida para fechar este item.

## Pendências

1. Gerente: `decisoes_do_dono` não ganha item novo por este handoff.
2. Gerente: o driver reinstala com frequência; a 003 cria 3 partições à frente e o `install.sh` chama
   `log_particao_garantir`/`evento_particao_garantir`; o agendamento mensal é do L0-05-d (trilha B deste turno):
   avisar a trilha B que existe `plat.sessoes_expurgar()`, `plat.log_particao_garantir()`,
   `plat.evento_particao_garantir()`, `plat.log_expurgar()`, `plat.evento_expurgar()` para o registro de periódicos.
3. Cronista: `docs/PARIDADE.md` recebe a tabela da seção 17 do ADR SÓ depois do testador (regra: nunca antes).
4. Esri (próximo turno, L0-07-b): conferir linha a linha os 46 privilégios contra "Privileges for roles" 11.4.
5. L0-03-e: implementar `pode_ler`/`pode_editar` e `compartilhamento_link` sobre o contrato da seção 4.3.

## Para o próximo papel

Contrato fixado no ADR seção 14 (rotas, corpos, códigos) e seção 5.1 (cookie). O frontend codifica contra ele com
o backend ainda inexistente: até o backend subir, o frontend valida com `tests/e2e` marcados `lento` contra a URL
interna, e com um servidor local de `web/` para o layout. Nenhum dos dois edita arquivo do outro. Ambos leem o ADR
inteiro antes de começar; em dúvida vale o ADR; se o ADR estiver errado, o construtor escreve o desvio no seu
handoff com o motivo medido e o gerente decide.

### Backend (handoff 30) — nesta ordem; cada passo com teste ao lado

1. `db/migracoes/003_identidade_acesso.sql` — ADR seção 12 inteira: 12.1 `privilegio` + `perfil_privilegio`
   semeados (46 + tetos da seção 3.2); 12.2 `papel_personalizado` + `papel_privilegio` (RLS); 12.3 colunas de
   `usuario` (`papel_id`, `origem`, `sujeito_externo`, `senha_hash` nullable + CHECK, `trocar_senha`,
   `falhas_desde`, `totp_ultimo_passo`, `codigos_recuperacao`, `desafio_2fa_hash`, `desafio_2fa_ate`, `ultimo_ip`);
   12.4 `senha_historico`; 12.5 `grupo` + `grupo_membro` (RLS de leitura por visibilidade com `plat.tem`); 12.6
   gatilhos `usuario_ultimo_admin`, `usuario_superadmin_so_plataforma`, `grupo_dono_coerente`; 12.7 `evento_tipo`
   (vocabulário da seção 9.4) + `evento` particionada + `evento_registrar` + `evento_particao_garantir` +
   `evento_expurgar`; 12.8 `log_acesso` particionada com guarda (`relkind`, `count(*) = 0`) + `log_particao_garantir`
   + `log_expurgar`; 12.9 inquilino `plataforma` (`config.auth.exigir_2fa = true`); 12.10 `privilegios_de`, `tem`;
   funções `SECURITY DEFINER` da tabela da seção 12 (assinaturas novas: `DROP FUNCTION IF EXISTS` da antiga);
   `REVOKE EXECUTE ... FROM PUBLIC` + `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` +
   `GRANT EXECUTE ... TO plat_app`; `REVOKE INSERT/UPDATE/DELETE` em `privilegio`, `perfil_privilegio`, `evento`,
   `evento_tipo`. Idempotente; `bash db/migrar.sh` duas vezes = 0 linhas novas. Teste: `tests/api/test_migracoes.py`
   ganha 003; `tests/api/test_funcoes_seguras.py` (ADR 16.2).
2. `app/limites.py` — constantes e faixas da seção 11 e os limites `TOKENS_POR_USUARIO = 20`, `GRUPOS_POR_USUARIO =
   512`, `LOTE_MAX = 100`, `LOG_JANELA_DIAS = 92`, `LOG_LIMITE_MAX = 1000`, `RESTRICAO_MAX = 20`. Cabeçalho de
   seção `# --- identidade (L0-02)`; a trilha B acrescenta a dela abaixo.
3. `app/erros.py` — `ErroAPI(status, erro, mensagem, detalhe=None)` e os dois handlers (`HTTPException`,
   `RequestValidationError`) que devolvem `{erro, mensagem, detalhe?, req_id}` (seção 14). Teste unitário
   `tests/unit/test_erros.py` (um caso por código usado).
4. `app/auth/__init__.py`, `app/auth/politica.py` — leitura de `tenant.config.auth` com padrões e faixas (JSON
   Schema em dicionário Python, sem dependência), corte para a faixa com aviso; regras de senha com `detalhe.regra`;
   `HASH_FANTASMA` gerado na partida. Teste `tests/unit/test_politica.py` (12 senhas inválidas da seção 16.5;
   valor fora da faixa cortado).
5. `app/auth/totp.py` — `codigo(segredo_b32, t)`, `verificar(segredo, codigo, ultimo_passo) -> passo|None`,
   `cifrar`/`decifrar` AES-GCM (`enc:v1:`), `codigos_recuperacao()` (8), `qr_svg(uri)` com `qrcode==8.2`
   (acrescentar a linha em `requirements.txt`; `tests/unit/test_dependencias.py` já reprova sem `==`). Teste
   `tests/unit/test_totp.py` com o vetor da RFC 6238 (T=59 → `287082`), replay, janela ±1, cifra ida-e-volta,
   prefixo `enc:v1:`.
6. `app/auth/redigir.py` — redige `token`, `senha`, `codigo`, `desafio` em query string e os cabeçalhos `Cookie`/
   `Authorization` em qualquer linha de log. Teste unitário.
7. `app/auth/sessao.py` — dependências FastAPI: `sessao_ou_token(request)` (cookie OU Bearer; ambos = 400),
   `so_sessao`, `exigir(privilegio)`, `superadmin`, `contexto_de(request)` (constrói `db.Contexto`), checagem de
   pendências (seção 5.4), checagem de `Origin`/`Content-Type` em escrita sob cookie (seção 5.3), restrição
   referer/IP do token (seção 8.3), escopo (`app/auth/escopos.py` com a expressão regular e `exigir_escopo`).
   Teste `tests/api/test_sessao.py` (cookie atributos, alterado, após logout, ambíguo, 415, origem).
8. `app/auth/middleware.py` — substitui o middleware de `main.py`: `X-Req-Id`, linha JSON no journal (já existe) E
   `plat.log_registrar` em `BackgroundTask` com `bytes` contados no `body_iterator`, rotas excluídas da seção 9.1,
   `rota` redigida. Teste `tests/api/test_log_acesso.py`: `GET /api/eu` com cookie e com token geram linha com
   `usuario_id`/`token_id`, `ip`, `bytes > 0`; `/saude` não gera; medida `custo_log_acesso_ms`.
9. `app/auth/rotas_login.py` — `GET /api/login/provedores`, `POST /api/login`, `POST /api/login/2fa`,
   `POST /api/logout` (seções 5-7, 14). Ordem interna do login: `auth_login` → abre contexto do inquilino resolvido →
   suspenso? → `origem`? → bloqueado? → `senha.verificar` (ou contra `HASH_FANTASMA`) → `auth_falha`/`auth_ok` →
   2FA? desafio : `auth_sessao_criar` → cookie → `evento_registrar('usuarios/entrar')` → `log_registrar` com
   `resultado`. Teste `tests/api/test_login.py` (todos os códigos da linha `/login` e `/login/2fa`; `latencia_login_ms`;
   força bruta de senha e TOTP; recuperação; journal sem segredo).
10. `app/auth/rotas_eu.py` — `/api/eu` (GET, PUT), `/api/eu/senha`, `/api/eu/sessoes`, `/api/eu/2fa/*`,
    `/api/eu/convites`. Teste `tests/api/test_eu.py`.
11. `app/auth/rotas_tokens.py` — `/api/tokens*` e `/api/tokens/{id}/log` (seção 8). Teste `tests/api/test_tokens.py`
    (ADR 16.4 inteira; `validade_dias = 0` só em `dev`; `latencia_auth_token_ms`).
12. `app/auth/rotas_usuarios.py` — `/api/usuarios*`, `/api/usuarios/lote`, `/api/privilegios`, `/api/papeis*`
    (seções 2.3, 3.3, 14). Teste `tests/api/test_usuarios.py` (último admin, só admin altera admin, lote de 100,
    domínio de e-mail, papel fora do teto/em uso).
13. `app/auth/rotas_grupos.py` — `/api/grupos*` (seção 4). Teste `tests/api/test_grupos.py` (ADR 16.5).
14. `app/auth/rotas_log.py` — `/api/log` (JSON e CSV), `/api/eventos`, com `X-Plat-Inquilino` para superadmin
    (leitura em transação `read only`). Teste `tests/api/test_log.py`.
15. `app/auth/rotas_plataforma.py` — `/api/plataforma/inquilinos*` (seção 10). Teste `tests/api/test_plataforma.py`
    (404 para não superadmin; slug reservado; `plataforma` não se suspende; suspenso não autentica).
16. `app/paginas.py` — dicionário `PAGINAS` da seção 15 e a rota que serve `web/<arquivo>` com `no-store`;
    `main.py` só o inclui. Teste `tests/api/test_paginas.py` (6 caminhos = 200 `text/html`, `Cache-Control`).
17. `app/main.py` — remove o middleware antigo, inclui `app.auth.middleware`, os routers acima, `app.erros`,
    `app.paginas`. É o único arquivo que a trilha B também edita: comitar cedo e avisar no `trilhas.json`.
18. `install.sh` — passo f: conferir `python3-cryptography`; passo g: semear `plataforma admin` com superadmin e
    `demo`/`demo2` sem (`tests/credenciais.txt` com 3 linhas); passo novo: escrever
    `/etc/nginx/conf.d/plat_limites.conf` (zona `plat_login` 10r/m) e, em `deploy/nginx.conf`, `location =
    /api/login` e `location = /api/login/2fa` com `limit_req zone=plat_login burst=10 nodelay; limit_req_status 429;`
    antes do `location /`; chamar `plat.log_particao_garantir(date_trunc('month', now()))` e o equivalente de
    `evento` após migrar. `tests/unit/test_instalador.py` ganha as três leituras.
19. `tests/api/cruzado_casos.py` + `tests/api/test_cruzado.py` — gerador da seção 16.1 (cobertura 100 % do
    `docs/openapi.json`, 4 chamadas por rota, controle de efeito em B, medida `rotas_total`/`rotas_cobertas`).
    `tests/api/test_privilegios_declarados.py` (seção 3.4) e `tests/api/eventos_esperados.py` +
    `test_eventos.py` (seção 9.4).
20. `make openapi` → `docs/openapi.json` comitado com todas as rotas e `response_model`; `make check` verde
    inteiro (P3); `make medidas` grava `tests/medidas/L0-02-tenant-auth.json` com: `latencia_login_ms`,
    `latencia_auth_token_ms`, `latencia_auth_sessao_ms`, `custo_log_acesso_ms`, `tempo_revogacao_s`,
    `rotas_total`, `rotas_cobertas`, `funcoes_com_public`, `testes_total`. Handoff 30 com comando + saída literal
    de cada um, o ramo que a guarda de `log_acesso` seguiu, e a saída de `bash /home/dev/fgr/sig/pipeline/testar.sh`
    (9/9; o banco é compartilhado) — o caminho desse script é o único nome de parceiro admitido, e só no handoff.

### Frontend (handoff 31) — em paralelo com o backend; contrato = ADR seções 5.1, 14, 15

1. `web/js/auth/api.js` — `chamar(metodo, url, corpo)` sobre `obterJSON` de `core.js`: sempre `credentials:
   'same-origin'`, `Content-Type: application/json` em escrita, devolve `{status, json}`; traduz o erro
   `{erro, mensagem}` para texto de tela (a mensagem já vem em português; o front só mostra). Nunca guarda token.
2. `web/js/auth/sessao.js` — `exigirSessao({privilegio?})`: `GET /api/eu`; 401 → `/entrar?inquilino=<localStorage
   plat_inquilino>&proximo=<location.pathname+search>`; `pendencias` → `/conta#senha` | `/conta#2fa`; privilégio
   ausente → tela "sem permissão" (não redireciona); devolve o usuário. `sair()` = `POST /api/logout` + `/entrar`.
3. `web/js/auth/barra.js` — barra superior comum (seção 15): nome do inquilino, nome do usuário → `/conta`, links
   Usuários/Grupos/Tokens/Log condicionados a `usuario.privilegios`, Sair. Injeta `<header class="barra">` no topo
   do `body`.
4. `web/login.html` + `web/js/auth/login.js` — seção 15.1: lê `?inquilino=` e `?proximo=`; `GET
   /api/login/provedores`; formulário de senha; troca para o formulário de código quando `exige_2fa`; alternância
   "código de recuperação"; contador de 5 min do desafio; mensagens da API; redireciona só para caminho relativo
   que começa por `/` e não por `//`; `body[data-pronto='1']` quando pronto.
5. `web/conta.html` + `web/js/auth/conta.js` — seção 15.2: dados, senha (regra ao vivo repetindo a política do
   `/api/eu`: a política vem em `usuario.inquilino.config_publica.auth` com `senha_min` e composição), 2FA
   (QR = `innerHTML` do `qr_svg` dentro de um `<div>` dedicado; o SVG vem do servidor e não contém script; o
   segredo em `<code>`), códigos de recuperação com [Copiar], sessões, convites. Âncoras `#senha` e `#2fa` abrem a
   seção e mostram o aviso de pendência.
6. `web/admin/usuarios.html` + `web/js/auth/usuarios.js` — seção 15.3: tabela paginada de `GET /api/usuarios`,
   filtros, busca, painel lateral de criar/editar, senha temporária mostrada uma vez, ações por linha, seleção em
   massa até 100 com resultado `alterados/recusados`, mensagens exatas da API (409 `ultimo_admin`).
7. `web/admin/grupos.html` + `web/js/auth/grupos.js` — seção 15.4: abas, criar, painel Visão geral/Membros,
   convidar com busca `GET /api/usuarios?q=`, aprovar, sair, apagar; botões condicionados a `meu_papel` e às marcações.
8. `web/admin/tokens.html` + `web/js/auth/tokens.js` — seção 15.5: lista, novo token (escopos como caixas; a caixa
   "administração do inquilino" só se `perfil === 'admin'`), validade, restrições, token mostrado uma vez,
   renovar/revogar, aba Acessos com `GET /api/tokens/{id}/log`.
9. `web/admin/log.html` + `web/js/auth/log.js` — seção 15.6: filtros, tabela paginada, exportar CSV (link para
   `/api/log?formato=csv&...`, o navegador baixa), aba Eventos.
10. `web/style.css` — acrescentar (sem mudar o que existe): `.barra`, `.tabela`, `.painel-lateral`, `.form`,
    `.erro`, `.aviso-pendencia`, `.codigo` (fonte mono para segredo/token/códigos), `.svg-qr`; orçamento: cada módulo
    ≤ 60 kB (ADR 0001 11.2).
11. `web/index.html` + `web/app.js` — quando há sessão (`GET /api/eu` 200), a página inicial mostra a barra e os
    atalhos das telas; sem sessão, mostra o que mostra hoje mais o link "Entrar". Não quebrar
    `tests/e2e/test_saude_pagina.py`.
12. `tests/e2e/test_login.py`, `test_2fa.py`, `test_conta.py`, `test_usuarios.py`, `test_grupos.py`,
    `test_tokens.py`, `test_log.py` — marcados `lento` + `e2e`, contra a URL interna, capturas
    `tests/e2e/capturas/L0-02-tenant-auth_<tela>.png`, 0 erro de console, 0 resposta ≥ 400 não esperada; o teste de
    2FA calcula o código com a mesma função de 6 linhas (copiar de `app/auth/totp.py` quando existir; até lá, a
    função está na seção 7.1 do ADR); senhas de `tests/credenciais.txt`; medida `pagina_pronta_ms` por tela.
13. Enquanto o backend não sobe: servir `web/` com `venv/bin/python -m http.server` no scratchpad só para
    layout; nenhum JSON fixo em código (regra P2): as telas mostram "não foi possível carregar" com o
    `status` quando a API não responde, e é isso que o e2e vê até o backend existir.

### Testador (40), depois de 30 e 31

Rodar `make check` inteiro; reinstalar do zero (`DROP SCHEMA plat CASCADE; DROP OWNED BY plat_app; DROP ROLE
plat_app` → `install.sh`); repetir a lista da seção 16 do ADR; gravar `tests/medidas/L0-02-tenant-auth.json`;
conferir as capturas; `bash /home/dev/fgr/sig/pipeline/testar.sh` = 9/9.

### Adversário (50)

Só o item, o portão (inclusive cláusulas herdadas), o repositório e a URL. Roteiro sugerido pelo próprio ADR seção 16
(o adversário não lê 30/31 nem este handoff): rotas do OpenAPI com sessão/token de `demo` sobre recursos de `demo2`;
funções `SECURITY DEFINER` por `psql` como `plat_app` com contexto de outro inquilino; 1.000 senhas em 3 min;
1.000.000 de códigos TOTP; token revogado/expirado/escopo/referer/IP; cookie após logout; `?token=` em `/api/`;
senha/cookie/desafio no journal; último admin; superadmin forjado por GUC.

## Resumo em 10 linhas

1. `L0_CONCEITO.md` chegou às 13:25 UTC (2 min após o início do laço); D1/D5/D6/D7/D14/D18/D19/D20 incorporados; sem ausência a registrar.
2. Modelo: perfil (admin/editor/visualizador/campo) = teto e papel padrão; 46 privilégios fechados em tabela; papel personalizado = subconjunto do teto; `plat.tem()` para rotas e RLS.
3. Grupos com UUID, papéis dono/gerente/membro, entrada convite/pedido/livre, marcações da Esri; contrato de compartilhamento (5 níveis, `pode_ler`) fixado para o L0-03-e.
4. Sessão: cookie `plat_sessao` HttpOnly/Secure/Lax, hash no banco, 12 h ociosa / 7 d máximo, revogável; CSRF por Lax + JSON + Origin.
5. Senha ≥ 8 com letra e número (portão; diverge do conceito D6 = 10, registrado), histórico 5, bloqueio 5/15/15 por usuário no banco + 10 r/min por IP no nginx; login em tempo constante (~118 ms medidos).
6. 2FA TOTP em biblioteca padrão (vetor RFC conferido), segredo AES-GCM com chave de `PLAT_SECRET`, anti-replay, 8 códigos de recuperação, exigir por inquilino; `qrcode==8.2` entra em `requirements.txt` (ausente na venv, medido).
7. Token `plat_`+43, escopos fechados, referer/IP, 90 d padrão / 365 d máximo (400 acima), revogação ≤ 1 s, rotação 24 h, 401 com motivo; `?token=` só fora de `/api/`.
8. `log_acesso` recriada particionada por mês (0 linhas), escrita por função em BackgroundTask, retenção 12 meses por DROP de partição; `evento` append-only com vocabulário D14 já nesta migração.
9. Superadmin = inquilino técnico `plataforma` com 2FA obrigatório; funções `plataforma_*` resolvem a sessão pelo hash, nunca por GUC; `REVOKE FROM PUBLIC` em todas as funções (11 hoje com `=X/`).
10. Handoff com 20 passos de backend e 13 de frontend, arquivos disjuntos (só `app/main.py`, `paginas.py`, `limites.py` colidem com a trilha B, por ordem de commit), contrato de 54 rotas fixado para o front codificar antes do back.
