# T2 · L0-02-tenant-auth · 40_testes — testador (trilha A)

## Objetivo

Conferir, sem acreditar nos handoffs 30/31, cada cláusula do portão do item (inclusive as herdadas do T1) e os portões
P1–P9, com prova própria na instância viva `https://plat.iagrointel.com` e no banco (`sudo -u postgres psql`), medir o
que o portão pede e gravar `tests/medidas/L0-02-tenant-auth.json` preservando as chaves do backend. Não consertei
código.

## O que fiz

1. `git log` (HEAD `ad2ea29`), `make lint`, `make sem-marcador`, `make teste` (2 rodadas: a 1ª levou SIGTERM externo aos
   77 s), `make e2e` inteiro (23 min 48 s), depois `make medidas` (suíte inteira com `PLAT_GRAVAR_MEDIDAS=1`).
2. Cláusula (a): consulta própria em `pg_class`/`pg_policy`/`pg_attribute` (RLS, FORCE, WITH CHECK, donos, grants).
3. Cláusula (b): li as 9 capturas `tests/e2e/capturas/L0-02-tenant-auth_*.png` regeneradas pelo `make e2e` (16:18–16:27).
4. Cláusula (c): script próprio `varredura_viva.py` (scratchpad) contra o `/api/openapi.json` VIVO (73 rotas): para
   cada rota, o caso do backend em 4 chamadas (sessão A · token A `admin:inquilino` · sessão A + `X-Plat-Inquilino:
   demo2` · anônimo) MAIS uma chamada genérica minha com id de B na URL (sessão A, token A, anônimo) e, nos POST de
   criação, corpo com `tenant_id`/`inquilino` de B; conferência final como `postgres` (fora da RLS) do md5 das linhas de
   B que eu criei.
5. Cláusulas (d)/(e) e segurança básica: script próprio `seguranca_viva.py` (cookie, cabeçalhos, XFF forjado, CSRF,
   token no log com IP/rota/bytes, `?token=` em `/api/`, contagem do middleware, política de senha, bloqueio 5/15,
   TOTP com repetição/passo+10/recuperação, cookie alterado/reusado, inquilino temporário com `config.auth` para provar
   expiração configurável, latências, journal sem segredo). Limite do nginx medido de OUTRO IP (GPU box) para não
   derrubar os logins do e2e de outro agente na mesma máquina.
6. `\df+`-equivalente por `pg_proc × aclexplode` (EXECUTE para PUBLIC = 0) e leitura do corpo das funções.
7. Apaguei o resíduo que dois abortos do meu próprio roteiro deixaram em `demo2`/`demo` (usuários 450/460, grupos,
   papéis 80/84/90, tokens 311/312/316/352, 3 agendas, 2 jobs cancelados). Não toquei no resíduo de outros.

## Evidência (comando + saída literal)

### 1. Repositório e suíte

