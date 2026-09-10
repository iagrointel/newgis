"""Lista curada de CRS brasileiros (hipótese do item L2-17-crs-transformacoes). Cada entrada tem o
código EPSG, o nome oficial (lido do `pyproj.CRS`, não digitado — `tests/unit/test_crs_registro.py`
reprova se um nome aqui não bater com o banco EPSG do PROJ desta máquina) e por que está na lista.

Correção sobre a hipótese escrita no item: o texto original dizia "UTM SIRGAS 31981-31985 e
31965-31975". Consultado o banco EPSG via `pyproj.database.query_crs_info` (comando abaixo), o conjunto
CORRETO das 21 zonas UTM SIRGAS2000 que cobrem o Brasil é 31965-31976 (zonas norte 11N-22N) e
31977-31985 (zonas sul 17S-25S) — a hipótese testemunhava a faixa aproximada, não os códigos exatos;
aqui vale o levantamento contra o registro oficial.

    python3 -c "
    from pyproj.database import query_crs_info
    for r in query_crs_info(auth_name='EPSG'):
        if 31960 <= int(r.code) <= 31990 and 'SIRGAS 2000' in (r.name or ''):
            print(r.code, r.name)"
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntradaCurada:
    epsg: int
    motivo: str
    grupo: str  # "geografico" | "utm" | "projetado" | "legado" | "web"


_UTM_SIRGAS_NORTE = tuple(range(31965, 31977))  # 11N..22N
_UTM_SIRGAS_SUL = tuple(range(31977, 31986))  # 17S..25S

CURADA: tuple[EntradaCurada, ...] = (
    EntradaCurada(4674, "SIRGAS 2000 geográfico — referência oficial vigente do SGB (Res. IBGE 1/2005)",
                  "geografico"),
    EntradaCurada(4326, "WGS 84 — referência do GPS/GNSS civil; usada por padrão em GeoJSON (RFC 7946)", "geografico"),
    EntradaCurada(3857, "WGS 84 / Pseudo-Mercator — projeção do mapa-base (MapLibre); nunca para medir área/distância",
                  "web"),
    EntradaCurada(5880, "SIRGAS 2000 / Brazil Polyconic — projeção equivalente (área) para mapas de todo o Brasil",
                  "projetado"),
    *[EntradaCurada(e, f"SIRGAS 2000 / UTM zona {e - 31965 + 11}N — faixa norte do Brasil (equador a ~8°N)", "utm")
      for e in _UTM_SIRGAS_NORTE],
    *[EntradaCurada(e, f"SIRGAS 2000 / UTM zona {e - 31977 + 17}S — faixa sul do Brasil (a maior parte do território)",
                    "utm")
      for e in _UTM_SIRGAS_SUL],
    EntradaCurada(4618, "SAD69 geográfico — datum legado (pré-2005); transformação por grade NTv2 (grades_ibge/)",
                  "legado"),
    EntradaCurada(4225, "Córrego Alegre 1970/72 geográfico — datum legado mais antigo; grade NTv2 CA7072_003",
                  "legado"),
    EntradaCurada(5524, "Córrego Alegre 1961 geográfico — datum legado mais antigo; grade NTv2 CA61_003", "legado"),
)

CODIGOS_CURADOS: frozenset[int] = frozenset(e.epsg for e in CURADA)
