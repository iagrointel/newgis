# L1 imagens — decisões de conceito

Data: 05/09/2026. Par de `L1.json` (60 itens: 10 filhos de L1-01, 9 de L1-02, 12 de L1-03, 3 de L1-04, 6 de L1-05,
o L1-06 proposto pela decomposição L3L6 e 19 itens novos L1-07 a L1-30). Tudo abaixo é o que, se estiver errado, obriga a
refazer: modelo de dado, identificadores, formato de arquivo, linguagem de expressão, modelo de job, contrato de URL,
armazenamento, CRS, versionamento, isolamento por inquilino e extensibilidade. Para cada decisão: opções, o que custa
mudar depois, recomendação com motivo MEDIDO nesta máquina (05/09/2026 ou na prova de 29-31/08), LIDO em código que roda
na casa (só leitura: `plataforma/pipeline/`, `geoapp/`, motor logístico, motor de LT, SIG de teste interno) ou DOCUMENTO
OFICIAL com URL testada por HTTP (lista completa em `L1.json`, campo `fontes_testadas_http_200_em_2026-09-05`), e o
que a decisão obriga nas outras linhas. Nenhum nome de cliente, parceiro ou piloto aparece aqui.

O que sustenta as escolhas, medido em 05/09/2026 nesta máquina e no GPU box:

- GDAL 3.8.4 do sistema com driver COG, JP2OpenJPEG, WEBP, netCDF/HDF/GRIB, Zarr, GeoPDF, WCS/WMS/WMTS e
  STACIT/STACTA; sem ECW nem MrSID. Ferramentas presentes: `gdaldem`, `gdal_contour`, `gdal_viewshed`,
  `gdal_pansharpen.py`, `gdal_polygonize.py`, `gdal_rasterize`, `gdal_calc.py`, `gdalmdimtranslate`, `gdal2tiles.py`.
- venv da prova do pipeline: titiler.core 2.2.0 (18 algoritmos de fábrica), rio-tiler 9.4.3 (211 colormaps),
  rio-cogeo 7.0.2, rasterio 1.5.0, morecantile 7.0.3, pystac 1.14.3, pystac-client 0.9.0, odc-stac 0.5.2,
  planetary-computer 1.0.0, xarray, numexpr 2.14.2, boto3. Ausentes na máquina inteira: pypgstac, titiler-pgstac,
  titiler.xarray, zarr, laspy, PDAL, untwine, exactextract, onnxruntime.
- PostgreSQL 16.13 + PostGIS 3.6.3 no `iagro_sat`, com `btree_gist` 1.7 (pré-requisito do pgstac); `postgis_raster`
  disponível e não usado; timescaledb 2.26.4 presente, mas fora do dado do cliente (TSL).
- Garage v2.3.0 ativo (S3 :3900, web :3902), balde de demonstração com cota; TiTiler da prova ativo (:8131); nginx
  com `proxy_cache` 3 GB/14 d, `proxy_cache_lock` e `slice 1m` para leitura por Range. Nada disso se toca; copia-se.
- Prova de 29/08: Sentinel-2 672 MB → 41,5 MB JPEG 75 (16,2:1) em 15,9 s; 4 bandas 16 bits ZSTD 1,1:1; ortofoto 10 cm
  300 MB → 29,7 MB em 1,8 s; tile frio 65-86 ms, quente 8,7 ms, CDN em acerto ≈ 40 ms; NDVI ao vivo custa o mesmo
  que RGB. Bancada de 31/08: 1.080 tiles/s por cliente quente sem degradar de 10 a 200 conexões; 20 pedidos ao mesmo
  tile frio = 1 falta + 19 acertos de cache.
- GPU box: RTX 4000 SFF Ada 20 GB, torch 2.5.1 com CUDA, disco a 100 % (16 GB livres), sem PDAL. Esta máquina:
  12 vCPU, 23 GB de RAM (3 GB disponíveis), `/` e `/mnt/pgdata` a 98 %.

---

## C1. Catálogo de imagens = pgstac, com espelho `plat.raster_item` para autorização

