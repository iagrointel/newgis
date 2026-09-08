# L6-02-c-wfs-ogcapi — conector WFS 2.0 e OGC API - Features

Trilha `stac`, worktree `/home/dev/plataforma/wt/stac`, ramo `wt/stac`.
Base de teste própria: schema `plat_tl602c` (`bash laco/trilha_ambiente.sh l602c`), sem flock global.

## O que foi construído

| arquivo | o que é |
|---|---|
| `app/conexao/vetor_externo.py` (novo, 640 linhas) | o protocolo: WFS 2.0 (GetCapabilities, DescribeFeatureType, GetFeature com COUNT/STARTINDEX/BBOX, RESULTTYPE=hits, GeoJSON e GML 3.2) e OGC API - Features (`/collections`, `/queryables`, `/items` com limit/bbox/datetime e link `rel=next`). Classe `Paginador` com as travas de parada. |
| `app/conexao/copia.py` (novo, 480 linhas) | job `conexao.copiar_vetor`: páginas → arquivo GeoJSON local → `ogr2ogr` → PostGIS, reprojeção, tipos declarados, `plat.camada_preparar`, item `camada_vetorial` com `dados.conexao` e `dados.procedencia`. |
| `app/conexao/cache.py` (novo) | cache de 30 s no processo para o modo referenciado, com invalidação ao editar/apagar a conexão. |
| `app/conexao/rotas.py` | 3 rotas de leitura novas: `/colecoes`, `/colecoes/{c}/campos`, `/colecoes/{c}/feicoes`. |
| `app/conexao/modelos.py` | modelos de saída das 3 rotas. |
| `app/conexao/seguranca.py` | `alvos_de_teste()` / `PLAT_TESTE_CONEXAO_ALVOS` (ver "válvula" abaixo). |
| `app/conexao/tarefas.py` | importa `copia` para registrar o job (nada de mexer em `app/jobs/tipos.py`, que a árvore principal também edita). |
| `app/limites.py` + `docs/LIMITES.md` | 14 limites novos do conector. |
| `app/jobs/worker.py` | 1 linha: o advisory lock de "1 pesado por vez" passou a carregar o schema (ver "achados"). |
| `db/migracoes/20260906T1609_camada_vetorial_conexao.sql` (novo) | `camada_vetorial` v3: propriedade `conexao` (o esquema v2 é `additionalProperties:false`). |
| `docs/adr/0018-conector-wfs-e-ogc-api-features.md` (novo) | as 7 decisões e a fronteira honesta. |
| `tests/api/conexao/servidor_ogc.py` (novo) | WFS 2.0 + OGC API Features de teste, no loopback, com modo de má-fé. |
| `tests/api/conexao/test_wfs_ogcapi.py` (novo) | o portão, cláusula por cláusula, + a refutação. |
| `tests/unit/test_conexao_seguranca.py` | 4 testes da válvula (faz o que promete, não faz mais, não vale em produção). |
| `tests/api/cruzado_casos.py` | os 3 casos A→B das rotas novas (só entram na varredura quando `docs/openapi.json` for regerado — ver "pendências"). |
| `MANUAL.md` §22 · `ARQUITETURA.md` §18 · `CHANGELOG.md` | documentação. |

## Portão de pronto, cláusula por cláusula

> "1 WFS e 1 OGC API Features públicos adicionados; camada copiada com 50 mil feições em tempo medido;
> paginação conferida (contagem = numberMatched); tipos de atributo preservados; teste."

| cláusula do portão | prova | resultado |
|---|---|---|
| **1 WFS público adicionado** | `test_medida_servicos_publicos_reais` contra `https://geoservicos.ibge.gov.br/geoserver/ows` | **9.708 coleções lidas em 3,0 s**, exemplo `BDIA:geol_area` |
| **1 OGC API Features público adicionado** | o mesmo teste, contra `https://demo.pygeoapi.io/master` | **17 coleções em 1,4 s**, exemplo `obs` |
| (os dois, no fluxo de ponta a ponta) | `test_wfs_e_ogc_api_adicionados_e_lidos` — cria as duas conexões pela API, lê coleção, CRS declarado e campos | passa; WFS declara `EPSG:31983` e o OGC API entrega em CRS84 |
| **camada copiada com 50 mil feições em tempo medido** | `test_copia_50_mil_feicoes_com_tempo_medido` | **50.000 linhas na tabela**, `copia_50k_feicoes_s` = **10,19 s** de ponta a ponta (0,781 s de download em 10 páginas, 1,648 s de `ogr2ogr`) |
| **paginação conferida (contagem = numberMatched)** | `test_paginacao_bate_com_number_matched[wfs]` e `[ogc_api]` | 1.234 feições lidas = 1.234 declaradas, em >= 13 páginas; o WFS anda com `STARTINDEX` 0/100/200 e o OGC API com o link `rel=next` no mesmo passo |
| **tipos de atributo preservados** | `test_copia_50_mil_feicoes_com_tempo_medido` (WFS, `DescribeFeatureType`) e `test_copia_ogc_api_preserva_tipos_de_queryables` (OGC API, `/queryables`) | `xsd:string`→`text`, `xsd:int`→`integer`, `xsd:double`→`double precision`, `xsd:boolean`→`boolean`, `xsd:date`→`date`; no OGC API o `integer` do JSON Schema (sem largura) vira `bigint`, e a ficha diz isso |
| **teste** | `tests/api/conexao/test_wfs_ogcapi.py` | **12 de 12 passam** (`............`), mais 4 testes novos da válvula em `tests/unit/test_conexao_seguranca.py` |

