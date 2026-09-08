# L4 rede de utilidades (+ L4-parcelas) — decisões de conceito

Data: 05/09/2026. Par de `L4.json` (59 itens: 32 filhos dos 6 itens existentes L4-01..L4-06, 24 itens novos L4-07..L4-30 e
3 itens L4-parcelas). Tudo abaixo é o que, se estiver errado, obriga a refazer a linha. Para cada decisão: opções, o que
custa mudar depois, recomendação com motivo MEDIDO nesta máquina, LIDO em código que roda na casa ou DOCUMENTO OFICIAL com
URL testada (HTTP 200 em 05/09/2026), e o que a decisão obriga nas outras linhas. Nomes de cliente não aparecem: "cooperativa
de teste" (schema `certaja.*`, só leitura), "distribuidora de teste do ES" (`edp_es.*`, só leitura), "SIG de teste interno"
(`/home/dev/fgr/sig`, só leitura), "motor de LT" (`/home/dev/rs-coop/tracado-lt`), "motor logístico" (`/home/dev/cbre`).

## 0. O que foi medido em 05/09/2026 e sustenta as escolhas

- Banco: PostgreSQL 16.13; `postgis` 3.6.3 e `postgis_topology` 3.6.3 instaladas; `timescaledb` 2.26.4 instalada (licença TSL:
  compressão e agregados contínuos não podem ser oferecidos como serviço a terceiros); **`pgrouting` NÃO instalada** —
  candidato apt `postgresql-16-pgrouting 4.0.1-1.pgdg24.04+1` (release notes 4.0 testadas por HTTP). Nenhuma venv da casa tem
  `pandapower`, `opendssdirect.py` ou `wntr`; o python do sistema tem networkx 3.6.1, geopandas 1.1.3, scipy 1.17.1.
- Máquina: 12 vCPU, 23 GB de RAM com 3 GB disponíveis; disco `/` a 98 % (13 GB livres) e `/mnt/pgdata` a 98 % (17 GB).
  Consequência: nenhum pacote BDGD novo (476 MB a 1 GB cada) sem a decisão D21; os 3 pacotes 2024 já em `/home/dev/liga/`
  (13 MB, cooperativa B, 476 MB) são o dado de trabalho.
- BDGD 2024 na casa (`brasil_rede_2024/stats.json`, medido 23/07/2026): 101 distribuidoras; MT 3.102.276,04 km; 6.077.450
  trafos; 103.114.921 UCs; 30.103.199 segmentos quantizados; a maior distribuidora tem 5.626.693 feições em SSDMT. Alguns
  pacotes trazem COMP em metros (razão COMP/geodésico ≈ 1.024 medida por amostra) e outros em km.
- Cooperativa de teste carregada em `certaja.*`: 44.268 segmentos de MT em 20 CTMT, 29.244 de BT, 26.581 ramais, 5.481
  trafos (3.727 do tipo "MT" monofásico a três fios com cliente de BT), 60.549 postes, 27.587 UC BT, 12.666 pontos de IP,
  1.385 unidades de GD. A BDGD **não traz geometria de nó**: a conectividade vem por códigos de ponto de acoplamento
  (PAC_1..PAC_3 no trafo, PN_CON na UC) e por coincidência de vértices.
- Linhagem entre safras (distribuidora de teste do ES, 2019-2024): chave de trafo estável em 99,0-99,4 % por par de anos;
  UCBT traz episódios (2-4 linhas por COD_ID) desde 2022; POT_NOM de 2021 teve troca em massa 45→15 kVA (23 %).
- Fluxo de potência já roda na casa (GPU box, `opendssdirect.py` 0.9.4, DSS C-API 0.14.5): 455 de 456 alimentadores da
  distribuidora de teste modelados, 332 convergiram nos 864 pontos (24 h × 3 tipos de dia × 12 meses, PRODIST Módulo 7),
  15 h de CPU; a cooperativa de teste inteira em ~40 s; perda de ferro simulada = 99,5 % da analítica PER_FER×8760.
  Armadilha registrada: sem o passo de partição por CTMT o modelo devolve zero em silêncio.
- Classificador de vegetação: 69.504 vãos de MT, 7 redes, 2 estados, faixa de 7,5 m por lado (NBR 15688 §5.6), NDVI
  Sentinel-2 P90 calibrado contra CHM Meta/WRI 1 m (2018-2020), AUC 0,74-0,81; nenhum vão visto em campo. Para transmissão,
  a geometria SINDAT desvia do as-built em mediana 3,1-11,2 km — não serve de faixa.
