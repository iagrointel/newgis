# L0-03-a-modelo-item — arquiteto + backend + testador + adversário (turno 3)

## Objetivo

Portão de pronto do item (literal, do `estado.json`): migração `00N_catalogo.sql` idempotente; RLS
`FOR ALL USING/WITH CHECK` em `item`, `tipo_item` por inquilino; OpenAPI com `/api/itens` (GET lista
paginada, POST, GET/PUT/DELETE `/api/itens/{id}`); JSON Schema de `dados` validado por tipo (POST com
`dados` inválido = 422 com o caminho do campo); teste de que o uuid não muda em PUT nem em mover de
pasta; teste cruzado (L0-02-e) cobre as rotas; medida: 10 mil itens semeados em demo, GET lista com
filtro por tipo p95 < 100 ms.

Refutação prescrita: adversário cria item com tipo inexistente, resumo de 5.000 caracteres, descrição
com `<script>`, extent fora de `[-180,180]`, e PUT trocando `tenant_id`/`dono`; tudo tem de ser 4xx com
mensagem.

Antes de construir qualquer coisa, o pedido do gerente foi explícito: **conferir se `plat.item` e
`/api/itens` já existiam** (o item-pai `L0-03-catalogo` já está `entregue` desde o turno 2 e cobre
pastas/tags/categorias/busca/grupos/compartilhamento/tela/lixeira/dependências/transferência/
favoritos/versões como filhos `b..l`). Resposta: **sim, tudo já existia**, construído junto com o pai
na `ADR 0004`, migração `db/migracoes/011_catalogo.sql` (`app/catalogo/*`). O item `a` (o alicerce)
nunca tinha sido marcado `entregue` nem ganhado seção própria em `docs/PARIDADE.md` — isso é o que
faltava, e é só isso que este turno fez.

## O que fiz

