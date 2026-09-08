# 20_arquitetura — L0-04-ingest-vetor (T2, trilha de preparação; arquiteto + dados)

## Objetivo

Deixar o ADR 0005 (ingestão vetorial) pronto para o turno de construção começar em 30/31: pipeline upload →
inspeção → confirmação → carga → catálogo/publicação → proveniência, com formato por driver, limites, recusas com
mensagem exata, modelo da tabela de camada, contrato de API, telas e testes — tudo decidido por medição nesta
máquina, não por leitura.

## O que fiz

1. Li `estado.json` (item pai + 10 filhos `L0-04-a…j`, L0-11, L0-12, L0-05-a, L0-03-a/i/l), `L0_CONCEITO.md`
   (D2-D4, D11-D13, D16, D17), `L2_CONCEITO.md` (C3-C5, C8, C9, C11, C12, C18), `L4_CONCEITO.md` (C1, C10, C14),
   ADRs 0001/0002/0003 e o **0004 (publicado 15:20 durante esta trilha)**; o SIG de teste interno
   (`app/ingest.py`, `pipeline/05_importar_dxf.py`, só leitura); o código real do L0-05 já no repositório
   (`app/jobs/registro.py`, `contexto_job.py`, `filho.py`, `limites.py`, `erros.py`).
2. Medi (Anexo A do ADR; scripts e logs em `medicoes/` ao lado deste arquivo): drivers do GDAL 3.8.4; módulos
   da venv sob `PYTHONNOUSERSITE=1`; `ogrinfo -json` em 30 arquivos de teste gerados de dado aberto (municípios do
   IBGE de uma UF simplificados, ferrovias DNIT, heliportos DECEA, sintéticos); `ogr2ogr → PostGIS` como `plat_app`
   com tempo e RSS por formato; 100 mil feições (GPKG/shapefile/GeoJSON/GeoJSONSeq) + pós-carga completa; matriz de
   memória sob `RLIMIT_DATA`; LibreDWG no GPU box; `magic` por arquivo.
3. Escrevi `enterprise/docs/adr/0005-ingestao-vetorial.md` (1.122 linhas, 20 seções + Anexo A), gravado em 4
   blocos para sobreviver a interrupção.
4. Limpei: schema `adr0005_tmp` apagado (`pg_namespace` = 0), arquivos grandes apagados, `/tmp` do GPU box limpo,
   scratchpad apagado no fim (evidência pequena copiada para `medicoes/`, 80 kB, sem senha e sem caminho).

## Evidência (comando + saída literal; o resto está em `medicoes/*.log`)

