# Roteiro de demonstração em 30 minutos

plat · análise / beta privado · setembro de 2026

Este roteiro percorre o que o produto faz hoje, passo a passo, em uma instalação real da versão
atual. A instalação de referência é a de teste interno. Nada aqui descreve produção. O conteúdo é
criado ao vivo durante a demonstração. A plataforma não tem carga de dados de demonstração
embutida. Cada afirmação do texto é verificável na tela ou na interface de programação no momento da
demonstração. O que a plataforma não faz está na lista gerada do painel do laço, no fim deste
documento, e no quadro de pedidos frequentes logo abaixo.

Cada passo declara o que dizer, o que não prometer e o teste de ponta a ponta que percorre o mesmo
caminho. O teste é `tests/e2e/test_demo.py`. Ele mede o tempo total do roteiro e reprova se o tempo passar de
30 minutos.

Antes de começar, abra um navegador de mesa no endereço da instalação. Tenha em mãos a credencial do
administrador do inquilino de demonstração. Deixe o catálogo sem nenhum conteúdo pré-carregado.

## Passo 1 — Versão e estado de saúde (1 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: A instalação responde em um endereço próprio. A primeira tela mostra a versão e o
  estado de saúde. O número de versão na tela é o mesmo que a interface de programação devolve em
  /api/versao. A resposta inclui também o identificador do commit do repositório. O estado "ok"
  significa que o banco está no esquema atual. Com o banco desatualizado, a mesma verificação
  responde 503.
- não prometer: A plataforma está em fase de análise e em beta privado. O nome público ainda não foi
  definido pelo dono. A demonstração usa o codinome interno.

## Passo 2 — Acesso controlado (2 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: O acesso pede o nome do inquilino, o usuário e a senha. A política de senha recusa
  senhas fracas. A conta bloqueia após tentativas repetidas de entrada. Cada usuário pode ativar o
  segundo fator por aplicativo gerador de código, com códigos de 6 dígitos que trocam a cada 30
  segundos, no padrão RFC 6238.
- não prometer: A entrada única por OIDC (OpenID Connect) ou SAML (Security Assertion Markup
  Language) ainda não existe. A integração LDAP (Lightweight Directory Access Protocol) está
  entregue. Os demais protocolos de federação estão na lista do que a plataforma não faz ainda.

## Passo 3 — Catálogo do inquilino (6 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: O catálogo organiza o conteúdo do inquilino em pastas, com tags, categorias e busca
  por campo. O item da demonstração é criado ao vivo, com título editado e duas tags aplicadas. A
  busca por campo encontra o item pelo título. O item favoritado aparece na aba de favoritos. Um item
  apagado vai para a lixeira e volta com o mesmo identificador.
- não prometer: O catálogo é interno ao inquilino. O compartilhamento por link é revogável. Não há
  portal público. A migração de conteúdo a partir do ArcGIS Online ainda não existe.

## Passo 4 — Envio de arquivo em partes (4 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: O envio de um arquivo grande é dividido em partes de 16 MiB (mebibytes), tamanho
  definido na configuração da plataforma. A tela mostra o avanço por parte. A conclusão confere o resumo
  criptográfico sha256 do arquivo inteiro. Uma parte que falhar pode ser reenviada sem repetir o
  arquivo inteiro.
- não prometer: Os conversores cobrem hoje os formatos básicos da fundação. Formatos como CAD,
  FileGDB e Parquet ainda não têm conversor. A exportação de dados do inquilino ainda não existe.

## Passo 5 — Fila de tarefas (4 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: Trabalhos demorados saem da requisição e vão para uma fila no próprio banco Postgres.
  A lista de tarefas mostra o progresso ao vivo sem recarregar a página. O detalhe mostra o estado, o
  resultado e o registro de execução. Uma tarefa em curso pode ser cancelada pela tela. A
  demonstração cria uma tarefa de prova, acompanha a conclusão e cancela uma segunda.
- não prometer: A fila executa os tipos de trabalho que o produto já tem. Ferramentas de
  geoprocessamento e análise como serviço ainda não existem.

## Passo 6 — Mapa com base local (5 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: O mapa desenha uma base cartográfica local. O arquivo da base tem 18,3 MiB. O arquivo
  é um recorte de Guarulhos do OpenStreetMap, sob a licença ODbL 1.0 (Open Database License). A
  própria instalação serve o arquivo por requisições de intervalo, sem serviço de tiles externo e sem
  chave de terceiro. A tela mostra escala, coordenadas do cursor e zoom de navegação.