Opções: (a) tabela própria `plat.raster_item` com JSONB do STAC e busca por bbox/data feita à mão; (b) pgstac (schema
`pgstac`, partições por coleção e por tempo, busca CQL2, hash de busca para mosaico) e nada mais; (c) pgstac para o STAC
e uma tabela-espelho mínima com RLS para dizer "este item é deste inquilino e está neste estado".

Custo de mudar depois: alto. O mosaico (L1-07) é uma busca registrada no pgstac; a STAC API que o ArcGIS Pro (desde 3.2)
e o QGIS (desde 3.40) consomem é o stac-fastapi-pgstac; trocar o catálogo depois invalida os ids de mosaico gravados em
web maps de clientes e obriga a reescrever a busca.

Recomendação: (c). Motivo DOCUMENTO OFICIAL: o pgstac é o catálogo do Planetary Computer e do eoAPI, e o titiler-pgstac
só funciona sobre ele (`stac-utils.github.io/titiler-pgstac`); requer PostgreSQL ≥ 13, PostGIS ≥ 3 e `btree_gist`
(MEDIDO: presentes). Motivo LIDO: a prova de 29/08 usou STAC estático por falta de disco e registrou que o Pro e o QGIS
pedem STAC API para filtrar, não catálogo estático. O pgstac não tem RLS nem noção de inquilino; por isso o espelho:
`plat.raster_item(tenant_id, item_id, colecao, perfil, sha256, bytes, estado, origem, licenca, criado_em)` com RLS igual
ao resto do schema `plat`, e a regra de que TODA leitura e escrita do pgstac passa pela API da casa, que filtra pela lista
de coleções do inquilino. Roles do pgstac usadas: `pgstac_read` para o TiTiler e a API, `pgstac_ingest` para o worker;
`pgstac_admin` só para migração.

Obriga: L0-03 cria o tipo de item `raster` apontando para `plat.raster_item`; L0-06 inclui o schema `pgstac` no backup e
o manifesto dos objetos; L7-03 trata `pypgstac migrate` como migração versionada em `db/migrar.sh`; o adversário de
qualquer item L1 testa o cruzamento de inquilino nos endpoints do stac-fastapi, não só nos da casa.

## C2. Identidade e imutabilidade: item = STAC id estável; objeto = nome por conteúdo; versão = item novo

Opções: (a) objeto no balde nomeado pelo nome do arquivo enviado e sobrescrito a cada reingestão; (b) objeto nomeado por
sha256 do conteúdo (`<item_id>/<asset>_<sha8>.tif`), nunca sobrescrito; (c) (b) mais um id de item ULID gerado pela casa
e um `title` livre do usuário.

Custo de mudar depois: alto. URLs de tile e de COG entram em web maps de terceiros e ficam lá por anos; o cache VSI do
GDAL dentro do TiTiler, o cache do nginx e a CDN guardam deslocamentos e tiles pelo nome do objeto.

Recomendação: (c). Motivo MEDIDO (29/08): sobrescrever o mesmo nome com conteúdo diferente deixou o TiTiler em 500 (`Read
failed`) e a CDN com tile velho; o `ingest.py` passou a nomear por sha e a acrescentar `&v=<sha8>` na URL, e o problema
não voltou. Item id = ULID (ordenável no tempo, sem colisão, sem vazar contagem); `title` é só rótulo. Nova versão de uma
imagem = item novo com extensão STAC `version` (`deprecated: true` no antigo e link `predecessor-version`), nunca troca
de asset no item existente. Exclusão = estado `excluido` + lixeira de 7 dias (L1-01-i).

Obriga: L0-03 nunca renomeia o id do item, só o título; L5-05 versiona predefinições de renderização (documentos), não
imagens; L7-09 conta bytes por objeto, e um mesmo sha enviado duas vezes ocupa uma vez.

## C3. Formato canônico: COG em três perfis; JPEG só para RGB; WEBP só atrás do nosso servidor; sem LERC

Opções: (a) guardar o original e converter na leitura; (b) COG único por item, um perfil só; (c) COG em perfis
declarados: `visual` (Byte, 3 bandas, JPEG 75), `cientifico` (tipo original, ZSTD 9, predictor 2) e `categorico` (ZSTD,
overview NEAREST, colormap e tabela de atributos preservados).

Custo de mudar depois: alto. Reconverter todo o acervo custa CPU e disco (disco a 98 %), e o preço por TB (spec 17.3)
distingue "ver" de "analisar" pela existência do perfil científico.

