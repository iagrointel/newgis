# G3 — conserto da parte FUNCIONAL da ingestão (turno 3, 06/09/2026)

Ramo `wt/g3fix`, worktree `/home/dev/plataforma/wt/g3fix`, base de teste `plat_tg3fix`
(`bash laco/trilha_ambiente.sh g3fix`). Nenhum comando desta trilha tocou o schema `plat` de produção.

Conserta os achados FUNCIONAIS do laudo `handoffs/T3/ataque-g3-ADVERSARIO.md`. Os achados de recurso
partilhado (chave de trinco global, schema de dados sem prefixo de instalação, `uso_bytes` que só sobe, falta
de justiça na fila, orçamento de conexões SSE, job morto que termina `concluido`, rastro não saneado) são de
outra trilha e **não foram tocados aqui**.

## 1. O que foi construído

| arquivo | o que mudou |
|---|---|
| `app/ingestao/formatos.py` | 13 formatos (eram 4); `ArquivoRecusado` como mãe de `ZipSuspeito` e `ConteudoNaoCorresponde`; `FORMATOS_QUE_DEPENDEM_DE_LICENCA` |
| `app/ingestao/inspecionar.py` | preparadores dos 9 formatos novos; `_inspecionar_camada` roda para TODAS as camadas; aviso de camada vazia e de camada sem geometria |
| `app/ingestao/rotas.py` | rota `/api/importacoes/formatos` antes da rota com parâmetro; captura de `ArquivoRecusado` → 422; campo `camada` na confirmação; 422 `camada_sem_geometria` |
| `app/ingestao/carregar.py` | `_proposta_efetiva` (a camada escolhida manda), recusa explícita de camada sem geometria |
| `db/migracoes/20260906T1607_slug_ingestao_reconciliado.sql` | alfabeto do slug reconciliado entre a criação do inquilino e a ingestão |
| `deploy/Dockerfile.worker` | base `python:3.12-slim-trixie` (GDAL 3.10.3) + portão de construção que reprova sem `ogrinfo -json` e sem os 12 drivers |
| `docs/adr/0010-worker-em-container.md` | seção 10: o portão do L0-05-e escrito, e o porquê da troca de base |
| `tests/dados/gerar.py` | 21 arquivos de teste (eram 9), um por formato mais os de ataque |
| `tests/unit/test_rotas_sombreadas.py` | rota literal engolida por rota com parâmetro reprova, em TODO o repositório |
| `tests/unit/test_app_versionada.py` | módulo carregado pela aplicação que não está versionado reprova |
| `tests/api/ingestao/test_formatos_base.py` | formatos, multi-camada, CSV de 300 colunas, zip malformado, planilha sem geometria |
| `tests/api/ingestao/test_slug_alfabeto.py` | as duas funções de slug exercitadas de verdade |
| `tests/api/ingestao/test_medidas_100k.py` | `tempo_inspecao_s` e `tempo_import_100k_s` com 100 mil feições (marcado `lento`) |
| `tests/medidas/L0-04-d-formatos-base.json`, `tests/medidas/L0-05-e-worker-em-container.json` | medidas gravadas |

Commits: `1409076` (ingestão) e `b24fefa` (contêiner e portão).

## 2. Achado por achado

### (1) O portão pede nove formatos e a instalação tem quatro — CONSERTADO, nada precisou ser instalado

O GDAL do host é **3.8.4** e `ogrinfo --formats` já traz driver para todos: ESRI Shapefile, GPKG, GeoJSON,
GeoJSONSeq, CSV, LIBKML (KML e KMZ), GPX, XLSX, GML, FlatGeobuf, DXF, OpenFileGDB. A instalação passa a
anunciar **13 formatos**: os 9 do portão do L0-04-d (`shapefile.zip`, `gpkg`, `geojson`, `geojsonseq`, `kml`,
`kmz`, `csv`, `gpx`, `xlsx`) e os 4 que o portão do L0-04-b pede a mais (`gml`, `flatgeobuf`, `dxf`, `gdb`).

**O que depende de licença de terceiro: só o DWG.** A leitura de DWG exige o ODA File Converter (binário
gratuito, licença própria) ou o LibreDWG (GPL-3). Nenhum dos dois está na máquina e a escolha é do dono — é a
pendência já registrada no item L0-04-e. Fica declarado em código
(`FORMATOS_QUE_DEPENDEM_DE_LICENCA`), anunciado na rota (`nao_aceitos`) e a recusa diz o motivo, com a saída
("converta para DXF"). Não é limitação técnica desta camada, é decisão pendente.

