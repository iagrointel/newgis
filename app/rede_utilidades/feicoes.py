"""Feições da rede (item L4-01-b-topologia-derivada): as tabelas genéricas `plat.rede_feicao_ponto`
(dispositivo) e `plat.rede_feicao_linha` (trecho) que a topologia deriva. São camadas NORMAIS e EDITÁVEIS —
esta passagem não as une ao catálogo geral (`camada_vetorial`, tabela dinâmica `d_<slug>.c_<uuid>`); ver
docs/rede/TOPOLOGIA.md seção "fronteira" para a fronteira honesta dessa decisão.

Cada feição pertence a um `plat.rede_tipo` (por `grupo`+`tipo_codigo`, o vocabulário do pacote importado); a
geometria (ponto/linha) tem de bater com `rede_grupo.geometria`, senão a gravação é recusada — uma feição de
linha num grupo de ponto não tem terminal, não tem topologia."""

import json

import psycopg2
import psycopg2.extras

from app.auth import comum as auth_comum
from app.erros import ErroAPI


def _jsonb(v: dict) -> str:
    return json.dumps(v, ensure_ascii=False)


def _tipo_do_grupo(cur, rede_id: str, grupo_codigo: str, tipo_codigo: int, geometria_esperada: str) -> str:
    cur.execute(
        "SELECT tp.id, g.geometria FROM plat.rede_tipo tp JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
        "WHERE tp.rede_id = %s::uuid AND g.codigo = %s AND tp.codigo = %s",
        (rede_id, grupo_codigo, tipo_codigo),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "tipo_inexistente", f"o grupo/tipo {grupo_codigo}/{tipo_codigo} não existe nesta rede "
                      "(a rede tem pacote de ativos importado?)")
    if r["geometria"] != geometria_esperada:
        raise ErroAPI(422, "geometria_incompativel",
                      f"o grupo {grupo_codigo} é de geometria '{r['geometria']}', não '{geometria_esperada}'")
    return r["id"]


def criar_ponto(cur, tenant_id: int, rede_id: str, corpo) -> dict:
    tipo_id = _tipo_do_grupo(cur, rede_id, corpo.grupo, corpo.tipo_codigo, "ponto")
    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao_ponto(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos) "
            "VALUES (%s, %s::uuid, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s::jsonb) "
            "RETURNING id, tipo_id, fase_bitmask, atributos, criado_em",
            (tenant_id, rede_id, tipo_id, corpo.lon, corpo.lat, corpo.fase_bitmask, _jsonb(corpo.atributos)),
        )
    except psycopg2.Error as e:
        raise auth_comum.erro_do_banco(e) from e
    r = cur.fetchone()
    tolerancia = _tolerancia_se_topologia_construida(cur, rede_id)
    if tolerancia is not None:
        marcar_area_suja(cur, tenant_id, rede_id, "criacao", str(r["id"]),
                         [f"POINT({corpo.lon} {corpo.lat})"], tolerancia)
    return r


def criar_linha(cur, tenant_id: int, rede_id: str, corpo) -> dict:
    tipo_id = _tipo_do_grupo(cur, rede_id, corpo.grupo, corpo.tipo_codigo, "linha")
    wkt = "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in corpo.coordenadas) + ")"
    try:
        cur.execute(
            "INSERT INTO plat.rede_feicao_linha(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos) "
            "VALUES (%s, %s::uuid, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s::jsonb) "
            "RETURNING id, tipo_id, fase_bitmask, atributos, criado_em",
            (tenant_id, rede_id, tipo_id, wkt, corpo.fase_bitmask, _jsonb(corpo.atributos)),
        )
    except psycopg2.Error as e:
        raise auth_comum.erro_do_banco(e) from e
    r = cur.fetchone()
    tolerancia = _tolerancia_se_topologia_construida(cur, rede_id)
    if tolerancia is not None:
        marcar_area_suja(cur, tenant_id, rede_id, "criacao", str(r["id"]), [wkt], tolerancia)
    return r


def listar_pontos(cur, rede_id: str, limite: int) -> list[dict]:
    cur.execute(
        "SELECT id, tipo_id, fase_bitmask, atributos, criado_em FROM plat.rede_feicao_ponto "
        "WHERE rede_id = %s::uuid ORDER BY criado_em LIMIT %s",
        (rede_id, limite),
    )
    return cur.fetchall()


def listar_linhas(cur, rede_id: str, limite: int) -> list[dict]:
    cur.execute(
        "SELECT id, tipo_id, fase_bitmask, atributos, criado_em FROM plat.rede_feicao_linha "
        "WHERE rede_id = %s::uuid ORDER BY criado_em LIMIT %s",
        (rede_id, limite),
    )
    return cur.fetchall()


