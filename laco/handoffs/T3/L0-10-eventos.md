# Handoff — item L0-10-eventos-historico (testador + backend, sub-tarefa: cobertura de eventos)

**Objetivo.** Confirmar a cláusula central do portão do item: "toda rota que altera estado grava 1
evento (teste enumera rotas de escrita do OpenAPI e exige evento correspondente; cobertura = 100 %
medida)" e "plat_app não consegue UPDATE/DELETE em evento (permission denied)". Escopo estrito:
cobertura de eventos, não a tela Auditoria/partição mensal/exportação CSV do resto do item.

## O que fiz

1. **Enumerei as rotas de escrita do OpenAPI vivo** (`curl http://127.0.0.1:8150/api/openapi.json`,
   serviço `plat-api` :8150) filtrando POST/PUT/DELETE/PATCH: **75 rotas**. Confirmei que
   `docs/openapi.json` comitado (o que os testes de fato leem, via `arquivo_openapi()` em
   `tests/api/conftest.py`) tinha exatamente o mesmo conjunto de caminhos nesse instante — o teste
   não está medindo um contrato desatualizado.
2. **Cruzei as 75 rotas contra `tests/api/eventos_esperados.py`**: cobertura já era **100 % antes de
   eu tocar em qualquer coisa** — 75 entradas, 0 faltando, 0 sobrando. A hipótese do item ("rotas
   novas de L0-11/L2-04/L6-01 podem ter ficado de fora") não se confirmou: as rotas de L0-11
   (`/api/arquivos`, `/api/arquivos/{sha256}`) já estavam declaradas (sem evento, com motivo
   documentado — arquivo tem `plat.arquivo` + `plat.log_acesso` como rastro, mesmo padrão de
   `/api/eu/2fa/iniciar`); os sub-itens de L2-04/L6-01 que tocam rota (ex.: `L2-04-b-parser-where-ast`,
   `L6-01-a-procedencia-acervo`) ainda não expõem rota de escrita nova — continuam `pendente` no
   backlog, exceto os dois `entregue`, que não adicionam endpoint HTTP.
3. **Rodei o teste que já existe** (`tests/api/test_eventos.py::test_toda_rota_de_escrita_tem_evento_declarado`
   + `tests/api/catalogo/test_eventos_e_seguranca.py`): verde antes de qualquer mudança minha.
4. **Conferi no código, rota por rota, as 3 entradas com lista vazia** (nenhum evento declarado) para
   não aceitar "sem evento" sem verificar que não é bug: `POST/DELETE /api/arquivos*`
   (`app/rotas_arquivos.py`, confirmado sem chamada a `registrar_evento`) e `POST /api/eu/2fa/iniciar`
   (`app/auth/rotas_eu.py:162`, que faz UPDATE em `plat.usuario` mas não liga `totp_ativo` — o motivo
   já escrito no comentário do dict bate com o código: só o `/confirmar` liga a conta).
5. **Gap real encontrado, fora da parte de cobertura de rota**: o portão também exige "plat_app não
   consegue UPDATE/DELETE em evento". `tests/api/test_funcoes_seguras.py::test_plat_app_sem_escrita_nas_tabelas_protegidas`
   já parametrizava `UPDATE plat.evento SET tipo = 'usuarios/sair'` mas **não tinha o caso DELETE**.
   Acrescentei `"DELETE FROM plat.evento"` à mesma lista parametrizada (1 linha).
6. **Confirmei por fora, com psql direto como `plat_app`** (não só via pytest), que UPDATE e DELETE
   em `plat.evento` são negados:
   ```
   $ PGPASSWORD=*** psql -h 127.0.0.1 -U plat_app -d iagro_sat
   UPDATE plat.evento SET tipo='usuarios/sair' WHERE tenant_id=1;
   ERROR:  permission denied for table evento
   DELETE FROM plat.evento WHERE tenant_id=1;
   ERROR:  permission denied for table evento
   ```
   Também com `\dp plat.evento`: `plat_app=r/postgres` — só SELECT, nem INSERT direto (a escrita é
   só pela função `SECURITY DEFINER` `plat.evento_registrar`, já coberta por
   `test_evento_registrar_sem_contexto_levanta`).

## Evidência (comando + saída)

A árvore principal (`/home/dev/plataforma/enterprise`) está com **muitas trilhas concorrentes em
voo neste exato turno**, todas sem commit ainda: LDAP/AD (`app/auth/ldap.py`, `db/migracoes/025_provedor_ldap.sql`),
roteamento OSRM (`app/rede/`, `/api/rota` `/api/matriz` `/api/isocrona`, que a própria trilha já
somou a `eventos_esperados.py` com justificativa própria), motor de expressão (`app/expressao/`),
homologação (`db/migrar_homolog.sh` etc.), jobs periódicos. Rodar `make check` cheio nessa árvore
agora mede o estado a meio caminho de outras trilhas, não o meu. Para não medir ruído alheio,
isolei em **git worktree a partir do HEAD real no momento** (commit `a108eeb`, depois `c193765`
— este último não toca rotas), apliquei só o meu diff de uma linha e rodei ali:

```
$ git worktree add --detach $WT HEAD   # a108eeb
$ git apply meu_diff.patch             # +1 linha em tests/api/test_funcoes_seguras.py
$ flock .../.pytest.lock -c 'venv/bin/ruff check app tests docs/gerar_limites.py'
All checks passed!
$ flock .../.pytest.lock -c '! grep -rnI ... -f tests/marcadores.regex ...'   # sem-marcador
(0 linhas — exit 0)
$ flock .../.pytest.lock -c 'venv/bin/python docs/gerar_limites.py --check'
(exit 0)
$ flock .../.pytest.lock -c 'venv/bin/pytest -m "not lento" tests/api/test_funcoes_seguras.py \
    tests/api/test_eventos.py tests/api/catalogo/test_eventos_e_seguranca.py -v'
tests/api/test_eventos.py ..
tests/api/catalogo/test_eventos_e_seguranca.py ..F...
tests/api/test_funcoes_seguras.py F................... (19 passed, 1 failed)
=== 2 failed, 26 passed ===
```

As **2 falhas são idênticas e fora de escopo**: `test_nenhuma_funcao_com_execute_para_public` e
`test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app` acusam `provedor_ldap_de` (+2
funções) com `EXECUTE` para `PUBLIC` — fato real do banco (a migração `025_provedor_ldap.sql`,
ainda não commitada, aplicou as funções sem o `REVOKE EXECUTE FROM PUBLIC` que `010/012/013/016/
019/024` já usam). Isso é do item de LDAP/AD, não deste; **reportado abaixo para quem estiver com
aquele item.** O meu caso novo (`DELETE FROM plat.evento`) está dentro dos 19 que passaram.

## Cobertura — números exatos

| | antes | depois |
|---|---|---|
| rotas de escrita no OpenAPI vivo | 75 | 75 (inalterado) |
| entradas em `eventos_esperados.py` | 75 | 75 (inalterado — nenhuma faltava) |
| cobertura | 100 % (75/75) | 100 % (75/75) |
| caso pytest `plat_app` × `plat.evento` | só UPDATE | UPDATE **e DELETE** |

Nenhuma entrada foi inventada ou removida de `eventos_esperados.py`: a hipótese de gap do item não
se confirmou nesta rodada. O único ajuste de código foi a linha de teste do DELETE.

## Riscos / achados

1. **`app/auth/rotas_eu.py:162` (`/2fa/iniciar`) faz UPDATE sem evento** — decisão já documentada
   (só liga a conta no `/confirmar`), não é bug; deixei como está.
2. **Migração `db/migracoes/025_provedor_ldap.sql` sem REVOKE EXECUTE FROM PUBLIC** — bug real,
   fora do meu item, de uma trilha concorrente ainda não commitada. Não toquei (risco de colidir
   com quem está no meio da edição); registrando aqui para o gerente rotear.
3. **Colisão de numeração de migração**: vi `025_provedor_ldap.sql` e `025_jobs_manutencao_analyze.sql`
   coexistindo como untracked ao mesmo tempo (2 trilhas pegaram o mesmo número). Também fora de
   escopo deste item, mas repito o alerta do próprio guia do laço: conferir `ls db/migracoes | tail -1`
   de novo bem no fim, não só no começo.
4. **`docs/openapi.json` no working tree principal diverge do que está no ar** (tem `/api/rota`,
   `/api/matriz`, `/api/isocrona`, `/api/login/ldap`, `/api/org/ldap*` que o serviço `plat-api`
   rodando ainda não expõe) — reflexo do código em voo de outras trilhas ainda não implantado; não é
   uma divergência que este item precise resolver, só registrando para não confundir quem rodar
   `make openapi` sem saber que o serviço vivo está atrás do working tree agora.
5. **Sem e2e para tela "Auditoria"**: não existe ainda (o resto do item — tela, partição mensal,
   exportação CSV, paridade Esri documentada — não foi tocado nesta sub-tarefa; portanto o item
   segue `pendente` no backlog, não `entregue`).

## Para quem continuar o item L0-10 inteiro

Falta, do portão original: tela "Auditoria" do admin (filtros usuário/período, exportação CSV/JSON
≤ 10 s para 100 mil eventos), partição mensal automática pelo periódico, `docs/PARIDADE.md` com a
paridade Esri (audit logs/portal logs) citando que a leitura por token também é registrada aqui
(diferencial já real: `plat.evento` grava evento de leitura por link/token, o que os logs do
ArcGIS Enterprise não fazem — só falta escrever isso na tabela de paridade). A parte de cobertura
de eventos por rota de escrita, que era o gap nomeado na hipótese, está fechada e não precisa
retrabalho — só monitorar quando novas rotas de L1/L2/L4/L5 nascerem.
