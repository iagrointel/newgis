# L1-01-b — CONSERTO do laudo do adversário

Ramo `wt/valida`, worktree `/home/dev/plataforma/wt/valida`. Três commits em cima do `b62d88a`
(o commit do adversário):

| commit | o que traz |
|---|---|
| `8be23a6` | `app/raster/validacao.py` consertado (os 9 achados) |
| `50611ed` | os 9 `xfail(strict=True)` saem; 7 casos novos no arquivo do construtor; medidas regravadas |
| `e5c0885` | ADR 0015 revisado (seções 3, 3.1, 5, 7, 8, 9) e entrada no CHANGELOG |

**Resultado: `55 passed`** — 23 casos do adversário (todos, nenhum apagado ou afrouxado) + 32 do
construtor (25 originais + 7 novos). `ruff check app tests` limpo, `make sem-marcador` rc=0.

```
cd /home/dev/plataforma/wt/valida
set -a; source /home/dev/plataforma/laco/var/trilha/valida.env; set +a
venv/bin/pytest tests/unit/test_raster_validacao.py tests/unit/test_raster_validacao_adversario.py -q
# 55 passed, 2 warnings in 24.65s
```

Sobre o marcador: os 23 testes do adversário estão byte a byte iguais aos de `b62d88a`, exceto os 9
decoradores `@pytest.mark.xfail(strict=True, reason=…)`, que viraram comentário `# ACHADO N: …` com o
texto integral do motivo em cima do teste correspondente, mais um bloco no docstring do arquivo dizendo
quando e por que saíram. `git diff b62d88a -- tests/unit/test_raster_validacao_adversario.py` mostra que
nenhuma linha de asserção mudou.

---

## Achado → conserto → prova

### ACHADO 4 (grave) — "sem rede" era falso

**Conserto.** Três camadas, cada uma provada sozinha (ADR 0015 §3):
1. **seccomp no processo filho.** Filtro BPF clássico montado à mão com `ctypes` sobre a libc (nenhuma
   dependência nova, `pyseccomp` não foi instalado) aplicado no `preexec_fn`: `socket(AF_INET, …)` e
   `socket(AF_INET6, …)` devolvem `EAFNOSUPPORT`; `AF_UNIX`/`AF_NETLINK` seguem permitidos porque a libc
   precisa deles. Vem com `PR_SET_NO_NEW_PRIVS`, então sobrevive ao `execve` e não exige privilégio.
2. **ambiente**: `GDAL_SKIP=HTTP` (tira o driver que abre `http://` direto), `PROJ_NETWORK=OFF`,
   `GDAL_HTTP_CONNECTTIMEOUT=1`, mais os que já existiam.
3. **conferência de caminho** (achados 1-3, abaixo).

**Namespace de rede foi testado e recusado, com medida.** `unshare(CLONE_NEWUSER|CLONE_NEWNET)` funciona
nesta máquina (rc=0, `connect` devolve `ENETUNREACH`), mas o kernel recusa escrever `/proc/self/uid_map`
(`EPERM`) e `/proc/self/setgroups` (`EACCES`): sem mapa de uid o filho passa a valer como `nobody` (uid
65534) para permissão de arquivo e deixaria de ler envio guardado com modo restrito. `unshare -rn` falha
pelo mesmo motivo. O seccomp fecha a rede sem mexer na identidade do processo — por isso é ele que vale, e
está escrito assim no ADR.

**Prova A — o ataque original, com o mesmo tipo de ouvinte em 127.0.0.1**, quatro caminhos (`/vsicurl` e
`http://`, direto e por VRT aninhado):

```
vsicurl direto       -> recusado: VRT com fonte fora do diretório do envio ou remota: '/vsicurl/http://127.0.0.1:46355/x.nen
http direto          -> recusado: VRT com fonte fora do diretório do envio ou remota: 'http://127.0.0.1:46355/y.tif'
vsicurl aninhado     -> recusado: VRT com fonte fora do diretório do envio ou remota: '/vsicurl/http://127.0.0.1:46355/z.nen
http aninhado        -> recusado: VRT com fonte fora do diretório do envio ou remota: 'http://127.0.0.1:46355/w.tif'
PEDIDOS RECEBIDOS PELO OUVINTE: []
isolamento medido no /proc do filho: {'seccomp': 2, 'no_new_privs': 1, 'rede': 'bloqueada no processo (seccomp: socket AF_INET/AF_INET6 devolve EAFNOSUPPORT)'}
```

**Prova B — a camada de conferência DESLIGADA**, chamando o GDAL direto dentro de um filho preparado por
`v._preparar_filho()`, para mostrar que o seccomp segura sozinho:

```
/vsicurl/http://127.0.0.1:45997/a.tif -> RasterioIOError '…' does not exist in the file system, and i
http://127.0.0.1:45997/b.tif         -> RasterioIOError '…' does not exist in the file system, and i
/vsis3/balde/c.tif                    -> RasterioIOError …
/vsigs/balde/d.tif                    -> RasterioIOError …
socket cru -> [Errno 97] Address family not supported by protocol
PEDIDOS RECEBIDOS: []
```

