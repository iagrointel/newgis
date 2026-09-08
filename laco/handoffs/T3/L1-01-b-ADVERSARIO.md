# L1-01-b — relatório do ADVERSÁRIO (validação e isolamento da entrada raster)

**VEREDITO: REFUTADO.**

O item promete, na hipótese e no portão, que a validação roda "em processo separado … sem `/vsicurl` em upload,
sem rede" e que cada caso "importa certo ou recusa com mensagem exata em português, nunca silêncio". Três coisas
medidas por mim derrubam isso:

1. **um arquivo enviado faz a validação ler arquivo de fora do envio** (VRT que aponta para outro VRT);
2. **um arquivo enviado faz a validação abrir conexão de rede** para um endereço escolhido por quem enviou;
3. **um raster comum (NoData = NaN) produz um relatório que o banco recusa** — a cláusula "relatório de validação
   gravado no job em JSON" não se cumpre para esse arquivo.

O resto do item é sólido: os limites do subprocesso são reais (li no `/proc` do filho vivo, não no código), o
BigTIFF esparso de 95,4 GB é recusado em 0,29 s, o IFD circular não trava, as medidas do construtor conferem com
medição externa (3 % de diferença) e nenhum dos meus ataques de memória passou dos 131 MB de pico.

Arquivo de teste: `tests/unit/test_raster_validacao_adversario.py` — 23 casos, **14 passam (defesa segurou)** e
**9 são `xfail(strict=True)`** (o teste afirma o que o item promete; a promessa não se cumpre). `strict` faz o
conserto virar falha do marcador, então nenhum achado se perde.

```
cd /home/dev/plataforma/wt/valida
flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_raster_validacao_adversario.py -q -rxX
# 14 passed, 9 xfailed, 1 warning in 14.24s
```

Ambiente: rasterio 1.5.0 / GDAL 3.12.1 / Python 3.12.3.

---

## ACHADO 1 (grave) — VRT aninhado lê arquivo fora do envio

`_conferir_vrt` confere as `SourceFilename` **do VRT enviado**. Se a fonte for outro VRT local, o segundo VRT não
é conferido por ninguém, e ele pode apontar para caminho absoluto qualquer.

```
$ venv/bin/python  # resumo do que o teste test_vrt_aninhado_nao_deve_ler_arquivo_fora_do_envio faz
envio/bom.tif                (raster legítimo, pixel 1)
envio/b.vrt   -> SourceFilename relativeToVRT="0" = <tmp>/fora/segredo.tif   (pixel 222)
envio/a.vrt   -> SourceFilename relativeToVRT="1" = b.vrt
>>> v.validar("envio/a.vrt", respostas={"data_aquisicao": "2026-01-02"})
ESTADO: aceito
problemas: []   avisos: []   pendencias: []
>>> rasterio.open("envio/a.vrt").read(1)[0,0]
222            # o GDAL leu o arquivo que está FORA do diretório do envio
```

Saída real da minha sonda (`scratchpad`, mesmo roteiro):

```
ESTADO: aceito
problemas: []
avisos: []
pendencias: []
PIXEL LIDO PELO GDAL VIA a.vrt: 200      # nessa sonda o arquivo de fora tinha pixel 200; no teste, 222
```

O pixel de fora entra no relatório: a leitura de prova (`d.read(1, window=…)`) do filho lê o arquivo de fora
**dentro da validação**. Como todos os inquilinos são atendidos pelo mesmo usuário do sistema, o alcance é todo
arquivo que o `plat_app`/worker enxerga, inclusive o diretório de trabalho de outro job.

Conclusão: **REFUTADO** — "sem VRT com fonte fora do diretório do envio" vale só para o primeiro nível.

## ACHADO 2 (grave) — a conferência do VRT só lê 1 MiB do XML

`_conferir_vrt` faz `caminho.read_text(...)[:1 << 20]`. Com um comentário XML de 1 MiB entre a primeira banda
(legítima, relativa) e a segunda (caminho absoluto de fora), a segunda fonte não é vista pela conferência.