```
$ git log --oneline | head -3
ad2ea29 Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores
38430b2 Medidas do item L0-02-tenant-auth (backend): rotas 56/56 cobertas, login 129 ms, auth por token 2,94 ms, log 0,98 ms, revogação 0,01 s
441069c ADR 0005: ingestão vetorial (T2, preparação do L0-04)
$ git status --short          (árvore NÃO limpa durante toda a rodada: trilha B editando ao vivo)
 M app/jobs/contexto.py  M app/jobs/rotas.py  M docs/openapi.json  M tests/api/cruzado_casos.py
 M tests/api/eventos_esperados.py  M tests/api/test_saude.py  M tests/medidas/L0-01-repo.json  ?? db/migracoes/007_jobs_eventos.sql

$ make lint            exit=0 (0,01 s)          $ make sem-marcador   exit=0
$ make teste  (1ª, 16:02:35Z)  ..FF.......FF.......FFFFFF............FFFF..........FFF..............F.. [35%] ... make: *** Terminated
                               -> SIGTERM externo aos 77,5 s (não foi OOM: dmesg sem "Killed process"; outro agente da
                               mesma sessão rodava `make check` no mesmo instante, scratchpad/run_check.sh)
$ make teste  (2ª, 16:32Z)     2 failed, 407 passed, 21 deselected, 4 warnings in 103.44s   rss_max=205 MB
  FAILED tests/api/jobs/test_jobs_fila.py::test_100_jobs_executados_exatamente_uma_vez            -> OUTRA TRILHA (B)
  FAILED tests/api/test_usuarios.py::test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga        -> TRILHA A, ver abaixo
    E  AssertionError: ({'perfil': 'editor'}, '{"erro":"possui_grupos","mensagem":"rebaixar quem possui grupos: transfira os grupos antes","detalhe":[{"id":"0c7d185a-…","nome":"GrupoB"}
    causa: plat.grupo "GrupoB" em demo2, dono = admin de demo2, criado 2026-09-05 16:03:38 UTC; `grep -rn GrupoB tests/` = 0
    (não é de nenhum teste do repositório; script de outro agente). O código responde 409 possui_grupos ANTES de 409
    ultimo_admin; o teste só aceita ultimo_admin|proprio_usuario. Resíduo + ordem de checagem = teste frágil.
$ make e2e  (16:03:53Z–16:27:41Z)   7 failed, 14 passed, 409 deselected in 1427.94s (0:23:47)   rss_max=166 MB
  FAILED tests/api/jobs/test_jobs_progresso.py, test_jobs_reinicio.py ×3, tests/e2e/test_tarefas.py ×3   -> OUTRA TRILHA (B), todas
  passaram (trilha A): tests/e2e/test_login.py ×2, test_2fa, test_conta, test_usuarios, test_grupos, test_papeis, test_tokens, test_log_acesso, test_saude_pagina
```

Nota sobre o número de rotas: o handoff 30 mediu 56 rotas com `PLAT_OPENAPI_ARQUIVO` = cópia só da trilha A. O
OpenAPI comitado em HEAD e o vivo têm **73 rotas / 54 caminhos** (iguais entre si: `so_comitado=[] so_vivo=[]`). As 17
rotas `/api/jobs*`/`/api/agendas*` estavam SEM caso em `cruzado_casos.py` em HEAD; o caso delas está na árvore, NÃO
comitado (diff da trilha B, 33 linhas com jobs/agendas). Por isso a 2ª rodada do `make teste` deu 407 e não os 384 do
handoff 30.

### 2a. RLS (consulta própria, 16:03Z)

```
relname|relkind|relrowsecurity|relforcerowsecurity|tem_tenant_id
agenda r t f t · evento p t f t · evento_y2026m09..12 r t f t · grupo r t f t · grupo_membro r t f t · job r t f t · job_log r t f t
log_acesso p t f t · log_acesso_y2026m09..12 r t f t · papel_personalizado r t f t · sessao r t f t · token_servico r t f t · usuario r t f t
papel_privilegio r t f f (política via papel_personalizado) · senha_historico r t f f (via usuario) · tenant r t f f (id = tenant_atual())
privilegio f · perfil_privilegio f · evento_tipo f · versao_migracao f · worker f   <- vocabulário/infra sem tenant_id
tabelas com tenant_id e SEM rls: (vazio)
WITH CHECK: p_grupo_inserir (a) = (tenant_id = plat.tenant_atual()); demais '*' = mesma expressão do USING
donos: todas postgres; roles plat_app/plat_worker rolsuper=f rolbypassrls=f
```

`relforcerowsecurity = f` em todas: irrelevante para `plat_app` (não é dono), mas as funções `SECURITY DEFINER` rodam
como `postgres` (dono) e ATRAVESSAM a RLS — por isso a checagem de inquilino dentro delas (cláusula herdada) é o que
segura; ver 2e.

### 2b. Navegador (capturas lidas a olho, 9 arquivos, 16:18–16:27Z)

