"""Escopos de token: expressão regular fechada, cobertura base → <uuid>, admin:inquilino cobre tudo (ADR 0002 8.2)."""

from types import SimpleNamespace

import pytest

from app.auth import escopos
from app.erros import ErroAPI

UUID = "0f7e5b1a-2c3d-4e5f-8a9b-0c1d2e3f4a5b"


@pytest.mark.parametrize(
    "ok",
    [
        "catalogo:ler",
        "camada:ler",
        f"camada:ler:{UUID}",
        "camada:editar",
        f"tiles:ler:{UUID}",
        "jobs:executar",
        "rede:ler",
        "rede:editar",
        "rede:validar",
        "rede:analisar",
        "admin:inquilino",
    ],
)
def test_escopos_validos(ok):
    assert escopos.valido(ok)


@pytest.mark.parametrize(
    "ruim",
    [
        "",
        "catalogo",
        "camada:apagar",
        "camada:ler:123",
        "admin",
        "ADMIN:INQUILINO",
        "tiles:ler:" + UUID + "x",
        "rede:apagar",
        f"rede:ler:{UUID}",  # item L4-23: rede:* não aceita sufixo de uuid (não há checagem de existência)
        "REDE:LER",
        12,
        None,
    ],
)
def test_escopos_invalidos(ruim):
    assert not escopos.valido(ruim)
    assert escopos.invalidos([ruim]) == [ruim]


def test_cobertura():
    assert escopos.cobre(["camada:ler"], "camada:ler", UUID)
    assert escopos.cobre([f"camada:ler:{UUID}"], "camada:ler", UUID)
    assert not escopos.cobre([f"camada:ler:{UUID}"], "camada:ler")
    assert not escopos.cobre(["camada:ler"], "camada:editar", UUID)
    assert escopos.cobre(["admin:inquilino"], "tiles:ler", UUID)


def test_cobertura_rede():
    """item L4-23-isolamento-por-inquilino-na-rede: token com rede:ler não cobre rede:editar/validar/analisar
    (vocabulário fechado, um escopo por operação); admin:inquilino cobre os quatro."""
    assert escopos.cobre(["rede:ler"], "rede:ler")
    assert not escopos.cobre(["rede:ler"], "rede:editar")
    assert not escopos.cobre(["rede:ler"], "rede:analisar")
    assert not escopos.cobre(["rede:ler"], "rede:validar")
    for base in ("rede:ler", "rede:editar", "rede:validar", "rede:analisar"):
        assert escopos.cobre(["admin:inquilino"], base)


def test_exigir_escopo_rede_403_com_detalhe():
    token = SimpleNamespace(modo="token", escopos=["rede:ler"])
    with pytest.raises(ErroAPI) as e:
        escopos.exigir_escopo(token, "rede:analisar")
    assert e.value.status_code == 403 and e.value.erro == "escopo_insuficiente"
    assert e.value.detalhe == {"exigido": "rede:analisar", "token_tem": ["rede:ler"]}


def test_exigir_escopo_403_com_detalhe_e_ignora_sessao():
    token = SimpleNamespace(modo="token", escopos=["catalogo:ler"])
    with pytest.raises(ErroAPI) as e:
        escopos.exigir_escopo(token, "camada:ler", UUID)
    assert e.value.status_code == 403 and e.value.erro == "escopo_insuficiente"
    assert e.value.detalhe == {"exigido": f"camada:ler:{UUID}", "token_tem": ["catalogo:ler"]}
    escopos.exigir_escopo(SimpleNamespace(modo="sessao", escopos=[]), "camada:ler", UUID)
    escopos.exigir_escopo(None, "camada:ler")
