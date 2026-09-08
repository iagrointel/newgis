# G1 — conserto de identidade, sessão, segundo fator e login externo (turno 3, ramo `wt/g1fix`)

Resposta ao laudo `laco/handoffs/T3/ataque-g1-ADVERSARIO.md`, que derrubou 6 dos 8 itens do grupo. Este turno
conserta o que foi delegado a ele; a varredura das 102 funções de definidor de segurança e as permissões
abertas a PUBLIC (achado G1-T2) ficaram com OUTRO agente — aqui não se tocou em permissão de função nem em
migração de `GRANT`/`REVOKE`.

Worktree `/home/dev/plataforma/wt/g1fix`, base própria `plat_tg1fix` (`bash laco/trilha_ambiente.sh g1fix`).
Nada rodou contra o schema `plat` de produção; a migração deste ramo NÃO foi aplicada em produção.

## 1. GRAVE — o login externo trancava a conta legítima (achado G1-l3)

O defeito tinha três camadas, e as três foram consertadas.

**(a) Provisionar pelo atributo canônico do diretório.** `app/auth/ldap.py::login_ldap` chamava
`plat.ldap_provisionar(...)` com o texto cru do corpo JSON. Agora `autenticar_e_buscar_grupos` devolve também
`login`, calculado por `login_canonico(entrada, dn, filtro_usuario, login_digitado)`: vale o atributo que o
próprio `filtro_usuario` do provedor usa como chave (`(uid={login})` → `uid`, `(cn={login})` → `cn`), depois
`uid`, depois o valor do primeiro RDN do DN, e só se o diretório não tiver respondido nada é que sobra o texto
digitado. Esse atributo entrou na lista `attributes=` da busca — sem pedi-lo, a entrada voltava sem ele.

**(b) A identidade é o DN, não o login.** `plat.ldap_provisionar` procurava a linha local por `login`. Agora
procura primeiro por `(tenant_id, origem='ldap', sujeito_externo)`, que é o que o diretório garante único; o
login é atributo e acompanha o diretório na atualização. Com isso o segundo login da MESMA identidade atualiza
a linha em vez de estourar o índice único `ux_usuario_sujeito_externo`. A colisão que sobra — dois DNs
diferentes disputando um login — vira o código curto `login_em_uso_externo`, levantado explicitamente.
Migração `db/migracoes/20260906T1611_g1_identidade_conserto.sql`, com `CREATE OR REPLACE` e a MESMA assinatura
e o mesmo tipo de retorno de 025: as ACL da função ficam intactas (conferido: `postgres=X/postgres,
plat_tg1fix_app=X/postgres`, sem PUBLIC).

**(c) Nome de restrição do banco nunca sai em rota pública.** `app/auth/comum.py::erro_do_banco` ganhou
`expor_restricao: bool = True`; `POST /api/login/ldap` chama com `expor_restricao=False`. Em rota autenticada
o nome continua saindo — ele é o que deixa o administrador entender qual regra recusou.

**(d) Caminho administrativo para desfazer.** `DELETE /api/usuarios/{id}/vinculo-externo` (privilégio
`membros.gerir`, `so_admin_sobre_admin`): apaga `sujeito_externo`, desabilita a conta, encerra as sessões dela
e grava o evento novo `usuarios/vinculo_externo_remover`. Recusa com 409 `sem_vinculo_externo` em conta local
ou já sem vínculo.

Prova: `tests/api/ldap/test_ataque_g1_ldap.py::test_l3_login_cru_nao_vira_identidade_local` passa com a
afirmação do adversário intacta (`login == "ana.silva"` e o canônico devolvendo 200), marca `xfail` removida.

## 2. MÉDIA — a conta mais forte tinha a política mais fraca (achado G1-b2)

`app/auth/rotas_login.py::login_2fa` passava `senha_alterada_em=None` para `_abrir_sessao`, e a verificação de
expiração era condicionada a esse parâmetro. Entrou a sentinela `NAO_INFORMADO`: quando ela chega,
`_abrir_sessao` lê `senha_alterada_em` do banco. `None` continua sendo o valor legítimo de quem não tem senha
local — é o que o caminho LDAP passa, com o motivo escrito no código. Prova: `test_b2` passa, marca removida.

## 3. MÉDIA — guarda que vivia num caminho só (achado G1-c1)

`app/geocodificador/rotas_esri.py::_autenticar` chamava `sessao.resolver()` direto. As 7 rotas do GeocodeServer
exigiam credencial — por isso nenhum teste de autenticação as pegava — mas pulavam três guardas: pendência de
conta (a tela de configurar 2FA), `checar_escrita_sob_cookie` (CSRF) e a checagem de `X-Plat-Inquilino`.

