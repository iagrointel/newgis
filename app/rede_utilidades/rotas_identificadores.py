"""Rotas de identidade e numeração de ativos da rede de utilidades
(item L4-28-identificadores-e-numeracao; ADR docs/adr/20260906T2121-rede-identificadores.md).

`/api/rede/{rede_id}/ativos` cria e lista identidades de ativo: global_id (uuid) estável + número
automático por tipo + código externo do cliente único por rede. `/api/rede/{rede_id}/faixas` reserva
blocos de numeração por usuário para criação desconectada (o conceito dos "unit identifiers" da Esri;
a fachada compatível está em `rotas_esri_un.py`). Renomear o código externo mantém o global_id e grava
histórico em `/ativos/{global_id}/renomeacoes`.

Escrita exige `rede.editar` (o mesmo privilégio do pacote de ativos); leitura segue a RLS do inquilino.
Segue a convenção do módulo (`rotas.py`): caminhos em `/api/rede/...`, sem prefixo de versão."""

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import identificadores as ident
from app.rede_utilidades.modelos_identificadores import (
    Ativo,
    AtivoEntrada,
    AtivoPagina,
    Faixa,
    FaixaEntrada,
    FaixaPagina,
    RenomeacaoEntrada,
    RenomeacaoLista,
)

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — identificadores"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}

SQL_ATIVO = (
    "SELECT a.global_id, a.rede_id, a.tipo_id, a.numero, a.codigo_externo, a.criado_em, a.atualizado_em, "
    "a.criado_por, t.chave AS tipo_chave, u.login AS criador_login, u.nome AS criador_nome "
    "FROM plat.rede_ativo a "
    "JOIN plat.rede_tipo t ON t.id = a.tipo_id "
    "JOIN plat.usuario u ON u.id = a.criado_por"
)


def _ativo_json(r: dict) -> dict:
    return {
        "global_id": str(r["global_id"]),
        "rede_id": str(r["rede_id"]),
        "tipo_id": str(r["tipo_id"]),
        "tipo_chave": r["tipo_chave"],
        "numero": r["numero"],
        "codigo": f"{r['tipo_chave']}-{r['numero']}",
        "codigo_externo": r["codigo_externo"],
        "criado_por": {"id": r["criado_por"], "login": r["criador_login"], "nome": r["criador_nome"]},
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _carregar_ativo(cur, rede_id: str, global_id: str) -> dict:
    cur.execute(SQL_ATIVO + " WHERE a.global_id = %s::uuid AND a.rede_id = %s::uuid", (global_id, rede_id))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "ativo_inexistente", "ativo inexistente nesta rede")
    return r


@router.post("/{rede_id}/ativos", response_model=Ativo, status_code=201, openapi_extra=EDITAR)
def criar_ativo(rede_id: str, corpo: AtivoEntrada, request: Request, auth: Auth = autenticado("rede.editar")):
    """Cria a identidade do ativo. Sem `numero`: o servidor aloca o próximo do tipo (criação conectada).
    Com `numero`: sincronização do que foi criado offline — o número tem de estar numa faixa aberta do
    próprio usuário. `codigo_externo` duplicado na rede = 409."""
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    tid = ident.uuid_ok(corpo.tipo_id, "tipo_inexistente")
    codigo_externo = corpo.codigo_externo.strip() if corpo.codigo_externo else None
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        ident.tipo_da_rede(cur, rid, tid)
        try:
            r = ident.criar_ativo(cur, auth.tenant_id, rid, tid, auth.usuario_id,
                                  codigo_externo, corpo.numero)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        gid = str(r["global_id"])
        registrar_evento(cur, request, "redes/ativos/criar", "rede_ativo", gid,
                         {"rede_id": rid, "tipo_id": tid, "numero": r["numero"],
                          "codigo_externo": codigo_externo, "desconectado": corpo.numero is not None})
        return _ativo_json(_carregar_ativo(cur, rid, gid))