Recomendação: (c). Motivo MEDIDO (relatório 03 e prova 09): RGB 34 cm JPEG 75 = 1,2 MB/km² e 19,9:1; WEBP 75 = 35,8:1
mas a Esri não enumera WEBP entre as compressões de COG lidas (doc de formatos do Pro, URL testada) — logo WEBP só sai
do nosso TiTiler como formato de tile, nunca como arquivo entregue ao ArcGIS; 16 bits comprime 1,3-1,6:1 (ZSTD ganha de
DEFLATE e LZW com tempo igual); JPEG converte para YCbCr 4:2:2 e destrói banda que não é cor (doc GDAL) — nunca em
NIR/térmico/índice; overview AVERAGE em raster de classes mistura classes, por isso NEAREST no perfil categórico. LERC
fica fora até teste no Pro real (D20): o ganho medido é pequeno (1,4:1 → 1,6:1 com erro 1 DN) e a compatibilidade não
está documentada. `TILING_SCHEME=GoogleMapsCompatible` é opção do perfil `visual` (elimina a reprojeção por tile) e
proibida no `cientifico` (reamostra o dado). Bloco 512, overviews internos, `BIGTIFF=IF_SAFER`, `rio-cogeo validate`
como portão. Formatos de entrada são os do GDAL do sistema; ECW e MrSID são recusados com mensagem (MEDIDO: sem SDK).

Obriga: L1-02-f só oferece formatos de tile PNG/JPEG/WEBP; L1-20 exporta em GeoTIFF/COG com a compressão pedida; L1-06
converte o acervo da casa nesses perfis; L7-09 cobra o perfil científico como "analisar".

## C4. CRS: guarda-se o nativo, serve-se só WebMercatorQuad, exporta-se em qualquer EPSG, área em geodésico

Opções: (a) reprojetar tudo para EPSG:3857 na ingestão; (b) reprojetar tudo para SIRGAS 2000 (4674) ou UTM; (c) guardar
o CRS nativo (`proj:epsg` ou `proj:wkt2`), servir tiles só em WebMercatorQuad e reprojetar na exportação.

Custo de mudar depois: alto para (a) e (b) (perda irreversível por reamostragem); baixo para (c).

Recomendação: (c). Motivo DOCUMENTO OFICIAL: o AGOL/Portal exige Web Mercator (Auxiliary Sphere) e HTTPS para tile layer
externa e casa o WMTS com o esquema do basemap; o Pro lê qualquer CRS por `.acs`/WCS. Motivo MEDIDO: com um só
TileMatrixSet o WMTS cai de 191 KB/655 ms para 18 KB/143 ms. Regras escritas: SIRGAS 2000 e WGS 84 são tratados como
coincidentes (sem transformação de datum, diferença submétrica declarada na ficha); reamostragem NEAREST obrigatória em
categórico e declarada (bilinear/cúbica) em contínuo; declividade de MDT em graus exige reprojeção métrica ou fator de
escala (portão do L1-16); área e comprimento de resultado sempre geodésicos; terrain-RGB gerado do MDT nativo e nunca de
tile já codificado (regra da casa).

Obriga: L2-01 assume WebMercatorQuad; L2-05/L3-01-c declaram o CRS de cálculo de cada extração; L1-25 (ImageServer
compatível) aceita `imageSR` 3857 e 4326 e recusa o resto com erro no formato Esri.

## C5. Servidor de tiles = TiTiler + titiler-pgstac em Python, atrás do nginx; Rust só em Garage e Martin

Opções: (a) servidor próprio em Rust; (b) GeoServer/MapServer; (c) TiTiler (rio-tiler/GDAL) com titiler-pgstac.

Custo de mudar depois: médio; o contrato de URL (C6) esconde o servidor, mas expressões, algoritmos e mosaicos são
específicos do rio-tiler.

