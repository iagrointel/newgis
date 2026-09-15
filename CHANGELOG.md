# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json` (com o comando que
os gerou) ou dos vereditos do adversário em `laco/handoffs/T<n>/<item>/refutacao.json`.

## setembro de 2026 (item L0-02-g residual: status do `POST /api/usuarios/lote` numa escalada 100% recusada)

`test_l0_02g_ator_nao_atribui_papel_com_um_privilegio_a_mais_que_o_seu` media que a rota já RECUSAVA a
escalada (`alterados: 0`, alvo em `recusados`), mas devolvia `200` — o adversário exige 403/422 para
qualquer tentativa de escalada. Conserto em `app/auth/rotas_usuarios.py::lote`: quando `alterados == 0`
e há `recusados`, a resposta vira `403` com `erro`/`mensagem`/`detalhe` do primeiro recusado (preserva o
`detalhe` original, por exemplo a lista de privilégios que faltam) e `recusados` continua no corpo, no
mesmo nível de `erro`. Aplicação parcial (≥1 alterado) continua `200`, sem mudança de contrato.

Prova: `roda_teste.sh tests/api/adversario/test_l0_identidade.py` → 18 passed (os 2 outros nomes que
falhavam num run anterior — `02b`/`02c` — são contenção do superadmin/2FA compartilhado entre workers
na mesma máquina, `410 desafio_expirado`; reproduzido e confirmado isolando-os); `roda_teste.sh
tests/api/test_usuarios_papel_escalada.py` → 8 passed (sem o teardown 409 auditoria_imutavel que o
laudo citava como de outro item — não apareceu nesta rodada). `MANUAL.md` §4.4 atualizado.

## setembro de 2026 (item L3-01-a-modelo-dado: refutação "execute_values manda bytes e fura a reescrita de schema")

Já estava CONSERTADO antes deste turno (achado 1 do laudo, 06/09/2026), em dois níveis: `gravar_feicoes`
(`app/amc/unidades.py`) não usa mais `psycopg2.extras.execute_values` — grava em `cur.execute` de TEXTO
com `jsonb_to_recordset`, que passa pela reescrita como qualquer consulta — e `MixinReescritaSchema`
(`app/schema_ambiente.py`, não tocado por regra da casa) já decodifica/reescreve/recodifica `bytes` em
`execute`/`executemany`/`callproc`/`mogrify`/`copy_expert`. O item `L3-01-a-modelo-dado` no
`laco/estado.json` ainda carrega o `bloqueio` antigo (pré-conserto) — registro desatualizado, não um
defeito vivo.

Reproduzido ao vivo com `psycopg2.extras.execute_values` de verdade contra um cursor-espião
(`CursorEspiao` de `tests/unit/test_schema_ambiente.py`) fora do schema padrão: `INSERT INTO plat.x(a,b)
VALUES %s` chega a `cur.execute` como `b'INSERT INTO plat_tteste.x(a,b) VALUES (%s,%s),(%s,%s)'` — o
schema de trilha, não `plat` de produção.

Prova: `roda_teste.sh tests/unit/test_schema_ambiente.py` → 22 passed (sem mudança; já cobria bytes em
todos os pontos de entrada); `roda_teste.sh tests/api/amc/test_amc_adversario_api.py -k
"test_adv_conjunto_de_feicoes_funciona_em_qualquer_schema or
test_adv_execute_values_e_o_unico_desvio_da_reescrita_de_schema"` → 2 passed. Nenhum código alterado
neste item; só a verificação acima e esta nota.

## lote f1-lote3, setembro de 2026 (item i: reprodutibilidade das 13 funções SQL do prefixo de schema)

Dívida de `laco/handoffs/T8/LANCAMENTO.md:448-450` ("falta escrever a migração equivalente") está PAGA,
não em aberto: a migração `db/migracoes/20260911T1440_prefixo_schema_de_dado_nas_funcoes.sql` (commit
`0278b96c`) já É essa migração. Ela não lista as treze funções — varre `pg_proc` do schema em aplicação
em tempo de execução e reescreve todo corpo de função com o literal `'d_' ||` para
`camada_schema_prefixo() ||`, exceto a própria função que define o prefixo — por isso vale tanto para
uma instalação nova quanto para a que já existia, e é idempotente.

Conferido no banco da trilha `plat_tuniao`: `plat_tuniao.versao_migracao` tem a migração aplicada
(11/09 14:19); a varredura do próprio hand-over (`pg_get_functiondef(p.oid) LIKE '%''d_'' ||%'`) não
acha nenhuma função com o literal fora de `camada_schema_prefixo()` (excluída de propósito); catorze
funções usam `camada_schema_prefixo()` hoje, cobrindo as treze do hand-over. Nada para escrever.

## lote f1-lote3, setembro de 2026 (item j1: 7 módulos com importação quebrada, LANCAMENTO.md:439-444)

A varredura original do hand-over tinha um falso positivo: `coleta/tela.js` importa `folhas` de
`coleta/motor.js`, que já exporta (`export function* folhas`) — o regex do scanner antigo não
reconhecia `function*`, só `function`. Corrigido isso, sobram 6 pares realmente quebrados (7 símbolos,
`amc/motor_pagina.js` importa dois de `combinacao.js`).

Consertados por união manual: buscada a implementação perdida na própria história do repositório
(commit ancestral do HEAD atual cujo hunk a fusão descartou) em vez de escrever comportamento novo —
`web/js/base/i18n.js::acrescentar` (mescla i18n de widget externo em tempo de execução), `web/js/base/
api.js::remendar` (PATCH genérico, mesmo padrão de `obter`/`enviar`/`alterar`/`apagar`) e
`::reqIdsRecentes` (anel das últimas 20 requisições por X-Req-Id, consumido por
`web/js/chamados/reportar.js`), `web/js/amc/combinacao.js::MAPA_COMBINADOR`/`::MAPA_POLITICA`
(tradução do vocabulário do modelo, gêmea de `app/amc/explicacao.py`, que já tem os dois dicionários)
e `web/js/base/layout.js::seletorTema` (botões de tema sobre `window.platTema`, script clássico que
já existe e já é usado pela própria `web/js/estilo/estilo.js`).

Fica ABERTO `web/js/executor/executar_tela.js::prepararWidgets`: a implementação histórica dependia de
`REGISTRO`/`carregarModulos`/`criarWidget` de `web/js/widgets/motor.js`, API que não existe mais no
motor atual (hoje só `BarramentoWidgets`/`montarWidgets` — o desenho mudou depois). Reintroduzir a
função exigiria reconciliar dois desenhos de motor de widget divergentes (o executor não tem hoje
nenhum caso para botão/cartão/embed/menu-widget/controlador/compartilhar/idioma/tema — caem todos no
`exec-desconhecido` genérico), decisão de arquitetura fora do escopo de uma união mecânica de
importação. Não inventado.

Prova: `node --check` nos 4 arquivos tocados e nos 6 módulos que os importam (`web/js/widgets/
externos.js`, `web/js/mapa/anotacoes.js`, `web/js/chamados/reportar.js`, `web/js/amc/motor_pagina.js`,
`web/js/estilo/estilo.js`, mais `web/js/coleta/tela.js` sem alteração) — todos OK; e resolução em
tempo de execução (`node -e "import('./x.js').then(m => console.log(typeof m.simbolo))"`) para cada
símbolo: todos `function`/`object`, nenhum mais `undefined`, exceto `prepararWidgets` (deixado aberto).
Suíte de testes não rodada (`tests/unit/test_front_sintaxe.py` não executado): memória livre ficou
abaixo de 5000 MB nas 10 tentativas de 60 s antes do pytest (medido `free -m`), então a prova ficou só
em `node`, permitido pela regra da casa.

## lote f1-lote3, setembro de 2026 (item j2: defeito #6 de LANCAMENTO.md:412, raster_item x raster_colecao)

Já estava FECHADO antes deste lote — desde 11/09 14h45, mesmo dia do hand-over (própria seção "A prova
que o dono pediu" de `laco/handoffs/T8/LANCAMENTO.md`), só a tabela do defeito #6 não tinha sido
atualizada. `colecao_espelhar` (`app/imagens/pgstac.py`) roda incondicionalmente dentro de
`_colecao_garantir` (`app/imagens/ingestao.py`), ANTES de checar se a coleção já existe no pgstac —
não só na criação, como o defeito original descrevia. Conferido de novo neste lote, sem alterar
código: `plat_tuniao.raster_colecao` tem a linha `1-imagens` (tenant 1) e `plat_tuniao.raster_item`
referencia essa coleção sem violar `raster_item_colecao_fkey`. Tabela do hand-over atualizada em
`laco/handoffs/T8/LANCAMENTO.md:412` (fora deste repositório): ABERTO → FECHADO, com a referência.

## turno 4, setembro de 2026 (item L4-05-d-epanet-inp: arquivo EPANET .inp entra e sai da rede de água)

Porta de entrada e de saída do formato que o setor de água usa: o `.inp` do EPANET. `ler_inp`/`escrever_inp`
(`app/rede_utilidades/epanet_inp.py`) cobrem JUNCTIONS, RESERVOIRS, TANKS, PIPES, PUMPS, VALVES, COORDINATES,
VERTICES, PATTERNS, CURVES e OPTIONS; seção fora do escopo vira aviso, nunca erro. `POST /api/rede/{id}/epanet`
enfileira o job `rede.epanet_importar`, que grava feições sobre o pacote de ativos `agua-epanet`;
`GET /api/rede/{id}/epanet` reconstrói o arquivo das tabelas, nunca devolve o que entrou. Migração
`20260910T2353_rede_epanet_importacao.sql`: fila da importação, `plat.rede_epanet_curva`/`rede_epanet_padrao`
(as curvas e os padrões que um ativo referencia por ID, e sem as quais o arquivo exportado é recusado pelo
WNTR) e a queda do `NOT NULL` das duas colunas `geom` da rede.

Medido sobre a rede de água real desta casa (`tests/medidas/L4-05-d-epanet-inp.json`): 11.119 junções,
7 reservatórios e 14.756 trechos lidos do arquivo, 11.126 feições de ponto e 14.756 de linha gravadas,
941.294,02 m de comprimento declarado, importação em 2,0 s. Topologia habilitada: 11.126 nós e 14.756 arestas.
Traçado conectado a partir de um reservatório alcança 11.126 nós, exatamente o tamanho da componente conexa que
o `networkx` calcula no próprio `.inp`. Exportar e reimportar numa rede nova dá o mesmo grafo, e o
`wntr.sim.EpanetSimulator` 1.5.0 roda o arquivo exportado sem erro.

Nó sem linha em `[COORDINATES]` entra sem geometria e com aviso, jamais como ponto em (0,0) — a refutação
exigida pelo item é teste (`test_adversario_remove_uma_coordenada`), e a soma de comprimento dos trechos não
muda quando a coordenada some, porque ela vem do campo Length e não da geometria. Fica declarado como parcial:
bomba e válvula são LINK no EPANET e ganham aqui o ponto médio dos dois nós (aproximação, não medição), e a
paridade com o "water utility network foundation" da Esri não foi medida — o modelo é fechado e licenciado.
ADR `docs/adr/20260907T1629-epanet-inp.md`. Mesclado no ramo de lançamento em 10/09 (trabalho de turno 4,
resgatado do ramo `wt/il405depane`).

## turno 4, setembro de 2026 (item L4-01-h-alinhamento-inspire-gnm: alinhamento ao INSPIRE Generic Network Model — PARCIAL, elétrica e água)

Mapeamento campo a campo do pacote de ativos (`L4-01-a`) para o Generic Network Model do INSPIRE
(`net`/`us-net-common`/`us-net-el`), documentado em `docs/INSPIRE_GNM.md` (fonte única: `MAPEAMENTO_GNM`
em `app/rede_utilidades/inspire_gnm.py`). Exportador `exportar_gml()` gera GML de uma rede de teste
(elétrica: 3 nós/2 elos com códigos reais de `eletrica-br.json`; água: 2 nós/1 elo) como
`base:SpatialDataSet` com membros `us-net-common:Appurtenance` (nós) e `us-net-common:UtilityLink`
(elos, decisão registrada no documento: `Cable`/`Pipe`/`ElectricityCable` são `UtilityLinkSet`, não
`Link`, e exigiriam uma segunda feature por elo). Validado contra o XSD OFICIAL do INSPIRE (cópia
vendorizada em `app/rede_utilidades/gnm_xsd/`, resolução 100% offline via `gnm_xsd/catalogo.xml`, sem
rede em CI): `xmllint --schema` contra `ElectricityNetwork.xsd` e `UtilityNetworksCommon.xsd`, ambos
`validates` (`tests/unit/test_inspire_gnm.py`, 6 testes verdes). PARCIAL porque o portão pede elétrica,
água e gás: gás fica de fora por não existir pacote-fonte (`L4-01-a` só publicou elétrica e água) — não
é lacuna do mapeamento GNM. Também fora: atributos operacionais (tensão, diâmetro, potência) não têm
correspondência no GNM (ele modela topologia e status, não o dado operacional do ativo) e o teamengine
oficial do INSPIRE não foi rodado (sem instância local nem rede autorizada; a prova usada é `xmllint`
contra o mesmo XSD que o teamengine consome na checagem estrutural). Mesclado no ramo de lançamento em
10/09 (trabalho de turno 4, resgatado do ramo `wt/il401halinh`).

### Commits

| sha | mensagem |
|---|---|
| 3c38aa4 | Alinhamento INSPIRE GNM (item L4-01-h): mapeamento, exportador GML e validação contra o XSD oficial |

## turno 9, setembro de 2026 (item L7-03-d-injecao-consulta: 180 payloads de injeção contra o FeatureServer/OGC, 0 execução, 2 defeitos de 500 corrigidos)

`tests/seguranca/test_injecao.py`: 180 payloads (where/outFields/orderBy/groupBy/outStatistics/having/objectIds/
OGC) contra camada importada de verdade — 0 respostas 5xx, 8 ms de latência máxima, tabela-canário e contagem
intactas; teste estático por AST (nenhum `.execute` em `app/` interpola nome de entrada do usuário) + `bandit
B608` em `app/consulta` fixado em 6 f-strings de lista branca. Corrigidos em `app/consulta/motor.py`: `LIKE` em
coluna numérica e `statisticParameters.value` não numérico devolviam 500 com traceback; agora 400 nomeado
(`_executar`, rede de segurança para erro de tipo do banco). `docs/SEGURANCA.md` §10. ZAP baseline não rodou
(sem imagem, disco 94 %, D21). (Colhido de `wt/cx5l703d`, integrado ao `wt/lancamento` no lote L7 #1; motor.py
aplicado por patch direto, não cherry-pick, porque a árvore de origem está 373 commits atrás.)

## turno 9, setembro de 2026 (item HARD-01-varredura-de-seguranca-continua: varredura de segurança no portão)

- HARD-01-varredura-de-seguranca-continua: `make seguranca` em `make check` (bandit + pip-audit + npm audit + gitleaks no histórico + trivy; ZAP baseline em `make seguranca-zap` contra instância própria), exceções com prazo em `docs/excecoes_seguranca.json`, binárias fixadas por sha256 (`deploy/ferramentas_binarias.txt`), seção 9 de docs/SEGURANCA.md gerada; consertos: defusedxml no Garage, `server_tokens off`, X-Frame-Options e Content-Security-Policy no nginx. (Colhido de `wt/cx4h01`, turno 7/8 daquela trilha, integrado ao `wt/lancamento` no lote L7 #1.)

## turno 9, setembro de 2026 (item L7-29-roteiro-demonstracao: roteiro de 30 minutos com e2e medido, fronteira gerada do painel e revisor separado)

`docs/DEMO.md` percorre o que o produto faz hoje em 9 passos (fundação L0 e mapa L2), cada um com
duração, "o que dizer", "não prometer" e o e2e que anda o mesmo caminho; seção "Passos que o roteiro
não percorre" responde os pedidos frequentes (dado de demonstração, imagens, edição, motor, traçado,
acervo, medição). A lista "o que a demonstração não faz ainda" NÃO é escrita à mão: é a seção
Fronteira de `laco/PAINEL.md` reproduzida entre marcadores, e `docs/gerar_demo.py --validar` reprova
o documento quando o bloco commitado diverge da regeneração (unitários cobrem estrutura, versão de 10
minutos como subconjunto na ordem e a regra de escrita de 03/09 com lista fechada de termos). O texto
foi revisado por agente separado sem o contexto do autor (33 pontos aplicados, nenhum fato mudado) e
o validador passou por cima do texto revisado. `tests/e2e/test_demo.py` percorre os 9 passos na
ordem contra a instalação real com captura por passo (`L7-29-roteiro-demonstracao_pNN_*.png`) e
reprova acima de 30 min: rodada final 71,2 s, 9 passos, 15 capturas, carga 1 min 5,08, RAM livre
7,4 GB (`tests/medidas/L7-29-roteiro-demonstracao.json`; passo mais lento: tarefas, 60,8 s — job de
prova de 45 s + espera de fila vazia + cancelamento pela tela). O e2e documentou o refresco da lista
de tarefas (relê só quando o contador de ativos muda entre tiques de 10 s; a regra está no ADR
`20260908T2030-roteiro-de-demonstracao-medido.md`) e a bancada de trilha passou a aceitar o
certificado autoassinado no contexto do navegador (`tests/e2e/conftest.py`, sem efeito com
certificado de verdade). As dependências do item seguem abertas (L7-01-c refutado, L3-01/L4-02/
L5-01/L6-01 pendentes) e o texto DIZ isso em vez de fingir. A lista "não faz ainda" foi regerada
contra o `PAINEL.md` atual do turno 9 antes de integrar. (Colhido de `wt/il729roteir`, turno 8
daquela trilha, integrado ao `wt/lancamento` no lote L7 #1.)

## turno 9, setembro de 2026 (item L5-03-form-builder: construtor de formulário de atributos, arrasta-e-solta)

Formulário de atributos por camada, versionado e publicável, desenhado arrastando (grupo, campo
obrigatório, domínio, condicional, cálculo) — o "L2-10 formulário" que faltava para a edição web e o
PWA de campo pararem de mostrar um campo-a-campo genérico. Novo `plat.formulario`/`formulario_versao`
(migração `20260910T2350_formulario.sql`), módulo `app/formulario/` (`motor.py` compila o desenho em
duas chaves novas de `plat.item.dados` — `form_condicionais`/`form_calculados` — lidas por
`app/edicao/servico.py::validar_atributos` sem mudar sua assinatura, e valida o mesmo desenho ao vivo
para `app/campo/servico.py`/`visita_criar`, que antes deste item não validava `dados` nenhuma).
Condicional e cálculo usam a linguagem de expressão do item L2-10-c-linguagem-expressao
(`app/expressao/avaliador_py.py`), a MESMA que o navegador usa (`web/js/expressao/avaliador.js`) —
byte a byte, sem duas implementações. Um só motor de RENDERIZAÇÃO no navegador,
`web/js/formulario/motor.js`, importado por `web/js/mapa/edicao.js` (edição web) e
`web/js/campo/roteiro.js` (PWA de campo); construtor arrasta-e-solta em `/camadas/{id}/formulario`
(`web/js/formulario/construtor.js`, sobre as primitivas de `web/js/editor/arrasto.js` do item
L5-08-editor-arrasto, reaproveitadas sem cópia).

Medido: 13 casos de API (`tests/api/test_formulario.py` — obrigatório incondicional e condicional,
domínio, cálculo ignorando o valor do cliente, RLS cruzada 404, desenho inválido recusado) + 1 e2e no
navegador contra a instância viva (`tests/e2e/test_formulario_construtor.py`, `venv/bin/pytest
tests/e2e/test_formulario_construtor.py -m lento --base-url https://demo.iagrointel.com`; medida em
`tests/medidas/L5-03-form-builder.json`): 5 campos em 2 grupos montados por `page.drag_and_drop`
nativo, publicados, e a MESMA sessão de navegador provando a refutação do item ("adversário define
campo obrigatório e submete sem ele pela API") em `POST /api/campo/visitas` — sem "nome" → 422
`campo_obrigatorio`; `categoria=A` sem "ativo" (condicional) → 422; `categoria=B`/`area=5`/
`total=999` enviado pelo cliente → servidor recomputa `total=10` (`area*2`), ignora o valor mandado.

Fora do escopo deste turno: cálculo/condicional na ATUALIZAÇÃO parcial de feição (só cobertos em
`adicionar`, contexto completo garantido; documentado em `app/edicao/servico.py`); domínio "vindo da
camada" é resolvido como um SNAPSHOT na hora de publicar, não uma consulta ao vivo a cada edição;
arrasto de propriedade avançada (visível/obrigatório/cálculo) é campo de texto com a expressão, não um
construtor de condição visual — decisão de escopo, não lacuna escondida.

## turno 9, setembro de 2026 (item L1-02-i-ogc-api-tiles-e-maps: OGC API — Tiles e OGC API — Maps por token)

Fecha a família de padrões OGC da imagem: a casa já falava WMTS, WMS 1.3.0, XYZ, TileJSON, STAC e um
ImageServer compatível Esri (L1-02 e L1-25); faltava OGC API — Tiles (OGC 20-057, classe "GeoData
TileSets") e OGC API — Maps, que é a porta que ArcGIS Pro/QGIS >= 3.34 procuram primeiro. Nova dupla de
módulos `app/imagens/ogc_tiles.py` (JSON puro: landing, conformance, `tileMatrixSets`, coleção, tileset)
e `app/imagens/rotas_ogc_tiles.py` (rotas, mesma porta de entrada `_autorizar` do resto do L1-02) —
nenhuma leitura de pixel própria: ladrilho de item chama `rotas_tiles._servir`, ladrilho de mosaico
chama `rotas_tiles._tile_mosaico_impl`, `/map` chama `tiles.recorte()` — as MESMAS funções que já
atendem XYZ, mosaico ad-hoc/registrado e o `GetMap` do WMS, respectivamente. `docs/adr/20260910T2056-
ogc-api-tiles-e-maps.md` registra as decisões de escopo (`{item}` no caminho vale para item raster OU
mosaico; `/map` só item raster nesta passagem; conformance honesto — 7 classes declaradas, todas
cumpridas, nada a mais).

Medido (`tests/medidas/L1-02-i-ogc-api-tiles-e-maps.json`; suíte própria `tests/api/imagens/
test_ogc_tiles.py`, 22 casos, todos verdes; rodada junto com `test_tiles_token.py` e `test_mosaico.py`
sem regressão — `test_wms.py` tem 2 falhas PRÉ-EXISTENTES, reproduzidas isoladamente ANTES de qualquer
mudança deste item, não relacionadas):

- **ladrilho byte-a-byte igual ao XYZ**, medido na instância viva (`demo.iagrointel.com`) sobre o item
  REAL Sentinel-2B 23KLQ — Guarulhos: `sha256` idêntico (`1cb61eb0…`, 165.711 bytes) entre
  `/svc/<tok>/raster/<item>/10/379/579.png` e `/svc/<tok>/ogc/tiles/collections/<item>/map/tiles/
  WebMercatorQuad/10/579/379.png` (mesma z/x/y, ordem de caminho trocada — `z/y/x` na família nova,
  `z/x/y` no XYZ, conforme a Tabela 4 da 20-057);
- **`/map` byte-a-byte igual ao `GetMap` do WMS**, mesmo item, bbox = extensão inteira reprojetada para
  EPSG:3857, 500×500: `cmp` sem diferença, 729.604 bytes idênticos nos dois lados, `Content-Crs:
  <http://www.opengis.net/def/crs/EPSG/0/3857>` no cabeçalho;
- **`/tileMatrixSets/WebMercatorQuad`** devolve os 25 níveis de zoom do PRÓPRIO `TMS.model_dump()` do
  morecantile (não um resumo escrito à mão) — conferido igual, campo a campo, no teste;
- **tileset metadata do segundo item real** (Ortofoto Mogi das Cruzes 2016): `dataType: "map"`, 7
  entradas de `tileMatrixSetLimits` calculadas em O(1) por zoom (dois cantos do bbox via `TMS.tile()`,
  não enumeração de ladrilhos — evita milhões de tiles num item de poucos graus em zoom alto);
- **grade inválida e token inválido**: `404 tileMatrixSet_invalido` / `403`, nunca 500 nem 200 fingido
  (medido ao vivo também).

Achados corrigidos no próprio turno (autoral, antes do adversário externo — ver §refutação abaixo):
(1) `width`/`height` do `/map` tinham `le=WMS_LARGURA_MAX`/`le=WMS_ALTURA_MAX` no `Query` — como
4096×4096 é EXATAMENTE o teto (`WMS_PIXELS_MAX`), a checagem `width*height > WMS_PIXELS_MAX` nunca
disparava (código morto) e um pedido no canto do teto caía direto no render: medido em **142 s** numa
única chamada de teste antes do conserto. Corrigido para três condições OR'd (mesma forma de
`rotas_wms._get_map`), sem `le=` no Query — o teto em si continua permitido, só o que passa dele é
recusado, e a recusa agora acontece ANTES do render; (2) `/map` de item de OUTRO inquilino devolvia
`422 mapa_nao_suportado` (assumia "não é raster, deve ser mosaico") em vez de `403` — corrigido para
chamar `_resolver_colecao` primeiro (que já dá o 403 honesto de "não existe para este token") e só
recusar por tipo depois de confirmar que o item PERTENCE ao inquilino.

Fora deste turno, nomeado em `docs/PARIDADE.md`: OGC API Maps sobre mosaico (motor de composição por
bbox livre não existe — o que existe compõe por célula da grade); tileset metadata do mosaico AD-HOC
sem registro prévio (mesma lacuna que `mosaico_tilejson`/`mosaico_wmts_rest` já tinham, por
consistência); `collections-selection`, `dataset-tilesets`, formatos vetorial/cobertura/netCDF, `/api`
(OpenAPI próprio desta família), HTML, dimensão `datetime` por coleção; teste com ArcGIS Pro/QGIS reais
(decisão D20 do dono).

**Rodada do adversário independente (mesmo turno, contexto próprio — nunca viu o código nem o
raciocínio acima): veredito PARCIAL.** Confirmou, sem confiar no autor: byte-a-byte idêntico em 10
combinações adicionais de zoom (não só as do autor), isolamento entre inquilinos em toda a superfície
(collections/tileset/tile/map), grade inválida sempre 404 limpo, SSRF/injeção/traversal sempre
recusados, 22 testes próprios verdes. Achou DOIS bugs reais, os dois CORRIGIDOS nesta mesma passagem
com teste de regressão: (1) `bbox=nan,nan,nan,nan`/`-inf,-inf,inf,inf` não levantam `ValueError` em
`float()` — escapavam da checagem de "invertido" e só quebravam dentro de `tiles.recorte`, saindo como
502 `leitura_falhou` (categoria errada); corrigido com `math.isfinite` explícito, 400 `bbox_invalido`.
(2) `crs=EPSG:4326; DROP TABLE x` passava o `startswith("EPSG:")` inteiro (com o texto depois do
número) e só quebrava dentro de `CRS.from_user_input`, ecoando a exceção crua no corpo do 502;
corrigido — o texto após `EPSG:` tem de ser só dígitos, senão 400 `crs_invalido` antes de qualquer
parser. Também mediu, sem corrigir (fora do escopo de uma fachada sobre motor de pixel compartilhado,
registrado em `docs/PARIDADE.md`): `/map` no TETO PERMITIDO (4096×4096) renderiza em ~27 s nesta
bancada — idêntico ao `GetMap` do WMS no mesmo tamanho (~34 s), o mesmo `tiles.recorte` por baixo dos
dois; e zoom abaixo do `minzoom` nativo do item é lento (até 18 s) tanto no XYZ quanto no OGC —
pré-existente no motor `tiles.ladrilho` do item L1-02 base, reproduzido idêntico nos dois caminhos.

Fechando a lacuna que o próprio portão previa e a suíte original ainda não cobria ("…ou em teste
próprio contra o JSON Schema da spec"): nova suíte `tests/api/imagens/test_ogc_tiles_schema.py` (5
casos) valida landing, conformance, `tileMatrixSets` (lista), `tileMatrixSet` (definição) e tileset
metadata contra o documento OpenAPI **bundled** oficial de OGC API — Tiles Part 1
(`tests/dados/ogc_schemas/ogcapi-tiles-1.bundled.json`, baixado 10/09/2026 de
`schemas.opengis.net`, sem depender de rede em execução) — validação de esquema de verdade, não
asserção de campo escrita à mão. Suíte final: **29 + 5 = 34 casos**, todos verdes.

## turno 9, setembro de 2026 (item L2-01-j-comparacao-cortina-tempo: comparação — cortina, lado a lado, lupa e tempo)

Quarta ferramenta do painel "Comparar" do SIG novo (`/sig`, ícone atalho `C`): cortina (swipe) vertical e
horizontal entre dois conjuntos de camadas, lado a lado sincronizado, lupa, e controle de tempo para
camada vetorial com campo de data — o que um parceiro compara com o concorrente em dez segundos. As
quatro ferramentas reaproveitam `Catalogo` (mapa/catalogo.js) em duas instâncias sincronizadas por
evento (`jumpTo` + trava contra retroalimentação) em vez de reescrever fonte/tile/ordem de camada; o
controle de tempo não abriu rota nova nenhuma — usa a MESMA operação `query` do FeatureServer
Esri-compatível que já existia (item L2-04-c), com filtragem 100% no servidor.

Medido na instância viva (`https://demo.iagrointel.com/sig`, captura em `tests/e2e/capturas/`,
`scratchpad/prova_final.py` reproduz a mesma sequência sem depender do `.pytest.lock`, disputado nesta
trilha por outro item rodando em paralelo):

- **sincronismo do lado a lado**: 20 movimentos aleatórios de centro/zoom/rotação só no mapa A —
  diferença de centro entre os dois mapas = **0,0 grau em todos os 20** (`diferencaMaximaCentro` e
  `diferencaCentroFinalLng/Lat` no resultado; zoom e rotação idênticos bit a bit);
- **controle de tempo**: 5 passos da janela instantânea + 3 da acumulativa, os **8 batendo exatamente**
  com `COUNT(*)` direto no banco (consulta SQL independente, não a mesma rota que a tela usa) — camada de
  TESTE de 100.000 pontos com `data_evento timestamptz`, ~3% NULL, 1/4 gravado com fuso diferente de UTC
  (`AT TIME ZONE`), porque nenhuma das 3 camadas reais do inquilino demo tem campo de data tipado
  (`scripts/comparar_demo_tempo.py criar/apagar` — apagada ao final deste item);
- **reprodução a 2 passos/s**: laço que espera cada passo terminar antes do próximo (nunca dois pedidos
  pendentes) — último passo medido em 104-322 ms, sempre abaixo do intervalo de 500 ms;
- **lupa**: achado e corrigido no próprio turno — `_aplicarVisual()` (que liga `pointer-events:none` no
  container em modo lupa, condição para o cursor alcançar o mapa principal por baixo) só rodava no ramo
  cortina/lado-a-lado; sem ela a lupa ficava presa no canto (0,0) do container. Corrigido, medido depois:
  diferença entre o alvo do cursor e o centro do círculo = **0,01 px** (achado pelo e2e, não pelo
  adversário — a suíte ainda não tinha rodado quando o código foi escrito pela primeira vez);
- **0 erros de console** em toda a sequência (cortina × 2 orientações, lado a lado, lupa, tempo × 2
  janelas, reprodução) — os 502 vistos numa rodada anterior eram `/api/imagens/.../tiles/...` de OUTRA
  trilha (item L1-01-j) rodando no mesmo inquilino demo compartilhado sob pressão de RAM da máquina, não
  deste item; o e2e documenta a tolerância e por quê (`tests/e2e/test_comparar.py`).

Fora deste turno, nomeado: controle de tempo para série raster/STAC (item irmão L1-04-serie-temporal,
ainda `pendente`); alça arrastável no divisor do "lado a lado" (hoje fixo 50/50); indicador de
carregamento na lupa enquanto o mapa B monta.

## turno 9, setembro de 2026 (item L1-01-j-proveniencia-da-imagem-lastro: proveniência verificável da imagem)

O "Lastro" da casa aplicado à imagem: o item raster passa a carregar, além do `file:checksum` que já
existia, a extensão `processing` (`processing:software` — versões de GDAL/rio-cogeo/rasterio/`plat`
MEDIDAS na hora da conversão, não uma constante — e `processing:lineage`, texto em português), um bloco
`plat:cadeia` (um passo por perfil convertido, o argv EXATO de cada `gdal_translate`, sha256 de entrada e
de saída) e `plat:manifesto_sha256` (sha256 do item STAC inteiro MENOS essa própria chave — canonicalização
fixa em `app/imagens/proveniencia.py`: `json.dumps(sort_keys=True, separators=(",",":"),
ensure_ascii=False)`). `app/imagens/cog.py` ganhou `ProdutoCOG.comando` (o argv que cada conversão rodou);
`app/imagens/ingestao.py` monta a cadeia e sela o manifesto no MESMO job que já converte, sem round-trip
extra.

Conferência: `POST /api/imagens/<item>/conferir` (`app/imagens/proveniencia.conferir_item`) baixa CADA
asset com checksum de volta do balde em stream (`objetos.sha256_remoto`, nunca o objeto inteiro em RAM),
recalcula o sha256 e compara — divergência POR ATIVO, nunca um veredito único para o item inteiro; um byte
trocado num ativo não esconde nem contamina o veredito dos outros. Preenchimento retroativo dos itens
ingeridos antes deste item, dois caminhos: `POST /api/imagens/proveniencia/preencher-pendentes` (rota de
administração, só metadado — `processing:software` do `plat:versoes` que a ingestão original JÁ media,
`plat:cadeia` fica AUSENTE de propósito, nunca fabricado) e o job de fila `imagens.reexecutar` (pesado:
baixa o bruto, reconverte com o `cog.py` ATUAL e compara o sha256 obtido com o registrado — a prova de
determinismo do portão).

Achado de build que quase quebrou o próprio manifesto: `pgstac.create_item`/`update_item` DESCARTA
qualquer chave de `properties` com valor `null` na gravação — uma ficha selada com `"plat:cadeia": null`
tinha o hash calculado sobre um dict que o banco nunca devolve de volta igual, e `conferir_item` acusava
divergência de manifesto em todo item sem cadeia, sempre, sem nenhum byte alterado. Corrigido: `cadeia=None`
OMITE a chave em vez de gravar `null` (`preencher_propriedades_proveniencia`); achado pelo próprio teste
de integração deste item (não pelo adversário — não houve rodada de adversário separada neste turno).
Segundo achado, de performance: a 1ª varredura de `preencher-pendentes` sem filtro levou 165 s escaneando
217 itens em 236 coleções (`pgstac.items` é particionado POR coleção, e esta trilha compartilhada acumulou
centenas de coleções efêmeras de outras suítes de teste — 16.713 itens pendentes fora do escopo real);
escopado para só a coleção `<tenant_id>-imagens` (`prov.itens_pendentes`), a mesma varredura caiu para
2,8 s.

Prova na instância viva (127.0.0.1:8184, restart de API e worker): os 2 itens raster reais do demo
(Sentinel-2B Guarulhos, Ortofoto Mogi das Cruzes — o 3º item listado antes era um duplicado já apagado)
preenchidos e conferidos, **0 divergências em 2 itens / 8 ativos** (a demo não tem 10 itens raster reais;
número relatado é o real, não inventado). `imagens.reexecutar` rodado de verdade sobre a Ortofoto Mogi
pela fila (job `0ba788c2…`, 10,5 s): **determinismo PROVADO** — sha256 do COG científico e do visual
reconvertidos bateram exatamente com os já registrados, mesmo argv (`NUM_THREADS=ALL_CPUS` incluído).
8 itens de teste (fixtures deste turno, sem dado real) apagados da coleção `1-imagens` ao final.

`tests/api/imagens/test_proveniencia.py` (20 casos, sem depender de GDAL/upload real — a montagem do
item passa pela MESMA `ingestao._item_stac` que `imagens.ingestar` chama, com objetos reais no balde):
unidades de canonicalização/manifesto/cadeia; item novo nasce com os campos; conferência acusa divergência
quando o adversário edita 1 byte do objeto (refutação literal do item) e os OUTROS ativos continuam `ok`;
item de outro inquilino invisível (404) no painel e na conferência; preenchimento leve idempotente; rota
de administração preenche item retroativo e a conferência bate depois. `venv/bin/ruff check app` limpo
nos arquivos deste item (7 erros pré-existentes em `app/jobs/tipos_prova.py`, não tocado, não são deste
turno).

**Adversário independente rodou ao fim do turno (P8) — dois achados, um confirmando, um corrigido.**
Refutação prescrita pelo item (editar 1 byte do objeto no balde com a chave RW e rodar a conferência):
TENTOU, FALHOU — `/conferir` acusou corretamente só o ativo alterado, os outros 3 continuaram `ok`,
`manifesto_ok` continuou `true` (o manifesto certifica os METADADOS do item, não o conteúdo do balde —
separação deliberada, confirmada); byte restaurado, demo devolvido limpo. Achado NOVO, fora da
refutação prescrita: `processing:software`, num item reexecutado (`cadeia_origem=
reexecucao_retroativa`), continuava sendo o `plat:versoes` da ingestão ORIGINAL mesmo quando o GDAL/
rio-cogeo da reexecução era outro — nada cruzava os dois blocos, e o manifesto sela essa combinação sem
reclamar (ele prova integridade PÓS-selagem, nunca veracidade do conteúdo selado). Não é um buraco
alcançável por um cliente da API (a função que grava `processing:software` nunca recebe versão de fora,
só o `plat:versoes` já medido), mas era invisível quando o GDAL do host muda entre a ingestão e uma
reexecução posterior. Corrigido: `plat:reexecucao.versoes_mudaram_desde_a_ingestao` (booleano, comparando
`plat:versoes` × `cog.versoes_software()` medido na hora) — a divergência agora é um campo, não algo que
só se percebe comparando dois blocos manualmente; `LINEAGE_RETROATIVA` cita o campo explicitamente. Sem
teste automatizado novo para este campo (só verificado na instância viva, rodando `imagens.reexecutar`
de novo sobre a Ortofoto Mogi e conferindo `versoes_mudaram_desde_a_ingestao: false`, coerente — o GDAL
não mudou entre as duas rodadas); ver "fora deste turno" abaixo.

Fora deste turno, nomeado: `plat raster reexecutar/verificar <item>` como comando de linha só (hoje: job
de fila + rota HTTP, mesmo caso de uso); reexecução em lote (hoje: um item por chamada de
`imagens.reexecutar`; só a varredura SEM reconversão é em lote); teste automatizado de
`versoes_mudaram_desde_a_ingestao` (hoje só verificado na instância viva — precisa de um jeito de
simular GDAL "trocado" sem depender da máquina ter duas versões instaladas).

## turno 8, setembro de 2026 (item L1-07-mosaico-por-colecao-e-pegadas: mosaico por busca registrada e pegadas)

Um mosaico virou uma busca STAC registrada, não mais um recorte ad-hoc: `POST /svc/<tok>/stac/mosaicos`
grava coleções, período, filtro CQL2 e ordenação, e devolve um id ESTÁVEL — registrar a mesma busca de
novo devolve o mesmo id, o que é o que permite colar o endereço do mosaico num mapa salvo e ele continuar
funcionando quando cenas novas entrarem na coleção. O registro delega ao próprio pgstac
(`pgstac.search_query()`, a mesma função que o `POST /searches/register` do titiler-pgstac chama por
baixo); a composição do ladrilho roda em casa, com `rio_tiler.mosaic.mosaic_reader` (`FirstMethod`) —
pixel a pixel, não cena a cena, o que corrige o mosaico ad-hoc anterior (que escolhia uma cena inteira e
deixava o resto do ladrilho em branco quando a junta caía dentro dele).

Escopo de token agora vale também por mosaico: `tiles:ler:<uuid-do-mosaico>` serve os ladrilhos, o
TileJSON, o WMTS e as pegadas do mosaico sem nunca abrir acesso às cenas avulsas que o compõem — medido
na instância viva (403 no item avulso com o token do mosaico). Pegadas (`GET .../mosaico/<uuid>/pegadas`)
devolvem GeoJSON com `id`/`datetime`/`eo:cloud_cover` por cena, contagem exata contra o que compõe a
busca.

Medido em `tests/medidas/L1-07-mosaico-por-colecao-e-pegadas.json` (`scratchpad/medir_l107.py`, grade
sintética de 6 quadrantes adjacentes, 4 km cada, 20 m/px): ladrilho do mosaico de z8 a z14 fica entre
**64 e 106 ms de Server-Timing** (mediana de 20 pedidos quentes: 89-127 ms; frio de processo em z8:
13,9 s, dominado por abrir a 1ª conexão ao Garage/COG, não por escolher entre cenas). Prova pela
instância real (`scratchpad/prova_l107_mosaico.py`, 127.0.0.1:8184): ladrilho na JUNTA entre dois
quadrantes com `X-Plat-Cenas-Candidatas: 6` e pixel médio 0,0 de um lado × 138,5 de outro (diferença
138,5/255) — os dois lados vieram de cenas DIFERENTES, não uma cena com o resto vazio; pegadas com 6
feições (contagem exata); registro duas vezes com o mesmo critério devolveu o mesmo id nas duas vezes.

Fora deste turno, nomeado: regras de seleção de pixel além de "primeira com dado" — mediana, média,
travar cena, "mais recente sem nuvem" (item irmão L1-08); pegadas como camada vetorial por Martin (só
GeoJSON pela API); tela "Coleção → Mosaico" no construtor de mapa (L2); `mosaicRule` do ImageServer
compatível Esri (L1-25) continua recusando — o item que faltava agora existe, mas ninguém ligou o
parâmetro Esri ao mosaico novo (`app/imagens/rotas_imageserver.py` estava sendo tocado por outra trilha
no mesmo turno; ligar as duas juntas ficou para um próximo turno, ver `docs/PARIDADE.md`).

## turno 7, setembro de 2026 (item L4-04-d-diagrama-esquematico: diagrama de rede, regras e layouts)
## turno 4, setembro de 2026 (item L2-05-e-raster-basico: treze ferramentas raster sobre COG)
## turno 3, setembro de 2026 (item L2-14-a-ingestao-de-fluxos: entrada de eventos em tempo real)
## turno 4, setembro de 2026 (item L4-05-d-epanet-inp: arquivo EPANET .inp entra e sai da rede de água)

Porta de entrada e de saída do formato que o setor de água usa: o `.inp` do EPANET. `ler_inp`/`escrever_inp`
(`app/rede_utilidades/epanet_inp.py`) cobrem JUNCTIONS, RESERVOIRS, TANKS, PIPES, PUMPS, VALVES, COORDINATES,
VERTICES, PATTERNS, CURVES e OPTIONS; seção fora do escopo vira aviso, nunca erro. `POST /api/rede/{id}/epanet`
enfileira o job `rede.epanet_importar`, que grava feições sobre o pacote de ativos `agua-epanet`;
`GET /api/rede/{id}/epanet` reconstrói o arquivo das tabelas, nunca devolve o que entrou. Migração
`20260907T1629_rede_epanet_importacao.sql`: fila da importação, `plat.rede_epanet_curva`/`rede_epanet_padrao`
(as curvas e os padrões que um ativo referencia por ID, e sem as quais o arquivo exportado é recusado pelo
WNTR) e a queda do `NOT NULL` das duas colunas `geom` da rede.

Medido sobre a rede de água real desta casa (`tests/medidas/L4-05-d-epanet-inp.json`): 11.119 junções,
7 reservatórios e 14.756 trechos lidos do arquivo, 11.126 feições de ponto e 14.756 de linha gravadas,
941.294,02 m de comprimento declarado, importação em 2,0 s. Topologia habilitada: 11.126 nós e 14.756 arestas.
Traçado conectado a partir de um reservatório alcança 11.126 nós, exatamente o tamanho da componente conexa que
o `networkx` calcula no próprio `.inp`. Exportar e reimportar numa rede nova dá o mesmo grafo, e o
`wntr.sim.EpanetSimulator` 1.5.0 roda o arquivo exportado sem erro.

Nó sem linha em `[COORDINATES]` entra sem geometria e com aviso, jamais como ponto em (0,0) — a refutação
exigida pelo item é teste (`test_adversario_remove_uma_coordenada`), e a soma de comprimento dos trechos não
muda quando a coordenada some, porque ela vem do campo Length e não da geometria. Fica declarado como parcial:
bomba e válvula são LINK no EPANET e ganham aqui o ponto médio dos dois nós (aproximação, não medição), e a
paridade com o "water utility network foundation" da Esri não foi medida — o modelo é fechado e licenciado.
ADR `docs/adr/20260907T1629-epanet-inp.md`.

## turno 4, setembro de 2026 (item L4-02-a-conectado-e-subrede: traçado conectado e subrede — PARCIAL)

Oito tipos de fonte de evento no vocabulário fechado: receptor HTTP, WebSocket servidor, GPS de frota e sensor
recebem; MQTT, WebSocket cliente, sondagem de URL e AIS vão buscar. Processo próprio `plat-fluxo` na porta
8155, com fila em memória, escrita em lote uma vez por segundo e métrica por fonte; gestão da fonte em
`/api/fluxos`, na aplicação, com escopos de token `fluxo:escrever` e `fluxo:ler`.

Medido contra o processo de verdade, com uvicorn e soquete TCP, em 12 núcleos com carga 6,8 e 6,2 GB livres:
**600.000 eventos em 60,0 s (10.000 por segundo, em lotes de 2.000), 600.000 gravados, perda zero, atraso
mediano de 30,9 ms** e 44,3 ms no percentil 95 contra o teto de 2.000 ms do portão; fila drenada 0,4 s depois
do último envio; memória residente de 78,5 MB; nenhum lote de escrita com erro
(`tests/medidas/L2-14-a-ingestao-de-fluxos.json`).

O que a construção corrigiu na decisão C14: **COPY não escreve em tabela com segurança de linha** — o Postgres
recusa e manda usar INSERT. Como o isolamento por inquilino é cláusula do portão, o lote virou um
`INSERT ... SELECT FROM unnest(...)`, medido em 62.419 linhas por segundo, seis vezes o alvo. A tabela de
eventos é particionada por mês com BRIN em tempo e GIST em geometria, como a decisão pedia.

Também nesta entrada: cliente MQTT 3.1.1 escrito com a biblioteca padrão (a casa não tem `paho` e o disco não
comporta dependência nova), exercido contra um servidor que fala o protocolo no fio; decodificador AIVDM das
mensagens de posição 1, 2, 3 e 18, conferido contra as duas cargas de referência públicas; paridade escrita
contra os tipos de feed do Velocity e do GeoEvent em `docs/PARIDADE.md`, com Kafka, Event Hub, AWS IoT, QoS 2,
MQTT 5 e broker próprio declarados fora.

## turno 4, setembro de 2026 (item L6-02-a-modelo-conexao-e-seguranca)

- O "Bearer da casa" passa a ser provado onde ele nasce, não só dentro de `buscar_seguro`:
  `tests/unit/test_conexao_credencial_chamadores.py` (job `conexoes.saude_verificar`) e
  `tests/api/test_conexoes_credencial_saltos.py` (rota `POST /api/conexoes/{id}/testar`, pela API de verdade,
  com varredura por texto na resposta e no registro de log). Seis guardas `xfail(strict=True)` afirmam o
  comportamento VULNERÁVEL: enquanto o conserto estiver de pé elas falham; se alguém o desfizer, elas passam
  (XPASS) e a suíte fica vermelha.
- `app/garage.py` deixa de seguir `Location` automaticamente nas duas chamadas que mandam `Authorization`
  (`allow_redirects=False`): o outro caminho da casa que montava credencial e seguia redirecionamento.
## turno 48, setembro de 2026 (item L2-16-c-script-vira-ferramenta: script Python com cabeçalho declarativo vira ferramenta do catálogo)

O usuário escreve um script Python cuja DOCSTRING DE MÓDULO é um YAML com o manifesto da ferramenta (nome, título,
parâmetros e saídas) e publica com `POST /api/ferramentas/script`: o cabeçalho é validado ANTES de gravar (422
`cabecalho_invalido`, nada é escrito) e o script vira ITEM `ferramenta_script` versionado pela máquina `item_versao`
do L5-05 — sem registro paralelo. O formulário (`GET /formulario`) é derivado SÓ do cabeçalho (rótulo, exigência,
padrão, mínimo/máximo e JSON Schema por parâmetro); o corpo do script não sai por ele. O vocabulário de tipos é o
GP da família do L2-05-a (texto=GPString, numero=GPDouble, inteiro=GPLong, booleano=GPBoolean,
item=GPFeatureRecordSetLayer). Executar (`POST /executar`, 202) valida os valores ANTES de enfileirar (422
`parametros_invalidos` com detalhe por campo, mesma forma do `dados_invalidos` do catálogo), confere no banco que
toda entrada do tipo `item` existe no inquilino e congela `versao` + `sha256` NO PEDIDO do job: o worker
(`app/ferramentas/script_tarefas.py`) roda o RETRATO imutável da versão pedida, confere o sha256 do texto antes de
rodar (diverge = FalhaDefinitiva) e executa no contêiner do inquilino (L2-16-b) com o teto do `timeout -k` do
coreutils (124 = estouro nomeado). O script lê `entradas.json`, usa o SDK copiado para o diretório de trabalho (o
`plat.saidas` novo grava `saida.json`) e o JOB registra o item `ferramenta_resultado` com procedência
`origem=script, ferramenta_id, versao, sha256_script` e evento `ferramentas/script-executado` (migração
`20260909T0049`). Refutação rodada: script que abre socket, que lê `/etc/shadow`, que grava via SDK em camada sem
permissão e que roda além do teto todos falham presos ao escopo (e sha256 adulterado no pedido é recusado pelo
worker); a execução de versão nova não muda execução passada nenhuma (procedência e log apontam a versão de cada
uma). Cláusula PENDENTE declarada: chamada pelo GPServer `submitJob` depende do ramo `wt/cx205` (L2-05-a), que
não é ancestral deste; o vocabulário GP já está alinhado. Interface `/ferramentas` com formulário renderizado do
cabeçalho e exemplo `examples/ferramentas/buffer_por_campo.py` (buffer por feição via SDK, publicado e executado
pela própria suíte com captura de tela). Medidas e provas em
`tests/medidas/L2-16-c-script-vira-ferramenta.json`; paridade com Python toolbox/web tool em `docs/PARIDADE.md`.

## turno 48, setembro de 2026 (item L2-16-a-sdk-python-geo: SDK Python `plat` e ferramenta por job cujo resultado vira item)

Pacote Python `plat` (`pacote/`, wheel interno por `make pacote`, sem PyPI até decisão do dono): `Plataforma(url,
token)` com quatro domínios — `catalogo`, `acervo`, `jobs` e `ferramentas`. Camada fina espelho da API (mesma
rota, mesmos parâmetros), paginação transparente (`iterar` segue o cursor), espera de job com `ao_progresso`, e
toda recusa vira exceção tipada por status: `ErroPermissao` (403) carrega o código nomeado da casa e o privilégio
`.exigido`; item de outro inquilino é `NaoEncontrado`, porque a RLS da casa devolve 404 de propósito e o SDK não
traduz 404 em 403. A ferramenta `ferramentas.buffer` é um tipo de job comum: buffer PLANO em srid MÉTRICO (srid
geográfico é recusado na porta com pyproj; teto de distância em `app/limites.py`), e o resultado vira ITEM do
catálogo do tipo novo `ferramenta_resultado` — com procedência (sha256 da geometria de entrada, biblioteca e
aproximação declarada) e evento de domínio `ferramentas/buffer` (migrações `20260908T1847` e `20260908T1929`).
`tests/sdk/` (18 testes) prova o HTTP de verdade: a suíte sobe uvicorn e worker próprios em portas efêmeras no
schema da trilha, e os exemplos dos docstrings rodam como doctest contra essa instalação
(`test_sdk_doctests.py`). Medida `ferramenta_buffer_fim_a_fim_s` em `tests/medidas/L2-16-a-sdk-python-geo.json`,
gravada só com carga de 1 min ≤ 8 (a primeira tomada, sob disputa da suíte inteira, foi descartada). Paridade com
o ArcGIS API for Python em `docs/PARIDADE.md` (seção SDK); decisões no ADR `20260908T1955-sdk-python-pacote`. As
cláusulas do portão que dependem de FeatureServer (L2-04-c, parcial sem merge), edição transacional (L2-03-a,
refutado), TiTiler/STAC e nbconvert ficaram PENDENTES declaradas no handoff do item.

## turno 48, setembro de 2026 (item L2-16-b-jupyter-por-inquilino-isolado: notebook JupyterLab por inquilino, com isolamento medido)

Cada inquilino tem um notebook próprio em `/notebooks/{slug}/` — aberto só com SESSÃO da plataforma (token de
serviço não abre; o slug de outro inquilino é 404, não 403). O contêiner sobe sob demanda no docker da própria
máquina (`plat-notebook`, 1,12 GB, construída por `install.sh --imagem-notebook`): partida medida em 2,21 s
(cláusula ≤ 20 s), `--memory 2g --cpus 2`, rede docker `--internal` e o firewall do host derrubando
contêiner→host — de dentro do kernel, a leitura de camada pela API interna funciona e conexão direta ao Postgres
e à internet falham (o código roda no kernel pela API do Jupyter no teste). A API chega ao contêiner por gateway
próprio (contêiner vigia segurando a rede, uvicorn em socket unix do host e uma bomba stdlib lançada por
`nsenter` dentro da rede — nada escuta em TCP do host). O único segredo no contêiner é o token de serviço do
usuário (escopos `catalogo:ler`+`camada:ler`, 1 dia), provado lendo `/proc/1/environ`. Processo que aloca acima
do teto é morto pelo cgroup (rc=137 medido; se a onda do OOM levar o PID 1, o levantar seguinte devolve o
notebook). O ceifador do worker encerra o contêiner sem uso de API por 30 min (ou vida > 12 h), revoga o token e
apaga o volume, e a passagem seguinte pelo proxy reergue na MESMA requisição (conserto do 500 medido: com o
contêiner morto o httpx recebia `http://:8888/...`, que ele reescreve relativo e estoura ValueError). O job
`notebooks.executar` roda o `.ipynb` agendado com `jupyter nbconvert --execute` no mesmo contêiner e grava a
saída HTML como item `notebook_saida` com evento `notebooks/executado` (migração `20260908T2258`: tipo, evento e
`plat.notebook_uso`). A suíte achou e consertou quatro defeitos reais: trava não reentrante no gateway (o mesmo
thread ficou esperando a própria trava), ordem de partida fria (IP do vigia consultado antes de existir), barra
final faltando no `base_url` (404 medido) e `websockets` fora da venv (PYTHONNOUSERSITE=1 da casa esconde
`~/.local`; o handshake do kernel dava 500). Medidas em `tests/medidas/L2-16-b-jupyter-por-inquilino-isolado.json`
(partida só com carga 1 min ≤ 8); paridade com ArcGIS Notebooks em `docs/PARIDADE.md`.
## setembro de 2026 (item L3-01-h-presets: presets nomeados do motor multicritério, aplicação na hora sem job)

Presets do AMC com CRUD por API e tela (`/amc/presets`, privilégio `analise.amc`): tabela
`plat.amc_preset` com RLS por inquilino e visibilidade por dono no escopo `usuario` — o preset de
outro inquilino é 404 `preset_inexistente`, provado na varredura cruzada A→B (GET/PATCH/DELETE/
aplicar) e por colega do mesmo inquilino. Cinco integrados somente leitura nascem com o schema,
entre eles o `pesos iguais` por contrato do item (válido para qualquer matriz). Aplicar
(`POST /api/amc/presets/{id}/aplicar`) recebe só a matriz, roda o combinador na mesma requisição e
devolve o resultado — nenhum `plat.job` é criado e a resposta nem menciona job; a tela nunca chama
`/api/jobs`. Exportar devolve o documento `plat/amc_preset` normalizado; importar recusa preset com
fator fora do modelo informado com 422 `fator_fora_do_modelo` e a lista do que falta (refutação do
item), e ignora o `integrado` do documento (o importado nasce comum). A rota de importar fica ANTES
de `/presets/{id}` porque o FastAPI resolve na ordem de registro. 22 testes de unidade, 12 de API,
8 casos novos na varredura cruzada e 1 e2e playwright ponta a ponta (lista de integrados, criar,
aplicar, exportar, importar, 0 erro de console). Página carrega em 60,8 ms até `body[data-pronto=1]`
no chromium (`tests/medidas/L3-01-h-presets.json`).

## turno 3, setembro de 2026 (item L3-06-criterios-de-feicao: critérios sobre a própria feição)

Quando a unidade de análise é a feição do usuário (imóvel, loja, lote), o critério deixa de ser o que a grade
mediu e passa a ser uma pergunta feita à feição. Entraram quatro: atributo numérico da própria feição,
contagem de pontos de outra camada em raio, contagem dentro e distância ao ponto mais próximo. A influência é
declarada pelo usuário (positiva, inversa, ideal — nota máxima no alvo, com queda simétrica), e o filtro de
inclusão por faixa tira a feição da comparação com o estado `filtrada`, sem posição e sem nota — filtro não é
veto, e valor ausente nunca filtra. `app/amc/criterios_feicao.py` só monta: quem mede é `app/amc/vetorial.py`,
quem transforma é `app/amc/transformacoes.py` e quem combina é `app/amc/combinacao.py`.

Rotas `POST /api/amc/criterios-feicao` (ranque, histograma por critério, matriz de correlação par a par) e
`POST /api/amc/criterios-feicao/exportar?formato=csv`, sem estado e sem tabela própria, e a tela
`/amc/criterios-feicao` com o histograma em SVG e a matriz, sem biblioteca de gráfico.

Medido sobre dado aberto que passou a viver no repositório (1.000 centróides de edificação e 212 lugares do
OpenStreetMap, ODbL 1.0, extraídos do mapa-base local): 1.000 feições × 4 critérios em 131,7 ms, ranque
1..1.000 sem buraco, e a contagem em raio conferida contra `ST_DWithin` do PostGIS feição a feição, com zero
divergência. Números e comandos em `tests/medidas/L3-06-criterios-de-feicao.json`.

Três achados de junção consertados no caminho, todos escondidos porque o `docs/openapi.json` comitado ainda
não trazia `/api/amc`: nenhuma rota do motor multicritério tinha entrada em `tests/api/eventos_esperados.py`;
a preparação da varredura cruzada tinha dois `return`, e o primeiro deixava todo o bloco do L3-01 morto; e a
junção de `app/schema_ambiente.py` tinha perdido a classe `CursorSchemaAmbiente` e duplicado `copy_expert`.

## turno 4, setembro de 2026 (item L4-01-d-atributos-de-rede: fase propagável, traversabilidade, is_connected/subrede — PARCIAL)

`plat.rede_atributo` (catálogo do item L4-01-a) ganha duas flags (`propagavel`, `apoia_traversabilidade`),
marcadas pelo sufixo real do código BDGD ao fim da importação do pacote (`*_fas_con` → propagável;
`*_p_n_ope` → apoia traversabilidade — 8 e 1 linhas marcadas no pacote `eletrica-br`) e semeia 31 linhas
sintéticas de atributo calculado (`comprimento_geodesico`/`is_connected`/`subrede`, `origem = {"calculado":
true}`). Sincronização em dois caminhos: TRIGGER (`AFTER UPDATE` em `rede_feicao_linha`/`_ponto`) copia
valor numa edição só; `POST /api/rede/{id}/atributos/sincronizar` reconstrói em lote a tensão/capacidade da
topologia e `plat.rede_topo_dispositivo_aresta` (a aresta INTERNA de um dispositivo de 2+ terminais — sem
ela o traçado não atravessa uma chave FECHADA; transformador nunca ganha esta aresta). `POST
.../atributos/propagar-fase` propaga a fase por BFS a partir do(s) controlador(es), aplicando
`plat.rede_atributo_substituicao` (regra por tipo, nunca inferida) e gravando divergência em
`plat.rede_atributo_discrepancia` sem nunca corrigir o valor declarado. `POST .../atributos/conectividade`
recalcula `is_connected`/`subrede` por alcançabilidade, respeitando a traversabilidade do dispositivo.
Refutado com uma rede sintética construída à mão (`tests/api/test_rede_atributos.py`, 7 casos): mudar
`FAS_CON` a montante muda a fase propagada de tudo a jusante e NUNCA de um ramo irmão; abrir uma chave
derruba `traversável` da aresta de dispositivo e zera a `subrede` do lado morto. Contrato em
`docs/adr/20260907T1315-atributos-de-rede.md`; modelo e paridade em `docs/rede/ATRIBUTOS.md`.

Medido em escala real (mesma rede da cooperativa de teste do item anterior — 73.512 arestas, 80.456 nós, 21
alimentadores): sincronização em lote em 2,58 s (73.512 arestas de tensão/capacidade atualizadas; 5.481
transformadores avaliados e ignorados por categoria, corretamente — nunca ganham aresta interna); propagação
de fase em 27,7 s (43.709 trechos de MT alcançados, 25.772 discrepâncias gravadas); conectividade em 30,2 s
(44.268/73.512 arestas conectadas em 2 subredes; `WHERE is_connected` devolve exatamente o mesmo número, uso
como filtro provado).

⛔⛔ **CLÁUSULA ABERTA, nomeada, não afrouxada**: a concordância de fase medida contra `FAS_CON` real ficou em
**41,04% (17.937/43.709)**, abaixo do ≥95% do portão. Razão medida, não desculpa: o extrato BDGD desta
cooperativa não tem NENHUMA subestação nem chave de média tensão do pacote `eletrica-br` (só trechos,
transformador e poste) — a propagação usa a extremidade de grau 1 de MENOR id como raiz ASSUMIDA de cada
alimentador (`raizes_assumidas_por_alimentador`), e um alimentador real costuma ter VÁRIAS extremidades de
grau 1 (ramais terminando em derivação monofásica); a raiz assumida não é necessariamente o lado da
subestação, então a fase da raiz e a fase predominante do alimentador podem ser trocadas por acaso. A
mecânica de propagação em si (BFS por caminho, substituição, discrepância, isolamento entre ramos irmãos)
está provada correta pela refutação sintética acima — o que falta é um controlador REAL no mesmo arquivo
para medir a concordância que o enunciado pede; nenhuma subestação/chave existe nesta base para prover isso.
Registrado em `tests/medidas/L4-01-d-atributos-de-rede.json`, cláusula `concordancia_fase_mt`, `"ok": false`.

⛔ Fronteira herdada de L4-01-b (achada ao escrever este item, não bug deste item): `topologia.habilitar`
funde diretamente as duas pontas de um trecho que se tocam quando são do MESMO grupo — pensado para um
trecho partido sem dispositivo no meio. Uma chave de 2 terminais do MESMO tier sentada exatamente sobre esse
encontro (o caso normal de uma chave em série na MT) cai no mesmo grupo de união do lado a lado — vira UM nó
só, não dois; `sincronizar_topologia_lote` detecta e conta (`ignorados_sem_dois_nos`), nunca cria a aresta
com um nó só. Consequência medida: 0 aresta de dispositivo na base real (sem chave no arquivo, a fronteira
nunca chegou a ser exercitada em escala). Ver ADR seção "fronteira achada" para a recomendação a um item
futuro de L4.

## turno 4, setembro de 2026 (item L4-01-b-topologia-derivada: topologia derivada da rede de utilidades)

`POST /api/rede/{id}/topologia/habilitar` reconstrói dois índices derivados das feições da rede —
`plat.rede_topo_no` (um por vértice de conexão/terminal) e `plat.rede_topo_aresta` (um por trecho, com nó de
origem/destino, comprimento geodésico e bitmask de fase) — numa transação, nunca incremental nesta passagem.
Tolerância de coincidência é parâmetro da rede (`plat.rede.tolerancia_m`, padrão 0,05 m), visível na ficha:
0,04 m conecta e 0,06 m não conecta na tolerância padrão; a mesma distância de 0,06 m conecta numa rede que
declarou 0,1 m. Cruzamento geométrico no meio de duas linhas nunca gera nó (cruzar não é conectar). `applyEdits`
de ponto/linha (paridade FeatureServer) marca área suja a cada gravação. RLS ligada e índice GIST conferidos
no catálogo do Postgres (não no arquivo de migração) em todas as 6 tabelas da topologia. Contrato em
`docs/adr/0020-topologia-derivada-da-rede-de-utilidades.md`; modelo e paridade em `docs/rede/TOPOLOGIA.md`.

Medido em escala real (schema `certaja` do `iagro_sat`, ativo da casa, somente leitura — a rede real da
cooperativa de teste, não um arquivo do repositório): 73.512 arestas reais (44.268 MT + 29.244 BT), 80.456
nós, 3.948 órfãos, 0 arestas sem nó, 21 alimentadores com componente conexa idêntica arquivo × topologia
(contador Python independente sobre o wkt cru), 1.554 terminais de alta órfãos batendo exato com o arquivo,
60.549 postes → 0 nós. Conserto de dois achados do próprio agente ao medir em escala (`tests/dados/carga_bdgd.py`):
literal `%` não escapado em SQL parametrizado (`IndexError: tuple index out of range` do psycopg2) e chave
errada num dicionário de retorno (`fins_de_linha` → `fins_de_linha_grau1`).

⛔ Fronteira medida, não fabricada: `certaja.ramlig` (ramal de ligação) tem os 26.581 registros do arquivo mas
**0 com geometria armazenada** (`wkt` nulo em 100%) — entra como atributo, não como aresta geométrica; a
topologia geométrica medida cobre MT + BT + transformador + poste (139.542 elementos reais). Tempo de
`habilitar` variou de ~21 s a ~600 s na mesma carga conforme a disputa por CPU/RAM de outras trilhas na
máquina compartilhada (swap 100% cheio no pior caso) — variação do ambiente, não do algoritmo (lotes de
4.000 linhas, ADR 0020 §5); os dois tempos ficam no arquivo de medida. Manutenção incremental por área suja
e traçado seguem fora desta passagem (itens seguintes da linha L4).
## turno 48, setembro de 2026 (item L4-parcelas-03-ajuste-e-qualidade: ajuste por mínimos quadrados e camada de qualidade da malha)

Ajuste de rede `app/parcelas/ajuste.py` (par do analyzeByLSA/applyLSA do ParcelFabricServer): Gauss-Newton
ponderado em metros e segundos de arco, peso por categoria de ponto (controle 0,005 m; apoio 0,05 m) e de
linha (medido 2 cm/10"; escritura 10 cm/60"; derivado 50 cm/300"), sempre superável por coluna explícita.
Portão resolvido pela prova FORTE: malha sintética 4x5 com desvio inicial determinístico, 30 nós, 3 controles,
98 observações, 54 incógnitas — as coordenadas ajustadas reproduzem a SOLUÇÃO ANALÍTICA a 1 mm (com tolerância
fina, 1e-4 m), e a refutação planta 1 m de erro numa linha de 100 m: ela vira a suspeita nº 1 por dominância
(resíduo normalizado > 3 sigma) e, excluída via `semLinhas`, a rede reconverge com todo resíduo dentro do
sigma. `analisar` não escreve nada (prova por checksum); `aplicar` move ponto com deslocamento estritamente
maior que a tolerância, recompõe linha e face e grava a versão em `plat.parcela_ajuste`. Fachada
`POST /api/parcelas/fabrica/{analyzeByLSA,applyLSA}` na forma da doc. A solução analítica pegou TRÊS bugs que
suíte de fumaça deixaria passar: sinal da derivada de distância, colunas da matriz de design por ponto em vez
de por incógnita e linha de distância sem divisão pelo sigma. Camada de qualidade `POST /api/parcelas/qualidade`
(Find Gaps and Overlaps + regras de atributo, relatório vivo que não altera dado): sobreposição por par do
MESMO tipo, lacuna por face do polygonize DENTRO de cada registro que nenhuma parcela DO REGISTRO cobre, área
declarada × calculada e fechamento acima de 0,10 m. No corpus vivo (`tests/medidas/L4-parcelas-03-ajuste-e-qualidade.json`):
11.473 lotes de exemplo, 9.432 pares de sobreposição e 250 lacunas, ambos conferidos com predicados independentes
(DE-9IM; ST_Difference contra a união do registro). O caminho até o verde custou duas lições de recurso alheio:
a conferência sem pré-filtro de bbox varreu 65,8 milhões de pares e o estouro derrubou o Postgres de produção
(OOM, dmesg 09/09) — e o polygonize do corpus inteiro de uma vez não termina (20 min de GEOS); por registro a
maior malha tem 968 lotes e é trivial. E dois defeitos de SQL pegos pela conferência: cobertura global apagava
lacuna coberta por malha de outro registro (234 × 250) e `ST_Polygonize(g)` com geometria solta resolve para a
forma AGREGADA, que misturava as bordas dos 25 registros — a forma por linha é `ST_Polygonize(ARRAY[g])`.
Paridade §13 (8 fontes datadas) e ADR 20260909T0142.

## turno 48, setembro de 2026 (item L4-parcelas-02-fluxos-cogo: fluxos de edição e fachada ParcelFabricServer)

Fluxos de edição da malha (`app/parcelas/fluxos.py`): dividir por rumo com as três
`divideOption` da referência (área igual — portão: 2 partes de 5.000 m² com desvio ≤ 0,01 m²;
proporção; faixas de largura fixa), dividir por linha de corte (linha que não cruza é recusada
com `linha_nao_cruza` — nunca divisão em silêncio), unir (as linhas externas continuam ativas e
passam à parcela unida; a divisa interna é RETIRADA — nada é apagado), recortar com as três
`clipOption`, construir parcelas a partir de linhas livres (build por `ST_Polygonize`), sementes
(`plat.parcela_semente`: createSeeds → build ignora a face com semente → reconstructFromSeeds
consome e devolve `reconstructedParcelCount`), duplicar, mudar tipo (edição de atributo) e
atribuir feição a registro com `CreatedByRecord`/`RetiredByRecord` (retirada pelo mesmo registro
que criou é recusada). Traverse COGO: poligonal de 6 lados fecha com erro conhecido raiz de 2 m
(± 1 mm) e o traverse que erra 5 m nasce com `erro_fechamento_m` = 5,000 e razão 81 exibidos —
não fecha em silêncio. Fachada REST `POST /api/parcelas/fabrica/{build,divide,merge,clip,
createSeeds,reconstructFromSeeds,assignFeaturesToRecord}` na forma da documentação do
ParcelFabricServer (`moment`, `success`, `serviceEdits`), escopo de token `parcelas:usar`,
registro triplo de rota (casos cruzados + eventos + x-auth/x-privilegio). Leitor de DXF ASCII
(`app/parcelas/dxf.py`: LINE e LWPOLYLINE; binário e DWG fora, declarado) com dado aberto da
casa: a planta de teste (corpus aberto de projeto) entra com 557 segmentos, o build fecha 125
faces e a camada LOT do desenho vira exatamente 1 lote de 525 m² (área conferida pela fórmula do
sapateiro no teste, independente do ST_Area; `tests/medidas/L4-parcelas-02-fluxos-cogo.json`).
Paridade §11/§12 escrita.

## turno 48, setembro de 2026 (item L4-parcelas-01-modelo-de-parcelas: malha de parcelas orientada a registro, retirar não apaga)

Seis tabelas por inquilino (`db/migracoes/20260908T2140_parcelas.sql`): `parcela_registro` (o documento
legal, vocabulário fechado), `parcela_ponto` (precisão declarada, ponto fixo), `parcela_linha` (COGO:
rumo, distância, raio COM SINAL, comprimento de arco, precisão de rumo e de distância),
`parcela_linha_parcela` (divisa partilhada n:n), `parcela` (polígono por tipo fechado — lote, gleba,
quadra, servidão, estrato — com área declarada, área calculada pelo banco e erro de fechamento) e
`parcela_conexao`. Biblioteca `app/parcelas/` (modelo, cogo, importar, validação): retirar parcela é
ato de registro que NÃO apaga — sai do atual, entra no histórico com o registro, linha exclusiva sai
junto, linha partilhada fica, ponto fica. Import dos lotes derivados do SIG de teste interno (dado
aberto, schema `sigcorp`, só leitura por `COPY` como postgres) com registro sintético por
empreendimento e vértice/linha deduplicados. Validação de sobreposição por consulta viva entre
parcelas ativas do mesmo tipo (tolerância 1 cm²). Paridade com o esquema do parcel fabric do ArcGIS
Pro 3.4 escrita com fontes datadas (`docs/PARIDADE_PARCELAS.md`); decisões em
`docs/adr/20260908T2210-parcelas.md`. Visões `v_parcela_atual`/`v_parcela_historico` com
`security_invoker` — a visão responde com a RLS de quem consulta, senão o histórico vazaria inquilino
pela porta do dono.
## turno 5, setembro de 2026 (item L5-20-sites-paginas-publicas: site do inquilino em /s/<inquilino>/)

O inquilino monta um site por arrasto e o publica numa URL pública própria. O documento do site é o MESMO
envelope de app e painel (`corpo.nos`, lista plana, aninhamento por `pai`), montado no MESMO editor de
arrasto do L5-08 com uma paleta nova: `pagina` na raiz, `secao` dentro da página, cartão dentro da seção,
mais `cabecalho`, `menu` e `rodape`, que pertencem ao site inteiro. São nove cartões — texto, imagem,
galeria de itens do catálogo com filtro, mapa incorporado, aplicativo, busca de conteúdo, chamada com
botão, estatísticas e conteúdo incorporado por https.

A página publicada é renderizada NO SERVIDOR e não depende de JavaScript: `curl` sem navegador já lê o
texto de cada cartão, e a página não tem uma linha de `<script>` (`tests/api/catalogo/test_site.py`). A
galeria e a busca são formulários `GET` respondidos já filtrados; a estatística é contagem feita no pedido;
o mapa e o aplicativo são quadros para a vitrine `/p/` do L5-14, com link equivalente ao lado. Medido no
site de teste: **3 páginas publicadas e os 9 tipos de cartão presentes no HTML**
(`tests/medidas/L5-20-sites-paginas-publicas.json`).

Tudo o que a página anônima lê passa por função `SECURITY DEFINER` que filtra `acesso = 'publico'` e
`plat.tenant_permite_publico` — a definição de "compartilhado com todos" nesta plataforma. O adversário
procurou o item privado de três maneiras (filtro por tipo na galeria, busca pelo título exato e citação por
uuid num cartão): **0 item privado vazado**; o cartão que aponta para item que deixou de ser público diz que
o conteúdo não está compartilhado, em vez de mostrá-lo.

`noindex, nofollow` é o padrão, no cabeçalho `X-Robots-Tag` e no `<meta>`; `index, follow` só com a opção
ligada explicitamente na tela, que traz o aviso ao lado. Como o `add_header` do nginx acrescenta em vez de
substituir, `deploy/nginx.conf` ganhou um `location /s/` sem o `X-Robots-Tag` herdado — nesse caminho quem
decide é a aplicação; em homologação a exceção não existe, de propósito. A página manda ainda
`default-src 'self'` com `frame-src` limitado às origens que AQUELA página declara.

Acessibilidade da página publicada: auditoria axe-core 4.12.1 (o motor que o Lighthouse usa nessa
categoria) nas etiquetas WCAG 2.0/2.1 A e AA, ponderada por impacto = **100 de 100, 0 violação crítica ou
séria**. Não é o binário do Lighthouse, que não está instalado nesta máquina; a medida diz isso no campo
`comando`. A cor do texto sobre a marca do inquilino é escolhida no servidor pelo contraste (WCAG 1.4.3),
para que um inquilino de cor clara não fique com texto branco sobre fundo claro.

Paridade escrita contra "Create a site" e os cartões do Hub em `docs/PARIDADE.md`, com a ressalva de método
registrada: a doc do Hub monta o conteúdo por JavaScript e não devolve texto ao `curl`, então a coluna Esri
vem da leitura do papel esri, nunca de citação literal de página estática.

## turno 5, setembro de 2026 (item L5-37-pacotes-modelos-entre-inquilinos: pacote de documentos e galeria de modelos)

`GET /api/itens/{id}/pacote` devolve um zip com `manifesto.json` e um `documentos/<id>.json` por documento
do fecho de dependências: o app, o mapa, o estilo, o formulário, o fluxo. Item cujo tipo tem
`tem_dado_fisico` (camada, vista, imagem, arquivo, rede) NÃO entra — é declarado como FONTE, com os campos,
a geometria e o SRID que o documento assume, e nada mais. Por isso o pacote do app de teste (2 documentos,
3 fontes) tem **1.622 bytes** (`tests/medidas/L5-37-pacotes-modelos-entre-inquilinos.json`): não há dado
dentro, o que o torna transportável entre inquilinos e entre instalações.

`POST /api/pacotes/verificar` é a tela do "antes de importar": não escreve nada e devolve, por fonte, a
diferença de esquema **campo a campo** (`campo_ausente`, `tipo_diferente`, `geometria_diferente` bloqueiam;
`srid_diferente` é reportado e não bloqueia, porque reprojetar é rotina e o documento não guarda
coordenada). `POST /api/pacotes/importar` só passa quando a análise diz `pronto`, e faz tudo numa transação.

Na importação, cada identificador é regerado — UUID de documento e ULID de nó — e todas as referências são
reescritas numa passada só; importar o mesmo pacote duas vezes dá dois conjuntos de itens sem nenhum id em
comum. A trava de segurança é a mesma passada: **todo UUID citado em qualquer lugar do documento** tem de
ser outro documento do pacote ou uma fonte mapeada para item que o inquilino de destino enxerga; qualquer
outro faz a importação inteira parar com `referencia_desconhecida`, sem criar nada. A leitura do zip
reaproveita literalmente `app/ingestao/formatos.py::conferir_zip` (a guarda que o upload de dado já usa),
então `../`, caminho absoluto, link simbólico, zip aninhado e zip-bomba são recusados antes de qualquer
`json.loads`. A assinatura é o sha256 da forma canônica do manifesto (a mesma do L5-05, reproduzível com
`jq -cS | sha256sum`), e o manifesto traz o sha256 de cada documento: um byte trocado em qualquer lugar
vira `pacote_adulterado`.

Galeria de modelos: `plat.pacote_modelo` (migração `20260908T1055`) guarda o zip em `bytea` — pacote é
pequeno e a galeria tem de funcionar no appliance, onde pode não haver armazenamento de objetos. Escopo
`inquilino` (só quem publicou vê) ou `plataforma` (todos veem); quem recusa o escopo `plataforma` de quem
não é superadmin é a POLÍTICA DE LINHA, não um `if` da rota. Modelo é imutável: republicar é publicar outro.
Tela `/modelos` lista a galeria, aceita zip do disco, monta o mapeamento fonte a fonte por seleção e mostra
as diferenças de esquema antes do botão de importar.

Limitação honesta, registrada aqui para ninguém prometer o que não existe: a parte "do canal" da hipótese
(parceiro publica modelo para OS INQUILINOS DELE) ficou de fora porque não existe hierarquia de inquilino
nesta plataforma — há `plataforma` e há `inquilino`, e nada entre os dois. Quando o item que criar a relação
parceiro→inquilinos chegar, é um valor a mais no `CHECK` do escopo e uma cláusula a mais na política.

## turno 5, setembro de 2026 (item L5-14-publicacao-links-embed: publicação de documento de construtor — links e embed)

## turno 7, setembro de 2026 (item L7-19-segredos-e-certificados: os 5 segredos fora do .env, rotação com 0 erro 5xx medido pelo k6)

Colheita da bancada `wt/segredos` (interrompida por limite de cota em 06/09) mais o conserto do que a
medição honesta achou nela. `PLAT_DSN`, `PLAT_GARAGE_ADMIN_TOKEN` e `PLAT_SECRET_ANTERIOR` saíram do
`.env` para `/etc/plat/segredos` (root 0600) entregues por `LoadCredential=` do systemd — o `.env` fica
só com configuração, e o Makefile injeta os segredos no pytest (a falta de `PLAT_DSN` na injeção tinha
deixado a suíte vermelha na coleta desde 06/09 à noite). `scripts/plat segredo rotacionar <nome>`
rotaciona os 5 segredos: PLAT_SECRET com dupla-chave (o valor antigo vira `PLAT_SECRET_ANTERIOR` por 24
h, sessões sobrevivem), PLAT_DSN e PLAT_DSN_WORKER com `ALTER ROLE` + reinício das consumidoras,
PLAT_GARAGE_ADMIN_TOKEN com restart do Garage + API, e a chave S3 de um inquilino sem reiniciar nada.
Em todos, o valor antigo deixa de autenticar (prova por `psycopg2.connect` com a senha velha depois da
rotação). A cláusula "0 erro 5xx durante a rotação" é medida pelo **k6** (v2.2.0,
`scripts/k6_saude_5xx.js`, martelo externo ao processo medido): 0 respostas 5xx em 276-762 requisições
por rotação (`tests/medidas/L7-19.json`). Chegar ao zero exigiu trocar o mecanismo depois de duas
medições ruins: "restart em cadeia" deixou 57 respostas 500 na janela entre o `ALTER ROLE` e o restart
da segunda unidade, e "parar tudo antes" deixou 1.334, porque com ativação por soquete a própria
conexão do cliente religa o serviço com a credencial velha (e `mask --runtime` não impede a religação
de unidade estática, medido em spike). O mecanismo final é uma janela `trust` de segundos no pg_hba
(só a role, só 127.0.0.1, linha marcada, removida por `finally`): velho e novo autenticam durante a
troca, e a senha velha morre quando a janela fecha. A API passa a subir por ativação por soquete
(`deploy/plat-api.socket`, uvicorn `--fd 3` com 2 workers — spike medido: conexão durante o stop
espera ~1 s e recebe 200, nunca refused/502). O adversário independente refutou a primeira versão e os achados que eram do item viraram conserto
neste mesmo turno: a janela trust abre dentro do `try` (linha nunca fica para trás no pg_hba, checado a
cada prova), a rotação de PLAT_SECRET reinicia também o worker (ele carrega a chave uma vez na subida e
decifra dentro de jobs), e o ANTERIOR expira de verdade — timer `plat-segredo-expira.timer` esvazia o
arquivo e reinicia API e worker na virada das 24 h (janela efetiva 24 h-24 h 59 min). Os achados que são
contaminação do ambiente ANTERIOR ao item (segredos reais semeados no journal por comandos de outras
operações; `.env` de worktrees de trilha com valores reais, um deles modo 664; segredos em
`/proc/<pid>/environ` de processos de trilha) ficaram registrados em `refutacao.json` e viraram itens
próprios do backlog com dono nomeado — o desenho do produto em si saiu limpo: unidades plat-* só veem os
segredos por `LoadCredential=`, repositório e histórico git com 0 ocorrências, `.env` raiz sem segredo.
Runbook em `docs/RUNBOOKS/segredos.md` (procedimento por segredo, janela trust declarada, ressalva do
garage.toml do daemon, que é da frente plataforma/pipeline e o produto nunca lê em operação).
## turno 3, setembro de 2026 (item L2-06-d-atualizacao-viva-sse: o painel reflete a edição sem recarregar)

O dado muda no banco e a tela mostra o número novo, sem recarregamento e sem sondagem. Gatilho POR COMANDO
na tabela física da camada (`plat.camada_notificar`, migração `20260908T0702_camada_eventos_vivos.sql`):
uma edição em lote de N linhas gera UM evento, não N. `pg_notify` no canal do schema, um `LISTEN` por
processo da aplicação e fan-out por camada para as conexões abertas — o MESMO desenho do progresso de
tarefa, não um segundo mecanismo de empurrão. Rota nova `GET /api/eventos/camadas?camadas=a,b`
(Server-Sent Events, autenticada): camada inexistente ou de outro inquilino é 404 na hora, cota estourada
é 429 na hora, `PLAT_SSE_LIGADO=false` é 503 na hora — nada que possa recusar entra no fluxo. Reconexão
recupera o que passou pela janela de retenção de quinze minutos (`Last-Event-ID`); a volta ainda marca
todas as camadas assinadas como sujas, porque entre a queda e o retorno pode ter passado edição que a
janela não alcança. No navegador, uma assinatura por tela agrupa a rajada em um segundo e refaz uma
consulta por fonte afetada; com o fluxo de pé o intervalo de cada fonte fica desligado e só volta se o
fluxo se declarar indisponível. O cabeçalho mostra "atualizado às hh:mm:ss" e diz quando está no intervalo
em vez do fluxo. Medido: 0,0005 s do COMMIT ao quadro no consumidor (teto do portão: 1 s); mil eventos numa
rajada viram uma consulta. Limites em `app/limites.py` (100 conexões por inquilino, 10 por usuário, 50
camadas por conexão, 30 min por conexão). ADR `docs/adr/20260908T0702-atualizacao-viva-de-camada.md`.
Fecha também três registros que faltavam das rotas do L2-06-a (caso cruzado, evento e `docs/openapi.json`).


## turno 3, setembro de 2026 (item L3-02-c-smaa: que pesos precisariam ser verdade para esta unidade ganhar)

SMAA-2 simplificado (Lahdelma e Salminen, 2001) sobre o sorteio de pesos do item L3-02-a: para cada
unidade, o indice de aceitabilidade por posicao (a fracao dos vetores de peso sorteados em que ela
ficou em 1o, 2o ... 20o lugar), o vetor central de pesos (a media dos pesos que a puseram em primeiro,
normalizada) e o fator de confianca (1 se ela fica mesmo em primeiro quando a combinacao e refeita com
esse vetor central). O modulo `app/amc/smaa.py` nao reimplementa nada: chama `sortear_pesos` do
L3-02-a e `combinar` do L3-01-e, e roda como job `amc.smaa` pela mesma razao da robustez (A8), sem
rota nova de API. A saida traz a tabela do top-20 com o vetor central em cada linha e
`explicacao_da_unidade`, que exibe o vetor central fator a fator em portugues.

A prova central e de resposta CONHECIDA, nao conferida contra a propria implementacao: tres unidades
sinteticas com dois fatores -- A=(100,0), B=(0,100), C=(49,49) -- e peso uniforme no simplex dao, na
conta a mao, aceitabilidade de primeiro lugar 0,5 / 0,5 / 0, C em segundo em 98 % dos sorteios e vetor
central (0,75; 0,25) para A. Medido com 20 mil sorteios: 0,5046 / 0,4955 / 0 e (0,7501; 0,2499). A
conferencia do adversario do item -- soma da aceitabilidade de primeiro lugar entre TODAS as unidades
igual a 1 +- 0,01 -- da 1,0 exato em 2.000 unidades x 1.000 sorteios (`tests/medidas/L3-02-c-smaa.json`),
por construcao: cada sorteio tem um vencedor so, com empate desempatado pela ordem da unidade. Quando
nao ha vencedor possivel (todas vetadas ou sem nota) a soma cai abaixo de 1 e a saida diz quantos
sorteios foram, em vez de inventar vencedor. Tempo do job: 0,221 s para 1.000 sorteios em 2.000
unidades x 6 fatores, com carga de 1 min 7,73 e 4,52 GB livres.

Limites escritos em `docs/AMC_SMAA.md` e carregados dentro da propria saida (campo `limites`): so o
peso e sorteado, entao a leitura vale sob incerteza de peso e nunca sob incerteza do dado; com
combinador linear e fator deterministico a regiao de pesos vencedores e convexa e o fator de confianca
da 1 por construcao (ele so separa com combinador nao linear, e por isso e medido e nao assumido);
combinador que ignora peso por definicao torna o sorteio inocuo; empate depende da ordem de entrada; e
linha inteira em zero quer dizer fora das 20 posicoes contadas, nunca ultimo lugar. ADR em
`docs/adr/20260908T1029-smaa-aceitabilidade-por-posicao.md`.

## turno 3, setembro de 2026 (item L4-05-e-gas-e-esgoto: pacotes de gás e de esgoto, escoamento por cota e importação TEKSI)

Dois pacotes de ativos novos, entregues como dado: `gas-br` (1 domínio, 4 tiers de PRESSÃO, 7 grupos, 24 tipos,
51 atributos, 29 regras, 3 configurações de terminal) e `esgoto-teksi` (2 domínios, tier por BACIA, 9 grupos,
21 tipos, 104 atributos com a coluna de origem do datamodel aberto TEKSI, 29 regras). Três rotas:
`GET /api/rede/{id}/esgoto/escoamento` confere se a ponta declarada como jusante é a mais baixa em cada trecho
que escoa por gravidade — e NUNCA inverte nada, cada divergência sai como problema nomeado com as duas cotas;
`GET /api/rede/{id}/gas/pressao` confere que todo regulador reduz pressão e que não há emenda entre tiers
diferentes sem controlador de pressão ao lado; `POST /api/rede/{id}/teksi` importa um GeoPackage no esquema
TEKSI (lido com o `sqlite3` da biblioteca padrão, sem GDAL) usando como de-para as origens declaradas no
próprio pacote. Rede sintética de 200 elementos com cotas em `tests/dados/gerar_esgoto.py`: os 99 trechos
concordam em 100 %, e inverter a cota de um deles derruba para 98 com o problema `contrafluxo`, sem que a
geometria mude. ADR 20260908T1054; paridade em `docs/rede/PARIDADE_GAS.md` (com o que NÃO foi conferido dito
em voz alta). De quebra, as 11 rotas de escrita de `/api/rede` ganharam a declaração de evento que faltava em
`tests/api/eventos_esperados.py`, e `docs/openapi.json` voltou a bater com a aplicação.

## turno 3, setembro de 2026 (item L3-19-multiescala: grades aninhadas do motor multicritério)

Construído do zero neste turno (RESGATE da sessão executora derrubada por cota só tinha a migração,
`app/multiescala/{crs,motor}.py` ainda sem rota nenhuma). Duas execuções ligadas: `POST
/api/multiescala/conjuntos/{id}/macro` gera a grade grosseira sobre a área de estudo inteira e roda a
combinação; `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina SÓ dentro das células macro
aprovadas (aritmético — a query de geração junta a região aprovada ANTES de expandir as sub-células, nunca
gera tudo para descartar depois) e roda a mesma combinação nela. `GET /api/multiescala/execucoes/{id}`
devolve o relatório por fator com `escala`/`escala_grosseira`/`razao_escala`, calculado pelo motor a partir
de `resolucao_fonte_m` (declarada no fator) x `resolucao_grade_m` (da execução) — o cliente nunca envia
esse campo. CRUD completo: `/conjuntos`, `/fatores`, `/fatores/{id}/amostras` (carga em lote),
`/execucoes`; `DELETE` de conjunto e fator (cascata pelas FKs da migração), acrescentados neste turno para
a varredura cruzada ter como limpar o que cria. Escopo de token novo `multiescala:usar`
(`app/auth/escopos.py`). ADR `docs/adr/20260906T1640-grades-aninhadas-multiescala.md`.

Um defeito de FRAMEWORK achado e corrigido, fora do arquivo deste item mas bloqueando-o:
`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` em `execute` e
`callproc`, mas não em `executemany` (psycopg2 implementa em C e não chama `execute` de volta) —
`POST /api/multiescala/fatores/{id}/amostras` falhava com `permission denied for schema plat` em qualquer
trilha. A MESMA lacuna já quebrava `POST /api/papeis` (não deste item), convertida por `erro_do_banco` num
403 "operação fora do inquilino da sessão" que parecia RLS cruzada e não era — reproduzido e confirmado
antes de mexer. Corrigido na classe (um método a mais, mesmo corpo de `execute`), vale para as duas rotas.

Um defeito do próprio teste (não do motor) achado rodando de verdade: uma área de estudo desenhada só um
pouco maior que a resolução da grade (~1,35-1,47 km sobre 1 km) produz uma célula-fatia cujo CENTRO
nominal (usado para achar o bloco de dado) cai FORA da extensão real da amostra — 2 das 4 células macro
ficavam sem nota, não por bug, porque nenhuma amostra alcançava o bloco que aquela célula ia procurar.
Corrigido aumentando a área de teste para 1.900 x 1.900 m (documentado no ADR, decisão B, para o próximo
teste desta família não tropeçar na mesma coisa).

Medido de verdade (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L3-19-multiescala.json`), 10/10 testes passam
duas vezes seguidas: grade macro de 1 km sobre estudo de 1.900x1.900 m dá 4 células, top_pct 50% aprova 2;
grade micro de 100 m (k=10) gera exatamente 200 células (2 aprovadas × 10²) contra 400 possíveis (4×10²) —
economia de 50,0%; o mesmo fator (1.000 m de escala nativa) sai `própria` na grade de 1 km e `grosseira`
na grade de 100 m da MESMA execução ligada, sem o cliente declarar nada de diferente — é a refutação do
item. `tests/api/multiescala/test_multiescala.py`: 10/10.

**Fora do portão deste turno, registrado no ADR**: `docs/openapi.json` comitado não inclui
`/api/multiescala/*` (regeneração é pendência do gerente após os merges); os 11 casos da varredura cruzada
já estão em `tests/api/cruzado_casos.py` (conferidos à mão contra o app rodando — todas as 11 rotas
recusam ou isolam o cross-tenant corretamente) e passam a valer em `test_cobertura_100_por_cento`/
`test_rota_nao_cruza` assim que `make openapi` rodar contra a árvore juntada. `L3-01-b-unidades`
(dependência declarada) segue PARCIAL num ramo não juntado (`wt/amc`); este item não depende dele em
código (CRS resolvido de forma própria em `app/multiescala/crs.py`), só na hipótese conceitual.
## turno 5, setembro de 2026 (item L5-01-a-layout-paginas: páginas e layout do app)

Sobre o editor de arrasto do L5-08: paleta nova (`web/js/editor/paleta_paginas.js`) com `pagina` (tela cheia
× rolável; `caminho`/`titulo`/`ordem`/`oculta`/`inicial`), `cabecalho`, `rodape`, `menu`, os widgets de
layout do Experience Builder (`linha`, `coluna`, `grade`, `acordeao`, `painel_fixo`, `painel_lateral`) e
`janela` (`modal`/`ancorada`) + `secao_vistas`/`vista`. Executor novo (`web/js/executor/{executor,paginas}.js`
+ tela `/executar?item=<id>&pagina=<caminho>`, `app/paginas.py`) que renderiza o MESMO documento como app de
verdade: nav entre páginas por `history.pushState`, `<dialog>` nativo para janela modal, painel lateral que
recolhe sem `display:none`, grade em CSS Grid `fr`. `web/js/editor/tela.js` escolhe a paleta pelo `tipo` do
item (`app` → paleta de páginas; o resto continua com a paleta comum do L5-08) — única mudança num arquivo
que outro item também toca.

Medido (`tests/medidas/L5-01-a-layout-paginas.json`, e2e `tests/e2e/test_layout_paginas.py`): app de 2
páginas (Central tela-cheia com mapa, Detalhes rolável com painel lateral/grade/janela) montado só por
arrasto (2.245,1 ms); menu navega e a URL muda por página, F5 reabre na página certa; painel lateral
recolhe/expande; grade mantém a razão 8:4 entre dois filhos em 1200 px (2,016) e 600 px (2,033) — diferença
0,017; janela modal abre pelo botão e fecha por Esc (`<dialog>` nativo). Refutação do adversário: 6 níveis
alternando linha/coluna, com irmão ao lado do 1º nível, em 3 larguras de viewport (1280/800/320) — 0 px de
estouro horizontal e nenhum nível com largura, altura, `display` ou `visibility` zerados (a correção que fez
isso passar foi `min-width:0`/`min-height:0` em todo item flexível, ADR
`20260907T1355-paginas-e-layout-do-app`). Achado corrigido no caminho: `drag_and_drop` sobre o SELETOR do
contêiner-alvo mira o CENTRO da caixa — quando o contêiner já tem um filho de largura 12/12, o centro cai
sobre o filho e o `drop` do HTML5 é entregue a ele, não ao contêiner (o novo nó entra um nível mais fundo do
que o pedido); o teste agora solta sempre no FUNDO do contêiner, como o e2e do L5-08 já fazia na raiz.
Paridade contra "Add and manage pages" e "Layout widgets" (doc EXB) em `docs/PARIDADE.md`.

## turno 4, setembro de 2026 (item L5-08-editor-arrasto: primitivas de edição compartilhadas pelos construtores)

Editor de arrasto próprio em `web/js/editor/` (5 módulos, 43.771 bytes medidos; 0 byte de biblioteca de
arrasto — `web/vendor/VERSOES.txt` segue sem SortableJS, dnd-kit ou GridStack) e tela `/construtor?item=<id>`
sobre o documento do L5-05. Paleta→tela e tela→tela por HTML5 Drag and Drop; alça de largura por Pointer
Events com `setPointerCapture`; árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e
menu "mover para" para quem só tem toque. Largura sempre em COLUNAS da grade de 12, nunca em pixel.

Medido (`tests/medidas/L5-08-editor-arrasto.json`, e2e `tests/e2e/test_editor_arrasto.py` contra a base da
trilha): o MESMO layout de 5 componentes montado só por arrasto (787,5 ms) e só por teclado e menus
(134,0 ms) grava dois documentos idênticos — diferença 0 depois de trocar cada ULID por `n1..nN` na ordem de
profundidade (o ULID é aleatório por construção, D2). Redimensionar por arrasto levou o mapa de 8 para 4
colunas nos dois caminhos; `"px"` não aparece no documento gravado. A árvore reflete o aninhamento
(aria-level 1/2/2/1/1). O painel recusa zoom 99 num campo `maximum: 22`: mensagem no campo, `aria-invalid`,
e o documento salvo depois continua com 12. Refutação do adversário no mesmo arquivo: soltar um contêiner
dentro de um descendente dele é recusado com motivo ("dentro de si"), soltar fora da tela não muda nada, o
menu de mover não oferece destino dentro do próprio nó, e o layout inteiro se monta só por toque no viewport
Pixel 7 (onde o HTML5 Drag and Drop não dispara). 0 erro de console em todos os caminhos.

Achado de ambiente: esta é a primeira tela que grava por `fetch` sob cookie a partir do navegador, e por
isso a primeira a bater no 403 `origem_invalida` quando `PLAT_URL_PUBLICA` não é a origem servida — os e2e
anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`. Em produção as duas
coincidem; no ambiente da trilha o nginx local reescreve o cabeçalho. ADR 20260907T0302.
## turno 5, setembro de 2026 (item L2-03-edicao: fechamento — dois achados corrigidos, junção do turno 4)

- **Treze ferramentas raster** (`app/ferramentas/raster.py`) no mesmo registro das vetoriais: estatísticas zonais,
  calculadora, reclassificar, recortar, reprojetar, mosaico, terreno (declividade, orientação, sombreamento,
  rugosidade, TPI), curvas de nível, vetorizar, rasterizar, amostrar em pontos, visibilidade e distância euclidiana.
- **Leitura por janela sobre o COG onde ele está** (`app/raster/fonte.py`, `app/raster/zonal.py`): caminho virtual do
  GDAL com a credencial só-leitura do balde do inquilino; faixas de 64 linhas. Medido: **pico de 777 MB de memória
  residente num raster de 9,77 GB de pixels**, contra teto de 2 GB (`tests/medidas/L2-05-e-raster-basico.json`).
- **Igualdade com a referência, medida**: declividade e visibilidade **iguais byte a byte** ao `gdaldem` e ao
  `gdal_viewshed` diretos; NDVI de cena Sentinel-2 real **igual ao avaliador do TiTiler a menos de 1e-6**;
  5.570 zonas sobre o COG de uso do solo do acervo em **3,35 s** (modo clássico 1,81 s; `rasterstats` 6,03 s na
  mesma rodada, carga 11,9 registrada ao lado). No modo comparável a média por zona **reproduz o `rasterstats`**
  (erro máximo 0,0); com peso por fração de pixel o erro médio é 0,30 % e o máximo, 4,7 %, está gravado.
- **Resultado raster com procedência** (`app/ferramentas/saida_raster.py`): COG validado pelo `rio-cogeo` no
  armazenamento, item STAC na coleção `analises` do inquilino, item de catálogo com `procedencia.ferramenta` e
  relação `derivado_de` por entrada. Migração `20260908T1159_raster_procedencia.sql` abre `procedencia` no tipo.
- **Refutação atendida**: raster sem nodata declarado segue com aviso registrado no resultado; declividade em CRS
  geográfico é recusada com o motivo e só passa com `escala` declarada; polígono de recorte fora da extensão é erro
  nomeado, e não produto vazio; o disco de cada saída é conferido contra o arquivo real.
- **Fora desta fase, escrito**: hidrologia, distância de custo, estatística focal e funções encadeadas do Image
  Server (`docs/PARIDADE_FERRAMENTAS_RASTER.md`, ADR `20260908T1240-ferramentas-raster.md`).

## turno 4, setembro de 2026 (item L2-05-a-catalogo-ferramentas-gpserver: registro de ferramentas e GPServer)

O esquema do alimentador deixou de ser desenho de apresentação e virou objeto do produto. Um diagrama é um
grafo derivado de um recorte da topologia — a subrede atualizada, um traçado com pontos de partida, ou uma
seleção de feições —, passado pelas regras do modelo escolhido e posicionado por um layout. Fica gravado em
`plat.rede_diagrama` com `rede_diagrama_no`/`rede_diagrama_aresta`, e as coordenadas dos nós vivem no espaço
do diagrama, adimensional: o esquema não tem geografia, e guardar aquilo em graus faria parecer que tem.

Três regras de construção, com vocabulário fechado: reduzir junção de passagem, colapsar contêiner e remover
tipos. Seis layouts: árvore inteligente, radial, linha principal, geográfico, grade e força dirigida.
Exportação em JSON, SVG e PNG, os três do mesmo grafo gravado. A tela `/redes/diagrama` põe o esquema e o
mapa lado a lado e casa a seleção nos dois sentidos: cada nó é um botão de verdade nos dois quadros, com
foco de teclado e rótulo anunciado, e a seleção não depende só de cor.

Editar a rede marca o diagrama como `inconsistente` no mesmo instante em que marca a subrede suja — a área
suja é apagada quando a topologia é reconstruída, então o estado tem de ser gravado na hora. Trocar de
layout não conserta: só gerar de novo devolve `consistente`.

Medido em `tests/medidas/L4-04-d-diagrama-esquematico.json` (comando
`venv/bin/pytest tests/api/test_rede_diagrama_medida.py -m lento -q`), sobre o MAIOR alimentador da
cooperativa de teste — 1 de 20, 4.963 trechos de média tensão no arquivo: o diagrama de 4.963 nós e 4.963
ligações é gerado em **0,694 s** (teto do portão: 10 s), com carga 6,06 e 6,79 GB de RAM livre na máquina.
Os quatro layouts do portão terminam com **0 par de nós a menos de 1 unidade**, entre 1,19 s e 1,76 s cada.
A regra de redução leva o grafo de **4.963 para 1.037 nós** e mantém **1 componente conexo** antes e depois.

O que NÃO faz, declarado em `docs/PARIDADE.md`: das cerca de onze opções de layout da fonte há seis; das
muitas regras dela há três; não existe edição manual do desenho, nem diagrama que se refaça sozinho quando a
subrede é atualizada, nem geração assíncrona. `colapsar_conteiner` é tradução, não equivalência — o modelo
daqui não tem contêiner com conteúdo, e o que a regra colapsa é o dispositivo multi-terminal. O quadro do
mapa desenha só os nós: ligar dois nós por uma reta seria inventar traçado. Acima de 200 nós a força
dirigida cai na grade, com o aviso na resposta, porque ela compara todos contra todos a cada rodada.

## turno 7, setembro de 2026 (item L4-01-f-alcance-do-tracado-rede-real: alcance do traçado e diagnóstico do órfão)

O traçado a jusante alcançava 34 dos 50 transformadores de um alimentador do ativo de referência. A causa
medida: a camada de PONTO do arquivo guarda a coordenada com 6 casas decimais de grau e a de LINHA com 13,
então o mesmo poste aparece nas duas com até 0,073 m de diferença; os 16 transformadores fora estavam todos
entre 0,051 m e 0,071 m da ponta de trecho mais próxima, e os 50 têm uma ponta cuja coordenada, arredondada
a 6 casas, é IGUAL à deles. Subir a tolerância da rede não é conserto: com 1,0 m os laços da média tensão
sobem de 584 para 638, porque o que funde nessa folga são pontas de trechos vizinhos.

Conserto: `plat.rede_regra.tolerancia_m` (migração `20260908T0650`) declara a tolerância DAQUELE par de
tipos; o pacote `eletrica-br` (versão 1.1.0) declara 0,10 m nos 16 pares que envolvem cadastro de ponto, e o
par (trecho, trecho) fica com a tolerância da rede. `topologia._admitir_pares` aplica isso e mais uma trava:
a folga extra serve para reencontrar o MESMO ponto, nunca para alcançar um SEGUNDO — sem ela, um dispositivo
de dois terminais soldaria duas pontas distintas e fecharia ciclo (pego pelo teste da refutação). Novo
`GET /api/rede/{id}/topologia/diagnostico`: os órfãos que sobram saem por classe, com contagem, distância e
exemplo.

Medido (`tests/medidas/L4-01-f-alcance-do-tracado-rede-real.json`; 7 alimentadores, 9.925 trechos, 1.172
transformadores, cada alimentador na sua própria rede, carga 1 min 9,49 e 4,3 GB livres): transformadores
alcançados a jusante do controlador de 428/600 para 599/600; pior alcance de um alimentador de 66,67 % para
99,51 %; alimentadores acima de 95 % de 1 de 5 para 5 de 5; laços na média tensão iguais antes e depois
(0,0,0,0,0,1,1 por alimentador); nós órfãos de 1.038 para 495. As classes `fora_da_tolerancia_declarada`
(274 nós, todos entre 0,0503 m e 0,0726 m) e `derivacao_sem_no` somem; sobram o segundo terminal de cada
transformador (sem a camada de baixa tensão carregada) e dois transformadores longe da rede. Dois dos sete
alimentadores têm laço no próprio arquivo e o traçado recusa arbitrar sentido neles, antes e depois.

## turno 7, setembro de 2026 (item L4-01-g-tarefas-import-tardio: a API sobe sem GDAL)

`pyogrio` — a ligação vetorizada com o GDAL/OGR que o importador BDGD usa — estava importado no topo de
`app/rede_utilidades/bdgd.py` e de `app/rede_utilidades/tarefas.py`, e nesta máquina vinha do site do
usuário (`~/.local`), não da venv. Como `app/jobs/tipos.py` importa as tarefas, todo `import app.main`
dependia dele: com `PYTHONNOUSERSITE=1`, que é como a unidade systemd roda a aplicação,
`tests/unit/test_dependencias.py::test_app_main_importa_sem_site_do_usuario` reprovava com
`ModuleNotFoundError: No module named 'pyogrio'`.

Duas mudanças, nenhuma sozinha: o pacote passa a ser dependência declarada (`pyogrio==0.12.1` em
`requirements.txt`, com o motivo escrito ao lado — é o job `rede.importar_bdgd` que precisa dele) e o
import passa a ser tardio, dentro da função que abre o arquivo (`bdgd._pyogrio()`, usada também por
`tarefas._ler_camadas_do_contrato`). A API sobe sem GDAL; quem depende do GDAL é o worker, no instante em
que lê o `.gdb`. Instalação na venv aditiva, conferida com `pip install --dry-run` antes: nenhuma versão
de fastapi, starlette, pydantic, psycopg2, uvicorn ou rasterio mudou. ADR
`docs/adr/20260908T0628-pyogrio-dependencia-declarada-import-tardio.md`.
## turno 7, setembro de 2026 (item L4-02-f-resultados-e-exportacao: o resultado vira seleção, camada e arquivo)

O resultado de um traçado deixa de morrer na resposta da chamada. A resposta ganha `agregacoes` — contagem e
comprimento por tipo de ativo e por nível de tensão, sendo o nível o tier declarado no pacote de ativos, com
a linha própria de "sem nível declarado" para o que não tem. Três portas novas, todas sobre o mesmo motor de
traçado, que saiu da rota para `app/rede_utilidades/despacho.py`:

- `POST /api/rede/{id}/tracar/exportar?formato=csv|geojson|gpkg` devolve o arquivo. O CSV abre com as
  colunas id, tipo, grupo, terminal, comprimento_m e nivel; o GeoJSON traz a geometria de cada elemento e a
  procedência; o GeoPackage é escrito com o `sqlite3` da biblioteca padrão (ADR 20260908T0607) e lido de
  volta pelo `ogrinfo` no teste.
- `POST /api/rede/{id}/tracar/camada` guarda o resultado como item de catálogo do tipo novo
  `camada_tracado`, com procedência: rede, configuração, pontos de partida, versão da topologia e data.
- `GET /api/rede/{id}/tracados` e `POST .../tracados/{id}/repetir`: o histórico dos 20 últimos traçados da
  pessoa, guardando o PEDIDO e não o resultado — repetir roda sobre a rede de hoje e a resposta traz
  `contagem_anterior` ao lado da contagem nova.

Tela `/redes/tracado` com os botões selecionar, salvar como camada e exportar, o painel lateral das duas
agregações e o histórico com repetir. Provas: `tests/api/test_rede_tracado_resultado.py` (7 casos) e
`tests/e2e/test_rede_tracado_resultado.py` (caminho inteiro pela tela). Fora do escopo deste turno, e
declarado: a medida de tempo sob carga e a exportação de 20 mil elementos da refutação do item.

## turno 7, setembro de 2026 (item L4-02-e-configuracoes-de-tracado: o pedido de traçado vira documento salvo)

Configuração de traçado nomeada e compartilhável, o que a rede de utilidades da Esri chama *trace
configuration*: tipo do traçado, barreiras de condição (atributo, fase, categoria, grupo ou tipo), barreiras
de filtro, filtro de saída, funções sobre atributo (soma, contagem, mínimo, máximo, média) e tipo de
resultado (elementos, geometria agregada, conectividade). Tabela `plat.rede_config_tracado` com RLS por
inquilino, dono e `compartilhada`; CRUD em `/api/rede/{id}/config_tracado`. **Não existe rota nova de
traçado**: `POST /api/rede/{id}/tracar` ganhou o campo `config_id`, e do corpo continuam valendo só os pontos
de partida e as barreiras pontuais. A barreira de condição é traduzida para o que o motor já sabia recusar —
a feição de ponto que casa perde os terminais, a de linha perde a aresta (`arestas_excluidas`, o único
parâmetro novo em `tracado._montar_sql_arestas`); a barreira de FILTRO faz o traçado correr uma segunda vez
com as duas listas somadas e publica a interseção, com `passagens` na resposta dizendo qual valeu.

Seis configurações vêm prontas com o pacote elétrica-BR (clientes a jusante, kVA instalado a jusante,
isolamento por chave fusível, alimentador inteiro, protetores a montante, trechos sem fase C), semeadas na
importação do pacote — ficam em `config_tracado.CONFIGS_PADRAO` e não dentro do arquivo do pacote, cujo
esquema JSON é fechado. Atributo, categoria, grupo, tipo, operador, função e tipo de resultado são conferidos
contra o catálogo DA REDE na criação: o que a rede não tem vira 422 dizendo o nome, nunca uma configuração
salva que só falharia ao ser usada. Tela `/redes/configuracoes` com a lista e o formulário. Paridade e
lacunas declaradas (sem *function barrier*, sem *filter bitset*, sem `SUBTRACT`, contenção por coincidência
de posição) em `docs/rede/CONFIG_TRACADO.md`; decisão em
`docs/adr/20260908T0145-configuracoes-de-tracado.md`.
## turno 7, setembro de 2026 (item L4-27-curto-circuito-e-protecao: corrente de curto por barra e coordenação)

`POST /api/rede/{id}/subrede/{nome}/curto` calcula a corrente de curto-circuito de cada barra do
alimentador — trifásica e fase-terra — pela fonte de tensão equivalente no ponto de falta, sobre o MESMO
modelo em memória que os exportadores OpenDSS e pandapower usam. O resultado sai como tabela
(`GET .../curto`) e como camada de pontos (`GET .../curto/camada`, com a coordenada lida da topologia na
hora, nunca copiada), e para cada barra vem o dispositivo a montante com o veredito de coordenação contra
a faixa de interrupção CADASTRADA: `interrompe`, `abaixo_da_faixa`, `acima_da_capacidade` ou `sem_dado`.

As premissas são o produto tanto quanto o número, e voltam gravadas em toda execução e toda leitura:
potência de curto da fonte, relação X/R, fator de tensão `c`, razão de sequência zero de linha e de fonte,
base de potência. Fonte sem potência de curto declarada é RECUSADA (`422 impedancia_de_fonte_ausente`), e
potência zero também (`impedancia_de_fonte_nula`): impedância nula daria corrente infinita, e isso não é
resultado.

Medido em `tests/medidas/L4-27-curto-circuito-e-protecao.json`, num alimentador real da cooperativa de
teste (191 dos trechos de média tensão de 20 alimentadores do arquivo): 192 barras, todas com corrente
calculada, de 6.442 A a 10.982 A trifásicos com fonte de 250 MVA, em 0,205 s (carga 8,57 e 2,75 GB de RAM
livre no instante da medida). Nesse alimentador, 191 das 192 barras saíram `sem_dado` na coordenação —
a BDGD não tem campo de faixa de interrupção, e nenhuma faixa foi suposta. Em `tests/unit`, a corrente
bate com a conta fechada `Ik = c·Un/(√3·|Z|)` em três barras de um alimentador sintético.

Limitações declaradas no cabeçalho do módulo e em `docs/PARIDADE.md`: impedância de condutor e de
transformador são valores de REFERÊNCIA (o cadastro não os traz), a rede é tratada como radial (onde há
laço a corrente sai subestimada, com aviso e contagem) e como equilibrada. Triagem: sinal, não prova.
O ArcGIS Utility Network não faz cálculo elétrico — isto é "além da paridade", nunca paridade.

## turno 7, setembro de 2026 (item L4-05-c-pandapower-e-matpower: conector para rede equilibrada)

A subrede passou a sair em mais dois formatos, na MESMA rota do OpenDSS:
`GET /api/rede/{id}/subrede/{nome}/exportar?formato=pandapower` devolve o `rede.json` que
`pandapower.from_json` lê, e `?formato=matpower` devolve o `.m` do caseformat 2. Os três formatos vêm do
mesmo modelo em memória (`opendss.montar_da_subrede`): uma leitura do banco, uma regra de conversão, três
línguas. Medido em `tests/medidas/L4-05-c-pandapower-e-matpower.json`: `pp.runpp` converge sobre o arquivo
exportado, o mesmo alimentador escrito em MATPOWER e relido por `pandapower.converter.from_mpc` converge com
tensão a menos de 1 % do outro, e o número de `bus`/`line`/`trafo` bate com nós, trechos e transformadores
contados por consulta independente ao banco.

Na outra ponta, `POST /api/rede/{id}/matpower` importa um caso público (`case9` e `case30` entram na suíte,
9 e 30 barras, e o traçado de menor caminho corre sobre eles). O caseformat não tem coordenada nenhuma:
a barra entra no grafo de negócio com `geom` NULO, e nunca no ponto (0, 0). Pacote de ativos novo,
`transmissao-matpower`, com os dois grupos declarados `sem_geometria` — o catálogo diz a mesma coisa que a
tabela. Limitações escritas no `NAO_FAZ.md` que sai em toda exportação: os dois formatos são de rede
EQUILIBRADA (as fases por trecho não são representadas — para desequilíbrio, o formato é o `dss`), e a
impedância de linha é a de REFERÊNCIA (o padrão do motor OpenDSS, escrito em vez de implícito), porque o
pacote de ativos não tem catálogo de condutor. Em `docs/PARIDADE.md` isto está registrado como CONECTOR: o
ArcGIS Utility Network não exporta para esses formatos nem roda fluxo de potência, e a linha não deve ser
lida como capacidade equivalente. ADR `docs/adr/20260908T0220-pandapower-e-matpower.md`.
## turno 7, setembro de 2026 (item L4-04-c-unificar-subrede: uma tabela de subrede, com a origem ao lado)

Dois itens tinham criado, em ramos separados, duas tabelas para o mesmo conceito: `plat.rede_subrede` (a
subrede DERIVADA do controlador, item L4-04-a) e `plat.rede_subrede_bdgd` (a hierarquia que o ARQUIVO da
BDGD declara, item L4-01-c). Agora é **uma tabela só**, com a coluna `origem`: a derivada é a canônica
(tier, ciclo de vida limpa/suja, elementos, resumo) e a do arquivo entra como origem declarada
(`origem='bdgd'`, `estado='declarada'`, com nível, código e pai). Um `CHECK` por origem impede a mistura, e
o gatilho de nível estrito do item L4-01-c passou para a tabela unificada com os mesmos nomes de exceção.

A migração `20260908T0152` copia as linhas da tabela antiga **preservando o `id`** e repõe as chaves
estrangeiras de `plat.rede_no.subrede_id` e `plat.rede_aresta.subrede_id` na tabela unificada — nenhuma
referência é reescrita, e a tabela antiga deixa de existir.

Novo: `app/rede_utilidades/reconciliacao.py` grava a hierarquia declarada pelo arquivo e a liga à derivada
de mesmo nome dentro do tier daquele nível (`equivalente_id`). As duas rodam no fim da marcação de
controladores da importação, sem rota nova; a saída passa a trazer `declarado` e `reconciliacao`. O que não
casa fica com `equivalente_id` nulo e é contado — divergência é candidata a erro de cadastro, nunca erro
provado. Decisão em `docs/adr/20260908T0152-uma-tabela-de-subrede.md`.

## turno 7, setembro de 2026 (item L4-01-e-dicionario-unidades-bdgd: a unidade vem do arquivo, medida)

O dicionário do pacote `eletrica-br` declarava `COMP` em quilômetro e `ENE_SUM` em megawatt-hora; o extrato
de referência da casa traz os dois em metro e em quilowatt-hora. A unidade passou a ser **medida na
importação, campo a campo**, e gravada na auditoria (`plat.rede_importacao.unidades`): comprimento pela razão
contra o comprimento geodésico da própria geometria (medida que o item L4-01-c já fazia, agora com nome e
casa própria em `app/rede_utilidades/unidades.py`), energia pela ordem de grandeza contra a potência
instalada dos transformadores e contra o número de unidades consumidoras — duas âncoras que têm de concordar.

Quem soma e quem exporta lê o fator de lá, nunca do dicionário: o sumário por subrede (item L4-04-c) grava a
unidade e a origem dela na própria linha, e o exportador OpenDSS deixou de multiplicar `ENE_SUM` por mil de
cabeça. Sem importação registrada nada é convertido — fator 1 e `origem: nao_medida` escrito ao lado do
número. Medido em `tests/medidas/L4-01-e-dicionario-unidades-bdgd.json`: dois arquivos iguais em tudo menos
na unidade dão o mesmo comprimento em metros e a mesma energia anual em quilowatt-hora, e a carga do
circuito exportado muda mil vezes quando a auditoria diz megawatt-hora. Fronteira: o exportador EPANET ainda
não existe; a exportação de subrede em JSON, que é o que serve à água hoje, passou a carregar o mesmo bloco
`unidades`.

## turno 7, setembro de 2026 (item L4-05-a-exportar-opendss: a subrede vira circuito OpenDSS)

`GET /api/rede/{id}/subrede/{nome}/exportar?formato=dss` devolve a pasta `.dss` da subrede num zip:
`Master.dss`, `Linhas.dss`, `Transformadores.dss`, `Cargas.dss`, `Curvas.dss`, `resumo.json` e `NAO_FAZ.md`.
Barra do circuito = nó da topologia (com os dois terminais de uma chave fechada fundidos numa barra só),
`Line` = trecho com comprimento geodésico medido, `Transformer` = transformador com kVA e perdas de PER_FER e
PER_TOT, `Load` = unidade consumidora, e a geração distribuída como carga negativa de corrente constante.
`jusante=true` inclui as subredes de tier inferior: é o alimentador inteiro, e não só o tier pedido.

O dicionário de códigos de tensão da BDGD (domínio TTEN) entra completo: **110 códigos, de 0 a 109, sem
buraco**, contra os 13 do conversor que a casa já rodava — que por isso não resolvia o **código 63 (23,1 kV)**,
presente num alimentador da cooperativa de teste. Todo código de tensão do acervo da casa (TEN_NOM, TEN_PRI e
TEN_SEC) é resolvido pelo dicionário, medido no próprio acervo. A curva de carga tem **864 pontos**
(12 meses x 3 tipos de dia x 24 horas, PRODIST Módulo 7), com feriado contando como domingo e energia
conservada.

Medido (`tests/medidas/L4-05-a-exportar-opendss.json`, opendssdirect.py 0.9.4): o circuito exportado compila
sem erro, e o circuito compilado tem **7 barras e 5 linhas** contra **8 nós menos 1 fusão de chave fechada, e
5 trechos**, contados por consulta independente ao banco.

O conversor falha alto em vez de completar cadastro: transformador sem POT_NOM, tensão nominal ausente ou
código fora do domínio TTEN param a exportação com 422. O que ele não faz — impedância de condutor, reatância
de transformador, chave manobrável, curva típica por classe, regulador e capacitor — sai escrito em
`NAO_FAZ.md`, dentro da pasta exportada. ADR `20260907T2319-exportador-opendss.md`.

## turno 7, setembro de 2026 (item L4-04-b-atualizar-e-exportar-subrede: nome da subrede no elemento, propagação, SubnetLine e exportação)

`Update Subnetwork` passa a fazer o que a fonte descreve: traça a subrede a partir dos controladores, grava o
nome dela em cada elemento (`plat.rede_subrede_elemento` — tabela derivada, para não misturar o cálculo com o
dado do arquivo), propaga os atributos declarados no tier (`plat.rede_tier.propagadores`, valor lido no
dispositivo controlador), gera a linha agregada da subrede (`rede_subrede.linha` e `comprimento_m`, a
SubnetLine da Esri) e devolve a subrede limpa. A edição marca `suja` só a subrede que a área suja toca — antes
qualquer edição sujava a rede inteira — e o lote (`redes.subredes_atualizar`, job, com filtro por tier) só
atualiza as sujas. `GET /api/rede/{id}/subrede/{nome}/exportar` devolve o JSON da subrede validado contra
`plat.rede.subrede_exportada`; `GET .../subredes/conferencia` compara o nome calculado com um atributo do
arquivo e lista as diferenças como candidatas a erro de cadastro.

Medido na cooperativa de teste (três maiores alimentadores da BDGD, 13.646 trechos de média tensão;
`tests/medidas/L4-04-b-atualizar-e-exportar-subrede.json`): 3 subredes, 14.878 elementos em 9,3 s com carga
12,66; nome da subrede igual ao `CTMT` do arquivo em 13.646 de 13.646 (1,0); a exportação do maior alimentador
traz 5.392 elementos, 4.963 ligações e 337.047 m de linha agregada. Achado no caminho e corrigido: sem a
camada de chaves no arquivo, a marcação automática elegia o TRANSFORMADOR como controlador do tier de média
tensão, e o traçado partia do lado de lá da fronteira de subrede — 4 elementos alcançados de 13.646 trechos.
## junção, setembro de 2026 (ramo wt/bdgdjob × wt/il402bmonta: casos cruzados e eventos da família de rede)

União dos dois ramos da linha L4 que trabalharam a rede de utilidades ao mesmo tempo. `test_cruzado.py`
reprovava porque a árvore tinha as rotas de topologia, feições, traçado, rede simples e controlador sem
caso em `tests/api/cruzado_casos.py`; a união trouxe os casos e os eventos correspondentes. Três consertos
que a união exigiu: (a) o registro de união tinha deixado dois `return` em `preparar()` e um caso sem `),`
— o primeiro `return` matava o segundo e todo caso de `/api/rede/{rede_id}` caía em KeyError; (b) três
casos de `/api/conexoes/{id}/colecoes*` apontavam rotas que não existem nesta árvore e saíram; (c) a rota
`POST /api/rede/{rede_id}/importar-bdgd` ganhou o tipo de evento `redes/importar_bdgd` no catálogo
(migração `20260907T2210`) — sem a linha, a rota gravava o job e falhava ao registrar o evento.

Colisão de nome resolvida (ADR `20260907T2200`): os dois ramos criaram `plat.rede_subrede` com conteúdo
diferente. A tabela do controlador de subrede fica com o nome (é o do portão do item e o termo de paridade
com a Esri); a hierarquia lida do arquivo BDGD passa a `plat.rede_subrede_bdgd`. As duas descrevem o mesmo
conceito por caminhos diferentes e hoje não conversam — unificá-las é decisão de desenho, não desta junção.

A asserção de contagem de rotas de escrita sob `/api/rede` foi de 6 para 16, com `POST .../tracar`
declarado como consulta com verbo de escrita (pede `rls:visibilidade`, não `rede.editar`).

Rede de referência sem nome de parceiro: o caminho do pacote `.gdb.zip` e o schema onde a BDGD real está
carregada saíram do código para `PLAT_REDE_REFERENCIA_GDB`, `PLAT_REDE_REFERENCIA_CTMT` e
`PLAT_REDE_REFERENCIA_ESQUEMA` (`tests/dados/carga_bdgd.py::esquema()`/`exigir_esquema()`); sem as
variáveis os testes de medida pulam com a razão escrita, em vez de estourar. Os textos passam a dizer
"distribuidora de referência" e "cooperativa de teste", e o nome do arquivo saiu da medida gravada — só o
sha256 identifica o pacote.
## turno 8, setembro de 2026 (item L2-04-i-wms-wmts-sld: WMS 1.3.0 e WMTS 1.0.0 por token)

A camada hospedada passa a ser servida como IMAGEM para qualquer cliente OGC, além de feição: `/wms/{item}`
com `GetCapabilities`, `GetMap` (png/png8/jpeg, transparência, estilos, `SLD_BODY`, 9 CRS e a ordem de eixo do
1.3.0), `GetFeatureInfo` (json/html/texto/GML) e `GetLegendGraphic`; `/wmts/{item}` em KVP e RESTful na grade
`GoogleMapsCompatible`, a mesma dos tiles do visualizador. A imagem sai de um rasterizador próprio (Pillow)
sobre as feições da caixa, com o estilo do L2-02-a — a cor do WMS é a mesma do mapa da casa. O job
`wmts.publicar` pré-renderiza a camada num PMTiles raster no bucket do inquilino, e o `GetTile` passa a servir
por leitura de faixa. Os dois `GetCapabilities` validam contra a XSD oficial do OGC, em cache local
(`docs/xsd/baixar_ogc_servicos.py`, rodado pelo `install.sh`). Medido em `tests/medidas/L2-04-i-wms-wmts-sld.json`:
GetMap 1024x768 quente p95 882 ms e frio 1.118 ms sobre 100 mil pontos; pré-renderização z0-z14 de 100 mil
feições em 40,5 s (836 tiles, 3,0 MB); GetMap em 3857 com 0 % de cobertura diferente do raster de referência.
Rajada de imagens grandes é enfileirada por orçamento de megapixels, com 503 `ServerBusy` no excedente.
Paridade: `docs/PARIDADE.md`; ADR `20260908T1900-wms-wmts`.

## turno 4, setembro de 2026 (item L2-04-d-featureserver-edicao-anexos: escrita pelo protocolo Esri sobre a porta única)

`applyEdits` (na camada e no serviço), `addFeatures`/`updateFeatures`/`deleteFeatures`, `calculate`, os seis
caminhos de anexo do protocolo Esri e `uploads/upload`, montados em
`/rest/services/{item}/FeatureServer/0/*` (`app/consulta/rotas_edicao_esri.py` + `app/consulta/esri_edicao.py`).
Nenhuma dessas rotas escreve em tabela de camada: todas traduzem o pedido Esri e chamam
`app.edicao.servico.aplicar_edicoes`, a porta única de escrita do item L2-03-a — o que vale para a API da
casa (tipo, domínio, CRS, propriedade, versão otimista) passou a valer para o cliente Esri sem cópia de regra.

Três decisões, no ADR `docs/adr/20260907T2016-featureserver-escrita-esri.md`: (1) erro sai com o código HTTP
REAL e o corpo no formato Esri, em vez do HTTP 200 com erro no corpo que a Esri usa; (2) `rollbackOnFailure`
(padrão verdadeiro) é um `SAVEPOINT` de lote, e a resposta continua trazendo o resultado feição a feição, com
`rolledBack`; (3) `calcExpression.sqlExpression` do `calculate` é traduzido para a linguagem de expressão da
casa (L2-03-f) e avaliado em Python — SQL do cliente nunca chega ao banco.

Migração `20260907T1927_featureserver_edicao.sql`: `origem` em `plat.feicao_historico` (preenchida pelo
gatilho a partir do parâmetro de sessão `plat.origem`, padrão `api`), `numero bigserial` em
`plat.feicao_anexo` (o protocolo Esri identifica anexo por inteiro; o uuid continua sendo a chave) e
`plat.esri_upload` (o bilhete do arquivo enviado antes de existir feição-pai).

Medidas em `tests/medidas/L2-04-d-featureserver-edicao-anexos.json`, com o comando exato: 26 testes de API
dedicados, todos passando. Duas cláusulas do portão NÃO foram feitas e estão nomeadas lá: edição por QGIS
(não instalado, sem ambiente gráfico) e a prova com o cliente Python `arcgis` (pacote não instalado). Ao
regerar `docs/openapi.json` apareceu que a junção dos ramos de origem havia apagado as rotas de edição, de
mapa e do FeatureServer do arquivo comitado; foram restauradas e cada um dos 29 (método, caminho) novos ganhou
caso na varredura cruzada A→B, que segue em 100 % de cobertura.

## turno 4, setembro de 2026 (item L1-02-tiles-token: ladrilho raster por inquilino, token no caminho)

Serviço de ladrilho raster sobre o COG que a ingestão (L1-01) deixou no Garage, com o token de serviço
no CAMINHO da URL (decisão C6 do conceito L1; ADR 20260907T0300).

- `/svc/<token>/raster/<item>/{z}/{x}/{y}[.png|.jpg|.webp]` (XYZ), `/tilejson.json`, `/info.json`,
  `/wmts` (KVP GetCapabilities e GetTile) e `/wmts/1.0.0/WMTSCapabilities.xml` (REST); mosaico da
  coleção em `/svc/<token>/mosaico/<colecao>/{z}/{x}/{y}`.
- Motor rio-tiler 9.4.3 lendo o COG por `/vsis3` com a chave só-leitura do balde do inquilino. Nenhuma
  rota aceita endereço de arquivo: o caminho nasce do catálogo do inquilino do token (sem `?url=`).
- Expressão sobre bandas por parâmetro (NDVI = `(b4-b3)/(b4+b3)`), com gramática própria antes do
  numexpr; faixa, colormap (211 do rio-tiler), seleção de bandas e escolha do asset.
- GetCapabilities do WMTS **valida contra o esquema oficial do OGC** (XSD vendorizado em
  `tests/dados/ogc_xsd`, validação sem rede).
- Cache no nginx com chave SEM o token e `auth_request` que confere token E dono do item a cada
  requisição — sem essa conferência, um token de outro inquilino recebia o ladrilho do cache (achado
  desta bancada, hoje é teste).
- Registro de uso agregado por token em `plat.tile_leitura` (migração `20260907T0249_tile_leitura.sql`)
  e leitura em `GET /api/tiles/leituras`. O token nunca é gravado, só o `token_id`.
- Bancada: `scripts/bench_tiles.py` (carga, `proxy_cache_lock`, revogação) e
  `scripts/prova_cliente_ogc.sh` (driver WMTS e WMS/TMS do GDAL lendo pixel do serviço).
- Medido: **68.738 ladrilhos/s** quente com o cache do nginx (`ab -c 32`, 0 erro; o mesmo nginx serve
  arquivo estático a 68.484/s — o serviço está no teto da máquina); frio 96 ladrilhos/s numa conexão,
  mediana 9,8 ms; 20 pedidos simultâneos ao mesmo ladrilho frio = **1 leitura + 19 acertos**; revogar
  o token passa a 403 em **2,86-2,90 s**. Números e comandos em `tests/medidas/L1-02-tiles-token.json`.
## turno 8, setembro de 2026 (item L2-12-b-layouts-elementos-exportacao: layout de impressão, exportação e Export Web Map Task)

Tipo de item `layout` (papel A4-A0/carta, orientação, margens, elementos em mm: quadro de mapa por extensão ou
escala 1:N, legenda, barra de escala, seta de norte verdadeiro/grade, grade UTM/geográfica, título e texto com
expressões, imagem, tabela, data, atribuição obrigatória), modelos padrão em código e modelos do inquilino.
Compositor `app/layout/compor.py`: primitivas em mm → PDF vetorial (WeasyPrint, texto selecionável) / PNG / JPG /
SVG, quadro raster no DPI pedido com teto de pixels declarado (A0 a 300 DPI sai a DPI efetivo menor, no relatório),
legenda paginada. Geometria declarada (`geometria.py`): escala ↔ zoom do MapLibre, UTM por pyproj. Quadro desenhado
pelo motor de render do L2-12-a (copiado de `wt/il212amotor` 900c0b16) numa página headless com token interno
assinado que cunha tokens de tile por camada — desenha camadas do catálogo via Martin. Job `layout.exportar`
(arquivo como objeto do inquilino, classe `layout_exportacao`), rotas `/api/layouts/{modelos,validar,previa,exportar}`,
Esri `Export Web Map Task` e `Get Layout Templates Info Task`. Painel Layout no visualizador (atalho `y`). Testes:
unidade (geometria, validação nomeada, PDF lido por pdftotext, legenda de 300 classes, teto A0), API contra uvicorn
real (régua sobre o PDF: dois pontos a 1.000 m medidos no pdftoppm, ≤ 1 %; cor da legenda; grade lida; Esri),
e2e do diálogo. ADR `20260908T1230`; PARIDADE com a tabela Print service × plat.

## turno 8, setembro de 2026 (itens UX-11-arquivos-sem-controle, UX-17-login-sem-controle e UX-18-plataforma-sem-tela: últimas lacunas da trilha de interface)

Trilha de interface. **UX-11**: seção "Arquivos e objetos" em `/admin/organizacao` — uso × cota (`GET
/api/arquivos`), varredura de órfãos, envio de arquivo cru com token de serviço `admin:inquilino` cunhado e revogado
em volta do `POST /api/arquivos` (cookie + Authorization dão 400; por isso `credentials: 'omit'`), baixar e apagar
(`DELETE /api/arquivos/{sha256}`) com confirmação; classe inválida recusada no navegador; 413/415 nomeados.
**UX-17**: `GET /api/login/provedores` declara o LDAP habilitado do inquilino; `/entrar` ganha o botão que alterna
para `POST /api/login/ldap` com os mesmos campos; 503 do diretório, 403 desabilitado/sem grupo e 409 login local
viram texto próprio e o login local segue disponível. **UX-18**: tela `/plataforma` (barra lateral só para
superadmin): lista de inquilinos com filtro e estados, criar (senha temporária mostrada uma vez com copiar; 409 e
422 no campo; slug e login validados antes), suspender/reativar/apagar com confirmação; sessão comum vê "sem
permissão". `button.perigo:hover` invertido (contraste). i18n +74 chaves (pt-BR/en/es). e2e
`tests/e2e/test_ux11_17_18_arquivos_ldap_plataforma.py` (4 testes; o do superadmin cria a sessão no banco e liga
o 2FA obrigatório pela API). Cobertura regenerada: 240 rotas, 11 lacunas de escrita (era 18) — nenhuma da trilha
de interface. ADR `docs/adr/20260908T1700-*`.

## turno 8, setembro de 2026 (item UX-23-mapa-sem-controle: painel Seleção, anotações com controle, importar pacote)

Trilha de interface. Painel **Seleção** (atalho `s`) no visualizador: por atributo (condições campo · operador ·
valor com E/OU → CQL2-JSON → `POST /api/mapa/camadas/{id}/filtrar`, com valores únicos sugeridos e o SQL
equivalente mostrado), por geometria do painel Desenho (`.../selecionar`, intersecta ou a até X m, combinando com
a seleção atual) e entre camadas (`POST /api/mapa/selecao-espacial`). O resultado vai para a tabela de atributos
(realce), vira filtro da camada no mapa (e sai) e é guardado como item `selecao`. Validação local nomeada por
condição; erro do servidor nomeado com o campo e a referência. **Anotações** reescritas: estados explícitos,
editar texto (só o autor; PATCH via `remendar`, que corrige o PUT que nunca funcionou), resolver/reabrir, apagar
com confirmação; avisos no painel, sem `alert`. **Importar pacote** no painel Exportar (`POST
/api/mapa/pacotes/importar`, zip cru): recusas locais, 413/422 nomeados, resumo com ligação para o mapa
importado. `Desenho.aoMudar` aceita vários ouvintes. e2e `tests/e2e/test_ux23_selecao_anotacoes_pacote.py`
(3 testes, capturas 390/1280, axe, console limpo); `test_mapa_chrome.py` conhece o painel. Cobertura regenerada:
240 rotas, 18 lacunas de escrita (era 24); o grupo `mapa` fica sem lacuna. ADR `docs/adr/20260908T1500-*`.

## turno 8, setembro de 2026 (item UX-09-telas-ferramentas-e-tarefas: catálogo de ferramentas com formulário gerado do esquema)

Trilha de interface. Nova tela `/ferramentas` (entrada na barra lateral com `jobs.executar`): catálogo dos tipos de
tarefa de `GET /api/jobs/tipos` em cartões por grupo, com custo declarado (memória, tempo, pesada, executor, perfil
mínimo) e número de parâmetros; busca; as de diagnóstico só com o filtro ligado. O formulário de cada ferramenta é
GERADO do JSON Schema dos parâmetros (número com limites, enum, caixa, lista, JSON, uuid, data-hora; obrigatório e
padrão do esquema; rótulo = nome do parâmetro, descrição e limites na ajuda). Validação no navegador com o motivo
no campo antes de qualquer chamada; 422 do serviço (`[{campo, mensagem}]`) volta ao campo. Executar cria a tarefa e
mostra a execução ao vivo no mesmo painel (canal SSE/polling da tela Tarefas): barra, log, cancelar enquanto roda,
ligação para `/tarefas/<id>` e para o item do resultado. Estados: catálogo vazio/erro com tentar de novo, filtro
sem resultado com limpar, ferramenta inexistente pela URL, perfil insuficiente, sem permissão. Módulo com funções
içadas porque inicia no topo (`await iniciar()` antes das `const`). i18n `ferramentas.*` + `nav.ferramentas` (três
idiomas). ADR `docs/adr/20260908T1400-*`. e2e `tests/e2e/test_ux09_ferramentas.py` (3 testes; `prova.progresso`
de 4 passos roda até "concluído"; cancelamento; capturas 390/1280; axe; console limpo). Parte NÃO coberta: ferramentas
GP no vocabulário Esri (L2-05-a) não existem em ramo nenhum.

## turno 8, setembro de 2026 (item UX-08-telas-rede-de-utilidades-e-motor: painéis Rotas e Motor no visualizador; rede de utilidades fica nos ramos L4)

Trilha de interface. O visualizador ganha dois painéis no mesmo chrome de UX-04, com atalhos `r` e `o`: **Rotas**
(`POST /api/rota`, `/api/isocrona`, `/api/matriz` sobre o OSRM do recorte — origem e destino por clique no mapa ou
digitados, isócrona em minutos, matriz origens × destinos em tabela; linha, polígono e marcadores no mapa; a
proveniência da resposta é mostrada; 503 do serviço e 422 `isocrona_vazia`/`matriz_grande_demais` viram texto nomeado
no painel) e **Motor** (multiescala L3-19: área de estudo criada da vista atual ou de um retângulo digitado em graus,
fatores com amostras em grade gerada sobre a área, pesos por fator escolhidos pelo usuário, macro com aprovação por
limiar ou top %, refino micro só nas aprovadas, relatório por fator com a explicação de escala grosseira, células
pintadas no mapa e popup com nota, cobertura e aprovação; rodar sem área ou sem fator mostra o motivo, nunca painel
vazio). API: `GET /api/multiescala/execucoes/{id}/celulas` (GeoJSON das células com nota, limite
`ESCALA_CELULAS_GEOJSON_MAX`, `truncado` declarado) e `area` do conjunto no JSON. Fator novo entra desligado no
estudo (a composição é escolha do usuário; o recém-criado no painel entra ligado). Marcadores do MapLibre recebem
papel `img` e nome (axe `aria-prohibited-attr`). Ids das seções do motor com prefixo `motor-secao-` (colidiam com os
controles). Cada chamada da rede e do motor com o caminho na própria linha, que é como o gerador de cobertura liga
rota → tela. e2e `tests/e2e/test_ux08_motor_rotas.py` (2 testes, capturas 390/1280, axe, sem chave crua);
`test_mapa_chrome.py` conhece os dois painéis. Cobertura regenerada: 240 rotas, 24 lacunas de escrita (era 34).
Parte NÃO coberta: traçado de rede de utilidades (montante/jusante, controladores) — não está no tronco; vive em
`wt/il402bmonta`, `il402cisola`, `il402dlacos`, `il404acontr`, `il405depane`, `il418redesi`, `il401datrib`.

## turno 8, setembro de 2026 (item UX-07-telas-do-construtor-e-aplicativo: escolha do item, publicação, motor de widgets juntado, plat-w-*)

Trilha de interface. Juntados `wt/cx506` (motor de widgets, L5-06) e `wt/cx501d` (widgets de página e menu,
L5-01-d): os arquivos do visualizador que `cx506` carregava em cópia antiga ficaram com a versão de UX-04 e só os
três trechos próprios do motor entraram no mapa (`<plat-w-mapa>`, `plat-mapa-enquadrar`, `mapa.extensao_alterada`).
Os elementos dos widgets passam a `plat-w-<nome>`: `plat-tabela`, `plat-tema` e `plat-idioma` colidiam com os
componentes do sistema de design e o `definir()` do motor silenciava a colisão. `/construtor` sem `?item=` lista
aplicativos e painéis (busca, estados) e cria um novo; com item, a barra tem Salvar, Publicar (com confirmação;
`POST /api/itens/{id}/versoes/{n}/publicar`), Executar e "escolher outro", com o estado de publicação e o conflito
409 nomeado; estados de item inexistente e tipo errado; chrome do editor pelo dicionário (`construtor.*`, três
idiomas; os rótulos da paleta ficam para L5-12). Paleta e painel lateral presos ao topo com rolagem própria — o
arrasto pegava o item errado quando a página rolava. Árvore da estrutura conforme ARIA (linha = treeitem focável;
Enter/Espaço selecionam). `/executar` e `/aplicativo` com estados explícitos; `/aplicativo?item=` roda um painel
(ou a página inicial de um app) pelo motor, traduzindo o documento do editor para a grade de widgets. `widgets.css`
só com tokens. e2e `tests/e2e/test_ux07_construtor.py` (novo app, três widgets por arrasto, publica, abre em
/executar e em /aplicativo; configuração inválida nomeada no painel e no aplicativo; estados); suítes L5-08, L5-01-a,
L5-06, L5-01-d e as do mapa passam contra esta árvore (o Martin da trilha precisa subir DEPOIS da bancada, como
em UX-04). Cobertura regenerada: 239 rotas, 34 lacunas de escrita.

## turno 8, setembro de 2026 (item UX-06-tela-administracao-inquilino: porta única /admin, acervo com licença, diretório LDAP, evento registrado)

Trilha de interface. `/admin` é a porta única da administração: um cartão por assunto (usuários ativos, convites
pendentes, grupos, papéis, tokens válidos, armazenamento uso/cota, usuários/cota, provedor LDAP, acervo com licença,
acessos em 24 h) com o número lido da rota que já existe e o caminho da tela que gere o assunto; entrada na barra
lateral por lista "ou" de privilégios; sem privilégio administrativo o hub mostra "sem permissão" com o caminho de
volta (refutação: 403 amigável, nunca tela quebrada). `/admin/acervo` (fecha UX-10): lista com busca e domínio, ficha
de procedência (endereço, licença, método, frescor, sha256, comando de reexecução, endereços testados) e "adicionar ao
catálogo", com o `409 confirmacao_pii_exigida` virando diálogo de confirmação antes da segunda chamada. Seção LDAP em
`/admin/organizacao` (`GET/PUT /api/org/ldap`, `POST /api/org/ldap/importar`, que estavam sem tela): senha de bind
só sobe quando preenchida, mapa grupo → perfil conferido no cliente, 409 do importar nomeado. Ficha do membro
(`GET /api/usuarios/{id}`, sem tela até aqui). Toda escrita administrativa mostra o evento registrado
(`comum.js::eventoRegistrado`, só com `org.log_ver`, nunca finge) com link para `/admin/log?aba=eventos&tipo=`; o
log ganhou link profundo. Estados explícitos (`estadoDeLista`) nas seis telas. Achados consertados: o gerador de
cobertura dava o método do PRIMEIRO nome da linha a todos os literais (`PUT /api/papeis/{id}` aparecia como lacuna
sem ser) e procurava o literal sem delimitador; `/admin/organizacao` registrava ouvintes em elementos que a página
"sem permissão" removeu (pageerror para quem não tem `org.configurar`); função declarada depois do `await` de
módulo em `/admin` (TDZ). e2e `tests/e2e/test_ux06_admin.py` (hub, visualizador conforme os privilégios reais do
perfil + sessão sem privilégio interceptada, acervo com o caminho LGPD, LDAP, PUT de papel, ficha do membro,
estados, link profundo); suítes anteriores das seis telas, convite, login, i18n, layout e guia passam. Cobertura
regenerada: 238 rotas, 34 lacunas de escrita (eram 38).

## turno 8, setembro de 2026 (item UX-05-telas-conexoes-uploads-tarefas-compartilhado: conexões com controle, fila de envio, tarefas traduzidas, página pública sem chrome)

Trilha de interface. `/conexoes` ganhou criar, editar e apagar (confirmação) por `<plat-formulario>` — nome, tipo
(travado depois de criada), endereço, modo, config JSON, credencial que nunca volta do servidor —, com os 422 do
servidor (`url_insegura`, `config_grande_demais`, pydantic) e o 409 de nome no campo certo; busca, ordenação por
coluna com `aria-sort` e estados vazio/carregando/erro/negado: fecha as quatro rotas de UX-13. `/uploads` virou fila
(vários arquivos, uma barra por arquivo, cancelar por arquivo ou tudo, tentar de novo, remover), com bytes, velocidade
e tempo restante pintados uma vez por quadro; o progresso por byte via `XMLHttpRequest` foi tentado e refutado pela
própria trilha (XHR na mesma origem leva o cookie e cai em `400 autenticacao_ambigua`), então as partes seguem por
`fetch` com `AbortController` e granularidade de 16 MiB — decisão registrada na ADR e no handoff para o dono da
autenticação. `/tarefas` sem texto cravado (lista, detalhe, agendas e `jobs/formato.js` pelo dicionário; pt-BR
inalterado, en/es com paridade) e com `<plat-estado>` na lista (vazio com "limpar filtros", erro, negado), no detalhe
(id inexistente) e nas agendas. `/c/<token>` deixou de montar a barra lateral do produto: cabeçalho próprio (marca,
idioma, tema), estados nomeados para 404/410/429/erro e a ficha do item incluído por
`GET /api/compartilhado/{token}/itens/{id}` (rota que estava sem tela). Achados consertados de passagem: o seletor
`.progresso span` da folha comum pintava o número da barra de tarefas com o fundo de andamento (contraste); a barra
de progresso não tinha nome acessível; o tema claro tinha sucesso 4,27:1 e acento 4,45:1 sobre a superfície de hover
(tokens escurecidos para 4,69 e 5,05); o título do item na página pública saía em caixa alta; o gerador de cobertura
só atribuía o texto da tela ao primeiro caminho do mesmo HTML (`/tarefas/{job_id}` aparecia sem estado nenhum).
Medida (`tests/medidas/UX-05.json`): arquivo sintético de 256 MiB (16 partes) com PUT/concluir interceptados no
navegador, maior tarefa longa do fio principal 199 ms, maior intervalo entre quadros 23 ms, 18 pinturas do rótulo
(carga 6,42). e2e `tests/e2e/test_ux05_telas.py` (4 telas, capturas 390/1280, axe, i18n, 0 erro de console);
suítes anteriores das quatro telas passam contra esta árvore. Cobertura regenerada: 238 rotas, 38 lacunas de escrita
(eram 41).
## codex cx1, setembro de 2026 (item UX-18-plataforma-sem-tela: console do superadmin em /admin/inquilinos)

Fecha as lacunas "POST /api/plataforma/inquilinos", "POST .../suspender", "POST .../reativar" e "DELETE .../{id} sem
tela" do mapa de cobertura (UX-00): tela nova `/admin/inquilinos` (entrada no menu só para o superadmin — `TELAS`
ganha `superadmin: true` e `telasVisiveis` a honra) com a lista dos inquilinos (estado, usuários, criação, último
acesso), "novo inquilino" (slug, nome, login e nome do primeiro administrador; a senha temporária aparece UMA vez, com
copiar e o link de entrada), suspender/reativar com confirmação e apagar com dupla confirmação. Estados por
`<plat-estado>`: carregando, vazio, erro com "tentar de novo" + referência, negado (a API responde 404 a quem não é
superadmin — vira o estado negado nomeado) e o estado das ações; erro nomeado no campo (422 validacao e 409
slug_existente/slug_reservado no slug; 409 plataforma_nao_suspende e 404 inquilino_inexistente no controle).
`docs/COBERTURA_UI.md` e `docs/cobertura_ui_lacunas.json` regenerados (26 → 22). e2e `tests/e2e/test_inquilinos_ux18.py`
com login do superadmin por TOTP na tela, negado real do admin de demo, criação/suspensão/reativação/apagamento
reais (o admin novo entra com a senha temporária e perde a sessão na suspensão), erros forjados nomeados, axe 0
sérias, capturas 390/1280; pt-BR/en/es.

## codex cx1, setembro de 2026 (item UX-16-ingestao-sem-tela: tela /importacoes para o fluxo arquivo → camada)

Fecha as lacunas "POST /api/importacoes", "PUT /api/importacoes/{id}/confirmar" e "DELETE /api/importacoes/{id} sem
tela" do mapa de cobertura (UX-00): tela nova `/importacoes` (menu com `conteudo.publicar_camada`) — lista das
importações (estado, formato, feições, erro), "nova importação" (item de arquivo já enviado + formato, com sugestão pela
extensão; dispara a inspeção e a tela acompanha o job até a proposta), "conferir e carregar" (proposta editada: título,
CRS quando o arquivo não declara, codificação, tipo de geometria, ação para geometrias inválidas, campos com tipo e
importar/não importar; dispara a carga e a tela acompanha até `concluída`, com "ver camada") e "apagar" (com
confirmação). Estados por `<plat-estado>` (lista: carregando, vazio com "nova importação", erro com "tentar de novo",
negado; fluxo: inspecionando/carregando, falhou nomeado; formulários) e erro da API NOMEADO no campo
(conteudo_nao_corresponde/formato_nao_suportado → formato; srid_inexistente → CRS; perguntas_pendentes → lista;
estado_invalido 409 e 403 no controle). Achado de API: `GET /api/importacoes/formatos` respondia 404
importacao_inexistente porque estava declarada depois de `/api/importacoes/{id}` — reordenada, com teste. A carga
morria na trilha com `tuple concurrently updated` (GRANT no d_demo partilhado): a mesma migração 20260908T0815 do
wt/cx203f entra aqui. `docs/COBERTURA_UI.md` e `docs/cobertura_ui_lacunas.json` regenerados (29 → 26). e2e
`tests/e2e/test_importacoes_ux16.py` com o fluxo REAL (upload pela API, inspeção e carga pelo worker da trilha,
apagar) e os erros forjados nomeados; axe 0 sérias; capturas 390/1280; pt-BR/en/es.

## codex cx1, setembro de 2026 (item UX-15-geocodificador-esri-sem-controle: GeocodeServer compatível com Esri com controle na tela e URL exposta)

Fecha as lacunas "POST /rest/services/Geocodificador/GeocodeServer[/findAddressCandidates|/geocodeAddresses|/reverseGeocode]
sem controle" do mapa de cobertura (UX-00). A tela `/geocodificar` (UX-14) ganha a seção "Serviço compatível com Esri":
a URL do GeocodeServer para copiar (com a dica do `?token=` e do escopo `geocodificar:usar`), "ver descritor" (POST no
descritor, público), "findAddressCandidates com o endereço acima", "reverseGeocode com a coordenada abaixo" e
"geocodeAddresses em lote" (um endereço por linha, até 500, OBJECTID + SingleLine como o cliente Esri manda) — a
resposta aparece no formato Esri (tabela Score/Match_addr/Addr_type ou ResultID/Status, mais o JSON) e as respostas de
negócio do protocolo (400 fora_da_distancia, 404 nao_encontrado, 422 lote_vazio/location_ausente) viram estado vazio
NOMEADO; 403 no formato Esri (`{error:{code,message}}`) vira negado com o código; 5xx vira erro com "tentar de novo" e
referência. A tela `/admin/tokens` expõe as URLs do GeocodeServer e do OGC API Records com o escopo exigido e botão
copiar (o mesmo motivo que o gerador de cobertura registra para as rotas de cliente externo). `docs/COBERTURA_UI.md` e
`docs/cobertura_ui_lacunas.json` regenerados (33 → 29). e2e `tests/e2e/test_geocodificar_esri_ux15.py` (chamadas reais
ao descritor, candidatos, reverso e lote; forjados 200/403/500; axe 0 sérias; capturas 390/1280); pt-BR/en/es.

## codex cx1, setembro de 2026 (item UX-14-geocodificador-sem-tela: tela /geocodificar para POST /api/geocodificar e /api/reverso)

Fecha as lacunas "POST /api/geocodificar" e "POST /api/reverso sem controle" do mapa de cobertura (UX-00): tela nova
`/geocodificar` (menu, sem privilégio além da sessão — as rotas exigem só o escopo `geocodificar:usar`) com dois
`<plat-formulario>`: endereço em linha única e/ou campos estruturados (até 50 candidatos, com pontuação, tipo de
acerto traduzido, coordenada e "ver no mapa") e coordenada para endereço (vizinho mais próximo, distância, marca
"fora do raio"). Estados do sistema de design por `<plat-estado>`: carregando, vazio NOMEADO com a resposta real do
motor (422 sem_correspondencia / sem_dado_instalado: o código e a mensagem, nunca o número cru), erro com "tentar de
novo" e referência, negado (403); 422 endereco_vazio e a lista do pydantic caem no campo. `docs/COBERTURA_UI.md` e
`docs/cobertura_ui_lacunas.json` regenerados (35 → 33). e2e `tests/e2e/test_geocodificar_ux14.py` (10 estados, dois
deles reais contra a base sem CNEFE; axe 0 sérias; capturas 390/1280); textos em pt-BR/en/es.

## codex cx1, setembro de 2026 (item UX-13-conexoes-sem-controle: a escrita de conexões com erro nomeado no controle da tela /conexoes)

Fecha a lacuna "POST/PATCH/DELETE /api/conexoes sem controle" do mapa de cobertura (UX-00). A tela `/conexoes` da
cadeia UX-05 já chamava as 8 rotas de `/api/conexoes*` (formulário `<plat-formulario>` de criar/editar, ação "apagar"
com confirmação, testar, histórico, publicar) com os quatro estados de `<plat-estado>`; este item prova a refutação
rota a rota e fecha o que faltava: 404 em PATCH/DELETE (conexão apagada por outra pessoa) avisa e recarrega a lista
em vez de deixar o formulário preso (`conexoes.ja_removida` em pt-BR/en/es). `tests/e2e/test_conexoes_ux13.py`:
lista vazia/erro/negada forjadas; POST com 403 (privilégio nomeado na mensagem do formulário), 409 (campo nome), 422
da validação (campo apontado por `loc`), 422 config e 413 cota forjados e criação real; PATCH com 403 e 422
url_insegura forjados e gravação real conferida por GET; DELETE com 403, 500 e 404 forjados nomeados no aviso da lista
(role=alert, referência) e remoção real; axe 0 sérias, capturas 390/1280, 0 erro de console. `docs/COBERTURA_UI.md`
regenerado (35 lacunas na junção, nenhuma de conexões).

## codex cx1, setembro de 2026 (item UX-12-categorias-sem-controle: as rotas de escrita de categorias com controle na tela /admin/categorias)

Fecha as lacunas "PUT /api/categorias" e "POST /api/categorias/importar sem controle" do mapa de cobertura (UX-00):
tela nova `/admin/categorias` (menu, privilégio `conteudo.categorias`) sobre a cadeia UX-00..05 — editor da
árvore de 3 níveis (nome, nova raiz/filha, subir/descer, remover bloqueado quando há itens) que grava a árvore
inteira com ids preservados, e "Importar modelo" (ISO 19115 / INSPIRE, idempotente). Estados do sistema de design:
`<plat-estado>` da lista (carregando, vazio com "importar modelo", erro com "tentar de novo", negado) e do
salvar/importar, onde o erro da API aparece nomeado — 409 categoria_em_uso com os caminhos e itens, 422
limite_categorias com "N de M", 403 negado (refutação: nunca o número cru). `docs/COBERTURA_UI.md` e
`docs/cobertura_ui_lacunas.json` regenerados (41 → 36). e2e com axe (0 sérias), capturas 390/1280 e restauração da
árvore original ao fim em `tests/e2e/test_categorias_ux12.py`; textos em pt-BR/en/es.
## codex cx1, setembro de 2026 (item UX-10-acervo-sem-tela: a rota de escrita do acervo com controle nomeado na tela /acervo)

Fecha a lacuna "POST /api/acervo/{fonte_id}/adicionar sem tela" do mapa de cobertura (UX-00): a tela /acervo do
L6-01-c (juntada aqui sobre a cadeia UX-00..05, com a legenda do acervo reaplicada nos arquivos do mapa da UX-04)
ganha os quatro estados do sistema de design — `<plat-estado>` na lista (carregando com esqueleto, vazio com
"limpar filtros", erro com "tentar de novo" e referência, negado) e no controle "adicionar ao meu mapa", que
passa a viver dentro da ficha com estado próprio: 403 vira negado com o privilégio exigido (e quem não tem
`conteudo.registrar_fonte` vê o negado antes de clicar), 409 vira o diálogo de confirmação de dado pessoal
(a confirmação repete com `confirma_risco_pii`), 413/422/5xx mostram a mensagem da API com a referência —
nunca o número cru (refutação). `plat-estado` ganhou `data-acao` nos botões; acervo.css e a legenda do mapa
ficaram só com tokens (guarda do UX-01 = 0). `docs/COBERTURA_UI.md` e `docs/cobertura_ui_lacunas.json`
regenerados: 41 → 40 lacunas. e2e com axe (0 sérias) e capturas 390/1280 em `tests/e2e/test_acervo_ux10.py`.

## turno 8, setembro de 2026 (item UX-04-tela-mapa-polimento: chrome único do visualizador; ramos de painel juntados)

Trilha de interface. Juntados no mesmo tronco os ramos de painel do mapa (`wt/l201mapa`, `wt/il201gtabel`,
`wt/desenho`, `wt/il201dpopup`, `wt/il201lexpor`); os arquivos que todos tocavam foram refeitos por junção de três
vias sobre a base `wt/l201mapa` (não por união de texto). O visualizador ganhou UM chrome: barra no topo, trilho à
esquerda com um botão por painel, gaveta com um `<plat-painel>` por função (pesquisar, camadas, legenda, medição,
desenho, anotações, impressão, exportar) e a tabela de atributos ancorada ao rodapé do mapa; atalhos de teclado
(b c l m d a i e t, f tela cheia, Esc, ?), tela cheia, impressão pelo navegador (@media print só o mapa), painel
inferior de 390 px em celular, navegação do produto como gaveta sobre o mapa, mapa-base escuro. `web/mapa.css` só
com tokens. e2e `tests/e2e/test_mapa_chrome.py` (cada painel em 1280 e 390, axe, i18n, atalhos, impressão, base);
os e2e dos painéis passam a abrir o painel que usam (`window.plat.mapa.abrirPainel`). Consertos achados ao juntar:
`<select>` de camada da tabela de atributos vazio (`append(nó, array)` em `tabela.js`), fuga da variável `simbologia`
duplicada em `app/mapa/rotas.py`, `return` morto em `simbologia.py`, `servir_local.py` e `main.py` duplicados pela
união; aviso da barra passa a flutuar sobre o mapa (um aviso mudava a altura do canvas e a composição do PNG). Chaves
de i18n dos painéis traduzidas para en e es (paridade mantida). Fora do escopo e registrado no handoff: o teste
`test_ordem_opacidade_e_enquadrar` depende da ordem da bancada (a camada inativa entre as duas ativas); o Martin de
produção não enxerga funções novas sem reinício, por isso o e2e da trilha sobe um Martin próprio.

## turno 8, setembro de 2026 (item UX-03-tela-conteudo-item-lixeira: estados explícitos, arrastar e soltar, seleção que sobrevive, 1.000 itens medidos)

Trilha de interface. A lista do catálogo passa a mostrar `<plat-estado>` em vez de ficar em branco: vazio (com "Novo
item" ou "limpar busca, pasta e filtros"), carregando com esqueleto, erro com a referência e "tentar de novo", negado
em 403; o painel do item idem para uuid inexistente/negado/erro. Arrastar arquivos sobre a lista cria itens
(`js/catalogo/soltar.js`) pelo MESMO caminho de "Novo item > Arquivo", agora extraído em
`novo.js::enviarArquivoComoItem` — e esse caminho estava quebrado desde o L0-03: as partes iam sob cookie (415, CSRF)
e a conclusão lia `item_id` onde a API devolve `arquivo_id`; passa a usar token de serviço em memória como a tela
/uploads (a API só aceita `admin:inquilino` nessas rotas, medido: `camada:editar` e `catalogo:ler` recebem 403 — quem
não é administrador não consegue enviar arquivo pelo navegador; registrado para o dono da rota). A seleção em massa
sobrevive a reordenar e filtrar (é por id; só troca de aba ou "limpar seleção" a zera). Desempenho:
`performance.measure('catalogo:render')` em `lista.js`; `tests/e2e/test_conteudo_ux03.py` cria 1.000 itens pela API e
mede p95 do render completo em 20 renders: **57,7 ms** (mediana 47,8 ms) com carga 11,3 e 6,7 GB livres
(`tests/medidas/UX-03.json`) — alvo 500 ms. Capturas em 390 e 1280; axe sem violação séria em lista, painel,
compartilhamento e lixeira.

## turno 8, setembro de 2026 (item UX-02-telas-entrada-conta-convite: entrada, 2FA, conta, convite e redefinição polidos; interface em pt-BR, en e es)

Trilha de interface. As telas públicas (/entrar, /aceitar-convite, /redefinir-senha) ganharam erro por campo
(`js/base/campos.js`: aria-invalid + mensagem ligada por aria-describedby, foco no primeiro inválido), botão ocupado
durante a chamada, aviso de Caps Lock, estado de servidor fora com "tentar de novo" e estados de token inválido/expirado
como `<plat-estado>` nomeado. O idioma passou a ser resolvido em `js/base/i18n.js` (URL > localStorage > <html lang> >
navegador > pt-BR), com o seletor `<plat-idioma>` nas telas públicas e a preferência da conta aplicada por
`exigirSessao`; `web/js/i18n/en.json` e `es.json` completos (995 chaves, paridade de chaves e de variáveis provada por
`tests/unit/test_i18n_paridade.py`); `ORG_IDIOMAS` passa a admitir os três. /conta: passos numerados do 2FA, estado
de carregando nas tabelas, troca de idioma aplicada na hora. e2e `tests/e2e/test_entrada_conta.py`: fluxo inteiro
entrar → 2FA → conta → sair com capturas em 360 e 1280, axe sem violação séria em cada tela, textos em en/es, e a
refutação (campo inválido nunca some sem mensagem) em entrada, código 2FA, convite e redefinição. Conserto de passagem:
`<plat-tabela>` usa aria-label em vez de caption oculta (traço de 1 px no canto da tabela).

## turno 8, setembro de 2026 (item UX-01-sistema-de-design: tokens únicos, componentes base, guia viva, guarda de literal)

Trilha de interface. `web/estilo/tokens.css` vira a única fonte de cor, tipo, espaço, raio, sombra e foco (primitivos
por tema + semânticos); `web/style.css` a importa e todas as telas passam à identidade "instrumento" (o remapeamento
por `body.instrumento` saiu). Componentes novos: `<plat-estado>`, `<plat-toasts>`/`notificar()`, `<plat-painel>`,
`<plat-tema>` com `tema_cedo.js`. Guia viva em `/estilo-guia` com contraste calculado no navegador. Guarda:
`docs/verificar_tokens.py` + `tests/unit/test_tokens_visuais.py` (0 literal fora de tokens.css, medido: 15 achados
corrigidos na primeira passagem). e2e `tests/e2e/test_estilo_guia.py`: axe 0 violações sérias nos dois temas (o acento
claro precisou escurecer para passar), troca de um token muda 3 telas, teclado e anel de foco; `test_capturas_telas.py`
captura as 20 telas em 1280 e 390 antes e depois. `scripts/servir_local.py` com TLS para o e2e de escrita em trilha.
Conserto de passagem: `/admin/organizacao` nunca marcava pronta (zona morta temporal de `smtpAtual`).

## turno 8, setembro de 2026 (item UX-00-mapa-de-cobertura-da-interface: rota sem tela reprova)

Trilha de interface. `docs/gerar_cobertura_ui.py` cruza as rotas da aplicação viva com as chamadas de `web/` e as
páginas de `app/paginas.py` e escreve `docs/COBERTURA_UI.md` (rota → tela/controle → estado) e a linha de base
`docs/cobertura_ui_lacunas.json`. Primeira medição: 196 pares método × rota, 137 cobertos, 22 sem controle, 20 sem
tela, 17 externos sem exposição, 28 lacunas de escrita. `tests/unit/test_cobertura_ui.py` reprova rota de escrita
nova sem tela e fora da linha de base; `--registrar` cria um item UX-<n> por grupo com lacuna. ADR em
`docs/adr/*-cobertura-da-interface.md`.

## codex cx1, setembro de 2026 (item L5-04-a-blocos-de-conteudo: narrativa por blocos no editor de arrasto, mapa com vista salva, texto alternativo obrigatório na publicação)

Tipo de item `narrativa` (migração `20260908T0300_narrativa_tipo.sql`, envelope do L5-05) editado pelo editor
compartilhado do L5-08 com a paleta `paleta_narrativa.js` (capa, texto, imagem, vídeo, áudio, mapa, tabela, botão,
separador, incorporar, aplicativo); o editor ganhou ganchos genéricos (`personalizados`/`controle`/`resumo`,
`api.propriedade`, área de texto para strings longas). Leitor próprio (`web/js/narrativa/leitor.js`) para
`/executar` e para a página publicada do L5-14; bloco de mapa com vista salva = bbox + proporção do quadro,
reaberto por `fitBounds` (deriva ≤ 1 % em 5 mapas × 2 viewports, e2e). Publicar recusa imagem sem texto
alternativo (`422 narrativa_nao_publicavel`, lista por bloco) — regra no servidor, mensagem no construtor. Ramo
junta `wt/il514public` (L5-14) e `wt/cx501d` (L5-01-d) para reusar publicação e sanitização. Testes: 5 unitários,
4 de API, 4 e2e com capturas.

## turno 5, setembro de 2026 (item L5-14-publicacao-links-embed: publicação de documento de construtor — links e embed)

Publicar um documento de construtor (`app`/`painel`) por `POST /api/itens/{id}/publicacao` faz três coisas
numa transação: aponta `plat.item.versao_publicada` (mecanismo já existente, reaproveitado), reserva a URL
`/p/<inquilino>/<slug>` (tabela nova `plat.item_publicacao`) e emite um token de serviço PRÓPRIO da
publicação com escopo calculado automaticamente (as camadas citadas pelo documento, via fecho de
`plat.item_relacao`) e `restricao.referer` = domínios de incorporação escolhidos — mesmo mecanismo de
`token_servico`/escopos do L0-02/L1-02, nenhuma autorização nova. Acesso à página: público (quando o
inquilino permite) ou por link-com-token (reaproveita `plat.compartilhamento_link`/`link_resolver`, o
mesmo de `/c/<token>`); nega com 401/403 depois de revogado. Rascunho editado não muda o publicado até
novo publish (a leitura pública é sempre da versão CONGELADA em `plat.item_versao`, nunca da linha viva).
`GET /p/{inquilino}/{slug}` serve a casca HTML com `Content-Security-Policy: frame-ancestors` calculado
pelos domínios do app (exceção só nesta rota; nunca um `X-Frame-Options: DENY` genérico) — só funciona
embutido nos domínios cadastrados. `GET /api/itens/{id}/publicacao/exportacao` devolve HTML autocontido
(sem chamada de rede) que abre por `file://` com o mesmo conteúdo. `GET .../publicacao/visualizacoes`
mostra a contagem por dia (`plat.item_publicacao_visualizacao`, incrementada dentro de
`plat.publicacao_resolver`, SECURITY DEFINER). Ver `docs/adr/20260907T1410-publicacao-links-embed.md`
(decisão de guardar o token da publicação em texto claro, não só hash — ele é uma chave publicável por
natureza, não um segredo) e `laco/handoffs/T5/L5-14-publicacao-links-embed.md` (portão cláusula a
cláusula, o que ficou de fora).
## turno 4, setembro de 2026 (item L5-01-d-widgets-pagina-menu: widgets de página e de menu)

- **12 widgets** sobre o motor do L5-06 (`web/js/widgets/`): texto (Markdown + `{campo}` da feição, sanitizado),
  imagem (endereço ou campo), botão (evento, link seguro, página), cartão, incorporar (iframe com sandbox e lista
  de domínios; HTML sanitizado em srcdoc), divisor, menu, controlador de widgets, compartilhar (link, QR local por
  `GET /api/qr.svg`, código de incorporação), login, seletor de idioma e seletor de tema.
- **Executor de páginas** (`/executar`) desenha esses tipos pelo motor de widgets — `texto` e `imagem` deixam de
  ter renderizador próprio; eventos `*.pagina` trocam de página; paleta de páginas ganha os tipos novos.
- Segurança: `web/js/widgets/seguro.js` (URL, domínio, sandbox, Markdown, `{campo}`), `htmlSeguro` com `proibir`
  (corta `<style>`); e2e injeta 10 vetores XSS em texto, cartão, botão, imagem, menu e embed — nenhum executa,
  console sem erro. ADR `docs/adr/20260907T2245-widgets-de-pagina-e-menu.md`; paridade em docs/PARIDADE.md.
## codex cx1, setembro de 2026 (item L2-06-c-acoes-seletores-filtros-cruzados: gatilho e ação entre elementos do painel, filtro cruzado por SQL no servidor)

O painel ganhou o barramento do L5-07 (verbatim, um só para a plataforma) e a ponte que liga elemento a elemento:
elemento `seletor` (categoria, número com faixa, data com presets, feição) e documento `mensagens` (gatilho →
ações `filtrar`/`selecionar`/`limpar_*`/`zoom`/`pan`/`piscar`/`popup`/`abrir`/`fechar`/`definir_parametro`). A
mesma mensagem valida nos DOIS lados: `app/paineis/interacoes.py` (422 `grafo_invalido` com a regra quebrada —
relação obrigatória em ação de dado, inclusive na mesma fonte, porque linha de painel não tem coluna de id) roda
os mesmos casos do `modelo.js` real em node (`tests/app/executar_painel_js.mjs`). O filtro dinâmico de cada ação
entra pelo CQL2 já auditado com um nó novo (`separar_espacial`: `s_intersects` só na forma de retângulo alinhado,
virando `ST_MakeEnvelope` com parâmetro — geometria nunca vira texto) e todo campo citado passa pela lista branca
da fonte. Estado no URL por vista (`v.v:`), então a URL copiada reabre com os mesmos seletores. Medido em
`tests/medidas/L2-06-c-acoes-seletores-filtros-cruzados.json`: latência gatilho→ação **p95 0,054 ms com 10.000
feições** (portão ≤ 100 ms; pior caso com relação por atributo 2,08 ms), ciclo A↔B cortado em uma volta
(200 disparos, 200 cortes), 5.000 seleções em 0,88 ms, e o e2e confere cada contagem da tela contra COUNT(*) na
tabela da camada, na MESMA conexão do contexto (a tabela tem RLS forçada por inquilino). Defeito corrigido no
caminho: filtro de execução com parte vazia montava `WHERE () AND (...)` e dava erro de sintaxe
(`app/paineis/dados.py`); ADR `docs/adr/20260909T0045-interacoes-do-painel.md`.

## codex cx1, setembro de 2026 (item L2-06-b-elementos-basicos: doze tipos de elemento no painel, todos com número do servidor)

Indicador (nove estatísticas, formato, ícone, cor por faixa, modo "uma feição"), gráfico serial (barras, linhas e
área; por categoria ou por data com o fuso do inquilino; várias séries; empilhado), pizza/rosca, tabela (colunas
com ordenação, ou agrupada com subtotal e total geral vindos do servidor), lista paginada, mapa, detalhes, texto
rico com markdown seguro, legenda e cabeçalho. Nenhum número é calculado no navegador: tudo passa pelo motor de
agregação do L2-06-e por `app/paineis/dados.py`. O mapa publica a extensão dos pontos que desenhou e ela vira
condição espacial em todas as fontes do painel. Medido em `tests/medidas/L2-06-b-elementos-basicos.json`: lista de
10.000 feições a **66,8 ms por página** (p95 no navegador, portão ≤ 300 ms), extensão do mapa recortando 10.000
para 999 feições e 14 elementos com captura própria. Dois defeitos de plataforma corrigidos no caminho: a ordem
dos parâmetros do SQL de agregação (gráfico por mês MAIS filtro global dava 500) e o repintar com resposta
atrasada (o painel voltava ao filtro anterior). Paridade contra a lista de elementos dos Dashboards em
`docs/PARIDADE.md`; ADR `docs/adr/20260908T1500-elementos-do-painel.md`.

## codex cx1, setembro de 2026 (item L2-01-i-graficos-de-camada: cinco gráficos por camada agregados no servidor, clique que seleciona no mapa)

`POST /api/camadas/{id}/grafico` ao lado da rota de estatísticas do L2-06-e (mesmo item, colunas, filtro,
extensão e cache; `compilar_filtro` passou a ser partilhado): barras/pizza com N maiores + `outros` calculado
na mesma consulta, linha por faixa de data pelo motor do L2-06-e, histograma com bordas de `numpy.histogram`
reproduzidas em float8 no Postgres (`width_bucket` nas bordas; contagens e bordas idênticas nos testes),
dispersão com `regr_*` sobre todas as linhas e amostra por `TABLESAMPLE` (reta igual à do `numpy.polyfit` a
1e-6), e `contagem` para a seleção. Achado de desempenho com migração própria: a política de RLS
`tenant_id = plat.tenant_atual()` impedia varredura paralela em toda camada hospedada (função PARALLEL UNSAFE
por padrão) — o histograma de 1 mi de pontos levava 551 ms; com `20260908T0100_funcoes_contexto_parallel_safe`
os cinco pedidos do portão ficam entre 72 e 168 ms p95 (`tests/medidas/L2-01-i-graficos-de-camada.json`).
No visualizador: bloco "Gráficos" e botão ▥ na árvore, SVG próprio puro (`grafico_svg.js`, árvore convertida por
`createElementNS`, ≤ 40 kB nos piores casos por tetos de desenho), tabela oculta e CSV dos mesmos dados, PNG por
canvas, guardado por camada em localStorage, clique que seleciona no mapa (filtro SQL-92 para a contagem no
servidor + expressão MapLibre numa camada de destaque). Testes: 31 de API, 16 unitários no node, 6 e2e com 12
capturas.
## codex cx1, setembro de 2026 (item L5-01-e-acoes-configuraveis: painel "Ações" por widget e ações do usuário)

Painel "Ações" no fim das propriedades de cada widget de app no construtor (`web/js/app/painel_acoes.js`, gancho
`extensaoPropriedades` do editor): gatilho (só os eventos que o TIPO do widget emite) → alvo (widget ou vista) →
ação (só as que o alvo aceita) → parâmetros (relação mesma fonte / por atributo com os campos em lista / espacial;
condição CQL2 sobre os registros de origem). Validação nos dois lados (`web/js/app/modelo.js` e
`app/app_modelo/validar.py`, contrato dos widgets espelhado em `contratos.py` e comparado por teste):
`evento_incompativel`, `alvo_incompativel`, `gatilho_repetido`, condição inválida ou com campo inexistente; campo
renomeado na fonte vira "referência quebrada" marcada no painel. Barramento aplica a condição (ação de widget não
dispara se nenhum registro passa). Botão "Ações" do usuário nos widgets de dado: exportar CSV/GeoJSON das feições
FILTRADAS, ver na tabela, zoom à seleção, criar item com a seleção (tipo `selecao`; sem o tipo, erro nomeado no
menu). Portão (`tests/e2e/test_app_acoes.py`): app "seleção no mapa → filtra tabela → gráfico pisca (condição) →
lista de escolas (atributo)" montado só pelo painel, 8 capturas, exportação com 1 linha filtrada (CSV e GeoJSON).
Refutação (`tests/unit/test_app_acoes.py`): 30 ações em cadeia, p95 0,47 ms por volta e profundidade 31, ciclo
fechado só avisa e para (filtro idempotente); renomear campo quebra a relação nomeadamente nos dois validadores.
Quadro gatilhos × alvos × ações vs os 8 gatilhos do EXB em `docs/PARIDADE.md`. ADR `20260908T1200`.
## 8 de setembro de 2026 (item L1-01-f-formatos-de-entrada: a lista fechada de formatos, com arquivo aberto provando cada um)

A ingestão de imagem ganha contrato de entrada. `app.imagens.formatos` é a tabela única — 12 formatos
aceitos (GeoTIFF/BigTIFF, JPEG 2000, Erdas Imagine, ENVI, ASCII Grid, PNG/JPEG com world file, netCDF
1 variável × 1 tempo, GRIB 1 mensagem, Zarr, KMZ superoverlay e o zip contêiner de mosaico) e os
recusados com mensagem dirigida (ECW/MrSID por SDK proprietário ausente; GeoPDF, HDF5, netCDF com eixo
de tempo apontando o L1-19, ASCII com vírgula decimal). A rota GET /api/imagens/formatos devolve
`formatos.lista()` e a tela de upload lê a mesma tabela (i18n pt-BR) — teste de API compara resposta e
código, tabela diferente é a refutação nomeada. O portão inteiro roda contra o job real, o Garage e o
pgstac da trilha (`tests/api/imagens/test_formatos_entrada.py`, 22 testes; arquivos de teste em
`tests/dados/raster/` com licença anotada): cada formato aceito vira COG válido (o científico do
GeoTIFF e o do MOSAICO revalidados fora do job com `cog_validate --strict`), zip com 4 cenas vira 1
item com 1 COG mosaicado (192×144 da união, identidade de mosaico preservada — achado: o VRT dizia
"1 cena"), zip com CRS diferentes recusa dizendo quais (EPSG:31983 × EPSG:4326, com o nome de cada
arquivo), JP2 de 12 bits importa com UInt16 preservado, IMG com `.rrd` importa. Quatro achados de
produto do ramo base, consertados e medidos aqui: (1) CRÍTICO — `pgstac.update_collection_extents()`
falhava no schema da trilha e o `except` Python capturava, mas a transação Postgres ficava ABORTADA: o
commit virava ROLLBACK e o item raster inteiro se perdia silenciosamente (21 itens 'arquivo', zero
'raster'); conserto por SAVEPOINT/ROLLBACK TO SAVEPOINT. (2) O cadeado de sidecar
(`GDAL_DISABLE_READDIR_ON_OPEN`) impede o driver ENVI de achar o `.hdr` irmão — e o mesmo cadeado
quebrava a 2ª etapa da conversão visual, porque o VRT REFERENCIA o `.dat`; `ambiente_isolado(*fontes)`
cede pela FONTE ORIGINAL (`cog._rodar(fonte=...)`). (3) Upload canônico (`objetos.guardar`, chave
`<slug>/<classe>/<sha256>.<ext>`) × objeto de imagem (`objetos_raster`, chave `<slug>/<item>/...`) são
contratos distintos — misturá-los chegava ao job como "o objeto não existe mais no armazenamento".
(4) A rota POST /api/imagens/ingestoes (L1-01-i) registrava o evento `imagens/ingestar` sem cadastro em
`plat.evento_tipo` — FK reprovava, 500 em todo POST; migração 20260908T2350 registra o tipo. ADR
20260908T2357. Ressalva do merge: `openapi.json` ficou obsoleto quanto à rota de formatos (turno de
outro item) e o caso cruzado de GET /api/imagens/formatos fica deliberadamente fora (rota só de
leitura, coberta pelo teste de igualdade com a tabela).

## 8 de setembro de 2026 (item L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo: lixeira de 7 dias, expurgo pelo catálogo e `plat raster gc`)

O item de imagem ganha fim de linha. Excluir pelo navegador esconde o item pela RLS (tile responde 404 em
0,016 s, `tests/medidas/L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo.json`), tira o corpo STAC do pgstac
guardando-o em `plat.raster_item.stac` (migração 20260908T1911) e enfileira o apagamento dos objetos para
daqui a 7 dias; restaurar dentro da retenção devolve tudo (o objeto nunca saiu do balde) e fora dela devolve
409 `objetos_ja_apagados`. O expurgo do catálogo passa a ter destruidor do tipo 'raster' (objetos + STAC +
espelho, bytes liberados no evento). O CLI `plat raster gc` lista órfãos, quebrados e lixeira vencida e
registra o relatório como job concluído em Tarefas — fora do worker, pelo caminho honesto da máquina de
estados: `plat.job_registrar_concluido` (migração 20260908T1932, SECURITY DEFINER) nasce pendente, vira
'rodando' se ninguém pegou e conclui por `plat.job_terminar`; a enumeração de inquilinos da CLI usa
`plat.tenants_para_manutencao()`, porque a RLS de `plat.tenant` deixa a tabela vazia para o app sem sessão.
A coleta LISTA e RELATA; apagar órfão é decisão humana. Refutação: 3 itens, apaga 2, o 3º intacto byte a
byte, e o COG excluído não volta pela URL antiga (403 dentro da retenção — barra até a fatia em cache do
nginx; 404 por ausência depois). ADR 20260908T1955.
## turno 3, setembro de 2026 (item L7-04-a-manual-capturas-geradas: manual gerado do registro vivo do e2e, com ajuda por contexto)

O manual deixou de ser texto à mão que apodrece: cada tela tem uma seção em `docs/manual/<tela>.md`
(uma fonte só, com front matter nos 3 idiomas) e a captura da seção é o arquivo que o TESTE de ponta a
ponta da própria tela produziu contra a versão atual — `make manual` valida o conjunto, roda os 14
arquivos de e2e pelo semáforo, copia cada captura para `<tela>@<versao>.png` e monta o site interno
(`docs/manual/index.html`, noindex, servido em `/manual`) e o PDF (17 páginas conferidas uma a uma).
Captura de versão diferente da versão do app REPROVA o build. Dentro do app, a ajuda por contexto
(`web/js/base/ajuda.js`, instalada pelo layout) abre no botão da barra lateral um painel na seção da
tela atual (`data-ajuda` no `<body>`), com busca sem diacríticos (mesma função exposta em
`window.platAjuda.buscar`, que o e2e exerce com 20 perguntas: 5,1 ms), seletor pt-BR/en/es e fecho por
Esc; HTML do corpo entra só por `htmlSeguro` (DOMPurify). `web/dados/manual.json` é gerado e commitado
(teste de unidade reprova se divergir da regeneração) para o painel funcionar sem build prévio.
Medição em `tests/medidas/L7-04-a-manual-capturas-geradas.json`: abrir o painel 56,1 ms, busca das 20
perguntas 5,1 ms (chromium do playwright contra a trilha). As rotas de página ganharam a rota
`/manual` em `app/paginas.py` (estático do disco, sem autenticação, noindex). Registro de construção
em `docs/adr/20260908T1925-manual-gerado-pelo-e2e.md`.
## turno 3, setembro de 2026 (item L4-02-c-isolamento: o que abrir para desenergizar um ponto)

`tipo=isolamento` em `POST /api/rede/{id}/tracar`, no mesmo grafo dos traçados irmãos (nenhum motor novo:
`isolamento.py` chama `lacos._preparar_mapa`/`_montar_arestas_custo` e `tracado._resolver_ponto`/
`elementos_e_geometria`). A resposta tem três partes: `dispositivos_a_abrir`, `elementos_isolados` e um
`resumo` com clientes, transformadores e quilômetros por nível de tensão. O conjunto é MÍNIMO POR INCLUSÃO,
não a fronteira inteira: numa rede radial a chave a jusante da falha não precisa abrir, e a prova disso é o
teste da rede de três chaves e dois fusíveis, onde a fronteira tem dois dispositivos e a resposta tem um.
Quem decide é um grafo reduzido (componente vira vértice, dispositivo vira ligação), percorrido uma vez por
candidato. Barreira de CONDIÇÃO: dispositivo sem `estado` declarado, ou com `operavel` negado, não é ponto
de corte — o traçado passa por ele e procura o próximo, e ele sai nomeado em `dispositivos_inoperantes`;
`ignorar_inoperante=false` abre mão da exigência e o conjunto muda de volta. Duas respostas honestas em vez
de conjunto inventado: `isolavel=false` quando há caminho de energia sem dispositivo, e `ponto_ja_sem_fonte`
quando o ponto já estava sem energia. Tela nova `/redes/isolamento` com o trecho isolado numa cor e os
dispositivos a abrir em cor própria (e2e com captura, lendo a cor do próprio MapLibre). 13 testes de API e 1
e2e verdes. Cláusulas com universo VAZIO, medidas e nomeadas em `tests/medidas/L4-02-c-isolamento.json`: a
extração da rede real da casa não traz camada de dispositivo de manobra (nenhuma das tabelas de manobra
existe no schema) e o ramal de ligação tem 0 de 26.581 registros com geometria; a medida de tempo ficou NÃO
MEDIDA por carga da máquina 10,95 (o brief proíbe medir tempo sob disputa).

## turno 8, setembro de 2026 (item L2-08-b-clonar-camadas-hospedadas: camadas e tabelas de um FeatureServer da Esri viram camadas do catálogo)

`POST /api/migracao/clones` (job `migracao.clonar`, retomável por camada) lê `/FeatureServer/{id}` pela conexão
`esri_rest` do L2-08-a e cria, por camada ou tabela, um item `camada_vetorial` com o mesmo preparo da ingestão:
campos com tipo, alias, tamanho e padrão (nomes saneados; `OBJECTID`/`GlobalID` viram `oid_origem`/
`globalid_origem`; `Shape__*` descartados com aviso), dados paginados por `resultOffset` (ou por `objectIds`),
geometria por EWKT com `102100` → `3857`, datas em ms (inclusive antes de 1970), domínios codificados e de
intervalo e subtipos inteiros pela mesma função da rota `/api/dominios/importar`, anexos no armazém de objetos
com sha256, relacionamentos entre as camadas clonadas (1:N com chave repetida no dado vira N:M por junção, com
aviso) e verificação (contagem origem × destino, sha256 de amostra normalizada) no relatório por camada;
re-execução sem mudança na origem não escreve nada. `X-Esri-Authorization: Bearer` passou a valer como
`Authorization`, então o FeatureServer da própria plataforma serve de fonte de teste. Conferido: serviço público
da Esri gravado com URL e data (20 feições, tabela relacionada, 3 anexos) e camada própria de 2.000 feições.
Fora desta rodada: caminho por File Geodatabase (`createReplica`), vista hospedada como vista, 500 mil feições
medidas (máquina acima da carga de medição).
## turno 48, setembro de 2026 (item L2-09-d-analise-3d-visibilidade: as quatro análises de terreno do Scene Viewer, com o viewshed sendo o gdal_viewshed de verdade)

`POST /api/analise3d/{visada,viewshed,perfil,sombra}` sobre um terreno INLINE no corpo (`app/analise3d/`:
grade srid/x0/y0/célula/alturas, sha256 canônico em toda procedência). A bacia visual NÃO é
reimplementada: a casa escreve o GeoTIFF, chama o binário `gdal_viewshed` instalado e devolve os bytes
dele mais o comando — a paridade da cláusula 2 é byte a byte com a MESMA linha de comando reexecutada,
em relevo suave e íngreme (`tests/unit/test_analise3d_viewshed.py`). Visada por varredura própria com
passo declarado: ponto de obstrução a 2,75 m do cruzamento verdadeiro (varredura densa independente de
0,25 m; cláusula 1 pede ≤ 30 m) — `tests/medidas/L2-09-d-analise-3d-visibilidade.json`. Perfil
bilinear conferido com `rasterio.sample` (20/20 amostras, cláusula 3); sombra = prisma + posição solar
NOAA, desvio de 0,268 % contra h/tan(elevação) no meio-dia solar verdadeiro de 21/12 (cláusula 4 pede
≤ 5 %). Refutações do item viraram 422 com código nomeado: observador abaixo do terreno, alvo a 200 km
ou fora da grade, amostras acima do teto, visada nula, Sol abaixo do horizonte, data sem fuso, srid
fora da faixa. `salvar_item` em qualquer rota cria item `analise_3d` pela MESMA função do
POST /api/itens (cota, schema, evento `itens/adicionar`, RLS) e exige o mesmo `conteudo.criar`; escopo
de token novo `analise3d:usar` (`app/auth/escopos.py`). Tela `/analise3d` (`web/analise3d.html`,
`web/js/analise3d/painel.js`) com terreno de exemplo determinístico; e2e com captura de cada análise
(`tests/e2e/capturas/L2-09-d-analise-3d-visibilidade_analise3d_*.png`; cláusula 5). Fora do item, por
portão: corte de malha e análise de malha integrada — paridade escrita em `docs/PARIDADE.md` (seção
"Análise 3D", cláusula 6), ADR `docs/adr/20260908T1818-analise-3d-visibilidade.md`.

Um defeito real de front achado na bancada do e2e e consertado: `perfilSvg` em
`web/js/analise3d/painel.js` chamava `.map()` da segunda série sem guardá-la — toda resposta de perfil
(que traz uma série só) quebrava a página com "Cannot read properties of undefined (reading 'map')"
com a API respondendo 200 correto. Corrigido com guard ternário; o e2e é o teste dele.

## turno 48, setembro de 2026 (item L2-03-a-api-edicao-transacional reentregue: a família de edição inteira pousa em master pela junção do wt/cx203f)

O item tinha sido marcado refutado por auditoria HARD-03 (07/09) com o motivo exato "artefato ausente em master":
`app/edicao/` existia só em ramos de worktree e nunca tinha pousado — o que deixou refutados, pela mesma causa,
L2-03-edicao, L2-03-f e todos os itens que dependem da porta de escrita (L2-03-d, L2-03-e, L2-07-c, L2-13). A
reentrega é a junção do ramo `wt/cx203f` sobre o master atual (`wt/il203aed`, merge `c54ca762`), que traz a API
`POST /api/camadas/{id}/edicoes` (única porta de escrita de feição; transação tudo-ou-nada, versão otimista com
409 e feição atual, domínios/tipo/SRID/ST_IsValid validados no servidor, rastreio preenchido pelo servidor, RLS
por inquilino), `POST /api/camadas/{id}/lote` (L2-03-f: prévia, até 5.000 síncrono, job `camadas.lote` acima, com
cálculo de campo pela linguagem L2-10-c traduzida a SQL) e a edição no mapa (`web/js/mapa/edicao.js` sobre
Martin/MapLibre do L2-01/L2-04-a). Na árvore junta, sobre o master que desde então ganhou as suítes adversariais
HARD-03 (tenancy/RLS e SSRF), tudo verde: `tests/api/test_edicao_transacional.py` 20 passed — as 6 cláusulas do
portão e os 6 ataques da refutação (lote de 100 mil recusado por limite declarado, CRS não declarado, SRID 0,
texto de 1 MB, fid de outro inquilino, edição concorrente sem sobrescrita silenciosa); cruzado/eventos/docs/
privilegios declarados 232 passed; adversário + unit verde; lote 9 passed com worker da trilha; `make lint` e
`make sem-marcador` ok; `docs/openapi.json` regenerado sem um byte de diferença.

## codex cx1, setembro de 2026 (item L2-03-f-edicao-em-lote-calculo-campo: edição em lote e cálculo de campo por expressão)

`POST /api/camadas/{id}/lote` sobre uma seleção (ids, expressão `onde` ou todas): calcular campo por expressão da
linguagem L2-10-c traduzida para SQL quando o subconjunto permite (`app/expressao/compilador_sql.py`) e avaliada
linha a linha no servidor quando não; atribuir valor fixo; apagar; corrigir geometrias inválidas (ST_MakeValid com
relatório); copiar/mover entre camadas com mapeamento de campos; pré-visualização (10 linhas antes/depois) sem
gravar. Até 5.000 feições roda no pedido; acima vira o job `camadas.lote` com progresso e cancelamento — tudo numa
transação só (erro ou cancelamento devolve a camada ao estado anterior). Campos derivados de geometria na
expressão (`$area_m2`, `$comprimento_m`, `$perimetro_m`, `$x`, `$y`). Mesma validação, "só as próprias", gatilhos
de versão/histórico, `tiles_versao` e evento por lote do L2-03-a. Painel "Edição em lote" na tela /mapa (edição do
L2-03-edicao) com prévia, aplicação, acompanhamento do job e erro nomeado. Medido em tests/medidas/L2-03-f-*.json:
100.000 MultiPolygon com `area_ha = $area_m2 / 10000` como job em 16,1 s (15,2 s dentro da transação), amostra de
1.000 igual a ST_Area/10000 (desvio 0), histórico gerado para as 100.000. Migrações: evento `camadas/lote`;
`camada_schema_garantir` só concede USAGE quando falta (evita "tuple concurrently updated" no d_demo partilhado).
ADR `docs/adr/20260908T0830-edicao-em-lote-calculo-de-campo.md`.
## turno 4, setembro de 2026 (item L2-01-f-navegacao-medicao-coordenadas: navegação, medição e coordenadas)

- **Medição no elipsoide** (`web/js/mapa/medicao.js`): Vincenty (GRS80) para distância; área por geodésicas
  densificadas + projeção equivalente local (proj4js 2.22.0 no vendor); segmentos parciais na tela e cópia;
  erro ≤ 0,1 % contra `ST_Length/ST_Area(geography)` em 5 segmentos e 3 polígonos (teste no node contra o PostGIS).
- **Coordenada do cursor em CRS escolhido** (`web/js/mapa/crs.js`: 4326, 4674, 31981-31985, 5880, 3857; definições
  de `spatial_ref_sys`, conferidas), UTM 22S ≤ 1 cm de `ST_Transform`; clique copia.
- **Ir para** aceita decimal com vírgula e sinal tipográfico, GMS e `x y EPSG:NNNN`; malformado recebe mensagem.
- **Navegação** (`web/js/mapa/navegacao.js`): favoritos (nome + extensão + rotação, localStorage por mapa),
  histórico voltar/avançar, norte, tela cheia, minha localização com círculo de precisão, atalhos documentados.
  e2e com 9 capturas; ADR `docs/adr/20260907T2330-navegacao-medicao-coordenadas.md`; paridade em PARIDADE.md.

## turno 3, setembro de 2026 (item L0-06-e-status: página aberta de estado da instalação)

`GET /api/status` e a página `/status` respondem sem sessão, com `X-Robots-Tag: noindex`: estado de api,
banco, worker, martin, titiler e garage (as mesmas sondas do health check profundo, nunca uma segunda lista),
migrações aplicadas e pendentes, fila (na fila, executando, falhas em 24 h), última cópia de segurança, último
ensaio de restauração, menor percentual livre de disco, espaço e objetos no armazenamento do Garage, dias
restantes do certificado, histórico de 90 dias por serviço e percentual de disponibilidade do mês, mais o log
de correções lido do próprio CHANGELOG. O histórico vem de `plat.status_amostra`, gravada a cada 5 minutos pelo
periódico `status.amostrar`, que usa o MESMO retrato que a página serve; o percentual é recalculado das
amostras a cada pedido (o teste recalcula por fora e compara). A resposta é só agregado: sem versão da
aplicação ou de dependência, sem caminho de volume, sem alvo `host:porta`, sem slug de inquilino, sem nome de
bucket — o detalhe continua no `/saude/profunda`, atrás de sessão de superadmin.

Medidas: 1.000 pedidos em 20 conexões levaram 1,07 s, todos servidos do cache de 30 s, nenhuma consulta ao
banco; retrato frio em 92 ms (carga 5,5-6,7 em 12 núcleos). Duas correções nasceram de medir em vez de ler:
somar o espaço com um `GetBucketInfo` por bucket custava 5.272,8 ms por retrato e virou uma chamada única de
estatística do cluster; e o log de correções vazava nome de dependência e caminho de arquivo do CHANGELOG (o
teste de vazamento reprovou de verdade), então passou a ser higienizado, e a frase que só sobra em pedaços não
entra. Cláusula do worker medida com servidor HTTP real em porta livre no lugar de `PLAT_WORKER_URL` — cai em
31 s e volta em 31 s, dentro dos 5 minutos do portão; `systemctl stop` de unidade de produção é proibido na
trilha e não foi usado. `tests/medidas/L0-06-e-status.json`, ADR `20260907T2257-pagina-de-estado-aberta.md`.

## turno 3, setembro de 2026 (item L7-34-saude-profunda: health check profundo por componente)

`GET /saude/profunda` sonda 13 componentes (banco+migrações, fila -- workers vivos e idade do job
pendente mais antigo via nova função `plat.fila_job_mais_antigo_pendente_s`, Martin, TiTiler, Garage
via S3 + Admin API `GetClusterHealth`, worker, nginx, certificado TLS, disco, RAM, e três declarados
`ausente` nesta topologia: CDN, backup, licença), cada uma num pool de threads próprio com tempo
limite de 2 s -- uma sonda pendurada nunca trava o endpoint inteiro (medido: Garage e Martin
pendurados por um servidor TCP que aceita e nunca responde viraram `erro` em 2,02 s e 1,05 s, bem
abaixo do limite de 10 s do portão). Resposta anônima (sem sessão, para o balanceador/CDN) só tem
nome+estado+tempo de cada componente; sessão de superadmin vê o detalhe (alvo `host:porta`, motivo,
contagens) -- nenhuma das duas nunca inclui DSN, token do Garage/admin ou o nome do inquilino
(varredura de texto sobre o corpo inteiro nos dois casos). `200`/`503` conforme o pior estado entre
os componentes; `ausente` nunca eleva o estado geral. Sem UI própria neste turno (papéis do item:
backend, adversário) -- consumido hoje só pelo balanceador e por chamada direta de admin.

Retomada de sessão que morreu antes por limite do servidor ao criar o symlink do venv no worktree
(o código e os testes já estavam prontos no disco, sem commit); corrigidos dois testes que assumiam
detalhe (`workers_vivos`, `volumes` de disco) na sessão anônima -- esses campos só existem na versão
admin, então passaram a usar `sessao_plat`. `tests/medidas/L7-34-saude-profunda.json`.
## turno 3, setembro de 2026 (item L3-08-pareto: fronteira de Pareto, análise sem agregação)

A pergunta que vem antes do peso: quais unidades podem ser as melhores para QUALQUER escolha de peso.
`app/amc/pareto.py` faz a ordenação não dominada de 2 a 4 objetivos em ordens (1ª, 2ª e 3ª fronteiras),
com direção declarada por objetivo, empate na mesma ordem e unidade com objetivo ausente FORA da
ordenação — nunca com o valor zero no lugar do que falta. A peneira rápida (ordem lexicográfica
decrescente, comparação só contra a fronteira em formação) foi conferida contra um laço ingênuo O(n²)
escrito do zero no teste, em **2.000 unidades** e em cinco combinações de objetivos e direções, com e
sem ausência de dado: ordem idêntica unidade a unidade em todas
(`tests/medidas/L3-08-pareto.json`). A refutação exigida pelo item passa: com dois objetivos iguais a
fronteira é a unidade de valor máximo e todos os seus empates, tanto no módulo quanto pela API.

Duas rotas de leitura sobre a execução do motor de grades aninhadas (L3-19): `POST /api/amc/pareto`
devolve a ordem por unidade com os valores que a produziram, e `POST /api/amc/pareto/camada` devolve as
ordens pedidas como GeoJSON, com os objetivos, a contagem por ordem e o aviso dos pesos em `metadados`
— o método viaja junto com o dado. Tela `/amc/pareto` com gráfico de dispersão e mapa ligados: escovar
um retângulo no gráfico aplica na camada de realce do MapLibre o filtro com exatamente aqueles
identificadores. A conta dessa ligação (`web/js/amc/pareto.js`) é executada em node pelos testes, como
já se faz com o combinador; o e2e do arrasto está escrito e **não foi corrido nesta trilha**, que não
tem nginx para servir `/static`. Nenhuma migração, nenhuma tabela nova: a catalogação do resultado
continua sendo o item L3-13. O teto de unidades da rota (`PARETO_UNIDADES_MAX = 50.000`) foi rodado, não
suposto: ordenar 50.000 unidades × 4 objetivos em 3 ordens levou **6.836 ms** com carga de 1 min de 5,51
e 5,81 GB livres — é teto de tamanho, não de conforto, e análise nessa escala deve virar job. ADR
`20260908T1140-fronteira-de-pareto-sem-agregacao.md`.
## turno 8, setembro de 2026 (item L7-13-a-chamados: chamados de suporte dentro do produto, com captura, SLA de primeira resposta e painel do operador)

O cliente reporta de dentro de qualquer tela (botão "Reportar problema"), com captura do canvas do mapa e
contexto automático (tela, versão, navegador, idioma, req_id das últimas 20 requisições, estrutura do DOM sem
valor de campo). O operador (superadmin) tem painel em `/admin/chamados` com a fila de todos os inquilinos,
resposta e mudança de estado por funções SECURITY DEFINER que provam a identidade pelo hash da sessão; quem
não é superadmin leva 404. Anexo passa por duas provas (varredura de cabeçalho em memória + prova de tipo lendo
o objeto de volta do Garage, esta FORA da transação porque o bucket só é visível após o commit — falha medida
nesta rodada); executável declarado geojson é 415 na entrada, e a chave do objeto nunca sai do banco (a
refutação "ler anexo alheio pela URL" não tem URL). SLA de primeira resposta por severidade (4/8/24/72 h
declarados em `app/limites.py`) exibido junto do tempo MEDIDO em toda leitura; e-mail de resposta no idioma da
conta do cliente (pt-BR/en/es, regra de escrita de 03/09 testada) e banner dentro do produto cobrindo quem não
tem e-mail. Testes: 32 unit + 9 API + 2 e2e (fluxo completo por tela contra a bancada TLS e invisibilidade
entre inquilinos na UI). ADR `docs/adr/20260908T2330-chamados-suporte.md`; MANUAL seção 22.
## turno 4, setembro de 2026 (item L6-02-o-importacao-exportacao-formatos: intercâmbio em lote e escrow do inquilino)

`POST /api/intercambio/exportacoes` acrescenta aos 11 formatos do L0-04-h os quatro que faltavam e que o
GDAL 3.8.4 desta máquina escreve: GeoJSON Sequence, File Geodatabase (driver `OpenFileGDB`, entregue como
zip do diretório `.gdb`), MBTiles e PMTiles. Com `tipo: "inquilino"` a mesma rota gera o **escrow**: todas as
camadas vetoriais do inquilino num único GeoPackage multi-camada mais um `manifesto.json` (schema, campos,
SRID, contagem de feições e sha256 por camada), num zip — a saída de dados prevista no L0-06.
`POST /api/intercambio/importacoes-lote` importa N arquivos numa chamada: é AGRUPAMENTO, não outro funil —
a prova de conteúdo, a inspeção e a carga continuam sendo as do L0-04, e a criação do lote é uma transação
só (arquivo malformado no meio não deixa importação pela metade). Antes de gerar, a exportação escreve o que
o formato de destino vai FAZER com os campos, em vez de deixar o aviso do GDAL passar em silêncio: nome de
campo acima de 10 caracteres truncado pelo DBF (com o nome exato que o shapefile vai ter), campo data-hora
virando texto ISO 8601, texto acima de 254 caracteres cortado, inteiro de 64 bits virando número real no
FileGDB e geometria quantizada na grade do tile em MBTiles/PMTiles. `GET /api/intercambio/formatos` responde
o que esta instalação lê, o que escreve e o que **não temos** com o motivo escrito — nunca um total de
formatos. Ver ADR de carimbo `20260907T1659` e `docs/PARIDADE.md`.

Medido (`tests/medidas/L6-02-o-importacao-exportacao-formatos.json`, máquina em disputa — carga 14,7 de 12
núcleos, então os tempos são limite superior): escrow de 20 camadas do inquilino em 5,66 s; camada de 2 mil
feições em 0,54 s para GeoJSONSeq e 0,54 s para o zip do FileGDB, com as 2.000 feições relidas do `.gdb`
pelo driver `OpenFileGDB`.

⛔ O que este item NÃO faz: ampliar a IMPORTAÇÃO. Esta instalação lê quatro formatos (shapefile.zip, gpkg,
geojson, csv, do L0-04); o lote repete esses conversores N vezes e não acrescenta formato de entrada — KML,
XLSX, FileGDB e CAD de entrada são dos itens irmãos L0-04-e e L0-04-f. Não há QGIS nesta máquina: a cláusula
"FileGDB abre no QGIS" foi provada pelo driver que o QGIS delega ao GDAL (`OpenFileGDB`), relendo o arquivo
com a mesma contagem, e não pelo aplicativo.

## turno 4, setembro de 2026 (item L0-04-h-exportar: exportação de camada para outros formatos)

`POST /api/exportacoes` enfileira o job `exportacao.gerar` (202) e devolve o arquivo (item `arquivo`,
validade de 7 dias) em 11 formatos: gpkg, geojson, shapefile(zip), csv, xlsx, kml, kmz, fgb, gml, dxf e
geoparquet (este pelo DuckDB, num processo próprio — o `ogr2ogr` desta instalação não tem driver Parquet, e
o DuckDB não sobrevive a um `fork`, então a conversão roda como `python -m app.exportacao.parquet_cli`,
neto do job). Filtro (`where`), campos e CRS de saída são conferidos ANTES de existir job (400 com o erro do
banco saneado, `app/exportacao/erros.py`). Isolamento entre inquilinos: o `ogr2ogr` abre conexão PRÓPRIA,
fora do pool da aplicação — o inquilino entra na string de conexão (`-c plat.tenant_id=N`), e é a RLS do
PostgreSQL que corta, provada com pedido forjado no banco e com o `ogr2ogr` chamado sem contexto nenhum
(`tests/api/exportacao/test_exportacao_cruzado.py`). Arquivo grande nunca vai inteiro à memória: envio ao
Garage em blocos/multipart (`objetos.guardar_arquivo`, novo) e download em blocos de 1 MiB
(`objetos.ler_stream`, novo) — medido com `tracemalloc` (pico < 3 partes de 8 MiB para um arquivo de 40 MiB).
Privilégio novo `conteudo.exportar` (editor/admin); opção do dono do item "permitir que outros exportem"
(`dados.exportacao.permitir_outros`, nasce desligada). Limite de 3 exportações em curso por usuário e guarda
de disco (`shutil.disk_usage`) antes do primeiro byte. Botão **Exportar** na tela do item
(`web/js/catalogo/item_exportar.js`). Achado à parte, sem relação direta com exportação: `CursorSchemaAmbiente`
não reescrevia `executemany`/`mogrify` (só `execute`/`callproc`), o que fazia qualquer rota que use essas duas
chamadas escrever no schema `plat` de PRODUÇÃO mesmo dentro de uma base de trilha isolada — consertado em
`app/schema_ambiente.py`. Ver ADR 0018 e `docs/PARIDADE.md` seção "Exportação de camada para outros formatos".

Medido (`tests/medidas/L0-04-h-exportar.json`, camada de 100 mil feições): tempo por formato de 0,80 s
(FlatGeobuf) a 14,54 s (XLSX); todos os 11 formatos reabertos com a mesma contagem de 100.000 feições
(`ogrinfo`/DuckDB conforme o formato).
## turno 4, setembro de 2026 (item L4-06-d-categorias-e-restricoes: categorias de rede, restrição de feição, tap de subrede)

Categoria `derivacao` (equivalente de *subnetwork tap*) acrescentada ao pacote `eletrica-br` (12 categorias
no pacote, o portão pedia ≥ 8), atribuída a `unidade_consumidora/1` — ponto com um único terminal, a mesma
condição de elegibilidade da Esri. Migração `20260906T2156_rede_categorias_restricoes.sql` entrega a feição
instanciada (`plat.rede_feicao`, com o estado `controlador_ativo` e a marca `suja`), a ligação de
conectividade (`plat.rede_feicao_ligacao`) e a restrição de feição por tipo (`plat.rede_tipo_restricao`,
vocabulário `sem_ponto_partida`/`sem_terminal`). Sobre esse esquema, `app/rede_utilidades/categorias.py` (novo)
e as rotas em `app/rede_utilidades/rotas.py`: `PUT /api/rede/{id}/tipos/{tipo_id}/categorias` redefine o
conjunto de categorias de um tipo e marca `suja=true` em toda feição já instanciada dele (a contagem volta
na resposta); recusa (409) remover a categoria `controlador` de um tipo com feição de controlador ATIVO — a
refutação do item; `PUT .../restricoes` redefine as restrições de feição; `POST .../feicoes` e
`.../feicoes/{id}/ligar` instanciam feição e ligação; `GET .../feicoes/{id}/isolamento` traça um passeio em
largura sobre a conectividade que **para na categoria `dispositivo_de_protecao`** (a fronteira entra no
resultado, o que está atrás dela não) e recusa (422) partir de feição cujo tipo tem `sem_ponto_partida` — o
caso do portão é a unidade consumidora. `docs/PARIDADE.md` ganhou as linhas de *feature restrictions* e
*subnetwork tap*, com a fronteira honesta escrita: a categoria e a condição de elegibilidade do tap existem,
mas não há traçado de SUBREDE que pare nela (só o de isolamento, que para na proteção) — isso fica para o
item de traçado completo. 7 testes novos em `tests/api/test_rede_categorias.py`; medidas em
`tests/medidas/L4-06-d-categorias-e-restricoes.json`.
## turno 8, setembro de 2026 (item L5-04-c-temas-capa-colecao: coleção com capa, aviso de citação privada ao publicar e og: só na página pública)

Novo tipo de item `colecao` (família documento): o corpo traz `capa` (título, subtítulo, mídia) e `itens`
citados por uuid com rótulo opcional, e as relações `item_de_colecao` (vocabulário novo em `plat.relacao_tipo`)
são sincronizadas do corpo a cada POST/PUT pelo extrator de `app/catalogo/relacoes.py` — editar a coleção
reordena e remove relações sem passo extra, e citar item inexistente ou a si mesma reprova com 422
`relacao_com_outro_inquilino` (gatilho `plat.tg_item_relacao`). `capa.midia` e `metadados.miniatura` só aceitam
caminho da casa ou URL https (422 `colecao_invalida`; `javascript:` e `data:` não passam). Publicar por link
continua conservador: o link nasce minimalista e `POST /links` devolve `avisos` nomeando cada item citado que
ficou de fora (API e tela — a tela oferece o botão "corrigir", que recria o link incluindo os citados); o
anônimo com um link parcial lê o aviso do que ficou fora, nunca um leitor vazio sem dizer por quê
(tests/e2e/test_colecao.py). A página pública `/c/<token>` passa a levar `og:title`/`og:description`/`og:image`
dos metadados da coleção (miniatura absolutizada com `PLAT_URL_PUBLICA`, todo atributo por `html.escape`,
`cache-control: no-store`); as páginas internas não levam og:. Leitora compartilhada `web/js/colecao/leitor.js`
(capas e fichas com navegação por clique e teclado, posição pelo fragmento, sem recarregar a página — 125,7 ms para
3 cliques, medida com carga 2,73 e 9 GB livres) usada pela página interna `/colecao` e pela anônima. Cláusula
"tema trocado sem reeditar blocos" fica PENDENTE por dependência: L5-10 (temas) não está em master nesta data;
o esquema já carrega `corpo.tema` para conformar quando aterrissar (`tests/medidas/L5-04-c-temas-capa-colecao.json`).
## turno 48, setembro de 2026 (item L4-29-regras-de-atributo-de-rede: três perfis de regra sobre a rede, sem ponto fixo)

O consumidor das seis funções de rede que a linguagem de expressão ganhou neste item (`Subrede`,
`Alimentador`, `TensaoAlimentador`, `ContarJusante`, `NivelRede`, `AtributoRede`, nos dois avaliadores,
43→49 funções, 30→39 vetores de convergência). Motor `app/rede/regras.py` + `plat.rede_regra` (migração
`20260908T1934_regras_atributo_rede.sql`, RLS): `calculo` escreve um atributo, `restricao` responde "posso
fechar esta chave?" (a chave 13,8-34,5 kV recusa, medido) e `validacao` lista em lote (trafos sem UC
listados, medido). A refutação do item — regra com laço "jusante de jusante" — morre por construção: UMA
rodada avalia cada regra UMA vez por objeto, não existe ponto fixo (contador 0→1→2 em duas rodadas,
`tests/medidas/L4-29-regras-de-atributo-de-rede.json`); profundidade demais corta na criação (70 `Se`
aninhados = 422 `profundidade_excedida`) e orçamento é costura exposta (`limite_passos`/`limite_ms`,
`limite_passos` estourado = erro NOMEADO e rodada sobrevive). Restrição é falha fechada: erro de avaliação
RECUSA com o código nomeado; nulo nunca recusa e nunca grava. Tetos em `app/limites.py`
(`REDE_REGRA_MAX`, `REDE_REGRAS_OBJETOS_MAX`, `REDE_REGRAS_ITENS_MAX`, `REDE_REGRAS_ERROS_MAX`) — o teto
freia o tamanho da rodada, não a iteração, porque não existe iteração. Paridade com os perfis de attribute
rule do ArcGIS Pro escrita com fontes datadas (`docs/PARIDADE_REGRAS_ATRIBUTO.md`): a direção do booleano
de constraint é invertida de propósito (recusa no lado verdadeiro deixa o nulo do lado seguro com lógica de
três valores); sem `$datastore` e sem ganchos de edição, lacunas declaradas. Decisões em
`docs/adr/20260908T1945-regras-atributo-de-rede.md`.
## turno plataforma-48, setembro de 2026 (item L4-20-consumidores-e-enderecos: consumidores como ativo terminal e endereços sem rede, 10.914 contra 10.911 da casa)

Seis tabelas `plat.rede_*` (trechos de média e baixa tensão, transformadores, unidades consumidoras,
consumo anual, endereços do censo e a camada `rede_endereco_sem_rede`) com RLS por inquilino e
nenhum campo identificável — a origem é um recorte de distribuidora que só existe no ambiente da
trilha (`PLAT_REDE_ESQUEMA_COOP`), nunca no git. Cinco rotas em `/api/rede/consumidores`: gerar e
listar os endereços sem rede, ficha da unidade e do trecho, e o cálculo de consumidores a jusante
(árvore de largura por circuito; trecho em malha fica com NULL e é reportado). Consumo só em
agregado por transformador ou circuito, com mínimo de 5 unidades — abaixo disso a resposta traz
`motivo`. A geração da camada sobre 182.750 endereços levou o POST acima do teto da suíte (600 s)
duas vezes antes de o perfil apontar o plano ruim: sob RLS o `EXISTS` de baixa tensão escolhia o
índice btree e varria ~13 mil linhas por endereço (118 s só ali). A forma final é KNN puro nos dois
lados (`LATERAL`, `ORDER BY geometria_calc <-> ... LIMIT 1`, raio como filtro depois), que só o
índice espacial serve. Medido (`tests/medidas/L4-20-consumidores-e-enderecos.json`): 10.914
endereços contra 10.911 da camada de referência da casa (0,03 %), geração em 6,4 s, jusante sobre
44.268 trechos de média em 3,6 s, unidade+API verdes. Detalhes e o histórico do plano ruim em
`docs/adr/20260908T1900-consumidores-e-enderecos-sem-rede.md`.
## turno 8, setembro de 2026 (item L7-04-d-videos-por-tarefa: 11 vídeos de tarefa gravados da sessão real, narração piper, legendas pt/en/es, quadro confrontado com a tela real)

`make videos` executa cada roteiro (`scripts/videos/roteiros.py`, 11 tarefas: saúde, entrar, conta,
usuários, grupos, papéis, tokens, log, tarefas, mapa, conexões) com Playwright contra a instalação
viva, grava o webm da própria sessão e o ffmpeg monta o mp4 h264+aac com a narração sintética pt-BR
(voz piper livre, binário fora do git em `~/tools/piper`, ausência falha com mensagem escrita — nunca
vídeo mudo passando por completo). A legenda WebVTT nasce da janela de tempo MEDIDA por relógio
compartilhado com o gravador e só é registrada depois de a ação do passo acontecer — a resposta
estrutural à refutação "passo que não existe na versão instalada", porque execução interrompida não
gera janela nem vídeo. Cada tarefa declara a seção de `MANUAL.md` a que corresponde; gerar e
`--validar` reprovam se a seção sair do manual, a página `/videos` mostra a seção em cada cartão e a
seção 22 do `MANUAL.md` aponta de volta (laço manual ↔ vídeo fechado sem depender da tela da
L7-04-a, que segue pendente como dependência). Regeneração por versão menor: o manifesto guarda a
versão do produto e sha256 de cada mp4; `--forcar` regenera, `--validar` só confere (11 vídeos,
vídeo+áudio por ffprobe, 3 legendas com marca de tempo, duração ≤ 180 s). Entrega por
`GET /videos/arquivo/{caminho}` com sessão e lista fechada de sufixos; `web/videos/` fora do git.
E2e (`tests/e2e/test_videos.py`, 3/3 verdes contra a bancada): página lista o manifesto com manual e
3 legendas por cartão; reprodução no navegador com duração ≤ 180 s e cues carregando; quadro do
vídeo capturado por canvas e confrontado com a tela real NO MESMO estado de sessão (a 1ª versão
comparava com a página logada — prova fraca, corrigida), diferença média 0,20 num teto de 24,0
(`tests/e2e/capturas/L7-04-d-videos-por-tarefa_*.png`). Medidas: 11 vídeos, maior duração 17,7 s,
4,6 MB, carga 1 min 5,29, RAM livre 7,0 GB (`tests/medidas/L7-04-d-videos-por-tarefa.json`, comando
`make videos`). ADR `docs/adr/20260908T2130-videos-por-tarefa.md`.
## turno 8, setembro de 2026 (item L0-12-contrato-api-e-limites: 42501 sem RLS deixa de virar 403 de inquilino — achado G4-23)

`app/auth/comum.py::erro_do_banco` convertia QUALQUER `InsufficientPrivilege` do banco (SQLSTATE 42501)
em `403 sem_permissao "operação fora do inquilino da sessão"` — GRANT faltando, schema errado e papel mal
configurado saíam para o cliente como se o inquilino do usuário tivesse ultrapassado a fronteira (o
disfarce escondeu o G4-24 por horas). Agora o 403 de inquilino exige prova: a mensagem de violação de
row-level security. Os demais 42501 viram `500 configuracao_banco`, com a causa real no diário. O teste
adversarial G4-23 saiu de xfail estrito para portão e a fronteira (violação de RLS continua 403) tem
teste próprio; `docs/CONTRATO_API.md` ganhou a linha do 500.

## turno 8, setembro de 2026 (item L0-11-arquivos-objetos: /saude marca o Garage como obrigatório — achado G4-19)

Faltava uma cláusula do portão do L0-11: `/saude` decidia o status HTTP só pelo banco, então instalação
com o Garage inalcançável continuava 200 "saudável" (`servicos["garage"] == "erro"` e tudo).
`app/saude.py` agora responde 503 quando um serviço de `OBRIGATORIOS = ("garage",)` está configurado e
não responde, declara a lista no corpo (`servicos_obrigatorios`) e a fronteira fica no ADR
20260908T2125: sem `PLAT_GARAGE_URL` configurada o sonda fica "ausente" e não derruba o 200 (modo de
desenvolvimento sem objetos); martin/titiler/worker continuam informativos. O teste adversarial
`test_saude_reprova_quando_o_garage_esta_fora` saiu de `xfail(strict=True)` para portão em pé, com
teste complementar da fronteira (`test_saude_200_quando_garage_ausente`) e o contrato do corpo
atualizado em `tests/api/test_saude.py`.
## turno 8, setembro de 2026 (item L6-03-paridade-conectores: as duas linhas `fora (decisão)` que o adversário provou falsas)

O adversário do item reproduziu 11 linhas `feito` OK e provou 2 FALSIFICADAS. As linhas "armazém em
nuvem" e "NoSQL (Knowledge Server)" diziam `fora (decisão)`, e nenhuma decisão do dono cobre nenhuma
das duas — o registro `laco/estado.json`, D18-D41, não fala de armazém em nuvem nem de Knowledge
Server; a linha do armazém citava ainda "L3L6_CONCEITO seção 14", seção que não existe no documento
(as seções são A1-A10 e B1-B13) e que não trata do assunto. Correção honesta: as duas linhas agora
declaram que NENHUM item do backlog e NENHUMA decisão do dono cobre a exclusão, e a linha "pasta (file
share)" perde o "decisão:" sem dono e fica `fora (L7-11)` (o item do appliance existe e é o que
cobre). A linha STAC citava `tests/api/imagens/test_stacit_gdal.py` no ramo `wt/stac`, que não tem o
arquivo; a citação aponta agora `wt/il101apgsta` (item L1-01-a, na fila de junção, onde o teste
existe — conferido com `git cat-file -e`). A trava do guard (`tests/unit/test_paridade_conectores.py`)
era mais fraca que a regra escrita nela: linha `fora` só precisava de um parêntese no estado. Agora a
trava cobra o que a regra promete: linha `fora` nomeia item (`L<n>-<n>`) ou decisão (`D<n>`) ou
declara "nenhum item"; e TODO caminho `tests/...` citado em qualquer célula da linha (a coluna "nós"
inclusive) tem de existir em `master` ou num ramo nomeado na própria linha. Suíte: 36 passed.
## turno 48, setembro de 2026 (item L3-01-i-exportacao-metodo: o método do motor AMC exportado em JSON canônico com sha256 e PDF verificado número a número)

O método sai do estado da aplicação e vira documento: `app/amc/metodo.py` define o formato
`plat/amc_metodo` — modelo normalizado (pesos a 4 casas, vetos, combinador e política COM descrição),
transformações por fator, camadas de entrada com sha256, a entrada bruta avaliada, o resultado com
cobertura e veto, versão do motor e o sha256 da serialização canônica do próprio documento.
`importar_metodo` recalcula o hash e recusa (`documento_alterado`, com gravado × recalculado) o
documento alterado depois da exportação — a refutação do item, provada por teste: peso trocado muda o
hash e o PDF antigo deixa de conferir. `app/amc/relatorio.py` gera o PDF determinístico (`invariant=1`,
mesmo documento = mesmos bytes) no molde Suitability Modeler com UMA seção por página (resumo, fluxo
do modelo, uma página por fator com histograma bruto e tabela de valores, pesos, resultado final,
ressalvas); `scripts/metodo_exportar.py` é a linha de comando. A regra contra número digitado é
testada de verdade: o teste extrai as palavras do PDF com pdfplumber e confere cada palavra que é só
número contra `metodo.numeros_do_documento` (que varre valores, textos e chaves — o "256" de
"sha256" entra). Medido (`tests/medidas/L3-01-i-exportacao-metodo.json`): geração 6,871 ms, 8 páginas
= 8 seções, 23 números no PDF e todos no JSON; PDF lido página a página (pdftoppm) — duas passadas, a
primeira achou célula estourando a margem no resumo e caixas sobrepostas no fluxo, corrigidas e
reverificadas. Conserto de infra exigido pelo item: `app/versao.py` agora lê o sha em worktree do git
(`.git` arquivo com "gitdir:" + `commidir`), com teste.
## turno 8, setembro de 2026 (item L7-29-roteiro-demonstracao: roteiro de 30 minutos com e2e medido, fronteira gerada do painel e revisor separado)

`docs/DEMO.md` percorre o que o produto faz hoje em 9 passos (fundação L0 e mapa L2), cada um com
duração, "o que dizer", "não prometer" e o e2e que anda o mesmo caminho; seção "Passos que o roteiro
não percorre" responde os pedidos frequentes (dado de demonstração, imagens, edição, motor, traçado,
acervo, medição). A lista "o que a demonstração não faz ainda" NÃO é escrita à mão: é a seção
Fronteira de `laco/PAINEL.md` reproduzida entre marcadores, e `docs/gerar_demo.py --validar` reprova
o documento quando o bloco commitado diverge da regeneração (unitários cobrem estrutura, versão de 10
minutos como subconjunto na ordem e a regra de escrita de 03/09 com lista fechada de termos). O texto
foi revisado por agente separado sem o contexto do autor (33 pontos aplicados, nenhum fato mudado) e
o validador passou por cima do texto revisado. `tests/e2e/test_demo.py` percorre os 9 passos na
ordem contra a instalação real com captura por passo (`L7-29-roteiro-demonstracao_pNN_*.png`) e
reprova acima de 30 min: rodada final 71,2 s, 9 passos, 15 capturas, carga 1 min 5,08, RAM livre
7,4 GB (`tests/medidas/L7-29-roteiro-demonstracao.json`; passo mais lento: tarefas, 60,8 s — job de
prova de 45 s + espera de fila vazia + cancelamento pela tela). O e2e documentou o refresco da lista
de tarefas (relê só quando o contador de ativos muda entre tiques de 10 s; a regra está no ADR
`20260908T2030-roteiro-de-demonstracao-medido.md`) e a bancada de trilha passou a aceitar o
certificado autoassinado no contexto do navegador (`tests/e2e/conftest.py`, sem efeito com
certificado de verdade). As dependências do item seguem abertas (L7-01-c refutado, L3-01/L4-02/
L5-01/L6-01 pendentes) e o texto DIZ isso em vez de fingir.

## turno 3, setembro de 2026 (grupo G1: conserto de identidade, sessão, segundo fator e login externo)

Resposta ao ataque adversarial do turno 3 (`laco/handoffs/T3/ataque-g1-ADVERSARIO.md`, 6 de 8 itens
refutados). Nove marcas `xfail(strict=True)` do adversário viraram teste verde, com a afirmação dele
intacta; sete continuam, porque não foram consertadas aqui (T1, T2, e3, g1, l1, l2, l4).

**Login por diretório (achado G1-l3, o mais grave).** `POST /api/login/ldap` provisionava a conta local com
o texto cru enviado pelo cliente. Num diretório com casamento frouxo (o glauth do próprio item), `ana.silva*`
autenticava como ana.silva e criava a conta local `ana.silva*` amarrada ao DN dela; a partir daí o login
canônico recebia 409 com o nome do índice do banco numa rota pública, e a conta legítima ficava trancada sem
rota administrativa. Três consertos: (1) a conta nasce com o atributo CANÔNICO do diretório — o que o próprio
`filtro_usuario` usa como chave, depois `uid`, depois o primeiro RDN do DN; (2) `plat.ldap_provisionar`
procura a identidade pelo sujeito externo (o DN) antes do login, então o mesmo DN atualiza a linha em vez de
estourar o índice único, e a colisão que sobra vira o código curto `login_em_uso_externo`; (3)
`erro_do_banco(expor_restricao=False)` nas rotas públicas — nome de restrição do banco só sai para quem já
está autenticado. Caminho para desfazer: `DELETE /api/usuarios/{id}/vinculo-externo` (`membros.gerir`),
que apaga o vínculo, desabilita a conta, encerra as sessões e grava `usuarios/vinculo_externo_remover`.

**Expiração de senha e segundo fator (G1-b2).** `login_2fa` passava `senha_alterada_em=None` e a verificação
de expiração dependia desse parâmetro: quem ligava o 2FA recebia a política de senha mais fraca da
plataforma. Sentinela `NAO_INFORMADO` — `_abrir_sessao` lê a data do banco quando ela não vem do chamador.

**Guarda única para toda rota autenticada (G1-c1).** As 7 rotas do GeocodeServer autenticavam por
`sessao.resolver()` direto e escapavam de três guardas: pendência de conta (2FA obrigatório do inquilino),
CSRF sob cookie e a checagem de `X-Plat-Inquilino`. `autenticado()` ganhou `token_por_querystring`, e o
`?token=` do protocolo Esri virou opção DENTRO da porta única. `tests/unit/test_contrato_guarda.py` varre o
app vivo e reprova rota que declare credencial sem passar pelo guarda (e o inverso). A varredura pegou mais
duas: `GET /api/uploads/tipos` e `GET /api/importacoes/formatos` declaravam `x-auth: S/T` e respondiam sem
credencial (achado G1-e1); `POST /api/logout` é a única exceção nomeada, com o motivo escrito.

**Três divergências portão × código, todas consertadas no código.** `plat.sessoes_expurgar()` cortava a
ociosidade em `interval '24 hours'` fixo e agora usa o mesmo corte por inquilino de `plat.auth_sessao`
(G1-a1). O mínimo de senha padrão passou de 8 para 10, como a hipótese do item declara, com o piso
configurável em 8 (mínimo do NIST SP 800-63B §3.1.1.2) — `docs/LIMITES.md` regerado (G1-b1). O prefixo do
token de serviço passou de 12 para 8 caracteres (G1-d1).

**Teste de fumaça da árvore limpa.** Dois adversários seguidos esbarraram em "o ramo principal não importa".
`tests/unit/test_arvore_limpa_importa.py` faz `git archive HEAD` para um diretório temporário e importa
`app.main` num subprocesso com ambiente sintético, monta o `app.openapi()` lá dentro, e confere que todo
módulo `app.*` carregado está em `git ls-files`.

Achado de teste: `test_a1` do adversário envelhecia a sessão com `SET LOCAL ROLE NONE` seguido de rollback,
que descarta o `SET LOCAL`; sem contexto de inquilino a política `p_sessao` fazia o `UPDATE` casar 0 linhas
em silêncio, e o xfail podia estar verde pela pré-condição quebrada, não pelo defeito. Corrigida só a
plumbing (contexto e `rowcount` conferido); a afirmação continua idêntica.

Migração `20260906T1611_g1_identidade_conserto.sql`, toda com `CREATE OR REPLACE` e assinatura inalterada:
nenhum `GRANT`/`REVOKE` novo, as ACL das funções ficam as que 003/025 escreveram. `docs/openapi.json` NÃO foi
regerado neste ramo de propósito (arquivo de colisão alta entre trilhas): quem juntar roda `make openapi`
uma vez, depois do merge.
## turno 8, setembro de 2026 (item L7-03-e-cabecalhos-csp-tls: CSP com nonce por resposta, frame-ancestors por inquilino, perfil TLS)

- **Content-Security-Policy em toda resposta**, montada por `app/cabecalhos.py` (middleware mais externo):
  documento HTML leva `script-src 'self' 'nonce-<sorteado por resposta>'`, sem `'unsafe-inline'` e sem
  `'unsafe-eval'`; resposta que não é documento leva `default-src 'none'`. Medido: 196 pares (método,
  caminho) do OpenAPI mais 6 rotas fora do esquema, e nenhuma resposta sem política — inclusive 401, 404,
  405 e 422 (`tests/api/test_cabecalhos.py`).
- **Embutir a aplicação no sítio do cliente** passou a ser configuração do inquilino
  (`plat.tenant.config -> 'origens_embutidas'`, lida pela função `plat.origens_embutidas` da migração
  `20260907T2047`): origem autorizada carrega, origem fora da lista é recusada pelo navegador. Provado com
  chromium 147 em `tests/e2e/test_csp_embutir.py` (6 testes). `X-Frame-Options` foi retirado: ele não sabe
  dizer "estas origens sim".
- **`Permissions-Policy`, COOP, CORP, `Referrer-Policy` e `nosniff` numa origem só** — a aplicação. O nginx
  deixou de repeti-los nas rotas proxiadas (`add_header` acrescenta: sairiam dois) e passou a declarar o
  conjunto inteiro em `/static/`, onde ele é a origem do corpo (`tests/unit/test_cabecalhos_fonte.py`).
- **CORS por token** reusando a `restricao.referer` que o token de serviço já tinha: a origem é ecoada só
  quando está na lista do próprio token, nunca `*`.
- **Perfil TLS intermediate da Mozilla, HTTP/2 e OCSP stapling** em `deploy/nginx_tls.conf`, instalado pelo
  `install.sh` em `/etc/nginx/conf.d/plat_tls.conf`. Medido na instalação pública ANTES do item: stapling
  ausente ("no response sent").
- **`/.well-known/security.txt`** no contrato da RFC 9116, com `Expires` sempre válido.
- **19 páginas de `web/` examinadas por leitura de arquivo**: zero `<script>` em linha sem nonce e zero
  tratador de evento em atributo. Com a política nova eles não executariam e a tela abriria em branco.
- Mozilla Observatory sobre a instalação pública, 07/09/2026, **antes** deste item: **B, 75 de 100, 11 de
  12 exames** (a falta de CSP tira 25). A nota depois não foi medida — depende de o dono instalar.
- ADR: `docs/adr/20260907T2105-cabecalhos-de-seguranca-e-perfil-tls.md`. Manual: `docs/SEGURANCA.md` §9.
## turno 10, setembro de 2026 (item HARD-02-testes-de-carga-e-caos: caos de processo de TRILHA — worker e API mortos no meio do job)

Fecha a cláusula de caos de processo que faltava no HARD-02. O cenário de banco morto é do
`tests/api/adversario/test_hard02_caos_banco.py` (wt/cx4h08, na fila) e o reinício da unidade de
produção é do `tests/api/jobs/test_jobs_reinicio.py` (que exige systemd e sudo); faltava a trilha
mesma, onde não há systemd — o worker de trilha é um subprocesso da suíte e a API é um uvicorn
próprio. `tests/api/jobs/test_hard02_caos_trilha.py` (2 testes, marcados `lento`, com guarda que
recusa rodar contra o schema `plat` — os processos mortos aqui são da suíte, e a prova é sobre
ambiente de trilha) prova, contra a trilha `l02caos`:

1. **Worker de trilha morto no meio** (`kill -9` no WorkerExtra com `prova.progresso` rodando): o job
   órfão segue `rodando` e sem marcador em `plat_trabalho.marcadores` (ninguém ceifa sem worker vivo);
   o worker NOVO, levantado pela própria suíte, ceifa por heartbeat vencido (limite de 60 s, ceifa a
   cada 30 s — migração 012), devolve o job com `reinicios=1` e `tentativa` <= 2, e quem retoma é a
   identidade do worker novo (nunca a do morto); o cancelamento via `POST /api/jobs/{id}/cancelar`
   termina em `cancelado` com `reinicios=1`.
2. **API de trilha morta no meio** (`kill -9` no uvicorn com o job rodando): a chamada seguinte falha
   (conexão recusada) e, com uma API nova no ar contra a mesma base, o MESMO cookie continua
   autenticado (a sessão vive no banco, não no processo), o job segue 200 no mesmo estado
   (`pendente`/`rodando`), com `reinicios=0` e o MESMO worker (a morte da API não é devolução de job)
   e o cancelamento pela API nova termina em `cancelado`.

Duas rodadas na trilha: 2 passed em 95,1 s e 2 passed em 94,3 s
(`bash laco/roda_teste.sh tests/api/jobs/test_hard02_caos_trilha.py` com o env da trilha). A
infraestrutura é a da casa: `WorkerExtra` e `porta_livre()` de `tests/api/jobs/conftest.py` (porta
pedida ao sistema, nunca constante; processos mortos sempre por PID exato) e um `ApiTrilha` novo que
segue o mesmo padrão para o uvicorn. **Segue aberto no item**: p95 por rota (medida pós-parada da
superfície, conforme o próprio texto do item) e o caos de banco (wt/cx4h08).
## turno 8, setembro de 2026 (item L0-08-b-saml: SAML 2.0 Web SSO por inquilino, SP- e IdP-initiated)

`plat.provedor_saml` (vários por inquilino, metadado do IdP por URL, XML ou parâmetros; par de chaves do SP
gerado aqui, chave privada cifrada com PLAT_SECRET), rotas `GET /api/sso/saml/metadata` (metadado do SP
assinado, válido contra o XSD do SAML), `iniciar`, `acs`, `logout` e `slo`, mais `GET/POST/PUT/DELETE
/api/org/saml`. Biblioteca python3-saml com `strict`, assinatura de resposta E de asserção obrigatórias,
asserção cifrada opcional (exigível), SHA-1 recusado, desvio de relógio de 300 s (10 min à frente = 401),
replay barrado pelo ID da asserção até o NotOnOrAfter, logout propagado nos dois sentidos (NameID +
SessionIndex por sessão). Identidade única com o OIDC: `plat.usuario_externo_provisionar(origem, ...)`
substitui o corpo de `oidc_provisionar`. Conferido: 16 testes com IdP sintético (sem Docker: sem assinatura,
outra chave, relógio, replay, XML Signature Wrapping, NameID fora da regra Esri, cifra, SLO, IdP desligado não
afeta o login local, isolamento A->B) e 5 contra o Keycloak 26 do L0-08-a (dois clientes SAML no realm de
teste). Sem captura de tela (chromium headless quebrado nesta máquina).
## turno 8, setembro de 2026 (item L3-10-corredor-custo-minimo: rota HTTP do traçado, testes e documentos)

Fechamento do item do traçado linear sobre a execução do motor multicritério (o motor, a ponte e a conferência
bit a bit contra o trecho de referência da casa já estavam no ramo). `POST /api/multiescala/execucoes/{id}/corredor`
devolve linha + corredor + manifesto (superfície declarada, parâmetros, medidas) de forma síncrona, com teto
próprio para a geometria do corredor e ponto do usuário nunca movido (ADR `20260908T1545-corredor-sincrono-com-teto.md`).
Reprodução do portão de referência medida e em `tests/medidas/L3-10-corredor-custo-minimo.json`: superfície IGUAL
BIT A BIT à `saida/superficie.npz` da rodada oficial (27 camadas do cache + 2 rasters), rota recalculada a
Hausdorff 100,0 m da oficial (uma célula de 100 m), trecho de 382,4 km traçado em 5,8 s (motor esparso com janela
de 400 células, teto do portão 10 s), corredor de 5 % = 1.877.780 células. O corredor de 5 % gravado no arquivo
oficial está VAZIO (zero célula) — registrado como achado, não há contra o que comparar. Testes: unidade (31, na
grade pequena e contra a referência, os de referência marcados `lento`) e API na trilha (11, sobre execução
multiescala real; área de estudo retangular de propósito — num quadrado 10x10 o desvio para a faixa barata NÃO
compensa na aritmética de peso = média × comprimento e a reta é o resultado certo).
## turno 3, setembro de 2026 (item L0-09-c-xml-iso-validacao: importar metadado ISO 19139)

A exportação de metadado ISO existia desde o item `L0-09-metadado-catalogo`; agora existe o caminho de volta.

- **`POST /api/itens/{id}/metadado.xml`** recebe um metadado ISO 19139/GMD e preenche o item: título, resumo,
  descrição, palavras-chave, créditos, termos de uso, situação e extensão pelo mesmo `editar_item` do
  PUT/PATCH (versão, permissão e evento `itens/atualizar`); a linhagem volta para `dados.procedencia`; contato,
  sistema de referência, formato e extensão declarada vão para `plat.item.metadado_iso`, a mesma coluna do
  editor MGB do item irmão L0-09-b (migração idempotente e idêntica). `?aplicar=false` lê sem gravar.
- **O XSD é parecer, não porteiro.** O registro real do catálogo aberto da INDE guardado em `tests/dados/`
  (produtor IBGE, gerado por ArcGIS 10.3) tem 20 erros contra o XSD oficial — ordem de elementos e extensões
  do Perfil MGB — e mesmo assim preenche 22 campos do item. XML malformado, grande demais ou com raiz que não
  é `gmd:MD_Metadata` responde 422 com linha e coluna; erro só de XSD sai como aviso posicionado, e `?estrito=1`
  o transforma em recusa.
- **O que não tem onde ser guardado sai nomeado**: 69 caminhos do registro da INDE (telefone, endereço postal,
  catálogo de feições) vêm no relatório `nao_coube`, com caminho, linha, contagem e exemplo — nenhuma gaveta
  inventada para eles.
- **Ida e volta fechada**: exportar e reimportar não perde campo do perfil (`metadado.diferencas` vazia nos três
  itens do teste e na prova pela API, de um item para outro).
- Refutação: entidade externa nunca é resolvida (sem rede, sem DTD), bomba de entidade não expande, XML de
  50 MB é recusado pelo tamanho antes de qualquer análise, namespace errado é recusado com a raiz no texto.

## turno 3, setembro de 2026 (item L2-04-h-wfs-2-gml: WFS 2.0 com filtro FES e GML 3.2 por token)

O WFS que existia desde o item `L2-04-servicos-esri-ogc` respondia às três operações básicas com um
esquema aproximado. Agora o serviço é o que um cliente de escritório adiciona por URL:

- **GetCapabilities 2.0.0 e 1.1.0 válidos contra o XSD oficial do OGC**, com o esquema em cache local
  (`docs/xsd/cache`, perfil `wfs20` do `docs/xsd/baixar_iso19139.py`: 124 arquivos, 1,9 MB, sha256 no
  manifesto) — a validação nunca toca a rede. `owslib` lê o documento e enxerga o tipo de feição.
- **DescribeFeatureType em XSD gerado das colunas**, importando o GML 3.2.1 oficial; o mesmo esquema
  valida, no teste, cada feição devolvida pelo GetFeature (seis tipos de geometria, Multi* inclusas).
- **Filtro FES 2.0** (`app/consulta/fes.py`): comparação, lógica, espacial (BBOX/Intersects/Within/
  DWithin) e temporal, traduzidos para a MESMA árvore do CQL2 e compilados pelo MESMO
  `cql2.compilar` — nenhum segundo gerador de SQL. XML lido por `defusedxml` (DTD, entidade e
  referência externa recusadas), com teto de bytes, de nós e de profundidade.
- **GetFeature** com `typeNames`, `count`/`startIndex`, `bbox`, `srsName`, `propertyName`, `sortBy`,
  `resultType=hits` e `resourceId`; **GetPropertyValue**; consulta armazenada **GetFeatureById**.
- **Transaction (Insert/Update/Delete)** pela porta ÚNICA de escrita da casa (`aplicar_edicoes`, item
  L2-03-a), com o parâmetro novo `origem` marcando `"wfs"` no evento de domínio.
- **Ordem dos eixos** resolvida num lugar só: forma de autoridade (`urn:ogc:def:crs:EPSG::4326`) é
  latitude, longitude; forma curta e CRS84 são longitude, latitude; geometria de filtro sem
  `srsName` usa o CRS padrão publicado — sem essa última regra o `-spat` do GDAL devolvia zero feição.

Medido (`tests/medidas/L2-04-h-wfs-2-gml.json`): 1.000 feições em GML 3.2 reabertas pelo GDAL com
geometria válida; o driver WFS do GDAL 3.8.4 lê o serviço vivo e conta 250, igual ao banco; `-spat`
traz 60 e `-where "area > 200"` traz 50, ambos traduzidos para FES pelo próprio driver; `ogr2ogr`
exporta as 250 para GeoPackage. 57 testes do item verdes. **Não medido:** QGIS (não instalado nesta
máquina) e AGOL/ArcGIS Pro (D20).

De quebra, o que a junção da família L2-04 tinha deixado para trás: `docs/openapi.json` regerado (19
rotas de serviço que não estavam lá), casos de varredura cruzada e eventos declarados para todas
elas, `docs/LIMITES.md` regerado com os limites da edição transacional e três linhas longas de
`make lint` herdadas dos ramos irmãos.

## turno 48, setembro de 2026 (item L2-02-b-classificacao-servidor: reentrega por junção do wt/cx202c)

- O item estava **refutado** por "artefato ausente em master" (auditoria HARD-03 de 07/09) — causa de
  integração: a família catalogo-visual (L2-02-b classificação, L2-02-c editor/rampas, L2-02-e símbolos/sprites/glifos)
  vivia só no ramo `wt/cx202c`. Este ramo é **master `61089697` + merge do `wt/cx202c`** (bdb104d7), com a junção
  concertada e provada na árvore junta (trilha `il202bclas`, schema `plat_til202bclas`, porta 8653).
- Concertos de junção, todos com commit próprio: `docs/openapi.json` e `docs/LIMITES.md` regenerados (as rotas de
  estilos/símbolos/mapas/tiles não estavam no contrato publicado); contagem de blocos `location` do modelo nginx passa a
  ignorar comentário (o bloco de repasse opcional de tiles está documentado em comentário); regra 3 do vendor estendida
  ao texto de licença `<nome>-<versão>.LICENSE.txt` (portão do L2-02-c exige a licença ao lado das rampas) com origem
  https do tarball npm; ordenação de imports de `app/main.py`.
- Verde na árvore junta: portão do L2-02-b (`tests/api/catalogo/test_classes_rota.py` +
  `tests/unit/test_classificacao.py`, 65), suítes de símbolos/estilos do L2-02-c e L2-02-e (79), coerência
  (`test_cruzado`/`test_eventos`/`test_docs`/`test_privilegios_declarados`/`test_instalador`/`test_vendor`/
  `test_limites_doc`, 255 + 1 skip), `tests/adversario` (1 xfail esperado), `make lint`, `make sem-marcador`.

## turno 4, setembro de 2026 (item L2-02-c-editor-simbologia-vetor: editor de simbologia no visualizador)

- **Editor de simbologia** (`web/js/mapa/estilo_editor.js`, painel `#painel-estilo` na tela `/mapa`): símbolo
  único (cor, contorno, tamanho, ícone do sprite, tracejado, seta, padrão de preenchimento), por categoria (valores
  do servidor, cor/ícone por valor, ordem, rampa qualitativa, "outros" para o que passa de 200), por classe de cor e de
  tamanho (método e n do L2-02-b, rampas ColorBrewer sequenciais/divergentes com inversão), proporcional, mapa de
  calor, agrupamento (clusters no tile), efeitos (sombra, brilho; mistura registrada), faixa de escala por camada e por
  classe; pré-visualização ao vivo pela mesma função que grava (`POST /api/estilos/compilar`); desfazer/refazer;
  exportar/importar JSON; salvar como item `estilo` ligado à camada (`camada_id` → `estilo_de_camada`).
- **Visualizador** desenha a camada com o estilo salvo mais recente (`/api/mapa/camadas`), com sprite e glifos do
  inquilino; `tilejson?agrupar=<raio>` serve clusters pela função `t_<hex>_ag` (migração
  `20260907T2110_agrupamento_tile.sql`, `plat.camada_agrupar`).
- Esquema `estilo-v1` estendido só com campos opcionais (migração `20260907T2100_estilo_editor.sql`); compilador com
  outros, classes de tamanho, ícone, tracejado, padrão, seta, efeitos e escala; ColorBrewer 1.7.0 no vendor com licença.
  ADR `docs/adr/20260907T2130-editor-de-simbologia.md`; paridade contra "Apply styles" em docs/PARIDADE.md.
## turno 4, setembro de 2026 (item L2-05-f-rede-isocrona-rota-ferramentas: ferramentas de rede com resultado em camada)

- **Seis ferramentas de rede** (`app/ferramentas/rede.py`), no mesmo registro do L2-05-a e no mesmo formulário de
  `/analise`: `area_de_servico` (isócrona por origem ou dissolvida), `rota_paradas` (ordem de fid ou otimizada),
  `matriz_od` (N×M, teto declarado 1.000×1.000), `mais_proximas` (K por tempo), `conectar_a_rede` (snap) e
  `localizar_alocar` (cobertura máxima por heurística gulosa declarada).
- **O cálculo continua no serviço do L2-11-c**: as ferramentas chamam `app/rede/osrm.py` e `app/rede/isocrona.py`,
  não um segundo cliente. A isócrona de 30 min de um ponto sai igual à de `/api/isocrona` (mesmo polígono,
  diferença simétrica de área 0,0 — `test_isocrona_de_30_min_e_a_mesma_do_servico_l2_11_c`).
- **Medidas** (`tests/medidas/L2-05-f-rede-isocrona-rota-ferramentas.json`): matriz 100×100 = 10.000 pares em
  **3,96 s** de execução inteira (matriz + escrita da camada + item), 10.000 de 10.000 pares com rota, com carga
  de 1 min em 7,68; rota de 10 paradas: **3.583,9 s** na ordem original contra **3.521,6 s** na ordem otimizada.
- **Procedência de rede**: toda camada de saída traz no `metodo` a versão do grafo OSM (arquivo, data e sha256 do
  recorte), agora com fonte única em `app.rede.osrm.PROVENIENCIA`.
- **Três defeitos corrigidos no que já existia**: a isócrona de 30 min estourava o tamanho de URL do cliente (a
  grade passa do `--max-table-size` do OSRM) e agora é partida em blocos; `ST_Extent` de camada com uma feição só
  degenerava em ponto e quebrava a publicação do item; caixa degenerada é recusada pelo CHECK de `plat.item`, e o
  item passa a ficar sem extent em vez de ganhar caixa inventada.
- **Paridade escrita** contra "Use proximity" do Map Viewer 11.4 (Generate Travel Areas, Find Nearest, Plan
  Routes) e a caixa Network Analyst do Pro, em `docs/PARIDADE.md`, com o que é parcial e o que está fora.

## turno 4, setembro de 2026 (item L2-05-a-catalogo-ferramentas-gpserver: registro de ferramentas e GPServer)

- **Registro `@ferramenta`** (`app/ferramentas/registro.py`): manifesto tipado no vocabulário GP da Esri, validado
  na importação (parâmetro sem tipo = erro de build), JSON Schema para o formulário e descritor GPServer.
- **Executor com proveniência** (`app/ferramentas/executor.py`): mesmo caminho como job (`ferramentas.executar`)
  e em processo abaixo do custo declarado; resultado = item `camada_vetorial` com `procedencia.ferramenta`
  (ferramenta, versão, parâmetros, entradas com uuid + versão + sha256 de conteúdo, data, autor) e relação
  `derivado_de`; cancelamento apaga a tabela. Ferramenta de exemplo `buffer` (geodésico, dissolver opcional).
- **API própria** `/api/ferramentas`, `/api/ferramentas/{nome}`, `/api/ferramentas/{nome}/executar`; tela `/analise`
  com formulário gerado do manifesto; ficha do item mostra a proveniência.
- **GPServer compatível** `/rest/services/{ferramenta}/GPServer/{tarefa}` (execute, submitJob, jobs/{id},
  results/{param}, cancel; `token=`; erro no formato Esri com código HTTP real).
- Migração `20260907T2005_ferramentas.sql` (relação `derivado_de`, evento `analises/executar`); limites em
  `app/limites.py` (seção ferramentas). ADR `docs/adr/20260907T2010-ferramentas-gpserver.md`.
## turno 8, setembro de 2026 (item L2-09-b-cena-extrusao-slides: documento de cena 3D, extrusão por atributo e slides)

O tipo de item `cena`, que existia desde a migração 011 com envelope vazio, ganhou esquema próprio
(`db/migracoes/20260908T0601_cena_esquema.sql`): câmera, terreno com exagero, iluminação por data e
hora, atmosfera, camadas com extrusão por atributo e slides. Nenhuma tabela nova e nenhuma rota nova de
documento — a cena é criada, versionada e publicada pelas rotas genéricas de `/api/itens`, e o esquema
continua na versão 1 porque todo documento que já existia (corpo vazio) segue válido. O que o JSON
Schema não expressa (id repetido, slide que cita camada ausente, extrusão sem altura, base acima do
topo) entra por `app/cena/documento.py`, chamado da MESMA porta que valida o grafo dos construtores.

A tela `/cena` usa o mesmo MapLibre do visualizador 2D — `fill-extrusion` para volume, `setTerrain`
para relevo, `setSky` e `setLight` para atmosfera e luz —, sem nenhuma segunda biblioteca 3D. Altura
vem de um atributo, com escala explícita, e é presa em 0 quando o valor é nulo, ausente ou negativo
(sem isso o MapLibre desenha caixa invertida em silêncio). Slide é vista salva no corpo do documento:
nome, câmera, camadas visíveis, hora e miniatura JPEG feita do próprio canvas; restaurar usa `jumpTo`,
não `flyTo`, para a vista voltar igual.

A posição do Sol é calculada no servidor (`app/cena/sol.py`, algoritmo do NOAA) e exposta em
`GET /api/cena/sol`, com a luz já no formato do estilo. A conferência do teste não é contra a própria
implementação: é contra a fórmula do Astronomical Almanac, escrita dentro do teste, em três datas e
horas, mais o invariante do ponto subsolar. Decisão de desenho em
`docs/adr/20260908T0620-documento-de-cena-3d.md`.

## turno 7, setembro de 2026 (item L7-19-segredos-e-certificados: os 5 segredos fora do .env, rotação com 0 erro 5xx medido pelo k6)
## turno 3, setembro de 2026 (item L0-02-g-checagem-privilegio-papel-id: quem concede papel tem de ter o papel)

Fecha um escalonamento de privilégio real na tela de usuários. O papel personalizado RESTRINGE o teto do perfil
(`plat.privilegios_de` é a interseção entre os dois), mas `POST /api/usuarios` e `PUT /api/usuarios/{id}`
conferiam apenas se o papel CABIA no perfil do alvo, nunca se o ATOR tinha o que estava concedendo. Um
administrador restrito por papel podia atribuir a outro um papel mais amplo que o seu, ou zerar o `papel_id` de
alguém — inclusive o próprio — e recuperar o teto inteiro do perfil, ou ainda promover um editor a administrador
sem papel, e fazer qualquer um dos três em massa pelo lote. `_nao_conceder_alem_do_proprio` (ADR 0016) recusa
com 403 `privilegio_proprio_insuficiente` e devolve no `detalhe` a lista do que sobraria. Vale para perfil e
papel juntos, porque promover a admin com papel nulo concede exatamente o mesmo conjunto.

A refutação exigida foi rodada na forma completa, não em um caso: para **cada um dos 47 privilégios** do
vocabulário, o papel do ator passa a ser "todos menos ele" e o papel oferecido passa a ser "todos" — um
privilégio a mais. **94 chamadas (POST e PUT), 94 respostas 403, nenhuma 2xx**; 92 pela conferência nova
(`privilegio_proprio_insuficiente`) e 2 pelo portão de privilégio (`sem_privilegio`), que são exatamente os
casos em que o privilégio retirado do ator era `membros.gerir` ou `membros.papel`. Retirando as duas chamadas
da conferência, 7 dos 10 testes do arquivo reprovam — a prova de que mordem.

Varredura de privilégio rota por rota, em duas camadas, sobre as **138 rotas** de `docs/openapi.json`. A
estática lê o fecho da dependência `autenticado(...)` de cada rota viva e compara com o declarado: **41 rotas**
cobram na dependência exatamente o privilégio nomeado que declaram, **72** declaram valor especial ou
alternativa e cobram no corpo, **8** cobram na dependência um privilégio que a declaração não menciona. A
dinâmica prova as 41 com chamada real: um administrador de inquilino descartável recebe um papel com todos os
privilégios menos um e **as 41 rotas respondem 403 `sem_privilegio` com `exigido` igual ao declarado**; com o
papel completo, nenhuma delas responde `sem_privilegio` (controle positivo). Fronteira declarada: **31 rotas**
de privilégio alternativo cobrado depois de carregar o recurso ficam fora do alcance deste item — a medida
`rotas_alternativas_nao_provadas` guarda o número, e as duas de `/api/usuarios` que o item alcança foram
provadas.

As 8 rotas de declaração incompleta (`/api/tokens/{id}` e `/renovar` cobrando `tokens.gerar` sem declarar,
`/api/acervo/{fonte_id}/adicionar` cobrando `conteudo.criar` numa declaração que promete alternativa,
`/api/itens/{id}/miniatura/gerar` e `/api/lixeira/esvaziar` cobrando `jobs.executar`, e `POST /api/logout` sem
dependência) **apertam** o acesso em vez de afrouxá-lo: exigem mais do que a documentação promete, então não são
falha de segurança, e sim documentação errada. O conserto é do dono de cada rota. A lista está CONGELADA em
`DIVERGENCIAS_CONHECIDAS` no teste: divergência nova reprova.

De quebra, um defeito que impedia a homologação inteira: `CursorSchemaAmbiente` não sobrescrevia `executemany`,
então o INSERT em lote de `plat.papel_privilegio` ia ao servidor com o literal `plat.` e todo ambiente fora do
schema de produção respondia 403 "operação fora do inquilino da sessão" nas rotas de papel. Corrigido junto com
`mogrify`, com guarda em `tests/unit/test_schema_ambiente_metodos.py` que varre `app/` atrás de método de cursor
usado sem sobrescrita. O cursor de `conexao_plat_app` passou a ser o mesmo, senão nenhum teste que escreve
`plat.` na mão roda fora de produção.

## turno 3, setembro de 2026 (item L1-01-b-validacao-e-isolamento-da-entrada: validação de raster)

Colheita da bancada `wt/segredos` (interrompida por limite de cota em 06/09) mais o conserto do que a
medição honesta achou nela. `PLAT_DSN`, `PLAT_GARAGE_ADMIN_TOKEN` e `PLAT_SECRET_ANTERIOR` saíram do
`.env` para `/etc/plat/segredos` (root 0600) entregues por `LoadCredential=` do systemd — o `.env` fica
só com configuração, e o Makefile injeta os segredos no pytest (a falta de `PLAT_DSN` na injeção tinha
deixado a suíte vermelha na coleta desde 06/09 à noite). `scripts/plat segredo rotacionar <nome>`
rotaciona os 5 segredos: PLAT_SECRET com dupla-chave (o valor antigo vira `PLAT_SECRET_ANTERIOR` por 24
h, sessões sobrevivem), PLAT_DSN e PLAT_DSN_WORKER com `ALTER ROLE` + reinício das consumidoras,
PLAT_GARAGE_ADMIN_TOKEN com restart do Garage + API, e a chave S3 de um inquilino sem reiniciar nada.
Em todos, o valor antigo deixa de autenticar (prova por `psycopg2.connect` com a senha velha depois da
rotação). A cláusula "0 erro 5xx durante a rotação" é medida pelo **k6** (v2.2.0,
`scripts/k6_saude_5xx.js`, martelo externo ao processo medido): 0 respostas 5xx em 276-762 requisições
por rotação (`tests/medidas/L7-19.json`). Chegar ao zero exigiu trocar o mecanismo depois de duas
medições ruins: "restart em cadeia" deixou 57 respostas 500 na janela entre o `ALTER ROLE` e o restart
da segunda unidade, e "parar tudo antes" deixou 1.334, porque com ativação por soquete a própria
conexão do cliente religa o serviço com a credencial velha (e `mask --runtime` não impede a religação
de unidade estática, medido em spike). O mecanismo final é uma janela `trust` de segundos no pg_hba
(só a role, só 127.0.0.1, linha marcada, removida por `finally`): velho e novo autenticam durante a
troca, e a senha velha morre quando a janela fecha. A API passa a subir por ativação por soquete
(`deploy/plat-api.socket`, uvicorn `--fd 3` com 2 workers — spike medido: conexão durante o stop
espera ~1 s e recebe 200, nunca refused/502). O adversário independente refutou a primeira versão e os achados que eram do item viraram conserto
neste mesmo turno: a janela trust abre dentro do `try` (linha nunca fica para trás no pg_hba, checado a
cada prova), a rotação de PLAT_SECRET reinicia também o worker (ele carrega a chave uma vez na subida e
decifra dentro de jobs), e o ANTERIOR expira de verdade — timer `plat-segredo-expira.timer` esvazia o
arquivo e reinicia API e worker na virada das 24 h (janela efetiva 24 h-24 h 59 min). Os achados que são
contaminação do ambiente ANTERIOR ao item (segredos reais semeados no journal por comandos de outras
operações; `.env` de worktrees de trilha com valores reais, um deles modo 664; segredos em
`/proc/<pid>/environ` de processos de trilha) ficaram registrados em `refutacao.json` e viraram itens
próprios do backlog com dono nomeado — o desenho do produto em si saiu limpo: unidades plat-* só veem os
segredos por `LoadCredential=`, repositório e histórico git com 0 ocorrências, `.env` raiz sem segredo.
Runbook em `docs/RUNBOOKS/segredos.md` (procedimento por segredo, janela trust declarada, ressalva do
garage.toml do daemon, que é da frente plataforma/pipeline e o produto nunca lê em operação).
## turno 3, setembro de 2026 (item L5-11-expressoes-no-navegador: perfis de uso, feição e geometria)

- A linguagem de expressão ganhou os sete PERFIS de uso (`app/expressao/perfis.py`,
  `web/js/expressao/perfis.js`): popup, rótulo, cálculo de formulário, visibilidade, restrição,
  indicador de painel e título dinâmico. Cada perfil declara os tipos de retorno que aceita e o
  orçamento de tempo (50 ms no navegador, 500 ms no servidor); o contexto é montado só da feição
  recebida (`$feicao`, `$geometria` e um `$campo` por atributo com nome de identificador).
- Seis funções novas nos dois avaliadores (43 → 49): `Atributo`, `Geometria`, `Area`,
  `Comprimento`, `Distancia` e `Dentro`. Geometria é GeoJSON, o modelo é a esfera de raio autálico
  6.371.008,8 m e o resultado métrico é arredondado a 6 casas para servidor e navegador devolverem
  o mesmo número — erro de modelo de até 0,5 %, sem valor de medição legal de área.
- Vetores compartilhados: 309 → 339 em `tests/expressoes/vetores.json`, mais 11 vetores de erro de
  geometria em `tests/expressoes/vetores_geometria_erros.json` e 57 vetores de perfil em
  `tests/expressoes/vetores_perfis.json`, todos rodados em Python e em Node.
- `MANUAL.md` seção 25, gerada de `TABELA_FUNCOES`/`PERFIS` por `docs/gerar_manual_expressao.py`,
  com uma linha e um exemplo por função. `docs/EXPRESSAO.md` ganhou a subseção de feição/geometria
  e a seção 12 (perfis). ADR `docs/adr/20260908T1331-expressoes-no-navegador.md`.
- Nenhuma tela chama os perfis ainda: o que entrou é a biblioteca, provada nos dois runtimes.
## turno 3, setembro de 2026 (item L4-07-fluxo-de-potencia: fluxo de potência do alimentador)

- Fluxo de potência trifásico desequilibrado do alimentador no OpenDSS, sobre o MESMO modelo em memória
  que os exportadores usam: `POST /api/rede/{id}/subrede/{nome}/fluxo` analisa e grava,
  `GET .../fluxo` devolve a tabela por elemento e `GET .../fluxo/camada?grandeza=` devolve a camada de
  tensão, corrente ou carregamento para o mapa. Tela nova em `/redes/fluxo`.
- Job `redes.analisar_alimentador`: um alimentador de cada vez, o que falhar entra em `recusados` sem
  derrubar o lote, e a agregação EXCLUI quem não convergiu, nomeando-o.
- Duas tabelas novas: `plat.rede_fluxo_execucao` (parâmetros, versão da topologia, convergência, ponto
  crítico, energia) e `plat.rede_fluxo_resultado` (barra e fase, trecho, transformador, no ponto crítico).
- O motor OpenDSS passou a rodar em PROCESSO PRÓPRIO: medido que ele derruba o interpretador inteiro
  quando usado fora da thread principal deste processo (ADR 20260908T1255).
- Consertos achados ao medir: o alvo do `BatchEdit` do OpenDSS é expressão regular, não curinga de
  arquivo (`Load.u*` casava com toda carga, geração inclusive), e o `Compile` troca o diretório de
  trabalho do processo.
- Barra com tensão fora de 0,5 a 1,5 por unidade agora é contada e avisada: é tensão de BASE errada, não
  estado de rede.
## turno 3, setembro de 2026 (item L7-01-d-instalador-extensoes: lista única de extensões)

O `install.sh` criava duas das quatro extensões que o schema exige. `pg_trgm` e `unaccent` tinham
entrado com o geocodificador (migração 045) declaradas como "já instaladas na casa" — verdade nesta
máquina, falso numa instalação nova. Sem `unaccent` a configuração de busca `plat.pt_sem_acento` não
nasce, a tabela `item` não é criada e o ensaio de restauração do L0-06-c acusa "tabela ausente na cópia
restaurada"; foi assim que o defeito apareceu, no primeiro ensaio de verdade.

A lista passa a morar em `db/extensoes.txt`, no mesmo formato de `deploy/pacotes_apt.txt`. `db/extensoes.sh`
traz `plat_extensoes_lista` e `plat_extensoes_garantir`, que cria o que falta e **confere em
`pg_extension`**, saindo diferente de zero com o nome do que não nasceu. Três consumidores leem o mesmo
arquivo: o `install.sh` (seção "b"), o `laco/trilha_ambiente.sh` (seção "0", nova) e o ensaio de
restauração, por `app.backup.drill.extensoes_do_ensaio()` — a tupla literal `EXTENSOES_DO_ENSAIO` deixa
de existir.

Medido em base descartável criada para o teste: base só com PostGIS termina com as quatro extensões e o
dump do schema restaura nela sem passo manual, com a tabela `item` e a configuração `pt_sem_acento`
presentes; a mesma restauração numa base sem `unaccent` não cria a tabela `item`. Ver
`tests/api/test_instalador_extensoes_base_nova.py`, `tests/unit/test_extensoes_lista.py`, o ADR
`docs/adr/20260907T2248-lista-unica-de-extensoes.md` e `tests/medidas/L7-01-d-instalador-extensoes.json`.
O `install.sh` inteiro segue sem teste que o rode: ele instala pacotes e escreve unidades do systemd.
## turno 3, setembro de 2026 (item L2-09-c-modelos-gltf-ifc-3dtiles: modelos 3D no mapa)

Modelo de projeto posicionado no globo, sem nenhuma biblioteca AGPL. Três caminhos, um pacote
(`app/modelos3d/`): **glTF binário** posicionado por longitude, latitude, altura, rotação e escala,
desenhado por camada personalizada do MapLibre com three.js 0.185.1 (MIT, vendorizado); **IFC** lido em
Python puro — elementos com identificador global, tipo, pavimento e propriedades em
`plat.modelo3d_elemento`, geometria convertida de malha tesselada e de sólido de extrusão, e o que não
converte sai CONTADO em `elementos_sem_forma` (arquivo aberto da buildingSMART: 13 elementos, 11 com
forma); e **OGC 3D Tiles 1.1** gerado do glTF com divisão em quadrantes, servido por URI relativa a
partir de `GET /api/modelos/{id}/3dtiles/{caminho}`.

Oito rotas novas em `/api/modelos`, duas tarefas de fila (`modelo3d.converter`, `modelo3d.tileset`), duas
tabelas com RLS por inquilino, e o bloco `modelos` acrescentado ao esquema do documento de cena. Modelo
com recurso externo (textura fora do arquivo) é recusado nos dois lados — servidor e navegador.

Medido: caixa desenhada pelo navegador contra a calculada pelo servidor, **0,097 m** de erro (folga do
portão: 0,5 m); validador oficial `3d-tiles-validator` 0.6.1 com **0 erros e 0 avisos** nas árvores de 1 e
de 8 tiles, e reprovando o controle negativo; **58,7 quadros/s** com o modelo na tela (carga 9,5, sem
GPU); IFC sintético de 50 MB com 62.038 elementos em 19,4 s e pico de 679 MB, dentro do teto de 1.024 MB
do trabalhador. `make check` ganhou `make sem-agpl`. i3s fica de fora, declarado (sem produtor aberto na
pilha); consumo do tileset pelo cliente pesado do concorrente segue pendente da decisão D20.

## turno 3, setembro de 2026 (item L3-19-multiescala: grades aninhadas do motor multicritério)

Construído do zero neste turno (RESGATE da sessão executora derrubada por cota só tinha a migração,
`app/multiescala/{crs,motor}.py` ainda sem rota nenhuma). Duas execuções ligadas: `POST
/api/multiescala/conjuntos/{id}/macro` gera a grade grosseira sobre a área de estudo inteira e roda a
combinação; `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina SÓ dentro das células macro
aprovadas (aritmético — a query de geração junta a região aprovada ANTES de expandir as sub-células, nunca
gera tudo para descartar depois) e roda a mesma combinação nela. `GET /api/multiescala/execucoes/{id}`
devolve o relatório por fator com `escala`/`escala_grosseira`/`razao_escala`, calculado pelo motor a partir
de `resolucao_fonte_m` (declarada no fator) x `resolucao_grade_m` (da execução) — o cliente nunca envia
esse campo. CRUD completo: `/conjuntos`, `/fatores`, `/fatores/{id}/amostras` (carga em lote),
`/execucoes`; `DELETE` de conjunto e fator (cascata pelas FKs da migração), acrescentados neste turno para
a varredura cruzada ter como limpar o que cria. Escopo de token novo `multiescala:usar`
(`app/auth/escopos.py`). ADR `docs/adr/20260906T1640-grades-aninhadas-multiescala.md`.

Um defeito de FRAMEWORK achado e corrigido, fora do arquivo deste item mas bloqueando-o:
`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` em `execute` e
`callproc`, mas não em `executemany` (psycopg2 implementa em C e não chama `execute` de volta) —
`POST /api/multiescala/fatores/{id}/amostras` falhava com `permission denied for schema plat` em qualquer
trilha. A MESMA lacuna já quebrava `POST /api/papeis` (não deste item), convertida por `erro_do_banco` num
403 "operação fora do inquilino da sessão" que parecia RLS cruzada e não era — reproduzido e confirmado
antes de mexer. Corrigido na classe (um método a mais, mesmo corpo de `execute`), vale para as duas rotas.

Um defeito do próprio teste (não do motor) achado rodando de verdade: uma área de estudo desenhada só um
pouco maior que a resolução da grade (~1,35-1,47 km sobre 1 km) produz uma célula-fatia cujo CENTRO
nominal (usado para achar o bloco de dado) cai FORA da extensão real da amostra — 2 das 4 células macro
ficavam sem nota, não por bug, porque nenhuma amostra alcançava o bloco que aquela célula ia procurar.
Corrigido aumentando a área de teste para 1.900 x 1.900 m (documentado no ADR, decisão B, para o próximo
teste desta família não tropeçar na mesma coisa).

Medido de verdade (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L3-19-multiescala.json`), 10/10 testes passam
duas vezes seguidas: grade macro de 1 km sobre estudo de 1.900x1.900 m dá 4 células, top_pct 50% aprova 2;
grade micro de 100 m (k=10) gera exatamente 200 células (2 aprovadas × 10²) contra 400 possíveis (4×10²) —
economia de 50,0%; o mesmo fator (1.000 m de escala nativa) sai `própria` na grade de 1 km e `grosseira`
na grade de 100 m da MESMA execução ligada, sem o cliente declarar nada de diferente — é a refutação do
item. `tests/api/multiescala/test_multiescala.py`: 10/10.

**Fora do portão deste turno, registrado no ADR**: `docs/openapi.json` comitado não inclui
`/api/multiescala/*` (regeneração é pendência do gerente após os merges); os 11 casos da varredura cruzada
já estão em `tests/api/cruzado_casos.py` (conferidos à mão contra o app rodando — todas as 11 rotas
recusam ou isolam o cross-tenant corretamente) e passam a valer em `test_cobertura_100_por_cento`/
`test_rota_nao_cruza` assim que `make openapi` rodar contra a árvore juntada. `L3-01-b-unidades`
(dependência declarada) segue PARCIAL num ramo não juntado (`wt/amc`); este item não depende dele em
código (CRS resolvido de forma própria em `app/multiescala/crs.py`), só na hipótese conceitual.
## turno 5, setembro de 2026 (item L5-01-a-layout-paginas: páginas e layout do app)

Sobre o editor de arrasto do L5-08: paleta nova (`web/js/editor/paleta_paginas.js`) com `pagina` (tela cheia
× rolável; `caminho`/`titulo`/`ordem`/`oculta`/`inicial`), `cabecalho`, `rodape`, `menu`, os widgets de
layout do Experience Builder (`linha`, `coluna`, `grade`, `acordeao`, `painel_fixo`, `painel_lateral`) e
`janela` (`modal`/`ancorada`) + `secao_vistas`/`vista`. Executor novo (`web/js/executor/{executor,paginas}.js`
+ tela `/executar?item=<id>&pagina=<caminho>`, `app/paginas.py`) que renderiza o MESMO documento como app de
verdade: nav entre páginas por `history.pushState`, `<dialog>` nativo para janela modal, painel lateral que
recolhe sem `display:none`, grade em CSS Grid `fr`. `web/js/editor/tela.js` escolhe a paleta pelo `tipo` do
item (`app` → paleta de páginas; o resto continua com a paleta comum do L5-08) — única mudança num arquivo
que outro item também toca.

Medido (`tests/medidas/L5-01-a-layout-paginas.json`, e2e `tests/e2e/test_layout_paginas.py`): app de 2
páginas (Central tela-cheia com mapa, Detalhes rolável com painel lateral/grade/janela) montado só por
arrasto (2.245,1 ms); menu navega e a URL muda por página, F5 reabre na página certa; painel lateral
recolhe/expande; grade mantém a razão 8:4 entre dois filhos em 1200 px (2,016) e 600 px (2,033) — diferença
0,017; janela modal abre pelo botão e fecha por Esc (`<dialog>` nativo). Refutação do adversário: 6 níveis
alternando linha/coluna, com irmão ao lado do 1º nível, em 3 larguras de viewport (1280/800/320) — 0 px de
estouro horizontal e nenhum nível com largura, altura, `display` ou `visibility` zerados (a correção que fez
isso passar foi `min-width:0`/`min-height:0` em todo item flexível, ADR
`20260907T1355-paginas-e-layout-do-app`). Achado corrigido no caminho: `drag_and_drop` sobre o SELETOR do
contêiner-alvo mira o CENTRO da caixa — quando o contêiner já tem um filho de largura 12/12, o centro cai
sobre o filho e o `drop` do HTML5 é entregue a ele, não ao contêiner (o novo nó entra um nível mais fundo do
que o pedido); o teste agora solta sempre no FUNDO do contêiner, como o e2e do L5-08 já fazia na raiz.
Paridade contra "Add and manage pages" e "Layout widgets" (doc EXB) em `docs/PARIDADE.md`.
## turno 4, setembro de 2026 (item L5-09-desfazer-refazer-rascunho: desfazer/refazer, autosave e diferença entre versões)

Três módulos novos em `web/js/editor/`: `desfazer.js` (pilha de JSON Patch RFC 6902 com direto+inverso por
passo, agrupamento de operação contínua por `grupo`), `rascunho.js` (autosave de servidor via
`PATCH ?rotulo=rascunho`, novo parâmetro em `app/catalogo/rotas_itens.py::editar_parcial`, + cópia local em
`localStorage` gravada a cada mudança, não só no ciclo do autosave) e `diferenca.js` (diferença entre duas
versões por ID de nó — nunca por posição, ao contrário do RFC 6902 posicional). `tela.js` ganhou os botões
Desfazer/Refazer (com atalho Ctrl+Z/Ctrl+Shift+Z), o aviso de rascunho recuperado ao reabrir a tela, o
comparador de versões, e a reação ao 409 de conflito de versão (que já existia desde o L5-05): mostra a
diferença contra a versão do servidor e exige clique explícito antes de sobrescrever ou descartar — nunca
silenciosamente.

Medido (`tests/medidas/L5-09-desfazer-refazer-rascunho.json`): 50 operações reais (inserir, mover,
redimensionar, definirPropriedade, remover) desfeitas e refeitas devolvem o documento inicial/final com o
mesmo hash sha256 da forma canônica, em 5 sementes determinísticas
(`tests/unit/test_desfazer_refazer.py`, roda por Node via `tests/unit/apoio_editor_desfazer.mjs`); um grupo
sintético de 5 redimensionamentos contínuos vira 1 passo de histórico (2 no total, com o inserir). e2e
(`tests/e2e/test_desfazer_refazer_rascunho.py`, 5 testes verdes): queda simulada da API (route.abort() em
todo PATCH) deixa a cópia local `pendente: true`; recarregar mostra "rascunho não gravado encontrado" e
"Usar rascunho recuperado" repõe o nó que nunca chegou ao servidor; diferença entre v3 e v7 classifica 1 nó
removido, 1 alterado e 1 adicionado, cada um no balde certo; autosave de rascunho grava versão nova rotulada
'rascunho' sem tocar `versao_publicada` nem o conteúdo da versão publicada (comparado byte a byte antes e
depois); duas abas editando o mesmo item — a segunda a salvar recebe 409 com a diferença visível e só grava
depois de um clique explícito, nunca perde a edição da aba silenciosamente. Regressão zero em
`tests/e2e/test_editor_arrasto.py` (L5-08, dependência) e nos 5 testes de `tests/api/catalogo/test_versoes.py`
(mais o novo `test_patch_rotulo_rascunho_nao_publica`).

Limitação registrada no ADR (20260907T1522): o link de compartilhamento público
(`app/catalogo/rotas_compartilhamento.py`, herdado, fora do escopo) mostra o `dados` corrente do item, não
uma vista presa a `versao_publicada` — não existe ainda um "renderizador do publicado" separado do editor.
O que este item garante é o ponteiro de publicação e o conteúdo por trás dele, que não se mexem sozinhos.

## turno 4, setembro de 2026 (item L5-08-editor-arrasto: primitivas de edição compartilhadas pelos construtores)

Editor de arrasto próprio em `web/js/editor/` (5 módulos, 43.771 bytes medidos; 0 byte de biblioteca de
arrasto — `web/vendor/VERSOES.txt` segue sem SortableJS, dnd-kit ou GridStack) e tela `/construtor?item=<id>`
sobre o documento do L5-05. Paleta→tela e tela→tela por HTML5 Drag and Drop; alça de largura por Pointer
Events com `setPointerCapture`; árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e
menu "mover para" para quem só tem toque. Largura sempre em COLUNAS da grade de 12, nunca em pixel.

Medido (`tests/medidas/L5-08-editor-arrasto.json`, e2e `tests/e2e/test_editor_arrasto.py` contra a base da
trilha): o MESMO layout de 5 componentes montado só por arrasto (787,5 ms) e só por teclado e menus
(134,0 ms) grava dois documentos idênticos — diferença 0 depois de trocar cada ULID por `n1..nN` na ordem de
profundidade (o ULID é aleatório por construção, D2). Redimensionar por arrasto levou o mapa de 8 para 4
colunas nos dois caminhos; `"px"` não aparece no documento gravado. A árvore reflete o aninhamento
(aria-level 1/2/2/1/1). O painel recusa zoom 99 num campo `maximum: 22`: mensagem no campo, `aria-invalid`,
e o documento salvo depois continua com 12. Refutação do adversário no mesmo arquivo: soltar um contêiner
dentro de um descendente dele é recusado com motivo ("dentro de si"), soltar fora da tela não muda nada, o
menu de mover não oferece destino dentro do próprio nó, e o layout inteiro se monta só por toque no viewport
Pixel 7 (onde o HTML5 Drag and Drop não dispara). 0 erro de console em todos os caminhos.

Achado de ambiente: esta é a primeira tela que grava por `fetch` sob cookie a partir do navegador, e por
isso a primeira a bater no 403 `origem_invalida` quando `PLAT_URL_PUBLICA` não é a origem servida — os e2e
anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`. Em produção as duas
coincidem; no ambiente da trilha o nginx local reescreve o cabeçalho. ADR 20260907T0302.
## turno 3, setembro de 2026 (F8: o schema de dado de camada passa a carregar a instalação)

- `plat.camada_schema_prefixo()` (migração `20260907T0245_isolamento_schema_de_dado.sql`): o dado de
  camada mora em `d_<slug>` em produção e em `d_plat_t<trilha>_<slug>` / `d_plat_homolog_<slug>` nas
  instalações derivadas. Produção não muda de lugar; nada é renomeado nem apagado. ADR 0018.
- `camada_schema_garantir`, `camada_preparar`, `tenant_criar` e `app/ingestao/carregar.py` usam o prefixo.
- `laco/trilha_ambiente.sh`: worktree com o conserto não recebe mais privilégio nos schemas de dado de
  produção (medido: `has_schema_privilege('plat_tf8isol_app','d_demo','USAGE')` = falso, contra
  verdadeiro para as trilhas antigas).
- Testes: `tests/api/ingestao/test_isolamento_schema_dado.py` (4 exigências do portão, 3 delas reprovam
  com o código anterior); dois testes que fixavam `'d_demo'` no texto passaram a perguntar o prefixo —
  mediam o schema de PRODUÇÃO de dentro da trilha (87 tabelas alheias contadas em 07/09/2026).

## turno 4, setembro de 2026 (junção F8 x corrida-camada-schema: isolamento COM trinco)

Os dois consertos acima redefinem as mesmas três funções `SECURITY DEFINER`. Como o carimbo do
isolamento (`20260907T0245`) é posterior ao do trinco (`20260907T0240`), aplicar os dois na ordem
deixava de pé as versões sem `pg_advisory_xact_lock` e
`tests/api/test_camada_schema_corrida.py::test_toda_funcao_com_ddl_tem_trinco` reprovava — que é o
aviso escrito no cabeçalho da própria migração do trinco. A migração
`20260907T2030_isolamento_schema_de_dado_com_trinco.sql` redefine `camada_schema_garantir`,
`camada_preparar` e `tenant_criar` uma única vez com as duas propriedades juntas, declarando
`-- depende:` das duas anteriores. Nenhuma migração já aplicada foi editada.

Duas escolhas registradas: (1) a chave do trinco de schema passa a ser o NOME DO SCHEMA
(`plat.camada_schema_prefixo() || slug`) e não mais o slug — com o isolamento, duas instalações com o
mesmo apelido de inquilino tocam schemas diferentes e não têm por que esperar uma pela outra;
`camada_preparar` mantém a chave `schema.tabela`, que já carregava o prefixo. (2) o alfabeto de slug e
de nome de schema é a união dos dois ramos (`-` do ramo do trinco, `_` e 80 caracteres do ramo do
isolamento), para que nenhuma junção posterior perca nem um nem outro. Medido na base da trilha
`f8isol`: `tests/api/test_camada_schema_corrida.py` e
`tests/api/ingestao/test_isolamento_schema_dado.py` = 10 aprovados em 23,23 s, com a segunda
instalação `f8isolb` no mesmo banco.

## turno 4, setembro de 2026 (corrida-camada-schema: DDL concorrente em função SECURITY DEFINER)

Defeito de produto achado em produção-de-teste: duas sessões do MESMO inquilino publicando camada ao mesmo
tempo caem as duas em `plat.camada_schema_garantir(slug)`, que faz `CREATE SCHEMA IF NOT EXISTS` mais
`GRANT USAGE ON SCHEMA` sem serialização. O `GRANT` atualiza a mesma linha de `pg_namespace`, que não tem
EvalPlanQual, e a segunda transação aborta com `tuple concurrently updated`; o job de ingestão morre no
passo 0. Medido pela bancada nova `tests/api/test_camada_schema_corrida.py`, com conexões reais alinhadas
por barreira, ANTES do conserto: 2 falhas em 12 chamadas com 2 conexões, 10 em 24 com 4, 15 em 36 com 6.
DEPOIS do conserto: 0 em 24 com 4 conexões, quatro rodadas seguidas do arquivo sem falha
(`tests/medidas/corrida-camada-schema.json`).

Conserto na migração `20260907T0240_ddl_concorrente_trinco.sql`: `pg_advisory_xact_lock(hashtext(<chave>))`
antes do DDL, chave derivada do objeto tocado. `IF NOT EXISTS` não bastava porque só cobre metade do
problema e nem essa metade é atômica (ADR 0025 seção 2). A classe inteira foi coberta, não só o caso
flagrado: `camada_schema_garantir`, `camada_preparar`, `tenant_criar` (mesmo `d_<slug>`, chave partilhada),
`evento_particao_garantir` e `log_particao_garantir` (mais reconferência depois do trinco) e os dois
expurgadores de partição. `tenant_apagar_interno` fica de fora com razão escrita: só emite `ALTER TABLE`,
que já pega bloqueio pesado na tabela. A chave é por slug, então inquilinos diferentes não esperam um pelo
outro — provado com uma transação segurando `demo` enquanto `demo2` completa em menos de 5 s e `demo`
estoura o `statement_timeout` de 1 s. Guarda contra regressão: `test_toda_funcao_com_ddl_tem_trinco` lê
`pg_proc.prosrc` vivo e reprova função `SECURITY DEFINER` que faça DDL de schema, GRANT ou CREATE/DROP
TABLE sem o trinco — necessário porque a migração redefine funções inteiras e um ramo posterior pode
derrubar o trinco em silêncio. ADR 0025.
## turno 4, setembro de 2026 (item L4-02-b-montante-jusante: sentido pela distância ao controlador)

`POST /api/rede/{id}/tracar` com `tipo=montante|jusante` passou a derivar o SENTIDO do controlador de subrede
quando a rede tem um em tier hierárquico: a árvore de caminhos mínimos a partir dos controladores
(`public.pgr_drivingDistance`, `equicost`) diz quem está mais perto da fonte; jusante de um ponto é a
subárvore dele, montante é a cadeia de pais até o controlador, que sai nomeado na resposta. Sem controlador,
segue valendo a direção declarada em atributo (item L4-18) — e a resposta sempre diz de onde veio o sentido,
no campo `origem_direcao`, que também pode ser imposto no pedido.

O traçado se recusa a inventar direção em três situações, cada uma com motivo próprio na resposta: tier
particionado (malha) sem nenhum trecho declarando `direcao_fluxo`; laço, isto é, mais de um caminho até o
controlador tocando o resultado pedido (sai `direcao='indeterminado'` com `nos_do_laco`); e ponto que nenhum
controlador alcança. Grafo, resolução de ponto, barreira e formato de saída são os de `tracado.py`: não há
segundo motor de traçado. ADR `docs/adr/20260907T2133-montante-jusante-por-controlador.md`.

Medido em `tests/medidas/L4-02-b-montante-jusante.json`. Fronteira honesta registrada ali: a comparação entre
o jusante de cada transformador da cooperativa de teste e as unidades consumidoras que o arquivo liga a ele
tem universo VAZIO — os 26.581 ramais de ligação do arquivo não têm geometria, então nenhuma das 27.587
unidades consumidoras tem caminho desenhado até o transformador.

Na mesma passagem, a união dos seis ramos de L4 fechou dois registros que faltavam e reprovavam o lote
inteiro na fila: as 11 rotas de escrita da rede de utilidades em `tests/api/eventos_esperados.py` e os 16
casos de cobertura cruzada em `tests/api/cruzado_casos.py`.

## turno 4, setembro de 2026 (item L4-04-a-controladores-e-tiers: controlador de subrede e tiers)

Onde cada subrede começa passou a ser dado gravado, e não convenção de traçado (ADR
`docs/adr/20260907T2031-controlador-de-subrede-e-tiers.md`; paridade em `docs/PARIDADE.md`, seção "controlador
de subrede e tiers"). `POST /api/rede/{id}/controlador` marca o TERMINAL de um dispositivo como controlador de
uma subrede num tier, e `DELETE .../controlador/{cid}` desfaz; só um tipo de ativo com a categoria de rede
`controlador` é aceito (poste é recusado com `422 categoria_nao_controladora`) e o NOME do controlador é único
dentro do tier (`409 nome_de_controlador_repetido`), enquanto a mesma subrede aceita vários controladores de
nomes distintos. A âncora gravada é feição + terminal, nunca o nó derivado: reconstruir a topologia inteira não
apaga controlador nenhum.

`plat.rede_subrede` é a tabela de subredes (nome, tier, estado `limpa`/`suja`, resumo do último traçado);
`POST .../subredes/{id}/atualizar` refaz o traçado a partir dos controladores e devolve a subrede limpa, e
qualquer área suja aberta na rede faz a leitura mostrar `suja` de novo, com `estado_gravado` ao lado.
`POST .../controladores/importar` marca, a partir do que a importação da BDGD trouxe, **1 controlador por
alimentador (CTMT)** — pelo terminal do disjuntor de saída quando o arquivo traz o equipamento, pelo nó de
cabeça (convenção declarada, gravada como `origem='no_de_cabeca'`) quando não traz — e **1 por transformador
de distribuição, no terminal de jusante, no tier de baixa tensão**. O pacote `eletrica-br` ganhou a categoria
`controlador` em subestação, disjuntor e transformador (nada foi removido). Tela `/redes/controladores` com a
tabela de subredes e a ficha do controlador (dispositivo, terminal, tier, subrede, papel, origem e o nó na
topologia corrente), com atualizar e remover.

Medido em `tests/medidas/L4-04-a-controladores-e-tiers.json`: numa rede no formato da BDGD com 2 alimentadores
e 1 transformador, a marcação automática deu **1 por dispositivo, 1 por nó de cabeça e 1 por transformador**, e
rodar de novo não duplicou nada (3 já marcados). 17 testes de API e 1 e2e da ficha. Lacuna nomeada: **grupo de
tier (tier group) não existe** no modelo — a fonte o exige em domínio hierárquico e o dispensa em particionado,
que é o caso do pacote elétrico entregue.

## turno 4, setembro de 2026 (item L4-04-c-sumarios-por-subrede: sumário por subrede, tabela e CSV)

Quanto tem cada alimentador passou a ser tabela, e não conta feita à mão (ADR
`docs/adr/20260907T2243-sumario-por-subrede.md`; paridade em `docs/PARIDADE.md`, seção "sumário por
subrede"). `plat.rede_subrede_resumo` tem uma linha por subrede com quilômetro por nível de tensão
(declarado pelo cadastro e pela geometria, com a diferença em porcento ao lado), transformadores e kVA
instalado, unidades consumidoras e sua distribuição por classe, energia anual faturada, dispositivos por
categoria de rede, geração distribuída (unidades e kW) e o tronco — a maior distância, andando pela rede,
de um controlador até um ponto alcançável da subrede. `POST /api/rede/{id}/subredes/resumos/calcular`
recalcula (a rede inteira, um tier ou uma subrede) e `GET /api/rede/{id}/subredes/resumos` devolve a
tabela com a DESCRIÇÃO das colunas ao lado das linhas — código, nome, tipo e unidade, que é o que um
elemento de painel precisa para se ligar à fonte sem rótulo escrito à mão; `formato=csv` devolve a mesma
tabela como arquivo.

A filiação de cada elemento à subrede vem do atributo que o arquivo declara por tier (`ctmt` na média
tensão, `uni_tr_mt` na baixa), a mesma convenção com que a importação da BDGD nomeia as subredes. É o
retrato do CADASTRO, não do que a topologia alcança, e está dito assim no ADR e na tabela de paridade.

Medido em `tests/medidas/L4-04-c-sumarios-por-subrede.json`, sobre o arquivo real da cooperativa de teste
(44.268 trechos de média tensão, 5.481 transformadores, 27.587 unidades consumidoras, 1.385 gerações):
**20 alimentadores somados em 1,5 s**, quilômetro de média tensão idêntico à soma do comprimento declarado
no arquivo nos 20 (tolerância do portão: 0,1 %), contagem de unidades consumidoras idêntica nos 20 e
**soma das unidades dos 20 sumários = 27.587 = total do arquivo** — nenhuma unidade contada em dois
alimentadores. A diferença entre o comprimento declarado e o da geometria, medida e guardada por
alimentador, vai de +0,03 % a −8,49 %. Um alimentador declarado na camada CTMT não tem trecho nenhum no
arquivo e ficou anotado (não vira subrede). 9 testes de API rápidos e 1 medição em escala real.

## turno 4, setembro de 2026 (item L4-18-rede-simples-trace-network: rede simples, direção de fluxo, montante e jusante)

Rede sem pacote de ativos, o equivalente de disciplina ao Trace Network da Esri (ADR 20260907T2005; documento
e tabela de paridade em `docs/rede/REDE_SIMPLES.md`). `POST /api/rede/simples` cria a rede a partir de DUAS
camadas do inquilino numa chamada — rede, catálogo mínimo, feições copiadas (multiparte explodida,
reprojetada), configuração de direção e topologia construída; a tela `/redes/simples` faz isso em
**3 interações** (`criar_rede_simples_cliques` = 3, `tests/e2e/test_rede_simples.py`). A direção de fluxo vem
de um ATRIBUTO do trecho, traduzido para o vocabulário fechado `digitalizada`/`contra`/`indeterminada`;
`POST /api/rede/{id}/tracar` ganhou `tipo=montante` e `tipo=jusante`, que param em toda aresta indeterminada
com um aviso por trecho (`app/rede_utilidades/fluxo.py`). `POST /api/rede/{id}/promover` carimba o pacote
mínimo e muda o modo para `utilidades`.

Medido em `tests/medidas/L4-18-rede-simples-trace-network.json`: uma bacia real do BC250 do IBGE
(**584 trechos, 585 nós**, recorte em `tests/dados/bacia_bc250.json`) virou rede simples em **464 ms**
(carga 6,83; 7,2 GiB livres) e **48 traçados** de montante/jusante bateram elemento a elemento com o cálculo
independente em `networkx`, com **65 arestas indeterminadas** no meio do caminho
(`tests/api/test_rede_simples_bacia_bc250.py`). 16 testes de API na rede sintética, entre eles a refutação do
item: marcar um trecho como indeterminado por `applyEdits` faz montante e jusante pararem nele, com aviso
nomeando trecho e nó.

## turno 4, setembro de 2026 (item L4-02-d-lacos-e-caminho-curto: laços, caminho mais curto e isolados)

`POST /api/rede/{id}/tracar` ganhou três valores novos de `tipo` (ADR 20260907T1748), sobre o MESMO grafo do
item irmão L4-02-a: `lacos` (ciclos por componente biconexo, `public.pgr_biconnectedComponents`), `isolados`
(sem caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`,
`public.pgr_connectedComponents`) e `caminho_curto` (origem/destino, custo = `atributo_custo` ou o
comprimento geodésico por padrão, `public.pgr_dijkstra` k=1 / `public.pgr_ksp` k>1). Módulo novo
`app/rede_utilidades/lacos.py`. 13 testes funcionais verdes (`tests/api/test_rede_lacos_caminho.py`):
rede radial sem laço = 0; quadrado fechado = 1 laço de 4 arestas; banco de capacitores sem linha = isolado
(fonte nunca é isolada); comprimento de `caminho_curto` bate com a soma independente do `ST_Length` dos
trechos (0% de diferença no caso testado, dentro do 0,5% do portão); `k=3` devolve 2 alternativas distintas
no quadrado (só existem 2) e 1 na rede radial (honesto: k não inventa caminho); custo por atributo
customizado (`impedancia`) escolhe caminho diferente do geodésico. Refutação: adversário fecha uma chave
normalmente aberta (via `applyEdits` real, item L4-01-b) e o laço passa a aparecer (0 → 1, mesmas arestas
esperadas); pedir `caminho_curto` com atributo de custo nulo num trecho do grafo é recusado com 422
`atributo_custo_nulo` e a lista das feições faltantes — nunca troca nulo por zero. Cláusulas NÃO medidas,
declaradas: laços da cooperativa de teste e p95 do maior alimentador — teste pronto
(`tests/api/test_rede_lacos_caminho_medida.py`, marcador `lento`), máquina com carga 9,5-10,4 no momento
(regra do brief: não medir acima de 8); registrado `medido: false` com a carga ao lado. Front-end
clique+tabela+e2e: mesma fronteira honesta do item irmão (sem `web/` de rede de utilidades no repositório).

## turno 4, setembro de 2026 (item L4-02-a-conectado-e-subrede: traçado conectado e subrede — PARCIAL)

`POST /api/rede/{id}/tracar` (tipo `conectado`|`subrede`), sobre `public.pgr_connectedComponents`
(pgRouting 4.0.1, já instalada — ver ADR 0021): ponto de partida por feição+terminal ou coordenada com
tolerância, barreiras que removem nó do grafo inteiro, travessabilidade por `atributos.estado`, fronteira
de subrede pela categoria `transformacao`. Rede sintética de 12 nós com resultado conhecido em pytest:
conectado = 9 elementos/6 nós, subrede = 6 elementos/4 nós (`tests/api/test_rede_tracado.py`, 13 casos,
todos verdes). Refutação: laço fechado não duplica elemento nem trava; transformador é a fronteira de
subrede, chave em série (mesmo grupo) não é. pgRouting confirmada instalada por consulta a
`pg_available_extensions`. Dois defeitos corrigidos na primeira execução real (import de `psycopg2` fora
de escopo; SQL de arestas sem a coluna `cost` que `pgr_connectedComponents` exige) — ver ADR 0021.
Cláusulas NÃO cumpridas, declaradas: (1) clique+tabela lateral+captura e2e — não existe front-end de rede
de utilidades no repositório para acoplar; (2) p95 ≤ 2 s no maior alimentador da cooperativa de teste —
teste pronto (`test_rede_tracado_medida.py`, marcador `lento`), mas a máquina estava com carga 18-21
(regra do brief: não medir acima de 8); registrado `medido: false` com a carga ao lado, não fingido.

## turno 4, setembro de 2026 (item L4-01-b-topologia-derivada: topologia derivada da rede de utilidades)

`POST /api/rede/{id}/topologia/habilitar` reconstrói dois índices derivados das feições da rede —
`plat.rede_topo_no` (um por vértice de conexão/terminal) e `plat.rede_topo_aresta` (um por trecho, com nó de
origem/destino, comprimento geodésico e bitmask de fase) — numa transação, nunca incremental nesta passagem.
Tolerância de coincidência é parâmetro da rede (`plat.rede.tolerancia_m`, padrão 0,05 m), visível na ficha:
0,04 m conecta e 0,06 m não conecta na tolerância padrão; a mesma distância de 0,06 m conecta numa rede que
declarou 0,1 m. Cruzamento geométrico no meio de duas linhas nunca gera nó (cruzar não é conectar). `applyEdits`
de ponto/linha (paridade FeatureServer) marca área suja a cada gravação. RLS ligada e índice GIST conferidos
no catálogo do Postgres (não no arquivo de migração) em todas as 6 tabelas da topologia. Contrato em
`docs/adr/0020-topologia-derivada-da-rede-de-utilidades.md`; modelo e paridade em `docs/rede/TOPOLOGIA.md`.

Medido em escala real (schema `certaja` do `iagro_sat`, ativo da casa, somente leitura — a rede real da
cooperativa de teste, não um arquivo do repositório): 73.512 arestas reais (44.268 MT + 29.244 BT), 80.456
nós, 3.948 órfãos, 0 arestas sem nó, 21 alimentadores com componente conexa idêntica arquivo × topologia
(contador Python independente sobre o wkt cru), 1.554 terminais de alta órfãos batendo exato com o arquivo,
60.549 postes → 0 nós. Conserto de dois achados do próprio agente ao medir em escala (`tests/dados/carga_bdgd.py`):
literal `%` não escapado em SQL parametrizado (`IndexError: tuple index out of range` do psycopg2) e chave
errada num dicionário de retorno (`fins_de_linha` → `fins_de_linha_grau1`).

⛔ Fronteira medida, não fabricada: `certaja.ramlig` (ramal de ligação) tem os 26.581 registros do arquivo mas
**0 com geometria armazenada** (`wkt` nulo em 100%) — entra como atributo, não como aresta geométrica; a
topologia geométrica medida cobre MT + BT + transformador + poste (139.542 elementos reais). Tempo de
`habilitar` variou de ~21 s a ~600 s na mesma carga conforme a disputa por CPU/RAM de outras trilhas na
máquina compartilhada (swap 100% cheio no pior caso) — variação do ambiente, não do algoritmo (lotes de
4.000 linhas, ADR 0020 §5); os dois tempos ficam no arquivo de medida. Manutenção incremental por área suja
e traçado seguem fora desta passagem (itens seguintes da linha L4).
## turno 3, setembro de 2026 (item L2-04-j-conformidade-clientes-e-paridade: matriz de conformidade viva)

`tests/esri/conformidade.py` + `make conformidade`: a lista de serviços do `docs/PARIDADE.md` deixa de ser
texto escrito à mão e passa a ser saída de medida. 102 linhas (45 parâmetros da operação `query`, diretório,
edição, anexos, OGC API Features, WFS 2.0, tiles vetoriais, serviços ainda não construídos e clientes), cada
uma nomeando a prova que a sustenta — um nó de teste ou uma chave dos roteiros de sonda dos itens irmãos. O
script roda as provas, grava `tests/esri/conformidade.json` com data e versão do repositório, e reescreve a
seção do documento entre marcadores. Regra: prova que falha derruba a linha para REFUTADO; linha sem prova
executada cai para "não medido" e nunca vira "suportado". `tests/unit/test_conformidade_matriz.py` reprova
documento editado à mão, linha afirmada sem prova, parâmetro da doc Esri ausente da matriz e item irmão
construído fora dela.

`tests/api/test_conformidade_clientes.py`: cliente OGC de terceiros (owslib) contra um uvicorn próprio da
trilha — lê o `GetCapabilities` do nosso WFS 2.0, monta o catálogo e faz `GetFeature` pelo código dele.
Também mede a AUSÊNCIA de rota WMS (404 e nenhum caminho no OpenAPI), e mede que QGIS e o pacote Python
`arcgis` não estão nesta máquina: as linhas que dependem deles ficam "não medido", com o motivo escrito.
`docs/TESTE_PARCEIRO_PRO_AGOL.md` traz o protocolo para quem tem ArcGIS Pro e ArcGIS Online executarem, com
`resultado: pendente` até haver evidência devolvida.

Dois defeitos que só aparecem com os ramos da família juntos foram consertados no caminho: o estilo do
catálogo não chegava ao cliente Esri (o descritor entregava o documento de estilo inteiro ao conversor de
`drawingInfo`, e o compilador da casa emite cadeia `case`, que o conversor não lia), e o tile vetorial
devolvia 422 (o repasse do visualizador casava antes no mesmo prefixo `/tiles/`).

## turno 3, setembro de 2026 (item L2-04-e-vector-tile-server-tilejson: servidor de tiles vetoriais em 3 contratos)

`app/tiles/vector_tile_server.py` + `app/tiles/exportacao.py` + `app/tiles/{autorizacao,martin_cliente,
tilejson,camada}.py`: **contrato 1** TileJSON 3.0.0 (`GET /tiles/{token}/{item}/tilejson.json`) + tile XYZ puro
(`.../{z}/{x}/{y}.pbf`) para MapLibre/QGIS; **contrato 2** VectorTileServer compatível Esri
(`GET /svc/{token}/rest/services/{item}/VectorTileServer` com `tileInfo` Web Mercator 512 px e `capabilities:
TilesOnly`, estilo em `.../resources/styles/root.json` compilado por `app.estilos.padrao`/`compilador` — item
L2-02-a, reusado sem reescrita —, sprites/glyphs REAIS mas vazios enquanto L2-02-e não existe, e o tile em ordem
Esri `.../tile/{z}/{y}/{x}.pbf`); **contrato 3** exportação por URL (`GET /svc/{token}/camadas/{item}.geojson|
.kml|.csv|.fgb|.gpkg`, filtro `where`/`bbox` reusando o AST do FeatureServer — L2-04-b/c). Token no CAMINHO em
todos os três (decisão do ladrilho raster, item L1-02, citada como ativo da casa a reusar).

Medido com Martin real (`.bin/martin` v1.15.0, mesmo binário do L2-01-b) e, para o contrato 2, com PyQGIS
headless de verdade: TileJSON válido contra o esquema oficial 3.0.0 (vendorizado em
`docs/esquemas/vendorizados/`); tile Esri (`z/y/x`) e MapLibre (`z/x/y`) **byte a byte idênticos** por construção
(`_tile_bytes` é o único ponto que fala com o Martin); `root.json` passa no validador oficial
`@maplibre/maplibre-gl-style-spec`; QGIS (`QgsVectorTileLayer` + `QgsMapBoxGlStyleConverter`) carregou a camada
por URL do `root.json` e renderizou as feições com requisições HTTP reais ao servidor (captura em
`tests/medidas/L2-04-e_qgis_captura.png`); KML de 10.000 feições confere com `ogrinfo`; GeoJSON de 1.000.000 de
feições via cursor nomeado do Postgres, RSS de pico do worker **145 MB** (teto do portão: 300 MB); token
revogado devolve 401 nas 10 rotas testadas (tiles, VectorTileServer, exportações).

Achados do adversário, corrigidos ou registrados como fronteira: `/vsistdout/` não funciona com o driver
FlatGeobuf nesta versão do GDAL (3.8.4) — FlatGeobuf e GeoPackage passaram a escrever em arquivo temporário via
`ogr2ogr`, apagado ao fim; tile z25 (fora do intervalo 0-24 aceito por `plat.camada_tile_garantir`) vira 502
nomeado, nunca 500 cru; `.csv` de camada com geometria MULTI funciona, e "camada sem geometria" não existe neste
catálogo (item alheio ao escopo do token dá 403, nunca 404/500); o ETag muda de verdade depois de editar uma
geometria, mas fica preso ao cache de 5 min em memória do próprio Martin (decisão já tomada pelo L2-01-b) dentro
dessa janela — sem prazo declarado no portão, registrado como achado honesto, não como defeito. `docs/adr/
20260907T1648-vector-tile-server-tres-contratos.md` e `tests/medidas/L2-04-e-vector-tile-server-tilejson.json`
têm a cláusula a cláusula. Fora do turno: Pro/AGOL reais (D20, exige credencial do parceiro); sprite/glyphs de
verdade (depende de L2-02-e, não construído).

## turno 4, setembro de 2026 (item L2-04-servicos-esri-ogc: diretório do FeatureServer, OGC API Features e WFS 2.0)
## turno 3, setembro de 2026 (item L3-02-a-monte-carlo-pesos: robustez do motor multicritério por sorteio de pesos)

`app/amc/robustez.py` (puro, sem I/O): `sortear_pesos` (Dirichlet no simplex ou faixa +-k% por fator,
declarada) e `simular_robustez`, que chama o combinador do L3-01-e (`app.amc.combinacao.combinar`) N
vezes e agrega por unidade (minimo, media, maximo, desvio, frequencia no top-k e no decil superior,
estavel = top-k em >=95% dos sorteios). Sorteio de peso em ordem canonica pelos IDs dos fatores (nunca
pela posicao de entrada), remapeada de volta na saida: permutar a ordem de entrada e reexecutar com a
mesma semente da o mesmo resultado (nota com tolerancia 1e-9 por soma de ponto flutuante nao ser
perfeitamente associativa; ranking exato). Veto e restricao nunca sao sorteados: `fracao_vetada` fixo
em todos os N sorteios, unidade vetada marcada com nota `-inf` antes de ordenar (exclusao do topo por
construcao, testada com unidade que teria a nota maxima sem o veto). Job `amc.robustez_pesos`
(`app/amc/tarefas.py`, pesado=True, timeout_s=120) registrado em `app/jobs/tipos.py`; resultado
(agregados + semente, nunca a matriz N x unidades, conforme A9) em `job.resultado` (jsonb existente,
sem migracao nova). Medido (`tests/medidas/L3-02-a-monte-carlo-pesos.json`): 1.000 sorteios em 5.000
unidades x 8 fatores como job, 0,767 s (78x dentro do limite de 60 s). ADR
`docs/adr/20260907T1245-robustez-sorteio-de-pesos.md`.
## turno 3, setembro de 2026 (item L3-01-f-explicacao: explicação da nota do motor multicritério)

`GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao` responde "por que esta unidade tem nota
N": tabela fator → valor bruto (com unidade e fonte) → transformação → favorabilidade → peso → contribuição,
mais soma, veto/motivo e cobertura (`app/amc/explicacao.py`). Recalculado a partir de `plat.amc_fator_bruto` na
hora, nunca lido de uma tabela de explicação gravada — o mesmo combinador de `app/amc/combinacao.py` (item
L3-01-e). Sobre 100 unidades sorteadas, |soma das contribuições − favorabilidade gravada| ≤ 0,5 (medido:
`tests/medidas/L3-01-f-explicacao.json`). Painel em `/amc/explicacao/<execucao_id>/<unidade_id>`
(`web/amc_explicacao.html` + `web/js/amc/explicacao_pagina.js`). Combinador fuzzy (mínimo/máximo/produto/soma
fuzzy/gama) não decompõe em contribuições por fator por definição matemática — a tabela mostra a favorabilidade
de cada fator sem fingir uma soma que não existe. Transformação contínua (Rescale by Function, item
L3-01-d-transformacoes, pendente) aparece com valor bruto e observação, nunca com número fabricado. ADR
`docs/adr/20260907T1245-explicacao-amc.md`.
## turno 3, setembro de 2026 (item L6-04-acervo-no-motor: camada do acervo como fator no motor multicritério)

Fecha o ciclo entre o motor AMC (L3-01-a/b/c) e a publicação sem cópia do acervo (L6-01-b): `app/amc/executor.py`
(job `amc.executar`, enfileirado sozinho por `POST /api/amc/execucoes` quando o modelo tem fator `camada.tipo =
'acervo'`) lê cada fator direto da view `plat_acervo.<view>` — nunca copia a tabela de origem — com
`app.amc.vetorial` fazendo a extração e uma transformação `linear` levando o valor bruto a favorabilidade 0-100.
Provado com 3 camadas REAIS já ingeridas na casa (`icmbio_unidades_conservacao`, `funai_terras_indigenas`,
`hidro_nacional_bc250`, 1,6 mi de linhas), não dado sintético. `app/amc/camadas.py::_acervo` passou a exigir
`plat.acervo_pode_ler` (mesmo porteiro da API de mapa) na CRIAÇÃO da execução — sem assinatura, 422
`sem_assinatura`, execução nem nasce; o job confere a assinatura DE NOVO, uma vez antes de cada fator e uma vez
depois do último, então revogar a assinatura NO MEIO do job (a refutação do item) derruba a execução com
`FalhaDefinitiva` e mensagem, sem gravar nenhuma linha de `amc_fator_bruto`/`amc_resultado` — os dois só são
escritos juntos, no bloco final, depois de todas as confirmações. Resultado de uma execução já concluída nunca é
apagado por uma revogação posterior (gatilho `amc_resultado_guarda`, sem mudança). Proveniência
(`amc_execucao.camadas`) ganhou o campo `fonte_id` explícito, ao lado de `sha256`/`contagem`/`contagem_origem`
que `mod_camadas._acervo` já gravava. Limite honesto: só fatores `camada.tipo == 'acervo'` são extraídos por este
job (fator do tipo `item` fica de fora, é ignorado na combinação); só transformação `linear`; camada lida só
dentro da caixa envolvente das unidades + folga, não da tabela inteira (necessário para não varrer camadas
nacionais de milhões de linhas a cada execução) — a combinação completa do motor (categorias, faixas, degraus,
funções contínuas, combinadores alternativos) é o item L3-01-d/e, ainda não construído.

Achado de merge: juntar os três worktrees de que este item depende (`wt/amc`, `wt/extrat`, `wt/t601b`, nenhum
ainda integrado a `master`) produziu um `SyntaxError` real em `tests/api/cruzado_casos.py` — o merge automático
(`git ort`) costurou dois `return Preparacao(...)` de branches diferentes de um jeito que partiu uma função no
meio por uma `def` e derrubou um `),` de fechamento do dicionário `CASOS`. Sem o conserto (feito neste ramo),
`make lint` e toda a suíte de API (que importa `tests/api/conftest.py`, que importa `cruzado_casos.py`) falhavam
na coleta. `docs/openapi.json` continua sem nenhuma das 18 rotas `/api/amc` — débito pré-existente do próprio
L3-01-a/b, não deste item; os dois testes que dependem dele (`test_amc_adversario_api.py` × 2,
`test_cruzado.py::test_cobertura_100_por_cento`) seguem vermelhos, sem regressão nova. `docs/adr/0017` do
L3-01-c também dispara `make sem-marcador` (falso positivo de uma palavra comum em português que contém a
sequência proibida por acaso) — não é código deste item, não corrigido aqui.
## turno 5, setembro de 2026 (item L5-31-construtor-de-camada-esquema: construtor de camada por esquema)

Camada vazia criada por lista de campos arrastados (`POST /api/camadas/esquema`): tipo, tamanho, alias,
obrigatório, valor padrão, domínio (lista código→rótulo) e índice, mais tipo de geometria e SRID. Reaproveita
inteiramente o núcleo do L0-04-ingest-vetor — `plat.camada_schema_garantir`/`plat.camada_preparar` (a mesma
tabela nasce com colunas obrigatórias, `FORCE ROW LEVEL SECURITY`, índice GIST e gatilhos de tenant/versão
que uma camada importada) e `app.ingestao.nomes.normalizar` para o nome de cada campo (mesma regra de acento,
palavra reservada e duplicata da ingestão). Alias e domínio — o que o PostgreSQL não guarda — vivem numa
tabela nova, `plat.camada_campo_meta`, com FK simples para `plat.item(id)` e coerência de inquilino por
gatilho `plat.tg_camada_campo_meta` (migração `20260907T1509_camada_esquema.sql`, mesmo padrão de
`plat.item_relacao`/`plat.item_grupo`): mesmo que uma política de RLS falhasse em algum caminho futuro, o
próprio banco recusaria uma linha de metadado apontando para item de outro inquilino. `GET /api/camadas/{id}/campos` devolve os campos no formato `fields` de um
tabela nova, `plat.camada_campo_meta`, com FK **composta** `(tenant_id, item_id)` para `plat.item` (exigiu uma
`UNIQUE (tenant_id, id)` nova em `plat.item`, migração `20260907T1509_camada_esquema.sql`): mesmo que uma
política de RLS falhasse em algum caminho futuro, o próprio banco recusaria uma linha de metadado apontando
para item de outro inquilino. `GET /api/camadas/{id}/campos` devolve os campos no formato `fields` de um
FeatureServer Esri (name/type/alias/length/nullable/domain) lendo tipo/tamanho/obrigatoriedade direto de
`information_schema.columns` — nunca uma cópia que pode desalinhar do banco.

Alterar esquema (`POST .../esquema/plano` mostra o plano; `PUT .../esquema` aplica) trata cada mudança por
cláusula: adicionar campo e renomear alias sempre aplicam; alargar tamanho de texto ou tipo (`ALARGAMENTO_SEGURO`:
inteiro→bigint→double, texto sempre aceito como destino) aplica; qualquer mudança que possa truncar ou
invalidar dado existente (reduzir tamanho, ou um tipo fora da lista de alargamentos seguros — o caso do
portão, texto→inteiro) só aplica se a camada estiver VAZIA; com dado, é recusada com a mensagem exata e
NUNCA aplicada calada. Tela `/construtor-camada`: paleta de 8 tipos com Drag and Drop API nativa do HTML5 (0
byte de biblioteca, mesmo princípio do editor de arrasto do L5-08) e clique como alternativa sem mouse — as
duas vias produzem exatamente o mesmo campo, provado em e2e.

Refutação do item (300 campos, um deles a palavra reservada `select` e outro com acento/símbolo/maiúscula):
normalizou os 300 sem colisão de nome e sem 500; o `GET /campos` continuou respondendo certo para as 300
colunas. Dois bugs reais achados e corrigidos ANTES do adversário: (1) a ordem de inserção tinha
`camada_campo_meta` ANTES de `plat.item` — a própria FK para `plat.item` recusava a primeira
`camada_campo_meta` ANTES de `plat.item` — a própria FK composta que o item pede recusava a primeira
gravação, sempre; (2) alargar de `text` (sem teto) para `varchar(N)` não conferia o maior valor já gravado —
corrigido para medir `max(length(...))` antes de aceitar. Ver `docs/PARIDADE.md` para a tabela completa
feito/parcial/fora contra a capacidade Esri.

### Medições (`tests/medidas/L5-31-construtor-de-camada-esquema.json`)

| medida | valor | comando |
|---|---|---|
| campos criados e lidos de volta em `/campos` | 5 | `GET /api/camadas/{id}/campos` |
| refutação: 300 campos hostis (reservada, acento, duplicata) | passa | `POST /api/camadas/esquema` com 300 campos |
| testes da suíte do item | 9/9 | `tests/api/catalogo/test_camada_esquema.py` |
| e2e (arrasto + clique + criação, 0 erro de console) | 1/1 | `tests/e2e/test_construtor_camada.py`, capturas em `tests/e2e/capturas/L5-31-*` |

### Commits

Ver `git log` do ramo desta trilha (`wt/il531constr`) — migração, backend (`app/catalogo/camada_esquema.py`),
frontend (`web/construtor_camada.html`, `web/js/catalogo/camada_esquema.js`, `web/estilo/camada_esquema.css`)
e testes (API + e2e) num só commit por não haver como dividir sem quebrar o portão no meio.
## turno 4, setembro de 2026 (item L2-04-f-mapserver-identify-legend-geometryserver: MapServer e GeometryServer)

O outro contrato do protocolo Esri, o dos clientes que consomem MAPA e não feição: `/svc/{token}/rest/services/
{mapa}/MapServer` com descritor, `/layers`, `/{id}`, `export`, `identify`, `find`, `legend` e `generateKml`
(`app/consulta/rotas_mapserver.py` + `app/consulta/mapserver.py`), e o
`/svc/{token}/rest/services/Utilities/Geometry/GeometryServer` com `project`, `buffer`, `areasAndLengths`,
`lengths`, `distance`, `union`, `intersect`, `difference`, `convexHull` e `simplify`
(`app/consulta/rotas_geometria.py`). O serviço é um item de tipo `mapa` do catálogo, e o identificador de
camada é a posição no documento; o diretório do item L2-04-b passou a listar mapa como `MapServer` ao lado da
camada como `FeatureServer`.

Sem dependência nova: o desenho é `PIL.ImageDraw`, o mesmo que `app/catalogo/miniatura.py` já usava, com o
símbolo vindo do `drawingInfo` que o FeatureServer publica — a amostra da legenda e o pixel do mapa saem da
MESMA estrutura, então não existe caminho em que a legenda diga uma cor e o mapa desenhe outra. Toda operação
do GeometryServer é uma chamada ao PostGIS; nada de geometria é calculado em Python.

Medido (`tests/medidas/L2-04-f-mapserver-identify-legend-geometryserver.json`): export de 1024×768 em
**0,075 s quentes sobre 5.003 polígonos** (carga 4,81 em 12 núcleos; teto do portão 1,5 s) e 0,047 s no mapa
de três camadas; `project` de 100 pontos com diferença **0,0 m** contra `ST_Transform`; envoltória geodésica
de 1 km com erro relativo de área **0,0** contra `ST_Buffer` sobre `geography`. `identify` sobre três camadas
devolve exatamente o mesmo conjunto de feições da consulta espacial escrita à mão (comparação por
identificador, com e sem tolerância).

Refutação declarada do item, toda ela em teste: export de 8.000×8.000 volta 400 com o limite declarado
(`MAPSERVER_LADO_MAX = 4096`, no descritor do serviço) antes de alocar imagem; `identify` com tolerância 0
responde sem erro; `layerDefs` com SQL injetado é 400 pelo analisador `where_ast`, o mesmo da operação
`query`, e nunca chega ao banco.

⛔ NÃO medido: QGIS e ArcGIS Pro não existem nesta máquina (sem ambiente gráfico). A cláusula do portão que
pede a captura do cliente está na matriz de conformidade como `nao_medido`, com o motivo — nunca como
aprovada. A comparação da imagem com a captura do visualizador foi substituída, com a razão escrita, pela
comparação do pixel desenhado com a cor que o `drawingInfo` declara para aquela classe. ADR:
`docs/adr/20260908T0712-mapserver-e-geometryserver.md`.

## turno 8, setembro de 2026 (item L2-04-k-sync-replicas-esri: createReplica/synchronizeReplica/extractChanges/unRegisterReplica no protocolo Esri)

As quatro operações de sincronização do FeatureServer (`app/consulta/rotas_sync_esri.py`, montadas em
`/rest/services/{item_id}/FeatureServer/*`) são uma FACHADA sobre o mecanismo de réplica do L2-13-b
(`app/replica/servico.py`) — nenhum relógio novo, nenhum pacote novo: o mesmo `plat.feicao_historico`
como relógio, o mesmo ponteiro `geracao_servidor` por camada, o mesmo GeoPackage por ogr. O cliente
Field Maps fala de camada "0"; a fachada aceita "0" E o uuid de qualquer outra camada do inquilino na
mesma réplica (extensão declarada em `docs/PARIDADE.md`), aplica as edições pela porta única
`app.edicao.servico` (versão otimista obrigatória por update, conflito de réplica concorrente resolvido
pela política da réplica, update de feição apagada é conflito e nunca insert silencioso) e deriva a
idempotência de `esri-sinc:{replica_id}:{replicaClientGen}` sobre o `UNIQUE(replica_id, idempotencia)`
do L2-13-b — a repetição devolve a resposta guardada com `repetida=true` e aplica zero mudança.
`extractChanges` lê a janela SEM adiantar o ponteiro; `unRegisterReplica` apaga pelo mesmo
`servico.apagar` da casa. O job assíncrono (`async=true` → `jobId`/`statusUrl`) usa a fila do L0-05 e o
teste prova os três estados `esriJobSubmitted/Executing/Succeeded` pelas FUNÇÕES DO WORKER de produção
(`plat.job_pegar`/`plat.job_terminar` com `PLAT_DSN_WORKER`), não por forjamento de linha. Os
descritores do serviço e da camada (`rotas_servico.py`) passam a anunciar `Sync`/`syncCapabilities` —
só o que existe, sem anunciar Create/Update/Delete/Uploads.

Medidas em `tests/medidas/L2-04-k-sync-replicas-esri.json`: createReplica síncrono de 200 feições em
0,35 s (carga de 1 min 3,07 registrada no comando). 14 testes em `tests/api/test_sync_esri.py`, todos
passando. Cláusula do portão NÃO feita e nomeada lá: Field Maps/ArcGIS Pro reais sincronizando
(decisão D20 do dono — não há licença Esri nesta máquina). Registro triplo das 8 rotas novas no mesmo
commit (cruzado_casos, eventos_esperados, openapi_extra).

## turno 4, setembro de 2026 (item L2-04-d-featureserver-edicao-anexos: escrita pelo protocolo Esri sobre a porta única)

`applyEdits` (na camada e no serviço), `addFeatures`/`updateFeatures`/`deleteFeatures`, `calculate`, os seis
caminhos de anexo do protocolo Esri e `uploads/upload`, montados em
`/rest/services/{item}/FeatureServer/0/*` (`app/consulta/rotas_edicao_esri.py` + `app/consulta/esri_edicao.py`).
Nenhuma dessas rotas escreve em tabela de camada: todas traduzem o pedido Esri e chamam
`app.edicao.servico.aplicar_edicoes`, a porta única de escrita do item L2-03-a — o que vale para a API da
casa (tipo, domínio, CRS, propriedade, versão otimista) passou a valer para o cliente Esri sem cópia de regra.

Três decisões, no ADR `docs/adr/20260907T2016-featureserver-escrita-esri.md`: (1) erro sai com o código HTTP
REAL e o corpo no formato Esri, em vez do HTTP 200 com erro no corpo que a Esri usa; (2) `rollbackOnFailure`
(padrão verdadeiro) é um `SAVEPOINT` de lote, e a resposta continua trazendo o resultado feição a feição, com
`rolledBack`; (3) `calcExpression.sqlExpression` do `calculate` é traduzido para a linguagem de expressão da
casa (L2-03-f) e avaliado em Python — SQL do cliente nunca chega ao banco.

Migração `20260907T1927_featureserver_edicao.sql`: `origem` em `plat.feicao_historico` (preenchida pelo
gatilho a partir do parâmetro de sessão `plat.origem`, padrão `api`), `numero bigserial` em
`plat.feicao_anexo` (o protocolo Esri identifica anexo por inteiro; o uuid continua sendo a chave) e
`plat.esri_upload` (o bilhete do arquivo enviado antes de existir feição-pai).

Medidas em `tests/medidas/L2-04-d-featureserver-edicao-anexos.json`, com o comando exato: 26 testes de API
dedicados, todos passando. Duas cláusulas do portão NÃO foram feitas e estão nomeadas lá: edição por QGIS
(não instalado, sem ambiente gráfico) e a prova com o cliente Python `arcgis` (pacote não instalado). Ao
regerar `docs/openapi.json` apareceu que a junção dos ramos de origem havia apagado as rotas de edição, de
mapa e do FeatureServer do arquivo comitado; foram restauradas e cada um dos 29 (método, caminho) novos ganhou
caso na varredura cruzada A→B, que segue em 100 % de cobertura.
## turno 8, setembro de 2026 (item HARD-01-varredura-de-seguranca-continua: varredura de segurança no portão)

- HARD-01-varredura-de-seguranca-continua: `make seguranca` em `make check` (bandit + pip-audit + npm audit + gitleaks no histórico + trivy; ZAP baseline em `make seguranca-zap` contra instância própria), exceções com prazo em `docs/excecoes_seguranca.json`, binárias fixadas por sha256 (`deploy/ferramentas_binarias.txt`), seção 9 de docs/SEGURANCA.md gerada; consertos: defusedxml no Garage, `server_tokens off`, X-Frame-Options e Content-Security-Policy no nginx.
## turno 48, setembro de 2026 (item L3-20-narrativa-de-resultado: resumo textual por template, com revisor que marca número sem origem)

`app/amc/narrativa.py`: `narrar(documento, top_n=3)` escreve o resumo do resultado como template puro
sobre o documento canônico `plat/amc_metodo` — uma ideia por frase, número só com origem em campo do
documento, universo nas formas "X de 100" e "o resultado cobre Y unidades" (regra de escrita de
03/09). A explicação de magnitude de cada nota é aritmética declarada (peso normalizado × valor do
fator de maior contribuição). `revisar(texto, documento)` é a refutação do item automatizada: marca
`numero_sem_origem` (a varredura cobre valores, números dentro de textos e dentro de chaves),
`termo_proibido` (lista da regra de escrita) e `pontuacao_proibida`. O texto gerado passa com zero
marcações; frase fabricada ("os pesos somam 17") é marcada. Sem banco, sem relógio, sem modelo de
linguagem. Conferência à mão do texto de 3 unidades gravada em
`tests/medidas/L3-20-narrativa-de-resultado.json`.
## turno 3, setembro de 2026 (item L0-14-cli-admin: a linha de comando `plat`, um ponto de entrada só)

`scripts/plat` (vinculado em `venv/bin/plat` pelo install.sh) passa a fazer por script o que o console e o
painel de administração fazem pela tela: `inquilino criar/listar/suspender/reativar/cota`, `usuario
criar/listar/redefinir-senha/desabilitar/reabilitar`, `token criar/listar/revogar`, `camada importar`,
`job listar/cancelar/repetir`, `evento exportar` (JSON ou CSV), `saude`, `segredo rotacionar` (repassa ao
script do L7-19) e `docs`. São 28 parsers e nenhuma dependência nova: `argparse`, `urllib`,
`http.cookiejar`, `csv` e `json` da biblioteca padrão (`tests/medidas/L0-14-cli-admin.json`).

A decisão de desenho (ADR 20260907T2318) é que **a CLI é cliente da própria API**: cada subcomando faz
login e chama a mesma rota que o navegador chamaria, com o mesmo privilégio, a mesma RLS e o mesmo evento
de auditoria. Nenhum comando abre conexão com o banco. Isso é o que torna a cláusula do portão
verificável: os 19 testes de `tests/api/test_cli_admin.py` comparam, subcomando a subcomando, o efeito da
linha de comando com o da rota equivalente chamada pelo cliente da suíte — mesmo resultado e mesmo evento
gravado (13 subcomandos comparados assim).

Antes deste item havia **quatro** `scripts/plat` diferentes (master com `segredo rotacionar`, e mais um em
cada um dos ramos L7-06-c, L7-01-c e L7-33), todos com o mesmo nome de arquivo: ficou um só, e quem
precisar de um grupo novo o acrescenta em `app/cli/principal.py`.

Segurança: senha nunca entra por argumento. `--senha`, `--password`, `--pass` e `-p` são recusados antes
de qualquer chamada, com a instrução do caminho certo (`--senha-stdin` ou `--senha-arquivo`), e todo
arquivo de credencial, de senha ou de segundo fator é recusado se estiver legível por grupo ou por outros
(fecha o achado 6a do adversário do T1: senha visível no `COMMAND=` que o `sudo` grava no journal). Rodada
sem acesso ao ambiente, a CLI falha com uma linha em português, saída 2 e sem rastro de pilha — o teste
confere que nem a senha da role aparece na saída.

`docs/CLI.md` é gerado pelo próprio `argparse` (`plat docs`) e o teste reprova se estiver velho; a ajuda de
todos os comandos é em português, com teste varrendo os 28 parsers atrás de resto de inglês. O `install.sh`
ganhou a etapa `k`, que cria os inquilinos de demonstração por `plat inquilino criar --se-nao-existir`, com
a senha do administrador vindo de arquivo em modo 600.

Fora desta passagem, nomeado: `backup agora/verificar/restaurar-drill` e `item exportar/importar pacote`
(`app/backup` e o pacote do inquilino ainda não estão em master — ramos `wt/il006adumpl`, `wt/il006cresto`
e `wt/il006dexpor` na fila); e `camada importar` só foi exercitado com `--sem-esperar`, porque a base de
trilha não tem worker rodando.

## turno 4, setembro de 2026 (item L0-04-i-fonte-registrada: conector postgres_fdw — "fonte de dado registrada")

"Fonte de dado registrada" = o "Data store item" da Esri Enterprise 11.4 / o "store" do GeoServer, restrito
ao PostgreSQL/PostGIS externo. Reaproveita o modelo genérico de L6-02-a (`plat.conexao`, credencial cifrada
AES-GCM): registrar (`POST /api/conexoes` tipo `postgres_fdw`), listar tabelas do banco do cliente
(`GET /api/conexoes/{id}/tabelas`, via `pg_catalog`, nunca cópia de dado), publicar em massa
(`POST /api/conexoes/{id}/publicar-em-massa` — uma camada `camada_vetorial` referenciada por tabela, o
"bulk publish" da Esri) e ver o estado da fonte por camada (`GET /api/conexoes/{id}/camadas`). Cada tabela
publicada vira `FOREIGN TABLE` + `VIEW` (SECURITY DEFINER `plat.conexao_fdw_publicar`, migração
`20260907T0148`, porque `plat_app` não tem `CREATE` nem `USAGE` na extensão `postgres_fdw`); a view injeta
`tenant_id` constante e filtra `WHERE plat.tenant_atual() = <constante>` — o predicado de uma RLS, porque
uma tabela estrangeira não aceita política sobre coluna que não tem.

Defesa de alvo (`app/conexao/pgfdw.py`) é DIFERENTE da defesa de SSRF HTTP (`seguranca.py`): um Postgres de
cliente pode estar legitimamente numa rede privada/VPN, então só metadado de nuvem/multicast/não-especificado
são bloqueados por categoria de IP; o banco `iagro_sat` é recusado em QUALQUER host (lista explícita) e o
(host,porta,banco) do `PLAT_DSN` desta instalação é recusado por IP — duas defesas do mesmo alvo por
caminhos diferentes. `app/conexao/seguranca.py` ganhou `resolver_ips_bloqueando_categorias` (extração
pequena e genérica, reaproveitada pelos dois módulos).

Os 3 casos do adversário: (1) usuário SUPERUSER do lado do banco do cliente — registro aceito com aviso, a
escrita continua estruturalmente impossível (a view só tem `GRANT SELECT`; provado tentando `INSERT` e
recebendo `InsufficientPrivilege`); (2) aponta para o próprio `iagro_sat` — `422` antes de qualquer
gravação; (3) injeção no nome da tabela em `publicar-em-massa` — aquele item do lote vem com erro, o resto
publica normal, a tabela alvo do adversário confere intacta.

e2e completo contra um segundo Postgres real (docker `postgres:16-alpine`, 3 tabelas de dado aberto formato
IBGE): registrar → listar 3 tabelas → publicar em massa → 3 `camada_vetorial` no catálogo com dado idêntico
à origem (conferido linha a linha, view lida como a aplicação leria) → parar o container → `503
fonte_indisponivel` com mensagem, a camada permanece no catálogo com `estado_fonte: "fonte_indisponivel"` →
religar o container. Credencial nunca em claro no banco (`encconexao:v1:...`) nem em nenhuma das 3 chamadas
capturadas por `caplog`. 32 testes unitários (`tests/unit/test_pgfdw_seguranca.py`) + 5 testes de API/e2e
(`tests/api/test_pgfdw.py`, pulados sem falhar quando o docker de teste não está no ar).

Risco aceito e documentado (não escondido): `CREATE/ALTER USER MAPPING ... OPTIONS (password ...)` do
`postgres_fdw` coloca a senha em texto claro dentro da DDL executada — limitação do próprio `postgres_fdw`
(o Esri Enterprise e o GeoServer têm a mesma, guardando a senha do Data Store/Store em configuração de
servidor). Achado corrigido durante a própria trilha: a primeira versão gravava `CREATE USER MAPPING FOR
plat_app` fixo — quebra em toda base de trilha (papel `plat_t<trilha>_app`); trocado para `session_user`,
que funciona igual em produção e em qualquer trilha. `plat.item.url` exige `http(s)`; camada `postgres_fdw`
grava `url = NULL` (a origem fica em `dados.procedencia`, mesmo padrão dos outros protocolos referenciados).
`srid` do schema de `camada_vetorial` é sempre obrigatório (`minimum: 1`) mesmo sem geometria — tabela não
espacial grava `srid: 4326` por convenção neutra (documentado no ADR, não escondido). ADR
`docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md`.
## turno 8, setembro de 2026 (item L0-02-g-checagem-privilegio-papel-id: conserto trazido de wt/valida para master — ALERTA-1 do adversário HARD-03)

- L0-02-g: `_nao_conceder_alem_do_proprio` em criar/editar/lote de usuário (commit 6ad841bf de wt/valida, nunca juntado; o adversário HARD-03 mediu 6 caminhos de escalada com 200 em master), com o piso do perfil visualizador isento para o administrador restrito continuar criando visualizador; refutação por privilégio (47) distingue piso de escalada.
## turno 4, setembro de 2026 (item L0-02-z-apagar-inquilino-apaga-schema: apagar inquilino apaga o schema de dado)

- `plat.tenant_apagar_interno` faz `DROP SCHEMA d_<slug> CASCADE` na mesma transação (tabelas de camada, funções de
  tile, políticas), sob trinco de transação por slug (`plat.trinco_schema_dado`) que `plat.camada_schema_garantir`
  também toma (migração `20260907T2215_tenant_apagar_schema.sql`). A fixture `InquilinoTemporario` confere no fim que o
  schema sumiu (e apaga como plat_app se a base ainda não tiver a migração). Origem: incidente dos 1.219 schemas
  `d_zt*` (laco/handoffs/T4/INCIDENTE-schemas-zt.md).

## turno 7, setembro de 2026 (item L7-19-segredos-e-certificados: os 5 segredos fora do .env, rotação com 0 erro 5xx medido pelo k6)

Colheita da bancada `wt/segredos` (interrompida por limite de cota em 06/09) mais o conserto do que a
medição honesta achou nela. `PLAT_DSN`, `PLAT_GARAGE_ADMIN_TOKEN` e `PLAT_SECRET_ANTERIOR` saíram do
`.env` para `/etc/plat/segredos` (root 0600) entregues por `LoadCredential=` do systemd — o `.env` fica
só com configuração, e o Makefile injeta os segredos no pytest (a falta de `PLAT_DSN` na injeção tinha
deixado a suíte vermelha na coleta desde 06/09 à noite). `scripts/plat segredo rotacionar <nome>`
rotaciona os 5 segredos: PLAT_SECRET com dupla-chave (o valor antigo vira `PLAT_SECRET_ANTERIOR` por 24
h, sessões sobrevivem), PLAT_DSN e PLAT_DSN_WORKER com `ALTER ROLE` + reinício das consumidoras,
PLAT_GARAGE_ADMIN_TOKEN com restart do Garage + API, e a chave S3 de um inquilino sem reiniciar nada.
Em todos, o valor antigo deixa de autenticar (prova por `psycopg2.connect` com a senha velha depois da
rotação). A cláusula "0 erro 5xx durante a rotação" é medida pelo **k6** (v2.2.0,
`scripts/k6_saude_5xx.js`, martelo externo ao processo medido): 0 respostas 5xx em 276-762 requisições
por rotação (`tests/medidas/L7-19.json`). Chegar ao zero exigiu trocar o mecanismo depois de duas
medições ruins: "restart em cadeia" deixou 57 respostas 500 na janela entre o `ALTER ROLE` e o restart
da segunda unidade, e "parar tudo antes" deixou 1.334, porque com ativação por soquete a própria
conexão do cliente religa o serviço com a credencial velha (e `mask --runtime` não impede a religação
de unidade estática, medido em spike). O mecanismo final é uma janela `trust` de segundos no pg_hba
(só a role, só 127.0.0.1, linha marcada, removida por `finally`): velho e novo autenticam durante a
troca, e a senha velha morre quando a janela fecha. A API passa a subir por ativação por soquete
(`deploy/plat-api.socket`, uvicorn `--fd 3` com 2 workers — spike medido: conexão durante o stop
espera ~1 s e recebe 200, nunca refused/502). O adversário independente refutou a primeira versão e os achados que eram do item viraram conserto
neste mesmo turno: a janela trust abre dentro do `try` (linha nunca fica para trás no pg_hba, checado a
cada prova), a rotação de PLAT_SECRET reinicia também o worker (ele carrega a chave uma vez na subida e
decifra dentro de jobs), e o ANTERIOR expira de verdade — timer `plat-segredo-expira.timer` esvazia o
arquivo e reinicia API e worker na virada das 24 h (janela efetiva 24 h-24 h 59 min). Os achados que são
contaminação do ambiente ANTERIOR ao item (segredos reais semeados no journal por comandos de outras
operações; `.env` de worktrees de trilha com valores reais, um deles modo 664; segredos em
`/proc/<pid>/environ` de processos de trilha) ficaram registrados em `refutacao.json` e viraram itens
próprios do backlog com dono nomeado — o desenho do produto em si saiu limpo: unidades plat-* só veem os
segredos por `LoadCredential=`, repositório e histórico git com 0 ocorrências, `.env` raiz sem segredo.
Runbook em `docs/RUNBOOKS/segredos.md` (procedimento por segredo, janela trust declarada, ressalva do
garage.toml do daemon, que é da frente plataforma/pipeline e o produto nunca lê em operação).
## turno 3, setembro de 2026 (item L5-32-vistas-de-camada: vista de camada como VIEW do PostgreSQL)

## turno 3, setembro de 2026 (item L0-04-k-rota-formatos-encoberta: rota de formatos encoberta pela rota com id)

`GET /api/importacoes/formatos` estava declarada depois de `GET /api/importacoes/{id}` e era inalcançável: o
roteador casava a rota parametrizada primeiro, lia `formatos` como identificador e respondia 404
`importacao_inexistente`. A rota fixa passou para antes da parametrizada e voltou a responder 200 com a
tabela de formatos aceitos. Na mesma passagem ela passou a exigir autenticação sem privilégio
(`autenticado(escopo_token="catalogo:ler")`), que é o que já declarava no OpenAPI — alcançável e anônima ela
reprovava a varredura cruzada de inquilino. `tests/unit/test_rotas_sombreamento.py` varre a aplicação inteira
(236 rotas) e reprova qualquer rota de segmento fixo declarada depois de uma parametrizada que a cobre; a
varredura achata os nós de router incluído, sem o que só se enxergam 3 rotas no FastAPI 0.138. Nenhum outro
par encoberto na app. ADR `docs/adr/20260908T0108-ordem-de-rota-fixa-e-parametrizada.md`.

## turno 3, setembro de 2026 (item L3-19-multiescala: grades aninhadas do motor multicritério)

Construído do zero neste turno (RESGATE da sessão executora derrubada por cota só tinha a migração,
`app/multiescala/{crs,motor}.py` ainda sem rota nenhuma). Duas execuções ligadas: `POST
/api/multiescala/conjuntos/{id}/macro` gera a grade grosseira sobre a área de estudo inteira e roda a
combinação; `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina SÓ dentro das células macro
aprovadas (aritmético — a query de geração junta a região aprovada ANTES de expandir as sub-células, nunca
gera tudo para descartar depois) e roda a mesma combinação nela. `GET /api/multiescala/execucoes/{id}`
devolve o relatório por fator com `escala`/`escala_grosseira`/`razao_escala`, calculado pelo motor a partir
de `resolucao_fonte_m` (declarada no fator) x `resolucao_grade_m` (da execução) — o cliente nunca envia
esse campo. CRUD completo: `/conjuntos`, `/fatores`, `/fatores/{id}/amostras` (carga em lote),
`/execucoes`; `DELETE` de conjunto e fator (cascata pelas FKs da migração), acrescentados neste turno para
a varredura cruzada ter como limpar o que cria. Escopo de token novo `multiescala:usar`
(`app/auth/escopos.py`). ADR `docs/adr/20260906T1640-grades-aninhadas-multiescala.md`.

Um defeito de FRAMEWORK achado e corrigido, fora do arquivo deste item mas bloqueando-o:
`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` em `execute` e
`callproc`, mas não em `executemany` (psycopg2 implementa em C e não chama `execute` de volta) —
`POST /api/multiescala/fatores/{id}/amostras` falhava com `permission denied for schema plat` em qualquer
trilha. A MESMA lacuna já quebrava `POST /api/papeis` (não deste item), convertida por `erro_do_banco` num
403 "operação fora do inquilino da sessão" que parecia RLS cruzada e não era — reproduzido e confirmado
antes de mexer. Corrigido na classe (um método a mais, mesmo corpo de `execute`), vale para as duas rotas.

Um defeito do próprio teste (não do motor) achado rodando de verdade: uma área de estudo desenhada só um
pouco maior que a resolução da grade (~1,35-1,47 km sobre 1 km) produz uma célula-fatia cujo CENTRO
nominal (usado para achar o bloco de dado) cai FORA da extensão real da amostra — 2 das 4 células macro
ficavam sem nota, não por bug, porque nenhuma amostra alcançava o bloco que aquela célula ia procurar.
Corrigido aumentando a área de teste para 1.900 x 1.900 m (documentado no ADR, decisão B, para o próximo
teste desta família não tropeçar na mesma coisa).

Medido de verdade (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L3-19-multiescala.json`), 10/10 testes passam
duas vezes seguidas: grade macro de 1 km sobre estudo de 1.900x1.900 m dá 4 células, top_pct 50% aprova 2;
grade micro de 100 m (k=10) gera exatamente 200 células (2 aprovadas × 10²) contra 400 possíveis (4×10²) —
economia de 50,0%; o mesmo fator (1.000 m de escala nativa) sai `própria` na grade de 1 km e `grosseira`
na grade de 100 m da MESMA execução ligada, sem o cliente declarar nada de diferente — é a refutação do
item. `tests/api/multiescala/test_multiescala.py`: 10/10.

**Fora do portão deste turno, registrado no ADR**: `docs/openapi.json` comitado não inclui
`/api/multiescala/*` (regeneração é pendência do gerente após os merges); os 11 casos da varredura cruzada
já estão em `tests/api/cruzado_casos.py` (conferidos à mão contra o app rodando — todas as 11 rotas
recusam ou isolam o cross-tenant corretamente) e passam a valer em `test_cobertura_100_por_cento`/
`test_rota_nao_cruza` assim que `make openapi` rodar contra a árvore juntada. `L3-01-b-unidades`
(dependência declarada) segue PARCIAL num ramo não juntado (`wt/amc`); este item não depende dele em
código (CRS resolvido de forma própria em `app/multiescala/crs.py`), só na hipótese conceitual.
## turno 5, setembro de 2026 (item L5-01-a-layout-paginas: páginas e layout do app)

Sobre o editor de arrasto do L5-08: paleta nova (`web/js/editor/paleta_paginas.js`) com `pagina` (tela cheia
× rolável; `caminho`/`titulo`/`ordem`/`oculta`/`inicial`), `cabecalho`, `rodape`, `menu`, os widgets de
layout do Experience Builder (`linha`, `coluna`, `grade`, `acordeao`, `painel_fixo`, `painel_lateral`) e
`janela` (`modal`/`ancorada`) + `secao_vistas`/`vista`. Executor novo (`web/js/executor/{executor,paginas}.js`
+ tela `/executar?item=<id>&pagina=<caminho>`, `app/paginas.py`) que renderiza o MESMO documento como app de
verdade: nav entre páginas por `history.pushState`, `<dialog>` nativo para janela modal, painel lateral que
recolhe sem `display:none`, grade em CSS Grid `fr`. `web/js/editor/tela.js` escolhe a paleta pelo `tipo` do
item (`app` → paleta de páginas; o resto continua com a paleta comum do L5-08) — única mudança num arquivo
que outro item também toca.

Medido (`tests/medidas/L5-01-a-layout-paginas.json`, e2e `tests/e2e/test_layout_paginas.py`): app de 2
páginas (Central tela-cheia com mapa, Detalhes rolável com painel lateral/grade/janela) montado só por
arrasto (2.245,1 ms); menu navega e a URL muda por página, F5 reabre na página certa; painel lateral
recolhe/expande; grade mantém a razão 8:4 entre dois filhos em 1200 px (2,016) e 600 px (2,033) — diferença
0,017; janela modal abre pelo botão e fecha por Esc (`<dialog>` nativo). Refutação do adversário: 6 níveis
alternando linha/coluna, com irmão ao lado do 1º nível, em 3 larguras de viewport (1280/800/320) — 0 px de
estouro horizontal e nenhum nível com largura, altura, `display` ou `visibility` zerados (a correção que fez
isso passar foi `min-width:0`/`min-height:0` em todo item flexível, ADR
`20260907T1355-paginas-e-layout-do-app`). Achado corrigido no caminho: `drag_and_drop` sobre o SELETOR do
contêiner-alvo mira o CENTRO da caixa — quando o contêiner já tem um filho de largura 12/12, o centro cai
sobre o filho e o `drop` do HTML5 é entregue a ele, não ao contêiner (o novo nó entra um nível mais fundo do
que o pedido); o teste agora solta sempre no FUNDO do contêiner, como o e2e do L5-08 já fazia na raiz.
Paridade contra "Add and manage pages" e "Layout widgets" (doc EXB) em `docs/PARIDADE.md`.
## turno 5, setembro de 2026 (item L5-15-vista-movel-responsivo: vista móvel e pré-visualização por dispositivo)

Visualizador em tempo de execução (`/visualizar?item=<id>`, `web/js/visualizador/visualizador.js`, sem
nenhuma primitiva de edição) sobre o mesmo documento do L5-05/L5-08: reflow automático de grade de 12
colunas para 1 coluna a ≤ 600 px (puro CSS, `web/estilo/visualizador.css`), mapa sempre presente com
bounding box não-nulo em qualquer largura, e widget `tabela` trocando de elemento semântico (`<table>` para
`<ul>`) na mesma faixa — sem inventar dado, só a propriedade `linhas_por_pagina` que o widget já grava.
Vista móvel MANUAL nova em `corpo.vista_movel` (esquema v3, migração `20260907T1505_vista_movel.sql`, cadeia
de leitura v2→v3 em `documento.py`): só nó de RAIZ (D1 do item) pode ter `oculto`/`ordem`/`largura_colunas`
próprios para o celular, e essa lista PREVALECE sobre o reflow quando `manual: true` — validado no mesmo
lugar que a referência pendente de `ligacoes` (`validar_grafo`, regras `referencia_pendente` e
`vista_movel_fora_da_raiz`). Painel "Vista móvel" novo no construtor (`editor.js`) edita isso por
checkbox/número, sem gesto nenhum.

Pré-visualização por dispositivo no construtor (`web/js/editor/pre_visualizacao.js`): iframe de MESMA
ORIGEM (precedente Puck) com três larguras fixas (celular 375, tablet 768, desktop 1440) recebendo o
documento em edição por `postMessage`, sem depender de salvar. Arrasto por TOQUE de verdade acrescentado a
`arrasto.js` (Pointer Events com limiar de 8 px e ghost seguindo o dedo, registrado ao lado do HTML5 DnD que
o L5-08 já tinha e que nunca dispara em toque) — paleta e cabeçalho do nó agora arrastam com um dedo real,
além do botão "Adicionar"/menu "mover para" que o L5-08 já provava.

Medido (`tests/medidas/L5-15-vista-movel-responsivo.json`, e2e `tests/e2e/test_vista_movel_responsivo.py`
contra a base da trilha): as 3 vistas (Pixel 7, iPad (gen 7), 1440×900) do mesmo `/visualizar?item=` não têm
rolagem horizontal e mostram o mapa com bounding box positivo; a tabela vira lista só ≤ 600 px (Pixel 7),
continua tabela em 810 px (iPad) e 1440 px. Vista móvel manual com um nó oculto e outro com `ordem: 0`
prevalece sobre a ordem natural do documento — o nó oculto nem aparece no DOM. Arrasto por toque no iPad
(148,9 ms) monta o mesmo tipo de nó que o menu "Adicionar" monta sem gesto nenhum. Refutação do adversário
(360×640, documento SEM vista móvel manual): os três nós de raiz continuam visíveis, com bounding box
positivo e dentro da largura da tela — 0 cortado, 0 inacessível.

Achado de ambiente corrigido no próprio item: `criarEditor` chama `aoMudar` uma vez, SÍNCRONO, antes de
devolver (primeiro desenho) — declarar a referência da pré-visualização como `const` lida DEPOIS de montar
o editor travava a tela inteira em "Cannot access before initialization" sem erro nenhum no console (só
`pageerror`, silencioso para quem só olha `console.error`); virou `let` lido por closure.

## turno 4, setembro de 2026 (item L5-08-editor-arrasto: primitivas de edição compartilhadas pelos construtores)

Editor de arrasto próprio em `web/js/editor/` (5 módulos, 43.771 bytes medidos; 0 byte de biblioteca de
arrasto — `web/vendor/VERSOES.txt` segue sem SortableJS, dnd-kit ou GridStack) e tela `/construtor?item=<id>`
sobre o documento do L5-05. Paleta→tela e tela→tela por HTML5 Drag and Drop; alça de largura por Pointer
Events com `setPointerCapture`; árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e
menu "mover para" para quem só tem toque. Largura sempre em COLUNAS da grade de 12, nunca em pixel.

Medido (`tests/medidas/L5-08-editor-arrasto.json`, e2e `tests/e2e/test_editor_arrasto.py` contra a base da
trilha): o MESMO layout de 5 componentes montado só por arrasto (787,5 ms) e só por teclado e menus
(134,0 ms) grava dois documentos idênticos — diferença 0 depois de trocar cada ULID por `n1..nN` na ordem de
profundidade (o ULID é aleatório por construção, D2). Redimensionar por arrasto levou o mapa de 8 para 4
colunas nos dois caminhos; `"px"` não aparece no documento gravado. A árvore reflete o aninhamento
(aria-level 1/2/2/1/1). O painel recusa zoom 99 num campo `maximum: 22`: mensagem no campo, `aria-invalid`,
e o documento salvo depois continua com 12. Refutação do adversário no mesmo arquivo: soltar um contêiner
dentro de um descendente dele é recusado com motivo ("dentro de si"), soltar fora da tela não muda nada, o
menu de mover não oferece destino dentro do próprio nó, e o layout inteiro se monta só por toque no viewport
Pixel 7 (onde o HTML5 Drag and Drop não dispara). 0 erro de console em todos os caminhos.

Achado de ambiente: esta é a primeira tela que grava por `fetch` sob cookie a partir do navegador, e por
isso a primeira a bater no 403 `origem_invalida` quando `PLAT_URL_PUBLICA` não é a origem servida — os e2e
anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`. Em produção as duas
coincidem; no ambiente da trilha o nginx local reescreve o cabeçalho. ADR 20260907T0302.
## turno 3, setembro de 2026 (item L2-04-j-conformidade-clientes-e-paridade: matriz de conformidade viva)

- `POST /api/camadas/{id}/vistas` cria uma vista da camada: filtro próprio, campos escondidos, só leitura ou
  editável, extensão limitada, estilo e janela de atributos próprios. `GET`/`PUT /api/vistas/{id}` leem e
  refazem a definição. Tela em `/vista-de-camada`, com o campo indo para "ocultos" por arrasto ou por clique.
- A vista é uma VIEW em `d_<slug>` com `security_invoker = true`, registrada como item `vista_de_camada`
  (tipo reservado desde `011_catalogo.sql`, agora no esquema v2). Campo oculto não é filtrado na saída: ele
  não existe na relação consultada, então `outFields=*` não o alcança. O filtro é congelado na definição da
  view, então `where=1=1` do cliente só se soma a ele.
- FeatureServer, descritor de serviço, diretório Esri, OGC API Features, WFS e o mapa web servem a vista sem
  código novo: o filtro por tipo virou `TIPOS_CAMADA` em `app/catalogo/tipos.py`.
- Vista `somente_leitura` recusa escrita com 403 na porta única (`app.edicao.servico`), antes do atalho de
  administrador. Vista editável nasce `WITH CASCADED CHECK OPTION`, e a violação vira 422 `fora_da_vista`.
- Compartilhar a vista não compartilha a camada-mãe: a ficha pública da vista deixa de trazer
  `campos_ocultos` e `camada_id`, e um token com escopo `camada:ler:<vista>` recebe 403 na camada-mãe.
- Dívidas trazidas junto e fechadas em arquivo novo: `plat.feicao_historico_registrar()` e
  `plat.origem_atual()` tinham EXECUTE para PUBLIC; e `plat.camada_schema_garantir` refazia o
  `GRANT USAGE ON SCHEMA` a cada chamada, o que fazia duas trilhas escreverem a mesma linha de `pg_namespace`
  ao mesmo tempo ("tuple concurrently updated"). Agora o GRANT só corre quando falta.

## turno 3, setembro de 2026 (item L3-19-multiescala: grades aninhadas do motor multicritério)

Construído do zero neste turno (RESGATE da sessão executora derrubada por cota só tinha a migração,
`app/multiescala/{crs,motor}.py` ainda sem rota nenhuma). Duas execuções ligadas: `POST
/api/multiescala/conjuntos/{id}/macro` gera a grade grosseira sobre a área de estudo inteira e roda a
combinação; `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina SÓ dentro das células macro
aprovadas (aritmético — a query de geração junta a região aprovada ANTES de expandir as sub-células, nunca
gera tudo para descartar depois) e roda a mesma combinação nela. `GET /api/multiescala/execucoes/{id}`
devolve o relatório por fator com `escala`/`escala_grosseira`/`razao_escala`, calculado pelo motor a partir
de `resolucao_fonte_m` (declarada no fator) x `resolucao_grade_m` (da execução) — o cliente nunca envia
esse campo. CRUD completo: `/conjuntos`, `/fatores`, `/fatores/{id}/amostras` (carga em lote),
`/execucoes`; `DELETE` de conjunto e fator (cascata pelas FKs da migração), acrescentados neste turno para
a varredura cruzada ter como limpar o que cria. Escopo de token novo `multiescala:usar`
(`app/auth/escopos.py`). ADR `docs/adr/20260906T1640-grades-aninhadas-multiescala.md`.

Um defeito de FRAMEWORK achado e corrigido, fora do arquivo deste item mas bloqueando-o:
`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` em `execute` e
`callproc`, mas não em `executemany` (psycopg2 implementa em C e não chama `execute` de volta) —
`POST /api/multiescala/fatores/{id}/amostras` falhava com `permission denied for schema plat` em qualquer
trilha. A MESMA lacuna já quebrava `POST /api/papeis` (não deste item), convertida por `erro_do_banco` num
403 "operação fora do inquilino da sessão" que parecia RLS cruzada e não era — reproduzido e confirmado
antes de mexer. Corrigido na classe (um método a mais, mesmo corpo de `execute`), vale para as duas rotas.

Um defeito do próprio teste (não do motor) achado rodando de verdade: uma área de estudo desenhada só um
pouco maior que a resolução da grade (~1,35-1,47 km sobre 1 km) produz uma célula-fatia cujo CENTRO
nominal (usado para achar o bloco de dado) cai FORA da extensão real da amostra — 2 das 4 células macro
ficavam sem nota, não por bug, porque nenhuma amostra alcançava o bloco que aquela célula ia procurar.
Corrigido aumentando a área de teste para 1.900 x 1.900 m (documentado no ADR, decisão B, para o próximo
teste desta família não tropeçar na mesma coisa).

Medido de verdade (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L3-19-multiescala.json`), 10/10 testes passam
duas vezes seguidas: grade macro de 1 km sobre estudo de 1.900x1.900 m dá 4 células, top_pct 50% aprova 2;
grade micro de 100 m (k=10) gera exatamente 200 células (2 aprovadas × 10²) contra 400 possíveis (4×10²) —
economia de 50,0%; o mesmo fator (1.000 m de escala nativa) sai `própria` na grade de 1 km e `grosseira`
na grade de 100 m da MESMA execução ligada, sem o cliente declarar nada de diferente — é a refutação do
item. `tests/api/multiescala/test_multiescala.py`: 10/10.

**Fora do portão deste turno, registrado no ADR**: `docs/openapi.json` comitado não inclui
`/api/multiescala/*` (regeneração é pendência do gerente após os merges); os 11 casos da varredura cruzada
já estão em `tests/api/cruzado_casos.py` (conferidos à mão contra o app rodando — todas as 11 rotas
recusam ou isolam o cross-tenant corretamente) e passam a valer em `test_cobertura_100_por_cento`/
`test_rota_nao_cruza` assim que `make openapi` rodar contra a árvore juntada. `L3-01-b-unidades`
(dependência declarada) segue PARCIAL num ramo não juntado (`wt/amc`); este item não depende dele em
código (CRS resolvido de forma própria em `app/multiescala/crs.py`), só na hipótese conceitual.
## turno 5, setembro de 2026 (item L5-01-a-layout-paginas: páginas e layout do app)

Sobre o editor de arrasto do L5-08: paleta nova (`web/js/editor/paleta_paginas.js`) com `pagina` (tela cheia
× rolável; `caminho`/`titulo`/`ordem`/`oculta`/`inicial`), `cabecalho`, `rodape`, `menu`, os widgets de
layout do Experience Builder (`linha`, `coluna`, `grade`, `acordeao`, `painel_fixo`, `painel_lateral`) e
`janela` (`modal`/`ancorada`) + `secao_vistas`/`vista`. Executor novo (`web/js/executor/{executor,paginas}.js`
+ tela `/executar?item=<id>&pagina=<caminho>`, `app/paginas.py`) que renderiza o MESMO documento como app de
verdade: nav entre páginas por `history.pushState`, `<dialog>` nativo para janela modal, painel lateral que
recolhe sem `display:none`, grade em CSS Grid `fr`. `web/js/editor/tela.js` escolhe a paleta pelo `tipo` do
item (`app` → paleta de páginas; o resto continua com a paleta comum do L5-08) — única mudança num arquivo
que outro item também toca.

Medido (`tests/medidas/L5-01-a-layout-paginas.json`, e2e `tests/e2e/test_layout_paginas.py`): app de 2
páginas (Central tela-cheia com mapa, Detalhes rolável com painel lateral/grade/janela) montado só por
arrasto (2.245,1 ms); menu navega e a URL muda por página, F5 reabre na página certa; painel lateral
recolhe/expande; grade mantém a razão 8:4 entre dois filhos em 1200 px (2,016) e 600 px (2,033) — diferença
0,017; janela modal abre pelo botão e fecha por Esc (`<dialog>` nativo). Refutação do adversário: 6 níveis
alternando linha/coluna, com irmão ao lado do 1º nível, em 3 larguras de viewport (1280/800/320) — 0 px de
estouro horizontal e nenhum nível com largura, altura, `display` ou `visibility` zerados (a correção que fez
isso passar foi `min-width:0`/`min-height:0` em todo item flexível, ADR
`20260907T1355-paginas-e-layout-do-app`). Achado corrigido no caminho: `drag_and_drop` sobre o SELETOR do
contêiner-alvo mira o CENTRO da caixa — quando o contêiner já tem um filho de largura 12/12, o centro cai
sobre o filho e o `drop` do HTML5 é entregue a ele, não ao contêiner (o novo nó entra um nível mais fundo do
que o pedido); o teste agora solta sempre no FUNDO do contêiner, como o e2e do L5-08 já fazia na raiz.
Paridade contra "Add and manage pages" e "Layout widgets" (doc EXB) em `docs/PARIDADE.md`.
## turno 4, setembro de 2026 (item L5-12-acessibilidade-i18n-construtores: acessibilidade e idioma da base dos construtores)

Sobre o editor de arrasto do L5-08: dicionário de idioma (`web/js/i18n/{pt-BR,en,es}.json`, paridade total de
chave e campo de substituição `{nome}` testados estaticamente), seletor de idioma dentro de `/construtor` que troca o dicionário
na hora (sem `location.reload()`; `document.documentElement.lang` atualizado também em `base/i18n.js`, WCAG
3.1.1), quinto painel de Ações (`documento.js::ligar/desligar` sobre `corpo.ligacoes`, que já existia vazia
desde o L5-08) e botão Publicar (`POST /api/itens/{id}/versoes/{n}/publicar`, rota que já existia). A
"árvore" de estrutura deixou de anunciar `role=tree`/`treeitem` (o componente não navega por seta entre
itens, e `role=tree` recusa botão/select como descendente em qualquer profundidade — achado do axe-core) e
passou a `role=list`/`listitem`, com `aria-level` no `<li>` (que o suporta) e o nível também por extenso no
`aria-label` do item. Corrigido de quebra: `--i-acento` do tema claro "instrumento" media 4,36:1 contra
`--i-acento-texto` — abaixo do 4,5:1 AA — escurecido para 4,74:1 (`web/estilo/tokens.css`, afeta toda tela
`instrumento` em modo claro, não só o construtor).

Medido (`tests/medidas/L5-12-acessibilidade-i18n-construtores.json`, e2e `tests/e2e/
test_construtor_acessibilidade.py`, 9 testes): axe-core (`resultTypes: violations`) zero violação
`critical`/`serious` em `/construtor` para item `app` e `painel`, com 3 widgets montados; fluxo fim-a-fim só
por `page.focus`/`page.keyboard` (3 widgets, ligar ação por type-ahead nativo do `<select>`, salvar,
publicar) grava `versao_publicada == versao_atual`; troca de idioma comprovadamente sem navegação (marcador
em `window` sobrevive à troca); zero chave crua visível na tela nos 3 idiomas. Refutação do adversário:
árvore de acessibilidade do playwright percorrida em `/construtor` (app e painel) — zero controle sem nome
computado (aria-label/aria-labelledby/texto/title/`label` implícito). `test_i18n_construtor_paridade.py`
(5 testes estáticos, sem navegador) trava a paridade dos três catálogos e que toda chave `construtor.*` do
código exista no dicionário. `test_editor_arrasto.py` (L5-08, já ENTREGUE) segue 5/5 — uma linha ajustada
porque `aria-level` mudou de elemento (razão acima), valor e aninhamento inalterados. ADR 20260907T1533.

## turno 4, setembro de 2026 (item L5-08-editor-arrasto: primitivas de edição compartilhadas pelos construtores)

Editor de arrasto próprio em `web/js/editor/` (5 módulos, 43.771 bytes medidos; 0 byte de biblioteca de
arrasto — `web/vendor/VERSOES.txt` segue sem SortableJS, dnd-kit ou GridStack) e tela `/construtor?item=<id>`
sobre o documento do L5-05. Paleta→tela e tela→tela por HTML5 Drag and Drop; alça de largura por Pointer
Events com `setPointerCapture`; árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e
menu "mover para" para quem só tem toque. Largura sempre em COLUNAS da grade de 12, nunca em pixel.

Medido (`tests/medidas/L5-08-editor-arrasto.json`, e2e `tests/e2e/test_editor_arrasto.py` contra a base da
trilha): o MESMO layout de 5 componentes montado só por arrasto (787,5 ms) e só por teclado e menus
(134,0 ms) grava dois documentos idênticos — diferença 0 depois de trocar cada ULID por `n1..nN` na ordem de
profundidade (o ULID é aleatório por construção, D2). Redimensionar por arrasto levou o mapa de 8 para 4
colunas nos dois caminhos; `"px"` não aparece no documento gravado. A árvore reflete o aninhamento
(aria-level 1/2/2/1/1). O painel recusa zoom 99 num campo `maximum: 22`: mensagem no campo, `aria-invalid`,
e o documento salvo depois continua com 12. Refutação do adversário no mesmo arquivo: soltar um contêiner
dentro de um descendente dele é recusado com motivo ("dentro de si"), soltar fora da tela não muda nada, o
menu de mover não oferece destino dentro do próprio nó, e o layout inteiro se monta só por toque no viewport
Pixel 7 (onde o HTML5 Drag and Drop não dispara). 0 erro de console em todos os caminhos.

Achado de ambiente: esta é a primeira tela que grava por `fetch` sob cookie a partir do navegador, e por
isso a primeira a bater no 403 `origem_invalida` quando `PLAT_URL_PUBLICA` não é a origem servida — os e2e
anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`. Em produção as duas
coincidem; no ambiente da trilha o nginx local reescreve o cabeçalho. ADR 20260907T0302.
## turno 4, setembro de 2026 (item L2-04-servicos-esri-ogc: diretório do FeatureServer, OGC API Features e WFS 2.0)

Construído em volta da operação `query` do FeatureServer (item L2-04-c, `wt/fsquery`, ADR 0018) sem reescrevê-la:
`app/consulta/rotas_servico.py` (descritor de serviço `.../FeatureServer?f=json` e de camada `.../FeatureServer/0
?f=json` — `fields`, `geometryType`, `objectIdField`, `fullExtent`), `app/consulta/rotas_ogc_features.py` (OGC API
Features Part 1: landing, conformance, collections, items com bbox/limit/offset, item único, GeoJSON puro) e
`app/consulta/rotas_wfs.py` (WFS 2.0 KVP: GetCapabilities validado pelo cliente real `owslib.wfs.WebFeatureService`,
DescribeFeatureType mínimo, GetFeature em GeoJSON e GML 3.2 simples). `applyEdits`/anexos/`queryRelatedRecords`/
`relationships` ficam de fora — dependem de L2-03-edicao e L2-10-b, nenhum construído (ADR 0019).

Bateria de 13 ataques (item_id com aspas/comentário SQL/`;`, bbox com sub-select/`pg_sleep()`/função não prevista,
BBOX do WFS com injeção, `REQUEST` desconhecida, `feature_id` não inteiro, unicode no item_id, cross-tenant nas 3
raízes): **13/13 recusados com 400/404, nenhum 500**. Dois achados corrigidos no mesmo turno: (1) `item_id::uuid`
sem validar antes deixava o Postgres levantar exceção sem handler → 500 real, inclusive na `/query` original do
L2-04-c — corrigido com validação de UUID compartilhada; (2) landing/conformance do OGC API Features respondiam 200
para item de outro inquilino (sem vazar dado, mas sem checar posse) — corrigido tocando `plat.item` sob RLS antes de
responder. `docs/PARIDADE.md` e `tests/medidas/L2-04-servicos-esri-ogc.json` têm a tabela cláusula a cláusula.

Fora do turno: QGIS/ArcGIS Pro/AGOL reais carregando o serviço (sem ambiente gráfico nesta máquina, mesma limitação
já registrada para L2-04-c e para Chrome headless); OGC API Features Part 3 (CQL2), WFS-T; GML validado contra o
XSD de referência do OGC.

## turno 3, setembro de 2026 (item L2-04-b-featureserver-catalogo-metadados: diretório de serviços Esri por token)

- Diretório de serviços compatível com Esri em `/svc/{token}/rest/...`: `rest/info`, `rest/generateToken`,
  `rest/services` (pastas do catálogo), `rest/services/{pasta}`, `FeatureServer`, `FeatureServer/{id}`,
  `FeatureServer/layers`, `FeatureServer/info/itemInfo` e `FeatureServer/info/metadata` (ISO 19139).
  O token vai no caminho porque é uma URL que se entrega e o cliente navega sozinho a partir dela;
  a consequência está declarada no ADR `20260907T1955-diretorio-servicos-esri-por-token.md`.
- O FeatureServer não foi reescrito: `app/consulta/rotas_servico.py` passou a expor
  `descritor_do_servico`/`descritor_da_camada` e o diretório as chama. O descritor da camada ganhou
  `indexes` (lidos de `pg_index`), `editFieldsInfo`, `types`/`subtypes`/`typeIdField`, `timeInfo`,
  `ownershipBasedAccessControlForFeatures` e `domain` por campo. `currentVersion` foi de 11.3 para 11.4.
- `app/consulta/formato_esri.py`: `f=json|pjson|html` e `callback` (JSONP) num lugar só. `f` desconhecido
  é 400 e nunca 500; nome de callback fora de identificador simples é recusado, nunca ecoado.
- `app/consulta/renderizador.py`: estilo MapLibre → `drawingInfo`. Cor constante vira `simple`,
  `["match", …]` vira `uniqueValue`, `["step", …]` vira `classBreaks`, `layout.text-field` vira
  `labelingInfo`. Expressão fora desses casos não é aproximada: sai `simple` cinza com o motivo.
- `app/consulta/cors_servicos.py`: CORS aberto em `/svc`, `/ogc` e `/tiles` — e só. Em `/api` a
  credencial é o cookie de sessão, e abrir ali seria falsificação de requisição entre sítios legível.
- O `drawingInfo` lê a relação `estilo_de_camada` (item de tipo `estilo` → camada), declarada pelo
  `PUT /api/itens/{estilo}/relacoes` que já existia; nada foi acrescentado ao catálogo por causa disto.
- Fica declarado como ausente, não simulado: `fields[].domain` nulo, `types`/`subtypes`/`relationships`
  vazios e `capabilities` só `Query` — as linhas L2-10-a, L2-10-b e L2-03-a não estão nesta base.
## turno 5, setembro de 2026 (item L2-03-edicao: fechamento — dois achados corrigidos, junção do turno 4)
## turno 8, setembro de 2026 (item L2-07-e-odk-central-ponte: ponte opcional com o ODK Central)
## turno 4, setembro de 2026 (item L2-04-d-featureserver-edicao-anexos: escrita pelo protocolo Esri sobre a porta única)

Uma equipe que já coleta no ODK Collect passa a alimentar as camadas da plataforma sem trocar de aplicativo.
`POST /api/odk/pontes` publica no ODK Central a MESMA planilha que gerou o formulário do L2-07-b (conferida
campo a campo antes de sair) e guarda a ligação em `plat.odk_ponte`;
`POST /api/odk/pontes/{id}/sincronizar` — e o job `odk.sincronizar`, no relógio do inquilino — lê os envios por
OData, baixa os anexos, e grava tudo pela porta única de escrita do formulário, com `relevant`/`constraint`/
`calculation` reavaliados no servidor. A idempotência é o `instanceID` do ODK em `plat.odk_envio`: sincronizar
três vezes seguidas deixa 20 feições e 0 duplicatas (medido em `tests/medidas/L2-07-e-odk-central-ponte.json`).
Envio recusado fica gravado com o motivo, nunca some. `GET /api/odk/pontes/{id}/entidades/{dataset}` traz as
Entities do Central como lista de escolhas com as propriedades como colunas de filtro (a cascata do L2-07-b).
A conexão é do tipo novo `odk_central` (L6-02-a): URL contra SSRF, token cifrado, e erro de credencial marcando
a saúde da conexão na tela que já existe.

1. `app/edicao/combinar.py::unir` checava `versao` declarada ANTES de checar existência/acesso do id — um
   id inexistente ou de outro inquilino, quando listado depois de um id existente sem `versao`, nunca
   chegava a 404 (ficava preso em 422 `versao_ausente`). Corrigido para existência de todos os ids primeiro,
   depois versão de todos (`tests/api/test_edicao_dividir_unir.py::test_unir_sem_declarar_versao_de_uma_das_feicoes_e_422`
   fecha o buraco original: `versoes` incompleto não pode mais deixar uma origem sem checagem de
   concorrência).
2. `limites.ANEXO_TAMANHO_MAX` (10 MiB) igual ao teto de corpo do middleware (`CORPO_MAX_PADRAO_BYTES`,
   também 10 MiB) — como o anexo viaja em JSON com o conteúdo em base64 (~4/3 de inchaço), o 413 genérico
   do corpo sempre disparava antes do 422 `anexo_grande` específico rodar; o limite documentado de anexo
   era, na prática, letra morta. Reduzido para 7 MiB, com folga sob o teto de corpo mesmo codificado
   (`tests/api/test_edicao_historico_anexos.py::test_anexo_no_teto_real_ainda_da_anexo_grande_nao_corpo_grande`).
⛔ O ODK Central de verdade NÃO foi usado: ele se instala por docker, docker não sobe nesta máquina e o disco
está em 96 %. A prova é contra um dublê HTTP da API documentada (`tests/odk_central_duble.py`); o que o dublê
não prova está listado no ADR `docs/adr/20260908T1130-ponte-odk-central.md`, seção "Prova".

## turno 4, setembro de 2026 (item L6-02-a-modelo-conexao-e-seguranca)

- O "Bearer da casa" passa a ser provado onde ele nasce, não só dentro de `buscar_seguro`:
  `tests/unit/test_conexao_credencial_chamadores.py` (job `conexoes.saude_verificar`) e
  `tests/api/test_conexoes_credencial_saltos.py` (rota `POST /api/conexoes/{id}/testar`, pela API de verdade,
  com varredura por texto na resposta e no registro de log). Seis guardas `xfail(strict=True)` afirmam o
  comportamento VULNERÁVEL: enquanto o conserto estiver de pé elas falham; se alguém o desfizer, elas passam
  (XPASS) e a suíte fica vermelha.
- `app/garage.py` deixa de seguir `Location` automaticamente nas duas chamadas que mandam `Authorization`
  (`allow_redirects=False`): o outro caminho da casa que montava credencial e seguia redirecionamento.
## turno 8, setembro de 2026 (item L2-07-b-formulario-de-coleta-xlsform: XLSForm vira formulário que grava feição)

`POST /api/formularios/xlsform` importa uma planilha XLSForm (pyxform) como item `formulario` do catálogo,
cria a camada de destino (e uma camada filha por `begin repeat`, com `pai_globalid`) e traduz relevant,
constraint, calculation e choice_filter do XPath para a linguagem de expressão própria por tabela de função
com estado feito/parcial/fora (regex, date, uuid e position ficam fora, com o trecho no aviso; tabela em
`GET /api/formularios/equivalencia`). A tela `/coleta?formulario=<id>` desenha texto, inteiro, decimal, data,
hora, data-hora, select_one com busca, select_multiple, cascata de 3 níveis, grupos e repetições, guarda
rascunho a cada mudança e envia; o servidor recalcula, reaplica relevância (campo não relevante vai NULL),
restrições e obrigatoriedade e só então grava pela `POST /api/camadas/{id}/edicoes`. Cálculo circular é 422
`dependencia_circular` na importação e no navegador. Conferido: 102 vetores XLSForm nos dois avaliadores
(`tests/expressoes/vetores_xlsform.json`), motor JS = motor Python em 13 respostas dos 5 formulários de
teste, 11 testes de API. Conserto no caminho: gatilho de histórico de feição (L2-03-d) quebrava com geometria
nula (`20260907T2020_historico_geom_nula.sql`). Fora do brief: geoponto com GPS, foto, áudio, assinatura,
código de barras, fila off-line.

Histórico e restauração são novos no banco: `plat.feicao_historico` + gatilho genérico
`feicao_historico_registrar()` ligado por `plat.camada_preparar` a TODA tabela de camada (não só a
escrita que passa pela API — SQL direto, importação e réplica também ficam registrados), migração
`20260907T1025`. Restaurar reaplica pela MESMA porta de escrita (`_inserir`/`_atualizar` de
`app.edicao.servico`) — feição existente vira `UPDATE`, feição apagada vira `INSERT` com o MESMO
`globalid` (referência externa nunca quebra); a própria restauração grava um marcador
`operacao='restaurar'` a mais no histórico, que nunca é reescrito.

Anexos (`plat.feicao_anexo`, migração `20260907T1035`): limite de tamanho e de tipo aplicados no
SERVIDOR em duas etapas (tamanho da string base64 antes de decodificar, depois o tamanho real) e
contra o conteúdo de fato (item L7-03-b) — um PDF disfarçado de PNG é recusado mesmo com
`content_type` mentindo. Objeto guardado no Garage por trás do adaptador já existente (`app.objetos`).

Dividir/unir (`app/edicao/combinar.py`): geometria estrutural nunca sai do MVT (recortado/generalizado
por tile) — as duas operações leem a geometria exata do banco e usam `ST_Union`/`ST_LineMerge`/
`ST_LineSubstring`. `unir` funciona para qualquer família de geometria; `dividir` está escopado a
LineString/MultiLineString de uma parte só nesta passagem (dividir polígono por linha de corte fica
de fora, registrado no ADR, não escondido).

Dois defeitos de infraestrutura achados e corrigidos nesta rodada (não só no código do item):
`app/garage.py::criar_chave` devolvia um dicionário sem `accessKeyId` no caminho de reaproveitamento
(`ListKeys` usa a chave `id`, `CreateKey` usa `accessKeyId`) — crashava com `KeyError` em vez de um
erro que diz o que aconteceu; e `docs/gerar_limites.py` ficaria não determinístico se um limite fosse
guardado como `frozenset` (a ordem de iteração de um set do Python varia entre execuções) — corrigido
trocando `ANEXO_TIPOS_PERMITIDOS` para tupla ordenada antes de existir um segundo caso.

ADR: `docs/adr/20260907T1123-historico-restauracao-anexos-feicao.md`. Medidas em
`tests/medidas/L2-03-edicao.json` — sem cláusula numérica de tempo neste item; a suíte dedicada (75
testes de API/unit) e o e2e dedicado (6 cláusulas no chromium do playwright, 0 erro de console) estão
registrados lá com o comando exato. Fronteira honesta e vereditos completos no handoff do item.

## turno 3, setembro de 2026 (item L2-03-a-api-edicao-transacional: edição transacional de feições — única porta de escrita)

`POST /api/camadas/{id}/edicoes` (`app/edicao/`): equivalente do `applyEdits` da Esri e, a partir
daqui, a única porta de escrita de feição para navegador, PWA, FeatureServer (L2-04-d) e OGC
(L2-04-g). Corpo com `adicionar`/`atualizar`/`apagar` numa transação — tudo-ou-nada por padrão
(`modo=transacao`), ou `modo=parcial` com `SAVEPOINT` por feição, devolvendo resultado feição a
feição (como o `applyEdits` com `rollbackOnFailure=false`). Roda direto contra a tabela de camada
`d_<slug>.c_<uuid16>` que `plat.camada_preparar` (029_ingestao_vetor.sql) já cria — nenhuma tabela
nova (migração 20260906T1859, bump do esquema `camada_vetorial` v2→v3, só propriedades opcionais).

Validação sempre no servidor: tipo de geometria e SRID da coluna (com a mesma promoção
Point/LineString/Polygon → Multi* que `app/ingestao/carregar.py` usa na carga); `ST_IsValid`, com
`ST_MakeValid` só quando `corrigir_geometria=true` (sem isso, polígono inválido é 422); domínio de
atributo por `dados.regras_campo` (obrigatório, somente-leitura, lista de valores ou
mínimo/máximo — mecanismo próprio deste item; quando o L2-10-a-dominios-subtipos, entregue noutra
trilha, for integrado, ganha uma segunda fonte compartilhada entre camadas, não substitui esta);
tamanho de texto (64 KiB); concorrência otimista pela coluna `versao` já existente na tabela de
camada — atualizar/apagar com a versão errada devolve `409` com a feição ATUAL, nunca sobrescreve
em silêncio; campos de rastreio (`fid`, `globalid`, `versao`, `tenant_id`, `criado_*`,
`atualizado_*`) NUNCA aceitos do corpo, sempre preenchidos pelo servidor; "só as próprias feições"
(`edicao.somente_proprias`) e "geometria travada" (`edicao.geometria_travada`) por camada, com
`feicoes.editar_total` (perfil admin) ignorando as duas. Sanidade de CRS não declarado: coordenada
fora de `[-180,180]`/`[-90,90]` numa camada de SRID geográfico sem `crs.srid` declarado é `422
geometria_fora_do_crs` (cobre o envio de metros — UTM/Web Mercator — sem declarar). Um evento por
LOTE (`camadas/editar`, nunca um por feição) com a contagem de adicionadas/atualizadas/apagadas, e
bump de `dados.tiles_versao` no item (ponto de integração para a invalidação de tiles do L2-01-b,
ainda pendente). Isolamento entre inquilinos por RLS FORCE já existente: o inquilino B recebe `404`
ao ler, atualizar ou apagar feição de A — nunca `403`, nunca sucesso silencioso, porque a existência
não é confirmada a quem não pode ver (ADR 20260907T0216).

Medido: 1.000 feições em `adicionar` (modo transação) em menos de 1 s, contra o teto de 3 s do
portão (`tests/medidas/L2-03-a-api-edicao-transacional.json`). Refutação do item (roteiro do
adversário) rodada nesta passagem: lote de 100 mil feições recusado pelo teto de lista
(`EDICAO_LOTE_MAX=2.000`); `crs.srid=0` recusado pela própria validação de entrada; texto de 1 MB
recusado (`EDICAO_TEXTO_MAX=64 KiB`); geometria em outro CRS sem declarar recusada pela sanidade de
grau; feição de outro inquilino nunca aceita (404); duas sessões editando a mesma feição — só uma
ganha (200), a outra recebe 409 com a versão atual, nunca as duas 200. 20 testes verdes em
`tests/api/test_edicao_transacional.py`.

Fora desta passagem (fronteira honesta, ver ADR): matriz fina de permissão por operação × grupo
(ficou em `edicao.habilitada`/`somente_proprias`/`geometria_travada` + privilégio único);
integração com `plat.dominio` do L2-10-a; consumidor da invalidação de tiles (L2-01-b); histórico/
restauração de feição (L2-03-d-historico-restauracao) — a coluna `versao` cobre só a concorrência
otimista, não um log de mudanças.
## turno 4, setembro de 2026 (item L2-01-d-popup-runtime: popup em tempo de execução, do clique ao valor formatado)

O motor que desenha o popup do visualizador e a configuração mínima que o governa (`plat.item.dados.popup`).

- **Configuração da camada** (`app/mapa/popup.py::normalizar`): título com `{campo}`, lista de campos com
  nome de exibição e formato (número com casas e separador pt-BR, moeda, data no fuso do inquilino, URL
  clicável, imagem por URL), campo marcado `servidor` e expressões. Camada sem configuração continua
  mostrando todos os campos como texto — o item acrescenta formato, nunca tira o popup de quem não
  configurou.
- **`GET /api/camadas/{id}/feicoes/{fid}/popup`**: devolve só o que o cliente não tem — campos que o tile
  não carrega (tabela companheira `<tabela>_x`, por `fid`) e expressões avaliadas no servidor pelo núcleo
  do item L2-10-c, com `$area_m2`/`$perimetro_m2` de `ST_Area`/`ST_Perimeter` geográficos no contexto.
  Camada de outro inquilino e feição inexistente respondem 404.
- **Tela**: paginação "i de N" entre feições coincidentes, campo nulo como travessão, zoom para a feição,
  e painel acoplado na parte de baixo em tela estreita (390 px) no lugar do popup flutuante.
- Medido: p95 da consulta ao servidor **8,38 ms** com carga 7,24 e 8,01 GB livres (alvo do portão: 100 ms);
  expressão de área contra `ST_Area` geográfica em 5 feições. Detalhe em
  `tests/medidas/L2-01-d-popup-runtime.json`, que também registra a ressalva: o erro é zero por construção,
  porque a expressão recebe a área da MESMA chamada PostGIS — o teste prova o encanamento, não um cálculo
  de área independente.
- Dois defeitos reais achados ao rodar o e2e no navegador: recursão infinita entre a árvore de camadas e
  `Catalogo.reordenar` (o catálogo avisava mesmo sem mudança de ordem, inclusive com nenhuma camada ligada)
  deixava a tela do mapa inteira sem árvore; e o botão de fechar do MapLibre cobria o botão "próxima
  feição" do paginador. Os dois corrigidos.
- Fora do item, com motivo escrito: anexos (não há armazenamento por feição), registros relacionados
  (L2-10-b pendente), valor de pixel de raster (L1-02-h pendente) e as ações "selecionar"/"editar"
  (L2-01-h/L2-03 fora desta linhagem).

## turno 4, setembro de 2026 (item L2-01-l-exportacao-do-mapa: exportar a partir do mapa)

Exportação passa a sair DO MAPA e não só do painel do item: a seleção (lista de fid), o filtro do
construtor (CQL2-JSON, o mesmo objeto de `/api/mapa/camadas/{id}/filtrar`) ou a camada inteira, com CRS,
campos e codificação. Origem pode ser `camada_vetorial`, `vista_de_camada` (o filtro da vista vale sempre
e os `campos_ocultos` não são exportáveis nem filtráveis) ou `selecao` salva. O catálogo de formatos foi de
11 para 16 com GeoJSON Sequence, File Geodatabase (zip), MVT (zip), PMTiles e o `pacote` de mapa, e passou
a declarar a POLÍTICA DE CRS de cada um: 12 formatos gerados da mesma seleção de 500 feições foram
reabertos por `ogrinfo` com contagem 500 e o EPSG que a política manda (`tests/medidas/L2-01-l-exportacao-do-mapa.json`,
`formatos_da_selecao_de_500`) — 31983 nos de CRS livre, 4326 nos que a especificação prende, nenhum nos
que não guardam CRS. Pedir CRS diferente do que o formato prende é 422, não um arquivo mentiroso.

O XLSX ganhou o teto do próprio Excel: uma camada de 1.048.600 feições é recusada com
`422 formato_limite_de_linhas` antes de existir job (a mesma camada sai em CSV). Toda resposta de pedido
traz `perda_declarada` — DXF sem atributo, shapefile truncando nome em 10 caracteres, tile recortando
geometria. Estilo da camada sai em MapLibre e em SLD 1.0.0, gerados da MESMA lista de classes da legenda.
Feição copiável como GeoJSON/WKT lida da tabela (o tile vem recortado). A imagem do mapa passou a levar
legenda e atribuição, com um "2x" que monta um mapa temporário do dobro do tamanho em vez de ampliar
pixel: as duas composições, com e sem legenda, foram comparadas pixel a pixel no navegador
(`png_legenda_e_atribuicao`: 775 pixels de diferença na faixa da atribuição). O mapa inteiro vira PACOTE
(documento + estilos + GeoPackage só das camadas citadas), pelo mesmo job e o mesmo link de 7 dias, e volta
por `POST /api/mapa/pacotes/importar` em OUTRO inquilino, recriando camadas, simbologia e o documento com
os identificadores novos; o pacote de um mapa que cita uma camada não leva nenhuma feição da outra camada
do mesmo inquilino (provado por despejo do GeoPackage).

Quatro defeitos de fora do item foram corrigidos porque bloqueavam o portão: `app/versao.py` não lia o sha
num GIT WORKTREE (`.git` é arquivo, não pasta) e o worker morria no arranque; a escrita sob cookie só
aceitava `application/json`, o que barrava o envio do pacote — a regra correta não é "JSON", é "nada que um
formulário HTML consiga produzir"; a falha do `ogr2ogr` era relatada pela última linha do stderr, que é
sempre a genérica; e `app/schema_ambiente.py` tinha duas definições de `executemany`, com a segunda (sem
tratamento de bytes) apagando a primeira em silêncio.

## turno 4, setembro de 2026 (item L0-04-h-exportar: exportação de camada para outros formatos)

`POST /api/exportacoes` enfileira o job `exportacao.gerar` (202) e devolve o arquivo (item `arquivo`,
validade de 7 dias) em 11 formatos: gpkg, geojson, shapefile(zip), csv, xlsx, kml, kmz, fgb, gml, dxf e
geoparquet (este pelo DuckDB, num processo próprio — o `ogr2ogr` desta instalação não tem driver Parquet, e
o DuckDB não sobrevive a um `fork`, então a conversão roda como `python -m app.exportacao.parquet_cli`,
neto do job). Filtro (`where`), campos e CRS de saída são conferidos ANTES de existir job (400 com o erro do
banco saneado, `app/exportacao/erros.py`). Isolamento entre inquilinos: o `ogr2ogr` abre conexão PRÓPRIA,
fora do pool da aplicação — o inquilino entra na string de conexão (`-c plat.tenant_id=N`), e é a RLS do
PostgreSQL que corta, provada com pedido forjado no banco e com o `ogr2ogr` chamado sem contexto nenhum
(`tests/api/exportacao/test_exportacao_cruzado.py`). Arquivo grande nunca vai inteiro à memória: envio ao
Garage em blocos/multipart (`objetos.guardar_arquivo`, novo) e download em blocos de 1 MiB
(`objetos.ler_stream`, novo) — medido com `tracemalloc` (pico < 3 partes de 8 MiB para um arquivo de 40 MiB).
Privilégio novo `conteudo.exportar` (editor/admin); opção do dono do item "permitir que outros exportem"
(`dados.exportacao.permitir_outros`, nasce desligada). Limite de 3 exportações em curso por usuário e guarda
de disco (`shutil.disk_usage`) antes do primeiro byte. Botão **Exportar** na tela do item
(`web/js/catalogo/item_exportar.js`). Achado à parte, sem relação direta com exportação: `CursorSchemaAmbiente`
não reescrevia `executemany`/`mogrify` (só `execute`/`callproc`), o que fazia qualquer rota que use essas duas
chamadas escrever no schema `plat` de PRODUÇÃO mesmo dentro de uma base de trilha isolada — consertado em
`app/schema_ambiente.py`. Ver ADR 0018 e `docs/PARIDADE.md` seção "Exportação de camada para outros formatos".

Medido (`tests/medidas/L0-04-h-exportar.json`, camada de 100 mil feições): tempo por formato de 0,80 s
(FlatGeobuf) a 14,54 s (XLSX); todos os 11 formatos reabertos com a mesma contagem de 100.000 feições
(`ogrinfo`/DuckDB conforme o formato).
## turno 4, setembro de 2026 (item L5-06-motor-widgets: motor de widgets sem framework)

- **Motor de widgets** (`web/js/widgets/`): registro com 6 manifestos validados (mapa, legenda, tabela, texto,
  botão, filtro), `import()` só dos módulos citados no documento, barramento com corte de recursão, ligações
  evento → ação por id de nó, caixa de erro nomeada para tipo desconhecido, configuração fora do esquema e
  módulo que não carrega; alternador de chrome de edição no mesmo módulo; página `/aplicativo`; `<plat-mapa>`
  embrulha o visualizador. Medido em `tests/medidas/L5-06-motor-widgets.json` (3 módulos = 1,32 kB por widget,
  primeira pintura 48 ms, carga 5,1). ADR `docs/adr/20260907T1930-motor-de-widgets.md`.

## turno 4, setembro de 2026 (item L2-01-mapa-web: visualizador de mapa próprio, do Martin à impressão)

Visualizador MapLibre da plataforma, com a pilha de tiles vetoriais que faltava chegar a `master`.

- **Servidor de tiles**: Martin 1.15.0 (musl, sha256 do pacote fixado em `deploy/martin_instalar.sh`) como
  unidade `plat-martin` em `127.0.0.1:8151`, publicando SÓ funções (`auto_publish.tables: false`) — a
  tabela crua da camada nunca é exposta. Papel de leitura `plat_leitor` (LOGIN, sem BYPASSRLS, sem ser
  dono), `plat.contexto_por_token` e a função de tile por camada com RLS vieram do trabalho dos itens
  L2-01-b/L2-04-a, que nunca tinha sido juntado.
- **API do mapa** (`app/mapa/`): `GET /api/mapa/camadas` com estilo MapLibre e legenda geradas da
  simbologia; `GET /api/mapa/camadas/{id}/tilejson` cunhando token de 12 h com escopo de UMA camada;
  repasse `GET /tiles/{esquema}/{funcao}/{z}/{x}/{y}` com a mesma autorização do `auth_request` do nginx
  (uma implementação, duas portas); `plat.camada_extensao` para o "enquadrar".
- **Tela `/mapa`**: lista de camadas com ordem (arrastar e por botão), opacidade, ligar/desligar e
  enquadrar; legenda; janela de atributos (campo nulo aparece marcado, multi-geometria não se repete);
  medição geodésica de distância e área; pesquisa de endereço (CNEFE) e de coordenada em decimal e em
  grau-minuto-segundo; escala, coordenadas e escala numérica 1:N; troca de mapa-base; impressão em PNG e
  em PDF com escala, barra de escala e seta de norte.
- **`GET /api/geocodificar`**: geocodificar é leitura e agora tem o verbo certo (o POST continua).
- Medido com 1.000.000 de feições: 2,4 s do clique ao primeiro desenho, 1,5 s de zoom até `idle`, 61 MB
  de heap; 10 camadas ao mesmo tempo em 4,3 s, pan em 302 ms, 24,8 MB. Tile z8 pelo repasse: 406 ms
  frio, 21 ms quente. Detalhe em `tests/medidas/L2-01-mapa-web.json`.
- Dois defeitos reais achados pelos testes e corrigidos: `attribution: undefined` fazia o MapLibre
  recusar a fonte inteira em silêncio; repassar `Content-Encoding: gzip` com corpo já descompactado
  entregava tile ilegível ao navegador. Registrados no ADR 20260907T0400.
## turno 4, setembro de 2026 (item L2-01-b-martin-tiles-vetoriais: servidor de tiles em produção, PARCIAL)
## turno 7, setembro de 2026 (item L7-19-segredos-e-certificados: os 5 segredos fora do .env, rotação com 0 erro 5xx medido pelo k6)

Sobe o serviço Martin de verdade (v1.15.0, binário oficial, sha256 conferido; `deploy/martin.yaml`,
`deploy/plat-martin.service`) em cima do contrato do L2-04-a, com generalização por zoom
(`ST_SimplifyPreserveTopology` abaixo de z12) e corte de 10.000 feições por tile marcado (migração
`20260906T1955_martin_generalizacao.sql`, já existente desta trilha antes deste turno). Duas peças novas:

1. **`/internal/tiles/verificar`** (`app/tiles/rotas.py`): o Martin (`martin-core::GetTileWithQueryError`)
   devolve 500 para QUALQUER erro do Postgres — nunca 401/403, conferido no código-fonte da tag
   `martin-v1.15.0`. A cláusula "sem token = 401" só existe porque o nginx faz `auth_request` para esta
   rota ANTES de repassar ao Martin. ADR `20260907T0235`.
2. **`plat.item_da_tabela`** (migração `20260907T0213_item_da_tabela.sql`): fecha um achado do próprio
   adversário desta rodada — a 1ª versão da rota acima recebia o item de query param do cliente, e um
   token amplo de QUALQUER inquilino autenticava para o item de QUALQUER outro (a `escopo_cobre` só
   compara texto do token, nunca dono do item). Agora o item vem da tabela que está na URL, nunca do
   cliente.

Medido (`tests/medidas/L2-01-b-martin-tiles-vetoriais.json`, trilha própria, Martin/nginx de teste em
8351/8451, não a unidade de produção): camada de 100 mil pontos sintéticos — tile z8 frio p95 41,8 ms,
quente p95 4,3 ms (limite 200/20 ms, passou); camada de 472.780 setores censitários do IBGE já na casa (a
hipótese do item citava "1 mi", número real registrado) servida por PMTiles (tippecanoe v2.80.0, `-z14
--drop-densest-as-needed --extend-zooms-if-still-dropping --maximum-tile-bytes=500000`) — 110 tiles
amostrados em z4-z14, 0 erro, 1 excede 1 MB por 1,3% (z9, região metropolitana de SP); RLS cruzada,
revogação de token e invalidação de cache por versão (0,12 s) passaram; 200 pedidos paralelos ao pior caso
(z0 da camada de 472,8 mil) na fonte PMTiles: 200/200 OK, RAM do Martin 38-39 MB — na FUNÇÃO AO VIVO (fora
do desenho, que é servir isso por PMTiles) o mesmo teste dá 180/200 em 500 sob a piscina pequena da trilha,
registrado como fronteira, não escondido. PMTiles: 206 a Range, sem Content-Encoding; abertura real no
QGIS Desktop NÃO verificada nesta máquina (sem GUI) — só o formato (magic bytes) e o protocolo HTTP.

Fica de fora, honesto: `ST_Subdivide` para polígono > 4.096 vértices (nenhuma camada de teste tem isso); a
unidade systemd `plat-martin` real não foi instalada como serviço do sistema nesta trilha (rodada como
processo de teste); a fonte PMTiles do Martin não passa pelo mesmo `auth_request` de token que a função ao
vivo (controle de acesso dela é o do arquivo/bucket, L0-11, fora do escopo medido).

### Commits

Ver `git log wt/il201bmarti` a partir do commit desta entrada.

## turno 3, setembro de 2026 (item L2-04-a-leitor-rls-martin: quem serve o tile não sabe o que é inquilino)

O servidor de tiles vetoriais fala direto com o PostGIS e não tem noção de sessão, privilégio ou inquilino.
Passa a existir um **papel de banco só de leitura** — LOGIN, sem BYPASSRLS, sem ser dono de nada, com SELECT
nas tabelas de camada e EXECUTE nas funções de tile — e uma função `plat.contexto_por_token`, que valida o
token de serviço, confere escopo `camada:ler` e restrição de Referer/IP, grava o uso em `plat.log_acesso` e
põe o inquilino na transação. Cada camada ganha a sua função de tile `d_<slug>.t_<16 hex>(z, x, y,
query_params)`, criada junto com a tabela; a primeira instrução dela é o contexto por token. Contrato no ADR
0020; o papel, a senha e a linha do `pg_hba.conf` saem de `db/leitor_instalar.sh`, chamado pelo `install.sh`.

A política de RLS do papel de leitura **não olha a GUC `plat.tenant_id` crua**: qualquer papel conectado
escreve nela, e o papel de leitura é o mesmo para todos os inquilinos. Ela olha `plat.tenant_leitor()`, que
exige uma prova (sha256 de um segredo que nenhum papel comum lê, mais o inquilino e o processo) emitida só
por `contexto_por_token`. Medido em `tests/medidas/L2-04-a-leitor-rls-martin.json`: `SET plat.tenant_id` feito
pelo próprio leitor devolve **0 linhas**; **6 chamadas cruzadas** às funções de tile com o token do outro
inquilino devolvem **0 tiles com dado**; token revogado deixa de valer em **0,002 s**; **1 linha de log por
chamada** de contexto aceita; segunda execução do instalador = **0 mudanças**.

⛔ Fronteira honesta: a linha de log de uma RECUSA é escrita e desfeita com a transação abortada (o PostgreSQL
não tem transação autônoma) — medida `linhas_log_de_recusa_persistidas: 0`. O rastro da recusa fica no log do
servidor (a exceção é nomeada) e no log de acesso da API. E o Martin em si não está instalado nem configurado
por este item: o que se entrega é o contrato de banco que ele consome.
## turno 3, setembro de 2026 (item L2-01-a-documento-mapa: o mapa é um documento com esquema, não um punhado de URLs)
## turno 5, setembro de 2026 (item L7-26-cdn-tiles: CDN de ladrilho — endereço versionado, purge por prefixo)

Camada de CDN em frente ao ladrilho raster do L1-02: endereço `/svc/<token>/raster/<item>@<versao>/{z}/{x}/{y}`,
`<versao>` = 12 caracteres do sha256 já gravado em `plat.raster_item` desde L1-01-a. Casar com o sha256
vigente → `Cache-Control: public, max-age=31536000, immutable` + `ETag`; não casar → `404 versao_inexistente`
sem ler o pixel — e a checagem de INQUILINO acontece antes da checagem de VERSÃO (achado desta bancada: sem
essa ordem, um token de outro inquilino pedindo `item-alheio@versao` recebia 404, vazando pela diferença de
código que aquele item existe com aquele sha256 em algum lugar; corrigido, com teste de regressão). O
`tilejson.json` já devolve a URL versionada — o cliente de mapa nunca precisa saber que "versão" existe.

⛔ Sem acesso à conta Cloudflare real: nenhum DNS, nenhuma Cache Rule, nenhum purge de produção foi tocado.
O que foi medido de verdade contra sockets reais (`scripts/cdn_simulada.py`, um proxy HTTP simulando o
mecanismo de uma Cache Rule "cache everything" com chave sem query string, cf-cache-status e purge por
prefixo — não é a Cloudflare, é a mesma classe de mecanismo): `tests/medidas/L7-26-cdn-tiles.json` via
`scripts/prova_cdn.py` — 2ª chamada HIT, revogar+purgar+3ª chamada 403 em 2,1 s (< 60 s), 87,5% de acerto
numa rodada de navegação simulada (96 pedidos, 12 ladrilhos distintos), e a API da aplicação sem cabeçalho
de cache de CDN. **Achado registrado (`docs/adr/20260907T1522-cdn-tiles.md`, seção 3)**: o cache de
autorização da origem (2 s, já existia no L1-02) pode fazer um purge só-uma-vez ser recacheado por um 200
morto se a chamada seguinte cair dentro da janela — o procedimento de purge tem de repetir por ≥ 2 s depois
da revogação, documentado em `docs/CDN.md` junto com o comando real de purge e o passo a passo pendente do
dono (DNS, Cache Rule, webhook de revogação, decisão de saída para Bunny/R2 acima de ~1 TB/mês).

Refutação: martelar a URL revogada 20× depois do purge (0 de 20 com 200/HIT) e trocar só o token no mesmo
item de outro inquilino pela CDN (403, não vaza pelo cache) — `laco/handoffs/T5/L7-26-cdn-tiles/refutacao.json`.
## turno 6, setembro de 2026 (item L2-02-f-estilo-raster: editor de estilo raster sobre o ladrilho do L1-02)

O tipo `raster` do construtor de estilo (L2-02-a) ganha o vocabulário que faltava para editar imagem de
verdade: `parametros_raster.bandas` (composição de banda, 1 a 4 índices — RGB ou banda única), `rescale`
(faixa aplicada, validada `min < max`), `colormap_name` (rampa de cor para banda única, contra o mesmo
vocabulário — `rio_tiler.colormap.cmap.list()`, 211 rampas — que `app/imagens/rotas_tiles.py` de fato
aceita: `app/estilos/compilador.py::_raster` importa `app.imagens.tiles` em vez de duplicar a lista, então
o editor nunca aceita algo que o ladrilho recusaria, nem o contrário), `expression` (NDVI/NDWI/livre, pela
MESMA gramática restrita do L1-02, `tiles.expressao_valida`), `esticamento.metodo`
(`minmax`/`percentil_2_98`/`desvio_padrao`/`nenhum`, documentando qual método propôs o `rescale` gravado) e
`resampling`/`nodata` (aceitos no documento; o L1-02 ainda não expõe parâmetro de URL para nenhum dos dois
— registrado como PARCIAL em `docs/PARIDADE.md`, não fingido como feito).

Nova rota no serviço de ladrilho: `GET /svc/<token>/raster/<item>/estatisticas.json` (item L1-02, módulo
`app/imagens/tiles.py::estatisticas`) devolve mín/máx/média/desvio-padrão/percentis 2-98 por banda (ou pela
expressão), decimado pelo rio-tiler — é a fonte ÚNICA que o editor consulta para propor o `rescale` do
esticamento por percentil/desvio-padrão, e que a legenda contínua (`compilador.legenda_raster`) cita: a
legenda nunca recalcula por conta própria, só repete o `rescale` que já saiu de lá. `compilador.parametros_tile(pc)`
traduz o vocabulário do documento (nomes do TiTiler: `bandas`/`rescale`/`colormap_name`/`expression`) para
os quatro parâmetros de consulta em português que o L1-02 de fato lê (`bandas`/`faixa`/`colormap`/`expressao`)
— nenhum outro campo do construtor vaza para a URL, e é essa mesma função que fecha a exigência do
adversário ("a URL de tile gerada não permite expressão arbitrária além do vocabulário do TiTiler").

CORS liberado (`Access-Control-Allow-Origin: *`) nas respostas de ladrilho/TileJSON/info/estatísticas do
L1-02: sem isso, `<img crossorigin>` do MapLibre (textura WebGL) falha ao carregar um ladrilho de outra
origem mesmo com HTTP 200 — achado ao montar o e2e com um `uvicorn` de verdade na porta 8248.

E2E (`tests/api/imagens/test_estilo_raster_e2e.py`, `page` do playwright + harness próprio
`tests/e2e/apoio_estilo/harness_estilo_raster.html`, contra um `uvicorn` real da trilha — o harness
vetorial do L2-02-a usa GeoJSON sintético por `file://`, raster precisa de HTTP de verdade): 4 capturas
(RGB, banda única + rampa, NDVI por expressão, percentil 2-98), cada uma com o tile pedido conferido 200
PNG não vazio ANTES da captura no navegador, e a legenda comparada byte a byte com o que
`/estatisticas.json` mediu de verdade na cena sintética de teste. Round-trip (salvo/reaberto idêntico) em
`tests/api/catalogo/test_estilos.py`. Adversário (`tests/unit/test_estilos_compilador.py`): rescale
invertido, banda fora de 1-64, expressão com divisão por literal zero, expressão fora da gramática do
TiTiler e colormap desconhecido — todos recusados na compilação, nunca só na renderização.

Fora do recorte (registrado, não fingido): classes discretas na rampa (o L1-02 só aceita `colormap_name`
nomeado, não colormap JSON custom) e funções raster encadeadas do Image Server (fora do portão literal do
item). Migração `db/migracoes/20260907T1312_estilo_raster_parametros.sql` (arquivo novo — a
`20260907T1148_estilo_modelo.sql` já estava aplicada e não pode ser editada).
## turno 5, setembro de 2026 (item L2-02-d-rotulos: rótulos por campo, expressão e classe, com prioridade/colisão e faixa de escala)

`plat_construtor.rotulos` deixa de ser `{visivel, campo, cor, tamanho}` e passa a ter classes: cada
classe tem filtro simples (`{campo, operador, valor}`), texto por `campo` ou por `expressao` da
linguagem própria (L2-10-c), fonte, tamanho (fixo ou por interpolação de zoom), cor, halo, âncora e
deslocamento (ponto), rótulo ao longo da linha com repetição (linha), várias linhas, maiúsculas,
unidade, prioridade e permitir-sobreposição, e faixa de escala própria. `app/expressao/
compilador_maplibre.py` (novo) compila o subconjunto da linguagem com equivalente nativo na Style
Spec; o que não compila (a começar por `TextoNumero`/`TextoData`, a formatação pt-BR) cai para uma
coluna pré-calculada do servidor com nome determinístico (`app/estilos/rotulos_servidor.py`, novo).
Achado medido em produção, não suposto: `symbol-sort-key` sozinho NÃO decide colisão entre classes
diferentes (layers diferentes) no MapLibre-GL real — quem decide é a ORDEM dos layers no array;
`_rotulos_layers` reordena por prioridade em vez de confiar só no sort-key (`docs/adr/
20260907T1640-rotulos-de-camada.md` tem o experimento de controle). Faixa de escala por classe vira
`minzoom`/`maxzoom` nativos (conversão OGC de 0,28 mm), não só metadata. `glyphs` é gravado
automaticamente no documento quando há rótulo (a Style Spec recusa `text-field` sem isso).

E2e sobre o MapLibre vendorizado real e um Martin real (binário de produção, fontes abertas Noto
Sans/Open Sans instaladas nesta máquina, numa porta descartável só da suíte): rótulo por campo,
rótulo por expressão com formatação `'1.234,5 ha'` (coluna do servidor), 2 classes com filtro,
rótulo de linha seguindo a linha em z14 (captura mostra o texto girando com o traçado), prioridade
(classe A vence B em colisão real, provado por amostragem de pixel com Pillow — 455 pixels pretos
de A, 0 vermelhos de B), faixa de escala (visível dentro, ausente fora, via
`queryRenderedFeatures`), glifos do Martin com cache (1ª chamada 14,6 ms, 2ª 1,1 ms, bytes
idênticos). Identidade "dois modos" (a mesma expressão compilada e pré-calculada dão o mesmo texto
em 100 feições) provada em `tests/unit/test_rotulos_servidor.py` com um intérprete de referência
escrito à mão (`tests/apoio_expressao_maplibre.py`) para o subconjunto emitido pelo compilador.
Refutação: divisão por zero, campo nulo, campo ausente e texto de 2.000 caracteres nunca produzem
`'null'`/`'NaN'`/`'undefined'` no rótulo (erro de avaliação em uma feição vira rótulo vazio só
naquela feição, nunca derruba o lote).

Fora do escopo, nomeado: compilação para SQL/coluna real na função de tile do Martin (pipeline de
ingestão, item L2-04); glifário definitivo com licença no catálogo (L2-02-e); `posicao_poligono`
não tem controle nativo separado no MapLibre (o motor sempre ancora dentro do polígono).

## turno 5, setembro de 2026 (item L2-02-a-modelo-estilo: o estilo de uma camada vira documento versionado)

O tipo `estilo` deixa de ter `corpo` livre e passa a carregar o **JSON Schema publicado**
(`docs/esquemas/estilo-v1.json`): `plat_construtor` (a intenção do usuário — 7 tipos: `unico`, `categoria`,
`classes`, `proporcional`, `calor`, `agrupamento`, `raster`, com campo, cortes, cores, rótulos, faixa de
escala e transparência) e `maplibre` (as camadas MapLibre Style Spec v8 que o navegador desenha). O servidor
recompila `maplibre` a partir de `plat_construtor` na gravação (`app/estilos/validador.py`) — nunca existe um
`maplibre` gravado que não seja exatamente o que aquele `plat_construtor` implica, o que fecha a ida-e-volta
sem perda sem depender do cliente calcular o documento certo. Validação em três camadas na gravação, nunca no
desenho: (1) `plat_construtor` compila sem erro (campo ausente, faixa invertida, tipo desconhecido —
`app/estilos/compilador.py`, `EstiloInvalido` → 422 `plat_construtor_invalido` com o campo apontado); (2)
todo campo citado em expressões `get`/`has`/`in` está no vocabulário `plat_construtor.campos` (422
`campo_inexistente`); (3) a Style Spec enviada é válida pelo pacote oficial `@maplibre/maplibre-gl-style-spec`
20.4.0, chamado por subprocesso Node (`ferramentas/estilo/validar.mjs`) — 422 `estilo_invalido` com a
mensagem literal do validador. `docs/adr/20260907T1200-modelo-de-estilo.md` registra a convivência com
`app/mapa/simbologia.py` (item L2-01-mapa-web, ramo `wt/l201mapa`, ainda não juntado): as duas coisas ainda
não se ligam (nenhum código resolve um `estilo.ref` desenhando-o), e o caminho de convergência fica descrito
lá, com a mesma paleta categórica preservada nos dois lugares.

`app/estilos/padrao.py::estilo_padrao` gera o estilo padrão de uma camada nova por hash sha256 do uuid do
item — mesmo uuid, mesma cor, em qualquer instalação (testado em `tests/unit/test_estilos_compilador.py`);
wiring dentro do INSERT de `app/ingestao/carregar.py` fica para quem tocar o L0-04-c/L2-02-e em seguida (a
função está pronta e testada, a chamada dentro do pipeline de ingestão não foi feita neste item).
`app/estilos/sld.py::gerar_sld` converte o subconjunto declarado (`unico`/`categoria`/`classes`) para SLD 1.0;
provado por leitura do XML (as mesmas cores do construtor), não por abrir no QGIS — QGIS não está instalado
nesta máquina (`SISTEMA.md` recursos), então essa metade da cláusula fica **parcial**, nomeada no handoff.

Sete exemplos (um por tipo do construtor) em `tests/estilos/*.json`: todos compilam, passam no validador
oficial e a ida-e-volta (compilar de novo o mesmo `plat_construtor`) dá byte a byte o mesmo `maplibre`.
Bateria da refutação, todas recusadas em 422 na gravação: expressão com campo inexistente, 300 layers
(o esquema limita a 200), sprite de URL externa (padrão restrito a `/sprites/...` interno), faixa de classe
invertida, valor de categoria duplicado; item de um inquilino não é legível por outro (404, RLS genérico do
catálogo). `tests/api/catalogo/conftest.py::DADOS_POR_TIPO["estilo"]` e duas fixtures de `test_mapas.py` que
fabricavam um `estilo` de exemplo com a forma antiga (`corpo` livre) foram atualizadas para o novo formato.

## turno 3, setembro de 2026
, setembro de 2026 (item L2-01-a-documento-mapa: o mapa é um documento com esquema, não um punhado de URLs)

O tipo `mapa` deixa de ter `corpo` livre e passa a carregar um **JSON Schema publicado**
(`docs/esquemas/mapa-v1.json`, gerado de `plat.tipo_item`): mapa-base, lista ordenada de camadas com
visibilidade, opacidade, faixa de escala, grupo (até 3 níveis), estilo, popup, filtro CQL2-JSON, rótulos,
campo de tempo e intervalo de atualização; extensão inicial, rotação, CRS de exibição fixo em 3857 e
favoritos. Cada camada aponta o item do catálogo por **uuid** (`ref`), nunca por URL — o oposto do Web Map
JSON da Esri, onde a URL do portal fica congelada dentro de cada mapa salvo. Rotas novas: `POST/GET/PUT
/api/mapas`, `GET /api/mapas` e `GET /api/mapas/{id}/completo`, que devolve o documento com as camadas já
resolvidas (título, tipo, campos, estilo, popup) em UMA chamada. Contrato no ADR 0022; de-para chave a chave
contra a Web Map Specification em `docs/PARIDADE.md`.

Medido em `tests/medidas/L2-01-a.json`: `/completo` de um mapa com **10 camadas** responde com p95 de
**20,7 ms** (mediana 12,2 ms) em **50 chamadas**, contra o teto de 150 ms do portão. Camada de outro inquilino
citada no documento = **404** (o mesmo 404 de uuid inexistente, sem revelar que existe); apagar camada usada
por mapa = **409** com a lista dos mapas dependentes; 500 camadas, 5 níveis de grupo, ciclo de grupo e
extensão fora do mundo = **422**, nenhum 200 e nenhum 500. Na tela `/mapa?id=<uuid>` a lista de camadas
reordena arrastando (e por teclado, Alt+seta): e2e grava a ordem, recarrega a página e confere que voltou a
mesma, com captura em `tests/e2e/capturas/L2-01-a-documento-mapa_painel_camadas.png`.

⛔ Fronteira honesta: `/completo` devolve o CONTRATO da URL de tiles com `pronto: false` e o motivo — não há
servidor de tiles vetoriais nem raster instalado nesta máquina (itens L2-01-b e L1-02) —, e `dominios` sai
vazio com o motivo escrito, porque a camada ainda não guarda vocabulário de domínio (L0-04-c, parcial). A tela
lista e reordena as camadas do documento; não as desenha no canvas, pelo mesmo motivo, e diz isso em cada
linha. ⛔ Quebra declarada: documento com `corpo.camadas` como lista de uuid soltos passa a ser 422.
## turno 3, setembro de 2026 (item L2-01-g-tabela-atributos: tabela de atributos acoplada ao mapa)

Tabela de atributos por camada, paginada no servidor: `GET/PUT /api/camadas/{id}/tabela/vista`,
`GET .../colunas`, `POST .../linhas` e `POST .../estatisticas`. Página de 50, 200 ou 1.000; ordenação por
coluna com desempate pela chave primária; busca em texto com `unaccent` sobre todas as colunas de texto;
filtro pela extensão do mapa (`&&` no índice GIST mais `ST_Intersects`); filtro pela seleção vinda do mapa;
estatísticas por coluna numérica (contagem, soma, média, mínimo, máximo, nulos) calculadas no banco.

A vista fica em `plat.tabela_vista` (migração `20260907T1922_tabela_atributos.sql`), uma linha por item e
usuário, com política por inquilino e por usuário: ordem, rótulo, coluna oculta, largura e domínio. Coluna
oculta não sai da API de colunas nem da linha; `GET .../vista` devolve a vista inteira para desfazer.

Nenhum identificador vem do pedido: o nome de coluna pedido é procurado na lista de colunas reais do
catálogo do banco e, se não estiver lá, é 422 antes de virar SQL.

Na tela do mapa, painel acoplado (`web/js/mapa/tabela.js`): clicar na linha realça e centra a feição,
clicar na feição filtra a tabela, setas navegam a grade e Enter abre o popup da linha.

Medido em camada de 1.000.000 de feições, com a carga da máquina em 10,7 (acima do teto de 8; passou mesmo
assim) — `tests/medidas/L2-01-g-tabela-atributos.json`: primeira página com contagem 275,9 ms no percentil
95; ordenar por coluna indexada 15,2 ms. A contagem passou a ser sob pedido (`contar`, padrão verdadeiro):
sozinha ela custa 263 ms porque a política de segurança por linha impede a varredura em paralelo — ver
`docs/adr/20260907T2028-tabela-de-atributos-conta-sob-pedido.md`.

Pendente: os e2e de tela (`tests/e2e/test_mapa_tabela.py`) foram escritos mas não rodaram nesta base de
trilha, que não tem URL que resolva; ficam pulados com o motivo.

## turno 3, setembro de 2026 (item L2-01-k-desenho-anotacoes: desenho e anotações no mapa)

Camada de desenho da tela do mapa com sete tipos — ponto, linha, polígono, retângulo, círculo (raio em
metros), texto e seta — com cor, contorno, preenchimento, opacidade, largura e tamanho de fonte; mover,
editar vértice, apagar, ordenar; medição da feição na própria lista; importação de GeoJSON e de KML
(`DOMParser`, sem biblioteca nova). O desenho vive DENTRO do documento do mapa (`corpo.desenho`, GeoJSON
mais estilo, sem tabela) e é validado no servidor por `app/catalogo/documento.py::erros_de_desenho`, que
confere o par tipo × geometria, o teto de 5.000 feições, o teto de 10.000 caracteres de texto, o raio do
círculo e a coordenada dentro do mundo. O botão "promover a camada" (`POST /api/mapa/{id}/desenho/promover`)
transforma a seleção numa camada hospedada de verdade, reusando `plat.camada_schema_garantir` e
`plat.camada_preparar` do L0-04, com `ST_MakeValid` e conferência de `ST_IsValid` antes de gravar o item.

Anotação de usuário ligada a uma feição (`plat.anotacao_feicao`, migração `20260907T1655`): comentário com
autor e data, visível a quem é membro ativo do grupo em que foi criada, nunca a outro inquilino — a
visibilidade é da RLS, não da aplicação. Texto é sempre dado: entra por `textContent`, nunca por HTML.

Achados de medição que viraram conserto: o `text-field` do MapLibre exige servidor de glifos (item
L2-02-e) e, sem ele, o MapLibre aceita a camada e a descarta em silêncio — o texto passou a ser desenhado
num canvas próprio, com halo por `strokeText`; o modo `select` do terra-draw dispara `finish` ao soltar o
arrasto de um vértice, o que fazia a edição virar cópia; e `Catalogo.reordenar` avisava mesmo sem mudança
de ordem, fechando um ciclo sem fim com a árvore de camadas sempre que o catálogo ganhava camada nova.

Medido com 5.000 desenhos num mapa: salvar em 190 ms e reabrir em 39 ms, idênticos bit a bit, com carga de
1 minuto em 14,12 e 7,8 GB de memória livre (`tests/medidas/L2-01-k-desenho-anotacoes.json`).
## turno 3, setembro de 2026 (item L2-08-a-leitor-portal-inventario: conserto de segurança, B1-B7 do adversário)

Sete achados do adversário independente (`laco/handoffs/T3/ataque-L4-portal-ADVERSARIO.md`, seção 2)
consertados; os 15 `xfail(strict=True)` de `tests/api/test_migracao_adversario.py` viraram teste normal
(marca retirada, achado por achado). **B1/B1b (crítico)**: `ClientePortal._cabecalhos(alvo)` só põe
`X-Esri-Authorization` quando `alvo` é a MESMA origem do portal configurado
(`seguranca._mesma_origem_de_confianca`, copiada com atribuição da defesa que o item L6-02-h fez para
redirecionamento) — nunca para o host de um item de terceiro nem para onde um 302 aponte; `_requisitar`
recalcula os cabeçalhos a cada salto. **B2 (alto)**: título com NUL e `numViews` não numérico agora são
SANEADOS antes do INSERT (`_sanear`, `_inteiro_nao_negativo`) — o item fica no inventário; quando o campo
é irrecuperável (não adapta para a coluna) o item é registrado e PULADO (`Totais.itens_pulados`, AVISO no
log do job), nunca trava o lote. **B3 (alto)**: `resposta_grande_demais` (página > 8 MiB) entrou em
`MOTIVOS_DEFINITIVOS` — falha limpa em `falhou` já na 1ª tentativa, não fica `rodando` para sempre.
**B4 (médio)**: quando a ordem do portal muda entre tentativas e a retomada perde itens, `Totais.aviso`
registra a contagem esperada x obtida e some para a coluna `mensagem` mesmo com o job `concluido`
(recuperar os itens perdidos fica fora do escopo do conserto — só detectar e avisar). **B5 (médio)**:
`relatorio._texto` neutraliza injeção de fórmula no CSV (`'` na frente de células que começam com
`=`/`+`/`-`/`@`). **B6 (baixo)**: `size: -1` do AGOL vira NULL, não entra mais somado em
`bytes_declarados`. **B7 (médio)**: `POST /api/migracao/inventarios` confere o perfil mínimo do job
(`servico.tipo_registrado` + `ordem_perfil`) ANTES de gravar a linha do inventário — editor sem privilégio
nunca cria mais um inventário órfão. Handoff: `laco/handoffs/T3/L2-08-a-CONSERTO.md`.

## turno 3, setembro de 2026 (item L2-08-a-leitor-portal-inventario: leitor de inventário de Portal/AGOL)

Leitura só-leitura do Portal for ArcGIS / ArcGIS Online do cliente, como job retomável
(`migracao.inventariar`): `portals/self`, `search` paginado, item, `item/data`, `item/resources`,
`relatedItems`, grupos com membros, usuários, e contagem de feições por camada dos serviços hospedados
(`query?returnCountOnly=true`). Grava em `plat.migracao_inventario` / `migracao_item` / `migracao_grupo` /
`migracao_usuario` (migração `20260906T1540_migracao_inventario_portal.sql`, RLS por inquilino), com
classificação prévia migra / migra parcial / não migra por tipo de item — tipo fora da tabela vira
`desconhecido`, nunca chute. Tela `/migracao` (escolher a conexão, ler, ver o relatório por tipo e por item)
e `GET /api/migracao/inventarios/{id}/relatorio.csv`. Rede pelo `app.conexao.seguranca` do L6-02-a (SSRF,
IP pinado, sem seguir redirecionamento sozinho); token em cabeçalho `X-Esri-Authorization`, nunca em URL;
429 com espera pelo `Retry-After`; corte de rede no meio retoma do ponto gravado sem reler o que já entrou.
`plat.migracao_usuario` não tem coluna de e-mail, nome ou telefone: o dado pessoal que o portal devolve não
tem onde ser gravado. ADR 0018. ⛔ a prova contra Portal REAL fica pendente da decisão D20 do dono
(credencial do parceiro) — `tests/migracao/PORTAL_DE_TESTE.md` diz o que a prova atual sustenta e o que não.
## turno 5, setembro de 2026 (item L2-10-b-relacionamentos: classes de relacionamento entre camadas)

`plat.relacionamento`/`plat.relacionamento_junc` (migração `20260907T1244_relacionamentos.sql`; **ADR
20260907T1436**): 1:N/1:1 vira FK real na tabela de destino (`(tenant_id, chave_destino) -> (tenant_id,
chave_origem)`, `ON DELETE CASCADE` quando `composto=true`, `SET NULL`/`RESTRICT` quando simples); N:M não
tem FK física (a junção pode ligar qualquer lado primeiro) e ganha gatilho de integridade
(`plat.relacionamento_junc_conferir`) sobre uma tabela de junção única para todo o inquilino. Cardinalidade
máxima em 1:N é gatilho GERADO por tabela de destino (mesmo padrão do L2-10-a, já com o cuidado de nunca
concatenar texto do usuário no corpo do dollar-quote). Chave de origem/destino é sempre um VALOR (campo
declarado ou `globalid`), nunca o `fid` físico — é por isso que o relacionamento sobrevive a apagar e
recriar a linha com o mesmo `globalid` (medido).

API: `POST/DELETE /api/relacionamentos`, `POST .../ligar` e `.../desligar` (N:M), `GET
/api/camadas/{id}/relacionados/{rel}` com paginação (`limite_relacionados` da classe vence o `limite` da
consulta) e o novo `GET /api/camadas/{id}/relacionamentos` (lista as classes que a camada enxerga, dos dois
sentidos, para a tela montar o popup sem conhecer o nome de antemão). `GET
/rest/services/{id}/FeatureServer/0/queryRelatedRecords` devolve os MESMOS fids da rota própria (paridade
testada). Popup na tela `/camadas/{id}/dominios` (reaproveitada do L2-10-a): botão "Relacionados" por linha
abre um `<plat-dialogo>` listando os registros ligados com link para `/camadas/{alvo}/dominios?fid=N`; a
página de destino lê `?fid=` e destaca a linha (`tr.destaque`) — e2e com 3 capturas
(`tests/e2e/capturas/L2-10-b-relacionamentos_*.png`).

Refutação do item, todas fechadas: ciclo de relacionamentos compostos A→B→A não trava a criação nem o
apagar (a segunda ponta do ciclo exige uma FK física que a camada de teste não declara, então cai em `404`
de campo, nunca trava); cardinalidade máxima violada por inserção DIRETA na tabela (fora da API, mesmo
caminho de uma edição em lote) é recusada pelo gatilho; paginação com `limite_relacionados` vence um
`limite` maior pedido pela consulta (mecanismo testado com N=25; N=100 mil não medido nesta passagem —
custo de disco/tempo compartilhado, registrado no ADR, não escondido). 8 testes de API + 1 e2e verdes;
medidas em `tests/medidas/L2-10-b-relacionamentos.json`.

Achado do turno (registrado para não se repetir): um teste de leitura que não fecha a própria transação
(`SELECT` sem `commit`/`rollback`) segura `AccessShareLock` na tabela indefinidamente; a chamada seguinte
que precise de `AccessExclusiveLock` na MESMA tabela (`ALTER TABLE ... ADD CONSTRAINT` ao criar a FK do
relacionamento) trava até o Postgres matar a sessão ociosa por `idle_in_transaction_session_timeout`
(~60 s) — e só então progride, com a conexão do teste já morta para a chamada seguinte
(`tests/api/test_relacionamentos.py::_contar` agora fecha a própria transação).

Fora desta passagem: formulário de criar/ligar/desligar um registro relacionado a partir do próprio popup
(a API já faz; falta só o botão); relacionamento sobrevivendo a importação/exportação FGDB (a ingestão
vetorial ainda não cobre FGDB).

## turno 4, setembro de 2026 (item L2-04-servicos-esri-ogc: diretório do FeatureServer, OGC API Features e WFS 2.0)

Construído em volta da operação `query` do FeatureServer (item L2-04-c, `wt/fsquery`, ADR 0018) sem reescrevê-la:
`app/consulta/rotas_servico.py` (descritor de serviço `.../FeatureServer?f=json` e de camada `.../FeatureServer/0
?f=json` — `fields`, `geometryType`, `objectIdField`, `fullExtent`), `app/consulta/rotas_ogc_features.py` (OGC API
Features Part 1: landing, conformance, collections, items com bbox/limit/offset, item único, GeoJSON puro) e
`app/consulta/rotas_wfs.py` (WFS 2.0 KVP: GetCapabilities validado pelo cliente real `owslib.wfs.WebFeatureService`,
DescribeFeatureType mínimo, GetFeature em GeoJSON e GML 3.2 simples). `applyEdits`/anexos/`queryRelatedRecords`/
`relationships` ficam de fora — dependem de L2-03-edicao e L2-10-b, nenhum construído (ADR 0019).

Bateria de 13 ataques (item_id com aspas/comentário SQL/`;`, bbox com sub-select/`pg_sleep()`/função não prevista,
BBOX do WFS com injeção, `REQUEST` desconhecida, `feature_id` não inteiro, unicode no item_id, cross-tenant nas 3
raízes): **13/13 recusados com 400/404, nenhum 500**. Dois achados corrigidos no mesmo turno: (1) `item_id::uuid`
sem validar antes deixava o Postgres levantar exceção sem handler → 500 real, inclusive na `/query` original do
L2-04-c — corrigido com validação de UUID compartilhada; (2) landing/conformance do OGC API Features respondiam 200
para item de outro inquilino (sem vazar dado, mas sem checar posse) — corrigido tocando `plat.item` sob RLS antes de
responder. `docs/PARIDADE.md` e `tests/medidas/L2-04-servicos-esri-ogc.json` têm a tabela cláusula a cláusula.

Fora do turno: QGIS/ArcGIS Pro/AGOL reais carregando o serviço (sem ambiente gráfico nesta máquina, mesma limitação
já registrada para L2-04-c e para Chrome headless); OGC API Features Part 3 (CQL2), WFS-T; GML validado contra o
XSD de referência do OGC.
Colheita da bancada `wt/segredos` (interrompida por limite de cota em 06/09) mais o conserto do que a
medição honesta achou nela. `PLAT_DSN`, `PLAT_GARAGE_ADMIN_TOKEN` e `PLAT_SECRET_ANTERIOR` saíram do
`.env` para `/etc/plat/segredos` (root 0600) entregues por `LoadCredential=` do systemd — o `.env` fica
só com configuração, e o Makefile injeta os segredos no pytest (a falta de `PLAT_DSN` na injeção tinha
deixado a suíte vermelha na coleta desde 06/09 à noite). `scripts/plat segredo rotacionar <nome>`
rotaciona os 5 segredos: PLAT_SECRET com dupla-chave (o valor antigo vira `PLAT_SECRET_ANTERIOR` por 24
h, sessões sobrevivem), PLAT_DSN e PLAT_DSN_WORKER com `ALTER ROLE` + reinício das consumidoras,
PLAT_GARAGE_ADMIN_TOKEN com restart do Garage + API, e a chave S3 de um inquilino sem reiniciar nada.
Em todos, o valor antigo deixa de autenticar (prova por `psycopg2.connect` com a senha velha depois da
rotação). A cláusula "0 erro 5xx durante a rotação" é medida pelo **k6** (v2.2.0,
`scripts/k6_saude_5xx.js`, martelo externo ao processo medido): 0 respostas 5xx em 276-762 requisições
por rotação (`tests/medidas/L7-19.json`). Chegar ao zero exigiu trocar o mecanismo depois de duas
medições ruins: "restart em cadeia" deixou 57 respostas 500 na janela entre o `ALTER ROLE` e o restart
da segunda unidade, e "parar tudo antes" deixou 1.334, porque com ativação por soquete a própria
conexão do cliente religa o serviço com a credencial velha (e `mask --runtime` não impede a religação
de unidade estática, medido em spike). O mecanismo final é uma janela `trust` de segundos no pg_hba
(só a role, só 127.0.0.1, linha marcada, removida por `finally`): velho e novo autenticam durante a
troca, e a senha velha morre quando a janela fecha. A API passa a subir por ativação por soquete
(`deploy/plat-api.socket`, uvicorn `--fd 3` com 2 workers — spike medido: conexão durante o stop
espera ~1 s e recebe 200, nunca refused/502). O adversário independente refutou a primeira versão e os achados que eram do item viraram conserto
neste mesmo turno: a janela trust abre dentro do `try` (linha nunca fica para trás no pg_hba, checado a
cada prova), a rotação de PLAT_SECRET reinicia também o worker (ele carrega a chave uma vez na subida e
decifra dentro de jobs), e o ANTERIOR expira de verdade — timer `plat-segredo-expira.timer` esvazia o
arquivo e reinicia API e worker na virada das 24 h (janela efetiva 24 h-24 h 59 min). Os achados que são
contaminação do ambiente ANTERIOR ao item (segredos reais semeados no journal por comandos de outras
operações; `.env` de worktrees de trilha com valores reais, um deles modo 664; segredos em
`/proc/<pid>/environ` de processos de trilha) ficaram registrados em `refutacao.json` e viraram itens
próprios do backlog com dono nomeado — o desenho do produto em si saiu limpo: unidades plat-* só veem os
segredos por `LoadCredential=`, repositório e histórico git com 0 ocorrências, `.env` raiz sem segredo.
Runbook em `docs/RUNBOOKS/segredos.md` (procedimento por segredo, janela trust declarada, ressalva do
garage.toml do daemon, que é da frente plataforma/pipeline e o produto nunca lê em operação).
## turno 3, setembro de 2026 (item L3-01-g-tela-motor: a tela do motor multicritério)

Tela `/amc/motor`, aberta a partir de um conjunto de unidades ou de uma execução. Monta o modelo (adicionar
fator = camada do catálogo ou do acervo + extrator + transformação, com pré-visualização do histograma sobre
os valores REAIS já extraídos; marcar veto = restrição declarada, objeto separado do peso), escolhe o peso de
cada fator por controle deslizante (multiplicador) ou por percentual com trava, manda rodar (a extração é job
do servidor) e, com a execução em mãos, RECOMBINA NA HORA ao mover um peso — medido no navegador: zero
requisição à API entre mover o controle e a lista mudar. Mapa recolorido por favorabilidade com rampa
declarada (vetado em cinza, sem nota vazado), lista das melhores unidades, clique = explicação fator a fator,
e link com os pesos na URL que reabre a mesma leitura.

Duas rotas novas: `GET /api/amc/execucoes/{id}/matriz` (valor bruto E favorabilidade de cada fator em cada
unidade — é o que torna a recombinação local possível sem uma terceira implementação da conta) e
`POST /api/amc/transformacoes/previsao` (porta HTTP de `app.amc.transformacoes.pre_visualizar`, mais a curva
desenhada sobre o domínio dos valores recebidos).

Os pesos viajam na URL, então a barra de endereço é fronteira de confiança: `web/js/amc/pesos_url.js` valida
antes de qualquer conta e a tela RECUSA o link adulterado (peso acima do máximo da escala, fator inexistente,
soma percentual fora de 100) com a razão escrita, deixando o mapa VAZIO em vez de recolorido com outros pesos.

Três defeitos achados pelo próprio e2e e corrigidos: sem carregar o dicionário, a barra lateral mostrava chave
crua; o campo de número dispara `change` outra vez ao perder o foco e redesenhava a lista entre o apertar e o
soltar do botão, perdendo o clique; e item de grade nasce com `min-width: auto`, o que fazia a tabela esticar
a coluna do painel por cima do mapa. A explicação de uma unidade passou a delegar as doze funções contínuas a
`app/amc/transformacoes.py` — sem isso a tela e a explicação dariam números diferentes para o mesmo fator.

## turno 3, setembro de 2026 (item L3-19-multiescala: grades aninhadas do motor multicritério)

Construído do zero neste turno (RESGATE da sessão executora derrubada por cota só tinha a migração,
`app/multiescala/{crs,motor}.py` ainda sem rota nenhuma). Duas execuções ligadas: `POST
/api/multiescala/conjuntos/{id}/macro` gera a grade grosseira sobre a área de estudo inteira e roda a
combinação; `POST /api/multiescala/execucoes/{id}/micro` gera a grade fina SÓ dentro das células macro
aprovadas (aritmético — a query de geração junta a região aprovada ANTES de expandir as sub-células, nunca
gera tudo para descartar depois) e roda a mesma combinação nela. `GET /api/multiescala/execucoes/{id}`
devolve o relatório por fator com `escala`/`escala_grosseira`/`razao_escala`, calculado pelo motor a partir
de `resolucao_fonte_m` (declarada no fator) x `resolucao_grade_m` (da execução) — o cliente nunca envia
esse campo. CRUD completo: `/conjuntos`, `/fatores`, `/fatores/{id}/amostras` (carga em lote),
`/execucoes`; `DELETE` de conjunto e fator (cascata pelas FKs da migração), acrescentados neste turno para
a varredura cruzada ter como limpar o que cria. Escopo de token novo `multiescala:usar`
(`app/auth/escopos.py`). ADR `docs/adr/20260906T1640-grades-aninhadas-multiescala.md`.

Um defeito de FRAMEWORK achado e corrigido, fora do arquivo deste item mas bloqueando-o:
`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` em `execute` e
`callproc`, mas não em `executemany` (psycopg2 implementa em C e não chama `execute` de volta) —
`POST /api/multiescala/fatores/{id}/amostras` falhava com `permission denied for schema plat` em qualquer
trilha. A MESMA lacuna já quebrava `POST /api/papeis` (não deste item), convertida por `erro_do_banco` num
403 "operação fora do inquilino da sessão" que parecia RLS cruzada e não era — reproduzido e confirmado
antes de mexer. Corrigido na classe (um método a mais, mesmo corpo de `execute`), vale para as duas rotas.

Um defeito do próprio teste (não do motor) achado rodando de verdade: uma área de estudo desenhada só um
pouco maior que a resolução da grade (~1,35-1,47 km sobre 1 km) produz uma célula-fatia cujo CENTRO
nominal (usado para achar o bloco de dado) cai FORA da extensão real da amostra — 2 das 4 células macro
ficavam sem nota, não por bug, porque nenhuma amostra alcançava o bloco que aquela célula ia procurar.
Corrigido aumentando a área de teste para 1.900 x 1.900 m (documentado no ADR, decisão B, para o próximo
teste desta família não tropeçar na mesma coisa).

Medido de verdade (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L3-19-multiescala.json`), 10/10 testes passam
duas vezes seguidas: grade macro de 1 km sobre estudo de 1.900x1.900 m dá 4 células, top_pct 50% aprova 2;
grade micro de 100 m (k=10) gera exatamente 200 células (2 aprovadas × 10²) contra 400 possíveis (4×10²) —
economia de 50,0%; o mesmo fator (1.000 m de escala nativa) sai `própria` na grade de 1 km e `grosseira`
na grade de 100 m da MESMA execução ligada, sem o cliente declarar nada de diferente — é a refutação do
item. `tests/api/multiescala/test_multiescala.py`: 10/10.

**Fora do portão deste turno, registrado no ADR**: `docs/openapi.json` comitado não inclui
`/api/multiescala/*` (regeneração é pendência do gerente após os merges); os 11 casos da varredura cruzada
já estão em `tests/api/cruzado_casos.py` (conferidos à mão contra o app rodando — todas as 11 rotas
recusam ou isolam o cross-tenant corretamente) e passam a valer em `test_cobertura_100_por_cento`/
`test_rota_nao_cruza` assim que `make openapi` rodar contra a árvore juntada. `L3-01-b-unidades`
(dependência declarada) segue PARCIAL num ramo não juntado (`wt/amc`); este item não depende dele em
código (CRS resolvido de forma própria em `app/multiescala/crs.py`), só na hipótese conceitual.
## turno 5, setembro de 2026 (item L5-01-a-layout-paginas: páginas e layout do app)

Sobre o editor de arrasto do L5-08: paleta nova (`web/js/editor/paleta_paginas.js`) com `pagina` (tela cheia
× rolável; `caminho`/`titulo`/`ordem`/`oculta`/`inicial`), `cabecalho`, `rodape`, `menu`, os widgets de
layout do Experience Builder (`linha`, `coluna`, `grade`, `acordeao`, `painel_fixo`, `painel_lateral`) e
`janela` (`modal`/`ancorada`) + `secao_vistas`/`vista`. Executor novo (`web/js/executor/{executor,paginas}.js`
+ tela `/executar?item=<id>&pagina=<caminho>`, `app/paginas.py`) que renderiza o MESMO documento como app de
verdade: nav entre páginas por `history.pushState`, `<dialog>` nativo para janela modal, painel lateral que
recolhe sem `display:none`, grade em CSS Grid `fr`. `web/js/editor/tela.js` escolhe a paleta pelo `tipo` do
item (`app` → paleta de páginas; o resto continua com a paleta comum do L5-08) — única mudança num arquivo
que outro item também toca.

Medido (`tests/medidas/L5-01-a-layout-paginas.json`, e2e `tests/e2e/test_layout_paginas.py`): app de 2
páginas (Central tela-cheia com mapa, Detalhes rolável com painel lateral/grade/janela) montado só por
arrasto (2.245,1 ms); menu navega e a URL muda por página, F5 reabre na página certa; painel lateral
recolhe/expande; grade mantém a razão 8:4 entre dois filhos em 1200 px (2,016) e 600 px (2,033) — diferença
0,017; janela modal abre pelo botão e fecha por Esc (`<dialog>` nativo). Refutação do adversário: 6 níveis
alternando linha/coluna, com irmão ao lado do 1º nível, em 3 larguras de viewport (1280/800/320) — 0 px de
estouro horizontal e nenhum nível com largura, altura, `display` ou `visibility` zerados (a correção que fez
isso passar foi `min-width:0`/`min-height:0` em todo item flexível, ADR
`20260907T1355-paginas-e-layout-do-app`). Achado corrigido no caminho: `drag_and_drop` sobre o SELETOR do
contêiner-alvo mira o CENTRO da caixa — quando o contêiner já tem um filho de largura 12/12, o centro cai
sobre o filho e o `drop` do HTML5 é entregue a ele, não ao contêiner (o novo nó entra um nível mais fundo do
que o pedido); o teste agora solta sempre no FUNDO do contêiner, como o e2e do L5-08 já fazia na raiz.
Paridade contra "Add and manage pages" e "Layout widgets" (doc EXB) em `docs/PARIDADE.md`.

## turno 4, setembro de 2026 (item L5-08-editor-arrasto: primitivas de edição compartilhadas pelos construtores)

Editor de arrasto próprio em `web/js/editor/` (5 módulos, 43.771 bytes medidos; 0 byte de biblioteca de
arrasto — `web/vendor/VERSOES.txt` segue sem SortableJS, dnd-kit ou GridStack) e tela `/construtor?item=<id>`
sobre o documento do L5-05. Paleta→tela e tela→tela por HTML5 Drag and Drop; alça de largura por Pointer
Events com `setPointerCapture`; árvore de estrutura, painel de propriedades gerado do JSON Schema do tipo e
menu "mover para" para quem só tem toque. Largura sempre em COLUNAS da grade de 12, nunca em pixel.

Medido (`tests/medidas/L5-08-editor-arrasto.json`, e2e `tests/e2e/test_editor_arrasto.py` contra a base da
trilha): o MESMO layout de 5 componentes montado só por arrasto (787,5 ms) e só por teclado e menus
(134,0 ms) grava dois documentos idênticos — diferença 0 depois de trocar cada ULID por `n1..nN` na ordem de
profundidade (o ULID é aleatório por construção, D2). Redimensionar por arrasto levou o mapa de 8 para 4
colunas nos dois caminhos; `"px"` não aparece no documento gravado. A árvore reflete o aninhamento
(aria-level 1/2/2/1/1). O painel recusa zoom 99 num campo `maximum: 22`: mensagem no campo, `aria-invalid`,
e o documento salvo depois continua com 12. Refutação do adversário no mesmo arquivo: soltar um contêiner
dentro de um descendente dele é recusado com motivo ("dentro de si"), soltar fora da tela não muda nada, o
menu de mover não oferece destino dentro do próprio nó, e o layout inteiro se monta só por toque no viewport
Pixel 7 (onde o HTML5 Drag and Drop não dispara). 0 erro de console em todos os caminhos.

Achado de ambiente: esta é a primeira tela que grava por `fetch` sob cookie a partir do navegador, e por
isso a primeira a bater no 403 `origem_invalida` quando `PLAT_URL_PUBLICA` não é a origem servida — os e2e
anteriores escreviam pelo contexto de requisição do playwright, que não manda `Origin`. Em produção as duas
coincidem; no ambiente da trilha o nginx local reescreve o cabeçalho. ADR 20260907T0302.
## turno 5, setembro de 2026 (item L2-03-edicao: fechamento — dois achados corrigidos, junção do turno 4)

Retomada do turno 4 (sessão anterior morreu por limitação do servidor da API antes de registrar, comitar
e enfileirar): conferência independente da suíte revelou dois defeitos reais, além do já corrigido pelo
próprio turno 4. Corrigidos e cobertos por teste permanente (não script de auditoria à parte — removido,
mesma convenção do commit `054286a`):

1. `app/edicao/combinar.py::unir` checava `versao` declarada ANTES de checar existência/acesso do id — um
   id inexistente ou de outro inquilino, quando listado depois de um id existente sem `versao`, nunca
   chegava a 404 (ficava preso em 422 `versao_ausente`). Corrigido para existência de todos os ids primeiro,
   depois versão de todos (`tests/api/test_edicao_dividir_unir.py::test_unir_sem_declarar_versao_de_uma_das_feicoes_e_422`
   fecha o buraco original: `versoes` incompleto não pode mais deixar uma origem sem checagem de
   concorrência).
2. `limites.ANEXO_TAMANHO_MAX` (10 MiB) igual ao teto de corpo do middleware (`CORPO_MAX_PADRAO_BYTES`,
   também 10 MiB) — como o anexo viaja em JSON com o conteúdo em base64 (~4/3 de inchaço), o 413 genérico
   do corpo sempre disparava antes do 422 `anexo_grande` específico rodar; o limite documentado de anexo
   era, na prática, letra morta. Reduzido para 7 MiB, com folga sob o teto de corpo mesmo codificado
   (`tests/api/test_edicao_historico_anexos.py::test_anexo_no_teto_real_ainda_da_anexo_grande_nao_corpo_grande`).

Suíte dedicada reconferida após os dois consertos: verde (mesmo comando do turno 4); `ruff` e
`sem-marcador` verdes. Portão e veredito do item-pai continuam os do turno 4 (nenhuma cláusula mudou de
prova, só a implementação ficou mais correta). Handoff em `laco/handoffs/T5/L2-03-edicao/`.

## turno 4, setembro de 2026 (item L2-03-edicao: edição de feições no mapa — criar/mover/vértice/dividir/unir/apagar, formulário, anexos, desfazer, histórico e restauração)

Constrói sobre o L2-03-a (API única de escrita) e o L2-01-mapa-web (visualizador): `web/js/mapa/edicao.js`
inteiro novo, ligado à tela `/mapa`. Criar ponto/linha/polígono por clique; mover e editar vértice
por arrasto (a geometria de trabalho vem sempre de `GET /api/camadas/{id}/feicoes/{globalid}`, exata,
nunca da versão recortada por tile); apagar; formulário de atributos gerado dos mesmos `campos`/
`regras_campo` da camada, com domínio/obrigatório espelhados no navegador — e reconferidos direto na
API nesta rodada, sem passar pela tela, provando que a validação real mora no servidor (cláusula do
item-pai). Aderência (checkbox "aderir a vértice próximo", tolerância de 12 px sobre feições
renderizadas) e edição em lote (N feições selecionadas por shift-clique, um atributo aplicado a todas
num único lote `atualizar`, reaproveitando o array heterogêneo que o L2-03-a já aceitava).

Histórico e restauração são novos no banco: `plat.feicao_historico` + gatilho genérico
`feicao_historico_registrar()` ligado por `plat.camada_preparar` a TODA tabela de camada (não só a
escrita que passa pela API — SQL direto, importação e réplica também ficam registrados), migração
`20260907T1025`. Restaurar reaplica pela MESMA porta de escrita (`_inserir`/`_atualizar` de
`app.edicao.servico`) — feição existente vira `UPDATE`, feição apagada vira `INSERT` com o MESMO
`globalid` (referência externa nunca quebra); a própria restauração grava um marcador
`operacao='restaurar'` a mais no histórico, que nunca é reescrito.

Anexos (`plat.feicao_anexo`, migração `20260907T1035`): limite de tamanho e de tipo aplicados no
SERVIDOR em duas etapas (tamanho da string base64 antes de decodificar, depois o tamanho real) e
contra o conteúdo de fato (item L7-03-b) — um PDF disfarçado de PNG é recusado mesmo com
`content_type` mentindo. Objeto guardado no Garage por trás do adaptador já existente (`app.objetos`).

Dividir/unir (`app/edicao/combinar.py`): geometria estrutural nunca sai do MVT (recortado/generalizado
por tile) — as duas operações leem a geometria exata do banco e usam `ST_Union`/`ST_LineMerge`/
`ST_LineSubstring`. `unir` funciona para qualquer família de geometria; `dividir` está escopado a
LineString/MultiLineString de uma parte só nesta passagem (dividir polígono por linha de corte fica
de fora, registrado no ADR, não escondido).

Dois defeitos de infraestrutura achados e corrigidos nesta rodada (não só no código do item):
`app/garage.py::criar_chave` devolvia um dicionário sem `accessKeyId` no caminho de reaproveitamento
(`ListKeys` usa a chave `id`, `CreateKey` usa `accessKeyId`) — crashava com `KeyError` em vez de um
erro que diz o que aconteceu; e `docs/gerar_limites.py` ficaria não determinístico se um limite fosse
guardado como `frozenset` (a ordem de iteração de um set do Python varia entre execuções) — corrigido
trocando `ANEXO_TIPOS_PERMITIDOS` para tupla ordenada antes de existir um segundo caso.

ADR: `docs/adr/20260907T1123-historico-restauracao-anexos-feicao.md`. Medidas em
`tests/medidas/L2-03-edicao.json` — sem cláusula numérica de tempo neste item; a suíte dedicada (75
testes de API/unit) e o e2e dedicado (6 cláusulas no chromium do playwright, 0 erro de console) estão
registrados lá com o comando exato. Fronteira honesta e vereditos completos no handoff do item.

## turno 3, setembro de 2026 (item L2-03-a-api-edicao-transacional: edição transacional de feições — única porta de escrita)

`POST /api/camadas/{id}/edicoes` (`app/edicao/`): equivalente do `applyEdits` da Esri e, a partir
daqui, a única porta de escrita de feição para navegador, PWA, FeatureServer (L2-04-d) e OGC
(L2-04-g). Corpo com `adicionar`/`atualizar`/`apagar` numa transação — tudo-ou-nada por padrão
(`modo=transacao`), ou `modo=parcial` com `SAVEPOINT` por feição, devolvendo resultado feição a
feição (como o `applyEdits` com `rollbackOnFailure=false`). Roda direto contra a tabela de camada
`d_<slug>.c_<uuid16>` que `plat.camada_preparar` (029_ingestao_vetor.sql) já cria — nenhuma tabela
nova (migração 20260906T1859, bump do esquema `camada_vetorial` v2→v3, só propriedades opcionais).

Validação sempre no servidor: tipo de geometria e SRID da coluna (com a mesma promoção
Point/LineString/Polygon → Multi* que `app/ingestao/carregar.py` usa na carga); `ST_IsValid`, com
`ST_MakeValid` só quando `corrigir_geometria=true` (sem isso, polígono inválido é 422); domínio de
atributo por `dados.regras_campo` (obrigatório, somente-leitura, lista de valores ou
mínimo/máximo — mecanismo próprio deste item; quando o L2-10-a-dominios-subtipos, entregue noutra
trilha, for integrado, ganha uma segunda fonte compartilhada entre camadas, não substitui esta);
tamanho de texto (64 KiB); concorrência otimista pela coluna `versao` já existente na tabela de
camada — atualizar/apagar com a versão errada devolve `409` com a feição ATUAL, nunca sobrescreve
em silêncio; campos de rastreio (`fid`, `globalid`, `versao`, `tenant_id`, `criado_*`,
`atualizado_*`) NUNCA aceitos do corpo, sempre preenchidos pelo servidor; "só as próprias feições"
(`edicao.somente_proprias`) e "geometria travada" (`edicao.geometria_travada`) por camada, com
`feicoes.editar_total` (perfil admin) ignorando as duas. Sanidade de CRS não declarado: coordenada
fora de `[-180,180]`/`[-90,90]` numa camada de SRID geográfico sem `crs.srid` declarado é `422
geometria_fora_do_crs` (cobre o envio de metros — UTM/Web Mercator — sem declarar). Um evento por
LOTE (`camadas/editar`, nunca um por feição) com a contagem de adicionadas/atualizadas/apagadas, e
bump de `dados.tiles_versao` no item (ponto de integração para a invalidação de tiles do L2-01-b,
ainda pendente). Isolamento entre inquilinos por RLS FORCE já existente: o inquilino B recebe `404`
ao ler, atualizar ou apagar feição de A — nunca `403`, nunca sucesso silencioso, porque a existência
não é confirmada a quem não pode ver (ADR 20260907T0216).

Medido: 1.000 feições em `adicionar` (modo transação) em menos de 1 s, contra o teto de 3 s do
portão (`tests/medidas/L2-03-a-api-edicao-transacional.json`). Refutação do item (roteiro do
adversário) rodada nesta passagem: lote de 100 mil feições recusado pelo teto de lista
(`EDICAO_LOTE_MAX=2.000`); `crs.srid=0` recusado pela própria validação de entrada; texto de 1 MB
recusado (`EDICAO_TEXTO_MAX=64 KiB`); geometria em outro CRS sem declarar recusada pela sanidade de
grau; feição de outro inquilino nunca aceita (404); duas sessões editando a mesma feição — só uma
ganha (200), a outra recebe 409 com a versão atual, nunca as duas 200. 20 testes verdes em
`tests/api/test_edicao_transacional.py`.

Fora desta passagem (fronteira honesta, ver ADR): matriz fina de permissão por operação × grupo
(ficou em `edicao.habilitada`/`somente_proprias`/`geometria_travada` + privilégio único);
integração com `plat.dominio` do L2-10-a; consumidor da invalidação de tiles (L2-01-b); histórico/
restauração de feição (L2-03-d-historico-restauracao) — a coluna `versao` cobre só a concorrência
otimista, não um log de mudanças.
## turno 4, setembro de 2026 (item L2-04-servicos-esri-ogc: diretório do FeatureServer, OGC API Features e WFS 2.0)

Construído em volta da operação `query` do FeatureServer (item L2-04-c, `wt/fsquery`, ADR 0018) sem reescrevê-la:
`app/consulta/rotas_servico.py` (descritor de serviço `.../FeatureServer?f=json` e de camada `.../FeatureServer/0
?f=json` — `fields`, `geometryType`, `objectIdField`, `fullExtent`), `app/consulta/rotas_ogc_features.py` (OGC API
Features Part 1: landing, conformance, collections, items com bbox/limit/offset, item único, GeoJSON puro) e
`app/consulta/rotas_wfs.py` (WFS 2.0 KVP: GetCapabilities validado pelo cliente real `owslib.wfs.WebFeatureService`,
DescribeFeatureType mínimo, GetFeature em GeoJSON e GML 3.2 simples). `applyEdits`/anexos/`queryRelatedRecords`/
`relationships` ficam de fora — dependem de L2-03-edicao e L2-10-b, nenhum construído (ADR 0019).

Bateria de 13 ataques (item_id com aspas/comentário SQL/`;`, bbox com sub-select/`pg_sleep()`/função não prevista,
BBOX do WFS com injeção, `REQUEST` desconhecida, `feature_id` não inteiro, unicode no item_id, cross-tenant nas 3
raízes): **13/13 recusados com 400/404, nenhum 500**. Dois achados corrigidos no mesmo turno: (1) `item_id::uuid`
sem validar antes deixava o Postgres levantar exceção sem handler → 500 real, inclusive na `/query` original do
L2-04-c — corrigido com validação de UUID compartilhada; (2) landing/conformance do OGC API Features respondiam 200
para item de outro inquilino (sem vazar dado, mas sem checar posse) — corrigido tocando `plat.item` sob RLS antes de
responder. `docs/PARIDADE.md` e `tests/medidas/L2-04-servicos-esri-ogc.json` têm a tabela cláusula a cláusula.

Fora do turno: QGIS/ArcGIS Pro/AGOL reais carregando o serviço (sem ambiente gráfico nesta máquina, mesma limitação
já registrada para L2-04-c e para Chrome headless); OGC API Features Part 3 (CQL2), WFS-T; GML validado contra o
XSD de referência do OGC.

## turno 3, setembro de 2026 (item L2-04-b-featureserver-catalogo-metadados: diretório de serviços Esri por token)

- Diretório de serviços compatível com Esri em `/svc/{token}/rest/...`: `rest/info`, `rest/generateToken`,
  `rest/services` (pastas do catálogo), `rest/services/{pasta}`, `FeatureServer`, `FeatureServer/{id}`,
  `FeatureServer/layers`, `FeatureServer/info/itemInfo` e `FeatureServer/info/metadata` (ISO 19139).
  O token vai no caminho porque é uma URL que se entrega e o cliente navega sozinho a partir dela;
  a consequência está declarada no ADR `20260907T1955-diretorio-servicos-esri-por-token.md`.
- O FeatureServer não foi reescrito: `app/consulta/rotas_servico.py` passou a expor
  `descritor_do_servico`/`descritor_da_camada` e o diretório as chama. O descritor da camada ganhou
  `indexes` (lidos de `pg_index`), `editFieldsInfo`, `types`/`subtypes`/`typeIdField`, `timeInfo`,
  `ownershipBasedAccessControlForFeatures` e `domain` por campo. `currentVersion` foi de 11.3 para 11.4.
- `app/consulta/formato_esri.py`: `f=json|pjson|html` e `callback` (JSONP) num lugar só. `f` desconhecido
  é 400 e nunca 500; nome de callback fora de identificador simples é recusado, nunca ecoado.
- `app/consulta/renderizador.py`: estilo MapLibre → `drawingInfo`. Cor constante vira `simple`,
  `["match", …]` vira `uniqueValue`, `["step", …]` vira `classBreaks`, `layout.text-field` vira
  `labelingInfo`. Expressão fora desses casos não é aproximada: sai `simple` cinza com o motivo.
- `app/consulta/cors_servicos.py`: CORS aberto em `/svc`, `/ogc` e `/tiles` — e só. Em `/api` a
  credencial é o cookie de sessão, e abrir ali seria falsificação de requisição entre sítios legível.
- O `drawingInfo` lê a relação `estilo_de_camada` (item de tipo `estilo` → camada), declarada pelo
  `PUT /api/itens/{estilo}/relacoes` que já existia; nada foi acrescentado ao catálogo por causa disto.
- Fica declarado como ausente, não simulado: `fields[].domain` nulo, `types`/`subtypes`/`relationships`
  vazios e `capabilities` só `Query` — as linhas L2-10-a, L2-10-b e L2-03-a não estão nesta base.

## turno 3, setembro de 2026 (item L0-06-d-exportar-inquilino: exportar o inquilino inteiro)

Botão "Exportar meu inquilino" em `/admin/organizacao` e o job `inquilino.exportar` por trás dele: o pacote é
um zip com `dados.gpkg` (uma camada por camada hospedada, com metadado e estilo nas tabelas `gpkg_metadata` da
norma), `catalogo.json` (itens, pastas, grupos, compartilhamentos, relações e usuários SEM segredo de
autenticação, validado contra `docs/esquemas/exportacao_inquilino.schema.json`), `arquivos.zip` (os objetos do
bucket, um por item) e `manifesto.json` (sha256 e tamanho de cada componente). A tela mostra o tamanho estimado
ANTES do clique e a cota de uma execução por dia; `app/exportacao_inquilino/importar.py` recria o catálogo num
inquilino novo com os MESMOS uuids. Medido no ambiente de trilha: pacote de 23.782 bytes com 2 itens, 1 camada
e 1 arquivo em 0,55 s (carga 12,02 numa máquina de 12 núcleos, 0,4 GB livres). Detalhe e limites em
`docs/adr/20260907T2245-exportacao-completa-do-inquilino.md`.

Dois defeitos alheios ao item foram corrigidos no caminho: `/admin/organizacao` não terminava de carregar
(zona morta temporal em `smtpAtual`, já em master, medida no navegador) e `app/schema_ambiente.py` tinha duas
sobrecargas de `executemany` vindas de ramos diferentes, a segunda sombreando a primeira.

## turno 3, setembro de 2026 (item L0-06-c-restore-drill: ensaio de restauração do backup)

Job `backup.restore_drill`: restaura o último dump de cada schema num banco de ensaio, compara `COUNT(*)`
de todas as tabelas com `tenant_id` contra a produção, confere o sha256 de até 3 objetos do bucket por
inquilino contra o manifesto e grava tabelas, linhas, divergências, diferenças posteriores e
`duracao_drill_s` em `plat.backup_drill`. Periódico mensal (dia 1, 04:30) e versão curta na suíte, dentro do
`make check`: 3,7 s ponta a ponta com a máquina em carga 7,20, e 21,2 s na rodada que precisa criar o
banco de ensaio (teto da cláusula: 60 s). A base de
comparação é o instante do dump: linha escrita depois dele é registrada como diferença posterior, com tabela
e delta, e não reprova; cópia com mais linhas que a produção, tabela ausente ou sha256 diferente do
registrado reprovam, viram evento `backup/falha` e e-mail ao superadmin. `GET /saude` ganha o bloco
`backup_drill` com a data do último ensaio. Runbook em `docs/RUNBOOKS/restauracao.md`, ADR
20260907T2230. Achado do primeiro ensaio real: o dump do schema da plataforma só restaura numa base com
`postgis`, `pgcrypto`, `pg_trgm` e `unaccent` — sem `unaccent` a tabela `item` não é criada e some em
silêncio; o `install.sh` cria só as duas primeiras.

## turno 3, setembro de 2026 (item L0-06-a-dump-logico: backup lógico diário por inquilino)

Fase 1 do backup, sem reiniciar o Postgres (`archive_mode` está desligado e ligá-lo exige reinício de um
banco compartilhado com outros serviços da casa — a recuperação a ponto no tempo fica para a fase 2, com
decisão do dono). Periódico `backup.dump_logico` às 03:00 no inquilino técnico: `pg_dump -Fc` do schema
`plat` e de cada `d_<slug>`, um arquivo por inquilino, restaurável sozinho. Cada linha de `plat.backup`
guarda sha256, bytes, `tempo_dump_s` e número de tabelas; a cópia vai para o bucket `plat-backup` do Garage
(multipart acima de 32 MB) e, quando as quatro variáveis `PLAT_BACKUP_EXTERNO_*` existem, para um destino S3
externo — configuração pela metade é recusada nomeando o que falta, em vez de mandar o dump para meio
endereço. Junto dos dumps vai um manifesto por inquilino (chave, sha256, bytes) gravado no próprio bucket.

O espaço livre é conferido ANTES de escrever qualquer byte (mínimo 10 GB por padrão); abaixo disso o job
termina em `falhou` com os dois números na mensagem, grava o evento `backup/falha` e enfileira `correio.enviar`
ao superadministrador — falha de backup não pode ser silêncio. Retenção 14 diários + 8 semanais por schema,
apagando linha, arquivo e objeto do bucket juntos. O periódico `backup.verificar` (segundas 05:30) reconfere
o sha256 de cada arquivo e lista arquivo órfão (o que está em disco sem linha em `plat.backup`).

Paridade escrita contra o `webgisdr` do ArcGIS Enterprise em `docs/PARIDADE.md`: cache de tile, dado
referenciado e armazenamento espaço-temporal estão fora dos dois lados, e pelas mesmas razões; a restauração
por inquilino e a retenção automática são nossas e não existem lá.
## turno 4, setembro de 2026 (item L1-02-tiles-token: ladrilho raster por inquilino, token no caminho)

Serviço de ladrilho raster sobre o COG que a ingestão (L1-01) deixou no Garage, com o token de serviço
no CAMINHO da URL (decisão C6 do conceito L1; ADR 20260907T0300).

- `/svc/<token>/raster/<item>/{z}/{x}/{y}[.png|.jpg|.webp]` (XYZ), `/tilejson.json`, `/info.json`,
  `/wmts` (KVP GetCapabilities e GetTile) e `/wmts/1.0.0/WMTSCapabilities.xml` (REST); mosaico da
  coleção em `/svc/<token>/mosaico/<colecao>/{z}/{x}/{y}`.
- Motor rio-tiler 9.4.3 lendo o COG por `/vsis3` com a chave só-leitura do balde do inquilino. Nenhuma
  rota aceita endereço de arquivo: o caminho nasce do catálogo do inquilino do token (sem `?url=`).
- Expressão sobre bandas por parâmetro (NDVI = `(b4-b3)/(b4+b3)`), com gramática própria antes do
  numexpr; faixa, colormap (211 do rio-tiler), seleção de bandas e escolha do asset.
- GetCapabilities do WMTS **valida contra o esquema oficial do OGC** (XSD vendorizado em
  `tests/dados/ogc_xsd`, validação sem rede).
- Cache no nginx com chave SEM o token e `auth_request` que confere token E dono do item a cada
  requisição — sem essa conferência, um token de outro inquilino recebia o ladrilho do cache (achado
  desta bancada, hoje é teste).
- Registro de uso agregado por token em `plat.tile_leitura` (migração `20260907T0249_tile_leitura.sql`)
  e leitura em `GET /api/tiles/leituras`. O token nunca é gravado, só o `token_id`.
- Bancada: `scripts/bench_tiles.py` (carga, `proxy_cache_lock`, revogação) e
  `scripts/prova_cliente_ogc.sh` (driver WMTS e WMS/TMS do GDAL lendo pixel do serviço).
- Medido: **68.738 ladrilhos/s** quente com o cache do nginx (`ab -c 32`, 0 erro; o mesmo nginx serve
  arquivo estático a 68.484/s — o serviço está no teto da máquina); frio 96 ladrilhos/s numa conexão,
  mediana 9,8 ms; 20 pedidos simultâneos ao mesmo ladrilho frio = **1 leitura + 19 acertos**; revogar
  o token passa a 403 em **2,86-2,90 s**. Números e comandos em `tests/medidas/L1-02-tiles-token.json`.
Conserto na migração `20260907T0240_ddl_concorrente_trinco.sql`: `pg_advisory_xact_lock(hashtext(<chave>))`
antes do DDL, chave derivada do objeto tocado. `IF NOT EXISTS` não bastava porque só cobre metade do
problema e nem essa metade é atômica (ADR 0025 seção 2). A classe inteira foi coberta, não só o caso
flagrado: `camada_schema_garantir`, `camada_preparar`, `tenant_criar` (mesmo `d_<slug>`, chave partilhada),
`evento_particao_garantir` e `log_particao_garantir` (mais reconferência depois do trinco) e os dois
expurgadores de partição. `tenant_apagar_interno` fica de fora com razão escrita: só emite `ALTER TABLE`,
que já pega bloqueio pesado na tabela. A chave é por slug, então inquilinos diferentes não esperam um pelo
outro — provado com uma transação segurando `demo` enquanto `demo2` completa em menos de 5 s e `demo`
estoura o `statement_timeout` de 1 s. Guarda contra regressão: `test_toda_funcao_com_ddl_tem_trinco` lê
`pg_proc.prosrc` vivo e reprova função `SECURITY DEFINER` que faça DDL de schema, GRANT ou CREATE/DROP
TABLE sem o trinco — necessário porque a migração redefine funções inteiras e um ramo posterior pode
derrubar o trinco em silêncio. ADR 0025.
## turno 3, setembro de 2026 (DESTRAVA dos 4 pais parciais: L0-05-jobs · L0-04-c-tabela-camada · L0-02-tenant-auth · L0-04-ingest-vetor)

Retomada de queda por cota (worktree `wt/destrava`), tarefa de maior alavanca do laço: conferir cláusula por
cláusula, contra o código de hoje (HEAD já igual ao da árvore principal, 8c2c63c), os 4 itens que travavam 73
dependentes. Achado central: os bloqueios registrados no `estado.json` estavam **defasados** — os "3 consertos
em curso" do L0-05-jobs (semeadura e2e, perfil visualizador, Cache-Control) e a trilha B (catálogo) que o L0-02
esperava já tinham chegado ao HEAD havia dias; o texto do bloqueio nunca foi atualizado.

Quatro defeitos reais, pequenos e cirúrgicos, corrigidos com prova (nenhum tocou `app/main.py`, `app/jobs/tipos.py`,
`app/limites.py` nem `app/catalogo/rotas_itens.py`):
1. **`app/schema_ambiente.py`** — `CursorSchemaAmbiente` só reescrevia `execute()`/`callproc()`; o `executemany()`
   usado por `POST/PUT /api/papeis` (lote de `papel_privilegio`) ia com `plat.` literal e quebrava em qualquer
   trilha/homologação (403 "operação fora do inquilino"). Achado já estava escrito e não commitado no worktree
   (agente anterior morreu no meio); revisado, confirmado com `tests/api/test_usuarios.py` (11/11) e commitado.
2. **`app/catalogo/tarefas.py`** — `catalogo.lixeira_expurgar` calculava `bytes_liberados` por item mas nunca
   escrevia de volta em `plat.tenant.uso_bytes`: a cota do inquilino só subia (achado do adversário G3). Corrigido
   só para `tipo='camada_vetorial'` (o único que a carga incrementa). Medido manualmente: sobe 188.416 na
   importação, volta ao valor exato de antes depois de apagar + expurgar.
3. **Migração `20260906T1812_ingestao_slug_com_hifen.sql`** — `plat.tenant.slug` aceita hífen, mas
   `camada_schema_garantir`/`camada_preparar` (029) e o `pattern` de "schema" no esquema JSON de `camada_vetorial`
   recusavam qualquer slug com hífen (outro achado do G3): um inquilino como `zt-inq-xxxxxx` (o formato do próprio
   fixture `InquilinoTemporario`) nunca conseguia importar camada nenhuma. Relaxado; teste novo
   `test_inquilino_com_hifen_no_slug_importa` prova a importação de ponta a ponta.
4. **`tests/api/test_sessao.py::test_sessao_ociosa_expira`** — `plat.auth_sessao` só usa o parâmetro de teste
   `PLAT_TESTE_OCIOSA_S` quando o inquilino não tem `config.auth.sessao_ociosa_horas` explícito; o `demo` de
   instalação passou a nascer com essa chave preenchida (12 h), travando o teste sempre em 200. Corrigido para
   remover a chave por baixo do bloqueio e devolvê-la no fim (try/finally) — não é defeito do mecanismo de sessão.

Medida nova gravada: `tests/medidas/L0-04-c-tabela-camada.json` — `tempo_import_100k_s = 14,0 s` (teto do portão:
60 s; shapefile dos 100.000 primeiros setores censitários de SP, IBGE Censo 2022, EPSG:4674).

Achado no worktree, não escrito por este turno, revisado e mantido: `db/migrar.sh` ganhou uma guarda que recusa
rodar (código 9) a partir de um `wt/*` sem `PLAT_TRILHA_ALVO` — protege exatamente o incidente descrito em
`BRIEF_WORKTREES.md` item 5 (migração de trilha aplicada em `plat` de produção). Efeito colateral aceito, não uma
regressão: `tests/api/test_migracoes.py` (2 testes) chamam o script direto e agora recusam de dentro de um
worktree — continuam passando a partir da árvore principal, onde a P3 "suíte inteira verde" é de fato avaliada.

Veredito por item (portão literal, cláusula a cláusula — detalhe completo em
`laco/handoffs/T3/DESTRAVA-pais-parciais.md`): os 4 itens permanecem **parcial** — nenhum tinha todas as cláusulas
prontas para virar `entregue` hoje, mas cada um saiu com pelo menos uma cláusula fechada com prova nova e o
bloqueio reescrito com a cláusula exata que falta (nunca deixado em branco).
## turno 3, setembro de 2026 (recurso partilhado sem dimensão de inquilino — laudo `ataque-g3-ADVERSARIO.md`)

Sete achados do adversário G3, todos sobre RECURSO PARTILHADO (o que é por linha já estava protegido por
RLS; o que é da instalação/máquina inteira não tinha dimensão de inquilino nenhuma), consertados em
`db/migracoes/20260906T1615a3f_recurso_partilhado_por_inquilino.sql` + código: (1) chave do trinco
(`plat.job.chave`) passou a ser comparada por `(tenant_id, chave)` — um inquilino não congela mais o
trabalho de outro; (2) fila reparte por inquilino (menos trabalho rodando, depois mais tempo de espera)
antes de olhar a prioridade escolhida pelo usuário — medido: inquilino que chegou 1º saiu da posição 21ª
para a 1ª; (3) `plat.job_ceifar_vencidos` novo permite a API ceifar trabalho sem executor vivo (antes,
68 s depois de um SIGKILL sem nenhum worker de pé, o trabalho seguia "rodando" na tela); (4) morte do
executor sem sinal (`job_ceifar`) passa a consumir TENTATIVA, não reinício — 3 SIGKILL seguidos no mesmo
trabalho fecham "falhou" na 3ª (nunca "concluído"; reproduzido ao vivo,
`tests/api/adversario_g3/g3_sigkill_worker.py`: veredito PASSA); reinício limpo do worker
(`systemctl restart`) continua contando como reinício; (5) `plat.tenant.uso_bytes` virou gatilho simétrico
em `plat.item` (soma no INSERT, devolve no DELETE) em vez de soma manual em `app/ingestao/carregar.py` —
medido: 188.416 → 376.832 → 0 depois de apagar e expurgar (antes ficava em 376.832 para sempre); (6) o
schema de dado do inquilino carrega o prefixo da INSTALAÇÃO (`plat.camada_schema_prefixo()`) — produção,
homologação e as trilhas do laço deixam de escrever todas em `d_<slug>`; (7) orçamento de conexões SSE
(`app/jobs/eventos.py`) virou teto da INSTALAÇÃO com três níveis (usuário/inquilino/total), repartido por
`PLAT_API_PROCESSOS` — antes o teto por usuário era por PROCESSO e a unidade sobe `--workers 2` (o limite
real valia o dobro do publicado, sem nenhum teto por inquilino).

Achado extra, fora do laudo original, do próprio gerente medindo o efeito colateral em produção: o
advisory lock "1 pesado por vez" (`app/jobs/worker.py::_pegar`) também é recurso partilhado — sem
namespace de instalação (`LOCK_PESADO`, cherry-pick `9eb88b9` de `wt/stac`) e com um defeito de disciplina
próprio (`pesado_ok` só refletia a aquisição FRESCA do lock: um worker que já o segurava de uma volta
anterior nunca mais o soltava sozinho — medido ao vivo, a trilha `destrava` segurando o lock horas com a
fila vazia). Testando o conserto apareceu uma TERCEIRA metade do mesmo defeito: advisory lock é reentrante
na mesma sessão, então um worker com `PLAT_WORKER_PROCESSOS > 1` que já tinha um pesado em curso pedia (e
recebia) um SEGUNDO pesado para si mesmo — dois pesados em paralelo no MESMO worker, sem nenhuma outra
trilha envolvida (`tests/api/jobs/test_jobs_fila.py::test_pesado_nunca_em_paralelo_com_pesado`, que já
existia e não tinha essa regressão até este achado). `tests/unit/test_worker_lock_pesado.py` (4 testes)
prova as três metades directement contra a classe `Worker`, sem banco.

`tests/unit/test_recurso_partilhado_por_inquilino.py` (a trava de classe que já existia, virada de
`xfail(strict=True)` para prova de cada um dos 5 pontos do laudo) ganhou um 6º ponto (o lock de pesado) e
reprova qualquer recurso partilhado novo que perca a dimensão de inquilino/instalação.

Achado colateral fora de escopo (registrado, não consertado aqui): `tests/api/jobs/test_jobs_memoria.py`
falha mesmo alocando só 64 MB sob um `RLIMIT_DATA` de 256 MB — confirmado com `git stash` que a falha É
PRÉ-EXISTENTE (reproduz sem nenhuma mudança desta trilha). Medido: o worker, ANTES de forkar qualquer job,
já tem `VmData` (`/proc/<pid>/status`) de ~483 MB — acima do teto de 256 MB que o filho herda por COW no
fork. É item do dono do L0-05-e/memória (RLIMIT_DATA x VmData herdado do pai), não de recurso partilhado.
## turno 3, setembro de 2026 (conserto do grupo G4: dono de objeto, teto de cota, expurgo de rastro, contrato comitado)

Cinco achados do ataque adversarial independente (`laco/handoffs/T3/ataque-g4-ADVERSARIO.md`, ramo `wt/adv4`)
consertados nesta trilha (`wt/g4fix`); decisões em `docs/adr/20260906T1747-g4-conserto-seguranca.md`.
`GET`/`DELETE /api/arquivos/{sha256}` agora exigem ser DONO do objeto ou ter `conteudo.ver_tudo`/
`conteudo.apagar_tudo` (G4-06, G4-07; um visualizador lia e apagava o logotipo da organização). Apagar objeto
grava evento (`arquivos/apagar`) e marca a linha como apagada por `plat.arquivo_apagado_marcar`, `SECURITY
DEFINER` com o inquilino como argumento explícito — não mais um `UPDATE` que a RLS engolia em silêncio fora de
sessão (G4-08, G4-09; a varredura de órfãos parou de acusar toda exclusão legítima). `plat.tenant` ganhou
`cota_bytes_teto`/`cota_usuarios_teto` (padrão 20 GiB / 2000, teto absoluto da instalação 1 TiB / 100.000);
`PUT /api/org` recusa com `422 cota_acima_do_teto` acima do teto do inquilino, e só a plataforma move o teto
(`PUT /api/plataforma/inquilinos/{id}/cotas`, superadmin) — três camadas independentes (esquema, rota,
gatilho `tg_tenant_cota_guarda`) fecham o que antes deixava um admin de inquilino subir a cota a `9×10¹⁸`
bytes com `200 OK` (G4-04, G4-05). `plat.evento_expurgar`/`log_expurgar` agora validam `p_meses` (1-1200, nunca
alcança o mês corrente) e perderam `EXECUTE` de `plat_app`/`plat_worker`; expurgo por UM inquilino é caminho
separado (`*_expurgar_inquilino`, `EXECUTE` só para `plat_worker`) que apaga linha, nunca partição — antes,
`evento_expurgar(-1)` derrubava a partição do mês corrente para todos os inquilinos (G4-10). `docs/openapi.json`
regerado e `tests/api/test_openapi_contrato.py` novo compara o arquivo comitado com `app.openapi()` a cada
rodada — estava 28 rotas atrás, o que fazia a cobertura de evento e a varredura cruzada de isolamento
enxergarem menos rotas do que a aplicação tem (G4-01). Migração
`db/migracoes/20260906T1601_g4_conserto_seguranca.sql`. `tests/api/test_g4_adversario.py` (ramo `wt/adv4`,
copiado) teve as marcas `xfail` destes oito achados trocadas por teste comum; `tests/api/test_g4_conserto.py`
cobre o que o ataque não podia medir de fora (ciclo completo do apagar, permissão de banco, caminho legítimo
do teto). Os demais 16 achados do laudo (G4-02/03/11 a 24) pertencem a outros itens/trilhas e ficam de fora.
## turno 3, setembro de 2026 (item L7-08-b-sdk-python: SDK Python gerado do OpenAPI)

SDK `plat` em `sdk/python/`: `plat_gerado/` gerado por `openapi-python-client` a partir de
`docs/openapi.json` (nunca editado à mão; `scripts/gerar_sdk.sh` regenera; `sdk/python/config_geracao.yaml`
é a única fonte de nomes) e `plat/` escrito à mão por cima (`Plataforma(url, token)`, `.itens`, `.camadas`,
`.mapas` — visões de `.itens` por tipo, não rotas próprias —, `.jobs.esperar()`, `.tokens`, erros como
Problem Details/RFC 9457 traduzidos do contrato real `{"erro","mensagem","detalhe","req_id"}`, ADR 0002
§14). `pip install ./sdk/python` empacota os dois pacotes num só `pyproject.toml` (setuptools, `src`
layout). 10 exemplos executáveis (`sdk/python/exemplos/`) que SÃO os testes (`tests/sdk/test_exemplos.py`,
19 testes no total com cobertura/regeneração/adversário) rodando contra a API real da trilha (uvicorn de
verdade em `:8278`, worker real só para o exemplo de jobs) e o inquilino `demo` semeado.

Achado real corrigido, não do SDK e sim do OpenAPI da própria API: três pares de classes Pydantic com
o MESMO nome Python em módulos diferentes (`Pagina`, `LoteEntrada`, `LoteSaida` — um em
`app/auth/modelos.py`, outro em `app/catalogo/modelos.py`) tinham o MESMO `title` no schema (FastAPI já
desambigua a chave do componente, `app__auth__modelos__Pagina` vs `app__catalogo__modelos__Pagina`, mas
não o `title`), o que impedia QUALQUER geração de SDK (`openapi-python-client` recusa "duplicate models
with name"). Corrigido com `model_config = ConfigDict(title="...")` explícito nas 6 classes — só o
`title` do schema muda, nenhum tipo/obrigatoriedade/nome Python — e `docs/openapi.json` regenerado
(2 linhas de diff). Sem esse conserto não existe SDK gerado possível para esta API, de nenhum gerador.

Medido (`tests/medidas/L7-08-b-sdk-python.json`): 196/196 operações do OpenAPI com módulo gerado
(`sync_detailed`/`asyncio_detailed`); regeneração byte-a-byte reproduzível (`tests/sdk/test_regeneracao.py`,
gerado numa pasta irmã do repositório — fora dele o post-hook `ruff format` do gerador usa outro
`target-version` e o diff vira ruído de ambiente, não do gerador); os 10 exemplos passam contra a API
real; adversário (token de escopo `catalogo:ler` tentando escrever, token de um inquilino lendo item de
outro, varredura de rota sem método) — `tests/sdk/refutacao.json`: **PASSA**. Tabela de paridade contra
`ArcGIS API for Python` em `docs/PARIDADE.md`. Dependência aberta `L2-04-servicos-esri-ogc` (FeatureServer
real) deixa `features.FeatureLayer.query/edit_features` fora desta trilha, nomeado — `.camadas`/`.mapas`
não fingem uma rota que não existe. ADR `docs/adr/20260907T1541-sdk-python.md`.
## turno 6, setembro de 2026 (item L7-06-b-alertas: regras de alerta, roteamento e runbook)

`deploy/alertas.yml`: 16 regras versionadas, as mesmas no hospedado e no appliance — disco acima de
85 % (aviso) e de 95 % (critico), memória disponível abaixo de 2 GiB, job da fila rodando há mais de
30 min, mais de 1 % de 5xx em 5 min, p95 de ladrilho acima de 500 ms por 10 min, certificado a menos
de 14 dias, backup sem sucesso há mais de 26 h, ensaio de restauração não feito no mês, réplica com
atraso acima de 5 min e réplica que sumiu (`absent`), serviço `plat-*` fora por 2 min, alvo caído por
5 min, e o par que vigia o próprio alertador (`AlertmanagerFora`, `PrometheusNaoConsegueFalarComAlertmanager`)
mais a `Sentinela` permanente.

`deploy/alertmanager.yml` (Alertmanager 0.26, apt): rota por severidade, duas regras de inibição
(disco crítico cala o aviso do mesmo ponto de montagem; serviço fora cala o alvo caído do mesmo
alvo), e três receptores — e-mail no molde do `emailsettings` do Portal, webhook compatível com
ntfy/Slack e canal de teste. Nenhum segredo no arquivo: senha e credencial vêm de
`/etc/plat/segredos/*` pelos campos `*_file`, e um teste reprova qualquer literal.

`deploy/alertas_teste.yml`: 24 casos de `promtool test rules`, um por regra mais o vizinho que NÃO
deve disparar. Acharam um defeito de verdade antes de produção: em `a and b` o PromQL devolve o valor
do lado esquerdo, e a mensagem da réplica saía com "atraso de 1s" em vez do atraso real.

`deploy/alertas_homologacao.sh` + `deploy/alertas_receptor_teste.py`: encenação de verdade em
Prometheus e Alertmanager próprios, com os MESMOS arquivos de produção (só os caminhos de segredo
mudam). Enche um volume ext4 de 64 MiB com `fallocate`, derruba um alvo `plat-*` que estava no ar,
grava backup de 30 h atrás, deixa o ensaio sem registro, marca um job como rodando há 35 min e aponta
a API para um certificado curto. Medido em 07/09/2026 (`tests/medidas/L7-06-b-alertas.json`).

`docs/RUNBOOKS/alertas.md`: uma seção por alerta, com o que fazer e como confirmar; o rótulo
`runbook` de cada regra é a chave da seção, e `tests/unit/test_alertas_regras.py` reprova regra sem
seção e seção sem as duas partes. `docs/adr/20260907T1830-alertador.md` registra por que Alertmanager
e não alerting do Grafana — e corrige a hipótese do item: o Alertmanager é um serviço A MAIS, o que
decidiu foi poder testar a regra fora do ar.

Fica de fora, nomeado: banner de alerta no painel do produto (falta decidir que privilégio deixa um
alertador externo escrever no produto) e o casamento automático entre silêncio de manutenção e modo
somente-leitura de instalação inteira, que ainda não existe.

## turno 6, setembro de 2026 (item L7-06-a-metricas-exporters: métricas Prometheus e exporters de infraestrutura)

`app/metricas.py` (biblioteca única, `CollectorRegistry` próprio por processo): `plat_http_requests_total`
+ histograma de latência (rótulo de rota = PADRÃO do roteador, `request.scope["route"].path`, nunca o
caminho literal com id — isso é o que segura a cardinalidade), `plat_tiles_requisicoes_total` (família
pronta, sem chamador ainda em `master`), `plat_jobs_processados_total` (worker), `plat_jobs_fila`/
`plat_jobs_workers_vivos` (API, agregado entre inquilinos via `plat.fila_estado()`, zero cardinalidade
nova). Contrato: rótulo de inquilino é SEMPRE `tenant_id` numérico (`plat.tenant.id`), nunca o slug
(schema `d_<slug>` pode carregar o nome do cliente) nem token. `GET /metrics` em `app/saude.py` (API) e
no servidor bruto do worker (`app/jobs/worker.py`). `app/db.py::_preparar` agora seta
`application_name = 'plat:<tenant_id>'` por conexão com contexto (e `'plat'` sem contexto, para não
vazar o inquilino anterior de uma conexão do pool) — é o único jeito de o `postgres_exporter`, de FORA
do processo, contar conexões por inquilino sem tocar no slug.

Exporters de infraestrutura novos: `postgres_exporter` (apt `prometheus-postgres-exporter` 0.15.0, role
dedicada `plat_metrica_pg` só com `pg_monitor` + `SELECT` em `plat.tenant`, duas consultas próprias de
baixa cardinalidade por `tenant_id`; coletores `stat_user_tables`/`statio_user_tables` DESLIGADOS —
medido: ligados, 231.807 séries, porque o `iagro_sat` é compartilhado por dezenas de frentes da casa;
`statement_timeout`/`lock_timeout` curtos na role depois de um achado real — DDL concorrente de outra
trilha prendeu 7 scrapes em `Lock/relation` por até 4 min) e `nginx_exporter` (apt
`prometheus-nginx-exporter` 1.1.0, `stub_status` interno em `127.0.0.1:8096`, vhost próprio
`deploy/nginx-metricas.conf`). Martin já expõe métrica nativa (achado: em `/_/metrics`, não `/metrics`
— `/metrics` cai na rota de nome de fonte de tile e devolve 404). Os seis viraram *scrape job* novo em
`/opt/monitoring/prometheus/prometheus.yml` (infra da casa, fora do repositório; só acrescentado, nunca
substituído). `X-Req-Id` até Martin: `location /tiles/` nova em `deploy/nginx.conf` que gera/repassa
`$request_id` e grava a MESMA string em `/var/log/nginx/plat_tiles_access.log`
(`deploy/nginx-log-formats.conf`) — Martin não tem como logar cabeçalho arbitrário do próprio processo
(CLI só tem `RUST_LOG`). Provado em produção: `X-Req-Id` de resposta e a linha do log batem, no mesmo
pedido. TiTiler não existe hoje no `plat` (porta 8152 reservada, `PLAT_TITILER_URL` vazio) — cláusula
parcial, mecanismo pronto.

Testes: `tests/unit/test_metricas.py` (7 casos: famílias presentes, rótulo de rota é o padrão da rota
não o caminho literal, assinatura de `registrar_requisicao` sem parâmetro de token, cardinalidade não
cresce com repetição, token de prova não aparece no corpo), `tests/unit/test_db_contexto.py` (2 casos,
`application_name`), `tests/api/test_metricas_rota.py` (4 casos: 200 com as famílias, sem auth, 50
inquilinos sintéticos → 50 séries novas em `plat_http_requests_total` (≤ 5.000 no total), refutação com
500 tokens (10 inquilinos × 50, cada um usado 1 vez e apagado — o produto já limita 20 tokens ativos por
usuário) → só 10 séries novas, nenhum token no corpo, e `plat_jobs_fila` sobe com um job de verdade
(não é número fixo)). `make check`/`tests/unit` e `tests/api` completos: **1 falha pré-existente e não
relacionada** em cada área, confirmadas idênticas com `git stash` (sem nenhuma mudança deste item) —
`tests/unit/test_jobs_registro.py::test_tipos_de_prova_estao_registrados` (poluição de `lru_cache`
entre testes do próprio arquivo) e o bloco inteiro de `tests/api/jobs/*` (`permission denied for table
ambiente` na função `plat.semente_demo_habilitada()` — GRANT que falta na base isolada da trilha,
`laco/trilha_ambiente.sh`, nada a ver com métricas). Não corrigidas aqui (fora do escopo do item; a
segunda é infraestrutura compartilhada do laço, não código do produto).

Achado fora do escopo, registrado em `docs/OBSERVABILIDADE.md` §8: `GET /catalog` do Martin descreve
cada fonte como `"<schema>.<tabela>"` (ex. `"d_demo.t_..."`) — em produção isso vazaria o slug do
cliente para quem alcançar a rota. Não é uma métrica e a rota pública de tiles ainda não existe; fica
para quem entregar `L2-01-b`/`L2-04` de verdade decidir.

ADR 0018 (número provisório — vários worktrees paralelos reivindicam 0018 no momento desta entrega;
renumerar no merge). Documentação: `docs/OBSERVABILIDADE.md` (novo), `MANUAL.md` seção 22,
`ARQUITETURA.md` corrigido (as linhas de `plat-martin` estavam desatualizadas — diziam "não existe"
desde antes do item L2-01-b ter mesclado o serviço de verdade).
## turno 4, setembro de 2026 (item L2-12-a-motor-render-servidor: motor de render no servidor, PNG/PDF por chromium headless)

Pool de páginas do chromium do playwright (`app/render/motor.py::Motor`) mantidas quentes, uma por processo
(`google-chrome` do sistema nunca é usado — regra da casa, ele quebra nesta máquina). Fila com teto
(`PLAT_RENDER_FILA_MAX`, 429 acima do limite) e um teto de tempo único para fila + execução
(`PLAT_RENDER_TIMEOUT_S`). Isolamento de rede por interceptação de rota (só `127.0.0.1`/`::1`/`localhost` e o
host de `PLAT_URL_PUBLICA` em produção passam; o resto é abortado antes de sair da máquina). Token interno
HMAC de curta duração (`app/render/token.py`, TTL cortado a 60 s mesmo se pedirem mais) mais bloqueio por
host (`request.client.host` tem de ser loopback) para uma futura chamada da página headless a uma rota
interna. `POST /api/render/mapa` (extensão/zoom/tamanho/DPI/formato) devolve PNG ou PDF; a página headless
(`web/render_mapa.html` + `web/js/mapa/render_entrada.js`) importa o MESMO `web/js/mapa/estilo.js` do
visualizador interativo — WYSIWYG de verdade, não uma cópia. ADR 0023.

Achado real rodando a medida de p95 sob carga (não hipotético): um `goto` que estoura o timeout deixava a
MESMA página presa, e as navegações seguintes nela falhavam também — exatamente o cenário da refutação do
item ("mata o processo do chromium no meio e confere recuperação do pool"). Consertado ANTES do adversário:
`Motor._pagina_de_reposicao` fecha a página envenenada e abre uma nova no lugar; provado isolado
(`test_pool_se_recupera_de_pagina_que_travou_no_meio`, contra um socket que aceita e nunca responde) e
também exercido pela medida de p95 (12 falhas em 33 tentativas de "quente" e o motor nunca ficou preso).

Medido (`tests/medidas/L2-12-a-motor-render-servidor.json`, `test_frio_e_quente_p95_da_demo_1024x768`):
frio p95 **1.347,8 ms** (2/2 amostras, teto do portão 3.000 ms — **passa**); quente p95 **1.400,2 ms** sobre
21 amostras que terminaram de 33 tentadas (teto do portão 1.000 ms — **não passa**), medido com a máquina
sob `uptime` ~20-23 de carga e `free` com 0 GB livres/swap cheio (dezenas de outras trilhas do laço rodando
ao mesmo tempo; `laco/vivo/leases` no momento confirma). Não repetido em janela mais calma por orçamento de
turno — fica nomeado para o adversário/próximo turno decidir se remede antes de fechar.
`tests/api/test_render.py` (7/7, servidor uvicorn real + chromium real, login com 2FA de verdade — achado:
a conta semeada de `plataforma` exige 2FA, sem isso o teste via 401 sem entender por quê) e
`tests/unit/test_motor_render.py` (7/8, só o de p95 falha pelo motivo acima) cobrem: PNG do tamanho pedido,
PDF gerado, PNG 300 DPI de A4 (2.480×3.508), fila recusando acima do limite, 20 pedidos simultâneos com
pool respeitado e todos < 30 s, página headless sem alcançar host externo (`fetch` para host de fora
resolve com falha de rede, não trava), token interno com TTL ≤ 60 s e bloqueio por host, e recuperação de
página travada.

## turno 4, setembro de 2026 (item L2-12-a-motor-render-servidor: motor de render no servidor, PNG/PDF por chromium headless)

Pool de páginas do chromium do playwright (`app/render/motor.py::Motor`) mantidas quentes, uma por processo
(`google-chrome` do sistema nunca é usado — regra da casa, ele quebra nesta máquina). Fila com teto
(`PLAT_RENDER_FILA_MAX`, 429 acima do limite) e um teto de tempo único para fila + execução
(`PLAT_RENDER_TIMEOUT_S`). Isolamento de rede por interceptação de rota (só `127.0.0.1`/`::1`/`localhost` e o
host de `PLAT_URL_PUBLICA` em produção passam; o resto é abortado antes de sair da máquina). Token interno
HMAC de curta duração (`app/render/token.py`, TTL cortado a 60 s mesmo se pedirem mais) mais bloqueio por
host (`request.client.host` tem de ser loopback) para uma futura chamada da página headless a uma rota
interna. `POST /api/render/mapa` (extensão/zoom/tamanho/DPI/formato) devolve PNG ou PDF; a página headless
(`web/render_mapa.html` + `web/js/mapa/render_entrada.js`) importa o MESMO `web/js/mapa/estilo.js` do
visualizador interativo — WYSIWYG de verdade, não uma cópia. ADR 0023.

Achado real rodando a medida de p95 sob carga (não hipotético): um `goto` que estoura o timeout deixava a
MESMA página presa, e as navegações seguintes nela falhavam também — exatamente o cenário da refutação do
item ("mata o processo do chromium no meio e confere recuperação do pool"). Consertado ANTES do adversário:
`Motor._pagina_de_reposicao` fecha a página envenenada e abre uma nova no lugar; provado isolado
(`test_pool_se_recupera_de_pagina_que_travou_no_meio`, contra um socket que aceita e nunca responde) e
também exercido pela medida de p95 (12 falhas em 33 tentativas de "quente" e o motor nunca ficou preso).

Medido (`tests/medidas/L2-12-a-motor-render-servidor.json`, `test_frio_e_quente_p95_da_demo_1024x768`):
frio p95 **1.347,8 ms** (2/2 amostras, teto do portão 3.000 ms — **passa**); quente p95 **1.400,2 ms** sobre
21 amostras que terminaram de 33 tentadas (teto do portão 1.000 ms — **não passa**), medido com a máquina
sob `uptime` ~20-23 de carga e `free` com 0 GB livres/swap cheio (dezenas de outras trilhas do laço rodando
ao mesmo tempo; `laco/vivo/leases` no momento confirma). Não repetido em janela mais calma por orçamento de
turno — fica nomeado para o adversário/próximo turno decidir se remede antes de fechar.
`tests/api/test_render.py` (7/7, servidor uvicorn real + chromium real, login com 2FA de verdade — achado:
a conta semeada de `plataforma` exige 2FA, sem isso o teste via 401 sem entender por quê) e
`tests/unit/test_motor_render.py` (7/8, só o de p95 falha pelo motivo acima) cobrem: PNG do tamanho pedido,
PDF gerado, PNG 300 DPI de A4 (2.480×3.508), fila recusando acima do limite, 20 pedidos simultâneos com
pool respeitado e todos < 30 s, página headless sem alcançar host externo (`fetch` para host de fora
resolve com falha de rede, não trava), token interno com TTL ≤ 60 s e bloqueio por host, e recuperação de
página travada.

Fronteira honesta: `POST /api/render/mapa` com `mapa_id` de um documento COM camadas devolve `501` — compor
as camadas dentro da página de render depende de servidor de tiles vetoriais (L2-01-b) e raster (L1-02) que
não existem nesta máquina (mesma fronteira já declarada em `app/mapas/documento.py`); o motor genérico
(pool/fila/token/isolamento/PNG/PDF) está pronto para qualquer página, a composição de camada é item futuro.
`deploy/plat-render.service` (porta 8154, `MemoryMax` NOMINAL, não medido sob carga real — a trilha não tem
a unidade systemd isolada) fica para conferência em produção. `docs/openapi.json` comitado não foi
regenerado (ficaria com um diff de milhares de linhas por dessincronia PRÉ-EXISTENTE de outros itens já
juntados neste ramo — regenerar aqui misturaria a autoria; registrado, não escondido).
## turno 4, setembro de 2026 (item L7-08-d-portal-api-chaves: portal da API e chaves de API)

Portal em `/portal`: página própria da casa (sistema visual `web/estilo/tokens.css`, `body.instrumento`),
não Scalar nem Redoc — identidade visual é regra de build, e a página da casa faz três requisições, todas
para a própria origem (ADR 0018 decisão 1). Índice de rota vindo de `/api/openapi.json` com o escopo de
cada uma, botão `Experimentar` que faz a requisição de verdade com a chave colada, e os 20 exemplos
executáveis. Resposta de `/portal` traz `Content-Security-Policy: default-src 'none'` mais `'self'` para
script/estilo/fonte/conexão e `frame-ancestors 'none'`. Medido com o navegador interceptando toda
requisição: **0 recurso externo** (`recursos_externos_carregados_pelo_portal`).

`x-plat-escopo` em **197 de 197 rotas** do OpenAPI, **derivado** da dependência `autenticado(...)` de cada
rota (`app/portal/openapi.py`), nunca escrito à mão — etiqueta escrita à mão envelhece em silêncio, e foi
o que a varredura achou no primeiro dia: `GET /api/uploads/tipos` e `GET /api/importacoes/formatos`
declaram `x-auth: S/T` e respondem 200 a anônimo (só vocabulário estático, sem dado de inquilino; a
etiqueta é que está errada, e o conserto é do item dono), e o descritor do GeocodeServer compatível Esri
declarava exigir escopo sem exigir (é metadado por decisão do ADR 0013 — corrigido para `publico`).
Varredura de regressão da refutação do item: chave de perfil `leitura` em toda rota que exige outro
escopo, **0 resposta 200 indevida** (`respostas_200_indevidas`); a mesma varredura sem credencial nenhuma
também não devolve 200 em rota não-pública.

Chave de API endurecida (migração `20260906T1617_chaves_api.sql`): `plat.token_servico.expira_em` era
**anulável** e `plat.auth_token` aceitava `expira_em IS NULL OR expira_em > now()` — chave sem prazo
valeria para sempre. A API nunca gravou NULL, mas o banco admitia. Agora `NOT NULL` com
`CHECK (expira_em <= criado_em + 366 dias)` e sem o ramo do NULL na função; provado por SQL direto em
`test_banco_recusa_chave_sem_prazo`. Coluna `usos` conta cada requisição autenticada, na mesma linha de
UPDATE que já gravava `ultimo_uso`. Perfis nomeados de chave (`leitura`, `edicao`, `tiles`, `admin`) são
apelidos de conjuntos do vocabulário existente, não escopos novos.

Erro da API passa a ser Problem Details da RFC 9457 por **acréscimo**: `application/problem+json` com
`type` (`urn:plat:erro:<codigo>`), `title`, `status`, `detail`, `instance`, e `erro`/`mensagem`/`detalhe`/
`req_id` intactos como membros de extensão. Decisão D18 embrulhada, não revogada; nenhum cliente da casa
mudou.

Vinte exemplos executáveis em `exemplos/` (10 Python de biblioteca padrão, 10 JavaScript com `fetch`
nativo do Node), lidos do disco pelo portal e **executados pela suíte** contra a API viva —
`exemplos_executados_com_sucesso` = 20, `exemplos_que_falharam` = 0. Exemplo que apodrecer reprova o e2e
em vez de virar documentação errada.

Divergência assumida do portão: o portão pedia "revogar → 403 em ≤ 5 s"; a plataforma responde **401
`token_revogado`**, que é o certo para credencial que deixou de existir e é o contrato do L0-02 já provado
em `tests/e2e/test_tokens.py`. O prazo foi medido e cumprido (`segundos_revogar_ate_negar_no_portal`).
ADR 0018, MANUAL seção 22.
## turno 4, setembro de 2026 (item L4-01-h-alinhamento-inspire-gnm: alinhamento ao INSPIRE Generic Network Model — PARCIAL, elétrica e água)

Mapeamento campo a campo do pacote de ativos (`L4-01-a`) para o Generic Network Model do INSPIRE
(`net`/`us-net-common`/`us-net-el`), documentado em `docs/INSPIRE_GNM.md` (fonte única: `MAPEAMENTO_GNM`
em `app/rede_utilidades/inspire_gnm.py`). Exportador `exportar_gml()` gera GML de uma rede de teste
(elétrica: 3 nós/2 elos com códigos reais de `eletrica-br.json`; água: 2 nós/1 elo) como
`base:SpatialDataSet` com membros `us-net-common:Appurtenance` (nós) e `us-net-common:UtilityLink`
(elos, decisão registrada no documento: `Cable`/`Pipe`/`ElectricityCable` são `UtilityLinkSet`, não
`Link`, e exigiriam uma segunda feature por elo). Validado contra o XSD OFICIAL do INSPIRE (cópia
vendorizada em `app/rede_utilidades/gnm_xsd/`, resolução 100% offline via `gnm_xsd/catalogo.xml`, sem
rede em CI): `xmllint --schema` contra `ElectricityNetwork.xsd` e `UtilityNetworksCommon.xsd`, ambos
`validates` (`tests/unit/test_inspire_gnm.py`, 6 testes verdes). PARCIAL porque o portão pede elétrica,
água e gás: gás fica de fora por não existir pacote-fonte (`L4-01-a` só publicou elétrica e água) — não
é lacuna do mapeamento GNM. Também fora: atributos operacionais (tensão, diâmetro, potência) não têm
correspondência no GNM (ele modela topologia e status, não o dado operacional do ativo) e o teamengine
oficial do INSPIRE não foi rodado (sem instância local nem rede autorizada; a prova usada é `xmllint`
contra o mesmo XSD que o teamengine consome na checagem estrutural).
## turno 3, setembro de 2026 (item L0-09-b-editor-iso-mgb: editor de metadado no Perfil MGB 2.0 da INDE)

Editor completo sobre `app/catalogo/metadado_mgb.py`, em cima do que `L0-09-metadado-catalogo` já tinha
(exportação ISO 19139/GMD somente-leitura): três rotas novas, `GET /api/itens/{id}/metadado` (leitura +
faltantes essencial/completo + avisos), `POST /api/itens/{id}/metadado/validar` (valida um rascunho sem
gravar — o botão "Validar" do editor) e `PUT /api/itens/{id}/metadado` (grava). Migração
`20260907T0148_metadado_mgb.sql` acrescenta `plat.item.metadado_iso` (jsonb) só para a parte PRÓPRIA do
metadado (contato, licença, extensão temporal/espacial declarada, sistema de referência, manutenção,
formato de distribuição); título, resumo, palavras-chave, créditos e termos de uso continuam em
`plat.item` e são computados AO VIVO a cada leitura — nunca duplicados, ao contrário do "Title" independente
do ArcGIS. Mudar o título pelo editor de metadado passa pelo MESMO núcleo do PUT/PATCH de item
(`rotas_itens.editar_item`); mudar o título pela Visão geral aparece no editor de metadado na próxima
leitura, porque os dois leem a mesma coluna (prova: `test_titulo_sincronizado_editor_muda_item_e_vice_versa`).

Linhagem (`qualidade_linhagem`) é sempre computada, nunca digitada: de `dados.procedencia` (quando o item
tiver, formato do item L0-09-a-procedencia) e do histórico de `plat.evento` do próprio item (criação,
atualização de dados) — não existe campo de texto livre para "processo" no editor. Estilo de apresentação
por inquilino (`plat.tenant.config.estilo_metadado`: `mgb2` padrão, `iso19115_3`, `dublin_core`) muda só
rótulo/agrupamento da MESMA leitura — armazenamento único nos três estilos, provado por
`test_estilo_muda_so_apresentacao_armazenamento_e_um_so`.

Refutação do item, as três provadas: metadado de 5 MB (limite declarado 1 MiB) → `422 metadado_grande`;
`extensao.temporal.fim` antes de `.inicio` → `422 metadado_invalido` com o caminho exato do campo; e
`extensao.espacial` declarada divergindo do extent real do item → **aviso, nunca bloqueio** (`avisos` na
resposta, `PUT` continua `200`). 11 testes próprios verdes em
`tests/api/catalogo/test_metadado_mgb.py` (`tests/medidas/L0-09-b-editor-iso-mgb.json` lista cláusula por
cláusula do portão de pronto → prova).

Editor em abas no front (`web/js/catalogo/item_metadado.js`, ligado na aba nova "Metadado" do painel do
item, `web/js/catalogo/item.js`): campos essenciais e completos, botão Validar (lista de faltantes sem
gravar) e Salvar, bloco de linhagem só leitura. `docs/PARIDADE.md` ganhou a comparação campo a campo com a
aba **Metadata** do ArcGIS Enterprise Portal 11.4 (estilos, Validate, XML, Overwrite, Synchronize):
`Overwrite` (importar XML de terceiro) fica `fora` (nenhum item pede isto ainda); a exportação do metadado
no pacote do inquilino fica `fora` porque **`L0-06-d-exportar-inquilino` não existe no repositório** — a
cláusula do portão que dependia dele está registrada como pendência real, não fingida (ADR
`docs/adr/20260907T0148-metadado-iso-mgb.md`, decisão 5).

**Pendências nomeadas**: XML de exportação (`metadado.xml`) ainda não inclui a parte própria nova
(`metadado_iso`) — fica para quando a saída for revisada junto com `L0-06-d`; `L0-09-a-procedencia`
(commit `ac4dbce`) não estava mesclado em `master` quando este worktree nasceu, então a linhagem foi
provada com `dados.procedencia` sintético do mesmo formato, não com uma camada importada de verdade; e2e
de navegador da aba nova fica para o próximo turno (sem tempo de trilha para levantar Playwright contra
`uvicorn` isolado nesta rodada — ver handoff).

### Commits

| sha | mensagem |
|---|---|
| 3c38aa4 | Alinhamento INSPIRE GNM (item L4-01-h): mapeamento, exportador GML e validação contra o XSD oficial |
## turno 3, setembro de 2026 (consertos do ataque G2 ao catálogo — trilha wt/g2fix; ADR 20260906T1623)

O adversário independente do grupo G2 refutou 6 dos 12 itens do catálogo (`laco/handoffs/T3/ataque-g2-ADVERSARIO.md`).
Seis dos nove achados estão consertados e os testes dele perderam a marca `xfail`, passando a exigir o
comportamento certo:

- **Perda de dado (G2-4).** `POST /api/lixeira/esvaziar` com identificador que a segurança de linha não resolvia
  enfileirava `ids: []`; a tarefa lia `[]` como `NULL` e `plat.lixeira_expurgar(0, now(), NULL)` devolvia a
  lixeira INTEIRA do inquilino, com expurgo físico. Agora a rota recusa (404 `nenhum_item_na_lixeira`; 409
  `lixeira_vazia` quando não há nada), a tarefa recusa lista vazia e recusa quando o banco devolve mais
  candidatos do que a lista pediu. Mesma correção em `catalogo.exportar_lista`.
- **Auditoria falsa (G2-5).** Uma atualização barrada pela segurança de linha afeta zero linhas sem erro, e a
  transferência de dono gravava `itens/transferir` de item arrastado que não mudou de dono. A pré-checagem
  passou a declarar a falha `arrasto_sem_edicao` e a execução levanta 409 `transferencia_sem_efeito` quando o
  UPDATE afeta zero linhas.
- **Teto da compactação (G2-3).** A compactação deixava 146 linhas depois de mil gravações contra o teto de 50,
  e o periódico rodava uma vez por dia. `compactar_item` repete a passada até estabilizar e pede
  `manter = teto - 1` (o ponto fixo é `manter + 1` linha); o periódico passou a rodar de hora em hora. A função
  `plat.item_versoes_compactar` não foi tocada.
- **Cache do link (G2-6).** A miniatura entregue por link e pela rota pública sai com `no-store,
  must-revalidate`, como as outras rotas do link; era `private, max-age=300`, e o link revogado continuava
  servindo do cache do navegador por cinco minutos.
- **Estrela de favorito (G2-9).** A tela mostrava o contrário do que o servidor guardou quando havia recarga de
  lista em voo. A intenção passa a ser registrada antes da chamada, com número de ordem, e a lista reconcilia
  toda resposta pedida antes dela.
- **Notificação interna (G2-7).** A metade de notificação do item L0-03-k não existia. Foram construídos a
  tabela `plat.notificacao` (dedup por chave, segurança de linha por usuário, teto por minuto, expurgo de 90
  dias), as rotas `/api/notificacoes`, a emissão em convite de grupo, pedido de entrada e fim de job, e o sino
  na barra lateral. **O item segue PARCIAL**: "item compartilhado comigo" e "prazo de token" ainda não emitem.

Continuam `xfail` de propósito, com a trilha das funções definidoras: G2-1 e G2-2 (`plat.item_versoes_compactar`
apaga versão de item de outro inquilino, e a fila aceita o pedido) e G2-8 (13 funções do schema com EXECUTE para
PUBLIC). A cláusula "nome de item de 2.048 caracteres" do portão do L0-03-f é insatisfazível — o banco para em
250 — e a decisão registrada no ADR é manter o banco e corrigir a cláusula.
## turno 4, setembro de 2026 (item L7-20-trilha-auditoria: trilha de auditoria de negócio)

Tabela `plat.auditoria` (append-only, não particionada, `docs/adr/0031-trilha-auditoria.md`): `REVOKE
INSERT/UPDATE/DELETE/TRUNCATE` de `plat_app` mais trigger `auditoria_imutavel`/`auditoria_sem_truncate`,
com exceção só para o próprio expurgo (marca de transação + dono da tabela, as duas ao mesmo tempo).
Duas escritas cobrem toda rota de escrita do OpenAPI: trigger `AFTER INSERT` sobre `plat.evento` (as
~97 rotas que já registram evento de domínio) e `plat.auditoria_cobrir()` chamada por `app/db.py` antes
do commit de toda transação de escrita (as 15 rotas restantes, sem evento de domínio próprio) —
**112 de 112 rotas de escrita cobertas** (`rotas_de_escrita_cobertas`). Contexto da requisição
(req_id/IP/token/método/rota) chega ao banco por GUC de transação (`app/auditoria.py`, `ContextVar`,
porque `app/db.py` prepara o cursor sem receber o `Request`).

Retenção por inquilino (`tenant.config`), padrão 730 dias, piso de 90 e teto de 3.650
(`limites.AUDITORIA_RETENCAO_*`): o piso é a resposta à refutação do item — sem ele o próprio
administrador apagaria a trilha encolhendo a retenção a 1 dia. Expurgo por `pg_cron`, nome do job
DERIVADO de `current_schema()` (nunca constante — é recurso global da máquina; produção agenda
`plat_auditoria_expurgo`, a trilha `plat_tt4aud_auditoria_expurgo`), idempotente (desagenda antes de
agendar, `jobs_pg_cron_com_o_nome_do_schema` = 1 depois de agendar duas vezes) e negado a `plat_app`.
Achado nesta trilha: `ALTER DEFAULT PRIVILEGES ... GRANT EXECUTE ON FUNCTIONS TO plat_app` (migração
001) dá EXECUTE a toda função nova por padrão — `REVOKE EXECUTE ... FROM PUBLIC` sozinho não bastava
para impedir `plat_app` de chamar `auditoria_expurgar()`; corrigido com `REVOKE` explícito nomeado por
papel (ADR 0031 seção D5), provado em `test_funcoes_de_expurgo_e_de_cron_negadas_a_plat_app`.

Exportação CSV/JSON sai da MESMA função (`plat.auditoria_listar`/`auditoria_contar`) que alimenta a
tela, então a contagem da exportação bate com a contagem em tabela por construção
(`exportacao_linhas_x_contagem`). Tela `/admin/auditoria` (`org.log_ver`) com filtro por usuário e
período, cartão de retenção (`org.configurar`) e nunca um botão de apagar linha. Refutação do item —
adversário edita um item e tenta apagar a própria trilha pela API, por SQL como `plat_app` e por
expurgo prematuro — reprovada nas três frentes (`test_adversario_nao_apaga_a_propria_trilha`).

Fora do escopo, registrado no ADR: `pgaudit` para DDL (decisão de instância, não de migração), envio a
SIEM (sem destino escolhido) e auditoria de leitura da camada `pessoal` (L7-12-a ainda não existe;
gancho pronto com `origem='aplicacao'`).
## turno 3, setembro de 2026 (item L7-06-c-logs-consulta-req-id: log consultável por pedido)

`plat logs --req-id <id>` (`scripts/plat`) reúne, em ordem de relógio, as linhas que nginx, API, worker e
Postgres escreveram sobre o MESMO pedido. O identificador nasce no `$request_id` do nginx, vai ao upstream
em `X-Req-Id` (que sobrescreve o cabeçalho do cliente), a API o adota em vez de cunhar outro, o Postgres o
recebe em `application_name` (`plat:<12 hex>`, que o `log_line_prefix` já registra em `%a`) e o worker o
herda de `proveniencia.req_id` do job. Martin e TiTiler não registram identificador próprio: a ligação com
eles é a linha do nginx que os proxia — está escrito no código para ninguém prometer o contrário.
`plat.log_acesso` ganhou a coluna `req_id` e `GET /api/log?req_id=` filtra por ela, dentro da RLS do
inquilino. Nível de log ajustável em tempo de execução, sem reinício, por logger ou prefixo de rota e com
prazo: `plat log nivel DEBUG --componente app.db --por 10min`, `--listar`, `--remover`; pela API,
`GET/POST/DELETE /api/log/nivel` (só superadmin: afeta o processo, não um inquilino). Retenção de 90 dias
em `deploy/journald-plat.conf`. Conserto de segurança que saiu daqui: a mensagem de toda linha JSON passa
pelo redator, e `?token=`/`?senha=` dentro de uma URL escrita numa mensagem também é redigida — sem isso o
`httpx` deixava o valor inteiro no journal. `app/versao.py` passou a entender worktree do git.

## turno 3, setembro de 2026 (item L2-17-crs-transformacoes: sistema de referência como serviço transversal)

`app/crs/` (registro, grades, serviço, rotas) — sem tabela `plat.*` própria (mesmo padrão de `app/rede`,
L2-11-c): registro de CRS lido do banco EPSG embutido no PROJ da máquina (pyproj 3.7.2/PROJ 9.4.0) mais
uma lista curada brasileira (`app/crs/curada.py`: SIRGAS2000 geográfico e as 21 zonas UTM 31965-31985,
WGS84, Web Mercator, Policônica 5880, SAD69 e Córrego Alegre 1961/1970-72 legados — correção sobre a
hipótese do item, que dizia "31981-31985 e 31965-31975"; o conjunto real medido no registro EPSG é
31965-31985). `GET /api/crs` (curada primeiro), `GET /api/crs/{epsg}`, `GET /api/crs/{epsg}.proj4`,
`POST /api/crs/transformar` (ponto/bbox, escopo novo `crs:usar`). Tela `/crs` (seletor de origem/destino
com a curada marcada ★, prévia em 3857 calculada no NAVEGADOR por proj4js vendorizado a partir das
mesmas definições de `/api/crs/{epsg}.proj4`).

Datum legado (SAD69, Córrego Alegre 1961/1970-72) transformado pelas grades NTv2 oficiais do IBGE
(ProGriD), vendorizadas em `grades_ibge/*.GSB` (sha256 conferido por `grades_ibge/instalar.sh`, chamado
pelo `install.sh` seção h5) e lidas por caminho absoluto num pipeline PROJ sem CRS declarado
(`+proj=pipeline +step +proj=hgridshift +grids=<arquivo>`) — funciona idêntico em `pyproj` e em
`ST_Transform` (mesma libproj), sem depender do CDN do PROJ nem de `PROJ_DATA` compartilhado fora de
`/home/dev/plataforma/`. Fora da cobertura de qualquer grade, cai nos parâmetros geocêntricos do R.PR
IBGE 01/2005 (sem grade, classe de exatidão EPSG 5,0 m) e DECLARA isso na resposta
(`transformacao_usada`, `cobertura`) — nunca silencioso. Detecção de eixos trocados por ÁREA DE USO do
CRS (a checagem `|lat|>90` sozinha não pega a maioria dos casos reais: longitude e latitude do Brasil
cabem as duas em [-90,90]). ADR `docs/adr/20260907T1630-crs-transversal.md`.

Prova da cláusula mais dura do portão ("10 pontos do IBGE ... erro <= 0,05 m"): comparado contra o
serviço OFICIAL AO VIVO do IBGE (`servicodados.ibge.gov.br/api/v1/progrid`, achado por busca — não estava
nos materiais estáticos já baixados) para 10 pontos, o pipeline local bate a <= 0,07 mm; sem
transformação de datum nenhuma, o mesmo ponto erra 62-72 m (`tests/unit/test_crs_grade_ibge.py`, fixture
`tests/dados/pontos_ibge_sad69_sirgas2000.json`, proveniência em `grades_ibge/PROVENIENCIA.md`). Paridade
ST_Transform/pyproj/proj4js em 31982 (sem grade, projeção pura) para 20 pontos: <= 0,01 m nas duas
comparações (`tests/unit/test_crs_paridade_31982.py`, proj4js rodado via Node sobre o mesmo arquivo
vendorizado que o navegador usa). Refutação (`tests/api/crs/test_crs.py`): EPSG inexistente -> 422
`crs_inexistente`; ponto fora da cobertura da grade -> 200 com `cobertura=fora_da_grade_usou_parametros`
e a transformação alternativa nomeada; eixos trocados -> 422 `eixos_suspeitos`; grade e PROJ direto (sem
grade) DIVERGEM de verdade nos mesmos 20 pontos (senão vendorizar a grade não faria diferença nenhuma).
e2e (`tests/e2e/test_crs.py`, checagem estrutural do DOM — a máquina não faz captura confiável de tela):
os dois seletores (origem/destino) mostram a curada primeiro, marcada; fluxo real de transformação exibe
a transformação usada.

**Pendência nomeada**: `app/crs/servico.py::transformar_bbox` devolve o ENVELOPE dos 4 cantos
transformados — por causa da convergência meridiana do UTM/Policônica, o envelope de ida e volta NÃO
reproduz o bbox original (medido: cresce ~700 m no canto para um bbox de 0,2°×0,2° perto de São Paulo,
transformado por 31982). Isso é esperado e documentado (a cláusula do portão fala em CANTO — provada
ponto a ponto —, não em envelope-do-envelope), mas quem for construir a ferramenta "reprojetar" do
L2-05-b sobre uma feição real (não um bbox de consulta) precisa saber que reprojetar um POLÍGONO exige
reprojetar cada vértice, nunca só os 2 cantos opostos do envelope. Sentido inverso SIRGAS2000 -> Córrego
Alegre não é suportado (recusa explícita, `CRSInexistenteErro`): a ingestão só LÊ dado legado, nunca
grava nele, e nenhum consumidor desta plataforma pede essa direção.
## turno 3, setembro de 2026 (item FK-CLASSE-CONSERTO: FK composta por inquilino no resto do schema `plat`)

Mesma classe do achado A1 de `L4-01-a-pacote-de-ativos` (FK simples entre duas tabelas com `tenant_id` não é
filtrada pela RLS — a checagem de referência do Postgres roda com o privilégio do dono da tabela, ignora a
política), fora de `plat.rede_*` (já corrigida em `20260906T1815_rede_fk_por_inquilino.sql`). A varredura de
`pg_constraint` daquele item achou 55 ocorrências fora da rede, listadas como "fora do escopo" na trava
`tests/api/test_fk_composta_por_inquilino.py`; 44 delas já existem no schema `master` (as outras 11 pertencem
a tabelas de trilhas ainda não mescladas — `exportacao`, `geocodificacao*`, `raster_item`, `raster_colecao`,
`rede.dono_id`/`rede.importado_por`). `db/migracoes/20260906T1847_fk_por_inquilino_classe.sql` dá `UNIQUE
(tenant_id, id)` a 10 tabelas-alvo (`usuario`, `papel_personalizado`, `item`, `grupo`, `pasta`, `categoria`,
`compartilhamento_link`, `conexao`, `job`, `token_servico`) e recompõe as 44 FKs como `(tenant_id, col)
REFERENCES alvo (tenant_id, id)`, preservando o `ON DELETE` original de cada uma — as 9 que eram `SET NULL`
usam a sintaxe de lista de colunas do Postgres 15+ (`ON DELETE SET NULL (col)`) para nulificar só a coluna da
FK, nunca `tenant_id` (que é `NOT NULL` em toda tabela do schema; verificado na base da trilha `fkclasse`,
nunca em produção: apagar um usuário referenciado só zera a coluna dele, o `tenant_id` da linha filha não
muda — sem essa sintaxe o Postgres tentaria nulificar as DUAS colunas da FK composta e o DELETE falharia
contra o `NOT NULL` de `tenant_id`). `PERMITIDAS` da trava fica vazio —
zero FKs simples entre tabelas com `tenant_id` no schema inteiro, dívida paga (as 11 restantes reaparecem
como achado novo quando a trilha que as introduz mesclar, e quem mesclar aplica o mesmo padrão).
`tests/unit/test_fk_por_inquilino_classe_conserto.py` prova 5 casos concretos como `plat_app` (alvo comum,
auto-referência uuid, auto-referência inteira, cadeia de duas tabelas): o inquilino B nunca grava apontando
para uma linha de A, e a mensagem de recusa do Postgres é IDÊNTICA para "id não existe" e "id é de outro
inquilino" — mata o oráculo de existência do achado A1. Medidas em `tests/medidas/fk-por-inquilino.json`.
## turno 3, setembro de 2026 (item L7-33-modo-somente-leitura: modo somente-leitura/manutenção global e por inquilino)

Bandeira em `plat.sistema`/`plat.sistema_trilha` (migração `20260906T2109_modo_manutencao.sql`), lida pelo
`ModoMiddleware` (ASGI puro, `app/modo.py`, mesmo desenho de `LimiteCorpoMiddleware` para controlar o
contrato de erro na leitura do corpo): toda escrita (`POST`/`PUT`/`PATCH`/`DELETE`) devolve `503` +
`Retry-After` + Problem Details, exceto `/saude`, `/api/versao`, `/api/modo`, login/logout e `POST
/api/jobs` de um tipo declarado `somente_leitura=True` (campo novo em `app/jobs/registro.py::tarefa`, hoje
só `catalogo.exportar_lista`, congelado na coluna `plat.job.somente_leitura` no momento da criação).
`plat.job_pegar` ganha a cláusula gêmea do lado do SQL: job já `rodando` não é tocado; pendente comum fica
retido enquanto `plat.modo_bloqueia(tenant)`, mesmo com vaga de cota livre; só o tipo `somente_leitura`
continua saindo da fila. CLI `plat modo ligar/desligar/estado` (`app/cli.py`, role `plat_worker` — só ela
tem `EXECUTE` nas funções, a API nunca liga o próprio modo); motivo obrigatório nos dois sentidos, recusado
no SQL (não só no `argparse`), cada chamada grava `plat.sistema_trilha`. `GET /api/modo` público alimenta a
faixa do front (`web/js/base/modo.js::aplicarFaixaModo()`, chamada por `exigirSessao` e por `/entrar`).

Achado consertado durante a montagem do portão: a hipótese do item citava uma rota `/status` que não
existe neste código (o par real de monitoramento é `/saude` + `/api/versao`, ADR 0001 seção 7) — corrigido
em `app/modo.py` e no teste, com a nota de por que a rota não existe.

Medido, com o worker real e o job de 2 minutos (`prova.progresso`) rodando ANTES do modo ligar: termina
normalmente com o modo ligado no meio da execução em **120,1 s** (`tests/medidas/L7-33-modo-somente-leitura.json`);
um segundo job (curto) criado antes do modo, atrás do primeiro na fila de um worker de um processo só,
continua `pendente` mesmo depois de o primeiro terminar e o worker ficar livre — só é pego ao desligar.
Refutação do item: varredura de `docs/openapi.json` (regenerado nesta passagem, estava desatualizado desde
antes deste item — 126 → 149 caminhos) por TODA rota `POST`/`PUT`/`PATCH`/`DELETE`, tentando escrever com o
modo ligado; um único `2xx` fora da isenção nomeada reprova (`tests/api/jobs/test_modo_manutencao.py::test_adversario_openapi_todas_as_rotas_de_escrita_bloqueadas`).
`tests/e2e/test_modo_manutencao.py` prova a faixa no navegador (liga pela CLI, `#faixa-modo` visível em
`/entrar`, captura, desliga, faixa some) — como todo e2e desta suíte, faz SKIP automático dentro de uma
trilha isolada (sem nginx/domínio público) e passou de verdade contra um `uvicorn` solto com
`--base-url http://127.0.0.1:8208`.

Fora desta passagem (nomeado, não escondido): nenhum consumidor (atualização L7-14, failover L7-07-c,
licença vencida L7-11-a) liga o modo sozinho — nenhum dos três existe ainda nesta plataforma. Silenciamento
de alerta durante o modo (L7-06-b): o ponto de leitura está pronto (`/saude` expõe `manutencao.ativo`), mas
não há motor de alerta construído para provar o silenciamento ponta a ponta. ADR
`20260907T1434-modo-manutencao.md`; `docs/PARIDADE.md` (paridade com `mode` do Portal e o site mode
`READ_ONLY` do Server).
## turno 5, setembro de 2026 (item L7-03-b-rate-limit-abuso: limite de taxa em três camadas contra abuso de volume)

Três camadas independentes, cada uma provada com pedidos HTTP reais (ADR `docs/adr/20260907T1500-limite-de-
taxa-tres-camadas.md`, `docs/SEGURANCA.md §9`): (1) nginx por IP, zonas `plat_api`/`plat_tiles` novas
(`deploy/nginx.conf`, `install.sh`) somadas à `plat_login` já existente do L0-02; (2) API por inquilino/plano,
janela deslizante em Postgres (`app/limite_taxa.py` + `plat.limite_taxa_verificar`, migração
`20260907T1444_limite_taxa.sql`, mesmo desenho de `plat.redefinicao_solicitar` da migração 047), chamada de
dentro de `app/auth/sessao.py::resolver` — cobre TODA requisição autenticada da casa, sessão OU token; (3)
fail2ban, jail `plat` dedicada (`deploy/fail2ban/`) sobre um `access_log` próprio do vhost do plat, nunca o
log genérico compartilhado com outros produtos nem o `backend=systemd`/journal que a jail `nginx-limit-req`
já instalada nesta máquina usa (leria todo nginx de todo produto).

Medido com nginx e fail2ban REAIS (`scripts/bench_limite_taxa.sh`, `tests/medidas/L7-03-b-rate-limit-
abuso.json`): zona `plat_api` (rate=120r/m burst=60) segura 37/90 pedidos rápidos em 429 via nginx contra
0/90 na porta direta (prova de que a camada 1 é só do nginx); zona `plat_tiles` segura 91/320 mesmo sem
existir rota de ladrilho real; `X-Forwarded-For` forjado e rotacionado a cada pedido não move o ponto do 429
(192/200 × 197/200, diferença 5 dentro do ruído); `fail2ban-regex` casa 2.226 linhas no log real; e o jail
BANE DE VERDADE (nftables) um atacante de loopback (`127.0.0.9` — nunca um IP real, ver o ADR) depois de 30
tentativas de login erradas, confirmado com o próprio `curl` sem resposta (000) durante o banimento e
desbanido logo depois. `X-Forwarded-For` no nível do processo já estava resolvido por um item anterior
(`deploy/plat-api.service` já sobe `--proxy-headers --forwarded-allow-ips 127.0.0.1`): este item prova que
`app/auth/sessao.py::ip_de()` herda essa defesa sem mudança nenhuma, em vez de inventar mecanismo novo.

Refutação do item — 10 casos em `tests/api/test_limite_taxa.py`, todos verdes: "50 IPs contra o mesmo
token" (a chave da camada 2 é `tenant:<id>`, nunca o IP — rotacionar o cabeçalho não devolve cota) e "1 IP
contra 50 tokens" (a camada 2 não segura isso sozinha por desenho — quem segura é a camada 1, que não sabe
o que é um token); cláusula "inquilino não afeta outro" com dois inquilinos temporários e teto igual; e uma
rede de segurança para o próprio laço — o padrão de produção (6000/min por inquilino) é alto o bastante para
não atrapalhar a suíte inteira martelando `demo`/`demo2`.

**Pendência nomeada, não fingida**: `L1-02-tiles-token` (rotas `/tiles/...`/`/svc/<token>/raster/...`) está
`entregue` mas não mesclado nesta base (`app/imagens/` não existe neste worktree — `laco/handoffs/T4/L1-02-
tiles-token.md`); a cláusula "tile acima do limite do plano" fica **parcial**: a zona de borda (`plat_tiles`)
já protege `/tiles/` mesmo sem a rota, e o mecanismo da camada 2 já suporta o escopo `tiles` (testado
diretamente na função SQL) — falta só anexar `limite_taxa.exigir(..., "tiles", ...)` no ponto que resolve o
token de ladrilho quando aquele ramo mesclar.
## turno 4, setembro de 2026 (item L0-03-e-compartilhamento: fechamento com o achado G2-6 e o segredo do link fora do log)

- Miniatura servida por link (`/api/compartilhado/{token}/itens/{id}/miniatura`) e pela rota pública sai com
  `Cache-Control: no-store` (`miniatura.entregar(cache=...)`): link revogado nega em ≤ 1 s também na imagem (G2-6).
- O token do link viaja no caminho da URL e ia inteiro para `plat.log_acesso.rota` (lida em /admin/log) e para o
  journal; `app/auth/redigir.py::caminho_redigido` redige o segmento depois de `/api/compartilhado/` e `/c/`.
- Diálogo Compartilhar: dependência abaixo do nível escolhido ganha aviso e etiqueta; "elevar ao nível do mapa" e
  "marcar todas as que posso elevar" são escolha explícita, só aplicadas ao Aplicar; a árvore reflete o nível novo.
- Página anônima `/c/{token}` escrevia o texto "null" no lugar de miniatura/resumo ausentes (append nativo).
- Testes novos: varredura cruzada A→B nas 10 rotas de compartilhamento (`test_compartilhamento_cruzado.py`), 404
  indistinguível de inexistente, público ligado em inquilino descartável, e2e com contexto anônimo do playwright
  (`tests/e2e/test_compartilhamento.py`, frente HTTP de trilha em `tests/e2e/frente_trilha.py`), medidas em
  `tests/medidas/L0-03-e.json`; `docs/PARIDADE.md` ganhou a seção "Compartilhamento de item".
## turno 3, setembro de 2026 (item L6-02-k-agendamento: atualização agendada de camadas copiadas)

Não é outro relógio: `conexao.atualizar_copia` é só mais um tipo de job agendável pelo mecanismo do L0-05
(`plat.agenda`, `app/jobs/agenda.py::tick`, cron mínimo de 15 min já validado). Busca o conteúdo pelo
conector (`app.conexao.seguranca.buscar_seguro`, defendido contra SSRF, `guardar_corpo=True`, teto próprio
`CONEXAO_COPIA_MAX_BYTES` = 8 MiB) e grava uma VERSÃO nova em `plat.camada_copia_versao`; a troca é atômica
por ponteiro (`plat.camada_copia_atual`, um UPSERT de uma linha) — a antiga só sai quando a nova entrou
inteira, e se o worker morrer no meio (ROLLBACK), a camada antiga continua íntegra (provado com um leitor
concorrente que nunca viu a linha vazia nem uma versão não comitada, `test_troca_atomica_sobrevive_a_
rollback`). Poda para 1 versão por conexão a cada ciclo (disco a 98%, D21). Teto de tarefas ATIVAS por
USUÁRIO (`plat.cota_agendas_usuario`/`plat.agendas_ativas_usuario`, default 10 — a referência Esri; o teto
de 50 por organização já existia em `plat.cota_agendas` desde a 004), aplicado em `agenda_criar`/
`agenda_retomar`. Quando 5 falhas seguidas pausam a agenda (mecanismo já existente, `plat.agenda_registrar_
fim`), agora grava um aviso em `plat.agenda_aviso` (throttle de 1 a cada 6h, decidido na entrada da fila);
o periódico `agenda.avisos_enviar` (a cada 15 min) drena e enfileira `correio.enviar` para o e-mail do dono
da agenda. Migração `20260907T1631_conexao_agendamento_camada.sql`.
## turno 3, setembro de 2026 (item L2-07-a-pwa-instalavel-cache: PWA de campo instalável, com cache offline)

PWA em `/campo/` — manifest, ícone (192/512, `any`+`maskable`), service worker sem workbox e app shell
próprio (HTML/CSS/JS, 28,6 KB somados; teto do portão é 1,5 MB) servidos por rotas dedicadas em
`app/campo/rotas.py`, nunca por `/static/` (ver ADR `20260907T1400-pwa-de-campo-shell-proprio.md`: a API
deliberadamente não monta `StaticFiles`, então o shell do PWA precisa se bastar para ser testável numa
trilha isolada sem nginx). Sessão de campo (`POST /api/campo/sessao`) reaproveita o token de serviço
genérico do L0-02-d com o escopo `campo:usar` já reservado no vocabulário (`app/auth/escopos.py`), 30
dias fixos, revogável como qualquer token; `GET /api/campo/mapas` projeta só o que o item precisa (RLS de
`plat.item` cuida do isolamento entre inquilinos). Cache do shell versionado por `web/campo/VERSAO_SHELL`
(não pelo git sha do repositório inteiro — motivo no ADR), `skipWaiting`+`clients.claim` mais uma checagem
de atualização em segundo plano a cada abertura (`app.js::registrarServiceWorker`), o que faz uma troca de
versão valer já na PRÓXIMA recarga (medido: 1). IndexedDB (`idb.js`) guarda token, mapas e a fila de
sincronização (vazia por enquanto — o emissor fica para o L2-07-c); a UI mostra indicador online/offline,
contagem da fila, estimativa de `StorageManager` e pedido de persistência. Achado corrigido durante o
teste de isolamento: o IndexedDB é isolado por ORIGEM, não por inquilino — sem checar a sessão ativa
contra o `tenant_slug` salvo, um segundo login (outro inquilino, mesmo navegador) reaproveitava o token
antigo; `app.js::obterSessaoAtual` agora descarta config e mapas quando o inquilino muda.

Suíte e2e roda contra HTTPS de verdade (certificado autoassinado + `--ignore-certificate-errors`), não
HTTP como o resto do repositório — é a única chamada do item que precisa (`app.js` grava o token por
`fetch()` de DENTRO da página, e a defesa de CSRF por `Origin`, ADR 0002 seção 5.3, só bate corretamente
quando o `Origin` real do navegador casa com `PLAT_URL_PUBLICA`). Lighthouse (pacote npm, categoria `pwa`
removida da v12 em diante — fixado em `lighthouse@^11.7.1` só em `tools/`, fora do git) sem item vermelho.
Refutação: armazenamento apagado no meio de uma coleta (o app ressincroniza sem travar), relógio do
dispositivo mudado (o servidor decide validade, nunca o cliente), PWA de outro inquilino no mesmo
navegador (token nunca aparece na linha de acesso — `tests/api/test_campo.py`). Medidas em
`tests/medidas/L2-07-a-pwa-instalavel-cache.json`.
| (este) | Editor de metadado no Perfil MGB 2.0 da INDE, abas essencial/completo (item L0-09-b-editor-iso-mgb) |
## turno 5, setembro de 2026 (item L6-02-d-arcgis-rest-externo: conector ArcGIS REST de terceiro — modo referenciado)

Leitura de serviços ArcGIS REST de Portal/AGOL de terceiro sobre `app.conexao.seguranca.buscar_seguro` (item
L6-02-a, nunca um cliente HTTP à parte): `app/conexao/esri_rest.py` (motor) + `app/conexao/rotas_esri_rest.py`
(`/api/conexoes/{id}/esri/*`). FeatureServer/MapServer: descrição da camada (geometria, `maxRecordCount`,
campos, capacidades), contagem por `returnCountOnly` e query paginado (`resultOffset`/`resultRecordCount`
sempre clampado ao `maxRecordCount` do servidor, com teto de páginas/feições — três travas independentes
contra servidor hostil). MapServer `export` e ImageServer `exportImage`: proxy de imagem dinâmica/raster
referenciado. Simbologia simples (`renderer.type=simple`, `esriSFS`/`esriSLS`) importada como cor de
preenchimento/contorno RGBA; `classBreaks`/`uniqueValue`/marcador de imagem ficam fora, sem fingir suporte.
Token do cliente decifrado só em memória e injetado como `token=` na querystring da chamada ao serviço
externo (convenção clássica do ArcGIS Server — diferente do Bearer do teste de saúde genérico), nunca no
corpo/erro da nossa API. ADR 0020; paridade em `docs/PARIDADE.md` seção "Conector ArcGIS REST externo".

Achado ao testar contra rede real (SIGEL/ANEEL, `sigel.aneel.gov.br/arcgis/rest/services`, ArcGIS Server
11.5): a raiz de um FeatureServer/MapServer sem `?f=json` devolve a página HTML do diretório de serviços do
ArcGIS Server, não o JSON esperado — `_buscar_json` corrigido para sempre anexar `f=json`. Medido: 3
serviços públicos federais brasileiros (EOL — ponto, `Areas_Publicas` — polígono com simbologia laranja/
contorno preto, `Distribuição` — polígono) responderam HTTP 200 em 07/09/2026, adicionados como conexão e
vistos (descrição + camada + simbologia); contagem da API bateu com a `returnCountOnly` bruta do serviço
(2.490); query paginada por UF trouxe geometria e atributos reais; `SIGEL/Linhas_de_Transmissao` (exige
token real, `{"error":{"code":499,"message":"Token Required"}}`) devolveu erro claro em < 30 s sem
credencial, sem retry em loop; `MapServer/export` devolveu PNG 256×256 real. Refutação do item
(`maxRecordCount=1`): provada sem rede (nenhum serviço público brasileiro com esse valor foi encontrado) —
`consultar_tudo` monkeypatchado com um servidor que nunca sinaliza fim de página para no teto
`ESRI_REST_PAGINAS_MAX` (50), sem loop infinito. 23 testes (17 de unidade + 6 de API com rede real,
`tests/unit/test_esri_rest_analise.py` e `tests/api/test_esri_rest.py`), suíte de conexão (`test_conexoes.py`
+ `test_conexao_seguranca.py`) continua verde.

Fora deste turno, nomeado: modo copiado (materializar em PostGIS — mesma fronteira do L6-02-b/c, ainda não
integrados a master); ImageServer `exportImage` com rede real (nenhum ImageServer público brasileiro
encontrado nesta sessão — código e teste de unidade escritos, prova de rede fica pendente); formato `f=pbf`
na query paginada (só `geojson` implementado; a hipótese cita os dois).
## turno 4, setembro de 2026 (item L0-14-identidade-visual: sistema de design "instrumento" e a régua)

Identidade visual do produto sobre uma fonte única de tokens (`web/estilo/tokens.css`: 108 tokens `--i-*`, cor
em claro e escuro, escala tipográfica, grade de 4 px com três densidades, raio, fio, sombra, larguras). Folhas
`web/estilo/base.css` e `web/estilo/componentes.css` substituem `web/style.css`; as folhas de tela
(`tarefas.css`, `conteudo.css`, `mapa.css`) e o estilo MapLibre (`web/js/mapa/estilo.js`, agora lê `--i-carta-*`
por `getComputedStyle`) só usam `var(--i-*)`. A varredura `tests/unit/test_estilo_tokens.py` reprova cor ou
medida de ritmo escrita à mão em css/js fora dos tokens, glifo ou emoji fora da família de ícones, tela sem
as três folhas e o `tema.js`. Par tipográfico com motivo em `docs/IDENTIDADE.md` (Big Shoulders Display ·
IBM Plex Sans · IBM Plex Mono, vendorizadas com sha256, OFL-1.1). Família única de ícones em
`web/js/base/icones.js` (84 ícones desenhados por DOM); os glifos de texto do produto (marcas, setas,
bolinhas, reticências, o "x" do diálogo) viraram ícones. Os 6 componentes de base têm os 7 estados (repouso,
foco visível, ativo, desativado, carregando, vazio, erro) em CSS e em código (`plat-tabela.ocupado/erro`,
`plat-busca.ocupado/erro/limpar`, `plat-paginacao.ocupado/erro`, `plat-dialogo.ocupado/erro`, `plat-aviso.carregando`).
Página viva `/estilo` (`web/estilo.html`, `web/js/estilo/estilo.js`) lê o arquivo de tokens pela rede e desenha
paleta com razão de contraste medida no navegador, escala, grade, forma, ícones e os 6 × 7 estados com os
elementos reais; tema (sistema/claro/escuro) e densidade escolhíveis, guardados em `localStorage` e aplicados
antes da primeira pintura por `web/js/base/tema.js`. Traço próprio: a RÉGUA — todo número mostrado carrega a
procedência (rota, instante, comando) em `data-procedencia` e `aria-label`, com a linha de procedência das
últimas chamadas à API no rodapé de toda tela (`web/js/base/regua.js`, `registrarChamada` em `api.js`).
Medido (`tests/medidas/L0-14.json`): 0 nó de texto abaixo de AA em 2.235 nós (escuro) e 2.234 (claro) nas 16
telas; axe-core sem violação crítica ou séria (7 menores por tema); capturas antes/depois em
`tests/e2e/capturas/L0-14_*`. Achados de passagem corrigidos: zona morta temporal de `smtpAtual` em
`web/js/auth/organizacao.js` (erro de página em `/admin/organizacao`) e o `<input type=file>` de `/uploads` sem
rótulo. `scripts/servir_local.py` sobe API + `/static/` de um worktree para abrir as telas sem nginx.
## turno 3, setembro de 2026 (item L7-01-c-dado-demonstracao: pacote de dado de demonstração aberto)

`dados/demo/catalogo.json` + `dados/demo/arquivos/` (0,96 MB, teto 300 MB): 9 arquivos abertos —
limites municipais do IBGE (Amapá/Roraima em `demo`, Acre em `demo2`, prova de isolamento), ponto
municipal derivado, rodovia federal (DNIT), hidrografia (ANA/BHO), estações do INMET, um recorte
real de Sentinel-2 (visual/TCI, ESA/Copernicus, via Earth Search) guardado como arquivo (sem
pipeline de raster nesta base — L1-01-ingest-raster segue parcial) e um extrato aberto do
OpenStreetMap (vias e nós de Fernando de Noronha, ODbL) usado como arestas/nós de uma composição
do tipo `rede`. `dados/demo/LICENCAS.md` é GERADO por `dados/demo/gerar_licencas.py` a partir do
catálogo (fonte, órgão, URL, licença e data de acesso de cada arquivo — nunca escrito à mão).

CLI `scripts/plat demo semear` (cria os itens pela própria API: arquivo → importação → camada
vetorial nos itens marcados `ingerir`, mais 1 mapa, 1 painel, 1 formulário e 1 rede compostos sobre
as camadas recém-criadas) e `scripts/plat demo verificar` (confere sha256/tamanho no disco e a
presença de cada item nos inquilinos `demo`/`demo2`, sem semear nada). Reusa o desenho do item
L0-13-dado-demonstracao (ramo `wt/t13`, ainda não integrado a `master`).

Medido (`tests/medidas/L7-01-c-dado-demonstracao.json`, `PLAT_GRAVAR_MEDIDAS=1`): 9 arquivos com
fonte/URL/licença/data de acesso; 0 ocorrência de nome de cliente/parceiro/piloto (22 nomes, 14
arquivos varridos, inclusive dentro dos `.zip`); pacote com 1,011 MB (teto 300 MB); 19 itens
semeados em `demo` (8 arquivos + 6 camadas + 1 mapa + 1 painel + 1 formulário + 1 rede — o raster
fica só como arquivo); reexecução idempotente em 0,45 s (0 arquivo/camada/composição novos). 12/12
testes verdes (`pytest tests/api/test_dado_demo_l7.py`).

Cláusula pendente, nomeada: uma corrida completa de ingestão travou duas vezes em "baixando o
arquivo" por contenção do Postgres compartilhado (outras trilhas concorrentes prendendo a consulta
de introspecção do driver GDAL/PostGIS em lock de relação por 8-65 min, visto em
`pg_stat_activity`); a terceira tentativa, com a fila mais livre, completou em 7 s. Não é defeito
do item: registrado para quem for medir tempo de semeadura sob carga.

Riscos de merge: nenhum arquivo do L0-13 foi tocado (`dados_demo/` dele é um diretório diferente de
`dados/demo/` deste item); `CHANGELOG.md` só ganhou esta entrada no topo.
## turno 3, setembro de 2026 (item L6-02-b-wms-wmts: conector WMS/WMTS externo)

Conector de WMS (1.1.1/1.3.0) e WMTS (KVP e RESTful) em `app/conexao/wms_wmts.py`, sobre `buscar_seguro`
(item L6-02-a), sem `owslib` (não instalado nesta máquina): GetCapabilities analisado à mão com `defusedxml`
(nunca resolve entidade externa — defesa contra XXE independente de tamanho); WMS devolve bbox sempre
lon/lat mesmo quando a fonte declara eixo lat/lon (WMS 1.3.0 + EPSG:4326/4674/4269/4258); GetMap/
GetFeatureInfo com CRS/tag corretos por versão (`CRS`/`I`/`J` em 1.3.0, `SRS`/`X`/`Y` em 1.1.1); WMTS com
TileMatrixSet nativo 3857 gera template `{z}/{x}/{y}` direto para o MapLibre; TileMatrixSet noutro CRS passa
por `mosaico_tile_reprojetado` (GDAL via `rasterio.warp`, até 4 tiles nativos por tile de saída, aviso
`mosaico_parcial` acima disso). Rotas em `app/conexao/rotas_wms_wmts.py`
(`/api/conexoes/{id}/wms/capacidades|mapa|feicao`, `/wmts/capacidades|tile-info|tile/{tms}/{z}/{x}/{y}`),
credencial injetada só no proxy (nunca sai na resposta), cache em processo por (conexão, operação,
parâmetros).

Três bugs reais só apareceram ao testar contra serviço público de verdade (a fixture da análise não os
pegava): `_href_get` lia `href` no elemento `<Get>` em vez do `<OnlineResource>` filho (URL de GetMap/
GetFeatureInfo sempre caía no `url_base`); `analisar_wmts` usava a função de busca de operação do WMS
(`<Capability>/<Request>`) para achar a URL de GetTile do WMTS, que declara em `<OperationsMetadata>/
<Operation>` — `url_kvp` sempre `None`; `_normalizar_crs` não entendia a forma URN com versão do meio
(`urn:ogc:def:crs:EPSG:6.3:3857`, do GeoWebCache do BDGEx) — TileMatrixSet 3857 nunca era reconhecido como
nativo. Um quarto, mais sério: `TopLeftCorner` do WMTS é lido na ordem de eixo do CRS declarado (tabela 7 da
1.0.0), e para CRS geográfico (mesma lista EPSG:4326/4674/4269/4258 do WMS 1.3.0) isso é (lat, lon) — o
código tratava sempre como (x, y), e o cálculo de índice de tile em `mosaico_tile_reprojetado` saía da
grade (`ValueError: negative dimensions`) contra o BDGEx real. Corrigido normalizando `topo_esquerdo` para
(x, y) = (leste/lon, norte/lat) sempre, na análise.

Portão de pronto (`tests/medidas/L6-02-b-wms-wmts.json`): 6 testes sem rede com fixture em
`tests/unit/test_wms_wmts_analise.py` (WMS 1.1.1, eixo invertido 1.3.0, XXE de 40 MiB simulado, teto de
bytes, WMTS KVP nativo 3857, WMTS RESTful EPSG:4674 não-nativo) + 3 testes com rede real marcados
`pytest.mark.lento` em `tests/api/test_wms_wmts.py` contra dois serviços públicos brasileiros medidos em
07/09/2026: WMS = INDE (`geoservicos.inde.gov.br`, 1.3.0, 5.126+ camadas) e WMTS = BDGEx (Exército;
`ctmmultiescalas_mercator` nativo `GoogleMapsCompatible`/3857, `ctm250` só em `bdgex`/EPSG:4326). GetMap,
GetFeatureInfo (atributos reais) e o proxy de reprojeção (tile geográfico → PNG 3857) passam fim-a-fim.
Ressalva honesta: nenhum WMTS público brasileiro com EPSG:4674 EXATO foi encontrado (IBGE devolveu HTTP
500 no `gwc/wmts` nas tentativas); o caso 4674 literal fica provado sem rede pela fixture/adversário, e o
mesmo caminho de código é provado com rede real contra EPSG:4326 (mesma família geográfica, mesmo bug de
eixo, mesma correção). A cláusula "vê no mapa" foi verificada no nível de API (GetMap devolve PNG válido
consumível pelo MapLibre), não por Playwright — marcado como limitação, não como aprovado sem prova.
## turno 3, setembro de 2026 (item L6-01-c-tela-acervo: tela do Acervo — busca, ficha, adicionar ao mapa e atribuição na legenda)

Tela `/acervo` (`web/acervo.html`, `web/acervo.css`, `web/js/acervo/acervo.js`): filtro pelos **22 domínios**
da taxonomia de `acervo.fonte` (medido, `tests/medidas/L6-01-c-tela-acervo.json`), busca por nome e órgão,
cartão por fonte (órgão, domínio, etiqueta de licença, frescor, tabelas, registros) e ficha completa de
procedência em painel lateral, com pré-visualização do endpoint vivo quando existe. Rota nova
`GET /api/acervo/dominios` devolve a taxonomia inteira com a contagem de fontes VISÍVEIS por domínio: domínio
sem fonte visível hoje aparece com zero, nunca some da lista.

Licença curada entra na lista, na ficha e no instantâneo gravado ao adicionar (`licenca_curada_tipo`, do
vocabulário fechado de `plat.acervo_licenca`, item L6-01-g) — nunca inferida do texto livre de `licenca`.
ODbL e CC-BY-SA acionam o aviso de atribuição obrigatória em dois lugares: na ficha e na legenda da tela
`/mapa`. A legenda lê `GET /api/acervo/meu-mapa`, rota nova que lista as camadas do acervo já adicionadas ao
catálogo do inquilino (`dados->>'protocolo' = 'acervo'`, isolamento pela RLS de `plat.item`) — `GET /api/itens`
não serve porque não devolve `dados` e não filtra por protocolo.

Medido no e2e `tests/e2e/test_acervo.py` (1 teste, percurso inteiro, contra o uvicorn da trilha): 22 domínios
no filtro; buscar "unidades de conservação" devolve **0 cartões** e as 3 fontes com esse nome no acervo — todas
sem licença escrita — não aparecem nem têm o identificador no HTML; adicionar cria 1 item `conexao` em modo
`referenciada` (sem cópia de dado); a legenda do mapa mostra o nome, a licença e a linha de atribuição;
`document.body.scrollWidth` = 390 px num visor de 390 px em `/acervo` e em `/mapa`; **0 erro de console** em
todo o percurso. Capturas em `tests/e2e/capturas/L6-01-c-tela-acervo_{ficha,legenda_no_mapa,celular}.png`.

Correção de borda na tela do mapa (item L2-01-a), achada ao medir o responsivo: painel flutuante ganhou
`max-width: calc(100% - var(--e4) * 2)` — o seletor de camada base media 378 px e terminava em 394 px num visor
de 390 px, empurrando a página 2 px para fora da tela.
## turno 10, setembro de 2026 (item L0-08-a-oidc: causa-raiz do 403 nas rotas de papel em trilha/homolog)

`CursorSchemaAmbiente` (item L0-08) sobrecarregava `execute` e `callproc`, mas não `executemany` — e o
psycopg2 não roteia `executemany` pelo `execute` (laço próprio em C). A rota `POST /api/papeis` (e
`PUT`, na edição) insere os privilégios com `executemany("INSERT INTO plat.papel_privilegio ...")`; em
trilha/homologação o literal sobrevivia à reescrita, o INSERT batia no schema de produção e voltava
42501 "permission denied for schema plat", convertido pela camada de erro em 403 "operação fora do
inquilino da sessão" — falha com diagnóstico trocado, a classe que o G4-23 condenou. Sobrecarga de
`executemany` acrescentada (`app/schema_ambiente.py`) e regressão unitária nova
(`tests/unit/test_schema_ambiente.py`, 5 testes: executemany/execute/callproc reescritos, GUC
`current_setting`/`set_config` preservado, schema padrão passa igual). Prova de API no ambiente da
trilha do item: 14 casos cruzados passam (`tests/api/test_cruzado.py -k "papeis or sso or oidc"`).
Ainda em aberto no escopo da suíte cruzada (itens de OUTROS ramos, não deste): 41 rotas publicadas no
OpenAPI sem caso em `tests/api/cruzado_casos.py` — convites, SMTP da organização, redefinição de
senha, uploads multipart, importações, geocodificador (`/api/geocodificar`, `/api/reverso`,
`/api/sugerir`) e os `GET` de `/ogc/records`.
## turno 3, setembro de 2026 (item L2-02-e-simbolos-sprites-glifos: biblioteca de símbolos, sprite por inquilino e glifos de fonte)

Biblioteca própria de símbolos em `app/simbolos/biblioteca.py`: **153 ícones** e **10 padrões de
preenchimento** (hachuras, pontos, tracejados), todos de produção própria sob CC0-1.0, gerados por
composição de traço sobre moldura de categoria (energia, água, saneamento, transporte, ambiente,
imobiliário, campo, setas, formas). Licença de cada arquivo, com sha256, em `docs/LICENCAS_SIMBOLOS.md`,
gerado do manifesto vivo por `scripts/gerar_licencas_simbolos.py` — o arquivo não se edita à mão.

Sprite por inquilino em `/api/simbolos/sprite/{slug}.json|.png`, 1x e 2x, no formato que o MapLibre
consome, composto pela própria API. O Martin não serve o sprite porque lê o diretório uma única vez na
subida do processo (medido com o binário v1.15.0 e `curl`, sem código nosso): um SVG acrescentado ao vivo
não aparece. Decisão e medição em `docs/adr/20260907T1642-sprite-proprio-em-vez-de-martin.md`. Os glifos
de fonte, que não mudam em runtime, continuam vindo do Martin de verdade (`app/simbolos/fontes.py`), sobre
as TTF embutidas Noto Sans (OFL-1.1) e Open Sans (Apache-2.0) registradas em `web/vendor/VERSOES.txt`.

Upload de SVG do inquilino saneado por `app/simbolos/validador.py`: `<script>`, referência externa e XML
perigoso (DOCTYPE/entidade — a bomba de XML da refutação) são recusados com **422** e motivo nomeado;
acima de 64 kB é recusado. O upload entra no sprite sob o prefixo `personalizado/`, então um ícone com o
mesmo nome de um da base não sobrescreve nada — os dois convivem no mesmo sprite (a segunda refutação).
Pedir o sprite de outro inquilino com token próprio dá **403 `inquilino_divergente`** (a terceira).

Medido (`tests/medidas/L2-02-e-simbolos-sprites-glifos.json`, com a carga da máquina ao lado): compor o
atlas dos 163 itens leva **0,097 s** em 1x e **0,145 s** em 2x; do POST do ícone até ele aparecer no
`sprite.json` pelo HTTP, **0,271 s** sem reinício de processo — folga de 18x sobre os 5 s do portão, e
isso com carga 12,38 e 0,4 GiB livres. Galeria em `/simbolos` com busca por nome e filtro por categoria;
o e2e escolhe um ícone e vê o marcador no mapa, e uma captura real do navegador mostra os glifos da Noto
Sans com acento português ("Nação, Água, Ímã, Coração, Codificação").

Achado de fora do item, consertado de passagem: `tests/e2e/apoio.py` nomeava a captura de qualquer item
como `L0-02-tenant-auth_*`, porque usava a constante do próprio módulo em vez do item do teste que a
chamou. `Tela(...)` agora recebe `item=`, com o valor antigo como padrão.

## turno 3, setembro de 2026 (item L2-05-d: grades, densidade, padrões espaciais e interpolação)

Oito ferramentas no mesmo registro e no mesmo executor dos itens L2-05-a/b/c: `tesselacao` (grade quadrada,
hexagonal e H3 de nível 5 a 10, tamanho em metros entre lados opostos, desenhada no UTM local, com recorte
opcional pela área), `densidade_kernel` (pontos e linhas, quártica/gaussiana/triangular/uniforme, raio e
célula declarados), `hot_spot` (Getis-Ord Gi* com vizinhança por distância fixa, z, p e faixa no vocabulário
do Gi_Bin), `centro_medio` (centro médio, círculo da distância padrão e elipse de desvio padrão, com peso
opcional), `vizinho_mais_proximo_medio` (índice R de Clark & Evans), `moran_global` (I de Moran com
significância sob normalidade), `interpolacao_idw` e `contorno` (superfície por IDW ou triangulação de
Delaunay e isolinhas pelo gerador do GDAL).

A estatística vive em `app/ferramentas/estatistica_espacial.py`, em numpy/scipy, sem banco. O teste do item
confere Gi* e I de Moran contra `esda`/`libpysal` na forma binária dos pesos (diferença medida de 8,9e-16 no
z do Gi* e de 3e-16 no I), a área do hexágono contra a fórmula fechada, a integral da densidade contra o
número de pontos (erro relativo de 1,1e-4) e contra o comprimento das linhas, o IDW contra uma implementação
escrita de novo no teste (diferença 0) e as isolinhas relidas pelo OGR do GDAL, que é o leitor do QGIS.

A saída de densidade e de IDW é camada de células enquanto o caminho de ingestão de raster do item L1-01 não
estiver em master; a mesma conta em array já está pronta e testada para virar COG por lá. Ver a decisão 4 do
ADR `docs/adr/20260908T0150-grades-densidade-padroes-e-interpolacao.md` e a tabela de paridade em
`docs/PARIDADE_FERRAMENTAS_GRADE.md`.

Correção de passagem no executor do L2-05-a: camada de saída com uma feição pontual quebrava a publicação
(extensão lida do anel do GeoJSON e retângulo degenerado recusado pelo CHECK `item_extent_check`).

## turno 3, setembro de 2026 (item L2-05-c-sobreposicao-agregacao: relação entre camadas)

Nove ferramentas que relacionam DUAS camadas, no mesmo registro e no mesmo executor dos itens L2-05-a e
L2-05-b: `juncao_espacial` (um-para-um com regra de mesclagem soma/média/mínimo/máximo/contagem/primeiro/
concatenar, ou um-para-muitos; relações intersecta, contém, dentro, a X metros e mais próximo, esta com o
identificador do vizinho e a distância geodésica), `juncao_atributo` (inner e left por igualdade de chave, com
recusa nomeada quando os tipos das chaves não casam; a geometria da camada juntada não entra),
`resumir_dentro` (contagem, estatísticas, medida geodésica da parte contida e separação por campo de grupo),
`contar_dentro`, `resumir_perto` (área de proximidade geodésica em volta da referência), `agregar_pontos` (em
polígonos existentes ou em grade quadrada/hexagonal desenhada em metros no UTM local e trazida de volta ao
SRID da camada), `enriquecer_por_area` (repartição de campo numérico por proporção de área geodésica),
`vizinho_mais_proximo` e `tabela_distancias`.

Três decisões de comportamento, todas escritas no método da procedência do item de saída: o par candidato sai
de `ST_Subdivide` sobre a camada de polígonos com `DISTINCT`, mas a relação e a medida são conferidas contra a
geometria original; a contagem dupla que polígonos sobrepostos provocam é contada e declarada, e
`atribuicao='exclusivo'` a desfaz; feição exatamente na fronteira conta nos dois polígonos vizinhos, como no
ArcGIS e como no `intersects` do geopandas.

25 testes em `tests/api/ferramentas/test_relacao.py` conferem cada ferramenta contra `geopandas.sjoin`,
`pandas.merge`, `shapely` e `pyproj.Geod` na mesma entrada, lida de volta do banco — nenhum número esperado
escrito à mão. Cláusulas do portão medidas: 100 pares do "mais próximo" com a distância geodésica conferida;
a soma distribuída pela proporção de área bate com a soma original (erro relativo 6,7e-8, tolerância 1e-6).
A cláusula de 1 milhão de pontos em 5.570 municípios em até 60 s NÃO foi medida na escala do enunciado (disco
a 93 %, carga acima de 8 e teto de 5 mil feições por teste no brief da corrida): o que ficou medido foi 4.001
pontos em 400 polígonos, com a carga ao lado, em `tests/medidas/L2-05-c-sobreposicao-agregacao.json`.
Paridade com "Summarize data" do Map Viewer em `docs/PARIDADE_FERRAMENTAS_RELACAO.md`; ADR
20260907T2210.

## turno 3, setembro de 2026 (item L2-05-b-vetor-basico: 19 ferramentas vetoriais elementares em SQL/PostGIS)

As operações que faltavam ao registro de ferramentas do item L2-05-a, todas como expressão SQL executada pelo
mesmo executor (em processo abaixo do custo declarado, senão como job) e publicadas como item de camada com
proveniência: `buffer` (agora geodésico com 48 segmentos por quarto de círculo, com distância por campo, anel
por distância interna, método plano opcional e dissolver), `recorte`, `intersecao`, `uniao`, `diferenca`,
`diferenca_simetrica`, `dissolver` (por campos, com soma/média/mínimo/máximo/desvio/contagem), `mesclar`
(N camadas), `explodir`, `centroide` (centro de massa ou ponto interior), `casco` (convexo ou côncavo),
`simplificar`, `suavizar`, `reprojetar`, `calcular_geometria` (área, perímetro, comprimento geodésicos e x/y),
`pontos_aleatorios` (com semente), `linhas_para_pontos` (vértices ou intervalo geodésico),
`poligonos_para_linhas` e `densificar`.

Regra da casa dentro da expressão: toda operação booleana em massa recebe `ST_ReducePrecision(ST_MakeValid(g))`
e a contagem de geometrias inválidas da entrada vai para o log e para o método gravado na procedência da
camada de saída. Teto novo: `VETOR_FEICOES_MAX` = 2 milhões de feições por entrada, declarado no manifesto e
conferido antes de operar; o teto de 30 min por execução já era o do job.

Conferência: 29 testes novos comparam cada ferramenta com shapely (geometria plana) ou `pyproj.Geod` (medida
geodésica) na MESMA entrada, com tolerância de área 1e-6 relativa e contagem exata; o buffer geodésico de 1 km
em latitude −23 fica a 5,0e-5 do círculo de referência calculado com `pyproj.Geod` (o portão aceita 5e-4).
Medidas em `tests/medidas/L2-05-b-vetor-basico.json`. Paridade com "Manage data" e "Use proximity" do Map
Viewer escrita em `docs/PARIDADE_FERRAMENTAS_VETOR.md`. Decisões em
`docs/adr/20260907T2119-ferramentas-vetoriais-elementares.md`.

O executor passou a aceitar parâmetro de LISTA de camadas (`GPMultiValue:GPFeatureRecordSetLayer`, usado pelo
`mesclar`) e a achatar essa lista ao escrever proveniência e `derivado_de`: a camada mesclada aponta para
todas as origens.
## turno 4, setembro de 2026 (item L2-01-mapa-web: visualizador de mapa próprio, do Martin à impressão)

Visualizador MapLibre da plataforma, com a pilha de tiles vetoriais que faltava chegar a `master`.

- **Servidor de tiles**: Martin 1.15.0 (musl, sha256 do pacote fixado em `deploy/martin_instalar.sh`) como
  unidade `plat-martin` em `127.0.0.1:8151`, publicando SÓ funções (`auto_publish.tables: false`) — a
  tabela crua da camada nunca é exposta. Papel de leitura `plat_leitor` (LOGIN, sem BYPASSRLS, sem ser
  dono), `plat.contexto_por_token` e a função de tile por camada com RLS vieram do trabalho dos itens
  L2-01-b/L2-04-a, que nunca tinha sido juntado.
- **API do mapa** (`app/mapa/`): `GET /api/mapa/camadas` com estilo MapLibre e legenda geradas da
  simbologia; `GET /api/mapa/camadas/{id}/tilejson` cunhando token de 12 h com escopo de UMA camada;
  repasse `GET /tiles/{esquema}/{funcao}/{z}/{x}/{y}` com a mesma autorização do `auth_request` do nginx
  (uma implementação, duas portas); `plat.camada_extensao` para o "enquadrar".
- **Tela `/mapa`**: lista de camadas com ordem (arrastar e por botão), opacidade, ligar/desligar e
  enquadrar; legenda; janela de atributos (campo nulo aparece marcado, multi-geometria não se repete);
  medição geodésica de distância e área; pesquisa de endereço (CNEFE) e de coordenada em decimal e em
  grau-minuto-segundo; escala, coordenadas e escala numérica 1:N; troca de mapa-base; impressão em PNG e
  em PDF com escala, barra de escala e seta de norte.
- **`GET /api/geocodificar`**: geocodificar é leitura e agora tem o verbo certo (o POST continua).
- Medido com 1.000.000 de feições: 2,4 s do clique ao primeiro desenho, 1,5 s de zoom até `idle`, 61 MB
  de heap; 10 camadas ao mesmo tempo em 4,3 s, pan em 302 ms, 24,8 MB. Tile z8 pelo repasse: 406 ms
  frio, 21 ms quente. Detalhe em `tests/medidas/L2-01-mapa-web.json`.
- Dois defeitos reais achados pelos testes e corrigidos: `attribution: undefined` fazia o MapLibre
  recusar a fonte inteira em silêncio; repassar `Content-Encoding: gzip` com corpo já descompactado
  entregava tile ilegível ao navegador. Registrados no ADR 20260907T0400.
## turno 4, setembro de 2026 (item L2-04-servicos-esri-ogc: diretório do FeatureServer, OGC API Features e WFS 2.0)

Construído em volta da operação `query` do FeatureServer (item L2-04-c, `wt/fsquery`, ADR 0018) sem reescrevê-la:
`app/consulta/rotas_servico.py` (descritor de serviço `.../FeatureServer?f=json` e de camada `.../FeatureServer/0
?f=json` — `fields`, `geometryType`, `objectIdField`, `fullExtent`), `app/consulta/rotas_ogc_features.py` (OGC API
Features Part 1: landing, conformance, collections, items com bbox/limit/offset, item único, GeoJSON puro) e
`app/consulta/rotas_wfs.py` (WFS 2.0 KVP: GetCapabilities validado pelo cliente real `owslib.wfs.WebFeatureService`,
DescribeFeatureType mínimo, GetFeature em GeoJSON e GML 3.2 simples). `applyEdits`/anexos/`queryRelatedRecords`/
`relationships` ficam de fora — dependem de L2-03-edicao e L2-10-b, nenhum construído (ADR 0019).

Bateria de 13 ataques (item_id com aspas/comentário SQL/`;`, bbox com sub-select/`pg_sleep()`/função não prevista,
BBOX do WFS com injeção, `REQUEST` desconhecida, `feature_id` não inteiro, unicode no item_id, cross-tenant nas 3
raízes): **13/13 recusados com 400/404, nenhum 500**. Dois achados corrigidos no mesmo turno: (1) `item_id::uuid`
sem validar antes deixava o Postgres levantar exceção sem handler → 500 real, inclusive na `/query` original do
L2-04-c — corrigido com validação de UUID compartilhada; (2) landing/conformance do OGC API Features respondiam 200
para item de outro inquilino (sem vazar dado, mas sem checar posse) — corrigido tocando `plat.item` sob RLS antes de
responder. `docs/PARIDADE.md` e `tests/medidas/L2-04-servicos-esri-ogc.json` têm a tabela cláusula a cláusula.

Fora do turno: QGIS/ArcGIS Pro/AGOL reais carregando o serviço (sem ambiente gráfico nesta máquina, mesma limitação
já registrada para L2-04-c e para Chrome headless); OGC API Features Part 3 (CQL2), WFS-T; GML validado contra o
XSD de referência do OGC.

## turno 3, setembro de 2026 (item L2-04-b-featureserver-catalogo-metadados: diretório de serviços Esri por token)

- Diretório de serviços compatível com Esri em `/svc/{token}/rest/...`: `rest/info`, `rest/generateToken`,
  `rest/services` (pastas do catálogo), `rest/services/{pasta}`, `FeatureServer`, `FeatureServer/{id}`,
  `FeatureServer/layers`, `FeatureServer/info/itemInfo` e `FeatureServer/info/metadata` (ISO 19139).
  O token vai no caminho porque é uma URL que se entrega e o cliente navega sozinho a partir dela;
  a consequência está declarada no ADR `20260907T1955-diretorio-servicos-esri-por-token.md`.
- O FeatureServer não foi reescrito: `app/consulta/rotas_servico.py` passou a expor
  `descritor_do_servico`/`descritor_da_camada` e o diretório as chama. O descritor da camada ganhou
  `indexes` (lidos de `pg_index`), `editFieldsInfo`, `types`/`subtypes`/`typeIdField`, `timeInfo`,
  `ownershipBasedAccessControlForFeatures` e `domain` por campo. `currentVersion` foi de 11.3 para 11.4.
- `app/consulta/formato_esri.py`: `f=json|pjson|html` e `callback` (JSONP) num lugar só. `f` desconhecido
  é 400 e nunca 500; nome de callback fora de identificador simples é recusado, nunca ecoado.
- `app/consulta/renderizador.py`: estilo MapLibre → `drawingInfo`. Cor constante vira `simple`,
  `["match", …]` vira `uniqueValue`, `["step", …]` vira `classBreaks`, `layout.text-field` vira
  `labelingInfo`. Expressão fora desses casos não é aproximada: sai `simple` cinza com o motivo.
- `app/consulta/cors_servicos.py`: CORS aberto em `/svc`, `/ogc` e `/tiles` — e só. Em `/api` a
  credencial é o cookie de sessão, e abrir ali seria falsificação de requisição entre sítios legível.
- O `drawingInfo` lê a relação `estilo_de_camada` (item de tipo `estilo` → camada), declarada pelo
  `PUT /api/itens/{estilo}/relacoes` que já existia; nada foi acrescentado ao catálogo por causa disto.
- Fica declarado como ausente, não simulado: `fields[].domain` nulo, `types`/`subtypes`/`relationships`
  vazios e `capabilities` só `Query` — as linhas L2-10-a, L2-10-b e L2-03-a não estão nesta base.
## turno 4, setembro de 2026 (item L2-15-a-geoparquet-bucket-catalogo: GeoParquet como formato de trabalho)

`POST /api/geoparquet` enfileira `geoparquet.gerar`: escreve GeoParquet 1.1 (metadado `geo` selado — o
DuckDB 1.5.5 desta máquina só escreve 1.0.0, medido; troca binária de mesmo tamanho, sem tocar rodapé),
particionado em hive (`particionar_por: {coluna, grao}`, `grao: valor` ou `ano_mes`) ou arquivo único, no
bucket do inquilino (`<slug>/geoparquet/<uuid do item>/<sha256>.parquet`, reuso de `app/objetos.py` do
L0-11), e publica/atualiza UM item de catálogo `tipo=parquet` (esquema, contagem, bbox por arquivo, sha256,
proveniência com `versao` incremental). Atualização incremental: cada partição é comparada por sha256 com a
rodada anterior — como o adaptador de objetos já deduplica por conteúdo, partição sem mudança nunca gera PUT
novo no Garage. Modo `arquivar` apaga a tabela de origem DEPOIS de conferir, na mesma transação, que a
contagem do Parquet bate com o `DELETE ... rowcount` (sem bater, nada é apagado — `app/db.py` reverte).
Reusa de propósito o motor do L0-04-h-exportar (conninfo com RLS embutida, guarda de disco, GPKG
intermediário) e o `_conexao`/`_literal` do `parquet_cli` (DuckDB não sobrevive a `fork`, roda em processo
próprio). Leitura por URL assinada reusa `/api/objetos/{chave}` (nenhuma rota de entrega nova); contrato de
assinatura vencida é 404 (mesmo de todo o resto da plataforma), não o 403 do texto do portão. Nenhum
privilégio novo: `conteudo.exportar` para gerar, `conteudo.apagar_tudo` (administrativo) OBRIGATÓRIO ADEMAIS
para `arquivar`. Ver ADR 20260907T1752.

Medido (`tests/medidas/L2-15-a-geoparquet-bucket-catalogo.json`): camada de **1.000.000 de polígonos**
exportada em **5,8 s** (carga da máquina 10,75 no início — load average alto não invalidou o resultado);
reaberta pelo DuckDB com COUNT(*) igual e diferença de ST_Area de **0,0** em 100 amostras contra o PostGIS
(tolerância pedida 1e-6). Partição por UF gera exatamente 27 arquivos (`tests/unit/test_geoparquet_unidade.py`
e `tests/api/geoparquet/test_geoparquet.py`). Refutação: geometria mista + SRID 31982, tabela sem geometria e
campo de 9 MB de texto (10 MB esbarra num teto do próprio driver CSV do GDAL, medido) não quebram o
conversor; coluna não declarada no item do catálogo nunca aparece no arquivo gerado (o SELECT nunca usa `*`).
NÃO MEDIDO: QGIS em docker abrindo o Parquet por URL (sem imagem local; disco a 95% impede baixar uma).
Achado que ficou fora do escopo deste item, registrado no ADR: `app/jobs/worker.py::_pegar()` pode prender o
advisory lock `plat.job.pesado` indefinidamente num worker ocioso, travando todo job pesado da frota.

## turno 4, setembro de 2026 (item L0-04-h-exportar: exportação de camada para outros formatos)

`POST /api/exportacoes` enfileira o job `exportacao.gerar` (202) e devolve o arquivo (item `arquivo`,
validade de 7 dias) em 11 formatos: gpkg, geojson, shapefile(zip), csv, xlsx, kml, kmz, fgb, gml, dxf e
geoparquet (este pelo DuckDB, num processo próprio — o `ogr2ogr` desta instalação não tem driver Parquet, e
o DuckDB não sobrevive a um `fork`, então a conversão roda como `python -m app.exportacao.parquet_cli`,
neto do job). Filtro (`where`), campos e CRS de saída são conferidos ANTES de existir job (400 com o erro do
banco saneado, `app/exportacao/erros.py`). Isolamento entre inquilinos: o `ogr2ogr` abre conexão PRÓPRIA,
fora do pool da aplicação — o inquilino entra na string de conexão (`-c plat.tenant_id=N`), e é a RLS do
PostgreSQL que corta, provada com pedido forjado no banco e com o `ogr2ogr` chamado sem contexto nenhum
(`tests/api/exportacao/test_exportacao_cruzado.py`). Arquivo grande nunca vai inteiro à memória: envio ao
Garage em blocos/multipart (`objetos.guardar_arquivo`, novo) e download em blocos de 1 MiB
(`objetos.ler_stream`, novo) — medido com `tracemalloc` (pico < 3 partes de 8 MiB para um arquivo de 40 MiB).
Privilégio novo `conteudo.exportar` (editor/admin); opção do dono do item "permitir que outros exportem"
(`dados.exportacao.permitir_outros`, nasce desligada). Limite de 3 exportações em curso por usuário e guarda
de disco (`shutil.disk_usage`) antes do primeiro byte. Botão **Exportar** na tela do item
(`web/js/catalogo/item_exportar.js`). Achado à parte, sem relação direta com exportação: `CursorSchemaAmbiente`
não reescrevia `executemany`/`mogrify` (só `execute`/`callproc`), o que fazia qualquer rota que use essas duas
chamadas escrever no schema `plat` de PRODUÇÃO mesmo dentro de uma base de trilha isolada — consertado em
`app/schema_ambiente.py`. Ver ADR 0018 e `docs/PARIDADE.md` seção "Exportação de camada para outros formatos".

Medido (`tests/medidas/L0-04-h-exportar.json`, camada de 100 mil feições): tempo por formato de 0,80 s
(FlatGeobuf) a 14,54 s (XLSX); todos os 11 formatos reabertos com a mesma contagem de 100.000 feições
(`ogrinfo`/DuckDB conforme o formato).
## turno 3, setembro de 2026 (item L3-01-j-equivalencia-motor-logistico: equivalência com o motor de referência)

O motor multicritério genérico reproduz o motor logístico de referência da casa. Os 19 fatores disponíveis
dele estão reescritos no vocabulário do modelo em `docs/modelos/motor_logistico_referencia.json` (esquema
`amc_modelo.v1`, oito com a transformação do valor bruto e onze com a identidade sobre um valor que já
chega em escala de favorabilidade, cada um dizendo isso em `nao_sustenta`), e `app/amc/agregacao.py` passa
a fazer a conta de célula para feição: média ponderada pela área de interseção sobre as células não
vetadas, fração vetada por área e motivo da maior área vetada.

Medido em 07/09/2026 contra o motor de referência lido só para leitura, em três perfis de peso
(declarado, todos iguais e sorteado): **100 % das 73.115 células e 100 % das 4.346 feições** dentro de
0,5 ponto, com diferença máxima de 0,0 contra o mesmo cálculo refeito em `numeric` no Postgres; veto e
motivo idênticos nas 73.115 células (51.598 vetadas); fração vetada idêntica nas 4.346 feições. A
agregação reproduz **os dez fatores que o motor de referência tira da grade**, em 100 % das feições cada;
os outros nove ele calcula direto na feição (sete numa tabela por imóvel, `varzea` pela fração de
inundação do imóvel, `mine` pelo veredito do imóvel) — a nota deles bate com essa fonte em 4.346 de 4.346,
que é a evidência de que não foi agregação que os produziu. Tempo: 0,05 a 0,09 s para combinar as 73.115
células e 0,03 s para agregar os 61.238 pares feição-célula, com carga de 5,4 a 6,2 na máquina.

O nome do schema do motor de referência não está escrito no repositório: vem de
`PLAT_MOTOR_REFERENCIA_ESQUEMA` e, sem ela, os testes de equivalência são pulados dizendo a razão.

De quebra, dois defeitos herdados que travavam os portões do repositório: `app/jobs/tipos.py` com bloco de
importação fora de ordem e uma palavra num ADR que contém, dentro dela, um dos marcadores proibidos e por isso reprovava em
`make sem-marcador`.

## turno 3, setembro de 2026 (item L3-15-metadado-fator: metadado do fator e teto de peso do proxy)

`app/amc/metadado.py` reúne o que cada fator do motor multicritério carrega além da conta: `fonte` e
`versao_fonte`, `unidade`, `direcao`, `base` (norma / engenharia / preferência), marca de `proxy` com teto de
peso, `classe_peso` (custo medido em R$ / apetite de risco / consequência normativa), `ancora_peso` (medida /
escolhida) e `nao_sustenta`. Os cinco últimos vêm do motor de linha de transmissão da casa
(`rs-coop/tracado-lt/motor/pesos.py`), onde a camada de vegetação nativa mede presença declarada e não
supressão de árvore, e por isso o peso dela para em `TETO_PROXY = 0,60`.

Teto de proxy agora é regra, não texto: a fatia do peso de um fator declarado proxy (`peso_i / Σ pesos`, a
mesma fatia que a soma ponderada normalizada usa, invariante a multiplicar todos os pesos pelo mesmo número)
não pode passar do `teto_peso` declarado. A recusa sai 422 nos DOIS lugares onde um peso entra — no documento
do modelo (`modelo_invalido`) e nos pesos de uma execução, que podem sobrescrever os do modelo
(`pesos_invalidos`) — e explica: nomeia o fator, a fatia medida, o teto, o que a camada mede e qual peso
caberia com os demais mantidos.

`app.amc.relatorio.montar_relatorio(..., definicao=...)` ganha o bloco `metadado` com a ficha de cada fator, a
lista dos proxies (descrição, teto, fatia) e a lista das âncoras (medida / escolhida / **não declarada**, que
é uma terceira coisa e não vira "escolhida"); a explicação por unidade carrega o mesmo bloco, e a tela
`/amc/explicacao/...` mostra a ficha no `?` de cada fator (elemento `details` nativo, sem biblioteca) e o
cartão "proxies e âncoras". No esquema, `versao_fonte` entra como campo OPCIONAL — quem não a declara fica
nomeado em `fatores_sem_versao_de_fonte`, o que é melhor que forçar o usuário a escrever qualquer coisa no
campo. `fonte` e `base` seguem obrigatórios, com `fonte` de comprimento mínimo 1.

Refutação (`tests/api/amc/test_metadado_api.py`): o adversário tentou salvar fator sem fonte, fator sem base,
proxy com peso 1000 contra 0,001 dos demais, o mesmo ataque pelos pesos da execução, `teto_peso = 0` para
esvaziar a regra, proxy sem descrição e a multiplicação de todos os pesos por 1000 — as sete recusadas ou sem
efeito, e nada gravado. Decisão e alternativas descartadas em
`docs/adr/20260907T1919-metadado-do-fator.md`.

## turno 3, setembro de 2026 (item L3-01-d-transformacoes: biblioteca de transformações do motor multicritério)

`app/amc/transformacoes.py` (numpy, puro) implementa os 16 tipos de transformação valor bruto → favorabilidade
0-100 do esquema (`categoria`, `faixas` com quebra manual/quantil/intervalo igual/quebras naturais, `linear`,
`degraus`, e as 12 funções contínuas do Rescale by Function do ArcGIS Pro 3.4 — fórmula DECLARADA, a Esri não
publica a fechada, ver ADR); `db/migracoes/20260907T1602_amc_transformacoes.sql` implementa as mesmas em
PL/pgSQL (`plat.amc_transformar_num`/`_cat`) para materializar sem trazer a coluna ao Python. Equivalência
SQL×numpy provada a ≤ 0,01 (`tests/unit/test_amc_transformacoes.py`, 20 casos + amostra aleatória de 200
valores); refutação do adversário (gaussiana/logística/MSLarge reimplementadas do zero a partir da página
pública da Esri, mais mínimo=máximo/spread 0/negativo/NaN) em
`tests/unit/test_amc_transformacoes_adversario.py`. Pré-visualização com histograma de entrada/saída em
~20-35 ms para 100 mil valores (limite do portão: 300 ms; `tests/unit/test_amc_transformacoes_desempenho.py`).
Reprodução do motor logístico real (CBRE, só leitura): 4 dos 19 fatores batem a ≤ 0,5 em 100 % das células
(`decl`, `rod`, `agua`, `press`); os outros 15 ficam fora de escopo (combinam várias colunas/veto/bônus, ou —
`gru`/`se` — têm coluna candidata que diverge de verdade, 3,90 % e 80,1 % das células), cada um com o motivo
nomeado em `tests/medidas/L3-01-d-transformacoes.json` — cláusula registrada como PARCIAL, não fingida como
passada. `app/amc/executor.py` (item L6-04) agora usa esta biblioteca inteira em vez de só `linear`. 16
gráficos gerados por `scripts/amc_transformacoes_graficos.py` em `docs/graficos/amc_transformacoes/`. ADR
`docs/adr/20260907T1602-transformacoes-amc.md`.
## turno 3, setembro de 2026 (item L3-02-b-sensibilidade-sobol-oat: sensibilidade global e local do motor multicritério)

`app/amc/sensibilidade.py` responde duas perguntas diferentes sobre o mesmo modelo. A global são os
índices de Sobol de primeira ordem e total sobre os pesos e os parâmetros de transformação, por amostra
de Saltelli na sequência de Sobol do `scipy.stats.qmc` (estimador de Saltelli 2010 para a primeira
ordem, de Jansen 1999 para o total), com N declarado, semente gravada e intervalo por reamostragem das
linhas da amostra. A local é o tornado um fator por vez: move o peso de cada fator de −50 % a +100 % com
os outros parados e mede quanto a lista dos k melhores muda. Sai um relatório por modelo, serializável,
com as duas leituras, o que manda no resultado e o que é irrelevante (índice total abaixo de 0,01).
Roda como job `amc.sensibilidade`, pela mesma razão do sorteio do item L3-02-a: o custo é N·(g+2)
recombinações. Sem rota nova, sem migração, sem dependência nova.

Medido (`tests/medidas/L3-02-b-sensibilidade-sobol-oat.json`): a função de teste de Ishigami, cujos
índices têm forma fechada, é reproduzida com desvio máximo de **0,0004** contra a referência (N=16.384,
81.920 avaliações em 0,009 s) — a tolerância do portão era 0,05. O relatório completo de um modelo de
2.000 unidades × 6 fatores (N=512, 4.096 recombinações, tornado de 9 passos por fator, 100
reamostragens) levou **1,295 s** com carga de 1 min 9,53 e 3,65 GB livres: passou com folga mesmo sob
disputa de máquina. A refutação do fator duplicado passou nos dois alvos e deixou dois achados escritos
como teste: somar o índice TOTAL das duas cópias conta a interação entre elas duas vezes (a conta certa
é o índice do grupo), e repartir o peso em duas metades sem alargar a faixa por √2 derruba o índice por
perda de variância, não por mudança do modelo.

Regra de linguagem mantida do item irmão: mede-se a dependência do modelo ao peso escolhido pelo
usuário, nunca a importância real do fator no território — a frase anda junto de todo número, e um
teste de adversário reprova a saída que a perder.

## turno 3, setembro de 2026 (item L3-04-restricoes: restrição como objeto próprio do motor multicritério)

`app/amc/restricao.py`: avalia UMA restrição declarada no modelo (`avaliar(cur, unidades, feicoes,
restricao)`) e compõe várias por OU (`compor`). Regra `intersecta` usa `ST_Intersects` puro sem buffer
e `ST_DWithin(geography, geography, buffer_m)` com buffer — nunca projeção plana escolhida por acaso;
regra `fracao_area_minima` usa `ST_Area(geography)`, o mesmo padrão de área geodésica já documentado em
`app.amc.crs`. Composição por OU é sempre binária (fração vetada 0,0 ou 1,0 — restrição veta, não pesa);
o motivo gravado é o da primeira restrição, na ordem do modelo, que vetou a unidade; `frase_motivo` lê só
o metadado `base` ("a norma veda: ..." para `norma`, "vetamos por precaução: ..." para `precaucao").
Camada sem nenhuma feição na área nunca veta em silêncio: levanta `ErroRestricao('camada_vazia', ...)`.
`app.amc.robustez` e `app.amc.combinacao` não mudaram: já tratavam `fracao_vetada` como fixa (A6). Medido
(`tests/medidas/L3-04-restricoes.json`): 12 testes, 3 restrições encadeadas com contagem por restrição
batendo com `ST_Intersects`/`ST_DWithin` recomputados à mão fora do módulo. Regra `valor_raster` fica
fora do escopo, declarada com erro explícito. ADR
`docs/adr/20260907T1617-restricao-como-objeto-proprio.md`.
## turno 3, setembro de 2026 (item L3-07-agregacao: agregação de grade para feição)

`app/amc/agregacao.py`: leva o resultado do motor por CÉLULA a uma FEIÇÃO qualquer (imóvel, lote,
município, setor) por interseção geométrica com `ST_Area`/`ST_Intersection` no CRS de trabalho — média
por fator ponderada pela área sobre células não vetadas, fração vetada (sobre todas as células
tocadas), veto principal (motivo da maior área vetada, desempate determinístico por `cell_id`),
recombinação opcional por pesos do modelo (`app.amc.combinacao.combinar`, item L3-01-e) e favorabilidade
final = combinação × (1 - fração vetada); limiar de fração vetada ("sai do ranking") é parâmetro de quem
chama. Caminho inverso (feição -> células) em `celulas_de_uma_feicao`. Feição sem nenhuma célula sai
`sem_celula = true`, nunca 0. Portão: reproduz `cbre.imoveis_fav` (piloto real, só leitura) para as
4.346 feições contra `cbre.hex_fav`/`cbre.hex` — 10 fatores comparáveis + `n_cel` + `pct_vetado` em
100% de reprodução (|Δ| ≤ 0,5), `veto_principal` em 99,65% (limiar do portão: 99,5%); tempo medido
4,5-22 s conforme carga da máquina (`tests/medidas/L3-07-agregacao.json`). Sete fatores do cbre
(`f_roubo`/`f_trib`/`f_renda`/`f_rlapp`/`f_polos`/`f_se`/`f_cluster`/`f_varzea`) ficam fora da
comparação por serem sobrescritos por gancho direto por imóvel no pipeline do cbre, não geometria de
grade (ver ADR). Refutação exigida: `tests/unit/test_amc_agregacao_adversario.py` recalcula 50 imóveis
com `ST_Intersection` escrito do zero no psql (nunca chama `agregacao.py` para o valor esperado) e
compara — achou e corrigiu o desempate de `veto_principal` (decisão 4 do ADR). Integração com a
execução real do motor entra com um fator sintético (`favorabilidade` já combinada por célula) — limite
documentado, ver decisão 3 do ADR `docs/adr/20260907T1650-agregacao-grade-feicao.md`.

## turno 3, setembro de 2026 (item L3-02-a-monte-carlo-pesos: robustez do motor multicritério por sorteio de pesos)

`app/amc/robustez.py` (puro, sem I/O): `sortear_pesos` (Dirichlet no simplex ou faixa +-k% por fator,
declarada) e `simular_robustez`, que chama o combinador do L3-01-e (`app.amc.combinacao.combinar`) N
vezes e agrega por unidade (minimo, media, maximo, desvio, frequencia no top-k e no decil superior,
estavel = top-k em >=95% dos sorteios). Sorteio de peso em ordem canonica pelos IDs dos fatores (nunca
pela posicao de entrada), remapeada de volta na saida: permutar a ordem de entrada e reexecutar com a
mesma semente da o mesmo resultado (nota com tolerancia 1e-9 por soma de ponto flutuante nao ser
perfeitamente associativa; ranking exato). Veto e restricao nunca sao sorteados: `fracao_vetada` fixo
em todos os N sorteios, unidade vetada marcada com nota `-inf` antes de ordenar (exclusao do topo por
construcao, testada com unidade que teria a nota maxima sem o veto). Job `amc.robustez_pesos`
(`app/amc/tarefas.py`, pesado=True, timeout_s=120) registrado em `app/jobs/tipos.py`; resultado
(agregados + semente, nunca a matriz N x unidades, conforme A9) em `job.resultado` (jsonb existente,
sem migracao nova). Medido (`tests/medidas/L3-02-a-monte-carlo-pesos.json`): 1.000 sorteios em 5.000
unidades x 8 fatores como job, 0,767 s (78x dentro do limite de 60 s). ADR
`docs/adr/20260907T1245-robustez-sorteio-de-pesos.md`.
## turno 3, setembro de 2026 (item L3-01-f-explicacao: explicação da nota do motor multicritério)

`GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao` responde "por que esta unidade tem nota
N": tabela fator → valor bruto (com unidade e fonte) → transformação → favorabilidade → peso → contribuição,
mais soma, veto/motivo e cobertura (`app/amc/explicacao.py`). Recalculado a partir de `plat.amc_fator_bruto` na
hora, nunca lido de uma tabela de explicação gravada — o mesmo combinador de `app/amc/combinacao.py` (item
L3-01-e). Sobre 100 unidades sorteadas, |soma das contribuições − favorabilidade gravada| ≤ 0,5 (medido:
`tests/medidas/L3-01-f-explicacao.json`). Painel em `/amc/explicacao/<execucao_id>/<unidade_id>`
(`web/amc_explicacao.html` + `web/js/amc/explicacao_pagina.js`). Combinador fuzzy (mínimo/máximo/produto/soma
fuzzy/gama) não decompõe em contribuições por fator por definição matemática — a tabela mostra a favorabilidade
de cada fator sem fingir uma soma que não existe. Transformação contínua (Rescale by Function, item
L3-01-d-transformacoes, pendente) aparece com valor bruto e observação, nunca com número fabricado. ADR
`docs/adr/20260907T1245-explicacao-amc.md`.
## turno 3, setembro de 2026 (item L6-04-acervo-no-motor: camada do acervo como fator no motor multicritério)

Fecha o ciclo entre o motor AMC (L3-01-a/b/c) e a publicação sem cópia do acervo (L6-01-b): `app/amc/executor.py`
(job `amc.executar`, enfileirado sozinho por `POST /api/amc/execucoes` quando o modelo tem fator `camada.tipo =
'acervo'`) lê cada fator direto da view `plat_acervo.<view>` — nunca copia a tabela de origem — com
`app.amc.vetorial` fazendo a extração e uma transformação `linear` levando o valor bruto a favorabilidade 0-100.
Provado com 3 camadas REAIS já ingeridas na casa (`icmbio_unidades_conservacao`, `funai_terras_indigenas`,
`hidro_nacional_bc250`, 1,6 mi de linhas), não dado sintético. `app/amc/camadas.py::_acervo` passou a exigir
`plat.acervo_pode_ler` (mesmo porteiro da API de mapa) na CRIAÇÃO da execução — sem assinatura, 422
`sem_assinatura`, execução nem nasce; o job confere a assinatura DE NOVO, uma vez antes de cada fator e uma vez
depois do último, então revogar a assinatura NO MEIO do job (a refutação do item) derruba a execução com
`FalhaDefinitiva` e mensagem, sem gravar nenhuma linha de `amc_fator_bruto`/`amc_resultado` — os dois só são
escritos juntos, no bloco final, depois de todas as confirmações. Resultado de uma execução já concluída nunca é
apagado por uma revogação posterior (gatilho `amc_resultado_guarda`, sem mudança). Proveniência
(`amc_execucao.camadas`) ganhou o campo `fonte_id` explícito, ao lado de `sha256`/`contagem`/`contagem_origem`
que `mod_camadas._acervo` já gravava. Limite honesto: só fatores `camada.tipo == 'acervo'` são extraídos por este
job (fator do tipo `item` fica de fora, é ignorado na combinação); só transformação `linear`; camada lida só
dentro da caixa envolvente das unidades + folga, não da tabela inteira (necessário para não varrer camadas
nacionais de milhões de linhas a cada execução) — a combinação completa do motor (categorias, faixas, degraus,
funções contínuas, combinadores alternativos) é o item L3-01-d/e, ainda não construído.

Achado de merge: juntar os três worktrees de que este item depende (`wt/amc`, `wt/extrat`, `wt/t601b`, nenhum
ainda integrado a `master`) produziu um `SyntaxError` real em `tests/api/cruzado_casos.py` — o merge automático
(`git ort`) costurou dois `return Preparacao(...)` de branches diferentes de um jeito que partiu uma função no
meio por uma `def` e derrubou um `),` de fechamento do dicionário `CASOS`. Sem o conserto (feito neste ramo),
`make lint` e toda a suíte de API (que importa `tests/api/conftest.py`, que importa `cruzado_casos.py`) falhavam
na coleta. `docs/openapi.json` continua sem nenhuma das 18 rotas `/api/amc` — débito pré-existente do próprio
L3-01-a/b, não deste item; os dois testes que dependem dele (`test_amc_adversario_api.py` × 2,
`test_cruzado.py::test_cobertura_100_por_cento`) seguem vermelhos, sem regressão nova. `docs/adr/0017` do
L3-01-c também dispara `make sem-marcador` (falso positivo de uma palavra comum em português que contém a
sequência proibida por acaso) — não é código deste item, não corrigido aqui.
## turno 3, setembro de 2026 (item L3-16-desempenho-escala: limites de escala do motor multicritério, medidos)

Contrato de escala do motor num lugar só (`app/amc/escala.py`, ADR
`docs/adr/20260907T1915-escala-do-motor-amc.md`): a combinação roda no navegador até 50.000 unidades e no
servidor acima disso, em blocos de 50.000 lidos por faixa de `unidade_id`; o plano é recusado ANTES de
enfileirar quando não cabe (unidades demais, fatores demais, bloco maior que o orçamento de RAM, prazo
projetado maior que o do job). `web/js/amc/combinacao.js` passa a recusar acima do limite com
`unidades_demais_para_o_navegador` — o mesmo número que `app/limites.py`, comparado por teste. Job pesado
novo `amc.recombinar` (1 por vez na máquina, provado com dois processos de worker e duas execuções).

Medidas de `tests/medidas/L3-16-desempenho-escala.json`, cada uma com `carga_1min`, `ram_livre_gb` e
`medido_em` ao lado (carga entre 2,84 e 3,10 em 12 núcleos): recombinação no servidor de 10 mil × 15 em
**0,0011 s**, 100 mil em **0,0808 s** e 1 milhão em **0,9734 s** (prazo do portão: 5 s); pico de memória de
um processo que recombina 1 milhão em 20 blocos: **70,26 MB** (orçamento do job: 1024 MB nesta máquina);
combinação de 50.000 × 15 no navegador (o maior tamanho que ele aceita): **21,18 ms**.

Cláusula REFUTADA e registrada como tal: à taxa medida da estatística zonal (**698,93 µs** por unidade e
por fator), 1 milhão de células × 15 fatores levaria **10.483,9 s** — quase 3 horas contra os 1.800 s do
portão. O motor recusa esse plano com `prazo_projetado_estourado`; o limite honesto de hoje é uma grade de
**166.898 unidades** com 15 fatores. Move esse número o item `L3-01-c2-extracao-em-lote`.
## turno 4, setembro de 2026 (item L4-03-d-areas-sujas-e-validacao: área suja, validação incremental e feição de erro)

Continuação de L4-03-a: toda feição tocada num `applyEdits` (adicionada, atualizada ou apagada) grava uma
**área suja** (`plat.rede_area_suja`, polígono envolvente com buffer de 2 m, carimbada com
`plat.rede.versao_edicao`) — "editar 1 trecho cria 1 área suja visível no mapa" (`GET .../areas_sujas`,
`FeatureCollection`). `POST .../validar_extensao` valida só a UNIÃO das áreas sujas ativas que tocam a
extensão pedida (ou todas, com `extensao: null` — "validar tudo"): a topologia é reconstruída só dentro
do escopo, nunca da rede inteira, e as áreas processadas viram limpas (soft-delete, `limpa_em`). **15
códigos de erro** (2 já existiam em tempo de escrita — `sem_regra`/`terminal_errado`, L4-03-a — mais 13
novos: `regra_inexistente`, `terminal_invalido`, `terminal_obrigatorio_ausente`, `feicao_sem_conexao`,
`sobreposicao_dispositivo`, `ciclo_tier_hierarquico`, `subrede_sem_controlador`,
`atributo_obrigatorio_nulo`, `geometria_invalida`, `associacao_ciclo`, `feicao_duplicada_geometria`,
`tipo_sem_regra_no_pacote`, `atributo_tipo_invalido`) gravados como **feição de erro** em
`plat.rede_erro` (`GET .../erros`, camada). `GET .../tracar` (feição existente ou geometria solta) avisa
(200) ou recusa (409) quando cruza uma área suja ativa, conforme `PUT .../area_sujas/modo`
(`avisar`/`bloquear`, `rede.administrar`) — os dois casos citam o polígono.

**Bug achado e corrigido** (migração `20260907T1308_rede_conserta_fk_regra_set_null.sql`): a FK composta
`(tenant_id, regra_id)` de `rede_conexao`/`rede_associacao` com `ON DELETE SET NULL` (item L4-03-a) zerava
as DUAS colunas do lado referenciador — inclusive `tenant_id`, que é `NOT NULL` — e qualquer reimportação
de CSV que removesse uma regra ainda em uso quebrava com `500`. Trocada por FK de uma coluna só
(`regra_id -> rede_regra.id`). **Fronteira honesta**: com a FK corrigida, `regra_inexistente` fica
inalcançável pela API (o banco garante `regra_id` sempre NULL-ou-válido) — continua no código como
validação defensiva, documentado no ADR e não afirmado como provocado no teste. `Verify`/`Repair Network
Topology` (validação sem gravar erro / reparo automático de geometria) ficam fora deste item. 19 testes
novos (`tests/api/test_areas_sujas_e_validacao.py`), 2 rotas somadas a `tests/api/eventos_esperados.py`
que faltavam desde L4-01-a (mais 2 de `/api/mapas`, gap de outro item, documentadas como `[]`), `docs/
PARIDADE.md` com a seção da capacidade, ADR `20260907T1243-areas-sujas-e-validacao.md`.

## turno 4, setembro de 2026 (item L4-03-a-regras-de-conectividade: applyEdits, validação em lote e CSV de regras)

O pacote elétrico ganha um QUINTO tipo de regra (`aresta_juncao_aresta`, separado de `juncao_aresta`
porque o papel da junção do meio é o VIA, não o terminal) e cresce de 24 para **58 regras**, cobrindo
os cinco tipos da *utility network* Esri (*Junction-Junction*, *Junction-Edge*, *Edge-Junction-Edge*,
*Containment*, *Structural Attachment*). A política padrão é **"sem regra = proibido"**: `POST
/api/rede/{id}/applyEdits` deriva as conexões da geometria gravada (coincidência de ponto, tolerância
0,5 m) e recusa com `409` — código `sem_regra` ou `terminal_errado`, mensagem citando a regra ou as
candidatas — qualquer par de tipos sem regra; associação (contenção/estrutura) é sempre explícita e
direcional. `POST .../validar` reavalia tudo em lote mesmo com a comporta desligada (é o instrumento
de auditoria da carga em massa). CSV nas 13 colunas de Import/Export Rules do ArcGIS Pro 3.4
(`regras_csv.py`): a ferramenta da Esri ACRESCENTA, esta SUBSTITUI o conjunto inteiro numa transação —
diferença documentada no ADR 20260906T2058. A única comporta (`plat.rede.regras_ativas`) é um
privilégio novo, `rede.administrar` (perfil admin), separado de `rede.editar`: quem edita feição não
desliga a avaliação nem substitui o conjunto de regras por CSV.

Trabalho do agente Kimi K3 (motor `regras.py`, migração, rotas, CSV — 15 commits, ~1.700 linhas)
estava pronto no worktree mas sem prova: sem rebase contra `master` (90 mil linhas de divergência,
toda aditiva — a linha L4 inteira e mais 4 itens ainda não tinham chegado à árvore principal), sem
nenhum teste do item (as rotas de applyEdits/CSV/ativação ficaram fora de commit), e a resposta de
`GET /api/rede/{id}` não expunha `regras_ativas` (só o `PUT` de ativação devolvia). Consertado neste
turno: rebase limpo (só `CHANGELOG.md` colidiu, textual); `regras_ativas` agora sai em toda ficha de
rede; 34 testes novos escritos e verdes (`tests/unit/test_regras_motor.py` — motor puro, sem banco;
`tests/api/test_regras_conectividade.py` — applyEdits/validar/comporta contra a API real;
`tests/api/test_regras_csv.py` — round-trip por token, malformação, privilégio); dois testes de
regressão de L4-01-a atualizados para a forma nova (7 rotas de escrita, não 3; a FK de auditoria
`rede_feicao.criado_por → usuario` entra em `PERMITIDAS` no mesmo padrão de `rede.dono_id`); ADR
20260906T2058 escrito (não existia, só citado); `docs/PARIDADE.md` atualizado (24→58 regras,
"parcial" → "feito"); `docs/openapi.json` regerado (0 rotas perdidas, 42 adicionadas pelo rebase +
este item). **Fronteira honesta**: a `descricao` da regra (só existe no pacote JSON) não sobrevive
ao round-trip de CSV — não é uma das 13 colunas da Esri, e o teste prova os dois lados. `via_terminal`
está no esquema e no CSV mas nenhuma regra do pacote elétrico o usa — pendência nomeada, não testada
com dado real. Paridade contra ArcGIS Pro/AGOL reais continua `pendente` (decisão D20).
## turno 3, setembro de 2026 (item L4-05-g-osm-power: conector OpenStreetMap power=* como rede de baixa confiança)

`POST /api/rede/{rede_id}/importar-osm` monta a rede power=* (linha, torre, poste, transformador,
subestação, geração distribuída) de UM município a partir de um extrato `.pbf`/`.osm` já na máquina, sobre
o pacote `eletrica-br` já importado na rede. Cada elemento grava `fonte = 'OSM'` nos atributos e a ficha da
importação (`GET .../importacoes`) mostra sempre a licença ODbL e o aviso "cadastro comunitário, não
oficial" — nunca dado oficial disfarçado de oficial. A topologia vem só dos refs do extrato (nunca de
coincidência geométrica): uma via vira um ou mais trechos, cortada nos vértices compartilhados com outra
via, nas pontas, e em nó tipado que muda o dono do trecho (transformador/subestação/gerador); torre e
poste fixam no trecho sem cortar, pela mesma regra de fixação estrutural do catálogo. Contagem sempre
conferida por etiqueta contra o que o extrato tinha dentro do recorte — o que não entra vira desvio
explicado, nunca silêncio. Leitura do extrato em fluxo (osmium `tags-filter` linha a linha) com **teto
declarado de 300 mil elementos** (`MAX_ELEMENTOS`): acima dele o subprocesso é encerrado e a importação
falha com erro explicado, nunca acumulando sem fim (regra dura da casa: extração de OSM nunca em memória
sem limite — já derrubou o banco desta máquina uma vez). Teste: `tests/api/test_rede_osm.py` (6 casos,
extrato sintético `tests/dados/taquari_power.osm` sobre o limite oficial de Taquari-RS); refutação provada
em `test_nunca_liga_no_de_outra_fonte_por_coincidencia` — um nó de outra fonte na MESMA coordenada de um
vértice que o OSM corta não recebe associação nenhuma da importação.

De quebra, um conserto que vale para qualquer importador em lote da casa: `psycopg2.extras.execute_values`
monta a consulta em **bytes**, e o reescritor de schema de homologação/trilha (`app/schema_ambiente.py`)
só tratava `str` — todo `INSERT ... VALUES %s` em lote (usado por este conector e por `bdgd.py`) ia sempre
para o schema `plat` de produção em vez do schema isolado da trilha, e falhava com "permission denied for
schema plat" em qualquer ambiente que não fosse produção. Corrigido decodificando bytes antes de reescrever.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: o esquema da rede de utilidades é dado)

Primeiro item da linha L4. O esquema de uma rede de utilidades — redes de domínio, tiers, grupos e tipos de
ativo, categorias de rede, atributos e configurações de terminal — passa a ser um **pacote de ativos**: um
documento JSON versionado, importado para dez tabelas `plat.rede_*` do inquilino (`POST
/api/rede/{rede_id}/pacote`) e exportado de volta a partir delas (`GET .../pacote`). O contrato está no ADR
0019; o mapeamento coluna a coluna, em `docs/PACOTE_REDE.md`, gerado do próprio dado.

A exportação é **reconstruída das tabelas**, nunca o arquivo recebido — dos 96.042 bytes importados do pacote
`eletrica-br`, saem os mesmos 96.042 bytes, e um teste altera uma linha no banco para mostrar que a exportação
muda junto (`test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido`). Pacote recusado sai com a lista
inteira de problemas, cada um com o caminho (`tipos[41].grupo`) e a **linha do arquivo enviado**.

Dois pacotes vêm com a instalação: `eletrica-br` (2 domínios, 4 tiers, 14 grupos, 24 tipos, 214 atributos, 24
regras) cobrindo as 13 camadas de rede da BDGD do Módulo 10 do PRODIST, e `agua-epanet` (1 domínio, 2 tiers, 6
grupos, 14 tipos, 41 atributos, 16 regras) no vocabulário do EPANET 2.2.

⛔ Fronteira honesta declarada no próprio dado: dos 214 atributos do pacote elétrico, **154 têm a coluna de
origem conferida contra uma extração real** (11 camadas) e **60 são declarados do documento da fonte, sem
conferência** (`SUB`, `UNSEMT`, `UNCRMT`, `UNREMT`, `UGMT_tab`); o pacote de água é inteiramente declarado.
Nenhum atributo com `conferida = false` deve decidir carga de dado sem antes conferir o dicionário da entrega.
Topologia, traçado e subrede não existem ainda — este item entrega só o catálogo do esquema.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: conserto pós-adversário, refutado -> corrigido)

O adversário independente do turno 3 (`handoffs/T3/ataque-L4-portal-ADVERSARIO.md` §1) refutou o item com
seis achados; todos corrigidos, com a mesma bateria de teste virando regressão permanente
(`tests/api/test_rede_pacote_conserto_a1_a4.py`, `tests/api/test_fk_composta_por_inquilino.py`).

**A1** (a FK não era filtrada pela RLS): as 10 tabelas `plat.rede_*` ganharam FK **composta** `(tenant_id,
id)` (`db/migracoes/20260906T1815_rede_fk_por_inquilino.sql`) — um inquilino não pendura mais linha própria
em `tipo`/`domínio` de outro pelo uuid alheio. A trava (`test_fk_composta_por_inquilino.py`) varre
`pg_constraint` do schema inteiro, não só a rede; achou 55 FKs do mesmo padrão em outras tabelas do produto,
documentadas como fora de escopo (não corrigidas aqui).

**A2/A2b** (seção repetida entrava em silêncio e a linha apontada era a errada): `localizador.py` foi
reescrito para construir um mapa de offsets numa única passada — a última ocorrência de uma chave
sobrescreve a anterior, como `json.loads`, então a linha apontada é sempre a da seção que a validação de
fato usou; `pacote._chave_repetida` recusa com 422 qualquer chave repetida, em qualquer profundidade.

**A3** (NUL em `texto`/`jsonb` derrubava a importação com 500): `pacote._procurar_nul` recusa com 422 antes
de a string chegar ao psycopg2.

**A4** (a rota travava o laço de eventos e a localização de linha era quadrática): `POST
.../{rede_id}/pacote` só lê o corpo no laço de eventos; validação e gravação vão para
`run_in_threadpool`. O mesmo mapa de offsets do conserto A2b tornou a localização de linha linear (medido:
pacote de 4 mil erros, 14,1 s → 1,2 s; pior `/saude` concorrente, 13,6 s → 0,19 s —
`tests/medidas/L4-01-a.json`). Tornar a concorrência real expôs um `DeadlockDetected` não tratado em duas
importações simultâneas na MESMA rede; corrigido com `SELECT ... FOR UPDATE` na linha da rede
(`_travar_rede`), que serializa a substituição do catálogo sem 500.

## turno 3, setembro de 2026 (item L6-01-h-frescor-verificacao: verificação periódica de frescor do acervo)

Job semanal `acervo.frescor_verificar` (`app/acervo/tarefas.py`, periódico domingo 05:20 em
`app/acervo/periodicos.py`), retomado do RESGATE da sessão executora derrubada por cota e fechado neste turno:
por camada EXPOSTA do registro (`plat.acervo_camada`, L6-01-a), `COUNT(*)` exato sob `SET LOCAL
statement_timeout` de 25 s (estouro vira o estado `nao_contado_no_prazo`, nunca zero — é o achado da casa de
01/09 que deu origem ao item), hash de conteúdo próprio quando há comando de reexecução declarado, e teste
HTTP (com defesa de SSRF de `app/conexao/seguranca.py`) dos endereços confirmados, com teto de 40 por rodada.
Tudo gravado em `plat` por funções `SECURITY DEFINER` (migração `20260906T1617_acervo_frescor.sql`) que só
rodam no inquilino técnico `plataforma`; trinco de rodada COM dimensão de inquilino (`plat.acervo_frescor_execucao`,
índice único parcial por `tenant_id`) — lição do L0-05-d, não a chave global de `plat.job`. `GET
/api/acervo/camadas` (com `vencida=true`), `GET /api/acervo/camadas/{id}/verificacoes` (12 mais recentes),
`GET /api/acervo/frescor/mudancas` (variação > 5 %) e `GET /api/acervo/frescor/execucoes`
(`app/acervo/rotas_frescor.py`); ficha do acervo e mapa (`/mapa`, painel `mapa-painel-acervo`) mostram o
mesmo selo `verificação vencida` de um módulo único (`web/js/acervo/frescor.js`), com o motivo (endereço
morto, prazo da fonte vencido, nunca verificada, verificação com mais de 14 dias).

Um defeito real corrigido rodando a suíte de verdade: `tests/api/test_acervo_frescor.py::_limpar_job`
tentava `UPDATE plat.job SET estado='concluido'` numa sessão `psql` NOVA sem religar o GUC
`plat.via_worker` daquela sessão (o gatilho `plat.job_transicao` só deixa a transição ir pelo worker) —
derrubava os quatro testes que chamam `acervo_frescor_verificar` de verdade. Corrigido religando o GUC no
mesmo comando, mesmo padrão de `_contexto_job`. Um teste reescrito por ser estatisticamente instável, não
por engano de lógica: `test_contagem_que_estoura_o_prazo_nao_vira_zero` forçava 1 ms de prazo sobre as 3
primeiras candidatas por ORDEM DE VERIFICAÇÃO, que nesta base são tabelas de poucas dezenas a milhares de
linhas — `COUNT(*)` às vezes terminava antes do Postgres checar a interrupção. Passa a chamar a função
privada `_contar` direto contra a maior tabela exposta da base (353.894 linhas medidas), onde 1 ms nunca
basta em nenhuma máquina. Uma lacuna de RLS achada por `tests/api/test_migracoes.py`: a migração do RESGATE
dava `GRANT SELECT` de `plat.acervo_frescor_execucao` a `plat_app` sem nunca ligar `ROW LEVEL SECURITY` —
qualquer inquilino leria a execução de rodada de outro (na prática só o inquilino técnico grava lá, mas o
invariante da casa exige a política mesmo assim). Corrigido em migração NOVA (a aplicada não se edita):
`20260906T1804_acervo_frescor_rls.sql`, mesmo padrão de `plat.conexao_saude_historico` (036).

Medido de verdade contra a base da trilha (`PLAT_GRAVAR_MEDIDAS=1`, `tests/medidas/L6-01-h-frescor-verificacao.json`):
**109/109 camadas expostas cobertas em 0,41 min** (portão: ≤ 30 min), 10 endereços testados por HTTP com 8
respostas, histórico de 12 verificações por camada confirmado após 15 gravações, 0 mudanças acima de 5 %
nesta rodada. `tests/api/test_acervo_frescor.py`: 13/13 passam duas vezes seguidas contra `plat_tt4fres`.
Refutação do item (adversário derruba um endpoint na fixture e confere o aviso) coberta por
`test_endpoint_derrubado_acende_o_aviso`: o aviso `endpoint_morto` aparece na ficha e no filtro `vencida=true`
e SOME quando o endereço volta a responder.

**Achados registrados, fora do portão deste item — não corrigidos aqui**: (1) incidente de produção — a
migração `20260906T1617_acervo_frescor` apareceu em `plat.versao_migracao` de PRODUÇÃO às 18:03:00 UTC deste
turno, junto com cinco migrações de outros ramos ainda não juntados (aviso do gerente); as verificações desta
sessão mostram que nenhum comando desta trilha escreveria lá (`trilha_ambiente.sh`/`trilha_reescrever.py`
reescrevem todo `plat.` para `plat_tt4fres.` antes de executar, e os `psql` diretos desta sessão foram só
leitura) — a origem mais provável é outro processo que rodou `db/migrar.sh`/`install.sh` fora de worktree ou
com o schema de outro ramo já copiado para a árvore principal; é idempotente e se reconcilia na junção real,
e a migração `20260906T1804` desta entrada corrige a lacuna de RLS também em produção quando aplicada lá.
(2) `laco/trilha_ambiente.sh` lê `listar_migracoes "$REPO/db/migracoes"` (a árvore principal
`/home/dev/plataforma/enterprise`, compartilhada e mexida por outras sessões o tempo todo), não
`"$FONTE/db/migracoes"` (o worktree da própria trilha) apesar do comentário do script dizer o contrário —
nesta rodada isso trouxe para o schema `plat_tt4fres` uma migração de outro ramo
(`20260906T1615_revoke_public_uploads_expirar`) que não existe no `db/migracoes` deste worktree, e quebrou
`tests/api/test_migracoes.py::test_tabela_reflete_os_arquivos_em_disco` (não é um defeito deste item; é um
defeito do script de trilha, fora do escopo de arquivo do L6-01-h — script mora em `laco/`, não no worktree).
(3) `tests/api/test_migracoes.py::test_migrar_duas_vezes_nao_insere_linha` e
`test_arquivo_aplicado_editado_devolve_codigo_3` passaram a falhar depois que a guarda nova de
`db/migrar.sh` (inserida pelo gerente nesta mesma janela, código de saída 9 ao rodar de dentro de um
worktree) mudou o comportamento que esses dois testes esperavam (código 3); também fora do escopo deste item.
## turno 8, setembro de 2026 (item L6-02-i-google-sheets: camada_schema_garantir serializado por slug)

A rodada completa da suíte de conexões (a cláusula que faltava ao item) esbarrava em "tuple concurrently
updated": com dois processos de worker na 1ª carga do mesmo inquilino, os dois executavam CREATE SCHEMA
IF NOT EXISTS + GRANT USAGE no mesmo schema ao mesmo tempo, e o GRANT reescreve a ACL da mesma tupla do
catálogo. A migração 20260908T2210 acrescenta pg_advisory_xact_lock por slug em plat.camada_schema_garantir:
a segunda chamada espera a primeira commitar e reconfere o IF NOT EXISTS. Duas rodadas completas seguidas
de tests/api/conexao/test_google_sheets.py: 8 passed (carga 3,5).

## turno 3, setembro de 2026 (item L0-07-d-smtp-convites: SMTP, convite de membro por e-mail e redefinição de senha por e-mail)
- **L7-06-d-paineis**: cinco painéis Grafana provisionados por arquivo (`deploy/grafana/paineis/*.json` + `deploy/grafana/provisioning/`), homologação própria (`deploy/paineis_homologacao.sh`) com carga curta de verdade e captura de cada painel em `tests/e2e/capturas/`. Métricas novas para o que os painéis precisavam e não existia: usuários ativos em 24 h, duração e tamanho do último backup/ensaio, uso de armazenamento e tamanho do schema de dado por inquilino.

SMTP configurável na instalação (`.env`, `PLAT_SMTP_*`) e por inquilino (`tenant.config->'smtp'`, senha
cifrada AES-GCM com rótulo próprio `plat-smtp`); `GET/PUT /api/org/smtp` e `POST /api/org/smtp/testar`
(envio síncrono, erro legível, nunca a senha). E-mail sempre por job `correio.enviar` (fila do L0-05),
`somente_sistema=True` (campo novo em `app/jobs/registro.py`) impede a criação via `POST /api/jobs` mesmo
por admin — fecharia canhão de spam com o SMTP do inquilino; só `app/jobs/sistema.py::enfileirar` cria.
Convite de membro (`plat.convite`, migração 047): o link carrega só o token, nunca o e-mail — o servidor
sempre lê o que o convite guarda (`ConviteAceitarEntrada` é `extra="forbid"`, um `email` extra no corpo
vira 422 antes de tocar o banco); token de uso único (sha256), validade 7 dias, aceitar roda numa função
SQL `SECURITY DEFINER` com `FOR UPDATE` que cria a conta e marca o convite usado na mesma transação. Sem
SMTP, a resposta devolve `link_manual` (mesmo padrão de senha temporária mostrada uma vez). Redefinição de
senha por e-mail (`plat.redefinicao_senha` + `plat.redefinicao_pedido`): solicitar sempre devolve
`202 {"ok":true}`, exista ou não a conta; limite de taxa por (inquilino, e-mail), 5 pedidos a cada 15
minutos, contado mesmo para e-mail inexistente (senão o próprio limite revelaria existência); aplicar
reusa a mesma rotina de troca de senha/histórico/sessões de `PUT /api/eu/senha`. Telas: `/admin/organizacao`
(seção SMTP), `/admin/usuarios` (convidar + lista de pendentes), `/aceitar-convite` e `/redefinir-senha`
(públicas). ADR 0017.

Três defeitos reais achados rodando de verdade contra `https://plat.iagrointel.com` com um servidor SMTP
de captura em stdlib puro (`tests/api/util_smtp_captura.py` — `aiosmtpd` está ausente) e o `plat-worker`
real, corrigidos ANTES do adversário (migrações 048/049): (1) variável PL/pgSQL `chave` ambígua contra a
coluna homônima em `plat.redefinicao_pedido` — todo `POST /api/senha/redefinir/solicitar` caía em 500;
(2) sete tipos de evento novos nunca inseridos em `plat.evento_tipo` — toda `registrar_evento` correspondente
violava a FK (500 em `PUT/DELETE /api/org/smtp`, `POST /api/convites`, aceitar convite, aplicar
redefinição); (3) duas consultas a `plat.tenant` sem contexto de inquilino (a conta ainda não existe)
caíam na RLS e devolviam `None` em vez da linha; (4) `correio.enviar` com `memoria_mb=192` estourava de
verdade o `RLIMIT_DATA` do filho (cryptography importado pela primeira vez depois do fork), subiu para 512.
Medido, com o worker/API reais e o servidor de captura: convite chega e-mail→resolver→aceitar→conta
criada→login funciona; link usado de novo e expirado (7 dias simulados por UPDATE direto) dão `410`
nos dois casos; e-mail malicioso extra no corpo do aceite vira `422` e nunca altera o e-mail da conta
criada (sempre o do convite); redefinição ponta a ponta com o mesmo padrão; 12 pedidos seguidos de
redefinição para o mesmo e-mail estouram o limite de taxa antes do fim (refutação do item); `testar envio`
com host inexistente devolve erro legível em menos de 1 s; a senha SMTP em claro NUNCA aparece no
`journalctl` real de `plat-worker`/`plat-api` (grep direto no log real, não simulado);
`POST /api/jobs {"tipo":"correio.enviar"}` recusa `403` mesmo para o admin do inquilino; isolamento
cruzado confirmado (admin de outro inquilino recebe `404` ao tentar cancelar convite alheio).
`tests/api/test_smtp_convites.py` + `tests/unit/test_correio_cifra.py` + `test_correio_cliente.py`:
21/21 passam contra o schema `plat` de produção. **Pendência nomeada**: o e2e de navegador
(`tests/e2e/test_convite.py`, escrito e com lint limpo) não foi executado neste turno — swap da
máquina em 7,7/8,0 GiB no momento do fechamento (contenção de múltiplos agentes concorrentes no laço,
não desta mudança), e a casa já teve OOM por lançar Chromium sob essa pressão; roda no próximo `make e2e`
com RAM livre. Fora do portão literal deste turno (hipótese do item, registrado no ADR 0017 §D5): avisos
de expiração de token (90/30/7/1 dia) e notificação de grupo por e-mail — o job `correio.enviar` já serve,
falta só o gatilho periódico cross-tenant.
## turno 3, setembro de 2026 (item L0-13-dado-demonstracao: conjunto aberto de demonstração)
## turno 3, setembro de 2026 (item L6-02-h-csv-url-geojson-kml: arquivo por URL pública vira camada)

Conexão `http` no modo `copiada` passa a ser fonte de ARQUIVO: `PUT /api/conexoes/{id}/arquivo` configura,
`POST /api/conexoes/{id}/arquivo/sincronizar` enfileira uma passagem e `GET .../arquivo` mostra o estado.
O job `conexoes.arquivo_sincronizar` baixa pelo MESMO `buscar_seguro` do teste de saúde (nenhum cliente HTTP
novo), reconhece o formato pelos bytes (`csv`, `geojson`, `kml`, `kmz`, `georss`, `gpx` — nunca pela extensão
nem pelo Content-Type), converte KML/KMZ/GeoRSS/GPX para GeoJSON com `ogr2ogr` como neto do job e entrega ao
pipeline de ingestão do L0-04 sem alterar nada dele: a camada nasce `camada_vetorial` com tabela PostGIS, RLS
e estatísticas, igual à importada à mão. Periódico `conexoes.arquivo_sincronizar_vencidas` (`*/15 * * * *`)
enfileira as agendadas vencidas, cada uma no inquilino dono.

Atualização agendada que não recarrega igual: `plat.conexao_arquivo` (migração
`20260906T1549391_conexao_arquivo_url.sql`) guarda ETag/Last-Modified/sha256 e os contadores `sincronizacoes`
x `recargas`. `304` não recarrega; servidor que ignora o condicional e responde `200` com o mesmo corpo também
não (o sha256 segura). Medido ponta a ponta contra um servidor no endereço público desta máquina — a defesa de
SSRF fica ligada e `localhost` continua recusado.

Consertado de caminho, no módulo de conexão: `Authorization`/`Cookie`/`Proxy-Authorization`/`X-Api-Key`
deixavam de ser removidos num redirecionamento para outro host (achado do adversário do L6-02-a, que deixou
aquele item marcado REFUTADO). Agora só seguem para o mesmo host, mesma porta e sem queda de https para http.
`ResultadoBusca` ganhou os cabeçalhos da resposta (é deles que sai o ETag).

Consertados dois defeitos de `app/ingestao/carregar.py` que só apareciam em camada de UM ponto — o caso mais
comum de arquivo pequeno por URL: a envoltória era lida do GeoJSON de `ST_Extent` (que degenera para `[x, y]`
e levantava "'float' object is not iterable") e, corrigida essa leitura, o retângulo de largura zero virava um
polígono inválido que o CHECK `item_extent_check` recusava. Agora a envoltória vem de `ST_XMin/ST_YMin/...` e o
lado nulo é afastado em `INGESTAO_EPSILON_ENVOLTORIA` (1e-7 grau, ~1 cm) — só o retângulo do item muda, nunca a
geometria da feição.

Refutação do item: CSV com latitude e longitude trocadas é RECUSADO quando produz valor fora de faixa, com a
mensagem dizendo que as colunas parecem trocadas; a plataforma nunca troca sozinha. A limitação — troca
indetectável quando os dois valores cabem em -90..90 — tem teste próprio para ninguém prometer mais do que o
mecanismo faz. KML de 200 mil pontos não é recusado: é medido.

O produto passa a trazer o próprio dado para se mostrar: 11 arquivos abertos e pequenos (1,19 MB no total)
em `dados_demo/arquivos/`, comitados no repositório, com fonte, órgão, endereço, licença e data de acesso
por arquivo em `dados_demo/catalogo.json` e em `docs/DADO_DEMO.md`. São limites municipais de dois estados
e ponto representativo por município (IBGE), rodovias federais de dois estados (DNIT/SNV), hidrografia de
uma otto-bacia (ANA/BHO 2017), cadastro de estações do INMET em CSV e em XLSX, um GeoPackage com três
camadas e uma planta de exemplo em DXF desenhada pela casa. `scripts/semear_dado_demo.py` semeia pela
PRÓPRIA API — envia o arquivo, registra o item, cria a importação e confirma a proposta —, é idempotente
(reconhece pelo título) e é chamado pelo `install.sh` (seção h2b) só quando a instalação é de demonstração.
`demo` e `demo2` recebem conjuntos DIFERENTES, que é como o isolamento entre inquilinos aparece na tela.
Cada item semeado carrega a licença em `termos_de_uso`, o órgão em `creditos` e o endereço em `url`.
Correção de infraestrutura junto: o advisory lock de "um job pesado por vez" era global no banco
(`plat.job.pesado`) e passa a levar o nome do schema, para que homologação e trilhas isoladas não disputem
a vaga com o worker de produção.
## turno 3, setembro de 2026 (item L7-03-b-antivirus-anexos: varredura de anexo e entrega segura)

Conserto dos achados 22 a 25 do adversário independente do turno 3 (`laco/handoffs/T3/ataque-g6-ADVERSARIO.md`),
que refutaram a camada de varredura de anexo: o polyglot (imagem válida com script colado depois) passava,
`Content-Type` fora da tabela desligava a varredura inteira, só os primeiros 8 KiB eram olhados e zip/kmz não
era aberto.

**A varredura deixou de depender do que o remetente declara.** `app/varredura_conteudo.py` passou de uma
checagem (família declarada x tipo do `libmagic`) para cinco, na ordem: família declarada x tipo real; lista de
negação determinística válida sob QUALQUER `Content-Type`, inclusive vazio, inventado e
`application/octet-stream` (shebang, assinatura de executável conferida à mão, tipo real de script/HTML sobre
bytes que são texto); busca de carga executável no corpo inteiro entregue pelo chamador, com emenda entre as
partes do multipart; integridade estrutural de imagem (PNG termina em `IEND`, JPEG em `FFD9`, GIF em `0x3B` —
byte depois do fim recusa); e lista de entradas do zip/kmz (extensão de script/executável ou conteúdo que
começa com shebang). Tipo declarado desconhecido deixou de significar "não examinar" e passou a significar
rigor máximo. Nenhuma regra usa o RÓTULO do `libmagic` para binário, porque ~0,9% dos blocos aleatórios saem
rotulados como outra coisa (MEDIDO, 18/2000): executável exige a assinatura mágica real no início — no caso do
`MZ`, com o `PE\0\0` conferido no deslocamento que o próprio arquivo declara em 0x3C — e script/HTML exige que
os bytes sejam texto. Limite declarado: as checagens de cabeçalho, estrutura e zip valem sobre a primeira parte
do envio (8 MiB); a busca de carga vale sobre o corpo inteiro.

**O conteúdo enviado por cliente volta como anexo, nunca como página.** `GET /api/arquivos/{sha256}` devolvia o
byte com o mesmo `Content-Type` que o remetente escolhera e sem `Content-Disposition` — um arquivo enviado como
`text/html` renderizava na origem da aplicação. `app/entrega_conteudo.py` rebaixa para
`application/octet-stream` tudo que não está no vocabulário fechado de `app/objetos.EXTENSOES`, força
`Content-Disposition: attachment` (nas duas formas da RFC 6266) e manda `X-Content-Type-Options: nosniff`; vale
para `GET /api/arquivos/{sha256}` e para a rota anônima `GET /api/objetos/{chave}`. A miniatura de item recebe
só o `nosniff`, porque é um PNG redesenhado pelo Pillow servido dentro de `<img>`.

Os 9 testes que o adversário deixou como `xfail(strict=True)` em
`tests/adversario/test_g6_varredura_anexos.py` passaram a reprovar de verdade e a marca saiu (o texto do ataque
ficou como comentário). `tests/unit/test_varredura_conteudo_polyglot.py` (24 testes) cobre os quatro grupos, a
entrega segura e — para que nenhuma regra volte a depender de sorte — 300 amostras de `os.urandom` sob
`application/octet-stream` e 100 sob `text/plain`, todas aceitas. Detalhe em `docs/SEGURANCA.md` §8.2 e §8.6.

## turno 3, setembro de 2026 (itens L7-31 e L7-19: credencial de armazenamento por ambiente, segredo em claro)

Conserto dos achados 11, 17 e 18 do adversário independente do turno 3
(`laco/handoffs/T3/ataque-g6-ADVERSARIO.md`).

**Homologação deixa de compartilhar a credencial raiz do armazenamento.** O `PLAT_GARAGE_ADMIN_TOKEN` era
byte a byte o mesmo nos dois ambientes (sha256 `e36bc0be9a6500d9` dos dois lados) e com ele o adversário
listou e leu os buckets de produção `plat-demo` (84 objetos, 127.026.292 bytes) e `plat-demo2`. Homologação
passa a ter uma chave S3 própria, sem poder de administração, criada e mantida pelo passo de operador
`scripts/garage_homolog_provisionar.sh`; `db/homolog_bootstrap.sh` chama esse passo em vez de copiar o token
do `.env` de produção. `app/objetos.py` ganha o modo de chave própria: sem token de administração e com
`PLAT_GARAGE_CHAVE_ID`/`PLAT_GARAGE_CHAVE_SEGREDO`, o bucket do inquilino nasce pelo `CreateBucket` do S3.
MEDIDO no Garage v2.3.0 desta máquina: bucket assim criado tem alias LOCAL da chave (não entra no espaço de
nomes global) e a chave recebe `403 AccessDenied` em qualquer bucket de que não seja dona. Produção não
declara essas chaves e segue no modo de administração, sem mudança de comportamento.
`tests/unit/test_isolamento_homologacao.py` (8 testes, só leitura, pulam com motivo se o Garage estiver
parado) prova: nenhum valor de credencial repetido entre os dois ambientes; nenhum token de administração
em homologação nem na configuração EFETIVA (que herda o `.env` de produção); `ListBuckets` da chave de
homologação sem bucket de produção; `403` ao listar `plat-demo` e `plat-demo2`; recusa da API de
administração ao segredo de homologação. Limitações declaradas do modo sem administração, em
`docs/AMBIENTES.md`: não há par RW/RO distinto, a cota não é gravada no Garage (só a checagem da aplicação
barra) e o uso em bytes vem de listagem.

**`PLAT_DSN` e `PLAT_GARAGE_ADMIN_TOKEN` preparados para sair do `.env`.** `app/settings.py` já lia qualquer
campo de `Settings` do `LoadCredential=` do systemd; ganha `SEGREDOS` (lista canônica) e
`segredos_em_claro()` (devolve nome, nunca valor). `install.sh` migra os dois para `/etc/plat/segredos/` no
mesmo padrão dos dois anteriores e passa a alinhar a senha de `plat_app` pelo credential;
`deploy/plat-api.service` e `deploy/plat-worker.service` declaram os dois `LoadCredential=`; o `Makefile`
injeta os quatro na suíte. `scripts/rotacionar_segredo.sh` cobre agora cinco nomes — os dois antigos mais
`PLAT_DSN`, `PLAT_GARAGE_ADMIN_TOKEN` (token gerenciado do Garage v2) e `PLAT_GARAGE_S3 <slug>`, esta última
a única sem reinício, porque a aplicação lê as chaves S3 do banco a cada chamada.
`deploy/plataforma-garage-segredos.conf` tira `rpc_secret` e `admin_token` do `garage.toml`; MEDIDO que o
binário aceita a forma por arquivo (`GARAGE_RPC_SECRET_FILE` com config sem a linha `rpc_secret` fala com o
daemon vivo). **A troca de valor em produção NÃO foi executada**: derruba serviço vivo e são os passos 1 a 3
de `docs/AMBIENTES.md` §5, com comando exato e como voltar atrás. Por isso o teste do adversário
`test_env_de_producao_nao_pode_ter_segredo_em_claro` e o `test_garage_toml_nao_pode_ter_token_em_claro`
continuam `xfail(strict=True)`; as duas marcas retiradas foram as de
`test_producao_e_homologacao_nao_compartilham_segredo` e `test_rotacao_cobre_os_cinco_segredos_do_portao`.
## turno 3, setembro de 2026 (item L6-01-b-view-so-leitura: publicação sem cópia do acervo)

Cada camada exposta do registro do acervo (`plat.acervo_camada`, item L6-01-a) passa a ter uma VIEW em
`plat_acervo`, com só as colunas da lista branca e o porteiro `plat.acervo_pode_ler('<camada>')` no `WHERE`.
Nenhum byte é copiado: a view lê a tabela original e usa o índice GiST dela. A leitura só passa quando o
inquilino tem linha em `plat.acervo_assinatura` — sem assinatura a view devolve zero linha e a API devolve
403. `plat_app` continua sem privilégio nenhum no schema `public`: quem tem `SELECT` na tabela de origem é o
papel `plat_acervo_publicador`, dono das views, que recebe uma tabela por vez. A view tem só `GRANT SELECT`,
então escrita é recusada pelo próprio Postgres, não pela ausência de rota. Rotas novas:
`GET /api/acervo/camadas`, `POST`/`DELETE /api/acervo/camadas/{camada}/assinatura`,
`GET /api/acervo/camadas/{camada}/feicoes` (GeoJSON por caixa envolvente) e
`GET /api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt`. Publicador: `scripts/acervo_publicar.py` (roda como
`postgres`, idempotente, despublica sozinho quem sai de `exposta`). Medido sobre `public.car_area_imovel`
(8.406.837 linhas por `COUNT(*)`; 7.357.920 é a estimativa `reltuples`): consulta de mapa por caixa
envolvente em 1,5 ms de mediana. Duas cláusulas da hipótese caíram na medição e estão no ADR 0018:
`SECURITY INVOKER` é incompatível com "nenhum GRANT direto a plat_app" (o Postgres recusa), e
`security_barrier` derruba o índice GiST porque o `&&` de geometria não é `LEAKPROOF` — o que protege é o
porteiro virar `One-Time Filter`, com o nó do índice `(never executed)`.
## turno 3, setembro de 2026 (conserto de segurança L6-02-a: credencial não atravessa mudança de origem)

`app/conexao/seguranca.buscar_seguro` retira `Authorization`, `Cookie`, `Proxy-Authorization` e qualquer nome
declarado em `cabecalhos_secretos` no primeiro salto de redirecionamento em que esquema, host ou porta deixam
de ser os da URL original; a retirada é definitiva (cadeia a→b→a não devolve a credencial) e redirecionamento
na mesma origem continua autenticado. `ResultadoBusca` ganhou o campo `credencial_retirada`. Conserta o achado
do adversário do grupo G5 (turno 3): a rota `POST /api/conexoes/{id}/testar` e o periódico
`conexoes.saude_verificar` decifram a credencial do inquilino, e um serviço cadastrado que respondesse 302
para outro host recebia esse segredo. `requests` e `httpx` já retiram a credencial nessa situação; a casa
seguia o redirecionamento à mão (para revalidar SSRF a cada salto) e não tinha herdado a proteção.
Provas: `tests/unit/test_conexao_credencial_redirect.py` (12 casos) e `tests/adversario/test_g5_adversario.py`
(o teste do adversário, agora sem a marca `xfail`). ADR 0012, seção "a credencial nunca atravessa uma mudança
de origem".
falta só o gatilho periódico cross-tenant.## turno 3, setembro de 2026 (item L6-02-h-csv-url-geojson-kml: arquivo por URL pública vira camada)

Conexão `http` no modo `copiada` passa a ser fonte de ARQUIVO: `PUT /api/conexoes/{id}/arquivo` configura,
`POST /api/conexoes/{id}/arquivo/sincronizar` enfileira uma passagem e `GET .../arquivo` mostra o estado.
O job `conexoes.arquivo_sincronizar` baixa pelo MESMO `buscar_seguro` do teste de saúde (nenhum cliente HTTP
novo), reconhece o formato pelos bytes (`csv`, `geojson`, `kml`, `kmz`, `georss`, `gpx` — nunca pela extensão
nem pelo Content-Type), converte KML/KMZ/GeoRSS/GPX para GeoJSON com `ogr2ogr` como neto do job e entrega ao
pipeline de ingestão do L0-04 sem alterar nada dele: a camada nasce `camada_vetorial` com tabela PostGIS, RLS
e estatísticas, igual à importada à mão. Periódico `conexoes.arquivo_sincronizar_vencidas` (`*/15 * * * *`)
enfileira as agendadas vencidas, cada uma no inquilino dono.

Atualização agendada que não recarrega igual: `plat.conexao_arquivo` (migração
`20260906T1549391_conexao_arquivo_url.sql`) guarda ETag/Last-Modified/sha256 e os contadores `sincronizacoes`
x `recargas`. `304` não recarrega; servidor que ignora o condicional e responde `200` com o mesmo corpo também
não (o sha256 segura). Medido ponta a ponta contra um servidor no endereço público desta máquina — a defesa de
SSRF fica ligada e `localhost` continua recusado.

Consertado de caminho, no módulo de conexão: `Authorization`/`Cookie`/`Proxy-Authorization`/`X-Api-Key`
deixavam de ser removidos num redirecionamento para outro host (achado do adversário do L6-02-a, que deixou
aquele item marcado REFUTADO). Agora só seguem para o mesmo host, mesma porta e sem queda de https para http.
`ResultadoBusca` ganhou os cabeçalhos da resposta (é deles que sai o ETag).

Consertados dois defeitos de `app/ingestao/carregar.py` que só apareciam em camada de UM ponto — o caso mais
comum de arquivo pequeno por URL: a envoltória era lida do GeoJSON de `ST_Extent` (que degenera para `[x, y]`
e levantava "'float' object is not iterable") e, corrigida essa leitura, o retângulo de largura zero virava um
polígono inválido que o CHECK `item_extent_check` recusava. Agora a envoltória vem de `ST_XMin/ST_YMin/...` e o
lado nulo é afastado em `INGESTAO_EPSILON_ENVOLTORIA` (1e-7 grau, ~1 cm) — só o retângulo do item muda, nunca a
geometria da feição.

Refutação do item: CSV com latitude e longitude trocadas é RECUSADO quando produz valor fora de faixa, com a
mensagem dizendo que as colunas parecem trocadas; a plataforma nunca troca sozinha. A limitação — troca
indetectável quando os dois valores cabem em -90..90 — tem teste próprio para ninguém prometer mais do que o
mecanismo faz. KML de 200 mil pontos não é recusado: é medido.
## turno 3, setembro de 2026 (nome de migração por carimbo de tempo — ADR 0014)

Migração nova passa a se chamar `db/migracoes/YYYYMMDDTHHMM_<slug>.sql` (carimbo UTC, mais 3 hexadecimais
quando duas nascem no mesmo minuto em trilhas diferentes). O nome do arquivo é CHAVE em
`plat.versao_migracao`, não etiqueta: renumerar um arquivo já aplicado faz o aplicador tratá-lo como novo e
reaplicá-lo. Com trilhas em paralelo, a numeração sequencial colidiu três vezes no mesmo dia (o mesmo arquivo
foi 031 → 037 → 044 → 045). A família de três dígitos fica FECHADA em 048, imutável; nenhum arquivo existente
foi renomeado. `app/migracoes.py` concentra o padrão de nome, a chave de ordenação (legado antes de qualquer
carimbo) e o cabeçalho opcional `-- depende: <arquivo>`; `db/migrar.sh`, `db/migrar_homolog.sh` e
`laco/trilha_ambiente.sh` repetem a mesma chave em bash. `tests/unit/test_migracoes_nome_e_dependencia.py`
reprova nome fora do padrão, três dígitos novos e dependência que vem depois na ordem;
`tests/api/test_saude.py` deixa de casar o glob de três dígitos e escreve o que "última migração" passa a
significar (a de autoria mais recente pela chave, não a maior string nem a última aplicada no relógio).
## turno 10, setembro de 2026 (item L0-09-a-procedencia: o e2e de navegador que faltava no bloco de procedência)

O item estava parcial por uma cláusula só de tela: o bloco de procedência era provado pela API e pelo SQL,
mas não havia e2e de navegador. `tests/e2e/test_procedencia_tela.py` abre a ficha de um item de dado com o
bloco cheio (`POST /api/itens`, tipo `camada_vetorial` — o esquema do tipo `mapa` é estrito e recusa
`dados.procedencia`), procura a seção `section.procedencia`, a nota exata `10,0/10`, os campos com a etiqueta
de origem (`medido` no sha256, `declarado` na licença) e a mensagem "Sem procedência registrada" no item sem
bloco (ausência de registro nunca é 0/10), com capturas 1280 e 390 em `tests/e2e/capturas/L0-09-a_*.png` e
0 erro de console. Observação registrada: o cabeçalho da ficha mostra outra régua de 0-10 (completude do
CADASTRO do item — resumo, descrição, tags, escopo do L0-03), que nos itens novos de teste marca "pontuação
2 de 10"; é outro número, com outro significado, e não entra no escopo deste item.

## turno 3, setembro de 2026 (item L6-02-c-wfs-ogcapi: conector WFS 2.0 e OGC API - Features)
## turno 3, setembro de 2026 (item L6-02-c-wfs-ogcapi: conector WFS 2.0 e OGC API - Features)
## turno 4, setembro de 2026 (item L4-28-identificadores-e-numeracao: identidade de ativo com faixa reservada para campo)

O ativo de rede de utilidades ganha as três identidades de uma vez, todas garantidas no banco
(`db/migracoes/20260906T2121_rede_identificadores.sql`, ADR `20260906T2121-rede-identificadores`):
**global_id** (uuid) interno e estável, que nunca muda nem na renomeação; **código externo** do cliente
(o `COD_ID` da BDGD) único por rede — índice único parcial, duplicado = 409; e **numeração automática por
tipo** com faixa reservada por usuário para criação desconectada, o conceito dos *unit identifiers* da
Esri. A reserva faz o contador do tipo pular a faixa numa instrução só
(`INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, trava de linha até o commit), então conectado e
desconectado nunca colidem e duas reservas simultâneas recebem blocos disjuntos — a refutação do item
(10 reservas concorrentes em duas sessões) virou teste permanente. Renomear o código externo é PATCH: o
global_id fica e cada troca grava linha em `plat.rede_ativo_renomeacao`.

Rotas internas em `/api/rede/{rede_id}/ativos` e `.../faixas`; fachada compatível em
`/rest/services/{servico}/UtilityNetworkServer/unitIdentifiers` com `query` e `reserve` (bloco exato
`firstUnit`/`lastUnit` ou a extensão `count` para o próximo bloco livre), `?token=` e resolução do serviço
por uuid ou nome — o mesmo desenho do GeocodeServer compatível. Divergências da Esri declaradas em
`docs/PARIDADE.md`: erro no contrato da plataforma, `gdbVersion`/`sessionID`/`moment` ignorados, sem
`reset`/`resize` (o contador nunca anda para trás e número entregue nunca é reutilizado). Medidas em
`tests/medidas/L4-28-identificadores-e-numeracao.json` (10 testes na base da trilha + fumaça HTTP ao
vivo: faixa de 100 reservada, 100 ativos criados dentro dela sem colisão, duplicado 409, renomeação com
histórico).

## turno 3, setembro de 2026 (item L0-04-h-exportar: tirar o dado da plataforma, em 11 formatos)

Exportação de camada vetorial como job (`POST /api/exportacoes` → 202; `GET /api/exportacoes[/{id}]`;
`GET /api/exportacoes/{id}/baixar`; `DELETE`), em 11 formatos: GeoPackage, GeoJSON, shapefile zipado, CSV,
XLSX, KML, KMZ, FlatGeobuf, GML, DXF e GeoParquet. Filtro `where` (parser do L2-04-b, lista branca de campos
do item) e `bbox`, campos escolhidos, CRS de saída por EPSG, codificação (UTF-8 ou ISO-8859-1 onde o formato
aceita) e opções de CSV brasileiro (separador, vírgula decimal, nome das colunas de coordenada). O arquivo
gerado vira item `arquivo` na pasta do usuário com validade de 7 dias; o periódico `exportacao.expirar`
apaga objeto e item quando vence e deixa a linha como `expirada` (a auditoria fica). Botão **Exportar** no
painel do item, com a caixa do dono "permitir que outros exportem" (nasce desligada, como na Esri).

Duas medições mandaram no desenho (ADR 0023): (1) **a RLS do PostgreSQL vale dentro do ogr2ogr** quando o
inquilino entra na string de conexão (`options='-c plat.tenant_id=N'`) — sem essa opção o ogr2ogr exporta
0 feição da mesma tabela, com ela exporta exatamente as do inquilino; é o banco, não o nosso código, que
impede a exportação de trazer linha de outro cliente. (2) **o driver LIBKML monta o documento inteiro em
memória**: 3,5 min de CPU e 255 MB de RSS para 50 mil pontos sem terminar, contra 0,34 s do driver `KML`
— por isso KML/KMZ usam o `KML` e o KMZ é o zip feito aqui. O GeoParquet sai pelo DuckDB porque o GDAL 3.8.4
desta máquina não tem driver Parquet (é o único formato que o `ogrinfo` daqui não reabre; o teste o reabre
com o DuckDB, e isso está escrito no catálogo de formatos).

Arquivo grande nunca é montado em memória: `objetos.guardar_arquivo` (novo) lê o arquivo em blocos de 8 MiB
e usa o multipart real do Garage acima de um bloco; a entrega sai em blocos de 1 MiB (`objetos.ler_stream`).
Limites novos em `app/limites.py`: 3 exportações em curso por usuário (429 na quarta) e guarda de disco
medida com `shutil.disk_usage` antes do primeiro byte.

Dois consertos de produto que este item destravou: `CursorSchemaAmbiente` agora reescreve o schema também em
`executemany` e `mogrify` — sem isso, `POST /api/papeis` escrevia no schema `plat` de PRODUÇÃO quando a
suíte rodava numa base isolada (erro "permission denied for schema plat"; onde a role tivesse acesso, teria
escrito no schema errado em silêncio) — e `docs/gerar_privilegios.py` passou a usar esse mesmo cursor.

Testes: `tests/unit/test_exportacao_unidade.py` (14, sem banco: CSV brasileiro, erro do banco saneado,
catálogo de formatos e a prova por `tracemalloc` de que 40 MiB sobem em 5 partes com pico abaixo de 3 partes)
+ `tests/api/exportacao/` (portão cláusula a cláusula sobre uma camada de 100 mil feições, mais a prova
cruzada em três níveis de que a exportação de um inquilino não traz linha de outro) + `tests/e2e/
test_exportar.py` (botão Exportar com captura). Medidas em `tests/medidas/L0-04-h-exportar.json`.

## turno 3, setembro de 2026 (item L6-02-c-wfs-ogcapi: conector WFS 2.0 e OGC API - Features)

Primeiro conector que LÊ dado de serviço de terceiro (ADR 0018). WFS 2.0 (GetCapabilities, DescribeFeatureType,
GetFeature com `COUNT`/`STARTINDEX`/`BBOX`, `RESULTTYPE=hits`, saída GeoJSON e GML 3.2) e OGC API - Features
(`/collections`, `/queryables`, `/items` com `limit`, `bbox`, `datetime` e link `rel=next`), nos dois modos:

- **referenciado** — `GET /api/conexoes/{id}/colecoes`, `.../colecoes/{c}/campos` e `.../colecoes/{c}/feicoes`,
  ao vivo, com cache de 30 s no processo (`app/conexao/cache.py`); editar ou apagar a conexão esquece o cache.
- **copiado** — job `conexao.copiar_vetor` (`POST /api/jobs`), que traz a coleção para uma tabela PostGIS do
  inquilino com item `camada_vetorial`, procedência e as mesmas colunas obrigatórias/RLS da ingestão de arquivo.

Regra dura do desenho: **todo I/O de rede passa por `app.conexao.seguranca.buscar_seguro`** (item L6-02-a) —
os drivers `WFS:`/`OAPIF:` do GDAL foram recusados de propósito, porque fariam a requisição fora da defesa
contra requisição forjada pelo servidor. O `ogr2ogr` só entra depois, sobre arquivo LOCAL, e roda com
`GDAL_HTTP_PROXY` apontando para porta fechada, de modo que nenhuma requisição sua possa sair da máquina.

Medido (`tests/medidas/L6-02-c-wfs-ogcapi.json`): 50 mil feições copiadas de um WFS 2.0, com o tempo de
download e o de carga separados; paginação conferida contra o `numberMatched` declarado; tipos de atributo
(`xsd:int`, `xsd:double`, `xsd:boolean`, `xsd:date`) preservados como o serviço os declarou; geometria
reprojetada de EPSG:31983 para 4326 com o CRS nativo gravado na ficha.

Refutação do adversário provada: um WFS que declara 5.000.000 de feições e ignora `COUNT`/`STARTINDEX` faz a
cópia parar no limite declarado, gravar o aviso na procedência da camada e devolver o worker à fila — três
travas independentes (limite, página maior do que a pedida, página repetida) além dos tetos de bytes e de
páginas.

Novo em `app/conexao/seguranca.py`: `PLAT_TESTE_CONEXAO_ALVOS`, par `host:porta` exato aceito só fora de
produção, para que a suíte fale com um WFS e um OGC API DE VERDADE subidos no loopback
(`tests/api/conexao/servidor_ogc.py`) em vez de depender do serviço de um órgão estar de pé.

## turno 3, setembro de 2026 (item L0-09-a-procedencia: bloco de procedência em todo item de dado)

Todo item que carrega dado passa a ter um bloco de procedência com o vocabulário que a casa já usa no registro
do acervo (`acervo.fonte`, 376 fontes) e no catálogo de camadas do motor logístico: fonte, endereço, licença,
data do dado, data de acesso, gerador, sha256, comando de reexecução, método, confiança, limites, frescor,
próxima verificação e responsável. Cada campo pode declarar a `origem`: `declarado` (alguém afirmou) ou
`medido` (a máquina calculou). O vocabulário campo a campo está em `docs/PROCEDENCIA.md`.

A pontuação é a régua da `acervo.v_completude`, sem peso novo: `round(campos / campos_possiveis * 10, 1)` sobre
os mesmos 10 campos. Item sem bloco tem pontuação nula, nunca `0,0` — ausência de registro não é medida de zero.
A conta existe em Python (`app/catalogo/procedencia.py`) e em SQL (`plat.procedencia_pontuacao`), e um teste
compara as duas em 7 blocos, porque a lista do catálogo não trafega `dados` (jsonb de 58 KB em média) e lê o
selo direto do banco.

Medido (`tests/medidas/L0-09-a-procedencia.json`): camada importada por arquivo nasce com os **4 campos que a
máquina mede** — sha256 do arquivo lido de volta, data de acesso, gerador e método — sem ninguém digitar;
licença e endereço ficam nulos de propósito, porque deduzi-los do nome do arquivo seria a procedência errada
que a regra D17 proíbe.

Onde aparece: ficha e lista (`procedencia` no objeto item), busca (`licenca:CC`, `licenca:nenhuma`,
`procedencia:[5 TO 10]`), filtro lateral (`?licenca=`, `?procedencia_min=`, faceta de licença) e exportação da
lista (colunas `licenca`, `procedencia_pontuacao`, `procedencia_campos`, `procedencia_sha256`,
`procedencia_gerador` no CSV; bloco inteiro no JSON).

Refutação do adversário provada em teste: o mesmo arquivo importado duas vezes dá o mesmo sha256 (e igual ao
`sha256sum` do arquivo de origem); um byte a mais dá hash diferente; licença preenchida com texto vazio vira
`null`, nunca string vazia — na criação e na edição.

Fronteira honesta: a exportação do inquilino inteiro em GeoPackage (`L0-06-d-exportar-inquilino`) ainda não
existe, então a cláusula "exportação leva a procedência" está cumprida na exportação que existe hoje, a da
lista do catálogo. A tela do item mostra o bloco e a pontuação, mas ainda não os EDITA (isso é o
`L0-09-b-editor-iso-mgb`); hoje a edição é pelo formulário de `dados` do próprio item.

## turno 3, setembro de 2026 (item L2-04-a-leitor-rls-martin: quem serve o tile não sabe o que é inquilino)

O servidor de tiles vetoriais fala direto com o PostGIS e não tem noção de sessão, privilégio ou inquilino.
Passa a existir um **papel de banco só de leitura** — LOGIN, sem BYPASSRLS, sem ser dono de nada, com SELECT
nas tabelas de camada e EXECUTE nas funções de tile — e uma função `plat.contexto_por_token`, que valida o
token de serviço, confere escopo `camada:ler` e restrição de Referer/IP, grava o uso em `plat.log_acesso` e
põe o inquilino na transação. Cada camada ganha a sua função de tile `d_<slug>.t_<16 hex>(z, x, y,
query_params)`, criada junto com a tabela; a primeira instrução dela é o contexto por token. Contrato no ADR
0020; o papel, a senha e a linha do `pg_hba.conf` saem de `db/leitor_instalar.sh`, chamado pelo `install.sh`.

A política de RLS do papel de leitura **não olha a GUC `plat.tenant_id` crua**: qualquer papel conectado
escreve nela, e o papel de leitura é o mesmo para todos os inquilinos. Ela olha `plat.tenant_leitor()`, que
exige uma prova (sha256 de um segredo que nenhum papel comum lê, mais o inquilino e o processo) emitida só
por `contexto_por_token`. Medido em `tests/medidas/L2-04-a-leitor-rls-martin.json`: `SET plat.tenant_id` feito
pelo próprio leitor devolve **0 linhas**; **6 chamadas cruzadas** às funções de tile com o token do outro
inquilino devolvem **0 tiles com dado**; token revogado deixa de valer em **0,002 s**; **1 linha de log por
chamada** de contexto aceita; segunda execução do instalador = **0 mudanças**.

⛔ Fronteira honesta: a linha de log de uma RECUSA é escrita e desfeita com a transação abortada (o PostgreSQL
não tem transação autônoma) — medida `linhas_log_de_recusa_persistidas: 0`. O rastro da recusa fica no log do
servidor (a exceção é nomeada) e no log de acesso da API. E o Martin em si não está instalado nem configurado
por este item: o que se entrega é o contrato de banco que ele consome.

## turno 3, setembro de 2026 (item L2-01-a-documento-mapa: o mapa é um documento com esquema, não um punhado de URLs)

O tipo `mapa` deixa de ter `corpo` livre e passa a carregar um **JSON Schema publicado**
(`docs/esquemas/mapa-v1.json`, gerado de `plat.tipo_item`): mapa-base, lista ordenada de camadas com
visibilidade, opacidade, faixa de escala, grupo (até 3 níveis), estilo, popup, filtro CQL2-JSON, rótulos,
campo de tempo e intervalo de atualização; extensão inicial, rotação, CRS de exibição fixo em 3857 e
favoritos. Cada camada aponta o item do catálogo por **uuid** (`ref`), nunca por URL — o oposto do Web Map
JSON da Esri, onde a URL do portal fica congelada dentro de cada mapa salvo. Rotas novas: `POST/GET/PUT
/api/mapas`, `GET /api/mapas` e `GET /api/mapas/{id}/completo`, que devolve o documento com as camadas já
resolvidas (título, tipo, campos, estilo, popup) em UMA chamada. Contrato no ADR 0022; de-para chave a chave
contra a Web Map Specification em `docs/PARIDADE.md`.

Medido em `tests/medidas/L2-01-a.json`: `/completo` de um mapa com **10 camadas** responde com p95 de
**20,7 ms** (mediana 12,2 ms) em **50 chamadas**, contra o teto de 150 ms do portão. Camada de outro inquilino
citada no documento = **404** (o mesmo 404 de uuid inexistente, sem revelar que existe); apagar camada usada
por mapa = **409** com a lista dos mapas dependentes; 500 camadas, 5 níveis de grupo, ciclo de grupo e
extensão fora do mundo = **422**, nenhum 200 e nenhum 500. Na tela `/mapa?id=<uuid>` a lista de camadas
reordena arrastando (e por teclado, Alt+seta): e2e grava a ordem, recarrega a página e confere que voltou a
mesma, com captura em `tests/e2e/capturas/L2-01-a-documento-mapa_painel_camadas.png`.

⛔ Fronteira honesta: `/completo` devolve o CONTRATO da URL de tiles com `pronto: false` e o motivo — não há
servidor de tiles vetoriais nem raster instalado nesta máquina (itens L2-01-b e L1-02) —, e `dominios` sai
vazio com o motivo escrito, porque a camada ainda não guarda vocabulário de domínio (L0-04-c, parcial). A tela
lista e reordena as camadas do documento; não as desenha no canvas, pelo mesmo motivo, e diz isso em cada
linha. ⛔ Quebra declarada: documento com `corpo.camadas` como lista de uuid soltos passa a ser 422.

## turno 3, setembro de 2026 (item L2-04-a-leitor-rls-martin: quem serve o tile não sabe o que é inquilino)

O servidor de tiles vetoriais fala direto com o PostGIS e não tem noção de sessão, privilégio ou inquilino.
Passa a existir um **papel de banco só de leitura** — LOGIN, sem BYPASSRLS, sem ser dono de nada, com SELECT
nas tabelas de camada e EXECUTE nas funções de tile — e uma função `plat.contexto_por_token`, que valida o
token de serviço, confere escopo `camada:ler` e restrição de Referer/IP, grava o uso em `plat.log_acesso` e
põe o inquilino na transação. Cada camada ganha a sua função de tile `d_<slug>.t_<16 hex>(z, x, y,
query_params)`, criada junto com a tabela; a primeira instrução dela é o contexto por token. Contrato no ADR
0020; o papel, a senha e a linha do `pg_hba.conf` saem de `db/leitor_instalar.sh`, chamado pelo `install.sh`.

A política de RLS do papel de leitura **não olha a GUC `plat.tenant_id` crua**: qualquer papel conectado
escreve nela, e o papel de leitura é o mesmo para todos os inquilinos. Ela olha `plat.tenant_leitor()`, que
exige uma prova (sha256 de um segredo que nenhum papel comum lê, mais o inquilino e o processo) emitida só
por `contexto_por_token`. Medido em `tests/medidas/L2-04-a-leitor-rls-martin.json`: `SET plat.tenant_id` feito
pelo próprio leitor devolve **0 linhas**; **6 chamadas cruzadas** às funções de tile com o token do outro
inquilino devolvem **0 tiles com dado**; token revogado deixa de valer em **0,002 s**; **1 linha de log por
chamada** de contexto aceita; segunda execução do instalador = **0 mudanças**.

⛔ Fronteira honesta: a linha de log de uma RECUSA é escrita e desfeita com a transação abortada (o PostgreSQL
não tem transação autônoma) — medida `linhas_log_de_recusa_persistidas: 0`. O rastro da recusa fica no log do
servidor (a exceção é nomeada) e no log de acesso da API. E o Martin em si não está instalado nem configurado
por este item: o que se entrega é o contrato de banco que ele consome.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: o esquema da rede de utilidades é dado)

Primeiro item da linha L4. O esquema de uma rede de utilidades — redes de domínio, tiers, grupos e tipos de
ativo, categorias de rede, atributos e configurações de terminal — passa a ser um **pacote de ativos**: um
documento JSON versionado, importado para dez tabelas `plat.rede_*` do inquilino (`POST
/api/rede/{rede_id}/pacote`) e exportado de volta a partir delas (`GET .../pacote`). O contrato está no ADR
0019; o mapeamento coluna a coluna, em `docs/PACOTE_REDE.md`, gerado do próprio dado.

A exportação é **reconstruída das tabelas**, nunca o arquivo recebido — dos 96.042 bytes importados do pacote
`eletrica-br`, saem os mesmos 96.042 bytes, e um teste altera uma linha no banco para mostrar que a exportação
muda junto (`test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido`). Pacote recusado sai com a lista
inteira de problemas, cada um com o caminho (`tipos[41].grupo`) e a **linha do arquivo enviado**.

Dois pacotes vêm com a instalação: `eletrica-br` (2 domínios, 4 tiers, 14 grupos, 24 tipos, 214 atributos, 24
regras) cobrindo as 13 camadas de rede da BDGD do Módulo 10 do PRODIST, e `agua-epanet` (1 domínio, 2 tiers, 6
grupos, 14 tipos, 41 atributos, 16 regras) no vocabulário do EPANET 2.2.

⛔ Fronteira honesta declarada no próprio dado: dos 214 atributos do pacote elétrico, **154 têm a coluna de
origem conferida contra uma extração real** (11 camadas) e **60 são declarados do documento da fonte, sem
conferência** (`SUB`, `UNSEMT`, `UNCRMT`, `UNREMT`, `UGMT_tab`); o pacote de água é inteiramente declarado.
Nenhum atributo com `conferida = false` deve decidir carga de dado sem antes conferir o dicionário da entrega.
Topologia, traçado e subrede não existem ainda — este item entrega só o catálogo do esquema.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: conserto pós-adversário, refutado -> corrigido)

O adversário independente do turno 3 (`handoffs/T3/ataque-L4-portal-ADVERSARIO.md` §1) refutou o item com
seis achados; todos corrigidos, com a mesma bateria de teste virando regressão permanente
(`tests/api/test_rede_pacote_conserto_a1_a4.py`, `tests/api/test_fk_composta_por_inquilino.py`).

**A1** (a FK não era filtrada pela RLS): as 10 tabelas `plat.rede_*` ganharam FK **composta** `(tenant_id,
id)` (`db/migracoes/20260906T1815_rede_fk_por_inquilino.sql`) — um inquilino não pendura mais linha própria
em `tipo`/`domínio` de outro pelo uuid alheio. A trava (`test_fk_composta_por_inquilino.py`) varre
`pg_constraint` do schema inteiro, não só a rede; achou 55 FKs do mesmo padrão em outras tabelas do produto,
documentadas como fora de escopo (não corrigidas aqui).

**A2/A2b** (seção repetida entrava em silêncio e a linha apontada era a errada): `localizador.py` foi
reescrito para construir um mapa de offsets numa única passada — a última ocorrência de uma chave
sobrescreve a anterior, como `json.loads`, então a linha apontada é sempre a da seção que a validação de
fato usou; `pacote._chave_repetida` recusa com 422 qualquer chave repetida, em qualquer profundidade.

**A3** (NUL em `texto`/`jsonb` derrubava a importação com 500): `pacote._procurar_nul` recusa com 422 antes
de a string chegar ao psycopg2.

**A4** (a rota travava o laço de eventos e a localização de linha era quadrática): `POST
.../{rede_id}/pacote` só lê o corpo no laço de eventos; validação e gravação vão para
`run_in_threadpool`. O mesmo mapa de offsets do conserto A2b tornou a localização de linha linear (medido:
pacote de 4 mil erros, 14,1 s → 1,2 s; pior `/saude` concorrente, 13,6 s → 0,19 s —
`tests/medidas/L4-01-a.json`). Tornar a concorrência real expôs um `DeadlockDetected` não tratado em duas
importações simultâneas na MESMA rede; corrigido com `SELECT ... FOR UPDATE` na linha da rede
(`_travar_rede`), que serializa a substituição do catálogo sem 500.

## turno 3, setembro de 2026 (item L2-10-a-dominios-subtipos: domínios de atributo e subtipos por camada)

Domínio de atributo como objeto do inquilino (`plat.dominio`: codificado com lista de códigos, ou intervalo
com mínimo e máximo), ligação campo -> domínio por camada e por subtipo (`plat.dominio_campo`), subtipo como
campo inteiro designado da camada (`plat.camada_subtipo`). **ADR 0021**; migrações
`20260906T1548_dominios_subtipos.sql` e `20260906T1620_dominios_gatilho_gerado.sql`.

- **A regra vale no banco.** Um INSERT direto na tabela da camada como `plat_app`, sem passar pela API, é
  recusado com `campo "uf": o valor 'ZZ' não pertence ao domínio "UF"` e com o nome do campo em `COLUMN` —
  a API repassa isso em `detalhe.campo`. Domínio de intervalo recusa abaixo do mínimo e acima do máximo
  (`campo "altura": o valor -0.1 está fora do intervalo 0.0 a 10.0`). Medido em
  `tests/medidas/L2-10-a-dominios-subtipos.json`.
- **Subtipo troca o domínio do mesmo campo.** Com dois subtipos ligados ao campo `situacao`, `terra` passa no
  subtipo 2 e é recusado no 1; sem subtipo vale o domínio padrão da camada; subtipo fora da lista é recusado.
- **Remover valor em uso = 409 com a contagem.** Quem conta é `plat.dominio_uso_contar`, a mesma função que
  responde `GET /api/dominios/{id}/uso`: quatro feições usando `C1` dão
  `{"erro": "valor_em_uso", "detalhe": {"codigo": "C1", "usos": 4}}`. Valor não usado sai sem drama.
- **Custo do gatilho, medido e corrigido.** A primeira versão, genérica, lia a linha com `to_jsonb(NEW)` e
  custou **1,80x** (10 mil inserções: 1,72 s sem gatilho, 3,11 s com) — acima do teto de 1,5x do item. Um
  gatilho que só faz `to_jsonb(NEW)` já custa cerca de 129 us por linha, porque converte a linha inteira, com
  geometria. O gatilho passou a ser GERADO por camada (`plat.dominio_v_<item>`, com `NEW.uf` no código), e
  três gatilhos AFTER (em `plat.dominio_campo`, `plat.camada_subtipo` e `plat.dominio`) regeneram a função
  sozinhos — nenhuma rota instala gatilho, e quem mexe por `psql` regenera do mesmo jeito.
- **FeatureServer com domains e types.** `GET /rest/services/{item_id}/FeatureServer/0` publica
  `fields[].domain` (codedValue e range) e `types[]` com `domains` por subtipo e `templates` com os valores
  padrão; conferido contra o que `GET /api/camadas/{id}/dominios` devolve do banco. É só o METADADO: `/query`
  e `/applyEdits` são da linha L2-08.
- **Tela `/camadas/{id}/dominios`.** Campo com domínio codificado vira lista de escolha que mostra a descrição
  e grava o código; trocar o subtipo refaz os campos dependentes e aplica os padrões; a tabela de feições usa
  a mesma tradução (`web/js/dominios/valores.js`, a função única do formulário, da tabela e — quando o painel
  de camada existir — do popup).
- **CSV de ida e volta** (`GET /api/dominios.csv`, `POST /api/dominios/csv`) e **importação do `fields`/`types`
  de um FeatureServer/FGDB** (`POST /api/dominios/importar`), que reaproveita domínio de mesmo nome em vez de
  duplicar.

Testes: `tests/api/test_dominios_subtipos.py` (inclui a refutação exigida: domínio de outro inquilino = 404,
50 mil códigos = 422, código duplicado recusado na API e no banco, trocar o tipo de campo com domínio ligado
= 409) e `tests/e2e/test_dominios.py` (playwright, com capturas).
## turno 3, setembro de 2026 (item L0-09-a-procedencia: bloco de procedência em todo item de dado)

Todo item que carrega dado passa a ter um bloco de procedência com o vocabulário que a casa já usa no registro
do acervo (`acervo.fonte`, 376 fontes) e no catálogo de camadas do motor logístico: fonte, endereço, licença,
data do dado, data de acesso, gerador, sha256, comando de reexecução, método, confiança, limites, frescor,
próxima verificação e responsável. Cada campo pode declarar a `origem`: `declarado` (alguém afirmou) ou
`medido` (a máquina calculou). O vocabulário campo a campo está em `docs/PROCEDENCIA.md`.

A pontuação é a régua da `acervo.v_completude`, sem peso novo: `round(campos / campos_possiveis * 10, 1)` sobre
os mesmos 10 campos. Item sem bloco tem pontuação nula, nunca `0,0` — ausência de registro não é medida de zero.
A conta existe em Python (`app/catalogo/procedencia.py`) e em SQL (`plat.procedencia_pontuacao`), e um teste
compara as duas em 7 blocos, porque a lista do catálogo não trafega `dados` (jsonb de 58 KB em média) e lê o
selo direto do banco.

Medido (`tests/medidas/L0-09-a-procedencia.json`): camada importada por arquivo nasce com os **4 campos que a
máquina mede** — sha256 do arquivo lido de volta, data de acesso, gerador e método — sem ninguém digitar;
licença e endereço ficam nulos de propósito, porque deduzi-los do nome do arquivo seria a procedência errada
que a regra D17 proíbe.

Onde aparece: ficha e lista (`procedencia` no objeto item), busca (`licenca:CC`, `licenca:nenhuma`,
`procedencia:[5 TO 10]`), filtro lateral (`?licenca=`, `?procedencia_min=`, faceta de licença) e exportação da
lista (colunas `licenca`, `procedencia_pontuacao`, `procedencia_campos`, `procedencia_sha256`,
`procedencia_gerador` no CSV; bloco inteiro no JSON).

Refutação do adversário provada em teste: o mesmo arquivo importado duas vezes dá o mesmo sha256 (e igual ao
`sha256sum` do arquivo de origem); um byte a mais dá hash diferente; licença preenchida com texto vazio vira
`null`, nunca string vazia — na criação e na edição.

Fronteira honesta: a exportação do inquilino inteiro em GeoPackage (`L0-06-d-exportar-inquilino`) ainda não
existe, então a cláusula "exportação leva a procedência" está cumprida na exportação que existe hoje, a da
lista do catálogo. A tela do item mostra o bloco e a pontuação, mas ainda não os EDITA (isso é o
`L0-09-b-editor-iso-mgb`); hoje a edição é pelo formulário de `dados` do próprio item.

## turno 3, setembro de 2026 (item L6-02-c-wfs-ogcapi: conector WFS 2.0 e OGC API - Features)

Primeiro conector que LÊ dado de serviço de terceiro (ADR 0018). WFS 2.0 (GetCapabilities, DescribeFeatureType,
GetFeature com `COUNT`/`STARTINDEX`/`BBOX`, `RESULTTYPE=hits`, saída GeoJSON e GML 3.2) e OGC API - Features
(`/collections`, `/queryables`, `/items` com `limit`, `bbox`, `datetime` e link `rel=next`), nos dois modos:

- **referenciado** — `GET /api/conexoes/{id}/colecoes`, `.../colecoes/{c}/campos` e `.../colecoes/{c}/feicoes`,
  ao vivo, com cache de 30 s no processo (`app/conexao/cache.py`); editar ou apagar a conexão esquece o cache.
- **copiado** — job `conexao.copiar_vetor` (`POST /api/jobs`), que traz a coleção para uma tabela PostGIS do
  inquilino com item `camada_vetorial`, procedência e as mesmas colunas obrigatórias/RLS da ingestão de arquivo.

Regra dura do desenho: **todo I/O de rede passa por `app.conexao.seguranca.buscar_seguro`** (item L6-02-a) —
os drivers `WFS:`/`OAPIF:` do GDAL foram recusados de propósito, porque fariam a requisição fora da defesa
contra requisição forjada pelo servidor. O `ogr2ogr` só entra depois, sobre arquivo LOCAL, e roda com
`GDAL_HTTP_PROXY` apontando para porta fechada, de modo que nenhuma requisição sua possa sair da máquina.

Medido (`tests/medidas/L6-02-c-wfs-ogcapi.json`): 50 mil feições copiadas de um WFS 2.0, com o tempo de
download e o de carga separados; paginação conferida contra o `numberMatched` declarado; tipos de atributo
(`xsd:int`, `xsd:double`, `xsd:boolean`, `xsd:date`) preservados como o serviço os declarou; geometria
reprojetada de EPSG:31983 para 4326 com o CRS nativo gravado na ficha.

Refutação do adversário provada: um WFS que declara 5.000.000 de feições e ignora `COUNT`/`STARTINDEX` faz a
cópia parar no limite declarado, gravar o aviso na procedência da camada e devolver o worker à fila — três
travas independentes (limite, página maior do que a pedida, página repetida) além dos tetos de bytes e de
páginas.

Novo em `app/conexao/seguranca.py`: `PLAT_TESTE_CONEXAO_ALVOS`, par `host:porta` exato aceito só fora de
produção, para que a suíte fale com um WFS e um OGC API DE VERDADE subidos no loopback
(`tests/api/conexao/servidor_ogc.py`) em vez de depender do serviço de um órgão estar de pé.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: conserto pós-adversário, refutado -> corrigido)

O adversário independente do turno 3 (`handoffs/T3/ataque-L4-portal-ADVERSARIO.md` §1) refutou o item com
seis achados; todos corrigidos, com a mesma bateria de teste virando regressão permanente
(`tests/api/test_rede_pacote_conserto_a1_a4.py`, `tests/api/test_fk_composta_por_inquilino.py`).

**A1** (a FK não era filtrada pela RLS): as 10 tabelas `plat.rede_*` ganharam FK **composta** `(tenant_id,
id)` (`db/migracoes/20260906T1815_rede_fk_por_inquilino.sql`) — um inquilino não pendura mais linha própria
em `tipo`/`domínio` de outro pelo uuid alheio. A trava (`test_fk_composta_por_inquilino.py`) varre
`pg_constraint` do schema inteiro, não só a rede; achou 55 FKs do mesmo padrão em outras tabelas do produto,
documentadas como fora de escopo (não corrigidas aqui).

**A2/A2b** (seção repetida entrava em silêncio e a linha apontada era a errada): `localizador.py` foi
reescrito para construir um mapa de offsets numa única passada — a última ocorrência de uma chave
sobrescreve a anterior, como `json.loads`, então a linha apontada é sempre a da seção que a validação de
fato usou; `pacote._chave_repetida` recusa com 422 qualquer chave repetida, em qualquer profundidade.

**A3** (NUL em `texto`/`jsonb` derrubava a importação com 500): `pacote._procurar_nul` recusa com 422 antes
de a string chegar ao psycopg2.

**A4** (a rota travava o laço de eventos e a localização de linha era quadrática): `POST
.../{rede_id}/pacote` só lê o corpo no laço de eventos; validação e gravação vão para
`run_in_threadpool`. O mesmo mapa de offsets do conserto A2b tornou a localização de linha linear (medido:
pacote de 4 mil erros, 14,1 s → 1,2 s; pior `/saude` concorrente, 13,6 s → 0,19 s —
`tests/medidas/L4-01-a.json`). Tornar a concorrência real expôs um `DeadlockDetected` não tratado em duas
importações simultâneas na MESMA rede; corrigido com `SELECT ... FOR UPDATE` na linha da rede
(`_travar_rede`), que serializa a substituição do catálogo sem 500.


## turno 3, setembro de 2026 (item L0-04-a-upload-arquivo: upload retomável pelo navegador)

Upload de arquivo em partes de 16 MiB pelo navegador, retomável (`POST /api/uploads` reserva cota do inquilino
e abre o multipart no Garage; `PUT /api/uploads/{id}/partes/{n}` aceita partes fora de ordem e reenviadas — o
`addPart` da Esri; `POST /api/uploads/{id}/concluir` fecha o multipart, confere sha256/tamanho/tipo×conteúdo e
registra o item `arquivo` no catálogo; `DELETE` aborta). Vocabulário de 14 tipos declarados (shapefile.zip,
gpkg, geojson, kml, kmz, csv, gpx, xlsx, dxf, dwg, gdb.zip, parquet, fgb, gml, zip) provados pelo CONTEÚDO real,
nunca só a extensão (`app/uploads/tipos.py`); os zip-baseados usam `app.ingestao.formatos.conferir_zip`
(arquivo pequeno) ou um parser do formato PKZIP por leitura em intervalo (`app/uploads/zip_remoto.py`, arquivo
grande — nunca baixa o objeto inteiro para RAM, motivo é a máquina ter pouca RAM livre e o item aceitar até
2 GiB por arquivo). Periódico `uploads.expirar` (`*/30 * * * *`) apaga upload sem atividade há 24 h em
qualquer inquilino (SECURITY DEFINER cruzando tenants, mesmo mecanismo de `plat.sessoes_expurgar`). Tela
`/uploads` (dropzone, barra de progresso nativa, identidade "instrumento").

Decisão registrada: a cota reservada NÃO usa `tenant.uso_reservado_bytes` (a hipótese do ADR 0005) — aquela
coluna já foi tomada por outra trilha para "armazenamento de tabela carregada", com significado explicitamente
"independente da cota do bucket Garage". A reserva deste item é a soma de `plat.upload.bytes_declarado` em
estado `iniciado` do inquilino (`plat.upload_reservado_bytes`), sob o mesmo `SELECT ... FOR UPDATE` da linha
do tenant.

Achado de processo (não de produto): a migração original (`044_uploads.sql`) colidiu com uma tabela IDÊNTICA
já aplicada ao banco compartilhado por outra sessão desta árvore, cujo código Python nunca apareceu em lugar
nenhum encontrado — registrado no handoff para o coordenador verificar se há uma segunda linha de trabalho no
mesmo item. Renomeada para `046_upload_retomavel.sql`, escrita para ser segura contra o schema já existir.

Testes: `tests/unit/test_uploads_tipos.py` (32, sem banco) + `tests/api/uploads/test_uploads.py` (18, API real:
100 MB em 7 partes com a 4ª reenviada e sha256 igual; `.gpkg` com zip dentro recusado com a mensagem exata;
2,1 GiB e cota insuficiente recusados com 413 antes de qualquer byte; zip-bomba de 1.500 entradas e caminho
`../` recusados; duas conclusões concorrentes — uma vence, a outra vê `ja_concluido`; duas sessões enviando
partes diferentes ao mesmo tempo — as duas terminam OK; upload esquecido expira em 24 h pelo periódico real)
+ `tests/e2e/test_uploads.py` (playwright contra a URL interna, barra de progresso, 0 erro de console).
`taxa_upload_mb_s` = 92,1 MB/s (local, `tests/medidas/L0-04-a-upload-arquivo.json`).

## turno 3, setembro de 2026 (item L0-07-b-papeis-privilegios: vocabulário fino, conferência Esri e gate de rebaixamento)

O grosso de privilégios/papéis já existia do L0-02 (vocabulário fechado, papéis personalizados, tela `/admin/papeis`,
`plat.tem`/`plat.privilegios_de`); este item fechou o que faltava do portão. `docs/gerar_privilegios.py` lê
`plat.privilegio`/`plat.perfil_privilegio` AO VIVO no banco (nunca `app/auth/privilegios.py`) e escreve
`docs/PRIVILEGIOS.md` (47 privilégios, 12 grupos, 20 administrativos), com `tests/api/test_privilegios_doc.py`
provando que o comitado bate com o banco agora. `tests/api/test_privilegios_matriz.py` chama toda rota do OpenAPI
vivo cujo `x-privilegio` é um nome puro do vocabulário (sozinho ou em composição `a|b`) com um usuário que
provadamente não o tem, e exige `403` em todas — dois clientes só bastam (um só com `tokens.gerar`, outro só com
`membros.ver`, a interseção perfil×papel do ADR 0002 faz o resto); a exceção nomeada (`PUT
/api/itens/{id}/compartilhamento`, que checa posse do item ANTES do privilégio de compartilhar) ganhou teste à
parte provando o gate real com o dono do item.

Achado do adversário: rebaixar o perfil de um usuário que possui itens do catálogo não era recusado —
`_editar` (`app/auth/rotas_usuarios.py`) só checava grupos (`409 possui_grupos`); a regra da Esri (E12-members)
é "não possui conteúdo NEM grupos". Corrigido com o mesmo padrão (`409 possui_itens`, listando os itens);
`tests/api/test_usuarios.py::test_rebaixar_perfil_com_itens_e_recusado` prova a recusa, que promover não
esbarra na regra, e que a purga do item destrava o rebaixamento.

Paridade linha a linha contra a lista de privilégios da Esri 11.4 (E12-priv, `laco/handoffs/T1/21_esri.md` §1.3):
43 gerais + 33 administrativos = 76 privilégios Esri, **35 feito · 11 parcial · 30 fora** — cada `fora` é uma
decisão de escopo já nomeada em outro item (notebook, app OAuth, pipeline, versionamento de dado, colaboração
entre organizações, licença/assento, vídeo, grafo de conhecimento, relatório de uso), nunca uma lacuna descoberta
agora. Tabela completa em `docs/PARIDADE.md` seção "Privilégios e papéis personalizados".

e2e novo (`tests/e2e/test_papeis.py::test_papel_curador_categoriza_mas_nao_publica`, captura
`L0-02-tenant-auth_papel_curador.png`): papel "Curador" (`conteudo.criar` + `conteudo.categorias`, este último
administrativo — só cabe em perfil `admin`) criado pela tela, atribuído a um usuário novo; ele reescreve a árvore
de categorias e cria conteúdo comum, mas uma tentativa de criar/publicar camada vetorial nega com `403
sem_privilegio` (`exigido: conteudo.publicar_camada`).

Refutação própria (papel esri+backend+frontend+testador+adversário, sem subagentes — item pequeno o bastante
para uma sessão): papel administrativo atribuído a perfil abaixo do teto → `422 papel_incompativel` (já provado
em `test_so_admin_cria_altera_e_apaga_admin`); ninguém concede privilégio que não tem → `403
privilegio_proprio_insuficiente` (`test_privilegios_e_papeis`); apagar papel em uso → `409 papel_em_uso`; as
~40 rotas de privilégio puro do OpenAPI vivo, uma a uma, sem o privilégio declarado → `403` em todas
(`test_privilegios_matriz.py`). Nenhuma reprovação nova encontrada além da já corrigida (`possui_itens`).

Pendente, registrado no handoff: teste automatizado do downgrade de tipo Esri "Creator → Viewer com conteúdo"
não tem equivalente 1:1 (nossa spec não tem tipo separado de perfil — decisão D5/D16 já registrada); relatório
de uso administrativo (`Content: Create and manage administrative reports`) e alguns privilégios de
colaboração/servidor seguem `fora` por decisão de escopo, não por falta de tempo.


## turno 3, setembro de 2026 (item L2-11-b-geocodificador-brasil: geocodificador próprio sobre CNEFE 2022)

Geocodificador PRÓPRIO em PostgreSQL/PostGIS (sem Nominatim/Pelias, decisão D28 sobre disco), base = CNEFE
2022 do IBGE. `db/migracoes/045_geocodificador.sql` (`plat.geo_uf`, `plat.geo_municipio`, `plat.geo_endereco`,
`plat.geo_instalacao`) + `scripts/geocodificador_instalar_uf.py` (baixa e mede o tamanho por `HEAD` antes,
carrega por `COPY` em lotes) + `app/geocodificador/` (normalização, motor de busca/reverso/sugestão, API
própria e `GeocodeServer` compatível Esri). Demo instalada: Roraima (menor arquivo de UF do CNEFE, 4,52 MB
comprimidos, 260.515 pontos, 15 municípios, carga em 10,4 s).

Medido (`tests/medidas/L2-11-b-geocodificador-brasil.json`, 50 endereços reais + 50 pontos reais do CNEFE):
erro mediano de geocodificação **0,0 m** (portão ≤ 30 m), acerto de número/face **98,0%** (portão ≥ 90%),
reverso acerta o logradouro em **100%** (portão ≥ 90%), sugestão p95 **33,1 ms** (portão ≤ 100 ms). Achado
de carga corrigido ANTES do commit: `COD_UNICO_ENDERECO` do CNEFE não é chave única (260.516 linhas, só
249.268 ids distintos em Roraima) — a tabela usa `id bigserial` como chave e guarda o código do IBGE em
coluna indexada não-única. Ambiguidade entre municípios (a refutação pede "Rua A" em São Paulo, o maior
arquivo do CNEFE, fora do teto de disco D28) foi provada com o mesmo fenômeno em Roraima: `RUA A` se repete
em 8 dos 15 municípios, medido. Consistência CEP × município/UF recusa com `422` quando os dois sinais
apontam lugares diferentes. QGIS como locator real fica como PENDÊNCIA nomeada (sem QGIS/ambiente gráfico
nesta máquina) — o protocolo foi provado por chamada HTTP direta simulando o que o QGIS manda. Ver ADR 0013
e `docs/PARIDADE.md` seção "Geocodificador".

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: conserto das três refutações do adversário)

O ataque adversarial (`laco/handoffs/T3/L2-10-c-ADVERSARIO.md`) refutou o item em três cláusulas. As três
foram consertadas no código e no documento; os 38 testes que o adversário deixou como `xfail(strict=True)`
passam sem que nenhum tenha sido apagado ou afrouxado (`venv/bin/pytest tests/unit/test_expressao_*.py`
= 1.652 casos, 0 falha, 0 xfail).

1. **Equivalência Python × JavaScript.** As 26 divergências que ele mediu fora dos 309 vetores vinham todas
do mesmo lugar: operação entregue ao operador ou à biblioteca da língua. A semântica passou a ser do
CONTRATO, escrita à mão nos dois lados e publicada em `docs/EXPRESSAO.md` §3.1 — resto (`%`) com o sinal do
DIVIDENDO (`math.fmod`, como o JavaScript/C/SQL); texto medido, cortado, comparado e casado em PONTO DE
CÓDIGO, com par substituto contando como um; `Numero` só com algarismo ASCII; data arredondada sempre para
baixo. Os 26 casos viraram vetor compartilhado em `tests/expressoes/vetores_convergencia.json` (30 vetores,
`vetores_de_convergencia_pos_adversario`), rodados junto dos 309 pelo teste de equivalência.

2. **Exceção crua.** `TextoNumero($x,15)` com 1e13 levantava `decimal.InvalidOperation` (contexto padrão de
28 dígitos). `_decimal_fixo` passou a usar `decimal.localcontext` com 60 dígitos e `avaliar` a capturar
`decimal.DecimalException` como `numero_invalido`: o Python agora formata o mesmo texto que o `toFixed` do
JavaScript nos cinco casos do ataque.

3. **Tabela de paridade com o Arcade.** A tabela inteira (134 linhas em 7 categorias) foi revista com o
critério estreito — `feito` só sem NENHUMA diferença conhecida e com vetor de teste da nossa função. As 6
linhas que o adversário derrubou (`Month`, `Now`, `Abs`, `Reverse`, `Back`, `Front`) e mais 12 viraram
`parcial` com a diferença escrita; `DefaultValue` deixou de ter estado contraditório. De **29 feito · 24
parcial · 81 fora** para **11 feito · 42 parcial · 81 fora** (`linhas_feito_na_paridade_arcade`).
`tests/unit/test_expressao_paridade.py` (novo) impede a volta da mentira: linha `feito` sem vetor reprova,
contagem de cabeçalho que não bate com as linhas reprova, `docs/PARIDADE.md` fora de sincronia reprova.

Também consertado (gravidade baixa, mesmo laudo): contexto de topo do lado JavaScript recusa objeto que não
é dicionário simples e, no Node, recusa `Proxy` (`util.types.isProxy`) — no navegador não há detecção
possível e isso está escrito em §7; campo desconhecido dentro de nó de AST passou a ser RECUSADO
(`no_desconhecido`) em vez de ignorado, e a importação lê cada campo por descritor, sem disparar getter.

## turno 3, setembro de 2026 (item L0-02-g-perfil-usuario: perfil próprio — foto, idioma, unidades, formato de data, visibilidade)

Conferido antes de escrever (portão da hipótese vs. o que já existia): a tela `/conta` herdada do
L0-02-tenant-auth já cobria 2 das 8 cláusulas do portão deste item (domínio de e-mail recusado com mensagem;
`login`/`perfil`/`papel_id`/`ativo` já fora da whitelist de `PUT /api/eu`) — as outras 6 (idioma, unidades,
formato de data, foto com limite de tamanho e recodificação, visibilidade) não tinham uma linha de código
(`grep` de `idioma_preferido`/`unidades`/`formato_data`/`foto_perfil`/`visibilidade_perfil` em `app/`, `web/`,
`db/migracoes/` = 0 ocorrências, handoff `laco/handoffs/T3/L0-02g-L0-05c.md` do turno anterior). Migração 042
acrescenta as 5 colunas a `plat.usuario` (idioma_preferido, unidades, formato_data, visibilidade_perfil,
foto_sha256), todas com `CHECK` de vocabulário fechado. `PUT /api/eu` ganha os 4 campos novos na MESMA
whitelist de `campos_json` (nunca uma segunda checagem: o mecanismo que já impedia escalar perfil/login é o
mesmo que agora valida os campos novos). `POST/DELETE /api/eu/foto` reaproveita o adaptador do L0-11
(`app/objetos.py::guardar`, classe `usuario_foto`) e o MESMO truque de base64 sob cookie que
`POST /api/org/logo` (L0-07-a) já usa — recorte central 200×200 pelo Pillow (`ImageOps.fit`, não `contain`
como o logotipo: rosto fica melhor cortado que emoldurado), sem metadado, sem os bytes originais do cliente.

Refutação do próprio item testada e passando: um SVG com `<script>` como foto nunca chega a ser interpretado
(o Pillow não abre SVG, recusa com `415 formato_nao_aceito` antes de qualquer gravação); tentativa de
`login`/`perfil`/`papel_id`/`ativo`/`superadmin` no `PUT /api/eu` continua `400 campo_nao_editavel`; e-mail
fora do domínio do PRÓPRIO inquilino (testado restringindo `demo`, não só o teste unitário de
`email_permitido`) continua `422 email_dominio` nomeando a lista. Foto acima de 1 MiB é `413 foto_grande`
(ou `422` quando o próprio limite do corpo em base64 já corta antes). e2e novo em `tests/e2e/test_conta.py`
(`test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio`) prova edição de nome/unidades, envio de
foto com aparição na barra lateral SEM recarregar (`#pessoa-foto`), e a mensagem de domínio recusado —
captura `L0-02-tenant-auth_perfil.png`, verificada visualmente. 20 testes de API novos em
`tests/api/test_eu.py` + 2 casos novos em `tests/api/cruzado_casos.py` (varredura cruzada A→B de
`POST/DELETE /api/eu/foto`, mesmo padrão do `org_logo`).

Bloqueio ambiental encontrado e NÃO causado por este item: o fixture `autouse` de sessão
`limpeza_de_residuos` (`tests/api/conftest.py`) depende de `sessao_plat` (superadmin do inquilino
`plataforma`, 2FA obrigatório) e o segredo TOTP guardado em `tests/credenciais_totp.txt` não bate mais com
o que está no banco — bloqueia `pytest` de TODA a suíte de API (não só deste item) até alguém religar o 2FA
do superadmin pela via legítima. A API completa foi verificada por um script equivalente fora do pytest
(mesmo `TestClient`, mesmo banco, autenticando como admin do inquilino `demo`, que não exige 2FA) — ver o
handoff do turno. `docs/openapi.json` e `docs/LIMITES.md` regenerados; `plat-api` (systemd) reiniciado para
servir o código novo aos e2e (verificado antes e depois: RAM estável, sem incidente). Docs: `MANUAL.md` §3.1a,
`ARQUITETURA.md`, `docs/PARIDADE.md`. Pendente, nomeado (não prometido como feito): consumo de
`unidades`/`formato_data` para reformatar número/data em outras telas e uma tela de "perfil de outro
usuário" que leia `visibilidade_perfil` — nenhuma das duas existe hoje; `idioma_preferido` é preferência
guardada, a aplicação de fato é o item `L7-10-a-i18n-pt-en-es` (pendente).

## turno 3, setembro de 2026 (itens L6-01-d-ficha-fonte · L6-01-f-lgpd: ficha do acervo completa + gate de LGPD no "adicionar")

Conferido antes de escrever: a ficha (`GET /api/acervo/{fonte_id}`, migração 021, item anterior) já tinha os
10 campos de procedência da hipótese (url, licença, frescor, data do dado, script gerador, sha256, método,
confiança, limites, próxima verificação) — `limites` já é "o que este dado não sustenta" em conteúdo real.
Somado nesta passagem: **`endpoints`/`endpoints_total`/`endpoints_confirmados_vivos`**
(`plat.acervo_endpoint`, migração 040, sobre `acervo.endpoint`, "vivo" = `confirmado AND http = '200'`) e
**`completude_texto`** ("4,5/10" por extenso; `None` nunca fabricado quando falta base de cálculo).

`acervo.fonte` não tinha campo de classificação de risco de dado pessoal (conferido por `\d`) — criada
**`plat.acervo_lgpd`** (migração 041), curada à mão (sem GRANT de escrita a `plat_app`), depois de uma
varredura real de 219 tabelas canônicas das 68 fontes licenciadas contra um padrão amplo de coluna (114
batidas, lidas uma a uma — a maioria nome de lugar ou CNPJ de fundo, não pessoa física). Achado real único:
**`onr`** (matrículas) — `url_mat` aponta para o documento de cartório com o nome do titular, mesmo a tabela
ingerida não guardando o nome. `POST /api/acervo/{fonte_id}/adicionar` recusa com 409
`confirmacao_pii_exigida` para fonte marcada sem `{"confirma_risco_pii": true}` no corpo, registrando a
recusa como evento (`acervo/adicionar_recusado_pii`) em transação própria (mesmo padrão de
`_falhou()`/`_bloqueado()` do login — registrar e levantar no mesmo bloco de `db.db()` apagaria o evento no
rollback). 16 testes novos/estendidos em `tests/api/test_acervo.py` (ficha de 20 fontes campo a campo,
campo ausente nunca fabricado, gate de LGPD com e sem confirmação, regressão da maioria sem curadoria).
**Sem tela ainda** (L6-01-c) e sem a classificação por COLUNA em `plat.acervo_camada` (fica pendente, não
prometida como feita). Docs: `MANUAL.md` §19, `ARQUITETURA.md` §16, `docs/PARIDADE.md`.

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: extensão do núcleo — 43 funções, 309 vetores Python=JavaScript, listas e dicionários, formatação pt-BR)

Continuação do núcleo entregue no mesmo turno (18 funções, 41 vetores). Passa a **43 funções**
(`tests/medidas/L2-10-c-expressao.json`, `funcoes_implementadas`), com texto (`Trim`, `Left`, `Right`,
`Mid`, `Find`, `Split`, `Replace`), número (`Floor`, `Ceil`, `Sqrt`), data (`Weekday`), escolha
(`Decode`), onze de coleção (`Lista`, `Contagem`, `Primeiro`, `Ultimo`, `Obter`, `Contem`, `Soma`,
`Media`, `Reverter`, `Unicos`, `Juntar`) e formatação pt-BR (`TextoNumero`, `TextoData`). Os tipos
**lista e dicionário** entram como valor de primeira classe, sem gramática de literal: a lista vem de
`Lista(...)` e o dicionário vem do contexto — o que fecha o caminho de um literal grande no texto da
expressão virar custo de análise.

**309 vetores** (`vetores_de_equivalencia`) rodam nos dois avaliadores e são comparados byte a byte
(`test_expressao_equivalencia.py`); os mesmos 309 passam pelo AST exportado → JSON → reimportado em
Python, em JavaScript e CRUZADO (AST escrita pelo Python, lida pelo JavaScript), com resultado idêntico
(`vetores_ast_ida_e_volta_nos_dois_lados` = 309). Erro nomeado igual nos dois runtimes em 46 casos de
ataque de tipo, limite e chave proibida (`test_expressao_extensao.py`); `__proto__`, `prototype` e
`constructor` são `campo_nao_permitido`, e o lado JavaScript não lê propriedade herdada nem executa
getter (medido: 0 leituras).

Limites medidos SOB ATAQUE, com o custo escondido dentro de uma chamada (comparação estrutural
quadrática em `Unicos` sobre 1.024 dicionários, 40 termos ≈ 21 milhões de comparações), não só com
árvore funda: corte pelo relógio em **50,63 ms** no Python e **53,65 ms** no JavaScript contra o teto de
50 ms do cliente, e **500,69 ms** contra o teto de 500 ms do servidor; com o relógio folgado o mesmo
ataque para em `limite_passos` (10^5), provando que os dois orçamentos cortam de forma independente.
Novos tetos por VALOR (1.024 itens por coleção, 4.096 nós, 20.000 pontos de código, profundidade 20)
recusam com `valor_grande` antes de a memória crescer.

**Paridade função a função com o Arcade function reference** (269 funções em 17 categorias, lido em
setembro de 2026) na seção 10 de `docs/EXPRESSAO.md`, resumida por categoria em `docs/PARIDADE.md`:
29 feito · 24 parcial · 81 fora nas 7 categorias com correspondência; as outras 10 categorias
(135 funções — FeatureSet, geometria, pixel, voxel, trajetória, portal, grafo, IA, depuração, empresa)
ficam inteiras de fora, cada uma com o motivo. Paridade de CAPACIDADE, nunca promessa de rodar script
Arcade sem adaptação: todo nome nosso é em português.

A EBNF do documento continua GERADA das tabelas de precedência do parser e conferida byte a byte
(`test_expressao_doc_sincronizada.py`), o que pegou nesta passagem uma divergência real: a ordem dos
operadores de comparação mudou no código e o documento ficou para trás.

FICA DE FORA e está escrito na seção 11: geometria, `Filter`/`Map`, domínio, `FeatureSetByRelationship`,
integração com popup/rótulo/formulário (L5-11), fuso horário do usuário e máscara livre de formatação.
A cláusula do portão "expressão que acessa camada de outro inquilino = erro de permissão" **não foi
provada**: não há camada ligada à expressão, logo não há caminho de acesso para atacar.

## turno 3, setembro de 2026 (itens L6-01-a-registro · L6-02-a-modelo-conexao-e-seguranca: registro de camadas do acervo + modelo genérico de conexão externa com defesa de SSRF)

Dois itens da linha L6, ADR 0012. **L6-01-a-registro** é FILHO DIFERENTE do já entregue
L6-01-a-procedencia-acervo (migração 021): aquele é a ficha da FONTE (376 linhas, sem geometria); este é o
registro de CAMADA — `plat.acervo_camada` (migração 030, renumerada de 028 por colisão com a trilha
concorrente do documento de construtor), uma linha por tabela canônica com geometria, populada por
`scripts/acervo_sync.py` (roda como `postgres`, psycopg2 do dpkg, sem venv). Medido 06/09/2026: 462
candidatas (270 em `public`) via `geometry_columns`×`acervo.objeto`; `COUNT(*)` exato com timeout de 25 s
(nunca `reltuples`); tabela fantasma é regra DINÂMICA (estimativa > 0 e exata = 0), nunca lista de nomes —
cobre as 2 fantasmas conhecidas do registro (`public.prodes_yearly_all_indexed`,
`farma.djen_pub_termo`) sem citá-las em código. Lista branca de colunas por nome (rede mínima, provisória —
o reforço por conteúdo é o item L6-01-f, ainda não construído). Duas rodadas completas medidas: 274,9s e
286,0s (ambas sob o portão de 5 min), com a máquina disputada por outro job pesado da casa (REFRESH
MATERIALIZED VIEW de 3h + COUNT(*) de 18 min concorrentes); ordem de processamento por "há mais tempo sem
sincronizar" prova convergência entre rodadas (81→172 expostas da 1ª para a 2ª). Achado ao testar: `--limite`
de depuração estava apagando o registro completo de rodadas anteriores (a poda comparava contra o que a
rodada limitada processou, não contra o universo real de candidatas) — corrigido antes de qualquer uso além
de teste. 6 testes em `tests/api/test_acervo_camada.py` (+ 1 `lento` rodando o universo inteiro).

**L6-02-a-modelo-conexao-e-seguranca**: `plat.conexao` (tenant_id+RLS; mesma migração 030) — tipo em
vocabulário fechado (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles/postgres_fdw/s3/http), `config`
JSONB, credencial cifrada com AES-GCM (`app/conexao/credencial.py`, prefixo `encconexao:v1:`, mesmo padrão do
TOTP e do bind LDAP — nunca `pgp_sym_encrypt`, que deixaria a chave passar pelo SQL). Só o MODELO e a
segurança nesta trilha — os 15 conectores concretos são itens futuros. `app/conexao/seguranca.py` defende
contra SSRF: esquema só http/https, sem userinfo, resolve o host com timeout numa thread separada, recusa IP
privado/loopback/link-local (inclui `169.254.169.254`)/CGNAT(100.64.0.0/10, gap medido de
`ipaddress.is_private`)/reservado/multicast, conecta PINADO no IP já validado (subclasse de
`httpcore.SyncBackend`; o TLS continua verificando o hostname original via `server_hostname`, então
DNS-rebinding não passa), e revalida CADA redirecionamento do zero (nunca segue automático) até 5 saltos.
Provado com servidor de teste bindado no IP PÚBLICO REAL desta máquina (nunca loopback, para não confundir
com o caso 1) redirecionando para `169.254.169.254`: aceita o hop 0, recusa só o hop 1. `POST /api/conexoes/
{id}/testar` roda o teste de saúde com timeout curto (conectar 3s/ler 6s) contra um endpoint público real
(IBGE, dado aberto); a credencial nunca aparece em resposta de API nem em log (provado com `caplog`). 25
testes em `tests/unit/test_conexao_seguranca.py` (os 8 casos do portão) + 13 em `tests/api/test_conexoes.py`
(CRUD, RLS cruzada A→B, unicidade de nome, tamanho de `config`, credencial oculta).

`make check` rodado sob `flock laco/.pytest.lock`; migração `030_conexao.sql` aplicada via `db/migrar.sh`
(registrada em `plat.versao_migracao`, junto com `027_acervo_camada.sql` e as migrações da trilha
concorrente que já estavam no disco). Documentação: `docs/adr/0012-registro-do-acervo-e-conexao-externa.md`,
`docs/PARIDADE.md` (2 seções novas).

## turno 3, setembro de 2026 (item L5-05-documento-versoes: documento de construtor — grafo de nós com ULID)

Base genérica que qualquer construtor do L5 (app, painel, e depois formulário, fluxo) vai usar para gravar um
grafo: reaproveita por inteiro `plat.item.dados`/`plat.tipo_item.esquema`/`plat.item_versao` de L0-03 (nenhuma
tabela nova). `app/catalogo/documento.py` acrescenta o que JSON Schema puro não expressa: `validar_grafo`
recusa (`422 grafo_invalido`) dois nós com o mesmo `id` ULID ou uma ligação apontando para um nó inexistente
em `corpo.nos`; `migrar_para_leitura` aplica `migrar_<tipo>_v<N>_v<N+1>` **na leitura** (nunca grava de volta
no banco) e registra o evento `itens/esquema_migrado`; `sha256_canonico` (json.dumps ordenado, sem espaço) é
um hash À PARTE do `sha256` de `item_versao`, reproduzível fora do banco por qualquer `sha256sum` — o
`sha256` de `item_versao` vem de `corpo::text` do jsonb do Postgres, MEDIDO nesta máquina como NÃO
reproduzível fora sem reimplementar a serialização interna do banco (ordena chave por comprimento-depois-
alfabeto, espaço depois de `:`/`,`).

Migração `028_documento_grafo.sql`: esquema de `app`/`painel` passa de trivial (`corpo:{}`) para grafo
(`corpo.nos`/`corpo.ligacoes` — os dois OPCIONAIS, então os 1.573/1.571 itens já semeados em demo/demo2
continuam válidos sem migração de escrita); `corpo.mapas`/`mapa_id` continuam aceitos porque são o contrato
já entregue de `app/catalogo/relacoes.py::_app` (item L0-03-i) — quebrar esse campo quebraria "usado-por" de
app/painel→mapa. Endpoints novos: `GET /api/esquemas` (lista de tipos com esquema publicado), `GET
/api/esquemas/{tipo}?versao=N` (serve o mesmo JSON Schema que valida `dados`, para o editor e para o agente
escreverem contra o mesmo contrato), `GET /api/itens/{id}/integridade` (recomputa o sha256 de cada versão a
partir do `corpo` gravado e compara com o `sha256` da linha — detecta edição direta em `plat.item_versao` por
fora do gatilho; só quem tem acesso de superusuário ao Postgres consegue fazer isso, `plat_app` tem
INSERT/UPDATE/DELETE revogados na tabela desde a 011). `docs/gerar_esquemas.py` espelha o esquema vigente de
`app`/`painel` em `docs/esquemas/<tipo>-v2.json` (mesma disciplina de `docs/gerar_limites.py`, `--check`
falha se divergir do banco); `docs/esquemas/<tipo>-v1.json` ficam como registro histórico, nunca regerados.

10 testes em `tests/api/catalogo/test_documento.py`: grafo válido cria e a versão traz `sha256_canonico`;
hash reproduzido fora do banco com `sha256sum` de verdade (subprocesso Python + hashlib, bate byte a byte);
nó sem ULID / ULID repetido / ligação pendente recusados na criação E na edição; rascunho nunca muda a versão
publicada até publicar explicitamente (e a versão anterior continua legível depois de publicar a seguinte);
ULID de nó nunca se repete em nenhuma versão ao longo de 5 edições; migração de esquema_versao=1 para 2 na
leitura, com o evento gravado, e a linha do banco continua em 1 (a migração não gravou de volta); RLS cruzado
(versões e integridade de um documento de outro inquilino = `404`); `plat_app` não consegue editar
`plat.item_versao` direto (confere a premissa do teste de corrupção); corrupção direta na linha de versão
(`sudo -u postgres psql`, simulando acesso de superusuário) aparece em `/api/itens/{id}/integridade`.
Latência medida: mediana de 30 `PUT /api/itens/{id}` (painel, 2 nós) = **17,3 ms**
(`tests/medidas/L5-05-documento-versoes.json`, `latencia_salvar_versao_ms`). Rotas novas cadastradas em
`tests/api/cruzado_casos.py` (P6: `/api/esquemas`, `/api/esquemas/{tipo}` como vocabulário — mesmo padrão de
`/api/tipos-item`; `/api/itens/{id}/integridade` como alvo padrão 401/403/404).

Decisões em `docs/adr/0011-documento-de-construtor.md`. Detalhe: `MANUAL.md` seção 17, `ARQUITETURA.md` seção 14.

## turno 3, setembro de 2026 (item L1-01-d-garage-por-inquilino: balde por inquilino com cota dupla, chave só-leitura e COG por Range)

Constrói sobre o adaptador do L0-11 (ADR 0006) o que a linha de imagens precisa. **ADR 20260908T1255**; migração
`20260908T1255_garage_por_inquilino.sql` (nome com carimbo de tempo UTC, regra fixa: a faixa de três dígitos está
fechada).
Constrói sobre o adaptador do L0-11 (ADR 0006) o que a linha de imagens precisa. **ADR 0016**; migração
`20260906T1547_garage_inquilino.sql` (a reserva original era 034, e depois 042, mas a árvore principal já tinha commitado 034/036/040/041/042
— renumerada e registrada no handoff).

- **Cota dupla.** `plat.tenant.cota_objetos` e `plat.arquivo_bucket.cota_objetos` novas; `UpdateBucket` do Garage
  passa a receber `quotas: {maxSize, maxObjects}`. Medido: com `maxObjects` na conta exata, o PUT seguinte volta
  403 e a mensagem que chega à API é **"o Garage recusou a gravação: a cota de objetos do inquilino foi atingida
  (limite do balde: N objetos)"** — em português, com o limite que o próprio Garage citou
  (`app/garage.traduzir_erro_s3`, classe `CotaGarage`). Para bytes a instância mediu **"o Garage recusou a
  gravação: a cota de armazenamento do inquilino foi atingida"** — sem número, porque essa mensagem do Garage não
  cita o limite. `POST /api/arquivos` acima da cota devolve **413 `cota_excedida`**; a frase que chega ali é a da
  checagem prévia ("cota de 500 bytes excedida: uso atual 138906, objeto de 2048 bytes"), porque ela corre antes e
  é mais informativa — a do Garage é a que sobe quando a prévia deixa passar.
- **Semeadura de instalação.** Passo `g3` do `install.sh` (`python -m app.baldes_semear`): balde, duas chaves,
  as duas cotas e o endpoint web por inquilino ativo. Medido no inquilino de teste: 1ª execução **1
  criado/alterado**, 2ª **0 criados/alterados**. A semeadura lê o balde de volta pela Admin API e reaplica quando
  o Garage discorda do banco — foi assim que se descobriu `plat-demo` com `maxObjects: null` no Garage e 200000
  no banco.
- **Objeto nomeado por conteúdo, nunca sobrescrito.** `app/objetos_raster.py`: `<item_id>/<asset>_<sha8>.<ext>`,
  `HEAD` antes de gravar, `ObjetoJaExiste` na segunda gravação do mesmo conteúdo; conteúdo novo produz chave nova
  (medido: `demo/zt_sobrescrita/cog_c9e41e3e.tif` → `cog_ebd6a855.tif`, a versão 1 intacta). A expressão da chave
  não admite ponto nem barra no item/asset: dez formas erradas (`..`, `../../etc`, maiúscula, sha curto) recusadas
  no teste unitário.
- **Chave só-leitura que sai de casa.** `GET /api/arquivos/_chave-leitura` (sessão + `org.integracoes`) entrega a
  credencial S3 RO do balde para a conexão do ArcGIS Pro e o `/vsis3` do TiTiler; a chave RW nunca sai. Refutação
  medida com boto3: com a chave RO, `PutObject` **403**, `DeleteObject` **403**, `CopyObject` no mesmo balde
  **403**, `CopyObject` entre baldes **403**, `CreateMultipartUpload` **403**; `ListBuckets` responde 200 mas
  mostra só `['plat-demo']` (o balde do outro inquilino não aparece). Contra o balde do vizinho, `GetObject`,
  `HeadObject` e `ListObjectsV2` = **403** cada.
- **COG por HTTPS com Range.** Bloco `/svc/<token>/cog/<slug>/...` em `deploy/nginx.conf` (`slice 1m`, cache das
  fatias, `auth_request` contra `GET /api/arquivos/_cog/autorizar`). Provado contra um nginx PRÓPRIO de teste
  (porta 8162, certificado autoassinado): objeto de 3.146.505 bytes, `Range: bytes=1048576-1048591` responde
  **206** com `Content-Range: bytes 1048576-1048591/3146505`, 16 bytes conferidos contra o conteúdo gravado;
  token inválido no caminho = **403** antes de o Garage ver a requisição. **O bloco NÃO foi aplicado no nginx do
  sistema neste turno** — quem aplica é o gerente.
- **Apagar devolve a cota.** `objetos_raster.apagar_item` mediu 72 objetos/138.095 bytes antes → 75/153.095 com
  3 objetos gravados → 72/138.095 depois, com os contadores do próprio Garage (GetBucketInfo). Segunda chamada
  devolve zeros. `objetos.apagar_bucket_do_inquilino` desfaz o balde inteiro (objetos, as duas chaves, o balde e
  a linha), porque `plat.inquilino_apagar` só limpa o banco.

Medidas em `tests/medidas/L1-01-d.json`. Testes: `tests/unit/test_objetos_raster.py` (30) e
`tests/api/test_garage_inquilino.py`.

## turno 3, setembro de 2026 (itens L0-02-e-varredura-cruzada-rls · L0-02-f-tela-usuarios: fechamento com evidência fresca + gap real corrigido)

Os dois itens já tinham quase todo o mecanismo construído desde a fundação do `L0-02-tenant-auth` (turno 2);
esta passagem mediu de novo com o código de HOJE (outras trilhas do turno adicionaram rotas por baixo desde a
última medição) e fechou o único gap real encontrado.

**L0-02-e (varredura cruzada A→B):** `tests/api/test_cruzado.py::test_cobertura_100_por_cento` rodado agora —
**138 rotas no `docs/openapi.json` vivo, 138 com caso em `tests/api/cruzado_casos.py`** (era 123 na última
medição gravada; o OpenAPI cresceu com LDAP e outros itens de T3, e `cruzado_casos.py` já tinha acompanhado).
Gravado em `tests/medidas/L0-02-e.json` (nome exigido pelo portão) e mantido também em
`tests/medidas/L0-02-tenant-auth.json` (convenção do item-pai, usada por `MANUAL.md`/`ARQUITETURA.md` desde o
turno 2 para o bloco inteiro de identidade e acesso). `tests/api/test_funcoes_seguras.py` (REVOKE EXECUTE de
PUBLIC em toda função SECURITY DEFINER do schema `plat`, `tenant_criar` por GUC forjado levanta
`so_superadmin`) roda dentro da mesma suíte e passou.

**L0-02-f (tela Usuários):** a tela (`web/admin/usuarios.html` + `web/js/auth/usuarios.js`) já tinha TUDO
construído — criar, editar, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear, lote até 100
(mudar perfil/desabilitar/reabilitar), recusa do último admin — mas só um e2e cobria a fatia
criar/editar/senha/lote-desabilitar/último-admin. Escrito `tests/e2e/test_usuarios.py::
test_usuarios_perfil_lote_2fa_desbloquear_apagar_com_grupos_e_401`, cobrindo pela INTERFACE o que faltava:
mudar perfil em massa (3 usuários), desligar 2FA, desbloquear (com bloqueio real de 5 senhas erradas antes),
apagar recusado listando 2 grupos, e o tempo entre desabilitar e o 401 do próprio usuário na próxima
requisição — **medido 73,1 ms** (`desabilitar_para_401_ms`, bem abaixo do 1 s do portão).

**Gap real encontrado e corrigido:** `apagar_usuario` só recusava por grupos possuídos; `plat.item.dono_id` é
FK sem `ON DELETE`, então um usuário com itens do catálogo (mapas, camadas, pastas) na verdade causava um
`409 em_uso` genérico do banco (nome da constraint, nunca os títulos) em vez da recusa nomeada que o portão
pede ("recusa listando os 2"). Adicionado `_itens_do_dono` (mesmo padrão de `_grupos_do_dono`) em
`app/auth/rotas_usuarios.py`, novo erro `409 possui_itens` com a lista de títulos, chave de i18n
`usuarios.possui_itens` e o mesmo tratamento no JS que já existia para `possui_grupos`. Provado por
`tests/api/test_usuarios.py::test_apagar_com_2_itens_do_catalogo_recusa_listando_os_2` (cria 2 itens, recusa
409 listando os 2 títulos, purga os itens pelo mesmo caminho de `tests/api/catalogo/conftest.py::
_expurgar_zt`, confirma que a exclusão passa a funcionar).

`docs/PARIDADE.md` linha "gestão de membros" atualizada (apagar recusa por grupos E itens, não só grupos).
Achado colateral, não deste item: `GET /saude` respondeu 503 durante a varredura porque outra trilha do turno
tinha uma migração (`028_documento_grafo`, depois `029_ingestao_vetor`) pendente de aplicar no banco
compartilhado — não é regressão de L0-02-e/f, é o estado normal de trilhas paralelas no mesmo turno.

**Adversário independente do turno**: PASSA em L0-02-e (43+19 testes filtrados; GUC forjado, cross-tenant e
rota-sem-caso todos bloqueados/reprovados como esperado). Achou um escalonamento de privilégio real em L0-02-f
(não cross-tenant): `POST /api/usuarios` checava admin só por `auth.perfil`, nunca por `membros.papel` — um
segundo admin com papel restrito a `{membros.ver, membros.gerir}` fabricava um admin PLENO. Corrigido nesta
mesma sessão (`criar_usuario` agora exige `membros.papel` para `perfil≠visualizador` ou `papel_id`), com
regressão própria (`test_criar_usuario_com_perfil_ou_papel_exige_membros_papel`) e sem falha nova na suíte
alvo. Pendência nomeada, não bloqueante: `papel_id` atribuído (na criação OU na edição) ainda não checa se o
ATOR possui os privilégios daquele papel — mesmo princípio que `_validar_papel` já aplica na criação de papéis,
ausente na atribuição de um papel já existente; fica para o dono decidir se abre item novo.

## turno 3, setembro de 2026 (item L0-09-metadado-catalogo: metadado ISO 19139 por item + catálogo externo OGC API Records)

`GET /api/itens/{id}/metadado.xml` (`app/catalogo/metadado.py`) gera `gmd:MD_Metadata` (ISO 19139/GMD — o
perfil que o Perfil MGB 2.0/GeoNetwork da INDE consomem) a partir do próprio item (título, resumo/descrição,
palavras-chave, créditos, termos de uso, extensão geográfica, dono como `pointOfContact`, inquilino como
`contact`) e de `dados.procedencia` quando existir (vira `dataQualityInfo`/`lineage`, D17 do L0_CONCEITO); o
servidor VALIDA o XML contra o XSD oficial antes de responder — nunca confia em si mesmo. O XSD (perfil
`schemas.opengis.net/iso/19139/20070417`, 57 arquivos, 796 KB) é baixado uma vez por
`docs/xsd/baixar_iso19139.py`, que reescreve todo `schemaLocation` absoluto para caminho relativo dentro do
próprio cache — depois de rodado, a validação nunca mais toca rede (comitado em `docs/xsd/cache/`, refeito
pelo `install.sh`; prova: a validação passa com o `socket.socket` da máquina bloqueado de propósito).

Catálogo externo por protocolo padrão: **OGC API Records** (OGC 20-004r1) em `/ogc/records`
(`app/catalogo/rotas_ogc.py`) — pouso, `/conformance`, uma coleção (`catalogo`, o catálogo inteiro do
inquilino), `/items` (GeoJSON, filtros `q`/`bbox`/`tipo`/`tags`, paginação cursor, reaproveitando
`listar_ids`/`carregar_varios` de `rotas_itens.py`) e `/items/{id}`, com link para o metadado ISO acima. CSW
fica de fora desta passagem (justificativa no próprio módulo: RAM da máquina no limite, nenhuma biblioteca
CSW instalada, protocolo legado frente à API REST — custo de mudar registrado como médio). As duas rotas
exigem sempre `catalogo:ler` (sessão OU token de serviço do L0-02) — nunca abertas, nem a página de pouso; o
isolamento por inquilino é o MESMO mecanismo de RLS de `plat.item` que `GET /api/itens` já usa (nenhum filtro
novo escrito nas rotas), o que é também a prova mais forte da refutação do item.

9 testes próprios verdes (`tests/api/catalogo/test_metadado_ogc.py`): item completo e item mínimo (só
obrigatórios) validam contra o XSD; item inexistente e de outro inquilino → `404`; token `catalogo:ler` lê o
próprio inquilino e nunca o outro (nem por XML nem pelo registro OGC); as duas rotas OGC recusam chamada sem
autenticação (`401`); coleção e conformidade respondem; o registro do item aponta para o seu próprio
metadado.xml. Sem migração: nada disto precisou de coluna nova em `plat.item` (o bloco `dados.procedencia`
que a exportação usa já é do modelo existente da ADR 0004).

**Pendências nomeadas** (não escondidas): ISO 19115-3 (só 19139 nesta passagem); CSW; e a varredura cruzada
A→B AUTOMÁTICA das duas rotas novas via `docs/openapi.json`/`tests/api/cruzado_casos.py` — este turno tinha
outras trilhas regravando esses dois arquivos ao vivo (concorrência real no mesmo repositório: `app/main.py`
e `app/catalogo/rotas_itens.py` também mudaram por baixo durante a construção, por outro item —
`L0-04-ingestao` e `L5-05-documento-versoes` — sem colisão real de linha graças a `git update-index` cirúrgico
em vez de `git add` cru); regenerar `docs/openapi.json` agora capturaria estado parcial de trilhas alheias,
por isso fica para a integração final do turno. O isolamento por inquilino já está PROVADO pelos 9 testes
próprios; falta só o item na varredura genérica. Ver `docs/PARIDADE.md` e `laco/handoffs/T3/L0-09-metadado.md`.

### Commits

| sha | mensagem |
|---|---|
| (este) | Metadado ISO 19139 por item e catálogo externo OGC API Records (item L0-09-metadado-catalogo) |
## turno 3, setembro de 2026 (item L0-02-g-checagem-privilegio-papel-id: quem concede papel tem de ter o papel)

Fecha um escalonamento de privilégio real na tela de usuários. O papel personalizado RESTRINGE o teto do perfil
(`plat.privilegios_de` é a interseção entre os dois), mas `POST /api/usuarios` e `PUT /api/usuarios/{id}`
conferiam apenas se o papel CABIA no perfil do alvo, nunca se o ATOR tinha o que estava concedendo. Um
administrador restrito por papel podia atribuir a outro um papel mais amplo que o seu, ou zerar o `papel_id` de
alguém — inclusive o próprio — e recuperar o teto inteiro do perfil, ou ainda promover um editor a administrador
sem papel, e fazer qualquer um dos três em massa pelo lote. `_nao_conceder_alem_do_proprio` (ADR 0016) recusa
com 403 `privilegio_proprio_insuficiente` e devolve no `detalhe` a lista do que sobraria. Vale para perfil e
papel juntos, porque promover a admin com papel nulo concede exatamente o mesmo conjunto.

A refutação exigida foi rodada na forma completa, não em um caso: para **cada um dos 47 privilégios** do
vocabulário, o papel do ator passa a ser "todos menos ele" e o papel oferecido passa a ser "todos" — um
privilégio a mais. **94 chamadas (POST e PUT), 94 respostas 403, nenhuma 2xx**; 92 pela conferência nova
(`privilegio_proprio_insuficiente`) e 2 pelo portão de privilégio (`sem_privilegio`), que são exatamente os
casos em que o privilégio retirado do ator era `membros.gerir` ou `membros.papel`. Retirando as duas chamadas
da conferência, 7 dos 10 testes do arquivo reprovam — a prova de que mordem.

Varredura de privilégio rota por rota, em duas camadas, sobre as **138 rotas** de `docs/openapi.json`. A
estática lê o fecho da dependência `autenticado(...)` de cada rota viva e compara com o declarado: **41 rotas**
cobram na dependência exatamente o privilégio nomeado que declaram, **72** declaram valor especial ou
alternativa e cobram no corpo, **8** cobram na dependência um privilégio que a declaração não menciona. A
dinâmica prova as 41 com chamada real: um administrador de inquilino descartável recebe um papel com todos os
privilégios menos um e **as 41 rotas respondem 403 `sem_privilegio` com `exigido` igual ao declarado**; com o
papel completo, nenhuma delas responde `sem_privilegio` (controle positivo). Fronteira declarada: **31 rotas**
de privilégio alternativo cobrado depois de carregar o recurso ficam fora do alcance deste item — a medida
`rotas_alternativas_nao_provadas` guarda o número, e as duas de `/api/usuarios` que o item alcança foram
provadas.

As 8 rotas de declaração incompleta (`/api/tokens/{id}` e `/renovar` cobrando `tokens.gerar` sem declarar,
`/api/acervo/{fonte_id}/adicionar` cobrando `conteudo.criar` numa declaração que promete alternativa,
`/api/itens/{id}/miniatura/gerar` e `/api/lixeira/esvaziar` cobrando `jobs.executar`, e `POST /api/logout` sem
dependência) **apertam** o acesso em vez de afrouxá-lo: exigem mais do que a documentação promete, então não são
falha de segurança, e sim documentação errada. O conserto é do dono de cada rota. A lista está CONGELADA em
`DIVERGENCIAS_CONHECIDAS` no teste: divergência nova reprova.

De quebra, um defeito que impedia a homologação inteira: `CursorSchemaAmbiente` não sobrescrevia `executemany`,
então o INSERT em lote de `plat.papel_privilegio` ia ao servidor com o literal `plat.` e todo ambiente fora do
schema de produção respondia 403 "operação fora do inquilino da sessão" nas rotas de papel. Corrigido junto com
`mogrify`, com guarda em `tests/unit/test_schema_ambiente_metodos.py` que varre `app/` atrás de método de cursor
usado sem sobrescrita. O cursor de `conexao_plat_app` passou a ser o mesmo, senão nenhum teste que escreve
`plat.` na mão roda fora de produção.

## turno 3, setembro de 2026 (item L1-01-b-validacao-e-isolamento-da-entrada: validação de raster)

Abre a linha L1 (imagens) com o portão que fica ANTES de qualquer conversão: `app/raster/validacao.py` (ADR
0015) roda toda a inspeção do arquivo do cliente em **subprocesso separado**, com `RLIMIT_AS` 768 MB,
`RLIMIT_CPU` 60 s, `RLIMIT_NOFILE` 64, `RLIMIT_CORE` 0, relógio de parede de 90 s (SIGKILL no grupo de
processos) e ambiente GDAL sem leitura de diretório (`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`), sem
`/vsicurl` (nenhuma extensão permitida ao driver HTTP), sem `.aux.xml`, sem `VRTRawRasterBand` e sem função
de pixel. O processo pai **nunca importa rasterio para olhar o arquivo do cliente**: só lê os 64 primeiros
bytes e confere a ASSINATURA de formato contra a extensão declarada (um PNG renomeado para `.tif` é recusado
sem sequer abrir subprocesso). Qualquer morte do filho — memória, CPU, relógio, sinal, saída sem JSON — vira
relatório `recusado` com a causa em português, nunca exceção subindo pela fila.

Três estados no mesmo relatório JSON, gravado inteiro no resultado do job `raster.validar`
(`app/raster/tarefas.py`): `recusado` (defeito do arquivo, mensagem exata), **`pendente`** (falta o que só o
usuário sabe — CRS, NoData, data de aquisição, escala para reduzir 16 bits a 8 no perfil visual: a
plataforma PERGUNTA e grava a resposta em `respostas`, **nunca assume um CRS**) e `aceito` (avisos não
impedem: CRS sem EPSG resolvível é aceito com o WKT2 inteiro gravado; extensão fora do Brasil vira aviso).
O tamanho descompactado é estimado pelo CABEÇALHO (`largura × altura × bandas × itemsize`) e comparado com a
cota do inquilino antes de ler um pixel; no zip só o diretório central é lido antes de decidir (nº de
entradas, soma declarada contra a cota, razão declarado/comprimido ≥ 50× = recusa, nome de caminho, link
simbólico, zip aninhado) e **nada é extraído antes de aprovado**.

Medido (`tests/medidas/L1-01-b.json`, 33 casos com arquivo sintético gerado em `tmp_path`, 31 deles com
subprocesso): tempo do subprocesso mediana **0,294 s**, máximo 0,406 s fora do caso que prova o relógio;
pico de RSS do subprocesso entre **87,1 MB e 130,4 MB**, ou seja 17 % do `RLIMIT_AS` declarado.
Um BigTIFF esparso de **320.000 × 320.000** (95,4 GB descompactados estimados, **menos de 200 kB em disco**)
é recusado em 0,3 s sem derrubar o pai; um TIFF fabricado à mão de 400.000 × 400.000 (menos de 1 kB) idem.
Os três casos de invenção do adversário estão na suíte e passam: TIFF com IFD circular (o laço não trava —
o relatório sai em menos de 10 s), JP2 truncado pela metade (recusado ao ler a janela de prova) e GeoTIFF
declarando **65.535 bandas** (recusado, RSS abaixo do limite). Provas de isolamento: filho que tenta alocar
2 GB morre e o pai devolve `morte=memoria`; filho em laço infinito é morto por relógio em 2,01 s com
`codigo_saida=-9`.

Fora deste turno de propósito: o e2e do job `raster.validar` (fila real) — a trilha rodou em worktree e não
sobe worker que dispute a fila de produção; o registro do tipo é provado por teste de unidade.

### conserto do laudo do adversário (mesmo turno)

Um adversário independente REFUTOU a primeira versão com 9 achados (`laco/handoffs/T3/L1-01-b-ADVERSARIO.md`,
23 casos em `tests/unit/test_raster_validacao_adversario.py`, 9 deles `xfail(strict=True)`). Os 9 foram
consertados e os 23 casos passam, sem nenhum ser apagado ou afrouxado — o texto de cada achado ficou como
comentário em cima do teste que o registrou. O que mudou:

* **A rede fecha no processo, não por variável.** O filho recebe um filtro **seccomp** (BPF clássico montado
  com `ctypes` sobre a libc; nenhuma dependência nova) que faz `socket(AF_INET/AF_INET6)` devolver
  `EAFNOSUPPORT`, com `PR_SET_NO_NEW_PRIVS` para sobreviver ao `execve`. Antes, `CPL_VSIL_CURL_ALLOWED_
  EXTENSIONS` aceitava qualquer extensão que o remetente escrevesse na URL e o `http://` direto nem passava
  por ela: o adversário recebeu `HEAD /x.nenhuma-extensao-permitida` e `GET /y.tif` num ouvinte em
  127.0.0.1. Medido depois do conserto, com o mesmo ouvinte e quatro caminhos de ataque (`/vsicurl` e
  `http://`, direto e por VRT aninhado): **0 pedido recebido**. Provado também com a camada de conferência
  DESLIGADA (chamando o GDAL direto no filho): 0 pedido, e `socket()` cru devolve erro. O filho MEDE o
  próprio isolamento em `/proc/self/status` e grava `info.isolamento` (`seccomp: 2`, `no_new_privs: 1`) no
  relatório. Namespace de rede foi testado e recusado: funciona, mas o kernel desta máquina não deixa
  escrever `uid_map`, e o filho passaria a valer como `nobody` para permissão de arquivo.
* **VRT conferido RECURSIVAMENTE.** Toda `SourceFilename` é resolvida com `os.path.realpath` (desfaz `..` e
  **ligação simbólica**) e tem de cair dentro do diretório do envio; VRT que aponta para VRT é conferido até
  5 níveis, com referência circular recusada. O XML é lido INTEIRO até 16 MiB — o corte de 1 MiB escondia
  uma segunda banda atrás de um comentário grande. Fechou os achados 1, 2 e 3 (leitura de arquivo de fora do
  envio por três caminhos).
* **`NaN` não derruba mais a gravação.** NoData `NaN` (comum em float32) virava `NaN` no JSON, que o `jsonb`
  do Postgres recusa: o relatório não chegava a ser gravado no job. Agora `NaN`/`±Infinity` viram o texto
  declarado `"NaN"`/`"Infinity"`/`"-Infinity"` na única saída do relatório, e há teste que **atravessa o
  `jsonb` de verdade** (`psycopg2.extras.Json` → `SELECT %s::jsonb`) com a role da aplicação.
* **Teto de VOLUME no zip**, além da razão de 50× e da cota: `min(cota, 8 × tamanho do envio + 8 MiB)`. Antes,
  um envio de 1,4 MB escrevia 60 MB no diretório de trabalho (42× o enviado) sem violar regra nenhuma.
* **Coordenada impossível vira PERGUNTA.** Latitude de 7.400.000° (resposta de CRS errada num arquivo em
  metros) saía como aviso e o arquivo era aceito; agora é pendência de `crs`, com a sugestão de UTM.
  "Fora do Brasil" continua aviso.
* **Nenhum defeito do arquivo sai como traceback.** `rasterio._err.CPLE_AppDefinedError` não é
  `RasterioError` nem `ValueError` e escapava do `except`, devolvendo ao usuário a última linha do traceback
  em inglês. Três redes novas (por operação, no `_inspecionar` inteiro e no `main` do filho) e um
  `_sem_caminho()` que tira caminho absoluto do servidor de toda mensagem vinda do GDAL/SO.
* **Zip legítimo de 200 rasters volta a ser aceito.** O código abria todos os arquivos ao mesmo tempo e
  batia no `RLIMIT_NOFILE=64` a partir de ~55 arquivos, recusando envio válido com `Too many open files` e o
  caminho do servidor na mensagem. Agora abre **um de cada vez** (cabeçalho numa passagem, janela de prova
  noutra) e o teto subiu para 256 como folga.
* **`complex64`/`int64` declarados.** Continuam aceitos (o arquivo está íntegro), mas o relatório passa a
  trazer `info.tipo_convertivel: false`: nenhum COG ou tile serve esses tipos, e a recusa é da conversão.

Suíte dos dois arquivos juntos: **55 passed** (32 do construtor, 23 do adversário), `ruff` limpo,
`make sem-marcador` limpo.

Um SEGUNDO adversário atacou o mecanismo novo e achou mais dois furos (`tests/unit/
test_raster_validacao_adversario2.py`, 3 casos `xfail(strict=True)`), consertados neste turno:

* **A conferência do VRT passa a percorrer a árvore do XML, não o texto.** A expressão regular casava só
  `<SourceFilename>`; um `VRTWarpedDataset` põe a fonte em `<SourceDataset>` e uma isca `<SourceFilename>`
  dentro de comentário XML fazia a conferência antiga passar — o VRT enviado lia arquivo de fora do envio.
  Agora vale a árvore (`xml.etree`): os elementos que sempre apontam para dado (`SourceFilename`,
  `SourceDataset`, `Filename`, `Dataset`, `MaskFilename`…) e todo texto ou atributo com forma de caminho
  (absoluto, `../`, `~`, esquema remoto, extensão de dado) são resolvidos por `realpath` e têm de cair
  dentro do diretório do envio. Como a recusa é do XML, ela vale ANTES de o GDAL abrir qualquer coisa: o
  filtro de chamadas de sistema deixa de ser a única camada que segura a rede.
* **O ambiente do filho é lista de PERMISSÃO** (`ambiente_do_filho()`). A remoção nominal de `PLAT_DSN` e
  `PLAT_SECRET` deixava passar `PLAT_DSN_WORKER` (senha da role que escreve no banco) e
  `PLAT_GARAGE_ADMIN_TOKEN` para o processo que abre o arquivo hostil, e `AF_UNIX` não é bloqueado pelo
  filtro. Entram só `PATH`, `HOME`, `TMPDIR`, idioma, fuso, caminho de biblioteca, ambiente virtual e o que
  começa com `GDAL_`/`PROJ_`/`CPL_`/`OGR_`.

Prova: `tests/unit/test_raster_validacao_refutacao3.py` (10 casos escritos antes do conserto; 8 falhavam
contra o código anterior) e os 3 `xfail(strict=True)` do 2º adversário, agora sem marcador. Os quatro
arquivos de teste do item juntos: **77 passed**, `ruff` limpo, `make sem-marcador` e `make limites` limpos.
## turno 3, setembro de 2026 (itens L3-01-a-modelo-dado e L3-01-b-unidades: motor multicritério — modelo, proveniência e unidade de análise)

Migração `20260907T1206_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
## turno 3, setembro de 2026 (itens L3-01-a-modelo-dado e L3-01-b-unidades: motor multicritério — modelo, proveniência e unidade de análise)

Migração `20260907T1206_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
Migração `044_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
Migração `045_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
## turno 3, setembro de 2026 (itens L3-01-a-modelo-dado e L3-01-b-unidades: motor multicritério — modelo, proveniência e unidade de análise)

Migração `045_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
Migração `044_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
Migração `045_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
## turno 3, setembro de 2026 (itens L3-01-a-modelo-dado e L3-01-b-unidades: motor multicritério — modelo, proveniência e unidade de análise)

Migração `20260907T1206_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
## turno 3, setembro de 2026 (itens L3-01-a-modelo-dado e L3-01-b-unidades: motor multicritério — modelo, proveniência e unidade de análise)

Migração `045_amc.sql` (idempotente) cria sete tabelas em `plat`, todas com RLS por inquilino: `amc_modelo` (cabeça
editável) e `amc_modelo_versao` (toda versão que já existiu, imutável para a aplicação por gatilho), `amc_conjunto_unidade`
e `amc_unidade`, `amc_execucao` (proveniência congelada), `amc_fator_bruto` e `amc_resultado` — linhas por (execução,
unidade, fator), nunca uma coluna por fator. `amc_resultado` tem `CHECK` que impede unidade vetada de carregar número na
escala sem motivo escrito.

O modelo é um documento JSON validado contra `docs/esquemas/amc_modelo.v1.json` (Draft 2020-12) mais três regras que o
esquema não expressa; a versão dele é o sha256 do JSON canônico (`sort_keys=True`, `separators=(",", ":")`,
`ensure_ascii=False`, UTF-8). Modelo inválido devolve 422 `modelo_invalido` com TODAS as violações, cada uma com cláusula,
caminho e frase em português. `scripts/amc_hash_independente.py` recomputa o mesmo hash sem importar o módulo da
aplicação, tanto de um arquivo quanto de todas as linhas gravadas de um inquilino.

18 rotas em `/api/amc` (privilégio `analise.amc`, já no vocabulário): modelos (criar, listar, ler, editar, versões,
apagar, validar sem gravar), conjuntos de unidades (criar, listar, ler, unidades paginadas em GeoJSON, apagar) e
execuções (criar, listar, ler, resultados, apagar). Conjunto de grade nasce como job `amc.gerar_unidades`; conjunto de
feições é síncrono e preserva o id do usuário.

Medido (`tests/medidas/L3-01-b.json`, `PLAT_GRAVAR_MEDIDAS=1 pytest tests/api/amc/test_unidades.py -m lento`): grade
quadrada de 250 m sobre 2.000 km² = **32.374 células em 1,14 s** (teto do portão: 60 s), com desvio de **1,175 %** da
contagem teórica calculada por fora com shapely/pyproj (teto: 2 %). Grade de 100 m sobre 2.500 km² = **250.986 células
em 8,61 s**, em 3 faixas, ocupando **186 MB** de tabela e índices. A escala de 1 milhão de células, que no fecho do item
não tinha sido gerada (`/mnt/pgdata` a 99 %, 13 GB livres) e entrou como projeção linear marcada `EXTRAPOLADO`, foi
**GERADA depois**: o adversário do item mediu **1.000.175 células em 30,97 s** (desvio de contagem +0,201 %) com 43 GB
livres, e a re-medição depois do conserto do teto deu **989.334 células em 33,55 s** (+0,202 %). A projeção de 34,3 s
era conservadora: errou ~10 % para mais. A linha de bytes para 1 milhão continua marcada `EXTRAPOLADO` porque essa
ninguém mediu.
em 8,61 s**, em 3 faixas, ocupando **186 MB** de tabela e índices. **1 milhão de células NÃO foi gerado** — `/mnt/pgdata`
está a 99 % com 13 GB livres —; a projeção linear (34,3 s e ~741 MB) está gravada com `EXTRAPOLADO` no nome do campo.

Refutações escritas como teste: editar um modelo já executado cria versão nova e a execução antiga continua apontando
para a versão antiga, com o resultado inalterado (`test_refutacao_editar_modelo_executado_nao_muda_a_execucao_nem_o_resultado`);
área que cruza duas zonas UTM é aceita com CRS único e distorção de área DECLARADA na ficha, nunca escondida; contagem e
área total conferidas contra pyproj/shapely fora do banco; A não lê modelo, conjunto, execução nem resultado de B — 11
rotas por id direto e as seis tabelas pela role da aplicação com o contexto do outro inquilino.

Testes do item, contados com `pytest <os quatro arquivos> --collect-only -q` (a linha por arquivo do rodapé, que
conta CASO, não função — os `parametrize` expandem): `tests/unit/test_amc_esquema.py` 11 + `tests/unit/test_amc_crs.py`
8 + `tests/api/amc/test_modelo.py` 16 + `tests/api/amc/test_unidades.py` 12 = **47 casos** (38 funções `def test_`).
A entrada anterior dizia "45 testes novos" e o painel do laço dizia "207 testes": **os dois números estavam errados** e
nenhum dos dois saía de artefato nenhum — quem apontou foi o adversário do item. Depois do conserto de 06/09/2026 os
mesmos quatro arquivos somam **73 casos**, mais 40 do adversário e 22 da trava de reescrita de schema. A varredura
cruzada do OpenAPI cobre as 18 rotas novas (`tests/api/cruzado_casos.py`). ADR
`docs/adr/0016-motor-amc-modelo-e-unidades.md`.

### conserto depois da refutação (`laco/handoffs/T3/L3-01-CONSERTO.md`)

O laudo `laco/handoffs/T3/L3-01-ADVERSARIO.md` refutou o item em cinco frentes; as duas cláusulas centrais do portão
(imutabilidade do modelo já executado e isolamento entre inquilinos) resistiram. Consertado:

1. **Reescrita de schema fechada como classe** (`app/schema_ambiente.py`). Era só `execute` com `str`; passou a cobrir
   `str` e `bytes` em `execute`, `executemany`, `callproc`, `mogrify` e `copy_expert`, com `copy_from`/`copy_to`
   declarados fora de cobertura com a razão escrita. Três defeitos do mesmo tipo apareceram no mesmo dia: o `bytes` de
   `psycopg2.extras.execute_values` (que quebrava o conjunto do tipo `feicoes` fora do schema `plat`), as conexões de
   teste (commit `c311aa7`) e o `executemany` de `POST`/`PUT /api/papeis` (que fazia a prova de isolamento entre
   inquilinos rodar contra o schema de produção). `tests/unit/test_schema_ambiente.py` (22 casos) reprova se aparecer
   um ponto de entrada novo sem reescrita. `app/amc/unidades.gravar_feicoes` não usa mais `execute_values`.
2. **Erro de privilégio deixou de mentir** (`app/auth/comum._erro_de_privilegio`): o SQLSTATE 42501 por política de
   inquilino continua 403 `sem_permissao`; por falta de GRANT passa a 500 `privilegio_do_banco` — é erro de instalação
   do ambiente e o 403 mandava o operador investigar o lugar errado.
3. **Coerência interna da transformação** (`app/amc/esquema._violacoes_transformacao`): faixa invertida ou degenerada,
   número de notas incompatível com o de quebras, quebras e bandas fora de ordem crescente e função contínua sem
   parâmetro passavam pelo `allOf` do esquema (que descreve 4 dos 16 tipos), entravam no hash e só quebrariam no motor.
4. **`zonas_utm_cobertas`** (`app/amc/crs.py`) enumera todas as zonas do intervalo; de −60° a −42° declarava
   `[21, 22, 24]` e "cruza 3 zonas".
5. **Teto de unidades sobre a contagem real** (`app/amc/unidades.gerar_grade`): era conferido só sobre a estimativa
   área/área-da-célula e a célula de borda passava do teto (medido: 1.000.175 com o teto em 1.000.000). Passou do teto,
   as unidades são apagadas, o conjunto vai a `falhou` com o motivo e a tarefa levanta `FalhaDefinitiva`.
6. **JSON canônico**: chave repetida no corpo cru sai 422 `json_ambiguo` (era aceita em silêncio, com a primeira
   ocorrência descartada pelo parser), e os números são normalizados antes do hash — `3` e `3.0` são o mesmo número em
   JSON e davam versões diferentes. O documento gravado é o normalizado, para o hash continuar recomputável por fora
   com a regra simples. Medido: os 53 modelos que existem em `plat` são todos resíduo de teste (`zt-*` e "modelo de
   teste interno"), então a mudança de regra não invalida histórico de ninguém.

Os 12 `xfail(strict=True)` do adversário viraram prova permanente (as marcas saíram; nenhuma asserção foi afrouxada).
A migração `044_amc.sql` foi renumerada para `045_amc.sql` (a árvore principal publicou `044_uploads.sql`) e depois,
na junção com `master`, para **`20260907T1206_amc.sql`**: a numeração de três dígitos está FECHADA em 048 (ADR 0014,
`app.migracoes.ULTIMO_LEGADO`), e `045` já era usado por `045_geocodificador.sql` na árvore principal. Conferido antes
do renome: `045_amc.sql` nunca foi aplicado sob esse nome em nenhum ambiente (produção `plat`, homologação nem
qualquer schema de trilha `plat_t*`) — o renome é seguro, sem entrada órfã para limpar em `versao_migracao`.
45 testes novos (`tests/unit/test_amc_esquema.py`, `tests/unit/test_amc_crs.py`, `tests/api/amc/`), verdes; a varredura
cruzada do OpenAPI cobre as 18 rotas novas (`tests/api/cruzado_casos.py`). ADR
`docs/adr/0016-motor-amc-modelo-e-unidades.md`.

### conserto depois da refutação (`laco/handoffs/T3/L3-01-CONSERTO.md`)

O laudo `laco/handoffs/T3/L3-01-ADVERSARIO.md` refutou o item em cinco frentes; as duas cláusulas centrais do portão
(imutabilidade do modelo já executado e isolamento entre inquilinos) resistiram. Consertado:

1. **Reescrita de schema fechada como classe** (`app/schema_ambiente.py`). Era só `execute` com `str`; passou a cobrir
   `str` e `bytes` em `execute`, `executemany`, `callproc`, `mogrify` e `copy_expert`, com `copy_from`/`copy_to`
   declarados fora de cobertura com a razão escrita. Três defeitos do mesmo tipo apareceram no mesmo dia: o `bytes` de
   `psycopg2.extras.execute_values` (que quebrava o conjunto do tipo `feicoes` fora do schema `plat`), as conexões de
   teste (commit `c311aa7`) e o `executemany` de `POST`/`PUT /api/papeis` (que fazia a prova de isolamento entre
   inquilinos rodar contra o schema de produção). `tests/unit/test_schema_ambiente.py` (22 casos) reprova se aparecer
   um ponto de entrada novo sem reescrita. `app/amc/unidades.gravar_feicoes` não usa mais `execute_values`.
2. **Erro de privilégio deixou de mentir** (`app/auth/comum._erro_de_privilegio`): o SQLSTATE 42501 por política de
   inquilino continua 403 `sem_permissao`; por falta de GRANT passa a 500 `privilegio_do_banco` — é erro de instalação
   do ambiente e o 403 mandava o operador investigar o lugar errado.
3. **Coerência interna da transformação** (`app/amc/esquema._violacoes_transformacao`): faixa invertida ou degenerada,
   número de notas incompatível com o de quebras, quebras e bandas fora de ordem crescente e função contínua sem
   parâmetro passavam pelo `allOf` do esquema (que descreve 4 dos 16 tipos), entravam no hash e só quebrariam no motor.
4. **`zonas_utm_cobertas`** (`app/amc/crs.py`) enumera todas as zonas do intervalo; de −60° a −42° declarava
   `[21, 22, 24]` e "cruza 3 zonas".
5. **Teto de unidades sobre a contagem real** (`app/amc/unidades.gerar_grade`): era conferido só sobre a estimativa
   área/área-da-célula e a célula de borda passava do teto (medido: 1.000.175 com o teto em 1.000.000). Passou do teto,
   as unidades são apagadas, o conjunto vai a `falhou` com o motivo e a tarefa levanta `FalhaDefinitiva`.
6. **JSON canônico**: chave repetida no corpo cru sai 422 `json_ambiguo` (era aceita em silêncio, com a primeira
   ocorrência descartada pelo parser), e os números são normalizados antes do hash — `3` e `3.0` são o mesmo número em
   JSON e davam versões diferentes. O documento gravado é o normalizado, para o hash continuar recomputável por fora
   com a regra simples. Medido: os 53 modelos que existem em `plat` são todos resíduo de teste (`zt-*` e "modelo de
   teste interno"), então a mudança de regra não invalida histórico de ninguém.

Os 12 `xfail(strict=True)` do adversário viraram prova permanente (as marcas saíram; nenhuma asserção foi afrouxada).
A migração `044_amc.sql` foi renumerada para **`045_amc.sql`**: a árvore principal publicou `044_uploads.sql`.
45 testes novos (`tests/unit/test_amc_esquema.py`, `tests/unit/test_amc_crs.py`, `tests/api/amc/`), verdes; a varredura
cruzada do OpenAPI cobre as 18 rotas novas (`tests/api/cruzado_casos.py`). ADR
`docs/adr/0016-motor-amc-modelo-e-unidades.md`.

### conserto depois da refutação (`laco/handoffs/T3/L3-01-CONSERTO.md`)

O laudo `laco/handoffs/T3/L3-01-ADVERSARIO.md` refutou o item em cinco frentes; as duas cláusulas centrais do portão
(imutabilidade do modelo já executado e isolamento entre inquilinos) resistiram. Consertado:

1. **Reescrita de schema fechada como classe** (`app/schema_ambiente.py`). Era só `execute` com `str`; passou a cobrir
   `str` e `bytes` em `execute`, `executemany`, `callproc`, `mogrify` e `copy_expert`, com `copy_from`/`copy_to`
   declarados fora de cobertura com a razão escrita. Três defeitos do mesmo tipo apareceram no mesmo dia: o `bytes` de
   `psycopg2.extras.execute_values` (que quebrava o conjunto do tipo `feicoes` fora do schema `plat`), as conexões de
   teste (commit `c311aa7`) e o `executemany` de `POST`/`PUT /api/papeis` (que fazia a prova de isolamento entre
   inquilinos rodar contra o schema de produção). `tests/unit/test_schema_ambiente.py` (22 casos) reprova se aparecer
   um ponto de entrada novo sem reescrita. `app/amc/unidades.gravar_feicoes` não usa mais `execute_values`.
2. **Erro de privilégio deixou de mentir** (`app/auth/comum._erro_de_privilegio`): o SQLSTATE 42501 por política de
   inquilino continua 403 `sem_permissao`; por falta de GRANT passa a 500 `privilegio_do_banco` — é erro de instalação
   do ambiente e o 403 mandava o operador investigar o lugar errado.
3. **Coerência interna da transformação** (`app/amc/esquema._violacoes_transformacao`): faixa invertida ou degenerada,
   número de notas incompatível com o de quebras, quebras e bandas fora de ordem crescente e função contínua sem
   parâmetro passavam pelo `allOf` do esquema (que descreve 4 dos 16 tipos), entravam no hash e só quebrariam no motor.
4. **`zonas_utm_cobertas`** (`app/amc/crs.py`) enumera todas as zonas do intervalo; de −60° a −42° declarava
   `[21, 22, 24]` e "cruza 3 zonas".
5. **Teto de unidades sobre a contagem real** (`app/amc/unidades.gerar_grade`): era conferido só sobre a estimativa
   área/área-da-célula e a célula de borda passava do teto (medido: 1.000.175 com o teto em 1.000.000). Passou do teto,
   as unidades são apagadas, o conjunto vai a `falhou` com o motivo e a tarefa levanta `FalhaDefinitiva`.
6. **JSON canônico**: chave repetida no corpo cru sai 422 `json_ambiguo` (era aceita em silêncio, com a primeira
   ocorrência descartada pelo parser), e os números são normalizados antes do hash — `3` e `3.0` são o mesmo número em
   JSON e davam versões diferentes. O documento gravado é o normalizado, para o hash continuar recomputável por fora
   com a regra simples. Medido: os 53 modelos que existem em `plat` são todos resíduo de teste (`zt-*` e "modelo de
   teste interno"), então a mudança de regra não invalida histórico de ninguém.

Os 12 `xfail(strict=True)` do adversário viraram prova permanente (as marcas saíram; nenhuma asserção foi afrouxada).
A migração `044_amc.sql` foi renumerada para **`045_amc.sql`**: a árvore principal publicou `044_uploads.sql`.

## turno 3, setembro de 2026 (item L0-08-d-ldap: LDAP/Active Directory como provedor de login externo)

Módulo isolado `app/auth/ldap.py` (`ldap3` 2.9.1, puro Python, sem dependência de sistema — só a venv):
`POST /api/login/ldap` faz bind de serviço opcional (ou anônimo) contra o diretório do inquilino, busca o
usuário por um filtro sempre ESCAPADO (`escape_filter_chars`, RFC 4515 — a refutação do item pedia
`*)(uid=*`; neutralizado), exige exatamente 1 resultado, faz bind do usuário com a senha informada (nunca
com senha vazia: recusada antes de abrir qualquer conexão) e mapeia `memberOf` para um dos 4 perfis da
plataforma via `plat.provedor_ldap.mapa_grupo_perfil` (maior alcance quando mais de um grupo mapeado bate).
Provisiona o usuário local automaticamente (`plat.ldap_provisionar`, migração `025_provedor_ldap.sql`) sem
nunca gravar a senha do LDAP e sem nunca sobrescrever uma conta `origem='local'` homônima (`409
login_em_uso_local`); depois do bind validado, **reaproveita** `app.auth.rotas_login._abrir_sessao` para
abrir a sessão — zero duplicação da lógica de cookie/política/evento do login local, e
`app/auth/rotas_login.py` não foi tocado (só `app/main.py` ganhou o registro da rota). Administração por
inquilino (privilégio `org.integracoes`, já reservado pela ADR 0002): `GET/PUT /api/org/ldap` (nunca devolve
a senha de bind, só cifrada em repouso — AES-GCM sob `PLAT_SECRET`) e `POST /api/org/ldap/importar` (grupo do
diretório → N usuários locais desabilitados, ativados no primeiro login — a opção do portão). Força bruta
contra o bind: contador em memória por processo, reaproveitando `bloqueio_tentativas`/`bloqueio_minutos` da
política do PRÓPRIO inquilino (cobre também login que ainda não existe localmente).

Servidor de teste: contêiner Docker `glauth` efêmero (imagem 98,9 MB medida; disco/RAM conferidos antes —
12 GiB livres, ~2,5 GiB disponíveis), nunca em produção (`tests/ldap_fixture/`), 4 usuários sintéticos (um
por perfil + um dedicado ao teste de colisão) + 1 conta de serviço + 4 grupos. Decisões e o formato de DN
medido (glauth usa `ou=` no RDN de grupo, não `cn=`) em `docs/adr/0008-ldap-ad.md`.

14 testes em `tests/api/ldap/test_login_ldap.py` (marcados `lento`), todos verdes: bind OK cai no perfil
certo (3 perfis); senha errada recusada; senha vazia nunca tenta bind; injeção de filtro neutralizada; grupo
não mapeado recusa com `403`; colisão com conta local recusa com `409`; **diretório fora do ar não derruba o
login local** (para o contêiner, LDAP responde `503`, login local no mesmo processo responde `200`, religa);
6ª tentativa errada de bind bloqueia como o login local (`423`); importação em massa cria desabilitado e
ativa no primeiro login; admin nunca vê a senha de bind; perfil inválido recusado; teste cruzado A/B
(`org.integracoes` de um inquilino nunca é o de outro); sem privilégio toma `403`. Latência medida:
mediana de 5 logins completos (bind de serviço + busca + bind do usuário + provisionamento + sessão) =
**12,2 ms** (`tests/medidas/L0-08-d-ldap.json`, `mediana_5_logins_ldap_ms`).

A suíte INTEIRA (não só a do item) apontou 3 lacunas que o teste próprio não cobria, todas corrigidas antes do
commit: (1) `CREATE FUNCTION` concede `EXECUTE` a PUBLIC por padrão — as 3 funções novas ganharam `REVOKE
EXECUTE ... FROM PUBLIC` explícito na própria migração, mesmo padrão da 003; (2) `tests/api/eventos_esperados.py`
e `tests/api/cruzado_casos.py` são listas fechadas por rota (o portão P6 do laço, teste cruzado A→B automático
gerado do OpenAPI) — as 3 rotas novas ganharam entrada nas duas.

**Incidente durante a construção (não escondido):** o contador de bloqueio local do superadmin `plataforma`
foi atingido por colisões de código TOTP entre rodadas de teste concorrentes desta sessão contra a MESMA
conta compartilhada por todas as trilhas do turno, e travou `make check-rapido` inteiro (503 erros em cascata
por causa da fixture `sessao_plat`, autouse). Diagnosticado (o segredo TOTP cacheado em
`tests/credenciais_totp.txt` estava desatualizado em relação ao do banco) e corrigido pelo mesmo caminho que
o `install.sh` já documenta (reset do 2FA da conta + remoção do cache; a suíte religou o 2FA sozinha na
rodada seguinte, novo segredo cacheado) — sem editar nenhum teste alheio. `tests/api/ldap/conftest.py`
também passou a sobrescrever a fixture `limpeza_de_residuos` só para o próprio diretório, para os testes de
LDAP nunca mais dependerem de `sessao_plat` (conta mais disputada da árvore).

### Commits

| sha | mensagem |
|---|---|
| (este) | LDAP/Active Directory como provedor de login externo por inquilino (item L0-08-d-ldap) |

## turno 3, setembro de 2026 (item L0-05-e-justica-entre-inquilinos: rodízio por inquilino na fila)

A fila escolhia o próximo job por ordem global (prioridade, `agendado_para`, `criado_em`), o que com um worker
é uma fila serial: no turno 2 mediu-se um job de 0 s de um inquilino esperando 10 minutos atrás de dois jobs de
300 s de outro. A migração `db/migracoes/20260906T2110_jobs_justica_inquilino.sql` põe o TURNO do inquilino
(`max(iniciado_em)` daquele inquilino, `NULLS FIRST`) como primeira chave de ordenação do `plat.job_pegar`:
prioridade e ordem de criação passam a ordenar a fila DENTRO do inquilino, e o rodízio alterna os inquilinos.
Com 2 inquilinos e 1 worker, um job curto de A espera no máximo o job de B que já está rodando — medido com
2 × 300 s de B (espera de A: 0,5 s) e repetido com 50 × 300 s de B (0,2 s), em ambos os casos 1 job de B
iniciado antes de A. Nada mais do `job_pegar` muda: chave em série, cota de simultâneos por inquilino e filtro
de pesado seguem iguais, e a cota foi remedida (dois jobs do mesmo inquilino em série com cota 1, e inquilinos
diferentes em paralelo). Índice parcial novo `(tenant_id, iniciado_em)` para o cálculo do turno.

A leitura de job devolve `posicao_fila` para job pendente (posição na fila do inquilino; nula fora de
`pendente`) e a tela Tarefas escreve esse número na coluna de progresso. Não existe posição global: entre
inquilinos a ordem é decidida pelo rodízio a cada retirada. Limite honesto: com mais de um worker a justiça é
estatística, não exata (cada worker decide por uma foto do instante do seu `SELECT ... SKIP LOCKED`).

Provas: `tests/api/jobs/test_jobs_justica.py`, `tests/unit/test_jobs_posicao_fila_tela.py`, medidas em
`tests/medidas/L0-05-e-justica-entre-inquilinos.json`, decisão em
`docs/adr/20260907T2109-justica-entre-inquilinos-na-fila.md`.

## turno 3, setembro de 2026 (item L0-05-e-worker-em-container: worker da fila em contêiner)

Segundo executor da fila de jobs (ADR 0003), em contêiner Docker, ao lado da unidade systemd `plat-worker`
(nunca no lugar dela — os dois podem apontar para o mesmo banco): `deploy/Dockerfile.worker` (python:3.12-slim-
bookworm, sem `--system-site-packages`; ver ADR 0010 seção 2 para por quê), `deploy/docker-compose.worker.yml`
(`network_mode: host` — Postgres/Garage só escutam 127.0.0.1, ADR 0010 seção 3; segredos pelo mesmo arquivo que
o `LoadCredential=` do systemd usa, lidos como root e soltos via `setpriv` antes do worker rodar uma linha) e
`deploy/entrypoint-worker.sh`. `install.sh` ganhou a flag opcional `--worker-container` (seção h4), sem mudar o
comportamento padrão.

Achado ao testar de verdade (não estava previsto no pedido): `app/jobs/filho._pdeathsig()` checava
`os.getppid() == 1` para decidir "o pai morreu" — certo fora de contêiner, **sempre falso dentro de um
contêiner sem `--init`, onde o próprio worker roda como PID 1**: 100% dos jobs falhavam, imediatamente, sem
log nem traceback. Corrigido comparando contra o PID medido ANTES do fork (`worker.py._lancar()` repassa),
correto nos dois ambientes; testado ponta-a-ponta (job real via API concluído na 1ª tentativa pelo contêiner,
antes: falhava as 3 tentativas sempre). `app/jobs/filho.limite_memoria_cgroup_mb()` (novo) lê o teto do cgroup
v2 pelo caminho real do processo (`/proc/self/cgroup`, nunca hardcoded) — serve tanto o `MemoryMax=` da
unidade systemd quanto o `mem_limit=` do contêiner sem distinção de código — e `preparar_ambiente()` nunca
deixa o `RLIMIT_DATA` de um filho passar do teto do cgroup menos uma reserva de 96 MB; testado com
`mem_limit: 300m` (clamp de 256→204 MB, com `AVISO` gravado no `job_log`) e com `2g` (sem clamp, regressão da
produção de hoje coberta). `GET /saude` do worker ganhou o campo `cgroup_memoria_max_mb`.

Achado colateral, documentado mas não corrigido aqui (fora do escopo do item, risco de colisão com duas outras
trilhas editando os mesmos arquivos neste turno): `app/catalogo/tipos.py`/`miniatura.py` importam
`jsonschema`/`Pillow`, nunca declarados em `requirements.txt` nem em `deploy/pacotes_apt.txt` — só funcionam no
host por uma instalação pip global de outro produto da máquina. A imagem do contêiner trava as duas versões
medidas (`jsonschema==4.26.0`, `Pillow==12.2.0`); o conserto do `requirements.txt` do host fica para o item
dono de `app/catalogo`.

9 testes de unidade novos (`tests/unit/test_jobs_filho_cgroup.py`): aritmética pura do clamp + 1 teste ponta-a-
ponta em subprocesso isolado (`resource.setrlimit(RLIMIT_DATA)` só baixa o teto no processo que o chama — dois
testes no mesmo processo do pytest quebrariam o segundo). A unidade systemd `plat-worker` de produção nunca foi
parada nem reiniciada para este item. Detalhe completo: ADR `docs/adr/0010-worker-em-container.md`,
`ARQUITETURA.md` seção 5.8, handoff `laco/handoffs/T3/L0-05-e-worker-container.md`.

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: linguagem de expressão própria — PARCIAL, só o núcleo)

Núcleo da linguagem de expressão própria (equivalente ao Arcade da Esri para os perfis popup, rótulo, cálculo,
restrição, validação, indicador — L2_CONCEITO.md decisão C6): gramática publicada em EBNF (`docs/EXPRESSAO.md`),
analisador recursivo descendente escrito à mão (mesmo padrão de `app/consulta/where_ast.py`, sem
`eval`/`exec`/`compile`), AST tipada exportável/reimportável em JSON, e **dois avaliadores que têm de concordar
byte a byte**: `app/expressao/avaliador_py.py` (Python, servidor) e `web/js/expressao/avaliador.js` (JavaScript
puro, sem `eval`/`new Function`, roda tanto no navegador quanto no Node de teste).

18 funções (texto: `Maiuscula`/`Minuscula`/`Concatenar`/`Texto`; número: `Arredondar`/`Absoluto`/`Minimo`/
`Maximo`/`Numero`/`Potencia`; data — convenção epoch-ms UTC, sem tipo dedicado, para os dois avaliadores não
dependerem de biblioteca de fuso horário nenhuma das duas línguas: `AgoraUTC`/`Ano`/`Mes`/`Dia`/`DiferencaDias`;
nulo: `SeNulo`/`EhNulo`; condicional: `Se`), semântica de nulo de três valores (como SQL), curto-circuito em
`Se`/`SeNulo`/`&&`/`||` (o ramo não escolhido nunca avalia — provado forçando `10 / 0` no ramo descartado).

Dois algoritmos escritos à mão, idênticos nos dois avaliadores (onde Python e JavaScript mais divergem por
padrão): formatação de número → texto (inteiro sem ponto, decimal até 6 casas sem zero à direita) e
arredondamento meio-para-longe-de-zero (nem o `round()` banker's do Python, nem o `Math.round` do JavaScript).

Segurança (refutação do item-pai): texto/tokens/argumentos acima do limite, string de 10 MB, cadeia longa do
mesmo operador (profundidade medida na ÁRVORE inteira, não só na descida do parser — uma cadeia
`1+1+1+...+1` é montada em laço, não recursão, e por isso não disparava o contador de descida do parser
sozinho; achado corrigido nesta mesma passagem), parênteses/unários/chamadas profundamente aninhados, limite
de passos (10⁵) e de tempo (500 ms servidor / 50 ms cliente) sob carga, campo fora da lista branca do
`contexto` (nunca `getattr` de objeto do chamador) — todos com erro nomeado, nunca `RecursionError` nem
travamento. `ast_de_json` (reimportação da AST gravada) ganhou os MESMOS limites de profundidade/aridade que o
texto, depois de identificado que um JSON fabricado à mão contornaria os dois guarda-corpos do lado texto.

Prova de equivalência: 41 vetores (`tests/expressoes/vetores.json`, portão pede ≥ 20) avaliados nos dois
avaliadores e comparados byte a byte (`tests/unit/test_expressao_equivalencia.py`, runner Node
`tests/expressoes/executar_js.mjs`); `docs/EXPRESSAO.md` conferido contra o código dos dois lados
(`tests/unit/test_expressao_doc_sincronizada.py` — toda função e todo código de erro documentado existe no
código, e vice-versa).

**Fora desta passagem** (item grande; fica para quando a integração existir): tipos lista/dicionário/geometria,
`FeatureSetByRelationship`, os ≥ 40 funções e ≥ 200 vetores da hipótese cheia, fuso horário de usuário,
formatação pt-BR, compilação para expressão MapLibre e para SQL, integração com popup/rótulo/formulário/regra
de atributo (`L5-11`), tabela de paridade completa com o Arcade function reference. Ver
`laco/handoffs/T3/L2-10-c-expressao.md`; medidas em `tests/medidas/L2-10-c-expressao.json`.

## turno 3, setembro de 2026 (item L2-11-c-rota-matriz-isocrona: rota, matriz e isócrona — PARCIAL)

Serviço de localização sobre um OSRM isolado de teste: `POST /api/rota` (dois pontos → geometria GeoJSON,
distância, duração, instruções resumidas em português — `app/rede/instrucoes.py`, vocabulário fechado de
`maneuver.type`/`maneuver.modifier` da doc OSRM v5.24), `POST /api/matriz` (N origens × M destinos, teto
N×M configurável por `PLAT_ROTA_MATRIZ_MAX`, padrão 625) e `POST /api/isocrona` (ponto + minutos → polígono
de alcance: grade de pontos ao redor do centro, tempo de cada um por `/table` do OSRM, casco côncavo por
`shapely.concave_hull` sobre os pontos alcançáveis — o OSRM não tem serviço de isócrona nativo, doc
testada só lista route/table/nearest/match/trip/tile). Escopo de token novo `rota:usar`.

Dado: recorte de Guarulhos **isolado, novo, ≤ 50 MB** (`osrm/guarulhos.osm.pbf`, 1,6 MiB, 210.065 nós,
42.720 vias, mesma área do mapa-base `L2-01-a`), construído sem tocar nenhum dos 4 contêineres OSRM já
ativos na máquina para outras frentes (portas 5000-5003) — novo contêiner `plat-osrm-guarulhos` em
**127.0.0.1:5010**, unidade systemd própria (`deploy/plat-osrm-guarulhos.service`, decisão de manter vivo:
memória medida ~40 MB, mesmo padrão dos outros 4). `osmium extract` no `.pbf` regional inteiro (135 MB, 17,5
milhões de nós) **morreu de OOM sob teto próprio três vezes** (RAM disponível ~2,5 GB, swap cheio) sem
afetar o sistema (`ulimit -v` conteve cada tentativa); o caminho que funcionou foi `ogr2ogr` (mesmo padrão
já medido seguro no `L2-01-a`, RSS ~300 MB) extraindo só as vias com `highway=*`, seguido de uma síntese
própria de `.osm` XML (`osrm/gerar_osm_xml.py`, deduplicando nó por coordenada) — proveniência completa em
`osrm/PROVENIENCIA.md`.

**Escopo entregue nesta trilha (ARQUITETO+BACKEND) é MENOR que o item completo do backlog**: pgRouting,
`/mais-proximo`, `/ajuste-de-trajeto` (match), perfis pé/bicicleta, NAServer Esri-compatível
(`solve`/`solveServiceArea`/`solveClosestFacility`), teste de 1.000×1.000, e a validação de 200 pontos
amostrados contra a isócrona de 15/30/45 min **não foram construídos** — ficam para a continuação do item
(ver handoff `laco/handoffs/T3/L2-11-c-rota.md`). Testado com 9 casos em `tests/api/rede/test_rota.py`
(rota real Guarulhos↔GRU, matriz 5×5, teto de matriz, isócrona de 10 min não vazia e conferida contra a
própria API de rota, autenticação, perfil/coordenada inválidos) — todos verdes contra o OSRM real via
`TestClient` (sem tocar o `plat-api` ao vivo, que outras trilhas do turno ainda editavam).

## turno 3, setembro de 2026 (item L2-01-a-basemap-local-pmtiles: mapa-base local em PMTiles)

Primeiro item de mapa real do produto: MapLibre GL JS 4.7.1 (já vendorizado) mais o protocolo `pmtiles-4.5.0.js`
(novo, BSD-3-Clause) lendo um PMTiles local (`web/dados/basemap/guarulhos.pmtiles`, 18,4 MiB, OSM ODbL 1.0,
proveniência em `web/dados/basemap/PROVENIENCIA.md`) servido pelo próprio nginx do appliance por Range HTTP —
sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro. Tela `/mapa`, tela cheia, dentro do sistema de
identidade visual "instrumento" (`class="instrumento"` no `<body>`, cores copiadas da paleta escura de
`web/estilo/tokens.css`): navegação, escala, coordenadas do cursor e seletor de camada base (uma opção hoje).
Detalhe em `MANUAL.md` seção 13; medidas em `tests/medidas/L2-01-a-basemap-local-pmtiles.json`.

**Incidente registrado (não escondido):** a primeira tentativa de extrair o recorte de OSM usou `osmium extract`
(índice de nós inteiro em memória) com RAM disponível já abaixo do guardrail de 4 GB do laço; o processo foi
morto pelo OOM killer do sistema, que na mesma varredura também matou um backend do Postgres, travando o cluster
14 minutos em `deactivating` (mesmo padrão de incidentes anteriores da casa). Remediado com o procedimento já
documentado (`pg_ctlcluster 16 main stop -m immediate --skip-systemctl-redirect`); o banco voltou consistente
(23 migrações aplicadas, nenhuma perdida) em cerca de 40 s e todos os serviços dependentes reconectaram sozinhos.
A extração foi refeita com `ogr2ogr` (streaming, GDAL, pico de RSS medido ~500 MB por chamada), sem repetir o erro.

### Commits

| sha | mensagem |
|---|---|
| (este) | Mapa-base local em PMTiles (item L2-01-a-basemap-local-pmtiles): MapLibre + PMTiles servido pelo nginx, tela `/mapa`, e2e |

## turno 3, setembro de 2026 (itens L7-14-instalacoes-apt-desta-linha · L7-16-assinatura-pacote)

### O que entrou — pacotes apt e assinatura de release (ADR 0007)

- `deploy/pacotes_apt.txt`: lista fechada de 7 pacotes dpkg que o `plat` já exige ou vai exigir em curto prazo
  (`python3-uvicorn`, `python3-psycopg2`, `python3-venv`, `python3-cryptography`, `gdal-bin`, `python3-gdal`,
  `python3-magic`); `install.sh` passo "e2" instala de forma idempotente só o que faltar (`dpkg -s` antes e
  depois do `apt-get install -y`). `tests/unit/test_pacotes_apt.py` confere a lista e a instalação real.
  `postgresql-16-pgrouting`/`pgstac`/FDW de terceiro ficam de fora de propósito (item `L7-14-extensoes-fdw`,
  dono próprio); `ezdxf`/LibreDWG ficam de fora porque a decisão de usá-los (ADR 0005 seção 12.4, D23) ainda
  não foi tomada.
- `scripts/assinar_pacote.sh` + `scripts/verificar_pacote.sh` (com `scripts/plat_assinatura.py`): assinatura e
  verificação Ed25519 de pacote de atualização via `cryptography`. Gera o par de chaves na primeira execução
  (privada fora do repositório, `/etc/plat/chaves/…` ou `$HOME/.config/plat/chaves/…`; pública registrada em
  `deploy/chaves_publicas_release.txt`, versionado no git). Funciona sem rede nos dois lados. Rotação de chave
  com período de dupla chave: a pública nova só é aceita depois de distribuída numa versão assinada com a
  antiga (`tests/unit/test_assinatura_pacote.py` prova a recusa cedo e a aceitação tarde). `gitleaks` não é
  pacote apt nesta distribuição; a cláusula "chave privada nunca no git" foi provada com uma varredura direta
  do histórico (`git log --all -p`) à procura do cabeçalho PEM.

## turno 3, setembro de 2026 (itens L0-04-d-formatos-base · L0-04-b-inspecao · L0-04-c-tabela-camada · L0-04-ingest-vetor · L0-05-e-worker-em-container: conserto dos achados FUNCIONAIS do adversário G3)

O ataque adversarial do grupo G3 (`laco/handoffs/T3/ataque-g3-ADVERSARIO.md`) refutou os cinco itens acima.
Esta passagem consertou a parte FUNCIONAL (formatos, rotas, camadas, medidas, portão do contêiner); os
achados de recurso partilhado (chave de trinco global, schema `d_<slug>` sem prefixo de instalação, cota que
só sobe, justiça da fila, orçamento de SSE) são de outra trilha (`wt/partilha`).

- **9 formatos do portão viravam 4**: a instalação anunciava só shapefile/gpkg/geojson/csv. O GDAL do host
  (3.8.4) já tinha driver para os 9 do L0-04-d e para os 4 a mais do L0-04-b (GML, FlatGeobuf, DXF, File
  Geodatabase zipada) — nada precisou ser instalado. `app/ingestao/formatos.py` passa a anunciar 13, com o
  DWG declarado à parte em `FORMATOS_QUE_DEPENDEM_DE_LICENCA` (decisão do dono, item L0-04-e).
- **`GET /api/importacoes/formatos` respondia 404**: estava declarada depois de `GET /api/importacoes/{id}`,
  e o roteador do Starlette casa na ordem de declaração — o parâmetro livre engolia a palavra "formatos". A
  rota literal passou para antes; `tests/unit/test_rotas_sombreadas.py` reprova qualquer rota nova do
  repositório inteiro que caia na mesma armadilha.
- **Pacote com várias camadas perdia todas menos a primeira, em silêncio**: `inspecionar.py` usava
  `camada = camadas[0]`. `_inspecionar_camada` roda agora para TODAS as camadas; a proposta lista cada uma
  em `proposta["camadas"]`, pergunta qual entra quando há mais de uma e avisa quais ficam de fora.
- **CSV de 300 colunas e 0 linhas terminava em `proposta` sem aviso nenhum**: camada com zero feições agora
  sai com aviso explícito citando o número de campos.
- **Inquilino com hífen no slug nunca importava**: `plat.tenant.slug` aceita hífen e dígito inicial desde a
  migração 002; `plat.camada_schema_garantir` (migração 029) recusava os dois. Migração
  `20260906T1607_slug_ingestao_reconciliado.sql` reconcilia o alfabeto (a criação do inquilino é a
  autoridade); `tests/api/ingestao/test_slug_alfabeto.py` exercita as duas funções ao vivo em vez de repetir
  as regras escritas à mão.
- **Zip malformado devolvia 500 em vez de 422**: `ZipSuspeito` e `ConteudoNaoCorresponde` eram classes irmãs
  sem mãe comum, e a rota só capturava a segunda. As duas passam a herdar de `ArquivoRecusado`, que é o que
  a rota captura.
- **As duas medidas nomeadas pelos portões não existiam**: `tests/api/ingestao/test_medidas_100k.py`
  (marcado `lento`) gera 100 mil feições derivadas de dado aberto já no repositório (disco não permitia
  baixar dado novo), mede `tempo_inspecao_s` (portão do L0-04-b, ≤ 5 s) e `tempo_import_100k_s` (portão do
  L0-04-c, ≤ 60 s) e grava em `tests/medidas/L0-04-b-inspecao.json` e `tests/medidas/L0-04-c-tabela-camada.json`.
- **L0-05-e estava `entregue` com o portão ainda como "a fixar pelo arquiteto"**: o texto do portão de
  verdade ficou escrito na seção 10 do ADR 0010. De caminho, a imagem do worker em contêiner (base
  `python:3.12-slim-bookworm`) tinha GDAL 3.6.2, sem `ogrinfo -json` — todo job de inspeção cairia nesse
  executor. A base passou a `python:3.12-slim-trixie` (GDAL 3.10.3) e o Dockerfile ganhou um portão de
  construção que reprova sem `-json` ou sem qualquer um dos 12 drivers.
- **Ponta de `master` que não importava**: entre dois commits, `app/main.py` importava
  `app.auth.rotas_convites`, que não tinha entrado no commit — um `git clone` não subia, embora a árvore de
  trabalho de quem programou funcionasse (arquivo presente no disco, só não versionado).
  `tests/unit/test_app_versionada.py` fecha isso por dois caminhos: fumaça (a aplicação importa e tem mais
  de 100 rotas) e todo módulo `app.*` carregado ao importar `app.main` tem de estar em `git ls-files`.

Sete testes de `tests/api/adversario_g3/test_g3_ingestao.py` perdem o `xfail(strict=True)` porque o defeito
que reproduziam foi consertado (nenhum teste apagado, nenhuma asserção enfraquecida). O teste do slug com
hífen, que escrevia as duas regras à mão e por isso nunca poderia virar prova, passa a ler o CHECK de
`plat.tenant` e o corpo de `plat.camada_schema_garantir` ao vivo e comparar os dois. Os dois achados de
recurso partilhado (schema sem prefixo de instalação, cota que só sobe) continuam `xfail`: são de outra
trilha.

### Commits

| sha | mensagem |
|---|---|
| `1409076` | Ingestão vetorial: 13 formatos, todas as camadas do arquivo e recusa explícita no lugar do silêncio |
| `b24fefa` | Worker em contêiner com GDAL que serve à ingestão, e o portão do item escrito |
| `072270c` | Troca as marcas dos testes do adversário que passaram a valer, e faz o do slug ler a regra viva |
### Galeria de mapas base por inquilino (item L2-01-e-mapas-base, migração `20260907T1649_mapa_base.sql`, ADR `20260907T1800`)

O mapa base deixou de ser fixo no código (item L2-01-a) e virou item do catálogo: tipo `mapa_base` em
`plat.tipo_item`, validado por JSON Schema na própria migração, com `creditos` e `termos_de_uso` do item
carregando a atribuição e a licença da fonte. Quatro fontes abertas de instalação (`app/mapas_base/semear.py`,
licença de cada uma em `docs/DADO_DEMO.md`): PMTiles vetorial local por Range HTTP, raster do OpenStreetMap
pelo proxy da casa, satélite Sentinel-2 por um TiTiler externo e "nenhum" (fundo cor). Rotas novas
`GET /api/mapas-base`, `POST /api/mapas-base/instalar` (idempotente, não sobrescreve edição do admin),
`POST /api/mapas-base/{id}/tornar-padrao` (troca o padrão em uma transação; índice único parcial como rede de
última linha) e `GET /api/mapas-base/osm/{z}/{x}/{y}.png`.

O proxy do OSM **não lê host de lugar nenhum**: recebe só `z/x/y`, valida os três contra a faixa do slippy map
e escolhe o host de uma tupla fixa em `app/limites.py` — proxy aberto é impossível por construção, não por
lista de bloqueio; a busca ainda passa por `app.conexao.seguranca.buscar_seguro`. Cache é arquivo em disco
(`var/cache/mapa_base_osm/`) com teto e poda do mais antigo, como a política de uso do `tile.openstreetmap.org`
exige. No navegador, trocar de mapa base troca o `style` inteiro do MapLibre: `web/js/mapa/mapa.js` guarda as
camadas operacionais, reaplica no `styledata` seguinte e restaura centro/zoom com `jumpTo`; três paletas
próprias (claro/escuro/cinza) para a fonte vetorial. Regra `@media print` em `web/mapa.css` mantém a
atribuição visível no papel (o layout de impressão completo é o item L2-12, ainda pendente).

Medido (`tests/medidas/L2-01-e.json`): PMTiles instalado 19.181.534 bytes; pior caso de disco da galeria
124.039.134 bytes (PMTiles + teto do cache do proxy), contra teto interino de 154.857.600 —
**a decisão D27 do dono segue aberta, então o teto é o do repositório, não um número dele**. Testes:
25 de unidade (esquema e proxy), 13 de API, 4 casos no cruzado de RLS. As cláusulas de e2e com captura
ficaram **pendentes**: a base por trilha não tem nginx (`PLAT_URL_PUBLICA` inválida de propósito), então
`tests/e2e/test_mapas_base.py` está escrito e salta — roda em homologação ou instalação real.

## 0.2.0 — turno 2, setembro de 2026 (itens L0-02-tenant-auth: identidade e acesso · L0-05-jobs: fila de trabalhos)

O produto passa a ter login com senha e segundo fator, sessão, usuários, grupos, papéis, tokens de serviço, log de
acesso e eventos por inquilino, superadmin em inquilino técnico, e uma fila de trabalhos com worker em processo
filho, progresso em tempo real, cancelamento, sobrevivência a reinício, agendas por cron e tela Tarefas. Nota: o
arquivo `VERSAO` ainda diz `0.1.0`; o gerente o sobe para `0.2.0` no fechamento do turno, junto com o `git_sha` de
`/saude` (o serviço no ar é `abbb03d`).

### O que entrou — identidade e acesso (L0-02, ADR 0002, migrações 003 e 009)

- Migração `003_identidade_acesso`: 46 privilégios com teto por perfil, papéis personalizados, colunas novas de
  `usuario` (segundo fator, bloqueio, pendências, origem), histórico de senha, grupos e membros, `evento` e
  `log_acesso` particionados por mês, inquilino técnico `plataforma` com 2FA obrigatório, funções `SECURITY DEFINER`
  reescritas com checagem de inquilino (`contexto_confere`) e superadmin por hash de sessão (`plataforma_operador`),
  `REVOKE EXECUTE FROM PUBLIC` em todas as funções e no privilégio padrão do schema.
- `app/auth/`: política de senha por inquilino (`tenant.config.auth`, padrões e faixas em `app/limites.py`), hash
  fantasma para tempo constante, bloqueio 5/15 min no banco, TOTP de biblioteca padrão com segredo cifrado
  (AES-GCM) e 8 códigos de recuperação, cookie `plat_sessao` com hash no banco e CSRF por `SameSite=Lax` + JSON +
  `Origin`, token de serviço `plat_…` com escopos, restrições de origem e IP, rotação de 24 h e revogação imediata,
  middleware que grava `plat.log_acesso` (bytes contados no fluxo) e redige segredos do journal, `X-Plat-Inquilino`
  só de leitura para o superadmin.
- 54 rotas do ADR mais `DELETE /api/plataforma/inquilinos/{id}` (migração 009: `tenant_apagar`), todas com
  `x-auth`, `x-privilegio`, `response_model` e evento declarado; erros no formato `{erro, mensagem, detalhe, req_id}`
  (`app/erros.py`); páginas em `app/paginas.py`.
- Sete telas sobre uma base reutilizável (`web/js/base/`: api, estado, i18n, dom, 6 componentes, layout;
  `style.css` tema único; DOMPurify 3.4.14 vendorizado com sha256): `/entrar`, `/conta`, `/admin/usuarios`,
  `/admin/grupos`, `/admin/papeis`, `/admin/tokens`, `/admin/log`; barra lateral por privilégio; página inicial com
  atalhos quando há sessão.
- Instalador: `plataforma/admin` semeado com superadmin, `demo`/`demo2` sem; 2FA reiniciado a cada instalação;
  partições de 4 meses; `plat_limites.conf` (10 r/min por IP em `/api/login` e `/api/login/2fa`); `Referrer-Policy`
  em toda `location`; limpeza de resíduos `zt-*` em `dev`; `python3-cryptography` conferido; `qrcode==8.2`.
- Testes: 5 unitários novos, 17 arquivos em `tests/api/` (varredura cruzada A→B gerada do OpenAPI com digest md5
  de todo o dado de B, força bruta, tempo constante, TOTP, token, funções seguras por `psql`, log de acesso por
  `User-Agent` único, eventos e privilégios declarados, inquilino temporário), 9 e2e playwright com captura mais
  `test_i18n_cru.py` (chave de tradução crua na tela reprova).

### O que entrou — fila de trabalhos (L0-05, ADR 0003, migrações 004, 006, 007, 008 e 010)

- Migração `004_jobs`: `job`, `job_log`, `worker`, `agenda`, RLS, gatilhos de estado final e de NOTIFY, funções do
  worker, cotas (`cota_jobs_simultaneos` 2, `cota_jobs_dia` 1.000, `cota_agendas` 50), schema `plat_trabalho`.
- `app/jobs/`: registro de tipos por decorador (`@tarefa`), worker com conexão própria, `LISTEN/NOTIFY`,
  `SKIP LOCKED`, heartbeat, "1 pesado por vez" por advisory lock, processo filho com `PR_SET_PDEATHSIG`,
  `RLIMIT_DATA`, BLAS em 1 thread e códigos de saída por causa, cancelamento cooperativo com escalonamento
  SIGTERM 30 s / SIGKILL +10 s, retentativa 2/4/8 s, teto de 5 reinícios, agendas por cron com fuso (croniter
  6.2.4) e relógio no worker, periódico `jobs.expurgo`, SSE `GET /api/jobs/{id}/eventos` com `Last-Event-ID`, 13
  rotas `/api/jobs*` e `/api/agendas*`, `/saude` com `fila` e `servicos.worker`, 6 tipos de diagnóstico.
- Unidade `plat-worker` (`Restart=always`, `KillMode=mixed`, `OOMPolicy=continue`, `MemoryMax=2G`), passo `h2` do
  instalador, chaves `PLAT_WORKER_*`, `PLAT_JOBS_DIR`, `PLAT_JOB_MAX_REINICIOS`, `PLAT_GPU_*`, `PLAT_DSN_WORKER`.
- Tela `/tarefas` (lista ao vivo por SSE com reserva por consulta, detalhe com log ao vivo, cancelar, repetir,
  baixar log, agendas) sobre a base da identidade; e2e `test_tarefas.py` com 5 provas e 3 capturas.
- Correções por achados do testador, cada uma com teste:
  - `006_jobs_transicoes` (commit `ad2ea29`): a role `plat_app` conseguia por SQL levar um job `pendente → rodando
    → concluido` com resultado forjado. Agora existe a role `plat_worker`, única com `EXECUTE` nas funções que
    mudam estado; `plat_app` perdeu `UPDATE` em `plat.job` (cancela por `job_cancelar`, reporta por
    `job_progresso`); gatilho `job_transicao` exige o GUC `via_worker` que só as funções do worker ligam;
    `jobs_expurgar` apaga marcadores e passos órfãos (1.371 acumulados antes).
  - `008_jobs_tentativa` (commit `90d03c0`): reinício e ceifa desfazem o incremento de `tentativa` feito por
    `job_pegar`; a retomada volta ao mesmo número (tentativa 1, reinícios 1). Testes de agenda robustos a resíduo
    de outras sessões.
  - `010_jobs_gatilhos_execute` (commit `7824846`): as três funções de gatilho da 004 nasceram com `EXECUTE` para
    `PUBLIC` e `plat_app` pelo privilégio padrão da 001; revogado (achado de `test_funcoes_seguras`).
  - `007_jobs_eventos` e integração com a identidade (commit `ffedc05`): `x-auth`/`x-privilegio` nas rotas da
    fila, eventos declarados, casos cruzados das 17 rotas.
  - `012_jobs_identidade_worker` e `013_jobs_execute_reafirma` (commit `9be9c6a`, depois do passe do cronista ter
    começado): identidade do worker por processo e ceifa só por heartbeat; `EXECUTE` do worker reafirmado contra o
    `GRANT ON ALL FUNCTIONS` da 011. Sem veredito do testador e do adversário neste turno.

### Medições (`tests/medidas/L0-02-tenant-auth.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| rotas no OpenAPI / com caso cruzado | 74 / 73 | `len(paths×methods)` de `docs/openapi.json`; casos em `tests/api/cruzado_casos.py` (o 74º caso entrou em `abbb03d`) |
| varredura cruzada viva: rotas, chamadas, 2xx indevidos, linhas de B alteradas | 73, 411, 0, 0 | `varredura_viva.py` do testador contra `/api/openapi.json` vivo, 6 vetores por rota; md5 das linhas de B como `postgres` |
| login (senha certa) | mediana 128,6 ms | 3 `POST /api/login` no TestClient (inclui pbkdf2 600.000) |
| login pela URL pública | 142,9 · 141,7 · 146,0 ms | 3 `POST /api/login` individuais (nginx + TLS) |
| login: 20 chamadas direto no uvicorn | mediana 129,2 · p95 145,4 · máx 156,6 ms | `testador_login_ms_20_uvicorn` |
| tempo constante (inexistente × senha errada) | 122,3 × 123,6 ms (TestClient); 121,7 × 123,2 ms (testador) | mediana de 4 e de 6 `POST /api/login` |
| autenticação por token | 3,0 ms (TestClient); 2,5 ms (testador) | mediana de `GET /api/eu` com Bearer menos `GET /api/versao` |
| custo de gravar `log_acesso` | 0,66 ms | mediana de 30 `GET /api/eu` com e sem `log_registrar` |
| revogação de token até o 401 | 0,01 s (TestClient) · 0,02 s (URL pública) · 6,2 ms (e2e) | `DELETE /api/tokens/{id}` e chamada seguinte |
| limite por IP no nginx | 10 × 401 depois 429 | 25 `POST /api/login` em 15 s de outro IP |
| RLS | 22 de 22 tabelas e partições com `tenant_id` | `pg_class × pg_attribute` |
| funções `SECURITY DEFINER` sem `PUBLIC` | 51 de 60 funções; 0 com `PUBLIC` | `pg_proc × aclexplode` |
| memória do `plat-api` | 122.781.696 bytes | `systemctl show plat-api -p MemoryCurrent` |
| páginas prontas (chromium) | login 54,3 · conta 37,8 · 2FA 9,7 · usuários 59,4 · grupos 60,8 · papéis 58,7 · tokens 78,9 · log 73,7 ms | `goto` até `body[data-pronto=1]` |
| e2e de identidade | 9 aprovados, 0 falhas | `make e2e` 16:03-16:27 UTC |
| marcadores de pendência / nomes de cliente | 0 / 0 | grep com a expressão do driver; grep da lista do testador |

### Medições (`tests/medidas/L0-05-jobs.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| job de 5 min | 300,4 s; 62 eventos `estado`; heartbeat ≤ 5,0 s; latência heartbeat → cliente 0,065 s | `prova.progresso(300 s, 60 passos)` pelo SSE (`test_jobs_progresso.py`) |
| primeiro evento SSE pela URL pública | 0,022 s | `GET https://plat.iagrointel.com/api/jobs/{id}/eventos` até o primeiro `estado` |
| cancelamento cooperativo | 0,426 s (API) · 0,24 s (tela) | `POST .../cancelar` até `estado = cancelado`; clique até `tr[data-estado=cancelado]` |
| cancelamento de tarefa que ignora a flag | 40,5 s | pedido até SIGTERM (30 s) + SIGKILL (10 s) |
| retomada após `systemctl restart plat-worker` | 1,0 s | job volta a `pendente`/`rodando` com `reinicios = 1` (`test_jobs_reinicio.py`) |
| vazão de jobs vazios | 2.135,9 por min (2 workers, 3 processos) | 100 `prova.progresso(duracao_s=0)` (`test_jobs_fila.py`); só a unidade com 1 processo: 1.613,7 por min (`40_testes.md`, seção 6) |
| RSS do processo pai do worker | 40.556 kB | `GET :8153/saude` após o job de memória |
| tela Tarefas pronta | 142,9 ms | `goto('/tarefas')` até `body[data-pronto=1]` |
| linha nova sem recarregar | 10,3 s | `POST /api/jobs` até `tr[data-id]` |
| valores distintos de progresso na linha | 2 | leituras de `.c-progresso .valor` num job de 60 s |

### Vereditos

- **L0-02-tenant-auth: adversário PASSA em 2 rodadas** (`refutacao.json`). Rodada 1, não destrutiva, 16 famílias de
  ataque no serviço vivo: varredura A→B em 40 rotas por id (40 × 404, 0 cross 200), 8 listas sem vazamento, spoof
  por cabeçalho (403), token de B age só como B, 0 função com `PUBLIC`, GUC forjado (`so_superadmin`), força bruta
  (6ª = 423), TOTP e recuperação sem replay, tempo existente × inexistente (delta 2,7 ms em 60 amostras), fixação e
  encerramento de sessão, CSRF (403/415), escalada a superadmin (422/404), token (escopo, revogado, IP, não se
  perpetua), segredos fora do git e do journal, 0 marcador, 0 nome de cliente. Rodada 2, com reinstalação do zero
  (schemas e roles apagados, `install.sh` em 50 s, 63 s fora do ar): invariantes recriados, login real pelo
  navegador, nova varredura cruzada de 34 rotas sem cross 200. Gerente (`99_veredito.md`): todas as 7 cláusulas do
  portão passam; item **parcial** só porque P3 (suíte inteira verde) dependia da trilha B em curso e P9 (esta
  documentação) estava pendente; vira `entregue` no fechamento do turno se a suíte fechar verde.
- **L0-05-jobs: testador com correções 006/008/010 por achados** (`40_testes.md`, em escrita no fim deste passe).
  Cláusulas do portão medidas: job de 5 min com progresso em tempo real, cancelamento, sobrevivência a
  `systemctl restart` e a `kill -9` (nunca `concluido` sem execução inteira: marcador só no último passo; 5 × `kill -9`
  → `falhou`), 1 worker por padrão com limite de RAM declarado, tela Tarefas por inquilino com RLS varrida em 15
  rotas, testes automatizados. **Achado 2 aberto** (acrescentado ao portão em `estado.json`): um worker homônimo
  fora do systemd (nome padrão = host) fez `job_ceifar` devolver os jobs do worker vivo, que foram reexecutados do
  zero; o portão passa a exigir identidade de worker única por processo e ceifa só por heartbeat vencido, com teste
  de dois workers. O adversário do L0-05 ainda não rodou; o item foi devolvido a `pendente` pelo driver às 17:30 UTC
  (sessão do gerente interrompida). A correção entrou no commit `9be9c6a` (17:52 UTC), sem veredito ainda:
  migração `012_jobs_identidade_worker` (identidade `<nome-base>:<pid>`, ceifa só por heartbeat vencido do job e do
  worker dono, assinatura por nome removida; a partida não devolve nada por nome e um `kill -9` no pai é recolhido
  pela ceifa em até cerca de 90 s; `worker.py`, `test_jobs_identidade.py` com dois workers do mesmo nome-base) e
  `013_jobs_execute_reafirma`, motivada por outra regressão achada depois da reinstalação destrutiva: a
  `011_catalogo` (em construção) faz `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app` e devolvia a
  `plat_app` as funções do worker, inclusive `via_worker_ligar`, desfazendo a 006. Testador e adversário ainda não
  conferiram a correção; até lá o estado do item é o descrito acima.
- Ressalvas registradas: `auth_login`, `auth_sessao` e `auth_token` são pré-contexto por chave-segredo (o portão as
  cita como "checam o inquilino"; a checagem acontece na função seguinte, `auth_sessao_criar`); "expiração
  configurável" é por `tenant.config.auth`, não por `.env`; `X-Forwarded-For` só é confiável atrás do nginx
  (herdado ao L7-03); job devolvido 5 vezes mostra "tentativa 0"; com 1 processo a fila é serial e sem justiça
  entre inquilinos.

### Commits do turno

| sha | mensagem |
|---|---|
| `0985a11` | ADR 0002: identidade e acesso (T2, trilha A) |
| `1540c84` | ADR 0003: fila de jobs (T2, trilha B) |
| `1668d76` | Tela Tarefas (L0-05-jobs, trilha B, frontend): lista ao vivo por SSE, detalhe com log, agendas e e2e |
| `cab32da` | Fila de jobs (L0-05, trilha B): migração 004, registro de tipos, worker plat-worker, agendas e tipos de diagnóstico |
| `52d7a3b` | API da fila (L0-05): /api/jobs, /api/agendas, eventos SSE, páginas /tarefas, /saude com fila, testes de API |
| `674798d` | Unidade plat-worker e instalador (L0-05): passo h2, chaves PLAT_WORKER_* no .env, conferência de worker vivo |
| `57c24a5` | ADR 0004: catálogo de conteúdo (T2, preparação do L0-03) |
| `431ba0c` | Instalador (L0-05): inquilinos de demonstração com cota_jobs_dia = 100000 |
| `6a00645` | Base do front (L0-02-tenant-auth, trilha A): tema único, módulos ES de base, componentes, layout, i18n e DOMPurify |
| `50d587d` | Telas de identidade (L0-02-tenant-auth, trilha A, frontend): entrar, minha conta, usuários, grupos, papéis, tokens, log |
| `757f0d3` | e2e do L0-02-tenant-auth (playwright, chromium): login, 2FA, conta, usuários, grupos, papéis, tokens, log |
| `9be4a04` | Identidade (L0-02, trilha A, 1/4): migração 003, política, TOTP, escopos, redação, contrato de erro, limites |
| `2ffe8b4` | Identidade (L0-02, trilha A, 2/4): sessão, token, middleware de log_acesso, 54 rotas do ADR 0002, páginas |
| `b5c336b` | Instalador (L0-02): admin de plataforma com superadmin, demos sem, limite por IP nos logins, partições, cryptography |
| `ae6ec45` | Testes do portão L0-02: varredura cruzada A→B gerada do OpenAPI, força bruta, token, funções seguras, log_acesso |
| `441069c` | ADR 0005: ingestão vetorial (T2, preparação do L0-04) |
| `38430b2` | Medidas do item L0-02-tenant-auth (backend) |
| `ad2ea29` | Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores |
| `ffedc05` | Integração T2 da fila com a identidade (L0-05 × L0-02): x-auth/x-privilegio, eventos e casos cruzados |
| `12b2c2e` | Medidas do testador para L0-02-tenant-auth (T2, 40) |
| `90d03c0` | Fila (L0-05): reinício não consome tentativa (008) e testes de agenda robustos a outras sessões |
| `7c62831` | Correção T2 do front (L0-02): componentes re-traduzem quando o dicionário chega; chaves conta.apos_pendencia e nav.tarefas_desc; e2e contra chave crua |
| `7824846` | Fila (L0-05): funções de gatilho da 004 sem EXECUTE para PUBLIC e plat_app (010) |
| `abbb03d` | Correção T2 do L0-02 (achados do testador): apagar inquilino, fixtures sem resíduo, log por chamada, Referrer-Policy em toda location |
| `41c1dd9`, `a06ca71` | Tela Conteúdo e e2e do L0-03-catalogo (outra trilha, em curso; documentada no passe do cronista desse item) |
| `7cd0327` | Documentação do turno 2 (cronista): MANUAL, ARQUITETURA, CHANGELOG 0.2.0, PARIDADE, README |
| `9be9c6a` | Correção T2 (2) da fila (L0-05, achado do testador): identidade do worker por processo e ceifa só por heartbeat (012, 013) |
| (este) | Documentação do turno 2, passe 2: absorve 012/013 e o commit 9be9c6a |

## 0.1.0 — turno 1, setembro de 2026 (item L0-01-repo: fundação)

Primeira versão. O repositório instala, sobe um serviço, responde saúde por HTTPS e isola inquilinos no
banco. Não há login, catálogo, camada nem mapa.

### O que entrou

- API FastAPI `plat-api` em 127.0.0.1:8150 (2 workers uvicorn, `MemoryMax=1G`), com `GET/HEAD /saude`
  (200 só com banco atualizado; 503 em `desatualizado`/`erro`), `GET/HEAD /api/versao`, página inicial
  `/` e `/api/docs`.
- nginx em `https://plat.iagrointel.com` com `X-Robots-Tag: noindex, nofollow` e
  `Strict-Transport-Security` em toda `location`, `/static/` servido do disco com `no-store`,
  redirecionamento de HTTP para HTTPS.
- Schema `plat` no banco `iagro_sat`: role `plat_app` (sem BYPASSRLS, sem posse), tabelas
  `versao_migracao`, `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS em toda tabela com
  `tenant_id` (USING e WITH CHECK); 9 funções `SECURITY DEFINER` para autenticação, sessão, token e log;
  inquilinos de demonstração `demo` e `demo2`.
- Migrações `001_fundacao` e `002_identidade`, aplicadas por `db/migrar.sh` com sha256 por arquivo,
  uma transação por arquivo e recusa (código 3) de arquivo aplicado que tenha mudado.
- `install.sh` idempotente (extensões, migrações, `.env` 600 com senha da role e `PLAT_GIT_SHA`, linha
  no `pg_hba.conf`, venv com `PYTHONNOUSERSITE=1` e prova de importação sem o diretório do usuário,
  administradores de demonstração com senha por stdin, unidade systemd, nginx com troca atômica
  preservando certbot, certbot na primeira vez, conferência pública de 200 + noindex + HSTS).
- `requirements.txt` com toda dependência da aplicação e da suíte fixada com `==` (`fastapi 0.138.0`,
  `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv 1.2.2`, `httpx 0.28.1`, ...); `uvicorn` e
  `psycopg2` do sistema, conferidos por nome de pacote dpkg.
- `make check`: ruff, varredura de marcador de pendência (inclui os `.md`), 81 testes rápidos (unit,
  instalador, dependências, vendor, contrato de `/saude`, `/api/docs`, banco, migrações, RLS, cabeçalhos
  HTTP reais) e 1 e2e playwright com captura; `make medidas` e `make vendor`.
- Front mínimo em módulos ES sem bundler; MapLibre GL JS 4.7.1 (ainda não carregado por nenhuma tela) e
  Swagger UI 5.32.15 (serve `/api/docs` sem CDN) em `web/vendor/`, versão no nome, sha256 e licença em
  `VERSOES.txt`; `favicon.svg`.
- Documentos: `docs/adr/0001-fundacao.md` (13 seções), `docs/openapi.json` gerado e comitado,
  `ARQUITETURA.md`, `MANUAL.md`, este arquivo, `README.md`; `docs/PARIDADE.md` só com cabeçalho (nenhuma
  capacidade de usuário para comparar ainda).

### Medições (`tests/medidas/L0-01-repo.json`, rodada 2 do testador sobre `8ffe950`, commit `3083366`; instalação e RLS da rodada 1)

| medida | valor | comando |
|---|---|---|
| instalação do zero (schema e role apagados) | 6,24 s | `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` (rodada 1) |
| reinstalação do zero pelo adversário sobre `8ffe950` | 9,66 s | `refutacao.json`, rodada 2, ataque 1 |
| instalação com `.env`, credenciais e linha do pg_hba também apagados | 9,14 s | idem; o script imprimiu `.env criado`, `linha acrescentada`, `tests/credenciais.txt criado` |
| instalação repetida em seguida | 4,69 s | idem; 0 migrações novas, 1 linha no pg_hba, NRestarts=0 |
| testes coletados / rápidos passando / e2e passando | 82 / 81 / 1 | `venv/bin/pytest --collect-only -q` (unit 31, api 50, e2e 1); `make check` |
| `make check` | rc=0, 2,86 s | `/usr/bin/time -f %e make check` |
| árvore suja depois de `make check` | 0 arquivos | `git status --short` |
| marcadores de pendência no código e nos documentos | 0 linhas | grep com a expressão do driver em `app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md` |
| nomes de cliente/parceiro no repositório | 0 linhas | `grep -rniE` com a lista do testador, fora de venv/.git/vendor |
| `/saude` pela URL pública | HTTP 200, `git_sha` = HEAD `8ffe950516f5`, 2 migrações, 0 pendentes | `curl -sSI` e `curl -sS https://plat.iagrointel.com/saude` |
| `X-Robots-Tag` com noindex | 11 de 11 rotas | `curl -sI` em API, estático, docs e 404 |
| `Strict-Transport-Security` | 11 de 11 rotas HTTPS; ausente no 301 de http | `curl -sI` |
| `/api/docs` sem URL externa; `make vendor` | 0 URLs; 4 arquivos OK | leitura do HTML; `sha256sum -c` |
| latência `/saude` pública, conexão nova (mediana / p95) | 19,8 / 21,0 ms | 20 × `curl -s -o /dev/null -w %{time_total}` |
| latência `/saude` pública, conexão reaproveitada (mediana / p95) | 1,9 / 2,8 ms | 20 URLs numa invocação de curl |
| memória do serviço (cgroup) | 88,5 MB | `systemctl show plat-api -p MemoryCurrent` |
| tabelas com `tenant_id` e RLS | 4 (mais `tenant` por `id`) | `pg_class × pg_attribute` |
| linhas visíveis a `plat_app` sem contexto | 0 | `psql` como `plat_app` sem `set_config` |
| página pronta / primeira pintura (chromium) | 62,6 / 48 ms | e2e `tests/e2e/test_saude_pagina.py` |

### Adversário (`laco/handoffs/T1/refutacao.json`): veredito final PASSA (rodada 2, HEAD `8ffe950`)

Rodada 1 (sobre `3b53c24`): PARCIAL. A refutação literal resistiu (apagar schema e role, reinstalar em
6,46 s, `/saude` 200 com noindex, 58 testes verdes), mas caíram: dependências `fastapi`, `starlette`,
`pydantic`, `python-dotenv` fora do `requirements.txt` (máquina nova não subia); senha de demonstração
em argumento de `sudo` (ficava no journal); documentos de topo vazios; sem `Strict-Transport-Security`;
Swagger de CDN externo; promessas do ADR sem código.

Rodada 2 (sobre `8ffe950`): PASSA. Reinstalação do zero em 9,66 s, 82 testes verdes, `/saude` 200 com
noindex e HSTS; os quatro achados reatacados e fechados com reprodução: aplicação importa e roda sem o
diretório do usuário (`PYTHONNOUSERSITE=1` na unidade viva); 0 senha no journal durante e depois da
reinstalação; ADR e código batem (`make medidas`, vendor com versão no nome, `PLAT_GIT_SHA` gravado,
`requirements.txt` completo, gravação em `log_acesso` adiada explicitamente ao L0-02); HSTS só no bloco
443 e `/api/docs` com 0 requisição externa em chromium real. Ressalvas que não derrubam o item: prova de
"máquina nova" por simulação; funções `SECURITY DEFINER` sem checagem de inquilino (regra para o L0-02);
caminhos do `install.sh` só lidos (`.env` inexistente, certbot emitindo, `nginx -t` reprovando).

### Commits

| sha | mensagem |
|---|---|
| `a1d0c20` | Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0) |
| `904a849` | Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes |
| `b22761e` | Medidas do item L0-01-repo regeneradas sobre o commit 904a849 |
| `ca61ea1` | Medidas do item L0-01-repo assinadas pelo testador (turno T1) |
| `3b53c24` | P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1 |
| `7092755` | Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0 |
| `8ffe950` | L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA |
| `3083366` | Medidas do item L0-01-repo, rodada 2 do testador sobre 8ffe950 |
| (este) | Documentação atualizada sobre 8ffe950 e 3083366 (passe curto do cronista) |

## L4-01-c-importador-bdgd (07/09/2026, turno 4)
- Job `rede.importar_bdgd` (`POST /api/rede/{id}/importar-bdgd`): pacote `.gdb.zip` local dentro de `PLAT_BDGD_RAIZ`, progresso, contrato de dado ANTES da carga (30 de 61 expectativas do YAML da casa avaliadas; as de nível transformador declaradas não avaliadas), contagem conferida contra o arquivo, unidade do COMP pela razão Σ COMP / Σ geodésico, três órfãos contados e listados.
- `_gravar_dispositivos` em lote (duas consultas por dispositivo viraram dois `execute_values`): tira ~17 mil idas ao banco da cooperativa de teste.
- `comprimento_m` da aresta passa a ser o COMP convertido (o comprimento do ATIVO); o geodésico fica em `atributos`. Cláusula "km de MT = Σ COMP ± 0,1 %" verdadeira por construção.
- Migração `20260907T1330_rede_importacao_contrato.sql`: colunas `contrato`, `comp`, `orfaos` (jsonb) em `plat.rede_importacao`.
- `inspecionar`/`sha256_gdb` aceitam arquivo único (GPKG) além de pasta `.gdb`.
## turno 4, setembro de 2026 (item L2-10-d-regras-de-atributo: regras de atributo por camada)

Sobre a porta única de escrita (L2-03-a, mesclada aqui) e a linguagem de expressão (L2-10-c): `dados.regras` da
camada (esquema v4) com regras de **cálculo** (campo alvo = expressão, gatilho por campo, ordem, encadeamento),
**restrição** (booleana; falso = 422 com código e mensagem configurados) e **validação** (job `camadas.validar`
grava erros em `e_<hex16>` e cria a camada de erros no catálogo), mais **campos virtuais** só-leitura avaliados na
leitura. Motor em `app/regras/motor.py` (ciclo detectado na configuração: `regra_ciclo` com o caminho); rotas
`GET/PUT /api/camadas/{id}/regras`, `POST /api/camadas/{id}/validar`, `GET /api/camadas/{id}/feicoes`,
`GET /api/camadas/{id}/erros`; `em_massa` no corpo de edição pula regras marcadas `excluir_em_massa`. Testes:
`tests/unit/test_regras_motor.py` (12) e `tests/api/test_regras_atributo.py` (validação de 100 mil como job com
N conferido por SQL; 1.000 edições com 3 regras contra sem regras, medido). ADR
`docs/adr/20260908T0740-regras-de-atributo.md`; paridade contra "attribute rules" (Pro/hosted 11.4) em
`docs/PARIDADE.md`. Fora: compilação para SQL (L2-10-e), WFS-T (não existe em master), tela.
## turno 8, setembro de 2026 (item L5-01-c-widgets-dado: widgets de dado do app sobre camada no servidor)

Os widgets de dado do app deixam de depender de a fonte estar inteira no navegador: a Vista ganha uma API assíncrona
(página, total, agregação, histograma, valores únicos, ids do filtro, exportação) que em fonte de camada delega ao
FeatureServer do L2-04 (`where` traduzido do CQL2-JSON, `orderByFields`, `resultOffset`, `outStatistics` por grupo,
`returnDistinctValues`, `returnIdsOnly`, `geometry`) e em fonte embutida/arquivo roda em memória. Tabela 2.0.0
(página/ordenação/contagem no servidor, exportar CSV e GeoJSON do filtro ativo), gráfico 2.0.0 (barra, linha, pizza,
histograma, dispersão; Chart.js 4.5.1 vendido, agregação no servidor), filtro 2.0.0 (texto, valores únicos,
intervalo, data), e os novos `lista` (cartões com modelo e expressão), `consulta` (atributo + espacial), `selecao`
(por atributo, tudo, inverter), `info-feicao` e `adicionar-dado` (GeoJSON temporário em fonte de memória). Filtros
dinâmicos de origens diferentes se combinam por AND na vista. Medido: p95 por página com 100 mil pontos e as 5
agregações comparadas com SQL direto em `tests/medidas/L5-01-c-widgets-dado.json`. Paridade: `docs/PARIDADE.md`
("Widgets de dado do aplicativo", 15 widgets Data centric do Experience Builder); ADR `20260908T1500-widgets-de-dado`.

## turno 8, setembro de 2026 (item L5-07-fontes-vistas-mensagens: modelo de dado do app e barramento de mensagens)

O documento `app` (esquema 3) ganha `fontes` (item do catálogo, caminho do servidor ou embutida; campos tipados),
`vistas` (fonte + filtro CQL2-JSON + seleção + ordenação + campos) e `mensagens` (gatilho {origem, evento} → ações
[{alvo, ação, parâmetros, relação}]) com os 8 gatilhos do Experience Builder e as ações de dado (filtrar,
selecionar, limpar_*) e de widget (zoom, pan, piscar, popup, abrir, fechar, definir_parametro). Regra de relação
dos Dashboards entre fontes diferentes (atributo com tipos que casam, ou espacial); sem relação é recusado no
construtor com mensagem e na API (422 `modelo_invalido`) — o mesmo validador em JS e Python, provado igual.
Barramento EventTarget com corte de ciclo em uma volta (aviso `ciclo_cortado`); estado de seleção e filtros na URL
por vista; widgets de tabela, gráfico (novo) e mapa (renderizador SVG da vista) ligados a vistas; painel "Dados e
mensagens" no construtor. Medido em node com 10 mil feições em memória: latência gatilho→ação p95 em
`tests/medidas/L5-07-fontes-vistas-mensagens.json` (com carga e RAM ao lado). e2e: seleção no mapa filtra tabela e
gráfico (2 vistas da mesma fonte) e a tabela de outra fonte por relação de atributo; URL reabre igual; recusa no
construtor com captura. Tabela gatilhos × ações contra a doc do Experience Builder em `docs/PARIDADE.md`. ADR
`20260908T1050-fontes-vistas-mensagens.md`. Ramo contém `wt/cx506` (L5-06) por merge.
## turno 3, setembro de 2026 (item L2-13-b-replicas-sincronizacao: réplicas para trabalho desconectado)

`POST /api/replicas` monta um recorte declarado de camadas (filtro por camada na linguagem `where` do
FeatureServer, extensão em Polygon 4326) e enfileira o job `replicas.criar`, que escreve um GeoPackage por
`ogr2ogr` — o mesmo formato que o QField lê. Dentro do pacote, além de uma tabela por camada, vão
`plat_sync` (fid, globalid e versão de cada feição), `plat_replica` (geração do servidor por camada),
`plat_dominio` (valores de domínio dos campos) e, opcionalmente, `plat_anexo` (metadado dos anexos).

`POST /api/replicas/{id}/sincronizar` sobe as mudanças do aparelho pela porta única de escrita do L2-03-a,
resolve versão divergente pela política escolhida na criação (`servidor_vence`, `cliente_vence`,
`pergunta` — conflito é sempre relatado, mesmo quando resolvido), baixa o que o servidor mudou desde a
geração do cliente e avança a geração. Repetir o mesmo lote com a mesma chave de idempotência devolve a
mesma resposta e aplica zero.

Sem tabela de rastreio nova: o relógio é o `id` de `plat.feicao_historico` (item L2-03-edicao), que já grava
por gatilho toda escrita, inclusive o DELETE. A migração acrescenta só o índice
`ix_feicao_historico_desde` e as três tabelas da réplica.

Medido: 100 mil feições exportadas em 1,97 s (pacote de 32,8 MB), com carga de 1 min em 7,86 de 12 núcleos.
Validade da réplica 30 dias, menor que a retenção declarada do rastreio (45) — invariante provado em teste,
porque o contrário devolveria mudanças a menos sem erro nenhum.

Nenhum privilégio novo (`campo.coletar`, mais `feicoes.editar` para sincronizar) e nenhuma dependência nova.
Detalhe e as limitações honestas: `docs/adr/20260908T1231-replicas-e-sincronizacao.md` e a seção 23 do
`MANUAL.md`.
## turno 8, setembro de 2026 (item L0-07-f-console-plataforma: console do superadmin, um portal com N inquilinos)

Tela `/plataforma` e rotas `/api/plataforma` completas sobre o console mínimo da 003/029: listagem com uso
(usuários ativos/cota, bytes/cota, itens/cota, jobs pendentes/rodando, último acesso), criação com admin de
senha temporária e cotas iniciais, detalhe com administradores, cotas alteráveis pelo operador, suspensão com
mensagem para os membros (login, sessão viva e token recebem **503 `inquilino_suspenso` com a mensagem**, nada
apagado; reativar devolve a mesma sessão), desligamento do 2FA de um administrador de inquilino (só admin, nunca
em `plataforma`, sessões do alvo caem), fila de jobs agregada com workers e a trilha de eventos da plataforma.
Superadmin continua resolvido só pelo hash da sessão (`plat.plataforma_operador`); as 10 rotas `/api/plataforma`
do OpenAPI respondem 404 a sessão comum, token e anônimo e 401 a cookie forjado (`tests/medidas/
L0-07-f-console-plataforma.json`). Slugs reservados numa função só (`plat.slug_reservado`, inclui os caminhos de
página da raiz); slug fora do CHECK = 422 (a API valida com a mesma expressão do CHECK; teste compara as duas).
e2e sem nginx (`tests/e2e/frente_estatica.py`): criar `demo3` pela tela, admin de demo3 entra pela tela de login,
suspender com mensagem, 503 com a mensagem no navegador (captura), reativar; página pronta em 152 ms. ADR
`20260908T0124-console-da-plataforma.md`. Fica para o L0-07-c: contador simétrico de bytes no lugar de
`sum(plat.arquivo.bytes)`.
## turno 8, setembro de 2026 (item L0-07-e-relatorios: relatórios do admin como job, CSV, agendamento por e-mail, painel Atividade)

Cinco relatórios do inquilino (`relatorios.gerar`, `app/relatorios/tarefas.py`): membros (perfil/papel, tipo de
conta, último acesso, itens, grupos), itens (tipo, dono, tamanho, compartilhamento, acessos em 30 dias pelo log
de acesso, última modificação), grupos, atividade (eventos por tipo e dia) e uso (série diária do que master já
mede; a série do L0-07-c substitui quando entrar). CSV com cabeçalho documentado (`GET /api/relatorios/tipos` =
`CABECALHOS`), gravado no armazenamento de objetos como a exportação do catálogo e baixado por
`GET /api/relatorios/{id}/csv` (404 para outro inquilino, 403 sem `org.exportar`). Limites declarados iguais aos
da Esri: 12 meses (422), 10 mil linhas (corte marcado `truncado`), 1 pedido por tipo por hora (429).
Agendamento diário/semanal/mensal vira `plat.agenda` com cron e entrega por e-mail do link assinado (7 dias) ao
solicitante pelo SMTP do inquilino. Painel `/admin/atividade`: totais, 10 itens mais acessados, eventos por dia e
por tipo, acessos por dia (SVG sem biblioteca), pedidos e agendas na mesma tela. Medido na trilha, worker em
subprocesso (`tests/medidas/L0-07-e-relatorios.json`): relatório de itens com 10.001 itens em **0,6 s** de job
(0,63 s de parede, carga 4,39, 7 GB livres); página pronta em 107 ms. Dado pessoal: e-mail só de domínio
corporativo configurado; sem CPF no modelo (teste procura). ADR `20260908T0155-relatorios-do-admin.md`.
## turno 4 (líder 5), setembro de 2026 (item L7-11-b-appliance-sem-internet: e2e inteiro atrás de um proxy de captura, 0 pedido a host externo)

`tests/operacao/proxy_captura.py` (proxy HTTP em fluxo, com túnel CONNECT só para a própria instalação; todo
outro host é recusado e contado) + `scripts/appliance_offline_medir.py` (roda `tests/e2e` inteiro com o navegador
atrás do proxy, `PLAT_E2E_PROXY` lido por `tests/e2e/conftest.py`, grava `tests/medidas/L7-11-b-*.json`).
Medido: 2.676 pedidos pelo proxy, **0 a host externo**, mapa-base PMTiles local apareceu, 33 e2e verdes (3
falhas reproduzem igual sem o proxy: ambiente da trilha). `tests/unit/test_appliance_sem_cdn.py` prende o
estático: nenhum HTML/JS/CSS carrega `http(s)://`, bibliotecas e fontes vendorizadas com sha256, Swagger local.
`docs/APPLIANCE.md`: o que não funciona offline e a mensagem exata da tela (conectores, CSW, catálogo público,
imagens, e-mail, OSRM, certbot), CA interna, rede `--internal` do compose (não executada: imagens do perfil
appliance pendentes por disco, D21). `tests/operacao/frente_estatica.py` faz o papel do nginx para e2e em trilha.

## turno 4, setembro de 2026 (item L7-08-c-sdk-js: SDK JavaScript e ajudantes MapLibre)

`web/sdk/plat.js` (também `sdk/js/plat.js`): módulo ES sem dependência, só `fetch`, com o mesmo modelo do SDK
Python — `Plataforma(url, token)`, `Plataforma.entrar()`, `.itens/.camadas/.mapas` (paginação por cursor em
`todos()`), `.jobs.esperar()`, `.tokens`, retentativa em 429/502/503/504, `ErroPlataforma` (RFC 9457). Ajudantes
MapLibre em `.maplibre`: `fonte(item)`, `camada(item)`, `estilo(mapaItem)`, `catalogo({bbox})`,
`transformRequest`, `enquadrar`. Regra medida e embutida: Bearer nunca junto com o cookie (a API responde 400
`autenticacao_ambigua`). 10 exemplos HTML em `/static/sdk/exemplos/` com CSP `default-src 'none'` na página,
sem inline; são o e2e (`tests/e2e/test_sdk_js.py`, 13 verdes no Chromium: os 10 exemplos, token revogado com a
mensagem exata, script inline bloqueado pela CSP, capturas dos dois mapas com >1.600 cores). Unidade em Node
(`tests/sdk_js/plat.test.mjs`, 13, via `tests/unit/test_sdk_js.py`). Paridade contra o ArcGIS Maps SDK for
JavaScript em `docs/PARIDADE.md`; ADR `docs/adr/20260908T0705-sdk-javascript.md`; `sdk/js/README.md`. Fora:
feições por camada e tiles dinâmicos (dependem do L2-04); CORS (a API é same-origin).
## turno 4 (líder 5), setembro de 2026 (item L7-03-d-injecao-consulta: 180 payloads de injeção contra o FeatureServer/OGC, 0 execução, 2 defeitos de 500 corrigidos)

`tests/seguranca/test_injecao.py`: 180 payloads (where/outFields/orderBy/groupBy/outStatistics/having/objectIds/
OGC) contra camada importada de verdade — 0 respostas 5xx, 8 ms de latência máxima, tabela-canário e contagem
intactas; teste estático por AST (nenhum `.execute` em `app/` interpola nome de entrada do usuário) + `bandit
B608` em `app/consulta` fixado em 6 f-strings de lista branca. Corrigidos em `app/consulta/motor.py`: `LIKE` em
coluna numérica e `statisticParameters.value` não numérico devolviam 500 com traceback; agora 400 nomeado
(`_executar`, rede de segurança para erro de tipo do banco). `docs/SEGURANCA.md` §10. ZAP baseline não rodou
(sem imagem, disco 94 %, D21).
## turno 4 (líder 5), setembro de 2026 (item L7-03-a-antivirus-upload: pipeline único de upload com lista por rota, antivírus opcional, SVG sanitizado e trilha da recusa)

`POST /api/arquivos?classe=` passa a decidir tipo e teto por classe ANTES de ler o corpo (`POLITICAS` em
`app/varredura_conteudo.py`; `Content-Length` acima = 413 com 0 mensagens de corpo lidas, medido), prova o tipo
pelos bytes (`.exe` como `.tif` = 415), varre por `clamd` quando `PLAT_CLAMD` está definido (INSTREAM por socket,
sem dependência; fora do ar = recusa), sanitiza SVG por lista branca (`app/svg_seguro.py`), aplica zip-bomba a
zip/KMZ (inclusive acima do buffer único, pelo diretório central) e registra toda recusa na trilha
(`arquivos/conteudo_recusado`, `arquivos/quarentena` com sha256 e assinatura; migração `20260907T2225`). A
entrega (`GET /api/arquivos/{sha}`) sai com `attachment` para tudo que não é imagem, `nosniff` e CSP `sandbox`.
`docs/SEGURANCA.md` §9 lista os tipos por classe (teste confere). `tests/seguranca/test_upload.py`: EICAR com
clamd de teste, SVG com script, zip de 1 GiB de zeros, KMZ com 10 mil entradas, polyglot GIF+HTML, anexo .html.
ClamAV real segue fora (D21, ~1,3 GiB de RAM de assinaturas).
## turno 4 (líder 5), setembro de 2026 (item L6-03-paridade-conectores: seção "Conectores e acervo" de docs/PARIDADE.md com teste que prende cada linha)

35 linhas (tipos de camada por URL do Map Viewer 11.4, itens de data store, Living Atlas, Data Pipelines, Data
Interoperability, cascateamento do GeoServer) em feito/parcial/fora, cada `feito`/`parcial` apontando para o
arquivo de teste e o ramo da fila onde ele vive. `docs/urls_paridade.txt` (20 URLs de referência) testado por
`scripts/paridade_urls_testar.py` → `tests/medidas/L6-03-paridade-conectores.json` (20 de 20 com 200 em 07/09).
`tests/unit/test_paridade_conectores.py` reprova linha `feito`/`parcial` sem teste existente (em master ou no
ramo citado, via `git cat-file`), linha `fora` com teste, chave citada sem URL e URL sem 200 na medida.
## turno 4, setembro de 2026 (item L6-01-i-raster-e-arquivos: o acervo de ARQUIVO no catálogo)

O acervo da casa não é só tabela: os 321 arquivos com sha256 de `acervo.camada_arquivo` (3,6 GB, 26 raster e 295
vetoriais, medidos 08/09/2026) entram no catálogo pela vista `plat.acervo_arquivo` e pela rota
`GET /api/acervo/arquivos`, com a ficha da fonte. `POST /api/acervo/arquivos/expor` enfileira
`acervo.expor_arquivo`, que **confere o sha256 antes de qualquer escrita**: raster vira item `raster` + item STAC
apontando para `acervo://<caminho>` (lido onde está, zero byte copiado para o balde — guardrail de disco D21) e
serve ladrilho por token (item L1-02); vetor é ingerido uma vez para PostGIS com `ogr2ogr`, na mesma tabela da
ingestão do L0-04. Guardrail: arquivo acima de 2 GB e lote acima de 3 GB são recusados sem job. Fonte sem licença
escrita (D17, medido: nenhuma das 27 fontes de arquivo tem) gera item privado e marcado `uso_restrito`. Medido em
`tests/medidas/L6-01-i-raster-e-arquivos.json`: 10 rasters e 30 arquivos expostos em 147,3 s, ladrilho do acervo
em 3.156 ms (GeoTIFF sem visão geral; converter para COG é decisão do dono). Refutação: 1 bit trocado num arquivo
recusa por `hash_divergente` sem criar item. ADR `docs/adr/20260908T1300-acervo-de-arquivo.md`.
## turno 4, setembro de 2026 (item L5-13-edicao-concorrente: mesclagem por nó, presença e bloqueio leve)

Sobre o construtor com desfazer/rascunho (L5-09, mesclado aqui): `base_versao` no PUT/PATCH de item — quando o
servidor já está adiante, `app/catalogo/mesclagem.py` mescla por nó (id ULID) a versão lida, a atual e a do
cliente; nós diferentes = 200 com `mesclagem`, o mesmo nó = 409 `versao_conflito` com o documento atual e os ids em
conflito (`detalhe.dados`, `detalhe.conflitos`). Presença efêmera por `POST/GET /api/itens/{id}/presenca` e SSE
`.../presenca/eventos` (memória + NOTIFY entre processos; expira em 12 s). Tela: absorve a mesclagem sem tocar o
histórico, mostra quem está no documento e em que nó, marca nós ocupados e avisa sem travar; o painel de 409 marca
o nó em conflito. Medido (`tests/medidas/L5-13-edicao-concorrente.json`): 100 pares aleatórios em nós disjuntos
sem perda (unidade e API), presença de outra aba em 1,28 s no navegador, PATCH retido 3 s fora de ordem nos dois
sentidos com 0 alteração perdida. Sem CRDT (D12). ADR `docs/adr/20260908T1130-edicao-concorrente.md`.
## turno 4 (líder 5), setembro de 2026 (item L7-07-b-replica-garage: Garage replicado provado com 3 nós rf=3, e a regra de quórum de 2 nós rf=2 medida)

`tests/operacao/garage_cluster.py` sobe N nós do binário da instalação com segredos em arquivo 0600
(`rpc_secret_file`/`admin_token_file`/`metrics_token_file`), zonas no layout e portas efêmeras;
`tests/operacao/test_garage_replica.py` (lento): 1.000 objetos escritos com um nó parado, nó religado,
re-sincronizado (5,2 s), scrub sem erro, conjunto de blocos em disco igual nos dois nós e os 1.000 sha256
conferidos com o nó que recebeu as escritas desligado; 256 MiB re-sincronizados em 4,7 s (54 MiB/s, mesma
máquina); cota por bucket mantida; `/metrics` só com o token. Medido também: **2 nós rf=2 mantêm a leitura mas
recusam escrita com um nó parado** (`503 quorum of 2`) — escrita contínua exige 3 nós rf=3; e o nó religado
só sincroniza depois de refazer `node connect` + `repair tables` (senão espera a anti-entropia de 10 min).
`docs/RUNBOOKS/garage.md` (adicionar nó, trocar disco, ver layout, scrub por timer
`deploy/plat-garage-scrub.{service,timer}`, cotas, o que não fazer). 10 GB de resync não medidos (D21).
## turno 4, setembro de 2026 (item L3-05-localizar-regioes: N regiões contíguas sobre a favorabilidade)

`app/amc/regioes.py` responde "onde ficam as N áreas", não só "quanto vale cada célula": crescimento de região
por fila de prioridade a partir de sementes espalhadas, com compromisso declarado entre FORMA (círculo, quadrado
ou hexágono, medido por compacidade em célula) e UTILIDADE, área total alvo distribuída entre as regiões, área
mínima e máxima por região, distância mínima e máxima entre elas, quatro métodos de avaliação (maior média,
maior soma, mediana, maior área de núcleo) e duas seleções (sequencial e combinatória). Célula sem dado ou
vetada é intransponível; fechar buraco nunca engole veto. `POST /api/multiescala/execucoes/{id}/regioes` roda o
motor sobre a grade de uma execução do motor multicritério e devolve um polígono por região (união das células,
4326) com as estatísticas. Medido (`tests/medidas/L3-05-localizar-regioes.json`): grade de 1.000.000 de células
em 3,42 s (N = 3) e 9,09 s (N = 10); sobre a execução real, 3 regiões sobre os 3 picos com área a 0 % do alvo.
Refutação: área maior que a disponível e N = 31 recusados com código próprio; mesma semente, resposta idêntica.
Paridade parâmetro a parâmetro contra o Locate Regions (Pro, página lida em 08/09/2026) em `docs/PARIDADE.md`;
ADR `docs/adr/20260908T1450-localizar-regioes.md`.
## turno 4, setembro de 2026 (item L0-08-a-oidc: login federado OpenID Connect por inquilino)

Módulo isolado `app/auth/oidc.py` (Authlib/`joserfc` 1.7.5, decisão medida contra httpx+JWT próprio em
`docs/adr/20260907T0147-oidc-authlib.md`): Authorization Code + PKCE S256, descoberta OIDC (RFC 8414, cache
com TTL de 1h) e validação de `id_token` em DUAS fases — assinatura via JWKS (`joserfc.jwt.decode`, refetch
automático em `kid` desconhecido = suporte a rotação de chave) e claims à parte (`JWTClaimsRegistry`: issuer,
audience = `client_id` do provedor, `exp`/`iat` com folga de 60 s, `nonce`) — achado do ADR: a etapa de
assinatura sozinha NÃO detecta token expirado. `GET /api/sso/oidc/{iniciar,retorno,logout}` (rotas próprias,
nunca `/api/login/oidc`, para não colidir com outro item em construção na mesma família); claim de
identificador de login é `sub` (nunca email, como a doc Esri do item recomenda), gravado em
`usuario.sujeito_externo` como `"<issuer>#<sub>"`. Transação de login (`state`/`nonce`/verificador PKCE) em
tabela própria (`plat.oidc_transacao`, migração `20260907T0147_provedor_oidc.sql`) com consumo ATÔMICO por
`DELETE...RETURNING` de uso único e TTL de 10 min — a defesa direta contra a refutação do item (reuso de
`code`, troca de `state`). Um inquilino pode ter MAIS DE UM provedor OIDC (rótulo + ordem configuráveis,
`GET/POST/PUT/DELETE /api/org/oidc`, privilégio `org.integracoes`); `client_secret` cifrado com o mesmo
esquema AES-GCM do LDAP/TOTP (prefixo `encoidc:v1:` isolado). `GET /api/login/provedores` passou a listar os
botões OIDC habilitados do inquilino (rótulo + id, nunca issuer/client_id).

Servidor de teste: Keycloak 26.0 em contêiner Docker efêmero (`tests/oidc_fixture/`, realm
`plataforma-teste-oidc` versionado em `realm.json`, 2 clients — um para a refutação de audiência trocada — 3
usuários sintéticos). O fluxo completo é dirigido por `httpx` puro, sem navegador (`google-chrome
--headless` quebrado nesta máquina); achado que exigiu tratamento especial: o Keycloak marca os cookies de
sessão de login como `Secure` mesmo servindo `http://` puro em modo dev, e o *cookie jar* automático do
`httpx.Client` os descarta — copiados manualmente para um cabeçalho `Cookie` explícito.

17 testes verdes (11 unidade com chaves RSA sintéticas em `tests/unit/test_oidc.py` — PKCE, cifra do
segredo, as 4 cláusulas literais do portão (assinatura errada/expirada/nonce errado/issuer errado) e a
rotação de chave; 6 de integração em `tests/api/oidc/test_login_oidc.py`, marcados `lento`, contra o
Keycloak real: login cai no inquilino/perfil certos com logout propagado (`X-Oidc-End-Session`), grupo não
mapeado nunca cria sessão, reuso de `code`/`state` nunca cria segunda sessão, troca de `state` entre duas
transações nunca cria sessão, `id_token` genuíno de OUTRO `client_id` (mesmo Keycloak, mesma chave) é
recusado só pelo `aud`, e provedor desligado (contêiner derrubado de verdade) não impede o login local do
admin do mesmo inquilino. Latência medida: 2 logins completos = 721 ms e 124 ms (`tests/medidas/
L0-08-a-oidc.json`, `latencia_login_oidc_ms`; o primeiro paga a descoberta OIDC fria, o segundo já usa o
cache). `tests/api/cruzado_casos.py` ganhou entrada para as 6 rotas novas (varredura cruzada A→B do
portão P6) — a suíte cruzada em si segue com uma falha PRÉ-EXISTENTE e não relacionada (fixture
`preparacao` recebe `403` em `POST /api/papeis` para o admin de `demo2` mesmo em `master` sem nenhuma
mudança deste item, confirmado por `git stash`), documentada como fronteira honesta no handoff, não
escondida nem contornada.

### Commits

| sha | mensagem |
|---|---|
| (este) | Login federado OpenID Connect por inquilino (item L0-08-a-oidc) |

## turno 8, setembro de 2026 (item L0-08-e-mapeamento-provisionamento: regras de provisionamento por provedor de login, tela Logins)

Um laço só de provisionamento para LDAP, OIDC e SAML (`app/auth/provisionamento.py`), chamado depois que o IdP
confirma a identidade: criação automática ou só por convite prévio (o convite por e-mail do L0-07-d; sem convite
= 403 `convite_necessario`, "peça convite"), padrões para membro novo (papel, grupos internos, pasta inicial),
mapa **valor exato** do grupo do IdP → perfil, papel e grupos internos (grupo chamado `administrador` sem regra não
vira nada), atualização a cada login (opcional), desligamento da conta quando o IdP deixa de mandar grupo mapeado
(opcional), grupos regidos sincronizados a cada login (entra e sai), e `POST /api/usuarios/{id}/desregistrar`
(vínculo removido, conta desativada, IdP intacto). Coluna `provisionamento` jsonb nas três tabelas de provedor
(migração `20260908T0212`), funções SECURITY DEFINER para localizar/regras/desligar/convite. Tela `/admin/logins`
(`org.integracoes`): lista LDAP/OIDC/SAML com rótulo e ordem dos botões, habilitação, criação e regras; editor de
regras por linha; tabela de paridade com a Esri 11.4 (New member defaults, group membership) na própria tela e no
ADR `20260908T0240-provisionamento-federado.md`. Testes: unidade (decisão pura, 500 grupos, 422 por campo),
integração com Keycloak real (grupos e usuários criados pela API de administração dentro do teste) e e2e da tela
com captura. Este ramo contém `wt/cx008` (OIDC + SAML) por merge.

## turno 8, setembro de 2026 (item L0-08-c-govbr: gov.br como provedor OIDC, adaptador provado contra IdP sintético)

gov.br (Login Único) vira um `modelo` do provedor OIDC (`plat.provedor_oidc.modelo = 'govbr'`, `api_base`),
sem cópia do fluxo: descoberta, PKCE S256, JWKS, validação e transação de uso único são as do L0-08-a. O adaptador
(`app/auth/govbr.py`) transforma `reliability_info` do id_token (nível bronze/prata/ouro, selos) e `amr` em valores
`nivel:*`, `selo:<id>`, `amr:*`; sem `reliability_info`, consulta a API de confiabilidades
(`/confiabilidades/v3/contas/{cpf}/niveis|confiabilidades?response-type=ids`) com o access_token; o mapeamento para
perfil/papel/grupos é o do L0-08-e (regra explícita, valor exato). CPF só como pseudônimo SHA-256 (nunca em login,
sujeito externo, evento ou log; teste procura). Tela Logins > Novo provedor OIDC com os campos do roteiro (ambiente,
issuer, client_id, client_secret cifrado, redirect_uri fixa, escopos). Provado contra `tests/govbr_fixture/idp_falso.py`
(formato do roteiro, 6 casos, inclusive id_token de outro issuer com 'gold' = 401); e2e da tela 51 ms. **Teste real
com credencial do órgão: pendente em `docs/PARIDADE.md`** (cadastro exige ofício). ADR `20260908T0630-govbr-login-unico.md`.
Este ramo contém `wt/cx2l008e` (e por ele `wt/cx008`).
## turno 4, setembro de 2026 (item L3-09-backtest-decisao-real: o modelo contra a escolha que já aconteceu)

`app/amc/backtest.py` compara o ranking de uma execução do motor multicritério com escolhas reais: percentil das
escolhas, nulo por permutação (N sorteios de igual número de unidades), AUC (Mann-Whitney, empate meio) com
p-valor de uma cauda, e preferência revelada por fator (`evitamento`, sinal e ordem, nunca peso).
`POST /api/multiescala/execucoes/{id}/backtest` recebe as escolhas por camada hospedada ou por lista de pontos,
conta as que caem fora da grade e devolve o relatório. Ressalvas no corpo do relatório, nunca em rodapé:
concordância com o passado não é acerto futuro, distância confunde, e camada mais nova que a decisão sai marcada
ANACRÔNICA. Medido sobre dado aberto (`tests/medidas/L3-09-backtest-decisao-real.json`): 602 galpões OSM com área
> 5.000 m² numa janela de 30 km × 22 km, grade de 500 m, modelo de um fator (proximidade de via arterial) —
AUC 0,718, percentil mediano 74,8, p-valor 0,002 em 500 permutações; escolhas do próprio modelo AUC 1,000 e ao
acaso 0,4993 (desvio medido 0,0145). Refutação: escolhas = todas as células devolvem `auc: null` com a frase, e
escolhas fora da grade aparecem em `n_fora`. ADR `docs/adr/20260908T1600-backtest-decisao-real.md`.
## turno 4, setembro de 2026 (item L6-02-j-bancos-externos: PostgreSQL/PostGIS externo referenciado e consulta SQL do cliente)

Sobre o conector `postgres_fdw` do L0-04-i, o item fecha o "banco externo" como o Esri e o GeoServer o
entendem: a tabela PostGIS remota é referenciada e publicada como camada (geometria e SRID lidos de
`geometry_columns`), e o cliente pode rodar **uma consulta SQL de leitura** sobre o banco dele pela rota
`POST /api/conexoes/{id}/consulta`. O validador (`app/conexao/consulta_sql.py`) recusa, antes de abrir
conexão, tudo que não é um único SELECT com LIMIT explícito sobre tabelas que a própria conexão lista:
`SELECT ...; DROP TABLE`, DELETE/UPDATE/INSERT em qualquer posição (CTE, subconsulta), funções de sistema
(`pg_sleep`, `pg_read_file`, `dblink`...), `pg_catalog`, outro schema, consulta sem LIMIT, LIMIT acima de
5.000. A execução é só-leitura com `statement_timeout` e devolve `tempo_ms`. Evento `conexoes/consultar`
(tabelas, linhas, tempo; nunca o texto). ADR `docs/adr/20260908T0640-bancos-externos-consulta-sql.md`.
Testes: `tests/unit/test_consulta_sql.py` (39 casos) e `tests/api/test_bancos_externos.py` (docker
PostGIS na porta 55499, pulado sem o container). **SQL Server e Oracle ficam pendentes** (sem container
liberado pelo dono não há teste; registrado no handoff). Limites novos em `docs/LIMITES.md`
(`CONEXAO_PG_CONSULTA_LINHAS_MAX`, `CONEXAO_PG_CONSULTA_TEXTO_MAX`).
## turno 4 (líder 5), setembro de 2026 (item L6-02-m-catalogo-endpoints-brasil: catálogo de conectores públicos prontos para um clique, retestado por semana)

`plat.endpoint_publico` (global, escrita só por função SECURITY DEFINER) + job `endpoints_publicos.retestar`
(semente curada + registro do acervo, toda segunda 04:00) + `GET /api/endpoints-publicos` (vivos; `?vivo=false`
= fora do ar) + `POST /api/endpoints-publicos/{id}/adicionar` (conexão do inquilino com ficha de procedência do
catálogo, idempotente; 409 para entrada fora do ar). "Vivo" exige o documento do protocolo (Capabilities,
`f=json` sem `error`, `stac_version`, `links`): HTTP 200 com HTML ou erro ArcGIS conta como morto. Tela
`/conexoes` ganha a seção "conectores públicos prontos" com a lista de fora do ar. Medido em 07/09
(`scripts/endpoints_publicos_testar.py` → `tests/medidas/L6-02-m-catalogo-endpoints-brasil.json`): 78 verdes de
100 candidatos; e2e adiciona 10 pela tela; 29 endereços adivinhados que nunca existiram foram podados da semente.
## turno 4 (líder 5), setembro de 2026 (item L6-06-descoberta-csw: descoberta por catálogo CSW 2.0.2 da INDE e criação de conexão WMS/WFS num clique)

`POST /api/csw/buscar` (texto e/ou bbox, `GetRecords` por GET KVP com `CQL_TEXT` e `outputSchema` ISO 19139,
paginação por `nextRecord`) e `POST /api/csw/conexoes` (`GetRecordById` → uma `plat.conexao` por
`CI_OnlineResource` WMS/WFS/WMTS com endereço, idempotente por tipo+url+camada, ficha de procedência do
registro ISO em `config.procedencia`; o `publicar` completa a ficha com o que o serviço vivo declara e o
resto vem do ISO). Registro com protocolo declarado e `linkage` vazio (caso real das cartas do IBGE na INDE)
devolve 422 `sem_servico_ligado` e não cria nada. Tela `/conexoes` ganha a seção "descobrir por catálogo".
Tudo por `buscar_seguro` (SSRF, 1 MiB, 20 s); XML por defusedxml; nomes/e-mails de contato retirados das
gravações de teste. Medido contra a INDE em 07/09 (`tests/medidas/L6-06-descoberta-csw.json`): 52 registros
para "tuberculose", 2 conexões (WMS+WFS) criadas de um registro e as 2 com saúde ok. Cinco endereços de
CSW estadual adivinhados não resolveram: só a INDE está verificada.
## turno 4 (líder 5), setembro de 2026 (item L7-11-c-telemetria-opcional: telemetria do appliance desligada por padrão, opt-in do superadmin, só agregados)

`app/telemetria.py` + migração `20260908T0555`: `plat.telemetria` (1 linha por instalação, `ligada=false`, chave
própria gerada), `GET /api/telemetria` (estado + prévia = o JSON exato que sai), `PUT` liga/desliga (superadmin,
evento na trilha), `POST /api/telemetria/enviar` e periódico diário `telemetria.enviar` (só quando ligada;
desligada = 0 chamadas de rede, medido); relatório com 13 campos fixos (`CAMPOS`: versão, saúde, fila,
contagens agregadas por `plat.telemetria_contagens()`), nunca nome/geometria/conteúdo. Receptor na casa
(`POST /api/telemetria/receber`): chave desconhecida = 403 sem gravar, campo a mais = 422, chave de outro
appliance no cabeçalho = 422; `plat.telemetria_appliance` alimenta `GET /api/telemetria/appliances`.
`docs/APPLIANCE.md` §5 lista os campos (teste confere). Ramo inclui o merge de `wt/cx5l711b` (dependência).
## turno 4, setembro de 2026 (item UX-17-login-sem-controle: diretório LDAP com controle em tela)

As três rotas do grupo `login` que só existiam no backend ganharam controle: em `/admin/organizacao`, a seção
"Diretório (LDAP / Active Directory)" (`PUT /api/org/ldap`: servidor, base, StartTLS, conta de serviço, filtro,
atributo de grupos, perfil padrão e mapa grupo → perfil) e o formulário "Importar um grupo do diretório"
(`POST /api/org/ldap/importar`), com os estados do sistema de design: carregando, erro com "tentar de novo" e
referência, negado (403, privilégio `org.integracoes`) e vazio; em `/entrar`, quando o inquilino habilitou o
diretório, `GET /api/login/provedores` o anuncia e a tela oferece "Entrar com o diretório da organização (LDAP)"
— o mesmo formulário enviado a `POST /api/login/ldap`, com endpoints literais no código (a credencial nunca vai a
um caminho vindo da rede). Erros nomeados no controle: 422 no campo, 409 sem configuração, 503 diretório
indisponível, 403 negado; nunca um código cru. e2e `tests/e2e/test_login_ldap_ux17.py` com o glauth de teste
real (configura, importa `gg-plataforma-leitura` = 1 encontrado, entra como usuária da rede em 125,6 ms), axe 0
violações sérias nas duas telas, capturas 390/1280. `docs/COBERTURA_UI.md` regenerado: 26 → 23 lacunas de
escrita. Textos em pt-BR, en e es.
## turno 4, setembro de 2026 (item L2-13-a-versoes-ramo-reconciliar: versionamento por ramo)

Camada marcada como versionada aceita RAMOS de trabalho paralelos, no molde do *branch versioning* do
ArcGIS Enterprise. Ler num ramo mostra as edições dele mais o padrão como estava no momento em que o
ramo nasceu; reconciliar compara os dois lados desde esse momento e lista as feições alteradas dos
dois; resolver decide `ramo`, `padrão` ou `manual` campo a campo; publicar (post) leva as linhas do
ramo para o padrão e fecha ou rebaseia o ramo; apagar descarta tudo.

Onde as linhas do ramo moram: numa tabela companheira `c_<uuid16>__ramo`, e não em colunas novas na
tabela da camada. O motivo está no ADR 20260908T1323 e vale repetir: todo caminho de leitura que já
existe (FeatureServer, OGC, WFS, tiles, exportação, união/divisão) lê a tabela sem filtro de versão, e
com as colunas lá dentro o não-vazamento passaria a depender de lembrar de corrigir cada um. Assim ele
é estrutural. O momento histórico do padrão vem de `plat.feicao_historico` (item L2-03-d), reusado
inteiro.

No protocolo Esri: `gdbVersion` na consulta e no `applyEdits`, `historicMoment` na consulta (os dois
como troca da RELAÇÃO lida, no motor), e um `VersionManagementServer` com `versions`, `versionInfos`,
`create`, `reconcile`, `conflicts`, `post`, `delete` e as sessões `startReading`/`stopReading`/
`startEditing`/`stopEditing`. As doze chamadas da sequência do cliente Python `arcgis` foram rodadas
por `tests/esri/cliente_arcgis_versoes.py`, todas ok; o pacote `arcgis` em si NÃO está instalado nesta
máquina e o script diz isso em vez de fingir. ArcGIS Pro de verdade continua pendente (D20).

Tela nova `/versoes`: diff lado a lado do conflito (base, ramo, padrão nas mesmas três colunas em toda
feição, com o lado que mudou marcado por classe e não só por cor) e a decisão gravada por feição.

Limite declarado: 50 ramos abertos por camada (`VERSOES_POR_CAMADA_MAX`), e a camada pode declarar um
teto menor em `dados.versionamento.ramos_max`.

## L1-02-g-wms-1-3-0-raster (10/09/2026)
- WMS 1.3.0 por token (`GET /svc/<token>/wms`, `app/imagens/rotas_wms.py` + `app/imagens/wms.py`): `GetCapabilities` (uma `<Layer>` por item raster que o token alcança, `EX_GeographicBoundingBox`, `BoundingBox` em EPSG:4326 e EPSG:3857) e `GetMap` (LAYERS/CRS/BBOX/WIDTH/HEIGHT/FORMAT/TRANSPARENT), reusando a mesma porta de entrada do WMTS (`_autorizar`, token no caminho, cache de 5 s).
- `tiles.recorte()` em `app/imagens/tiles.py`, ao lado de `ladrilho()`: leitura de um bbox arbitrário (não uma célula de grade) via `rio_tiler.io.Reader.part`, para o CRS/tamanho que o cliente pedir no GetMap.
- Eixo invertido do WMS 1.3.0 em EPSG:4326 (BBOX = lat,lon nesse CRS, x,y normal em EPSG:3857) tratado em `wms.py::bbox_do_parametro`/`bbox_para_atributo` e testado nos dois CRS.
- Isolamento entre inquilinos: a lista de camadas visíveis é calculada uma vez por token (tenant_id + escopo) e usada tanto no GetCapabilities quanto na validação do GetMap — camada fora dela vira `LayerNotDefined`, a mesma mensagem para "não existe" e "não é sua".
- Erro de domínio (CRS inexistente, tamanho acima do teto, BBOX degenerado, STYLES desconhecido, operação não suportada) sempre em `ServiceExceptionReport` (XML da spec), nunca 500 mudo; `SLD`/`SLD_BODY` só é consultado como string, nunca entra num parser de XML (defesa estrutural contra XXE).
- `app/limites.py`: seção WMS (`WMS_LARGURA_MAX`/`WMS_ALTURA_MAX`/`WMS_PIXELS_MAX` = 4096×4096, `WMS_CAMADAS_MAX` = 500).
- XSD oficial do WMS 1.3.0 (`capabilities_1_3_0.xsd`, `exceptions_1_3_0.xsd`) trazido para `tests/dados/ogc_xsd/wms/1.3.0/` a partir do commit `b0b52199f` (já no object store do repositório, cache de XSD do item L2-04-i) — sem depender de rede para validar.
- `tests/api/imagens/test_wms.py` (21 casos): GetCapabilities válido no XSD oficial, GetMap com tamanho exato, JPEG sem transparência, fora-da-cobertura em branco, eixo invertido 4326×3857, isolamento entre inquilinos, token sem escopo/inválido, e os abusos do adversário (WIDTH gigante, BBOX invertido de verdade, CRS inexistente, STYLES arbitrário, SLD_BODY com XXE).
- Fora desta passagem (ver `docs/PARIDADE.md`): `GetFeatureInfo`, `TIME`/dimensão, `GetLegendGraphic` (depende de L1-02-f, ainda pendente).

## L1-02-f-predefinicoes-de-renderizacao-e-legenda (10/09/2026)
- `app/imagens/predefinicoes.py`: 6 predefinições de FÁBRICA (RGB natural, falsa-cor NIR, NDVI, NDWI,
  NBR aproximado — PARCIAL, sem banda SWIR real nesta instalação —, relevo sombreado com hillshade
  analítico calculado dentro do próprio ladrilho/recorte) + predefinições CUSTOM por item, guardadas em
  `plat.render_predefinicao` (migração `20260910T1620`, RLS, JSON Schema
  `docs/esquemas/renderizacao-v1.json`: bandas, esticamento min/max·desvio-padrão·percentil (aproximado
  por `statistics.NormalDist`, sem recalcular pixel)·explícito, colormap nomeado do rio-tiler, nodata
  transparente, opacidade, reamostro.
- Aplicado nos TRÊS caminhos sem mudar o comportamento padrão de quem não passa nada: `predef=` no
  XYZ/WMTS/TileJSON (`rotas_tiles.py`), `STYLES=` no WMS `GetMap` + `GetLegendGraphic` novo
  (`rotas_wms.py`/`wms.py`, `<Style>`/`<LegendURL>` no `GetCapabilities`) e `renderingRule` no
  ImageServer (`rotas_imageserver.py`) — só a forma mínima `{"rasterFunction":"<nome>"}`, forma
  encadeada/`rasterFunctionArguments` continua recusada com erro Esri; `allowRasterFunction` agora é
  `true` quando o item tem banda suficiente para ao menos 1 predefinição de fábrica.
- `tiles.ladrilho()`/`tiles.recorte()` ganharam `resampling`/`nodata_transparente` (default idêntico ao
  de antes); `predefinicoes.renderizar_hillshade` lê 1 banda e calcula sombreamento fora do pipeline de
  `rio_tiler.render` (formula padrão azimute 315°/altitude 45°, `np.gradient`); `aplicar_opacidade` faz
  pós-processamento de alfa por PIL só quando `opacidade<1`.
- Legenda: `legenda_json`/`legenda_png` (mesma fonte para as duas — nunca dessincronizadas), servidas
  por `/svc/<token>/raster/<item>/legenda.json|png` e pelo `GetLegendGraphic` do WMS.
- CRUD de sessão em `app/imagens/rotas_predefinicoes.py` (`/api/imagens/<item>/predefinicoes`,
  `POST .../tornar-padrao`): nome de fábrica é reservado, banda fora do item é 422
  `predefinicao_incompativel` na hora de salvar (não só no uso).
- `plat.item` ganhou `UNIQUE (tenant_id, id)` (faltava, item L1-02-f precisava de FK composta por
  inquilino, regra de `tests/api/test_fk_composta_por_inquilino.py`).
- `tests/api/imagens/test_predefinicoes.py` (22 casos): esquema/banda/colormap inválidos nunca viram
  500, determinismo da query string, NDVI abre + legenda bate com os cortes, falsa-cor muda o pixel de
  forma previsível (>50% dos pixels diferem), trocar a predefinição padrão muda a URL publicada sem
  quebrar a anterior (nome explícito continua servindo), isolamento entre inquilinos, WMS `STYLES=`/
  `GetLegendGraphic`, ImageServer `renderingRule` (forma mínima aceita, forma encadeada e nome
  inexistente recusados sem 500). `test_imageserver_token.py` atualizado: o teste antigo que esperava
  `renderingRule` SEMPRE recusado (400) virou dois testes (mosaicRule continua fora; renderingRule com
  nome desconhecido é 422/400, nunca 500 — a FORMA passou a ser aceita, o CONTEÚDO ainda é validado).
- Prova pela instância viva (127.0.0.1:8184, item Sentinel-2 real de 3 bandas): cor verdadeira × falsa
  cor (recomposição 3-1-2, predefinição custom) — 99,46% dos 65.536 pixels do mesmo ladrilho diferem
  (diferença média 12,7/8,9/7,1 por canal RGB); ver relatório do turno para os dois PNG e os comandos.
- Fora deste turno: linguagem de expressão livre por predefinição do usuário (item L1-12, ainda
  pendente — as 3 predefinições de índice usam expressão FIXA, escolhida em código, sobre a gramática
  já existente de `tiles.py`); tabela de cor CUSTOM por intervalo (só rampa nomeada, como o portão
  pede); histórico de versão de uma predefinição editada (edita substitui o corpo, `versao` sobe, mas
  não guarda a versão anterior — só a troca de PADRÃO entre predefinições distintas preserva a URL
  antiga, não a edição de uma já publicada).

## L4-13-integracao-telemetria (10/09/2026)
- `plat.rede_medicao` particionada por mês (`PARTITION BY RANGE (ts)`, mesmo padrão de `plat.evento`:
  função `rede_medicao_particao_garantir` SECURITY DEFINER com `pg_advisory_xact_lock`, RLS própria em
  cada partição, REVOKE ALL de acesso direto à partição — SEM TimescaleDB, proibido para dado de
  cliente nesta casa). `ativo` é só o `id` (uuid) de uma feição, sem FK: a mesma decisão de desenho do
  módulo campo, uma leitura de algo que saiu da camada continua sendo um fato.
- Catálogo fechado `plat.rede_medicao_grandeza` (8 grandezas: corrente/tensão por fase, temperatura —
  `tipo='bruto'` — e `carregamento_pct` — `tipo='derivado'`, só o motor de alarme escreve). Placa do
  ativo (kVA/tensão nominal) em `plat.rede_medicao_ativo`, sem depender de nenhuma tabela de feição.
- `POST /api/rede/medicao/leituras`: lote (até 2.000), idempotente por `(tenant, ativo, grandeza, ts)`
  — `ON CONFLICT DO NOTHING`, reenviar não duplica —, recusa item a item (nunca o lote inteiro) por
  `ts_futuro` (tolerância de 120 s de relógio do sensor), `grandeza_desconhecida` e
  `unidade_incompativel`, sempre com mensagem. `PUT/GET /api/rede/medicao/ativos/{ativo}` (placa),
  `.../ultimas` (última leitura por grandeza) e `.../serie` (série por período, padrão 7 dias) — a
  ficha do ativo. `GET /api/rede/medicao/jusante` soma a leitura mais recente de uma grandeza entre os
  transformadores alcançados a jusante de um ponto pela topologia derivada (reusa
  `app.rede_utilidades.fluxo.tracar_fluxo`, sem mudar nada nele).
- Motor de alarme "carregamento > 100% por 30 min" (`servico.py::avaliar_alarme_carregamento`) roda
  DENTRO da própria chamada de publicação, para cada ativo tocado que já tem placa cadastrada — sem
  depender de job periódico. Calcula `carregamento_pct` (S(kVA) ≈ √3×V×I_média ÷ 1000, sobre kVA
  nominal) para cada `ts` de corrente na janela de retrospecto que ainda não tem o derivado (não só o
  mais recente — um lote com histórico, como o do simulador desta prova ou um sensor que ficou
  offline, precisa da série completa para o "surto contínuo de 30 min" existir). `plat.
  rede_medicao_alarme_estado` guarda só o ESTADO atual (evita reabrir o mesmo alarme a cada leitura);
  dispara `rede_medicao/alarme_disparado` na transição, `rede_medicao/alarme_resolvido` quando volta a
  ≤ 100%.
- Privilégio novo `rede.medir` (perfis campo/editor/admin — migração e espelho em
  `app/auth/privilegios.py`, vocabulário 47→48). Tarefa periódica `rede_medicao.particoes_criar`
  registrada PAUSADA (`ativa=false`; o mês corrente e o seguinte já existem desde a migração).
- Tela `/rede/medicao/ficha?ativo=<uuid>&rede_id=<uuid opcional>` (`web/rede_medicao_ficha.html` +
  `web/js/rede/medicao_ficha.js`): última leitura de cada grandeza, gráfico de 7 dias (SVG inline, sem
  biblioteca) e — quando `rede_id` é passado — um mapa MapLibre (estilo vazio, só o marcador) com o
  ponto do ativo colorido (vermelho = alarme ativo, verde = normal, cinza = sem placa); atualiza
  sozinha a cada 5 s.
- Simulador `scripts/rede_medicao_simulador.py`: 20 sensores de trafo reais da rede
  `lancamento-demo-utilidades` (35 trafos disponíveis), corrente por fase a cada 5 min, temperatura a
  cada 5 min, tensão a cada 10 min; `--provar` mede publicar→ficha e mostra o alarme disparando com
  histórico simulado; `--limpar` apaga leitura/placa/estado de alarme dos ativos que tocou (nunca a
  rede em si).
- Medido na instância viva (127.0.0.1:8184, tenant `demo`, 10/09/2026): 1.540 leituras (65 min de
  histórico × 20 trafos) publicadas em 0,7 s; publicar → aparecer na ficha do ativo = **0,089 s**
  (portão pede ≤ 5 s); alarme disparou em 8 dos 20 trafos simulados com carregamento acima de 100%
  (ex.: 151,5%, desde 30 min antes do fim do backfill); gráfico de 7 dias com 15 pontos.
- 11 testes novos em `tests/api/test_rede_medicao.py`: idempotência (mesmo lote 2×, mesmo trio dentro
  do mesmo lote), recusa com mensagem (ts futuro, grandeza desconhecida, unidade incompatível,
  `carregamento_pct` publicada de fora), isolamento entre inquilinos usando o MESMO `ativo` uuid nos
  dois lados (leitura, série e placa — cláusula inegociável), ficha do ativo (última leitura por
  grandeza, série filtra por janela), alarme dispara/resolve/NÃO dispara antes de 30 min contínuos,
  agregação a jusante com uma rede mínima real (2 trafos, 2 trechos).
- Paridade Esri (`docs/PARIDADE.md`): GeoEvent Server e ArcGIS Velocity fazem streaming/regra sobre
  telemetria, mas não têm uma tabela de medição por ativo nativa dentro do Utility Network — registrado
  como ALÉM da capacidade Esri equivalente, não paridade.
- Fora deste turno: MQTT/ingestão por fluxo (a rota é HTTP; L2-14-tempo-real é quem cobre ingestão de
  fluxo em geral); agregação a jusante por ALIMENTADOR/subrede nomeada (a agregação existe e está
  testada, mas parte de um `ativo` ponto de partida — subrede/controlador automático depende de
  L4-04-a/b, não construído para a rede de demonstração desta trilha); retenção/expurgo de partição
  antiga (a de `plat.evento` existe como molde, não copiada aqui por não ser exigida pelo portão).

## auditoria-apagar-inquilino (15/09/2026)

- `plat.tenant_apagar_interno` apagava `plat.auditoria` pelo loop genérico de tenant_id e o gatilho `plat.tg_auditoria_imutavel()` recusava com 409 `auditoria_imutavel` (10 arquivos de teste erravam no teardown da fixture `inquilino_temporario`); corrigido em `db/migracoes/20260915T1500_auditoria_apagar_inquilino.sql` (marca `plat.apagando_inquilino` local à transação, só DELETE, só dentro da função; auditoria do inquilino apagada de forma explícita) — prova: `roda_teste.sh tests/api/test_usuarios_papel_escalada.py` 8 passed sem erro de teardown (antes: 8 passed + 1 error) e `tests/api/test_auditoria_imutavel_apagar_inquilino.py` 3 passed.

## notificacoes-internas-completar (15/09/2026, item L0-03-k-favoritos-notificacoes, metade notificação)

- A tabela/API/sino de `plat.notificacao` já existia (commit `d1334f735`, 07/09), mas três das cinco origens
  que a hipótese do item pedia nunca chegaram a chamar `plat.notificar`: `jobs/concluido`/`jobs/falhou`
  estavam na lista `app/notificacoes.TIPOS` desde o começo, mas nenhum código os emitia (o worker terminava
  o job e ninguém era avisado); "item compartilhado comigo" e "transferência de dono" nunca tinham código
  nenhum (a passagem anterior declarou as duas fora de escopo).
- `app/jobs/worker.py::Worker._notificar_dono`, chamado de `_terminar` (concluído, timeout, falha definitiva)
  e do desvio por `plat.job_devolver` quando as tentativas se esgotam sem passar por `job_terminar`; nunca
  propaga exceção (notificar é efeito colateral, não pode derrubar o job que acabou de terminar).
- `app/catalogo/transferencia.py::executar` notifica o NOVO dono (`itens/transferido`), um aviso por item
  PRINCIPAL do plano — itens arrastados (vista/estilo) não geram aviso extra.
- `app/catalogo/rotas_compartilhamento.py::aplicar_compartilhamento` notifica os membros ATIVOS de cada
  grupo NOVO adicionado ao compartilhamento (`itens/compartilhado`), nunca quem compartilhou; o diff
  antes/depois evita renotificar quando o mesmo grupo já estava lá.
- Escopo: só a metade de NOTIFICAÇÃO. Favoritos ("estado errado na tela") é o item-irmão L0-03-f, de outro
  trabalhador (`wt/f2-l0sse`) — não tocado aqui. "Prazo de token" continua fora (exigiria periódico
  cross-tenant que não existe, mesma lacuna já registrada para o aviso por e-mail).
- Prova: `bash laco/roda_teste.sh tests/unit/test_jobs_notificar_dono.py` — 8 passed (sem banco; espiona
  `Worker.um` e confere a SQL emitida por `_notificar_dono`/`_terminar`, já que o daemon `plat-worker` vivo
  desta trilha não pode ser reiniciado para carregar este código). `bash laco/roda_teste.sh tests/api/
  catalogo/test_notificacoes.py` — 9 passed (as 7 preexistentes + as 2 novas de compartilhamento/
  transferência), contra a trilha `uniao` real. `docs/PARIDADE.md`: nova seção "Notificações internas".
