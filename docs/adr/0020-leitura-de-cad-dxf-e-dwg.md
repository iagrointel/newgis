# ADR 0020 — Leitura de CAD: DXF pelo GDAL, DWG por conversão prévia (item L0-04-e)

Estado: aceito (dados, backend, testador, adversário; turno T3, setembro de 2026). Fecha os dois formatos de
desenho da ingestão vetorial (ADR 0005 seção 10, que os deixava de fora). Depende do ADR 0015 (validação e
isolamento de entrada raster): o mecanismo de subprocesso é o mesmo, aplicado a programa externo.

Numeração: 0016 e 0018 já foram tomados por duas trilhas cada antes do merge; se 0020 colidir, renumerar este
arquivo e as referências em `app/ingestao/` é troca de string.

## 1. O que entra e o que fica de fora

Entra: **DXF de texto** (ASCII), lido pelo driver DXF do GDAL, e **DWG**, convertido antes para DXF pelo
`dwg2dxf` do GNU LibreDWG (GPL-3), em processo separado. Fica de fora, declarado: DXF binário (o driver do GDAL
não lê — a recusa diz isso e manda gravar em ASCII), e o ODA File Converter (seção 7).

## 2. Isolamento: o mesmo do ADR 0015, aplicado a programa externo

O arquivo é do cliente e o GDAL abre o que o cabeçalho mandar. O adversário do item L1-01-b provou que a
validação saía à rede por VRT aninhado e lia arquivo de fora do envio por três caminhos. DXF tem a mesma
superfície (é texto que o GDAL interpreta) e o DWG passa ainda por um decodificador em C de terceiro. Logo:

* o **pai** (`app/ingestao/cad.py`) só usa `open()` puro: assinatura de formato nos primeiros 64 bytes, versão
  do DWG nos 6 primeiros, e a seção HEADER do DXF com leitura limitada a `HEADER_MAX` = 2 MiB;
* o **filho** é `ogrinfo`/`ogr2ogr`/`dwg2dxf`, lançado por `app/ingestao/isolamento.py`: filtro seccomp em BPF
  clássico que faz `socket(AF_INET/AF_INET6)` devolver `EAFNOSUPPORT`, `PR_SET_NO_NEW_PRIVS` (sobrevive ao
  `execve`), `RLIMIT_AS` 768 MB, `RLIMIT_CPU` 60 s, `RLIMIT_NOFILE` 256, `RLIMIT_CORE` 0, `os.setsid()` +
  `killpg` no relógio de parede de 90 s, ambiente do GDAL sem driver HTTP, sem PROJ na rede, sem varredura de
  diretório, sem PAM, e `PLAT_DSN`/`PLAT_SECRET` removidos;
* todo caminho passa por `isolamento.caminho_dentro()`: `realpath` (desfaz `..` e ligação simbólica) e prefixo
  do diretório do envio; `/vsi` é recusado antes de chegar ao GDAL.

O isolamento é **medido**, não prometido: `isolamento.isolamento_declarado()` roda um filho de prova e lê
`/proc/self/status` dele (`Seccomp: 2`, `NoNewPrivs: 1`); o valor entra na proposta da importação
(`proposta.cad.isolamento`) e o e2e falha se não for 2.

Duplicação assumida: `app/raster/validacao.py` (ramo do L1-01-b) tem hoje a sua própria cópia dessas
primitivas. Quando os dois ramos entrarem em `master`, aquele módulo passa a importar deste — está no handoff
do item como pendência de merge, com o nome das funções.

## 3. Três coisas que só se souberam medindo

1. **`DXF_INLINE_BLOCKS` e `DXF_ENCODING` são opção de CONFIGURAÇÃO (`--config`), não de abertura (`-oo`).**
   Com `-oo DXF_ENCODING=UTF-8` o nome de camada acentuado continua saindo trocado; com
   `--config DXF_ENCODING UTF-8` sai certo. Por isso o preparador da ingestão ganhou um campo `config` ao lado
   do `oo`, e `_cfg()` traduz a lista em `--config CHAVE VALOR`.
