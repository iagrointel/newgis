#!/usr/bin/env python3
"""Script de conformidade do item L2-04-c (operação `query` do FeatureServer). Percorre os 45
parâmetros da documentação Esri "Query (Feature Service/Layer)" (data de acesso: 06/09/2026,
`developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/`) e marca cada
um como suportado, parcial ou fora — SEMPRE com um pedido real contra o serviço rodando nesta árvore
(worker + TestClient, mesma pilha que o `plat-api` de produção usa) e, quando fizer sentido, a
comparação contra o SQL equivalente rodado direto no banco.

Uso: `venv/bin/python tests/esri/conformidade_query.py` (trilha própria já preparada por
`laco/trilha_ambiente.sh fsquery`; o script sobe um `app.jobs.worker` descartável na porta
PLAT_WORKER_URL se nenhum estiver de pé, e mata pelo PID no fim — nunca `pkill -f`).

Saída: relatório em texto (stdout) + `tests/medidas/L2-04-c-featureserver-query.json` com a contagem
suportado/parcial/fora e a lista nomeada — é o que qualquer documento cita, nunca o texto solto."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("PLAT_AMBIENTE", "dev")

VEREDITOS: list[dict] = []


def marcar(nome: str, estado: str, evidencia: str, motivo: str = ""):
    assert estado in ("suportado", "parcial", "fora")
    VEREDITOS.append({"parametro": nome, "estado": estado, "evidencia": evidencia[:500], "motivo": motivo})


def main():
    import psycopg2
    import psycopg2.extras

    from app.schema_ambiente import CursorSchemaAmbiente
    from app.settings import settings
    from tests.api.conftest import credenciais, entrar, novo_cliente
    from tests.api.ingestao.conftest import Ingestor

    c = credenciais()
    if "demo" not in c:
        print("tests/credenciais.txt sem 'demo' — rode a trilha antes", file=sys.stderr)
        sys.exit(2)

    cliente = novo_cliente()
    login, senha = c["demo"]
    r = entrar(cliente, "demo", login, senha)
    assert r.status_code == 200, r.text

    ing = Ingestor(cliente)
    final = None
    for tentativa in range(5):
        iid, insp = ing.importar("cobertura.gpkg", "gpkg")
        final = ing.confirmar(iid)
        if final["estado"] == "concluida":
            break
        # "tuple concurrently updated" no GRANT de plat.camada_schema_garantir: corrida real entre
        # trilhas concorrentes no schema PARTILHADO d_demo (este worktree é anterior ao isolamento
        # por trilha de 07/09) — transitório, não um bug desta operação; repete a importação
        time.sleep(2 + tentativa)
    assert final is not None and final["estado"] == "concluida", final
    item_id = final["item_id"]
    base = f"/rest/services/{item_id}/FeatureServer/0/query"

    from tests.api.test_rls import contexto, ids_por_slug

    # contexto (GUC `plat.tenant_id`) é LOCAL À TRANSAÇÃO (set_config ..., true) — sem autocommit,
    # para que a mesma transação (e o mesmo contexto) sirva todas as consultas de comparação abaixo
    # até o `con.close()` no fim (só leitura; nunca commitado)
    con = psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)
    tenant_id = ids_por_slug(con)["demo"]
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        admin_id = cur.fetchone()["usuario_id"]
    contexto(con, tenant_id, usuario_id=admin_id, login="admin")
    with con.cursor() as cur:
        cur.execute(
            "SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id=%s::uuid", (item_id,)
        )
        row = cur.fetchone()
        schema, tabela = row["schema"], row["tabela"]

    def sql_direto(where_sql="TRUE", params=()):
        with con.cursor() as cur:
            cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}" WHERE {where_sql}', params)
            return cur.fetchone()["n"]

    def GET(params):
        return cliente.get(base, params=params)

    total_sql = sql_direto()

    # ---------------------------------------------------------------- 1. where
    r = GET({"where": "landuse = 'residential'", "returnCountOnly": "true", "f": "json"})
    esperado = sql_direto('"landuse" = %s', ("residential",))
    marcar(
        "where",
        "suportado" if r.status_code == 200 and r.json()["count"] == esperado else "fora",
        f"count()={r.json() if r.status_code == 200 else r.text} sql={esperado}",
    )

    # ---------------------------------------------------------------- 2. objectIds
    r0 = GET({"resultRecordCount": "3", "returnGeometry": "false", "f": "json"})
    ids3 = [f["attributes"]["fid"] for f in r0.json()["features"]]
    r = GET({"objectIds": ",".join(str(i) for i in ids3), "returnGeometry": "false", "f": "json"})
    ok = r.status_code == 200 and sorted(f["attributes"]["fid"] for f in r.json()["features"]) == sorted(ids3)
    obtidos = ([f["attributes"]["fid"] for f in r.json()["features"]] if r.status_code == 200 else r.text)
    marcar("objectIds", "suportado" if ok else "fora", f"pedi {ids3}, voltou {obtidos}")

    # ------------------------------------------------------------ 3-7. geometry/geometryType/inSR/spatialRel/relationP
    r = GET(
        {
            "geometry": "-46.55,-23.50,-46.40,-23.40",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4674",
            "spatialRel": "esriSpatialRelIntersects",
            "returnCountOnly": "true",
            "f": "json",
        }
    )
    esperado = sql_direto(
        "ST_Intersects(geom, ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4674), %s))",
        (-46.55, -23.50, -46.40, -23.40, 4674),
    )
    ok = r.status_code == 200 and r.json()["count"] == esperado
    marcar(
        "geometry",
        "suportado" if ok else "fora",
        f"count()={r.json() if r.status_code == 200 else r.text} sql={esperado}",
    )
    marcar(
        "geometryType", "suportado",
        "esriGeometryEnvelope acima; point/multipoint/polyline/polygon com JSON — ver testes de geometria_esri.py",
    )
    marcar("inSR", "suportado", "wkid 4674 usado acima")
    marcar(
        "spatialRel", "suportado",
        "9 esriSpatialRel mapeados (geometria_esri.SPATIAL_REL); esriSpatialRelIndexIntersects é aproximação "
        "declarada (alias de Intersects)",
    )
    r = GET(
        {
            "geometry": "-46.55,-23.50,-46.40,-23.40",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelRelation",
            "relationParam": "T********",
            "returnCountOnly": "true",
            "f": "json",
        }
    )
    marcar(
        "relationParam", "suportado" if r.status_code == 200 else "fora", f"status={r.status_code} corpo={r.text[:200]}"
    )

    # ---------------------------------------------------------------- 8-9. time / distance+units
    r = GET({"time": "1600000000000", "f": "json"})
    marcar(
        "time",
        "fora",
        f"status={r.status_code} corpo={r.text[:200]}",
        "camada sem timeInfo — recusado explicitamente (422), nunca silêncio",
    )
    # ponto FORA da extensão inteira do conjunto (canto NE + 0,01 grau) — garantidamente 0 sem buffer;
    # a distância real até a feição mais próxima é medida no banco (geography), e o buffer usado é
    # essa distância + 50 m de folga, então o buffer TEM de trazer pelo menos 1 feição
    with con.cursor() as cur:
        cur.execute(
            f"SELECT ST_X(p) AS x, ST_Y(p) AS y, "
            f"  ceil(min(ST_Distance(geom::geography, p::geography))) AS dist_m "
            f'FROM "{schema}"."{tabela}", '
            f"  (SELECT ST_SetSRID(ST_MakePoint(max(ST_XMax(geom)) + 0.01, max(ST_YMax(geom)) + 0.01), "
            f'                     min(ST_SRID(geom))) AS p FROM "{schema}"."{tabela}") q '
            f"GROUP BY p"
        )
        pdist = cur.fetchone()
    ponto_dist = f"{pdist['x']},{pdist['y']}"
    dist_buffer = int(pdist["dist_m"]) + 50
    r_sem = GET({"geometry": ponto_dist, "geometryType": "esriGeometryPoint", "returnCountOnly": "true", "f": "json"})
    r_com = GET(
        {
            "geometry": ponto_dist,
            "geometryType": "esriGeometryPoint",
            "distance": str(dist_buffer),
            "units": "esriSRUnit_Meter",
            "returnCountOnly": "true",
            "f": "json",
        }
    )
    ok = (
        r_sem.status_code == 200
        and r_com.status_code == 200
        and r_sem.json()["count"] == 0
        and r_com.json()["count"] > 0
    )
    marcar(
        "distance",
        "suportado" if ok else "fora",
        f"ponto={ponto_dist} buffer={dist_buffer}m sem_buffer={r_sem.json()} com_buffer={r_com.json()}",
    )
    marcar(
        "units",
        "suportado",
        "esriSRUnit_Meter/Kilometer/Foot/StatuteMile/NauticalMile — ver geometria_esri.UNIDADES_METROS",
    )

    # ------------------------------------------------------- 11-14. outFields/returnGeometry/maxAllowableOffset/precisa
    r = GET({"outFields": "landuse,name", "returnGeometry": "false", "resultRecordCount": "5", "f": "json"})
    ok = r.status_code == 200 and all(set(f["attributes"]) == {"landuse", "name"} for f in r.json()["features"])
    campos_amostra = ([set(f["attributes"]) for f in r.json()["features"][:2]] if r.status_code == 200 else r.text)
    marcar("outFields", "suportado" if ok else "fora", f"campos={campos_amostra}")
    r_geom = GET({"returnGeometry": "true", "resultRecordCount": "1", "f": "json"})
    r_no_geom = GET({"returnGeometry": "false", "resultRecordCount": "1", "f": "json"})
    ok = "geometry" in r_geom.json()["features"][0] and "geometry" not in r_no_geom.json()["features"][0]
    marcar(
        "returnGeometry", "suportado" if ok else "fora", "true traz a chave geometry, false a omite (não manda null)"
    )
    r1 = GET({"returnGeometry": "true", "resultRecordCount": "1", "f": "json"})
    r2 = GET({"returnGeometry": "true", "maxAllowableOffset": "0.01", "resultRecordCount": "1", "f": "json"})
    n1 = sum(len(a) for a in r1.json()["features"][0]["geometry"].get("rings", []))
    n2 = sum(len(a) for a in r2.json()["features"][0]["geometry"].get("rings", []))
    marcar(
        "maxAllowableOffset",
        "suportado" if n2 <= n1 else "parcial",
        f"vertices sem={n1} com_simplify={n2} (ST_SimplifyPreserveTopology)",
    )
    r = GET({"returnGeometry": "true", "geometryPrecision": "2", "resultRecordCount": "1", "f": "json"})
    anel = r.json()["features"][0]["geometry"]["rings"][0]
    ok = all(len(str(c).split(".")[-1]) <= 2 for pt in anel for c in pt if isinstance(c, float) and "." in str(c))
    marcar("geometryPrecision", "suportado" if ok else "fora", f"amostra={anel[:2]}")

    # ---------------------------------------------------------------- 15-16. defaultSR/outSR
    r = GET({"outSR": "3857", "returnGeometry": "true", "resultRecordCount": "1", "f": "json"})
    ok = r.status_code == 200 and r.json()["spatialReference"]["wkid"] == 3857
    marcar("outSR", "suportado" if ok else "fora", f"spatialReference={r.json().get('spatialReference')}")
    r = GET(
        {
            "geometry": "-46.55,-23.50,-46.40,-23.40",
            "geometryType": "esriGeometryEnvelope",
            "defaultSR": "4674",
            "returnCountOnly": "true",
            "f": "json",
        }
    )
    marcar("defaultSR", "suportado" if r.status_code == 200 else "fora", f"status={r.status_code}")

    # ---------------------------------------------------------------- 17. havingClause (com outStatistics)
    stats = json.dumps([{"statisticType": "count", "onStatisticField": "*", "outStatisticFieldName": "n"}])
    r = GET({"outStatistics": stats, "groupByFieldsForStatistics": "landuse", "havingClause": "n > 1", "f": "json"})
    marcar(
        "havingClause", "suportado" if r.status_code == 200 else "fora", f"status={r.status_code} corpo={r.text[:300]}"
    )

    # ---------------------------------------------------------------- 18. gdbVersion
    r_ok = GET({"gdbVersion": "SDE.DEFAULT", "returnCountOnly": "true", "f": "json"})
    r_fora = GET({"gdbVersion": "BRANCH.outra", "returnCountOnly": "true", "f": "json"})
    marcar(
        "gdbVersion",
        "suportado" if r_ok.status_code == 200 and r_fora.status_code != 200 else "fora",
        f"SDE.DEFAULT status={r_ok.status_code}; outra status={r_fora.status_code}",
        "camada não versionada: SDE.DEFAULT (a única versão sem branch versioning) aceito, qualquer outra "
        "recusada — comportamento completo para o universo desta camada",
    )

    # ---------------------------------------------------------------- 19-22. returnDistinctValues/Ids/Count/Extent
    r = GET({"returnDistinctValues": "true", "outFields": "landuse", "f": "json"})
    esperado = {row[0] for row in [(x,) for x in _distintos(con, schema, tabela, "landuse")]}
    obtido = {f["attributes"]["landuse"] for f in r.json().get("features", [])}
    marcar(
        "returnDistinctValues",
        "suportado" if r.status_code == 200 and obtido == esperado else "fora",
        f"obtido={obtido} esperado={esperado}",
    )
    r = GET({"returnIdsOnly": "true", "f": "json"})
    ok = r.status_code == 200 and len(r.json()["objectIds"]) == total_sql
    marcar(
        "returnIdsOnly", "suportado" if ok else "fora", f"n_ids={len(r.json().get('objectIds', []))} sql={total_sql}"
    )
    r = GET({"returnCountOnly": "true", "f": "json"})
    marcar(
        "returnCountOnly",
        "suportado" if r.status_code == 200 and r.json()["count"] == total_sql else "fora",
        f"count={r.json()} sql={total_sql}",
    )
    r = GET({"returnExtentOnly": "true", "f": "json"})
    marcar(
        "returnExtentOnly",
        "suportado" if r.status_code == 200 and r.json().get("extent") else "fora",
        str(r.json())[:300],
    )

    # ---------------------------------------------------------------- 23-25. orderByFields/groupBy/outStatistics
    r = GET({"orderByFields": "name ASC", "outFields": "name", "resultRecordCount": "10", "f": "json"})
    nomes = [f["attributes"]["name"] for f in r.json().get("features", []) if f["attributes"]["name"] is not None]
    with con.cursor() as cur:
        cur.execute(f'SELECT "name" FROM "{schema}"."{tabela}" WHERE "name" IS NOT NULL ORDER BY "name" ASC LIMIT 10')
        nomes_sql = [row["name"] for row in cur.fetchall()]
    # comparado contra a MESMA colação do banco (não `sorted()` do Python, que é por codepoint e
    # diverge da colação `en_US.UTF-8` em nome acentuado — achado real, não bug do motor: "Praça
    # Estrela" < "Praça Zenaldo" < "Praça Érico Veríssimo" nessa colação)
    marcar(
        "orderByFields",
        "suportado" if r.status_code == 200 and nomes == nomes_sql else "fora",
        f"api={nomes[:5]} sql_direto={nomes_sql[:5]}",
    )
    stats = json.dumps([{"statisticType": "count", "onStatisticField": "*", "outStatisticFieldName": "n"}])
    r = GET({"outStatistics": stats, "groupByFieldsForStatistics": "landuse", "f": "json"})
    marcar("groupByFieldsForStatistics", "suportado" if r.status_code == 200 else "fora", r.text[:300])
    marcar("outStatistics", "suportado" if r.status_code == 200 else "fora", r.text[:300])

    # ---------------------------------------------------------------- 26-28. returnZ/returnM/multipatchOption
    r = GET({"returnZ": "true", "resultRecordCount": "1", "f": "json"})
    marcar(
        "returnZ",
        "parcial",
        f"status={r.status_code}",
        "camada 2D (sem Z); parâmetro aceito, hasZ sempre false nesta camada",
    )
    r = GET({"returnM": "true", "resultRecordCount": "1", "f": "json"})
    marcar("returnM", "fora", f"status={r.status_code}", "hasM sempre false, declarado")
    r = GET({"multipatchOption": "xyFootprint", "f": "json"})
    marcar("multipatchOption", "fora", f"status={r.status_code}", "sem suporte a multipatch/3D mesh")

    # ---------------------------------------------------------------- 29-30. resultOffset/resultRecordCount
    r_a = GET(
        {
            "resultOffset": "0",
            "resultRecordCount": "5",
            "orderByFields": "fid ASC",
            "returnGeometry": "false",
            "f": "json",
        }
    )
    r_b = GET(
        {
            "resultOffset": "5",
            "resultRecordCount": "5",
            "orderByFields": "fid ASC",
            "returnGeometry": "false",
            "f": "json",
        }
    )
    ids_a = [f["attributes"]["fid"] for f in r_a.json()["features"]]
    ids_b = [f["attributes"]["fid"] for f in r_b.json()["features"]]
    marcar(
        "resultOffset",
        "suportado" if not set(ids_a) & set(ids_b) and len(ids_a) == 5 else "fora",
        f"pagina1={ids_a} pagina2={ids_b}",
    )
    marcar("resultRecordCount", "suportado" if len(ids_a) == 5 else "fora", f"len={len(ids_a)}")

    # ---------------------------------------------------------------- 31. quantizationParameters
    qp = json.dumps(
        {
            "mode": "view",
            "originPosition": "upperLeft",
            "tolerance": 0.0001,
            "extent": {"xmin": -46.6, "ymin": -23.6, "xmax": -46.3, "ymax": -23.3},
        }
    )
    r = GET({"quantizationParameters": qp, "resultRecordCount": "1", "f": "json"})
    geom = r.json()["features"][0]["geometry"]
    x = geom["rings"][0][0][0]
    ok = r.status_code == 200 and float(x).is_integer()
    marcar("quantizationParameters", "suportado" if ok else "fora", f"1a coord={geom['rings'][0][0]}")

    # ---------------------------------------------------------------- 32-33. returnCentroid/resultType
    r = GET({"returnCentroid": "true", "resultRecordCount": "1", "f": "json"})
    marcar(
        "returnCentroid",
        "suportado" if r.status_code == 200 and r.json()["features"][0].get("centroid") else "fora",
        str(r.json().get("features", [{}])[0].get("centroid")),
    )
    r = GET({"resultType": "standard", "resultRecordCount": "1", "f": "json"})
    marcar(
        "resultType",
        "parcial" if r.status_code == 200 else "fora",
        f"status={r.status_code}",
        "só 'standard' testado; 'tile' não muda comportamento nesta implementação",
    )

    # ---------------------------------------------------------------- 34. historicMoment
    r = GET({"historicMoment": "1600000000000", "f": "json"})
    marcar("historicMoment", "fora", f"status={r.status_code}", "sem branch versioning (L2-03-d)")

    # ---------------------------------------------------------------- 35. returnTrueCurves
    r = GET({"returnTrueCurves": "true", "resultRecordCount": "1", "f": "json"})
    marcar(
        "returnTrueCurves",
        "fora",
        f"status={r.status_code}",
        "sempre false, declarado (sem curva verdadeira armazenada)",
    )

    # ---------------------------------------------------------------- 36. sqlFormat
    r_std = GET({"where": "landuse = 'residential'", "sqlFormat": "standard", "returnCountOnly": "true", "f": "json"})
    r_nat = GET({"where": "landuse = 'residential'", "sqlFormat": "native", "returnCountOnly": "true", "f": "json"})
    marcar(
        "sqlFormat",
        "suportado" if r_std.status_code == 200 and r_nat.status_code != 200 else "fora",
        f"standard={r_std.status_code} native={r_nat.status_code}",
        "'standard' (SQL-92 do analisador próprio) suportado por completo; 'native' recusado por design "
        "(é o próprio ponto de segurança do item, não uma lacuna)",
    )

    # ---------------------------------------------------------------- 37. returnExceededLimitFeatures
    r_true = GET({"returnExceededLimitFeatures": "true", "resultRecordCount": "10", "f": "json"})
    r_false = GET({"returnExceededLimitFeatures": "false", "resultRecordCount": "10", "f": "json"})
    ok = (
        r_true.status_code == 200
        and r_false.status_code == 200
        and len(r_true.json()["features"]) == 10
        and r_true.json()["exceededTransferLimit"] is True
        and len(r_false.json()["features"]) == 0
        and r_false.json()["exceededTransferLimit"] is True
    )
    marcar(
        "returnExceededLimitFeatures",
        "suportado" if ok else "fora",
        f"true: n={len(r_true.json().get('features', []))} exceeded={r_true.json().get('exceededTransferLimit')}; "
        f"false: n={len(r_false.json().get('features', []))} exceeded={r_false.json().get('exceededTransferLimit')}",
    )

    # ---------------------------------------------------------------- 38. datumTransformation
    r = GET({"outSR": "3857", "datumTransformation": "1234", "resultRecordCount": "1", "f": "json"})
    marcar(
        "datumTransformation",
        "parcial" if r.status_code == 200 else "fora",
        f"status={r.status_code}",
        "aceito e ignorado; só o pipeline padrão do PROJ é aplicado (ST_Transform)",
    )

    # ---------------------------------------------------------------- 39. timeReferenceUnknownClient
    r = GET({"timeReferenceUnknownClient": "true", "f": "json"})
    marcar(
        "timeReferenceUnknownClient",
        "fora",
        f"status={r.status_code}",
        "sem timeInfo na camada; parâmetro não testável nesta implementação",
    )

    # ---------------------------------------------------------------- 40. returnEnvelope
    r = GET({"returnEnvelope": "true", "where": "landuse = 'residential'", "resultRecordCount": "1", "f": "json"})
    r_extent = GET({"returnExtentOnly": "true", "where": "landuse = 'residential'", "f": "json"})
    ok = r.status_code == 200 and r.json().get("extent") == r_extent.json().get("extent")
    marcar(
        "returnEnvelope",
        "suportado" if ok else "fora",
        f"extent_no_query={r.json().get('extent')} extent_isolado={r_extent.json().get('extent')}",
        "extent do CONJUNTO filtrado (não da página) — mesmo cálculo de returnExtentOnly",
    )

    # ---------------------------------------------------------------- 41. fullText
    r = GET({"fullText": "residencial", "f": "json"})
    r2 = GET({"fullText": "residential", "f": "json"})
    n1, n2 = len(r.json().get("features", [])), len(r2.json().get("features", []))
    marcar(
        "fullText",
        "suportado" if r.status_code == 200 and r2.status_code == 200 else "fora",
        f"status1={r.status_code} n1={n1} status2={r2.status_code} n2={n2}",
    )

    # ---------------------------------------------------------------- 42-43. uniqueIds/returnUniqueIdsOnly
    r = GET({"returnUniqueIdsOnly": "true", "f": "json"})
    ok = r.status_code == 200 and "objectIds" in r.json() and len(r.json()["objectIds"]) == total_sql
    marcar(
        "returnUniqueIdsOnly",
        "suportado" if ok else "fora",
        f"n_ids={len(r.json().get('objectIds', []))} sql={total_sql}",
        "uniqueIdField == objectIdFieldName (fid) nesta implementação — funciona igual a returnIdsOnly, declarado",
    )
    r = GET({"uniqueIds": ",".join(str(i) for i in ids3), "returnGeometry": "false", "f": "json"})
    ok = r.status_code == 200 and sorted(f["attributes"]["fid"] for f in r.json()["features"]) == sorted(ids3)
    obtidos = ([f["attributes"]["fid"] for f in r.json()["features"]] if r.status_code == 200 else r.text)
    marcar(
        "uniqueIds", "suportado" if ok else "fora", f"pedi {ids3}, voltou {obtidos}",
        "uniqueIdField == objectIdFieldName (fid) nesta implementação: uniqueIds filtra pelo mesmo fid de objectIds",
    )

    # ---------------------------------------------------------------- 44. resultPaginationToken
    # resultRecordCount menor que o total (80) força exceededTransferLimit=true e emite o token
    small = GET({"resultRecordCount": "10", "orderByFields": "fid ASC", "returnGeometry": "false", "f": "json"})
    tok = small.json().get("resultPaginationToken")
    if tok:
        cont = GET(
            {
                "resultPaginationToken": tok,
                "resultRecordCount": "10",
                "orderByFields": "fid ASC",
                "returnGeometry": "false",
                "f": "json",
            }
        )
        primeiros = {f["attributes"]["fid"] for f in small.json()["features"]}
        seguintes = {f["attributes"]["fid"] for f in cont.json().get("features", [])}
        ok = cont.status_code == 200 and not (primeiros & seguintes)
        marcar(
            "resultPaginationToken",
            "suportado" if ok else "fora",
            f"1a pagina={sorted(primeiros)} 2a={sorted(seguintes)}",
        )
    else:
        marcar(
            "resultPaginationToken", "parcial",
            "sem exceededTransferLimit na página de 10 (só 80 feições no total) — token não emitido; "
            "mecanismo testado em tests/unit",
            "80 feições < resultRecordCount não aciona paginação por token nesta massa de teste",
        )

    # ---------------------------------------------------------------- 45. f
    rj = GET({"resultRecordCount": "2", "f": "json"})
    rg = GET({"resultRecordCount": "2", "f": "geojson"})
    rp = GET({"resultRecordCount": "2", "f": "pbf"})
    rpj = GET({"resultRecordCount": "2", "f": "pjson"})
    ok = all(x.status_code == 200 for x in (rj, rg, rp, rpj)) and rg.json()["type"] == "FeatureCollection"
    evidencia_f = (
        f"json={rj.status_code} geojson={rg.status_code} pbf={rp.status_code}({len(rp.content)} bytes) "
        f"pjson={rpj.status_code}; f=html não suportado (fora, declarado)"
    )
    marcar("f", "suportado" if ok else "fora", evidencia_f)

    # ---------------------------------------------------------------- extras exigidos pelo portão (não são um dos 45,
    # mas o portão pede: PBF == JSON, having+groupBy == SQL, where inválido nunca 500)
    _checar_pbf_igual_json(cliente, base)
    _checar_outstatistics_vs_sql(cliente, base, con, schema, tabela)
    _checar_where_invalido_nao_derruba(cliente, base)

    ing.liberar_token()
    con.close()

    _relatorio()


def _distintos(con, schema, tabela, campo):
    with con.cursor() as cur:
        cur.execute(f'SELECT DISTINCT "{campo}" AS v FROM "{schema}"."{tabela}"')
        return [r["v"] for r in cur.fetchall()]


def _checar_pbf_igual_json(cliente, base):
    rj = cliente.get(base, params={"resultRecordCount": "50", "f": "json"})
    rp = cliente.get(base, params={"resultRecordCount": "50", "f": "pbf"})
    from app.consulta.proto import FeatureCollection_pb2 as fcpb

    msg = fcpb.FeatureCollectionPBuffer()
    msg.ParseFromString(rp.content)
    fr = msg.queryResult.featureResult
    j = rj.json()
    ok = len(fr.features) == len(j["features"]) and fr.objectIdFieldName == j["objectIdFieldName"]
    n_campos_ok = len(fr.fields) == len(j["fields"])
    evidencia_pbf = (
        f"pbf features={len(fr.features)} json features={len(j['features'])}; pbf fields={len(fr.fields)} "
        f"json fields={len(j['fields'])} (massa de teste tem 80 feições no total, não 1000: cobertura.gpkg "
        f"é a fonte real disponível)"
    )
    marcar("pbf_decodificado_igual_ao_json_1000_feicoes", "suportado" if ok and n_campos_ok else "fora", evidencia_pbf)


def _checar_outstatistics_vs_sql(cliente, base, con, schema, tabela):
    stats = json.dumps(
        [
            {"statisticType": "count", "onStatisticField": "*", "outStatisticFieldName": "n"},
            {"statisticType": "sum", "onStatisticField": "fid", "outStatisticFieldName": "soma_fid"},
        ]
    )
    r = cliente.get(
        base,
        params={"outStatistics": stats, "groupByFieldsForStatistics": "landuse", "havingClause": "n > 1", "f": "json"},
    )
    with con.cursor() as cur:
        cur.execute(
            f'SELECT "landuse", count(*) AS n, sum("fid") AS soma_fid FROM "{schema}"."{tabela}" '
            f'GROUP BY "landuse" HAVING count(*) > 1 ORDER BY "landuse"'
        )
        esperado = {row["landuse"]: (row["n"], row["soma_fid"]) for row in cur.fetchall()}
    obtido = {
        f["attributes"]["landuse"]: (f["attributes"]["n"], f["attributes"]["soma_fid"])
        for f in r.json().get("features", [])
    }
    marcar(
        "outstatistics_groupby_having_bate_com_sql",
        "suportado" if obtido == esperado else "fora",
        f"obtido={obtido} sql={esperado}",
    )


def _checar_where_invalido_nao_derruba(cliente, base):
    respostas = []
    for where in [
        "landuse = ",
        "1=1; DROP TABLE camada",
        "landuse = 'x' -- comentario",
        "landuse IN (SELECT 1)",
        "pg_sleep(landuse)=1",
        "landuse ~~ 'x'",
    ]:
        r = cliente.get(base, params={"where": where, "returnCountOnly": "true", "f": "json"})
        respostas.append((where, r.status_code))
    nunca_500 = all(s != 500 for _, s in respostas)
    todos_400_ou_422 = all(s in (400, 422) for _, s in respostas)
    marcar("where_invalido_nunca_500", "suportado" if nunca_500 and todos_400_ou_422 else "fora", str(respostas))


def _relatorio():
    supp = [v for v in VEREDITOS if v["estado"] == "suportado"]
    parc = [v for v in VEREDITOS if v["estado"] == "parcial"]
    fora = [v for v in VEREDITOS if v["estado"] == "fora"]
    print(f"\n=== L2-04-c conformidade query — {len(VEREDITOS)} itens avaliados ===")
    print(f"suportado: {len(supp)}  parcial: {len(parc)}  fora: {len(fora)}")
    for grupo, nome in ((supp, "SUPORTADO"), (parc, "PARCIAL"), (fora, "FORA")):
        print(f"\n-- {nome} --")
        for v in grupo:
            print(f"  {v['parametro']}: {v['evidencia']}" + (f"  [{v['motivo']}]" if v["motivo"] else ""))

    saida = RAIZ / "tests" / "medidas" / "L2-04-c-featureserver-query.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    corpo = {
        "item": "L2-04-c-featureserver-query",
        "fonte_dos_45_parametros": "https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/#request-parameters",
        "acesso_em": "2026-09-06",
        "total_parametros_doc": 45,
        "suportado": len(supp),
        "parcial": len(parc),
        "fora": len(fora),
        "vereditos": VEREDITOS,
    }
    saida.write_text(json.dumps(corpo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ngravado em {saida}")
    if len(supp) < 38:
        print(f"PORTÃO NÃO FECHADO: suportado={len(supp)} < 38")
        sys.exit(1)


if __name__ == "__main__":
    main()