login (formulário, "análise / beta privado"), login_erro ("inquilino, usuário ou senha inválidos" em vermelho, sem
distinguir causa), 2fa (Minha conta com 2FA "ligado", 8 códigos de recuperação, sessão com IP 216.238.123.14),
conta (2FA desligado, 2 sessões, "Encerrar"), usuarios (3 usuários e2e, botões Editar/Redefinir/Desabilitar/Apagar,
recomendação de 2 admins), grupos (painel Membros com dono ativo + convidado), papeis (4 perfis com 46/26/7/11
privilégios, 20 administrativos; papéis personalizados), tokens (lista com prefixo, escopo, expira, último IP,
revogar), log (24.915 linhas, filtros, CSV, coluna bytes/ms/resultado). **Dois defeitos visíveis, que o e2e não pega
porque só confere console/HTTP:**
- `L0-02-tenant-auth_2fa.png`: os avisos das seções Sessões e Convites mostram a chave crua **`conta.apos_pendencia`**
  (`web/js/auth/conta.js:72` usa `t('conta.apos_pendencia')`; a chave NÃO existe em `pt-BR.json` — verificador
  próprio: 306 chaves usadas, 363 no JSON, 1 ausente).
- `L0-02-tenant-auth_log.png`: botões da paginação mostram **`paginacao.anterior` / `paginacao.proxima`** cruas (as
  chaves existem; `plat-paginacao.connectedCallback` chama `t()` na importação de `componentes.js`, antes do `await
  carregar()` da tela — `atualizar()` só reescreve a faixa "1–50 de N", não os botões).
- Resíduo de teste visível na demo: tela Tokens com 131 tokens (`zt-*`, `plat_*`), Papéis com 13 `zt-*`, Grupos com 4
  `zt-cruzado-*` (suítes interrompidas não limpam; `plat.tenant` tem 7 inquilinos `zt-inq-*` ativos sem rota de apagar).

### 2c. Cruzado A→B em TODAS as rotas do OpenAPI vivo (`varredura_viva.py`, 16:30Z, 29 s)

```
{'rotas_total': 73, 'rotas_com_caso_backend': 73 (árvore; em HEAD seriam 56), 'rotas_varridas_por_mim': 73,
 'chamadas': 411, 'linhas_de_B_que_mudaram': {}}
distribuição: sessao_A 200×18 201×3 204×1 400×1 401×17 404×30 409×2 410×1 · token_A 200×15 201×4 204×1 401×1 403×16 404×35 410×1
 sessao_A+X-Plat-Inquilino 200×3 204×1 401×16 403×48 404×4 410×1 · anonimo 200×3 204×1 401×64 404×4 429×1
 generica_sessao_A 401×9 404×27 422×1 · generica_token_A 403×5 404×27 422×5 · generica_anonimo 401×35 404×2 · POST_com_tenant_de_B 201×2 401×4 404×1 422×1
```

Os 2xx, um a um: sessão/token de A em rotas `proprio` (`/api/eu*`, listas, `/api/privilegios`, `/api/papeis`,
`/api/tokens?todos=1`, `/api/log?usuario_id=<B>` e `/api/eventos?ator_id=<B>` com `total = 0`), sem nenhuma marca de B
(login/grupo/papel/prefixo/"demo2"/ids de job e agenda); POST `/api/grupos`, `/api/papeis`, `/api/tokens` com o MESMO
nome de B criam em A (apagados por A a seguir = estavam em A); `X-Plat-Inquilino` de não-superadmin = 403 em 48 rotas e
2xx só nas públicas (`/saude`, `/api/versao`, `/api/login/provedores`, `/api/logout`); `POST_com_tenant_de_B` 201 em
`/api/jobs` e `/api/agendas` com `tenant_id` de B no corpo → `SELECT tenant_id` como postgres = 1 (A), não 2. O script
marcou 7 linhas "2xx indevidas", todas falsos positivos meus: eco de "demo2" em `/api/login/provedores?inquilino=demo2`
(só slug+nome, público por ADR) e eco do nome na criação em A. **2xx cruzados reais = 0 em 411 chamadas; md5 das
linhas de B intacto.** Anônimo em `/api/plataforma/*` = 404 (ADR 10: superadmin responde 404 para não confirmar a rota).

### 2d. Token de serviço no log

