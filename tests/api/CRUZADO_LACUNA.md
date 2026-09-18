# Rotas vivas SEM caso na varredura cruzada A→B — medido em 18/09/2026

`docs/openapi.json` (regerado hoje do esquema vivo) lista **960** operacoes.
`tests/api/cruzado_casos.py` tem caso para **439**. Sem caso: **521** (54,3 %).

A medida antiga de `tests/medidas/L0-02-e.json` (138/138, "100 %") e de **06/09/2026**,
quando a API tinha 138 rotas. Ela nunca mediu estas 521.

Por metodo: GET 291 - POST 171 - DELETE 28 - PUT 23 - PATCH 8.

## Por familia

| familia | sem caso | de escrita |
|---|---:|---:|
| `/svc/rest` | 43 | 14 |
| `/api/rede` | 39 | 19 |
| `/rest/services` | 34 | 18 |
| `/api/camadas` | 25 | 14 |
| `/api/amc` | 18 | 10 |
| `/api/conexoes` | 18 | 3 |
| `/api/campo` | 17 | 7 |
| `/api/itens` | 15 | 9 |
| `/api/org` | 15 | 10 |
| `/api/imagens` | 11 | 7 |
| `/svc/ogc` | 10 | 0 |
| `/api/parcelas` | 10 | 10 |
| `/api/intercambio` | 9 | 4 |
| `/api/webhooks` | 9 | 6 |
| `/api/acervo` | 9 | 0 |
| `/api/mapa` | 9 | 5 |
| `/api/sso` | 9 | 2 |
| `/api/dominios` | 8 | 5 |
| `/api/fluxos` | 8 | 5 |
| `/api/modelos3d` | 8 | 2 |
| `/api/chamados` | 8 | 4 |
| `/api/ferramentas` | 8 | 4 |
| `/api/telemetria` | 7 | 5 |
| `/notebooks` | 7 | 4 |
| `/api/simbolos` | 7 | 1 |
| `/api/exportacoes` | 6 | 2 |
| `/api/inquilino` | 6 | 2 |
| `/api/migracao` | 6 | 2 |
| `/api/widgets` | 6 | 2 |
| `/ogc/features` | 6 | 4 |
| `/api/agol` | 6 | 3 |
| `/api/plataforma` | 6 | 3 |
| `/api/relacionamentos` | 5 | 4 |
| `/api/geocodificador` | 5 | 2 |
| `/api/layouts` | 5 | 3 |
| `/api/login` | 5 | 1 |
| `/api/mapas` | 5 | 2 |
| `/api/odk` | 5 | 2 |
| `/svc/camadas` | 5 | 0 |
| `/svc/mosaico` | 5 | 0 |
| `/api/anotacoes` | 4 | 3 |
| `/api/modelos` | 4 | 2 |
| `/svc/stac` | 4 | 2 |
| `/api/crs` | 4 | 1 |
| `/api/formularios` | 4 | 2 |
| `/api/geoparquet` | 4 | 1 |
| `/api/mapas-base` | 4 | 2 |
| `/svc/raster` | 4 | 0 |
| `/api/log` | 3 | 2 |
| `/api/auditoria` | 3 | 1 |
| `/api/endpoints-publicos` | 3 | 1 |
| `/api/render` | 3 | 2 |
| `/api/backup` | 2 | 0 |
| `/api/foto360` | 2 | 1 |
| `/api/modelo3d` | 2 | 1 |
| `/wmts/rest` | 2 | 0 |
| `/api/csw` | 2 | 2 |
| `/api/multiescala` | 2 | 2 |
| `/api/pacotes` | 2 | 2 |
| `/api/cena` | 1 | 0 |
| `/api/dominios-limites` | 1 | 0 |
| `/api/dominios.csv` | 1 | 0 |
| `/api/eventos` | 1 | 0 |
| `/api/modo` | 1 | 0 |
| `/api/p` | 1 | 0 |
| `/api/portal` | 1 | 0 |
| `/api/publico` | 1 | 0 |
| `/api/videos` | 1 | 0 |
| `/csw` | 1 | 0 |
| `/svc/cog` | 1 | 0 |
| `/svc/wms` | 1 | 0 |
| `/tiles/tilejson.json` | 1 | 0 |
| `/tiles` | 1 | 0 |
| `/videos/arquivo` | 1 | 0 |
| `/wms` | 1 | 0 |
| `/wmts` | 1 | 0 |
| `/api/compartilhado` | 1 | 1 |
| `/api/estilos` | 1 | 1 |
| `/api/usuarios` | 1 | 1 |