O filho MEDE o próprio isolamento em `/proc/self/status` e grava `info.isolamento` no relatório
(`seccomp: 2`, `no_new_privs: 1`). Se um dia o kernel recusar o filtro, a validação continua rodando e o
relatório passa a dizer "bloqueada apenas por variável de ambiente do GDAL" — o operador vê a diferença
em vez de achar que está protegido. Teste: `test_rede_fechada_no_processo_e_medida_no_proc_do_filho`.

### ACHADOS 1, 2 e 3 (graves) — VRT lia arquivo de fora do envio

**Conserto** (`_conferir_vrt`, ADR 0015 §3.1): XML lido INTEIRO com teto declarado de 16 MiB
(`VRT_XML_MAX`; acima disso recusa em português), `SourceFilename` lida com o atributo `relativeToVRT`,
resolvida com `os.path.realpath` (desfaz `..` **e ligação simbólica**) e obrigada a cair dentro do
diretório do envio por comparação de prefixo real; fonte que também é `.vrt` é conferida
RECURSIVAMENTE até `VRT_PROFUNDIDADE_MAX = 5`, com registro dos já vistos (referência circular tem
mensagem própria). `VRTRawRasterBand` e função de pixel seguem recusados em todos os níveis.

```
A1 vrt aninhado para fora -> VRT com fonte fora do diretório do envio ou remota: '/tmp/…/fora/segredo.tif'
A2 fonte depois de 1 MiB  -> VRT com fonte fora do diretório do envio ou remota: '/tmp/…/fora/segredo.tif'
A3 fonte por link         -> VRT com fonte fora do diretório do envio ou remota: 'link.tif'
```

Testes novos do construtor: `test_vrt_aninhado_so_e_aceito_dentro_do_envio` (o caso legítimo — VRT que
aponta para VRT DENTRO do envio — continua `aceito`), `test_vrt_circular_e_profundo_demais_recusados`,
`test_vrt_com_xml_acima_do_teto_recusado`.

### ACHADO 5 (grave) — NoData NaN quebrava a gravação

**Conserto** (ADR 0015 §8): `NaN`, `Infinity` e `-Infinity` viram o TEXTO `"NaN"`, `"Infinity"`,
`"-Infinity"` na única saída do relatório (`_fechar`, por onde passam todos os caminhos, inclusive as
recusas do pai) e na saída do filho, que agora escreve com `allow_nan=False` — se algum escapar, falha
alto em vez de silencioso. **Não** viram `None`: `None` confundiria "não há NoData" com "o NoData é NaN".

```
A5 nodata NaN -> aceito {'valor': 'NaN', 'origem': 'arquivo'} | json estrito: True
```

O teste do adversário só exige `json.dumps(allow_nan=False)`. Acrescentei prova mais forte, que é a que o
laudo pedia — o relatório ATRAVESSANDO o `jsonb` de verdade, pelo mesmo caminho do worker
(`psycopg2.extras.Json`), com a role da aplicação: `test_nodata_nan_grava_no_jsonb_do_banco`.

### ACHADO 6 (médio) — extensão geograficamente impossível

**Conserto**: latitude fora de [-90, 90] ou longitude fora de [-180, 180] (ou valor não finito) vira
PENDÊNCIA de `crs`, com a sugestão de UTM na mensagem. "Fora do Brasil" continua AVISO, porque o cliente
pode ter imagem de fora — o teste `test_extensao_fora_do_brasil_avisa` do construtor segue passando.

```
A6 latitude 7.400.000 -> pendente | a extensão do arquivo no CRS EPSG:4674 (informado) cai fora do planeta ([300000.0, 7399920.0, …
```

### ACHADO 7 (médio) — a conta da bomba zip era razão, não volume

**Conserto** (ADR 0015 §5): teto de VOLUME `min(cota do inquilino, 8 × tamanho do arquivo enviado +
8 MiB)`, conferido **antes** de criar `zip_extraido`. O piso de 8 MiB existe para o envio minúsculo
legítimo (zip de poucos kB com GeoTIFF sem compressão dentro).

```
A7 zip 1,4 MB -> 25 MB -> recusado | escrito no disco: 0 bytes (envio 639945)
   zip de 625 kB declara 24.6 MB descompactados, acima do teto de 12.9 MB para um envio desse tamanho
   (8× o enviado mais 8.0 MB); nada foi descompactado
```

Teste novo: `test_zip_com_volume_desproporcional_ao_envio_recusado` (razão 13×, abaixo dos 50×, e ainda
assim recusado por volume — prova que o teto novo é o que decide, não a razão antiga).

### ACHADO 8 (médio) — traceback cru em inglês