- não prometer: Este passo mostra a base local. As camadas do catálogo sobre o mapa, a edição de
  feição e a imagem de satélite existem em itens próprios do painel, com estados diferentes, e não
  são percorridas neste passo.

## Passo 7 — Construtor de aplicação (5 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: O construtor monta uma aplicação por arrastar e soltar. A demonstração cria duas
  páginas por arrasto, uma com mapa em tela cheia e outra com painel lateral e grade. A aplicação
  resultante navega pelo menu. Ela guarda a página aberta na própria URL. Ela abre uma janela modal
  que fecha com a tecla Esc.
- não prometer: O construtor cobre páginas e layout, e está em construção. Os elementos de dado
  (L5-01-c), a publicação por link (L5-14) e os modelos prontos (L5-01-f) não estão entregues. O
  construtor é hoje a parte do produto com menos paridade com o ArcGIS Online.

## Passo 8 — Auditoria de acesso (2 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: Cada acesso à interface de programação fica registrado com usuário, caminho e código
  de resposta. O filtro por status seleciona, por exemplo, só as respostas da classe 2xx. A
  exportação devolve o recorte em CSV (valores separados por vírgula). A aba de eventos registra os
  acontecimentos do inquilino, como a entrada do usuário no passo 2.
- não prometer: O registro de acesso não substitui a trilha de auditoria completa. A trilha
  completa, com retenção e classificação de dados pessoais, ainda não existe.

## Passo 9 — Saúde da instalação (1 min)

- e2e: tests/e2e/test_demo.py
- o que dizer: A demonstração termina onde começou, na verificação de operação. A interface de
  programação responde em /saude com o estado do banco e a contagem de migrações aplicadas e
  pendentes. O código de resposta é 200 com o banco atualizado e 503 em caso contrário. É essa
  resposta que um monitor de máquina pode acompanhar.
- não prometer: A verificação de saúde é a observabilidade disponível hoje. Painéis de métrica,
  alertas e página pública de status ainda não existem.

## Passos que o roteiro não percorre

Os itens desta seção são pedidos frequentes em demonstração. Cada item traz o que dizer quando o
pedido acontecer. Os números exatos por linha de produto estão na lista gerada do painel, no fim do
documento.

- Dados de demonstração pré-carregados. Não entregue (L7-01-c e L0-13). Dizer que a plataforma vem
  vazia por escolha de instalação limpa. Dizer que a demonstração cria o conteúdo ao vivo. Dizer que
  uma carga de demonstração é um projeto à parte, não um recurso existente.
- Imagens de satélite, COG (Cloud Optimized GeoTIFF) e tiles de imagem. A ingestão de imagem
  (L1-01-ingest-raster) e o catálogo STAC por inquilino (L1-01-a) estão entregues. O serviço de
  ladrilho raster por token (L1-02-tiles-token) está refutado no painel. Dizer que a imagem entra,
  vira COG e aparece no catálogo. Não prometer publicação de ladrilho de imagem para cliente OGC
  (Open Geospatial Consortium) nesta versão.
- Edição no mapa e serviços OGC ou Esri-compatíveis. As ferramentas de geometria (L2-03-b) estão
  entregues; o item de edição transacional (L2-03-a) está parcial e o item L2-03-edicao está
  refutado. Os serviços compatíveis com FeatureServer e OGC API - Features (L2-04) estão parciais.
  Dizer que existe edição de feição e existe serviço, e que nenhum dos dois passou pelo adversário
  ainda.
- Motor multicritério com tela. O combinador (L3-01-e) e os conjuntos de pesos nomeados (L3-01-h)
  estão entregues, com tela própria em /amc/presets. A tela do motor (L3-01-g) está parcial. Dizer
  o que está medido e não apresentar a tela do motor como pronta.
- Traçado de rede elétrica. A linha L4 tem um item entregue (L4-27, curto-circuito e proteção) e
  oito parciais, entre eles parcelas, série temporal da rede e regras de atributo. As telas de
  traçado, isolamento, diagrama e fluxo existem no repositório. Dizer que a linha existe em parte e
  que o traçado ainda não passou pelo portão.
- Acervo da casa com tela. O registro de procedência (L6-01-a) e a verificação de frescor (L6-01-h)
  estão entregues. A tela do acervo existe em /acervo e o item L6-01-c está refutado no painel.
  Dizer que a tela existe e que o item ainda não foi aceito.
