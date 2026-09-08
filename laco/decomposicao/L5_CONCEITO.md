# L5 — construtores arrasta-e-solta: decisões de conceito

Linha L5 do laço PLATAFORMA ENTERPRISE. Data: 05/09/2026. Par deste documento: `L5.json` (57 itens novos, 4
existentes mantidos como pais). Tudo aqui é análise interna do laço; nada vai para cliente sem a regra de
escrita de 03/09.

Cada decisão traz: opções, o que custa mudar depois, recomendação com motivo em uma das três formas
admitidas (MEDIDO nesta máquina, LIDO em código que roda aqui, DOCUMENTO OFICIAL com URL testada por HTTP)
e o que ela obriga nas outras linhas. As medições estão no anexo A com comando e saída; as bibliotecas
candidatas no anexo B com tamanho, licença e data do último commit; as URLs no anexo C com o código HTTP.

Ordem de leitura: D1 (framework) e D2 (documento e identificadores) são as duas que, erradas, obrigam a
refazer tudo. As demais dependem delas.

---

## 0. O que é um construtor, para esta plataforma

Um construtor é três coisas separadas e só três: (1) um DOCUMENTO JSON que descreve o resultado (páginas,
widgets, nós, perguntas, blocos, elementos), (2) um RENDERIZADOR que lê o documento e o transforma em tela
(o app publicado, o formulário na PWA, o painel, o relatório) e (3) um EDITOR que altera o documento por
arrasto, por teclado e por menu. Toda decisão abaixo protege a fronteira entre os três: o documento é a
verdade; renderizador e editor são trocáveis; quem escreve o documento pode ser uma pessoa arrastando, um
importador (XLSForm, Web Map Specification) ou o agente (DOC.md §20.3, fase v2).

Os doze construtores da linha (app, painel, fluxo, formulário, narrativa, site/hub, app instantâneo,
popup, simbologia, relatório, camada, gerenciador de trabalho/captura rápida/operação ao vivo) usam UM
motor de widgets, UM editor de arrasto, UM barramento de mensagens, UMA linguagem de expressão, UM
esquema de versões e UM mecanismo de publicação. Isso é o que faz 57 itens caberem numa equipe: o custo
marginal de cada construtor é a paleta e o esquema, não a infraestrutura.

---

## D1. Framework de interface: exige React/Vue/Lit ou não?

Pergunta que o ADR 0001 (seção 11.3) deixou explicitamente para esta linha.

Opções:

| opção | o que traz | o que custa |
|---|---|---|
| a) continuar sem framework: módulos ES + Custom Elements nativos + loja de estado própria (≈ 3 kB) | zero dependência nova; o SIG de teste interno já roda 227 kB de módulos próprios em produção assim (LIDO: `web/js/*.js`, 5 arquivos); qualquer desenvolvedor de JavaScript entende; bundler continua opcional (regra 1 do ADR) | escrever nós mesmos o que um framework dá de graça: reatividade fina, diff de árvore. Para widgets pequenos e isolados isso é pouco; para um editor de propriedades gerado de JSON Schema é ~40 kB de código próprio |
| b) Preact (11 kB) ou Lit (~7 kB de núcleo) | reatividade e templates com custo de peso desprezível; ambos licença MIT/BSD-3; ambos publicam ESM que carrega sem bundler | o estado e a renderização passam a viver no framework (o custo que o ADR nomeia); Lit exige decorators/TS para ser confortável; Preact sem JSX é verboso |
| c) React 19 + biblioteca de builder pronta (Puck 13,3 mil estrelas MIT, Craft.js, dnd-kit, xyflow) | o caminho da Esri (Experience Builder é React + Redux, doc oficial "Jimu") e do Retool/Kepler (React) | React 19 não publica mais UMD (MEDIDO: `umd/react.production.min.js` inexistente no pacote 19.2.8; só CJS/ESM) → bundler OBRIGATÓRIO, e o ADR mediu 392 MB de RSS e 78 MB de `node_modules` por build numa máquina com 3 GB livres; `react-dom-client.production.js` = 536 kB; Puck/Craft/dnd-kit/xyflow exigem `react` como peer (anexo B); reescrever `web/js/` inteiro |
| d) Vue 3 (168 kB global prod) | framework completo com build opcional | mesmo lock-in de estado da (c) com menos ecossistema de builder que React |

O que custa mudar depois: (a)→(b) custa pouco, porque um Custom Element pode ter Preact/Lit por dentro sem
mudar o documento nem o barramento (o widget continua sendo `<plat-mapa>` para quem está fora). (a)→(c)
custa reescrever todos os renderizadores de widget e o editor; o documento, o esquema, o barramento e a API
não mudam. Logo a proteção real não é a escolha do framework, é que NADA da lógica de negócio viva dentro
dele: documento (D2), vistas (D4), mensagens (D5), expressões (D6) e estilo (D7) são JSON e código
puro sem DOM.

Recomendação: **(a)**, com três licenças para trocar: (1) um widget pode adotar Preact ou Lit por dentro
quando o e2e do item medir defeito ou latência que o código próprio não resolve, e a decisão vai num ADR
do item; (2) o editor de nós (D9) e a grade de painéis (D20) podem trazer biblioteca vanilla vendida
(anexo B); (3) React só se o dono decidir que o produto do canal precisa do ecossistema React de widgets de
terceiros, e aí é uma decisão de produto, não técnica.

Motivo medido (anexo A.1): a API nativa de arrastar e soltar do navegador funciona sob o chromium do
playwright desta máquina (`drag_and_drop` da paleta para a tela em 123 ms), o arrasto por Pointer Events
funciona, a alternativa por teclado funciona, e a emulação de celular (Pixel 7) aceitou o drop. Ou seja: o
ingrediente que faz "arrasta-e-solta" parecer exigir framework não exige. Motivo de doc: Esri chegou a
React por ter uma equipe de plataforma e um SDK de terceiros para alimentar (Jimu, TypeScript, Redux, doc
oficial); nós não temos nem um nem outro nesta fase, e o parceiro do canal monta apps, não escreve widgets
React (DOC.md §20.1).

Obriga: L7-10 (acessibilidade) e L7-04 (manual) medem sobre Custom Elements; L2-01 (mapa) expõe o mapa
como widget `<plat-mapa>` desde o início, não como função `initMapa` (o SIG de teste interno faz o segundo
e por isso a tela e o mapa se conhecem demais: LIDO em `map.js`, 458 linhas com estado global `S.mapa`).

---

## D2. Modelo de documento e identificadores

Decisão: todo construtor grava um documento com envelope fixo:

```
{ "tipo": "app|painel|formulario|fluxo|narrativa|pagina|popup|estilo|relatorio|captura|diagrama_trabalho|vista_camada",
  "esquema_versao": 1, "id": "<ULID do item>", "nome": "...", "corpo": { ...árvore de nós... } }
```

Regras que não mudam depois:

1. **Todo nó tem `id` ULID imutável, gerado na criação, nunca derivado de posição.** Referências entre nós
   (ação → alvo, bloco → mapa, passo → formulário) são por id. Motivo: reordenar, duplicar e mesclar
   (D12) sem quebrar ligações. O Experience Builder liga widgets por id de widget e vista de dado (doc
   "Add actions to widgets"); o QuickCapture usa `dataSourceId` próprio, não o índice do serviço (doc
   "Project JSON"); os dois aprenderam isso. Custo de errar: toda ação e toda ligação quebra ao mover um
   widget, e não há migração possível sem reescrever os documentos.
2. **JSON Schema por tipo e por versão** em `docs/esquemas/<tipo>-v<N>.json`, validado no servidor
   (jsonschema 4.26.0 já na venv, MEDIDO) e servido em `/api/esquemas/` para o editor gerar painéis de
   propriedades e para o agente (D16 do backlog: o agente escreve contra o mesmo esquema). Referências a
   itens do catálogo são validadas contra o inquilino da sessão (D11).
