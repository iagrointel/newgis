# Backend — correção de desempenho da lista de itens (L0-03-catalogo, T2)

## Objetivo
`lista_tipo_p95_ms` media 203 ms (mediana 199,7) contra o portão `assert p95 < 100` de
`tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95`. O testador atribuiu a contenção de ambiente; o
gerente refutou isso medindo isolado (conexão httpx reaproveitada, mesma sessão, mesmo momento): `/api/eu`
(só sessão) em 3,9 ms mediana contra `/api/itens?tipo=mapa` com piso fixo de ~170-200 ms sempre — assinatura
de overhead fixo por chamada, não contenção. Pedido: achar a(s) consulta(s) reais com profiling, corrigir e
medir de novo isolado.

## O que fiz
1. Reproduzi o request exato do testador (`scratchpad/testador/desempenho.py`, tenant `demo`, corpus de 11 mil,
   `tipo=mapa&limite=50`) diretamente contra o Postgres (`sudo -u postgres` para achar tenant/usuário, depois
   sessão como `plat_app` com `set_config` igual ao app) e via profiling em Python chamando `listar_ids`/
   `carregar_varios` direto (sem HTTP), com timers por trecho.
2. Isolei: `listar_ids` (contagem + ids ordenados) = ~7 ms. `carregar_varios` (busca os N itens por `SQL_ITEM`)
   = ~180 ms — TODO o piso estava aqui, não na consulta de busca/ordenação.
3. `EXPLAIN (ANALYZE, BUFFERS)` de `SQL_ITEM` para os 50 ids achou duas causas, nenhuma contenção:
   - **JIT disparado em toda chamada.** O plano tinha custo total estimado 105.383 (acima de
     `jit_above_cost=100000`) por causa de `LEFT JOIN LATERAL plat.item_contagens(i.id) c ON true`: a função é
     STABLE mas o planejador assume 1.000 linhas por chamada (default de função de saída múltipla,
     confirmado com `ALTER FUNCTION ... ROWS 1`, que derrubou o custo estimado para 544 e removeu o JIT).
     `EXPLAIN ANALYZE` mostrava "Emission 36-43 ms" só de compilação JIT, repetida em TODA chamada porque a
     consulta não usa prepared statement cacheado entre chamadas (psycopg2 sem `prepare`).
   - **Colunas pesadas buscadas e nunca usadas na lista.** `i.dados` (jsonb) media 58 KB em média e um item do
     corpus chegou a 2,8 MB; `descricao`, `descricao_html`, `termos_de_uso*` também iam na consulta. `item_json`
     só usa esses campos com `completo=True` (nunca passado por `carregar_varios`) — a lista descartava tudo
     isso em Python, mas o Postgres já tinha formatado/destoastado e mandado pela conexão. `EXPLAIN ANALYZE`
     reportava 12-95 ms de "Execution Time", mas o round-trip real (`psql \timing`, mesma consulta, sem
     EXPLAIN) media 92-185 ms — a diferença é exatamente essa serialização+transferência que o EXPLAIN não
     conta (ele materializa as linhas mas não as manda ao cliente).
