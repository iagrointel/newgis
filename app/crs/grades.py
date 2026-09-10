"""Grades NTv2 do IBGE (ProGriD) para transformação de datum legado → SIRGAS2000, e escolha de qual
delas usar por área geográfica (item L2-17-crs-transformacoes). Proveniência completa, sha256 e o
levantamento de área/exatidão contra o registro EPSG em `grades_ibge/PROVENIENCIA.md`.

Cada grade é lida por CAMINHO ABSOLUTO num pipeline PROJ sem CRS declarado nas pontas
(`+proj=pipeline +step +proj=hgridshift +grids=<arquivo>`), verificado contra o serviço oficial do IBGE
(`tests/unit/test_crs_grade_ibge.py`) — não depende de `PROJ_DATA`/`PROJ_LIB` nem de rede em produção
(ADR 0001 seção 11.4: sem CDN)."""

import math
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer

RAIZ = Path(__file__).resolve().parents[2]
DIR_GRADES = RAIZ / "grades_ibge"

EPSG_SIRGAS2000 = 4674


@dataclass(frozen=True)
class Grade:
    nome: str
    arquivo: str
    epsg_origem: int
    origem_nome: str
    # bounds (oeste, sul, leste, norte) — área de uso da operação EPSG que referencia esta mesma grade
    # (br_ibge_<nome>.tif no CDN do PROJ), lida via pyproj.transformer.TransformerGroup; comando de
    # reexecução em grades_ibge/PROVENIENCIA.md.
    bounds: tuple[float, float, float, float]
    exatidao_classe_epsg_m: float

    def caminho(self) -> Path:
        return DIR_GRADES / self.arquivo

    def cobre(self, lon: float, lat: float) -> bool:
        w, s, e, n = self.bounds
        return w <= lon <= e and s <= lat <= n

    def pipeline(self) -> str:
        return f"+proj=pipeline +step +proj=hgridshift +grids={self.caminho()}"


GRADES: tuple[Grade, ...] = (
    Grade("SAD69 → SIRGAS2000", "SAD69_003.GSB", 4618, "SAD69",
          bounds=(-74.01, -35.71, -25.28, 7.04), exatidao_classe_epsg_m=1.0),
    Grade("Córrego Alegre 1961 → SIRGAS2000", "CA61_003.GSB", 5524, "Corrego Alegre 1961",
          bounds=(-58.16, -27.5, -38.82, -14.99), exatidao_classe_epsg_m=2.0),
    Grade("Córrego Alegre 1970/72 → SIRGAS2000", "CA7072_003.GSB", 4225, "Corrego Alegre 1970-72",
          bounds=(-58.16, -33.78, -34.74, -2.68), exatidao_classe_epsg_m=2.0),
)

GRADES_POR_EPSG_ORIGEM: dict[int, tuple[Grade, ...]] = {
    epsg: tuple(g for g in GRADES if g.epsg_origem == epsg) for epsg in {g.epsg_origem for g in GRADES}
}

# Parâmetros de transformação de 7/3 do R.PR IBGE 01/2005 (SAD69/96 GPS <-> SIRGAS2000), sem grade —
# usados como alternativa DECLARADA quando o ponto cai fora da cobertura de qualquer grade acima.
# Conferidos de forma independente contra um exercício universitário (UFPR, prof. Carlos Aurélio Nadal,
# "Exercício de transformação de sistemas de referência") que aplica os MESMOS três parâmetros à estação
# RBMC de Chapecó: SIRGAS2000 (X=3450305.441, Y=-4512731.664, Z=-2892128.265) -> SAD69 com
# DX=+67.35 DY=-3.88 DZ=+38.22 dá X=3450372.791 Y=-4512735.544 Z=-2892090.045, φ=-27°08'13.4956",
# λ=-52°35'56.3671" — bate com o que este pipeline calcula (abaixo, sentido inverso SAD69->SIRGAS2000
# usa os sinais trocados, é a mesma translação geocêntrica).
PIPELINE_FALLBACK_SAD69 = (
    "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=push +v_3 "
    "+step +proj=cart +ellps=aust_SA +step +proj=helmert +x=-67.35 +y=3.88 +z=-38.22 "
    "+step +inv +proj=cart +ellps=GRS80 +step +proj=pop +v_3 +step +proj=unitconvert +xy_in=rad +xy_out=deg"
)
FALLBACK_NOME = "parâmetros geocêntricos R.PR IBGE 01/2005 (sem grade; classe de exatidão declarada 5,0 m)"


def transformar_datum_legado(lon: float, lat: float, epsg_origem: int) -> dict:
    """Transforma (lon, lat) em graus decimais de um datum legado (SAD69/Córrego Alegre) para
    SIRGAS2000, escolhendo a grade certa por área e declarando qual transformação foi usada — a
    cláusula de refutação do item exige que o ponto FORA da cobertura não quebre, e sim caia na
    alternativa (parâmetros sem grade) com isso escrito na resposta."""
    candidatas = GRADES_POR_EPSG_ORIGEM.get(epsg_origem, ())
    for grade in candidatas:
        if grade.cobre(lon, lat):
            t = Transformer.from_pipeline(grade.pipeline())
            lon2, lat2 = t.transform(lon, lat)
            # hgridshift devolve +-inf quando o ponto cai fora do retângulo INTERNO da grade, mesmo
            # estando dentro do bbox declarado acima (a grade não é um retângulo perfeito de dados —
            # tem borda de segurança); só aceitar resultado finito.
            if math.isfinite(lon2) and math.isfinite(lat2):
                return {
                    "lon": lon2, "lat": lat2,
                    "transformacao_usada": grade.nome,
                    "cobertura": "dentro_da_grade",
                    "exatidao_classe_epsg_m": grade.exatidao_classe_epsg_m,
                }
    if epsg_origem != 4618:
        raise ValueError(f"sem grade nem alternativa registrada para EPSG {epsg_origem} -> SIRGAS2000")
    t = Transformer.from_pipeline(PIPELINE_FALLBACK_SAD69)
    lon2, lat2 = t.transform(lon, lat)
    return {
        "lon": lon2, "lat": lat2,
        "transformacao_usada": FALLBACK_NOME,
        "cobertura": "fora_da_grade_usou_parametros",
        "exatidao_classe_epsg_m": 5.0,
    }