## Lista completa

### `/svc/rest` (43)

- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/areasAndLengths`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/buffer`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/convexHull`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/difference`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/distance`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/intersect`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/lengths`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/project`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/simplify`
- `POST /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/union`
- `POST /svc/{token}/rest/services/{item_id}/MapServer/export`
- `POST /svc/{token}/rest/services/{item_id}/MapServer/find`
- `POST /svc/{token}/rest/services/{item_id}/MapServer/identify`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/areasAndLengths`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/buffer`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/convexHull`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/difference`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/distance`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/intersect`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/lengths`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/project`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/simplify`
- `GET /svc/{token}/rest/services/Utilities/Geometry/GeometryServer/union`
- `GET /svc/{token}/rest/services/{item_id}/MapServer`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/export`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/find`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/generateKml`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/identify`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/layers`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/legend`
- `GET /svc/{token}/rest/services/{item_id}/MapServer/{camada_id}`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer/resources/fonts/{fontstack}/{faixa}.pbf`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer/resources/sprites/sprite.json`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer/resources/sprites/sprite.png`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer/resources/styles/root.json`
- `GET /svc/{token}/rest/services/{item_id}/VectorTileServer/tile/{z}/{y}/{x}.pbf`
- `GET /svc/{token}/rest/services/{item}/ImageServer`
- `GET /svc/{token}/rest/services/{item}/ImageServer/exportImage`
- `GET /svc/{token}/rest/services/{item}/ImageServer/identify`
- `GET /svc/{token}/rest/services/{item}/ImageServer/tile/{level}/{row}/{col}`

### `/api/rede` (39)

- `DELETE /api/rede/{rede_id}/faixas/{faixa_id}`
- `PATCH /api/rede/{rede_id}/ativos/{global_id}`
- `POST /api/rede/medicao/leituras`
- `POST /api/rede/{rede_id}/applyEdits`
- `POST /api/rede/{rede_id}/ativos`
- `POST /api/rede/{rede_id}/atributos/conectividade`
- `POST /api/rede/{rede_id}/atributos/propagar-fase`
- `POST /api/rede/{rede_id}/atributos/sincronizar`
- `POST /api/rede/{rede_id}/atributos/substituicoes`
- `POST /api/rede/{rede_id}/epanet`
- `POST /api/rede/{rede_id}/faixas`
- `POST /api/rede/{rede_id}/importar-osm`
- `POST /api/rede/{rede_id}/regras.csv`
- `POST /api/rede/{rede_id}/teksi`
- `POST /api/rede/{rede_id}/validar`
- `POST /api/rede/{rede_id}/validar_extensao`
- `PUT /api/rede/medicao/ativos/{ativo}`
- `PUT /api/rede/{rede_id}/area_sujas/modo`
- `PUT /api/rede/{rede_id}/regras/ativacao`
- `GET /api/rede/medicao/ativos/{ativo}`
- `GET /api/rede/medicao/ativos/{ativo}/serie`
- `GET /api/rede/medicao/ativos/{ativo}/ultimas`
- `GET /api/rede/medicao/grandezas`
- `GET /api/rede/medicao/jusante`
- `GET /api/rede/{rede_id}/areas_sujas`
- `GET /api/rede/{rede_id}/ativos`
- `GET /api/rede/{rede_id}/ativos/{global_id}`
- `GET /api/rede/{rede_id}/ativos/{global_id}/renomeacoes`
- `GET /api/rede/{rede_id}/atributos/discrepancias`
- `GET /api/rede/{rede_id}/epanet`
- `GET /api/rede/{rede_id}/epanet/{importacao_id}`
- `GET /api/rede/{rede_id}/erros`
- `GET /api/rede/{rede_id}/esgoto/escoamento`
- `GET /api/rede/{rede_id}/faixas`
- `GET /api/rede/{rede_id}/gas/pressao`
- `GET /api/rede/{rede_id}/importacoes`
- `GET /api/rede/{rede_id}/regras`
- `GET /api/rede/{rede_id}/regras.csv`
- `GET /api/rede/{rede_id}/tracar`

### `/rest/services` (34)

