# ADR 0020 — A topologia da rede é um índice DERIVADO, nunca a fonte

Data: 2026-09-06 · Item: `L4-01-b-topologia-derivada` · Estado: aceito · Papéis: redes, backend, dados, testador

Segundo item da linha L4. Parte do esquema entregue por `L4-01-a-pacote-de-ativos` (ADR 0019): domínios, tiers,
grupos, tipos, terminais e regras já existem por rede. Este item constrói, a partir das FEIÇÕES da rede, o que
o ArcGIS chama de *Enable Network Topology*.

## 1. Problema

Uma rede de utilidades vira um GRAFO (nós e arestas com custo) para qualquer coisa útil acontecer depois —
traçado, isolamento, cálculo de queda de tensão. O ArcGIS resolve isso com o *utility network*: habilitar a
topologia lê as camadas de feição, aplica regras de coincidência com tolerância, e escreve uma malha de rede
(*network topology*) que fica presa às classes de feição. A malha não é editável diretamente; comandos de
edição a marcam "suja" (*dirty area*) e ela é reconstruída por trecho.

## 2. Decisão: feições continuam feições, topologia é índice reconstruído

`plat.rede_feicao_ponto` (dispositivo) e `plat.rede_feicao_linha` (trecho) são camadas NORMAIS e EDITÁVEIS —
inserir, listar, (editar/apagar ficam para o item de edição de rede). `POST /api/rede/{rede_id}/topologia/
habilitar` lê essas duas tabelas inteiras e escreve `plat.rede_topo_no` e `plat.rede_topo_aresta` do zero:
apaga a topologia anterior da rede e regrava tudo numa transação. Não há leitura incremental do índice
anterior — é reconstrução total, não remendo.

**Fronteira honesta, aceita nesta passagem:** a "área suja" do ArcGIS (marcar só o que mudou e reconstruir só
aquele trecho) NÃO existe aqui. Toda chamada de `habilitar` é uma reconstrução completa. Para o tamanho de
rede testado (dezenas de milhares de feições, `tests/medidas/L4-01-b.json`) isso é rápido o bastante para não
doer; se um dia uma rede for grande o bastante para a reconstrução completa incomodar, a manutenção
incremental é o próximo item da linha, não um retrabalho deste.

## 3. Coincidência geométrica + associação explícita — por que as duas

A hipótese do item diz "coincidência geométrica com tolerância declarada por rede... mais associações
explícitas". Um dispositivo com dois terminais (ex.: transformador, `alta`/`baixa`) ocupa FISICAMENTE um único
ponto — os dois terminais têm a MESMA coordenada. Se a topologia fundisse tudo que está a `tolerancia_m` de
distância, os dois terminais virariam o MESMO nó, apagando exatamente a fronteira (MT de um lado, BT do outro)
que o transformador existe para marcar.

A saída (`app/rede_utilidades/topologia.py`): trecho-trecho sempre funde por coincidência PURA (mesmo grupo,
ou regra explícita entre grupos diferentes — ex.: ramal → trecho de baixa tensão); dispositivo com 0 ou 1
terminal também funde por coincidência pura (não há ambiguidade); dispositivo com 2+ terminais tem cada
terminal resolvido em separado, usando a ORDEM do `tier` do trecho vizinho (`rede_tier.ordem`) para decidir
qual terminal (`montante=true` vai para o tier de ordem menor) recebe qual ligação — dado que já existe no
pacote de ativos, sem amarrar a nenhum nome de terminal específico. Quando os dois lados de um dispositivo
multi-terminal tocam o MESMO tier (ex.: uma chave em série no meio do mesmo trecho de MT), não há como
decidir o lado sem um traçado de rede completo — a escolha aqui é ordem de chegada determinística (mesma
entrada sempre dá a mesma saída), documentado como limitação, nunca escondido.

## 4. Um nó por terminal, não por dispositivo

`plat.rede_topo_no` grava um nó por VÉRTICE DE CONEXÃO (onde trechos se tocam sem dispositivo no meio) e um
nó por TERMINAL de dispositivo — nunca um nó por dispositivo. Um transformador MT/BT sempre nasce como (até)
2 nós de topologia: um funde com o trecho de MT, outro com o de BT (ou fica órfão, se nada tocar aquele
terminal). Isso é o que faz `nos_orfaos` significar algo real: um terminal que existe (o dispositivo foi
cadastrado) mas nada foi ligado a ele — sinal de dado incompleto, não um bug de contagem.

## 5. Achado de performance: `ST_DWithin(geom::geography, geom::geography, tol)` não usa índice

Medido construindo a rede sintética em escala real (`tests/dados/gerar_rede.py`, ~470 mil feições): a consulta
de pares próximos usando só `ST_DWithin` sobre o cast para `geography` não empurra a busca para o índice GIST
— vira busca every-pair (nested loop sem filtro de índice), inviável a partir de dezenas de milhares de
candidatos (uma rodada de 50 mil pontos não terminou em 2 minutos). Corrigido com um PRÉ-FILTRO por
`ST_DWithin(geom, geom, graus)` (geometria pura — usa o índice GIST por bounding box) com uma folga generosa
em graus (derivada da tolerância declarada e da latitude máxima da própria rede, ×1,5 de segurança), seguido
da conferência exata em `geography` só sobre o punhado de pares que sobra. A tolerância exigida pelo portão
(0,04 m conecta, 0,06 m não) continua exata — o pré-filtro só pode ADICIONAR candidatos de sobra, nunca excluir
um par verdadeiro; quem decide é sempre a checagem em `geography`.

## 6. Caminho da rota: `/api/rede/{rede_id}/topologia/...`, sem `v1`

Mesma decisão do ADR 0019 §6: o portão do item dizia `/api/v1/rede/{id}/topologia/habilitar`; a linha L4
inteira responde em `/api/rede/...`, sem prefixo de versão.

## 7. Isolamento por inquilino

`rede_feicao_ponto`, `rede_feicao_linha`, `rede_topo_no`, `rede_topo_aresta` e `rede_topo_resumo` têm `tenant_id`
+ RLS no mesmo padrão de `plat.rede_*` (ADR 0019 §5) e toda FK entre elas é COMPOSTA `(tenant_id, id)`, não
simples — a mesma trava do achado A1 do item anterior (`tests/api/test_fk_composta_por_inquilino.py`) cobre as
tabelas novas automaticamente, porque varre o schema inteiro. Provado por teste cruzado no nível do banco (não
só da rota): `tests/api/test_rede_topologia.py::test_inquilino_b_nunca_le_topologia_de_a`.

## 8. O que este ADR NÃO decide

Traçado (percorrer o grafo, respeitando `caminhos_validos` e o estado aberto/fechado de uma chave), subrede,
manutenção incremental por área suja, e a UI de desenhar feição de rede no mapa são itens seguintes da linha
L4. A associação entre `plat.rede_feicao_ponto`/`rede_feicao_linha` e o catálogo geral de camadas
(`camada_vetorial`, tabela dinâmica `d_<slug>.c_<uuid>`) também fica para depois — ver docs/rede/TOPOLOGIA.md
seção "fronteira".
