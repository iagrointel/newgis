# Ataque adversarial ao grupo G1 — identidade, sessão, segundo fator, senha, token, LDAP

Adversário independente, turno 3, 06/09/2026. Não construí nada disto e não aceitei nenhuma
afirmação sem reproduzir com comando e saída. Não consertei nada: cada achado virou teste com
`@pytest.mark.xfail(strict=True)`, que vira prova no dia em que alguém consertar.

- Testes escritos: `tests/api/test_ataque_g1_adversario.py` e `tests/api/ldap/test_ataque_g1_ldap.py`
  (worktree `/home/dev/plataforma/wt/adv1`, ramo `wt/adv1`).
- Base própria: `bash laco/trilha_ambiente.sh adv1` → schema `plat_tadv1`. Nada rodou contra `plat`
  de produção, exceto as CONSULTAS de leitura em `pg_proc` que o próprio teste do item faz.
- Resultado da rodada: **12 passaram, 16 xfailed** (16 achados).

## (a) Veredito item a item

| item | veredito | cláusula do portão que caiu |
|---|---|---|
| L0-02-a-login-sessao | **REFUTADO** (gravidade baixa) | "sessão com ultimo_uso > 12 h devolve 401 **e a linha é apagada pelo periódico**" — o 401 acontece, a linha não sai |
| L0-02-b-politica-senha-bloqueio | **REFUTADO** (gravidade média) | mínimo de senha é 8, não os 10 da hipótese; expiração de senha não vale para quem tem 2FA |
| L0-02-c-2fa-totp | **REFUTADO** (gravidade média) | "usuário sem 2FA cai na tela de configuração **antes de qualquer rota**" — 7 rotas vivas passam por cima da pendência |
| L0-02-d-token-servico | **REFUTADO** (gravidade baixa) | "prefixo de 8 caracteres na lista" — o prefixo tem 12. Todo o resto do portão aguentou |
| L0-02-e-varredura-cruzada-rls | **REFUTADO** (gravidade ALTA) | "pg_proc mostra proacl sem PUBLIC para todas as funções SECURITY DEFINER" (falso hoje) e "cobertura 100 % é cláusula" (o teste reprova hoje; a cobertura real é 155 de 196 rotas vivas = 79,1 %) |
| L0-02-f-tela-usuarios | NÃO REFUTADO | nenhuma cláusula literal caiu sob ataque |
| L0-02-g-perfil-usuario | NÃO REFUTADO (portão literal) | um achado fora do portão: `visibilidade_perfil` é gravada e nunca é aplicada |
| L0-08-d-ldap | **REFUTADO** (gravidade ALTA) | identidade local nasce do texto cru do cliente; a partir daí o login canônico fica trancado com 409; o escape de filtro nunca é exercitado; sem limite por IP na borda; TLS não testado |

**6 de 8 refutados.** Dois de segurança real: **G1-T2** (funções SECURITY DEFINER executáveis por
PUBLIC no schema `plat` de produção) e **G1-l3** (uma requisição não autenticada tranca a conta
legítima de um usuário de diretório).

## (b) Suposições transversais

Escritas antes de olhar item por item, e atacadas primeiro. Três caíram e cada uma derruba mais de
um item.

### T1. "A prova de cobertura é medida sobre o sistema que existe" — CAIU

O portão do L0-02-e diz "cobertura 100 % é cláusula, medida em `tests/medidas/L0-02-e.json`:
rotas_total = rotas_cobertas". A medida é 138 = 138. Mas `rotas_total` vem de `docs/openapi.json`,
um retrato PARADO no repositório, e `make check` (`lint sem-marcador limites teste e2e`) não roda
`make openapi` nem tem teste algum que compare o arquivo com `app.openapi()`.

```
$ venv/bin/python -c "..."   # app.openapi() × docs/openapi.json
vivo: 196   arquivo: 168
SÓ no app vivo (28): /api/convites{,/resolver,/aceitar}, /api/uploads*, /api/org/smtp*,
  /api/senha/redefinir/{solicitar,aplicar,resolver}, /api/sugerir, /api/geocodificar, /api/reverso,
  7 rotas /rest/services/Geocodificador/GeocodeServer*
SÓ no arquivo (0)
```