- `POST /rest/services/{ferramenta}/GPServer/{tarefa}/execute`
- `POST /rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/cancel`
- `POST /rest/services/{ferramenta}/GPServer/{tarefa}/submitJob`
- `POST /rest/services/{item_id}/VersionManagementServer`
- `POST /rest/services/{item_id}/VersionManagementServer/create`
- `POST /rest/services/{item_id}/VersionManagementServer/versionInfos`
- `POST /rest/services/{item_id}/VersionManagementServer/versions`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/conflicts`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/delete`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/post`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/reconcile`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/startEditing`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/startReading`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/stopEditing`
- `POST /rest/services/{item_id}/VersionManagementServer/{versao_guid}/stopReading`
- `POST /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers`
- `POST /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/query`
- `POST /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/reserve`
- `GET /rest/services/{ferramenta}/GPServer`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}/execute`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/cancel`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}/jobs/{job_id}/results/{parametro}`
- `GET /rest/services/{ferramenta}/GPServer/{tarefa}/submitJob`
- `GET /rest/services/{item_id}/FeatureServer/0/queryRelatedRecords`
- `GET /rest/services/{item_id}/FeatureServer/{camada}`
- `GET /rest/services/{item_id}/VersionManagementServer`
- `GET /rest/services/{item_id}/VersionManagementServer/versionInfos`
- `GET /rest/services/{item_id}/VersionManagementServer/versions`
- `GET /rest/services/{item_id}/VersionManagementServer/{versao_guid}/conflicts`
- `GET /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers`
- `GET /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/query`
- `GET /rest/services/{servico}/UtilityNetworkServer/unitIdentifiers/reserve`

### `/api/camadas` (25)

- `DELETE /api/camadas/{id}/versoes/{versao}`
- `DELETE /api/camadas/{item_id}/dominios/{ligacao_id}`
- `DELETE /api/camadas/{item_id}/subtipos`
- `POST /api/camadas/{id}/versionar`
- `POST /api/camadas/{id}/versoes`
- `POST /api/camadas/{id}/versoes/{versao}/conflitos/{globalid}/resolver`
- `POST /api/camadas/{id}/versoes/{versao}/publicar`
- `POST /api/camadas/{id}/versoes/{versao}/reconciliar`
- `POST /api/camadas/{item_id}/dominios`
- `POST /api/camadas/{item_id}/feicoes`
- `POST /api/camadas/{item_id}/tabela/estatisticas`
- `POST /api/camadas/{item_id}/tabela/linhas`
- `PUT /api/camadas/{item_id}/subtipos`
- `PUT /api/camadas/{item_id}/tabela/vista`
- `GET /api/camadas/{id}/feicoes/{fid}/popup`
- `GET /api/camadas/{id}/versoes`
- `GET /api/camadas/{id}/versoes/{versao}`
- `GET /api/camadas/{id}/versoes/{versao}/conflitos`
- `GET /api/camadas/{item_id}/classes`
- `GET /api/camadas/{item_id}/dominios`
- `GET /api/camadas/{item_id}/relacionados/{rel}`
- `GET /api/camadas/{item_id}/relacionamentos`
- `GET /api/camadas/{item_id}/subtipos`
- `GET /api/camadas/{item_id}/tabela/colunas`
- `GET /api/camadas/{item_id}/tabela/vista`

### `/api/amc` (18)

- `DELETE /api/amc/presets/{id}`
- `PATCH /api/amc/presets/{id}`
- `POST /api/amc/criterios-feicao`
- `POST /api/amc/criterios-feicao/exportar`
- `POST /api/amc/presets`
- `POST /api/amc/presets/importar`
- `POST /api/amc/presets/{id}/aplicar`
- `POST /api/amc/similaridade`
- `POST /api/amc/similaridade/exportar`
- `POST /api/amc/transformacoes/previsao`
- `GET /api/amc/conjuntos/{conjunto_id}/unidades`
- `GET /api/amc/execucoes/{execucao_id}/matriz`
- `GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao`
- `GET /api/amc/modelos/{modelo_id}/versoes`
- `GET /api/amc/modelos/{modelo_id}/versoes/{versao_hash}`
- `GET /api/amc/presets`
- `GET /api/amc/presets/{id}`
- `GET /api/amc/presets/{id}/exportar`

### `/api/conexoes` (18)

