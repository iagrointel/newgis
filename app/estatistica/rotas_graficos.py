"""Rota `POST /api/camadas/{item_id}/grafico` (item L2-01-i-graficos-de-camada): um gráfico por pedido,
agregado no servidor (`app/estatistica/graficos.py`); a leitura do item, as colunas, o filtro/extensão e o
cache são os mesmos da rota de estatísticas do L2-06-e (`app/estatistica/rotas.py`)."""

from __future__ import annotations

import json
import time

import psycopg2.extensions
from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.estatistica import agregacao as agr
from app.estatistica import graficos as gr
from app.estatistica.rotas import (
    X,
    _cache_guardar,
    _cache_obter,
    _camada_do_item,
    _colunas,
    compilar_filtro,
    visiveis,
)
from app.schema_ambiente import reescrever_schema
from app.settings import settings

router = APIRouter(tags=["estatistica"])


def _num(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "quantize"):
        return float(v)
    return v


# date/timestamp/timestamptz chegam como TEXTO do Postgres, não como datetime do Python: a faixa de um
# gráfico é um rótulo, e o datetime do Python não representa ano 0 (que é onde '0001-01-01 UTC' cai ao
# ser truncado em America/Sao_Paulo), nem 'infinity' — refutação "datas fora de faixa" do item.
_DATA_COMO_TEXTO = psycopg2.extensions.new_type((1082, 1114, 1184), "PLAT_DATA_TEXTO", lambda v, _cur: v)


def _executar(cur, sql: gr.Sql) -> list[dict]:
    sql_final = reescrever_schema(sql.sql, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO)
    with cur.connection.cursor() as tcur:
        psycopg2.extensions.register_type(_DATA_COMO_TEXTO, tcur)
        tcur.execute(sql_final, sql.params)
        nomes = [d.name for d in tcur.description]
        return [dict(zip(nomes, linha, strict=True)) for linha in tcur.fetchall()]


def _reltuples(cur, schema: str, tabela: str) -> float | None:
    """Estimativa de linhas do planejador (para dimensionar a amostra). schema/tabela já passaram por IDENT_RE
    e entram como literal de TEXTO: a reescrita de schema de trilha só enxerga o texto do SQL."""
    sql = f"SELECT reltuples FROM pg_class WHERE oid = to_regclass('\"{schema}\".\"{tabela}\"')"
    with cur.connection.cursor() as tcur:
        tcur.execute(reescrever_schema(sql, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO))
        r = tcur.fetchone()
    return float(r[0]) if r and r[0] is not None else None


def _categorias(cur, camada, p, colunas, where_sql, where_params) -> dict:
    linhas = _executar(cur, gr.sql_categorias(camada["schema"], camada["tabela"], p, colunas, where_sql, where_params))
    series = [{"chave": _num(r["chave"]), "n": int(r["n"]), "valor": _num(r["valor"])} for r in linhas]
    if not linhas:
        return {"series": [], "total": 0, "nulos": 0, "grupos": 0, "truncado": False, "outros": None}
    grupos = int(linhas[0]["grupos"])
    n_total = int(linhas[0]["n_total"])
    s_total = _num(linhas[0]["s_total"])
    ny_total = int(linhas[0]["ny_total"] or 0)
    nulos = int(linhas[0]["nulos"])
    outros = None
    if grupos > len(linhas):
        n_resto = n_total - sum(int(r["n"]) for r in linhas)
        s_resto = None if s_total is None else s_total - sum(float(r["s"] or 0) for r in linhas)
        ny_resto = ny_total - sum(int(r["ny"]) for r in linhas)
        if p.estatistica == "count":
            valor = n_resto
        elif p.estatistica == "sum":
            valor = s_resto
        else:
            valor = (s_resto / ny_resto) if (s_resto is not None and ny_resto) else None
        outros = {"categorias": grupos - len(linhas), "n": n_resto, "valor": valor}
    return {"series": series, "total": n_total, "nulos": nulos, "grupos": grupos,
            "truncado": outros is not None, "outros": outros}


def _linha(cur, camada, p, colunas, where_sql, where_params) -> dict:
    try:
        sql = gr.sql_linha(camada["schema"], camada["tabela"], p, colunas, where_sql, where_params)
    except agr.ErroAgregacao as exc:
        raise ErroAPI(422, exc.codigo, exc.mensagem) from exc
    linhas = _executar(cur, sql)
    if len(linhas) > agr.LIMITE_GRUPOS:
        raise ErroAPI(422, "limite_de_grupos_excedido",
                      f"a série de datas passou de {agr.LIMITE_GRUPOS} faixas; use granularidade maior ou um filtro")
    series = [{"chave": _num(r["faixa"]), "n": int(r["n"]),
               "valor": _num(r["valor"]) if p.estatistica != "count" else int(r["n"])} for r in linhas]
    nulos = sum(r["n"] for r in series if r["chave"] is None)
    return {"series": series, "total": sum(r["n"] for r in series), "nulos": nulos, "grupos": len(series),
            "truncado": False, "outros": None}


