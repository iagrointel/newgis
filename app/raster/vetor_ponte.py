"""Ponte entre a camada vetorial do inquilino (tabela PostGIS) e os utilitários raster (item L2-05-e).

Três serviços, e nada além disso:

* `exportar(...)`: escreve a camada (ou só a sua geometria) como GeoJSON no diretório de trabalho, já
  reprojetada para o CRS do raster. É o que vira `-cutline` do gdalwarp e fonte do gdal_rasterize;
* `zonas(...)`: devolve, uma a uma, as feições de uma camada como (fid, atributos, geometria GeoJSON,
  limites) no CRS do raster — o que as estatísticas zonais consomem sem carregar a camada inteira em
  memória (cursor nomeado, lote a lote);
* `carregar_geojson(...)`: cria a tabela de destino a partir do GeoJSON que o gdal_contour ou o
  gdal_polygonize escreveu, com os campos declarados. A geometria entra por `ST_GeomFromGeoJSON` e o
  SRID é o do raster de origem, declarado por quem chama.

Nomes de tabela e de campo NUNCA vêm do usuário: schema e tabela nascem do executor (`c_<16 hex>`) e os
campos são os da camada de entrada, já validados pelo catálogo. Ainda assim toda identificação passa por
`_ident`, porque a regra da casa é que identificador em SQL montado sempre é citado.
"""

from __future__ import annotations

import json
from pathlib import Path

LOTE = 500


def _ident(nome: str) -> str:
    if not nome or len(nome) > 63 or '"' in nome:
        raise ValueError(f"identificador inválido: {nome!r}")
    return '"' + nome + '"'


def _origem(camada: dict) -> str:
    return f'{_ident(camada["schema"])}.{_ident(camada["tabela"])}'


def _geom_no_crs(camada: dict, srid: int) -> str:
    return "geom" if int(camada["srid"]) == int(srid) else f"ST_Transform(geom, {int(srid)})"


def exportar(ctx, camada: dict, srid: int, caminho: Path, campos: list[str] | None = None) -> Path:
    """GeoJSON da camada inteira no CRS pedido (FeatureCollection). Usado como cutline e como fonte de
    rasterização; o arquivo fica no diretório de trabalho do job e morre com ele."""
    campos = campos if campos is not None else camada.get("campos") or []
    lista = ", ".join(f"'{c}', t.{_ident(c)}" for c in campos)
    propriedades = f"jsonb_build_object({lista})" if campos else "'{}'::jsonb"
    with ctx.db() as cur:
        cur.execute(
            f"SELECT jsonb_build_object('type', 'FeatureCollection', 'features', "
            f"coalesce(jsonb_agg(jsonb_build_object('type', 'Feature', 'id', t.fid, "
            f"'properties', {propriedades}, "
            f"'geometry', ST_AsGeoJSON({_geom_no_crs(camada, srid)})::jsonb)), '[]'::jsonb)) AS gj "
            f"FROM {_origem(camada)} t WHERE t.geom IS NOT NULL"
        )
        gj = cur.fetchone()["gj"]
    caminho.write_text(json.dumps(gj), encoding="utf-8")
    return caminho


def zonas(ctx, camada: dict, srid: int, campos: list[str] | None = None):
    """Gera (fid, {campos}, geometria GeoJSON, (x0, y0, x1, y1)) por feição, em lotes — a camada nunca é
    materializada inteira em memória."""
    campos = campos if campos is not None else camada.get("campos") or []
    lista = ", ".join(f"'{c}', t.{_ident(c)}" for c in campos)
    propriedades = f"jsonb_build_object({lista})" if campos else "'{}'::jsonb"
    geom = _geom_no_crs(camada, srid)
    ultimo = 0
    while True:
        with ctx.db() as cur:
            cur.execute(
                f"SELECT t.fid, {propriedades} AS props, ST_AsGeoJSON({geom})::jsonb AS gj, "
                f"ST_XMin({geom}) AS x0, ST_YMin({geom}) AS y0, ST_XMax({geom}) AS x1, ST_YMax({geom}) AS y1 "
                f"FROM {_origem(camada)} t WHERE t.geom IS NOT NULL AND t.fid > %s "
                f"ORDER BY t.fid LIMIT {LOTE}", (ultimo,)
            )
            linhas = cur.fetchall()
        if not linhas:
            return
        for r in linhas:
            ultimo = int(r["fid"])
            yield int(r["fid"]), dict(r["props"] or {}), r["gj"], (r["x0"], r["y0"], r["x1"], r["y1"])


def carregar_geojson(ctx, destino: dict, caminho: Path, srid: int, campos: list[dict],
                     geometria: str) -> int:
    """Cria a tabela de destino e insere o GeoJSON produzido por um utilitário do GDAL. Devolve o número
    de feições. `campos` é [{nome, tipo}] com tipo SQL já decidido por quem chama."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    feicoes = dados.get("features") or []
    alvo = f'{_ident(destino["schema"])}.{_ident(destino["tabela"])}'
    colunas = ", ".join(f"{_ident(c['nome'])} {c['tipo']}" for c in campos)
    with ctx.db() as cur:
        cur.execute(f"CREATE TABLE {alvo} (fid bigserial PRIMARY KEY"
                    + (f", {colunas}" if colunas else "")
                    + f", geom geometry({geometria}, {int(srid)}))")
        if feicoes:
            nomes = ", ".join(_ident(c["nome"]) for c in campos)
            marcadores = ", ".join(["%s"] * len(campos))
            sql = (f"INSERT INTO {alvo} ({nomes + ', ' if nomes else ''}geom) VALUES "
                   f"({marcadores + ', ' if marcadores else ''}"
                   f"ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), {int(srid)})))")
            for inicio in range(0, len(feicoes), LOTE):
                lote = feicoes[inicio:inicio + LOTE]
                cur.executemany(sql, [
                    [*[(f.get("properties") or {}).get(c["nome"]) for c in campos],
                     json.dumps(f.get("geometry"))]
                    for f in lote if f.get("geometry")
                ])
    return len(feicoes)


__all__ = ["LOTE", "carregar_geojson", "exportar", "zonas"]
