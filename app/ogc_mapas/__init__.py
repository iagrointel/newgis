"""WMS 1.3.0 e WMTS 1.0.0 sobre as camadas hospedadas do catálogo (item `L2-04-i-wms-wmts-sld`).

É o par OGC do FeatureServer (L2-04-c): o mesmo item, o mesmo token, a mesma camada — só que devolvendo
IMAGEM em vez de feição, que é o que QGIS, ArcGIS Pro, AGOL/Portal e qualquer cliente OGC antigo sabem
consumir por URL. Módulos:

- `matrizes`  — TileMatrixSet `GoogleMapsCompatible` (WMTS), aritmética de tile <-> caixa.
- `dados`     — leitura das feições de uma caixa, já reprojetadas e simplificadas pelo tamanho do pixel.
- `estilo`    — estilo efetivo da camada (item `estilo`, padrão determinista ou SLD recebido no pedido).
- `pintor`    — rasterizador próprio (Pillow): feições + estilo -> PNG/PNG8/JPEG.
- `sld_leitura` — leitor do subconjunto SLD 1.0 que o escritor do L2-02-a produz.
- `capacidades` — os dois documentos `GetCapabilities` (XML), validados contra a XSD oficial em cache.
- `rotas_wms` / `rotas_wmts` — os protocolos.
"""
