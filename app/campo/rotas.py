"""Rotas do módulo campo (item L2-07-campo): fila de trabalho, roteiro do dia e visita com foto — portado de
rs-coop/certaja/sig (`app/main.py`, rotas `/api/filas*`, `/api/rotas*`, `/api/visitas*`, `/api/fotos/{nome}`).

Privilégio único `campo.coletar` (já existe na casa desde a migração 003 — perfil `campo` inteiro foi
desenhado para isto) para toda escrita; leitura é `rls:visibilidade` (qualquer sessão válida do inquilino, a
RLS de cada tabela `plat.campo_*` já isola por `tenant_id`). Sem escopo de token dedicado ainda (nenhum
`campo:*` no vocabulário fechado de `app/auth/escopos.py`): token de serviço precisa de `admin:inquilino`
(o padrão de `autenticado()` quando `escopo_token` não é passado)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db, objetos
from app.auth.sessao import Auth, autenticado, iso
from app.campo import fotos, servico
from app.campo.modelos import (
    FilaAlvosAdicionar,
    FilaCriar,
    FilaOrdem,
    RoteiroCriar,
    VisitaCriar,
    VisitaFotoEntrada,
)
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/campo", tags=["campo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "campo.coletar"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


def _foto_url(chave: str) -> str:
    return objetos.url_assinada(chave, 3600)


def _fila_json(f: dict, extra: dict | None = None) -> dict:
    j = {
        "id": str(f["id"]), "titulo": f["titulo"], "camada_id": str(f["camada_id"]), "status": f["status"],
        "criado_em": iso(f.get("criado_em")), "atualizado_em": iso(f.get("atualizado_em")),
    }
    if extra:
        j.update(extra)
    return j


def _alvo_json(a: dict) -> dict:
    return {
        "id": str(a["id"]), "globalid": str(a["globalid"]), "ordem": a["ordem"], "nota": a["nota"],
        "status": a["status"],
    }


def _visita_json(v: dict) -> dict:
    fotos_json = [
        {**{k: f[k] for k in ("id", "sha256", "bytes", "largura", "altura") if k in f},
         "url": _foto_url(f["chave"])}
        for f in (v.get("fotos") or [])
    ]
    return {
        "id": str(v["id"]), "cliente_uuid": str(v["cliente_uuid"]) if v.get("cliente_uuid") else None,
        "fila_id": str(v["fila_id"]) if v.get("fila_id") else None,
        "alvo_id": str(v["alvo_id"]) if v.get("alvo_id") else None,
        "roteiro_id": str(v["roteiro_id"]) if v.get("roteiro_id") else None,
        "camada_id": str(v["camada_id"]), "globalid": str(v["globalid"]), "status": v["status"],
        "texto": v.get("texto"), "usuario_id": v.get("usuario_id"), "usuario_login": v.get("usuario_login"),
        "lat": v.get("lat"), "lon": v.get("lon"), "gps_acc_m": v.get("gps_acc_m"),
        "capturado_em": v.get("capturado_em"), "recebido_em": iso(v.get("recebido_em")),
        "dados": v.get("dados") or {}, "fotos": fotos_json,
    }


# ---------------------------------------------------------------------- camada de origem (apoio da tela de criação)
@router.get("/camadas/{camada_id}/globalids", openapi_extra=LER)
def camada_globalids(camada_id: str, limite: int = 200, auth: Auth = autenticado()) -> dict:
    """Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo."""
    cid = uuid_ok(camada_id, "item_inexistente", "item de camada inexistente")
    limite = max(1, min(limite, 1000))
    with db.db(auth.contexto()) as cur:
        _item, dados = servico.camada_ou_404(cur, cid)
        return {"feicoes": servico.listar_globalids(cur, dados, limite)}


# ---------------------------------------------------------------------- fila
@router.post("/filas", status_code=201, openapi_extra=ESCREVER)
def criar_fila(corpo: FilaCriar, request: Request, auth: Auth = autenticado("campo.coletar")):
    camada_id = uuid_ok(corpo.camada_id, "item_inexistente", "item de camada inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.fila_criar(cur, auth, corpo.titulo, camada_id, corpo.globalids)
        registrar_evento(cur, request, "campo/fila_criar", "campo_fila", r["id"], {
            "camada_id": camada_id, "adicionados": r["adicionados"], "ignorados": len(r["ignorados"]),
        })
    return r


@router.get("/filas", openapi_extra=LER)
def listar_filas(auth: Auth = autenticado()) -> dict:
    with db.db(auth.contexto()) as cur:
        linhas = servico.filas_listar(cur)
    return {"filas": [
        _fila_json(f, {"n_alvos": f["n_alvos"], "n_visitados": f["n_visitados"], "n_roteiros": f["n_roteiros"]})
        for f in linhas
    ]}


@router.get("/filas/{fila_id}", openapi_extra=LER)
def ver_fila(fila_id: str, auth: Auth = autenticado()) -> dict:
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        alvos = servico.fila_alvos_listar(cur, fid)
        roteiros = servico.roteiros_listar(cur, fid)
    return {
        "fila": _fila_json(f), "alvos": [_alvo_json(a) for a in alvos],
        "roteiros": [
            {"id": str(r["id"]), "titulo": r["titulo"], "motor": r["motor"], "n_paradas": r["n_paradas"],
             "distancia_m": r["distancia_m"], "duracao_s": r["duracao_s"], "criado_em": iso(r["criado_em"])}
            for r in roteiros
        ],
    }


@router.get("/filas/{fila_id}/alvos.geojson", openapi_extra=LER)
def alvos_geojson(fila_id: str, auth: Auth = autenticado()) -> JSONResponse:
    """Camada de alvos da fila (item 4 do pedido: `GET /api/rede/{id}/feicoes/*.geojson` é o molde já usado
    pela rede de utilidades; aqui a MESMA forma para os alvos de uma fila de campo, com o estado de visita em
    cada feição para colorir no mapa)."""
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        alvos = servico.fila_alvos_listar(cur, fid)
        _item, dados_camada = servico.camada_ou_404(cur, str(f["camada_id"]))
        fc = servico.feicoes_geojson(cur, dados_camada, [str(a["globalid"]) for a in alvos])
    por_globalid = {str(a["globalid"]): a for a in alvos}
    for feat in fc["features"]:
        a = por_globalid.get(feat["properties"]["globalid"])
        if a:
            feat["properties"].update({"alvo_id": str(a["id"]), "ordem": a["ordem"], "status": a["status"]})
    return JSONResponse(fc, headers=SEM_CACHE)


@router.post("/filas/{fila_id}/alvos", status_code=201, openapi_extra=ESCREVER)
def adicionar_alvos(fila_id: str, corpo: FilaAlvosAdicionar, request: Request,
                    auth: Auth = autenticado("campo.coletar")):
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        f = servico.fila_ou_404(cur, fid)
        _item, dados_camada = servico.camada_ou_404(cur, str(f["camada_id"]))
        adicionados, ignorados = servico.fila_alvos_adicionar(cur, auth, fid, dados_camada, corpo.globalids)
        registrar_evento(cur, request, "campo/fila_alvos_adicionar", "campo_fila", fid, {
            "adicionados": adicionados, "ignorados": len(ignorados),
        })
    return {"adicionados": adicionados, "ignorados": ignorados}


@router.put("/filas/{fila_id}/ordem", openapi_extra=ESCREVER)
def reordenar_fila(fila_id: str, corpo: FilaOrdem, request: Request, auth: Auth = autenticado("campo.coletar")):
    fid = uuid_ok(fila_id, "fila_inexistente", "fila inexistente")
    with db.db(auth.contexto()) as cur:
        servico.fila_ou_404(cur, fid)
        n = servico.fila_ordem_atualizar(cur, fid, [uuid_ok(a) for a in corpo.alvo_ids])
        registrar_evento(cur, request, "campo/fila_ordem_atualizar", "campo_fila", fid, {"reordenados": n})
    return {"reordenados": n}


# ---------------------------------------------------------------------- roteiro
@router.post("/roteiros", status_code=201, openapi_extra=ESCREVER)
def criar_roteiro(corpo: RoteiroCriar, request: Request, auth: Auth = autenticado("campo.coletar")):
    fid = uuid_ok(corpo.fila_id, "fila_inexistente", "fila inexistente")
    origem = {"lon": corpo.origem.lon, "lat": corpo.origem.lat}
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_criar(cur, auth, fid, origem, corpo.titulo, [uuid_ok(a) for a in corpo.alvo_ids],
                                  corpo.maximo)
        registrar_evento(cur, request, "campo/roteiro_criar", "campo_roteiro", r["id"], {
            "fila_id": fid, "motor": r["motor"], "n_paradas": r["n_paradas"],
        })
    return {**r, "criado_em": iso(r["criado_em"])}


@router.get("/roteiros", openapi_extra=LER)
def listar_roteiros(fila_id: str | None = None, auth: Auth = autenticado()) -> dict:
    fid = uuid_ok(fila_id) if fila_id else None
    with db.db(auth.contexto()) as cur:
        linhas = servico.roteiros_listar(cur, fid)
    return {"roteiros": [
        {"id": str(r["id"]), "fila_id": str(r["fila_id"]), "titulo": r["titulo"], "motor": r["motor"],
         "distancia_m": r["distancia_m"], "duracao_s": r["duracao_s"], "n_paradas": r["n_paradas"],
         "criado_em": iso(r["criado_em"])}
        for r in linhas
    ]}


@router.get("/roteiros/{roteiro_id}", openapi_extra=LER)
def ver_roteiro(roteiro_id: str, auth: Auth = autenticado()) -> dict:
    rid = uuid_ok(roteiro_id, "roteiro_inexistente", "roteiro inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_ou_404(cur, rid)
        paradas = servico.roteiro_paradas(cur, rid)
    return {
        "id": str(r["id"]), "fila_id": str(r["fila_id"]), "titulo": r["titulo"],
        "origem": {"lon": r["origem_lon"], "lat": r["origem_lat"]}, "motor": r["motor"],
        "distancia_m": r["distancia_m"], "duracao_s": r["duracao_s"], "aviso": r["aviso"],
        "criado_em": iso(r["criado_em"]),
        "paradas": [
            {"ordem": p["ordem"], "alvo_id": str(p["alvo_id"]), "globalid": str(p["globalid"]),
             "status": p["status"], "nota": p["nota"], "trecho_m": p["trecho_m"], "trecho_s": p["trecho_s"],
             "visita_id": str(p["visita_id"]) if p["visita_id"] else None}
            for p in paradas
        ],
    }


@router.get("/roteiros/{roteiro_id}/trajeto.geojson", openapi_extra=LER)
def roteiro_trajeto_geojson(roteiro_id: str, auth: Auth = autenticado()) -> JSONResponse:
    rid = uuid_ok(roteiro_id, "roteiro_inexistente", "roteiro inexistente")
    with db.db(auth.contexto()) as cur:
        r = servico.roteiro_ou_404(cur, rid)
    feature = {
        "type": "Feature", "id": str(r["id"]),
        "properties": {"titulo": r["titulo"], "motor": r["motor"], "distancia_m": r["distancia_m"],
                       "duracao_s": r["duracao_s"], "aviso": r["aviso"]},
        "geometry": r["geometria"],
    }
    return JSONResponse({"type": "FeatureCollection", "features": [feature]}, headers=SEM_CACHE)


# ---------------------------------------------------------------------- visita
@router.post("/visitas", status_code=201, openapi_extra=ESCREVER)
def criar_visita(corpo: VisitaCriar, request: Request, auth: Auth = autenticado("campo.coletar")):
    # existência de alvo/fila/roteiro é conferida aqui (404 antes de tocar a tabela de visita); a feição em si
    # NUNCA é exigida existir ainda na camada — visitar algo que já sumiu da camada continua sendo um FATO
    if corpo.fila_id:
        with db.db(auth.contexto()) as cur:
            servico.fila_ou_404(cur, uuid_ok(corpo.fila_id))
    if corpo.alvo_id:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT 1 FROM plat.campo_alvo WHERE id = %s::uuid", (uuid_ok(corpo.alvo_id),))
            if cur.fetchone() is None:
                raise ErroAPI(404, "alvo_inexistente", "alvo inexistente")
    with db.db(auth.contexto()) as cur:
        servico.camada_ou_404(cur, uuid_ok(corpo.camada_id, "item_inexistente", "item de camada inexistente"))
        visita, criada = servico.visita_criar(cur, auth, corpo)
        if criada:
            registrar_evento(cur, request, "campo/visita_registrar", "campo_visita", str(visita["id"]), {
                "status": corpo.status, "fila_id": corpo.fila_id, "alvo_id": corpo.alvo_id,
            })
    return JSONResponse(
        {**_visita_json(visita), "ja_existia": not criada}, status_code=201 if criada else 200,
    )


@router.get("/visitas", openapi_extra=LER)
def listar_visitas(fila_id: str | None = None, alvo_id: str | None = None, roteiro_id: str | None = None,
                   limite: int = 500, auth: Auth = autenticado()) -> dict:
    with db.db(auth.contexto()) as cur:
        linhas = servico.visitas_listar(
            cur, fila_id=uuid_ok(fila_id) if fila_id else None, alvo_id=uuid_ok(alvo_id) if alvo_id else None,
            roteiro_id=uuid_ok(roteiro_id) if roteiro_id else None, limite=limite,
        )
    return {"visitas": [
        {"id": str(v["id"]), "fila_id": str(v["fila_id"]) if v["fila_id"] else None,
         "alvo_id": str(v["alvo_id"]) if v["alvo_id"] else None, "camada_id": str(v["camada_id"]),
         "globalid": str(v["globalid"]), "status": v["status"], "texto": v["texto"],
         "usuario_login": v["usuario_login"], "lat": v["lat"], "lon": v["lon"],
         "capturado_em": v["capturado_em"], "recebido_em": iso(v["recebido_em"]), "n_fotos": v["n_fotos"]}
        for v in linhas
    ]}


@router.get("/visitas/{visita_id}", openapi_extra=LER)
def ver_visita(visita_id: str, auth: Auth = autenticado()) -> dict:
    vid = uuid_ok(visita_id, "visita_inexistente", "visita inexistente")
    with db.db(auth.contexto()) as cur:
        v = servico.visita_ou_404(cur, vid)
    return _visita_json(v)


@router.post("/visitas/{visita_id}/fotos", status_code=201, openapi_extra=ESCREVER)
def enviar_foto(visita_id: str, corpo: VisitaFotoEntrada, request: Request,
                auth: Auth = autenticado("campo.coletar")):
    vid = uuid_ok(visita_id, "visita_inexistente", "visita inexistente")
    dados = fotos.decodificar_base64(corpo.conteudo)
    with db.db(auth.contexto()) as cur:
        servico.visita_ou_404(cur, vid)
        f = servico.visita_foto_guardar(cur, auth, vid, dados)
        registrar_evento(cur, request, "campo/visita_foto_enviar", "campo_visita", vid, {
            "foto_id": f["id"], "bytes": f["bytes"],
        })
    return {**{k: v for k, v in f.items() if k != "chave"}, "url": _foto_url(f["chave"])}


__all__ = ["router"]