2. **O DXF mente sobre a própria codificação.** O arquivo de teste declara `$DWGCODEPAGE ANSI_1252` no
   cabeçalho e grava os nomes de camada em UTF-8 — é o que o gerador mais usado do mercado faz. Decisão: quem
   decide é o BYTE (se a parte não-ASCII é UTF-8 válida, é UTF-8); o cabeçalho vira segunda opinião, gravada em
   `codificacao.declarada`, e a divergência sai como aviso na proposta.
3. **Bloco aninhado não precisa de ezdxf.** A hipótese do item admitia trazer o `ezdxf` se o driver do GDAL não
   desse conta de bloco dentro de bloco. Dá: um INSERT de `CONJUNTO_ILUMINACAO`, que por sua vez insere dois
   `POSTE`, sai como `GEOMETRYCOLLECTION` com toda a geometria já transladada. O `ezdxf` fica **fora da
   aplicação** e entra só no gerador dos arquivos de teste (`tests/dados/cad/gerar.py`).

## 4. Camadas, blocos, cotas, textos e hachuras

O driver do GDAL não devolve uma camada OGR por camada do DXF: devolve `entities` (e `blocks`, quando os blocos
não são explodidos), com a camada do desenho no campo `Layer`. A contagem por camada é feita com o próprio
GDAL, `ogr2ogr` com dialeto SQLITE e `GROUP BY Layer`, gravando `GeoJSONSeq` no diretório de trabalho — e é
essa contagem que o teste compara, camada a camada, com um `ogrinfo` rodado à parte.

Blocos: o padrão é **manter a inserção como uma feição com o nome do bloco** (`DXF_INLINE_BLOCKS=FALSE`), com a
lista das definições ao lado; quem quiser a geometria aberta responde `blocos: "explodido"` na confirmação.

Cota: **o GDAL decompõe a `DIMENSION` nas linhas e no texto que a desenham** — nenhuma feição sai com
`SubClasses` contendo `AcDbDimension` (medido: arquivo com 4 DIMENSION sai como 12 `AcDbLine` + 4 `AcDbMText`).
Logo a cota não pode ser contada pelo GDAL, e é contada no TEXTO do DXF, em fluxo, com teto de 512 MB. Texto e
hachura, esses, o GDAL identifica pela subclasse.

## 5. Unidade e georreferência: perguntar, nunca supor

O DXF quase nunca traz projeção, e a metade das plantas está em coordenada de obra. Duas perguntas, ambas com o
mesmo tratamento do ADR 0015 seção 4 — a plataforma **pergunta e grava a resposta**, nunca assume:

* **unidade** (`$INSUNITS`): 0 significa "não declarada" e vira pendência com a lista de opções e os metros por
  unidade. Nada de "assume-se metro";
* **sistema de coordenadas**: ou o usuário informa o EPSG em que o desenho já está, ou envia de 2 a 4 pontos de
  controle (coordenada do desenho e coordenada de terreno).

Os pontos de controle são ajustados por **semelhança 2D (Helmert)** — escala, rotação e translação, quatro
parâmetros, mínimos quadrados (`app/ingestao/georreferencia.py`, mesma transformação do `app/georef.py` do SIG
de teste interno). Não é transformação afim de propósito: a semelhança preserva ângulo e proporção, e um
desenho de engenharia não pode ser esticado em um eixo só para "fechar" nos pontos. O que se acrescentou ao
código de origem é o que o portão pede e lá não existia: **resíduo por ponto e RMSE**, calculados já na
confirmação, para que quem confirma VEJA o erro antes de a carga rodar.

Com 2 pontos o sistema é exatamente determinado e o RMSE é zero por construção; o ajuste devolve esse aviso
escrito. A transformação é aplicada com `ST_Affine` na tabela já carregada — o desenho original nunca é
reescrito.

## 6. Tetos declarados

| teto | valor | por quê |
|---|---|---|
| tamanho do arquivo | 2 GB | acima disso o envio é outro problema, não a leitura |
| entidades | 2.000.000 | medido: 2 milhões de POINT (180 MB de DXF) são lidos em 10,5 s dentro do `RLIMIT_AS` de 768 MB; acima disso a recusa manda dividir por camada ou por região |
| camadas | 5.000 | |
| HEADER lido no pai | 2 MiB | a seção HEADER é a primeira do arquivo |
| texto varrido para contar cota | 512 MB | acima disso a contagem de cota para e sai um aviso; as outras contagens são do GDAL e continuam valendo para o arquivo inteiro |

