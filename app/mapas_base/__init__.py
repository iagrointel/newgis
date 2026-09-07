"""Galeria de mapas base por inquilino (item L2-01-e-mapas-base): cada mapa base é um item comum do
catálogo (tipo `mapa_base`, migração 20260907T1649_mapa_base.sql) — não há tabela nova. Este pacote só
acrescenta o que o catálogo genérico não faz: os 4 modelos de instalação padrão (semear.py) e o proxy raster
do OSM com cache e defesa contra SSRF (proxy_osm.py), montados em rotas.py."""