Recomendação: (c). Motivo MEDIDO: 36-56 ms por tile in-process, inclusive NDVI; o gargalo é E/S do balde e codificação
de imagem (C), não Python; a CDN e o cache nginx fazem o resto (1.080 tiles/s quente). Motivo DOCUMENTO OFICIAL: Martin
marca COG como instável, sem JPEG/WEBP/ZSTD e sem EPSG:3857; não existe servidor COG maduro em Rust (relatório 03 §3.4).
GeoServer tem WCS/SLD e COG só como módulo comunitário (doc testada); entra só se um edital exigir SLD, e aí como
fachada, não como armazenamento. Unidade `plat-titiler` :8152, 4 workers, `path_dependency` que aceita apenas `item_id`
resolvido no banco do inquilino (anti-SSRF, LIDO em `pipeline/app.py`), `Server-Timing` em toda resposta.

Obriga: L7-06 mede tempo por tile e taxa de acerto do cache; L7-01 instala `plat-titiler` pelo mesmo `install.sh`;
L2-01 consome TileJSON.

## C6. Contrato de URL: token longo no caminho, revogável, validado antes do cache

Opções: (a) URL assinada que expira em minutos; (b) token como parâmetro de consulta; (c) token longo no caminho
`/svc/<token>/raster/<item>/{z}/{x}/{y}.png`, `/svc/<token>/mosaico/<busca>/…`, `/svc/<token>/cog/<item>/<asset>.tif`,
`/svc/<token>/stac/`, `/svc/<token>/rest/services/<item>/ImageServer`.

Custo de mudar depois: muito alto. A URL fica gravada no web map do cliente por tempo indefinido.

Recomendação: (c). Motivo DOCUMENTO OFICIAL (doc Esri lida 29/08, URLs testadas): o AGOL só guarda credencial de serviço
ArcGIS; "OGC WCS, WFS, WMS, and WMTS services secured with token-based authentication are not supported"; o que aceita é
a URL com o token embutido ou parâmetro custom. Motivo LIDO: é o padrão `/svc/<tok>/` do SIG de teste interno, que o AGOL
e o Pro já carregaram. Regras: token = registro em `plat.token_servico` com escopo em LISTA (itens, coleções, mosaicos;
pedido do L5-14), Referer e CIDR opcionais, validade opcional, revogação imediata, log por leitura (hash do token, nunca
o token); validação por `auth_request` do nginx ANTES do `proxy_cache`, com resposta em cache local de 5 s, para que
revogação valha em ≤ 5 s mesmo com tile em cache; chave de cache SEM o token (item + z/x/y + parâmetros de renderização),
para que tokens diferentes compartilhem tile. URL assinada curta (24 h) só para arquivo de exportação (L1-20).

Obriga: L0-02 dá a coluna de escopo em lista e o endpoint de validação rápido; L5-14 usa o mesmo token para app
publicada; L7-09 lê o log de leitura por token; L7-03 audita que o log não guarda o token em claro.

## C7. Linguagem de expressão = a do rio-tiler (numexpr) com bandas por nome comum e gramática publicada

Opções: (a) Arcade (proprietária, sem interpretador aberto); (b) linguagem própria; (c) expressão do rio-tiler avaliada
por numexpr, com aliases de banda resolvidos por `eo:bands` e gramática EBNF publicada com vetores de teste.

Custo de mudar depois: alto. A expressão fica gravada em predefinições de renderização, URLs de WMTS, itens derivados
(proveniência) e nós de fluxo.

Recomendação: (c). Motivo MEDIDO: NDVI por `expression` custa +2 ms por tile; o `+` precisa ir codificado (`%2B`), erro
já pago. Motivo DOCUMENTO OFICIAL: numexpr restringe a aritmética e funções matemáticas (sem chamada arbitrária), o que
é a base do sandbox; a Esri chama o equivalente de Band Arithmetic/NDVI raster function (URLs testadas). Regra da casa
já adotada pelo L2-10 para a linguagem de atributos: gramática publicada e vetores compartilhados com o front, para que
JS e Python concordem. Catálogo de índices de fábrica gerado do mesmo JSON.

Obriga: L2-02 mostra a expressão no editor raster; L5-02 usa a expressão como parâmetro de nó; L1-25 traduz o
`renderingRule` da Esri para expressão da casa só para as funções listadas.

## C8. Predefinição de renderização = documento JSON v1 com JSON Schema, versionado; a legenda sai dele

