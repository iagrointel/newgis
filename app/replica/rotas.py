"""Rotas de réplica (item L2-13-b): criar (job que empacota), listar, ler, baixar o pacote, sincronizar e
apagar. Privilégio: `campo.coletar` — trabalho desconectado é a mesma permissão da PWA de campo, e o perfil
`campo` já a tem. A sincronização, que ESCREVE feição, exige ainda `feicoes.editar` ou `feicoes.editar_total`,
resolvido em dependência (antes do corpo, ADR 0002 seção 5) como em app/edicao/rotas.py."""

import psycopg2
from fastapi import APIRouter, Depends, Request, Response

from app import db, objetos
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.erros import ErroAPI
from app.jobs import servico as jobs
from app.jobs.contexto import sessao_de
from app.replica import servico
from app.replica.modelos import ReplicaEntrada, SincronizarEntrada, SincronizarSaida

router = APIRouter(tags=["replicas"])
CAMPO = {"x-auth": "S/T", "x-privilegio": "campo.coletar"}


def _auth_campo(auth: Auth = autenticado("campo.coletar", escopo_token="camada:ler")) -> Auth:  # noqa: B008
    return auth


def _auth_sincronizar(auth: Auth = autenticado("campo.coletar", escopo_token="camada:editar")) -> Auth:  # noqa: B008
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "sincronizar réplica escreve feição: exige feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )
    return auth


@router.post("/api/replicas", status_code=202, openapi_extra=CAMPO)
def criar_replica(corpo: ReplicaEntrada, request: Request, auth: Auth = Depends(_auth_campo)) -> dict:
    try:
        with db.db(auth.contexto()) as cur:
            replica = servico.criar(cur, request, auth, corpo)
            camadas = servico._camadas_da_replica(cur, replica)
            saida = servico.serializar(replica, camadas)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    # o job fica FORA da transação da criação de propósito: ele é criado depois de a réplica existir, senão
    # o worker pode pegá-lo antes do commit e não achar a réplica
    job = jobs.criar(sessao_de(auth), "replicas.criar", {"replica_id": saida["id"]})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.replica SET job_id = %s::uuid WHERE id = %s::uuid", (job["id"], saida["id"]))
    saida["job_id"] = job["id"]
    return saida


@router.get("/api/replicas", openapi_extra=CAMPO)
def listar_replicas(auth: Auth = Depends(_auth_campo)) -> list[dict]:
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        return servico.listar(cur, auth)


@router.get("/api/replicas/{id}", openapi_extra=CAMPO)
def obter_replica(id: str, auth: Auth = Depends(_auth_campo)) -> dict:
    iid = comum.uuid_ok(id, "replica_inexistente", "réplica inexistente")
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        replica = servico._replica_ou_404(cur, iid)
        servico._exigir_dono(auth, replica)
        return servico.serializar(replica, servico._camadas_da_replica(cur, replica))


@router.get("/api/replicas/{id}/pacote", openapi_extra=CAMPO)
def baixar_pacote(id: str, auth: Auth = Depends(_auth_campo)) -> Response:
    iid = comum.uuid_ok(id, "replica_inexistente", "réplica inexistente")
    with db.db(auth.contexto(), somente_leitura=True) as cur:
        replica = servico._replica_ou_404(cur, iid)
        servico._exigir_dono(auth, replica)
    if replica["estado"] != "pronta" or not replica.get("pacote_chave"):
        raise ErroAPI(409, "replica_nao_pronta", f"a réplica está em {replica['estado']}; o pacote ainda não existe",
                      {"estado": replica["estado"], "erro": replica.get("erro")})
    conteudo = objetos.ler(replica["pacote_chave"])
    nome = f"replica-{iid}.gpkg"
    return Response(
        content=conteudo, media_type=servico.CONTENT_TYPE,
        headers={"content-disposition": f'attachment; filename="{nome}"',
                 "x-plat-sha256": replica["pacote_sha256"] or ""},
    )


@router.post("/api/replicas/{id}/sincronizar", response_model=SincronizarSaida,
             openapi_extra={"x-auth": "S/T", "x-privilegio": "campo.coletar"})
def sincronizar_replica(
    id: str, corpo: SincronizarEntrada, request: Request, auth: Auth = Depends(_auth_sincronizar)
) -> SincronizarSaida:
    iid = comum.uuid_ok(id, "replica_inexistente", "réplica inexistente")
    esc.exigir_escopo(auth, "camada:editar")
    try:
        with db.db(auth.contexto()) as cur:
            return servico.sincronizar(cur, request, auth, iid, corpo)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.delete("/api/replicas/{id}", status_code=204, openapi_extra=CAMPO)
def apagar_replica(id: str, request: Request, auth: Auth = Depends(_auth_campo)) -> Response:
    iid = comum.uuid_ok(id, "replica_inexistente", "réplica inexistente")
    with db.db(auth.contexto()) as cur:
        servico.apagar(cur, request, auth, iid)
    return Response(status_code=204)