Consequência: a medida gravada (138 = 138) já não reproduz, e a de hoje é pior do que ela diz.
O mesmo arquivo parado alimenta `test_privilegios_declarados.py` e `test_eventos.py`, que também
ficam cegos. Derruba L0-02-e e explica G1-e1/e2/e3.

O próprio arquivo de medidas já se contradiz: `rotas_total` = 138 e
`testador_rotas_total_vivo` = 73, medidos com um dia de diferença.

### T2. "Toda função SECURITY DEFINER de `plat` é fechada a PUBLIC" — CAIU

Cláusula literal do portão do L0-02-e. Era verdade em 05/09 (`testador_secdef_sem_public`:
"0 com EXECUTE para PUBLIC"); é falsa hoje.

```
$ sudo -u postgres psql -d iagro_sat -X -A -F'|' -c "SELECT p.proname, p.prosecdef, ... WHERE
  p.pronamespace='plat'::regnamespace AND EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee=0)"
convite_aceitar|t|=X/postgres,postgres=X/postgres,plat_app=X/postgres
convite_resolver|t|=X/postgres,...
redefinicao_contexto|t|=X/postgres,...
redefinicao_resolver|t|=X/postgres,...
redefinicao_solicitar|t|=X/postgres,...
uploads_expirar_candidatos|t|=X/postgres,...
(mais 7 sem SECURITY DEFINER: amc_*_guarda, redefinicao_marcar_usada, tg_conexao_atualizado_em,
 upload_reservado_bytes)
```

Causa: `db/migracoes/046_upload_retomavel.sql` e `047_smtp_convites_redefinicao.sql` fazem
`GRANT EXECUTE ... TO plat_app` sem o `REVOKE EXECUTE ... FROM PUBLIC` que 003/006/024 usam.
O banco `iagro_sat` é compartilhado com dezenas de outros papéis de aplicação (cbresig_app, fgr,
etc.): PUBLIC aqui não é abstrato.

O teste do próprio item pega isso e **está vermelho na árvore entregue**:

```
$ venv/bin/pytest tests/api/test_funcoes_seguras.py -q
FAILED tests/api/test_funcoes_seguras.py::test_nenhuma_funcao_com_execute_para_public
E   AssertionError: assert ['tg_conexao_...licitar', ...] == []
E     Left contains 9 more items, first extra item: 'tg_conexao_atualizado_em'
```

Ou seja: o portão P6 do L0-02-e reprova hoje, e o item continua marcado `entregue`.

### T3. "O que está entregue é reproduzível a partir do repositório" — CAIU

```
$ cd /home/dev/plataforma/enterprise && git show master:app/main.py | grep -n "rotas_convites\|correio\|uploads"
19:    rotas_convites,
26:    rotas_redefinicao,
42:from app.correio.rotas_smtp import router as rotas_smtp
51:from app.uploads.rotas import router as rotas_uploads
$ git ls-files app/auth | grep -c "rotas_convites\|rotas_redefinicao"
0
$ git status --short | grep '^??'
?? app/auth/rotas_convites.py  ?? app/auth/rotas_redefinicao.py  ?? app/auth/modelos_convite.py
?? app/auth/modelos_redefinicao.py  ?? app/correio/  ?? app/uploads/  ?? app/migracoes.py
```

O commit `master` 90ab545 **não importa**: `from app.main import app` levanta
`ImportError: cannot import name 'rotas_convites'`. Um checkout limpo não sobe a API, logo nenhum
portão deste grupo é reproduzível a partir do repositório. Tive de trabalhar sobre um instantâneo
da árvore de trabalho (`rsync` de `enterprise/` para `wt/adv1/`, sem `.git`), e digo isso porque
muda o que estas medidas provam: elas provam o SISTEMA QUE RODA, não o repositório.

### T4. "A política declarada por inquilino é aplicada onde é declarada" — AGUENTOU, com uma trinca

`sessao_ociosa_horas`, `bloqueio_tentativas`, `bloqueio_minutos`, `sessao_max_dias`,
`token_max_dias`, `dominios_email` e `exigir_2fa` são de fato lidos de `tenant.config.auth` e
aplicados (o corte 1–24 h vive dentro de `plat.auth_sessao`, não no Python — bem feito).
A trinca é `senha_expira_dias`, que só é avaliada no caminho de senha (achado G1-b2).