def _histograma(cur, camada, p, colunas, where_sql, where_params) -> dict:
    linhas = _executar(cur, gr.sql_histograma(camada["schema"], camada["tabela"], p, colunas, where_sql, where_params))
    if not linhas or linhas[0]["lo"] is None or int(linhas[0]["n"]) == 0:
        nulos = int(linhas[0]["nulos"]) if linhas else 0
        return {"series": [], "bordas": [], "total": nulos, "nulos": nulos, "grupos": 0, "truncado": False,
                "outros": None}
    primeiro = linhas[0]
    bordas = [float(b) for b in primeiro["bordas"]]
    contas = {int(r["faixa"]): int(r["conta"]) for r in linhas if r["faixa"] is not None}
    series = [{"chave": i, "de": bordas[i - 1], "ate": bordas[i], "n": contas.get(i, 0), "valor": contas.get(i, 0)}
              for i in range(1, p.faixas + 1)]
    n, nulos = int(primeiro["n"]), int(primeiro["nulos"])
    return {"series": series, "bordas": bordas, "minimo": float(primeiro["lo"]), "maximo": float(primeiro["hi"]),
            "total": n + nulos, "nulos": nulos, "grupos": p.faixas, "truncado": False, "outros": None}


def _dispersao(cur, camada, p, colunas, where_sql, where_params) -> dict:
    reg = _executar(cur, gr.sql_regressao(camada["schema"], camada["tabela"], p, colunas, where_sql, where_params))[0]
    n, total = int(reg["n"] or 0), int(reg["total"] or 0)
    pct = gr.percentual_amostra(_reltuples(cur, camada["schema"], camada["tabela"]), p.amostra)
    amostra = gr.sql_amostra(camada["schema"], camada["tabela"], p, colunas, where_sql, where_params, pct)
    pontos = _executar(cur, amostra)
    series = [{"x": float(r["x"]), "y": float(r["y"])} for r in pontos]
    regressao = None
    if reg["a"] is not None and reg["b"] is not None:
        regressao = {"a": float(reg["a"]), "b": float(reg["b"]), "r2": None if reg["r2"] is None else float(reg["r2"]),
                     "n": n}
    return {"series": series, "regressao": regressao, "amostra": len(series) < n,
            "x_min": _num(reg["x_min"]), "x_max": _num(reg["x_max"]), "y_min": _num(reg["y_min"]),
            "y_max": _num(reg["y_max"]), "total": total, "nulos": total - n, "grupos": len(series),
            "truncado": len(series) < n, "outros": None}


@router.post("/api/camadas/{item_id}/grafico", openapi_extra=X)
def grafico(
    item_id: str,
    corpo: dict,
    request: Request,
    auth: Auth = autenticado(escopo_token="camada:ler"),
):
    """Gráfico de uma camada, agregado no servidor. Corpo: `tipo` (barras, pizza, linha, histograma,
    dispersao, contagem), `campo`, `campo_y`, `estatistica` (count, sum, avg), `granularidade`, `fuso`,
    `faixas`, `max_categorias`, `amostra`, `filtro` (where SQL-92) e `extensao` (caixa em graus)."""
    t0 = time.perf_counter()
    try:
        p = gr.montar_pedido(corpo)
    except agr.ErroAgregacao as exc:
        raise ErroAPI(422, exc.codigo, exc.mensagem) from exc

    with db.db(auth.contexto()) as cur:
        camada = _camada_do_item(cur, item_id)
        todas = _colunas(cur, camada["schema"], camada["tabela"])
        colunas = visiveis(todas)
        corpo_canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
        chave = (camada["item_id"], camada["versao_atual"], "grafico", corpo_canonico)
        cacheado = _cache_obter(chave)
        if cacheado is not None:
            saida = dict(cacheado)
            saida["cache"] = True
            return saida
        where_sql, where_params = compilar_filtro(corpo, todas)
        try:
            if p.tipo == "contagem":
                r = _executar(cur, gr.sql_contagem(camada["schema"], camada["tabela"], where_sql, where_params))[0]
                resultado = {"series": [], "total": int(r["total"]), "nulos": 0, "grupos": 0, "truncado": False,
                             "outros": None}
            elif p.tipo in ("barras", "pizza"):
                resultado = _categorias(cur, camada, p, colunas, where_sql, where_params)
            elif p.tipo == "linha":
                resultado = _linha(cur, camada, p, colunas, where_sql, where_params)
            elif p.tipo == "histograma":
                resultado = _histograma(cur, camada, p, colunas, where_sql, where_params)
            else:
                resultado = _dispersao(cur, camada, p, colunas, where_sql, where_params)
        except agr.ErroAgregacao as exc:
            raise ErroAPI(422, exc.codigo, exc.mensagem) from exc

    resposta = {"tipo": p.tipo, "campo": p.campo, "campo_y": p.campo_y, "estatistica": p.estatistica,
                "granularidade": p.granularidade if p.tipo == "linha" else None, **resultado,
                "tempo_ms": round((time.perf_counter() - t0) * 1000, 1), "cache": False}
    _cache_guardar(chave, resposta)
    return resposta
