"""Área suja por edição de feição (item L4-03-d-areas-sujas-e-validacao; ADR
docs/adr/20260907T1243-areas-sujas-e-validacao.md).

Uma área suja é o POLÍGONO ENVOLVENTE (envelope de um buffer em metros sobre a geometria da feição, para que
um ponto também vire um polígono visível) de UMA feição editada, carimbado com a versão de edição da rede.
"Editar um trecho cria uma área suja": a marcação é por FEIÇÃO, nunca por lote inteiro — um `applyEdits` com
N feições afetadas grava até N áreas sujas (menos se duas feições geram exatamente o mesmo envelope, o que o
`ON CONFLICT DO NOTHING` da unicidade por feição+versão evita duplicar).

`limpa_em` é soft-delete: a validação que processa uma área marca a data em vez de apagar a linha, para que o
histórico "quantas vezes esta área foi suja" sobreviva. `ativas()`/`intersectando()` sempre filtram
`limpa_em IS NULL` — é o que "visível no mapa" e "só dentro da área suja" significam na prática."""

BUFFER_M = 2.0  # metros; declarado aqui (não em rotas_areas_sujas.py) porque a próxima carga em massa que
# precisar do mesmo envelope (ex. um job de manutenção) importa esta constante em vez de reinventar o número.


def registrar_por_feicoes(cur, tenant_id: int, rede_id: str, versao: int, feicao_ids: list[str]) -> int:
    """Uma área suja por feição de `feicao_ids` que tenha geometria (feição sem geometria não tem envelope
    possível — nunca fabricamos um polígono). Devolve quantas linhas gravou."""
    if not feicao_ids:
        return 0
    cur.execute(
        "INSERT INTO plat.rede_area_suja(tenant_id, rede_id, feicao_id, versao, geometria) "
        "SELECT %s, %s::uuid, f.id, %s, ST_Envelope(ST_Buffer(f.geometria::geography, %s)::geometry) "
        "FROM plat.rede_feicao f WHERE f.rede_id = %s::uuid AND f.id = ANY(%s::uuid[]) "
        "AND f.geometria IS NOT NULL",
        (tenant_id, rede_id, versao, BUFFER_M, rede_id, feicao_ids),
    )
    return cur.rowcount


def registrar_para_geometria_apagada(cur, tenant_id: int, rede_id: str, versao: int, feicao_id: str,
                                     geometria_wkt: str | None) -> int:
    """Feição apagada: a geometria já não está na tabela, então recebe a envoltória calculada ANTES do
    DELETE (WKT em 4326, passado pelo chamador). `feicao_id` na área suja fica NULL (a FK cairia junto com a
    feição, ON DELETE CASCADE) — a área continua visível, só sem referência de volta."""
    if geometria_wkt is None:
        return 0
    cur.execute(
        "INSERT INTO plat.rede_area_suja(tenant_id, rede_id, feicao_id, versao, geometria) "
        "VALUES (%s, %s::uuid, NULL, %s, "
        "ST_Envelope(ST_Buffer(ST_GeomFromText(%s, 4326)::geography, %s)::geometry))",
        (tenant_id, rede_id, versao, geometria_wkt, BUFFER_M),
    )
    return cur.rowcount


def proxima_versao(cur, rede_id: str) -> int:
    cur.execute(
        "UPDATE plat.rede SET versao_edicao = versao_edicao + 1 WHERE id = %s::uuid RETURNING versao_edicao",
        (rede_id,),
    )
    return cur.fetchone()["versao_edicao"]


def listar(cur, rede_id: str, apenas_ativas: bool = True) -> list[dict]:
    sql = ("SELECT id, feicao_id, versao, ST_AsGeoJSON(geometria) AS geojson, criado_em, limpa_em "
           "FROM plat.rede_area_suja WHERE rede_id = %s::uuid")
    params: list = [rede_id]
    if apenas_ativas:
        sql += " AND limpa_em IS NULL"
    sql += " ORDER BY criado_em"
    cur.execute(sql, params)
    return cur.fetchall()


def intersectando(cur, rede_id: str, extensao_geojson: dict | None) -> list[dict]:
    """Áreas sujas ATIVAS que tocam `extensao_geojson` (GeoJSON de polígono); sem extensão, TODAS as
    ativas — é o que faz 'validar tudo' processar exatamente a soma das áreas sujas de hoje, nunca a rede
    inteira."""
    if extensao_geojson is None:
        cur.execute(
            "SELECT id, feicao_id, versao, geometria FROM plat.rede_area_suja "
            "WHERE rede_id = %s::uuid AND limpa_em IS NULL",
            (rede_id,),
        )
    else:
        import json as _json
        cur.execute(
            "SELECT id, feicao_id, versao, geometria FROM plat.rede_area_suja "
            "WHERE rede_id = %s::uuid AND limpa_em IS NULL "
            "AND ST_Intersects(geometria, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
            (rede_id, _json.dumps(extensao_geojson)),
        )
    return cur.fetchall()


