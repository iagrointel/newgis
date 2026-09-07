"""Rotas de revisão do item L2-11-a-geocodificacao-csv: a criação do lote é a rota genérica `POST /api/jobs`
(tipo `geocodificador.lote_csv`, ver `tarefas.py`) — aqui só o que é específico da tela de revisão: listar
pendentes, gravar a coordenada arrastada no mapa (origem 'manual') e re-geocodificar só os pendentes."""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, uuid_ok
from app.erros import ErroAPI
from app.geocodificador import lote

router = APIRouter(prefix="/api/geocodificador/lote", tags=["geocodificador"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EDITAR = {"x-auth": "S", "x-privilegio": "feicoes.editar"}
_SCHEMA_OK = re.compile(r"^d_[a-z0-9_]{1,60}$")
_TABELA_OK = re.compile(r"^c_[0-9a-f]{16}$")


class CoordenadaManual(BaseModel):
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)


class RegeocodificarEntrada(BaseModel):
    limiar_pendente: float | None = Field(default=None, ge=0, le=100)


def _item_geocodificacao(cur, item_id: str) -> dict:
    """Carrega o item + a linha de `plat.geocodificacao_lote`; 404 (nunca 403) se o item não existe, não é
    desta trilha de produto, ou pertence a outro inquilino (RLS de `plat.item` já filtra por tenant; o filtro
    por `dados->>'fonte'` aqui é só para não confundir com camada importada por outro caminho)."""
    cur.execute("SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'",
                (item_id,))
    item = cur.fetchone()
    if item is None or (item["dados"] or {}).get("fonte") != "geocodificacao_lote":
        raise ErroAPI(404, "item_inexistente", "camada de geocodificação inexistente")
    cur.execute("SELECT * FROM plat.geocodificacao_lote WHERE item_id = %s::uuid", (item_id,))
    registro = cur.fetchone()
    if registro is None:
        raise ErroAPI(404, "item_inexistente", "camada de geocodificação inexistente")
    schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
    if not (_SCHEMA_OK.match(schema) and _TABELA_OK.match(tabela)):
        raise ErroAPI(500, "camada_corrompida", "nome de schema/tabela da camada é inválido")
    return {"item": item, "registro": registro, "schema": schema, "tabela": tabela}


@router.get("", openapi_extra=LER)
def listar(limite: int = Query(50, ge=1, le=200), auth: Auth = autenticado(escopo_token="geocodificar:usar")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT g.item_id, i.titulo, g.resumo, g.limiar_pendente, g.criado_em "
            "FROM plat.geocodificacao_lote g JOIN plat.item i ON i.id = g.item_id "
            "ORDER BY g.criado_em DESC LIMIT %s",
            (limite,),
        )
        linhas = cur.fetchall()
    return {"itens": [
        {"item_id": str(r["item_id"]), "titulo": r["titulo"], "resumo": r["resumo"],
         "limiar_pendente": float(r["limiar_pendente"]), "criado_em": r["criado_em"].isoformat()}
        for r in linhas
    ]}


@router.get("/{item_id}", openapi_extra=LER)
def ver(item_id: str, auth: Auth = autenticado(escopo_token="geocodificar:usar")):
    iid = uuid_ok(item_id, "item_inexistente", "camada de geocodificação inexistente")
    with db.db(auth.contexto()) as cur:
        ctx = _item_geocodificacao(cur, iid)
    r = ctx["registro"]
    return {
        "item_id": iid, "titulo": ctx["item"]["titulo"],
        "mapeamento": r["mapeamento"], "limiar_pendente": float(r["limiar_pendente"]), "resumo": r["resumo"],
        "proveniencia_enderecos": r["proveniencia"], "criado_em": r["criado_em"].isoformat(),
    }


@router.get("/{item_id}/pendentes", openapi_extra=LER)
def pendentes(item_id: str, limite: int = Query(200, ge=1, le=1000), deslocamento: int = Query(0, ge=0),
              auth: Auth = autenticado(escopo_token="geocodificar:usar")):
    iid = uuid_ok(item_id, "item_inexistente", "camada de geocodificação inexistente")
    with db.db(auth.contexto()) as cur:
        ctx = _item_geocodificacao(cur, iid)
        schema, tabela = ctx["schema"], ctx["tabela"]
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}" WHERE pendente')
        total = cur.fetchone()["n"]
        cur.execute(
            f'SELECT fid, endereco_entrada, campos_entrada, ST_X(geom) AS lon, ST_Y(geom) AS lat, score, '
            f'  tipo_acerto, erro, avisos, origem '
            f'FROM "{schema}"."{tabela}" WHERE pendente ORDER BY fid LIMIT %s OFFSET %s',
            (limite, deslocamento),
        )
        linhas = cur.fetchall()
    return {
        "total": total,
        "itens": [
            {"fid": r["fid"], "endereco_entrada": r["endereco_entrada"], "campos_entrada": r["campos_entrada"],
             "lon": r["lon"], "lat": r["lat"], "score": float(r["score"]) if r["score"] is not None else None,
             "tipo_acerto": r["tipo_acerto"], "erro": r["erro"], "avisos": r["avisos"] or [], "origem": r["origem"]}
            for r in linhas
        ],
    }


