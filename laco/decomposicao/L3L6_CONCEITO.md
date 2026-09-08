# L3 motor multicritério + L6 conectores e acervo — decisões de conceito

Data: 05/09/2026. Par de `L3L6.json` (61 itens: 32 na L3, 29 na L6). Tudo abaixo é o que, se estiver errado, obriga a
refazer. Para cada decisão: opções, o que custa mudar depois, recomendação com motivo MEDIDO nesta máquina, LIDO em
código que roda na casa ou DOCUMENTO OFICIAL com URL testada (HTTP 200 em 05/09/2026), e o que a decisão obriga nas
outras linhas. Nomes de cliente não aparecem: "motor logístico" (`/home/dev/cbre/pipeline/85_fatores.sql` e
`cbre/web/README.md` seção MOTOR, só leitura), "motor de LT" (`/home/dev/rs-coop/tracado-lt/motor/`, só leitura),
"SIG de teste interno" (`/home/dev/fgr/sig`, só leitura).

O que foi medido em 05/09/2026 e sustenta as escolhas:

- `acervo.fonte` = 376 fontes; 68 com texto em `licenca`, mas só 15 com licença NOMEADA (IBGE, ODbL, CC, Copernicus,
  MapBiomas); 356 com frescor; 297 com `url_http`; 35 com sha256; `cliente_ve` nunca preenchido. `acervo.objeto` =
  1.165 tabelas-fonte canônicas (739 GB) + 264 cópias (206 GB); no servidor principal, 462 tabelas-fonte canônicas têm
  coluna de geometria em `geometry_columns` (269 em `public`). `acervo.endpoint` = 779 URLs, 442 confirmadas, 342
  confirmadas e vivas. Duas tabelas fantasma conhecidas (estimativa > 0, COUNT(*) = 0).
- Extensões instaladas: postgis 3.6.3, postgres_fdw 1.1, pg_cron 1.6, timescaledb 2.26.4, pgcrypto, vector; disponíveis
  sem instalar: file_fdw. Ausentes: h3-pg, tds_fdw, oracle_fdw, ogr_fdw, pgstac.
- GDAL 3.8.4: lê e escreve GPKG, Shapefile, GeoJSON/Seq, KML/LIBKML, DXF, CSV, XLSX, OpenFileGDB, MVT, PMTiles,
  MSSQLSpatial; lê WFS e OAPIF. Sem driver Parquet/Arrow e sem OCI (Oracle).
- Python: numpy 2.4, scipy 1.17 (tem `stats.qmc.Sobol`), rasterio 1.5, geopandas 1.1, shapely 2.1, duckdb 1.5.5,
  pystac-client 0.9, h3 4.5, scikit-image 0.26, scikit-learn 1.8, pyarrow 24, defusedxml 0.7. Ausentes: owslib, SALib,
  exactextract, fiona.
- Máquina: 12 vCPU, 23 GB de RAM com 3 GB disponíveis, disco `/` e `/mnt/pgdata` a 98 % (13 e 17 GB livres).
- Motor logístico: 73.115 células hexagonais de 250 m × 19 fatores em `cbre.hex_fav` (16 MB) e 4.346 feições em
  `cbre.imoveis_fav`; combinação `fav = Σ w·f / Σ w × (1 − fração vetada)` recalculada no navegador em ≈ 5 ms;
  transformações declaradas em texto em `cbre.fatores`; extração em SQL em 1-2 min.
- Motor de LT: registro de 44 camadas em `camadas.py` com papel (veto / custo / atrai / rito / métrica), escala
  (micro / macro), base legal e `url`; pesos reancorados em frequência de corpus (`pesos.py`), teto de proxy 0,60;
  Monte Carlo sobre o simplex com verificação bit a bit contra a superfície oficial (`monte_carlo.py`); backtest contra
  linhas construídas e preferência revelada (`backtest.py`, `preferencia_revelada.py`); manifesto de proveniência com
  commit e sha256 (`proveniencia.py`); METODOLOGIA com 53 regras, sendo a primeira "ausência de dado nunca vira medição".

---

## PARTE A — L3, motor multicritério

### A1. O que é "o modelo": documento JSON versionado por hash, não linhas soltas em tabela

Opções: (a) tudo relacional (tabela de fatores, tabela de transformações, tabela de pesos, como `cbre.fatores`);
(b) documento JSON único por modelo; (c) híbrido: definição do modelo em JSONB validado por JSON Schema, e execução,
fator bruto e resultado em tabelas relacionais.

Custo de mudar depois: alto. Export/import, hash de proveniência, o nó do construtor de fluxos (L5-02) e o relatório
PDF leem o mesmo objeto; trocar o formato depois obriga a migrar todo modelo salvo e invalida os hashes.

