# T1 · 32 — Backend, rodada de correção do item L0-01-repo (resposta ao PARCIAL do adversário)

Commit: `8ffe950` sobre `7092755` (documentação do cronista). Árvore limpa. `plat-api` ativo, `NRestarts=0`.

## Objetivo
Fechar as cláusulas que o adversário derrubou em `50_refutacao.md` / `refutacao.json` sem redesenho:
(1) máquina que nunca viu o repo, (2) senha no journal, (3) ADR × código, (4) HSTS + Swagger UI local,
(5) varredura `sem-marcador` nos `.md`, (6) registrar o achado das funções SECURITY DEFINER para o L0-02.
Não toquei em `ARQUITETURA.md`, `MANUAL.md`, `CHANGELOG.md`, `README.md` (cronista, comitados em `7092755`).

## O que fiz
1. **Dependências fixadas, sem `~/.local`.** `requirements.txt` fixa com `==` tudo que `app/` e `tests/` importam
   (fastapi 0.138.0, starlette 1.3.1, pydantic 2.13.4, pydantic_core 2.46.4, python-dotenv 1.2.2, httpx 0.28.1,
   anyio 4.13.0 e transitivas; pytest/playwright/ruff já estavam). `uvicorn` e `psycopg2` continuam dpkg por
   decisão do ADR 2.1, mas o `install.sh` confere `dpkg -s python3-uvicorn python3-psycopg2 python3-venv` e aborta
   nomeando o que falta. `PYTHONNOUSERSITE=1` em três lugares: `Environment=` na unidade (`deploy/plat-api.service`),
   `export` no `Makefile`, e `env PYTHONNOUSERSITE=1` em cada `sudo -u` do `install.sh` (`PY=(...)`, `PIP=(...)`,
   linhas 21-22), porque o `sudo` zera o ambiente. O passo f do instalador prova `import app.main` e exige
   `fastapi.__file__` dentro de `venv/`. Teste: `tests/unit/test_dependencias.py` (subprocesso com
   `PYTHONNOUSERSITE=1`, sem `.env`, sem banco; confere `site.ENABLE_USER_SITE == False` e origem dos 4 módulos).
2. **Senha por stdin.** Passo g: `HASH=$(printf '%s' "$senha" | "${PY[@]}" -c "... gerar_hash(sys.stdin.read())")`
   (linha 104). `printf` é builtin, não aparece em `ps`; o `COMMAND=` que o `sudo` grava no journal não tem mais
   a senha. `tests/credenciais.txt` foi apagado antes da reinstalação, logo as senhas semeadas são novas (as antigas
   continuam no journal antigo, ver Riscos). `tests/unit/test_instalador.py` reprova `gerar_hash(sys.argv`.
3. **ADR × código.** `make medidas` (`PLAT_GRAVAR_MEDIDAS=1`, suíte inteira com `--base-url`); `install.sh` grava
   `PLAT_GIT_SHA=$(git rev-parse HEAD)` no `.env` a cada execução e, sem `.git`, exige sha válido no `.env`;
   `app/versao.py` cai para `PLAT_GIT_SHA` do ambiente e depois do `.env` via `settings` (3 testes novos em
   `test_versao.py`). Vendor renomeado para a convenção do ADR (`maplibre-gl-4.7.1.js/.css`) com
   `tests/unit/test_vendor.py` (nome `<nome>-<versão>.js|css`, sha256, licença, toda entrada de `VERSOES.txt`) e alvo
   `make vendor` (`sha256sum -c`). ADR 0001 alterado nas seções 1, 2.1, 4.2, 7, 8, 9, 10, 11.2, cada uma com
   "alterado em T1: motivo"; a gravação em `plat.log_acesso` virou **decisão explícita** para o L0-02 (seção 9);
   `fgrsig` da linha 293 removido.
4. **HSTS + Swagger local.** `deploy/nginx.conf` traz `add_header Strict-Transport-Security "max-age=31536000"
   always;` no `server` e nas 2 `location` (armadilha do `add_header`); o `install.sh` remove essas linhas quando o
   bloco ainda é `:80`, chama o certbot e reescreve o bloco (passo i3). O passo j agora espera 200 **com** HSTS
   (os workers antigos do nginx serviam 200 sem o cabeçalho por 1-2 s). `/api/docs` é rota própria com
   `swagger-ui-bundle-5.32.15.js` + `swagger-ui-5.32.15.css` (npm pack `swagger-ui-dist@5.32.15`, Apache-2.0,
   sha256 em `VERSOES.txt`), `favicon.svg` local, `validatorUrl: null` (o bundle consultaria
   `validator.swagger.io`), `redoc_url=None` (o ReDoc padrão também vinha de CDN). Testes: `tests/api/test_docs.py`
   (0 `http(s)://` no HTML, `/docs` `/redoc` `/openapi.json` = 404) e 3 testes novos em `test_cabecalhos.py`
   (HSTS em 6 rotas HTTPS, ausente no 301 de `:80`, recursos da documentação servidos pelo nginx sem `X-Req-Id`).