# --- GeoJSON para o mapa (item L2-01-mapa-web, fatia "rede de utilidades") ------------------------------
# Bloco restaurado de da2330fd: a fusão de 17/09 ficou com um feicoes.py sem estes 2 ajudantes (as rotas
# .geojson de rotas_topologia.py foram clobadas junto). `.geojson`: mesmas duas tabelas, mas com a geometria
# (ST_AsGeoJSON, 6 casas — ~11 cm, sobra para a escala de rede de distribuição) e o nome do tipo/disciplina
# já resolvidos pelo join tipo->grupo->domínio, para o navegador não ter de saber o esquema do pacote de
# ativos só para rotular um popup.
_SQL_GEOJSON_PONTO = (
    "SELECT f.id, f.tipo_id, tp.nome AS tipo, dm.disciplina AS disciplina, f.fase_bitmask, f.atributos, "
    "ST_AsGeoJSON(f.geom, 6) AS geojson "
    "FROM plat.rede_feicao_ponto f "
    "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
    "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
    "JOIN plat.rede_dominio dm ON dm.id = g.dominio_id "
    "WHERE f.rede_id = %(rede_id)s::uuid"
)
_SQL_GEOJSON_LINHA = (
    "SELECT f.id, f.tipo_id, tp.nome AS tipo, dm.disciplina AS disciplina, f.fase_bitmask, f.atributos, "
    "ST_AsGeoJSON(f.geom, 6) AS geojson "
    "FROM plat.rede_feicao_linha f "
    "JOIN plat.rede_tipo tp ON tp.id = f.tipo_id "
    "JOIN plat.rede_grupo g ON g.id = tp.grupo_id "
    "JOIN plat.rede_dominio dm ON dm.id = g.dominio_id "
    "WHERE f.rede_id = %(rede_id)s::uuid"
)
_BBOX_SQL = " AND f.geom && ST_MakeEnvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326)"


def _feicao_para_feature(r: dict) -> dict:
    propriedades = {
        **(r["atributos"] or {}),
        "id": str(r["id"]),
        "tipo_id": str(r["tipo_id"]),
        "tipo": r["tipo"],
        "disciplina": r["disciplina"],
        "fase_bitmask": r["fase_bitmask"],
    }
    return {"type": "Feature", "geometry": json.loads(r["geojson"]), "properties": propriedades}


def _feature_collection(
    cur, sql_base: str, rede_id: str, limite: int, bbox: tuple[float, float, float, float] | None
) -> dict:
    sql = sql_base
    params = {"rede_id": rede_id}
    if bbox is not None:
        sql += _BBOX_SQL
        params.update(minx=bbox[0], miny=bbox[1], maxx=bbox[2], maxy=bbox[3])
    sql += " ORDER BY f.id LIMIT %(limite)s"
    params["limite"] = limite
    cur.execute(sql, params)
    linhas = cur.fetchall()
    return {"type": "FeatureCollection", "features": [_feicao_para_feature(r) for r in linhas]}


def geojson_pontos(cur, rede_id: str, limite: int, bbox: tuple[float, float, float, float] | None) -> dict:
    return _feature_collection(cur, _SQL_GEOJSON_PONTO, rede_id, limite, bbox)


def geojson_linhas(cur, rede_id: str, limite: int, bbox: tuple[float, float, float, float] | None) -> dict:
    return _feature_collection(cur, _SQL_GEOJSON_LINHA, rede_id, limite, bbox)


# --- área suja (refutação do item: applyEdits tem de marcar onde a topologia gravada ficou velha) -----------

