"""Rotas de feições e topologia derivada da rede de utilidades (item L4-01-b-topologia-derivada; ADR 0020).

`POST /api/rede/{rede_id}/feicoes/pontos` e `.../linhas` gravam as camadas de rede (normais, editáveis) que a
topologia deriva. `POST /api/rede/{rede_id}/topologia/habilitar` reconstrói o índice inteiro (nunca incremental
nesta passagem — ver docs/rede/TOPOLOGIA.md); `GET .../topologia` devolve o resumo da última construção;
`GET .../topologia/nos` e `.../arestas` listam o resultado (paginação simples, sem filtro espacial ainda).

Mesmo padrão de `rotas.py`: escrita exige `rede.editar`; leitura segue a visibilidade por inquilino (RLS);
construção pesada vai para o threadpool (lição do achado A4 do item L4-01-a)."""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import feicoes, topologia
from app.rede_utilidades.modelos import (
    Feicao,
    FeicaoLinhaEntrada,
    FeicaoPontoEntrada,
    TopologiaResumo,
)

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — topologia"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 2000


def _uuid_ok(valor: str) -> str:
    import uuid as uuid_mod

    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _feicao_json(r: dict) -> dict:
    return {"id": str(r["id"]), "tipo_id": str(r["tipo_id"]), "fase_bitmask": r["fase_bitmask"],
            "atributos": r["atributos"], "criado_em": iso(r["criado_em"])}


@router.post("/{rede_id}/feicoes/pontos", response_model=Feicao, status_code=201, openapi_extra=EDITAR)
def criar_feicao_ponto(rede_id: str, corpo: FeicaoPontoEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = feicoes.criar_ponto(cur, auth.tenant_id, rid, corpo)
        registrar_evento(cur, request, "redes/feicao_criar", "rede", rid,
                         {"tipo": "ponto", "grupo": corpo.grupo, "tipo_codigo": corpo.tipo_codigo})
        return _feicao_json(r)


@router.post("/{rede_id}/feicoes/linhas", response_model=Feicao, status_code=201, openapi_extra=EDITAR)
def criar_feicao_linha(rede_id: str, corpo: FeicaoLinhaEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = feicoes.criar_linha(cur, auth.tenant_id, rid, corpo)
        registrar_evento(cur, request, "redes/feicao_criar", "rede", rid,
                         {"tipo": "linha", "grupo": corpo.grupo, "tipo_codigo": corpo.tipo_codigo})
        return _feicao_json(r)


@router.get("/{rede_id}/feicoes/pontos", openapi_extra=LER)
def listar_feicoes_ponto(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = feicoes.listar_pontos(cur, rid, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": [_feicao_json(r) for r in itens]}


@router.get("/{rede_id}/feicoes/linhas", openapi_extra=LER)
def listar_feicoes_linha(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = feicoes.listar_linhas(cur, rid, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": [_feicao_json(r) for r in itens]}


def _habilitar_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        try:
            resumo = topologia.habilitar(cur, auth.tenant_id, rid, auth.usuario_id)
        except LookupError as e:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e
        except Exception as e:  # noqa: BLE001 — erro do banco vira mensagem legível, nunca 500 cru
            import psycopg2

            if isinstance(e, psycopg2.Error):
                raise auth_comum.erro_do_banco(e) from e
            raise
        registrar_evento(cur, request, "redes/topologia_habilitar", "rede", rid, resumo)
    return resumo


@router.post("/{rede_id}/topologia/habilitar", response_model=TopologiaResumo, status_code=201,
             openapi_extra=EDITAR)
async def habilitar_topologia(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma."""
    rid = _uuid_ok(rede_id)
    resumo = await run_in_threadpool(_habilitar_sincrono, rid, auth, request)
    return {**resumo, "construido_em": iso(resumo["construido_em"])}


@router.get("/{rede_id}/topologia", response_model=TopologiaResumo, openapi_extra=LER)
def ver_resumo_topologia(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT rede_id, tolerancia_m, nos, arestas, nos_orfaos, arestas_sem_no, duracao_ms, construido_em "
            "FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rid,),
        )
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")
        return {
            "rede_id": str(r["rede_id"]), "tolerancia_m": float(r["tolerancia_m"]), "nos": r["nos"],
            "arestas": r["arestas"], "nos_orfaos": r["nos_orfaos"], "arestas_sem_no": r["arestas_sem_no"],
            "duracao_ms": r["duracao_ms"], "construido_em": iso(r["construido_em"]),
        }


@router.get("/{rede_id}/topologia/nos", openapi_extra=LER)
def listar_nos(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT n.id, n.papel, n.tipo_id, n.origem_id, n.terminal_num, ST_X(n.geom) AS lon, "
            "ST_Y(n.geom) AS lat, "
            "(SELECT count(*) FROM plat.rede_topo_aresta a "
            " WHERE a.no_origem_id = n.id OR a.no_destino_id = n.id) AS grau "
            "FROM plat.rede_topo_no n WHERE n.rede_id = %s::uuid ORDER BY n.criado_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "papel": r["papel"], "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
             "origem_id": str(r["origem_id"]) if r["origem_id"] else None, "terminal_num": r["terminal_num"],
             "grau": r["grau"], "lon": r["lon"], "lat": r["lat"]}
            for r in cur.fetchall()
        ]
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/topologia/arestas", openapi_extra=LER)
def listar_arestas(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT id, grupo_id, tipo_id, origem_id, no_origem_id, no_destino_id, comprimento_m, "
            "fase_bitmask, atributos FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid "
            "ORDER BY criado_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "grupo_id": str(r["grupo_id"]), "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
             "origem_id": str(r["origem_id"]), "no_origem_id": str(r["no_origem_id"]) if r["no_origem_id"] else None,
             "no_destino_id": str(r["no_destino_id"]) if r["no_destino_id"] else None,
             "comprimento_m": r["comprimento_m"], "fase_bitmask": r["fase_bitmask"], "atributos": r["atributos"]}
            for r in cur.fetchall()
        ]
        return {"total": len(itens), "itens": itens}
