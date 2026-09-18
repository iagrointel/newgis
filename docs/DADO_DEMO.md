# Dados de demonstração instalados com o appliance

Este arquivo lista todo dado de terceiro que o instalador ou a galeria de mapas base (item
L2-01-e-mapas-base) instala por padrão, com licença, atribuição obrigatória e proveniência —
exigido pelo portão de pronto do item. Nenhuma fonte aqui é dado de cliente.

## Mapas base (galeria, `plat.item` tipo `mapa_base`)

| # | fonte | tipo de instalação | atribuição (`item.creditos`) | licença (`item.termos_de_uso`) | proveniência |
|---|---|---|---|---|---|
| 1 | OpenStreetMap (recorte de Guarulhos-SP) | PMTiles vetorial local, servido por Range HTTP pelo próprio nginx (`web/dados/basemap/guarulhos.pmtiles`) | © colaboradores do OpenStreetMap | ODbL 1.0 (Open Database License) — https://opendatacommons.org/licenses/odbl/1-0/ | `web/dados/basemap/PROVENIENCIA.md` (item L2-01-a-basemap-local-pmtiles); extraído com `ogr2ogr` + `tippecanoe` de um extrato OSM datado |
| 2 | OpenStreetMap (padrão, "Standard" tile layer) | raster, por proxy próprio com cache em disco e `User-Agent` identificado (`GET /api/mapas-base/osm/{z}/{x}/{y}.png`, nunca o navegador direto — política de uso do OSM) | © colaboradores do OpenStreetMap | dado ODbL 1.0; estilo cartográfico "Standard" sob CC BY-SA 2.0 — ver https://www.openstreetmap.org/copyright | política de uso: https://operations.osmfoundation.org/policies/tiles/ (uso pesado sem cache é proibido; daí o proxy) |
| 3 | Sentinel-2 (mosaico da casa) | raster, servido direto pelo navegador a partir de um TiTiler (`PLAT_TITILER_URL`, item L1-02), COG único (cena 23KLQ) | Contém dados Copernicus Sentinel modificados, processados pela casa via TiTiler | reuso livre conforme a Política de Dados e Informação do Programa Copernicus (Regulamento (UE) nº 1159/2013) | cena baixada e convertida a COG (`s2-23klq-20260818_visual*.tif`, banda visual RGB) no balde de objetos da própria casa; instalada só quando `PLAT_TITILER_URL` está configurado — sem isso a fonte 3 não entra na galeria |
| 4 | (nenhuma) | fundo de cor sólida, sem fonte externa | — | — | sem dado de terceiro; sempre disponível |

## Regra de instalação

`app/mapas_base/semear.py` só cria os itens 1, 2 e 4 sempre; o item 3 (satélite) só entra quando o
inquilino técnico tem `PLAT_TITILER_URL` configurado (produção não tem por padrão — ver `.env`).
`POST /api/mapas-base/instalar` é idempotente: chamar de novo não duplica nem sobrescreve um item
que o admin já editou (título/ordem/padrão mudados manualmente).

## Por que nenhuma licença aqui é "livre para qualquer uso"

ODbL exige atribuição e "share-alike" de bases de dados derivadas; CC BY-SA da cartografia OSM
exige atribuição e mesma licença de trabalhos derivados; a Política de Dados do Copernicus é aberta
mas cita a UE/ESA como titular dos dados originais. A atribuição visível no canto do mapa (DOM) e a
listagem acima cobrem a exigência de atribuição das três licenças; nenhuma delas autoriza remover a
atribuição, mesmo em relatório impresso.

## Conjunto de demonstração (`dados_demo/`, item L0-13-dado-demonstracao)

Os arquivos abaixo são o conjunto que o `install.sh` semeia em `demo` e `demo2` quando a instalação é
de demonstração (`PLAT_AMBIENTE` de demonstração; em produção nada é semeado). Um bloco por arquivo, com
a mesma fonte, endereço, licença e data de acesso que `dados_demo/catalogo.json` registra — o teste
`tests/api/test_dado_demo.py` reprova quando documento e catálogo divergem em qualquer um dos quatro campos.

Nenhum arquivo aqui é dado de cliente, de parceiro ou de piloto, e o mesmo teste varre os arquivos
(inclusive dentro dos `.zip`) contra a lista de nomes proibidos da casa.

Uma alteração declarada na origem: de `estacoes_inmet_centro_oeste.csv` foi removida uma linha, a da
estação A934 (MT). O nome do município dela colide, como palavra inteira, com um nome da lista de
`laco/nomes_proibidos.regex` — o nome não é repetido aqui, porque este documento passa pela mesma varredura.
A estação é pública e legítima; a remoção existe para manter a varredura absoluta, sem lista de exceção.
O resto do arquivo é o cadastro oficial do INMET tal como baixado.

#### `municipios_ap_rr.zip`