- Medição de uso por inquilino e exportação do inquilino. A medição para cobrança (L7-09) segue
  pendente. A exportação por inquilino (L0-06-d) está parcial e o item L7-25 segue pendente. Dizer
  que o limite técnico existe na fundação e que a medição para cobrança não existe.

## Versão de 10 minutos

Esta versão serve a uma audiência que não tem meia hora. Ela segue a mesma ordem, com os passos de
maior impacto. Os passos cortados ficam para uma segunda conversa. A lista do fim do documento
responde pelos ausentes.

- Passo 1 (1 min) — versão e saúde na primeira tela.
- Passo 2 (1 min) — entrada com inquilino e segundo fator.
- Passo 3 (3 min) — catálogo com item criado, busca, favorito e lixeira.
- Passo 6 (3 min) — mapa com base local, escala e coordenadas.
- Passo 8 (1 min) — auditoria de acesso com filtro e CSV.
- Passo 9 (1 min) — saúde da instalação na interface de programação.

<!-- gerado de laco/PAINEL.md:inicio -->
## O que a demonstração não faz ainda

Gerado de laco/PAINEL.md (seção Fronteira) em 2026-09-18. Não editar entre os marcadores: rode `venv/bin/python docs/gerar_demo.py --preencher` depois de regenerar o painel.

Uma linha por linha do produto. O que está `pendente` não existe na tela nem na máquina.

### L0 fundação

Deve fazer: repositório, identidade e acesso, catálogo por inquilino, ingestão de vetor, fila de trabalhos, cópia de segurança, administração da organização, SSO, metadado.

Não faz ainda (52 de 75 itens não entregues; pendentes 12): `L0-02-e-varredura-cruzada-rls`, `L0-02-tenant-auth`, `L0-03-e-compartilhamento`, `L0-03-f-tela-conteudo`, `L0-04-a-upload-arquivo`, `L0-04-b-inspecao`, `L0-04-c-tabela-camada`, `L0-04-d-formatos-base`, `L0-04-ingest-vetor`, `L0-04-k-rota-formatos-encoberta`, `L0-05-a-fila-postgres`, `L0-05-b-progresso-cancelamento`, `L0-10-eventos-historico`, `L0-11-arquivos-objetos`, `L0-12-contrato-api-e-limites`, `L0-13-dado-demonstracao`, `L0-14-identidade-visual`, `L0-03-h-lixeira-protecao-status`, `L0-03-j-transferencia-dono`, `L0-04-f-fgdb-parquet-fgb-gml`, `L0-04-g-atualizar-dados`, `L0-05-c-tela-tarefas`, `L0-05-e-justica-entre-inquilinos`, `L0-05-jobs`, `L0-06-c-restore-drill`, `L0-06-d-exportar-inquilino`, `L0-06-e-status`, `L0-07-a-configuracoes-org`, `L0-07-admin-org`, `L0-07-c-cotas-uso`, `L0-07-f-console-plataforma`, `L0-09-a-procedencia`, `L0-14-cli-admin`, `L0-15-marca`, `UX-29-org-lacunas-1609`, `L0-03-k-favoritos-notificacoes`, `L0-03-l-versoes-item`, `L0-04-j-camada-vista`, `L0-06-b-pitr-pgbackrest`, `L0-06-backup-status`, `L0-07-e-relatorios`, `L0-08-a-oidc`, `L0-08-b-saml`, `L0-08-e-mapeamento-provisionamento`, `L0-08-sso`, `L0-09-b-editor-iso-mgb`, `L0-09-c-xml-iso-validacao`, `L0-09-d-ogc-records-csw`, `L0-09-metadado-catalogo`, `L0-05-e-worker-em-container`, `L0-08-c-govbr`, `L0-08-d-ldap`.

### L1 imagens

Deve fazer: COG/STAC/tiles por inquilino, token de acesso, conectores Sentinel/NASA/Copernicus/MapBiomas, série temporal, IA na entrada.