- `POST /api/conexoes/{id}/arquivo/sincronizar`
- `POST /api/conexoes/{id}/descobrir`
- `PUT /api/conexoes/{id}/arquivo`
- `GET /api/conexoes/{id}/arquivo`
- `GET /api/conexoes/{id}/esri/camadas/{camada}`
- `GET /api/conexoes/{id}/esri/camadas/{camada}/contagem`
- `GET /api/conexoes/{id}/esri/camadas/{camada}/feicoes`
- `GET /api/conexoes/{id}/esri/descricao`
- `GET /api/conexoes/{id}/esri/imagem`
- `GET /api/conexoes/{id}/esri/mapa`
- `GET /api/conexoes/{id}/tile`
- `GET /api/conexoes/{id}/tilejson`
- `GET /api/conexoes/{id}/wms/capacidades`
- `GET /api/conexoes/{id}/wms/feicao`
- `GET /api/conexoes/{id}/wms/mapa`
- `GET /api/conexoes/{id}/wmts/capacidades`
- `GET /api/conexoes/{id}/wmts/tile-info`
- `GET /api/conexoes/{id}/wmts/tile/{tile_matrix_set}/{z}/{x}/{y}`

### `/api/campo` (17)

- `POST /api/campo/filas`
- `POST /api/campo/filas/{fila_id}/alvos`
- `POST /api/campo/roteiros`
- `POST /api/campo/sessao`
- `POST /api/campo/visitas`
- `POST /api/campo/visitas/{visita_id}/fotos`
- `PUT /api/campo/filas/{fila_id}/ordem`
- `GET /api/campo/camadas/{camada_id}/globalids`
- `GET /api/campo/filas`
- `GET /api/campo/filas/{fila_id}`
- `GET /api/campo/filas/{fila_id}/alvos.geojson`
- `GET /api/campo/mapas`
- `GET /api/campo/roteiros`
- `GET /api/campo/roteiros/{roteiro_id}`
- `GET /api/campo/roteiros/{roteiro_id}/trajeto.geojson`
- `GET /api/campo/visitas`
- `GET /api/campo/visitas/{visita_id}`

### `/api/itens` (15)

- `DELETE /api/itens/{id}/publicacao`
- `DELETE /api/itens/{id}/site`
- `POST /api/itens/{id}/exportar`
- `POST /api/itens/{id}/metadado.xml`
- `POST /api/itens/{id}/metadado/validar`
- `POST /api/itens/{id}/publicacao`
- `POST /api/itens/{item_id}/paineis/fontes/{fonte_id}/dados`
- `PUT /api/itens/{id}/metadado`
- `PUT /api/itens/{id}/site`
- `GET /api/itens/{id}/metadado`
- `GET /api/itens/{id}/pacote`
- `GET /api/itens/{id}/publicacao`
- `GET /api/itens/{id}/publicacao/exportacao`
- `GET /api/itens/{id}/publicacao/visualizacoes`
- `GET /api/itens/{id}/site`

### `/api/org` (15)

- `DELETE /api/org/oidc/{provedor_id}`
- `DELETE /api/org/saml/{provedor_id}`
- `POST /api/org/exportar`
- `POST /api/org/oidc`
- `POST /api/org/saml`
- `PUT /api/org/logins/{tipo}/{id}`
- `PUT /api/org/oidc/{provedor_id}`
- `PUT /api/org/saml/{provedor_id}`
- `PUT /api/org/sso/oidc`
- `PUT /api/org/sso/saml`
- `GET /api/org/logins`
- `GET /api/org/oidc`
- `GET /api/org/saml`
- `GET /api/org/sso/oidc`
- `GET /api/org/sso/saml`

### `/api/imagens` (11)

- `DELETE /api/imagens/{item_id}/predefinicoes/{nome}`
- `POST /api/imagens/ingestoes`
- `POST /api/imagens/proveniencia/preencher-pendentes`
- `POST /api/imagens/{item_id}/conferir`
- `POST /api/imagens/{item_id}/predefinicoes`
- `POST /api/imagens/{item_id}/predefinicoes/{nome}/tornar-padrao`
- `PUT /api/imagens/{item_id}/predefinicoes/{nome}`
- `GET /api/imagens/formatos`
- `GET /api/imagens/{item_id}`
- `GET /api/imagens/{item_id}/predefinicoes`
- `GET /api/imagens/{item_id}/tiles/{z}/{x}/{y}.png`