def limpar(cur, rede_id: str, ids: list[str]) -> int:
    if not ids:
        return 0
    cur.execute(
        "UPDATE plat.rede_area_suja SET limpa_em = now() "
        "WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[]) AND limpa_em IS NULL",
        (rede_id, ids),
    )
    return cur.rowcount


def uniao_geometria(cur, rede_id: str, area_ids: list[str]) -> str | None:
    """WKB (hex) da união das áreas sujas dadas — o polígono que 'reconstrói só dentro da área suja' usa
    para restringir a busca de feições em escopo. None se a lista vier vazia (nada para unir)."""
    if not area_ids:
        return None
    cur.execute(
        "SELECT ST_AsEWKB(ST_Union(geometria)) AS uniao FROM plat.rede_area_suja "
        "WHERE rede_id = %s::uuid AND id = ANY(%s::uuid[])",
        (rede_id, area_ids),
    )
    r = cur.fetchone()
    return bytes(r["uniao"]).hex() if r and r["uniao"] is not None else None


def feicoes_em_escopo(cur, rede_id: str, uniao_ewkb_hex: str | None) -> list[str]:
    """Ids das feições GEORREFERENCIADAS que caem dentro da união de áreas sujas (todas, se `uniao` for
    None — usado só quando o chamador já decidiu que o escopo é 'toda a rede', nunca como atalho de
    'validar por extensão')."""
    if uniao_ewkb_hex is None:
        cur.execute(
            "SELECT id::text FROM plat.rede_feicao WHERE rede_id = %s::uuid AND geometria IS NOT NULL",
            (rede_id,),
        )
    else:
        cur.execute(
            "SELECT id::text FROM plat.rede_feicao WHERE rede_id = %s::uuid AND geometria IS NOT NULL "
            "AND ST_Intersects(geometria, %s::geometry)",
            (rede_id, uniao_ewkb_hex),
        )
    return [r["id"] for r in cur.fetchall()]


def cruza_area_suja_geojson(cur, rede_id: str, geojson: dict) -> dict | None:
    """Igual a `cruza_area_suja(por_id=False)`, mas para geometria de entrada em GeoJSON (o formato que a
    rota de traçado recebe) em vez de WKT — usada quando o traçado parte de um ponto ainda não gravado como
    feição."""
    import json as _json
    cur.execute(
        "SELECT id, ST_AsGeoJSON(geometria) AS geojson FROM plat.rede_area_suja "
        "WHERE rede_id = %s::uuid AND limpa_em IS NULL "
        "AND ST_Intersects(geometria, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) LIMIT 1",
        (rede_id, _json.dumps(geojson)),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return {"id": str(r["id"]), "geojson": _json.loads(r["geojson"])}


def cruza_area_suja(cur, rede_id: str, geometria_wkt_ou_id: str, por_id: bool = False) -> dict | None:
    """A primeira área suja ATIVA que a geometria (ou a feição, se `por_id`) toca; None se nenhuma. Devolve
    {"id", "geojson"} para o chamador citar o polígono no aviso/recusa do traçado."""
    if por_id:
        cur.execute(
            "SELECT a.id, ST_AsGeoJSON(a.geometria) AS geojson FROM plat.rede_area_suja a "
            "JOIN plat.rede_feicao f ON f.id = %s::uuid "
            "WHERE a.rede_id = %s::uuid AND a.limpa_em IS NULL AND f.geometria IS NOT NULL "
            "AND ST_Intersects(a.geometria, f.geometria) LIMIT 1",
            (geometria_wkt_ou_id, rede_id),
        )
    else:
        cur.execute(
            "SELECT id, ST_AsGeoJSON(geometria) AS geojson FROM plat.rede_area_suja "
            "WHERE rede_id = %s::uuid AND limpa_em IS NULL "
            "AND ST_Intersects(geometria, ST_GeomFromText(%s, 4326)) LIMIT 1",
            (rede_id, geometria_wkt_ou_id),
        )
    r = cur.fetchone()
    if r is None:
        return None
    import json as _json
    return {"id": str(r["id"]), "geojson": _json.loads(r["geojson"])}
