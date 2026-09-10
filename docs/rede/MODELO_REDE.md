# Modelo de elementos da rede de utilidades (item L4-01-modelo-rede)

Contrato do item, o modelo de dado, o importador BDGD e a paridade contra o *Utility Network* do
ArcGIS Pro (a peça de negócio: nós, arestas, subredes e associações). Ver também `docs/PACOTE_REDE.md`
(o catálogo, item L4-01-a) e `docs/rede/TOPOLOGIA.md` (o índice derivado por coincidência, item
L4-01-b); ADR `20260906T2126-modelo-de-elementos-da-rede.md`.

## 1. O que este item entrega e o que ele NÃO é

Três peças da família L4-01 respondem a perguntas diferentes:

| item | pergunta que responde | tabelas |
|---|---|---|
| L4-01-a (pacote de ativos) | o que PODE existir na rede? | `rede_tipo`, `rede_regra`, `rede_dominio`, `rede_tier` |
| L4-01-b (topologia derivada) | onde as feições se TOCAM geometricamente? | `rede_topo_no`, `rede_topo_aresta` |
| **L4-01-modelo-rede (este)** | qual é a rede de NEGÓCIO, com conectividade DECLARADA pela fonte? | `rede_no`, `rede_aresta`, `rede_subrede`, `rede_associacao`, `rede_importacao` |

É sobre o grafo deste item que o pgRouting corre (`plat.rede_menor_caminho`). A diferença para o item
b: aqui a conectividade não é inferida por proximidade geométrica com tolerância — ela é lida do
identificador que a própria fonte declara (na BDGD, `PN_CON`/`PAC`), e o gatilho de cada tabela
recusa qualquer gravação fora do catálogo do pacote.

## 2. O modelo de dado

- `rede_no` — um nó por elemento físico, com `papel` fixo em 4 valores: `juncao` (ponto de conexão
  anônimo, sem tipo de ativo), `dispositivo` (transformador, chave — com `estado` de manobra),
  `fonte` (subestação) e `consumidor` (unidade consumidora). `seq` é o inteiro estável que o
  pgRouting exige; `codigo_externo` é o identificador da fonte.
- `rede_aresta` — um trecho/condutor entre dois `rede_no`, com `comprimento_m` (NULL declarado
  quando a fonte não tem geometria para aquele trecho, nunca zero disfarçado) e `no_origem_seq`/
  `no_destino_seq` copiados pelo gatilho, nunca preenchidos pela aplicação.
- `rede_subrede` — hierarquia por nível estrito (1 subestação → 2 alimentador → 3 transformador →
  4 reservado), pai obrigatoriamente um nível acima; nível 1 é o único sem pai.
- `rede_associacao` — conectividade explícita entre um ativo (dispositivo/fonte/consumidor) e uma
  junção, outro ativo ou um trecho, com `tipo` (`conectividade`/`contencao`/`fixacao`) validado contra
  `plat.rede_regra` do pacote na escrita, não depois.
- `rede_importacao` — auditoria de cada rodada de importação: o que o arquivo declarava por camada, o
  que entrou, e cada desvio nomeado com quantidade e exemplos.

## 3. O importador BDGD (`app/rede_utilidades/bdgd.py`)

Lê um FileGDB de distribuidora (camadas SUB, CTMT, SSDMT, UNTRMT, UNSEMT, SSDBT, RAMLIG, UCBT_tab,
UCMT_tab, PONNOT) e monta: fonte (SUB) → alimentador (CTMT, subrede nível 2) → trecho de MT (SSDMT) →
transformador (UNTRMT, subrede nível 3) → trecho de BT (SSDBT) → consumidor (UCBT_tab/UCMT_tab), com
chave (UNSEMT) entrando com estado de manobra. `inspecionar()` lê o feature count de cada camada
direto do GDB (`pyogrio.read_info`) — essa é a régua contra a qual a contagem inserida é comparada;
tudo o que não bate vira desvio nomeado, nunca some.