### T5. "Isolamento por inquilino" — AGUENTOU em tudo que consegui tentar

Cookie de A com `X-Plat-Inquilino: demo2` → 403 `so_superadmin`. Token de A com o cabeçalho → 403.
Admin de A criando usuário em B → 403. Token de A em rota de B → 403/404. As funções com contexto
obrigatório levantam `contexto_de_outro_inquilino`. O único ponto que ignora o cabeçalho é o
GeocodeServer (achado G1-c1), e ali não há dado de inquilino a vazar.

## (c) Item por item — comando e saída real

Ambiente de todos os blocos abaixo:
```
cd /home/dev/plataforma/wt/adv1
set -a; source /home/dev/plataforma/laco/var/trilha/adv1.env; set +a
```

### L0-02-a-login-sessao — REFUTADO em 1 cláusula

O que aguentou (teste `test_a_cookie_apos_logout_alterado_e_de_outro_inquilino`, passa):

```
 logout -> 204
 cookie reusado apos logout -> 401 sessao_expirada
 cookie com 1 caractere trocado -> 401
 cookie de demo + X-Plat-Inquilino demo2 -> 403
 set-cookie (https): plat_sessao=...; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure
 ocorrencias do token de sessao em plat.log_acesso: 0
 sessao com criado_em > 7 d -> 401
```

Medida (`test_a_medidas_de_login_e_sessao`, passa): **latência de login mediana 127,3 ms** em 20
logins (p95 131,4 ms), abaixo dos 400 ms do portão, com pbkdf2 de 600 mil iterações incluído.

**ACHADO G1-a1** (`test_a1_sessao_ociosa_alem_da_politica_some_no_periodico`):

```
 envelhece ultimo_uso para 13 h: UPDATE 1
 GET /api/eu -> 401
 linha ainda na tabela ANTES do periodico: 1
 sessoes_expurgar() apagou: 0
 linha ainda na tabela DEPOIS do periodico: 1
 agora com 25 h: 1  ->  sessoes_expurgar()=1  ->  linhas restantes 0
```

`plat.sessoes_expurgar()` (migração 003) apaga por `coalesce(ultimo_uso, criado_em) < now() -
interval '24 hours'`, número FIXO, enquanto a sessão deixa de valer pela política do inquilino
(12 h por padrão, 1 h no mínimo configurável). A cláusula é "devolve 401 **e** a linha é apagada
pelo periódico"; hoje o token morto fica no banco por até 24 h, e por até 23 h a mais que a
política do inquilino manda.

### L0-02-b-politica-senha-bloqueio — REFUTADO em 2 cláusulas

**ACHADO G1-b1** (`test_b1_senha_de_oito_caracteres_e_recusada`): a hipótese do item é "mínimo 10
caracteres com pelo menos uma letra e um número". O produto entrega 8:
`app/limites.py: "senha_min": (8, 8, 64)` e `app/auth/politica.py: senha_min: int = 8`.

```
 senha de 8 caracteres ('Abcdefg1') -> 204
```

O inquilino nem pode descer abaixo de 8, mas o padrão da plataforma é 8, não 10.

**ACHADO G1-b2** (`test_b2_expiracao_de_senha_vale_tambem_para_quem_tem_2fa`): com
`senha_expira_dias = 30` e a senha alterada há 60 dias, dois usuários do MESMO inquilino:

```
 SEM 2FA  -> pendencias ['trocar_senha']
 COM 2FA  -> pendencias []
```

`app/auth/rotas_login.py::login_2fa` chama `_abrir_sessao(..., senha_alterada_em=None)`, e a
verificação de expiração está dentro de `_abrir_sessao`, condicionada a esse parâmetro. Quem liga o
segundo fator recebe a política de senha mais fraca — o contrário do que se espera.

**Refutação literal do item — AGUENTOU** (`test_b_bloqueio_por_usuario_nao_nega_o_inquilino`):
"1.000 senhas em 3 min contra um usuário e contra 200 logins diferentes do mesmo inquilino".

```
 300 tentativas em 42,7 s -> 7,0 tentativas/s; extrapolado para 180 s = 1.264 tentativas; codigos {401: 300}
 admin do inquilino durante/depois do ataque -> 200
```

