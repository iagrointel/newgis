# ADR 20260906T2126 — Modelo de elementos da rede (nós, arestas, subrede, associação)

Data: 2026-09-06/07 · Item: `L4-01-modelo-rede` · Estado: aceito · Papéis: redes, arquiteto, dados, backend, adversário

## 1. Onde este item fica entre os irmãos da família L4-01

Três peças já existiam ou nasceram na mesma trilha e não se repetem aqui:

- `L4-01-a-pacote-de-ativos` (ADR 0019): o CATÁLOGO — o que PODE existir na rede (`plat.rede_tipo`,
  `plat.rede_regra`, domínio, tier, terminal), declarado em pacote JSON por disciplina.
- `L4-01-b-topologia-derivada` (ADR 0020): um ÍNDICE reconstruído por coincidência geométrica sobre
  camadas de feição genéricas (`plat.rede_feicao_ponto/linha`), sem conectividade declarada pela fonte.
- **Este item**: a REDE DE NEGÓCIO propriamente dita — nós tipados (junção, dispositivo, fonte,
  consumidor), arestas (trecho/condutor), hierarquia de subrede (subestação → alimentador →
  transformador) e associação explícita nó↔nó / nó↔aresta, quando a fonte DECLARA a conectividade
  (a BDGD faz isso por `PN_CON`/`PAC`, ao contrário de um shapefile solto). É sobre este grafo que o
  pgRouting corre (`plat.rede_menor_caminho`), não sobre o índice do item b.

## 2. Decisão: nó por papel, não por camada da fonte

`plat.rede_no.papel` tem 4 valores fixos (`juncao`, `dispositivo`, `fonte`, `consumidor`), independente
de quantas camadas de origem existam por disciplina. A BDGD tem SUB (fonte), CTMT/SSDMT/SSDBT (viram
arestas, não nós), UNTRMT/UNSEMT (dispositivo), UCBT_tab/UCMT_tab (consumidor) e PONNOT (só geometria,
funde por `codigo_externo`). Um pacote de água ou gás mapeia para o mesmo papel sem mudar o esquema —
é o pacote (item a) que declara `codigos_fonte` por tipo, este item só materializa nós/arestas com o
`tipo_id` que o pacote resolveu.

## 3. Conectividade explícita: gatilho recusa fora do catálogo, não a auditoria depois

`rede_associacao_validar` (na migração) confere a regra em `plat.rede_regra` NA ESCRITA — associação
fora do catálogo declarado pelo pacote nunca entra na tabela, o que é mais forte que validar depois
por relatório. Para associação nó-junção (a junção é sempre anônima, sem `tipo_id`) a regra é
conferida contra os tipos das ARESTAS que já tocam aquela junção, porque a junção em si não carrega
tipo — decisão equivalente à da Esri, que também não tipa o vértice de coincidência simples.

## 4. Hierarquia de subrede por nível estrito, não por grafo livre

`plat.rede_subrede_bdgd.nivel` vai de 1 (subestação) a 4, e o gatilho `rede_subrede_bdgd_validar` exige que o
pai tenha nível exatamente `nivel - 1`. Isso torna ciclo impossível por construção (uma volta exigiria
nível constante em algum ponto do caminho) — mais barato que detectar ciclo em runtime toda vez que
alguém reatribuir `pai_id`. Custo aceito: uma hierarquia com "salto" real (subestação alimentando um
transformador direto, sem alimentador nomeado) não é representável sem um nível intermediário
artificial; não apareceu na BDGD testada e fica como limitação registrada.

## 5. `seq` inteiro ao lado do `id` uuid — pgRouting não aceita uuid

pgRouting (`pgr_dijkstra`) exige nó/aresta como inteiro. `rede_no.seq`/`rede_aresta.seq` são
`GENERATED ALWAYS AS IDENTITY`, estáveis e nunca escritos pela aplicação; o gatilho da aresta copia
`no_origem_seq`/`no_destino_seq` do nó no momento da escrita, então a função de menor caminho nunca
precisa fazer join com a tabela de nós para montar o grafo — só filtra por `rede_id` e por nó `aberto`.

## 6. Estado de manobra mora no nó (dispositivo), nunca na aresta

Um trecho não tem "aberto/fechado" — quem abre ou fecha é a chave/disjuntor (`UNSEMT.P_N_OPE` na
BDGD: `A` normalmente aberta, `F` normalmente fechada; qualquer outro valor, inclusive vazio, não
afirma nada e fica `na`). `plat.rede_menor_caminho` exclui do grafo toda aresta que TOCA um nó
`aberto`, o que é o comportamento de uma chave normalmente aberta de verdade: a rede continua
conectada fisicamente, mas o caminho de energia não passa ali.

## 7. Fronteiras honestas aceitas nesta passagem

- **Sem HTTP ainda**: `app/rede_utilidades/bdgd.py` expõe `importar(cur, ...)` como função de
  biblioteca; não há `POST /api/rede/{id}/importar-bdgd` nesta entrega — a importação de uma BDGD real
  (centenas de MB, minutos) pertence ao desenho de job assíncrono (fila de jobs já existe no produto),
  e amarrar isso a uma rota síncrona seria prometer um comportamento que não foi medido em arquivo
  grande. Registrado como pendência, não escondido.
- **`tier group` e *Update Subnetwork*/*Trace*** continuam fora (ver `docs/PARIDADE.md`, itens da
  linha L4 seguintes: `L4-02-*` traçado, `L4-04-*` subredes e diagrama). Este item entrega a
  DEFINIÇÃO da subrede (a tabela e a hierarquia), não a atualização incremental nem o resultado de
  traçado — a mesma fronteira que o ADR 0019 já registrou para tier group.
- **Camada opcional ausente no GDB não é erro**: distribuidora pequena sem PONNOT, ou sem alguma
  camada de trecho/dispositivo/consumidor, entra com contagem 0 declarada e um desvio único
  (`ponnot_ausente` etc.), nunca uma linha de exceção por feição.

## 8. Prova (turno de fechamento)

Ver `tests/api/test_rede_modelo.py` (importador rodado contra o pacote apontado por `PLAT_REDE_REFERENCIA_GDB`, um FileGDB real
no formato ANEEL, camadas SUB/CTMT/SSDMT/UNTRMT/SSDBT/UCBT_tab/RAMLIG/UNSEMT/UCMT_tab/PONNOT) e
`tests/medidas/L4-01-modelo-rede.json` para os números. `inspecionar()` é a régua: a contagem inserida
por camada é comparada contra `pyogrio.read_info(..., layer=camada)["features"]`, com toda diferença
explicada por um desvio nomeado (nunca um número sem explicação).
