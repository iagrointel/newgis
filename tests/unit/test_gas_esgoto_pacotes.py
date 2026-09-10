"""Pacotes de gás e de esgoto, leitura do GeoPackage TEKSI e conferência de escoamento sem banco
(item L4-05-e-gas-e-esgoto).

O que se prova aqui, sem tocar no Postgres: os dois pacotes entregues estão na forma canônica e cumprem o
portão (regras, configurações de terminal, tiers de pressão, tier por bacia); o de-para do TEKSI sai do próprio
pacote e cobre as colunas de cota; o GeoPackage sintético de 200 elementos é lido de volta com as coordenadas e
as cotas certas."""

import json
from pathlib import Path

import pytest

from app.rede_utilidades import instalados, teksi
from app.rede_utilidades import pacote as pacote_mod
from tests.dados import gerar_esgoto

RAIZ = Path(__file__).resolve().parents[2]
PACOTES = RAIZ / "app" / "rede_utilidades" / "pacotes"


def _doc(codigo: str) -> dict:
    return pacote_mod.ler((PACOTES / f"{codigo}.json").read_bytes())


@pytest.mark.parametrize("codigo", ["gas-br", "esgoto-teksi"])
def test_pacote_novo_esta_no_catalogo_instalado_e_na_forma_canonica(codigo):
    assert codigo in instalados.catalogo()
    bruto = (PACOTES / f"{codigo}.json").read_bytes()
    assert pacote_mod.canonizar(pacote_mod.ler(bruto)) == bruto


@pytest.mark.parametrize("codigo", ["gas-br", "esgoto-teksi"])
def test_cada_pacote_tem_ao_menos_20_regras_e_configuracoes_de_terminal(codigo):
    doc = _doc(codigo)
    assert len(doc["regras"]) >= 20, len(doc["regras"])
    assert len(doc["terminais"]) >= 2
    # configuração de terminal serve para alguma coisa: todo tipo de ativo aponta uma que existe
    codigos = {t["codigo"] for t in doc["terminais"]}
    assert {t["terminal"] for t in doc["tipos"]} <= codigos
    # e ao menos uma tem caminho válido declarado (é o que dá sentido de montante para jusante)
    assert any(t["caminhos_validos"] for t in doc["terminais"])


def test_gas_tem_os_quatro_tiers_de_pressao_em_ordem_decrescente():
    doc = _doc("gas-br")
    tiers = sorted((t for t in doc["tiers"]), key=lambda t: t["ordem"])
    assert [t["codigo"] for t in tiers] == ["transporte", "alta_pressao", "media_pressao", "baixa_pressao"]
    assert all(t["tipo"] == "hierarquico" for t in tiers)


def test_gas_o_regulador_e_o_controlador_de_tier_de_pressao():
    """Cláusula do portão: regulador como controlador de tier. No pacote isso é (a) categoria de controle de
    pressão, (b) atributos que dizem de qual tier para qual tier, e (c) regra de conexão para os dois lados."""
    doc = _doc("gas-br")
    tipos = {(t["grupo"], t["codigo"]): t for t in doc["tipos"]}
    reguladores = [t for (g, _c), t in tipos.items() if g == "regulador"]
    assert reguladores
    assert all("controle_de_pressao" in t["categorias"] for t in reguladores)
    atributos = {a["codigo"] for a in doc["atributos"] if a["grupo"] == "regulador"}
    assert {"tier_montante", "tier_jusante"} <= atributos
    # o regulador de rede recebe da alta e entrega na média: dois lados declarados em regras
    regras = {(r["de"], r["para"]) for r in doc["regras"]}
    assert ("regulador/2", "tubulacao_de_gas/2") in regras
    assert ("regulador/2", "tubulacao_de_gas/3") in regras


def test_esgoto_tem_tier_por_bacia_e_marca_o_que_esta_sob_pressao():
    doc = _doc("esgoto-teksi")
    tiers = {t["codigo"]: t for t in doc["tiers"]}
    assert "bacia_de_esgotamento" in tiers and "bacia_de_drenagem" in tiers
    assert all(t["tipo"] == "particionado" for t in tiers.values())
    # os trechos que a gravidade não governa saem marcados no DADO, não no código
    recalque = [t for t in doc["tipos"] if "recalque" in t["categorias"]]
    assert {t["chave"] for t in recalque} == {"linha_de_recalque", "sifao_invertido"}


