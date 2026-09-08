# L1-01-b — relatório do SEGUNDO ADVERSÁRIO (validação e isolamento da entrada raster)

**VEREDITO: REFUTADO.**

O primeiro adversário refutou o item; o construtor consertou e trocou o mecanismo (seccomp BPF por `ctypes`,
`_conferir_vrt` recursivo com `realpath`, NaN em texto, teto de volume do zip). Ataquei o MECANISMO NOVO. Ele
melhorou muito — mas dois furos graves continuam abertos, e um deles é o ACHADO 1 do primeiro laudo renascido
por outra porta, agora com o filtro de chamadas de sistema LIGADO.

**Os dois achados:**

1. **A conferência de VRT só casa `<SourceFilename>`.** Um VRT do tipo transformado (`VRTWarpedDataset`)
   esconde a fonte em `<SourceDataset>`, que não passa por conferência nenhuma. Um arquivo enviado lê arquivo
   de fora do diretório do envio, com o seccomp ligado. **O achado 1 renasceu.**
2. **`PLAT_DSN_WORKER` e `PLAT_GARAGE_ADMIN_TOKEN` vazam para o ambiente do processo filho** (só `PLAT_DSN` e
   `PLAT_SECRET` são removidos). Como o filtro permite soquete local, o filho **conectou no Postgres**. A frase
   "o filho nunca fala com o banco" é falsa.

**E o que muda a leitura de risco do item inteiro, não é nota de rodapé:**

> **O filtro de chamadas de sistema é a ÚNICA coisa segurando a saída para a rede.** As variáveis do GDAL não
> seguram: `CPL_VSIL_CURL_ALLOWED_EXTENSIONS` aceita a extensão que o próprio atacante escreve na URL, e
> `GDAL_SKIP=HTTP` não cobre o `/vsicurl`. Medi o mesmo pedido com o filtro ligado e desligado: ligado, o
> soquete nem é criado; **desligado, o mesmo VRT fez a validação disparar pedido para o meu ouvinte.** Logo o
> item não tem defesa em profundidade na rede: tem uma camada só. Se o filtro não instalar (libc fora do lugar,
> kernel sem `CONFIG_SECCOMP_FILTER`, outra arquitetura), a validação **continua rodando** e a requisição
> forjada volta, sem recusa e sem aviso — só uma linha em `info.isolamento`.

Arquivo de teste: `tests/unit/test_raster_validacao_adversario2.py` — **12 casos: 9 passam (defesas que
seguraram) e 3 são `xfail(strict=True)`** (os dois furos acima; H1 rende dois casos). `strict` faz o conserto
virar falha do marcador, então nenhum achado se perde.

```
cd /home/dev/plataforma/wt/valida
set -a; source /home/dev/plataforma/laco/var/trilha/valida.env; set +a   # trilha própria: sem flock
venv/bin/pytest tests/unit/test_raster_validacao_adversario2.py -q -rxX
# xx....x.....   (9 passed, 3 xfailed)
venv/bin/pytest tests/unit/test_raster_validacao.py tests/unit/test_raster_validacao_adversario.py \
                tests/unit/test_raster_validacao_adversario2.py -q -p no:warnings
# .......................................................xx....x.....   (64 passed, 3 xfailed)
venv/bin/ruff check tests/unit/test_raster_validacao_adversario2.py
# All checks passed!
```

Ambiente: rasterio 1.5.0 / GDAL 3.12.1 / Python 3.12.3 / x86_64 / kernel com `CONFIG_SECCOMP_FILTER=y`.

---

## ACHADO H1 (grave) — o VRT transformado lê arquivo fora do envio

`_conferir_vrt` (validacao.py:523) procura fontes com
`_RE_FONTE_VRT = re.compile(r"<SourceFilename([^>]*)>(.*?)</SourceFilename>", re.S)`.

O `VRTWarpedDataset` não usa `<SourceFilename>`: a fonte dele fica em
`<GDALWarpOptions><SourceDataset>`. Esse elemento **não é lido por ninguém**. Basta que o regex encontre
*alguma* `<SourceFilename>` válida para a conferência passar — e ele não respeita comentário XML, então a isca
pode estar dentro de `<!-- -->`, invisível para o GDAL e visível para o regex.

Arquivo do ataque (`_vrt_warped()` no meu teste; o molde saiu de `gdal.Warp(..., format="VRT")`):

```xml
<VRTDataset ... subClass="VRTWarpedDataset">
  <!-- <SourceFilename relativeToVRT="1">bom.tif</SourceFilename> -->   <- isca: existe DENTRO do envio
  ...
  <GDALWarpOptions>
    <SourceDataset relativeToVRT="0">/tmp/.../fora/segredo.tif</SourceDataset>   <- fonte REAL, fora do envio
```

Medido:

```
estado: pendente | problemas: [] | bandas: 1
PIXEL FORA DO ENVIO LIDO: 222
```

O arquivo `fora/segredo.tif` (pixel 222) está fora do diretório do envio, é aberto e tem pixel lido **dentro da
validação** (a janela de prova do `_inspecionar`). O relatório sai `pendente` — quer dizer, aceito, só pedindo
CRS/NoData. Nenhum `problemas`.

O alcance é o mesmo que o primeiro adversário descreveu: como todos os inquilinos são atendidos pelo mesmo
usuário do sistema, vale todo arquivo raster que o worker enxerga, inclusive o diretório de trabalho de outro
job. Teste: `test_vrt_warped_sourcedataset_nao_deve_ler_arquivo_fora_do_envio`.

**Observação de escopo:** não testei `VRTPansharpenedDataset`, que também referencia fonte por elemento próprio.
A correção certa não é acrescentar `<SourceDataset>` ao regex, é conferir **toda** referência de arquivo do XML.

### H1b — com o filtro degradado, o mesmo arquivo bate na rede

O `<SourceDataset>` não conferido aceita `/vsicurl/`. Com o filtro instalado, o pedido morre no `socket()`. Com
o filtro degradado (`_fechar_a_rede` devolvendo `False`, que é o que acontece se a libc/kernel/arquitetura não
cooperarem), o pedido sai:

```
validar() warped/vsicurl, seccomp OFF -> recusado ['o GDAL não abriu chain.vrt: GDALWarpOptions.Validate(): hSrcDS is not set.']
isolamento: 0 | PEDIDOS: ['HEAD /x.nenhuma-extensao-permitida HTTP/1.1']
```

O ouvinte em 127.0.0.1, criado pelo próprio teste, **recebeu o pedido**. O relatório diz `recusado` só porque
devolvi 404 — a requisição forjada já tinha saído, e o caminho da URL é canal de saída de dado. O alvo pode ser
endereço interno (serviço de metadados da nuvem, `plat-api` na 8150, o próprio Postgres).

Teste: `test_vrt_warped_com_seccomp_degradado_nao_deve_bater_na_rede`.

### Prova de que o filtro é a única camada

Chamei o GDAL direto num filho preparado por `_preparar_filho()` (conferência de VRT fora do caminho), com a
extensão que a allowlist do GDAL aceita — a que o atacante escolhe:

```
seccomp ON  ext-permitida -> RasterioIOError CURL error: failed to open socket: Address f… | PEDIDOS: []
seccomp OFF ext-permitida -> RasterioIOError HTTP response code: 404                       | PEDIDOS: ['HEAD /x.nenhuma-extensao-permitida HTTP/1.1']
```

Com `.tif` (extensão fora da allowlist) nenhum dos dois sai — mas a extensão é escolha de quem escreve a URL,
então isso não é defesa. Teste que registra a medida: `test_seccomp_e_a_barreira_de_rede_ligado_bloqueia_desligado_libera`
(passa, e falha de propósito se um dia a rede fechar sem o filtro — aí a tese muda).

---

## ACHADO H2 (grave) — segredos do worker no ambiente do filho, e soquete local aberto

`_executar_filho` monta `ambiente = {**os.environ, **AMBIENTE_FILHO}` e remove **só dois** nomes:

```python
ambiente.pop("PLAT_DSN", None)  # o filho nunca fala com o banco
ambiente.pop("PLAT_SECRET", None)
```

O `.env` da trilha (e o do worker) traz também **`PLAT_DSN_WORKER`** — a DSN da role `plat_worker`, a única que
muda estado de job, com senha embutida — e **`PLAT_GARAGE_ADMIN_TOKEN`**. Nenhum dos dois é removido. Medido no
filho preparado:

```
{"status": ["NoNewPrivs:\t1", "Seccomp:\t2"],
 "PLAT_DSN_WORKER": "postgresql://plat_worker:SENHA_SECRETA@127.0.0.1/iagro_sat",
 "PLAT_GARAGE_ADMIN_TOKEN": "tok3n-admin-do-garage",
 "PLAT_DSN": null,
 "AF_INET": "[Errno 97] Address family not supported by protocol",
 "AF_INET6": "[Errno 97] Address family not supported by protocol",
 "AF_UNIX": "criou", "AF_NETLINK": "criou", "AF_PACKET": "[Errno 1] Operation not permitted",
 "unix_postgres": "CONECTOU"}
```

Duas coisas juntas: a credencial de escrita está lá, **e** o filtro cobre só `AF_INET`/`AF_INET6`, então
`AF_UNIX` passa e o filho **conectou no soquete local do Postgres** (`/var/run/postgresql/.s.PGSQL.5432`). O
comentário "o filho nunca fala com o banco" descreve uma intenção, não uma barreira: o que impede hoje é o filho
não executar código do atacante, não o isolamento.

