"""Leitura/escrita do `.inp` do EPANET, sem banco (item L4-05-d-epanet-inp).

Cláusulas do portão provadas aqui (a metade que não depende de banco): "exportar .inp e reimportar dá o mesmo
grafo" (ida e volta byte-a-byte nos campos, não no texto) — nas duas fontes usadas nesta casa: a fixture
sintética com as 10 seções (JUNCTIONS/RESERVOIRS/TANKS/PIPES/PUMPS/VALVES/COORDINATES/VERTICES/PATTERNS/CURVES)
e o arquivo REAL medido (`brasilia_caesb.inp`, CAESB/atlas público, 11.119 junções + 7 reservatórios, 14.756
trechos, 941.294 m). Refutação do item ("adversário remove uma linha de COORDINATES...") também mora aqui: a
metade que é montagem de feição (`montar_feicoes`) é pura, sem banco."""

from pathlib import Path

import pytest

from app.rede_utilidades import epanet_importar, epanet_inp

DADOS = Path(__file__).resolve().parent.parent / "dados"
COMPLETO = DADOS / "epanet_completo.inp"
REAL = DADOS / "brasilia_caesb.inp"


def _ida_e_volta(doc: epanet_inp.DocumentoEpanet) -> epanet_inp.DocumentoEpanet:
    texto2 = epanet_inp.escrever_inp(doc)
    return epanet_inp.ler_inp(texto2)


def test_le_todas_as_secoes_da_fixture_sintetica():
    doc = epanet_inp.ler_inp(COMPLETO.read_text(encoding="utf-8"))
    assert doc.contagens() == {
        "junctions": 4, "reservoirs": 1, "tanks": 1, "pipes": 5, "pumps": 1, "valves": 1,
        "coordinates": 6, "vertices": 1, "patterns": 1, "curves": 1,
    }
    bomba = doc.pumps[0]
    assert bomba == {"id": "B1", "node1": "J2", "node2": "J3", "head_curve": "C1", "power": None,
                      "pattern": None, "speed": None}
    valvula = doc.valves[0]
    assert valvula["type"] == "PRV" and valvula["setting"] == 20.0
    assert doc.curves["C1"] == [(0.0, 50.0), (10.0, 40.0), (20.0, 20.0)]
    assert doc.patterns["PAT1"] == [1.0, 1.1, 0.9, 1.0]
    assert doc.vertices["P2"] == [(15.0, 2.0)]


def test_ida_e_volta_campo_a_campo_fixture_sintetica():
    doc = epanet_inp.ler_inp(COMPLETO.read_text(encoding="utf-8"))
    doc2 = _ida_e_volta(doc)
    assert doc.contagens() == doc2.contagens()
    for campo in ("junctions", "reservoirs", "tanks", "pipes", "pumps", "valves",
                  "coordinates", "vertices", "patterns", "curves"):
        assert getattr(doc, campo) == getattr(doc2, campo), campo


@pytest.mark.skipif(not REAL.exists(), reason="fixture real (brasilia_caesb.inp) não está neste checkout")
def test_ida_e_volta_arquivo_real_11119_juncoes_14756_trechos():
    """Ativo da casa (GPU box `/home/dev/nascente/artifacts/edge_tests/brasilia_caesb.inp`, dado público CAESB/
    atlas.caesb.df.gov.br): 11.119 junções + 7 reservatórios = 11.126 nós, 14.756 trechos, Σ Length = 941.294 m
    — os números citados no portão do item."""
    doc = epanet_inp.ler_inp(REAL.read_text(encoding="utf-8"))
    c = doc.contagens()
    assert c["junctions"] == 11119
    assert c["reservoirs"] == 7
    assert c["pipes"] == 14756
    assert c["coordinates"] == 11126
    soma = sum(p["length"] for p in doc.pipes)
    assert soma == pytest.approx(941294.02, abs=0.01)
    doc2 = _ida_e_volta(doc)
    assert doc.contagens() == doc2.contagens()
    assert doc.pipes == doc2.pipes
    assert doc.coordinates == doc2.coordinates
    assert sum(p["length"] for p in doc2.pipes) == pytest.approx(soma, abs=1e-6)