### `/svc/ogc` (10)

- `GET /svc/{token}/ogc/tiles`
- `GET /svc/{token}/ogc/tiles/collections`
- `GET /svc/{token}/ogc/tiles/collections/{item}`
- `GET /svc/{token}/ogc/tiles/collections/{item}/map`
- `GET /svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}`
- `GET /svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}`
- `GET /svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}.{ext}`
- `GET /svc/{token}/ogc/tiles/conformance`
- `GET /svc/{token}/ogc/tiles/tileMatrixSets`
- `GET /svc/{token}/ogc/tiles/tileMatrixSets/{tile_matrix_set_id}`

### `/api/parcelas` (10)

- `POST /api/parcelas/fabrica/analyzeByLSA`
- `POST /api/parcelas/fabrica/applyLSA`
- `POST /api/parcelas/fabrica/assignFeaturesToRecord`
- `POST /api/parcelas/fabrica/build`
- `POST /api/parcelas/fabrica/clip`
- `POST /api/parcelas/fabrica/createSeeds`
- `POST /api/parcelas/fabrica/divide`
- `POST /api/parcelas/fabrica/merge`
- `POST /api/parcelas/fabrica/reconstructFromSeeds`
- `POST /api/parcelas/qualidade`

### `/api/intercambio` (9)

- `DELETE /api/intercambio/exportacoes/{id}`
- `POST /api/intercambio/exportacoes`
- `POST /api/intercambio/importacoes-lote`
- `PUT /api/intercambio/importacoes-lote/{lote_id}/confirmar`
- `GET /api/intercambio/exportacoes`
- `GET /api/intercambio/exportacoes/{id}`
- `GET /api/intercambio/exportacoes/{id}/baixar`
- `GET /api/intercambio/formatos`
- `GET /api/intercambio/importacoes-lote/{lote_id}`

### `/api/webhooks` (9)

- `DELETE /api/webhooks/{id}`
- `PATCH /api/webhooks/{id}`
- `POST /api/webhooks`
- `POST /api/webhooks/{id}/entregas/{entrega_id}/reenviar`
- `POST /api/webhooks/{id}/reativar`
- `POST /api/webhooks/{id}/rotacionar`
- `GET /api/webhooks`
- `GET /api/webhooks/{id}`
- `GET /api/webhooks/{id}/entregas`

### `/api/acervo` (9)

- `GET /api/acervo/camadas/{acervo_camada_id}/verificacoes`
- `GET /api/acervo/camadas/{camada}/exportar`
- `GET /api/acervo/dominios`
- `GET /api/acervo/frescor/camadas`
- `GET /api/acervo/frescor/execucoes`
- `GET /api/acervo/frescor/mudancas`
- `GET /api/acervo/meu-mapa`
- `GET /api/acervo/uso`
- `GET /api/acervo/uso/mensal`

### `/api/mapa` (9)

- `POST /api/mapa/camadas/{id}/filtrar`
- `POST /api/mapa/camadas/{id}/selecionar`
- `POST /api/mapa/pacotes/importar`
- `POST /api/mapa/selecao-espacial`
- `POST /api/mapa/{mapa_id}/desenho/promover`
- `GET /api/mapa/camadas/{id}/estilo`
- `GET /api/mapa/camadas/{id}/feicoes/{fid}`
- `GET /api/mapa/camadas/{id}/valores`
- `GET /api/mapa/fuso`

### `/api/sso` (9)

- `POST /api/sso/saml/acs`
- `POST /api/sso/saml/slo`
- `GET /api/sso/oidc/iniciar`
- `GET /api/sso/oidc/logout`
- `GET /api/sso/oidc/retorno`
- `GET /api/sso/saml/iniciar`
- `GET /api/sso/saml/logout`
- `GET /api/sso/saml/metadata`
- `GET /api/sso/saml/slo`

### `/api/dominios` (8)

- `DELETE /api/dominios/{dominio_id}`
- `POST /api/dominios`
- `POST /api/dominios/csv`
- `POST /api/dominios/importar`
- `PUT /api/dominios/{dominio_id}`
- `GET /api/dominios`
- `GET /api/dominios/{dominio_id}`
- `GET /api/dominios/{dominio_id}/uso`

