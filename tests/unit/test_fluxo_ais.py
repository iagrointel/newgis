"""Decodificador AIVDM das mensagens de posição (item L2-14-a-ingestao-de-fluxos, fonte do tipo `ais`).

As duas cargas usadas aqui são os exemplos públicos clássicos de AIVDM e os valores esperados são os que a
literatura de referência publica para elas — é o que torna este teste uma verificação do LAYOUT DE BITS e
não uma conversa do código com ele mesmo:

  `133m@ogP00PD;88MD5MTDww@2D7k` — mensagem 1, MMSI 205344990, Antuérpia (4,4070 E / 51,2296 N)
  `B5NJ;PP005l4ot5Isbl03wsUkP06` — mensagem 18, MMSI 367430530, baía de São Francisco (-122,2673 / 37,7850)
"""

import pytest

from app.fluxo import ais

CARGA_TIPO_1 = "133m@ogP00PD;88MD5MTDww@2D7k"
CARGA_TIPO_18 = "B5NJ;PP005l4ot5Isbl03wsUkP06"


def _sentenca(carga: str, *, total=1, parte=1, seq="", canal="A", preenchimento=0) -> str:
    corpo = f"!AIVDM,{total},{parte},{seq},{canal},{carga},{preenchimento}"
    soma = 0
    for c in corpo[1:]:
        soma ^= ord(c)
    return f"{corpo}*{soma:02X}"


def test_mensagem_1_posicao_de_classe_a():
    evento = ais.decodificar_carga(CARGA_TIPO_1)
    assert evento["tipo_mensagem"] == 1
    assert evento["mmsi"] == "205344990"
    assert round(evento["lon"], 4) == 4.4070
    assert round(evento["lat"], 4) == 51.2296
    assert evento["rumo_grau"] == 110.7


def test_mensagem_18_posicao_de_classe_b():
    evento = ais.decodificar_carga(CARGA_TIPO_18)
    assert evento["tipo_mensagem"] == 18
    assert evento["mmsi"] == "367430530"
    assert round(evento["lon"], 4) == -122.2673
    assert round(evento["lat"], 4) == 37.7850
    assert "estado_navegacao" not in evento  # classe B não tem estado de navegação


def test_sentenca_completa_pelo_remontador():
    assert ais.Remontador().alimentar(_sentenca(CARGA_TIPO_1))["mmsi"] == "205344990"


def test_checksum_errado_e_recusado():
    """Sentença com um bit trocado no caminho não vira posição: seria um navio no lugar errado."""
    boa = _sentenca(CARGA_TIPO_1)
    ruim = boa[:-2] + ("00" if boa[-2:] != "00" else "11")
    assert ais.Remontador().alimentar(ruim) is None


def test_sentenca_sem_checksum_e_aceita():
    """Nem toda fonte NMEA manda o checksum; sem ele a sentença ainda é legível."""
    sem = _sentenca(CARGA_TIPO_1).split("*")[0]
    assert ais.Remontador().alimentar(sem)["mmsi"] == "205344990"


def test_multiparte_so_devolve_na_ultima_parte():
    r = ais.Remontador()
    assert r.alimentar(_sentenca(CARGA_TIPO_1[:14], total=2, parte=1, seq="3")) is None
    evento = r.alimentar(_sentenca(CARGA_TIPO_1[14:], total=2, parte=2, seq="3"))
    assert evento["mmsi"] == "205344990"
    assert not r.partes  # a chave sai do acumulador; parte solta não vaza memória


def test_parte_fora_de_ordem_descarta_o_acumulado():
    r = ais.Remontador()
    r.alimentar(_sentenca(CARGA_TIPO_1[:14], total=3, parte=1, seq="3"))
    assert r.alimentar(_sentenca(CARGA_TIPO_1[14:], total=3, parte=3, seq="3")) is None
    assert not r.partes


@pytest.mark.parametrize("linha", ["", "lixo", "$GPGGA,123519,4807.038,N", "!AIVDM,1,1,,A", "!AIVDM,x,1,,A,133,0"])
def test_linha_que_nao_e_aivdm_nao_quebra(linha):
    assert ais.Remontador().alimentar(linha) is None


def test_tipo_fora_do_escopo_declarado_e_ignorado():
    """Mensagem 5 (dados estáticos) chega e é ignorada: o escopo declarado é posição."""
    assert ais.decodificar_carga("55P5TL01VIaAL@7WKO@mBplU@<PDhh00000000") is None


def test_carga_com_caractere_invalido_nao_quebra():
    assert ais.decodificar_carga("\x01\x02\x03") is None