5. **`sem-marcador`** varre também `*.md` da raiz, `requirements.txt`, `pyproject.toml` (mesma expressão de
   `tests/marcadores.regex` = a do `driver.sh`). Ela pegou o `XXXXXX` do `mktemp` no meu próprio `install.sh`
   (troquei por nome com data e pid).
6. Extras achados no caminho: a cópia de segurança do bloco nginx agora fica **fora** de `sites-enabled`
   (a primeira versão ficou dentro e o `nginx -t` acusou "conflicting server name"); se `nginx -t` reprovar, o
   bloco anterior volta e o script sai com 5 (risco 2 da refutação).

## Evidência (comando + saída literal)
```
$ PYTHONNOUSERSITE=1 ./venv/bin/pip install -q --disable-pip-version-check -r requirements.txt; echo rc=$?
rc_install=0
$ PYTHONNOUSERSITE=1 ./venv/bin/python -c 'import app.main; import fastapi; print("ok", fastapi.__file__)'
ok /home/dev/plataforma/enterprise/venv/lib/python3.12/site-packages/fastapi/__init__.py
$ grep -n 'sys.stdin.read\|^PY=\|^PIP=' install.sh
21:PY=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/python)
22:PIP=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/pip)
104:  HASH=$(printf '%s' "$senha" | "${PY[@]}" -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))")
$ /usr/bin/time -f "tempo_total=%e s" sudo bash install.sh plat.iagrointel.com 8150   (3ª rodada, sobre HEAD 8ffe950)
PLAT_GIT_SHA=8ffe950516f59aa17149c0d75d22b3859b40e487 gravado no .env
venv: Python 3.12.3 · fastapi 0.138.0 da venv · pytest 9.1.1
== j. conferência pública
https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow · Strict-Transport-Security: max-age=31536000
== instalado em 4 s: https://plat.iagrointel.com (serviço plat-api, porta 8150)
tempo_total=4.45 s
rc_install=0
$ sudo journalctl -n 50 --since "-10min" | grep -c <cada senha, 2 antigas + 2 novas>   -> total=0
$ sudo journalctl --since "-10min" | grep -c <cada senha, 2 antigas + 2 novas>         -> total=0
$ sudo journalctl --since "-10min" -o cat _COMM=sudo | grep gerar_hash | tail -1
    root : PWD=/home/dev/plataforma/enterprise ; USER=dev ; COMMAND=/usr/bin/env PYTHONNOUSERSITE=1 venv/bin/python -c 'import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))'
$ curl -sI https://plat.iagrointel.com/saude | grep -iE '^(HTTP|strict|x-robots)'
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000
X-Robots-Tag: noindex, nofollow
$ curl -sI http://plat.iagrointel.com/saude | grep -iE '^(HTTP|location|strict)'
HTTP/1.1 301 Moved Permanently
Location: https://plat.iagrointel.com/saude
$ curl -s https://plat.iagrointel.com/api/docs | grep -cE 'https?://'          -> 0
$ curl -s https://plat.iagrointel.com/api/docs | grep -oE '(src|href)="[^"]+"'
href="/static/vendor/swagger-ui-5.32.15.css"
href="/static/favicon.svg"
src="/static/vendor/swagger-ui-bundle-5.32.15.js"
$ for r in /redoc /docs; do curl -s -o /dev/null -w "$r %{http_code}\n" https://plat.iagrointel.com$r; done
/redoc 404
/docs 404
$ curl -s https://plat.iagrointel.com/saude | jq -r '.git_sha,.banco,.migracoes_pendentes'; git rev-parse --short=12 HEAD
8ffe950516f5 ok 0
8ffe950516f5
$ grep -n Environment /etc/systemd/system/plat-api.service; sudo cat /proc/$(systemctl show plat-api -p MainPID --value)/environ | tr '\0' '\n' | grep PYTHONNOUSERSITE
12:Environment=PYTHONNOUSERSITE=1
PYTHONNOUSERSITE=1
$ awk '/^server/{n++} /Strict-Transport/{c[n]++} END{for(i in c) print "server#"i, c[i]}' /etc/nginx/sites-enabled/plat.iagrointel.com
server#1 3          (só o bloco 443; o bloco :80 do certbot não tem)
$ make vendor
maplibre-gl-4.7.1.js: OK · maplibre-gl-4.7.1.css: OK · swagger-ui-bundle-5.32.15.js: OK · swagger-ui-5.32.15.css: OK
$ /usr/bin/time -f "make_check_tempo=%e s" make check
ruff: All checks passed! · sem-marcador: 0 linhas · pytest: 81 passed, 1 deselected in 1.43s · e2e: 1 passed in 0.58s
make_check_tempo=2.83 s   rc_make=0
$ make openapi; git diff --stat docs/openapi.json          -> vazio (só rotas fora do esquema mudaram)
$ systemctl show plat-api -p NRestarts -p ActiveState       -> NRestarts=0 ActiveState=active
```
Contagem de testes: 57 + 1 e2e antes → **81 + 1 e2e** agora (24 novos: 4 dependências, 3 versão, 2 vendor,
5 instalador, 2 docs, 6 + 1 + 1 cabeçalhos).