@router.patch("/{item_id}/pendentes/{fid}", openapi_extra=EDITAR)
def gravar_manual(item_id: str, fid: int, corpo: CoordenadaManual, request: Request,
                   auth: Auth = autenticado("feicoes.editar")):
    """O arrasto no mapa da tela de revisão chega aqui: grava a coordenada escolhida à mão, com
    `origem = 'manual'` (nunca sobrescreve como se fosse acerto do motor) e tira a linha da lista de
    pendentes."""
    iid = uuid_ok(item_id, "item_inexistente", "camada de geocodificação inexistente")
    with db.db(auth.contexto()) as cur:
        ctx = _item_geocodificacao(cur, iid)
        schema, tabela = ctx["schema"], ctx["tabela"]
        cur.execute(
            f'UPDATE "{schema}"."{tabela}" SET geom = ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), '
            f'  origem = \'manual\', pendente = false, erro = NULL, atualizado_em = now(), atualizado_por = %(uid)s '
            f'WHERE fid = %(fid)s RETURNING fid',
            {"lon": corpo.lon, "lat": corpo.lat, "uid": auth.usuario_id, "fid": fid},
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "ponto_inexistente", "ponto pendente inexistente nesta camada")
        cur.execute(f'SELECT count(*) FILTER (WHERE pendente) AS pendentes, count(*) AS total '
                    f'FROM "{schema}"."{tabela}"')
        contagem = cur.fetchone()
        resumo_novo = dict(ctx["registro"]["resumo"])
        resumo_novo["pendentes"] = contagem["pendentes"]
        resumo_novo["resolvidos"] = contagem["total"] - contagem["pendentes"]
        cur.execute("UPDATE plat.geocodificacao_lote SET resumo = %s WHERE item_id = %s::uuid",
                    (jsonb(resumo_novo), iid))
    return {"fid": fid, "lon": corpo.lon, "lat": corpo.lat, "origem": "manual", "pendentes_restantes":
            contagem["pendentes"]}


@router.post("/{item_id}/regeocodificar", openapi_extra=EDITAR)
def regeocodificar(item_id: str, corpo: RegeocodificarEntrada, auth: Auth = autenticado("feicoes.editar")):
    """Re-roda o motor SÓ nas linhas ainda pendentes (origem ainda 'automatica'): um ponto já corrigido à mão
    (`origem = 'manual'`) nunca é tocado — regra do item ('re-geocodificar só os pendentes')."""
    iid = uuid_ok(item_id, "item_inexistente", "camada de geocodificação inexistente")
    t0 = time.monotonic()
    with db.db(auth.contexto()) as cur:
        ctx = _item_geocodificacao(cur, iid)
        schema, tabela = ctx["schema"], ctx["tabela"]
        limiar_atual = float(ctx["registro"]["limiar_pendente"])
        limiar = corpo.limiar_pendente if corpo.limiar_pendente is not None else limiar_atual
        cur.execute(f'SELECT fid, linha_origem, campos_entrada FROM "{schema}"."{tabela}" '
                    f"WHERE pendente AND origem = 'automatica' ORDER BY fid")
        pendentes_atuais = cur.fetchall()
        atualizados = 0
        for linha in pendentes_atuais:
            resultado = lote.geocodificar_campos(cur, linha["linha_origem"], linha["campos_entrada"],
                                                  limiar_pendente=limiar)
            geom = f"SRID=4326;POINT({resultado.lon} {resultado.lat})" if resultado.lon is not None else None
            cur.execute(
                f'UPDATE "{schema}"."{tabela}" SET '
                "  geom = CASE WHEN %(geom)s IS NULL THEN geom ELSE ST_GeomFromEWKT(%(geom)s) END, "
                "  score = %(score)s, tipo_acerto = %(tipo_acerto)s, cod_municipio = %(cod_municipio)s, "
                "  pendente = %(pendente)s, erro = %(erro)s, avisos = %(avisos)s, atualizado_em = now() "
                "WHERE fid = %(fid)s",
                {"geom": geom, "score": resultado.score, "tipo_acerto": resultado.tipo_acerto,
                 "cod_municipio": resultado.cod_municipio, "pendente": resultado.pendente, "erro": resultado.erro,
                 "avisos": resultado.avisos, "fid": linha["fid"]},
            )
            atualizados += 1
        cur.execute(f'SELECT count(*) FILTER (WHERE pendente) AS pendentes, count(*) AS total '
                    f'FROM "{schema}"."{tabela}"')
        contagem = cur.fetchone()
        resumo_novo = dict(ctx["registro"]["resumo"])
        resumo_novo["pendentes"] = contagem["pendentes"]
        resumo_novo["resolvidos"] = contagem["total"] - contagem["pendentes"]
        cur.execute("UPDATE plat.geocodificacao_lote SET resumo = %s, limiar_pendente = %s WHERE item_id = %s::uuid",
                    (jsonb(resumo_novo), limiar, iid))
    return {"item_id": iid, "reprocessados": atualizados, "pendentes_restantes": contagem["pendentes"],
            "duracao_s": round(time.monotonic() - t0, 3)}