**Camada ausente no GDB não é erro** — igual para as 9 camadas do modelo, sem exceção: uma
distribuidora pequena sem PONNOT, sem UNSEMT, ou até sem SUB/CTMT (achado deste item: as duas
primeiras eram as únicas sem esse tratamento, corrigido) entra com contagem 0 declarada e um desvio
único explicando, nunca com a importação inteira abortando.

## 4. Achado de dado real: RAMLIG não tem segundo ponto de conexão nomeado

Medido contra um extrato real de distribuidora (Vale do Taquari/RS, `tests/dados/bdgd_extrato_etb23.gdb`,
conferido também na BDGD completa de 2.418.764 linhas de RAMLIG): `PN_CON_2` vem **vazio em 100%** das
linhas. O manual da ANEEL e o próprio arquivo confirmam por que: o ramal de ligação liga a rede
(`PN_CON_1`, que casa com o `PN_CON` da unidade consumidora em ~95% dos casos medidos) direto ao
CONSUMIDOR — não a uma segunda junção nomeada. `PAC_1`/`PAC_2` são os terminais do próprio ativo
RAMLIG (convenção igual à de SSDMT/SSDBT/UNTRMT), não pontos de rede.

O importador, como está, trata RAMLIG como trecho junção↔junção (mesmo padrão de SSDMT/SSDBT) e por
isso não consegue montar a aresta: toda linha vira o desvio `trecho_sem_ponto_conexao`, nunca um
crash nem um número inventado. **A conectividade do consumidor com a rede não se perde** — a
associação criada em `_consumidores` liga o mesmo `PN_CON` à junção correspondente — mas o ramal em
si, como ativo físico com comprimento, não entra na malha do pgRouting nesta passagem. Modelar
RAMLIG como aresta junção→consumidor (em vez de junção→junção) é decisão de arquitetura que precisa
de UCBT_tab/UCMT_tab processados ANTES de RAMLIG (hoje é depois) e de uma chave de busca por
`PN_CON` nos nós de papel `consumidor` (hoje só `juncao` tem essa chave) — registrado como pendência
do próximo item da linha (`L4-01-c-importador-bdgd` ou `L4-02-*`), nunca escondido atrás de um número
que pareça completo.

## 5. Paridade com o ArcGIS Utility Network — domínios, tiers, associations, subnetworks

A tabela viva fica em `docs/PARIDADE.md` (linha L4). Resumo:

| capacidade Esri | aqui | estado |
|---|---|---|
| *domain network* / *structure network* | `rede_dominio` (item L4-01-a) | feito |
| *tier* com rank/tipo | `rede_tier` (item L4-01-a) | feito |
| *tier group* | não existe como objeto próprio | fora (ADR 0019 §8) |
| nó/aresta com atributo por *asset type* | `rede_no`/`rede_aresta` + `tipo_id` (este item) | feito |
| *containment/attachment association* | `rede_associacao` tipo `contencao`/`fixacao` (este item) | feito, sem consumidor ainda |
| *connectivity association* | `rede_associacao` tipo `conectividade` (este item) | feito |
| *subnetwork* (definição, hierarquia) | `rede_subrede` (este item) | feito |
| *Update Subnetwork* / *Trace* | — | fora (próximos itens L4-02/L4-04) |
| *terminal configuration* | `rede_terminal_config` (item L4-01-a) | feito |
| importador de fonte real com contagem conferida | `bdgd.py` (este item) | parcial — ver §4 |

## 6. pgRouting

`CREATE EXTENSION pgrouting` fica no schema `public` — achado deste item: é objeto único por BANCO,
não por schema de trilha/tenant, e uma segunda `CREATE EXTENSION IF NOT EXISTS ... WITH SCHEMA X` é
no-op se a extensão já existe em QUALQUER schema. Instalar em `public` (nunca reescrito pelo
`CursorSchemaAmbiente`) evita que a primeira trilha a rodar a migração "capture" a extensão para o
schema dela e quebre `pgr_dijkstra` para todas as outras. `plat.rede_menor_caminho(rede, de, para)`
devolve o caminho de custo mínimo (comprimento geodésico), excluindo toda aresta que toca um nó em
estado `aberto` — o comportamento de uma chave normalmente aberta.
