"""Terreno do visualizador (item L2-09-a-terreno-terrain-rgb-relevo).

Três codificações de altura em RGB, cada uma servindo um consumidor diferente:

- `terrain_rgb` (Mapbox): fonte do `setTerrain` do MapLibre. Formato desta trilha, 0,1 m de passo.
- `terrarium` (Mapzen): entrada exigida pelo pós-processamento `convert_to_contour` do Martin 1.15.
- `normal_map` (Mapzen "normal"): entrada exigida pelo pós-processamento `convert_to_hillshade` do
  Martin 1.15 — NÃO é altura, é a direção da normal da superfície (canais R/G), com o canal alfa
  como proxy de elevação para o ganho de contraste.

Achado registrado em ADR: o Martin 1.15 NÃO gera hillshade/contorno a partir do terrain-RGB
diretamente (a hipótese do item presumia isso). Hillshade lê *normal map*, contorno lê *Terrarium*.
Por isso o job produz as três camadas a partir da MESMA leitura do GLO-30.
"""