Recomendação: (c). Motivo LIDO: o motor logístico já vive em dois lugares (dicionário `cbre.fatores` no banco e
`fatores.json` no front) e o motor de LT em um dicionário Python (`CAMADAS`) que o próprio projeto chama de "prova de
procedência: nada entra sem linha aqui"; o que funcionou nos dois foi o registro declarativo único, e o que doeu foi ter
duas cópias da mesma regra (o `monte_carlo.py` registra que uma cópia divergente de `achar()`/`chave_cache()` rodou a
robustez sobre a superfície errada). Um JSON canônico (chaves ordenadas, separadores fixos) com `sha256` como id de
versão resolve as duas coisas: uma cópia e um hash. Esquema mínimo: `amc_modelo(id, tenant_id, nome, versao_hash,
definicao jsonb, criado_por, criado_em, imutavel bool)`, `amc_conjunto_unidade`, `amc_fator_bruto(execucao_extracao_id,
unidade_id, fator_id, valor real, cobertura)`, `amc_execucao(modelo_versao_hash, pesos jsonb, camadas jsonb com sha256 e
COUNT(*), motor_versao, semente, iniciado_em, estado)`, `amc_resultado(execucao_id, unidade_id, fav real, vetado bool,
motivo text)`. Documento oficial que sustenta a forma "modelo com abas": Suitability Modeler, abas Settings / Suitability /
Locate / Sources / Evaluate (`.../suitability-modeling-framework.htm`, Pro 3.4).

Obriga: L0-03 aceita item do catálogo do tipo "modelo AMC" e "resultado AMC"; L5-02 trata o modelo como nó com entradas
por id; L7-08 expõe o JSON Schema no portal de API; o adversário sempre recomputa o hash com script próprio.

### A2. Separar EXTRAÇÃO (cara, materializada) de COMBINAÇÃO (barata, interativa)

Opções: (a) tudo num job (extrair e combinar a cada mudança de peso); (b) fator bruto materializado por unidade uma
vez, combinação recalculada em SQL ou no navegador a cada peso.

Custo de mudar depois: alto. Presets, Monte Carlo, SMAA, comparação de cenários e AHP só são viáveis se mover um peso
custar milissegundos.

Recomendação: (b). Motivo MEDIDO: no motor logístico a extração de 12-19 fatores em 73 mil células leva 1-2 min em SQL e
a recombinação de 4.346 feições leva ≈ 5 ms no navegador; o Monte Carlo do motor de LT só é possível porque reaproveita as
máscaras já cacheadas e recompõe. O Suitability Modeler faz o mesmo: transforma e recombina "na resolução da tela e na
extensão atual" para dar resposta imediata, e só roda em resolução plena antes do Locate (transformation pane, doc Pro).
Regra de tamanho: ≤ 50 mil unidades recombinam no navegador (dados como vetor binário, como o `hex_fav.bin` de 16 bytes
por célula); acima, em SQL no servidor (item L3-16 mede 1 mi).

Obriga: L2-01 aceita camada "recolorida no cliente" a partir de um vetor de valores por id (o mesmo mecanismo do raster
de índice `hex_idx.png`); L0-05 executa só a extração como job; L3-13 publica o resultado como camada depois de a
combinação ser gravada.

### A3. Escala e tipo da favorabilidade: 0-100 em ponto flutuante, NULL para ausente

Opções: (a) 1-10 inteiro (padrão Esri do Suitability Modeler e do Weighted Overlay, escalas "1 to 9", "1 to 10");
(b) 0-100 inteiro (motor logístico, `smallint`); (c) 0-1 (fuzzy, QGIS fuzzify); (d) 0-100 real.

Custo de mudar depois: médio-alto (todos os testes de tolerância ±0,5, as rampas de cor e os presets).

Recomendação: (d), com apresentação opcional em 1-10 para quem vem do ArcGIS (divisão por 10, só na tela). Motivo:
0-100 é a linguagem que o cliente do motor logístico já usa ("favorabilidade 0-100"); `smallint` arredonda e o item
L3-01-j exige reproduzir `cbre.hex_fav` com |Δ| ≤ 0,5, o que só é honesto em real; NULL é obrigatório pela regra "ausência
de dado nunca vira medição" (METODOLOGIA §1), e o Weighted Overlay da Esri tem tratamento explícito de NoData e de
"Restricted" (valor mínimo − 1) que aqui viram `NULL` e `vetado = true` com motivo, nunca um número na escala.

Obriga: L2-02 (simbologia) precisa de classe "sem dado" e "vetado" separadas da rampa; L3-01-i escreve a escala no PDF.

### A4. Linguagem das transformações: JSON declarativo com dupla implementação (SQL e numpy), não expressão livre

Opções: (a) expressão livre (Arcade, SQL, Python) por fator; (b) tipos declarados com parâmetros (JSON), executados por
código do produto; (c) (b) agora e (a) mais tarde com analisador restrito.

Custo de mudar depois: alto se começar por (a): explicação por unidade, hash do método, adversário recompute e relatório
dependem de saber o que a função faz sem executar código do usuário.

