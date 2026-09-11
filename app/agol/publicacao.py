"""Estado de publicação AGOL por item (item L2-08-migracao-agol): tabela `plat.agol_publicacao`, uma linha por
`(tenant_id, item_id)`, migração `db/migracoes/20260910T2015_agol.sql`. Mesmo desenho de
`app/imagens/raster_item.py` (tabela-espelho com RLS por inquilino, upsert em `ON CONFLICT`) — o campo `dados`
de `plat.item` de uma `camada_vetorial` tem esquema fechado (`additionalProperties:false`, 029/036), então o
estado de uma integração como esta não cabe lá sem migrar aquele esquema; uma tabela própria, no mesmo padrão
que a casa já usa para o raster, evita mexer no contrato de todas as camadas vetoriais só por causa do AGOL."""

ESTADOS = ("nunca_publicado", "pendente", "publicando", "publicado", "erro")


def registrar(cur, tenant_id: int, item_id: str, **campos) -> dict:
    """Upsert por `(tenant_id, item_id)`. `campos` são só os que mudam (o `COALESCE` preserva o resto — uma
    chamada que só marca `estado='publicando'` não apaga a URL do serviço da rodada anterior)."""
    cur.execute(
        """
        INSERT INTO plat.agol_publicacao (
            tenant_id, item_id, job_id, estado, portal, agol_geojson_item_id, agol_servico_item_id,
            servico_url, n_feicoes, mensagem, publicado_em
        ) VALUES (%(tenant_id)s, %(item_id)s::uuid, %(job_id)s::uuid, %(estado)s, %(portal)s, %(agol_geojson_item_id)s,
                  %(agol_servico_item_id)s, %(servico_url)s, %(n_feicoes)s, %(mensagem)s,
                  CASE WHEN %(estado)s = 'publicado' THEN now() ELSE NULL END)
        ON CONFLICT (tenant_id, item_id) DO UPDATE SET
            job_id = COALESCE(EXCLUDED.job_id, plat.agol_publicacao.job_id),
            estado = EXCLUDED.estado,
            portal = COALESCE(EXCLUDED.portal, plat.agol_publicacao.portal),
            agol_geojson_item_id = COALESCE(EXCLUDED.agol_geojson_item_id, plat.agol_publicacao.agol_geojson_item_id),
            agol_servico_item_id = COALESCE(EXCLUDED.agol_servico_item_id, plat.agol_publicacao.agol_servico_item_id),
            servico_url = COALESCE(EXCLUDED.servico_url, plat.agol_publicacao.servico_url),
            n_feicoes = COALESCE(EXCLUDED.n_feicoes, plat.agol_publicacao.n_feicoes),
            mensagem = EXCLUDED.mensagem,
            publicado_em = CASE WHEN EXCLUDED.estado = 'publicado' THEN now()
                                 ELSE plat.agol_publicacao.publicado_em END,
            atualizado_em = now()
        RETURNING *
        """,
        {
            "tenant_id": tenant_id, "item_id": item_id, "job_id": campos.get("job_id"),
            "estado": campos.get("estado", "pendente"), "portal": campos.get("portal"),
            "agol_geojson_item_id": campos.get("agol_geojson_item_id"),
            "agol_servico_item_id": campos.get("agol_servico_item_id"),
            "servico_url": campos.get("servico_url"), "n_feicoes": campos.get("n_feicoes"),
            "mensagem": campos.get("mensagem"),
        },
    )
    return _json(cur.fetchone())


def obter(cur, tenant_id: int, item_id: str) -> dict | None:
    cur.execute(
        "SELECT * FROM plat.agol_publicacao WHERE tenant_id = %s AND item_id = %s::uuid", (tenant_id, item_id)
    )
    r = cur.fetchone()
    return _json(r) if r else None


def listar(cur, tenant_id: int) -> list[dict]:
    cur.execute(
        "SELECT * FROM plat.agol_publicacao WHERE tenant_id = %s ORDER BY atualizado_em DESC", (tenant_id,)
    )
    return [_json(r) for r in cur.fetchall()]


def _json(r: dict) -> dict:
    return {
        "item_id": str(r["item_id"]),
        "estado": r["estado"],
        "portal": r.get("portal"),
        "agol_geojson_item_id": r.get("agol_geojson_item_id"),
        "agol_servico_item_id": r.get("agol_servico_item_id"),
        "servico_url": r.get("servico_url"),
        "n_feicoes": r.get("n_feicoes"),
        "mensagem": r.get("mensagem"),
        "job_id": str(r["job_id"]) if r.get("job_id") else None,
        "publicado_em": r["publicado_em"].isoformat() if r.get("publicado_em") else None,
        "atualizado_em": r["atualizado_em"].isoformat() if r.get("atualizado_em") else None,
    }