def _tolerancia_se_topologia_construida(cur, rede_id: str) -> float | None:
    """A tolerância da última construção, ou None se a rede nunca teve `habilitar`. Sem topologia construída
    não existe índice a proteger, logo nenhuma edição marca área suja (o primeiro `habilitar` já lê o estado
    atual das feições)."""
    cur.execute("SELECT tolerancia_m FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    return float(r["tolerancia_m"]) if r else None


def marcar_area_suja(cur, tenant_id: int, rede_id: str, motivo: str, feicao_id: str,
                     wkts: list[str | None], tolerancia_m: float) -> None:
    """Grava o polígono da área suja: envelope da geometria velha U nova, expandido pela tolerância da rede
    (em `geography`, metros de verdade) — qualquer nó/aresta da topologia gravada dentro dele é suspeito até
    o próximo `habilitar`."""
    geoms = [w for w in wkts if w]
    if not geoms:
        return
    partes = ", ".join(["ST_GeomFromText(%s, 4326)"] * len(geoms))
    cur.execute(
        "INSERT INTO plat.rede_topo_area_suja(tenant_id, rede_id, motivo, feicao_id, geom) "
        f"SELECT %s, %s::uuid, %s, %s::uuid, "
        f"ST_Buffer(ST_Envelope(ST_Collect(ARRAY[{partes}]))::geography, %s)::geometry "
        "RETURNING id",
        (tenant_id, rede_id, motivo, feicao_id, *geoms, tolerancia_m),
    )
    linha = cur.fetchone()
    if linha is not None:
        _propagar_aos_derivados(cur, rede_id, str(linha["id"]))


def _propagar_aos_derivados(cur, rede_id: str, area_id: str) -> None:
    """Uma área suja nova invalida, NO MESMO INSTANTE, o que foi derivado da rede e a edição tocou: a subrede
    volta a `suja` (item L4-04-a) e o diagrama a `inconsistente` (item L4-04-d).

    Por que aqui e por que agora. Os dois derivados já sabiam se marcar (`subredes.marcar_sujas` e
    `diagrama.marcar_inconsistentes`), mas ninguém os chamava na edição: a primeira só era chamada por
    `topologia.habilitar()` e pela atualização em lote, e a segunda não era chamada em lugar nenhum. O
    estado tem de ser gravado no instante da edição, não calculado depois, porque `habilitar()` APAGA as
    áreas sujas da rede — quem sobrevive à reconstrução é o estado gravado do derivado, não a área.

    Este é o único ponto por onde passam as cinco portas de edição (criar ponto, criar linha, e
    `applyEdits` de adição, alteração e remoção), e só roda quando a rede já tem topologia construída —
    logo a propagação não pesa em carga inicial, onde não há derivado a invalidar. Passa o `area_id` desta
    edição: o cruzamento é com a área desta feição, nunca com todas as áreas abertas da rede, para que uma
    edição a quilômetros de distância não suje um derivado que ela não tocou."""
    from app.rede_utilidades import diagrama as diagrama_mod
    from app.rede_utilidades import subredes as subredes_mod

    subredes_mod.marcar_sujas(cur, rede_id, area_id)
    diagrama_mod.marcar_inconsistentes(cur, rede_id, area_id)


def _wkt_ponto(lon: float, lat: float) -> str:
    return f"POINT({lon} {lat})"


def _wkt_linha(caminho: list) -> str:
    return "LINESTRING(" + ", ".join(f"{par[0]} {par[1]}" for par in caminho) + ")"


def _geom_esri(entrada: dict, geometria: str) -> str:
    """Geometria no JSON da Esri (ponto `{"x":..,"y":..}`, linha `{"paths":[[[lon,lat],...]]}`) → WKT.
    A linha aceita um único caminho (o caso da edição de trecho); multiparte é recusada com mensagem clara
    em vez de virar MULTILINESTRING silencioso — a feição de trecho aqui é LineString simples."""
    g = entrada.get("geometry")
    if g is None:
        raise ErroAPI(422, "geometria_ausente", "a feição não trouxe 'geometry'")
    if geometria == "ponto":
        try:
            return _wkt_ponto(float(g["x"]), float(g["y"]))
        except (KeyError, TypeError, ValueError) as e:
            raise ErroAPI(422, "geometria_invalida", "ponto exige geometry {\"x\": lon, \"y\": lat}") from e
    caminhos = g.get("paths") if isinstance(g, dict) else None
    if not caminhos or len(caminhos) != 1 or len(caminhos[0]) < 2:
        raise ErroAPI(422, "geometria_invalida",
                      "linha exige geometry {\"paths\": [[[lon, lat], ...]]} com um único caminho de 2+ pontos")
    return _wkt_linha(caminhos[0])


def aplicar_edicoes(cur, tenant_id: int, rede_id: str, corpo: dict, geometria: str) -> dict:
    """applyEdits (paridade FeatureServer) sobre a camada de rede: `adds`, `updates`, `deletes` numa chamada,
    resultado por feição (`addResults`/`updateResults`/`deleteResults` com `success` e `error` por item).
    `tipo_codigo`/`grupo` vão nos ATRIBUTOS do add (é o vocabulário do pacote, como nas rotas de criação);
    o update identifica a feição por `attributes.id` e aceita geometria nova, `fase_bitmask` e `atributos`
    novos — qualquer combinação. Cada feição gravada marca a área suja correspondente SE a topologia já foi
    construída (refutação do item). A chamada inteira é uma transação só (o `db.db` da rota dá commit no fim):
    se algo inesperado quebra, nada fica gravado pela metade — mas falhas ESPERADAS (tipo inexistente, id
    desconhecido) viram `success: false` no item e não derrubam as demais, como no applyEdits da Esri."""
    tabela = "rede_feicao_ponto" if geometria == "ponto" else "rede_feicao_linha"
    tolerancia = _tolerancia_se_topologia_construida(cur, rede_id)
    res = {"addResults": [], "updateResults": [], "deleteResults": []}
    _seq = {"n": 0}

    def falha(saida, feicao_id, e):
        item = {"id": feicao_id, "success": False,
                "error": {"code": e.status_code if isinstance(e, ErroAPI) else 500,
                          "description": e.mensagem if isinstance(e, ErroAPI) else str(e)}}
        res[saida].append(item)

    def savepoint():
        """Um erro de banco (ex.: CHECK de fase_bitmask) aborta a transação do Postgres INTEIRA; sem um
        SAVEPOINT por feição, a primeira falha esperada derrubaria todos os itens seguintes do lote. Com ele,
        a falha fica no item (success: false) e o lote continua — comportamento do applyEdits da Esri."""
        _seq["n"] += 1
        return f"sp_applyedits_{_seq['n']}"

    for entrada in corpo.get("adds", []):
        sp = savepoint()
        cur.execute(f"SAVEPOINT {sp}")
        try:
            atributos = entrada.get("attributes") or {}
            tipo_id = _tipo_do_grupo(cur, rede_id, atributos.get("grupo", ""),
                                     atributos.get("tipo_codigo", -1), geometria)
            wkt = _geom_esri(entrada, geometria)
            cur.execute(
                f"INSERT INTO plat.{tabela}(tenant_id, rede_id, tipo_id, geom, fase_bitmask, atributos) "
                "VALUES (%s, %s::uuid, %s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s::jsonb) RETURNING id",
                (tenant_id, rede_id, tipo_id, wkt, atributos.get("fase_bitmask"),
                 _jsonb(atributos.get("atributos") or {})),
            )
            novo_id = str(cur.fetchone()["id"])
            if tolerancia is not None:
                marcar_area_suja(cur, tenant_id, rede_id, "criacao", novo_id, [wkt], tolerancia)
            res["addResults"].append({"id": novo_id, "success": True})
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except (ErroAPI, psycopg2.Error) as e:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            falha("addResults", None, e)

    for entrada in corpo.get("updates", []):
        atributos = entrada.get("attributes") or {}
        feicao_id = atributos.get("id")
        sp = savepoint()
        cur.execute(f"SAVEPOINT {sp}")
        try:
            if not feicao_id:
                raise ErroAPI(422, "id_ausente", "o update não trouxe attributes.id")
            cur.execute(
                f"SELECT ST_AsText(geom) AS wkt FROM plat.{tabela} WHERE id = %s::uuid AND rede_id = %s::uuid "
                "FOR UPDATE",
                (feicao_id, rede_id),
            )
            velha = cur.fetchone()
            if velha is None:
                raise ErroAPI(404, "feicao_inexistente", f"a feição {feicao_id} não existe nesta rede")
            wkt_novo = _geom_esri(entrada, geometria) if "geometry" in entrada else None
            novos_atributos = atributos.get("atributos") if "atributos" in atributos else None
            cur.execute(
                f"UPDATE plat.{tabela} SET "
                "geom = COALESCE(ST_SetSRID(ST_GeomFromText(%s), 4326), geom), "
                "fase_bitmask = COALESCE(%s, fase_bitmask), "
                "atributos = COALESCE(%s::jsonb, atributos) "
                "WHERE id = %s::uuid AND rede_id = %s::uuid",
                (wkt_novo, atributos.get("fase_bitmask"),
                 _jsonb(novos_atributos) if novos_atributos is not None else None, feicao_id, rede_id),
            )
            if tolerancia is not None:
                marcar_area_suja(cur, tenant_id, rede_id, "edicao", feicao_id,
                                 [velha["wkt"], wkt_novo], tolerancia)
            res["updateResults"].append({"id": feicao_id, "success": True})
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except (ErroAPI, psycopg2.Error) as e:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            falha("updateResults", feicao_id, e)

    for feicao_id in corpo.get("deletes", []):
        sp = savepoint()
        cur.execute(f"SAVEPOINT {sp}")
        try:
            cur.execute(
                f"DELETE FROM plat.{tabela} WHERE id = %s::uuid AND rede_id = %s::uuid "
                "RETURNING ST_AsText(geom) AS wkt",
                (feicao_id, rede_id),
            )
            velha = cur.fetchone()
            if velha is None:
                raise ErroAPI(404, "feicao_inexistente", f"a feição {feicao_id} não existe nesta rede")
            if tolerancia is not None:
                marcar_area_suja(cur, tenant_id, rede_id, "remocao", feicao_id, [velha["wkt"]], tolerancia)
            res["deleteResults"].append({"id": feicao_id, "success": True})
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except (ErroAPI, psycopg2.Error) as e:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            falha("deleteResults", feicao_id, e)

    return res
