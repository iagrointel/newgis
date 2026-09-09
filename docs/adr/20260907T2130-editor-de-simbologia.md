# ADR 20260907T2130 — editor de simbologia vetorial sobre o documento do L2-02-a

Item L2-02-c-editor-simbologia-vetor. Segue C2 (Style Spec pura + `plat_construtor`), C19 (registro
declarativo), L5_CONCEITO D1 (sem framework) e a regra "zero renderizador duplicado".

## Decisões

1. **O navegador não compila.** A pré-visualização ao vivo chama `POST /api/estilos/compilar`, a MESMA
   função que grava (`app/estilos/compilador.py`), e aplica as camadas devolvidas com
   `Catalogo.aplicarEstilo` (web/js/mapa/catalogo.js). Só a montagem de sugestões é código de navegador
   (`estilo_sugestao.js`, função pura testada no node): categorias e classes a partir das respostas do
   L2-02-b (`/api/camadas/{id}/classes`) e rampas ColorBrewer (vendor, Apache-2.0, licença ao lado).
2. **Esquema estilo-v1 estendido sem mudar de versão** (migração `20260907T2100_estilo_editor.sql`): só
   campos opcionais — `camada_id`, `simbolo.tracejado/padrao/seta/icone_tamanho`, `categorias[].icone/
   escala_*`, `classes[].tamanho/escala_*`, `outros`, `rampa_invertida`, `efeitos`. Documento gravado
   antes continua válido; `docs/esquemas/estilo-v1.json` regerado do banco.
3. **Estilo liga-se à camada por `dados.camada_id`** → relação `estilo_de_camada` (extrator em
   `app/catalogo/relacoes.py`). O visualizador (`app/mapa/rotas.py::_ficha`) desenha a camada com o estilo
   MAIS RECENTE ligado a ela; sem estilo, vale a simbologia embutida do L2-01. Um estilo que o compilador
   de hoje recuse cai para a embutida com aviso no log, nunca tela vazia.
4. **"Outros" é o ramo padrão do `case`**; feição sem categoria deixa de herdar a cor da última categoria
   (era o comportamento anterior; a fixture `tests/estilos/categoria.json` foi regerada). O editor manda
   até 200 valores (limite do esquema) e o resto vira `outros` com a contagem.
5. **Clusters no tile, não no navegador.** `plat.camada_agrupar` agrupa por célula de grade alinhada ao
   mundo (lado = 2 × raio_px em unidades do zoom, tile de 512 px); `t_<hex>_ag` é a função de tile com a
   mesma prova de token da `t_<hex>`; `GET .../tilejson?agrupar=<raio>` cria-a sob demanda. Célula que
   cruza a borda do tile é contada em cada tile pelo que cai nele (declarado). O teste confere a contagem
   por célula com COUNT(*) independente (exato) e com ST_ClusterKMeans (tolerância 0,6 declarada).
6. **Faixa de escala**: por camada vira `minzoom`/`maxzoom` (denominador 1:N → zoom no equador); por
   classe vira `step` sobre `zoom` na opacidade, porque `zoom` só entra em `step`/`interpolate`.
7. **Efeitos**: sombra = camada de preenchimento deslocada por baixo; brilho = linha larga com `line-blur`
   por baixo; `mistura` (multiply/screen) é gravada e registrada em `metadata` — a Style Spec não tem blend
   por camada (parcial em PARIDADE.md). Desfazer/refazer = instantâneos do documento (até 100).

## Fora deste item
Densidade de pontos, predominância, bivariado, gráfico (pie) e dicionário (declarados fora em
PARIDADE.md); FeatureSet inline; rótulos avançados (L2-02-d); raster (L2-02-f); fps com 1 mi de pontos
não medido nesta bancada (1.000 pontos).