```
A) padding 1MiB -> aceito [] bandas: 2
   pixel banda 2 (fora do envio): 222
```

O relatório sai `aceito`, com `bandas: 2`, e a banda 2 lê de fora. Conclusão: **REFUTADO**.

## ACHADO 3 (grave, condicionado) — fonte do VRT por ligação simbólica

O arquivo ENVIADO é recusado se for link simbólico (`caminho.is_symlink()`), e link dentro de zip é recusado. A
FONTE do VRT não passa por essa peneira:

```
B) fonte por link simbolico -> aceito []
   pixel lido: 177
```

Depende de o atacante conseguir criar um link no diretório do envio — hoje não há caminho conhecido pela API para
isso, então classifico como grave-condicionado, não explorável por si só. A correção é a mesma dos achados 1 e 2:
resolver a fonte (`Path.resolve()`) e exigir que ela fique dentro do diretório do envio, recursivamente.

## ACHADO 4 (grave) — a validação sai à rede

O ambiente do filho põe `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.nenhuma-extensao-permitida`. Quem escreve a URL
escolhe a extensão dela, e o `http://` direto do GDAL não é barrado por essa lista. Pelo VRT aninhado (achado 1):

```
b1.vrt -> recusado [...] 0.3 s      # /vsicurl/http://127.0.0.1:PORTA/x.nenhuma-extensao-permitida
b2.vrt -> recusado [...] 0.29 s     # http://127.0.0.1:PORTA/y.tif
PEDIDOS RECEBIDOS PELO SERVIDOR: ['HEAD /x.nenhuma-extensao-permitida HTTP/1.1', 'GET /y.tif HTTP/1.1']
```

O servidor de teste (127.0.0.1, criado pelo próprio teste) **recebeu os dois pedidos**. O arquivo acabou recusado
só porque devolvi 404. Isto é requisição forjada pelo servidor (SSRF): o alvo pode ser um endereço interno —
serviço de metadados da nuvem, `plat-api` na 8150, PostgreSQL —, e o caminho da URL é canal de saída de dado.
`GDAL_HTTP_TIMEOUT=1` limita a duração, não o fato. Conclusão: **REFUTADO** — "sem rede" não se sustenta.

Defesa que segurou no mesmo terreno: fonte remota **no VRT enviado** (`http://`, `/vsicurl/`, `/vsis3/`,
`/vsizip/`, `..`, `/etc/passwd`) é recusada antes de qualquer leitura, e o `VRTRawRasterBand` não lê `/etc/passwd`
nem escondido no segundo nível, porque `GDAL_VRT_ENABLE_RAWRASTERBAND=NO` é obedecido pelo GDAL:

```
ESTADO: recusado ['os dados de a.vrt não puderam ser lidos ...']
GDAL recusou: Read failed. See previous exception for details.
```

## ACHADO 5 (grave) — relatório com NoData NaN não é JSON e não chega ao banco

NoData `NaN` é comum em raster float32. O relatório sai com `nan`, e o caminho de gravação do job não aguenta:

```
nodata NaN -> aceito | info.nodata: {'valor': nan, 'origem': 'arquivo'}
   JSON estrito FALHA: Out of range float values are not JSON compliant: nan

json.dumps default -> {"info": {"nodata": {"valor": NaN}}}
Json adapter      -> {"info": {"nodata": {"valor": NaN}}}
$ sudo -u postgres psql -d iagro_sat -tAc "select '{\"info\": {\"nodata\": {\"valor\": NaN}}}'::jsonb"
ERROR:  invalid input syntax for type json
```

`app/jobs/filho.py:160` faz `json.dumps(resultado, default=str)` — que **aceita** NaN — e
`app/jobs/worker.py:371` grava com `psycopg2.extras.Json`, que produz o mesmo `NaN` para uma coluna `jsonb`. A
cláusula "relatório de validação gravado no job em JSON" falha para esse arquivo, e falha como erro de banco, não
como recusa explicada. Conclusão: **REFUTADO** nessa cláusula.

## ACHADO 6 (médio) — extensão geograficamente impossível é aceita

