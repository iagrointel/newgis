# Dado de demonstração (item L0-13-dado-demonstracao)

Conjunto pequeno e aberto que o instalador semeia nos inquilinos de demonstração `demo` e `demo2`,
para que a plataforma nunca precise de dado de cliente para ser mostrada, testada ou fotografada.

- Os arquivos ficam em `dados_demo/arquivos/`, comitados no repositório (nenhuma instalação baixa
  nada da rede). Tamanho total medido: **1.19 MB em 11 arquivos**.
- `dados_demo/catalogo.json` é a fonte de verdade (arquivo, inquilino, formato, título, resumo,
  tags, categoria, fonte, órgão, endereço, licença, data de acesso, bytes e sha256).
- `scripts/semear_dado_demo.py` semeia pela PRÓPRIA API: envia o arquivo, registra o item de
  arquivo, cria a importação e confirma a proposta. Não existe caminho paralelo de carga.
- Este documento é gerado por `dados_demo/gerar_do_acervo.py --so-doc`; não edite à mão.
- Nenhum arquivo tem nome de pessoa, CPF, nome de empresa privada, nome de cliente, de parceiro ou
  de piloto. O que existe de nome próprio é topônimo oficial do IBGE (município, rio, rodovia).
- `demo` e `demo2` recebem conjuntos DIFERENTES: o que está num não aparece no outro. É assim que se
  vê na tela que um inquilino não enxerga o dado do outro.

## Cada arquivo, com fonte, endereço, licença e data de acesso


### Inquilino `demo`

#### `municipios_ap_rr.zip`

- Título no catálogo: Limites municipais do Amapá e de Roraima
- Fonte: IBGE, malha municipal
- Órgão: IBGE
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Formato: shapefile.zip · 161559 bytes · sha256 `2f9e8ef463244c58c333100aeb29fdd1e8e0f42cbba072d98f8949a000023541`
- Uso: carregado como camada pela ingestão

#### `pontos_municipais_ap_rr.geojson`

- Título no catálogo: Ponto representativo dos municípios do Amapá e de Roraima
- Fonte: IBGE, malha municipal (ponto derivado pela casa)
- Órgão: IBGE
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Formato: geojson · 6075 bytes · sha256 `46eb9a3d9808bbcd331c5a0337689145243680c8911a60940f926f7e11e54e27`
- Uso: carregado como camada pela ingestão

#### `rodovias_federais_rr.geojson`

- Título no catálogo: Rodovias federais de Roraima
- Fonte: DNIT, SNV (rodovias federais)
- Órgão: DNIT
- Endereço: https://servicos.dnit.gov.br/vgeo/
- Licença: DNIT, dado público do VGeo; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Formato: geojson · 91370 bytes · sha256 `d97855c658667e30514ef25264e74ce2f1708bc96e4c6f8464b7ab2ca3da4a14`
- Uso: carregado como camada pela ingestão

#### `hidrografia_bacia_4668.geojson`

- Título no catálogo: Hidrografia da otto-bacia 4668
- Fonte: ANA, Base Hidrográfica Ottocodificada (BHO 2017)
- Órgão: ANA
- Endereço: https://dadosabertos.ana.gov.br/
- Licença: ANA, dado aberto; licença não declarada na fonte (campo licenseInfo nulo no portal, conferido em 06/09/2026)
- Data de acesso: 2026-09-06
- Formato: geojson · 374457 bytes · sha256 `66ce1103d7150cf51edfa191ed5e629603faf3c7171ee7df9ce7a3f41afa4ddb`
- Uso: carregado como camada pela ingestão

#### `estacoes_inmet_norte.csv`

- Título no catálogo: Estações meteorológicas do INMET na região Norte
- Fonte: INMET, cadastro de estações
- Órgão: INMET
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Formato: csv · 5493 bytes · sha256 `6e277ab2af3492cf1df4f98084a38f97fb5d5574d366a335625854b303cabb5d`
- Uso: carregado como camada pela ingestão

#### `demonstracao_3_camadas.gpkg`

- Título no catálogo: GeoPackage de demonstração com três camadas
- Fonte: IBGE, DNIT e ANA (mesmas camadas acima, reunidas pela casa)
- Órgão: IBGE/DNIT/ANA
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos); DNIT, dado público do VGeo; licença não declarada na fonte; ANA, dado aberto; licença não declarada na fonte (campo licenseInfo nulo no portal, conferido em 06/09/2026)
- Data de acesso: 2026-09-06
- Formato: gpkg · 393216 bytes · sha256 `1035423dbdc50e354267cf34398d175dcf1c6e6951406f5312dbb70980f98ce4`
- Uso: carregado como camada pela ingestão

#### `estacoes_inmet_norte.xlsx`

- Título no catálogo: Planilha das estações do INMET na região Norte
- Fonte: INMET, cadastro de estações (convertido pela casa)
- Órgão: INMET
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Formato: xlsx · 7831 bytes · sha256 `b4c8662aaa0024ab5e9f1db139f485daaef677209de0ec1185895d56bed85981`
- Uso: fica no catálogo como arquivo (formato ainda não ingerido: lacuna do L0-04-d)

#### `planta_exemplo.dxf`

- Título no catálogo: Planta de exemplo em DXF
- Fonte: desenho da casa (dados_demo/gerar_do_acervo.py)
- Órgão: iAgroSat
- Endereço: https://iagrointel.com/
- Licença: CC0 1.0 (arquivo desenhado pela casa só para demonstração; nenhum dado de terceiro dentro)
- Data de acesso: 2026-09-06
- Formato: dxf · 9337 bytes · sha256 `b37a397d3ae50192f7eb493ee573e25edea7a8741855fa06c7d8bca805c17332`
- Uso: fica no catálogo como arquivo (formato ainda não ingerido: lacuna do L0-04-d)

### Inquilino `demo2`

#### `municipios_ac.zip`

- Título no catálogo: Limites municipais do Acre
- Fonte: IBGE, malha municipal
- Órgão: IBGE
- Endereço: https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/
- Licença: IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)
- Data de acesso: 2026-09-06
- Formato: shapefile.zip · 81101 bytes · sha256 `3198c01e98abf3b2116b76b6fc3f48e8d5f452ff7a74328fdabcc741a6395b84`
- Uso: carregado como camada pela ingestão

#### `rodovias_federais_ac.geojson`

- Título no catálogo: Rodovias federais do Acre
- Fonte: DNIT, SNV (rodovias federais)
- Órgão: DNIT
- Endereço: https://servicos.dnit.gov.br/vgeo/
- Licença: DNIT, dado público do VGeo; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Formato: geojson · 52149 bytes · sha256 `a1b404525a616597a03ed859dbac49b8ad59025173e6c1f71011b7ac74a5d5aa`
- Uso: carregado como camada pela ingestão

#### `estacoes_inmet_centro_oeste.csv`

- Título no catálogo: Estações meteorológicas do INMET na região Centro-Oeste
- Fonte: INMET, cadastro de estações
- Órgão: INMET
- Endereço: https://portal.inmet.gov.br/dadoshistoricos
- Licença: INMET, dado aberto; licença não declarada na fonte
- Data de acesso: 2026-09-06
- Formato: csv · 10446 bytes · sha256 `b6455dd85e4e6172337e2249adae06fbbe70213e0a5802ea46b12701f3d78d68`
- Uso: carregado como camada pela ingestão

## O que a semeadura cria além dos arquivos

No inquilino `demo`: as categorias do catálogo, dois grupos de demonstração, o primeiro item
compartilhado com um desses grupos, um link de compartilhamento e um item na lixeira
(`Planta de exemplo (versão retirada do catálogo)`).