`plat.auth_falha` escreve `WHERE id = p_usuario`: o contador é da linha do usuário, nunca do
inquilino. O admin entra normalmente. **NÃO REFUTADO nesta cláusula.**

Fica registrado o que a cláusula NÃO cobre: cada tentativa custa ~123 ms de CPU (pbkdf2 600 mil,
medido também no caminho do usuário inexistente, que usa `HASH_FANTASMA` — tempo constante,
121,4 ms × 123,0 ms). A aplicação não tem freio próprio; o freio é do nginx
(`limit_req zone=plat_login rate=10r/m burst=10` em `location = /api/login` e
`location = /api/login/2fa`), e ele só existe se a requisição passar pela borda.

### L0-02-c-2fa-totp — REFUTADO em 1 cláusula

O que aguentou (`test_c_forca_bruta_replay_e_relogio`, passa):

```
   tentativa 1..5 -> 401 codigo_invalido
   tentativa 6    -> 423 bloqueado
 codigo com relogio +5 min (passo atual + 10) -> 401
 segredo no banco: enc:v1:Y...
```

**ACHADO G1-c1** (`test_c1_pendencia_de_2fa_fecha_tambem_o_geocodeserver`): inquilino novo com
`config.auth.exigir_2fa = true`, admin que já trocou a senha temporária e ainda não ligou o 2FA:

```
 /api/eu pendencias -> ['configurar_2fa']
 GET /api/usuarios                                              -> 403   (correto)
 GET /rest/.../GeocodeServer/suggest?text=rua                   -> 200   (a pendência não vale)
 GET /rest/.../GeocodeServer/findAddressCandidates?SingleLine=  -> 200
```

Causa em `app/geocodificador/rotas_esri.py::_autenticar`: chama `auth_sessao.resolver(request)`
direto em vez de `autenticado()`. Com isso as 7 rotas GeocodeServer ficam fora de três guardas de
uma vez — pendências (a cláusula deste portão), `checar_escrita_sob_cookie` (CSRF) e a checagem de
`X-Plat-Inquilino` (que ali responde 200 em vez de 403 `so_superadmin`). A cláusula literal é
"antes de qualquer rota".

### L0-02-d-token-servico — REFUTADO em 1 cláusula cosmética

O que aguentou (`test_d_escopo_restricao_revogacao_e_log`, passa):

```
  POST /api/itens com escopo catalogo:ler  -> 403
  GET  /api/itens com escopo catalogo:ler  -> 200
  validade_dias 400                        -> 400 validade_acima_do_maximo
  token com restrição ip 10.0.0.0/8, chamada de 127.0.0.1 -> 401 ip_nao_permitido
  referer https://*.exemplo.gov.br:
     Origin ausente                        -> 401
     https://a.exemplo.gov.br              -> 200
     https://a.b.exemplo.gov.br            -> 200
     https://exemplo.gov.br  (ápice)       -> 401
     https://mal.exemplo.gov.br.evil.com   -> 401
     http://a.exemplo.gov.br  (esquema)    -> 401
  antes de revogar -> 200; depois de revogar (0,011 s) -> 401 token_revogado "token revogado em ..."
  token de A + X-Plat-Inquilino demo2 -> 403
  campos da listagem: sem nenhum campo com 'hash'
  latência de requisição autenticada por token: mediana 4,77 ms (rota /api/eu inteira)
```

O log por token também confere (`test_d_leitura_por_token_aparece_no_log_com_token_id`, passa):
`GET /api/tokens/{id}/log` traz linhas com `ip`, `rota`, `bytes`, `status`.

**ACHADO G1-d1** (`test_d1_prefixo_do_token_tem_oito_caracteres`): o portão pede "prefixo de 8
caracteres na lista"; `app/auth/rotas_tokens.py::_inserir` grava `prefixo = valor[:12]`.

```
  prefixo='plat_PaOpofX' len=12 ; token len=48
```

São 7 caracteres do próprio segredo guardados em claro num campo que a listagem devolve. Não é
exploração (restam 36 caracteres de `secrets.token_urlsafe(32)`), mas é a cláusula literal e é
entropia dada de graça. Gravidade baixa; nenhuma outra cláusula do item caiu.