@router.get("/{rede_id}/ativos", response_model=AtivoPagina, openapi_extra=LER)
def listar_ativos(rede_id: str, tipo_id: str | None = None, codigo_externo: str | None = None,
                  limite: int = 200, deslocamento: int = 0,
                  auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    if not 1 <= limite <= 1000 or deslocamento < 0:
        raise ErroAPI(422, "paginacao_invalida", "limite entre 1 e 1000 e deslocamento >= 0")
    filtros, params = "", [rid]
    if tipo_id:
        filtros += " AND a.tipo_id = %s::uuid"
        params.append(ident.uuid_ok(tipo_id, "tipo_inexistente"))
    if codigo_externo:
        filtros += " AND a.codigo_externo = %s"
        params.append(codigo_externo)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(f"SELECT count(*) AS n FROM plat.rede_ativo a WHERE a.rede_id = %s::uuid{filtros}", params)
        total = cur.fetchone()["n"]
        cur.execute(SQL_ATIVO + f" WHERE a.rede_id = %s::uuid{filtros} ORDER BY a.numero "
                                "LIMIT %s OFFSET %s", [*params, limite, deslocamento])
        return {"total": total, "itens": [_ativo_json(r) for r in cur.fetchall()]}


@router.get("/{rede_id}/ativos/{global_id}", response_model=Ativo, openapi_extra=LER)
def ver_ativo(rede_id: str, global_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _ativo_json(_carregar_ativo(cur, ident.uuid_ok(rede_id, "rede_inexistente"),
                                           ident.uuid_ok(global_id, "ativo_inexistente")))


@router.patch("/{rede_id}/ativos/{global_id}", response_model=Ativo, openapi_extra=EDITAR)
def renomear_ativo(rede_id: str, global_id: str, corpo: RenomeacaoEntrada, request: Request,
                   auth: Auth = autenticado("rede.editar")):
    """Renomeia o código externo. O global_id nunca muda; cada troca grava histórico. Trocar pelo MESMO
    código é idempotente (200 sem histórico)."""
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    gid = ident.uuid_ok(global_id, "ativo_inexistente")
    novo = corpo.codigo_externo.strip()
    with db.db(auth.contexto()) as cur:
        try:
            r = ident.renomear(cur, auth.tenant_id, rid, gid, novo, auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        if r["mudou"]:
            registrar_evento(cur, request, "redes/ativos/renomear", "rede_ativo", gid,
                             {"rede_id": rid, "anterior": r["anterior"], "novo": novo})
        return _ativo_json(_carregar_ativo(cur, rid, gid))


@router.get("/{rede_id}/ativos/{global_id}/renomeacoes", response_model=RenomeacaoLista, openapi_extra=LER)
def historico_renomeacoes(rede_id: str, global_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    gid = ident.uuid_ok(global_id, "ativo_inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar_ativo(cur, rid, gid)
        cur.execute(
            "SELECT h.codigo_externo_anterior, h.codigo_externo_novo, h.renomeado_em, "
            "h.renomeado_por, u.login AS autor_login, u.nome AS autor_nome "
            "FROM plat.rede_ativo_renomeacao h JOIN plat.usuario u ON u.id = h.renomeado_por "
            "WHERE h.ativo_global_id = %s::uuid ORDER BY h.id",
            (gid,),
        )
        itens = [{
            "codigo_externo_anterior": r["codigo_externo_anterior"],
            "codigo_externo_novo": r["codigo_externo_novo"],
            "renomeado_por": {"id": r["renomeado_por"], "login": r["autor_login"], "nome": r["autor_nome"]},
            "renomeado_em": iso(r["renomeado_em"]),
        } for r in cur.fetchall()]
        return {"total": len(itens), "itens": itens}


@router.post("/{rede_id}/faixas", response_model=Faixa, status_code=201, openapi_extra=EDITAR)
def reservar_faixa(rede_id: str, corpo: FaixaEntrada, request: Request, auth: Auth = autenticado("rede.editar")):
    """Reserva o próximo bloco livre de `quantidade` números do tipo para o usuário da sessão. Duas
    reservas concorrentes recebem blocos disjuntos (alocação atômica no contador do tipo)."""
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    tid = ident.uuid_ok(corpo.tipo_id, "tipo_inexistente")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        ident.tipo_da_rede(cur, rid, tid)
        try:
            r = ident.reservar_faixa(cur, auth.tenant_id, rid, tid, auth.usuario_id, corpo.quantidade)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/faixas/reservar", "rede_faixa", str(r["id"]),
                         {"rede_id": rid, "tipo_id": tid, "inicio": r["inicio"], "fim": r["fim"]})
        r = {**r, "liberada_em": None, "tipo_id": tid, "usuario_id": auth.usuario_id}
        return ident.faixa_json(r, auth.login)


@router.get("/{rede_id}/faixas", response_model=FaixaPagina, openapi_extra=LER)
def listar_faixas(rede_id: str, tipo_id: str | None = None, minhas: bool = False,
                  auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    filtros, params = "", [rid]
    if tipo_id:
        filtros += " AND f.tipo_id = %s::uuid"
        params.append(ident.uuid_ok(tipo_id, "tipo_inexistente"))
    if minhas:
        filtros += " AND f.usuario_id = %s"
        params.append(auth.usuario_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(f"SELECT count(*) AS n FROM plat.rede_faixa f WHERE f.rede_id = %s::uuid{filtros}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT f.id, f.tipo_id, f.inicio, f.fim, f.consumidos, f.criado_em, f.liberada_em, "
            "f.usuario_id, u.login AS dono_login "
            "FROM plat.rede_faixa f JOIN plat.usuario u ON u.id = f.usuario_id "
            f"WHERE f.rede_id = %s::uuid{filtros} ORDER BY f.inicio",
            params,
        )
        return {"total": total,
                "itens": [ident.faixa_json(r, r["dono_login"]) for r in cur.fetchall()]}


@router.delete("/{rede_id}/faixas/{faixa_id}", status_code=204, openapi_extra=EDITAR)
def liberar_faixa(rede_id: str, faixa_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Libera a faixa antes de esgotada (só o dono da faixa ou um admin do inquilino). O que sobrou de
    número NÃO volta ao contador — número entregue nunca é reutilizado."""
    rid = ident.uuid_ok(rede_id, "rede_inexistente")
    fid = ident.uuid_ok(faixa_id, "faixa_inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, usuario_id, inicio, fim, consumidos, liberada_em FROM plat.rede_faixa "
            "WHERE id = %s::uuid AND rede_id = %s::uuid FOR UPDATE",
            (fid, rid),
        )
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "faixa_inexistente", "faixa inexistente nesta rede")
        if r["liberada_em"] is not None:
            return Response(status_code=204)  # idempotente: já estava liberada
        if r["usuario_id"] != auth.usuario_id and auth.perfil != "admin" and not auth.superadmin:
            raise ErroAPI(403, "faixa_de_outro_usuario",
                          "só o dono da faixa ou um admin do inquilino libera a faixa")
        cur.execute("UPDATE plat.rede_faixa SET liberada_em = now() WHERE id = %s::uuid", (fid,))
        registrar_evento(cur, request, "redes/faixas/liberar", "rede_faixa", fid,
                         {"rede_id": rid, "inicio": r["inicio"], "fim": r["fim"],
                          "consumidos": r["consumidos"]})
    return Response(status_code=204)