def test_esgoto_usa_a_mesma_chave_de_cota_em_todo_grupo_de_trecho():
    doc = _doc("esgoto-teksi")
    grupos_linha = {g["codigo"] for g in doc["grupos"] if g["geometria"] == "linha"}
    for grupo in grupos_linha:
        codigos = {a["codigo"] for a in doc["atributos"] if a["grupo"] == grupo}
        assert {"cota_montante", "cota_jusante", "no_montante", "no_jusante"} <= codigos, grupo


def test_mapa_teksi_sai_do_pacote_e_cobre_as_colunas_de_cota():
    mapa = teksi.mapa_do_pacote(_doc("esgoto-teksi"))
    assert set(mapa) == {"vw_tww_reach", "vw_tww_wastewater_structure", "pump"}
    trecho = mapa["vw_tww_reach"]
    assert ("coletor", "cota_montante") in trecho["rp_from_level"]
    assert ("coletor", "cota_jusante") in trecho["rp_to_level"]
    estrutura = mapa["vw_tww_wastewater_structure"]
    assert ("poco_de_visita", "cota_de_fundo") in estrutura["wn_bottom_level"]


def test_toda_coluna_do_mapa_existe_como_atributo_do_pacote():
    doc = _doc("esgoto-teksi")
    pares = {(a["grupo"], a["codigo"]) for a in doc["atributos"]}
    for _camada, colunas in teksi.mapa_do_pacote(doc).items():
        for _coluna, alvos in colunas.items():
            for alvo in alvos:
                assert alvo in pares, alvo


def test_geopackage_sintetico_tem_200_elementos_e_volta_com_cota_e_geometria(tmp_path):
    arquivo = tmp_path / "teksi.gpkg"
    rede = gerar_esgoto.escrever_geopackage(arquivo)
    assert len(rede["estruturas"]) + len(rede["trechos"]) == 200

    lido = teksi.ler_geopackage(arquivo, _doc("esgoto-teksi"))
    assert lido["contagens"]["trechos_lidos"] == 99
    assert lido["contagens"]["estruturas_lidas"] == 101
    assert lido["contagens"]["ignoradas"] == 0

    primeiro = lido["linhas"][0]
    esperado = rede["trechos"][0]
    assert primeiro["attributes"]["grupo"] == "coletor"
    assert primeiro["attributes"]["atributos"]["cota_montante"] == esperado["rp_from_level"]
    assert primeiro["attributes"]["atributos"]["cota_jusante"] == esperado["rp_to_level"]
    assert primeiro["geometry"]["paths"][0] == esperado["_caminho"]
    poco = next(p for p in lido["pontos"] if p["attributes"]["grupo"] == "poco_de_visita")
    assert "cota_de_fundo" in poco["attributes"]["atributos"]


def test_rede_sintetica_escoa_por_gravidade_nos_99_trechos():
    """A cláusula de 100 % medida no DADO gerado, antes de qualquer banco: a ponta declarada como jusante é
    sempre a mais baixa, e a cota de fundo das estruturas nomeadas diz o mesmo."""
    rede = gerar_esgoto.rede_sintetica()
    cotas = {e["obj_id"]: e["wn_bottom_level"] for e in rede["estruturas"]}
    concordam = sum(1 for t in rede["trechos"] if t["rp_to_level"] < t["rp_from_level"])
    testemunha = sum(1 for t in rede["trechos"]
                     if cotas[t["rp_to_obj_id"]] < cotas[t["rp_from_obj_id"]])
    assert concordam == len(rede["trechos"]) == 99
    assert testemunha == 99


def test_geopackage_que_nao_e_teksi_e_recusado_com_codigo_curto(tmp_path):
    arquivo = tmp_path / "vazio.gpkg"
    arquivo.write_bytes(b"nem sqlite")
    with pytest.raises(teksi.ErroTeksi) as e:
        teksi.ler_geopackage(arquivo, _doc("esgoto-teksi"))
    assert e.value.codigo in ("nao_e_geopackage", "arquivo_ilegivel")


def test_paridade_gas_esta_escrita_e_cita_a_fonte():
    texto = (RAIZ / "docs" / "rede" / "PARIDADE_GAS.md").read_text(encoding="utf-8")
    assert "gas-utility-network-foundation" in texto
    assert texto.count("|") > 60  # é tabela linha a linha, não um parágrafo
    medidas = json.loads((RAIZ / "tests" / "medidas" / "L4-05-e-gas-e-esgoto.json").read_text(encoding="utf-8"))
    assert medidas["clausulas"]