Não faz ainda (62 de 66 itens não entregues; pendentes 49): `L1-01-b-validacao-e-isolamento-da-entrada`, `L1-01-c-conversao-cog-perfis-miniatura-estatisticas`, `L1-02-a-servico-titiler-por-inquilino`, `L1-02-b-token-de-servico-com-escopo-por-lista`, `L1-02-c-wmts-xyz-tilejson-validados`, `L1-02-d-cache-nginx-cdn-e-bancada-de-carga`, `L1-02-f-predefinicoes-de-renderizacao-e-legenda`, `L1-02-tiles-token`, `L1-03-a-quadro-de-conectores-e-tela-sensores`, `L1-03-b-sentinel-2`, `L1-07-mosaico-por-colecao-e-pegadas`, `L1-12-linguagem-de-expressao-de-banda`, `L1-01-e-upload-grande-retomavel`, `L1-01-f-formatos-de-entrada`, `L1-01-g-raster-categorico-colormap-e-tabela-de-atributos`, `L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo`, `L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro`, `L1-02-g-wms-1-3-0-raster`, `L1-02-h-ponto-estatisticas-e-histograma`, `L1-03-c-sentinel-1-sar`, `L1-03-conectores-sensores`, `L1-03-d-landsat`, `L1-03-e-mapbiomas`, `L1-03-f-cog-globais-por-vsicurl`, `L1-03-k-planetary-computer-e-stac-de-terceiros`, `L1-03-l-item-referenciado-sem-copia`, `L1-04-c-grafico-de-indice-por-poligono`, `L1-05-a-registro-de-modelo-e-proveniencia`, `L1-05-b-trabalhador-gpu-remoto`, `L1-08-regras-de-mosaico-e-selecao-de-pixel`, `L1-09-mascara-de-nuvem`, `L1-13-cadeia-de-funcoes-raster-ao-vivo`, `L1-14-analise-raster-em-lote-gera-item-novo`, `L1-15-estatistica-zonal`, `L1-16-derivados-de-terreno-e-terrain-rgb`, `L1-20-exportacao-recorte-e-massa`, `L1-23-cota-e-medicao-por-tb`, `L1-25-servico-de-imagem-esri-compativel`, `L1-27-ficha-de-metadado-e-licenca-da-imagem`, `L1-29-teste-no-arcgis-real-do-parceiro`, `L1-30-paridade-image-server-documento-vivo`, `UX-32-imagens-lacunas-1609`, `L1-01-h-ingestao-em-lote-por-manifesto-e-cli`, `L1-02-i-ogc-api-tiles-e-maps`, `L1-03-h-clima-nasa-power-e-copernicus-cds`, `L1-03-n-comerciais-com-chave-do-cliente`, `L1-03-p-drone-ortomosaico-e-fotos-brutas`, `L1-03-q-lidar-copc-mdt-mds`, `L1-04-a-controle-de-tempo-cortina-e-lado-a-lado`, `L1-04-e-diferenca-entre-datas-e-tendencia`, `L1-04-serie-temporal`, `L1-05-c-mudanca-s2-calibrada`, `L1-06-rasters-do-acervo-em-cog`, `L1-10-camada-congelada-pmtiles`, `L1-21-wcs-2-0-1`, `L1-24-imagens-orientadas`, `L1-05-d-camadas-leves-edificacoes-e-vegetacao-em-faixa`, `L1-05-e-pacote-de-modelo-importavel`, `L1-05-ia-na-entrada`, `L1-19-multidimensional-netcdf-zarr`, `L1-05-f-amostras-e-rotulos-para-treino`, `L1-18-pansharpening-e-ortorretificacao-rpc`.

### L2 plataforma

Deve fazer: mapa web, simbologia, edição, serviços Esri-compatíveis e OGC, geoprocessamento, painéis, campo, migração de AGOL, 3D, relações e regras, geocodificação e rota, impressão, versionamento e sincronização, tempo real, analítica grande, notebooks.