`AF_UNIX` liberado é decisão defensável (a libc precisa dele) — o defeito é a **denylist de ambiente**. A
correção é allowlist: montar o ambiente do filho do zero com os nomes que ele precisa, em vez de copiar
`os.environ` e tirar dois.

Testes: `test_segredos_do_worker_nao_devem_vazar_para_o_filho` (xfail estrito) e
`test_seccomp_deixa_af_unix_passar_documenta_a_fronteira` (passa, registra o fato).

---

## ATAQUE 7 (medida) — o pico de RAM não é propriedade do arquivo

Recomputei. **O tempo confere**: mediana 0,29 s contra 0,2975 s do `tests/medidas/L1-01-b.json`. **O pico de RAM
não é reprodutível como número do item.** O `ru_maxrss` do `os.wait4` conta as páginas que o filho herda do PAI
no fork (o `preexec_fn` força fork antes do exec), então o valor segue o tamanho do worker, não o do raster.
Medido engordando o próprio pai:

```
pai magro   : pai VmRSS=91552  kB -> filho ru_maxrss=91668  kB  tempo=0.298
pai +64 MB  : pai VmRSS=157124 kB -> filho ru_maxrss=116192 kB  tempo=0.296
pai +128 MB : pai VmRSS=222692 kB -> filho ru_maxrss=181764 kB  tempo=0.297
```

E o mesmo caso, medido dentro da suíte inteira (pytest com os três módulos carregados), deu **144.528 kB** contra
**91.664 kB** isolado — 57 % de diferença, sem trocar o arquivo validado.

Duas consequências honestas:
* o número de RAM do `tests/medidas/L1-01-b.json` (mediana 90.694–95.694 kB, e o arquivo é regravado a cada
  execução) só vale sob um pai do tamanho do pytest; num worker real ele muda;
* mais importante: **o `RLIMIT_AS` de 768 MB é contado a partir de um espaço de endereçamento que já vem cheio
  do pai.** Quanto mais gordo o worker, menos folga sobra para o GDAL dentro do mesmo teto. Não é refutação de
  cláusula do portão — é leitura de risco que não estava escrita.

Teste: `test_medida_recomputada_e_o_pico_de_ram_nao_e_propriedade_do_ARQUIVO`.

---

## O que resistiu (ataques meus que o mecanismo novo segurou)

| ataque | medida | conclusão |
|---|---|---|
| `socket(AF_INET/AF_INET6)` no filho | `errno 97` (EAFNOSUPPORT) nos dois | filtro funciona |
| `AF_PACKET` | `[Errno 1]` EPERM | bloqueado (por privilégio, não pelo filtro) |
| **descritor de soquete HERDADO do pai** (o furo clássico: o filtro impede criar, não usar) | `fd fechado: [Errno 9] Bad file descriptor` | fechado — mas pelo `close_fds` padrão do `Popen`, **não** pelo filtro |
| VRT `SimpleSource` 7 níveis (um a mais que o limite) | `recusado: VRT aninhado além de 5 níveis` | segurou |
| VRT `SimpleSource` por ligação simbólica para fora | `recusado: VRT com fonte fora do diretório do envio` | segurou (`realpath`) |
| VRT `SimpleSource` `../` que sai de vez | recusado | segurou |
| VRT `SimpleSource` `..` que sai e VOLTA para dentro | `pendente` (legítimo, aceito) | correto |
| VRT com byte nulo no nome da fonte | recusado (`ValueError` virou recusa em português) | segurou |
| VRT de 16 MiB − 1 com a fonte hostil no FIM do XML | recusado (XML lido inteiro; o corte de 1 MiB morreu) | segurou |
| zip aninhado em 2 níveis | `recusado: zip aninhado não é aceito: 'inner.zip'` | segurou |
| zip com entrada de nome `../escapou.tif` | recusado; `escapou.tif` não existe fora | segurou |
| zip legítimo de 200 rasters | aceito; disco escrito dentro do teto | segurou (achado 9 do 1º laudo, consertado) |
| zip que mente no cabeçalho para mais | a extração corta em `restante < 0`; o `ZipExtFile` já limita ao `file_size` | segurou |
| zip de razão alta (648×) | `recusado: razão de compressão de 648× (limite 50×)` | segurou |
| NoData `NaN` | vira o texto `"NaN"`; `json.dumps(allow_nan=False)` passa | segurou (achado 5 consertado) |
| NoData informado `1e400` | vira `"Infinity"`; JSON estrito passa | segurou |
| NoData `-0.0` | preservado como número `-0.0`; JSON estrito passa | segurou |
| NoData `NaN` em banda de INTEIRO | vetor vazio: na criação o rasterio recusa; gravado depois, o GDAL descarta (`nodata is None`) | não existe |
| filtro degradado | relatório grava `seccomp: 0` e troca o texto da rede | **não é silêncio** — mas não recusa e não emite aviso |