- Telemetria: o SIG de teste interno já tem `edpsig.telemetria_leitura (tenant_id, alvo_id, cod_id, ts, fonte, leitura jsonb,
  recebido_em)`; o dossiê P4 fixa as grandezas (corrente por fase 5-15 min, temperatura de tanque, tensão agregada 10 min =
  PRODIST Módulo 8 DRP/DRC).
- Continuidade: `/home/dev/liga/aneel_continuidade/` (3,7 GB: DEC/FEC 2020-2029, compensação, limites, dicionário de
  interrupções); a BDGD tem CONJ em SSDMT/UNTRMT/UCBT e DIC/FIC por UC.
- Água: EPANET `.inp` real no GPU box (11.119 nós, 7 reservatórios, 14.756 tubos, 941 km); FeatureServers abertos de rede
  de água de 5 operadoras com `licenseInfo` vazio (uso interno; nunca publicar derivado).
- Esri: 351 páginas de doc (Pro 3.4 = Enterprise 11.4: utility-network, network-diagrams, trace-network, parcel-editing,
  toolboxes, REST UtilityNetworkServer, NetworkDiagramServer, ParcelFabricServer, VersionManagementServer) responderam
  HTTP 200 em 05/09/2026 (lista no scratchpad `esri_ok.txt`; cada item do JSON cita as suas). A página de serviços de
  utility network do Server 11.4 diz que o serviço exige geodatabase corporativa com **branch versioning**.
- GeoServer e QGIS Server: nenhum tem topologia de rede, regra ou traçado (só WFS-T/OGC API); QGIS desktop tem análise
  de rede (caminho mais curto, área de serviço) e edição topológica; TEKSI/QGEP é o esquema aberto de esgoto/água em PostGIS.

## C1. Onde vive a rede: camada normal + topologia derivada (não "tabela de grafo" como fonte)

- Opções: (a) as feições de rede são camadas normais do inquilino e a topologia é um índice derivado, reconstruído por
  validação; (b) a rede é um grafo canônico (`no`/`aresta`) e as camadas são projeções; (c) `postgis_topology` como base.
- Custo de mudar depois: (a)→(b) obriga a reescrever edição, FeatureServer e versionamento; (b)→(a) perde o índice.
  (c) não modela terminal, associação nem tier — sair dela depois é refazer tudo.
- Recomendação: **(a)**, que é exatamente a arquitetura do utility network da Esri (`architecture.htm`, `about-network-
  topology.htm`): a topologia é um índice à parte, marcado sujo por edição e refeito por `validate`. Motivo medido: o
  FeatureServer/OGC do SIG de teste interno (RLS com 20 políticas, 9/9 testes) já edita camadas normais; o Pro e o QGIS
  continuam lendo as camadas como sempre. `postgis_topology` (instalada) fica como referência de faces/arestas para a malha
  de parcelas (C16), não para a rede.
- Obriga: L2-03 (edição) precisa de gancho pós-`applyEdits` por camada para gravar área suja; L2-04 (FeatureServer) expõe
  as camadas de rede sem saber que são rede.

## C2. Motor de grafo: pgRouting 4.0 sobre a topologia derivada, SQL de arestas filtrado por inquilino

- Opções: (a) pgRouting (Dijkstra, drivingDistance, connectedComponents, biconnectedComponents, articulationPoints,
  bridges, KSP, withPoints, contraction) lendo `plat.rede_topo_aresta`; (b) grafo em memória no serviço (networkx) carregado
  por subrede; (c) recursão SQL própria.
- Custo de mudar: (b) exige cache por inquilino e invalidação a cada edição — o que a Esri faz com o índice no banco; (c) é
  reescrever cada traçado.
- Recomendação: **(a) como motor, (c) só para montante/jusante direcional** (BFS a partir do controlador, que pgRouting não
  conhece). pgRouting aceita a SQL de arestas como texto: essa SQL SEMPRE carrega `WHERE tenant_id = current_setting(...)`
  e roda sob a role da aplicação (C11). Instalação pelo gerente no turno de L4-02-a (apt, guardrail de instalação).
  Contração (`pgr_contraction`) e partição por subrede são a resposta à escala (L4-22); o alvo ≤ 2 s p95 em 10 mil trechos
  é o portão, medido, não prometido.
