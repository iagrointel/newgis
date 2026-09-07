# 0019 — Diretório do FeatureServer, OGC API Features e WFS 2.0 (item L2-04-servicos-esri-ogc)

Data: 2026-09-07 (turno T4, trilha `esriogc`).

## Contexto

Item de COMPATIBILIDADE (destrava 14 outros itens no `estado.json`: L7-01, L7-02-a, L7-03, L7-03-d, L7-05, L7-08-a/b,
L7-30, L3-13, L4-16, L5-01-c, L5-02-f, L5-07, L5-31). A operação `query` do FeatureServer (item L2-04-c) já existia,
fechada em `wt/fsquery` (ADR 0018): 39/45 parâmetros Esri, PBF pela definição oficial, p95 de 1,6 ms sobre 8,4
milhões de linhas. Faltava o que envolve a `query` para um cliente Esri/OGC/QGIS conseguir DESCOBRIR e usar o
serviço sem já saber a URL exata: o descritor de serviço/camada (Esri), e os dois protocolos abertos que o item
também promete (OGC API Features, WFS 2.0).

## Decisão

### D1 — Construir em volta, nunca reescrever

Toda leitura de feição passa por `motor.PedidoQuery`/`preparar_pedido`/`executar_features`/`executar_count`
exatamente como o item L2-04-c os deixou; `app/consulta/rotas_servico.py`, `rotas_ogc_features.py` e `rotas_wfs.py`
só traduzem vocabulário de protocolo (Esri REST, OGC API Features, WFS KVP) para esse motor e de volta. Nenhum
segundo caminho de SQL foi escrito para nenhum dos três protocolos.

Custo de mudar: baixo — qualquer melhoria futura no motor (novo parâmetro, novo tipo de geometria) beneficia os
três protocolos ao mesmo tempo, porque nenhum deles duplica lógica de consulta.

### D2 — Descritor de serviço/camada gera `fullExtent` por `ST_Extent` sob demanda, nunca em cache

A Esri espera `fullExtent`/`extent` no descritor. Como o descritor é chamado raramente (não está no caminho de
`query`/tile), um `ST_Extent(geom)` direto na tabela é aceitável; cache fica para quando um cliente real mostrar
que o custo importa. `capabilities` nunca anuncia mais que `"Query"` e `relationships` é sempre `[]` — anunciar
edição/relacionamento sem o L2-03-edicao/L2-10-b por trás seria o mesmo defeito que um botão que não faz nada (P2).

### D3 — Uma coleção OGC API Features por item, id fixo `"0"`, espelhando a mesma restrição do FeatureServer

O modelo de dados desta plataforma publica uma camada por item de catálogo (decisão já tomada em L2-04-c). OGC API
Features normalmente agrupa VÁRIAS coleções por servidor; aqui a raiz é por item (`/ogc/features/{item_id}`) e tem
sempre 1 coleção, para não inventar um agrupamento que o catálogo ainda não tem.

Custo de mudar: médio — se um dia existir "workspace com N camadas" como conceito de catálogo, a raiz muda de
por-item para por-workspace; a forma de cada coleção (bbox, GeoJSON) não muda.

### D4 — WFS 2.0: GeoJSON como saída padrão de fato, GML 3.2 escrito à mão como segunda opção

O núcleo do WFS 2.0 exige GML; construir um serializador GML completo (curvas, Multi*, todos os tipos OGC) não
cabia no orçamento do turno. Optou-se por oferecer os dois: `OUTPUTFORMAT=application/json` (GeoJSON, o que
GeoServer/MapServer também oferecem como extensão comum) com o mesmo `como_geojson` do resto do repositório, e um
GML 3.2 mínimo (Point/LineString/Polygon simples) para o núcleo do protocolo. `GetCapabilities` foi verificado
contra um cliente OGC real (`owslib.wfs.WebFeatureService 0.29.3`, que só entende o subconjunto de verdade da spec —
não é um mock escrito por nós); `GetFeature` em GML não foi validado contra o XSD de referência do OGC, registrado
como parcial.

Custo de mudar: baixo (GeoJSON já é o formato canônico interno; GML pode ganhar mais tipos depois sem tocar no
resto do módulo).

### D5 — `applyEdits`, anexos, `queryRelatedRecords`, relacionamentos: fora, por dependência não satisfeita

O item pede esses quatro mecanismos na hipótese, mas nenhum tem fundação no repositório: L2-03-edicao (escrita
transacional) e L2-10-b (relacionamentos) estão `pendente`. Construir uma versão "de mentira" desses caminhos
violaria P2 (sem botão inerte no lugar de mecanismo); a decisão foi declarar `capabilities="Query"` sempre e `relationships=[]` sempre, e
deixar a lacuna nomeada em `docs/PARIDADE.md`, não escondida atrás de um botão inerte.

## Achados corrigidos nesta trilha (adversário próprio, sem agente externo)

1. **500 real**: `rotas_query._camada_do_item` fazia `item_id::uuid` sem validar o formato antes — qualquer
   `item_id` malformado (`x' OR '1'='1`, `;DROP TABLE...`) chegava ao Postgres, que levantava
   `psycopg2.errors.InvalidTextRepresentation` sem handler, virando HTTP 500 (exatamente o que a refutação do item
   proíbe: "o texto do cliente chegou ao banco antes de ser recusado"). Esse bug afetava também a rota `/query`
   original do item L2-04-c, já fechada em `wt/fsquery` — a bateria de ataque dele havia testado `where` malformado,
   nunca `item_id` malformado no path. Corrigido com um regex de UUID (`_item_id_valido`) antes de qualquer consulta,
   compartilhado pelos três protocolos novos e pela `query` original.
2. **Vazamento de rota entre inquilinos**: `pouso`/`conformance` do OGC API Features respondiam 200 (nunca com
   dado do outro inquilino, mas com a landing page) para um item_id de outro inquilino, porque não tocavam o banco
   antes de responder — a autenticação confere ESCOPO, não posse do item. Corrigido: as duas rotas agora carregam o
   item sob RLS antes de montar a resposta, igual ao FeatureServer e ao WFS (que já tocavam o banco).

Os dois foram achados pela própria bateria de ataque desta trilha (13 casos, `tests/esri/conformidade_servicos.py`),
consertados no mesmo turno, e reexercitados — não ficaram para depois.

## O que fica de fora desta passagem

- `applyEdits`, anexos, `queryRelatedRecords`, `relationships` (D5).
- OGC API Features Part 3 (CQL2/Filter) — item próprio L2-04-g.
- WFS-T (transações), Filter Encoding 2.0 no `FILTER=` do WFS.
- QGIS/ArcGIS Pro/AGOL reais carregando o serviço — sem ambiente gráfico disponível nesta máquina (mesma limitação
  já registrada para Chrome headless em CLAUDE.md e para QGIS no ADR 0018); testado com HTTP direto e com o cliente
  Python real `owslib`, nunca com um mock escrito por nós.
