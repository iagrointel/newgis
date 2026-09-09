# ADR 20260909T0045 — interações do painel

Item L2-06-c-acoes-seletores-filtros-cruzados. Gatilho → ações entre elementos do painel (o mesmo modelo do
barramento do L5-07) e o elemento `seletor`; o filtro de um elemento atravessa os outros por SQL no servidor.

## Decisões

1. **Um barramento só, o do L5-07.** O painel não ganha uma segunda máquina de eventos: `web/js/app/barramento.js`
   entra no documento do painel verbatim e o painel registra seus elementos nela. O que é novo é a PONTE
   (`web/js/paineis/interacoes.js`): gatilho do painel → mensagem do barramento; mensagem publicada → repintar os
   elementos-alvo com filtro novo. Regra que o teste guarda: qualquer divergência futura entre o `modelo.js` do
   barramento e o validador do servidor (`app/paineis/interacoes.py`) reprova — a unidade roda o `modelo.js` real
   em node (`tests/app/executar_painel_js.mjs`) contra os mesmos casos da API.
2. **Vistas `v:<id>`, não agregação no navegador.** Cada pedido de elemento é uma vista do L5-07 com o filtro
   acumulado da execução; o URL guarda o ESTADO DAS VISTAS (`v.v:`), por isso a URL copiada reabre com os mesmos
   seletores sem interação (cláusula 5). O filtro de execução do painel (L2-06-b) vira parâmetro `filtro` da
   requisição de dados, nunca é recalculado no cliente.
3. **Relação obrigatória em ação de dado, mesmo na mesma fonte — e a `mesma_fonte` do L5-07 NÃO vale aqui.** No
   dashboard de widget a seleção traduz para `in (ids)`; no painel a origem é uma LINHA de camada, que não tem
   coluna de id estável (a fonte lê uma vista SQL do L2-06-a). Então gatilho de seleção/clique exige relação
   declarada `atributo` (campo_origem → campo_alvo, operador `=`/`in`) ou `espacial` (envelope da origem vira
   `s_intersects` no alvo). Sem relação, o editor recusa com 422 `grafo_invalido` e a mensagem nomeia as duas
   fontes — a cláusula 4 do portão é essa recusa. Aviso de ciclo A→B→A também é validado aqui, como AVISO
   (o barramento corta a recursão em uma volta; `ciclo_ab_ba` medido em `tests/medidas/…json`).
4. **Filtro dinâmico entra pelo CQL2 já auditado, com UM nó novo.** `app/paineis/cql2.py::separar_espacial` aceita
   `s_intersects` na ÚNICA forma que o barramento produz (retângulo alinhado aos eixos de 5 pontos) e a tira da
   árvore: vira caixa `[o,s,l,n]` executada como `ST_MakeEnvelope(%s,%s,%s,%s,4326)` com PARÂMETRO — geometria
   nunca vira texto de SQL. `s_intersects` dentro de `or` é recusado (não separa); outra geometria é recusada.
   O resto do filtro segue pelo tradutor de texto de sempre, e todo nome de campo citado passa pela lista branca
   da fonte (`propriedades()` → `campo_fora_da_fonte`), inclusive o do seletor.
5. **O filtro cruza, não substitui — e zero é contagem legítima.** O seletor de categoria acumula com o filtro fixo
   da fonte e com o filtro de execução (`WHERE fixo AND execução AND seletor`), por isso `via` no seletor derruba o
   indicador da fonte de água a 0 SEM marcar "sem dado": `renderIndicador` só marca vazio com valor ausente, nunca
   com 0. Defeito corrigido no caminho em `app/paineis/dados.py`: com parte de filtro VAZIA o SQL montava
   `WHERE () AND (...)` — agora as partes não vazias entram no `join`.
6. **Latência gatilho→ação é medida no evento, não no repinte.** O portão é 100 ms p95 com 10 mil feições; a
   medição (`web/js/paineis/interacoes.js`, `performance.now()` entre publicar a mensagem e o alvo iniciar a
   ação) fica no MEDIDOR de elemento (`plat.painel_medidor`) e vai para `tests/medidas/…json` junto de
   carga_1min/ram_livre_gb/medido_em. Medido: p95 0,054 ms; pior caso com filtro por atributo 2,08 ms — a ação é
   local (montar filtro + pedir repinte), a requisição de dado é depois e não conta para o gatilho.
7. **A tabela de dado tem RLS forçada por inquilino — a conferência de contagem do e2e roda na MESMA conexão do
   contexto.** `d_demo.c_*` só responde com `plat.tenant_id` gravado na conexão (`tenant_atual()`), e a consulta
   devolve 0 linhas, não erro, sem contexto. Por isso `tests/e2e/test_painel_interacoes.py::_sql` grava o
   contexto (padrão de `tests/api/test_rls.py`) e consulta na mesma conexão — contar "fora" daria 0 e o teste
   passaria ao contrário por acaso. Cada cláusula do portão confere a contagem da tela contra COUNT(*) direto.
8. **`in-list` com teto na origem.** Relação por atributo com `in` corta em 10.000 valores na ORIGEM da ação
   (`barramento.js` do L5-07 verbatim; a ponte corta a seleção no mesmo teto) — 5.000 feições selecionadas é o
   caso medido da refutação (0,88 ms no gatilho). O teto existe para a seleção nunca virar uma lista de 1 milhão
   de ids no corpo do pedido; acima de 10.000 o filtro leva os 10.000 primeiros, de forma determinística.