Arquivo em coordenada UTM sem CRS; o usuário responde `crs=4674` (erro comum). Latitude declarada de 7.400.000°:

```
{"estado": "aceito",
 "avisos": ["extensão fora do território esperado (Brasil): [300000.0, 7399920.0, 300080.0, 7400000.0] em
             EPSG:4326 — confira o CRS"],
 "pendencias": []}
```

"Fora do Brasil" e "coordenada que não existe no planeta" recebem o mesmo tratamento (aviso). Como o item promete
que a plataforma **pergunta** em vez de assumir, a resposta errada do usuário devia virar pendência, não aviso.

## ACHADO 7 (médio) — a conta da bomba zip é razão, não volume

O limite é razão de compressão ≥ 50×. Um zip a 42× passa e é escrito inteiro no disco **antes** de qualquer
checagem de raster:

```
zip enviado 1.43 MB | declara 60.4 MB | razao 42.3x (limite 50x)
estado: aceito | 0.46 s
escrito em disco ANTES de qualquer checagem de raster: 60.4 MB = 42x o arquivo enviado
```

Com a cota de inquilino padrão (4 GiB), um envio de ~100 MB escreve 4 GiB no diretório de trabalho do worker. Em
máquina a 96 % de disco isso é material. A cláusula do portão ("zip de 1 GB que descompacta para 50 GB") está
cumprida; o que não existe é teto de VOLUME escrito por envio.

Defesas que seguraram no mesmo terreno (testes que passam): razão ≥ 50× recusada sem extrair nada; zip dentro de
zip recusado; zip dentro de zip **disfarçado de .tif** recusado pela assinatura (escreve só os poucos kB
declarados, nunca a bomba); entrada que mente para menos é cortada na extração.

## ACHADO 8 (médio) — exceção não capturada vira mensagem crua em inglês

GeoTIFF sem geotransform com CRS respondido (caso irmão do caso "sem CRS" do portão):

```
{"estado": "recusado",
 "problemas": ["a validação terminou sem relatório (código 1): rasterio._err.CPLE_AppDefinedError:
                latitude max < latitude min.; nada foi importado"]}
subprocesso: {'codigo_saida': 1, 'morte': 'saida 1'}
```

`rasterio._err.CPLE_AppDefinedError` não é `RasterioError` nem `ValueError`, então escapa do `except` do
`_inspecionar` e mata o filho. O que chega ao usuário é a última linha do traceback, em inglês, com o nome do
módulo privado do rasterio e sem dizer o que fazer. O portão pede "mensagem exata em português".

## ACHADO 9 (médio) — zip legítimo com 200 rasters é recusado em inglês e entrega o caminho do servidor

```
(a) 200 tif no zip -> recusado | 0.33 s
    problemas: ['o GDAL não abriu t060.tif: /tmp/.../zip_extraido/t060.tif: Too many open files']
```

Duas coisas: (i) o `_inspecionar` abre TODOS os arquivos do zip ao mesmo tempo e bate no `RLIMIT_NOFILE=64`, o que
recusa um envio legítimo a partir de ~55 rasters; (ii) a mensagem tem texto do GDAL em inglês e o caminho
absoluto do servidor. Mesmo defeito de idioma nas recusas comuns, que este teste registra como linha de base:

```
'zip inválido: File is not a zip file'
'o GDAL não abriu trunc.jp2: No code-stream in JP2 file'
```

---

## O que resistiu (ataques meus que a validação segurou)