- Obriga: L0-01 registra a extensão em `install.sh`; L4-23 testa o filtro de inquilino no `EXPLAIN`.

## C3. Esquema da rede é DADO: pacote de ativos versionado (JSON + tabelas)

- Opções: (a) domínio/tier/grupo/tipo/categoria/terminal/regra em tabelas de catálogo carregadas de um JSON versionado
  por inquilino; (b) esquema fixo em código (uma rede elétrica hard-coded); (c) um pacote por domínio em módulos Python.
- Custo de mudar: (b)/(c)→(a) obriga a migrar cada inquilino e reescrever validação; (a) permite água/gás/esgoto/telecom
  sem código novo.
- Recomendação: **(a)**, espelho do "asset package" da Esri (Utility Network Data Management Support) e dos pacotes
  "Electric/Water/Gas Utility Network Foundation". O pacote `elétrica-BR` nasce mapeado coluna a coluna às 13 camadas da BDGD
  Módulo 10; o `água-EPANET` nasce do `.inp`. Regras "sem regra = proibido" (doc `network-rules.htm`). Formato de importação/
  exportação de regras em CSV com as colunas da Esri para reaproveitar pacotes existentes.
- Obriga: L6-01 (acervo) publica os pacotes como itens com licença; L2-10 (domínios/subtipos) tem de aceitar subtipo
  codificado por grupo/tipo de ativo.

## C4. Terminal é nó: dispositivo com N terminais vira N nós + arestas internas com traversabilidade por estado

- Opções: (a) terminal como nó da topologia e caminhos internos como arestas (o estado da chave fecha/abre a aresta
  interna); (b) dispositivo como nó único com atributo "aberto/fechado"; (c) terminal só como atributo textual.
- Custo de mudar: (b)/(c)→(a) refaz importador, traçado e edição; sem (a) não existe "jusante a partir do lado BT do
  trafo" nem isolamento correto por lado de chave.
- Recomendação: **(a)** (doc `device-terminals.htm`, `create-a-terminal-configuration.htm`). Na BDGD, o lado AT do UNTRMT
  liga ao SSDMT e o lado BT ao SSDBT/RAMLIG — é o único jeito de o traçado não "subir" de BT para MT.
- Obriga: L2-03 (edição) mostra terminal ao conectar; L4-24 (cartografia) desenha terminal na escala de edição.

## C5. Atributos de rede desnormalizados na topologia (fase em bitmask, tensão, estado, subrede, is_connected)

- Opções: (a) copiar para `rede_topo_aresta/no` os atributos que o traçado lê (sincronizados por trigger/lote); (b) juntar
  com a camada a cada traçado.
- Custo de mudar: (b)→(a) é só desempenho; (a)→(b) perde 1 ordem de grandeza (junção com 5,6 mi de linhas por traçado).
- Recomendação: **(a)** (doc `network-attributes.htm`, `attribute-propagation.htm`, `is-connected-attribute.htm`). Fase
  como bitmask (A=1,B=2,C=4) propagável do controlador; concordância com FAS_CON da BDGD medida (portão de L4-01-d:
  ≥ 95 %, diferenças listadas como candidatas a erro de cadastro, nunca corrigidas em silêncio).
- Obriga: L2-10 (regras de atributo) ganha ponto de extensão para funções de rede (L4-29).

## C6. Subrede = nome propagado + controlador por terminal + linha agregada; atualização como job incremental

- Opções: (a) `plat.rede_subrede` (controlador, tier, estado limpa/suja, resumo) + coluna `subrede` em cada elemento +
  linha agregada; (b) subrede calculada a cada consulta.
- Custo de mudar: (b)→(a) é acrescentar; (a) é o que todo consumidor (painel, OpenDSS, CIM, diagrama) lê.
- Recomendação: **(a)** (doc `subnetworks.htm`, `subnetwork-controller.htm`, `update-subnetworks.htm`, `subnetline-feature-
  class.htm`, `export-subnetworks.htm`). Na importação BDGD, 1 controlador por CTMT (terminal do equipamento de saída da SUB
  ou nó de cabeça quando o arquivo não traz o equipamento) e 1 por UNTRMT no tier BT. Tier hierárquico (radial) tem direção;
  tier particionado (malha, transmissão) devolve "indeterminado" — nunca inventa direção (regra da casa: ausência de dado
  não vira medição).