Conserto: `autenticado()` ganhou `token_por_querystring: bool = False`. O `?token=` que o protocolo REST da
Esri exige virou uma opção DENTRO da porta única, e as 6 rotas autenticadas passaram a usar
`autenticado(escopo_token="geocodificar:usar", token_por_querystring=True)`. O `_autenticar` paralelo deixou de
existir. As 6 declaram `x-privilegio: proprio` (o mesmo de `/api/geocodificar`); o descritor do locator, que
sempre respondeu sem credencial, passou a declarar o que faz: `x-auth: "-"`, `x-privilegio: publico`.

**Teste que varre o contrato**: `tests/unit/test_contrato_guarda.py` (8 casos, sem banco). Desce a árvore de
rotas do app VIVO — nunca `docs/openapi.json`, que é retrato parado — e cruza duas leituras de cada rota: o que
ela DECLARA em `x-auth` e o que ela FAZ (existe na árvore de dependências do FastAPI alguma criada por
`autenticado()`?). Reprova nos dois sentidos: declara credencial e não tem guarda, ou tem guarda e se declara
pública. Tem também a guarda da guarda (`test_a_varredura_enxerga_o_app_inteiro`, exige > 150 rotas vistas),
porque nesta versão do FastAPI `app.routes` guarda `_IncludedRouter` e não as rotas — descer errado faria a
varredura aprovar tudo por não ver nada.

A varredura achou mais três rotas fora do guarda, e as três foram resolvidas:
- `GET /api/uploads/tipos` e `GET /api/importacoes/formatos` declaravam `x-auth: S/T` e respondiam sem
  credencial (é o achado G1-e1). Passaram pelo guarda com `escopo_token=None` — são vocabulário, não dado.
  ⚠ **risco de merge**: `app/uploads/rotas.py` e `app/ingestao/rotas.py` são das trilhas L0-04/L0-04-a.
- `POST /api/logout` é a única exceção nomeada, com o motivo escrito no `EXCECOES` do teste: precisa aceitar
  cookie já expirado, ou quem tem a sessão vencida receberia 401 ao tentar sair.
- `GET /saude` e `GET /api/versao` não declaravam `x-auth`/`x-privilegio`; agora declaram `-`/`publico`.

Isso fecha também `test_e1` e `test_e2` do adversário (marcas removidas).

## 4. BAIXA, do portão — três divergências portão × código

Nos três casos consertei o CÓDIGO, não o portão: `laco/estado.json` não foi tocado (regra 1 do BRIEF) e não
precisa ser, porque o código passou a fazer o que o portão já dizia.

| achado | portão dizia | código fazia | conserto |
|---|---|---|---|
| G1-a1 | "sessão ociosa devolve 401 **e a linha é apagada pelo periódico**" | `plat.sessoes_expurgar()` cortava por `interval '24 hours'` FIXO | a função passou a usar o MESMO corte por inquilino de `plat.auth_sessao` (`config.auth.sessao_ociosa_horas`, padrão 12 h, faixa 1–24 h). Sessão órfã (sem dono) continua saindo pelo teto absoluto de 24 h, que é o maior valor que a política aceita — sem inquilino não há política a consultar. |
| G1-b1 | "mínimo 10 caracteres com pelo menos uma letra e um número" | padrão 8 | `limites.AUTH_PADROES["senha_min"] = (10, 8, 64)` e `Politica.senha_min = 10`. O PISO configurável fica em 8, que é o mínimo do NIST SP 800-63B §3.1.1.2 para senha escolhida pelo usuário: um inquilino que queira 8 escreve 8 em `config.auth`; quem não escreve nada recebe 10. Letra e número já eram exigidos sem condição (`politica.regra_da_senha`). `docs/LIMITES.md` regerado por `docs/gerar_limites.py`; ADR 0002 §11 atualizado. |
| G1-d1 | "prefixo de 8 caracteres na lista" | `valor[:12]` | `valor[:limites.TOKEN_PREFIXO_TAMANHO]`, com `TOKEN_PREFIXO_TAMANHO = 8`. São 4 caracteres a menos do segredo guardados em claro num campo que a listagem devolve. |

## 5. Teste de fumaça da árvore limpa

O adversário afirmou que `master` não importava. **Isso está vencido**: o gerente testou numa cópia limpa e ela
importa; `test_t3` agora passa com a marca removida. O que era verdade e ficou: não existia teste que
garantisse isso, e dois adversários diferentes esbarraram no assunto.