**Fronteira honesta:** aceitar e inspecionar não é tratar a semântica própria de cada formato. Os blocos e a
georreferência por pontos do DXF continuam sendo o item **L0-04-e**; os domínios, subtipos e anexos da File
Geodatabase continuam sendo o **L0-04-f**. Aqui os dois entram pelo caminho comum do GDAL.

### (2) A rota que anuncia os formatos responde 404 — CONSERTADO, com teste que vale para toda rota nova

`GET /api/importacoes/formatos` estava declarada depois de `GET /api/importacoes/{id}`; o roteador casa na
ordem de declaração e o parâmetro engolia a palavra "formatos". A rota literal passou para antes.

`tests/unit/test_rotas_sombreadas.py` tem três testes: (a) nenhuma rota de caminho literal é alcançada
depois de uma rota com parâmetro do mesmo prefixo, para TODAS as rotas do repositório; (b) toda rota com
parâmetro resolve para ela mesma quando os parâmetros são substituídos por um valor sintético; (c) a cláusula
por nome da rota de formatos. Provado que pega a regressão: com a ordem antiga de volta, (a) e (c) reprovam.

### (3) Pacote geográfico com três camadas perde duas sem aviso — CONSERTADO nas duas metades

A inspeção usava `camada = camadas[0]`. Agora `_inspecionar_camada` roda para TODAS as camadas e a proposta
guarda a de cada uma em `proposta["camadas"]` (nome, contagem, geometria, CRS, campos, validade, perguntas,
avisos). Quando há mais de uma:

- `"camada"` entra em `perguntas`: confirmar sem responder devolve 422 `perguntas_pendentes`. Nada é
  escolhido em silêncio.
- um aviso nomeia as camadas que **não** entram nesta importação e diz como trazê-las.
- a confirmação aceita `{"camada": {"escolhida": "<nome>"}}` e troca campos, geometria, CRS e validade pelos
  daquela camada; `carregar` usa a mesma resolução (`_proposta_efetiva`), senão carregaria os campos da
  camada errada.
- as três camadas de um GeoPackage importam uma a uma, do mesmo arquivo enviado uma vez só, gerando três
  tabelas (`test_as_tres_camadas_do_gpkg_importam_uma_a_uma`).

O KMZ de três pastas gera três camadas; o GPX, que declara sempre cinco camadas e traz quatro vazias, abre na
única com dado e diz quais estão vazias.

### (4) Planilha com trezentas colunas e nenhuma linha termina em silêncio — CONSERTADO

Camada com zero feições passa a sair com aviso explícito na proposta, citando o número de campos e dizendo
que a tabela sairia vazia. Camada sem geometria ganha aviso próprio.

### (5) Inquilino com hífen no apelido nunca importa — CONSERTADO

`plat.tenant.slug` tem `CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,38}$')` desde a migração 002; a 029 escreveu
`'^[a-z][a-z0-9_]{0,60}$'` dentro de `plat.camada_schema_garantir`. Todo slug com hífen ou dígito inicial era
aceito na criação e recusado na ingestão com `slug_invalido`. A migração
`20260906T1607_slug_ingestao_reconciliado.sql` faz a ingestão aceitar o mesmo alfabeto da criação (mais `_`,
por compatibilidade com schemas antigos). `tests/api/ingestao/test_slug_alfabeto.py` **exercita as duas
funções** em vez de ler o texto delas: `minha-org`, `org2`, `2024-prefeitura`, `a-b-c-d` passam nas duas;
`Maiuscula`, `com espaco`, `-comeca-com-hifen`, `x`, `org.ponto`, `org/barra` são recusados nas duas.

### (6) Arquivo compactado malformado levanta erro interno — CONSERTADO

`ZipSuspeito` e `ConteudoNaoCorresponde` eram classes irmãs, ambas filhas de `ValueError`, e a rota só
capturava a segunda: um zip malformado subia como 500 com rastro. As duas passam a herdar de
`ArquivoRecusado`, que é o que a rota captura → 422 com código `zip_suspeito` e mensagem em português. Toda
recusa nova de conteúdo herda daí.

### (7) As duas medidas nomeadas nos portões não existem — GRAVADAS

