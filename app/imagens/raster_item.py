"""Tabela-espelho `plat.raster_item` (item L1-01-a): fonte de autorização por RLS de verdade, complementar
ao filtro por nome de coleção do pgstac (app/imagens/pgstac.py). Toda escrita de item passa pelas duas —
o pgstac guarda o STAC, esta tabela guarda quem pode ver o quê (RLS, `p_raster_item`, migração
20260906T1901_raster_item.sql) e a proveniência mínima do raster (sha256/perfil/bytes/estado)."""


def espelhar(cur, tenant_id: int, colecao: str, item_id: str, raster: dict | None = None) -> None:
    raster = raster or {}
    cur.execute(
        """
        INSERT INTO plat.raster_item (tenant_id, colecao, item_id, sha256, perfil, bytes, estado)
        VALUES (%s, %s, %s, %s, %s, %s, coalesce(%s, 'ativo'))
        ON CONFLICT (tenant_id, colecao, item_id) DO UPDATE SET
            sha256 = EXCLUDED.sha256, perfil = EXCLUDED.perfil, bytes = EXCLUDED.bytes, estado = EXCLUDED.estado
        """,
        (
            tenant_id, colecao, item_id,
            raster.get("sha256"), raster.get("perfil"), raster.get("bytes"), raster.get("estado"),
        ),
    )


def espelhar_lote(cur, tenant_id: int, colecao: str, item_ids: list[str]) -> int:
    """INSERT em massa (semeadura de teste): usa `unnest` em vez de um INSERT por item — é o mesmo caminho
    que uma ingestão em lote real usaria (item L1-01-h), só sem sha256/perfil/bytes (sintético, sem raster)."""
    if not item_ids:
        return 0
    cur.execute(
        """
        INSERT INTO plat.raster_item (tenant_id, colecao, item_id, estado)
        SELECT %s, %s, x, 'ativo' FROM unnest(%s::text[]) AS x
        ON CONFLICT (tenant_id, colecao, item_id) DO NOTHING
        """,
        (tenant_id, colecao, item_ids),
    )
    return len(item_ids)


def listar(cur, tenant_id: int, colecao: str | None = None) -> list[dict]:
    if colecao:
        cur.execute(
            "SELECT * FROM plat.raster_item WHERE tenant_id = %s AND colecao = %s ORDER BY item_id",
            (tenant_id, colecao),
        )
    else:
        cur.execute("SELECT * FROM plat.raster_item WHERE tenant_id = %s ORDER BY colecao, item_id", (tenant_id,))
    linhas = cur.fetchall()
    return [_json(r) for r in linhas]


def _json(r: dict) -> dict:
    return {
        "id": r["id"],
        "tenant_id": r["tenant_id"],
        "colecao": r["colecao"],
        "item_id": r["item_id"],
        "sha256": r["sha256"],
        "perfil": r["perfil"],
        "bytes": r["bytes"],
        "estado": r["estado"],
    }