```
$ ogrinfo --version
GDAL 3.8.4, released 2024/02/08
$ ogrinfo --formats | grep -ci parquet
0
$ PYTHONNOUSERSITE=1 venv/bin/python -c "import importlib; [print(m, ...) for m in ['duckdb','pyogrio','lxml','ezdxf','multipart']]"
duckdb AUSENTE  pyogrio AUSENTE  lxml AUSENTE  ezdxf AUSENTE  multipart AUSENTE          (existem só em ~/.local)
$ ogrinfo -ro -json -so /vsizip/municipios_semprj.zip      → srs=AUSENTE (Polygon, 75)
$ ogrinfo -ro -json -so heliportos_pv.csv -oo AUTODETECT_TYPE=YES -oo X_POSSIBLE_NAMES=long -oo Y_POSSIBLE_NAMES=lat
   → lat Real, long Real, "Elevação (m)" Real, Data Date, geom Point, srs=AUSENTE
$ ogrinfo -ro -q -oo AUTODETECT_TYPE=YES -al milhar_pv.csv → valor (String) = 1.234,5 · data (String) = 08/02/2024
$ ogrinfo -ro -json -so --config DXF_INLINE_BLOCKS FALSE blocos.dxf → camadas blocks(1) + entities(6): 3 × Point BlockName=ARVORE
$ ogrinfo -ro -json -so binario.dxf → ERROR 4: not recognized as a supported file format
$ /usr/bin/time -f "TEMPO %e s RSS %M kB" ogr2ogr -f PostgreSQL "PG:$PLAT_DSN" sint100k.gpkg -nln adr0005_tmp.sint100k_gpkg -nlt PROMOTE_TO_MULTI -lco GEOMETRY_NAME=geom -lco FID=fid -lco SPATIAL_INDEX=NONE -lco PRECISION=NO --config PG_USE_COPY YES
TEMPO 2.57 s RSS 58124 kB
pós-carga (plat_app, \timing): IsValid 190 ms · MakeValid/Reduce 1631 ms · ADD COLUMN ×7 2321 ms · UNIQUE 343 ms · GIST 750 ms · ANALYZE 262 ms · stats 66 ms → 45 MB
$ gpkg_municipios (origem GeoJSON tipo Geometry, -nlt PROMOTE_TO_MULTI) → geom geometry(Geometry,4326)   ← não tipa
$ … -nlt MULTIPOLYGON → geom geometry(MultiPolygon,4326); -lco FID64=YES → fid bigint
$ LAUNDER padrão: "Código IBGE"→"código ibge", "Área km²"→"Área km²", "select"→"select"   ← normalização é nossa
$ shp sem .prj sem -a_srs → geometry(MultiPolygon) SRID 0 (silêncio); com -a_srs EPSG:4674 → 4674
$ gravata: ST_IsValid f "Self-intersection[-37.05 -10.85]"; ST_MakeValid → ST_MultiPolygon, 2 partes, área 0.005
$ prlimit --data=268435456 ogrinfo … (SEM OPENBLAS_NUM_THREADS=1) → rc 124 (travado 45 s) em 9 de 9 execuções, RSS ≈ 40 MB
$ OPENBLAS_NUM_THREADS=1 prlimit --data=268435456 ogrinfo -ro -json -so sint100k.geojson (55 MB) → TEMPO 1.19 s RSS 54528 kB rc 0
$ OPENBLAS_NUM_THREADS=1 prlimit --data=536870912 ogrinfo -ro -json -so grande2m.geojson (1 feição, 51 MB) → sinal 6, RSS 555008 kB
$ sem limite → rc 1 "unable to open", RSS 644 MB (10 mi vértices, 255 MB: idem, 645 MB)
$ ssh gpu: dxf2dwg -y --as r2000 … rc 0 (1221 B); dwg2dxf … rc 0; ogrinfo na volta → "error at line 991"; ezdxf → "missing ENDSEC tag"
$ sudo -u postgres psql -c "DROP SCHEMA adr0005_tmp CASCADE" … SELECT count(*) FROM pg_namespace WHERE nspname='adr0005_tmp' → 0
```

## Decisões do ADR (resumo; seção 1 do ADR tem a lista de 13)

- 5 estados, 2 jobs (`ingestao.inspecionar` 768 MB/300 s não pesado; `ingestao.carregar` 1.024 MB/3.600 s pesado,
  `tentativas=1`, chave `arquivo:<id>`), confirmação humana no meio; nada cria tabela antes da confirmação.
- Upload em partes de 16 MiB pela API (corpo bruto; `python-multipart` ausente), multipart S3 no Garage pelo
  contrato do L0-11 estendido (parte_iniciar/enviar/concluir/abortar/ler_intervalo), cota reservada antes do byte 1.
- Inspeção = `ogrinfo -json` + varredura do tipo real de geometria (120-230 ms/100 mil) + sondas nossas
  (codificação, separador, milhar, `dd/mm`, duplicatas, aspas, unidade DXF, WKT sem código, maior feição do GeoJSON).
- Carga = `ogr2ogr` neto com `-nlt <varrido>`, `-sql … AS <nome normalizado>`, `-a_srs` confirmado, `COPY`,
  `FID64`, sem índice; pós-carga em uma transação: MakeValid com relatório, 7 colunas obrigatórias, `FORCE ROW LEVEL
  SECURITY` (a tabela é do `plat_app`), sequência com teto 2^31−1, GIST, ANALYZE, estatísticas, item com id
  pré-gerado, relação `arquivo_de_camada`, função de tile (C3) com stub de `contexto_por_token`, proveniência D17.
