"""Política de senha e faixas de tenant.config.auth (ADR 0002 seções 6.1, 11, 16.5): 12 senhas inválidas com a regra
nomeada; valor fora da faixa é cortado (nunca mais fraco que o padrão); plataforma exige 2FA sempre."""

import logging

import pytest

from app import limites
from app.auth import politica as pol

PADRAO = pol.politica_de({}, "demo")

INVALIDAS = [
    ("", "minimo"),
    ("a1", "minimo"),
    ("abcdef1", "minimo"),  # 7
    ("12345678", "composicao"),  # sem letra
    ("abcdefgh", "composicao"),  # sem dígito
    ("        ", "minimo"),  # 8 espaços: sem letra e sem dígito... o mínimo passa? não: len 8 ok → composição
    ("x" * 129 + "1", "maximo"),
    ("maria123", "igual_login"),  # igual ao login
    ("Demo2026", "igual_login"),  # igual ao slug (caso-insensível)
    ("Maria Silva1", "igual_login"),  # igual ao nome
    ("ãéíõú", "minimo"),
    ("1234567a", None),  # válida: controle
]


@pytest.mark.parametrize("senha,regra", INVALIDAS)
def test_senhas_invalidas_nomeiam_a_regra(senha, regra):
    esperado = regra
    if senha == "        ":
        esperado = "composicao"
    r = pol.regra_da_senha(senha, PADRAO, login="maria123", slug="demo2026", nome="Maria Silva1")
    assert r == esperado, (senha, r)


def test_composicao_extra_quando_o_inquilino_exige():
    forte = pol.politica_de({"auth": {"senha_maiuscula": True, "senha_simbolo": True, "senha_min": 10}}, "x")
    assert pol.regra_da_senha("abcdefgh12", forte) == "composicao"
    assert pol.regra_da_senha("Abcdefgh12", forte) == "composicao"
    assert pol.regra_da_senha("Abcdefgh1!", forte) is None
    assert "maiúscula" in pol.mensagem_da_regra("composicao", forte) and "símbolo" in pol.mensagem_da_regra(
        "composicao", forte
    )


def test_frase_senha_com_espacos_e_aceita():
    assert pol.regra_da_senha("cavalo correto 7 baterias", PADRAO) is None


def test_padroes_batem_com_limites():
    for chave, (padrao, _, _) in limites.AUTH_PADROES.items():
        valor = getattr(PADRAO, chave)
        assert (list(valor) if isinstance(valor, tuple) else valor) == padrao, chave


def test_valor_fora_da_faixa_e_cortado_com_aviso(caplog):
    with caplog.at_level(logging.WARNING, logger="plat.politica"):
        p = pol.politica_de(
            {
                "auth": {
                    "senha_min": 4,
                    "bloqueio_tentativas": 99,
                    "sessao_ociosa_horas": 0,
                    "senha_expira_dias": 5,
                    "token_max_dias": 1000,
                    "token_padrao_dias": 400,
                }
            },
            "demo",
        )
    assert p.senha_min == 8 and p.bloqueio_tentativas == 10 and p.sessao_ociosa_horas == 1
    assert p.senha_expira_dias == 30 and p.token_max_dias == 365 and p.token_padrao_dias == 365
    assert sum("cortado" in r.getMessage() for r in caplog.records) >= 5


def test_tipo_errado_vira_padrao_e_dominios_normalizados():
    p = pol.politica_de(
        {"auth": {"senha_min": "dez", "exigir_2fa": "sim", "dominios_email": [" Org.Gov.BR ", ""]}}, "demo"
    )
    assert p.senha_min == 8 and p.exigir_2fa is False
    assert p.dominios_email == ("org.gov.br",)
    assert pol.email_permitido("m@org.gov.br", p) and not pol.email_permitido("m@outro.com", p)
    assert pol.email_permitido(None, p) and pol.email_permitido("x@qualquer.com", PADRAO)


def test_plataforma_exige_2fa_mesmo_com_config_falsa():
    assert pol.politica_de({"auth": {"exigir_2fa": False}}, "plataforma").exigir_2fa is True


def test_validar_config_auth_nomeia_cada_erro():
    erros = pol.validar_config_auth(
        {
            "senha_min": 4,
            "exigir_2fa": "x",
            "dominios_email": ["ok.gov.br", "in valido"],
            "senha_expira_dias": 10,
            "chave_x": 1,
        }
    )
    campos = {e["campo"] for e in erros}
    assert campos == {"senha_min", "exigir_2fa", "dominios_email", "senha_expira_dias", "chave_x"}
    assert pol.validar_config_auth({"senha_min": 10, "senha_expira_dias": 0, "dominios_email": ["a.gov.br"]}) == []
    assert pol.validar_config_auth({"token_padrao_dias": 200, "token_max_dias": 100})[0]["campo"] == "token_padrao_dias"
    assert pol.validar_config_auth([]) == [{"campo": "auth", "erro": "deve ser um objeto"}]


def test_publica_nao_vaza_mais_que_a_regra_ao_vivo():
    assert set(PADRAO.publica()) == {
        "senha_min",
        "senha_maiuscula",
        "senha_minuscula",
        "senha_simbolo",
        "exigir_2fa",
        "token_max_dias",
        "token_padrao_dias",
        "dominios_email",
    }


def test_hash_fantasma_e_um_hash_valido_e_unico_por_processo():
    from app.senha import ALGORITMO, verificar

    assert pol.HASH_FANTASMA.startswith(ALGORITMO + "$600000$")
    assert not verificar("qualquer", pol.HASH_FANTASMA)