### Sobre o ponto 3 do meu encargo (falso senso de segurança)

Não confirmei "prossegue em silêncio". Quando o filtro não instala, o relatório **não** mente: grava
`seccomp: 0` e troca `info.isolamento.rede` para "bloqueada apenas por variável de ambiente do GDAL". Isso é
melhor do que eu esperava achar. O que **falta** é consequência: a validação não recusa, não emite `avisos` nem
`pendencias`, e nada no `resumo()` menciona. Quem lê o relatório pelo estado (`aceito`/`pendente`) não vê
diferença nenhuma entre um arquivo validado com a rede fechada e um validado com a rede aberta. Registrado em
`test_seccomp_degradado_e_registrado_no_relatorio` (passa, e a última asserção documenta a ausência do aviso).

### Sobre o buraco de arquitetura no BPF (não explorável AQUI)

O programa BPF começa com "arquitetura diferente → permite" (`(jeq, 0, 6, arch)` salta para `ALLOW`). Num
processo i386 ou x32 o `socket()` passaria inteiro. **Não é explorável nesta máquina**: `CONFIG_X86_X32_ABI is
not set` e o filho é `python3` de 64 bits, sem caminho conhecido para executar binário de 32 bits. Fica como
forma, não como achado — mas é o motivo pelo qual "arquitetura diferente" devia ser `KILL`, não `ALLOW`.

---

## O que continua SEM PROVA (fronteira honesta)

1. **Isolamento continua sendo processo, não máquina.** Mesmo usuário do sistema, sem namespace, leitura de todo
   arquivo do worker. H1 e H2 são consequência direta. A barreira é a lista de conferências em Python mais um
   filtro de uma linha, não o sistema operacional.
2. **`VRTPansharpenedDataset` não testado** — referencia fonte por elemento próprio, e a mesma classe de furo do
   H1 pode valer; não construí o caso.
3. **`RLIMIT_AS` e o relógio de 90 s seguem sem prova por arquivo real.** A observação 2 e 3 do primeiro
   adversário continua de pé; meu maior pico com arquivo hostil foi 181 MB, e isso por causa do pai, não do
   arquivo.
4. **Não achei jeito de fazer o `<SourceDataset>` alcançar o Postgres pelo `AF_UNIX`**: `PG:` como fonte do warp
   morre em `GDALWarpOptions.Validate(): hSrcDS is not set`. O `AF_UNIX` está aberto e a credencial está no
   ambiente, mas **não liguei os dois por um arquivo enviado** — H2 é exposição, não cadeia de exploração
   fechada. Digo isso com todas as letras para não vender mais do que medi.
5. **Nada foi provado pela fila real**: chamei `validar()` direto, sem worker, sem RLS, sem dois jobs
   concorrendo no mesmo `zip_extraido`.
6. **Não olhei** rota HTTP, conversão (COG/pirâmide/tile) nem antivírus: fora do item.
7. **`make sem-marcador` não varre `tests/`** — observação do primeiro adversário, ainda verdadeira.

## Correção mínima que eu exigiria antes de dar o item por pronto

1. Conferir **toda** referência de arquivo do XML do VRT — `<SourceDataset>` inclusive —, e recusar VRT cujo
   XML tenha referência que a conferência não saiba interpretar (lista de permissão, não de proibição).
2. Montar o ambiente do filho por **allowlist**, do zero. Hoje `PLAT_DSN_WORKER` e `PLAT_GARAGE_ADMIN_TOKEN`
   viajam junto.
3. Decidir o que fazer quando o filtro não instala. Hoje segue com a rede aberta e uma nota em `info`. Ou recusa,
   ou vira `problema`/`aviso` visível no estado — porque, medido, o filtro é a única camada de rede que existe.
4. `KILL` em vez de `ALLOW` para arquitetura não reconhecida no BPF.
5. Parar de tratar `ram_pico_kb` como número do item: ou mede o filho descontando o pai, ou o arquivo de medidas
   diz que o valor depende do worker.

## Higiene

* `venv/bin/ruff check tests/unit/test_raster_validacao_adversario2.py` → `All checks passed!`
* Rodei os três arquivos do item juntos: **64 passed, 3 xfailed**, nenhum teste do construtor nem do primeiro
  adversário quebrado pelo meu arquivo.
* Não toquei em código de produção. `tests/medidas/L1-01-b.json` é regravado pela suíte do construtor a cada
  execução; restaurei com `git checkout --` para não sujar o commit.
* Meu arquivo cria só diretórios do `tmp_path` do pytest e ouvintes em `127.0.0.1` com porta 0 (efêmera), que
  ele mesmo desliga.
