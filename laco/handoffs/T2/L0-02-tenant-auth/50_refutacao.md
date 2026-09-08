# 50 — Refutacao (adversario independente) · L0-02-tenant-auth · T2

**Veredito: PASSA** (nao destrutivo). Reinstalacao/P5: PENDENTE do gate 40_testes.md (ver Pendencias).

## Objetivo
Derrubar a isolacao multi-inquilino e a autenticacao do item L0-02. Padrao: achar problema.
Portao (literal): "adversario escreve consultas cruzadas e chamadas com token de outro inquilino
em todas as rotas listadas no OpenAPI; qualquer 200 cruzado = refutado."

## O que fiz
Contexto proprio: li so o item no estado.json, o 00_plano.md e o ADR 0002. NAO li 20/30/31/40.
Ataquei o servico VIVO (127.0.0.1:8150 = mesmo processo que serve https://plat.iagrointel.com,
pid 2897776/83/84) com dois inquilinos de demonstracao (A=demo, B=demo2) e o inquilino tecnico
`plataforma`. Scripts em scratchpad (sweep.py, attack/seed, auth_attacks.py, sess_csrf.py,
super_tok.py, xff.py, hdr.py). 16 familias de ataque; todas resistiram.

## Evidencia (comando + saida literal)

1. **Varredura cruzada A->B (nucleo do portao).** `sweep.py`: login demo/demo2, seed em B
   (usuario 434, grupo 0c7d..., papel 75, token 301, job, agenda, sessao 8471...), e 40 rotas por
   id com o cookie de A contra os ids de B (GET/PUT/DELETE/POST em usuarios, grupos(+membros/
   entrar/aceitar/aprovar), papeis, tokens(+log/renovar), jobs(+eventos/log/cancelar/repetir),
   agendas(+pausar/retomar/rodar-agora), eu/sessoes, plataforma/*).
   Saida: **40/40 = 404** (usuario_inexistente / grupo_inexistente / token_inexistente /
   job_inexistente / agenda_inexistente / nao_encontrado). **CROSS200=[]**. Nenhuma linha de B mudou.
2. **Listas nao vazam B.** GET /api/usuarios,/grupos,/papeis,/tokens,/jobs,/agendas,/eventos,/log
   com cookie de A: **8/8 leakB=False** (ex.: /api/usuarios total=16, so demo; /api/log total=25587,
   so tenant 1).
3. **Spoof por cabecalho.** sessao de A + `X-Plat-Inquilino: demo2` -> **403**, nao troca de
   inquilino; /api/usuarios idem 403 sem leak. `X-Tenant`/`X-Plat-Tenant` ignorados (segue demo).
4. **Token de B cross.** `Authorization: Bearer <token de B>` em /api/eu -> 200 devolvendo o
   proprio dono (id 2, demo2). Age SO como B.
5. **SECURITY DEFINER / PUBLIC / BYPASSRLS (achado do T1).** `pg_proc`: **0** funcoes com `=X`
   (PUBLIC); EXECUTE so plat_app/plat_worker. `pg_roles`: plat_app/plat_worker rolsuper=f
   rolbypassrls=f. `pg_class`: RLS ativa em toda tabela com tenant_id, **inclusive as particoes**
   evento_y2026m09..12 e log_acesso_y2026m09..12. Tabelas de `plat` sao owned por **postgres**
   (logo RLS aplica a plat_app; nao ha owner-bypass para o papel da app).
6. **Forjar contexto como plat_app (psql).** Contexto honesto (plat.tenant_id=1): `SELECT count(*)
   FROM plat.usuario WHERE tenant_id=2` = **0**; `plat.job_cancelar('<job de B>',1)` = **NULL**,
   job de B intacto (a funcao filtra `AND tenant_id=plat.tenant_atual()`). `plat.tenant_suspender(
   '<hash de A>',2,false)` -> **ERROR so_superadmin**. Funcoes de superadmin resolvem a sessao no
   banco (plataforma_operador), nunca por GUC. (Forjar o GUC e ler B so acontece com a SENHA do
   papel plat_app = comprometimento de host, nao caminho de app; ver o_que_nao_prova.)
7. **Forca bruta.** 5 senhas erradas = 401 credenciais_invalidas; 6a = **423 bloqueado**; senha
   CORRETA apos as 5 falhas = **423 bloqueado**.
8. **TOTP replay / reuso de recuperacao.** mesmo passo TOTP reusado = 401 codigo_invalido
   (anti-replay por totp_ultimo_passo); recovery#1 ok, mesmo codigo de novo = 401. `totp_secret`
   no banco = **enc:v1:...** (cifrado).
9. **Tempo existente x inexistente (60x).** mediana 140,2 ms vs 137,5 ms, **delta 2,7 ms** sobre
   base ~140 ms (HASH_FANTASMA equaliza; sem oraculo).
10. **Sessao.** cookie `HttpOnly; Secure; SameSite=lax; Max-Age=604800`. Fixacao: login ignora
    cookie do atacante e emite novo (cookie do atacante -> 401). Usuario desativado: sessao vira
    401 na hora. Logout: 204 -> 401. Troca de senha por s2 derruba s1 (-> 401).
11. **CSRF.** POST /api/tokens com `Origin: https://evil.example` -> **403 origem_invalida**; com
    Content-Type nao-JSON -> **415 tipo_nao_aceito**; Origin correto -> 201.
12. **Superadmin / escalada.** PUT/POST usuario com `superadmin:true` -> **422 extra_forbidden**;
    A -> /api/plataforma/* -> **404**; login em `plataforma` -> **exige_2fa=true** (superadmin com
    totp_ativo=t, sem cookie ate 2FA).
13. **Token: escopo/revogado/IP/auto-perpetuacao.** catalogo:ler em /api/usuarios,/api/log -> 403
    escopo_insuficiente; revogado -> 401 token_revogado; validade 100000 -> 400
    validade_acima_do_maximo (max 365); token cria token / 2fa / lista sessoes -> 403 so_sessao;
    restricao de IP -> 401 ip_nao_permitido do IP real.
14. **Segredos.** `.env` nao rastreado, gitignored, **600**; credenciais 600; **0** segredo
    hardcoded no py/js/sh; journal (3h) com **0** valor de cookie(32hex) e **0** de token;
    log_acesso **0/30882** com token=/plat_sessao= na rota.
15. **Placeholder / teste-que-nao-testa.** **0** TODO/FIXME/NotImplemented/placeholder em app+web/js;
    **0** `assert True`; 253 testes/60 arquivos; `test_cruzado.py` deriva **73** metodo×caminho do
    OpenAPI, exige cobertura 100%, 4 vetores por rota e compara **digest md5 de todo o dado de B**
    antes/depois; CASOS=73 -> **73/73**.
16. **P7.** `git grep` de nomes de cliente/parceiro (fora vendor) = **0**; unica mencao em
    tests/medidas/L0-01-repo.json e a citacao do proprio comando de checagem P7 (meta).

## Portao, clausula a clausula
| clausula | veredito | evidencia |
|---|---|---|
| RLS ativa nas tabelas de inquilino | passa | relrowsecurity=t em todas com tenant_id + particoes |
| A nao le/edita B em nenhuma rota | passa | 40 rotas vivas = 0 cross 200; test_cruzado 73/73 com digest-diff |
| login/logout/2FA/troca senha/usuarios funcionam | passa | verificado por HTTP (e2e navegador = testador, P1) |
| token no log com IP/rota/bytes | passa | 1481 linhas com token_id, 0 ip/bytes NULL |
| secdef checa inquilino + EXECUTE so plat_app | passa | contexto_confere/plataforma_operador; proacl sem PUBLIC |
| middleware grava log_acesso por requisicao | passa | 30882 linhas, campos populados e redigidos |
| limiares do ADR (senha/bloqueio/expiracao/MFA) | passa | comportamento vivo bate com ADR 0002 secoes 5-8 |

## Riscos
- A restricao de IP do token confia em request.client.host. Em producao esta correta (nginx anexa o
  IP real; uvicorn --forwarded-allow-ips 127.0.0.1 usa o hop nao-confiavel mais a direita; XFF
  forjado pela URL publica = 401). Se um dia :8150 for exposto sem nginx, ou o forwarded-allow-ips
  virar `*`, o spoof passa a valer. Manter :8150 em loopback e a config atual.
- Bloqueio por usuario permite negacao de servico de uma conta conhecida (o admin unico do
  inquilino). Mitigacao ja documentada no ADR (limite por IP no nginx + 2o admin recomendado).

## Pendencias
- **Reinstalacao (P5) nao executada:** o gate `40_testes.md` estava AUSENTE ate o fim desta sessao
  (verificado as 2026-09-05T16:20:02Z). A refutacao com `drop schema plat + role + sudo bash install.sh
  plat.iagrointel.com 8150` (derruba o servico por segundos) so roda DEPOIS que 40 existir. NAO
  rodei para nao colidir com o TESTADOR e por respeitar o gate. Deixo plat-api e plat-worker ATIVOS.
- E2E playwright das telas (P1) e paridade Esri viva (P4) ficam com testador/esri.

## Para o proximo papel (gerente)
Julgar o portao: pelas evidencias nao destrutivas, TODAS as clausulas passam e o adversario NAO
refutou o nucleo (0 cross 200 em 40 rotas vivas + 73/73 no teste do repo). Se quiser fechar P5,
lancar a rodada de reinstalacao quando 40_testes.md existir e conferir que o schema/roles/funcoes
se recriam e que uma varredura cruzada minima segue 404. Sujeira de teste que deixei em `demo`/
`demo2` (usuarios vitima/bob/mfa*/pendtest/disab/pw, grupo GrupoB, papel PapelB2, tokens): recriaveis
e sem efeito de isolacao; o expurgo natural ou o proprio drop-schema da reinstalacao os remove.