`tests/api/ingestao/test_medidas_100k.py` (marcado `lento`) gera 100 mil feições, mede
`tempo_inspecao_s` (portão do L0-04-b: ≤ 5 s) e `tempo_import_100k_s` (portão do L0-04-c: ≤ 60 s), grava em
`tests/medidas/L0-04-b-inspecao.json` e `tests/medidas/L0-04-c-tabela-camada.json` e **apaga o arquivo grande
no fim** (disco a 91 % quando este item rodou).

Sobre o dado: o portão sugere "setores censitários de um estado". A regra da casa proíbe baixar dado novo com
o disco neste nível, então as 100 mil feições são DERIVADAS do dado aberto que já está no repositório
(cobertura do solo de Guarulhos, OSM/ODbL, em `web/dados/basemap/guarulhos.pmtiles`), replicadas numa grade
com os atributos reais ciclados. É sintético em posição, real em forma e em esquema; a medida vale para o
tamanho do arquivo e o número de feições, não para a geometria de um estado. Está escrito assim no próprio
arquivo de medida.

### (8) Item entregue com o portão por escrever, e contêiner com GDAL que não serve — CONSERTADO o segundo, PROPOSTO o primeiro

**GDAL do contêiner.** A imagem era `python:3.12-slim-bookworm` + `gdal-bin`, que no bookworm é **GDAL
3.6.2** — e nele `ogrinfo -json` não existe. Como `app/ingestao/inspecionar.py` lê TODO arquivo com
`ogrinfo -ro -json -so`, qualquer job `ingestao.inspecionar` que caísse nesse executor falharia.
`bookworm-backports` não resolve (medido: não há `gdal-bin` lá, o candidato continua `3.6.2+dfsg-1+b2`). A
base passou a **`python:3.12-slim-trixie`**, com **GDAL 3.10.3**. O Dockerfile ganhou um **portão de
construção**: a imagem não é produzida se `ogrinfo -json` falhar ou se faltar qualquer um dos 12 drivers.

Medido e gravado em `tests/medidas/L0-05-e-worker-em-container.json`: os 13 arquivos de teste são lidos com o
MESMO nome de camada e a MESMA contagem de feições no host (3.8.4) e no contêiner (3.10.3) — 13 de 13. Única
diferença conhecida: o LIBKML do 3.10 expõe um campo a mais no KML (16 contra 15) e no KMZ (12 contra 11). A
imagem foi construída, medida e **apagada** (disco a 92 %).

**Portão do item.** O texto em `estado.json` continua sendo "portão a fixar pelo arquiteto…". A edição do
arquivo de estado é do gerente; o texto do portão de verdade está escrito na **seção 10 do ADR 0010** e é o
seguinte:

> A imagem `plat-worker` constrói, e a própria construção reprova se o GDAL dela não tiver `ogrinfo -json`
> nem todos os drivers dos formatos declarados em `app/ingestao/formatos.py`. Um contêiner subido pelo
> `deploy/docker-compose.worker.yml` pega, na MESMA fila `plat.job` da unidade systemd, um job
> `ingestao.inspecionar` e um `ingestao.carregar` de arquivo real, e produz a mesma proposta e a mesma
> contagem de feições que o executor por processo. O contêiner roda como usuário sem privilégio (uid 10001) e
> o teto de memória do cgroup é lido por `app/jobs/filho.py`. Matar o contêiner no meio de um job devolve o
> job à fila e não deixa tabela órfã. A imagem é reproduzível a partir do repositório: comando de construção,
> versão do GDAL e sha256 do Dockerfile gravados em `tests/medidas/L0-05-e-worker-em-container.json`.

**Enquanto o texto provisório estiver no `estado.json`, o item é PARCIAL, não entregue.** A cláusula que falta,
exatamente: *um job `ingestao.inspecionar` e um `ingestao.carregar` de arquivo real, pegos da fila DENTRO do
contêiner e comparados com o executor por processo*. Esta trilha provou a leitura de GDAL dentro do
contêiner nos 13 formatos, não o job passando pela fila lá dentro.

### (extra) A ponta do ramo principal não importava — TESTE ESCRITO

`tests/unit/test_dependencias.py` já importava `app.main`, mas a partir do diretório de trabalho: o arquivo
que faltava no commit estava no disco, então o teste passava e o clone não subia.
`tests/unit/test_app_versionada.py` fecha o buraco por dois caminhos: fumaça (a aplicação importa e tem mais
de 100 rotas) e **todo módulo `app.*` carregado ao importar `app.main` tem de estar em `git ls-files`**.
Provado que pega: com um `app/zz_prova_nao_versionado.py` importado pelo `main.py` e não versionado, o teste
reprova nomeando o arquivo.