3. **Migração de esquema na leitura**, por função `migrar_<tipo>_v<N>_v<N+1>` em Python, com teste que
   aplica a cadeia inteira a documentos de exemplo guardados em `tests/documentos/`. Precedente: Puck
   documenta "Data Migration" entre versões com quebra; o Experience Builder migra apps de versões antigas
   ao abrir. Nunca migrar no navegador: um documento gravado é sempre lido pelo servidor primeiro.
4. **Português nos nomes de campo do documento** (regra 2 do ADR 0001): `paginas`, `widgets`, `acoes`,
   `fontes`, `vistas`, `nos`, `ligacoes`, `perguntas`, `blocos`.

Custo de mudar o envelope depois de haver documentos: uma migração por tipo. Custo de mudar a regra de
id: reescrever todos os documentos e todas as ligações. Por isso a regra 1 é a única deste documento
que se recomenda travar num teste de esquema que reprove qualquer nó sem ULID.

Obriga: L0-03 aceita os tipos de item acima e referencia `plat.item_versao` (D3).

---

## D3. Armazenamento e versionamento

```
plat.item_versao (item_id, versao int, corpo jsonb, sha256 text, autor_id, criado_em, rotulo text, tenant_id)
plat.item.versao_publicada int NULL
```

- Versão é imutável (mesma disciplina de `versao_migracao`: sha256 gravado, arquivo não se edita).
  Salvar = inserir versão nova; publicar = apontar `versao_publicada`; reverter = apontar para trás.
  Rascunho = versão mais alta não publicada; autosave grava versões com `rotulo = 'rascunho'` e um
  expurgo mantém as últimas N por item (política em L7-12).
- Diferença entre versões = diff de JSON no cliente (JSON Patch), sem tabela extra.
- Miniatura no publish (chromium headless, MEDIDO: captura em 25 ms, anexo A.2).

Opções rejeitadas: gravar só a última versão (o StoryMaps e o Dashboards guardam rascunho e publicado
separados; o usuário Esri espera "rascunho não altera o publicado", doc "Publish, revise, and share");
guardar histórico em git (bom para texto, ruim para consulta por SQL/RLS e para o adversário do P6).

Custo de mudar: nenhum enquanto a tabela for só de anexos ao item; se mais tarde um documento passar de
~1 MB (narrativas com muita mídia), o corpo vai para o Garage por sha256 e a coluna vira ponteiro, sem
mudar a API.

Obriga: L0-06 (backup) exporta `item_versao` no dump por inquilino; L7-12 define retenção.

---

## D4. Fontes, vistas e o formato do filtro

