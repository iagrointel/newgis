"""Resolução do tipo de geometria a partir do que o `ogrinfo -json` devolve (ADR 0005 seção 4.2 passo 5): um só
tipo -> ele mesmo; Polygon+MultiPolygon (ou Line/Multi, Point/Multi) -> promove para o Multi; qualquer mistura de
famílias diferentes (ponto+polígono, por exemplo) -> pergunta. Z é lido do sufixo " Z"/"25D" do próprio tipo."""

from __future__ import annotations

FAMILIAS = {
    "Point": "Point", "MultiPoint": "Point",
    "LineString": "Line", "MultiLineString": "Line",
    "Polygon": "Polygon", "MultiPolygon": "Polygon",
}
MULTI_DE = {"Point": "MultiPoint", "LineString": "MultiLineString", "Polygon": "MultiPolygon"}
TIPOS_CONCRETOS = set(FAMILIAS)


def normalizar_tipo_ogr(tipo: str) -> tuple[str, bool]:
    """(tipo sem sufixo Z, tem_z) — 'Point Z' / '3D Point' / 'Point25D' -> ('Point', True)."""
    t = (tipo or "").strip()
    tem_z = False
    for sufixo in (" Z", "25D"):
        if t.endswith(sufixo):
            t = t[: -len(sufixo)].strip()
            tem_z = True
    if t.startswith("3D "):
        t = t[3:].strip()
        tem_z = True
    return t, tem_z


def resolver(tipos_contagem: dict[str, int]) -> dict:
    """`tipos_contagem` = {"Polygon": 74, "MultiPolygon": 1, "NULL": 0}. Devolve
    {"tipos", "escolhida", "perguntar", "opcoes", "z", "sem_geometria"}."""
    sem_geometria = int(tipos_contagem.pop("NULL", 0) or tipos_contagem.pop("None", 0) or 0)
    limpos: dict[str, bool] = {}
    z = False
    familias: set[str] = set()
    for tipo, n in tipos_contagem.items():
        if not n:
            continue
        base, tem_z = normalizar_tipo_ogr(tipo)
        if base not in FAMILIAS:
            # tipo não reconhecido (Geometry/Unknown escaparam da varredura, ou GeometryCollection): pergunta
            return {"tipos": tipos_contagem, "escolhida": None, "perguntar": True,
                    "opcoes": ["geometria genérica"], "z": False, "sem_geometria": sem_geometria}
        limpos[base] = True
        z = z or tem_z
        familias.add(FAMILIAS[base])
    if not limpos:
        return {"tipos": tipos_contagem, "escolhida": None, "perguntar": True, "opcoes": [],
                "z": False, "sem_geometria": sem_geometria}
    if len(familias) > 1:
        return {"tipos": tipos_contagem, "escolhida": None, "perguntar": True,
                "opcoes": ["separar em camadas", "descartar um tipo", "geometria genérica"], "z": z,
                "sem_geometria": sem_geometria}
    familia = next(iter(familias))
    escolhida = MULTI_DE[familia] if len(limpos) > 1 or any(k.startswith("Multi") for k in limpos) else familia
    return {"tipos": tipos_contagem, "escolhida": escolhida, "perguntar": False, "opcoes": [escolhida], "z": z,
            "sem_geometria": sem_geometria}