Não faz ainda (119 de 126 itens não entregues; pendentes 26): `L2-01-b-martin-tiles-vetoriais`, `L2-01-c-lista-camadas-legenda`, `L2-01-d-popup-runtime`, `L2-01-e-mapas-base`, `L2-01-g-tabela-atributos`, `L2-01-h-selecao-filtros`, `L2-02-a-modelo-estilo`, `L2-02-b-classificacao-servidor`, `L2-02-c-editor-simbologia-vetor`, `L2-02-d-rotulos`, `L2-02-simbologia`, `L2-03-a-api-edicao-transacional`, `L2-03-c-formulario-atributos-runtime`, `L2-03-edicao`, `L2-04-a-leitor-rls-martin`, `L2-04-b-featureserver-catalogo-metadados`, `L2-04-c-featureserver-query`, `L2-04-d-featureserver-edicao-anexos`, `L2-04-g-ogc-api-features-crs-cql2`, `L2-04-j-conformidade-clientes-e-paridade`, `L2-04-servicos-esri-ogc`, `L2-05-a-catalogo-ferramentas-gpserver`, `L2-05-b-vetor-basico`, `L2-05-c-sobreposicao-agregacao`, `L2-06-e-estatisticas-servidor`, `L2-10-a-dominios-subtipos`, `L2-10-c-linguagem-expressao`, `UX-00-mapa-de-cobertura-da-interface`, `UX-01-sistema-de-design`, `UX-02-telas-entrada-conta-convite`, `UX-03-tela-conteudo-item-lixeira`, `UX-04-tela-mapa-polimento`, `UX-09-telas-ferramentas-e-tarefas`, `L2-01-f-navegacao-medicao-coordenadas`, `L2-01-i-graficos-de-camada`, `L2-01-k-desenho-anotacoes`, `L2-01-l-exportacao-do-mapa`, `L2-02-e-simbolos-sprites-glifos`, `L2-02-f-estilo-raster`, `L2-03-d-historico-restauracao`, `L2-03-e-anexos`, `L2-03-f-edicao-em-lote-calculo-campo`, `L2-04-e-vector-tile-server-tilejson`, `L2-04-h-wfs-2-gml`, `L2-05-d-grades-densidade-padroes-interpolacao`, `L2-05-e-raster-basico`, `L2-05-f-rede-isocrona-rota-ferramentas`, `L2-05-geoprocessamento`, `L2-06-b-elementos-basicos`, `L2-06-c-acoes-seletores-filtros-cruzados`, `L2-06-d-atualizacao-viva-sse`, `L2-06-paineis`, `L2-07-a-pwa-instalavel-cache`, `L2-07-b-formulario-de-coleta-xlsform`, `L2-07-c-fila-sincronizacao-idempotente`, `L2-08-a-leitor-portal-inventario`, `L2-08-b-clonar-camadas-hospedadas`, `L2-08-c-converter-web-map-e-estilo`, `L2-08-d-relatorio-migracao-e-exportacao-reversa`, `L2-08-migracao-agol`, `L2-10-b-relacionamentos`, `L2-10-d-regras-de-atributo`, `L2-10-relacoes-regras`, `L2-11-a-geocodificacao-csv`, `L2-11-b-geocodificador-brasil`, `L2-11-c-rota-matriz-isocrona`, `L2-11-geocodificacao-rota`, `L2-12-a-motor-render-servidor`, `L2-17-crs-transformacoes`, `L2-19-paridade-l2-e-manual`, `UX-05-telas-conexoes-uploads-tarefas-compartilhado`, `UX-06-tela-administracao-inquilino`, `UX-10-acervo-sem-tela`, `UX-11-arquivos-sem-controle`, `UX-12-categorias-sem-controle`, `UX-13-conexoes-sem-controle`, `UX-14-geocodificador-sem-tela`, `UX-15-geocodificador-esri-sem-controle`, `UX-16-ingestao-sem-tela`, `UX-17-login-sem-controle`, `UX-18-plataforma-sem-tela`, `UX-19-rede-sem-tela`, `UX-20-usuarios-sem-controle`, `UX-21-multiescala-sem-tela`, `UX-22-ferramentas-esri-sem-tela`, `UX-23-mapa-sem-controle`, `UX-25-camadas-lacunas-1609`, `UX-30-dominios-lacunas-1609`, `UX-33-mapa-lacunas-1609`, `UX-34-diversos-lacunas-1609`, `L2-04-f-mapserver-identify-legend-geometryserver`, `L2-04-i-wms-wmts-sld`, `L2-04-k-sync-replicas-esri`, `L2-07-campo`, `L2-07-d-mapa-offline-por-area`, `L2-09-3d`, `L2-09-a-terreno-terrain-rgb-relevo`, `L2-09-b-cena-extrusao-slides`, `L2-09-c-modelos-gltf-ifc-3dtiles`, `L2-12-b-layouts-elementos-exportacao`, `L2-12-impressao-layout`, `L2-13-a-versoes-ramo-reconciliar`, `L2-13-b-replicas-sincronizacao`, `L2-13-versionamento-sync`, `L2-14-a-ingestao-de-fluxos`, `L2-14-b-camada-viva-historico`, `L2-14-c-regras-alertas-incidentes`, `L2-14-tempo-real`, `L2-15-a-geoparquet-bucket-catalogo`, `L2-15-analitica-grande`, `L2-15-b-consultas-duckdb-em-escala`, `L2-18-camada-de-consulta-sql`, `L2-07-e-odk-central-ponte`, `L2-09-d-analise-3d-visibilidade`, `L2-12-c-series-de-mapas-lote`, `L2-16-a-sdk-python-geo`, `L2-16-b-jupyter-por-inquilino-isolado`, `L2-16-c-script-vira-ferramenta`, `L2-16-notebooks-scripts`.