### L0-02-e-varredura-cruzada-rls — REFUTADO (o mais grave)

Além de T1 e T2 acima, varri à mão as 28 rotas vivas que a varredura não conhece, com quatro
identidades (anônimo, sessão de A, token de A com `admin:inquilino`, sessão de A +
`X-Plat-Inquilino: demo2`). Nenhuma vazou dado de outro inquilino — o isolamento aguentou. Três
outras coisas apareceram:

**ACHADO G1-e1** — `GET /api/uploads/tipos` declara `x-auth: S/T` e responde sem credencial:
```
 anon /api/uploads/tipos -> 200 [{"tipo":"shapefile.zip",...
 anon GET /rest/services/Geocodificador/GeocodeServer -> 200
```

**ACHADO G1-e2** — as 7 rotas `/rest/services/Geocodificador/GeocodeServer*` não declaram
`x-privilegio`. Existe teste para reprovar isso (`test_privilegios_declarados.py`), e ele não vê
as rotas porque lê o arquivo parado.

**ACHADO G1-e3** — duas rotas fora da varredura devolvem 500:
```
 DELETE /api/convites/1  (sessão de A) -> psycopg2.errors.InvalidTextRepresentation:
   invalid input syntax for type uuid: "1"
 PUT /api/org/smtp  (corpo {})         -> psycopg2.errors.ForeignKeyViolation:
   Key (tipo)=(org/smtp_remover) is not present in table "evento_tipo"
```
A varredura cruzada aceita só 401/403/404 e teria pego as duas. É a prova do custo de T1.

**O teste de cobertura do portão reprova hoje, na sua própria régua:**

```
$ venv/bin/pytest tests/api/test_cruzado.py::test_cobertura_100_por_cento
E  AssertionError: rotas sem caso cruzado: [('DELETE', '/api/importacoes/{id}'), ('GET', '/api/importacoes'),
   ('GET', '/api/importacoes/formatos'), ('GET', '/api/importacoes/{id}'), ('GET', '/api/itens/{id}/metadado.xml'),
   ('GET', '/ogc/records'), ('GET', '/ogc/records/collections'), ... ]  (13 rotas)
1 failed
```

Medida do adversário (`test_e_medida_da_cobertura_real`, passa):
`adversario_rotas_vivas` = **196** · `adversario_rotas_vivas_cobertas` = **155** →
**cobertura real 79,1 %; 41 rotas vivas sem caso cruzado**. A medida gravada no repositório diz
138 = 138 e 100 %.

### L0-02-f-tela-usuarios — NÃO REFUTADO

Refutação literal do item, item por item (`test_f_editor_admin_cruzado_e_ultimo_admin` e
`test_f_desabilitado_perde_a_sessao_em_menos_de_um_segundo`, os dois passam):

```
 editor POST /api/usuarios                       -> 403
 editor PUT /api/usuarios/<outro> {perfil: admin} -> 403
 editor POST /api/usuarios/lote                   -> 403
 admin de A cria usuário com X-Plat-Inquilino demo2 -> 403 so_superadmin
 desabilitar a própria conta admin  -> 409 proprio_usuario "não se desabilita a própria conta"
 rebaixar o ÚLTIMO admin ativo      -> 409 ultimo_admin "é o último administrador ativo; nomeie outro antes"
 lote com 101 ids                   -> 422
 usuário desabilitado, próxima requisição (0,011 s) -> 401
```

Nada caiu.

### L0-02-g-perfil-usuario — NÃO REFUTADO no portão literal

Refutação literal (`test_g_foto_email_e_campos_nao_editaveis`, passa):

```
 foto SVG com <script>       -> 415 formato_nao_aceito
 foto de 1,2 MB              -> 422
 PUT /api/eu {login: ...}    -> 400 campo_nao_editavel
 PUT /api/eu {perfil: admin} -> 400 campo_nao_editavel
 PUT /api/eu {papel_id: 1}   -> 400 campo_nao_editavel
 PUT /api/eu {ativo: true}   -> 400 campo_nao_editavel
 e-mail fora dos domínios    -> 422 email_dominio "e-mail fora dos domínios permitidos do inquilino"
 e-mail de domínio permitido -> 200
```

