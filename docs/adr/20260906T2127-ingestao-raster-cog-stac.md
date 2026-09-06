# Ingestão de raster: validação isolada, COG em dois perfis, STAC no pgstac e nome por sha256

- Estado: aceito
- Data: 2026-09-06
- Item: L1-01-ingest-raster (base: L1-01-a, pgstac + STAC API por inquilino)

## Contexto

O portão do item exige a vertical inteira: upload pelo navegador vira job, o job produz COG validado
pelo rio-cogeo, o COG vai para o Garage, um item STAC nasce no pgstac, e a imagem aparece no Conteúdo
e no mapa do inquilino, com tempo e taxa de compressão registrados por job. A refutação exige três
entradas hostis (sem CRS, nodata errado, 16 bits), leitura do COG por Range (HTTP 206) e garantia de
que sobrescrever não corrompe (objeto nomeado pelo sha256 do conteúdo).

## Decisões

1. **Base sobre L1-01-a (ramo wt/pgstac, ebf12fc).** O pgstac já está instalado no banco (0.9.12) e a
   fundação Python/SQL (`app/imagens/pgstac.py`, `plat.raster_item`, privilégios) existe naquele ramo,
   ainda pendente no estado. Este item faz merge dele em vez de duplicar migrações. O vínculo
   catálogo ↔ STAC não ganha coluna nova: o `stac_id` do item STAC É o uuid do `plat.item`.

2. **Dois perfis de COG, declarados.** `visual` (JPEG quando o raster tem 1-3 bandas sem alfa, WEBP
   quando tem alfa ou 4 bandas; 8 bits escalados pelo percentil 2-98 calculado no BRUTO; nodata vira
   alfa no WEBP e é descartado no JPEG com fundo preto) e `cientifico` (ZSTD, dtype e nodata
   originais preservados, predictor 2 para inteiros e 3 para ponto flutuante). Os dois com BLOCKSIZE
   512, overviews internos por média (modo para raster categórico, quando detectado pela validação),
   NUM_THREADS=ALL_CPUS, BIGTIFF=IF_SAFER. JPEG não aceita 16 bits nem alfa; WEBP aceita alfa mas é
   8 bits — por isso o perfil científico existe: nenhum dado se perde. A escolha JPEG×WEBP é feita
   por regra escrita aqui, não por heurística escondida.

3. **Validação em subprocesso isolado antes de qualquer conversão.** `gdalinfo -json` roda via
   `ctx.subprocesso` (herda RLIMIT_DATA do worker, morre com o cancelamento) com
   `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` e sem `/vsicurl/`: o arquivo validado é sempre uma cópia
   local no diretório de trabalho do job. Regras:
   - **Sem CRS**: recusa com mensagem clara (`sem_crs`) indicando como reenviar declarando o EPSG
     (`epsg_declarado` no pedido, escrito no COG e registrado na proveniência como decisão humana);
   - **Nodata fora do intervalo do dtype** (ex.: -9999 em Byte, 65535 em UInt16 com valor máximo
     real menor): corrige reescrevendo o nodata no COG e registra `nodata_corrigido` na
     proveniência; nodata impossível de representar recusa com mensagem;
   - **16 bits**: importa certo — o científico preserva UInt16/Int16 e o visual escala;
   - **Dimensões/bandas acima do limite** (`PLAT_RASTER_*` em `app/limites.py`): recusa.

4. **Objeto por conteúdo (sha256), herdado de `app.objetos`.** O COG sobe para o bucket do inquilino
   pela mesma função `objetos.guardar` do resto da plataforma: a chave é
   `<slug>/raster/<item_id>/<sha256>.tif`; reenvio do mesmo conteúdo cai na mesma chave e não
   regrava; conteúdo novo ganha chave nova — sobrescrever um item nunca toca o objeto do anterior
   (refutação "sobrescrever não corrompe"). O bruto original permanece no objeto do upload.

5. **STAC no pgstac por ingestão, coleção fixa por inquilino.** A coleção de imagens do inquilino é
   `<tenant_id>-imagens`, criada sob demanda. O item carrega assets `visual`, `cientifico`, `bruto` e
   `miniatura` (URLs assinadas relativas), extensões `proj` (epsg, shape, transform), `raster`
   (estatísticas por banda), `file` (checksum sha256, tamanho) e `processing` (software e versões).
   `plat.raster_item` espelha autorização/estado (RLS), como em L1-01-a.

6. **Entrega por Range (206).** `GET /api/objetos/{chave}` ganha suporte a `Range: bytes=a-b`
   (206, `Accept-Ranges: bytes`): é o que torna o COG legível por `/vsicurl/` sem baixar o objeto
   inteiro, e é a prova pedida pela refutação. O handler de tiles usa exatamente esse caminho.

7. **Mapa com tiles servidos pela própria API, até L1-02.** `GET
   /api/imagens/{item_id}/tiles/{z}/{x}/{y}.png` abre o COG `visual` via rasterio sobre a URL
   assinada (leitura por Range), reprojeta a janela WebMercator e renderiza PNG de 256 px. É um
   mínimo honesto para "aparece no mapa": o TiTiler com chave RO por bucket é o item L1-02 e
   substitui este handler sem mudar o contrato da URL. O mapa abre um item raster por
   `/mapa?item=<uuid>`.

8. **Medida por job.** O resultado do job grava `duracao_s`, `bytes_bruto`, `bytes_visual`,
   `bytes_cientifico` e `taxa_compressao` (bytes dos dois COGs / bytes do bruto) em
   `plat.job.resultado` — é o "tempo e taxa de compressão registrados por job" do portão.

9. **ECW fora desta passagem.** O GDAL 3.8.4 do appliance não traz o driver ECW (proprietário). A
   hipótese dizia "ECW (se GDAL)"; a validação recusa ECW com mensagem clara (`formato_nao_suportado`
   nomeando o driver). JP2 entra pelo driver JP2OpenJPEG, presente.

## Consequências

- A vertical inteira roda dentro do worker atual; nenhum serviço novo.
- O handler de tiles é deliberadamente simples (sem cache): L1-02 o substitui.
- Upload continua sendo o fluxo retomável de L0-04-a; raster ganha os tipos `geotiff` e `jp2` no
  vocabulário de upload, com verificação por bytes (assinatura TIFF/BigTIFF e caixa JP2).