| ataque | comando / saída | conclusão |
|---|---|---|
| limites do filho | li `/proc/<pid>/limits` e `/proc/<pid>/environ` do filho VIVO: `Max address space 805306368` (= 768 MB), `Max cpu time 60`, `Max open files 64`, `Max core file size 0`; `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, `GDAL_PAM_ENABLED=NO`, `GDAL_VRT_ENABLE_RAWRASTERBAND=NO`, `GDAL_HTTP_TIMEOUT=1`; `PLAT_DSN`/`PLAT_SECRET` ausentes | os limites são reais, não declaração |
| fonte remota no VRT enviado | 6 formas (`http://`, `/vsicurl/`, `/vsis3/`, `/vsizip/`, `../`, `/etc/passwd`) → todas recusadas | segurou |
| `VRTRawRasterBand` para `/etc/passwd`, escondido no 2º nível | recusado; o GDAL obedece `GDAL_VRT_ENABLE_RAWRASTERBAND=NO` | segurou |
| `.aux.xml` plantado ao lado | `pendente`, pendência `crs`, `info.crs is None` — o vizinho não empresta CRS nem data | segurou |
| caminho absoluto por entidade XML (`&#47;…`) | recusado — **mas com a mensagem errada** ("fonte inexistente"; o GDAL lê o arquivo, ele existe) | segurou por acidente |
| bloco de 1 GiB declarado no cabeçalho (tags de ladrilho reescritas para 32768×32768 num GeoTIFF válido de 1024×1024) | recusado em 0,29 s, pico 92 MB, `morte=None`, pai vivo | segurou |
| faixa única de 858 MB (30.000×30.000 esparso, 597 bytes em disco) | recusado, pico 92 MB | segurou |
| BigTIFF esparso 320.000×320.000 (arquivo meu, 4,7 MB em disco) | `recusado: tamanho descompactado estimado de 95.4 GB (320000×320000×1 bandas uint8) acima da cota de 4.0 GB; nada foi lido`, 0,29 s, pico 90 MB | segurou |
| IFD circular (próximo IFD = ele mesmo) | 0,27 s, `pendente` pedindo NoData e CRS, `morte=None` | segurou |
| JP2 truncado | recusado, pico 82 MB | segurou (idioma no achado 9) |
| 65.535 bandas | `recusado: 65535 bandas; o máximo aceito é 512`, pico 130,6 MB < 768 MB | segurou |
| `.tif` que é PNG | recusado no PAI, `subprocesso is None` — não abriu subprocesso | segurou |
| 20.000 tags desconhecidas de TIFF (tentativa de entupir o `stderr` do filho e travar o pai, que lê o `stdout` até EOF antes do `stderr`) | filho gastou 0,3 s, `stderr` 0 byte — não consegui gerar volume | não reproduzi (ver fronteira) |

## Medida — conferida por fora

Medi o filho com `/usr/bin/time -v`, chamado à mão, fora do pytest:

```
Maximum resident set size (kbytes): 92736     Elapsed (wall clock): 0:00.28   # GeoTIFF 64×64×3, aceito
Maximum resident set size (kbytes): 90404     Elapsed (wall clock): 0:00.28   # BigTIFF esparso, recusado
```

Contra `tests/medidas/L1-01-b.json` (31 casos): RSS mediana 90.828 kB, tempo mediana 0,287 s. Diferença de
**2,1 % em RAM e 2,4 % em tempo** — bem abaixo dos 30 % de tolerância. **Medida confiável.**

Dois reparos de exatidão no texto do construtor (não no dado):
* o handoff diz "pico entre 87,1 e 130,4 MB"; o mínimo do próprio arquivo é **79.464 kB = 79,5 MB**
  (`zip_acima_cota_ram_pico_kb`). O teto (130.340 kB) confere.
* o `tests/medidas/L1-01-b.json` é **reescrito a cada execução** dos testes do construtor e os valores oscilam
  alguns por cento entre execuções — quem comparar o arquivo com `git diff` vai ver ruído, não regressão.
* o cabeçalho de `tests/unit/test_raster_validacao.py` cita "ADR 0012"; o ADR do item é o **0015**.

## Higiene

```
$ venv/bin/ruff check app/raster tests/unit/test_raster_validacao*.py
All checks passed!
$ flock … make sem-marcador
! grep -rnI … -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md
(rc=0)
$ flock … venv/bin/pytest tests/unit/test_raster_validacao.py -q
25 passed  (2m55s, quase tudo espera de fila; 7,6 s de CPU)
```

Os dois arquivos juntos: `39 passed, 9 xfailed, 2 warnings in 24.34s` (25 do construtor + 14 meus + 9 achados).
As 25 do construtor passam mesmo, e o meu arquivo não interfere nelas. Observação sobre `make sem-marcador`: ele **não varre `tests/`**, então nenhuma
afirmação sobre marcador vale para os arquivos de teste.

