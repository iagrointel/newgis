# L0-08-d-ldap — turno 3 (sessão única: arquiteto+backend, com pesquisa/teste/adversário do próprio autor)

**Objetivo do turno**: construir LDAP/Active Directory como provedor de login externo por inquilino —
bind, mapeamento de grupo→perfil, provisionamento automático — provado contra um diretório de teste real
(contêiner Docker), sem tocar `app/auth/rotas_login.py` fora do registro da rota nova.

## Portão do item no backlog (para referência)

> e2e: entrar com usuário do OpenLDAP de teste, cair no perfil mapeado pelo grupo; senha errada = 401 com
> bloqueio local; diretório fora do ar = mensagem e login local intacto; importar grupo cria N usuários
> desabilitados até o primeiro login (opção); credencial de bind cifrada

> refutação: adversário injeta filtro LDAP no login (`*)(uid=*`), usa bind anônimo, e faz 1.000 binds/min

## O que fiz

### 1. Biblioteca e servidor de teste (decididos e documentados em `docs/adr/0008-ldap-ad.md`)

`ldap3==2.9.1` instalado só na venv (`requirements.txt`; MEDIDO ausente antes, `pip install --dry-run`
confirmou zero dependência de sistema — só `pyasn1`, já presente via dpkg). Disco/RAM conferidos antes de
subir contêiner (`df -h /` 12 GiB livres, `free -h` ~1,2-2,6 GiB disponíveis): coube; usei `glauth/glauth`
(imagem 98,9 MB medida) em vez de OpenLDAP completo, e em vez do mock em Python — servidor LDAP real, não
reimplementado. `tests/ldap_fixture/glauth.cfg` (TOML): 4 usuários sintéticos (um por perfil + 1 dedicado ao
teste de colisão) + 1 conta de serviço + 3 grupos; `subir.sh`/`descer.sh` idempotentes, porta 3893 só em
127.0.0.1. Medido por busca real contra o contêiner: DN de usuário = `cn=<nome>,ou=<grupo>,ou=users,<baseDN>`;
`memberOf` = `ou=<grupo>,ou=groups,<baseDN>` (glauth usa `ou=` no RDN de grupo, não `cn=`) — por isso o
mapeamento casa pelo DN inteiro OU só pelo valor do primeiro RDN, nunca assume o nome do atributo.

### 2. Banco (`db/migracoes/025_provedor_ldap.sql`)

`plat.provedor_ldap` (RLS `FOR ALL`, `UNIQUE(tenant_id)`: url, base_dn, start_tls, bind_dn/bind_senha_cifrada
— AES-GCM sob `PLAT_SECRET`, reimplementado em `app/auth/ldap.py` com AAD própria, nunca importado de
`totp.py` — filtro_usuario, atributo_grupos, perfil_padrao, mapa_grupo_perfil jsonb) + 3 funções
`SECURITY DEFINER` sem exigir contexto de sessão (mesmo padrão de `auth_login`/`tenant_publico`):
`provedor_ldap_de(slug)` (lê a config, com `tenant.config` junto para a política de bloqueio),
`ldap_provisionar(...)` (upsert; `RAISE 'login_em_uso_local'` se já existe conta `origem='local'` com o
mesmo login) e `ldap_importar_lote(...)` (grupo→N usuários desabilitados). 2 eventos novos em
`plat.evento_tipo` (`org/ldap_configurar`, `org/ldap_importar`). Aplicada e testada isolada antes do commit
(criei, testei manualmente, encontrei um bug de retorno — faltava `config` — dropei os 3 objetos + a linha
de `versao_migracao` e recriei a migração corrigida ANTES de commitar; nunca ficou uma versão quebrada
registrada como aplicada).

### 3. `app/auth/ldap.py` (módulo novo isolado)

`POST /api/login/ldap` (público): resolve provedor → tenant suspenso (503) / desabilitado (403) → bloqueio
em memória (por `tenant_id`+login, reaproveitando `bloqueio_tentativas`/`bloqueio_minutos` da política do
PRÓPRIO inquilino — cobre também login ainda não provisionado) → bind serviço/anônimo → busca com filtro
SEMPRE escapado (`escape_filter_chars`) → exige exatamente 1 resultado → bind do usuário (senha vazia
recusada ANTES de qualquer conexão) → mapeia `memberOf` para perfil (maior alcance quando mais de um grupo
bate) → `ldap_provisionar` → `auth_login` de novo → **reaproveita** `rotas_login._abrir_sessao` (import
direto; não duplica cookie/política/evento). `GET/PUT /api/org/ldap` e `POST /api/org/ldap/importar`
(privilégio `org.integracoes`, já reservado pela ADR 0002) para configuração e importação em massa.
`app/main.py` ganhou 1 linha de import + 1 linha na lista `ROUTERS` (`rotas_ldap.router`) — **nenhuma linha
de `app/auth/rotas_login.py` foi tocada**. `app/limites.py` ganhou a seção `LDAP` (timeout, tamanho máximo
de busca/importação); `docs/LIMITES.md` regenerado e conferido (`docs/gerar_limites.py --check`).

