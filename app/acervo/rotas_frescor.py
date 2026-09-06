"""Rotas de frescor do acervo (item L6-01-h-frescor-verificacao; migração 20260906T1617_acervo_frescor.sql).

Três leituras, todas sobre views da plataforma — `acervo.*` continua só leitura e nenhuma destas rotas escreve
em lugar nenhum:

  `GET /api/acervo/camadas`            camadas do registro com o estado de verificação; `vencida=true` filtra as
                                        que precisam do aviso. É o que a ficha e o mapa consomem.
  `GET /api/acervo/camadas/{id}/verificacoes`  o histórico da camada (as 12 mais recentes que o job mantém).
  `GET /api/acervo/frescor/mudancas`   as contagens que variaram mais de 5 % contra a verificação anterior.
  `GET /api/acervo/frescor/execucoes`  as rodadas do periódico (quando rodou, quanto durou, o que cobriu).

Este router é incluído ANTES de `app/acervo/rotas.py` em `app/main.py`: `/api/acervo/camadas` e
`/api/acervo/frescor/*` casariam com `/api/acervo/{fonte_id}` se a ordem fosse a inversa, e o FastAPI resolve
pela ordem de inclusão.

Regra D17 herdada sem exceção: `plat.v_acervo_camada_frescor` junta `plat.acervo_ficha`, que já filtra fonte sem
licença escrita; e as rotas só devolvem camada com `estado = 'exposta'` quando não se pede o contrário, porque
camada bloqueada ou pendente de licença não é oferecida a ninguém."""

from fastapi import APIRouter, Query

from app import db
from app.acervo.modelos import (
    AcervoCamadaFrescorPagina,
    AcervoExecucaoPagina,
    AcervoMudancaPagina,
    AcervoVerificacaoHistorico,
)
from app.auth.comum import paginacao
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(tags=["acervo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}

CAMPOS_FRESCOR = (
    "acervo_camada_id, fonte_id, schema_nome, tabela, estado, fonte_nome, fonte_dominio, fonte_licenca, "
    "fonte_frescor, proxima_verificacao, verificada_em, contagem_estado, linhas_exatas, linhas_anteriores, "
    "variacao_pct, mudanca_relevante, hash_estado, endpoints_testados, endpoints_mortos, endpoint_morto, "
    "prazo_da_fonte_vencido, nunca_verificada, verificacao_antiga, verificacao_vencida, motivo_vencida"
)


def _iso(r: dict) -> dict:
    """Datas em ISO 8601 e `numeric` em float — o pydantic recusa Decimal em campo float sem isto."""
    j = dict(r)
    for campo in ("verificada_em", "proxima_verificacao", "iniciada_em", "concluida_em", "endpoint_verificado_em"):
        if j.get(campo) is not None:
            j[campo] = j[campo].isoformat()
    if j.get("variacao_pct") is not None:
        j["variacao_pct"] = float(j["variacao_pct"])
    return j


@router.get("/api/acervo/camadas", response_model=AcervoCamadaFrescorPagina, openapi_extra=LER)
def listar_camadas(
    fonte_id: str | None = Query(default=None, max_length=200),
    vencida: bool | None = None,
    estado: str = Query(default="exposta", pattern="^(exposta|bloqueada|pendente_de_licenca|todos)$"),
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    onde, params = ["true"], []
    if estado != "todos":
        onde.append("estado = %s")
        params.append(estado)
    if fonte_id:
        onde.append("fonte_id = %s")
        params.append(fonte_id)
    if vencida is not None:
        onde.append("verificacao_vencida = %s")
        params.append(vencida)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.v_acervo_camada_frescor WHERE {filtro}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT count(*) FILTER (WHERE verificacao_vencida) AS vencidas "
            f"FROM plat.v_acervo_camada_frescor WHERE {filtro}", params
        )
        vencidas = cur.fetchone()["vencidas"]
        cur.execute(
            f"SELECT {CAMPOS_FRESCOR} FROM plat.v_acervo_camada_frescor WHERE {filtro} "
            f"ORDER BY verificacao_vencida DESC, fonte_id, acervo_camada_id LIMIT %s OFFSET %s",
            [*params, lim, desl],
        )
        itens = [_iso(r) for r in cur.fetchall()]
    return {"total": total, "vencidas": vencidas, "itens": itens}


@router.get("/api/acervo/camadas/{acervo_camada_id:path}/verificacoes",
            response_model=AcervoVerificacaoHistorico, openapi_extra=LER)
def historico_camada(acervo_camada_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O identificador de camada é o slug `<fonte_id>/<schema>.<tabela>` (decisão B2 do L6-01-a) e tem barra
    dentro, por isso `:path`. A camada tem de estar na visão de frescor (que já herda o filtro de licença);
    fora dela é 404, indistinguível de inexistente."""
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT {CAMPOS_FRESCOR} FROM plat.v_acervo_camada_frescor WHERE acervo_camada_id = %s",
                    (acervo_camada_id,))
        camada = cur.fetchone()
        if camada is None:
            raise ErroAPI(404, "camada_inexistente", "camada do acervo inexistente")
        cur.execute(
            "SELECT verificada_em, contagem_estado, linhas_exatas, linhas_anteriores, variacao_pct, "
            "mudanca_relevante, hash_estado, hash_valor, duracao_ms, execucao_id "
            "FROM plat.acervo_camada_verificacao WHERE acervo_camada_id = %s "
            "ORDER BY verificada_em DESC, id DESC",
            (acervo_camada_id,),
        )
        verificacoes = [_iso(r) for r in cur.fetchall()]
    return {"camada": _iso(camada), "total": len(verificacoes), "verificacoes": verificacoes}


@router.get("/api/acervo/frescor/mudancas", response_model=AcervoMudancaPagina, openapi_extra=LER)
def listar_mudancas(
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.v_acervo_frescor_mudanca")
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT acervo_camada_id, fonte_id, schema_nome, tabela, verificada_em, linhas_anteriores, "
            "linhas_exatas, variacao_pct, execucao_id FROM plat.v_acervo_frescor_mudanca "
            "ORDER BY verificada_em DESC, abs(variacao_pct) DESC LIMIT %s OFFSET %s",
            (lim, desl),
        )
        itens = [_iso(r) for r in cur.fetchall()]
    return {"total": total, "limiar_pct": 5.0, "itens": itens}


@router.get("/api/acervo/frescor/execucoes", response_model=AcervoExecucaoPagina, openapi_extra=LER)
def listar_execucoes(
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.acervo_frescor_execucao")
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT id, iniciada_em, concluida_em, duracao_ms, camadas_expostas, camadas_verificadas, "
            "camadas_nao_contadas, endpoints_testados, endpoints_responderam, mudancas "
            "FROM plat.acervo_frescor_execucao ORDER BY iniciada_em DESC, id DESC LIMIT %s OFFSET %s",
            (lim, desl),
        )
        itens = [_iso(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}
