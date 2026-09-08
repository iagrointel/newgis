"""Regras de provisionamento (item L0-08-e): decisão pura sem banco — valor exato do grupo do IdP, padrão quando
nada casa, mapeamento só por regra explícita (um grupo chamado 'administrador' sem regra não vira admin), corte
em 1000 valores do IdP, validação de forma (422 nomeando o campo)."""

import uuid

import pytest

from app import limites
from app.auth import provisionamento as pv
from app.erros import ErroAPI

G1, G2, G3 = (str(uuid.uuid4()) for _ in range(3))
BRUTO = {
    "criacao": "convite",
    "atualizar_a_cada_login": True,
    "desligar_sem_grupo": True,
    "padrao": {"papel_id": 7, "grupos": [G1]},
    "pasta": "Pessoal de {login}",
    "mapa": {
        "gis-editores": {"perfil": "editor", "papel_id": 3, "grupos": [G2]},
        "gis-admins": {"perfil": "admin", "grupos": [G2, G3]},
        "Leitura": {"perfil": "visualizador"},
    },
}


def test_regras_normalizadas_e_de_volta_ao_json():
    r = pv.regras_de(BRUTO)
    assert r.criacao == "convite" and r.desligar_sem_grupo and r.pasta == "Pessoal de {login}"
    assert r.padrao.papel_id == 7 and r.padrao.grupos == [G1]
    assert set(r.mapa) == {"gis-editores", "gis-admins", "Leitura"}
    assert r.regidos == [G1, G2, G3]
    assert r.perfis() == {"gis-editores": "editor", "gis-admins": "admin", "Leitura": "visualizador"}
    assert pv.regras_de(pv.para_json(r)) == r
    assert pv.regras_de(None).criacao == "automatica" and pv.regras_de({}).regidos == []


def test_valor_exato_e_padrao():
    r = pv.regras_de(BRUTO)
    d = pv.decidir(r, ["gis-editores"], {}, None)
    assert (d.perfil, d.papel_id, d.grupos, d.valores_casados) == ("editor", 3, [G2], ["gis-editores"])
    d = pv.decidir(r, ["outro", "GIS-EDITORES"], {}, "visualizador")  # caixa diferente = valor diferente
    assert d.perfil == "editor" and d.papel_id == 7 and d.grupos == [G1] and d.valores_casados == []
    d = pv.decidir(r, [], {}, "campo")
    assert d.perfil == "campo" and d.papel_id == 7 and d.grupos == [G1]
    d = pv.decidir(r, ["gis-admins", "gis-editores"], {}, None)
    assert d.perfil == "admin" and d.papel_id == 3 and d.grupos == [G2, G3]


def test_grupo_com_nome_de_papel_nao_mapeia_sem_regra():
    r = pv.regras_de({"mapa": {"gis-editores": {"perfil": "editor"}}})
    for nome in ("administrador", "admin", "Admin", "editor", "papel:admin"):
        d = pv.decidir(r, [nome], {}, None)
        assert d.perfil is None and d.papel_id is None and d.grupos == [] and d.valores_casados == [], nome
        d = pv.decidir(r, [nome], {}, "visualizador")
        assert d.perfil == "visualizador", nome


def test_500_grupos_do_idp_e_corte_em_1000():
    muitos = [f"g{i}" for i in range(500)] + ["gis-editores"]
    r = pv.regras_de({"mapa": {"gis-editores": {"perfil": "editor"}}})
    d = pv.decidir(r, pv.valores_do_idp(muitos), {}, None)
    assert d.perfil == "editor" and d.valores_casados == ["gis-editores"]
    alem = [f"g{i}" for i in range(limites.PROVISIONAMENTO_GRUPOS_IDP_MAX)] + ["gis-editores"]
    assert "gis-editores" not in pv.valores_do_idp(alem)  # acima do teto é ignorado, nunca processado
    assert pv.valores_do_idp("so-um") == ["so-um"] and pv.valores_do_idp(None) == []
    assert pv.valores_do_idp(["x" * 201, " ok "]) == ["ok"]


@pytest.mark.parametrize(
    "bruto,campo",
    [
        ({"criacao": "sempre"}, "criacao"),
        ({"atualizar_a_cada_login": "sim"}, "atualizar_a_cada_login"),
        ({"padrao": {"papel_id": 0}}, "padrao"),
        ({"padrao": {"grupos": ["nao-e-uuid"]}}, "padrao"),
        ({"mapa": {"g": {"perfil": "dono"}}}, "mapa[g]"),
        ({"mapa": {"": {"perfil": "editor"}}}, "mapa"),
        ({"pasta": "a/b"}, "pasta"),
        ({"mapa": {f"g{i}": {} for i in range(limites.PROVISIONAMENTO_REGRAS_MAX + 1)}}, "mapa"),
    ],
)
def test_forma_invalida_422_nomeia_o_campo(bruto, campo):
    with pytest.raises(ErroAPI) as e:
        pv.regras_de(bruto)
    assert e.value.status_code == 422 and e.value.detalhe["campo"] == campo