def test_secao_fora_do_escopo_vira_aviso_nao_erro():
    texto = ("[JUNCTIONS]\n J1 10 1\n[CONTROLS]\n LINK P1 OPEN AT TIME 0\n[COORDINATES]\n"
             " J1 0 0\n[END]\n")
    doc = epanet_inp.ler_inp(texto)
    assert len(doc.junctions) == 1
    assert any("CONTROLS" in a for a in doc.avisos)


def test_campo_numerico_invalido_lanca_erro_com_a_secao_e_a_linha():
    texto = "[JUNCTIONS]\n J1 abc 1\n"
    with pytest.raises(epanet_inp.ErroInp, match=r"\[JUNCTIONS\] linha 2"):
        epanet_inp.ler_inp(texto)


def test_tipo_de_valvula_desconhecido_recusado():
    texto = "[VALVES]\n V1 N1 N2 100 XYZ 10\n"
    with pytest.raises(epanet_inp.ErroInp, match="XYZ"):
        epanet_inp.ler_inp(texto)


# --- refutação: nó sem [COORDINATES] (montar_feicoes, sem banco) ------------------------------------------

def _texto_sem_uma_coordenada() -> str:
    return (
        "[JUNCTIONS]\n J1 10 1\n J2 12 1\n"
        "[PIPES]\n P1 J1 J2 100 200 130 0 Open\n"
        "[COORDINATES]\n J1 0 0\n"
        "[END]\n"
    )


def test_no_sem_coordenada_fica_sem_geometria_nunca_ponto_zero_zero():
    doc = epanet_inp.ler_inp(_texto_sem_uma_coordenada())
    montado = epanet_importar.montar_feicoes(doc, crs_epsg=None)
    j2 = next(p for p in montado["pontos"] if p["atributos"].get("no_id") == "J2")
    assert j2["lonlat"] is None, "J2 não tem linha em [COORDINATES]: tem de ficar SEM geometria, nunca (0,0)"
    j1 = next(p for p in montado["pontos"] if p["atributos"].get("no_id") == "J1")
    assert j1["lonlat"] == (0.0, 0.0), "J1 tem coordenada REAL (0,0) no arquivo — esse é o caso que não pode "\
        "se confundir com 'sem coordenada'"
    assert montado["n_sem_coordenada"] == 1
    assert any("J2" in a and "sem linha em [COORDINATES]" in a for a in montado["avisos"])
    # o trecho conectado ao nó sem coordenada também fica sem geometria própria — mas o comprimento DECLARADO
    # (o que entra na comparação de soma do portão) nunca depende de geometria.
    p1 = montado["linhas"][0]
    assert p1["coords"] is None
    assert p1["atributos"]["tubulacao_comprimento"] == 100.0
    soma = sum(linha["atributos"]["tubulacao_comprimento"] for linha in montado["linhas"])
    soma_arquivo = sum(p["length"] for p in doc.pipes)
    assert soma == soma_arquivo == 100.0


def test_coordenada_fora_da_faixa_wgs84_sem_crs_epsg_e_erro_explicado():
    texto = "[JUNCTIONS]\n J1 10 1\n[COORDINATES]\n J1 187583.22 8252603.78\n[END]\n"
    doc = epanet_inp.ler_inp(texto)
    with pytest.raises(epanet_importar.ErroImportacaoEpanet, match="crs_epsg"):
        epanet_importar.montar_feicoes(doc, crs_epsg=None)


def test_coordenada_utm23s_reprojetada_com_crs_epsg():
    texto = "[JUNCTIONS]\n J1 10 1\n[COORDINATES]\n J1 187583.22 8252603.78\n[END]\n"
    doc = epanet_inp.ler_inp(texto)
    montado = epanet_importar.montar_feicoes(doc, crs_epsg=31983)
    lon, lat = montado["pontos"][0]["lonlat"]
    # SIRGAS 2000 / UTM 23S perto de Brasília: lon ~ -47.9, lat ~ -15.8 (mesma região da fixture real)
    assert -48.5 < lon < -47.0
    assert -16.5 < lat < -15.0
