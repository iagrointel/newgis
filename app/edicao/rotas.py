"""Rota `POST /api/camadas/{id}/edicoes` (item L2-03-a): única porta de escrita de feição para navegador, PWA,
FeatureServer (L2-04-d) e OGC (L2-04-g). Privilégio (`feicoes.editar` OU `feicoes.editar_total`) é resolvido
DENTRO de uma dependência (`_auth_editor`, não no corpo da função) para rodar antes da validação do corpo pelo
pydantic — mesma ordem do ADR 0002 seção 5 que `app.auth.sessao.autenticado` já aplica para um privilégio só;
aqui são dois em OU, então a checagem é feita à mão dentro de outra dependência (ver
`tests/api/test_privilegios_matriz.py`, que chama a rota sem NENHUM dos dois e exige 403 antes do corpo)."""

import psycopg2
from fastapi import APIRouter, Depends, Request

from app import db
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.edicao.modelos import EdicoesEntrada, EdicoesSaida
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