```
log_acesso do token 353 (URL pública):
GET /api/eu | status=200 | bytes=1694 | ip=216.238.123.14 | token_id=353
GET /api/usuarios | status=403 | bytes=182 | ip=216.238.123.14 | token_id=353   (escopo catalogo:ler -> escopo_insuficiente)
token_valor_no_log_ou_rota = 0 · GET /api/eu?token=<valor> -> 401 nao_autenticado, rota gravada "/api/eu?token=%3Credigido%3E"
revogação: DELETE -> GET com o token 0,02 s depois = 401 token_revogado
amostra geral: 30.876 linhas, ip NULL = 0, bytes NULL = 0; linhas 200 em /api/* sem usuario_id e sem token_id = 0
```

### 2e. Herdadas do T1

```
pg_proc plat: total=60 secdef=51 com_public=0 acl_nula=0 grantee_fora_de_plat_app/plat_worker/postgres=0
default privileges do schema plat: plat_app=X (funções) — logo função nova nasce sem PUBLIC
checam contexto (corpo lê contexto_confere/tenant_atual/so_superadmin/plataforma_operador): auth_sessao_criar, auth_falha, auth_ok,
 auth_desafio_2fa_criar, contexto_confere, evento_registrar, log_registrar, log/evento_particao_garantir, sessoes_encerrar_usuario,
 tenant_criar/listar/suspender, plataforma_operador/tenant_id, job_cancelar, job_progresso, jobs_expurgar
NÃO checam (pré-contexto, chave = segredo): auth_login(slug,login) [só lê por slug+login; devolve senha_hash para o app comparar],
 auth_sessao(hash), auth_token(hash,ip), auth_desafio_2fa_resolver(hash), auth_sessao_encerrar(hash), tenant_publico(slug), *_expurgar,
 gatilhos tg_*, e as 14 da trilha B só para plat_worker (agenda_*, job_pegar/heartbeat/terminar/devolver/ceifar, worker_*)
```

O portão nomeia `auth_login` entre as que "checam o inquilino do contexto"; ela não pode (roda antes de haver
contexto) — o que ela faz é filtrar por `t.slug = p_tenant AND u.login = lower(p_login)`, e o contexto nasce depois em
`auth_sessao_criar`, que checa. Registro como PASSA por leitura, com a ressalva de que a cláusula está escrita de forma
mais forte do que o mecanismo permite.

```
middleware: log_acesso antes=35354 depois=35476 (delta 122 para as minhas 8 requisições + o que o e2e de outro agente gravou no mesmo 1,5 s)
senha: curta_7 -> 422 senha_fraca/minimo · so_letras -> 422/composicao · so_digitos -> 422/composicao · igual_login -> 422/igual_login
       ok_8 -> 204 · voltar à temporária -> 422/historico
bloqueio: 401 401 401 401 401 423 {"erro":"bloqueado","mensagem":"usuário bloqueado até 2026-09-05T16:46:14Z"} (6ª com senha CERTA)
          POST /usuarios/{id}/desbloquear -> 204; login -> 200. tempo constante inexistente × errada = 121,7 × 123,2 ms
TOTP: confirmar 000000 -> 401 codigo_invalido · confirmar certo -> 200 + 8 códigos · login -> {exige_2fa: true, sem "usuario"} ·
      /2fa certo -> 200 · MESMO código em novo desafio -> 401 codigo_invalido · passo +10 -> 401 · recuperação 1ª -> 200, 2ª -> 401 ·
      desafio falso -> 410 · banco: totp_ativo=true, totp_secret começa por "enc:v1:"
expiração configurável: inquilino zt-cfg-177f2d criado por POST /api/plataforma/inquilinos com config.auth {sessao_max_dias:1,
      sessao_ociosa_horas:1, token_max_dias:2, token_padrao_dias:1, bloqueio_tentativas:3} ->
      sessão criado 16:31:31 expira 2026-09-06T16:31:31 (1 d) ociosa_ate 17:31:31 (1 h) · token validade 3 -> 400 validade_acima_do_maximo
      {maximo_dias: 2} · token sem validade -> expira 2026-09-06 (1 d) · 401 401 401 423 (3 tentativas) · suspender -> login 503
      ⛔ NÃO é por .env: `app/settings.py` não tem chave de expiração; é `tenant.config.auth` (ADR seção 11, `app/limites.py`
      AUTH_PADROES) e só se grava na criação do inquilino ou por psql (PUT /api/inquilino/config é do L0-07-a).
```

