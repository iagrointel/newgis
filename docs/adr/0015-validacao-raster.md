# ADR 0015 — Validação e isolamento da entrada raster (item L1-01-b)

Estado: aceito (arquiteto+raster+backend, turno T3, setembro de 2026). Abre a linha L1 (imagens). Depende do
ADR 0003 (fila de jobs, filho com `RLIMIT_DATA`) e do ADR 0006 (arquivos/objetos, cota por inquilino). NÃO
converte nada: é o portão que fica ANTES da conversão para COG, da pirâmide e do tile.

Numeração: 0013/0014 podem ser tomados por outras trilhas em worktree (garage, stac) antes do merge; se
houver colisão, renumerar este arquivo e as três referências em `app/raster/` é uma troca de string.

**Revisão de setembro de 2026 (turno 3).** Um adversário independente REFUTOU a primeira versão com 9 achados
(`laco/handoffs/T3/L1-01-b-ADVERSARIO.md`): a validação saía à rede por VRT aninhado, lia arquivo de fora do
envio por três caminhos diferentes, e um raster comum com NoData `NaN` produzia relatório que o `jsonb`
recusava. As seções 3, 3.1, 5, 7, 8 e 9 abaixo são o conserto, e dizem em cada ponto o que era antes e por
que mudou. Os 23 casos de ataque dele estão em `tests/unit/test_raster_validacao_adversario.py` e passam
todos; nenhum foi apagado ou afrouxado.

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
| `RLIMIT_NOFILE` | 256 | VRT com muitas fontes e zip com muitos rasters. Era 64 e recusava um zip LEGÍTIMO a partir de ~55 arquivos (achado 9 do adversário); a causa principal, porém, era o código abrir todos ao mesmo tempo — hoje abre um de cada vez, e o teto de 256 é folga, não muleta. |
| `RLIMIT_CORE` | 0 | disco a 98 %: nenhum core dump de 768 MB. |
| relógio de parede | 90 s (`TIMEOUT_S`) | um `threading.Timer` no pai manda SIGKILL ao GRUPO (`os.setsid` no filho, `killpg`) — pega também neto (`ogr…`) que o GDAL tenha lançado. |
| `GDAL_CACHEMAX` | 64 MB | dentro do AS. |

A diferença para o ADR 0003 (`RLIMIT_DATA` no filho do job) é deliberada e não conflita: o filho do job
continua com `RLIMIT_DATA`; este subprocesso é NETO dele e ganha `RLIMIT_AS` por cima, mais apertado.

## 3. Sem rede, sem `/vsi`, sem leitura de diretório

Três camadas, cada uma provada sozinha (a primeira versão tinha só a terceira, e o adversário passou por ela):

1. **Bloqueio no processo (seccomp).** O filho recebe, entre o `fork` e o `exec` (`preexec_fn`), um filtro BPF
   clássico montado à mão que faz `socket(AF_INET, …)` e `socket(AF_INET6, …)` devolverem `EAFNOSUPPORT`;
   `AF_UNIX` e `AF_NETLINK` continuam permitidos porque a libc precisa deles. O filtro vem com
   `PR_SET_NO_NEW_PRIVS`, portanto sobrevive ao `execve` e não exige privilégio nenhum. Nenhuma dependência
   nova: é `ctypes` sobre a libc já instalada. O filho MEDE o próprio isolamento em `/proc/self/status`
   (`Seccomp: 2`, `NoNewPrivs: 1`) e escreve o resultado em `info.isolamento` do relatório — declaração
   verificável, não promessa. Se o kernel recusar o filtro, a validação continua rodando e o relatório passa
   a dizer "bloqueada apenas por variável de ambiente do GDAL": o operador vê a diferença.
2. **Ambiente do GDAL.** `GDAL_SKIP=HTTP` (tira o driver que abre `http://` direto),
   `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.nenhuma-extensao-permitida`, `GDAL_HTTP_TIMEOUT=1`,
   `GDAL_HTTP_CONNECTTIMEOUT=1`, `GDAL_HTTP_MAX_RETRY=0`, `PROJ_NETWORK=OFF` (o PROJ não busca grade de
   transformação na rede). Isto sozinho **não fecha a rede** — a lista de extensões aceita qualquer extensão
   que o próprio remetente escreva na URL, e o `http://` direto nem passa por ela. Fica como cinto, não como
   fecho.
3. **Conferência de caminho.** `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` (o GDAL não varre o diretório do envio
   procurando arquivo auxiliar), `GDAL_PAM_ENABLED=NO` (não lê nem escreve `.aux.xml` ao lado do arquivo do
   cliente), `GDAL_VRT_ENABLE_PYTHON=NO`, `GDAL_VRT_ENABLE_RAWRASTERBAND=NO`. Caminho que contenha `/vsi` é
   recusado no pai E no filho. `PLAT_DSN`/`PLAT_SECRET` são removidos do ambiente do filho: ele não fala com
   o banco.

