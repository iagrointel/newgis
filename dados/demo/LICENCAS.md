# Licencas do pacote de dado de demonstracao

Gerado por `dados/demo/gerar_licencas.py` a partir de `dados/demo/catalogo.json`. Nao editar a mao: editar o catalogo e rodar o gerador de novo.

Total de arquivos: 9. Tamanho somado: 0.96 MB (teto do item: 300 MB).

## Limites municipais do Amapá e de Roraima

- **Arquivo**: `dados/demo/arquivos/municipios_ap_rr.zip` (161,559 bytes, sha256 `2f9e8ef463244c58c333100aeb29fdd1e8e0f42cbba072d98f8949a000023541`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: IBGE, malha municipal (IBGE)
- **Endereco**: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- **Licenca**: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- **Data de acesso**: 2026-09-06
- **Resumo**: Malha municipal do IBGE recortada em dois estados e simplificada para 0,002 grau.

## Limites municipais do Acre

- **Arquivo**: `dados/demo/arquivos/municipios_ac.zip` (81,101 bytes, sha256 `3198c01e98abf3b2116b76b6fc3f48e8d5f452ff7a74328fdabcc741a6395b84`)
- **Inquilino de demonstracao**: `demo2`
- **Orgao/fonte**: IBGE, malha municipal (IBGE)
- **Endereco**: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- **Licenca**: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- **Data de acesso**: 2026-09-06
- **Resumo**: Malha municipal do IBGE recortada em um estado, simplificada para 0,002 grau. Usada só em demo2 para provar isolamento entre inquilinos.

## Ponto representativo dos municípios do Amapá e de Roraima

- **Arquivo**: `dados/demo/arquivos/pontos_municipais_ap_rr.geojson` (6,075 bytes, sha256 `46eb9a3d9808bbcd331c5a0337689145243680c8911a60940f926f7e11e54e27`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: IBGE, malha municipal (ponto derivado pela casa) (IBGE)
- **Endereco**: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- **Licenca**: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- **Data de acesso**: 2026-09-06
- **Resumo**: Um ponto por município, obtido por ST_PointOnSurface do próprio limite municipal do IBGE. Não é a sede municipal oficial.

## Rodovias federais de Roraima

- **Arquivo**: `dados/demo/arquivos/rodovias_federais_rr.geojson` (91,370 bytes, sha256 `d97855c658667e30514ef25264e74ce2f1708bc96e4c6f8464b7ab2ca3da4a14`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: DNIT, SNV (rodovias federais) (DNIT)
- **Endereco**: https://servicos.dnit.gov.br/vgeo/
- **Licenca**: DNIT, dado público do VGeo; licença não declarada na fonte
- **Data de acesso**: 2026-09-06
- **Resumo**: Trechos do Sistema Nacional de Viação (SNV) do DNIT no estado de Roraima.

## Hidrografia da otto-bacia 4668

- **Arquivo**: `dados/demo/arquivos/hidrografia_bacia_4668.geojson` (374,457 bytes, sha256 `66ce1103d7150cf51edfa191ed5e629603faf3c7171ee7df9ce7a3f41afa4ddb`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: ANA, Base Hidrográfica Ottocodificada (BHO 2017) (ANA)
- **Endereco**: https://metadados.snirh.gov.br/geonetwork/srv/por/catalog.search#/metadata/BHO_2017_curso_dagua
- **Licenca**: ANA, dado público (Lei de Acesso à Informação); sem licença explícita CC no metadado
- **Data de acesso**: 2026-09-06
- **Resumo**: Trechos de drenagem da Base Hidrográfica Ottocodificada (BHO 2017) de uma única otto-bacia.

## Estações meteorológicas do INMET na região Norte

- **Arquivo**: `dados/demo/arquivos/estacoes_inmet_norte.csv` (5,493 bytes, sha256 `6e277ab2af3492cf1df4f98084a38f97fb5d5574d366a335625854b303cabb5d`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: INMET, cadastro de estações (INMET)
- **Endereco**: https://portal.inmet.gov.br/paginas/catalogoestações
- **Licenca**: INMET, dado público (Lei de Acesso à Informação)
- **Data de acesso**: 2026-09-06
- **Resumo**: Cadastro de estações automáticas e convencionais do INMET com latitude/longitude, região Norte.

## Vias de Fernando de Noronha (OpenStreetMap)

- **Arquivo**: `dados/demo/arquivos/vias_fernando_de_noronha.geojson` (185,398 bytes, sha256 `290a5c12faef51ff11562506510ce5850aef0c15e5ba7ecaef44c65e23d2db9f`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: OpenStreetMap, contribuidores (extraído via Overpass API) (OpenStreetMap Foundation)
- **Endereco**: https://overpass-api.de/api/interpreter
- **Licenca**: Open Database License (ODbL) 1.0 — https://www.openstreetmap.org/copyright
- **Data de acesso**: 2026-09-07
- **Resumo**: 411 trechos com a marca highway=* extraídos do OpenStreetMap por uma consulta Overpass (way["highway"] no retângulo -32.45,-3.90,-32.38,-3.82). Usada como camada de ARESTAS do item de demonstração do tipo `rede` — é um grafo de vias, não uma rede de utilidade (elétrica/água); o documento do item diz isso.

## Nós da rede de vias de Fernando de Noronha (derivado)

- **Arquivo**: `dados/demo/arquivos/nos_via_fernando_de_noronha.geojson` (68,470 bytes, sha256 `bbad8db9219f0278d3f11c7133d086da0d55235b84dea8f5186f008090c22269`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: OpenStreetMap, contribuidores (nós derivados pela casa a partir do extrato Overpass) (OpenStreetMap Foundation)
- **Endereco**: https://overpass-api.de/api/interpreter
- **Licenca**: Open Database License (ODbL) 1.0 — https://www.openstreetmap.org/copyright
- **Data de acesso**: 2026-09-07
- **Resumo**: 576 pontos, um por extremidade única de trecho de via do arquivo vias_fernando_de_noronha.geojson (derivado pela casa, mesma fonte). Usada como camada de NÓS do item de demonstração do tipo `rede`.

## Sentinel-2, composição visual (TCI), recorte de Fernando de Noronha

- **Arquivo**: `dados/demo/arquivos/sentinel2_fernando_de_noronha_visual.tif` (37,040 bytes, sha256 `cd1cf8db2b5208100347affadad610e8b5fb312edd6a8bbd287c5f5c9e675875`)
- **Inquilino de demonstracao**: `demo`
- **Orgao/fonte**: ESA/Copernicus Sentinel-2 L2A, catálogo STAC Earth Search (Element 84) sobre o AWS Open Data (ESA / Copernicus Programme)
- **Endereco**: https://earth-search.aws.element84.com/v1
- **Licenca**: Copernicus Sentinel Data — acesso livre e gratuito (Copernicus Open Access, Regulation (EU) No 1159/2013)
- **Data de acesso**: 2026-09-07
- **Resumo**: Recorte de 778 x 885 pixels (10 m, ~7,8 x 8,8 km), 3 bandas (composição visual TCI já processada pelo provedor), da cena S2B_25MER_20260819_0_L2A (nuvem 4,5%), lido por janela via /vsicurl do COG publicado no Earth Search da Element 84 (AWS Open Data). GUARDADO COMO ARQUIVO, não como camada raster processada: a ingestão de raster (COG + pgSTAC) é item separado (L1-01-ingest-raster), ainda parcial nesta base — `plat demo verificar` confere o arquivo e o hash, não uma camada raster.

## Nota sobre nomes proprios

Nenhum arquivo deste pacote cita nome de cliente, parceiro ou piloto da casa (conferido por `tests/api/test_dado_demo_l7.py::test_nenhum_nome_de_cliente_parceiro_ou_piloto`, que abre inclusive o conteudo dos `.zip`). Os orgaos citados (IBGE, DNIT, ANA, INMET, OpenStreetMap Foundation, ESA/Copernicus) sao fontes de dado aberto, nao clientes ou parceiros comerciais da iAgroSat.
