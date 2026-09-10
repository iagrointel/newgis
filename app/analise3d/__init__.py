"""Análise 3D sobre terreno e extrusões (item L2-09-d-analise-3d-visibilidade).

Quatro análises do Scene Viewer com implementação própria no servidor, cada uma com a sua paridade
declarada em `docs/PARIDADE.md` (seção "Análise 3D"):

  * `visada`   — linha de visada entre observador e alvo, amostrada no terreno, com veredito
                 visível/obstruído e o PONTO de obstrução;
  * `viewshed` — bacia visual por `gdal_viewshed` (o próprio binário, por subprocesso com relógio),
                 devolvida também como GeoTIFF (os bytes do GDAL, sem retoque) e como PNG para o mapa;
  * `perfil`   — perfil de elevação ao longo de uma linha, com ganho, perda e declividade máxima;
  * `sombra`   — sombra projetada de extrusões (prismas verticais) por data e hora, com a posição
                 solar pelo algoritmo NOAA e a aproximação declarada na resposta.

O terreno entra como GRADE INLINE na requisição (SRID SIRGAS 2000 UTM, metros; `app/analise3d/terreno.py`)
enquanto o armazenamento de MDT da família raster (L2-05-e/L2-09-a) não cruza para master. Resultado pode
ser guardado como item `analise_3d` do catálogo, com `analise`, `parametros`, `resultado` e `procedencia`.
"""