## O que o item NÃO prova (fronteira honesta)

1. **Isolamento é rlimit, e só.** O filho roda com o mesmo usuário (`Uid 1001`), sem namespace, sem `seccomp`
   (`Seccomp: 0`, `NoNewPrivs: 0`), com a rede do host e acesso de leitura a todo arquivo do worker. Os achados 1
   e 4 são consequência direta disso: a barreira é a lista de conferências em Python, não o sistema operacional.
2. **O `RLIMIT_AS` nunca foi exercitado por arquivo real.** A prova do construtor usa o parâmetro `_prova` do
   próprio módulo (`bytearray(2 GB)` e laço infinito), que é código de teste dentro do arquivo de produção. Meus
   três ataques de memória por cabeçalho pararam antes, porque o GDAL recusou primeiro; o maior pico que consegui
   foi 130,6 MB. Logo: o limite existe (li no `/proc`), mas ninguém mostrou o GDAL batendo nele com um arquivo.
3. **O relógio de 90 s também não foi exercitado por arquivo real** — só pelo `_prova` "tempo". Não achei arquivo
   que fizesse o filho passar de 0,5 s.
4. **`preexec_fn` + leitura de `stdout` até EOF antes do `stderr`**: se um dia o filho escrever mais de 64 kB em
   `stderr`, o pai fica preso até o relógio. Não consegui produzir esse volume (o GDAL engole os avisos), então é
   risco de forma, não achado.
5. **Nada aqui foi provado pela fila real**: o job `raster.validar` só foi lido, não executado por worker. O
   achado 5 (NaN) é a soma de três fatos verificados isoladamente (relatório com NaN, o que o `Json` do psycopg2
   escreve, o que o `jsonb` recusa), não de um job que falhou em produção.
6. **Sem multi-inquilino de verdade**: chamei `validar()` direto, com a cota passada por argumento. Não testei
   `_cota_bytes_tenant`, RLS, nem concorrência de dois jobs escrevendo no mesmo `zip_extraido`.
7. **Formatos**: só `.tif/.tiff/.jp2/.vrt/.zip`. Não testei ECW, MrSID, HDF, NetCDF, GRIB — que não são aceitos.
8. **Tipo de dado**: `complex64` e `int64` são aceitos sem aviso nem pergunta (teste
   `test_tipo_de_dado_exotico_passa_sem_uma_palavra`, que passa). Não é promessa do portão; é fronteira: nenhum
   COG/tile serve esses tipos, e a recusa vai acontecer na conversão, não aqui.
9. **Não olhei** rota HTTP, conversão (COG/pirâmide/tile) nem antivírus: fora do item.

## Correção mínima que eu exigiria antes de dar o item por pronto

1. Resolver a fonte do VRT com `Path.resolve()` e exigir que caia dentro do diretório do envio, **recursivamente**
   (VRT que aponta para VRT), sem limite de 1 MiB de leitura — ou, mais barato e mais seguro, recusar VRT cuja
   fonte não seja um dos arquivos do próprio envio, e recusar VRT aninhado.
2. Fechar a rede no filho de verdade (`GDAL_HTTP_*` não fecha): `--disable-network` não existe no GDAL, então ou
   namespace de rede vazio, ou `unshare`/`seccomp`, ou executar o filho sem rota. Enquanto isso, tratar `SSRF` como
   risco aberto no ADR.
3. Trocar `NaN`/`Infinity` por `None` (com o valor em texto, se for preciso) antes de devolver o relatório.
4. Capturar `Exception` no `_inspecionar` e transformar em recusa em português, com o detalhe cru no log, nunca na
   mensagem.
5. Abrir os arquivos do zip um a um (fechando cada um) em vez de todos ao mesmo tempo, e tirar caminho absoluto de
   toda mensagem.

Commits deste relatório: ver o ramo `wt/valida` (`tests/unit/test_raster_validacao_adversario.py` e este arquivo).