- Obriga: L2-06 (painéis) liga a `rede_subrede_resumo`; L4-05-a/b exportam por subrede.

## C7. Traçado: contrato de API único, configuração nomeada, resultado tipado, tempo medido

- Opções: (a) `POST /api/v1/rede/{id}/tracar {tipo, pontos_de_partida[{feição,terminal}|{coordenada,tolerância}],
  barreiras, config_id|configuração_inline}` → `{elementos[], geometria_agregada, resumo, funções, avisos, tempo_ms,
  versao_topologia}`; (b) um endpoint por tipo; (c) só a fachada Esri.
- Custo de mudar: (b) multiplica testes; (c) prende o produto ao JSON da Esri.
- Recomendação: **(a) como contrato nosso, e a fachada Esri (L4-16) traduz** (doc `trace-utility-network-server`,
  `configure-a-trace.htm`, `results.htm`). Tipos: conectado, subrede, controladores, montante, jusante, isolamento, laços,
  caminho mais curto, isolados. Resultado sobre área suja devolve aviso com o polígono (nunca silêncio).
- Obriga: L7-08 (SDK) expõe `tracar()`; L2-05 (geoprocessamento) aceita resultado de traçado como entrada.

## C8. Versionamento: a rede obedece ao ramo de L2-13, com delta de topologia por versão e post só com zero área suja

- Opções: (a) versão = conjunto de linhas de delta (feições + topologia + áreas sujas) sobre a padrão, reconciliar detecta
  conflito de feição E de topologia, post exige validação; (b) versão = cópia da rede; (c) rede sem versão (edição direta).
- Custo de mudar: (c)→(a) refaz edição, campo e fachada Esri; (b) não escala (5,6 mi de linhas por cópia).
- Recomendação: **(a)** — é o que a Esri exige para serviço de UN (página 11.4: branch versioning obrigatório) e o que
  torna o cenário "e se" (L4-25) possível sem tocar a padrão. Momentos de rede (validado_em, subrede_atualizada_em) por versão.
- Obriga: **L2-13 tem de nascer assim** (dependência externa proposta); L2-07 (campo) sincroniza contra uma versão.

## C9. Diagrama esquemático: armazenado, com template (regras + layout) e coordenadas próprias; layout no servidor em Python

- Opções: (a) `rede_diagrama` + `rede_diagrama_no/aresta (x, y)` no espaço do diagrama, gerados de traçado/subrede,
  layouts calculados no servidor (networkx para árvore/radial; linha principal e força dirigida próprios com scipy);
  (b) layout no navegador (elkjs/dagre) sem armazenar; (c) diagrama = mapa com outra simbologia.
- Custo de mudar: (b) perde consistência (o diagrama tem de ficar "inconsistente" quando a rede muda) e não serve à API;
  (c) não é diagrama.
- Recomendação: **(a)** (doc `about-network-diagrams.htm`, `introduce-diagram-templates.htm`, `diagram-layouts.htm`,
  `diagram-rules.htm`, `network-diagram-consistency.htm`, REST `network-diagram-service`). O MapLibre exibe o diagrama em
  sistema de coordenadas próprio (unidades do diagrama), com seleção bidirecional. elkjs (EPL-2.0) só se um layout
  ortogonal exigir e o arquiteto aceitar a licença.
- Obriga: L2-01 (mapa) precisa de "vista sem CRS geográfico"; L2-12 (impressão) imprime diagrama.

## C10. CRS, tolerância e comprimento: geometria no CRS da plataforma, coincidência em geography com tolerância por rede, comprimento geodésico

- Opções: (a) tolerância de coincidência declarada por rede (padrão 0,05 m) avaliada por `ST_DWithin` em geography, e
  comprimento geodésico (GRS80) gravado na aresta; (b) tolerância em graus; (c) reprojetar para UTM por zona.
- Custo de mudar: (b) erra por latitude; (c) quebra rede que cruza zona (a maior distribuidora cruza 3).
- Recomendação: **(a)** (METODOLOGIA do motor de LT, regras 6 e 12: comprimento geodésico, CRS explícito em toda
  comparação, `ST_Buffer(geography)` devolve o SRID de entrada). Portão de L4-01-b: 0,04 m conecta, 0,06 m não.
