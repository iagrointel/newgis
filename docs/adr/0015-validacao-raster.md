# ADR 0015 — Validação e isolamento da entrada raster (item L1-01-b)

Estado: aceito (arquiteto+raster+backend, turno T3, setembro de 2026). Abre a linha L1 (imagens). Depende do
ADR 0003 (fila de jobs, filho com `RLIMIT_DATA`) e do ADR 0006 (arquivos/objetos, cota por inquilino). NÃO
converte nada: é o portão que fica ANTES da conversão para COG, da pirâmide e do tile.

Numeração: 0013/0014 podem ser tomados por outras trilhas em worktree (garage, stac) antes do merge; se
houver colisão, renumerar este arquivo e as três referências em `app/raster/` é uma troca de string.

## 1. Por que um processo separado

O arquivo é do cliente e o GDAL abre o que o cabeçalho mandar. Um TIFF de 400.000 × 400.000 pixels ocupa
menos de 1 kB em disco e faz o leitor tentar alocar 149 GB; um BigTIFF esparso de 320.000 × 320.000 cabe em
200 kB; um JP2 truncado leva o decodificador a erro dentro da biblioteca C. Nada disso pode acontecer no
processo que segura a conexão do banco e a fila. Logo:

* o PAI (`validar()`, roda no filho do worker) só olha os primeiros 64 bytes do arquivo com `open()` puro.
  **Nunca importa rasterio para olhar o arquivo do cliente.**
* o FILHO (`python -m app.raster.validacao <json>`) importa rasterio, abre o arquivo, e devolve o relatório
  em JSON pelo stdout. Morte do filho por qualquer causa (memória, CPU, relógio, sinal, saída sem JSON) vira
  relatório `recusado` com a causa escrita em português — nunca uma exceção que suba pela fila.

## 2. Limites declarados

| limite | valor | por quê |
|---|---|---|
| `RLIMIT_AS` | 768 MB | o item exige AS (endereço reservado), não DATA. Vale porque o ambiente do filho fixa `OPENBLAS_NUM_THREADS=1`/`OMP_NUM_THREADS=1`: sem isso o OpenBLAS reserva endereço por thread e 512 MB já trava no import (medição do ADR 0003 §4.3). Pico medido nos 31 casos com subprocesso: 130 MB (`tests/medidas/L1-01-b.json`). |
| `RLIMIT_CPU` | 60 s | laço de decodificação preso queima CPU sem crescer em RAM; o kernel manda SIGXCPU e depois SIGKILL. |
| `RLIMIT_NOFILE` | 64 | VRT com muitas fontes. |
| `RLIMIT_CORE` | 0 | disco a 98 %: nenhum core dump de 768 MB. |
| relógio de parede | 90 s (`TIMEOUT_S`) | um `threading.Timer` no pai manda SIGKILL ao GRUPO (`os.setsid` no filho, `killpg`) — pega também neto (`ogr…`) que o GDAL tenha lançado. |
| `GDAL_CACHEMAX` | 64 MB | dentro do AS. |

A diferença para o ADR 0003 (`RLIMIT_DATA` no filho do job) é deliberada e não conflita: o filho do job
continua com `RLIMIT_DATA`; este subprocesso é NETO dele e ganha `RLIMIT_AS` por cima, mais apertado.

## 3. Sem rede, sem `/vsi`, sem leitura de diretório

`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` (o GDAL não varre o diretório do envio procurando arquivo
auxiliar), `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.nenhuma-extensao-permitida` (nenhuma extensão pode ser lida por
HTTP), `GDAL_HTTP_TIMEOUT=1`, `GDAL_PAM_ENABLED=NO` (não escreve `.aux.xml` ao lado do arquivo do cliente),
`GDAL_VRT_ENABLE_PYTHON=NO`, `GDAL_VRT_ENABLE_RAWRASTERBAND=NO`. Caminho que contenha `/vsi` é recusado no
pai E no filho. `PLAT_DSN`/`PLAT_SECRET` são removidos do ambiente do filho: ele não fala com o banco.

VRT é aceito, mas conferido como texto antes de o GDAL vê-lo: `VRTRawRasterBand` (leitura crua de arquivo
arbitrário, ex. `/etc/passwd`) e banda derivada por função de pixel são recusados; `SourceFilename` tem de
ser relativo, existir e ficar dentro do diretório do envio.

## 4. O que a validação decide — e o que ela NUNCA decide sozinha

Três estados, um só relatório:

* **`recusado`** — defeito do arquivo, com a mensagem exata: assinatura que não bate com a extensão, extensão
  fora da lista, tamanho descompactado estimado acima da cota do inquilino, bandas com tipos diferentes,
  mais de 512 bandas, lado acima de 200.000 px, zip suspeito, dado ilegível.
* **`pendente`** — falta um dado que só o usuário tem. A plataforma **pergunta e grava a resposta no job**
  (`respostas`), nunca assume: CRS ausente, NoData não declarado, data de aquisição ausente, escala para
  reduzir 16 bits a 8 no perfil visual. O job CONCLUI com o relatório; a tela cria outro job com a resposta.
* **`aceito`** — pode seguir para conversão. Avisos não impedem: CRS sem EPSG (WKT2 gravado inteiro),
  extensão fora do território esperado, NoData suprido por banda alfa.

Um CRS que o arquivo não traz e o usuário não informa **nunca** vira "assume-se 4326". Foi a regra que mais
mudou o desenho: sem ela o pendente viraria aceito com projeção errada e o erro só apareceria no mapa.

## 5. Tamanho antes de ler, e o zip

O tamanho descompactado é ESTIMADO pelo cabeçalho — `largura × altura × bandas × itemsize` — e comparado com
a cota do inquilino ANTES de qualquer leitura de pixel. É por isso que o BigTIFF esparso de 95,4 GB virtuais
(200 kB em disco) é recusado em 0,3 s sem estourar memória.

No zip só o diretório central é lido antes de decidir: nº de entradas (≤ 1.000), soma dos tamanhos
declarados contra a cota, razão declarado/comprimido (≥ 50× = recusa), nomes de caminho (`..`, absoluto,
barra invertida, byte de controle), link simbólico, zip aninhado. **Nada é extraído antes de aprovado**, e
na extração o contador para se a entrada for maior do que o cabeçalho declarou (cabeçalho que mente para
menos).

## 6. Reaproveitamento

As checagens de CRS/tipo/NoData/extensão vieram de `validate()` de `/home/dev/plataforma/pipeline/ingest.py`,
**copiadas**: aquele arquivo é de outra frente e não foi editado. O que foi acrescentado aqui e não existe lá:
o subprocesso com limites, a assinatura de formato contra a extensão, a estimativa contra a cota, o zip, o
VRT, e a distinção `pendente` × `recusado` (lá, faltar CRS era erro).