### 4. Testes (`tests/api/ldap/`, 14 casos, marcados `lento`)

`conftest.py`: fixture `servidor_ldap` (sobe/derruba o contêiner; pula com `docker` ausente) com
**readiness real** (bind anônimo, não só TCP connect — a primeira conexão por um mapeamento de porta do
Docker recém-criado ocasionalmente fechava com "session terminated by server", medido nesta máquina; a
espera por porta sozinha não bastava) e `provedor_ldap_demo` (configura pela PRÓPRIA API, `PUT
/api/org/ldap`, nunca por SQL direto). Casos: bind OK cai no perfil certo (3 perfis) · senha errada · senha
vazia nunca tenta bind · injeção de filtro neutralizada · grupo não mapeado recusa com `403` · colisão com
conta local recusa com `409` (conta dedicada `dora.lima` — usar um login já consumido por outro teste do
arquivo testaria a `UNIQUE` genérica de login, não a regra que o item pede) · **diretório fora do ar não
derruba o login local** (para o contêiner, confere `503` na rota LDAP e `200` na rota local, religa) · bind
repetido bloqueia como o login local (6ª tentativa = `423`) · importação em massa cria desabilitado e ativa
no 1º login · admin nunca vê a senha de bind · perfil inválido recusado · teste cruzado A/B (`org.integracoes`
de `demo2` nunca é o de `demo`) · sem privilégio toma `403` · latência medida.

## Evidência (comando + saída literal)

```
$ ./venv/bin/pip install --dry-run ldap3
Would install ldap3-2.9.1                         # zero dependência de sistema

$ docker images glauth/glauth:latest --format '{{.Size}}'
98.9MB

$ sudo bash db/migrar.sh   (trecho)
aplicada   025_provedor_ldap (2430 ms)

$ ./venv/bin/ruff check app/auth/ldap.py tests/api/ldap/ tests/ldap_fixture/ tests/api/eventos_esperados.py tests/api/cruzado_casos.py
All checks passed!

$ flock .../.pytest.lock ./venv/bin/pytest -m lento tests/api/ldap -v --base-url https://plat.iagrointel.com
14 passed, 1 warning in 3.70s
(tests/medidas/L0-08-d-ldap.json: mediana_5_logins_ldap_ms = 12,2 ms)

$ flock .../.pytest.lock ./venv/bin/pytest tests/api/test_eventos.py tests/api/test_funcoes_seguras.py tests/api/test_cruzado.py -q
161 passed
```

Smoke test manual ponta a ponta (antes da suíte existir, contra o `TestClient` real): login de `ana.silva`
→ `200 {"ok":true,...,"perfil":"admin","origem":"ldap"}`; `bruno.souza`→`editor`; `carla.dias`→`visualizador`;
senha errada → `401 credenciais_invalidas`; filtro `*)(cn=*` → `401` (nunca autentica); diretório derrubado
(`docker rm -f`) → LDAP `503 ldap_indisponivel`, login local no MESMO processo → `200`; 6 tentativas erradas
seguidas contra `bruno.souza` → 5×`401` + `423` na 6ª; importação de `gg-plataforma-leitura` criou
`carla.dias ativo=false`, primeiro login flipou para `ativo=true` (conferido por `SELECT` direto).

## Achados do `make check-rapido` completo (rodei a suíte INTEIRA, não só a do item — regra do laço)

Três classes de correção que a suíte cheia pegou e a minha própria não cobria:

1. **`REVOKE EXECUTE ... FROM PUBLIC` faltando nas 3 funções novas**: `CREATE FUNCTION` concede EXECUTE a
   PUBLIC por padrão; `test_nenhuma_funcao_com_execute_para_public` (`tests/api/test_funcoes_seguras.py`)
   acusou `provedor_ldap_de`/`ldap_provisionar`/`ldap_importar_lote` com PUBLIC ainda podendo chamar. Corrigido
   na migração (REVOKE + GRANT explícitos a `plat_app`, mesmo padrão que a 003 já usa) — reaplicado (drop +
   recriação limpa da mesma migração, ainda não commitada, sem afetar nenhuma linha real: a tabela estava
   vazia de configuração de produção).