**Por que não namespace de rede.** `unshare(CLONE_NEWUSER|CLONE_NEWNET)` funciona nesta máquina e daria uma
rede vazia, mas o kernel aqui recusa escrever `/proc/self/uid_map` (EPERM), então o filho passaria a valer
como `nobody` para efeito de permissão de arquivo e deixaria de ler envio guardado com modo restrito. O
seccomp fecha a rede sem mexer na identidade do processo, então é ele que vale.

### 3.1 VRT: conferência RECURSIVA da fonte

VRT é aceito, mas conferido como texto antes de o GDAL vê-lo. A primeira versão conferia só o VRT ENVIADO e
só o primeiro 1 MiB do XML; o adversário passou pelas duas coisas (achados 1, 2 e 3): `a.vrt` → `b.vrt` →
caminho absoluto de fora, e uma segunda banda escondida atrás de um comentário XML de 1 MiB. Hoje:

* o XML é lido INTEIRO, com teto declarado de 16 MiB (`VRT_XML_MAX`); acima disso, recusa em português;
* toda `SourceFilename` é resolvida com `os.path.realpath` — o que desfaz `..` e **ligação simbólica** — e tem
  de cair dentro do diretório do envio, comparado por prefixo real;
* fonte que também seja `.vrt` é conferida RECURSIVAMENTE, até `VRT_PROFUNDIDADE_MAX = 5` níveis, com registro
  dos já vistos: cadeia mais funda e referência circular são recusadas com mensagem própria;
* `VRTRawRasterBand` e banda derivada por função de pixel continuam recusados, em qualquer nível.

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
declarados contra a cota, razão declarado/comprimido (≥ 50× = recusa), **teto de VOLUME ligado ao tamanho do
envio**, nomes de caminho (`..`, absoluto, barra invertida, byte de controle), link simbólico, zip aninhado.
**Nada é extraído antes de aprovado**, e na extração o contador para se a entrada for maior do que o
cabeçalho declarou (cabeçalho que mente para menos).

O teto de volume é `min(cota do inquilino, 8 × tamanho do arquivo enviado + 8 MiB)`. Ele existe porque a
razão de 50× e a cota de 4 GiB, sozinhas, deixavam um envio de 1,4 MB escrever 60 MB no diretório de
trabalho do worker (achado 7 do adversário) — e um envio de ~100 MB escreveria os 4 GiB inteiros, numa
máquina a 96 % de disco. O piso de 8 MiB existe para o envio minúsculo legítimo (um zip de poucos kB com
GeoTIFF sem compressão dentro).

## 6. Reaproveitamento

As checagens de CRS/tipo/NoData/extensão vieram de `validate()` de `/home/dev/plataforma/pipeline/ingest.py`,
**copiadas**: aquele arquivo é de outra frente e não foi editado. O que foi acrescentado aqui e não existe lá:
o subprocesso com limites, a assinatura de formato contra a extensão, a estimativa contra a cota, o zip, o
VRT, e a distinção `pendente` × `recusado` (lá, faltar CRS era erro).

## 7. Nenhum defeito do arquivo sai como traceback

`rasterio._err.CPLE_AppDefinedError` **não** é `RasterioError` nem `ValueError`: um GeoTIFF sem geotransform
com CRS respondido matava o filho e devolvia ao usuário a última linha do traceback, em inglês, com o nome de
um módulo privado do rasterio (achado 8 do adversário). Hoje há três redes:

* cada abertura, cada projeção de extensão e cada leitura de janela captura `Exception` e vira problema ou
  aviso em português;
* `_inspecionar` inteiro tem uma rede final ("o arquivo não pôde ser interpretado pelo GDAL (…)");
* `_principal` (o `main` do filho) captura `Exception` e ainda assim escreve um relatório JSON — o código de
  saída continua 0, então o pai lê relatório, não traceback.

Toda mensagem vinda do GDAL ou do sistema operacional passa por `_sem_caminho()`, que troca caminho absoluto
por nome de arquivo: o usuário vê `t060.tif`, nunca `/srv/plat/trabalho/<job>/zip_extraido/t060.tif`. O texto
em inglês do GDAL continua colado depois do prefixo em português quando é a única informação existente
(`No code-stream in JP2 file`) — traduzi-lo por conta própria seria inventar diagnóstico.

## 8. NaN não é JSON

