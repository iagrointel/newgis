# ADR 20260907T1200 — Modelo de estilo (item L2-02-a-modelo-estilo)

Data: 07/09/2026. Decide a estrutura de dados do documento de estilo (tipo de item `estilo`) e como ela
convive com o que o item L2-01-mapa-web (ramo `wt/l201mapa`, ainda não juntado ao `master`) já construiu.

## Contexto

C2 do `laco/decomposicao/L2_CONCEITO.md` já tinha decidido o formato (MapLibre Style Spec pura + bloco
`plat_construtor`). O que faltava era a estrutura de dados versionada, o esquema publicado, o validador de
gravação e a conversão para SLD/estilo padrão. Ao mesmo tempo, `app/mapa/simbologia.py` (L2-01) já resolveu
o mesmo problema para um vocabulário reduzido de 3 tipos (`simples`/`valores_unicos`/`intervalos`), pensado
só para a tela do visualizador, com a legenda derivada da mesma função `classes()`.

## Decisão

1. **`app/estilos/compilador.py`** é o compilador único do vocabulário completo de `plat_construtor`
   (`unico`/`categoria`/`classes`/`proporcional`/`calor`/`agrupamento`/`raster`) para camadas MapLibre. Ele
   generaliza a mesma disciplina do L2-01 (`classes()` alimenta estilo e legenda) para o vocabulário maior do
   construtor persistido no catálogo.
2. **O documento gravado é sempre a forma canônica**: `app/estilos/validador.py::validar_estilo` valida o que
   o cliente enviou (Style Spec oficial, campos citados, `plat_construtor` compilável) e depois REESCREVE
   `corpo.maplibre` com `compilador.compilar(plat_construtor)` antes de persistir. Isto fecha a cláusula de
   ida-e-volta sem perda sem exigir que o cliente calcule o hash certo, e garante que nunca existe um
   `maplibre` gravado que não seja exatamente o que aquele `plat_construtor` implica.
3. **JSON Schema em `docs/esquemas/estilo-v1.json`** (gerado de `plat.tipo_item.esquema` por
   `docs/gerar_esquemas.py`, que agora publica também o tipo `estilo`, além de `mapa`).

## O que isso obriga em L2-01 (caminho de convergência, não feito neste item)

`app/mapa/simbologia.py` usa um vocabulário PRÓPRIO e mais estreito (`simples`/`valores_unicos`/`intervalos`)
que não é o `plat_construtor` deste item — foi escrito antes deste ADR existir, como uma simplificação
interna da tela. As duas coisas não competem hoje porque **nenhum código ainda liga uma coisa na outra**: o
mapa (L2-01) lê a simbologia embutida na entrada de camada do documento de mapa (`corpo.camadas[].estilo`),
e o item de catálogo tipo `estilo` (este item) é uma referência (`ref`) alternativa para o mesmo campo —
ver `app/mapas/documento.py::_resolver_estilo`, que já forwarda `item.dados.corpo` sem impor forma (por
isso não quebrou com o esquema mais estrito; só os testes que fabricavam um `estilo` de exemplo com a forma
antiga precisaram de ajuste — ver `tests/api/catalogo/test_mapas.py`).

Caminho de migração recomendado para quando o mapa passar a RESOLVER um `estilo.ref` de verdade (hoje ele só
repassa o `corpo` como veio, não desenha a partir dele — isso é trabalho do frontend do mapa, fora deste
item): o renderizador do navegador deve consumir `corpo.maplibre.layers` diretamente (é MapLibre Style Spec
pura nos dois formatos — o de `simbologia.py` e o deste item), e o editor de simbologia embutida do mapa
(hoje 3 tipos) pode either (a) continuar como um atalho de UI que grava plat_construtor implícito nos 3
tipos mais comuns, convertendo para o vocabulário de 7 tipos deste item na hora de "promover" a simbologia
embutida para um item `estilo` referenciável, ou (b) ser substituído pelo editor do construtor completo. A
paleta categórica e a rampa sequencial usadas em `app/estilos/padrao.py` são DELIBERADAMENTE as mesmas 12/7
cores de `app/mapa/simbologia.py` — o dia da convergência não muda a cor de nada que já existe.

## Consequência

- `tests/api/catalogo/conftest.py::DADOS_POR_TIPO["estilo"]` e duas fixtures de `test_mapas.py` que
  fabricavam um item `estilo` com `corpo` livre (o esquema antigo aceitava qualquer objeto) foram atualizadas
  para o novo formato — comportamento existente preservado, só a forma do documento de exemplo mudou.
- `docs/esquemas/mapa-v1.json` (commit `f0fa96a`, item L2-01-a-documento-mapa) tem um defeito PRÉ-EXISTENTE
  e não relacionado a este item: o `title` do esquema está gravado como "documento de mapa do plat_tstac
  (mapa-v1)" — contaminado pelo nome de uma trilha (`stac`) de quando o arquivo foi gerado, porque
  `CursorSchemaAmbiente` reescreve toda ocorrência textual de `plat` (mesmo dentro de uma string humana,
  não só referência de schema) para o nome da trilha corrente. `tests/api/catalogo/test_mapas.py::
  test_esquema_do_tipo_mapa_e_o_arquivo_publicado` falha por causa disso em QUALQUER trilha cujo nome não
  seja `tstac`. Não é deste item; registrado aqui para quem for corrigir L2-01-a não perder a causa.