2. **`EVENTOS_POR_ROTA` (`tests/api/eventos_esperados.py`) e `CASOS` (`tests/api/cruzado_casos.py`)**: os dois
   são listas fechadas por rota, geradas do `docs/openapi.json`; toda rota de escrita nova PRECISA de uma
   entrada em cada um (o portão P6 do laço é literalmente isso — teste cruzado A→B automático). Acrescentei
   as 3 entradas (`POST /api/login/ldap`, `GET/PUT /api/org/ldap`, `POST /api/org/ldap/importar`).
3. **Incidente do superadmin `plataforma` bloqueado (não escondido)**: durante a construção, tentativas
   MINHAS contra `sessao_plat` (usando um segredo TOTP cacheado que já estava desatualizado — outra trilha
   tinha resetado o 2FA da conta antes) colidiram com o contador de bloqueio local e travaram a conta até
   `2026-09-06T11:18Z`, derrubando `make check-rapido` INTEIRO (503 erros em cascata via a fixture autouse
   `sessao_plat`/`limpeza_de_residuos`). Diagnosticado (segredo cacheado ≠ segredo no banco) e corrigido pelo
   MESMO caminho que `install.sh` documenta (reset do 2FA + apagar `tests/credenciais_totp.txt`; a suíte
   religou sozinha, novo segredo cacheado) — sem editar nenhum teste alheio. `tests/api/ldap/conftest.py`
   ganhou uma sobrescrita local (só para este diretório) da fixture `limpeza_de_residuos`, para os testes de
   LDAP nunca mais dependerem de `sessao_plat` (a conta mais disputada da árvore neste turno).

Depois dos três, `make check-rapido` voltou a rodar; a única falha residual observada
(`tests/api/jobs/test_jobs_sse.py::test_limite_de_conexoes_por_usuario_e_liberado_ao_fechar`) é de outra
área (fila de jobs/SSE), reproduzida isolada e sem relação com nenhum arquivo deste item — registrada aqui
para o gerente decidir se abre um achado à parte, não corrigida por mim.

## Riscos

- Contador de força bruta é em memória de PROCESSO (`--workers 2` dobra o teto efetivo; não sobrevive a
  reinício) — aceitável para uma primeira passagem, nomeado no ADR 0008 seção D6, não escondido.
- StartTLS e `sAMAccountName` (Active Directory de verdade) nunca testados contra diretório real — só contra
  o glauth de teste (sem certificado, `start_tls=false` na config de teste).
- `GET /api/login/provedores` ainda devolve lista vazia — LDAP não aparece ali (é rota própria
  `/api/login/ldap`, não o "botão de provedor" do L0-08-a/b/c); tela de entrada/admin não tem UI (frontend
  não é papel deste item — ver `docs/PARIDADE.md`).
- Repositório com MUITA atividade concorrente de outras trilhas no mesmo turno (main.py, app/limites.py,
  requirements.txt, tests/api/conftest.py mudaram por baixo enquanto eu trabalhava): toda edição em arquivo
  compartilhado foi feita por `Edit` (não `Write`) com leitura fresca imediatamente antes, para nunca
  sobrescrever o trabalho de outra trilha; `flock` respeitado em toda chamada de pytest.

## Pendências

- Contador de força bruta compartilhado entre workers (tabela ou período curto no banco) — nomeado, não
  construído.
- OIDC/SAML/gov.br (resto do L0-08-sso) e a tela (`L0-08-f`, frontend) ficam para outro item/turno.

## Para o próximo papel (cronista/gerente)

`docs/adr/0008-ldap-ad.md` (decisões D1-D7) · `docs/PARIDADE.md` (linha nova "AD-LDAP: bind, mapeamento...")
· `ARQUITETURA.md` seção 4.9 (foi varrida para dentro do commit `023b0bb` de outra trilha antes que eu
commitasse — conferido: o conteúdo está intacto em `git show HEAD:ARQUITETURA.md`) · `MANUAL.md` seção 15
· `CHANGELOG.md` (entrada deste turno) · `tests/medidas/L0-08-d-ldap.json`. **Commitado: `989d0df`**
("LDAP/Active Directory como provedor de login externo por inquilino"), 17 arquivos, só os deste item
(conferido `git status --short` antes do `git add` — nada de outras trilhas foi arrastado).

**Confirmação final (pós-commit) chegou**: `make check-rapido` completo, `1005 passed, 43 deselected` em
279 s — a ÚNICA falha é `tests/api/jobs/test_jobs_sse.py::test_limite_de_conexoes_por_usuario_e_liberado_ao_fechar`,
reproduzida isolada antes do commit e confirmada sem relação com nenhum arquivo deste item (área de fila de
jobs/SSE, não de identidade/LDAP) — fica registrada para o gerente decidir se abre um achado à parte.