NoData `NaN` é comum em raster float32. `json.dumps` com `default=str` aceita `NaN`, `psycopg2.extras.Json`
escreve `NaN`, e o `jsonb` do Postgres recusa o documento INTEIRO — o relatório não chegava a ser gravado no
job, e falhava como erro de banco, não como recusa explicada (achado 5 do adversário). Decisão: `NaN`,
`Infinity` e `-Infinity` viram o TEXTO `"NaN"`, `"Infinity"`, `"-Infinity"` na única saída do relatório
(`_fechar`) e na saída do filho (`json.dumps(..., allow_nan=False)`, que agora falharia alto se escapasse
algum). Não viram `None`: `None` confundiria "não há NoData" com "o NoData é NaN". Quem consumir o relatório
lê `info.nodata.valor == "NaN"` e sabe o que fazer.

## 9. Fronteiras declaradas

* **Coordenada impossível.** Extensão fora do Brasil continua AVISO (o cliente pode ter imagem de fora).
  Extensão que cai fora do planeta — latitude fora de [-90, 90] ou longitude fora de [-180, 180], o que
  acontece quando o usuário responde EPSG:4674 para um arquivo em metros — passa a ser PENDÊNCIA de `crs`,
  com a sugestão de UTM na mensagem. A plataforma pergunta; não aceita com aviso (achado 6).
* **`complex64`, `complex128`, `int64`, `uint64`.** Continuam ACEITOS na validação: o arquivo está íntegro e
  a validação não é o lugar de julgar destino. Mas o relatório passa a declarar `info.tipo_convertivel:
  false` para eles, porque nenhum COG nem tile serve esses tipos — a recusa é da CONVERSÃO (item L1-01-c),
  com a lista em `TIPOS_SEM_CONVERSAO`. Sem isso o usuário só descobria na etapa seguinte, sem explicação.
* **Isolamento continua sendo processo, não máquina.** O filho roda com o mesmo usuário do sistema e enxerga,
  em leitura, todo arquivo que o worker enxerga. O que mudou é que a rede está fechada por seccomp e que a
  conferência de fonte do VRT é recursiva e resolvida por `realpath`. Confinamento de sistema de arquivos
  (namespace de montagem, contêiner por job) é outro item; enquanto não existir, a barreira de leitura de
  arquivo é a lista de conferências em Python, e isso está escrito aqui de propósito.
* **O `RLIMIT_AS` e o relógio de 90 s continuam sem prova por arquivo real.** Os testes que os exercitam usam
  o parâmetro `_prova` do próprio módulo. Nenhum arquivo fabricado pelo construtor ou pelo adversário fez o
  GDAL passar de 131 MB de pico nem de 0,5 s.

## 10. Turno 4 — os dois achados do 2º adversário

* **A conferência do VRT olha a ÁRVORE, não o texto.** Casar `<SourceFilename>` por expressão regular
  cobria uma parte do modelo: o `VRTWarpedDataset` referencia a fonte em `<SourceDataset>`, e um comentário
  XML com uma isca `<SourceFilename>` bastava para a conferência antiga achar que havia fonte legítima. O
  XML passa a ser interpretado (`xml.etree`, que não expande entidade externa) e percorrido nó a nó: valem
  os elementos que sempre apontam para dado (`SourceFilename`, `SourceDataset`, `Filename`, `Dataset`,
  `SourceDatasetName`, `MaskFilename`) e, além deles, qualquer texto ou atributo com forma de caminho
  (absoluto, `../`, `~`, esquema remoto, extensão de dado). Toda referência é resolvida por `realpath` e tem
  de cair dentro do diretório do envio; `/vsi…`, esquema remoto e byte nulo são recusados. XML que não
  interpreta é recusado. Consequência de projeto: a recusa acontece ANTES de o GDAL abrir qualquer coisa,
  então a rede deixa de ter o filtro de chamadas de sistema como única camada — com o filtro degradado, o
  VRT com `/vsicurl` continua recusado.
* **O ambiente do filho é lista de permissão.** Remover `PLAT_DSN` e `PLAT_SECRET` de `os.environ` só
  protege contra as variáveis que alguém lembrou de nomear; `PLAT_DSN_WORKER` (senha da role que escreve no
  banco) e `PLAT_GARAGE_ADMIN_TOKEN` seguiam para o processo que abre o arquivo hostil, e `AF_UNIX` passa
  pelo filtro. `ambiente_do_filho()` monta o ambiente do zero: `PATH`, `HOME`, `TMPDIR`, idioma, fuso,
  caminho de biblioteca e ambiente virtual, mais o que começa com `GDAL_`, `PROJ_`, `CPL_` ou `OGR_`, e
  por cima o `AMBIENTE_FILHO`. Variável nova do worker fica de fora por padrão, não por lembrança.
* **O que continua valendo.** O isolamento segue sendo de processo: `AF_UNIX` não é bloqueado (a libc
  precisa) e o filho lê, em leitura, os arquivos que o worker lê. O que mudou é que já não existe credencial
  no ambiente dele para transformar esse soquete em acesso ao banco.