`tests/unit/test_arvore_limpa_importa.py`, 3 casos:
1. `git archive HEAD` para um diretório temporário (por construção, só arquivo versionado) e
   `python -c "from app.main import app"` lá dentro, em subprocesso, com ambiente SINTÉTICO (PLAT_SECRET de
   zeros, DSN que nunca é aberto — importar o app não conecta) e sem herdar nenhuma variável `PLAT_*` real;
2. o mesmo, montando `app.openapi()` — é onde aparecem colisão de nome de modelo e referência a esquema
   inexistente (o defeito que o commit 2fe849d consertou); exige > 120 caminhos;
3. barato e imediato: todo módulo `app.*` carregado no processo está em `git ls-files` — pega o arquivo que
   ainda não foi `git add`ado ANTES de virar um commit que não importa.

## 6. Um defeito de TESTE encontrado ao consertar

`test_a1` do adversário envelhecia a sessão com `SET LOCAL ROLE NONE` seguido de `con.rollback()` — que
descarta o `SET LOCAL`. Sem contexto de inquilino, a política `p_sessao` faz o `UPDATE` casar **0 linhas em
silêncio**, e o teste caía na pré-condição (`/api/eu` devolvendo 200), não na cláusula do periódico. O xfail
podia estar verde pelo motivo errado. Corrigi só a plumbing — contexto posto como o resto do arquivo já faz
(`_config_do_demo`) e `rowcount` conferido; a AFIRMAÇÃO do adversário está idêntica.

## 7. Prova (comandos e resultado)

```
cd /home/dev/plataforma/enterprise && git worktree add /home/dev/plataforma/wt/g1fix wt/g1fix
ln -s /home/dev/plataforma/enterprise/venv wt/g1fix/venv ; ln -s ../../enterprise/.env wt/g1fix/.env
bash /home/dev/plataforma/laco/trilha_ambiente.sh g1fix
# a migração deste ramo é aplicada SÓ na base da trilha (nunca em produção):
TRILHA=g1fix laco/trilha_reescrever.py db/migracoes/20260906T1611_g1_identidade_conserto.sql \
  | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -
cd /home/dev/plataforma/wt/g1fix
set -a; source /home/dev/plataforma/laco/var/trilha/g1fix.env; set +a
bash tests/ldap_fixture/subir.sh

venv/bin/pytest tests/api/test_ataque_g1_adversario.py -p no:randomly
#   18 passed, 4 xfailed          (era 12 passed, 13 xfailed)
venv/bin/pytest tests/api/ldap -m lento -p no:randomly
#   17 passed, 3 xfailed          (era 14 passed + 3 xfailed do ataque)
venv/bin/pytest tests/unit/test_contrato_guarda.py tests/unit/test_arvore_limpa_importa.py -p no:randomly
#   11 passed
sudo -u postgres psql -d iagro_sat -X -A -F'|' -c "SELECT proname, array_to_string(proacl,',') FROM pg_proc
  WHERE pronamespace='plat_tg1fix'::regnamespace AND proname IN ('ldap_provisionar','sessoes_expurgar')"
#   ldap_provisionar|postgres=X/postgres,plat_tg1fix_app=X/postgres   (sem PUBLIC)
#   sessoes_expurgar|postgres=X/postgres,plat_tg1fix_app=X/postgres   (sem PUBLIC)
```

## 8. Marcas do adversário: 9 removidas, 7 continuam

Removidas (defeito consertado, o teste passa com a afirmação original): T3, a1, b1, b2, c1, d1, e1, e2, l3.

Continuam `xfail(strict=True)`, porque não foram consertadas aqui — nenhuma foi apagada ou afrouxada:
- **T1** (`docs/openapi.json` 28 rotas atrás do app vivo) e **T2** (6 funções SECURITY DEFINER executáveis por
  PUBLIC no `plat` de produção) e **e3** (duas rotas devolvendo 500): são do L0-02-e e das trilhas de convite/
  SMTP; T2 é explicitamente do outro agente. **T1 ficou pior com este turno**: acrescentei 1 rota
  (`DELETE /api/usuarios/{id}/vinculo-externo`) e mudei declarações de 9 rotas, e `docs/openapi.json` NÃO foi
  regerado de propósito — é arquivo de colisão alta com as outras trilhas, e regerá-lo aqui esconderia o
  conflito em vez de resolvê-lo. Quem juntar os ramos roda `make openapi` UMA vez, depois do merge.
- **g1** (`visibilidade_perfil` gravada e nunca aplicada): fora dos quatro itens deste turno.
- **l1** (sem `limit_req` por IP em `/api/login/ldap` na borda), **l2** (caminho TLS do LDAP nunca exercitado)
  e **l4** (o glauth casa a fuga `\2a` como curinga, então o escape RFC 4515 nunca é exercitado): fora do
  escopo delegado. l1 é conserto de `deploy/nginx.conf` + o arquivo em `/etc/nginx/sites-enabled/`, que este
  ramo não toca; l2 e l4 pedem outro diretório de teste (OpenLDAP com certificado), não código.