### 3. Segurança básica no ar

```
Set-Cookie: plat_sessao=<redigido>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure   (64 hex; banco guarda só sha256: 0 linhas com o valor)
cabeçalhos em /api/eu: Strict-Transport-Security max-age=31536000 · X-Content-Type-Options nosniff · X-Frame-Options DENY ·
  X-Robots-Tag noindex,nofollow · Cache-Control no-store,must-revalidate · x-req-id   (Referrer-Policy declarado no server{} mas
  NÃO chega em /api/* nem em /entrar: os add_header do location cancelam os herdados e o conjunto repetido omite Referrer-Policy;
  sem Content-Security-Policy)
X-Forwarded-For forjado pelo cliente (10.9.9.9) via nginx -> ip gravado 216.238.123.14 (uvicorn 0.27.1 pega o último não confiável)
CSRF sob cookie: form sem JSON -> 415 tipo_nao_aceito · Origin https://atacante.example -> 403 origem_invalida ·
  Origin https://plat.iagrointel.com.atacante.example -> 403 · JSON SEM Origin -> 201 (ADR 5.3: Origin só é conferido quando vem;
  a barreira do POST sem Origin é o Content-Type JSON + SameSite=Lax) · form sem Origin -> 415
cookie alterado 1 char -> 401 · cookie reusado após logout -> 401
nginx /api/login de OUTRO IP (GPU box), 25 POST em 15 s: 401 401 401 429 429 429 429 429 401 429 ... (10 r/min, burst 10; corpo do 429 é o
  HTML do nginx, não JSON); /api/login/2fa idem; 10 GET /api/eu anônimos = 401 (sem limite)
?token= em /api/eu -> 401 e redigido (só /svc/ /ogc/ /tiles/ aceitam; ainda não existem)
journal plat-api 15 min (1.034 linhas): senha do admin, cookie e tokens = ausentes; log_acesso.rota = 0 ocorrências
```

### 4. Medições

```
login 20× direto no uvicorn: mediana 129,2 ms · p95 145,4 · máx 156,6   (3× pela URL pública: 142,9 141,7 146,0)
auth por token: GET /api/eu Bearer 3,67 ms − GET /api/versao 1,17 ms = 2,50 ms
revogação -> 401: 0,02 s · plat-api MemoryCurrent 122.781.696 bytes (117 MiB, mestre + 2 workers) · RSS do mestre 25,5 MB
rotas cobertas pela varredura cruzada: 73/73 (vivo) · placeholders = 0 · nomes de cliente = 0
```

### 5. `make medidas` e commit