- Obriga: L0-04 (ingestão) declara o CRS de origem; L2-05 mede comprimento do mesmo jeito.

## C11. Isolamento por inquilino: tenant_id + RLS em toda tabela de rede; pgRouting nunca como superusuário

- Opções: (a) RLS em catálogo, topologia, associações, subredes, erros, diagramas, medições e resultados, com a SQL de
  arestas já filtrada; (b) schema por inquilino; (c) banco por inquilino.
- Custo de mudar: (b)/(c) quebram o acervo compartilhado (L6) e o custo de operação (1 humano no laço).
- Recomendação: **(a)**, o padrão do SIG de teste interno (RLS por `SET LOCAL`), estendido: token com escopos
  `rede:ler/editar/validar/analisar`. Portão de L4-23: teste cruzado A→B em ≥ 40 rotas.
- Obriga: L0-02 (auth) aceita escopos por linha; L7-03 (segurança) inclui as rotas de rede na varredura.

## C12. Formatos de troca: BDGD (entrada), OpenDSS (análise), CIM/CGMES (troca), pandapower/MATPOWER, EPANET .inp, INSPIRE US (saída)

- Opções: (a) um exportador por formato lendo a subrede + pacote de ativos, com tabela de mapeamento tipo↔classe declarada;
  (b) um "formato interno" e conversores externos; (c) só BDGD/OpenDSS.
- Custo de mudar: (c) fecha a porta a quem já tem CIM ou EPANET; (b) é (a) com um passo a mais.
- Recomendação: **(a)**. OpenDSS é o motor de análise (trifásico desequilibrado, aceito pelo Módulo 7, já rodando na
  casa); pandapower para rede equilibrada/CGMES/curto-circuito IEC 60909; CIM só como "lido e escrito pelos conversores
  X e Y" — a norma IEC é paga e não foi lida; nunca escrever "conforme IEC". Conversor é só conversor: relatório "o que não
  fez" obrigatório (lição do `bdgd2opendss`, que a própria doc chama de "exclusivamente um conversor").
- Obriga: L0-05 (jobs) executa análise pesada como job com executor remoto (GPU box) quando a RAM local (3 GB livres) não
  permitir; L6-01 expõe os pacotes de exemplo abertos.

## C13. Análise elétrica é resultado versionado, sempre com estado de convergência e premissas ao lado

- Opções: (a) `plat.rede_fluxo_resultado` (versão da topologia, parâmetros, convergiu, n_passos_nao_conv, avisos jsonb,
  valores por elemento) e camadas derivadas; (b) resultado só em arquivo do job; (c) resultado sobrescreve atributo da camada.
- Custo de mudar: (c) mistura cadastro com simulação (irreversível); (b) não serve ao mapa nem ao painel.
- Recomendação: **(a)**, calcado nas colunas de `edp_es.perda_tecnica_modelo` (só leitura) que já carregam `convergiu`,
  `n_passos_nao_conv`, `avisos`. Regras da casa que viram portão: carregamento a partir de energia anual é estimativa com
  fator de carga assumido (0,45) — declarar sempre; percentual de perda só quando o balanço do arquivo fecha (na cooperativa
  de teste a faturada supera a injetada em 10 %: mostra-se "balanço não fecha"); alimentador que não convergiu não entra
  em agregação. Texto para fora: "triagem, sinal, não prova"; nunca "fraude/irregular".
- Obriga: L2-06 (painéis) e L2-02 (simbologia) leem resultado com tarja de convergência.

## C14. Telemetria: medição por ativo em tabela particionada nativa (sem TSL), ligada por global_id, entrada pelo L2-14

- Opções: (a) `plat.rede_medicao` particionada por tempo (partição nativa + pg_partman), chave = global_id do ativo,
  última leitura materializada na ficha; (b) hypertable TimescaleDB com compressão; (c) medição fora do banco (Parquet).
- Custo de mudar: (b) é gate jurídico (TSL proíbe DBaaS) — sair depois obriga a migrar dado do cliente; (c) perde a junção
  com a topologia (agregar a jusante).
- Recomendação: **(a)**, com a forma já provada em `edpsig.telemetria_leitura`. Alarmes contra nominal (kVA da placa,
  faixa de tensão do Módulo 8 lida da norma e gravada com fonte).
