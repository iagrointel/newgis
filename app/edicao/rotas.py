"""Rota `POST /api/camadas/{id}/edicoes` (item L2-03-a): única porta de escrita de feição para navegador, PWA,
FeatureServer (L2-04-d) e OGC (L2-04-g). Privilégio (`feicoes.editar` OU `feicoes.editar_total`) é resolvido
DENTRO de uma dependência (`_auth_editor`, não no corpo da função) para rodar antes da validação do corpo pelo
pydantic — mesma ordem do ADR 0002 seção 5 que `app.auth.sessao.autenticado` já aplica para um privilégio só;
aqui são dois em OU, então a checagem é feita à mão dentro de outra dependência (ver
`tests/api/test_privilegios_matriz.py`, que chama a rota sem NENHUM dos dois e exige 403 antes do corpo)."""

import psycopg2
from fastapi import APIRouter, Depends, Request, Response

from app import db, limites
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.edicao import anexos, combinar, historico, lote
from app.edicao.modelos import (
    AnexoEntrada,
    DivisaoEntrada,
    EdicoesEntrada,
    EdicoesSaida,
    LoteEntrada,
    LoteSaida,
    RestaurarSaida,
    UniaoEntrada,
)
from app.edicao.servico import aplicar_edicoes, obter_feicao
from app.erros import ErroAPI

router = APIRouter(tags=["edicao"])
EDITAR = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}


def _auth_editor(auth: Auth = autenticado(escopo_token="camada:editar")) -> Auth:  # noqa: B008
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )
    return auth


@router.post("/api/camadas/{id}/edicoes", response_model=EdicoesSaida, openapi_extra=EDITAR)
def editar_feicoes(
    id: str, corpo: EdicoesEntrada, request: Request, auth: Auth = Depends(_auth_editor)
) -> EdicoesSaida:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return aplicar_edicoes(cur, request, auth, iid, corpo)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.post("/api/camadas/{id}/lote", response_model=LoteSaida, openapi_extra=EDITAR,
             responses={202: {"model": LoteSaida}})
def editar_em_lote(
    id: str, corpo: LoteEntrada, request: Request, response: Response, auth: Auth = Depends(_auth_editor)
) -> LoteSaida:
    """Edição em lote (item L2-03-f): pré-visualização (`previa`), execução síncrona até LOTE_SINCRONO_MAX feições
    ou job `camadas.lote` acima disso (202 com `job_id`; acompanhar em GET /api/jobs/{id})."""
    from app.jobs import servico as jobs
    from app.jobs.contexto import sessao_de

    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    ator = lote.ator_de(auth)
    try:
        with db.db(auth.contexto()) as cur:
            plano = lote.planejar(cur, iid, corpo, ator)
            if corpo.previa:
                return lote.previa(cur, plano, corpo, ator)
            if len(plano.fids) > limites.LOTE_SINCRONO_MAX:
                job = jobs.criar(sessao_de(auth), "camadas.lote",
                                 {"camada_id": iid, "corpo": corpo.model_dump(), "editar_total": ator.editar_total})
                comum.registrar_evento(cur, request, "camadas/lote", "item", iid,
                                       {"operacao": corpo.operacao, "execucao": "job", "total": len(plano.fids),
                                        "job_id": job["id"]})
                response.status_code = 202
                return LoteSaida(execucao="job", operacao=corpo.operacao, total=len(plano.fids), job_id=str(job["id"]),
                                 avisos=list(plano.avisos), traducao=plano.traducao,
                                 traducao_motivo=plano.traducao_motivo)
            saida = lote.executar(cur, plano, corpo, ator)
            lote.registrar_efeitos(cur, plano, saida, iid,
                                   lambda tipo, props: comum.registrar_evento(cur, request, tipo, "item", iid, props))
            return saida
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/feicoes/{globalid}", openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def obter_feicao_rota(id: str, globalid: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> dict:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        return obter_feicao(cur, iid, globalid)

LER_HISTORICO = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


@router.get("/api/camadas/{id}/feicoes/{globalid}/historico", openapi_extra=LER_HISTORICO)
def listar_historico(id: str, globalid: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> list[dict]:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        return historico.listar(cur, iid, globalid)


@router.post(
    "/api/camadas/{id}/feicoes/{globalid}/historico/{historico_id}/restaurar",
    response_model=RestaurarSaida,
    openapi_extra=EDITAR,
)
def restaurar_feicao(
    id: str, globalid: str, historico_id: int, request: Request, auth: Auth = Depends(_auth_editor)
) -> RestaurarSaida:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return historico.restaurar(cur, auth, request, iid, globalid, historico_id)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/feicoes/{globalid}/anexos", openapi_extra=LER_HISTORICO)
def listar_anexos(id: str, globalid: str, auth: Auth = autenticado(escopo_token="camada:ler")) -> list[dict]:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        return anexos.listar(cur, iid, globalid)


@router.post("/api/camadas/{id}/feicoes/{globalid}/anexos", status_code=201, openapi_extra=EDITAR)
def enviar_anexo(
    id: str, globalid: str, corpo: AnexoEntrada, request: Request, auth: Auth = Depends(_auth_editor)
) -> dict:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return anexos.enviar(cur, auth, request, iid, globalid, corpo.nome, corpo.content_type, corpo.conteudo)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get("/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}", openapi_extra=LER_HISTORICO)
def baixar_anexo(id: str, globalid: str, anexo_id: str, auth: Auth = autenticado(escopo_token="camada:ler")):
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    anexo_id = comum.uuid_ok(anexo_id, "anexo_inexistente", "anexo inexistente")
    esc.exigir_escopo(auth, "camada:ler", iid)
    with db.db(auth.contexto()) as cur:
        dados, content_type, nome = anexos.baixar(cur, iid, globalid, anexo_id)
    return Response(
        content=dados, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.delete(
    "/api/camadas/{id}/feicoes/{globalid}/anexos/{anexo_id}",
    status_code=204, response_class=Response, openapi_extra=EDITAR,
)
def apagar_anexo(
    id: str, globalid: str, anexo_id: str, request: Request, auth: Auth = Depends(_auth_editor)
) -> Response:
    iid = comum.uuid_ok(id)
    globalid = comum.uuid_ok(globalid, "feicao_inexistente", "feição inexistente nesta camada")
    anexo_id = comum.uuid_ok(anexo_id, "anexo_inexistente", "anexo inexistente")
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            anexos.apagar(cur, auth, request, iid, globalid, anexo_id)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return Response(status_code=204)


@router.post("/api/camadas/{id}/feicoes/unir", openapi_extra=EDITAR)
def unir_feicoes(id: str, corpo: UniaoEntrada, request: Request, auth: Auth = Depends(_auth_editor)) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return combinar.unir(cur, auth, request, iid, corpo.ids, corpo.versoes, corpo.atributos)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.post("/api/camadas/{id}/feicoes/dividir", openapi_extra=EDITAR)
def dividir_feicao(id: str, corpo: DivisaoEntrada, request: Request, auth: Auth = Depends(_auth_editor)) -> dict:
    iid = comum.uuid_ok(id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            return combinar.dividir(cur, auth, request, iid, corpo.id, corpo.versao, corpo.ponto)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