```
$ make medidas   (PLAT_GRAVAR_MEDIDAS=1 pytest --base-url https://plat.iagrointel.com; 16:34:08Z–16:47:39Z)
6 failed, 424 passed, 4 warnings in 799.53s (0:13:19)   rss_max=213 MB
  FAILED tests/api/jobs/test_jobs_fila.py, test_jobs_reinicio.py, test_jobs_rls.py ("efeito parcial de prova.progresso sobrou: 99 == 0"),
         tests/e2e/test_tarefas.py::test_primeira_pintura_com_mil_jobs                                     -> OUTRA TRILHA (B)
  FAILED tests/api/test_usuarios.py::test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga                  -> TRILHA A (mesmo resíduo GrupoB)
  FAILED tests/api/test_log_acesso.py::test_rotas_excluidas_nao_geram_linha  E assert 1128 == 1129           -> TRILHA A: o nº de linhas de
         demo DIMINUIU em 1 durante o teste (algo apagou log_acesso ao mesmo tempo); contagem absoluta é frágil com outro agente no banco
$ venv/bin/python mesclar_medidas.py -> chaves: 35 (16 do backend preservadas: rotas_total=73, rotas_cobertas=73, latencia_login_ms=128.7,
  pagina_pronta_ms_{login 51.5, conta 40.7, usuarios 130.5, log 113.4, ...}, tempo_revogacao_ms_e2e=6.3 + 19 testador_*)
$ git commit 12b2c2e  (só tests/medidas/L0-02-tenant-auth.json)
  capturas NÃO comitadas: `.gitignore:5 tests/e2e/capturas/*.png` — o repositório ignora todas as capturas por regra própria;
  as 9 regeneradas às 16:45–16:47Z ficam em disco (`ls -la tests/e2e/capturas`)
```

## Riscos

1. **Árvore compartilhada e em mutação**: 7 arquivos alterados e a migração 007 aplicada no banco (16:04Z) SEM commit,
   por outra trilha, durante a minha rodada; o serviço no ar é HEAD `ad2ea29` mas o banco já tem 007. Nada do que medi
   é reprodutível a partir de HEAD sozinho até a trilha B comitar.
2. **Interferência entre agentes**: meu 1º `make teste` foi morto por SIGTERM; outro agente esperou o meu e2e e rodou
   o dele em seguida; o e2e de ambos passa pelo mesmo limite de IP do nginx. Um `pkill pytest` de qualquer agente
   derruba a rodada do outro.
3. **Resíduo de teste no banco cresce a cada rodada interrompida** (tokens ativos em demo: 24; 7 inquilinos `zt-inq-*`
   ativos sem rota de apagar; `GrupoB` de origem externa faz `test_ultimo_admin` falhar). A suíte não é idempotente
   sobre a demo.
4. Duas chaves de i18n cruas na tela (2b) passam pelo e2e porque a cláusula "0 erro de console" não olha texto.
5. Referrer-Policy some por causa da armadilha do `add_header` que o próprio `deploy/nginx.conf` documenta.

## Pendências

1. Frontend: `conta.apos_pendencia` no `pt-BR.json`; `plat-paginacao` traduzir os botões em `atualizar()` ou após
   `carregar()`. Backend/frontend: Referrer-Policy repetido nos `location` do `deploy/nginx.conf`.
2. Trilha B: comitar os casos de jobs/agendas (sem eles HEAD tem 20 testes vermelhos, como o handoff 30 já disse).
3. Gerente: a cláusula "expiração configurável" está PROVADA por `tenant.config.auth`, não por `.env` como o pedido
   deste turno dizia; a tela para mudar depois de criado é do L0-07-a.
4. Limpeza da demo (tokens/papéis/grupos/inquilinos `zt-*`) antes de qualquer demonstração; rota ou CLI para apagar
   inquilino de teste (L0-05-d/L0-07).

## Para o próximo papel

**Adversário (50)**: repita 2c com o seu próprio script — o meu está em
`/tmp/claude-1001/-home-dev/a44f35ad-ead9-4a5b-9329-6c154aa35f9e/scratchpad/t40/varredura_viva.py` e o resultado
em `varredura_viva.json` (411 chamadas). Onde eu não cheguei: (i) B chamando rotas de A com token de B que tenha
`admin:inquilino` (só fiz A→B); (ii) sessão de superadmin com `X-Plat-Inquilino` lendo B — provei só que NÃO-superadmin
recebe 403; (iii) concorrência de 2 workers no contador de bloqueio (ADR 16.6 admite); (iv) `?token=` em `/svc/`
`/ogc/` `/tiles/` (não existem ainda); (v) o ramo `DROP + CREATE` de `log_acesso` quando `count(*) = 0` (30_backend
item 1, último tópico) — apagar dado de log em migração merece olhar. Use outro IP para força bruta pelo nginx.

**Gerente (99)**: cláusulas do portão próprio (a)(b)(c)(d) PASSAM; herdadas PASSAM com a ressalva de `auth_login`
(pré-contexto) e de "configurável" = por inquilino; P1 PASSA com defeito visível de tradução em 2 telas (decida se
reprova P1 ou abre pendência); P3 NÃO PASSA em HEAD (falhas da trilha B + `test_ultimo_admin` por resíduo); P9 NÃO
PASSA ainda (MANUAL/CHANGELOG/ARQUITETURA sem o L0-02; cronista não rodou); P4 não conferi (não há `21_esri.md` nesta
trilha e `docs/PARIDADE.md` não tem a seção 17 do ADR).

## Tabela cláusula → evidência → veredito

| cláusula | evidência | veredito |
|---|---|---|
| (a) tenant/usuario/sessao/token/permissao com RLS ativa | 2a: 22/22 tabelas e partições com `tenant_id` têm `relrowsecurity=t`; `papel_privilegio`, `senha_historico`, `tenant` com política por junção; 0 sem RLS | PASSA |
| (b) login/logout/2FA/troca de senha/usuários no navegador, e2e com captura | 9 e2e verdes no `make e2e`; 9 capturas lidas (2b) | PASSA (com 2 chaves i18n cruas: pendência 1) |
| (c) A não lê nem edita B em NENHUM endpoint | 2c: 73/73 rotas do OpenAPI vivo, 411 chamadas, 0 × 2xx cruzado real, md5 das linhas de B intacto | PASSA |
| (d) token de serviço no log com IP/rota/bytes | 2d: 2 linhas do token 353 com ip=216.238.123.14, rota, bytes 1694/182; revogado em 0,02 s; valor redigido | PASSA |
| (e1) SECURITY DEFINER checa inquilino; EXECUTE só plat_app/plat_worker | 2e: 51 secdef, 0 PUBLIC, 0 grantee estranho; as com contexto obrigatório checam; `auth_login`/`auth_sessao`/`auth_token` são pré-contexto por chave-segredo | PASSA com ressalva de redação |
| (e2) middleware grava log_acesso por requisição autenticada | 2e: delta ≥ 8 nas minhas 8; 0 linhas 200 em /api/* sem usuário e sem token; ip/bytes nunca NULL em 30.876 | PASSA |
| (e3) senha ≥ 8 com letra e número | 2e: 4 recusas com `detalhe.regra` nomeada, 1 aceita, histórico recusa | PASSA |
| (e4) 6ª tentativa em 15 min bloqueada | 2e: 401×5 depois 423 com `bloqueado_ate` na 6ª CERTA; 3 tentativas quando `bloqueio_tentativas=3` | PASSA (423, como o ADR) |
| (e5) expiração de sessão/token configurável | 2e: inquilino com `sessao_max_dias=1`, `token_max_dias=2` muda `expira_em` e recusa validade 3 | PASSA por `tenant.config.auth`; NÃO por `.env` |
| (e6) MFA TOTP por usuário: ligar, entrar, repetido recusado | 2e: 200 → 401 no mesmo código; passo +10 → 401; recuperação 2ª → 401 | PASSA |
| nginx 10 r/min em /api/login → 429 | 3: 429 de outro IP após o burst; 2fa idem | PASSA (429 é HTML do nginx, não JSON) |
| cookie HttpOnly/Secure/SameSite; CSRF | 3: atributos presentes; form → 415, Origin estranha → 403; JSON sem Origin passa (ADR 5.3) | PASSA conforme ADR |
| `?token=` só fora de /api/ | 3: 401 + redigido em /api/eu | PASSA (o "fora" ainda não existe) |
| P1 funciona no navegador, 0 erro de console | e2e 9/9; capturas | PASSA com defeito visível de i18n |
| P2 sem placeholder | 0 (regex do driver, inclusive tests/) | PASSA |
| P3 suíte inteira verde | make teste 2 falhas (1 A por resíduo, 1 B); make e2e 7 falhas (B); make medidas 6 falhas (4 B, 2 A: resíduo GrupoB e contagem de log_acesso sob concorrência) | NÃO PASSA |
| P4 paridade declarada e testada | sem `21_esri.md`; PARIDADE.md sem seção | NÃO CONFERIDO |
| P5 reprodutível | não reinstalei do zero (o adversário fará; RAM baixa); migrações 003 idempotente segundo o backend | NÃO CONFERIDO POR MIM |
| P6 multi-inquilino e segurança | (a)(c)(d)(e) acima | PASSA |
| P7 dado aberto, sem nome de cliente, sem PII | grep = 0; demo só com dados sintéticos | PASSA |
| P8 adversário | ainda não rodou | PENDENTE |
| P9 documentado | MANUAL/CHANGELOG/ARQUITETURA sem L0-02; openapi.json comitado = vivo (73) | NÃO PASSA ainda |
