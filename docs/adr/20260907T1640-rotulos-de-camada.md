# Rótulos de camada (item L2-02-d-rotulos)

## Contexto

O modelo de estilo (L2-02-a) já reservava um bloco `plat_construtor.rotulos` simples
(`{visivel, campo, cor, tamanho}` → um layer `symbol` com `text-field: ["get", campo]`). O item
pede o vocabulário cheio da hipótese Esri (texto por campo ou expressão, classes com filtro e
faixa de escala, fonte/tamanho/cor/halo, posição por âncora e deslocamento, rótulo ao longo da
linha com repetição, posição no polígono, várias linhas, maiúsculas, unidade, prioridade e
colisão) mais a integração com a linguagem de expressão própria (L2-10-c).

## Decisões

**1. Texto por campo ou por expressão, com fallback para coluna do servidor.** A linguagem L2-10-c
ainda não tem compilador para MapLibre nem para SQL (registrado como PENDENTE no próprio item).
Como este é o primeiro consumidor real, o compilador nasce aqui: `app/expressao/
compilador_maplibre.py` traduz o subconjunto da AST com equivalente nativo na Style Spec
(aritmética, comparação, lógica, `Se`/`SeNulo`/`EhNulo`, `Concatenar`/`Texto`/`Maiuscula`/
`Minuscula`, `Absoluto`/`Minimo`/`Maximo`/`Arredondar`). O que não tem equivalente (a começar por
`TextoNumero`/`TextoData`, a formatação pt-BR que dá nome à cláusula do portão) levanta
`NaoCompilavel` com motivo nomeado, e o compilador de estilo (`app/estilos/compilador.py::
_texto_da_classe`) troca a expressão por `["get", <coluna do servidor>]`, onde o nome da coluna é
determinístico (`app/estilos/rotulos_servidor.nome_coluna_servidor`, sha256 truncado da expressão
normalizada). A função de tile do Martin que calcularia essa coluna de verdade é trabalho do L2-04
(pipeline de ingestão/tiles) — aqui está provado o CONTRATO (nome de coluna estável, cálculo pelo
mesmo avaliador Python, nunca produz `'null'`/`'NaN'`/`'undefined'`) e a IDENTIDADE (a mesma
expressão, um caminho compilado e um pré-calculado, dá o mesmo texto em 100 feições).

**2. Cada classe de rótulo é um layer `symbol` próprio**, com `filter` compilado do bloco
`filtro` simples `{campo, operador, valor}` — não uma única expressão `case` dentro de um layer.
Mais simples de gerar/entender e permite fonte/tamanho/cor por classe sem uma árvore de expressões
condicionais gigante; o custo é N layers por N classes (aceitável, o schema limita a 20 classes).

**3. `prioridade` (colisão entre classes) NÃO é resolvida por `symbol-sort-key` sozinho — é
resolvida pela ORDEM dos layers.** Medido de verdade no MapLibre-GL real ANTES de escrever a
implementação final (`tests/e2e/test_rotulos_render.py::test_prioridade_classe_a_vence_b_em_colisao`,
com um experimento de controle isolado que variou ordem e sort-key independentemente): dado o
MESMO `symbol-sort-key` ou nenhum, o layer que vem DEPOIS no array sempre venceu a colisão contra o
que vem antes; variar só o sort-key sem variar a ordem não mudou o resultado. `symbol-sort-key` só
ordena feições DENTRO do mesmo layer (mesma classe) — continua gravado (paridade com a Style Spec,
importante quando uma classe tem muitas feições competindo entre si), mas quem decide classe-vs-
classe é `_rotulos_layers` reordenando o array: prioridade explícita menor (mais importante) fica
por último; sem prioridade, fica primeiro (perde contra qualquer prioridade explícita). O campo
`prioridade` do editor continua "número menor = mais importante" (convenção cartográfica comum); o
sinal do `symbol-sort-key` gravado é negado (`-prioridade`) só para não contradizer a Style Spec
para quem ler o documento cru esperando o sentido oficial dela dentro de UM layer.

**4. Faixa de escala por classe vira `minzoom`/`maxzoom` NATIVOS**, não só metadata descritiva
(que é o que o resto do compilador ainda faz para os outros tipos — decisão de outro item, não
mexida aqui). Conversão escala↔zoom pela convenção OGC do pixel de renderização padronizado de
0,28 mm (WMTS Implementation Standard, anexo E): `escala(z) = (2π·6378137/256/0,00028) / 2^z`.
`escala_min` (denominador MENOR, mais perto) vira o TETO de zoom (`maxzoom`); `escala_max` (MAIOR,
mais longe) vira o PISO (`minzoom`). Testado ponta a ponta: o mesmo rótulo aparece dentro da faixa
e some fora dela (`queryRenderedFeatures` no MapLibre real, não só o número calculado).

**5. `glyphs` é gravado automaticamente no documento** (`app/estilos/compilador.GLYPHS_PADRAO =
"/fontes/plat/{fontstack}/{range}.pbf"`) sempre que há pelo menos um layer `symbol` — a Style Spec
recusa `text-field` sem `glyphs` no documento (o validador oficial provou isso na prática, não é
suposição). O caminho público (`/fontes/...`) é convenção fixa que casa com o padrão já existente
no schema (`corpo.maplibre.glyphs`); a instalação real do glifário no Martin, com licença
documentada, é o item L2-02-e-simbolos-sprites-glifos (ainda pendente) — aqui só o suficiente para
provar o mecanismo: Martin real (binário de produção, `/usr/local/bin/martin` v1.15.0) com Noto
Sans e Open Sans abertas (pacotes `fonts-noto-core`/`fonts-open-sans`, instalados nesta máquina),
numa porta descartável só desta suíte de teste.

## Medido

`tests/medidas/L2-02-d-rotulos.json`. Cache de glifos do Martin: 1ª chamada 14,6 ms, 2ª (mesmo
processo, mesmo pedido) 1,1 ms — 13× mais rápida, bytes idênticos.

## O que fica de fora (nomeado, não escondido)

- Compilação da linguagem de expressão para SQL (coluna real na função de tile do Martin): fica
  para o item de pipeline (L2-04) que já tem o contrato de função de tile pronto (L2-04-a, ramo
  `wt/stac`, ainda não juntado nesta árvore).
- `posicao_poligono` (`centro` × `ponto_interior`): o MapLibre não expõe as duas opções como
  propriedade de estilo — o motor sempre calcula um ponto de ancoragem interno ao polígono
  (equivalente a `ponto_interior`). O campo fica no schema para quando houver pré-cálculo próprio
  de centróide como coluna do servidor; hoje as duas opções produzem o mesmo layer.
- Sprite/glifário definitivo com licença documentada no catálogo: L2-02-e.
- `>= 40 funções`/formatação pt-BR/tipos lista-dicionário-geometria na linguagem de expressão:
  fora do escopo deste item (pertencem ao L2-10-c cheio); aqui só o que já existia (18 funções do
  núcleo) foi compilado para MapLibre.