Opções: (a) parâmetros soltos na query string; (b) estilo MapLibre puro (não tem stretch, colormap por valor nem
expressão); (c) documento próprio v1 (bandas, expressão, rescale, colormap, nodata, resampling, cadeia de funções,
opacidade) validado por JSON Schema, gravado por item ou por mapa em `plat.item_versao` (modelo do L5-05) e serializado
de forma determinística para a URL.

Custo de mudar depois: alto. É o que o L2-02 edita, o que a URL WMTS carrega, o que a legenda desenha e o que o
ImageServer compatível traduz.

Recomendação: (c). Motivo DOCUMENTO OFICIAL: é o papel do "raster function template" de exibição do Image Server e do
"processing template" das imagery layers (URLs testadas); a extensão STAC `render` guarda o mesmo conteúdo no item.
Motivo LIDO: o L5-05 já decidiu o envelope de documento versionado; reaproveita-se. Determinismo da serialização é portão
(mesma predefinição → mesma query string → mesmo tile em cache).

Obriga: L2-02 edita esse documento em vez de formato próprio, com ColorBrewer mapeado para os nomes do rio-tiler; L5-05
aceita o tipo `renderizacao`; L1-25 mapeia `renderingRule` ↔ predefinição.

## C9. Mosaico = busca STAC registrada (id = hash da busca) + regras declaradas; sem seamline

Opções: (a) mosaico físico (COG único gerado por job); (b) MosaicJSON estático; (c) busca registrada no pgstac
(titiler-pgstac `searches/register`) com `sortby`, filtro CQL2 e `pixel_selection`.

Custo de mudar depois: alto. O id do mosaico entra na URL do web map.

Recomendação: (c) para o dinâmico, (a) como derivado opcional (L1-14 "mosaico para novo raster") e (b) nunca. Motivo
DOCUMENTO OFICIAL: o hash de busca é estável e o titiler-pgstac expõe WMTS/TileJSON por busca; os métodos de mosaico da
Esri (None, Closest to Center, By Attribute, Lock Raster, Northwest, Seamline, Closest to Viewpoint) mapeiam para
`sortby` + `pixel_selection` + travar cena, e Seamline/Closest to Viewpoint ficam FORA com motivo (não há linha de costura
nem ponto de vista numa busca). "Mais recente sem nuvem" = ordem por data desc + máscara por pixel (C10) + `first`. Custo
por tile cresce com o nº de cenas candidatas; limite por tile declarado e medido para N = 1, 3, 6, 12.

Obriga: L1-25 traduz `mosaicRule` só para esses métodos; L1-04-a lê as datas do STAC; L6-01-i expõe mosaicos do acervo
com o mesmo mecanismo.

## C10. Nuvem é dado de primeira classe: máscara por pixel como asset, fração por polígono calculada, nunca só o número da cena

Opções: (a) usar `eo:cloud_cover` da cena; (b) máscara por pixel (SCL do Sentinel-2, `qa_pixel` do Landsat, modelo leve
quando não há) como asset `mascara` do item, com a fração de nuvem calculada dentro do polígono do usuário.

Custo de mudar depois: médio; séries e mosaicos já gerados sem máscara precisam ser refeitos.

Recomendação: (b). Motivo LIDO: a série anual por lote do motor logístico e o estudo de lote vazio da casa só ficaram
defensáveis com janela seca e cenas de nuvem 0-7,8 % medidas por lote, não por cena; o `geoapp` (`/api/series`) já aplica
a mesma ideia. Motivo DOCUMENTO OFICIAL: SCL classes 3, 8, 9, 10, 11 (sombra, nuvem média/alta, cirro, neve). Modelos
leves (s2cloudless, omnicloudmask) só com taxa de erro medida e escrita na ficha.

Obriga: L1-04-c marca datas nubladas em vez de omiti-las; L1-08 usa a máscara antes de `first`; L1-05-c nunca compara
pixel sob nuvem.

## C11. Tempo: só `datetime`/`start_datetime`/`end_datetime` do STAC; sem tabela de tempo própria

Opções: (a) tabela `plat.raster_tempo` paralela; (b) o tempo é a propriedade STAC e a coleção é a série.

Custo de mudar depois: médio.

