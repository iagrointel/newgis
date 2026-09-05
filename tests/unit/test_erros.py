"""Contrato de erro {erro, mensagem, detalhe?, req_id} (ADR 0002 seção 14): um caso por código usado, mais o 404 de
rota inexistente, o 405 e o 422 do pydantic no mesmo formato."""

import re

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import erros

CASOS = [
    (400, "validade_acima_do_maximo"),
    (401, "credenciais_invalidas"),
    (403, "pendencia"),
    (404, "nao_encontrado"),
    (409, "ultimo_admin"),
    (410, "desafio_expirado"),
    (415, "tipo_nao_aceito"),
    (422, "senha_fraca"),
    (423, "bloqueado"),
    (503, "inquilino_suspenso"),
]


class Corpo(BaseModel):
    nome: str


def _app():
    app = FastAPI()
    erros.instalar(app)

    @app.middleware("http")
    async def rid(request: Request, call_next):
        request.state.req_id = "0123456789abcdef"
        return await call_next(request)

    @app.get("/erro/{status}/{codigo}")
    def erro(status: int, codigo: str, detalhe: str | None = None):
        raise erros.ErroAPI(status, codigo, detalhe=[detalhe] if detalhe else None)

    @app.post("/corpo")
    def corpo(c: Corpo):
        return {"ok": c.nome}

    def dep():
        raise erros.ErroAPI(403, "so_sessao")

    @app.get("/dep", dependencies=[Depends(dep)])
    def com_dep():
        return {}

    return TestClient(app)


@pytest.mark.parametrize("status,codigo", CASOS)
def test_um_caso_por_codigo(status, codigo):
    r = _app().get(f"/erro/{status}/{codigo}")
    assert r.status_code == status
    j = r.json()
    assert j["erro"] == codigo and isinstance(j["mensagem"], str) and j["mensagem"]
    assert "detalhe" not in j
    assert re.fullmatch(r"[0-9a-f]{16}", j["req_id"])


def test_detalhe_aparece_quando_informado():
    j = _app().get("/erro/422/senha_fraca?detalhe=minimo").json()
    assert j["detalhe"] == ["minimo"]


def test_404_de_rota_e_405_no_mesmo_formato():
    c = _app()
    r = c.get("/nao/existe")
    assert r.status_code == 404 and r.json()["erro"] == "nao_encontrado" and r.json()["req_id"]
    r = c.delete("/corpo")
    assert r.status_code == 405 and r.json()["erro"] == "metodo_nao_permitido"


def test_422_do_pydantic_com_lista_de_campos():
    r = _app().post("/corpo", json={"nome": 5})
    assert r.status_code == 422
    j = r.json()
    assert j["erro"] == "validacao" and j["detalhe"][0]["campo"] == "body.nome" and j["req_id"]


def test_erro_em_dependencia():
    r = _app().get("/dep")
    assert r.status_code == 403 and r.json()["erro"] == "so_sessao"