- Título: Limites municipais do Amapá e de Roraima
- Inquilino: demo
- Formato: shapefile.zip
- Fonte: IBGE, malha municipal
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Tamanho: 161559 bytes (sha256 `2f9e8ef463244c58c333100aeb29fdd1e8e0f42cbba072d98f8949a000023541`)

#### `pontos_municipais_ap_rr.geojson`

- Título: Ponto representativo dos municípios do Amapá e de Roraima
- Inquilino: demo
- Formato: geojson
- Fonte: IBGE, malha municipal (ponto derivado pela casa)
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Tamanho: 6075 bytes (sha256 `46eb9a3d9808bbcd331c5a0337689145243680c8911a60940f926f7e11e54e27`)

#### `rodovias_federais_rr.geojson`

- Título: Rodovias federais de Roraima
- Inquilino: demo
- Formato: geojson
- Fonte: DNIT, SNV (rodovias federais)
- Endereço: https://servicos.dnit.gov.br/vgeo/
- Licença: DNIT, dado público do VGeo; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Tamanho: 91370 bytes (sha256 `d97855c658667e30514ef25264e74ce2f1708bc96e4c6f8464b7ab2ca3da4a14`)

#### `hidrografia_bacia_4668.geojson`

- Título: Hidrografia da otto-bacia 4668
- Inquilino: demo
- Formato: geojson
- Fonte: ANA, Base Hidrográfica Ottocodificada (BHO 2017)
- Endereço: https://dadosabertos.ana.gov.br/
- Licença: ANA, dado aberto; licença não declarada na fonte (campo licenseInfo nulo no portal, conferido em 06/09/2026)
- Data de acesso: 2026-09-06
- Tamanho: 374457 bytes (sha256 `66ce1103d7150cf51edfa191ed5e629603faf3c7171ee7df9ce7a3f41afa4ddb`)

#### `estacoes_inmet_norte.csv`

- Título: Estações meteorológicas do INMET na região Norte
- Inquilino: demo
- Formato: csv
- Fonte: INMET, cadastro de estações
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Tamanho: 5493 bytes (sha256 `6e277ab2af3492cf1df4f98084a38f97fb5d5574d366a335625854b303cabb5d`)

#### `demonstracao_3_camadas.gpkg`

- Título: GeoPackage de demonstração com três camadas
- Inquilino: demo
- Formato: gpkg
- Fonte: IBGE, DNIT e ANA (mesmas camadas acima, reunidas pela casa)
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos); DNIT, dado público do VGeo; licença não declarada na fonte; ANA, dado aberto; licença não declarada na fonte (campo licenseInfo nulo no portal, conferido em 06/09/2026)
- Data de acesso: 2026-09-06
- Tamanho: 393216 bytes (sha256 `1035423dbdc50e354267cf34398d175dcf1c6e6951406f5312dbb70980f98ce4`)

#### `estacoes_inmet_norte.xlsx`

- Título: Planilha das estações do INMET na região Norte
- Inquilino: demo
- Formato: xlsx
- Fonte: INMET, cadastro de estações (convertido pela casa)
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Tamanho: 7831 bytes (sha256 `b4c8662aaa0024ab5e9f1db139f485daaef677209de0ec1185895d56bed85981`)

#### `planta_exemplo.dxf`

- Título: Planta de exemplo em DXF
- Inquilino: demo
- Formato: dxf
- Fonte: desenho da casa (dados_demo/gerar_do_acervo.py)
- Endereço: https://iagrointel.com/
- Licença: CC0 1.0 (arquivo desenhado pela casa só para demonstração; nenhum dado de terceiro dentro)
- Data de acesso: 2026-09-06
- Tamanho: 9337 bytes (sha256 `b37a397d3ae50192f7eb493ee573e25edea7a8741855fa06c7d8bca805c17332`)

#### `municipios_ac.zip`

- Título: Limites municipais do Acre
- Inquilino: demo2
- Formato: shapefile.zip
- Fonte: IBGE, malha municipal
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Tamanho: 81101 bytes (sha256 `3198c01e98abf3b2116b76b6fc3f48e8d5f452ff7a74328fdabcc741a6395b84`)

#### `rodovias_federais_ac.geojson`

- Título: Rodovias federais do Acre
- Inquilino: demo2
- Formato: geojson
- Fonte: DNIT, SNV (rodovias federais)
- Endereço: https://servicos.dnit.gov.br/vgeo/
- Licença: DNIT, dado público do VGeo; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Tamanho: 52149 bytes (sha256 `a1b404525a616597a03ed859dbac49b8ad59025173e6c1f71011b7ac74a5d5aa`)

#### `estacoes_inmet_centro_oeste.csv`

- Título: Estações meteorológicas do INMET na região Centro-Oeste
- Inquilino: demo2
- Formato: csv
- Fonte: INMET, cadastro de estações
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Tamanho: 10380 bytes (sha256 `883f45456098117517ba9950e73e5b09875a6d1288eef1ef538fe783553e1e28`)