### L3 motor AMC

Deve fazer: motor multicritério explicável como serviço, com robustez medida.

Não faz ainda (29 de 37 itens não entregues; pendentes 11): `L3-01-a-modelo-dado`, `L3-01-b-unidades`, `L3-01-c-extracao-fator`, `L3-01-d-transformacoes`, `L3-01-f-explicacao`, `L3-01-g-tela-motor`, `L3-01-j-equivalencia-motor-logistico`, `L3-01-motor-servico`, `L3-01-c2-extracao-em-lote`, `L3-01-i-exportacao-metodo`, `L3-04-restricoes`, `L3-06-criterios-de-feicao`, `L3-12-integracao-fluxo-e-api`, `L3-13-resultado-como-camada`, `L3-18-paridade-esri-amc`, `UX-26-amc-lacunas-1609`, `UX-27-multiescala-lacunas-1609`, `L3-02-a-monte-carlo-pesos`, `L3-02-b-sensibilidade-sobol-oat`, `L3-02-d-comparacao-cenarios`, `L3-02-robustez`, `L3-03-ahp-pares`, `L3-05-localizar-regioes`, `L3-09-backtest-decisao-real`, `L3-10-corredor-custo-minimo`, `L3-11-fator-de-rede`, `L3-08-pareto`, `L3-17-similaridade`, `L3-20-narrativa-de-resultado`.

### L4 rede de utilidades

Deve fazer: modelo de rede, traçado, edição com regras, sub-redes e diagramas, conectores BDGD/CIM, estruturas e regras avançadas.

Não faz ainda (72 de 73 itens não entregues; pendentes 33): `L4-01-a-pacote-de-ativos`, `L4-01-b-topologia-derivada`, `L4-01-c-importador-bdgd`, `L4-01-f-alcance-do-tracado-rede-real`, `L4-01-g-tarefas-import-tardio`, `L4-01-modelo-rede`, `L4-02-a-conectado-e-subrede`, `L4-02-b-montante-jusante`, `L4-02-c-isolamento`, `L4-02-tracado`, `L4-03-a-regras-de-conectividade`, `L4-03-c-edicao-topologica-no-mapa`, `L4-03-d-areas-sujas-e-validacao`, `L4-04-a-controladores-e-tiers`, `L4-04-b-atualizar-e-exportar-subrede`, `L4-05-a-exportar-opendss`, `L4-07-fluxo-de-potencia`, `L4-08-queda-de-tensao-e-carregamento`, `L4-23-isolamento-por-inquilino-na-rede`, `UX-08-telas-rede-de-utilidades-e-motor`, `L4-01-d-atributos-de-rede`, `L4-02-d-lacos-e-caminho-curto`, `L4-02-e-configuracoes-de-tracado`, `L4-03-b-terminais`, `L4-03-e-versao-de-rede`, `L4-03-edicao-rede`, `L4-04-c-sumarios-por-subrede`, `L4-04-c-unificar-subrede`, `L4-04-d-diagrama-esquematico`, `L4-05-b-cim-iec-61970-61968`, `L4-05-c-pandapower-e-matpower`, `L4-05-d-epanet-inp`, `L4-05-f-transmissao-sindat-sigel`, `L4-06-a-contencao`, `L4-06-b-estrutura-postes`, `L4-06-d-categorias-e-restricoes`, `L4-09-perdas-tecnicas-por-segmento`, `L4-10-continuidade-dec-fec`, `L4-11-gd-conectada-e-hospedagem`, `L4-12-inspecao-vegetacao-na-faixa`, `L4-13-integracao-telemetria`, `L4-16-api-rest-compativel-un`, `L4-21-qualidade-e-saude-da-rede`, `L4-22-desempenho-em-escala`, `L4-24-cartografia-de-rede`, `UX-24-rede-lacunas-1609`, `UX-28-parcelas-lacunas-1609`, `L4-01-e-dicionario-unidades-bdgd`, `L4-01-h-alinhamento-inspire-gnm`, `L4-02-f-resultados-e-exportacao`, `L4-04-e-diagrama-camadas-e-contencao`, `L4-04-subredes-diagramas`, `L4-05-conectores-rede`, `L4-05-e-gas-e-esgoto`, `L4-05-g-osm-power`, `L4-05-h-inspire-utility-networks`, `L4-06-c-objetos-nao-espaciais`, `L4-06-estruturas-regras-avancadas`, `L4-14-balanco-de-energia-por-alimentador`, `L4-15-serie-temporal-da-rede`, `L4-17-migracao-de-un-e-rede-geometrica`, `L4-18-rede-simples-trace-network`, `L4-19-planejamento-de-linha-nova`, `L4-20-consumidores-e-enderecos`, `L4-25-cenarios-e-se`, `L4-26-inspecao-de-campo-do-ativo`, `L4-28-identificadores-e-numeracao`, `L4-29-regras-de-atributo-de-rede`, `L4-parcelas-01-modelo-de-parcelas`, `L4-parcelas-02-fluxos-cogo`, `L4-30-manual-e-tour-de-rede`, `L4-parcelas-03-ajuste-e-qualidade`.

