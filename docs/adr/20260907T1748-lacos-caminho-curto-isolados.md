# ADR — laços, caminho mais curto e isolados sobre pgRouting (item L4-02-d-lacos-e-caminho-curto)

## Contexto

O item irmão L4-02-a (`tracado.py`, ADR 0021) já monta, sobre `plat.rede_topo_no`/`rede_topo_aresta`
(topologia derivada, ADR 0020), um grafo com arestas REAIS (trechos) e VIRTUAIS (caminhos internos de
dispositivo multi-terminal, condicionados a travessabilidade e, opcionalmente, a não atravessar a categoria
`transformacao`) para os traçados `conectado`/`subrede` via `public.pgr_connectedComponents`. Este item
estende a MESMA família com três traçados novos, sobre o MESMO grafo:

1. **laços** — ciclos da rede, via `public.pgr_biconnectedComponents`: um bloco biconexo com mais de uma
   aresta contém um ciclo (com dois nós só, duas arestas paralelas já são um laço de dois caminhos); um
   bloco de uma aresta só é uma ponte (árvore), nunca um laço.
2. **caminho_curto** — o caminho de menor custo entre dois pontos, via `public.pgr_dijkstra` (k=1) ou
   `public.pgr_ksp` (k>1, algoritmo de Yen). Custo = comprimento geodésico por padrão (`comprimento_m`, o
   mesmo "COMP" gravado pela topologia) ou qualquer atributo numérico do trecho/dispositivo.
3. **isolados** — elementos sem caminho a nenhuma feição de uma CATEGORIA escolhida (padrão `fonte`), via
   `public.pgr_connectedComponents`: o componente do elemento não contém nenhum nó de `categoria_controlador`.

## Decisão

**Mesma rota, `tipo` estendido.** Em vez de três rotas novas, os três traçados entram como valores novos do
campo `tipo` da rota já existente `POST /api/rede/{rede_id}/tracar` (a fraseologia do próprio item —
"tipo=lacos|caminho_curto|isolados" — replica literalmente a forma do item irmão, "tipo=conectado|subrede").
`TracadoEntrada` (modelos.py) ganhou `destino`, `atributo_custo`, `k` e `categoria_controlador`, todos
opcionais, e `pontos_partida` deixou de exigir `min_length=1` no pydantic — cada `tipo` valida sua própria
exigência sobre esses campos NA ROTA (`_tracar_sincrono`), porque cada um tem uma exigência diferente sobre
os MESMOS campos (conectado/subrede exigem `pontos_partida`; caminho_curto exige um único ponto + destino;
lacos/isolados não exigem nenhum ponto, operam sobre a rede inteira).

Como os cinco `tipo` devolvem formatos DIFERENTES de resposta, a rota deixou de declarar
`response_model=TracadoResultado` (que só descrevia conectado/subrede) — o formato de cada um está
documentado na docstring da rota e provado pelos testes de cada item; `ElementoTracado`/`TracadoResultado`
saíram do `docs/openapi.json` gerado (não do banco, não do código — só o pydantic model que restringia a
resposta a um formato só).

**Módulo novo `lacos.py`, reusando `tracado.py` por import direto.** Em vez de fatorar `_resolver_ponto`/
`_uuid_lista`/`_info_tipos` para um lugar comum (o que exigiria editar `tracado.py`, do item irmão, ainda
"aberto"), `lacos.py` importa o módulo `tracado` e chama essas funções diretamente
(`app.rede_utilidades.tracado._resolver_ponto(...)`) — zero mudança de comportamento em `tracado.py`, zero
risco de conflito de merge com o trabalho em curso naquele item. A montagem do grafo (`_montar_arestas_custo`)
É NOVA neste módulo, não reusada de `tracado._montar_sql_arestas`, porque precisa de colunas extras
(`comprimento_m`, `atributos`) que o traçado original não expõe.

**"Nulo nunca vira zero" — recusa GLOBAL, não só no caminho.** Antes de rodar `pgr_dijkstra`/`pgr_ksp` com um
`atributo_custo` customizado, a função varre TODAS as arestas alcançáveis da rede (não só as do caminho que
acabaria sendo escolhido) atrás de `atributos->>atributo_custo IS NULL` e recusa com 422 se achar alguma,
citando a(s) feição(ões). É mais estrito do que checar só o caminho resultante — a alternativa (deixar o
algoritmo escolher livremente e só then falhar se o vencedor tiver nulo) permitiria que o mesmo pedido, feito
de novo depois que outro trecho mudasse de estado, retornasse um caminho DIFERENTE silenciosamente por causa
de um atributo nulo em um trecho que nunca fez parte do caminho escolhido — o comportamento do sistema para
o mesmo par origem/destino dependeria de dado ausente em lugar nenhum relacionado à pergunta feita. A
checagem global é mais simples de implementar e testar (não depende de qual caminho o solver escolheria) e
mais conservadora (nunca finge que o atributo pedido está completo quando não está).

**"controlador" = categoria `fonte` por padrão, configurável.** O pacote de ativos não tem uma categoria
chamada literalmente "controlador" com o sentido que o item usa (existe uma, mas significa "ajusta grandeza
elétrica sem interromper" — errada para este propósito). A categoria `fonte` ("onde a energia/água entra na
rede; o traçado a montante termina aqui", presente em `eletrica-br` e `agua-epanet`) é o equivalente de
disciplina ao "subnetwork controller" da Esri citado nas fontes do item, e vira o padrão de
`categoria_controlador` — outra categoria pode ser escolhida por parâmetro, desde que exista no pacote da
rede (senão 422 `categoria_controlador_sem_feicao`).

**Isolados atravessa a fronteira de subrede.** `isolados` usa o grafo "conectado" (nunca para em
`transformacao`), não o de "subrede": isolamento é sobre a rede física inteira, e um transformador não deixa
de contar como caminho para a fonte só porque muda o nível de tensão.

## Fronteira honesta

Mesma do item irmão: não existe front-end de rede de utilidades no repositório para acoplar clique + tabela
lateral + captura e2e (a cláusula "e2e" do portão fica registrada como NAO_CUMPRIDA em
`tests/medidas/L4-02-d-lacos-e-caminho-curto.json`, com a mesma justificativa). A cláusula de laços/desempenho
na rede real da cooperativa de teste depende da máquina estar com carga ≤ 8 no momento da medição (regra do
brief); quando a carga está acima disso, a cláusula fica registrada como NÃO MEDIDA, honesta, com a carga e
a RAM livre ao lado — nunca fingida.