### `/api/fluxos` (8)

- `DELETE /api/fluxos/{id}`
- `DELETE /api/fluxos/{id}/eventos`
- `PATCH /api/fluxos/{id}`
- `POST /api/fluxos`
- `POST /api/fluxos/{id}/simular`
- `GET /api/fluxos`
- `GET /api/fluxos/{id}`
- `GET /api/fluxos/{id}/eventos`

### `/api/modelos3d` (8)

- `DELETE /api/modelos3d/{id}`
- `POST /api/modelos3d`
- `GET /api/modelos3d`
- `GET /api/modelos3d/{id}`
- `GET /api/modelos3d/{id}/3dtiles/{caminho}`
- `GET /api/modelos3d/{id}/elementos`
- `GET /api/modelos3d/{id}/elementos/{guid}`
- `GET /api/modelos3d/{id}/glb`

### `/api/chamados` (8)

- `POST /api/chamados`
- `POST /api/chamados/{id}/anexos`
- `POST /api/chamados/{id}/comentarios`
- `POST /api/chamados/{id}/fechar`
- `GET /api/chamados`
- `GET /api/chamados/banner`
- `GET /api/chamados/{id}`
- `GET /api/chamados/{id}/anexos/{anexo_id}`

### `/api/ferramentas` (8)

- `POST /api/ferramentas/script`
- `POST /api/ferramentas/script/{id}/executar`
- `POST /api/ferramentas/script/{id}/versao`
- `POST /api/ferramentas/{nome}/executar`
- `GET /api/ferramentas`
- `GET /api/ferramentas/script/{id}/execucoes`
- `GET /api/ferramentas/script/{id}/formulario`
- `GET /api/ferramentas/{nome}`

### `/api/telemetria` (7)

- `DELETE /api/telemetria/appliances/{chave}`
- `POST /api/telemetria/appliances`
- `POST /api/telemetria/enviar`
- `POST /api/telemetria/receber`
- `PUT /api/telemetria`
- `GET /api/telemetria`
- `GET /api/telemetria/appliances`

### `/notebooks` (7)

- `DELETE /notebooks/{slug}/{caminho}`
- `PATCH /notebooks/{slug}/{caminho}`
- `POST /notebooks/{slug}/{caminho}`
- `PUT /notebooks/{slug}/{caminho}`
- `GET /notebooks/{slug}`
- `GET /notebooks/{slug}/`
- `GET /notebooks/{slug}/{caminho}`

### `/api/simbolos` (7)

- `POST /api/simbolos`
- `GET /api/simbolos`
- `GET /api/simbolos/fontes/{fontstack}/{faixa}.pbf`
- `GET /api/simbolos/sprite/{slug}.json`
- `GET /api/simbolos/sprite/{slug}.png`
- `GET /api/simbolos/sprite/{slug}@2x.json`
- `GET /api/simbolos/sprite/{slug}@2x.png`

### `/api/exportacoes` (6)

- `DELETE /api/exportacoes/{exportacao_id}`
- `POST /api/exportacoes`
- `GET /api/exportacoes`
- `GET /api/exportacoes/formatos`
- `GET /api/exportacoes/{exportacao_id}`
- `GET /api/exportacoes/{exportacao_id}/baixar`

### `/api/inquilino` (6)

- `DELETE /api/inquilino/exportacoes/{exportacao_id}`
- `POST /api/inquilino/exportar`
- `GET /api/inquilino/exportacoes`
- `GET /api/inquilino/exportacoes/{exportacao_id}`
- `GET /api/inquilino/exportacoes/{exportacao_id}/baixar`
- `GET /api/inquilino/exportar/estimativa`

### `/api/migracao` (6)

- `DELETE /api/migracao/inventarios/{id}`
- `POST /api/migracao/inventarios`
- `GET /api/migracao/inventarios`
- `GET /api/migracao/inventarios/{id}`
- `GET /api/migracao/inventarios/{id}/itens`
- `GET /api/migracao/inventarios/{id}/relatorio.csv`

### `/api/widgets` (6)

- `DELETE /api/widgets/externos/{nome}`
- `POST /api/widgets/externos`
- `GET /api/widgets/externos`
- `GET /api/widgets/externos/{nome}`
- `GET /api/widgets/externos/{nome}/i18n.json`
- `GET /api/widgets/externos/{nome}/modulo.js`