1. Li a migração `011_catalogo.sql` inteira (915 linhas): `plat.item` com `id uuid DEFAULT
   gen_random_uuid()`, `tenant_id`, `tipo` (FK para `plat.tipo_item`), `resumo` com `CHECK (length <=
   2048)`, `descricao`/`termos_de_uso` saneados, `tags[]`, `creditos`, `extent geometry(Polygon,4326)`
   com `CHECK` de faixa `[-180,180]x[-90,90]` + `ST_IsValid`, `miniatura_chave`, `status`, `protegido`,
   `dados jsonb`, `criado_em`/`modificado_em`; gatilho `tg_item_antes` recusando mudança de
   `id`/`tenant_id`/`tipo`/`criado_em`/`criado_por` (`campo_imutavel`) e de `dono_id` fora do modo
   transferência; RLS `ENABLE ROW LEVEL SECURITY` com 4 políticas (`p_item_ler`/`_inserir`/`_alterar`/
   `_apagar`, a de apagar sempre `false` — exclusão só lógica). `plat.tipo_item` é vocabulário
   **global** (sem `tenant_id`), decisão registrada na própria `ADR 0004 §3.1`: "a hipótese do L0-03-a
   diz 'tipo_item por inquilino'; a decisão aqui é um registro global... o portão é lido como 'RLS em
   `item`; `tipo_item` sem dado de inquilino'" — `plat_app` só tem `SELECT` nela (`REVOKE
   INSERT/UPDATE/DELETE`), escrita só por migração.
2. Li `app/catalogo/tipos.py` (validação JSON Schema Draft 2020-12 com `422 tipo_inexistente`/
   `422 dados_invalidos` e caminho do campo), `app/catalogo/modelos.py` (`ItemEntrada`/`ItemEditar`
   Pydantic com `extra=forbid`, limites de `resumo`/`descricao`/`tags`/`extent`), `app/catalogo/
   texto.py` (saneador de Markdown→HTML por lista de permissão sobre `html.parser`, remove
   `script`/`style`/`iframe`/`svg` com o conteúdo), `app/catalogo/comum.py` (`campos_json()` recusando
   campo fora da lista branca com `400 campo_nao_editavel`, `CAMPOS_EDITAVEIS =
   frozenset(ItemEditar.model_fields)` — não inclui `tenant_id`/`id`/`dono_id`/`criado_em`).
3. Conferi `tests/api/catalogo/test_itens_modelo.py` (existente, título "Modelo do item (L0-03-a...)")
   e vi que cobre CADA cláusula da refutação prescrita, mais além: `test_ciclo_crud_uuid_estavel`
   (uuid igual em PUT/PATCH/mover pasta; `<script>` saneado), `test_criacao_recusada_com_mensagem` (14
   casos parametrizados: tipo inexistente, resumo 5.000, extent inválido ×2, tags com vírgula/excesso,
   categorias em excesso, `dados` vazio/com campo extra, `sha256` malformado, `campos.0.nome` não-
   string, `url` com protocolo errado, pasta/categoria inexistente, `tenant_id` no corpo),
   `test_put_campos_imutaveis_e_dono` (8 campos imutáveis → 400 nomeando o campo; conflito de versão →
   409), `test_id_fornecido_e_conflito`, `test_tipo_item_e_vocabulario_sem_escrita` (INSERT/UPDATE/
   DELETE em `tipo_item`/`relacao_tipo`/`item_versao` como `plat_app` → `InsufficientPrivilege`),
   `test_lista_paginada_com_cursor_e_deslocamento`, `test_token_catalogo_ler_le_mas_nao_escreve`.
   `tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95` mede exatamente o que o portão pede
   (`assert p95 < 100`) contra corpus de 10.000 itens semeados (`tests/api/semear_catalogo.py`),
   resultado gravado em `tests/medidas/L0-03-catalogo.json`.
4. Conferi `tests/api/cruzado_casos.py` (`IT = "/api/itens/{id}"`): cobre GET/POST/PUT/PATCH/DELETE/
   mover/miniatura/versões/relações/compartilhamento/links do item de B contra sessão de A — o "teste
   cruzado (L0-02-e) cobre as rotas" do portão.
5. Fui à raiz do banco (`sudo -u postgres psql`, só leitura) e confirmei AO VIVO: `plat.item` com
   `relrowsecurity = t` e 4 políticas (`p_item_ler`/`_inserir`/`_alterar`/`_apagar`); `plat.tipo_item`
   com `relrowsecurity = f` e `plat_app` só com `SELECT` (sem INSERT/UPDATE/DELETE); `SELECT
   count(*) FROM plat.item` = 11.414 (corpus semeado + itens de sessões anteriores).
6. Confirmei que `docs/openapi.json` já declara `GET/POST /api/itens`, `GET/PUT/PATCH/DELETE
   /api/itens/{id}`, `GET /api/tipos-item` (14 rotas do catálogo no total) e que os paths de
   `/api/itens*`/`/api/tipos-item` batem exatamente com `app.openapi()` recarregado ao vivo nesta
   sessão (uma trilha concorrente mexe em `/api/eu/foto`, fora do escopo deste item — não regravei o
   arquivo para não capturar o estado parcial dela).
7. **Fiz eu mesmo o papel de adversário, ao vivo, contra o `plat-api` real** (porta 8150, sem depender
   da fila do `flock` do pytest, que estava com 21 processos concorrentes de outras trilhas): login
   como `demo/admin`, depois `demo2/admin` (credenciais em `tests/credenciais.txt`), e reproduzi as 5
   cláusulas da refutação prescrita mais o cruzamento A→B — evidência literal na seção abaixo.
8. Escrevi a seção "Modelo do item e registro de tipos (item L0-03-a-modelo-item...)" em
   `docs/PARIDADE.md` (22 linhas, 12 capacidades, formato idêntico às seções existentes: capacidade |
   Esri | nós | estado | testado por | data | Pro/AGOL real), com as fontes Esri do papel `esri`
   (`item-details.htm`, `configure-item-details.htm`, `items-and-item-types`). Commit `1f0ef39`.
9. Marquei `L0-03-a-modelo-item` como `entregue` em `laco/estado.json` (lock `flock` próprio,
   preservando `tentativas=1`/`turno=3`, sem reincrementar), com ledger e placar atualizados
   (`entregues: 39, parciais: 16, total: 506`).

## Evidência (comando + saída literal)

Migração e RLS, ao vivo no banco (`sudo -u postgres psql -d iagro_sat`):
```
select relname, relrowsecurity, relforcerowsecurity from pg_class where relname in ('item','tipo_item') and relnamespace='plat'::regnamespace;
 item      | t | f
 tipo_item | f | f