Recomendação: (c), com a lista de tipos fechada = os três métodos do Suitability Modeler (Unique Categories, Range of
Classes com quebras manuais/quantil/intervalo igual/quebras naturais, Continuous Functions) e as 13 funções do Rescale by
Function com os mesmos nomes de parâmetro (Exponential, Gaussian, Large, Linear, Logarithm, LogisticDecay, LogisticGrowth,
MSLarge, MSSmall, Near, Power, Small, SymmetricLinear; "value below threshold" e "value above threshold" para fora da
faixa — doc Pro 3.4, URL testada), mais "degraus/bandas" que o motor logístico usa (banda de 15/30/45/60 min → 100/80/50/30).
Toda transformação tem duas implementações (SQL para materializar e numpy para pré-visualizar e para o adversário) com
teste de equivalência |Δ| ≤ 0,01. Motivo LIDO: as 19 transformações do motor logístico cabem todas nessa lista (linear com
mínimo/máximo, categoria→nota, banda, degrau com veto), e a coluna `transformacao` de `cbre.fatores` já é texto
declarativo que a tela mostra no "?": o JSON só o torna executável.

Obriga: L5-02 usa a mesma biblioteca para "calcular campo"; L3-18 escreve a paridade função a função; L7-08 publica o
JSON Schema dos tipos.

### A5. Combinação padrão e política de dado ausente

Opções de combinação: soma ponderada normalizada Σ w f / Σ w (motor logístico), soma com percentuais que fecham 100
(Weighted Overlay, que ainda arredonda para inteiro), soma sem normalizar (Weighted Sum), média geométrica (o "ranking
original" do motor logístico), mínimo/máximo/produto/soma/gama (Fuzzy Overlay). Opções de ausente: tratar como 0, como
nota pior, como NULL na unidade, ou excluir o fator daquela unidade renormalizando pelos pesos presentes.

Custo de mudar depois: alto (toda comparação com o motor logístico e todo teste de tolerância).

Recomendação: padrão = Σ w f / Σ w sobre os fatores COM dado, veto multiplicativo por (1 − fração vetada) quando a
unidade é agregada, e os demais como combinadores escolhíveis no modelo; ausente = excluir o fator e gravar cobertura,
mostrando-a na explicação. Motivo LIDO: é exatamente o que o `85_fatores.sql` faz (`sum(a*f)/NULLIF(sum(a) FILTER (WHERE
f IS NOT NULL),0)`), e o `cbre.fatores` marca fator "gancho" com NULL até o dado existir sem contaminar a nota. Motivo
DOCUMENTO: o Weighted Overlay exige que as influências somem 100 e trunca decimais; oferecer esse modo dá paridade, mas
não pode ser o padrão porque perde precisão. O produto e a média geométrica ficam disponíveis porque um fator em zero
tem de poder anular (comportamento que o motor logístico usa na média geométrica do ranking original).

Obriga: L3-14 varre o código por `COALESCE(...,0)` em coluna de fator; L3-01-f explica a cobertura; L3-18 documenta
que o modo "percentual inteiro" é paridade e não recomendação.

### A6. Veto e restrição são objetos separados do peso e nunca entram no sorteio de robustez

Opções: (a) veto como transformação que dá 0 (Weighted Overlay "Restricted" = min − 1); (b) restrição como objeto próprio
com base (norma × precaução), fonte, buffer, versão da camada e contagem de unidades excluídas por restrição.

Custo de mudar depois: médio (o relatório e o Monte Carlo dependem de saber o que é lei e o que é preferência).

Recomendação: (b). Motivo LIDO: a decisão do dono no motor de LT ("a rota de veto é A rota; o custo vai para o método";
METODOLOGIA §11) e a nota `veto_e_precaucao` em `camadas.py` ("dizer 'vetamos por precaução', nunca 'a lei proíbe'")
mostram que a distinção é jurídica, não numérica; o `monte_carlo.py` declara "veto NÃO é sorteado (é exclusão legal,
não preferência)". Restrição por buffer usa `geography` em metros (METODOLOGIA §3.12, CRS explícito).

Obriga: L3-02 nunca sorteia restrição; L3-01-i escreve a base de cada restrição; L6 entrega camadas do acervo com
`base_legal` opcional na ficha para alimentar isso.

### A7. Unidade de análise, identificador e CRS de trabalho

Opções: grade H3 (índice global, sem extensão no Postgres desta máquina), grade PostGIS (`ST_HexagonGrid` /
`ST_SquareGrid`) em CRS métrico, ou feições do usuário. CRS: UTM SIRGAS 2000 da zona do centróide; policônica nacional
(EPSG:5880); Web Mercator.

Custo de mudar depois: alto (id da unidade é a chave de fator bruto, resultado, explicação e agregação).

Recomendação: grade PostGIS em UTM SIRGAS 2000 da zona do centróide (`srid_trabalho` gravado no conjunto), id =
`(conjunto_id, indice_linha_coluna)`; feição do usuário mantém o id de origem + surrogate; H3 só como índice opcional via
biblioteca Python. Motivo MEDIDO: h3-pg não está instalado e a regra do brief é não instalar; o motor logístico usa hex de
250 m em EPSG:31983 e o motor de LT usa grade de 100 m em EPSG:31984, ambos UTM. Motivo DOCUMENTO/METODOLOGIA: "nunca
comprimento no plano; a policônica infla 1,5 % em 2.500 km" (§2.6) e "CRS explícito em toda comparação" (§3.12); Web
Mercator distorce área em latitude e não serve para grade de área igual. Área da unidade sempre geodésica (GRS80).

