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
from app.edicao import lote
from app.edicao.modelos import EdicoesEntrada, EdicoesSaida, LoteEntrada, LoteSaida
from app.edicao.servico import aplicar_edicoes
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