## Riscos
1. **Journal antigo ainda tem as senhas anteriores** (18 linhas anotadas pelo adversário, antes das 13:05). As senhas
   foram trocadas, então o que está lá não abre nada; apagar exigiria `journalctl --vacuum-time` sobre o journal de
   TODOS os serviços da máquina, decisão do gerente, não minha.
2. "Máquina que nunca viu o repo" continua sendo simulação (`PYTHONNOUSERSITE=1` + origem dos módulos). Uma máquina
   sem `python3-uvicorn`/`python3-psycopg2` para com mensagem nomeada, não sobe; não há segunda máquina para provar.
3. `install.sh` agora reescreve o bloco nginx **duas vezes** na primeira instalação (antes e depois do certbot);
   o caminho do certbot não foi exercitado aqui (o certificado já existe), só lido.
4. `tests/medidas/L0-01-repo.json` está assinado pelo testador sobre `ca61ea1` e cita `maplibre-gl.js` (nome antigo) e
   57 testes; não regravei (é do testador; `make medidas` está pronto para isso).
5. A fixture `cliente` (TestClient) emite `StarletteDeprecationWarning` sobre `httpx`/`httpx2` com starlette 1.3.1;
   é aviso, não erro; fica para quem atualizar a pilha.

## Pendências
- Testador: `make medidas` para regravar o JSON sobre `8ffe950` (nomes de vendor e contagem de testes mudaram).
- Adversário: repetir o roteiro (`scratchpad/refutacao_destrutiva.sh`) sobre `8ffe950`; as três cláusulas
  derrubadas têm agora prova executável (item 1, 2 e 4 acima) e as cascas dos `.md` são do commit `7092755`.
- Gerente: decidir sobre `journalctl --vacuum` (risco 1).

## Para o próximo papel
**Entrada obrigatória do L0-02 (achado do adversário, ataque 4, NÃO corrigido aqui por não ser cláusula deste item):**
as funções `SECURITY DEFINER` de `002_identidade.sql` **não checam inquilino**:
- `plat.auth_sessao_criar(p_usuario, ...)` chamada no contexto do tenant 1 com usuário do tenant 2 devolve token
  válido que `plat.auth_sessao` resolve para `demo2/admin`;
- `plat.auth_falha(usuario_de_outro_tenant, 1, 60)` bloqueia o admin do outro inquilino;
- `plat.auth_login('demo2','admin')` entrega `senha_hash` e `totp_secret` de outro inquilino a quem tiver o DSN;
- `plat.tenant_criar` aceita GUC `plat.usuario_id` forjado pelo cliente (criou tenant 3 no teste, desfeito por rollback);
- todas têm `EXECUTE` para `PUBLIC`, hoje inalcançável só porque `PUBLIC` não tem `USAGE` no schema.
O que o L0-02 tem de entregar junto com as rotas: (a) as funções que recebem `p_usuario` exigem
`plat.tenant_atual()` igual ao `tenant_id` do usuário quando houver contexto, ou recebem `p_tenant` e conferem;
(b) `REVOKE EXECUTE ... FROM PUBLIC` + `GRANT` só a `plat_app`; (c) `tenant_criar` decide superadmin pela sessão
resolvida no banco (`auth_sessao`), nunca por GUC que o cliente possa setar; (d) teste adversarial por rota
A→B (P6) e teste direto das funções como `plat_app` (o roteiro do adversário, `scratchpad/rls_ataque.py`, serve
de base). Também do L0-02, por decisão escrita no ADR seção 9: o middleware passa a gravar `plat.log_acesso`
via `plat.log_registrar` para `/api/`, `/svc/`, `/ogc/`, com o teste "token de serviço aparece no log".