4. Corrigi as duas causas:
   - `db/migracoes/019_item_contagens_lote.sql`: nova função `plat.item_contagens_lote(uuid[])`, MESMO cálculo
     de `plat.item_contagens` (mesma política de bypass — `SECURITY DEFINER`, dono `postgres` com
     `BYPASSRLS`, contam o total, não "visível a mim", igual ao original), mas para os N ids da página em UMA
     consulta agregada (`GROUP BY`) em vez de uma chamada de função por linha. `plat.item_contagens` continua
     existindo e é usada por `GET /api/itens/{id}` (uma chamada só, não é N+1 ali).
   - `db/migracoes/020_item_contagens_rows.sql`: `ALTER FUNCTION plat.item_contagens(uuid) ROWS 1` (era o
     default 1000) — estimativa correta para a rota de item único, sem mudar nada de comportamento.
   - `app/catalogo/comum.py`: `SQL_ITEM_LISTA` (derivada de `SQL_ITEM` por substituição de texto, para não
     duplicar o SQL e evitar deriva) sem a LATERAL de contagens e com `dados`/`descricao`/`descricao_html`/
     `termos_de_uso*` trocados por `NULL` — só para a lista. `contagens_lote(cur, ids)` chama a função em lote
     uma vez.
   - `app/catalogo/rotas_itens.py`: `carregar_varios` passou a usar `SQL_ITEM_LISTA` + `contagens_lote` (uma
     consulta a mais, em vez de 50 chamadas de função) e mescla as 4 contagens em cada linha antes de
     `item_json`. Se algum dia alguém chamar `carregar_varios(..., completo=True)` (hoje nenhum chamador faz
     isso), cai para `SQL_ITEM` cheio em vez de devolver `dados`/`descricao` vazios por engano.
5. Apliquei as migrações (`sudo bash db/migrar.sh`) e **reiniciei `plat-api.service`** (rodava desde antes das
   minhas mudanças; sem reiniciar, o código antigo continuava servindo `plat.iagrointel.com`).
6. Medi de novo isolado, mesma metodologia do gerente (`httpx.Client`, conexão reaproveitada, aquecimento fora
   da conta, 20 amostras) e rodei `scratchpad/testador/desempenho.py` (o script real do testador) contra o
   serviço reiniciado.
7. `make check-rapido` (lint + sem-marcador + teste) sob `flock /home/dev/plataforma/laco/.pytest.lock`:
   612 passed. Também rodei `make check` completo (inclui e2e): 1 falha em
   `tests/unit/test_vendor.py::test_todo_arquivo_do_vendor_esta_em_versoes_com_sha_e_licenca` — **confirmada
   pré-existente e fora de escopo** (reproduz igual com `git stash` das minhas mudanças; é sobre fontes novas em
   `web/vendor/` de outro agente, não tocado por mim).

## Evidência literal (antes → depois)

Mesma metodologia do gerente (httpx, conexão reaproveitada, mesma sessão), contra `https://plat.iagrointel.com`:

```
antes (do pedido do gerente):
  /api/eu (só sessão)                    mediana   3,9 ms   p95  20,5 ms
  /api/itens?tipo=mapa&pagina=1          mediana 194,7 ms   min 173,7 ms   p95 199,9 ms
  /api/itens?pagina=1 (sem filtro)       mediana 207,3 ms   min 194,6 ms

depois (mesmos endpoints, plat-api.service reiniciado com o código novo):
  /api/eu                                mediana   3,9 ms   p95  21,0 ms   max  22,3 ms
  /api/itens?tipo=mapa&pagina=1          mediana  21,8 ms   min  19,1 ms   p95  24,1 ms   max 24,4 ms
  /api/itens?pagina=1 (sem filtro)       mediana  33,8 ms   min  28,8 ms   p95  51,4 ms   max 51,6 ms
```

`scratchpad/testador/desempenho.py` (script real do testador, corpus de 11 mil) depois do fix:
```
lista_tipo_p95_ms      p95=   40,9 ms  mediana=   22,6  min=  19,9 max=   59,8  n=20  resultados=1505  portao 100 ms: CUMPRE
facetas_p95_ms         p95=   32,9 ms  mediana=   28,4  min=  23,8 max=   32,9  n=10
cursor: 200 paginas, 10000 ids distintos, 0 repetidos (total declarado 10078)
```
(sem duplicata/lacuna na paginação por cursor — confere que `carregar_varios` não mudou a ordem nem perdeu item)

Suite (`tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95`, TestClient in-process, registrado em
`tests/medidas/L0-03-catalogo.json` com `PLAT_GRAVAR_MEDIDAS=1`):
```
lista_tipo_p95_ms: 203,0 ms (mediana 199,7) → 50,8 ms (mediana 23,8)
facetas_p95_ms:     25,8 ms → 25,5 ms  (não tocado pelo fix; consistente)
```