### L5 builder

Deve fazer: construtores arrasta-e-solta de aplicação, fluxo, formulário e narrativa.

Não faz ainda (57 de 63 itens não entregues; pendentes 39): `L5-01-b-widgets-mapa`, `L5-01-c-widgets-dado`, `L5-01-e-acoes-configuraveis`, `L5-02-a-editor-de-nos`, `L5-02-b-execucao-proveniencia`, `L5-03-a-construtor-elementos`, `L5-03-b-logica-condicional-calculo-restricao`, `L5-06-motor-widgets`, `L5-07-fontes-vistas-mensagens`, `L5-11-expressoes-no-navegador`, `L5-14-publicacao-links-embed`, `L5-26-construtor-popup`, `UX-07-telas-do-construtor-e-aplicativo`, `L5-01-app-builder`, `L5-01-d-widgets-pagina-menu`, `L5-01-f-modelos-app-galeria`, `L5-02-c-agendamento-variaveis`, `L5-02-d-exportar-python-importar-json`, `L5-02-f-fluxo-como-ferramenta-e-api`, `L5-02-fluxos`, `L5-03-c-dominios-listas-cascata`, `L5-03-d-repeticoes-relacionadas-anexos`, `L5-03-e-xlsform-ida-e-volta-idiomas`, `L5-04-a-blocos-de-conteudo`, `L5-10-temas-marca`, `L5-17-painel-elementos-avancados`, `L5-18-painel-parametros-url-vistas`, `L5-20-sites-paginas-publicas`, `L5-21-dados-abertos-catalogo-publico`, `L5-23-apps-instantaneos-motor-galeria`, `L5-24-apps-instantaneos-modelos-1`, `L5-27-simbologia-por-arrasto`, `L5-29-construtor-relatorio-pdf`, `L5-31-construtor-de-camada-esquema`, `L5-33-a-diagrama-de-trabalho`, `L5-33-b-modelos-e-trabalhos`, `L5-39-paridade-l5-e-manual`, `UX-31-fluxos-lacunas-1609`, `L5-02-e-iteradores-condicionais`, `L5-03-form-builder`, `L5-04-b-imersivos-sidecar-tour-swipe`, `L5-04-c-temas-capa-colecao`, `L5-13-edicao-concorrente`, `L5-19-painel-expressoes-de-dado-tempo-real`, `L5-22-sites-dominio-proprio-tema`, `L5-25-apps-instantaneos-modelos-2`, `L5-28-galeria-simbolos-rampas-estilos`, `L5-30-relatorio-lote-agendado`, `L5-32-vistas-de-camada`, `L5-33-c-atribuicao-avancada-indicadores`, `L5-34-captura-rapida-designer-pwa`, `L5-36-widgets-personalizados-sdk`, `L5-37-pacotes-modelos-entre-inquilinos`, `L5-04-storymap`, `L5-16-agente-escreve-configuracao`, `L5-35-missao-operacao-ao-vivo`, `L5-38-importadores-configuracao-esri`.

### L6 conectores

Deve fazer: acervo da casa e conectores vivos.

Não faz ainda (28 de 32 itens não entregues; pendentes 4): `L6-01-a-registro`, `L6-01-b-view-so-leitura`, `L6-01-f-lgpd`, `L6-01-g-licenca-curada`, `L6-01-acervo-casa`, `L6-01-c-tela-acervo`, `L6-01-d-ficha-fonte`, `L6-01-e-assinatura-e-uso`, `L6-02-b-wms-wmts`, `L6-02-d-arcgis-rest-externo`, `L6-02-g-pmtiles-xyz-tilejson`, `L6-02-h-csv-url-geojson-kml`, `L6-02-k-agendamento`, `L6-02-m-catalogo-endpoints-brasil`, `L6-03-paridade-conectores`, `L6-04-acervo-no-motor`, `L6-01-i-raster-e-arquivos`, `L6-02-conectores-vivos`, `L6-02-e-stac-externo`, `L6-02-f-geoparquet-duckdb`, `L6-02-i-google-sheets`, `L6-02-j-bancos-externos`, `L6-02-l-saude`, `L6-02-n-etl-na-entrada`, `L6-02-o-importacao-exportacao-formatos`, `L6-05-proveniencia-camada-externa`, `L6-01-j-multi-servidor`, `L6-06-descoberta-csw`.

