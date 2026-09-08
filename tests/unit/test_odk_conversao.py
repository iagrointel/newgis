"""Conversões puras da ponte com o ODK Central (item L2-07-e-odk-central-ponte): linha do OData -> resposta de
formulário, e Entities -> lista de escolhas em cascata. Sem banco e sem rede."""

from pathlib import Path

import pytest

from app.coleta import motor, xlsform
from app.erros import ErroAPI
from app.odk import ponte

XLSFORMS = Path(__file__).resolve().parents[1] / "coleta" / "xlsforms"


@pytest.fixture(scope="module")
def doc() -> dict:
    return xlsform.importar((XLSFORMS / "campo_odk.xlsx").read_bytes(), "campo_odk.xlsx")


LINHA = {
    "__id": "uuid:zt-odk-000",
    "__system": {"submissionDate": "2026-09-02T10:00:00.000Z", "submitterId": 5},
    "inicio": "2026-09-02T09:55:00.000Z", "fim": "2026-09-02T10:00:00.000Z",
    "ponto": "P-000",
    "local": {"type": "Point", "coordinates": [-46.6, -23.5, 720.0]},
    "detalhe": {"arvores": 12, "estado_ponto": "bom"},
    "foto": "foto-000.png",
    "amostras": [{"codigo_a": "A0-1", "peso_a": 1.5}, {"codigo_a": "A0-2", "peso_a": 2.5}],
    "meta": {"instanceID": "uuid:zt-odk-000"},
}


def test_achatar_tira_o_grupo_e_guarda_a_repeticao():
    valores, repeticoes = ponte.achatar(LINHA)
    assert valores["ponto"] == "P-000"
    assert valores["arvores"] == 12 and valores["estado_ponto"] == "bom"  # o grupo `detalhe` some
    assert "__id" not in valores and "__system" not in valores and "meta" not in valores
    assert [x["codigo_a"] for x in repeticoes["amostras"]] == ["A0-1", "A0-2"]


def test_instance_id_e_o_campo_id_do_odata():
    assert ponte.instance_id(LINHA) == "uuid:zt-odk-000"
    for ruim in ({}, {"__id": ""}, {"__id": 7}, {"__id": None}):
        with pytest.raises(ErroAPI) as e:
            ponte.instance_id(ruim)
        assert e.value.erro == "envio_sem_instance_id"


def test_geopoint_do_odata_vira_o_texto_que_o_documento_espera(doc):
    corpo = ponte.resposta_da_linha(doc, LINHA)
    assert corpo["valores"]["local"] == "-23.5 -46.6 720.0"
    assert corpo["valores"]["ponto"] == "P-000" and corpo["valores"]["arvores"] == 12
    assert corpo["repeticoes"]["amostras"][1]["peso_a"] == 2.5
    assert corpo["inicio"] == "2026-09-02T09:55:00.000Z"
    assert corpo["dispositivo"] == "odk-central"


def test_campo_que_o_documento_nao_conhece_e_ignorado(doc):
    linha = dict(LINHA) | {"campo_novo_do_central": "x", "detalhe": {"arvores": 3, "outro": 9}}
    corpo = ponte.resposta_da_linha(doc, linha)
    assert "campo_novo_do_central" not in corpo["valores"] and "outro" not in corpo["valores"]
    assert corpo["valores"]["arvores"] == 3


def test_a_resposta_convertida_passa_no_motor_do_formulario(doc):
    """A conversão não pode gerar resposta que o motor do L2-07-b recusaria por tipo ou por restrição."""
    corpo = ponte.resposta_da_linha(doc, LINHA)
    r = motor.avaliar_resposta(doc, corpo["valores"], corpo["repeticoes"])
    assert r.ok, r.erros


def test_restricao_violada_no_central_continua_recusada_aqui(doc):
    """`arvores >= 0` é restrição do formulário: valor negativo vindo do Central não vira feição."""
    linha = dict(LINHA) | {"detalhe": {"arvores": -5, "estado_ponto": "bom"}}
    corpo = ponte.resposta_da_linha(doc, linha)
    r = motor.avaliar_resposta(doc, corpo["valores"], corpo["repeticoes"])
    assert not r.ok and any(e.get("campo") == "arvores" for e in r.erros)


def test_nomes_de_anexo_ligam_arquivo_ao_campo(doc):
    assert ponte.nomes_de_anexo(doc, LINHA)["foto-000.png"] == "foto"
    assert ponte.tipo_do_arquivo("foto-000.png") == "image/png"


def test_entidades_viram_lista_de_escolhas_com_as_propriedades_como_colunas():
    brutas = [
        {"uuid": "e1", "currentVersion": {"label": "Salvador", "data": {"estado": "ba", "populacao": "2900000"}}},
        {"uuid": "e2", "currentVersion": {"label": "Campinas", "data": {"estado": "sp"}}},
        {"uuid": "e3", "deletedAt": "2026-09-01T00:00:00Z", "currentVersion": {"label": "Apagada", "data": {}}},
        {"nao": "e um dicionario de entidade"},
    ]
    opcoes = ponte.escolhas_de_entidades(brutas)
    assert [o["nome"] for o in opcoes] == ["e1", "e2"]          # a apagada e a malformada saem
    assert opcoes[0]["rotulo"] == {"pt": "Salvador"} and opcoes[0]["estado"] == "ba"


def test_cascata_de_tres_niveis_sobre_entidades_lidas_do_central():
    """As Entities de três datasets viram três listas; o filtro em cascata do L2-07-b é feito sobre as
    propriedades da entidade (nível 2 filtra pelo nível 1, nível 3 pelo nível 2)."""
    estados = ponte.escolhas_de_entidades(
        [{"uuid": "ba", "currentVersion": {"label": "Bahia", "data": {"regiao": "ne"}}},
         {"uuid": "sp", "currentVersion": {"label": "São Paulo", "data": {"regiao": "se"}}}])
    municipios = ponte.escolhas_de_entidades(
        [{"uuid": "ssa", "currentVersion": {"label": "Salvador", "data": {"estado": "ba"}}},
         {"uuid": "spo", "currentVersion": {"label": "São Paulo", "data": {"estado": "sp"}}}])
    bairros = ponte.escolhas_de_entidades(
        [{"uuid": "pit", "currentVersion": {"label": "Pituba", "data": {"municipio": "ssa"}}},
         {"uuid": "pin", "currentVersion": {"label": "Pinheiros", "data": {"municipio": "spo"}}}])
    escolhido_estado = "ba"
    n2 = [m for m in municipios if m["estado"] == escolhido_estado]
    assert [m["nome"] for m in n2] == ["ssa"]
    n3 = [b for b in bairros if b["municipio"] == n2[0]["nome"]]
    assert [b["nome"] for b in n3] == ["pit"] and n3[0]["rotulo"]["pt"] == "Pituba"
    assert [e["nome"] for e in estados if e["regiao"] == "ne"] == ["ba"]