### `/ogc/features` (6)

- `DELETE /ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}`
- `PATCH /ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}`
- `POST /ogc/features/{item_id}/collections/{colecao_id}/items`
- `PUT /ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}`
- `GET /ogc/features/{item_id}/api`
- `GET /ogc/features/{item_id}/collections/{colecao_id}/queryables`

### `/api/agol` (6)

- `POST /api/agol/publicacoes`
- `POST /api/agol/testar`
- `PUT /api/agol/credencial`
- `GET /api/agol/credencial`
- `GET /api/agol/publicacoes`
- `GET /api/agol/publicacoes/{item_id}`

### `/api/plataforma` (6)

- `POST /api/plataforma/chamados/{id}/comentarios`
- `POST /api/plataforma/chamados/{id}/estado`
- `POST /api/plataforma/inquilinos/{id}/cotas`
- `GET /api/plataforma/chamados`
- `GET /api/plataforma/chamados/{id}`
- `GET /api/plataforma/chamados/{id}/anexos/{anexo_id}`

### `/api/relacionamentos` (5)

- `DELETE /api/relacionamentos/{rel_id}`
- `POST /api/relacionamentos`
- `POST /api/relacionamentos/{rel_id}/desligar`
- `POST /api/relacionamentos/{rel_id}/ligar`
- `GET /api/relacionamentos/{rel_id}`

### `/api/geocodificador` (5)

- `PATCH /api/geocodificador/lote/{item_id}/pendentes/{fid}`
- `POST /api/geocodificador/lote/{item_id}/regeocodificar`
- `GET /api/geocodificador/lote`
- `GET /api/geocodificador/lote/{item_id}`
- `GET /api/geocodificador/lote/{item_id}/pendentes`

### `/api/layouts` (5)

- `POST /api/layouts/exportar`
- `POST /api/layouts/previa`
- `POST /api/layouts/validar`
- `GET /api/layouts/modelos`
- `GET /api/layouts/modelos/{id}`

### `/api/login` (5)

- `POST /api/login/saml/acs`
- `GET /api/login/oidc/iniciar`
- `GET /api/login/oidc/retorno`
- `GET /api/login/saml/iniciar`
- `GET /api/login/saml/metadata`

### `/api/mapas` (5)

- `POST /api/mapas`
- `PUT /api/mapas/{id}`
- `GET /api/mapas`
- `GET /api/mapas/{id}`
- `GET /api/mapas/{id}/completo`

### `/api/odk` (5)

- `POST /api/odk/pontes`
- `POST /api/odk/pontes/{id}/sincronizar`
- `GET /api/odk/pontes`
- `GET /api/odk/pontes/{id}`
- `GET /api/odk/pontes/{id}/entidades/{dataset}`

### `/svc/camadas` (5)

- `GET /svc/{token}/camadas/{item_id}.csv`
- `GET /svc/{token}/camadas/{item_id}.fgb`
- `GET /svc/{token}/camadas/{item_id}.geojson`
- `GET /svc/{token}/camadas/{item_id}.gpkg`
- `GET /svc/{token}/camadas/{item_id}.kml`

### `/svc/mosaico` (5)

- `GET /svc/{token}/mosaico/{alvo}/{z}/{x}/{y}.{ext}`
- `GET /svc/{token}/mosaico/{mosaico_id}/pegadas`
- `GET /svc/{token}/mosaico/{mosaico_id}/tilejson.json`
- `GET /svc/{token}/mosaico/{mosaico_id}/wmts`
- `GET /svc/{token}/mosaico/{mosaico_id}/wmts/1.0.0/WMTSCapabilities.xml`

### `/api/anotacoes` (4)

- `DELETE /api/anotacoes/{id}`
- `PATCH /api/anotacoes/{id}`
- `POST /api/anotacoes`
- `GET /api/anotacoes`

### `/api/modelos` (4)

- `DELETE /api/modelos/{id}`
- `POST /api/modelos`
- `GET /api/modelos`
- `GET /api/modelos/{id}/pacote`

### `/svc/stac` (4)

- `DELETE /svc/{token}/stac/mosaicos/{mosaico_id}`
- `POST /svc/{token}/stac/mosaicos`
- `GET /svc/{token}/stac/mosaicos`
- `GET /svc/{token}/stac/mosaicos/{mosaico_id}`

### `/api/crs` (4)