### L7 operação

Deve fazer: instalador limpo, carga, segurança, manual e tour, observabilidade, alta disponibilidade, SDK e webhooks, medição e cobrança, i18n e acessibilidade, appliance no cliente, LGPD, suporte, produção final.

Não faz ainda (81 de 82 itens não entregues; pendentes 46): `HARD-01-varredura-de-seguranca-continua`, `HARD-02-testes-de-carga-e-caos`, `HARD-03-adversario-por-linha-em-lote`, `L7-01-d-instalador-extensoes`, `L7-19-b-journal-sem-segredo`, `L7-31-a-segredos-trilha`, `L7-01-a-compose-perfis`, `L7-01-b-instalacao-conteiner-limpo`, `L7-01-instalador-limpo`, `L7-03-a-antivirus-upload`, `L7-03-b-rate-limit-abuso`, `L7-03-c-ssrf-conectores`, `L7-03-d-injecao-consulta`, `L7-03-e-cabecalhos-csp-tls`, `L7-03-f-dependencias-cve-log-correcoes`, `L7-03-seguranca`, `L7-06-a-metricas-exporters`, `L7-06-b-alertas`, `L7-06-c-logs-consulta-req-id`, `L7-06-observabilidade`, `L7-15-processo-release`, `L7-16-assinatura-pacote`, `L7-19-segredos-e-certificados`, `L7-31-ambiente-homologacao`, `L7-33-modo-somente-leitura`, `L7-34-saude-profunda`, `L7-35-atualizacao-versao-assinada`, `D21 (dono)`, `L7-01-c-dado-demonstracao`, `L7-02-a-k6-cenarios`, `L7-02-b-pool-e-limites-por-inquilino`, `L7-02-carga`, `L7-03-g-asvs-nivel2-pentest`, `L7-04-a-manual-capturas-geradas`, `L7-04-b-tour-primeiro-acesso`, `L7-04-c-manual-admin-runbooks`, `L7-04-manual-e-tour`, `L7-06-d-paineis`, `L7-07-a-replica-postgres`, `L7-07-alta-disponibilidade`, `L7-07-b-replica-garage`, `L7-07-c-ensaio-failover`, `L7-08-a-webhooks-eventos`, `L7-08-b-sdk-python`, `L7-08-c-sdk-js`, `L7-08-d-portal-api-chaves`, `L7-08-sdk-api-webhooks`, `L7-09-a-medidor-diario`, `L7-09-b-planos-limites-relatorio`, `L7-09-medicao-cobranca`, `L7-10-a-i18n-pt-en-es`, `L7-10-b-acessibilidade-wcag21aa`, `L7-10-i18n-acessibilidade`, `L7-12-a-classificacao-retencao`, `L7-12-b-registro-tratamento-dpa-incidente`, `L7-12-lgpd-governanca`, `L7-14-instalacoes-apt-desta-linha`, `L7-17-capacidade-planejamento`, `L7-18-custo-por-inquilino`, `L7-21-pagina-status`, `L7-22-sla-e-incidentes`, `L7-23-pgbackrest-pitr`, `L7-24-drill-restauracao`, `L7-25-exportacao-inquilino`, `L7-26-cdn-tiles`, `L7-27-origem-br-soberania`, `L7-29-roteiro-demonstracao`, `L7-30-teste-parceiro-pro-agol`, `L7-03-b-antivirus-anexos`, `L7-04-d-videos-por-tarefa`, `L7-05-producao-final`, `L7-11-a-appliance-licenca`, `L7-11-appliance-cliente`, `L7-11-b-appliance-sem-internet`, `L7-11-c-telemetria-opcional`, `L7-13-a-chamados`, `L7-13-c-laco-agentico-suporte`, `L7-13-suporte-chamados`, `L7-14-extensoes-fdw`, `L7-28-iso27001-controles`, `L7-32-postgres-manutencao-versao`.

<!-- gerado de laco/PAINEL.md:fim -->
