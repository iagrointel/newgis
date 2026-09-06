# L1-01-b — Validação e isolamento da entrada raster (handoff T3)

Ramo `wt/valida`, worktree `/home/dev/plataforma/wt/valida`. Não toca `enterprise/` nem `laco/estado.json`.

## O que foi construído

| arquivo | o que é |
|---|---|
| `app/raster/__init__.py` | pacote da linha L1 |
| `app/raster/validacao.py` (602 linhas) | pai (`validar()`) + filho (`python -m app.raster.validacao`) |
| `app/raster/tarefas.py` | job `raster.validar` (grava o relatório inteiro em `resultado.validacao`) |
| `app/jobs/tipos.py` | **uma linha**: `from app.raster import tarefas as raster_tarefas  # noqa: F401` |
| `docs/adr/0015-validacao-raster.md` | ADR (limites declarados, três estados, zip, VRT, reaproveitamento) |
| `tests/unit/test_raster_validacao.py` | 25 testes, 33 casos com arquivo sintético em `tmp_path` |
| `tests/medidas/L1-01-b.json` | tempo e pico de RSS do subprocesso, caso a caso |
| `CHANGELOG.md` | entrada do turno 3 |

Nenhuma migração: o relatório mora no `resultado` do job, que já existe (ADR 0003). A reserva **036** do
adendo do brief fica LIVRE — não usei.

## Portão de pronto, cláusula → prova

Reproduza tudo com um comando:
`cd /home/dev/plataforma/wt/valida && flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_raster_validacao.py -q`
(25 passed; sem banco, sem worker, sem rede).

| cláusula do portão | teste | resultado |
|---|---|---|
| sem CRS → pede, não assume; resposta gravada | `test_sem_crs_pede_e_resposta_grava` | `pendente`, campo `crs`; com `respostas={"crs":31983}` vira `aceito` com `origem="informado"`; `crs="EPSG:999999"` → recusado com "o CRS informado não foi reconhecido" |
| CRS sem EPSG (WKT custom) | `test_crs_sem_epsg_wkt_custom_aceita_com_wkt2` | `aceito`, `epsg=None`, rótulo "WKT2 sem EPSG", WKT2_2019 inteiro gravado, aviso |
| NoData ausente | `test_nodata_ausente_pede_e_resposta_grava` | `pendente` campo `nodata`; respondido → `aceito` |
| 16 bits | `test_16_bits_dados_aceita_visual_pede_escala` | perfil `dados` = `aceito` (`tipo=uint16`); perfil `visual` = `pendente` campo `escala`; com `[0,4000]` = `aceito` |
| bandas com tipos diferentes | `test_bandas_tipos_diferentes_vrt` e `..._zip_com_dois_tif` | recusado: "bandas com tipos de dado diferentes: uint16, uint8; todas as bandas têm de ter o mesmo tipo" |
| zip 50× declarado, sem gerar 50 GB | `test_zip_bomba_declarada_50x_recusa_antes_de_extrair` | cabeçalho local+central adulterado no teste; recusado por razão de compressão E, com cota de 10 kB, por soma declarada; `zip_extraido/` **não existe** depois |
| `.tif` que é PNG renomeado | `test_tif_que_e_png_renomeado` | recusado no PAI (`subprocesso is None`): "o conteúdo não corresponde à extensão .tif: os primeiros bytes são de PNG, não de GeoTIFF" |
| EPSG:4674 e EPSG:31983 aceitos, CRS gravado | `test_epsg_4674_e_31983_aceitos_com_crs_gravado` | os dois `aceito`, `epsg` correto, `bbox4326` conferida, ColorInterp `[red,green,blue]`, data do `TIFFTAG_DATETIME` |
| 1 banda para perfil visual | `test_uma_banda_visual_recusa_dados_aceita` | visual: recusado "perfil visual exige pelo menos 3 bandas (RGB); o arquivo tem 1"; dados: `aceito` |
| RLIMIT_AS e timeout DECLARADOS em ADR | ADR 0015 §2 + `test_ambiente_do_filho_sem_readdir_e_sem_curl` | AS 768 MB, CPU 60 s, NOFILE 64, CORE 0, relógio 90 s |
| GeoTIFF de 100 GB virtual recusado sem derrubar o pai | `test_bigtiff_esparso_100gb_virtual_recusado_sem_derrubar_o_pai` | BigTIFF esparso 320.000×320.000, **< 200 kB em disco**; recusado por "tamanho descompactado estimado de 95.4 GB … acima da cota"; `codigo_saida=0`, `morte=None`; pai vivo |
| relatório gravado no job em JSON | `test_tipo_de_job_registrado` + `app/raster/tarefas.py` | tipo `raster.validar` no `REGISTRO`, `memoria_mb=1024 ≥ RLIMIT_AS`, `tentativas=1`, `perfil_minimo=editor`; devolve `{"validacao": <relatório>, "arquivo_chave", "sha256"}` |

Extras que o portão não pediu e ficaram: data de aquisição ausente pede (`test_data_aquisicao_ausente…`),
extensão fora do Brasil avisa (`test_extensao_fora_do_brasil_avisa`), extensão desconhecida recusa, caminho
`/vsi…` recusado, VRT remoto e `VRTRawRasterBand` recusados, zip-bomba real de zeros recusado.