- `POST /api/crs/transformar`
- `GET /api/crs`
- `GET /api/crs/{epsg}`
- `GET /api/crs/{epsg}.proj4`

### `/api/formularios` (4)

- `POST /api/formularios/xlsform`
- `POST /api/formularios/{id}/respostas`
- `GET /api/formularios/equivalencia`
- `GET /api/formularios/{id}`

### `/api/geoparquet` (4)

- `POST /api/geoparquet`
- `GET /api/geoparquet`
- `GET /api/geoparquet/{catalogo_item_id}/arquivos`
- `GET /api/geoparquet/{job_id}`

### `/api/mapas-base` (4)

- `POST /api/mapas-base/instalar`
- `POST /api/mapas-base/{id}/tornar-padrao`
- `GET /api/mapas-base`
- `GET /api/mapas-base/osm/{z}/{x}/{y}.png`

### `/svc/raster` (4)

- `GET /svc/{token}/raster/{item}/estatisticas.json`
- `GET /svc/{token}/raster/{item}/legenda.json`
- `GET /svc/{token}/raster/{item}/legenda.png`
- `GET /svc/{token}/raster/{item}/predefinicoes.json`

### `/api/log` (3)

- `DELETE /api/log/nivel`
- `POST /api/log/nivel`
- `GET /api/log/nivel`

### `/api/auditoria` (3)

- `PUT /api/auditoria/config`
- `GET /api/auditoria`
- `GET /api/auditoria/config`

### `/api/endpoints-publicos` (3)

- `POST /api/endpoints-publicos/{id}/adicionar`
- `GET /api/endpoints-publicos`
- `GET /api/endpoints-publicos/{id}`

### `/api/render` (3)

- `POST /api/render/mapa`
- `POST /api/render/token`
- `GET /api/render/saude`

### `/api/backup` (2)

- `GET /api/backup/backups`
- `GET /api/backup/ensaios`

### `/api/foto360` (2)

- `POST /api/foto360`
- `GET /api/foto360/{item_id}`

### `/api/modelo3d` (2)

- `POST /api/modelo3d/ingestoes`
- `GET /api/modelo3d/{item_id}`

### `/wmts/rest` (2)

- `GET /wmts/{item_id}/rest/WMTSCapabilities.xml`
- `GET /wmts/{item_id}/rest/{camada}/{estilo}/{tms}/{z}/{y}/{x}.png`

### `/api/csw` (2)

- `POST /api/csw/buscar`
- `POST /api/csw/conexoes`

### `/api/multiescala` (2)

- `POST /api/multiescala/execucoes/{id}/backtest`
- `POST /api/multiescala/execucoes/{id}/corredor`

### `/api/pacotes` (2)

- `POST /api/pacotes/importar`
- `POST /api/pacotes/verificar`

### `/api/cena` (1)

- `GET /api/cena/sol`

### `/api/dominios-limites` (1)

- `GET /api/dominios-limites`

### `/api/dominios.csv` (1)

- `GET /api/dominios.csv`

### `/api/eventos` (1)

- `GET /api/eventos/camadas`

### `/api/modo` (1)

- `GET /api/modo`

### `/api/p` (1)

- `GET /api/p/{inquilino}/{slug}`

### `/api/portal` (1)

- `GET /api/portal/exemplos`

### `/api/publico` (1)

- `GET /api/publico/wms/{fonte}`

### `/api/videos` (1)

- `GET /api/videos`

### `/csw` (1)

- `GET /csw`

### `/svc/cog` (1)

- `GET /svc/{token}/cog/{item}/{asset}.tif`

### `/svc/wms` (1)

- `GET /svc/{token}/wms`

### `/tiles/tilejson.json` (1)

- `GET /tiles/{token}/{item_id}/tilejson.json`

### `/tiles` (1)

- `GET /tiles/{token}/{item_id}/{z}/{x}/{y}.pbf`

### `/videos/arquivo` (1)

- `GET /videos/arquivo/{caminho}`

### `/wms` (1)

- `GET /wms/{item_id}`

### `/wmts` (1)

- `GET /wmts/{item_id}`

### `/api/compartilhado` (1)

- `POST /api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados`

### `/api/estilos` (1)

- `POST /api/estilos/compilar`

### `/api/usuarios` (1)

- `POST /api/usuarios/{id}/desregistrar`