Recomendação: (b). Motivo DOCUMENTO OFICIAL: `datetime` é obrigatório no item STAC (ou o par start/end), o pgstac
particiona por ele e o Time slider do Portal lê datas da camada (URLs testadas). Motivo de refutação: a data mostrada
tem de ser a da aquisição, nunca a do upload (o adversário do L1-04 confere isso).

Obriga: L1-01-b exige a data na entrada (ou pede); L1-19 fatia cubos em itens por tempo até 1.000 fatias; L5-25
("imagens no tempo") lê as mesmas datas.

## C12. Origem do item: `copiado` (ocupa cota) ou `referenciado` (host de terceiros em lista fechada)

Opções: (a) copiar tudo para o balde; (b) referenciar tudo; (c) os dois estados, declarados no item, com lista de hosts
permitidos por conector e materialização sob demanda.

Custo de mudar depois: médio; afeta cota, latência e o que a ficha promete.

Recomendação: (c). Motivo MEDIDO: leitura por `/vsicurl` de COG remoto funciona (Element84, GCS, AWS `--no-sign-request`)
e a latência de tile referenciado é maior que a de copiado (a medir e escrever na ficha do conector). Motivo LIDO: o
`acervo.endpoint` da casa registra frescor e última verificação HTTP por endereço; o item referenciado herda a regra
("a fonte pode sumir; última verificação em …"). Lista de hosts conferida na LEITURA, não só na criação (o adversário
edita o href no pgstac e espera 400).

Obriga: L6-02-e usa o mesmo mecanismo com URL do usuário e a mesma lista de bloqueio de hosts internos; L7-09 não cobra
bytes de item referenciado; L1-20 materializa antes de exportar em massa.

## C13. Armazenamento: balde por inquilino no Garage, chave só-leitura por inquilino, escrita só pelo worker, endpoint S3 para o Pro

Opções: (a) um balde só com prefixo por inquilino; (b) balde por inquilino com chave e cota próprias.

Custo de mudar depois: alto (mover objetos entre baldes com disco a 98 %).

Recomendação: (b). Motivo DOCUMENTO OFICIAL: Garage dá chave × balde × cota e administração por API (URLs testadas);
o `Create Cloud Storage Connection File` do Pro aceita endpoint S3 compatível com provedor MinIO/Amazon, e a Esri
escreve que não testa nem garante S3 compatíveis (risco declarado, teste em D20). Motivo MEDIDO: Garage estável na prova
com centenas de leituras por Range; nginx `slice 1m` + `proxy_cache` cacheia fatias de COG. Sem `postgis_raster` para
imagem: o disco do banco é o mais caro e o COG no balde é o que o Pro/QGIS leem direto.

Obriga: L0-06 faz dump por inquilino = STAC + manifesto de objetos; L7-07 replica o Garage na 2ª máquina; L7-11
(appliance) leva o balde junto.

## C14. Modelo de job: fila Postgres do L0-05 com filas `cpu`, `gpu`, `rede`; GPU box é worker remoto da mesma fila

Opções: (a) chamada síncrona ao GPU box por HTTP; (b) fila separada no GPU box; (c) mesma fila Postgres, worker remoto
por túnel SSH, 1 job de GPU por vez.

Custo de mudar depois: médio.

Recomendação: (c). Motivo MEDIDO: GPU box com RTX 4000 20 GB e CUDA disponível, disco a 100 % (16 GB livres), o que
obriga a checar `df`/`free` antes de aceitar job e a limpar a saída; a regra da casa é 1 job pesado por vez. Motivo
LIDO: o L0-05 já decidiu Postgres como fila; acrescentam-se só nomes de fila, sub-passos e cancelamento cooperativo
(pedido registrado). Toda análise que materializa resultado (L1-14 a L1-19, L1-05) é job e produz item NOVO com
proveniência; nada roda síncrono acima do limite declarado (recorte ≤ 50 MB, polígono ≤ área declarada).

Obriga: L0-05 aceita worker em outra máquina; L7-06 mostra a fila `gpu`; L7-03 audita a chave SSH com comando forçado.

## C15. Proveniência = extensões STAC `file`, `processing`, `mlm` + bloco `plat:cadeia` com hash canônico e reexecução

Opções: (a) só `file:checksum`; (b) proveniência completa: multihash do COG e do bruto, software e versões, comando,
sha das entradas, hash canônico do item, comando de reexecução e verificação.