**Conserto** (ADR 0015 §7): `rasterio._err.CPLE_AppDefinedError` não é `RasterioError` nem `ValueError`.
Agora há três redes: cada abertura/projeção/leitura captura `Exception`; `_inspecionar` inteiro tem uma
rede final; e `_principal` (o `main` do filho) captura `Exception` e ainda assim escreve relatório JSON,
então o código de saída continua 0 e o pai lê relatório, nunca traceback. Toda mensagem vinda do GDAL/SO
passa por `_sem_caminho()`.

```
A8 sem geotransform -> aceito | codigo_saida 0 | não foi possível projetar a extensão para EPSG:4326: latitude max < latitude min.
```

### ACHADO 9 (médio) — zip legítimo de 200 rasters recusado em inglês, com caminho do servidor

**Conserto**: `_inspecionar` abre **um arquivo de cada vez** (1ª passagem só cabeçalho, 2ª só a janela de
prova) em vez de manter todos abertos; `RLIMIT_NOFILE` sobe de 64 para 256 como folga; `_sem_caminho()`
troca caminho absoluto por nome de arquivo em toda mensagem do GDAL/SO.

```
A9 zip com 200 rasters -> aceito | bandas 200 | problemas []
```

### Fronteira `complex64`/`int64` — decidida e declarada

Continuam ACEITOS na validação (o arquivo está íntegro; a validação não julga destino), mas o relatório
passa a trazer `info.tipo_convertivel: false`, com a lista em `TIPOS_SEM_CONVERSAO` (`complex64`,
`complex128`, `complex_int16`, `int64`, `uint64`): a recusa é da CONVERSÃO (L1-01-c). Escolhi não emitir
aviso porque isso quebraria `test_tipo_de_dado_exotico_passa_sem_uma_palavra`, que é teste do adversário
e não podia ser afrouxado — a informação passa a existir no relatório sem mexer numa asserção dele.

```
F complex64 -> aceito | tipo_convertivel: False
```

Teste novo: `test_tipo_sem_conversao_e_declarado_no_relatorio`. ADR 0015 §9.

---

## Reparos de exatidão que o adversário pediu no texto

* `tests/unit/test_raster_validacao.py` citava "ADR 0012"; corrigido para **0015** em todo o arquivo.
* A faixa de pico de RSS ("87,1 a 130,4 MB") está errada no handoff antigo — o mínimo do próprio arquivo
  de medidas é 79,5 MB. A entrada nova do CHANGELOG não repete a faixa.
* `tests/medidas/L1-01-b.json` é regravado pela suíte a cada execução (agora com 40 casos, era 33): o
  ruído entre execuções é do gerador, não regressão. Fica registrado; não mexi no gerador para não
  mudar o contrato do arquivo no meio do turno.

## O que NÃO foi consertado, e por quê

* **Isolamento continua sendo processo, não máquina.** O filho roda com o mesmo usuário do sistema e
  enxerga, em leitura, todo arquivo que o worker enxerga. Fechei a rede e a leitura POR VRT; confinamento
  de sistema de arquivos (namespace de montagem, contêiner por job) não cabe neste item e está declarado
  na §9 do ADR como fronteira aberta.
* **`RLIMIT_AS` e o relógio de 90 s continuam sem prova por arquivo real** — a observação 2 e 3 do
  adversário segue de pé. Nenhum arquivo fabricado por ele ou por mim fez o GDAL passar de 131 MB de pico
  nem de 0,5 s.
* **`preexec_fn` + `stdout` lido até EOF antes do `stderr`**: risco de forma que ele apontou (item 4 da
  fronteira dele) e que continua existindo; não consegui produzir os 64 kB de `stderr` necessários.
* **O job na fila real** continua sem e2e (a trilha roda em worktree e não sobe worker que dispute a fila
  de produção). O caminho que quebrava — relatório → `jsonb` — agora tem teste que atravessa o banco.
* **`make sem-marcador` não varre `tests/`** — observação dele, que continua verdadeira.

## Para o adversário reproduzir

```
cd /home/dev/plataforma/wt/valida && git log --oneline -4
set -a; source /home/dev/plataforma/laco/var/trilha/valida.env; set +a   # trilha própria: sem flock
venv/bin/pytest tests/unit/test_raster_validacao_adversario.py -q -rxX   # 23 passed
venv/bin/pytest tests/unit/test_raster_validacao.py -q                   # 32 passed
venv/bin/ruff check app tests
make sem-marcador
git diff b62d88a -- tests/unit/test_raster_validacao_adversario.py       # só docstring e marcadores
```

Quatro testes de `tests/unit` falham nesta trilha e **não são deste item**: eles falham igual no commit
`b62d88a` (conferido com `git stash`). `test_jobs_registro.py::test_tipos_de_prova_estao_registrados`
cai em `raster.validar: memoria_mb=1024 fora de [128, 512] (teto PLAT_WORKER_MEMORIA_MB)` — vazamento de
`monkeypatch` entre módulos quando a suíte roda inteira; `test_versao.py` (2) e `test_vendor.py` (1) são
do ambiente de worktree. Rodados isolados, os arquivos do item passam.