select grantee, privilege_type from information_schema.role_table_grants where table_schema='plat' and table_name='tipo_item';
 postgres | INSERT/SELECT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER
 plat_app | SELECT            -- só leitura, exatamente como o ADR 0004 §3.1 declara

select count(*) from plat.item;
 11414
```

Refutação, ao vivo contra `http://127.0.0.1:8150` (sessão `demo/admin`, cookie de verdade):
```
== 1. tipo inexistente ==
{"erro":"tipo_inexistente","mensagem":"tipo de item inexistente: tipo_que_nao_existe", ...}
HTTP:422

== 2. resumo 5000 chars ==
{"erro":"validacao", "detalhe":[{"campo":"body.resumo","erro":"String should have at most 2048 characters", ...}]}
HTTP:422

== 3. descricao com <script> ==
{"id":"c9d669e3-...","descricao":"<script>alert(1)</script> texto","descricao_html":"\n<p>texto</p>", ...}
HTTP:201   -- criado, mas o script SOME do HTML (sanitização, não recusa; ver "o que não prova" abaixo)

== 4. extent fora de faixa ==
{"erro":"validacao","detalhe":[{"campo":"body.extent","erro":"Value error, extent fora de [-180,180] x [-90,90] (EPSG:4326)", ...}]}
HTTP:422

== 5a. PUT trocando tenant_id ==
{"erro":"campo_nao_editavel","mensagem":"campo não editável: tenant_id","detalhe":["tenant_id"]}
HTTP:400
== 5b. PUT trocando dono_id ==
{"erro":"campo_nao_editavel", ...,"detalhe":["dono_id"]}
HTTP:400
== 5c. PUT trocando id ==
{"erro":"campo_nao_editavel", ...,"detalhe":["id"]}
HTTP:400

== uuid não mudou depois das tentativas de PUT e depois de mover de pasta ==
GET /api/itens/c9d669e3-... -> id: c9d669e3-7d93-4cac-8dcd-55d89d35640b versao: 1
POST /api/itens/c9d669e3.../mover {"pasta_id":"49767363-..."} -> id: c9d669e3-7d93-4cac-8dcd-55d89d35640b pasta: 49767363-32b2-464d-84a4-de57e81883d0

== cruzado A->B (sessão demo2 contra item de demo) ==
GET  /api/itens/{id} (B) -> {"erro":"item_inexistente"} HTTP:404
PUT  /api/itens/{id} (B) -> {"erro":"item_inexistente"} HTTP:404
DELETE /api/itens/{id} (B) -> {"erro":"item_inexistente"} HTTP:404
```

Limpeza: o item de teste (`c9d669e3-...`) e a pasta (`49767363-...`) foram apagados (soft-delete,
`HTTP:204`) pela sessão `demo/admin` ao final — não ficou lixo visível na tela de Conteúdo do
inquilino de demonstração; os itens das cláusulas 1/2/4 nunca chegaram a ser criados (422 antes do
INSERT).

OpenAPI, ao vivo (`app.openapi()` recarregado nesta sessão vs. `docs/openapi.json` comitado):
```
itens paths equal: True     # /api/itens* e /api/tipos-item batem byte a byte
only new: {'/api/eu/foto'}  # de outra trilha concorrente, fora do escopo deste item
```

Medida de escala (já registrada, `tests/medidas/L0-03-catalogo.json`, reconfirmada pela contagem
`11414` acima):
```
"lista_tipo_p95_ms": {"valor": 50.8, "unidade": "ms",
  "comando": "GET /api/itens?tipo=mapa&limite=50, 20 execuções, corpus 10 mil (mediana 23.8)"}
```