- Limite por **maior feição** (16 MiB) e não por tamanho de arquivo (GeoJSON de 55 MB lê em fluxo com 54 MB).
- CSV/XLSX por normalizador próprio (o GDAL não lê milhar nem `dd/mm`, engole aspa aberta, não abre `.txt`).
- DXF pelo driver do GDAL com `DXF_INLINE_BLOCKS=FALSE` (bloco = ponto com `blockname`), 1 camada por *layer*,
  unidade e georreferência (Helmert com RMSE) sempre perguntadas. DWG desligado até medição no corpus (D23 aberta).
- GeoParquet fora desta fase (driver e `duckdb`/`pyogrio` ausentes sob a regra da venv); caminho: `pyogrio` na venv.
- Migração `007_ingestao.sql` (upload, upload_parte, importacao, cota no tenant, funções `camada_preparar/
  camada_tile_criar/camada_apagar/feicao_versao/feicao_inserir`, role `plat_leitor`, tipo `tabela`, esquema v2 de
  `camada_vetorial`, `tenant_criar` cria `d_<slug>`).

## Listas para o turno de construção

### Backend (`app/ingestao/`)

`formatos.py` (tabela 10.1 + prova por bytes 3.3), `zip_seguro.py` (3.2), `nomes.py` (8), `crs.py` (9: sugestão por
extent, `GET /api/crs`), `csv_normalizar.py` (11), `helmert.py` (12.2, numpy), `inspecao.py` (4: pré-sondas +
`ogrinfo -json` + varredura + proposta), `carga.py` (6: 10 passos), `sql_camada.py` (chamadas a `camada_preparar`,
estatísticas, tile), `atualizar.py` (13), `exportar.py` (14, `filtro_simples.py`), `tarefas.py` (`@tarefa` × 5:
inspecionar, carregar, atualizar, exportar, uploads_expirar/importacoes_expirar/orfaos/exportacoes_expirar/
lixeira_tabelas como periódicos em `periodicos.py` próprio), `rotas_uploads.py`, `rotas_importacoes.py`,
`rotas_camadas.py`, `objetos_local.py` estendido (multipart em disco) até o L0-11; `db/migracoes/007_ingestao.sql`;
`app/limites.py` seção `# --- ingestão (L0-04)`; `docs/openapi.json` regenerado; nginx `location /api/uploads/ {
client_max_body_size 20m; proxy_request_buffering off; }` em `deploy/nginx.conf`.

### Frontend (`web/`)

`conteudo_novo_arquivo.html` + `js/ingestao/assistente.js`, `upload.js` (fatias de 16 MiB, reenvio de parte com
falha, barra, retomada por `GET /api/uploads/{id}`), `proposta.js`, `campos.js` (tabela editável de campos),
`crs.js` (busca), `csv.js` (prévia 10 linhas), `dxf.js` (unidade + pontos de controle + RMSE), `importacoes.js`,
`camada_dados.js` + `tabela.js` (aba Dados, paginada), `exportar.js` (diálogo). Sem biblioteca nova.

### Dados/testes

`tests/dados/gerar.py` + `semente_municipios.geojson` (583 kB, único arquivo comitado) + `esperado/*.json`;
suíte da seção 19.2; medidas `tempo_import_100k_s`, `tempo_inspecao_s`, `taxa_upload_mb_s`, `rss_ogr2ogr_mb`.

## Riscos

1. **`ctx.subprocesso` bufferiza** (LIDO): progresso do `ogr2ogr -progress` chega só no fim do passo 3. Mitigação
   no ADR 20.2 (leitor de stream próprio em `app/ingestao/`), sem editar `app/jobs/`.
