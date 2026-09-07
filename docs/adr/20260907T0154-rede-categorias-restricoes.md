# ADR 20260907T0154 — Categorias de rede, restrição de feição e tap de subrede (feição mínima)

Data: 2026-09-07 · Item: `L4-06-d-categorias-e-restricoes` · Estado: aceito (turno 4, trilha `il406dcateg`)
Decorre de: ADR 0019 (pacote de ativos da rede de utilidades)

## Contexto

`L4-01-a-pacote-de-ativos` entrega o ESQUEMA de rede: `plat.rede_categoria` e `plat.rede_tipo_categoria`
carregam as categorias declaradas no pacote e a associação de cada tipo às suas categorias. Isso basta para
importar/exportar o pacote, mas nenhuma cláusula do portão deste item ("isolamento usa a categoria
'proteção'", "alterar categoria dispara área suja", "restrição impede traçado a partir de UC") é provável só
com esquema: todas exigem FEIÇÃO — um ativo instanciado — porque "área suja em todas as feições do tipo" e
"traçado a partir de uma feição" não fazem sentido sobre o catálogo abstrato.

## Decisão

1. **`plat.rede_feicao`** é a feição mínima: `tipo_id` + `codigo` (único por tipo dentro da rede),
   `controlador_ativo` (booleano — o estado que a refutação do item precisa) e `suja` (booleano — nasce
   `true`, como a topologia da Esri). Sem geometria: a topologia derivada de camada real é `L4-01-b`, e a
   área suja como extensão ESPACIAL (com ciclo de validação) é `L4-03-d`. Aqui a área suja é só a marca por
   feição, e a mudança de categoria a redefine em massa (a cláusula do portão pede a contagem, não o polígono).
2. **`plat.rede_feicao_ligacao`** é a aresta de conectividade, não dirigida (par ordenado por texto do uuid).
   Serve só ao traçado de isolamento deste item; a derivação de ligação a partir da geometria real (interseção
   de linha, nó compartilhado) fica para o item que também resolve topologia (`L4-01-b`).
3. **`plat.rede_tipo_restricao`** com vocabulário fechado a `sem_ponto_partida` e `sem_terminal` — as duas
   citadas literalmente no portão. A Esri tem um conjunto maior de *feature restrictions*; ampliar o
   vocabulário é decisão do item que primeiro precisar de outra restrição, não deste.
4. **Isolamento é um passeio em largura**, não o motor de traçado completo. Ele para (sem atravessar) em toda
   feição cuja categoria seja `dispositivo_de_protecao` — a fronteira ENTRA no resultado (é o ponto de corte),
   o que está atrás dela não. Não há múltiplas fases, não há atributo de rede como barreira configurável, não
   há direção de fluxo. Isso é intencional: o portão só pede que "isolamento use a categoria proteção", não um
   motor de traçado Esri-completo — esse é item de linha própria, declarado como fora de escopo aqui.
5. **Subnetwork tap fica PARCIAL, por decisão, não por esquecimento.** A categoria `derivacao` existe no
   pacote `eletrica-br` (12 categorias, o portão pedia ≥ 8) e está na condição de elegibilidade da Esri —
   atribuída a `unidade_consumidora/1`, feição de ponto com um único terminal. Mas não existe traçado de
   SUBREDE que trate `derivacao` como fim de ramal (só o traçado de isolamento acima, que para na proteção).
   Construir esse traçado sem antes ter subredes nomeadas (`L4-04-a`, ainda não feito) seria simular uma
   capacidade que não existe — decisão registrada em `docs/PARIDADE.md`, não escondida no código.

## Consequência

Os quatro itens que dependem de feição real (área suja espacial, controlador com nome de subrede, traçado de
subrede parando no tap, validação de rede completa) ACRESCENTAM coluna/tabela a `plat.rede_feicao` e afins;
nenhum deles recria a tabela. `plat.rede_feicao.suja` é o único campo que este item promete manter estável
como contrato entre itens.