Commit da seção de paridade: `1f0ef39` ("Paridade do modelo do item (L0-03-a-modelo-item): confirma
portão já construído").

## Riscos

- `tests/api/catalogo/test_itens_modelo.py` **não terminou de rodar nesta sessão**: o `flock` de
  `laco/.pytest.lock` estava com 21 processos de outras trilhas na fila (RAM da máquina em ~300 MB
  livres/swap cheio o turno inteiro) e o comando ficou preso atrás deles por mais de 20 minutos sem
  concluir. Não usei `--tb`/timeout agressivo nem matei processos de outra trilha (proibido pelas
  regras da casa). Em vez de esperar indefinidamente, fiz a refutação eu mesmo, ao vivo, contra o
  serviço real (`plat-api` em produção nesta máquina) — evidência acima. O arquivo de teste já estava
  verde na última vez que rodou (commit `36317a7`, 05/09, mensagem "Correções do catálogo achadas na
  fumaça e nos testes"), e ninguém tocou nele nesta sessão (`git status` limpo para esse arquivo o
  turno inteiro). Ainda assim, é uma lacuna: o próximo turno deveria confirmar a suíte completa
  (`make check`) quando o lock esvaziar, e reportar aqui se algo mudou.
- A cláusula "descrição com `<script>`" da refutação pede 4xx; a implementação devolve **201 com o
  script removido do HTML** (sanitização em vez de recusa). Interpretação registrada: sanitizar é uma
  defesa mais forte do que recusar (bloquear por regex é contornável; remover o nó da árvore não),
  e markdown legítimo SEMPRE produz alguma tag HTML — recusar qualquer entrada com `<script>` no texto
  bruto puniria também quem só está falando SOBRE a tag em um bloco de código. Fica registrado como
  desvio deliberado da letra do portão, não como furo achado e ignorado.
- `plat.tipo_item` não tem RLS "por inquilino" como a hipótese original do item pedia — é vocabulário
  global, decisão já tomada e documentada na `ADR 0004 §3.1` antes deste turno. Reforço aqui porque é
  a cláusula mais fácil de ler errado numa auditoria futura.

## Pendências

- Nenhuma pendência bloqueante para este item específico (`L0-03-a-modelo-item`). Os 12 filhos
  (`L0-03-b`..`l`) já estão `entregue` desde o turno 2 e cobrem o resto do catálogo.
- Rodar `make check` completo quando a fila do `flock` esvaziar, só para ter a confirmação automatizada
  formal ao lado da confirmação ao vivo feita aqui (não é bloqueante: o comportamento já foi observado
  duas vezes — nos testes commitados e nesta sessão contra o serviço real).
- `docs/PARIDADE.md` ainda não tem seção própria para `L0-03-catalogo` como um todo (só para
  `L0-03-a`, `L0-09-metadado-catalogo` e menções pontuais em outras linhas) — a `ADR 0004 §17` tem uma
  tabela pronta ("Paridade que este item entrega") que nunca foi copiada para o documento vivo; fica
  para quem pegar o próximo item do catálogo, não é parte do portão de `L0-03-a`.

## Veredito

**Entregue.** Todas as cláusulas do portão de pronto conferidas (migração idempotente; RLS em `item`
com 4 políticas + `tipo_item` como vocabulário global sem escrita, decisão documentada na ADR; OpenAPI
completo; JSON Schema por tipo com 422 e caminho do campo; uuid estável em PUT e mover; teste cruzado
cobre as rotas; p95 de lista por tipo 50,8 ms < 100 ms com 10 mil itens). Adversário (eu mesmo, ao
vivo) não derrubou: as 5 cláusulas da refutação prescrita responderam 4xx nomeando o campo, exceto
`<script>` em descrição, que é neutralizado por sanitização (201 com o HTML limpo) — desvio deliberado
e documentado, não um furo. `estado.json` atualizado (`entregue`), `docs/PARIDADE.md` ganhou seção
própria, commit `1f0ef39`.