---

# Rodada 2 — refutacao COM REINSTALACAO (gate 40_testes.md aberto)

**Veredito final: PASSA.** O gate `40_testes.md` apareceu 2026-09-05T16:38:07Z (commit 12b2c2e do
testador: varredura viva 73/73, 411 chamadas, 0 acesso cruzado, login mediana 129 ms). Esperei o
pytest concorrente terminar e executei a reinstalacao destrutiva.

## Reinstalacao (hora exata — derruba o servico por segundos)
- `systemctl stop plat-api plat-worker` -> **17:14:17Z**
- `DROP SCHEMA plat CASCADE; DROP SCHEMA plat_trabalho CASCADE; DROP OWNED BY plat_app; DROP OWNED
  BY plat_worker; DROP ROLE plat_app; DROP ROLE plat_worker` -> **schemas restantes=0, roles
  restantes=0** as **17:14:30Z** (dropou 79+2 objetos).
- `sudo bash install.sh plat.iagrointel.com 8150` -> rc=0, "instalado em 50 s", concluido
  **17:15:20Z**. plat-api e plat-worker ativos.
- **Servico indisponivel ~63 s** (17:14:17 -> 17:15:20).

## Instalacao nova, conferida
- Estrutura recriada: 27 tabelas, 60 funcoes, 25 politicas, plat_trabalho 2 tabelas, migracoes
  001..011, particoes evento/log_acesso 2026m09..12. Inquilinos: demo, demo2, plataforma. Admins
  semeados: plataforma (superadmin, 2FA obrigatorio), demo/demo2 (nao-superadmin).