Custo de mudar depois: alto (é a tese Lastro da casa aplicada à imagem; itens sem cadeia não são auditáveis).

Recomendação: (b). Motivo LIDO: o motor de LT tem manifesto com commit e sha256 e a regra "ausência de dado nunca vira
medição"; o registro único do acervo mostrou que reprodutível de verdade (script + sha256) é 8 % das fontes — o L1 nasce
com 100 %. Motivo DOCUMENTO OFICIAL: extensões `file`, `processing`, `mlm`, `version` (URLs testadas). Modelo de IA sem
controle negativo medido fica `experimental` e invisível ao inquilino (regra de 19/08: detector reprovado no controle
negativo).

Obriga: L3-13 grava o resultado do motor multicritério com o mesmo bloco; L1-30 e o adversário recomputam hashes com
script próprio; L7-12 cita a cadeia como evidência de LGPD/auditoria.

## C16. Isolamento por inquilino no L1: cinco fronteiras testadas em toda entrega

Fronteiras: (1) pgstac por prefixo de coleção + espelho com RLS (C1); (2) balde e chave por inquilino (C13); (3) token de
serviço com escopo em lista (C6); (4) worker com token de escopo mínimo por job (C14); (5) cache nginx com chave por
item, nunca por token. Custo de mudar depois: muito alto; recomendação: cada item L1 tem cláusula de teste cruzado A→B e o
adversário sempre tenta o cruzamento pelos endpoints do stac-fastapi e do TiTiler, não só pelos da casa.

## C17. Extensibilidade: conector = classe com contrato; função raster = `BaseAlgorithm`; formato = GDAL; modelo = manifesto aberto

Opções: (a) código por caso; (b) registros com contrato fixo e JSON Schema.

Custo de mudar depois: médio.