- Obriga: L2-14 aceita chave de ativo; L7-09 (medição/cobrança) conta pontos de medição.

## C15. Inspeção orbital é camada derivada com data, régua e ressalva — nunca atributo do cadastro

- Opções: (a) resultado por vão em tabela própria (NDVI P90, fração > 6 m no CHM, classe, nº de cenas, nuvem, datas) com
  a ressalva impressa; (b) gravar "vegetação=ALTO" no trecho.
- Custo de mudar: (b) contamina o cadastro e apaga a data da cena.
- Recomendação: **(a)**, com o classificador calibrado da casa (limiar por estado/zona) e as regras: "localiza", não
  "antecipa"; 4-7× o acaso; classe por vão, nunca por árvore; o CHM é modelo de 2018-2020; transmissão só com eixo
  as-built (SIGEL), com SINDAT o job recusa.
- Obriga: L1-03 (conectores de sensor) fornece Sentinel-2 por STAC e o CHM por /vsicurl; L0-05 roda como job.

## C16. Parcelas (L4-parcelas): modelo dirigido por REGISTRO, linhas COGO, ajuste por mínimos quadrados em numpy; não é rede

- Opções: (a) `plat.parcela_registro/parcela_<tipo>/linha/ponto` com histórico por registro (parcela ativa/histórica),
  linhas com rumo/distância/raio, `postgis_topology` como apoio para linhas partilhadas, ajuste LSA em numpy/scipy;
  (b) parcelas como camada de polígonos com versionamento genérico; (c) reaproveitar o modelo de rede (nó/aresta).
- Custo de mudar: (b)→(a) refaz histórico e COGO; (c) força semântica errada (parcela é área fechada por linhas com
  medida, não fluxo).
- Recomendação: **(a)** (doc `whatisparcelfabric.htm`, `aboutparcelfabricschema.htm`, `createparcelfabricrecords.htm`,
  `least-squares-parcel-fabric.htm`, REST `parcel-fabric-service`). Dado de exemplo: os 8.638 lotes DERIVADOS do SIG de teste
  interno (dado aberto, lote ≠ matrícula). Regra da casa: parcela ≠ gleba ≠ lote ≠ matrícula; SIGEF e CAR são polígonos
  declarados, entram como referência, nunca como parcela "oficial"; nenhuma matrícula real, nenhum nome.
- Obriga: L2-13 (versionamento) serve às parcelas; L2-03 (edição) fornece COGO básico (rumo/distância) reaproveitável.

## C17. Paridade e fachada Esri: contrato nosso primeiro, fachada `UtilityNetworkServer`/`NetworkDiagramServer`/`ParcelFabricServer` por cima, e "Pro edita UN contra nós" declarado FORA

- Opções: (a) fachada que traduz os JSON da doc REST para os nossos endpoints (trace, validateNetworkTopology,
  queryAssociations, updateSubnetwork, exportSubnetwork, traceConfigurations, locations, queryNetworkMoments,
  unitIdentifiers; diagram templates, createDiagramFromFeatures, applyLayout, export; build/divide/merge/clip/LSA); (b) nada
  compatível; (c) prometer que o ArcGIS Pro edita a nossa rede.
- Custo de mudar: (c) é promessa impossível de cumprir — o UN do Pro exige geodatabase corporativa da Esri com branch
  versioning e o dataset proprietário; descobrir isso depois de vender é refazer o discurso.
- Recomendação: **(a)**, com o script de conformidade por operação (parâmetro a parâmetro, doc datada) e a linha "Pro
  editando UN contra nós = FORA" escrita em `docs/PARIDADE.md` com a URL. O que a Esri não faz (fluxo de potência, perdas,
  DEC/FEC, hospedagem de GD, inspeção orbital, balanço, série temporal de safras) entra como "além da paridade", não
  como "paridade".
- Obriga: o papel `esri` mantém a tabela; L2-08 (migração) chama L4-17 quando o item migrado é rede.

## O que fica FORA desta rodada (declarado)

- Circuits de telecom (UN versão 7, REST `circuits-utility-network-server`) — registrado em PARIDADE como fora.
- Download de BDGD "pelo nome" para qualquer distribuidora — depende de D21 (disco).
- Simulação hidráulica (WNTR/EPANET) e simulação de gás (pandapipes) — só depois da instalação decidida pelo arquiteto por item.
- Qualquer uso de dado de FeatureServer de operadora com licença vazia fora de teste interno.
- Qualquer número em documento para fora que não saia de `tests/medidas/*.json`.