**ACHADO G1-g1** (fora do portão literal, dentro da hipótese): `visibilidade_perfil`
(privado/inquilino) é validada, gravada e devolvida em `/api/eu`, e nenhum consumidor a lê —
`grep visibilidade_perfil app/` só acha escrita, leitura do próprio e o modelo. Um perfil marcado
"privado" aparece igual na listagem `/api/usuarios` para qualquer membro do inquilino. É campo que
promete e não entrega.

### L0-08-d-ldap — REFUTADO (segundo achado grave)

Os 14 testes do item passam nesta máquina (`pytest -m lento tests/api/ldap` → 14 passed em 4,05 s).
O que aguentou do meu ataque (`test_injecao_de_filtro_senha_vazia_e_curinga`, passa): `*`,
`*)(uid=*`, `ana.silva)(|(uid=*` e `\2a` recebem 401/423, e senha vazia nunca vira bind anônimo.

**ACHADO G1-l3 — o mais grave do grupo** (`test_l3_login_cru_nao_vira_identidade_local`):

```
 login='ana.silva'    -> (base limpa) 200
 login='ana.silva*'   -> 200 perfil=admin      # nasce o usuário local 'ana.silva*'
 SELECT login, perfil, origem FROM plat.usuario WHERE origem='ldap'
   ana.silva*|admin|ldap
 login='ana.silva'    -> 409 {"erro":"conflito","detalhe":{"restricao":"ux_usuario_sujeito_externo"}}
 login='ANA.SILVA'    -> 409 (mesma restrição)
 login='an*'          -> 409 (mesma restrição)
```

Duas coisas, uma dentro da outra:

1. `app/auth/ldap.py::login_ldap` chama `plat.ldap_provisionar(tenant_id, login, ...)` com o
   **texto cru digitado pelo cliente**, embora a entrada canônica do diretório já esteja em
   `achado` (`dn` e `cn`). O usuário local nasce com o nome que o cliente escolheu.
2. Existe um índice único `ux_usuario_sujeito_externo` amarrando (inquilino, DN). O primeiro texto
   a chegar toma o DN, e todo login posterior da MESMA identidade — inclusive o canônico — recebe
   **409 com o nome da restrição do banco, numa rota pública e não autenticada**. A conta legítima
   fica trancada e não existe rota administrativa para desfazer isso.

Entrada do ataque no diretório de teste do próprio item, e é aí que entra o achado seguinte.

**ACHADO G1-l4** (`test_l4_o_escape_do_filtro_e_de_fato_exercitado`): o glauth trata a fuga
RFC 4515 como curinga.

```
 montar_filtro('(cn={login})', 'ana.silva*') -> '(cn=ana.silva\2a)'      # o escape está certo
 busca '(cn=ana.silva)'    -> ['cn=ana.silva,ou=gg-plataforma-admin,...']
 busca '(cn=ana.silva\2a)' -> ['cn=ana.silva,ou=gg-plataforma-admin,...']   # devia ser vazio
 busca '(cn=\2a)'          -> 10 entradas
```

Ou seja: o escape do login, que é a defesa que o item declara contra injeção de filtro, **nunca é
exercitado**. O que barra `*)(uid=*` é a regra "exatamente 1 resultado" (`(cn=\2a)` devolve 10),
não o escape. A prova de resistência a injeção do item é nula neste servidor.

**ACHADO G1-l1** (`test_l1_login_ldap_tem_limite_por_ip_na_borda`): o limite de 10 r/min por IP
está em `location = /api/login` e `location = /api/login/2fa`, casamento exato;
`/api/login/ldap` cai no `location /`, sem limite. O único freio é `_FALHAS`, dicionário EM
MEMÓRIA por (inquilino, login) e por PROCESSO (a unidade sobe `--workers 2`). Medido:

```
 binds/s medidos contra logins diferentes: 172,0  (10.317/min), nenhum bloqueio
```

A refutação do item fala em 1.000 binds/min; medi 10× isso sem encontrar barreira. Vale o mesmo
para `/api/senha/redefinir/solicitar` e `/api/convites/aceitar`, também fora do `limit_req`.

