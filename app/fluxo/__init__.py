"""Entrada de eventos em tempo real (item L2-14-a-ingestao-de-fluxos).

Equivalente aos *feeds* do ArcGIS Velocity/GeoEvent Server: uma FONTE é um objeto do inquilino, com tipo em
vocabulário fechado (`tipos.py`), mapeamento de campos (`mapeamento.py`), filtro de entrada (`filtro.py`,
sobre a linguagem de expressão do item L2-10-c) e teto de eventos por segundo (`limite.py`). O processo
`plat-fluxo` (`servico.py`, porta 8155) recebe, normaliza e grava em lote (`fila.py`) na tabela particionada
`plat.fluxo_evento`; a API de gestão (`rotas.py`) vive no processo da aplicação, como qualquer outro objeto
do catálogo.

O que é receptor PASSIVO (o evento chega de fora): `http`, `websocket_servidor`, `gps_frota`, `sensor`.
O que é conector ATIVO (o processo vai buscar): `websocket_cliente`, `mqtt`, `sondagem`, `ais`.
"""
