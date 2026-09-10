"""GeoJSON de uma camada hospedada para o AGOL (item L2-08-migracao-agol): mesma consulta do
`geojson_da_camada` de `/home/dev/fgr/sig/pipeline/20_agol_publish.py` (todas as colunas exceto `geom`/
`tenant_id`, `ST_AsGeoJSON(ST_Transform(geom,4326),7)`), adaptada a `app.consulta.campos.campos_da_camada`
(a mesma lista branca que o FeatureServer usa, item L2-04-c — nunca "todas as colunas da tabela" às cegas) e
com um teto de feições (`limites.AGOL_FEICOES_MAX`): o script original fazia `cur.fetchall()` sem limite
nenhum porque rodava para uma fazenda só; aqui, multi-inquilino, uma camada maior que o teto é recusada com
uma mensagem clara em vez de estourar a memória do worker."""

from __future__ import annotations

import json
from pathlib import Path

from app import limites
from app.consulta.campos import campos_da_camada
from app.jobs.registro import FalhaDefinitiva


def exportar_para_arquivo(cur, schema: str, tabela: str, caminho: Path) -> int:
    """Escreve um FeatureCollection em `caminho`; devolve o número de feições. `FalhaDefinitiva` (nunca vale a
    pena repetir) quando a camada está vazia ou acima de `AGOL_FEICOES_MAX`."""
    campos = [c for c in campos_da_camada(cur, schema, tabela) if c["papel"] != "geometria_controle"]
    cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')  # noqa: S608 — schema/tabela vêm de plat.item
    n = cur.fetchone()["n"]
    if n == 0:
        raise FalhaDefinitiva("a camada não tem feições — nada para publicar no ArcGIS Online")
    if n > limites.AGOL_FEICOES_MAX:
        raise FalhaDefinitiva(
            f"a camada tem {n} feições, acima do teto de {limites.AGOL_FEICOES_MAX} para publicação direta "
            "no ArcGIS Online por esta rota"
        )
    colunas = ", ".join(f'"{c["nome"]}"' for c in campos)
    sql = (
        f'SELECT ST_AsGeoJSON(ST_Transform("geom", 4326), 7) AS __geom, {colunas} '
        f'FROM "{schema}"."{tabela}"'
    )  # noqa: S608 — schema/tabela/colunas vêm do catálogo (plat.item) e da lista branca de campos_da_camada
    cur.execute(sql)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[')
        primeira = True
        while True:
            linhas = cur.fetchmany(500)
            if not linhas:
                break
            pedacos = []
            for linha in linhas:
                geom = json.loads(linha.pop("__geom")) if linha.get("__geom") else None
                feicao = {"type": "Feature", "geometry": geom, "properties": dict(linha)}
                pedacos.append(("" if primeira else ",") + json.dumps(feicao, default=str))
                primeira = False
            fh.write("".join(pedacos))
        fh.write("]}")
    return n


__all__ = ["exportar_para_arquivo"]