## 9. Fronteira honesta — o que este turno NÃO prova

1. **Produção.** Tudo foi medido em `plat_tg1fix`. A migração não foi aplicada em `plat`.
2. **Diretório real.** O conserto do G1-l3 foi medido em glauth. As duas partes que são do PRODUTO —
   provisionar pelo atributo canônico e não devolver nome de restrição — independem do diretório. Não há um
   Active Directory aqui para medir se `caseIgnoreMatch` com espaços repetidos abre a mesma porta.
3. **Navegador.** Nenhum playwright. O caminho de tela do vínculo externo (item d da seção 1) tem rota e
   evento, não tem botão: o front não foi tocado.
4. **A rota nova não tem teste de API próprio** além do que a varredura de contrato cobre; ela é exercitada
   indiretamente pelo caminho do G1-l3. Fica registrado como pendência, não como feito.
5. **`senha_min = 10` é mudança de política de produto**, não só de código: inquilino com `senha_min: 8`
   escrito em `config.auth` continua em 8, mas quem não escreveu nada passa a exigir 10 na PRÓXIMA troca de
   senha (senha já gravada não é invalidada). Vale confirmar com o dono antes do merge.

## 10. Arquivos

Código: `app/auth/ldap.py` · `app/auth/comum.py` · `app/auth/rotas_login.py` · `app/auth/rotas_usuarios.py` ·
`app/auth/rotas_tokens.py` · `app/auth/sessao.py` · `app/auth/politica.py` · `app/limites.py` ·
`app/geocodificador/rotas_esri.py` · `app/uploads/rotas.py` · `app/ingestao/rotas.py` · `app/saude.py`
Banco: `db/migracoes/20260906T1611_g1_identidade_conserto.sql`
Testes: `tests/unit/test_contrato_guarda.py` (novo) · `tests/unit/test_arvore_limpa_importa.py` (novo) ·
`tests/api/test_ataque_g1_adversario.py` e `tests/api/ldap/test_ataque_g1_ldap.py` (marcas)
Docs: `docs/LIMITES.md` (regerado) · `docs/adr/0002-identidade-e-acesso.md` · `CHANGELOG.md`

## 11. Regressão medida — o que a suíte diz, e contra qual linha de base

O worktree `/home/dev/plataforma/wt/g1base` (ramo `wt/g1base`, commit `2fe849d` = `master`) roda contra a
MESMA base `plat_tg1fix`. Toda falha que aparece nos dois é da árvore, não deste ramo.

```
venv/bin/pytest tests/unit tests/api/test_login.py test_sessao.py test_usuarios.py test_eu.py test_org.py
  test_tokens.py geocodificador uploads ingestao test_privilegios_declarados.py test_privilegios_matriz.py
  test_eventos.py test_docs.py test_cabecalhos.py test_ataque_g1_adversario.py -m "not lento"
```

Falhas que existem TAMBÉM em `master` na mesma base (não deste ramo, e nenhuma foi consertada aqui):
- `test_migracoes_nome_e_dependencia::test_a_familia_legada_esta_fechada_no_ultimo_numero_existente` —
  `049_convite_resolver_config.sql` foi criado com número de três dígitos por outra trilha;
- `test_sessao::test_sessao_ociosa_expira` (`PLAT_TESTE_OCIOSA_S` não pega no cliente de sessão);
- 3 de `test_usuarios` (o `execute_values` fura o `CursorSchemaAmbiente`; o próprio adversário registrou);
- 4 de `uploads`, 2 de `test_privilegios_matriz`, 10 de `geocodificador` (CNEFE não instalado nesta base);
- `test_eventos::test_toda_rota_de_escrita_tem_evento_declarado` — 10 rotas de `conexoes`, `eu/foto` e
  `importacoes`, de outras trilhas, sem entrada em `EVENTOS_POR_ROTA` (a rota NOVA deste ramo tem a dela).

Falhas causadas por este ramo e já corrigidas no commit `3f48bce`: os exemplos de composição de senha com 8
caracteres (`tests/unit/test_politica.py`, `tests/api/test_eu.py`) passaram a 10, o prefixo do token passou a
ser conferido contra `limites.TOKEN_PREFIXO_TAMANHO`, e `docs/openapi.json` recebeu a declaração das duas
operações de saúde.

Limpeza da linha de base quando não for mais necessária:
`git -C /home/dev/plataforma/enterprise worktree remove /home/dev/plataforma/wt/g1base && git branch -D wt/g1base`