Obriga: L2-05 (criar grade) usa a mesma função; L3-19 (multiescala) aninha grades no mesmo CRS; L3-07 agrega por
`ST_Area` no CRS de trabalho, nunca em 4326.

### A8. Modelo de job: extração como job da fila (L0-05), combinação síncrona, robustez como job

Opções: tudo síncrono; tudo job; misto.

Custo de mudar depois: médio.

Recomendação: misto, com a regra "1 job pesado de máquina por vez" do guardrail e `setsid nohup` para o worker
(METODOLOGIA §9.43-44). Motivo MEDIDO: 3 GB de RAM disponíveis; o Monte Carlo do motor de LT teve de reduzir workers
por memória (`_workers_seguros`, 2,7 GB por worker). Progresso por fator; cancelamento; job morto no meio nunca aparece
concluído (portão do L0-05).

Obriga: L0-05 expõe progresso granular (por fator) e cancelamento cooperativo; L7-06 mede memória por job.

### A9. Robustez: resumo por unidade, nunca N × unidades armazenado

Opções: guardar cada sorteio; guardar só agregados por unidade (mín/média/máx, frequência no top-k, aceitabilidade por
posição) e a semente.

Custo de mudar depois: baixo-médio.

Recomendação: agregados + semente; reprodutível bit a bit pela semente. Sorteio de pesos por Dirichlet no simplex ou por
faixa ± k % declarada (o motor de LT usa U(0,5p; 2,0p) para custo e U(0,8v; 1,2v) para atração); Sobol com
`scipy.stats.qmc` (presente; SALib ausente) e teste de Ishigami; SMAA-2 (Lahdelma e Salminen 2001) para "que pesos fariam
esta unidade ganhar". Motivo LIDO: `monte_carlo.py` grava frequência por célula, famílias de rota por Hausdorff, e
verifica a recomposição contra a superfície oficial antes de sortear; esse guarda ("recomposição não reproduz a
superfície oficial — abortado") entra como teste obrigatório do L3-02-a.

Obriga: L3-01-e expõe a função de combinação pura (sem I/O) para ser chamada N vezes; L2-06 (painéis) mostra mapa de
frequência.

### A10. Proveniência e reprodutibilidade: hash de modelo + hash e COUNT(*) de cada camada + versão do motor

Opções: guardar só o id da camada; guardar sha256 e contagem no momento da execução; exigir árvore git limpa (motor
de LT) para execução "oficial".

Custo de mudar depois: alto (é o que torna um resultado auditável; sem isso não há "laudo" nem Lastro).

Recomendação: execução grava `{camada_id, sha256 ou hash de conteúdo quando existir, COUNT(*) ou nº de pixels, versão}`
por entrada, versão do motor (VERSAO + git sha) e semente; reexecução sobre as mesmas entradas tem de dar tabela e COG
com o mesmo sha256 (portão L3-13); resultado "oficial" exige commit limpo, como `proveniencia.exigir_arvore_limpa()`.
Motivo LIDO: o `release.py` do motor de LT tem `portao_proveniencia` e `portao_numeros` porque peças foram publicadas
com manifestos de 4 commits diferentes; a regra "número nunca digitado" (METODOLOGIA §2.1) vale para o PDF do L3-01-i.

Obriga: L6 entrega sha256/contagem da camada do acervo na ficha (já existe em `acervo.fonte.sha256` para 35 fontes e
`acervo.objeto.linhas_exatas`); L1 entrega multihash no item STAC; L0-03 guarda versão do item.

### A11. Metadado do fator: base, proxy com teto, classe de peso, "o que não sustenta"

Opções: só nome e fonte; ou o registro completo do motor de LT.

Custo de mudar depois: baixo no esquema (JSONB), alto na cultura: sem isso o produto vira "pesos que ninguém aprovou".

Recomendação: campos obrigatórios `fonte`, `unidade`, `direcao`, `base` (norma / engenharia / preferência) e opcionais
`proxy` (com teto de peso, padrão 0,60 da escala como em `pesos.py`), `classe_peso` (custo medido em R$ / apetite de
risco / consequência normativa), `ancora_peso` (medida / escolhida) e `nao_sustenta`. Motivo LIDO: `pesos.py` registra
que "dos 20 pesos de custo, ZERO tinha âncora externa" e que a camada `veg_nativa` mede presença declarada, não supressão
de arbórea (duas trocas de grandeza), logo não pode pesar como se medisse o gatilho.

Obriga: o relatório (L3-01-i) e a tela (L3-01-g) mostram esses campos; a regra de escrita de 03/09 vale para o texto.

### A12. Contrato de API

Opções: (a) uma rota `/api/amc/rodar` que recebe tudo e devolve tudo; (b) recursos separados (modelo, conjunto, execução,
resultado, explicação, robustez, localizar, método). Recomendação: (b), porque presets, robustez e comparação de cenários
reusam a execução de extração sem repeti-la (A2). Obriga: L5-02 chama os mesmos recursos pelo nó do fluxo; L7-08 gera o SDK
a partir do OpenAPI comitado; L2-04 publica o resultado como serviço (L3-13).

`POST /api/amc/modelos` (valida JSON Schema, devolve `versao_hash`), `GET /api/amc/modelos/{id}/versoes`,
`POST /api/amc/conjuntos` (grade ou feições), `POST /api/amc/execucoes` (extração → job), `POST
/api/amc/execucoes/{id}/combinar` (pesos → resultado síncrono ou job por tamanho), `GET
/api/amc/resultados/{id}/unidades?bbox&limite`, `GET /api/amc/resultados/{id}/explicar/{unidade_id}`, `POST
/api/amc/resultados/{id}/robustez`, `POST /api/amc/resultados/{id}/localizar` (regiões), `GET
/api/amc/resultados/{id}/metodo.{json,pdf}`. Tudo por token com escopo e RLS. Custo de mudar depois: médio (SDK L7-08
e nó L5-02).

### A13. Análise linear (corredor de custo mínimo) é o MESMO produto, com outro combinador

Custo de mudar depois: alto se nascer como módulo à parte (dois esquemas de modelo, dois relatórios, duas proveniências).

Opções: motor de LT como módulo à parte; ou o mesmo esquema de modelo com combinador "superfície de custo" (custo por
máximo, atração multiplicativa com piso, veto intransponível, curva de relevo) e um "resolvedor" (Dijkstra 16 vizinhos,
corredor-epsilon, compressão de amplitude).

Recomendação: mesmo esquema. Motivo LIDO: o `route_v1.py` já compõe por passadas comutativas e declara que o resultado
"não depende da ordem da lista de camadas"; a única diferença para a soma ponderada é o combinador e o passo final.
Documento: Distance Accumulation e Optimal Region Connections (Pro 3.4) são o par Esri. Regra que viaja: teto de
sinuosidade = amplitude da superfície (S_máx = C_máx/C_mín), então a compressão de amplitude é obrigatória e declarada.

Obriga: L3-04 (restrições) alimenta o veto intransponível; L2-09 (3D) pode exibir perfil; L7-02 mede tempo do Dijkstra.

### A14. Isolamento por inquilino e extensibilidade

Opções: RLS por tabela (padrão da casa) × schema por inquilino × banco por inquilino. Recomendação: RLS, como em
`002_identidade.sql`, porque o acervo (B1) é compartilhado e uma view com predicado de assinatura só funciona no mesmo banco.
Obriga: L7-03 inclui teste cruzado A→B em `amc_*`; L7-11 (appliance) recria as mesmas policies.

RLS em `amc_*` por `tenant_id` (mesmo padrão de `002_identidade.sql`: policy `FOR ALL ... USING/WITH CHECK` com
`plat.tenant_atual()`); camada do acervo entra como fator só através da view assinada (L6-01-b), nunca por leitura
direta de `public`. Extensibilidade: extratores, transformações e combinadores são classes Python registradas com JSON
Schema próprio e par de testes (SQL × numpy); tipo novo sem par de testes = erro de build. Custo de mudar depois: baixo.

---

## PARTE B — L6, conectores e acervo da casa

### B1. Como o acervo chega ao inquilino: VIEW só-leitura sobre a tabela original, sem cópia, sem GRANT direto

Opções: (a) copiar a tabela para o schema do inquilino; (b) GRANT SELECT direto em `public.*` a `plat_app`; (c) view
`SECURITY INVOKER` em schema `plat_acervo` com lista branca de colunas e predicado de assinatura, GRANT só nas views;
(d) postgres_fdw para tudo, mesmo no mesmo banco.

Custo de mudar depois: alto (tiles do Martin, FeatureServer, extrator do motor e LGPD dependem do caminho de leitura).

Recomendação: (c). Motivo MEDIDO: disco a 98 % proíbe (a) (as 462 tabelas-fonte com geometria somam centenas de GB;
só as cópias já custam 242 GB); (b) expõe colunas de identificação e impede revogação por camada; (d) custa uma
conexão por consulta no mesmo servidor. Motivo LIDO: `plat_app` é `NOBYPASSRLS` e não é dona das tabelas (ADR 0001);
a view com `WHERE plat.acervo_pode_ler('<camada>')` e GRANT só na view mantém isso. Consulta de mapa sobre 7,36 mi de
imóveis do CAR responde em 20 ms nesta máquina com o índice GiST da tabela original (DOC.md 17.2), o que a view
preserva. Documento Esri para paridade: Living Atlas em Enterprise 11.4 "referencia" conteúdo do ArcGIS Online quando
há internet e "publica camadas de limites diretamente no portal" quando não há (`what-is-living-atlas.htm`, 11.4).

Obriga: L2-04 serve FeatureServer/OGC a partir de views (applyEdits = 405); L2-01/Martin usa função com inquilino; L7-03
inclui o teste "nenhuma tabela `public` tem GRANT a `plat_app`"; L7-12 (LGPD) usa a mesma lista branca.

### B2. Identificador da camada do acervo e ligação com o registro

Opções: usar `acervo.objeto` PK `(servidor, banco, schema, tabela)`; usar `fonte_id`; criar slug próprio.

Recomendação: `acervo_camada_id` = slug estável `<fonte_id>/<schema>.<tabela>` gravado em `plat.acervo_camada`, com
FK lógica para `acervo.objeto` e `acervo.fonte` (só leitura; a plataforma NUNCA escreve em `acervo.*`). Motivo: uma
fonte tem várias tabelas (SICAR nacional = 20 tabelas); o slug é legível na URL do serviço e sobrevive a reinventário do
registro. Custo de mudar depois: alto (URLs de serviço publicadas no ArcGIS do cliente).

Obriga: L2-04 usa o slug na URL do FeatureServer; L3 grava o slug na proveniência.

### B3. Licença: vocabulário fechado numa tabela curada em `plat`, nunca inferida do texto livre do registro

Opções: ler `acervo.fonte.licenca` como está (texto livre; 32 registros dizem "dado público (licença não declarada na
fonte)"); ou tabela `plat.acervo_licenca(fonte_id, tipo, url, conferida_em, evidencia)` com vocabulário fechado.

Custo de mudar depois: médio no esquema, alto no risco (regra D17: sem licença escrita o acervo é auditável, não
vendável).

Recomendação: tabela curada com tipos `CC0 | CC-BY | CC-BY-SA | ODbL | dado-aberto-com-termo-do-orgao | Copernicus |
licenca-propria | nao-declarada`; só `≠ nao-declarada` com URL testada aparece ao inquilino; o texto da licença é aceito
por clique na assinatura; ODbL e CC-BY-SA levam atribuição na legenda e `LICENCA.txt` na exportação. Motivo MEDIDO:
hoje só 15 fontes têm licença nomeada; o portão do L6-01 pede ≥ 40 com licença ESCRITA, então o item L6-01-g é pesquisa
(URL da página de licença de cada órgão) e não engenharia; o que não fechar vai para `decisoes_do_dono` (D17).
Documento Esri para paridade: "users are responsible for adhering to the terms of use for each item of ArcGIS Living
Atlas content" (Business Analyst, `understand-arcgis-living-atlas.htm`); o Living Atlas passa por "curation process"
com revisão de "reliable source" (blog Esri, não usado como evidência; a página 11.4 é a evidência).

Obriga: L7-12 (LGPD/governança) usa o mesmo vocabulário para classificação; L7-09 (medição) lê o registro de uso por
camada; L0-09 (metadado ISO) exporta a licença no campo `MD_Constraints`.

### B4. LGPD: bloqueio por fonte e por coluna com teste automático, antes de qualquer exposição

Opções: revisar caso a caso na tela; ou lista negra de colunas (regex de nome e de conteúdo) + lista de fontes em
bloqueio permanente + decisão de exposição gravada com usuário e data, com teste no `make check`.

Recomendação: a segunda. Motivo: regra da casa (nunca publicar dado pessoal identificado; SNGPC tem nome de paciente;
SICOR identidade, CNPJ sócios, CAFIR tocam sigilo). Teste percorre todas as views, casa nomes com a lista negra e
amostra 1.000 linhas por coluna texto contra regex de CPF/CNPJ. Custo de mudar depois: nenhum; custo de não fazer: o
maior do produto.

Obriga: L7-03 e L7-12 herdam o teste; L2-04 não publica coluna fora da lista branca mesmo por `outFields=*`.

### B5. Frescor e verificação: job em `plat`, o registro `acervo.*` continua sendo escrito só pelos scripts da casa

Obriga: L0-05 recebe o job semanal; L7-06 alerta quando a verificação atrasa; L6-01-d exibe o resultado na ficha.

Opções: a plataforma atualizar `acervo.fonte.atualizado_em`; ou gravar em `plat.acervo_verificacao(camada, em, count,
sha256, http)` e mostrar "verificação vencida" quando `proxima_verificacao < hoje` ou endpoint morto.

Recomendação: a segunda. Motivo: `acervo.*` é gerado por `registro.py`/`contagem2.py`/`frescor.py`; duas escritas no
mesmo registro repetem o defeito "duas cópias da mesma regra". COUNT(*) com timeout de 25 s por tabela como no
`contagem2.py` (as 48 tabelas que não contam concentram 1,38 bi estimados: sai como "não concluída em N s", nunca como
zero — METODOLOGIA §7.31). Custo de mudar depois: baixo.

### B6. Modelo de conexão externa: um objeto `conexao` + camada em dois modos (referenciada × copiada)

Opções: cada tipo de conector com tabela própria; ou `plat.conexao(tipo, config jsonb validado por schema por tipo,
credencial cifrada, saude)` + item do catálogo `camada_externa(modo = referenciada | copiada, conexao_id, params)`.

Custo de mudar depois: alto (é o esquema que L2-01 lê para montar o mapa e que L6-02-k agenda).

Recomendação: a segunda, com o vocabulário de tipos = a lista do Map Viewer 11.4 ("ArcGIS Server web service, OGC WFS,
OGC WMS, OGC WMTS, OGC API Features, KML, GeoRSS, GeoJSON, CSV, tile layers" — `add-layers-mv.htm`, 11.4) + o que a
spec da casa acrescenta (STAC, GeoParquet, PMTiles/TileJSON, Google Sheets, bancos externos) + o que o GeoServer chama
de cascata (WMS, WMTS, WFS e stored queries — `data/cascaded/index.html`). "Referenciada" = lida ao vivo (proxy quando há
credencial ou CRS que o MapLibre não desenha); "copiada" = materializada em PostGIS como camada normal do inquilino
(L0-04) com `origem_conexao_id`, agendamento e troca atômica. Motivo DOCUMENTO: o Data Pipelines da Esri só escreve em
"feature layers and files written to your content" (FAQ, doc.arcgis.com) — a cópia é o único modo dele; o GeoServer só
cascateia (só o modo referenciado). Ter os dois é a paridade com ambos.

Obriga: L2-01 renderiza `camada_externa` referenciada por tipo (WMS/WMTS/XYZ direto ou proxy; WFS/OGC API por bbox
com cache curto); L0-04 aceita ingestão a partir de conexão; L0-05 executa a cópia; L7-03 audita o proxy.

### B7. Credencial e SSRF

Opções: credencial em texto no JSONB (nunca); cifrada no banco com chave fora (recomendado); cofre externo (Vault, não
instalado). Obriga: L7-03 herda os 8 casos de SSRF como teste permanente; L7-12 trata credencial de cliente como dado
sensível com expurgo ao apagar a conexão.

Credencial cifrada com `pgp_sym_encrypt` (pgcrypto presente) e chave em `.env` (modo 600), nunca em log nem em resposta;
proxy resolve o DNS, bloqueia RFC1918/loopback/link-local/169.254.169.254, só http/https, revalida redirecionamento,
limite de bytes e tempo; XML com defusedxml (presente; owslib ausente, e não se instala). Custo de mudar depois: nenhum;
é pré-requisito do primeiro conector. Documento Esri: o Portal guarda credenciais de serviço ao adicionar item
("store credentials with service item", `add-items.htm` 11.4) — aqui o equivalente é a credencial cifrada + proxy.

### B8. Bancos externos: FDW para PostgreSQL (referenciado), GDAL para SQL Server (copiado), Oracle pendente

Custo de mudar depois: baixo no esquema (é só mais um `tipo` de conexão), alto na promessa comercial (não anunciar Oracle
antes de existir).

Opções: FDW para tudo (exige tds_fdw e oracle_fdw, ausentes); GDAL para tudo (MSSQLSpatial presente; OCI ausente);
misto.

Recomendação: misto conforme o que existe nesta máquina, com Oracle declarado "pendente de instalação com decisão do
dono" e ausente da tela até existir (proposta externa L7-14). "Query layer" do cliente = SELECT com lista branca, LIMIT
obrigatório, sem DDL/DML. Documento Esri: data store item de banco permite "publish map image layers and feature layers
in bulk" e "bulk publishing and editing are not supported for data in a cloud data warehouse" (`data-store-items.htm`,
11.4); e a spec da casa (DOC.md §22) já anotou que "query layer roda SQL direto no banco e o dado não precisa estar em
geodatabase" — o cliente com ArcGIS Pro lê o nosso PostgreSQL sem Enterprise.

Obriga: L7-11 (appliance) documenta como o cliente registra o próprio banco; L7-03 testa injeção na query layer.

### B9. Agendamento: fila L0-05 com pg_cron como relógio, tetos declarados, troca atômica

Custo de mudar depois: médio (tarefas salvas dos inquilinos e o histórico de execuções).

Opções: pg_cron chamando SQL direto; cron do sistema; fila da plataforma.

Recomendação: `plat.tarefa_agendada` + tick do pg_cron (1.6 presente) que enfileira na fila L0-05; histórico de 30
execuções; 5 falhas seguidas pausam; e-mail ≤ 1 a cada 6 h; tetos por inquilino medidos e declarados (a referência Esri
publica 10 tarefas por usuário, 50 por organização, 15 min de intervalo mínimo — `schedule-data-pipeline-tasks.htm`).
Troca atômica = carregar em tabela nova e trocar por `ALTER TABLE ... RENAME` numa transação. Motivo: job que morre no
meio nunca deixa camada vazia (guardrail e METODOLOGIA §7.35 "erro nunca é sucesso").

Obriga: L0-05 aceita enfileiramento por tick; L2-13 (versionamento) pode guardar a versão anterior da camada copiada.

### B10. CRS de camada externa: nativo gravado, entrega em 3857/4326, reprojeção no proxy declarada

Opções: recusar serviço que não anuncia 3857; reprojetar no cliente (MapLibre não faz); reprojetar no proxy (recomendado).
Obriga: L2-01 mostra a marca 'reprojetado' na ficha; L7-02 mede o custo do proxy em tiles/s.

WMS/WMTS: pedir 3857 quando anunciado; se o serviço só anuncia 4674/4326 (comum em órgão brasileiro), o proxy reprojeta
por GDAL e marca "reprojetado" na ficha (perda de nitidez em raster declarada). WFS/OGC API: GDAL reprojeta para 4326 na
cópia; o `srid` nativo fica na ficha. Motivo: METODOLOGIA §3.12 (CRS explícito); MapLibre desenha só 3857. Custo de mudar
depois: baixo.

### B11. Ficha única de procedência para acervo e para camada externa

Opções: ficha diferente por origem (acervo × externa × upload); ficha única de 10 campos (recomendado). Custo de mudar
depois: médio (a tela de ficha e o metadado ISO do L0-09 leem o mesmo objeto).

Os 10 campos de `acervo.v_completude` (url, licença, frescor, data do dado, script gerador, sha256, método, confiança,
limites, próxima verificação) são a ficha de TODA camada, interna ou externa; campo ausente aparece "não registrado".
Para camada externa, o que vier do serviço (AccessConstraints/Fees, título, `license` do STAC, `copyrightText` do ArcGIS)
preenche automaticamente. Motivo LIDO: "procedência errada é pior que procedência nenhuma" (regra da casa, 01/09) — daí
"não registrado" em vez de valor padrão. Obriga: L0-09 (metadado ISO) mapeia esses 10 campos para ISO 19115.

### B12. Catálogo de endpoints prontos vem do registro vivo, não de lista digitada

Opções: lista escrita à mão no repositório (envelhece e ninguém reconfere) × gerada do registro e retestada (recomendado).
Obriga: L7-06 alerta quando a taxa de endpoints vivos cai; L6-03 cita só os que estão verdes na data.

`plat.endpoint_publico` é gerado de `acervo.endpoint WHERE confirmado AND http = '200'` (342 hoje) filtrado por tipo de
serviço + a fila keyless global do mapa aberto da casa (`geoapp/PLUG_READY_QUEUE.md`, cada linha "abriu de fato" por
gdalinfo), retestado por semana; entrada morta some. Motivo: regra "URL testada por HTTP" do laço; e a 1ª mineração de
URL do acervo foi reprovada por atribuir URL errada à fonte — o catálogo só usa `confirmado = true` (host casa com o
órgão). Custo de mudar depois: baixo.

### B13. Multi-servidor: FDW só-leitura ou "não disponível nesta instalação", nunca cópia sem decisão

Opções: copiar para o principal (disco proíbe); FDW só-leitura (recomendado quando a rede permite); marcar indisponível.
Custo de mudar depois: baixo (a ficha já diz onde a camada vive).

412 tabelas vivem em 2-3 máquinas e muitas só fora do servidor principal; postgres_fdw existe; disco a 98 %. A ficha
diz onde a camada vive. Obriga: L7-11 (appliance no cliente) tem de lidar com o mesmo caso ao contrário (o acervo da
casa fica fora da instalação do cliente e entra por FDW/serviço com token).

---

## O que estas decisões obrigam nas outras linhas (resumo)

| linha | obrigação |
|---|---|
| L0-03 catálogo | tipos de item: modelo AMC, resultado AMC, conjunto de unidades, camada do acervo (só-leitura), camada externa (referenciada/copiada), conexão, tarefa agendada, pipeline de dados |
| L0-04 ingestão | aceitar entrada a partir de conexão (cópia agendada) com `origem_conexao_id`; formatos = lista medida do GDAL 3.8.4 |
| L0-05 fila | progresso por fator, cancelamento cooperativo, enfileiramento por tick do pg_cron, troca atômica |
| L1 imagens | multihash no STAC; rasters do acervo em COG (proposta L1-06); TiTiler lê asset externo assinado |
| L2-01 mapa | recolorir camada por vetor de valores por id (cliente); renderizar camada externa por tipo; aviso "fora do ar" |
| L2-02 simbologia | classes "sem dado" e "vetado" separadas; atribuição obrigatória na legenda (ODbL, CC BY-SA, serviços externos) |
| L2-04 serviços | FeatureServer/OGC a partir de views só-leitura; slug do acervo na URL; applyEdits = 405 |
| L2-05 geoprocessamento | grade hex/quadrada e estatística zonal com o mesmo código do extrator L3 |
| L2-11 rota | extrator de tempo/distância por rede (L3-11) |
| L2-15 analítica | DuckDB como leitor de GeoParquet remoto (L6-02-f) |
| L5-02 fluxos | nó "motor" e nó "pipeline de dados" leem o mesmo JSON de modelo/pipeline |
| L7-03 segurança | testes: SSRF, GRANT em `public`, colunas LGPD, query layer, credencial em log |
| L7-08 SDK/API | JSON Schema de modelo, transformação e conexão publicados |
| L7-09 medição | registro de uso por camada do acervo entra na fatura |
| L7-12 LGPD | mesmo vocabulário de classificação e mesma lista negra |
| L7-14 (proposta) | tds_fdw / oracle_fdw exigem apt e decisão do dono |

## Decisões que ficam com o dono (para `decisoes_do_dono`)

- D17 (já aberta): quem assina a licença das fontes cujo órgão não a declara; o portão de ≥ 40 camadas só fecha com
  licença ESCRITA, e hoje há 15 nomeadas.
- D21 (já aberta): disco; L6-01-i (rasters/arquivos do acervo) e L6-02 modo copiado dependem de espaço.
- Nova: instalar tds_fdw/oracle_fdw (Instant Client tem licença própria) para bancos externos referenciados; sem isso,
  SQL Server só copiado e Oracle fora.
- Nova: conta de serviço Google de teste da casa para o conector Sheets privado (sem ela, o item fica "pendente", nunca
  "feito").