- **Invariantes de seguranca (P6):** funcoes com EXECUTE PUBLIC = **0** (o conjunto completo de
  migracoes inclui a 010, que revoga os 3 gatilhos da 004 - job_notificar/job_log_notificar/
  job_estado_final_imutavel - de PUBLIC e de plat_app; plat_app nao os chama: "permission denied");
  secdef sem contexto e com PUBLIC = 0; tabelas com tenant_id **sem** RLS = **0**; plat_app/
  plat_worker rolsuper=f rolbypassrls=f; owner de todas as tabelas = postgres.
- **/saude publico:** `HTTP/1.1 200 OK` · `X-Robots-Tag: noindex, nofollow` ·
  `Strict-Transport-Security: max-age=31536000` · banco=ok · migracoes_pendentes=0. /api/openapi.json
  publico = 200.
- **Login real pelo navegador (playwright, senha regenerada de tests/credenciais.txt):** /entrar 200
  -> apos entrar redireciona para / (painel real com Inicio/Usuarios/Grupos/Tarefas/Papeis/Tokens/
  Log); /api/eu 200 (admin/demo); cookie `plat_sessao` httpOnly=true secure=true sameSite=Lax;
  logout 204 -> /api/eu 401; **0 erro real de console** (o unico e o 401 esperado pos-logout).
  Capturas: pw_01_form.png, pw_02_logado.png.
- **Varredura cruzada A->B DE NOVO na instalacao nova:** 34 rotas por id do OpenAPI vivo com cookie
  de A contra ids de B -> **CROSS200=[]**, nenhum status inesperado; 0 lista vaza B; token de B ->
  /api/eu = dono id 2 tenant demo2 (so B); `X-Plat-Inquilino: demo2` -> **403**.

## make check inteiro (P3) — 402 passed, 7 failed, TODAS as 7 fora do item L0-02
- **4** em `tests/api/jobs` (`test_jobs_fila.py`, `test_jobs_memoria.py`) = **trilha B / L0-05**:
  worker nao levou o job a estado final em 60 s sob a contencao do proprio make check;
  `test_repetir_cria_job_novo_com_proveniencia` falha tambem isolado (defeito de trilha B a fechar).
- **3** (`test_cruzado::test_cobertura_100_por_cento`, `test_eventos`,
  `test_privilegios_declarados`) = **corrida de worktree compartilhada**: a app viva ja tinha a rota
  `DELETE /api/plataforma/inquilinos/{id}` e as migracoes 009/010/011 da trilha B antes de
  docs/openapi.json e cruzado_casos serem comitados. **Re-rodados isolados no HEAD abbb03d = 80
  passed**; docs/openapi.json comitado x vivo = **74/74 identicos**. Nao sao refutacao do L0-02.

## Estado ao terminar
plat-api e plat-worker **ativos**; /saude 200 git_sha abbb03d02920 ambiente producao. Nada
consertei no repositorio. As 7 falhas do make check ficam registradas por arquivo (trilha B), nao
como refutacao do item.
