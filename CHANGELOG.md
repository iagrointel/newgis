# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json` (com o comando que
os gerou) ou dos vereditos do adversário em `laco/handoffs/T<n>/<item>/refutacao.json`.

## turno 7, setembro de 2026 (item L4-04-d-diagrama-esquematico: diagrama de rede, regras e layouts)

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

## turno 3, setembro de 2026 (item L0-07-d-smtp-convites: SMTP, convite de membro por e-mail e redefinição de senha por e-mail)

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
