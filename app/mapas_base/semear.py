"""Quatro fontes abertas de instalação da galeria de mapas base (item L2-01-e-mapas-base). Licença e
proveniência de cada uma em docs/DADO_DEMO.md — este módulo só monta o `dados`/`creditos`/`termos_de_uso`
que o esquema do tipo `mapa_base` (20260907T1649_mapa_base.sql) exige; a criação em si passa pelo
`POST /api/itens` genérico (app.catalogo.rotas_itens.criar), sem SQL próprio.

A cena Sentinel-2 (fonte 3) é o mesmo ativo citado no item como "mosaico S2 via TiTiler (L1-02) — ativo da
casa a reusar": um COG já convertido no balde de objetos partilhado, servido pelo TiTiler de
`PLAT_TITILER_URL`. Sem essa variável configurada (produção não a tem por padrão hoje), a fonte 3 fica de
fora da instalação — a galeria segue com 3 fontes (pmtiles, osm_raster_proxy, nenhum), que já cumpre o
portão ("≥ 3 mapas base")."""

from __future__ import annotations

# Cena fixa do balde de objetos partilhado da casa (medida em 07/09: 41,5 MiB, EPSG:32723, bandas RGB
# "visual"; bounds/zoom lidos do próprio tilejson do TiTiler antes de fixar aqui). Trocar exige atualizar
# zoom_min/zoom_max junto — não há sondagem automática (a mesma regra de "procedência declarada, nunca
# sondada" do resto da casa, ver app/conexao/proveniencia.py).
_S2_CHAVE_S3 = "s2-23klq-20260818/s2-23klq-20260818_visual_fa4965ee.tif"
_S2_ZOOM_MIN = 8
_S2_ZOOM_MAX = 14


def definicoes_padrao(titiler_url: str | None) -> list[dict]:
    """Lista de `{titulo, creditos, termos_de_uso, dados}` prontos para `ItemEntrada`. `titiler_url` é
    `settings.PLAT_TITILER_URL`; passar `None` (ou vazio) omite a fonte 3 (satélite) da lista."""
    definicoes = [
        {
            "titulo": "OSM local (Guarulhos) — vetorial",
            "resumo": "PMTiles vetorial servido pelo próprio nginx (Range HTTP), sem serviço de tiles dinâmico.",
            "creditos": "© colaboradores do OpenStreetMap",
            "termos_de_uso": (
                "Dado sob ODbL 1.0 (Open Database License — https://opendatacommons.org/licenses/odbl/1-0/). "
                "Recorte de Guarulhos-SP; proveniência completa em web/dados/basemap/PROVENIENCIA.md."
            ),
            "dados": {
                "tipo": "pmtiles", "estilo": "escuro",
                "url": "/static/dados/basemap/guarulhos.pmtiles",
                "zoom_min": 0, "zoom_max": 16, "ordem": 0, "padrao": True,
            },
        },
        {
            "titulo": "OSM padrão (proxy da casa) — raster",
            "resumo": "Tile raster clássico do OpenStreetMap, sempre pelo proxy próprio com cache em disco.",
            "creditos": "© colaboradores do OpenStreetMap",
            "termos_de_uso": (
                "Dado sob ODbL 1.0; estilo cartográfico \"Standard\" sob CC BY-SA 2.0 "
                "(https://www.openstreetmap.org/copyright). Servido por proxy próprio com cache em disco e "
                "identificação do cliente, conforme https://operations.osmfoundation.org/policies/tiles/ — "
                "nunca o navegador direto ao tile.openstreetmap.org."
            ),
            "dados": {
                "tipo": "osm_raster_proxy",
                "url": "/api/mapas-base/osm/{z}/{x}/{y}.png",
                "zoom_min": 0, "zoom_max": 19, "ordem": 1, "padrao": False,
            },
        },
        {
            "titulo": "Fundo sem mapa base",
            "resumo": "Cor sólida, sem fonte externa nenhuma.",
            "creditos": None,
            "termos_de_uso": None,
            "dados": {"tipo": "nenhum", "ordem": 3, "padrao": False},
        },
    ]
    if titiler_url:
        url_tile = (
            f"{titiler_url.rstrip('/')}/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png"
            f"?url=s3://demo/{_S2_CHAVE_S3}"
        )
        definicoes.insert(2, {
            "titulo": "Satélite (Sentinel-2 da casa)",
            "resumo": "Mosaico Sentinel-2 servido por TiTiler (item L1-02); cena única, não cobre o Brasil inteiro.",
            "creditos": "Contém dados Copernicus Sentinel modificados, processados pela casa via TiTiler",
            "termos_de_uso": (
                "Copernicus Sentinel Data — reuso livre conforme a Política de Dados e Informação do "
                "Programa Copernicus (Regulamento (UE) nº 1159/2013)."
            ),
            "dados": {
                "tipo": "satelite_titiler",
                "url": url_tile,
                "zoom_min": _S2_ZOOM_MIN, "zoom_max": _S2_ZOOM_MAX, "ordem": 2, "padrao": False,
            },
        })
    return definicoes