Extras provados no mesmo arquivo, que não estavam no portão mas o item precisava: bbox e datetime no modo
referenciado; cache curto (a segunda consulta idêntica NÃO vai ao serviço — conferido contando as requisições
recebidas pelo servidor de teste); WFS que só fala GML (páginas convertidas localmente pelo GDAL, camada
reprojetada cai no Brasil); conexão de tipo sem conector recusada com 422 nomeado; e a trava cruzada A→B das
três rotas, que devolve 404 SEM sequer falar com o serviço externo.

## Refutação exigida

> "adversário aponta WFS com 5 mi de feições e sem paginação: o modo copiado para no limite declarado e
> avisa, sem travar o worker."

`test_wfs_de_5_milhoes_sem_paginacao_para_no_limite_e_avisa`, **7,46 s**. O servidor de teste declara
`numberMatched="5000000"`, ignora `COUNT`/`STARTINDEX` e devolve sempre o mesmo bloco de 2.000 feições. Com
`limite_feicoes=1000` e `tam_pagina=500`, o job:

- **termina** (`estado: concluido`), não fica girando nem falha;
- copia **exatamente 1.000 feições** (conferidas com `count(*)` na tabela, sob o contexto do inquilino);
- marca `limite_atingido: true` e `ignora_paginacao: true` no resultado;
- grava o aviso em `dados.conexao` e em `dados.procedencia.limites` do item — quem abrir a camada daqui a um
  mês vê que ela é um pedaço, não a coleção inteira;
- **devolve o worker à fila**: logo depois, `prova.progresso` roda e conclui, e o processo do worker segue vivo.

Variante provada à parte (`test_servico_que_repete_a_mesma_pagina_para_na_hora`): serviço que aceita
`STARTINDEX` mas devolve sempre a MESMA página é cortado na **segunda** requisição pela trava de repetição —
sem ela, o laço só pararia no teto de 2.000 páginas.

## Decisão que estrutura o item: o GDAL não fala com o serviço externo

Os drivers `WFS:`/`OAPIF:` do GDAL existem nesta máquina (GDAL 3.8.4, `ogrinfo --formats`) e foram
RECUSADOS. Eles fazem a requisição por dentro do `libcurl`, fora de `app.conexao.seguranca`, e a defesa
contra requisição forjada pelo servidor (item L6-02-a) deixaria de valer justamente no caminho que mais
recebe URL de terceiro. Aqui as páginas são baixadas por `buscar_seguro`, gravadas em arquivo local do job, e
o `ogr2ogr` só entra depois, sobre arquivo local, com `GDAL_HTTP_PROXY=127.0.0.1:1` (porta fechada) para que
nenhuma requisição sua possa sair da máquina.

## Válvula na defesa de SSRF — leia antes de aprovar

`PLAT_TESTE_CONEXAO_ALVOS` é uma lista de pares `host:porta` EXATOS que a validação deixa passar mesmo no
loopback. Aceita só fora de produção (`settings.producao` ignora e loga aviso). Existe porque a regra do laço
proíbe a suíte depender de serviço de terceiro, e um WFS de verdade tem de subir em algum lugar.
Provas em `tests/unit/test_conexao_seguranca.py`: o par declarado passa; `127.0.0.1:8150` (a API desta
máquina) e `169.254.169.254` seguem recusados COM a válvula ligada; em `producao` a variável não vale; lixo na
variável não libera nada. Nada mais da validação é dispensado.

## Fronteira honesta (o que NÃO foi entregue)

- **WFS 1.0/1.1**: só 2.0.0 (é quem tem `STARTINDEX`/`numberMatched`).
- **Agendamento da cópia**: o job é agendável pelo relógio do L0-05, mas a política e a tela são o L6-02-k.
- **Filtro CQL2 / `Filter` OGC**: L6-02-n. Só `bbox` e `datetime`.
- **Camada referenciada desenhada no mapa**: L6-02-b.
- **WFS-T (escrita de volta)** e **OGC API Parte 2 (CRS negociado)**: fora de escopo; `/items` é lido em CRS84.
- **`docs/openapi.json` NÃO foi regerado** (ver pendências), então `tests/api/test_cruzado.py` ainda não
  varre as 3 rotas novas; a trava cruzada A→B delas está provada à mão em
  `test_conexao_de_outro_inquilino_nao_vaza_nem_chega_a_falar_com_o_servico`.
- **Tela**: nenhuma. O conector é API + job.

## Achados que valem para as outras trilhas