**ACHADO G1-l2** (`test_l2_o_caminho_tls_do_ldap_e_exercitado`): a hipótese cita StartTLS/LDAPS;
`tests/ldap_fixture/glauth.cfg` sobe com `[ldaps] enabled = false` e sem certificado, e
`tests/api/ldap/conftest.py` fixa `"start_tls": False`. Nenhum teste exercita o caminho TLS.
Some-se que o portão pede "contêiner OpenLDAP" e o que existe é glauth, e que as cláusulas
chamadas de "e2e" no portão são provadas por teste de API, não por navegador
(não há `tests/e2e/test_ldap.py`).

## (d) Fronteira honesta — o que NÃO foi provado

1. **O repositório**. Trabalhei sobre um instantâneo da árvore de trabalho de
   `/home/dev/plataforma/enterprise`, porque `master` não importa (T3). Tudo aqui vale para o
   sistema que roda, não para o commit.
2. **Navegador**. Não rodei playwright. As cláusulas "e2e com captura" dos portões a/b/c/f/g
   ficam com a prova que os autores já registraram; não as refiz nem as contesto.
3. **Produção pela borda**. Não disparei nada contra `plat.iagrointel.com`. O limite do nginx foi
   lido em `/etc/nginx/sites-enabled/plat.iagrointel.com` e em `deploy/nginx.conf`, não medido —
   medir exigiria bater na URL pública e correria o risco de bloquear o admin real (D37/D40).
4. **Diretório real**. G1-l3 e G1-l4 são medidos em glauth. Num OpenLDAP/AD estrito o `\2a` não
   casa, então a PORTA DE ENTRADA do G1-l3 é dependente do diretório. O que é do produto e
   independe do diretório continua de pé: provisionar pelo texto cru em vez do atributo canônico, e
   devolver o nome de uma restrição do banco em 409 numa rota pública. Não tenho um AD para medir
   se `caseIgnoreMatch` com espaços repetidos abre a mesma porta — é hipótese, não medida.
5. **"apagar usuário com 2 itens (recusa listando os 2)"** (portão do L0-02-f): não consegui criar
   item pela API sem montar o `dados` do esquema do tipo, então não reproduzi essa cláusula.
   Continua provada só pelo teste dos autores.
6. **Três falhas que NÃO são do produto**. `test_usuarios::test_privilegios_e_papeis`,
   `test_so_admin_cria_altera_e_apaga_admin` e
   `test_criar_usuario_com_perfil_ou_papel_exige_membros_papel` reprovam na minha trilha com
   `permission denied for schema plat` porque `execute_values` fura o `CursorSchemaAmbiente` —
   defeito de isolamento de trilha já conhecido (conserto pendurado no merge do `wt/amc`), não do
   item. Não conto como achado.
7. **Carga real**. Não rodei 1.000.000 de códigos TOTP nem 1.000 senhas de verdade; medi o custo
   unitário e a vazão e extrapolei, dizendo qual é qual.
8. **Não conserto**. Nenhuma das 16 marcas `xfail(strict=True)` foi acompanhada de correção. No dia
   em que o defeito sair, o teste passa, o `strict` transforma o XPASS em falha e obriga quem
   consertou a tirar a marca — é assim que este laudo vira prova.

## Como reproduzir tudo

```
cd /home/dev/plataforma/enterprise && git worktree add -b wt/adv1 /home/dev/plataforma/wt/adv1 master
ln -s /home/dev/plataforma/enterprise/venv /home/dev/plataforma/wt/adv1/venv
rsync -a --exclude .git --exclude venv --exclude var --exclude __pycache__ \
      /home/dev/plataforma/enterprise/ /home/dev/plataforma/wt/adv1/     # T3: master não importa
bash /home/dev/plataforma/laco/trilha_ambiente.sh adv1
cd /home/dev/plataforma/wt/adv1
set -a; source /home/dev/plataforma/laco/var/trilha/adv1.env; set +a
bash tests/ldap_fixture/subir.sh
venv/bin/pytest tests/api/test_ataque_g1_adversario.py tests/api/ldap/test_ataque_g1_ldap.py -p no:randomly -rxX
# esperado hoje: 12 passed, 16 xfailed
venv/bin/pytest tests/api/test_funcoes_seguras.py -q     # 1 failed (achado G1-T2)
```

Limpeza: `sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tadv1 CASCADE; DROP SCHEMA plat_trabalho_tadv1 CASCADE'`
e `bash tests/ldap_fixture/descer.sh`.
