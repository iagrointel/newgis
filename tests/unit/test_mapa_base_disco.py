"""Custo em disco do mapa base instalado (item L2-01-e-mapas-base, cláusula do portão "tamanho em disco do
mapa base instalado registrado em tests/medidas/L2-01-e.json e <= o teto"). Mede o que a instalação de
verdade deixa no disco: o PMTiles vetorial servido pelo nginx (fonte 1) mais o teto do cache do proxy raster
do OSM (fonte 2). As fontes 3 (satélite via TiTiler externo) e 4 (fundo cor) não gravam byte nenhum aqui.

O teto de D27 ainda é decisão ABERTA do dono; até haver número dele vale o teto já em vigor no repositório
(limites.MAPA_BASE_DISCO_BYTES_MAX) — está dito assim no handoff, sem fingir que D27 foi decidida."""

from pathlib import Path

import pytest

from app import limites

ROOT = Path(__file__).resolve().parents[2]
PMTILES = ROOT / "web" / "dados" / "basemap" / "guarulhos.pmtiles"


def test_tamanho_em_disco_do_mapa_base_instalado_cabe_no_teto(medida):
    if not PMTILES.exists():
        pytest.skip(f"{PMTILES} ausente (instalação sem o recorte do item L2-01-a)")
    pmtiles_bytes = PMTILES.stat().st_size
    total = pmtiles_bytes + limites.MAPA_BASE_OSM_CACHE_BYTES_MAX

    assert pmtiles_bytes <= limites.MAPA_BASE_PMTILES_BYTES_MAX, pmtiles_bytes
    assert total <= limites.MAPA_BASE_DISCO_BYTES_MAX, total

    gravar = medida("L2-01-e")
    gravar("pmtiles_em_disco_bytes", pmtiles_bytes, "bytes",
           "os.stat de web/dados/basemap/guarulhos.pmtiles (fonte 1 da galeria)")
    gravar("cache_proxy_osm_teto_bytes", limites.MAPA_BASE_OSM_CACHE_BYTES_MAX, "bytes",
           "limites.MAPA_BASE_OSM_CACHE_BYTES_MAX (teto do cache em disco da fonte 2)")
    gravar("mapa_base_disco_total_bytes", total, "bytes",
           "PMTiles em disco + teto do cache do proxy OSM (pior caso da instalação)")
    gravar("mapa_base_disco_teto_bytes", limites.MAPA_BASE_DISCO_BYTES_MAX, "bytes",
           "limites.MAPA_BASE_DISCO_BYTES_MAX (teto interino: D27 do dono ainda aberta)")