1. **`docs/openapi.json` está DEFASADO no ramo**: o arquivo comitado tem 126 rotas, o app tem 173 — faltam 44
   rotas de outros itens (mapas, exportação, geocodificação em lote, migração, rede de utilidades, uploads,
   convites, SMTP, GeocodeServer). Regerar aqui traria trabalho alheio para dentro deste commit e faria
   `test_cruzado` exigir caso para todas elas. **Quem fizer o merge tem de rodar `make openapi` e conferir se
   `tests/api/cruzado_casos.py` cobre as 44** — hoje `rotas_total == rotas_cobertas` só passa por o arquivo
   estar velho.
2. **O advisory lock de "1 pesado por vez" era do BANCO INTEIRO** (`hashtext('plat.job.pesado')`). Como
   produção, homologação e todas as bases por trilha vivem no mesmo `iagro_sat`, o worker de UMA trilha
   segurava o único lugar e o job pesado de TODAS as outras ficava `pendente` sem nada rodando (medido:
   `pg_locks` apontava o worker de `trilha-l09a` enquanto o meu rodava só job leve). Passou a carregar o
   schema (`plat.job.pesado:<PLAT_SCHEMA>`). Em produção, onde só existe `plat`, o comportamento não muda —
   a única ressalva é uma reinicialização em ondas, em que worker velho e novo usariam nomes diferentes por
   alguns segundos.
3. **`laco/trilha_ambiente.sh` não dá privilégio nos schemas de dado `d_<slug>`.** Eles são criados uma vez
   com `AUTHORIZATION plat_app` (produção) e a role da trilha não tem `USAGE`/`CREATE` neles — qualquer teste
   que crie CAMADA (ingestão de arquivo inclusive) morre com `permission denied for schema d_demo`. Foi
   preciso rodar à mão:
   `GRANT ALL ON SCHEMA d_demo, d_demo2, d_plataforma TO plat_tl602c_app, plat_tl602c_worker;`
   Sugestão para o gerente: ou o `trilha_ambiente.sh` passa a fazer esse GRANT, ou o produto passa a derivar o
   schema de dado do ambiente (`d_<PLAT_SCHEMA>_<slug>`), que é o conserto de verdade — hoje a homologação
   grava camada no MESMO `d_demo` da produção.
4. **Porta fixa de worker de teste não serve mais**: 18159 (a do `worker_extra`) e 18162 estavam ocupadas por
   workers de outras trilhas, e o `/saude` do worker alheio respondia — o `WorkerExtra` dava o worker por
   iniciado e o job ficava pendente para sempre. Aqui se usa porta efêmera + conferência do `nome_base`.
5. **`GetCapabilities` de GeoServer nacional é grande**: o do IBGE tem **11.602.903 bytes** (medido 06/09, 2,3
   s). O teto de metadado começou em 8 MiB e recusava um serviço público legítimo; está em 32 MiB.

## Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh l602c
sudo -u postgres psql -d iagro_sat -c \
  "GRANT ALL ON SCHEMA d_demo, d_demo2, d_plataforma TO plat_tl602c_app, plat_tl602c_worker"
cd /home/dev/plataforma/wt/stac
set -a; source /home/dev/plataforma/laco/var/trilha/l602c.env; set +a
venv/bin/pytest tests/api/conexao/test_wfs_ogcapi.py -q -p no:randomly     # o portão
venv/bin/pytest tests/unit/test_conexao_seguranca.py -q -m "not lento"     # a válvula de SSRF
venv/bin/ruff check app/conexao tests/api/conexao
```

Ao terminar: `DROP SCHEMA plat_tl602c CASCADE; DROP SCHEMA plat_trabalho_tl602c CASCADE`.

## Commits do ramo

- `b2bd88e` — Conector WFS 2.0 e OGC API - Features nos modos referenciado e copiado (item L6-02-c-wfs-ogcapi)

21 arquivos, 2.694 linhas. Nenhum outro arquivo do worktree entrou: a árvore é compartilhada com outros
agentes e o commit foi montado hunk a hunk (`git apply --cached` de recorte, e blob montado do HEAD para
`CHANGELOG.md` e `MANUAL.md`, onde outra trilha escrevia ao mesmo tempo).

## Riscos de merge

- `app/limites.py`, `docs/LIMITES.md`, `CHANGELOG.md`, `MANUAL.md`, `ARQUITETURA.md`: só o bloco deste item
  entrou, sempre no fim do arquivo (ou no topo, no caso do CHANGELOG). Conflito, se houver, é de vizinhança.
- `app/jobs/worker.py`: uma linha (`LOCK_PESADO`). A árvore principal mexe neste arquivo.
- `app/conexao/rotas.py` / `modelos.py` / `tarefas.py` / `seguranca.py`: só este item mexe hoje.
- `app/jobs/tipos.py` NÃO foi tocado de propósito (o job se registra pelo `app/conexao/tarefas.py`).
- `docs/openapi.json` NÃO foi tocado — mas precisa de `make openapi` no merge (achado 1).
- `tests/api/cruzado_casos.py`: os 3 casos deste item foram parar no commit `1d0040b` de outra trilha (árvore
  compartilhada). Estão no ramo; nada a fazer.