## 7. LibreDWG medido, e o que fica com o dono

Corpus: os 141 DWG do conjunto de teste do GNU LibreDWG, de R1.4 a R2018 (24 em R2000, 21 em R2018), rodados
com `dwg2dxf` 0.14.8583.

* **O LibreDWG leu 141 de 141 — 0 % de falha de leitura.** A cláusula do portão ("decisão ODA registrada em
  `decisoes_do_dono` se o LibreDWG falhar em mais de 10 % do corpus") **não foi acionada**. O ODA File Converter
  continua sendo uma decisão em aberto do dono, pela licença própria, e não foi instalado nem invocado.
* **Mas 29 desses 141 (20,57 %) chegam ao GDAL e não viram nenhuma feição.** São desenhos cujo único conteúdo é
  entidade que o driver DXF do GDAL não representa: `RAY`, `XLINE`, `HELIX`, `SPLINE`, sólido 3D (`Cone`),
  `Underlay`, e — o caso que mais importa — os arquivos só de bloco e só de cota. **A perda é do leitor de DXF,
  não do conversor de DWG**; trocar o LibreDWG pelo ODA não resolveria nada disso.

O conversor roda como **processo separado**, nunca ligado à aplicação (o LibreDWG é GPL-3). O caminho vem de
`PLAT_DWG2DXF`, depois `/opt/plat/libredwg/bin/dwg2dxf`, depois o `PATH`; sem conversor a recusa nomeia a
versão do arquivo e diz o que fazer. DWG que o conversor não lê devolve a **versão comercial e a marca de 6
bytes** na mensagem (`R2018 (AC1032)`), porque quem enviou precisa saber que o problema é a versão do arquivo,
não o desenho dele.

## 8. Fronteiras declaradas

* **Sem tela.** Nesta passagem não existe página de importação no `web/`; o e2e do fluxo é de API, com a
  transcrição de cada passo gravada em `tests/capturas/`. Captura de tela fica para o item da interface.
* **O `RLIMIT_AS` de 768 MB não foi atingido por arquivo nenhum**, nem pelos 2 milhões de entidades. Vale como
  cinto, sem prova de que aperte.
* **Cota contada no texto do DXF é contagem de `DIMENSION`, não geometria de cota.** A geometria que entra na
  tabela é a que o GDAL desenhou (linhas e texto), como em qualquer visualizador.
* **Um DWG que o LibreDWG lê "com aviso" é aceito.** O conversor emite aviso em muitos arquivos e ainda assim
  produz DXF válido; os cinco primeiros avisos ficam gravados em `conversao.avisos`. Não se distingue, aqui,
  perda parcial de conteúdo — para isso seria preciso um segundo leitor independente, e não há.
* **`tests/dados/cad/r2018.dwg` não é nosso.** O LibreDWG só escreve até r2004, então o arquivo R2018 de teste
  veio do conjunto de teste do GNU LibreDWG (GPL-3); a procedência está em `tests/dados/cad/PROVENIENCIA.md`.
  Os demais arquivos de teste são gerados por `tests/dados/cad/gerar.py` a partir de nada.
* **`GET /api/importacoes/formatos` exige credencial, decisão registrada.** O conteúdo é estático e igual
  para todo inquilino (não há dado de inquilino nele), mas a rota ficou, por um turno, sem a dependência
  `autenticado(...)` que as vizinhas (`listar`, `ver`) têm — destoava, e rota sem autenticação por omissão é
  indistinguível de esquecimento. Decisão: autenticar como as vizinhas (`escopo_token="catalogo:ler"`), não
  declarar pública. Motivo: mesmo sem dado de inquilino, a lista revela a superfície de ingestão (que formatos
  a instalação aceita) a quem não entrou, e não há ganho em publicá-la — nenhuma página pública a consome.
  `test_formatos_nao_responde_anonimo` prova 401/403 sem credencial; `test_formatos_publicados_incluem_dxf_e_dwg`
  prova que a resposta não carrega slug, chave nem contagem do inquilino que a pediu.