Um documento não fala em tabela nem em SQL. Fala em **fonte** (id de item do catálogo: camada, raster,
tabela, camada do acervo, fluxo publicado) e em **vista** (fonte + filtro + seleção + ordenação + lista
de campos), ambas com id (D2). Widgets se ligam a vistas. É o modelo do Experience Builder ("data
source" e "data view", doc "Core concepts") e é o que faz a ação "filtrar registros" ser global: quem
filtra a vista muda todos os widgets que a usam.

Formato do filtro: **CQL2-JSON** (OGC 21-065r2, anexo C), com o texto CQL2 aceito na entrada e convertido.
Motivos: é padrão OGC já exigido pelo OGC API - Features do L2-04; é JSON (serializa dentro do
documento sem escapar SQL); tem operadores espaciais e temporais; converte para `where` do FeatureServer
e para SQL parametrizado no servidor com uma única função. Rejeitados: `where` em texto SQL (injeção,
dialeto), JSONLogic (sem espacial), Arcade (proprietário).

Custo de mudar: uma função de conversão por lado (JS e Python) e uma migração dos documentos.

Obriga: L2-04 aceita CQL2-JSON no `query` além de `where`; L2-06 grava filtros de painel no mesmo
formato.

---

## D5. Barramento de mensagens (gatilho → ação)

Contrato, igual em app, painel, narrativa e site:

```
{ "id": ULID, "gatilho": {"origem": <id de widget|vista>, "evento": "clique|dado_adicionado|filtro_mudou|extensao_mudou|localizacao|registros_carregados|selecao_mudou|vista_mudou"},
  "acoes": [ {"alvo": <id>, "acao": "filtrar|selecionar|limpar_filtro|limpar_selecao|zoom|pan|piscar|popup|abrir|fechar|definir_parametro",
              "parametros": {...}, "relacao": {"tipo": "mesma_fonte|atributo|espacial", "campo_origem":..., "campo_alvo":..., "operador":...}} ] }
```

Os oito eventos são os oito gatilhos do Experience Builder (doc "Add actions to widgets"); as ações de
mapa são as sete dos Dashboards (filtrar, definir extensão, piscar, popup, pan, seguir feição, zoom; doc
"Actions"). A regra de relação entre fontes diferentes é a dos Dashboards: por atributo (tipos têm de
casar, com as duas exceções inteiro/decimal e data/data-hora) ou espacial (interseção de geometrias).

Implementação: `EventTarget` nativo + fila com corte de recursão (uma mensagem não pode disparar a si
mesma na mesma volta). Sem biblioteca.

Custo de mudar: o contrato é a parte cara (todo documento o cita); o transporte (EventTarget × loja)
troca-se sem tocar em documento.

Obriga: cada widget do L2 que virar widget de app declara no manifesto os eventos que emite e as ações
que aceita (D19).

---

## D6. Linguagem de expressão: uma, com dois avaliadores

O L2-10 já decidiu "linguagem de expressão própria documentada, equivalente ao Arcade nas funções mais
usadas, aplicada no servidor". A decisão desta linha é que **a mesma linguagem roda no navegador**, com o
mesmo analisador (gramática publicada em EBNF) e o mesmo arquivo de vetores de teste, porque o formulário
(visibilidade, cálculo, restrição), o popup (título, texto, elemento de expressão), o rótulo (L2-02), o
indicador de painel e o caminho condicional do fluxo/diagrama precisam avaliar sem ida ao servidor, e o
servidor precisa recusar exatamente o que o navegador recusaria (regra "a API recusa o que o formulário
recusaria", refutação do L5-03-b).

Superfície recomendada: sintaxe de expressão infixa (como Arcade e XLSForm) com `$feicao.campo`,
`${campo}` aceito na importação de XLSForm, funções em português e inglês como sinônimos documentados
(`Area()/Area()`, `Texto()/Text()`), sem atribuição, sem laço livre (só `Map/Filter` com limite de passos),
sem acesso a rede. Perfis (como os "profiles" do Arcade, doc oficial): popup, rótulo, formulário, restrição,
painel, fluxo — cada perfil declara as variáveis disponíveis.

Rejeitados: JSONLogic (JSON puro; sem tipo de data/geometria; implementação Python sem manutenção);
JSONata (80 kB, boa, mas sintaxe estranha ao usuário de Arcade/XLSForm e sem avaliador Python
mantido); Arcade (proprietário); JavaScript com `Function()` (impossível de isolar).

Custo de mudar a linguagem depois: reescrever todas as expressões gravadas — inviável. Custo de trocar o
avaliador mantendo a gramática: zero para os documentos. Por isso a gramática e os vetores nascem antes
do primeiro documento com expressão.

Obriga: L2-10 entrega EBNF + vetores (`tests/expressoes/*.json`) desde o primeiro turno; L2-02 usa a
mesma linguagem nos rótulos.

---

## D7. Formato de estilo e legenda

Estilo de camada = **MapLibre Style Spec** puro (`layers[].paint/layout/filter` com expressões da spec),
acrescido de um bloco `plat_construtor` (campo, método de classificação, cortes, rampa, símbolo) que só o
construtor lê para reabrir os controles. O renderizador (MapLibre) nunca lê o bloco; o construtor nunca
grava fora da spec. Validação com o validador oficial da spec no `make check`.

Legenda: derivada do estilo por código próprio (o precedente `maplibre-gl-legend`, MIT, 45 estrelas, é
pequeno demais para vender e serve de referência de leitura). Símbolos: SVG próprios com licença
registrada (D19 do backlog, `VERSOES.txt`).

Custo de mudar: um estilo MapLibre é lido por QGIS (plugin), por Martin e por qualquer visualizador
compatível; sair dele custaria um conversor. Não há motivo previsível.

Obriga: L2-02 grava o bloco `plat_construtor`; L5-38 converte `renderer` do Web Map Specification
(9 tipos listados na doc: simple, uniqueValue, classBreaks, heatmap, dotDensity, dictionary, pieChart,
predominance, temporal) para os 4 primeiros e declara os 5 restantes como fora.

---

## D8. Formulário: documento próprio, XLSForm como formato de troca

Opções medidas (anexo B):

| biblioteca | licença | tamanho do artefato | veredito |
|---|---|---|---|
| SurveyJS Creator (survey-creator-js 3.0.3) | comercial ("SEE LICENSE IN LICENSE"; EULA da Devsoft Baltic, licença por desenvolvedor, doc de licenciamento testada) | 98 kB + survey-core 1,42 MB | fora: licença |
| SurveyJS Form Library (survey-core) | MIT | 1,42 MB | fora: peso 24× o orçamento de módulo e traz o modelo de documento deles |
| Form.io (@formio/js 5.5.2) | MIT | 1,67 MB, 35 dependências | fora: peso e dependências |
| Enketo (enketo-core 9.0.1) | Apache-2.0 | 12 dependências, precisa de build; renderiza ODK XForms | fora nesta fase; referência para a PWA se o L2-07 optar por XForms |
| próprio | — | estimado ≤ 60 kB (renderizador) + ≤ 60 kB (editor) | recomendado |

Motivo: o formulário roda em três lugares com o mesmo documento (edição web L2-03, PWA offline L2-07,
widget de app) e avalia a linguagem de D6; nenhuma biblioteca pronta usa a nossa linguagem nem grava no
nosso documento. O que se herda dos padrões é o VOCABULÁRIO: tipos de pergunta e colunas do XLSForm
(doc "XLSForm essentials" e "Question types" do Survey123; xlsform.org), elementos e lógica do Field Maps
("Build the form"). XLSForm é o formato de exportação/importação (L5-03-e), verificado com pyxform, o
que dá ODK Central e a migração do Survey123 (L2-08) de graça.

Regra de esquema herdada do Field Maps (doc): nome, tipo e tamanho de campo travam depois do primeiro
salvamento; alterar exige apagar e criar (L5-03-a, L5-31).

Custo de mudar: importar/exportar XLSForm protege o conteúdo; trocar o renderizador custa só o
renderizador.

Obriga: L2-07 renderiza o documento de formulário do L5-03, não um segundo formato; L2-10 expõe
domínios codificados e tabelas relacionadas por API para o construtor.

---

## D9. Fluxo: grafo JSON, execução como job, renderizador próprio

Documento: `{nos: [{id, tipo: "ferramenta|entrada|saida|para_cada|se|subfluxo", ferramenta_id, versao,
parametros, posicao}], ligacoes: [{id, de: {no, porta}, para: {no, porta}}], parametros: [...]}`; portas
tipadas (`vetor:ponto|linha|poligono|qualquer`, `raster`, `tabela`, `numero`, `texto`, `lista`,
`extensao`). O catálogo de nós vem do OpenAPI das ferramentas (L2-05, L3-01, fluxos publicados, scripts
do L2-16): nenhum nó escrito à mão.

Modelo de job (D5 do backlog, L0-05): uma execução = um job com sub-passos (um por nó, em ordem
topológica); cada passo grava o manifesto de proveniência (entradas com sha256 de conteúdo, parâmetros,
versão da ferramenta, git sha, duração, mensagens); a camada de saída recebe o manifesto inteiro. É o
portão de proveniência que o motor de LT já aplica (`motor/release.py`, LIDO: "se qualquer artefato
declarar commit diferente do corrente, o release falha"), levado ao nível de nó. Reexecução com as
mesmas entradas dá o mesmo hash — é o que permite chamar o resultado de reprodutível (regra do acervo:
"reprodutível de verdade = script + sha256").

Agendamento: tabela `plat.agenda` (cron, fuso, próxima execução, pausado, expira) lida pelo worker a cada
minuto; sem `croniter`/`apscheduler` instalados hoje (MEDIDO: ausentes na venv) — o item que implementar
escolhe instalar `croniter` ou escrever o analisador de 5 campos (≈ 150 linhas). Saída versionada com
`%t%` no nome (doc "Schedule geoprocessing tools" do Pro).

Renderizador do editor de nós — opções medidas (anexo B):

| candidato | licença | tamanho | último commit | veredito |
|---|---|---|---|---|
| Drawflow 0.0.60 | MIT | 46 kB, 0 dependências, vanilla | 2024-10-19, 273 issues abertas | único vanilla; sem manutenção há 22 meses |
| Rete 2.0.6 | MIT | núcleo 18 kB + conexão 24 kB + render-utils 16 kB; renderização exige plugin de framework (rete-lit-plugin 340 kB) | 2026-07-24 | mantido, mas empurra para D1(b) |
| litegraph.js 0.7.18 / fork Comfy 0.17.2 | MIT | 176 a 619 kB | 2024-08 / 2026-01 | pesado; feito para grafos de processamento de imagem |
| xyflow 12.11 | MIT | 188 kB | 2026-09-02 | exige React |
| próprio (SVG para ligações, HTML para nós, Pointer Events) | — | ≤ 60 kB | — | recomendado |

Recomendação: **próprio**, porque o documento já é nosso, o editor de nós é reusado pelo gerenciador de
trabalho (L5-33-a) com outra paleta, e nenhum candidato mantido dispensa framework. Licença de troca: se
o e2e do L5-02-a medir menos de 30 fps ao arrastar com 200 nós, Drawflow entra vendido (46 kB) como
renderizador, sem tocar no documento.

Exportação Python (L5-02-d): gerada por modelo Jinja2 (3.1.6 na venv) a partir do grafo, chamando o SDK
do L7-08; um `def fluxo(parametros)` por fluxo, sub-fluxos em módulos (forma do "Export a model to
Python" do Pro).

Obriga: L0-05 entrega sub-passos e cancelamento cooperativo; L7-08 gera função por ferramenta do
OpenAPI; L2-05/L3-01 declaram tipo de entrada/saída por porta no OpenAPI (senão o editor não valida
tipo).

---

## D10. Publicação, token de app e incorporação

- URL publicada: `/p/<inquilino>/<slug>` (app, painel, narrativa, formulário público, site em
  `/s/<inquilino>/`). Leitura por função `SECURITY DEFINER plat.publicado_ler(slug, token)` que devolve só
  a versão publicada; o rascunho nunca é alcançável por essa rota.
- Acesso: público, inquilino, grupo, ou link com token. O **token de app** é um `token_servico` (ADR
  0001) com `escopos = ['ler:item:<id>', ...]` cobrindo exatamente os itens de dado citados no documento
  publicado; regenerado a cada publish (a lista pode mudar), revogável, com log de leitura (P6). Os
  serviços de dado (FeatureServer/OGC/tiles) verificam o escopo por item. Revogar o app = revogar o token.
- Incorporação: o nginx do ADR manda `X-Frame-Options: DENY` em tudo; `/p/` passa a responder
  `Content-Security-Policy: frame-ancestors <lista do app>` e sem `X-Frame-Options` (ADR novo, item
  L5-14). Parâmetros do app hospedeiro entram por `#param=valor` (regra dos Dashboards, doc "URL
  parameters": hash, sem recarregar) e por `postMessage`.
- Exportação estática: HTML + JSON + instantâneo dos dados citados (GeoJSON/PMTiles/COG por URL absoluta
  ou embutidos), para o hub e para o appliance (L7-11).
- Sites (L5-20): renderizados no servidor para HTML estático (Jinja2), com o JS só para os widgets vivos;
  `noindex` por padrão (regra da casa), `index` só por opção explícita do inquilino com aviso.

Custo de mudar: a forma da URL é pública e vira link em site de cliente — trocar depois custa
redirecionamentos para sempre. Decidir agora e não mais mexer.

Obriga: L1-02 e L2-04 aceitam escopo por lista de itens; L0-01 (nginx) ganha a exceção de `/p/`.

---

## D11. Isolamento por inquilino nos documentos

- `plat.item_versao` tem `tenant_id` e RLS como toda tabela (ADR 0001 §3.3). O adversário do P6 testa
  A→B em `/api/itens/{id}/versoes`, em `/p/` com token de A em item de B, e no `frame-ancestors`.
- Validação no servidor de que toda fonte/vista/ferramenta citada no documento pertence ao inquilino da
  sessão (ou é do acervo, L6-01, ou pública). Documento que cita item de fora = 422, nunca gravado. É a
  única defesa contra o agente (L5-16) ou um importador escrever referência cruzada.
- Expressões (D6) e expressões de dado de painel (L5-19) não podem nomear tabela; só vistas por id. O
  SQL de uma expressão de dado é gerado pelo servidor sobre views do inquilino, nunca recebido em texto
  livre.
- Widgets personalizados (D19) de um inquilino nunca carregam em documento de outro; sandbox opcional
  por iframe.

Obriga: nada novo além do ADR; reforça que o adversário de cada item L5 inclui o teste cruzado.

---

## D12. Desfazer/refazer e edição concorrente

- Desfazer/refazer = JSON Patch (RFC 6902) com a operação inversa gravada na pilha; arrastar = uma
  operação agrupada. Funciona porque os nós têm id (D2): `replace /nos/<id>/posicao` é estável.
- Concorrência nesta fase: **versão otimista** (`base_versao` no PUT; 409 com o documento atual quando
  diverge), presença por SSE (quem está no documento e em que nó), mesclagem automática quando os dois
  lados tocaram nós disjuntos. Sem CRDT.
- CRDT (Yjs 13.6.32, MIT, MEDIDO 300 kB) fica para depois e só se o e2e do L5-13 medir perda de trabalho
  com a mesclagem por nó. Preparação que custa zero agora e evita reescrita depois: o documento é uma
  árvore JSON com ids únicos, exatamente o que um `Y.Map` aninhado representa.

Custo de mudar para CRDT depois: trocar a camada de sincronização; o documento não muda; o histórico de
versões (D3) continua sendo o registro oficial.

---

## D13. Temas

Tema = tokens CSS em JSON (cores, tipografia, raio, espaçamento, sombras), aplicados em `:root` do app;
claro/escuro; três níveis (plataforma → inquilino via `tenant.config` → documento). Contraste WCAG 1.4.3
calculado no editor. Referências de paridade: os seis temas padrão dos StoryMaps (doc "Theme reference":
Summit, Obsidian, Ridgeline, Mesa, Tidal, Slate, com cores publicadas) e os temas do Web AppBuilder.
Nada de bibliotecas de componentes com tema próprio (Shoelace 8 MB desempacotado, fora).

---

## D14. Acessibilidade do arrasto (regra que vale para todos os construtores)

WCAG 2.2, critério 2.5.7 "Dragging Movements", nível AA (URL testada): toda função operada por arrasto
tem de ter alternativa de ponteiro único (clicar/tocar), separada da alternativa por teclado (2.1.1).
Consequência de desenho: cada operação de arrasto tem um botão ou item de menu equivalente ("adicionar ao
fim", "mover para…", "ligar a…", setas de reordenar), e o e2e de cada construtor monta o mesmo documento
pelos dois caminhos e compara (diff vazio). MEDIDO (anexo A.1): o caminho por teclado funciona no chromium
do playwright no mesmo teste do arrasto. Isso também é o que torna os construtores testáveis sem
depender de gestos frágeis de automação.

---

## D15. Móvel

Duas estratégias, as duas no documento: reflow responsivo (grade 12 → 1 coluna; painéis viram abas
inferiores — padrão do SIG de teste interno, LIDO em `core.js` `ligarCasca()`), e **vista móvel própria**
opcional por documento (elementos e posições distintos; largura ≤ 600 px carrega a vista móvel — regra
dos Dashboards, doc "Introduction to dashboards"). Pré-visualização por dispositivo no construtor em
iframe de mesma origem (precedente Puck "Viewports"). e2e em três viewports (Pixel 7, iPad, 1440) é
cláusula de todo item com tela.

---

## D16. Idioma dentro do documento

Rótulos podem ser texto simples ou mapa por idioma `{"pt": "...", "en": "..."}` (precedente
`label::idioma` do XLSForm). O renderizador escolhe pelo idioma do usuário e cai para `pt`. Chaves da
interface do construtor em `web/js/i18n/<idioma>.json` com teste de chave faltante. O L7-10 mede o
produto inteiro em cima disso.

---

## D17. Relatório e PDF com mapa

Opções: (a) WeasyPrint 69.0 (já instalado; é o que o SIG de teste interno usa em `relatorios.py`, LIDO)
— texto e tabela ótimos, mas não executa WebGL, logo o mapa teria de virar imagem antes; (b) chromium
headless do playwright (já instalado para o e2e) renderizando o MESMO runtime de widgets com CSS de
impressão e `page.pdf()`.

MEDIDO (anexo A.2): no chromium 147 do playwright desta máquina, sem nenhuma flag, o WebGL vem por
SwiftShader (ANGLE/Vulkan) e um mapa MapLibre com 2.000 polígonos fica pronto (`idle`) em 330 a 350 ms;
captura PNG em 25 ms; PDF A4 em 17 ms; 40 kB de PDF. A tentativa com flags de SwiftShader dá o mesmo
resultado — não são necessárias.

Recomendação: **(b)** para relatório e impressão de layout (L2-12 pode reusar), num processo de worker
próprio (`plat-worker-pdf`) com `MemoryMax` medido (o chromium ocupa centenas de MB; a máquina tem 3 GB
livres). WeasyPrint continua para relatório tabular sem mapa se o worker de PDF estiver ocupado.

Obriga: L2-12 decide se usa o mesmo caminho; L0-05 aceita um worker de tipo `pdf` com concorrência 1.

---

## D18. CRS nos documentos

Vistas de mapa gravam `centro [lon, lat]` e `zoom` em EPSG:4326/Web Mercator (o que o MapLibre consome);
extensões em `[minx, miny, maxx, maxy]` 4326. Coordenadas exibidas ao usuário seguem `tenant.config.srid_padrao`
(ADR 0001) com conversão no cliente (proj4js, 100 kB, ou tabela de definições EPSG servida pela API a
partir do `spatial_ref_sys` do PostGIS — preferir a segunda, sem biblioteca). Fluxos gravam o CRS de cada
saída no manifesto (regra da casa: "CRS explícito em toda comparação"). O QuickCapture só aceita Web
Mercator no mapa (doc "Project JSON"); nós não impomos isso ao dado, só à vista.

---

## D19. Extensibilidade: manifesto de widget e API versionada

```
{ "nome": "plat-semaforo", "versao": "1.0.0", "api_widget": 1, "modulo": "./widgets/semaforo.js",
  "esquema_config": {...JSON Schema...}, "eventos": ["selecao_mudou"], "acoes": ["filtrar"],
  "fontes": {"min": 1, "max": 1, "tipos": ["vetor"]}, "i18n": {"pt": {...}, "en": {...}} }
```

- O mesmo manifesto serve para os widgets da casa e para os do parceiro (L5-36). `api_widget` é o
  contrato: mudar de forma incompatível = `api_widget: 2` com adaptador para o 1 por um ciclo.
- Carregamento por `import()` só dos widgets citados (MEDIDO: o e2e conta módulos por
  `performance.getEntriesByType('resource')`). Nada de bundle único.
- Sandbox opcional (iframe + ponte `postMessage` para o barramento) para widget de terceiro.

É o equivalente do Jimu (doc "Introduction to ArcGIS Experience Builder", developers) sem React e sem
TypeScript obrigatório. Custo de mudar: o manifesto é lido por documentos (o nome do widget está no nó);
renomear widget exige migração (D2.3).

---

## D20. Grade de layout e painéis: biblioteca ou CSS próprio

| candidato | licença | tamanho | último commit | veredito |
|---|---|---|---|---|
| GridStack 13.2.0 | MIT | 88 kB (`gridstack-all.js`) + 5 kB CSS, 0 dependências, sem framework | 2026-09-04 (9,1 mil estrelas) | recomendado para a grade de PAINEL (arrastar/redimensionar/aninhar/responsivo por colunas/salvar-restaurar) |
| Muuri | MIT | 84 kB | 2024-05-25 | sem manutenção |
| dockview-core | MIT | 374 a 525 kB | ativo | pesado; feito para IDE |
| CSS Grid próprio | — | ~10 kB | — | recomendado para o LAYOUT de APP (linhas/colunas/painel lateral: poucos contêineres, sem redimensionamento livre) |

GridStack entra vendido pela regra 3 do ADR (ESM, MIT, linha em `VERSOES.txt`) e só carrega na tela de
painel. Custo de trocar: o documento do painel grava `{coluna, linha, largura, altura}` em unidades de
grade, não o formato do GridStack — o adaptador tem ~50 linhas.

---

## D21. Gráficos

| candidato | licença | tamanho | veredito |
|---|---|---|---|
| uPlot 1.6.32 | MIT | 51 kB | só série temporal (linha); ótimo para o L1-04 e L2-14 |
| Chart.js 4.5.1 | MIT | 209 kB (`chart.umd.min.js`) | barras/linha/pizza/dispersão/histograma; recomendado para app e painel, carregado só nas telas com gráfico |
| ECharts 6.1.0 | Apache-2.0 | 500 kB (simple) a 1,12 MB (completo) | tudo (medidor, treemap, sankey), mas 2,5 a 5× o Chart.js |
| plotly.js | MIT | 4,3 MB | fora |

Medidor (gauge) e indicador: SVG próprio (≈ 3 kB), porque o Chart.js não tem medidor e o ECharts custa
500 kB por isso. Agregação sempre no servidor (L2-04 estatística), nunca no navegador sobre a camada
inteira.

---

## D22. Tabela

Tabulator 6.5.2 (MIT) pesa 446 kB; o SIG de teste interno renderiza tabelas com HTML próprio e paginação
no servidor (LIDO em `pages.js`). Recomendação: **própria**, com virtualização simples (janela de 200
linhas) e paginação/ordenação pelo FeatureServer/OGC (`resultOffset/resultRecordCount/orderByFields`);
Tabulator só se o e2e do L5-01-c medir p95 > 300 ms por página com 100 mil feições e o código próprio não
resolver.

---

## D23. Texto rico e sanitização

Texto de widget, bloco de narrativa e popup gravam **Markdown** (portável, diffável, seguro de
versionar) e renderizam com `markdown-it` (MIT, 115 kB) ou com o conversor mínimo próprio (títulos,
negrito, lista, link, imagem: ~4 kB) — começar pelo próprio; e **DOMPurify** (Apache-2.0/MPL-2.0, 29 kB)
em qualquer HTML que venha de documento, obrigatório desde o primeiro widget de texto (o adversário de cada
item injeta HTML). Editor visual (Quill 2, BSD-3, 209 kB) fica como opção tardia do bloco de texto da
narrativa; o documento não muda.

---

## D24. Sites e dados abertos

Página de site é documento tipo `pagina` renderizado no servidor (Jinja2) para HTML completo sem JS
(SEO e leitor de tela), com o JS hidratando só widgets vivos (mapa, galeria). Dados abertos: página por
conjunto com licença ESCRITA obrigatória (regra D17 do acervo: sem licença o dado é auditável, não
vendável nem publicável), JSON-LD `schema.org/Dataset` + DCAT, downloads gerados sob demanda com cache
por sha256. `noindex` por padrão em tudo; indexação só por opção explícita do inquilino (regra da casa).

---

## D25. Gerenciador de trabalho (tarefas humanas)

Reusa o editor de nós (D9) com paleta de PASSOS (manual, formulário, abrir app, executar fluxo, decisão,
aprovação, atribuir, e-mail, webhook, esperar) e caminhos condicionais na linguagem de D6. Diagrama tem
versão ATIVADA (imutável) e rascunho; cada trabalho nasce preso à versão em que foi criado (doc "Create
and manage workflow diagrams": ativar, rascunho, duplicar). Trabalho = linha com propriedades + extensão
(tabela de propriedades estendidas por inquilino) + localização (geometria) + histórico de passos.
Atribuição espacial por camada de referência (doc "Advanced Assignment") é uma consulta PostGIS. Recorrência
usa a agenda de D9. Na Esri a recorrência exige licença "Server Advanced" (doc "Schedule and manage
recurring jobs"); aqui é a mesma tabela `plat.agenda`.

---

## 1. O que a Esri faz, construtor a construtor (para a paridade, URLs no anexo C)

- **Experience Builder** (doc.arcgis.com, "latest"): 67 widgets em 6 grupos (30 centrados no mapa, 15 de
  dado, 6 de página, 6 de menu/barra, 8 de layout, 2 de seção — contados na página "Widgets"); páginas
  de tela cheia e roláveis, cabeçalho/rodapé, janelas fixas e ancoradas, seções com vistas; 8 gatilhos e
  ações de dado × widget ("Add actions to widgets"); temas; modo expresso; edição desenvolvedor = React +
  Redux + TypeScript (Jimu). Fora do nosso alcance por depender de produto Esri: Business Analyst,
  Autodesk Construction Cloud (3 widgets), Floor Filter (Indoors), Oriented Imagery, Suitability Modeler
  (nós temos o motor L3 — vira widget), Survey (nós temos L5-03), QuickCapture (nós temos L5-34).
- **Web AppBuilder**: a doc oficial diz que será aposentado no 2º trimestre de 2027 (API JS 3.x aposentada
  em julho de 2024); temas Foldable/Dashboard/Launchpad/Billboard/Box/Dart/Jewelry Box; widgets em
  controlador, em painel e na tela. Serve para a paridade de "modos de app" (L5-01-f), não como alvo.
- **Instant Apps**: 20+ modelos ("Choose an app template": 3D Viewer, Atlas, Attachment Viewer, Basic,
  Chart Viewer, Compare, Countdown, Data Explorer beta, Exhibit, Gallery, Imagery Viewer, Insets,
  Interactive Legend, Manager, Nearby, Observer, Portfolio, Public Notification, Reporter, Sidebar,
  Slider, Zone Lookup); modo expresso; publicar em poucos passos. Nós: 12 modelos em dois itens + o motor.
- **Dashboards**: 12 elementos (mapa, lista, gráfico serial, pizza, tabela, seletores de categoria/número/
  data, indicador com referência, detalhes, medidor, conteúdo incorporado, texto rico), 7 ações de mapa,
  4 eventos-fonte, relação por atributo/espacial, "renderizar só quando filtrado", vistas desktop/móvel
  (≤ 600 px), parâmetros de URL de 5 tipos com `#`, expressões de dado (Arcade) como fonte.
- **StoryMaps**: blocos de conteúdo (texto, botão, separador, código, mapa, ação de mídia, gráfico,
  infográfico, tabela, imagem, vídeo, áudio, embed, app, linha do tempo); imersivos sidecar (acoplado,
  flutuante, apresentação), map tour (guiado, explorador, categorizado, a partir de camada), swipe;
  briefings, frames, coleções; 6 temas padrão com cores publicadas; rascunho automático e publish com
  verificação de compartilhamento dos itens citados; texto alternativo obrigatório em mídia.
- **Hub / Enterprise Sites**: páginas por cartões, catálogo de dados abertos com downloads e API; as
  páginas de doc do Hub são renderizadas por JavaScript e não devolvem texto ao `curl` (anexo C), por isso
  a paridade do L5-20/21 se escreve contra a doc do Sites e o modelo DCAT.
- **Survey123 / Field Maps**: XLSForm com ~35 colunas suportadas e ~30 tipos de pergunta; web designer com
  os mesmos tipos; fórmulas (operadores, funções, restrições, cálculos, `pulldata`, consulta a camada);
  Field Maps: 8 elementos básicos, 3 de escolha, anexos, grupos, lógica (visível/obrigatório/editável/
  cálculo em Arcade), campo trava tipo/tamanho após salvar; relatório de feição (Feature Report) cobra
  crédito no Online e é gratuito com limitações no Enterprise.
- **Workflow Manager**: diagramas com biblioteca de passos, rascunho → ativar, duplicar; modelo de trabalho
  = diagrama + propriedades + propriedades estendidas; atribuição avançada (usuário, grupo, espacial por
  camada de referência); recorrência (licença Server Advanced); webhooks para criar trabalhos.
- **ModelBuilder / geoprocessamento (Pro 3.7)**: um iterador por modelo (sub-modelo para mais), parâmetros
  obrigatório/opcional/derivado, exportar para Python (função por modelo, sub-modelos em módulos),
  relatório do modelo, histórico de geoprocessamento com reabrir, agendamento pelo Task Scheduler com
  `%t%` no nome da saída.
- **QuickCapture**: designer por arrasto de botões, projeto JSON (basemap, dataSources, templateGroups,
  templates, userInput, tracking), só Web Mercator no mapa, uso em Experience Builder e Survey123.
- **Mission**: Manager (web), Responder (móvel) e Mission Server dedicado; tarefas com tipo/status/
  atribuído/prazo/prioridade; relatórios; comunicação par a par. Nós entregamos o Manager e o Responder
  sobre L2-14; o servidor dedicado e o par a par ficam fora.
- **Carto Builder/Workflows**: componentes em 20+ categorias (agregação, controle, junção, espacial,
  índices, criação de tileset…), agendamento, histórico de versões, execução por API, variáveis; toda a
  execução é SQL no armazém do cliente. Nossa diferença: execução como job PostGIS/raster com proveniência
  por nó; sem armazém externo.
- **Felt**: SDK JS só no plano Enterprise (doc); linguagem de estilo própria (Felt Style Language).
  Referência de UX (mapa colaborativo), não de arquitetura.
- **Kepler.gl**: React + Redux, exige token Mapbox; referência de exploração visual de milhões de pontos
  (deck.gl), fora da pilha.
- **Retool**: referência de builder de componentes (dezenas de componentes, eventos, formulário por JSON
  Schema); proprietário.

---

## 2. O que esta linha obriga nas outras (consolidado)

| linha | obrigação | item L5 que pede |
|---|---|---|
| L0-01 | exceção de `X-Frame-Options` em `/p/` com `frame-ancestors` por app | L5-14 |
| L0-03 | tipos de item e `plat.item_versao` | L5-05 |
| L0-05 | job com sub-passos e cancelamento cooperativo; worker `pdf` | L5-02-b, L5-29 |
| L1-02 | token de serviço com escopo por lista de itens | L5-14 |
| L2-01 | mapa como Custom Element `<plat-mapa>` | L5-06 |
| L2-02 | estilo MapLibre puro + bloco `plat_construtor`; rótulos na linguagem de D6 | L5-27 |
| L2-04 | CQL2-JSON no query; `queryRelatedRecords`; estatística agregada | L5-07, L5-26, L5-01-c |
| L2-05/L3-01 | tipo de porta declarado no OpenAPI de cada ferramenta | L5-02-a |
| L2-06 | grava filtros em CQL2-JSON e posições em unidades de grade | L5-17 |
| L2-07 | renderiza o documento de formulário do L5-03 | L5-03-a |
| L2-10 | EBNF + vetores de teste da linguagem desde o primeiro turno | L5-11 |
| L2-12 | pode reusar o chromium headless medido | L5-29 |
| L7-08 | SDK Python com função por ferramenta gerada do OpenAPI | L5-02-d |
| L7-10 | mede sobre a base de acessibilidade do L5-12 | L5-12 |

---

## Anexo A — medições (05/09/2026, esta máquina, scratchpad apagável)

### A.1 Arrastar e soltar sem biblioteca, sob o chromium do playwright

Página de teste com três mecanismos: HTML5 Drag and Drop (paleta → tela, `dataTransfer`), arrasto por
Pointer Events com `setPointerCapture`, e alternativa por teclado (Enter sobre o item focado). Teste com
`/home/dev/plataforma/enterprise/venv/bin/python` (playwright 1.59.0, chromium 147).

```
$ venv/bin/python dnd_test.py
{"log": "drop:mapa\ndrop:tabela\nptr:100,30\nkbd:mapa\n", "canvas_widgets": 3, "html5_drag_ms": 122.9}
{"mobile_html5_dnd": true, "mobile_canvas": 1, "mobile_log": "drop:mapa\n"}
```

Leitura: os dois drops HTML5 chegaram; o arrasto por ponteiro moveu a caixa 100 px em x e 30 px em y
como pedido; o caminho por teclado adicionou o mesmo widget; na emulação Pixel 7 (`p.devices`), o
`drag_and_drop` também completou. Conclusão: a base do editor (L5-08) não exige biblioteca nem framework,
e é automatizável no e2e por três caminhos.

### A.2 Mapa MapLibre renderizado em headless para captura e PDF (base do relatório, L5-29)

Página com MapLibre GL JS 4.7.1 (cópia do `web/vendor/` do repositório), 2.000 polígonos em GeoJSON com
cor por expressão, `preserveDrawingBuffer: true`; medição até o evento `idle`, depois `screenshot()` e
`pdf()`.

```
$ venv/bin/python mapa_test2.py
{"label": "padrao", "args": [], "webgl_renderer": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
 "mapa": {"ms": 349, "loaded": true, "feicoes": 2000}, "ate_idle_ms": 432, "screenshot_ms": 25, "pdf_ms": 17,
 "png_bytes": 44659, "pdf_bytes": 40526, "console": ["GL Driver Message ... GPU stall due to ReadPixels" x4]}
{"label": "swiftshader", "args": ["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"],
 "mapa": {"ms": 330, "loaded": true, "feicoes": 2000}, "ate_idle_ms": 410, "screenshot_ms": 70, "pdf_ms": 41, "console": []}
$ python3 -c "...PIL..."   # pixels diferentes do fundo #eeeeff
padrao      pixels nao-fundo: 108900 de 480000 22.7 %  cores distintas 496
swiftshader pixels nao-fundo: 108900 de 480000 22.7 %  cores distintas 496
```

Leitura: WebGL está disponível por padrão (SwiftShader), o mapa desenhou (22,7 % da área com 496 cores
distintas = os polígonos coloridos), `queryRenderedFeatures` viu as 2.000 feições, e o PDF saiu em 17 ms.
As flags de SwiftShader não mudam o resultado (apenas silenciam avisos de desempenho). Primeira tentativa
falhou por erro de sintaxe na página de teste (registrado para não repetir: gerar o GeoJSON em Python, não
em JS inline).

### A.3 Ferramentas já presentes na venv do repositório (para as decisões D2, D9, D17)

```
jsonschema 4.26.0 · pydantic 2.13.4 · jinja2 3.1.6 · weasyprint 69.0 · playwright (chromium 147)
shapely 2.1.2 · rasterio 1.5.0 · pyproj 3.7.2
ausentes: croniter, procrastinate, apscheduler
node v22.22.2 (só para ferramentas de build opcionais; nada do produto depende)
```

### A.4 Referências lidas em código que roda nesta máquina

- `SIG de teste interno/web/js/`: `core.js` 20,9 kB (estado `S`, `api()`, roteador, estado na URL,
  `ligarCasca()` móvel), `map.js` 39,2 kB (MapLibre, temáticos, swipe, medição, sketch), `niveis.js`
  50,0 kB, `pages.js` 67,4 kB, `v3.js` 49,8 kB = 227 kB de módulos próprios sem framework, em produção.
- `SIG de teste interno/app/relatorios.py`: PDF por WeasyPrint (`HTML(string=...).write_pdf()`), sem mapa.
- motor logístico `web/motor.js` 37,5 kB: motor multicritério inteiro calculado no navegador com presets
  declarados — modelo do widget "motor" (L3-01 como widget de app).
- motor de LT `motor/release.py`: portão de proveniência por commit e sha256 (modelo do L5-02-b).

## Anexo B — bibliotecas candidatas medidas (registro npm + jsDelivr + API GitHub, 05/09/2026)

Tamanho = bytes do arquivo minificado que iria para `web/vendor/`, lido da listagem do jsDelivr (sem
download do pacote); último commit = `pushed_at` da API do GitHub.

| pacote | versão | licença | arquivo | bytes | último commit | estrelas | uso proposto |
|---|---|---|---|---|---|---|---|
| sortablejs | 1.15.7 | MIT | Sortable.min.js | 45.478 | 2026-03-24 | 31,2 mil | opcional: reordenar listas/outline |
| interactjs | 1.10.28 | MIT | dist/interact.min.js | 98.203 | 2026-08-01 | 12,9 mil | não necessário (Pointer Events nativos medidos) |
| gridstack | 13.2.0 | MIT | dist/gridstack-all.js | 88.145 | 2026-09-04 | 9,1 mil | grade de painel (D20) |
| drawflow | 0.0.60 | MIT | dist/drawflow.min.js | 46.190 | 2024-10-19 | 6,1 mil | reserva para o editor de nós |
| rete + connection + render-utils | 2.0.6 | MIT | 3 arquivos | 18.496 + 23.819 + 16.096 | 2026-07-24 | 12,2 mil | renderização exige plugin de framework (lit 340 kB) |
| litegraph.js / @comfyorg/litegraph | 0.7.18 / 0.17.2 | MIT | build/litegraph.core.min.js / dist/litegraph.es.js | 176.325 / 619.240 | 2024-08-01 / 2026-01-14 | 8,1 mil / 252 | fora |
| @xyflow/react | 12.11.6 | MIT | dist/umd/index.js | 188.290 | 2026-09-02 | 38,3 mil | exige React |
| @dnd-kit/core | 6.3.1 | MIT | — | 42.422 | 2026-07-13 | 17,6 mil | exige React |
| @measured/puck | 0.20.2 | MIT | — | — | 2026-09-04 | 13,3 mil | exige React |
| @craftjs/core | 0.2.12 | MIT | — | 37.809 | 2025-02-14 | 8,7 mil | exige React |
| grapesjs | 0.23.6 | BSD-3-Clause | dist/grapes.min.js | 1.151.347 | 2026-08-26 | 26,2 mil | fora: construtor de HTML/CMS, 1,15 MB |
| survey-core / survey-js-ui | 3.0.3 | MIT | survey.core.min.js | 1.422.755 / 222.788 | 2026-09-05 | 4,9 mil | fora (D8) |
| survey-creator-js / -core | 3.0.3 | comercial (EULA) | — | 97.786 / — | 2026-09-04 | 1,3 mil | fora: licença |
| @formio/js | 5.5.2 | MIT | dist/formio.full.min.js | 1.674.188 (35 deps) | 2026-09-04 | 2,1 mil | fora (D8) |
| enketo-core | 9.0.1 | Apache-2.0 | (12 deps, build) | — | 2026-09-04 | 32 | referência XForms |
| react / react-dom | 19.2.8 | MIT | sem UMD; cjs/react-dom-client.production.js | 536.016 | — | — | exige bundler |
| preact | 10.29.8 | MIT | dist/preact.min.js | 11.322 | 2026-09-05 | 38,8 mil | licença de troca D1(b) |
| lit | 3.3.3 | BSD-3-Clause | (núcleo ~7 kB; pacote 106 kB) | — | 2026-09-03 | 21,8 mil | licença de troca D1(b) |
| vue | 3.5.42 | MIT | dist/vue.global.prod.js | 167.536 | — | — | fora |
| alpinejs | 3.17.1 | MIT | dist/cdn.min.js | 55.744 | 2026-09-04 | 31,9 mil | não necessário |
| chart.js | 4.5.1 | MIT | dist/chart.umd.min.js | 208.522 | 2026-05-27 | 67,7 mil | gráficos (D21) |
| uplot | 1.6.32 | MIT | dist/uPlot.iife.min.js | 51.081 | 2026-04-22 | 10,5 mil | série temporal |
| echarts | 6.1.0 | Apache-2.0 | dist/echarts.simple.min.js / echarts.min.js | 500.315 / 1.121.883 | 2026-09-04 | 67,2 mil | reserva |
| tabulator-tables | 6.5.2 | MIT | dist/js/tabulator.min.js | 445.984 | — | — | reserva (D22) |
| quill | 2.0.3 | BSD-3-Clause | dist/quill.js | 209.274 | — | — | reserva (D23) |
| markdown-it | 15.0.1 | MIT | dist/browser/markdown-it.umd.min.js | 114.836 | — | — | opcional (D23) |
| dompurify | 3.4.14 | MPL-2.0 OR Apache-2.0 | dist/purify.min.js | 29.204 | 2026-09-05 | 17,4 mil | obrigatório (D23) |
| yjs | 13.6.32 | MIT | dist/yjs.mjs | 299.797 | 2026-09-05 | 22,8 mil | adiado (D12) |
| jsonata | 2.2.2 | MIT | jsonata.min.js | 79.757 | 2026-07-30 | 2,7 mil | rejeitado (D6) |
| json-logic-js | 2.0.5 | MIT | logic.js | 14.844 | 2024-07-09 | 1,5 mil | rejeitado (D6) |
| jsep | 1.4.0 | MIT | dist/jsep.min.js | 10.836 | 2024-11-18 | 965 | referência de analisador para D6 |
| expr-eval | 2.0.2 | MIT | dist/bundle.min.js | 25.276 | 2024-08-15 | 1,4 mil | referência |
| terra-draw + adaptador maplibre | 1.33.0 / 1.4.1 | MIT | terra-draw.modern.js + adapter | 235.956 + 8.120 | 2026-09-01 | 1,1 mil | desenho (L5-01-b), se o nativo do L2-03 não bastar |
| @mapbox/mapbox-gl-draw | 1.5.1 | ISC | (6 deps) | — | 2026-08-31 | 1,1 mil | alternativa |
| @maplibre/maplibre-gl-compare | 0.5.0 | ISC | dist/maplibre-gl-compare.js | 11.333 | — | — | cortina (swipe) |
| @watergis/maplibre-gl-export | 5.0.0 | MIT | dist/maplibre-gl-export.umd.js | 820.986 | 2026-09-01 | 188 | fora: 821 kB (embute html2canvas) |
| @watergis/maplibre-gl-legend | — | MIT | — | — | 2026-05-05 | 45 | referência de leitura |
| signature_pad | 5.1.4 | MIT | dist/signature_pad.umd.min.js | 16.703 | 2026-09-03 | 12,0 mil | assinatura (L5-03-d) |
| pmtiles | 4.5.0 | BSD-3-Clause | dist/pmtiles.js | 20.229 | 2026-08-19 | 3,0 mil | já previsto no L2-01 |
| i18next | 26.4.2 | MIT | dist/umd/i18next.min.js | 43.702 | 2026-09-03 | 8,6 mil | não necessário (chaves JSON próprias) |
| dexie / idb | 4.4.5 / 8.0.3 | Apache-2.0 / ISC | dexie.min.js / build/index.js | 96.153 / 11.656 | — | — | fila offline da PWA (L2-07 decide; idb basta) |
| cronstrue | 3.24.0 | MIT | dist/cronstrue.min.js | 22.033 | — | — | texto legível do cron no editor (L5-02-c) |
| jspdf / pdfmake | 4.2.1 / 0.3.11 | MIT | — | 420.165 / 1.053.972 | — | — | fora: PDF vem do chromium (D17) |
| golden-layout / dockview-core / muuri / split.js | — | MIT | — | 2,1 MB / 374 kB / 84 kB / 6,8 kB | — | — | fora / fora / sem manutenção / opcional |
| @shoelace-style/shoelace | 2.20.1 | MIT | 8,35 MB desempacotado | — | — | — | fora (D13) |

## Anexo C — URLs testadas por HTTP (curl -sIL, User-Agent de navegador, 05/09/2026 13:01 a 13:06 UTC)

Lição de método (mesma do handoff T1 do papel esri): `doc.arcgis.com/en/<produto>/latest/...` é a série
viva para Experience Builder, Dashboards, Instant Apps, Survey123, Field Maps, Map Viewer e Web AppBuilder;
`doc.esri.com/en/<produto>/latest/...` (redirecionado da versão 12.1/3.7/2026) para Workflow Manager,
QuickCapture, Mission, StoryMaps e Pro; `enterprise.arcgis.com/en/<produto>/11.4/` devolve 403 ou 404
para os construtores (não existe doc versionada 11.4 dos apps nessa raiz), e as páginas raiz de
`doc.arcgis.com/en/<produto>/latest/` devolvem 403 sem caminho de página. Um 200 na raiz do site não é
evidência (armadilha já registrada pelo papel esri). As páginas do Hub e do Carto são renderizadas por
JavaScript: respondem 200 mas o texto útil não chega ao `curl`.

Esri, 200:
- https://doc.arcgis.com/en/experience-builder/latest/get-started/what-is-arcgis-experience-builder.htm
- https://doc.arcgis.com/en/experience-builder/latest/configure-widgets/widgets-overview.htm
- https://doc.arcgis.com/en/experience-builder/latest/configure-widgets/action-triggers.htm
- https://doc.arcgis.com/en/experience-builder/latest/build-apps/add-a-page.htm
- https://doc.arcgis.com/en/experience-builder/latest/build-apps/add-widgets.htm
- https://doc.arcgis.com/en/experience-builder/latest/configure-widgets/{map,chart,filter,table,list,near-me,suitability-modeler,edit,print}-widget.htm
- https://developers.arcgis.com/experience-builder/ e https://developers.arcgis.com/experience-builder/guide/core-concepts/
- https://doc.arcgis.com/en/web-appbuilder/latest/create-apps/what-is-web-appbuilder.htm (aposentadoria 2º trimestre de 2027)
- https://doc.arcgis.com/en/web-appbuilder/latest/create-apps/{themes-tab,widgets-tab}.htm
- https://doc.arcgis.com/en/instant-apps/latest/create-apps/app-templates-overview.htm
- https://doc.arcgis.com/en/instant-apps/latest/customize/configuration-overview.htm
- https://doc.arcgis.com/en/instant-apps/latest/create-apps/preview-and-publish.htm
- https://doc.arcgis.com/en/dashboards/latest/get-started/what-is-a-dashboard.htm
- https://doc.arcgis.com/en/dashboards/latest/create-and-share/actions.htm
- https://doc.arcgis.com/en/dashboards/latest/create-and-share/url-parameters.htm
- https://doc.arcgis.com/en/dashboards/latest/create-and-share/configuring-actions-on-dashboard-elements.htm
- https://doc.arcgis.com/en/dashboards/latest/get-started/{indicator,gauge,serial-chart,map-element-and-tools,share-a-dashboard,understand-data-sources}.htm
- https://doc.esri.com/en/arcgis-storymaps/latest/get-started/what-is-arcgis-storymaps.html
- https://doc.esri.com/en/arcgis-storymaps/latest/author-and-share/{add-sidecars,add-swipes,add-map-tours}.html
- https://doc.esri.com/en/arcgis-storymaps/latest/share-and-collaborate/publish.html
- https://doc.esri.com/en/arcgis-storymaps/latest/reference/theme-reference.html
- https://doc.arcgis.com/en/survey123/create/main/{xlsformessentials,xlsformformulas,question-types-overview,xlsformexpressions,xlsformsappearance}.htm
- https://doc.arcgis.com/en/survey123/create/web-designer/quickreferencecreatesurveys.htm
- https://doc.arcgis.com/en/survey123/analyze/printsurveyresults.htm
- https://doc.arcgis.com/en/field-maps/latest/prepare-maps/configure-the-form.htm
- https://doc.arcgis.com/en/arcgis-online/create-maps/create-form-mv.htm
- https://doc.arcgis.com/en/arcgis-online/create-maps/configure-pop-ups-mv.htm
- https://developers.arcgis.com/arcade/ e https://developers.arcgis.com/arcade/profiles/
- https://developers.arcgis.com/web-map-specification/ e .../objects/renderer/
- https://doc.esri.com/en/arcgis-workflow-manager/latest/help/{create-and-manage-workflow-diagrams,job-template,advanced-assignment}.html
- https://doc.esri.com/en/arcgis-workflow-manager/latest/administer/{schedule-and-manage-recurring-jobs,create-jobs-with-webhooks}.html
- https://doc.esri.com/en/arcgis-quickcapture/latest/get-started/introduction-quickcapture.html
- https://doc.esri.com/en/arcgis-quickcapture/latest/create/{editprojectjson,project-map}.html
- https://doc.esri.com/en/arcgis-mission/latest/essentials/essentials-what-is-arcgis-mission.html
- https://doc.esri.com/en/arcgis-mission/latest/manager/task-status.html
- https://doc.esri.com/en/arcgis-pro/latest/help/analysis/geoprocessing/modelbuilder/{what-is-modelbuilder-,exporting-a-model-to-python,iterators-for-looping,model-parameters,model-report,run-a-model}.html
- https://doc.esri.com/en/arcgis-pro/latest/help/analysis/geoprocessing/basics/{schedule-geoprocessing-tools,geoprocessing-history}.html
- https://doc.arcgis.com/en/insights/latest/get-started/ (200, conteúdo por JavaScript)
- https://doc.arcgis.com/en/hub/get-started/what-is-arcgis-hub-.htm e https://doc.arcgis.com/en/hub/sites/create-a-site.htm (200, conteúdo por JavaScript)

Esri, não usáveis como evidência (403/404 nesta máquina): `enterprise.arcgis.com/en/{experience-builder,dashboards,sites,workflow-manager,web-appbuilder,survey123,instant-apps,insights}/11.4/`;
blog de aposentadoria do Web AppBuilder (403); `doc.arcgis.com/en/{experience-builder,dashboards,instant-apps,field-maps,web-appbuilder}/latest/` (raiz, 403).

Outros, 200: docs.carto.com/carto-user-manual/workflows (+ components, scheduling-workflows, version-history,
executing-workflows-via-api, using-variables-in-workflows), developers.felt.com (js-sdk, felt-style-language),
docs.kepler.gl, github.com/keplergl/kepler.gl, docs.retool.com/apps (+ reference/components), interactjs.io,
dndkit.com, retejs.org/docs, github.com/jerosoler/Drawflow, github.com/jagenjo/litegraph.js,
grapesjs.com/docs, puckeditor.com/docs, craft.js.org/docs/overview, help.form.io (form-builder),
surveyjs.io/survey-creator/documentation/overview, surveyjs.io/licensing, surveyjs.io/pricing, gridstackjs.com,
sortablejs.github.io/Sortable, docs.yjs.dev, lit.dev/docs, preactjs.com, xlsform.org/en, docs.getodk.org/form-design-intro,
getodk.github.io/xforms-spec, github.com/enketo/enketo, maplibre.org/maplibre-style-spec (+ expressions),
jsonlogic.com, jsonata.org, echarts.apache.org, www.w3.org/TR/WCAG22, www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html,
html.spec.whatwg.org/multipage/dnd.html, www.w3.org/TR/pointerevents3, ogcapi.ogc.org/styles, ogcapi.ogc.org/processes,
stacspec.org/en, docs.ogc.org/is/21-065r2/21-065r2.html (CQL2), json-schema.org/specification,
github.com/watergis/maplibre-gl-{terradraw,export,legend}, github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md.
Não usáveis: felt.com (403), docs.protomaps.com/pmtiles (403), www.ogc.org/standards/ogcapi-styles (404).