2. **`FORCE ROW LEVEL SECURITY` é indispensável** porque a tabela nasce de propriedade do `plat_app` (o `ogr2ogr`
   conecta com o `PLAT_DSN`); sem ele o P6 passa em falso. Está na função `camada_preparar` e no teste.
3. **DWG não provado** (LibreDWG perdeu entidades e produziu DXF ilegível num caso mínimo). D23 continua aberta;
   L0-04-e mede no corpus antes de qualquer promessa.
4. **`OPENBLAS_NUM_THREADS=1` é condição de vida** do `ogrinfo/ogr2ogr` sob `RLIMIT_DATA` (9/9 travadas sem ela).
   O filho do worker já exporta; qualquer teste que chame GDAL sob limite fora do worker tem de exportar também.
5. **KML_BYTES_MAX (64 MiB) é declarado, não medido**; L0-04-d mede.
6. **ADR 0004 3.2 fixa `additionalProperties: false`** para `camada_vetorial`: a 007 tem de atualizar o esquema
   (v2) antes de o primeiro item existir, senão a validação da API recusa `dados.estatisticas/procedencia`.
7. `tg_item_imutaveis` do ADR 0004: conferir na integração que aceita `INSERT` com `id` fornecido (4.4 depende).
8. O ADR não consultou URL nenhuma por HTTP (toda referência é ao GDAL/PostGIS instalados); o papel `esri` do turno
   de construção escreve a paridade contra "Publish hosted feature layers"/"CSV, TXT, GPX" 11.4.

## Pendências

- Migração pode ter de renumerar (`007` → `008`) conforme a ordem de integração com L0-03 (`006`) e L0-11.
- `plat.contexto_por_token` entra como stub (tile vazio sem contexto) até o L2-04-a; `plat_leitor` nasce `NOLOGIN`.
- Item `tabela` (sem geometria) é tipo novo registrado pela 007 (o ADR 0004 não o tinha).
- `decisoes_do_dono`: nada novo além de D23 (DWG/ODA), que este ADR reforça com medição.

## Colisões com A/B e com o ADR 0004 (tabela completa em 20.2 do ADR)

- B (L0-05): `subprocesso` bufferizado; `PLAT_WORKER_MEMORIA_MB=1536 ≥ 1024` ok; `executor=gpu` é gancho → DWG
  desligado.
- A (L0-02): privilégios e escopos já semeados; nada a pedir.
- ADR 0004: `id` fornecido no INSERT do item; esquema v2 do tipo; destruidor chama `camada_apagar`; miniatura por job
  no fim da carga; `permite_download` governa a exportação; relação `arquivo_de_camada` (não `resultado_de_job`).
- Áreas tocadas por este item na construção: `app/ingestao/` (novo), `app/limites.py` (seção própria),
  `app/main.py` (montar rotas — colide com A e B: ordem de commit), `deploy/nginx.conf` (location nova),
  `db/migracoes/007_*`, `web/js/ingestao/` (novo), `tests/dados/` (novo).

## Para o próximo papel

- **Gerente**: integrar este ADR no plano do T3; decidir numeração da migração; lançar `esri` (paridade 11.4:
  publish-features, csv-gpx, add-item-part) e `dados` (revisar tabela 10.1 com os arquivos do gerador) antes de 30.
- **Backend**: começar por `007_ingestao.sql` + `nomes.py` + `formatos.py` + `inspecao.py` (a proposta é o contrato
  da tela); `carga.py` passo a passo com o teste de órfãos desde o 1º commit; `objetos_local.py` multipart em disco.
- **Frontend**: o assistente lê `GET /api/importacoes/formatos` e a proposta; nada de lista fixa no JS.
- **Testador**: `tests/dados/gerar.py` primeiro (é o que todos os testes consomem); medir `tempo_import_100k_s`
  com o sintético gerado na hora e apagado.
- **Adversário**: a tabela 4.3/10.1 é a lista de mensagens exatas; silêncio ou 500 em qualquer arquivo de 19.1 =
  refutado; `pg_class.relforcerowsecurity` em toda `c_*`.
