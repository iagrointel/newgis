"""Modelo de estilo do plat (item L2-02-a-modelo-estilo; C2 do `laco/decomposicao/L2_CONCEITO.md`).

O documento de estilo (tipo de item `estilo`, esquema em `docs/esquemas/estilo-v1.json`) grava duas partes
que a mesma função compõe: `plat_construtor` (a intenção do usuário: tipo de classificação, campo, cortes,
cores) e `maplibre` (as camadas MapLibre Style Spec v8 que o navegador desenha). `compilador.compilar`
é a ÚNICA função que produz `maplibre` a partir de `plat_construtor` — o mesmo caminho vale para o estilo
gravado pelo editor, o estilo padrão da ingestão (`padrao.py`) e a conversão para SLD (`sld.py`); não existe
um segundo lugar no código que decida uma cor.

Este módulo generaliza o que `app/mapa/simbologia.py` (item L2-01-mapa-web, ramo `wt/l201mapa`, ainda não
juntado) fez para os 3 tipos de estilo do visualizador (`simples`/`valores_unicos`/`intervalos`): aqui o
vocabulário é o do construtor completo (`unico`/`categoria`/`classes`/`proporcional`/`calor`/`agrupamento`/
`raster`), e o resultado é o documento persistido no catálogo, não uma função chamada em memória pela tela
do mapa. Ver `docs/adr/20260907T1200-modelo-de-estilo.md` para o caminho de convergência das duas frentes.
"""