## Refutação — os 3 casos do adversário já incluídos

| caso | teste | o que acontece |
|---|---|---|
| TIFF com IFD circular (próximo IFD aponta para ele mesmo) | `test_adversario_tiff_com_ifd_circular` | **não trava**: o relatório sai em < 10 s, `morte=None`; o GDAL corta o laço e vê um TIFF 8×8 sem CRS → `pendente` pedindo o CRS (nunca aceito em silêncio) |
| JP2 truncado na metade | `test_adversario_jp2_truncado` | `recusado` ("os dados de truncado.jp2 não puderam ser lidos (arquivo truncado ou corrompido)" ou "o GDAL não abriu"), `morte=None` |
| GeoTIFF declarando 65.535 bandas | `test_adversario_geotiff_65535_bandas` | `recusado` ("65535 bandas; o máximo aceito é 512" ou o GDAL recusa), RSS < 768 MB |
| filho tentando alocar 2 GB | `test_estouro_de_memoria_no_filho_nao_derruba_o_pai` | `morte=memoria`, pai devolve "a validação excedeu a memória do subprocesso (768 MB)" |
| filho em laço infinito | `test_tempo_esgotado_mata_o_filho` | `morte=timeout`, `codigo_saida=-9`, 2,01 s com `timeout_s=2` |

RAM do subprocesso medida em TODO caso (`os.wait4` → `ru_maxrss`), e o `assert` de
`tests/unit/test_raster_validacao.py::validar` reprova qualquer caso que passe do `RLIMIT_AS`.
Medido: **87,1 MB a 130,4 MB** de pico em 31 casos; tempo mediana 0,294 s, máximo 0,406 s fora do caso do
relógio. Zero travamento, zero aceitação silenciosa (todo estado `recusado` tem mensagem e todo `pendente`
tem pergunta — o `validar()` do teste afirma isso em cada caso).

## O que ficou de fora, e por quê

1. **e2e do job `raster.validar` pela fila real** — a trilha rodou em worktree e não sobe worker que dispute
   a fila de produção (regra do brief). O tipo é provado por teste de unidade (registro + validação dos
   parâmetros); a função de validação é provada direto. **Fica para depois do merge.**
2. **Rota HTTP** que crie o job e mostre o relatório na tela: é outro item (L1-01 tem sequência própria);
   aqui só o motor e o tipo de job.
3. **Conversão** (COG, pirâmide, tile): item seguinte. Este é o portão que roda ANTES.
4. **Formatos**: aceitos `.tif/.tiff/.jp2/.vrt/.zip`. ECW, MrSID, HDF, NetCDF e GRIB ficam fora de propósito
   (licença e superfície de ataque); acrescentar é uma linha em `ASSINATURAS` mais um caso de teste.

## Limitações honestas

- `BRASIL_BBOX` é uma caixa com folga, não a fronteira: a checagem de extensão é **aviso**, nunca recusa.
- O tamanho descompactado é ESTIMADO (`largura × altura × bandas × itemsize`); compressão interna do
  GeoTIFF não é considerada — de propósito, porque a estimativa tem de ser o pior caso.
- A razão de compressão do zip usa o que o cabeçalho DECLARA. Um zip que declara pouco e entrega muito é
  pego na extração (o contador para quando a entrada passa do declarado), não antes.
- `RLIMIT_AS` 768 MB só funciona porque o ambiente do filho fixa `OPENBLAS_NUM_THREADS=1`/`OMP_NUM_THREADS=1`
  (medição do ADR 0003 §4.3: sem isso, 512 MB já trava no import). Quem mexer no ambiente tem de remedir.
- O `preexec_fn` do `subprocess.Popen` não é seguro com threads no pai em geral; aqui o pai é o filho do
  worker (um job por processo) e o único thread extra é o `Timer` do relógio, criado DEPOIS do `Popen`.

## Riscos de merge

- `app/jobs/tipos.py`: **uma linha** de import, na mesma lista das outras (baixo risco de conflito).
- `CHANGELOG.md`: entrada nova no topo da seção "turno 3" (conflito de contexto possível, resolução trivial).
- `docs/adr/0015-…`: a árvore principal já foi até **0012**; as trilhas `garage` e `stac` podem tomar 0013 e
  0014. Se colidirem, renumerar este arquivo e as 3 referências em `app/raster/*.py` (`grep -n "ADR 0015"`).
- Nenhuma migração; a reserva 036 do brief não foi usada.

## Comandos para o adversário

```
cd /home/dev/plataforma/wt/valida
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_raster_validacao.py -q
venv/bin/ruff check app/raster tests/unit/test_raster_validacao.py
make sem-marcador
cat tests/medidas/L1-01-b.json
# caso avulso, sem pytest (mede tempo/RAM do subprocesso):
venv/bin/python -c "from app.raster import validacao as v; import json; print(json.dumps(v.validar('ARQUIVO.tif'), ensure_ascii=False, indent=1))"
```

## Commits do ramo

- `45cd0a1` Validação e isolamento da entrada raster em subprocesso com limites (item L1-01-b)
- `5795a81` Medidas por caso e entrada no changelog do item L1-01-b
