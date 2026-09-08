"""Rota do traçado de custo mínimo sobre uma execução do motor multicritério (item L3-10-corredor-custo-minimo;
equivalente da casa ao par `Distance Accumulation` + `Optimal Path as Line`).

`POST /api/multiescala/execucoes/{id}/corredor` recebe dois pontos em EPSG:4326, monta a superfície de custo a
partir das notas da execução (regra em `app/amc/corredor_execucao.py`), acha o caminho de custo mínimo e o
corredor-epsilon, e devolve linha + corredor + MANIFESTO: a superfície declarada, os parâmetros e as medidas.
Síncrono porque a grade tem teto (`ESCALA_CELULAS_MAX`) e o traçado nessa escala leva menos de um segundo — o
que a resposta traz é a duração medida, não uma promessa.

Nada é gravado além do evento: quem quiser a linha como camada usa a rota de resultado-como-camada."""

import time

from fastapi import APIRouter, Request

from app import db, limites
from app.amc import corredor as motor
from app.amc import corredor_execucao as ponte
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import uuid_ok
from app.erros import ErroAPI
from app.multiescala.corredor_modelos import CorredorEntrada, CorredorSaida

router = APIRouter(prefix="/api/multiescala", tags=["multiescala"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "multiescala:usar"


def _erro(e: ponte.ErroCorredorExecucao) -> ErroAPI:
    """Traduz o erro do motor. Ponto em veto e ponto fora da área são 422 (o pedido é que está errado), e a
    mensagem diz QUAL dos dois pontos — sem isso o usuário fica trocando os dois às cegas."""
    return ErroAPI(422, e.codigo, e.mensagem, e.detalhe)


@router.post("/execucoes/{id}/corredor", response_model=CorredorSaida, openapi_extra=LER)
def tracar_corredor(id: str, corpo: CorredorEntrada, request: Request,
                    auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Traça a linha de custo mínimo entre dois pontos sobre as notas desta execução e devolve o corredor."""
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    inicio = time.perf_counter()
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT e.id, e.grade_id, g.colunas, g.linhas, g.resolucao_m, c.srid_trabalho, "
            "c.origem_x_m, c.origem_y_m "
            "FROM plat.escala_execucao e JOIN plat.escala_grade g ON g.id = e.grade_id "
            "JOIN plat.escala_conjunto c ON c.id = e.conjunto_id WHERE e.id = %s::uuid",
            (eid,),
        )
        ex = cur.fetchone()
        if not ex:
            raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
        colunas, linhas = int(ex["colunas"]), int(ex["linhas"])
        resolucao_m = float(ex["resolucao_m"])
        if colunas * linhas > limites.ESCALA_CELULAS_MAX:
            raise ErroAPI(422, "grade_grande_demais",
                          "a grade desta execução passa do teto de células do traçado",
                          {"celulas": colunas * linhas, "teto": limites.ESCALA_CELULAS_MAX})
        cur.execute(
            "SELECT c.col, c.lin, r.nota, r.aprovada FROM plat.escala_resultado r "
            "JOIN plat.escala_celula c ON c.id = r.celula_id WHERE r.execucao_id = %s::uuid",
            (eid,),
        )
        celulas = cur.fetchall()
        try:
            custo, veto, diag = ponte.superficie(
                celulas, colunas, linhas, custo_maximo=corpo.custo_maximo, sem_dado=corpo.sem_dado,
                veto_abaixo_de=corpo.veto_abaixo_de, veto_nao_aprovadas=corpo.veto_nao_aprovadas)
        except ponte.ErroCorredorExecucao as e:
            raise _erro(e) from e
        cur.execute(
            "SELECT ST_X(a) AS ax, ST_Y(a) AS ay, ST_X(b) AS bx, ST_Y(b) AS by FROM ("
            "  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%(alon)s, %(alat)s), 4326), %(srid)s) AS a, "
            "         ST_Transform(ST_SetSRID(ST_MakePoint(%(blon)s, %(blat)s), 4326), %(srid)s) AS b) q",
            {"alon": corpo.origem.lon, "alat": corpo.origem.lat, "blon": corpo.destino.lon,
             "blat": corpo.destino.lat, "srid": ex["srid_trabalho"]},
        )
        p = cur.fetchone()
        ox, oy = float(ex["origem_x_m"]), float(ex["origem_y_m"])
        try:
            a = ponte.celula_do_ponto(p["ax"], p["ay"], ox, oy, resolucao_m, colunas, linhas, "origem")
            b = ponte.celula_do_ponto(p["bx"], p["by"], ox, oy, resolucao_m, colunas, linhas, "destino")
            saida = ponte.tracar(custo, veto, a, b, vizinhanca=corpo.vizinhanca, epsilon=corpo.epsilon,
                                 resolucao_m=resolucao_m)
        except ponte.ErroCorredorExecucao as e:
            raise _erro(e) from e
        except motor.ErroCorredor as e:
            raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
        linha_geojson = _linha_geojson(cur, saida["linha"]["celulas"], ox, oy, resolucao_m, ex["srid_trabalho"])
        corredor_geojson, omitida, n_corredor = _corredor_geojson(cur, saida["corredor"], eid)
        duracao_ms = int((time.perf_counter() - inicio) * 1000)
        registrar_evento(cur, request, "multiescala/corredor", "escala_execucao", eid, {
            "custo_maximo": corpo.custo_maximo, "sem_dado": corpo.sem_dado,
            "veto_abaixo_de": corpo.veto_abaixo_de, "veto_nao_aprovadas": corpo.veto_nao_aprovadas,
            "vizinhanca": corpo.vizinhanca, "epsilon": corpo.epsilon,
            "celulas_vetadas": diag["celulas_vetadas"], "corredor_celulas": n_corredor,
            "comprimento_km": saida["metricas"]["comprimento_km"],
            "sinuosidade": saida["metricas"]["sinuosidade"], "duracao_ms": duracao_ms,
        })
        return {
            "execucao_id": eid,
            "linha": linha_geojson,
            "corredor": corredor_geojson,
            "corredor_celulas": n_corredor,
            "corredor_geometria_omitida": omitida,
            "manifesto": {
                "superficie": diag,
                "parametros": {
                    "origem": {"lon": corpo.origem.lon, "lat": corpo.origem.lat, "lin": a[0], "col": a[1]},
                    "destino": {"lon": corpo.destino.lon, "lat": corpo.destino.lat, "lin": b[0], "col": b[1]},
                    "vizinhanca": corpo.vizinhanca, "epsilon": corpo.epsilon,
                    "motor": saida["linha"]["motor"], "resolucao_m": resolucao_m,
                    "colunas": colunas, "linhas": linhas, "srid_trabalho": ex["srid_trabalho"],
                },
                "medidas": {
                    **saida["metricas"],
                    "custo_total": round(saida["linha"]["custo"], 4),
                    "corredor_otimo": round(saida["corredor"]["otimo"], 4) if saida["corredor"] else None,
                    "corredor_teto": round(saida["corredor"]["teto"], 4) if saida["corredor"] else None,
                },
            },
            "duracao_ms": duracao_ms,
        }


def _linha_geojson(cur, celulas, origem_x_m: float, origem_y_m: float, resolucao_m: float, srid: int) -> dict:
    """Centro de cada célula do caminho, no CRS de trabalho, virado LineString em 4326 pelo próprio banco."""
    pontos = ", ".join(
        f"{origem_x_m + (int(c) + 0.5) * resolucao_m} {origem_y_m + (int(li) + 0.5) * resolucao_m}"
        for li, c in celulas
    )
    if len(celulas) < 2:  # caminho de uma célula só: LineString precisa de dois pontos
        pontos = f"{pontos}, {pontos}"
    cur.execute(
        "SELECT ST_AsGeoJSON(ST_Transform(ST_GeomFromText(%s, %s), 4326))::json AS g",
        (f"LINESTRING({pontos})", srid),
    )
    return cur.fetchone()["g"]


def _corredor_geojson(cur, faixa, eid: str) -> tuple[dict | None, bool, int]:
    """União das células do corredor, vinda das geometrias que a grade já tem (nunca recalculadas aqui)."""
    if not faixa:
        return None, False, 0
    n = int(faixa["celulas"])
    if n > limites.CORREDOR_CELULAS_GEOJSON_MAX:
        return None, True, n
    lins, cols = faixa["mascara"].nonzero()
    cur.execute(
        "SELECT ST_AsGeoJSON(ST_Union(c.geom))::json AS g FROM plat.escala_celula c "
        "JOIN plat.escala_resultado r ON r.celula_id = c.id AND r.execucao_id = %s::uuid "
        "JOIN unnest(%s::int[], %s::int[]) AS p(lin, col) ON p.lin = c.lin AND p.col = c.col",
        (eid, [int(x) for x in lins], [int(x) for x in cols]),
    )
    return cur.fetchone()["g"], False, n
