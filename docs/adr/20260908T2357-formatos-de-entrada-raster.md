# Formatos de entrada do raster: tabela única testada, contêiner zip e o cadeado de sidecar que cede

- Estado: aceito
- Data: 2026-09-08
- Item: L1-01-f-formatos-de-entrada

## Contexto

O job de ingestão (`imagens.ingestar`, itens L1-01-b a L1-01-i) aceitava o que o GDAL abrisse, sem
contrato nomeado com o usuário: a tela de upload não podia dizer quais formatos entram, o zip de
várias cenas virava "1 raster" sem identidade de mosaico, e nada provava que cada formato prometido
realmente vira COG válido no fim. O portão do item pede a lista fechada e testada (cada formato com
arquivo aberto em `tests/dados/raster/` que importa e vira COG), recusa de ECW/MrSID com a mensagem
que explica a ausência do SDK proprietário, zip de 4 cenas virando 1 item mosaicado, zip com CRS
diferentes recusando dizendo quais, e a tela lendo a MESMA tabela do código.

## Decisões

1. **Uma tabela, dois consumidores: `app.imagens.formatos`.** `FORMATOS` (12 aceitos: GeoTIFF/BigTIFF,
   JPEG 2000, Erdas Imagine, ENVI, ASCII Grid, PNG/JPEG com world file, netCDF 1 variável × 1 tempo,
   GRIB 1 mensagem, Zarr, KMZ superoverlay, e o zip contêiner de mosaico) e `RECUSADOS` (ECW/MrSID por
   SDK proprietário ausente; GeoPDF, HDF5, netCDF com eixo de tempo, ASCII com vírgula decimal, com a
   mensagem dirigida de cada um). `lista()` é o que a rota GET /api/imagens/formatos devolve e o que
   `web/js/uploads/enviar.js` usa (i18n `pt-BR.json`); teste de API compara a resposta com
   `formatos.lista()` — tabela diferente é a refutação nomeada do item. O validador isolado
   (`app.raster.validacao`) reporta o rótulo pelo driver GDAL, e a recusa por extensão acontece ANTES
   de qualquer subprocesso.

2. **Zip é contêiner, não formato: mosaico por VRT, com a identidade do contêiner preservada.** Zip
   com N rasters de mesmo CRS e mesma grade extrai para o diretório de trabalho e monta
   `gdalbuildvrt`; o VRT entra na conversão como raster único (geometria e dimensões da UNIÃO — medido
   4 cenas 2×2 de 96×72 virando 192×144). Achado de produto corrigido: `_fonte_de_conversao` devolvia
   o relatório do VRT e o item dizia "não mosaico, 1 cena"; o relatório do VRT agora carrega
   `formato`/`mosaico`/`arquivos`/`extraido_em` do contêiner de origem. CRS diferentes entre as cenas
   recusam ANTES de montar qualquer coisa, com o EPSG de cada arquivo na mensagem (EPSG:31983 ×
   EPSG:4326 nomeados, com o nome do arquivo de cada um).

3. **O cadeado de sidecar (`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`) cede para o par ENVI — e a razão
   vale também via VRT.** Medido nesta trilha: o driver ENVI descobre o `.hdr` irmão pelo READDIR do
   diretório; com o cadeado fechado, "not recognized as supported file format" — a validação isolada
   já cedia por isso. A SURPRESA foi a segunda etapa: o COG visual é convertido DE UM VRT que
   REFERENCIA o `.dat`, e o `gdal_translate` da etapa 2 reabre o `.dat` com o cadeado fechado e falha
   de novo. Conserto: `ambiente_isolado(*fontes)` (varargs) e o `cog._rodar` decide pela FONTE
   ORIGINAL da conversão (`fonte=bruto` explícito na etapa 2), não pelo argumento do comando — regra:
   quem chama passa TODAS as fontes que o comando toca.

4. **Refutações com arquivo pronto, cada uma virando teste:** JP2 de 12 bits importa com dtype UInt16
   preservado (mais de 8 bits não é recusa); IMG com pirâmides externas `.rrd` importa (o irmão viaja
   no zip, mesma regra do `.hdr`); netCDF com eixo de tempo recusa apontando o L1-19 ("4 fatias"
   nomeadas — nunca importa como bandas silenciosas); ASCII Grid com vírgula decimal recusa com a
   mensagem dirigida.

5. **`pgstac.update_collection_extents()` sob SAVEPOINT — o rollback silencioso que engolia o item.**
   Achado CRÍTICO medido nesta trilha (e primeiro sintoma do teste): 21 itens todos 'arquivo', zero
   'raster'. Causa: no schema da trilha a função do pgstac falha ("relation collections does not
   exist"), o `except` Python capturava e seguia — mas a transação Postgres ficou ABORTADA, o commit
   do `with ctx.db()` virava ROLLBACK e TODA a ingestão se perdia sem erro em lugar nenhum. Conserto:
   `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` em volta da chamada; extents são derivados e nunca derrubam a
   ingestão (o aviso vai ao log do job). Corolário escrito: erro do Postgres dentro de try/except
   Python sem savepoint é perda silenciosa de transação inteira.

6. **Upload canônico × objeto de imagem: duas chaves, dois contratos.** O bruto sobe por
   `objetos.guardar` (chave `<slug>/<classe>/[<referencia>/]<sha256>.<ext>`, o mesmo caminho do POST
   /api/arquivos) e o job lê com `objetos.baixar`; `objetos_raster.guardar_bytes` é só para os objetos
   de imagem do item (visual/científico/miniatura, chave `<slug>/<item_id>/<asset>_<sha8>.<ext>`).
   Misturar os dois foi a primeira causa de "o objeto do arquivo não existe mais no armazenamento" —
   a ChaveInvalida do padrão errado chegava como FileNotFoundError no job.

7. **Tipo de evento da rota precisa de migração.** A rota POST /api/imagens/ingestoes (L1-01-i)
   registrava o evento `imagens/ingestar` sem cadastro em `plat.evento_tipo` — FK `evento_tipo_fkey`,
   500 em todo POST. Migração `20260908T2350_evento_tipo_imagens_ingestar.sql` registra o tipo com
   `ON CONFLICT DO NOTHING`; expõe a regra: rota que registra evento com tipo novo exige migração, e
   trilha nova exige re-rodar `trilha_ambiente.sh` para aplicá-la.

## Consequências

- A lista de formatos é contrato: acrescentar formato é editar a tabela, gerar o arquivo de teste e
  o teste passa a exigir o COG válido — sem terceiro caminho.
- Mosaico zip de ENVI (`.dat` + `.hdr` dentro do contêiner) fica fora do escopo deste item: o VRT do
  mosaico referencia caminhos extraídos e a regra 3 cobre o par solto; contêiner de ENVI é item
  próprio se houver demanda.
- `openapi.json` do repositório ficou obsoleto quanto à rota de formatos (gerado pelo turno de outro
  item); o caso cruzado de GET /api/imagens/formatos fica deliberadamente FORA (a rota é só leitura
  da tabela, coberta pelo teste de igualdade com `formatos.lista()`), para não conflitar no merge.
- Os quatro achados de produto (savepoint, chaves de objeto, cadeado via VRT, migração de evento) são
  consertos no ramo e valem para todo item futuro que ingere arquivo.
