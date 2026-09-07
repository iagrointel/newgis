"""Estilo padrão da ingestão (item L2-02-a-modelo-estilo; item L0-04-c pede uma cor por camada nova).

Determinístico: o mesmo `uuid` de item devolve a mesma cor em qualquer instalação, sempre — não há
relógio, não há aleatoriedade, não há estado. A cor sai de um hash sha256 do uuid (texto), índice na
mesma paleta categórica fixa; a paleta em si é o único "número mágico" do módulo, e é a paleta
citada em `docs/adr/20260907T1200-modelo-de-estilo.md` (a mesma ordem de `app/mapa/simbologia.py`,
para o dia em que os dois convergirem não trocar a cor de nada que já existe)."""

from __future__ import annotations

import hashlib

PALETA = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2",
    "#edc948", "#9c755f", "#ff9da7", "#8cd17d", "#bab0ac", "#d37295",
]
GEOMETRIA_PARA_PLAT = {"ponto": "ponto", "linha": "linha", "poligono": "poligono", "raster": "raster"}


def cor_determinista(item_uuid: str) -> str:
    """Índice na paleta a partir do sha256 do uuid — mesmo uuid, mesma cor, em qualquer máquina."""
    h = hashlib.sha256(str(item_uuid).encode("utf-8")).hexdigest()
    return PALETA[int(h[:8], 16) % len(PALETA)]


def estilo_padrao(item_uuid: str, geometria: str) -> dict:
    """Documento de estilo completo (`{esquema_versao, corpo}`) pronto para `plat.item.dados` de um
    estilo padrão embutido; `geometria` já normalizada para o vocabulário do construtor."""
    if geometria not in GEOMETRIA_PARA_PLAT:
        geometria = "poligono"
    cor = cor_determinista(item_uuid)
    if geometria == "raster":
        pc = {"tipo": "raster", "geometria": "raster", "versao": 1,
              "parametros_raster": {"rescale": [0, 255]}}
    else:
        simbolo = {"cor": cor}
        if geometria == "ponto":
            simbolo["raio"] = 4.0
        elif geometria == "linha":
            simbolo["largura"] = 1.5
        else:
            simbolo["contorno_cor"] = "#1d3c34"
            simbolo["opacidade"] = 0.55
        pc = {"tipo": "unico", "geometria": geometria, "versao": 1, "simbolo": simbolo}

    from app.estilos import compilador

    maplibre = compilador.compilar(pc)
    return {"esquema_versao": 1, "corpo": {"plat_construtor": pc, "maplibre": maplibre}}