## Addendum 06/09/2026 — pesquisa: multi-setor de rede e alcance internacional/baixo recurso (D38, pedido do dono)

Pergunta do dono: vale perseguir "água, rodovia, construção etc., não só elétrica", com arquitetura plugável, incluindo países de menos recurso? Pesquisa datada, com fonte:

- **A decisão C3 já resolve o "plugável".** Esquema da rede é DADO (pacote de ativos JSON+tabelas versionado), não código — água/gás/telecom já têm formato de importação declarado em C12 (EPANET .inp, pandapipes, CIM/CGMES). "Trazer o dado deles" não é item novo de arquitetura; é ingestão de um pacote de ativos existente. Isso é MELHOR que grande parte do mercado: o próprio Esri só multiplexa domínios dentro de UMA licença de Utility Network, com rastreamento cruzado entre eles ("an outage from an electrical network can affect the delivery of another resource, such as gas or water") — [Esri, ArcGIS Utility Network overview](https://www.esri.com/en-us/arcgis/products/arcgis-utility-network/overview). Isso é o alvo de paridade do L4-01-a + tracing cross-domínio, ainda não item explícito — abrir se o dono priorizar 2º setor.
- **Existe um padrão internacional formal para isto**: o modelo genérico de rede da INSPIRE (UE), que estende o "Generic Network Model" (GNM) com sub-esquemas por setor — Eletricidade, Óleo/Gás/Químico, Esgoto, Térmica, Água, Telecomunicações — [INSPIRE, Utility and Governmental Services](https://knowledge-base.inspire.ec.europa.eu/utility-and-governmental-services_en). Alinhar o pacote de ativos (C3) ao GNM, não só ao Esri, dá exportabilidade fora do Brasil sem redesenho — candidato a decisão futura, não urgente.
- **Água é o candidato mais forte de 2º setor**: EPANET/WNTR já no ADR (C12), padrão INSPIRE Water Network existe, e o gancho social é medido — mais de 2 bilhões de pessoas sem acesso seguro a água potável — [Esri/Fulcrum, water infrastructure](https://www.fulcrumapp.com/blog/water-and-wastewater-infrastructure-planning-with-gis-data/). Mas hoje ZERO fonte de dado de água real foi ingerida (diferente de elétrica: 376 fontes, BDGD, PRODIST) — o item L4-05-d/e é só o FORMATO de troca, não dado.
- **Rodovia NÃO é uma rede de utilidade no sentido do L4** (não tem "traçado/isolamento/subrede" como elétrica/água) — é routing + condição de pavimento + tráfego, tema separado da INSPIRE ("Transport Networks", diferente de "Utility and Governmental Services"). Hoje a casa só tem corredor/routing de LT (L4-19) e OSRM genérico (L2-11) — rodovia como PRODUTO teria de nascer como linha própria, não um item dentro de L4.
- **Construção NÃO é rede** — é BIM/IFC (GABARITO, projeto separado da casa). Confundir os dois é erro de categoria; não entra em L4.
- **Achados sobre países de baixo recurso** (relevantes para "plugável, funciona com pouco recurso"): pesquisa aponta 3 problemas recorrentes — (1) software caro e complexo, (2) dado de entrada de baixa qualidade "mas a apresentação em GIS sugere veracidade" (o mesmo risco que a casa já trata com "triagem: sinal, não prova"), (3) pouca capacidade local de análise/DBA — [PMC, GIS baixo recurso](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3051879/); "dado de pavimento de rodovia raramente existe" em países em desenvolvimento — mesma fonte. Isso favorece exatamente o que já está no roadmap: **appliance auto-hospedado (L7-11)**, UI para não-especialista, e camada de sensoriamento orbital como FALLBACK quando não há cadastro oficial (já é know-how da casa em outros projetos) — não um item novo, uma priorização do que já existe.

**Recomendação registrada, não decidida**: não abrir "água/rodovia/construção" como frente nova agora. Documentar a capacidade plugável (ela já existe por C3) como argumento comercial; só investir em ingestão real de 2º setor (água, candidato) quando houver demanda medida — mesma disciplina que travou L1-L7 em portão verificável, não promessa.