Profiling isolado direto em Python (sem HTTP, `listar_ids`/`carregar_varios` chamados na mesma conexão,
15 amostras, mediana):
```
                    antes       depois
listar_ids           6,7 ms      4,8-6,4 ms   (não mudou; nunca foi o problema)
carregar_varios     179,7 ms      9,4 ms
total               187,8 ms     14,7 ms
```

EXPLAIN ANALYZE de `SQL_ITEM` para 50 ids (isolando as duas causas, medidas separadamente):
```
consulta completa (LATERAL item_contagens, custo estimado 105.383 > jit_above_cost)     94,0 ms execução
  ↳ com jit=off                                                                          35,8 ms execução
  ↳ sem a LATERAL de item_contagens (jit não dispara mais)                               12,5 ms execução
custo estimado depois de ALTER FUNCTION item_contagens ROWS 1                               544 (era 105.383)
plat.item_contagens_lote(uuid[]) para os 50 ids em UMA chamada                            4,8 ms execução
round-trip real (psql \timing, sem EXPLAIN) da consulta completa                    155-184 ms
round-trip real sem item_contagens (mas ainda com dados/descricao/termos_de_uso)      92-105 ms
```
Tamanho das colunas pesadas nos 50 itens de teste: `dados` (jsonb) média 58.379 bytes, máximo 2.796.268 bytes
(2,8 MB) num item; soma de `dados+descricao+descricao_html` nos 50 = 2.919.124 bytes (~2,85 MB) — é essa
formatação+transferência que o EXPLAIN ANALYZE não conta e que fechava a diferença entre 12-95 ms (execução)
e 92-185 ms (round-trip real).

## Para o gerente
- Causa real, medida (não suposição): (1) N+1 de `plat.item_contagens` por LATERAL disparando JIT em toda
  chamada por causa da estimativa de linhas errada da função — mesmo padrão que a 017 já tinha corrigido para
  `pode_ler`; (2) a lista buscava `dados`/`descricao*`/`termos_de_uso*` (colunas pesadas, jsonb até 2,8 MB) que
  `item_json` descarta quando `completo=False` — pagava o custo no Postgres e na rede antes de jogar fora em
  Python.
- Correção: `plat.item_contagens_lote` (migração 019, agregação única para a página inteira) +
  `ALTER FUNCTION item_contagens ROWS 1` (migração 020) + `SQL_ITEM_LISTA` sem as colunas pesadas
  (`app/catalogo/comum.py`) + `carregar_varios` usando as duas (`app/catalogo/rotas_itens.py`).
  `GET /api/itens/{id}` (item único) não mudou — continua com `SQL_ITEM` completo, porque ali 1 chamada não é
  N+1 e o cliente pode precisar de `dados`/`descricao` no detalhe.
- `p95` de `lista_tipo_p95_ms` medido de novo isolado (httpx, conexão reaproveitada, 20 amostras):
  **24,1 ms** (era 199,9 ms) e pelo script real do testador **40,9 ms** com o corpus de 11 mil — os dois
  cumprem o portão de <100 ms com folga. `make check-rapido` = 612 passed. `plat-api.service` reiniciado (a
  correção só valia para conexões novas do processo antigo; agora está rodando o código novo).
- Fora de escopo, achado ao rodar `make check` completo: `tests/unit/test_vendor.py` falha por causa de fontes
  novas em `web/vendor/` (não commitadas, aparentemente trabalho de outro agente em andamento) — reproduz
  igual sem as minhas mudanças (`git stash`), não é meu para consertar; sinalizando para quem estiver com o
  item de frontend/vendor.
- Commit: `79490e9` — "fix(catalogo): elimina N+1 de item_contagens e colunas pesadas na lista de itens".