## 3. Como reproduzir

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh g3fix
cd /home/dev/plataforma/wt/g3fix
# a migração desta trilha ainda não está em master, então trilha_ambiente.sh (que lê o repo principal)
# não a aplica; aplique à mão na base da trilha:
TRILHA=g3fix /home/dev/plataforma/laco/trilha_reescrever.py \
  db/migracoes/20260906T1607_slug_ingestao_reconciliado.sql > /tmp/mig.sql && chmod 644 /tmp/mig.sql
sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/mig.sql && rm -f /tmp/mig.sql

set -a; source /home/dev/plataforma/laco/var/trilha/g3fix.env; set +a
export PLAT_WORKER_URL=http://127.0.0.1:18170        # confira `ss -ltnH` antes: porta é recurso da máquina
venv/bin/python tests/dados/gerar.py                 # 21 arquivos, nada baixado
venv/bin/python -m app.jobs.worker &                 # mate SÓ pelo PID no fim
venv/bin/pytest tests/unit/test_rotas_sombreadas.py tests/unit/test_app_versionada.py -q
venv/bin/pytest tests/api/ingestao -q -p no:randomly
venv/bin/pytest tests/api/ingestao/test_medidas_100k.py -m lento -q   # 100 mil feições; apaga o arquivo
```

Contêiner (constrói, mede e apaga):
```
docker build -f deploy/Dockerfile.worker -t plat-worker:g3fix .
docker run --rm --entrypoint bash plat-worker:g3fix -lc 'ogrinfo --version'
docker rmi plat-worker:g3fix
```

## 4. O que ficou de fora, e por quê

1. **Tabela sem geometria não é carregada.** Planilha, CSV sem coluna de coordenada e tabela de atributo de
   GeoPackage são inspecionadas e a confirmação as **recusa com 422 `camada_sem_geometria` e mensagem**, em
   vez de deixar o job morrer no meio. Carregar de verdade exige mudar `plat.camada_preparar` (índice GIST
   sobre `geom` incondicional) e o esquema JSON de `camada_vetorial` (`srid` obrigatório), o que mexe em
   território de L2 (tiles e FeatureServer). É a cláusula "CSV sem coluna de coordenada vira tabela sem geom"
   do portão do L0-04-d que **continua aberta**.
2. **Semântica própria de DXF e File Geodatabase** — itens L0-04-e e L0-04-f, ainda `pendente`.
3. **DWG** — decisão do dono sobre o conversor.
4. **Teto por feição** (o milhão de vértices do laudo, seção T1) — não é achado desta lista; segue aberto.
5. **Job da fila dentro do contêiner** — ver o item 8 acima.
6. Os achados de recurso partilhado do laudo, que são de outra trilha.

## 5. Riscos de junção

- `db/migracoes/20260906T1607_slug_ingestao_reconciliado.sql` **redefine `plat.camada_schema_garantir` e
  `plat.camada_preparar` inteiras**. A trilha que está pondo prefixo de instalação no schema de dados
  (`d_<slug>`) vai mexer nas MESMAS duas funções. Quem juntar por último tem de manter o alfabeto relaxado —
  `tests/api/ingestao/test_slug_alfabeto.py` reprova se ele se perder.
- `tests/api/adversario_g3/` foi trazido de `wt/adv3` (commit `761bd8c`) **sem alteração**: nenhum `xfail`
  foi mexido, nenhum teste apagado. A troca das marcas dos testes de ingestão que agora passam
  (`test_formatos_anunciados_cobrem_os_9_do_portao`, `test_formato_do_portao_e_aceito`,
  `test_gpkg_com_3_camadas_propoe_as_3`, `test_csv_300_colunas_e_0_linhas_recusa_com_mensagem_na_inspecao`,
  `test_zip_malformado_devolve_422_e_nunca_500`, `test_rota_de_formatos_de_importacao_e_alcancavel`,
  `test_medidas_de_desempenho_da_ingestao_estao_gravadas`, `test_inquilino_com_hifen_no_slug_consegue_importar`)
  está registrada na seção 6. `test_g3_fila.py` e `test_g3_tela.py` não foram tocados: são da outra trilha.
- `app/main.py` não foi alterado.