Recomendação: (b). Conector (`ficha/testar/buscar/recortar/propriedades_stac`) registrado em `app/conectores/registro.py`,
LIDO no padrão do `geoapp` (`_clip_global`, `_pc_clip`) e nas armadilhas já pagas (`ReadRaster` + `np.frombuffer`,
`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, SoilGrids em Homolosine, GHSL em Mollweide, hosts sem Range). Função raster =
subclasse de `BaseAlgorithm` do TiTiler com JSON Schema de parâmetros (DOCUMENTO OFICIAL: guia de algoritmos). Modelo de
IA importado = ONNX + manifesto JSON com schema publicado (equivalente aberto do `.emd/.dlpk`). Licença é campo
obrigatório do contrato do conector: sem URL de licença o conector não carrega; fontes NC (FABDEM, GEM full-layers)
ficam fora por regra do catálogo da casa.

Obriga: L5-02 lê o registro de ferramentas para montar nós; L6-02 reusa o conector genérico; L7-08 expõe os JSON Schemas
no portal de API.

## C18. Compatibilidade com o ArcGIS: quatro portas, cada uma com o que é e o que não é

Portas: (1) XYZ/WMTS/WMS para "ver" no AGOL/Portal/Pro (sem instalar nada; HTTPS, Web Mercator, CORS para `*.arcgis.com`);
(2) STAC API + endpoint S3 (`.acs`) + WCS para "analisar" no Pro; (3) ImageServer REST compatível (subconjunto: info,
exportImage, identify, tile, legend, computeStatisticsHistograms, rasterAttributeTable, query de pegadas) para o único
caso em que o AGOL guarda credencial e o Pro trata como Imagery layer; (4) PMTiles e COG por URL NUNCA prometidos ao
ArcGIS (doc lida: não há suporte). Custo de mudar depois: alto na porta 3 (formato de resposta da Esri). Recomendação:
construir 1 e 2 primeiro, 3 como PARCIAL declarado operação a operação, e nada é marcado "testado em Pro/AGOL" sem o JSON
de resultado do parceiro (D20; item L1-29). Motivo DOCUMENTO OFICIAL: tabela A1/A2 do relatório 04 (URLs testadas hoje).

Obriga: L2-04 mantém o mesmo padrão de erro JSON da Esri; L7-04 (manual) publica o roteiro de colagem; `docs/PARIDADE.md`
é gerado de JSON (L1-30), nunca escrito à mão.

## C19. Nuvem de pontos e multidimensional: fora do banco, no balde, em formato otimizado para nuvem

Nuvem de pontos: COPC (LAZ 1.4 com octree; DOCUMENTO OFICIAL copc.io, PDAL `writers.copc`) no balde, servido por Range;
MDT/MDS/altura derivados como COG (L1-16); nada de `pointcloud` no Postgres. Requer instalar PDAL ou untwine (ausentes;
apt/sudo = decisão registrada). Multidimensional: modo "fatiar" (um item por tempo/nível, até 1.000) como padrão e modo
"cubo" (Zarr + `datacube` + titiler.xarray) como fase 2, porque `zarr` e `titiler.xarray` não estão instalados e o GDAL
3.8 lê/escreve Zarr mas o disco não permite duplicar cubos hoje. Custo de mudar depois: baixo (fatiar → cubo é conversão).

Obriga: L2-09 escolhe o leitor de COPC no navegador; L1-03-h (CDS) usa o modo fatiar; D21 (disco) antes de qualquer cubo.

## C20. Medição por TB: bytes por perfil lidos do balde, tiles e saída lidos do log, "analisar" medido pela existência do perfil científico

Opções: (a) contar por item o que o usuário declarou; (b) medir no balde (API de administração do Garage) e no log
`plat.log_svc`, por dia, em `plat.uso_raster` particionada por mês, conferindo contagem direta em teste.

Custo de mudar depois: alto (é a fatura).

Recomendação: (b). Motivo DOCUMENTO OFICIAL: a Esri cobra imagem tilada a 1,2 crédito/GB/mês e a contagem diária de cenas
de coleção dinâmica; aqui a unidade é byte armazenado por perfil + tile servido + byte de saída + segundo de CPU/GPU, sem
crédito. Motivo LIDO: spec 17.3 diferencia "ver" e "analisar" (+50 %); a diferença é medida pela presença do asset
`cientifico`, não declarada. Item referenciado não conta bytes; o mesmo sha conta uma vez.

Obriga: L7-09 consome `plat.uso_raster`; L0-07 mostra a cota na tela do administrador; L1-01-i faz a cota cair na
exclusão.

---

## O que fica declarado FORA da linha L1 (e por quê)

- Ortomapeamento completo (aerotriangulação, ajuste de bloco, edição de linha de costura) e Drone2Map/Reality Mapping:
  só o produto pronto entra (L1-03-p) e o OpenDroneMap roda como job no GPU box com limites; nada de ajuste interativo.
- Métodos de mosaico Seamline e Closest to Viewpoint; correção de cor entre cenas (color correction) além de stretch por
  cena.
- Treino de modelo dentro do produto (L1-05-f exporta amostras; o treino só entra quando um modelo passar em controle
  negativo).
- Pixel editor, estéreo, análise em espaço de imagem, vídeo/motion imagery.
- Tarifa de análise de raster por pixel (a Esri não publica; nunca inflar a conta do outro lado).
- Qualquer promessa de PMTiles ou COG por URL dentro do ArcGIS.

## Decisões que exigem o dono (registrar em `decisoes_do_dono`)

- D20 (já aberta): credencial/tempo do parceiro para testar XYZ, WMTS, STAC Connection, `.acs`, WMS, WCS e o ImageServer
  compatível em Pro/AGOL reais; até lá toda paridade da linha fica "pendente".
- D21 (já aberta): disco a 98 % nas duas máquinas e 100 % no GPU box; a linha converte por partes e recusa job sem espaço.
- Nova: chave de teste de fornecedor comercial (PlanetScope/SkyFi/Maxar) para o L1-03-n; até lá o item fecha só a parte
  "sem chave".
- Nova: instalações que exigem apt/sudo — PDAL/untwine (L1-03-q), onnxruntime-gpu e Docker do OpenDroneMap no GPU box
  (L1-05-e, L1-03-p). As instalações por `pip` na venv (pypgstac, titiler-pgstac, psycopg[binary,pool], numexpr,
  exactextract, zarr, titiler.xarray) não exigem decisão, só `df` antes.
- Nova: licença ZSTD/LERC no Pro — padronizar ZSTD no perfil científico depende do teste real; se falhar, DEFLATE
  predictor 2 (reconversão do científico, custo de CPU e disco).
