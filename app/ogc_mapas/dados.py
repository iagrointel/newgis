"""Leitura das feições de uma caixa para desenhar (item L2-04-i). Diferente do FeatureServer, aqui o
alvo é PIXEL: a consulta já devolve a geometria REPROJETADA para o CRS pedido e SIMPLIFICADA pelo
tamanho do pixel (`ST_SimplifyPreserveTopology`), porque desenhar vértice mais fino que o pixel só
gasta banco e memória. O corte é feito com `&&` sobre o índice GiST da coluna `geom` (a caixa é
transformada para o SRID nativo, nunca a coluna — senão o índice não entra) e o recorte por
`ST_ClipByBox2D` evita mandar polígono do país inteiro para pintar um município.

A RLS continua valendo: quem abre o cursor é `db.db(auth.contexto())`, igual a toda rota de serviço.
"""

from __future__ import annotations

import json

from app.erros import ErroAPI

# teto de feições por pedido de imagem: acima disto a imagem já é uma mancha e o custo vira do servidor
LIMITE_FEICOES = 50_000


def _sql_caixa(srid_pedido: int, srid_nativo: int) -> str:
    """`ST_MakeEnvelope` no CRS do pedido, transformado para o SRID nativo da tabela (o lado do índice)."""
    env = "ST_MakeEnvelope(%s, %s, %s, %s, %s)"
    return env if srid_pedido == srid_nativo else f"ST_Transform({env}, {srid_nativo})"


def feicoes_da_caixa(cur, schema: str, tabela: str, srid_nativo: int, caixa, srid_pedido: int,
                     tolerancia: float, campos: list[str] | None = None,
                     where_extra: str | None = None, params_extra: list | None = None,
                     limite: int = LIMITE_FEICOES) -> list[dict]:
    """[{'geometria': <GeoJSON no CRS do pedido>, 'propriedades': {...}, 'id': fid}] dentro da caixa.

    Devolve no máximo `limite` feições; quem chama sabe que bateu no teto quando o tamanho é o limite."""
    minx, miny, maxx, maxy = caixa
    if not (minx < maxx and miny < maxy):
        raise ErroAPI(400, "caixa_invalida", "BBOX precisa ter minx < maxx e miny < maxy")
    cols = ", ".join(f'"{c}"' for c in (campos or []))
    projecao = f", {cols}" if cols else ""
    geom_saida = "geom" if srid_pedido == srid_nativo else f"ST_Transform(geom, {srid_pedido})"
    # ordem: recorta na caixa (no CRS do pedido) e só então simplifica com a tolerância em unidades desse CRS
    geom_saida = f"ST_ClipByBox2D({geom_saida}, ST_MakeEnvelope(%s, %s, %s, %s, {srid_pedido}))"
    if tolerancia > 0:
        geom_saida = f"ST_SimplifyPreserveTopology({geom_saida}, %s)"
    sql = (f'SELECT fid{projecao}, ST_AsGeoJSON({geom_saida}) AS g '
           f'FROM "{schema}"."{tabela}" WHERE geom && {_sql_caixa(srid_pedido, srid_nativo)}')
    params: list = [minx, miny, maxx, maxy]
    if tolerancia > 0:
        params.append(tolerancia)
    params += [minx, miny, maxx, maxy, srid_pedido]
    if where_extra:
        sql += f" AND ({where_extra})"
        params += list(params_extra or [])
    sql += " LIMIT %s"
    params.append(limite + 1)
    cur.execute(sql, params)
    linhas = cur.fetchall()
    saida = []
    for r in linhas[:limite]:
        if not r["g"]:
            continue
        props = {k: v for k, v in r.items() if k not in ("g", "fid")}
        saida.append({"id": r["fid"], "propriedades": props, "geometria": json.loads(r["g"])})
    return saida


def extensao_nativa(cur, schema: str, tabela: str, srid_nativo: int, srid_saida: int = 4326):
    """(minx, miny, maxx, maxy) da camada no CRS pedido, ou None quando a tabela está vazia."""
    alvo = "ST_Extent(geom)" if srid_saida == srid_nativo else f"ST_Extent(ST_Transform(geom, {srid_saida}))"
    cur.execute(f'SELECT {alvo} AS e FROM "{schema}"."{tabela}"')
    r = cur.fetchone()
    if not r or not r["e"]:
        return None
    nums = r["e"].replace("BOX(", "").replace(")", "").replace(",", " ").split()
    return tuple(float(v) for v in nums)
