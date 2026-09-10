"""Decodificação de corpo, filtro de entrada e teto por segundo da fonte de fluxo (item
L2-14-a-ingestao-de-fluxos).

Cláusulas do portão cobertas aqui: "filtro na entrada descarta e conta" e o teto de eventos/s com descarte
contado; da refutação, "JSON com 10 MB".
"""

import datetime

import pytest

from app import limites
from app.fluxo import entrada
from app.fluxo import filtro as f
from app.fluxo import formato as fo
from app.fluxo import limite as li
from app.fluxo import mapeamento as m
from app.fluxo.fila import Fila
from app.fluxo.fontes import Fonte

UTC = datetime.UTC


# ------------------------------------------------------------------ formato
def test_json_objeto_ou_lista():
    assert fo.decodificar(b'{"a":1}', "json") == [{"a": 1}]
    assert fo.decodificar(b'[{"a":1},{"a":2}]', "json") == [{"a": 1}, {"a": 2}]


def test_ndjson_ignora_linha_vazia():
    assert fo.decodificar(b'{"a":1}\n\n{"a":2}\n', "ndjson") == [{"a": 1}, {"a": 2}]


def test_csv_com_cabecalho():
    assert fo.decodificar(b"id,lon,lat\nA,-46.6,-23.5\n", "csv") == [{"id": "A", "lon": "-46.6", "lat": "-23.5"}]


def test_csv_sem_cabecalho_e_recusado():
    with pytest.raises(fo.ErroFormato) as e:
        fo.decodificar(b"", "csv")
    assert e.value.motivo == "csv_sem_cabecalho"


def test_geojson_feature_collection_traz_propriedades_e_geometria():
    corpo = (b'{"type":"FeatureCollection","features":[{"type":"Feature",'
             b'"properties":{"placa":"AAA0A00"},"geometry":{"type":"Point","coordinates":[-46.6,-23.5]}}]}')
    registros = fo.decodificar(corpo, "geojson")
    assert registros[0]["placa"] == "AAA0A00"
    assert registros[0]["geometry"]["coordinates"] == [-46.6, -23.5]


def test_gpx_le_trkpt():
    corpo = (b'<gpx version="1.1"><trk><trkseg>'
             b'<trkpt lat="-23.5" lon="-46.6"><time>2026-01-15T12:00:00Z</time><ele>760</ele></trkpt>'
             b'</trkseg></trk></gpx>')
    registros = fo.decodificar(corpo, "gpx")
    assert registros == [{"lat": "-23.5", "lon": "-46.6", "time": "2026-01-15T12:00:00Z", "ele": "760"}]


def test_esri_json_traz_atributos_e_ponto():
    corpo = b'{"features":[{"attributes":{"id":1},"geometry":{"x":-46.6,"y":-23.5}}]}'
    registros = fo.decodificar(corpo, "esri_json")
    assert registros[0]["id"] == 1
    assert registros[0]["geometry"] == {"type": "Point", "coordinates": [-46.6, -23.5]}


def test_corpo_de_dez_mega_e_recusado_antes_de_decodificar():
    """Refutação do item: 'envia JSON com 10 MB'. O teto do receptor é 4 MiB e a recusa vem por tamanho,
    nunca por o analisador de JSON tentar montar dez megabytes em memória."""
    gigante = b'[{"a":"' + b"x" * (10 * 1024 * 1024) + b'"}]'
    with pytest.raises(fo.ErroFormato) as e:
        fo.decodificar(gigante, "json")
    assert e.value.motivo == "corpo_grande_demais"


def test_lote_acima_do_teto_de_eventos_e_recusado():
    corpo = ("[" + ",".join(["{}"] * (limites.FLUXO_LOTE_MAX + 1)) + "]").encode()
    with pytest.raises(fo.ErroFormato) as e:
        fo.decodificar(corpo, "json")
    assert e.value.motivo == "lote_grande_demais"


def test_json_invalido_tem_motivo_estavel():
    with pytest.raises(fo.ErroFormato) as e:
        fo.decodificar(b"{nao e json", "json")
    assert e.value.motivo == "json_invalido"


def test_corpo_que_nao_e_utf8():
    with pytest.raises(fo.ErroFormato) as e:
        fo.decodificar(b"\xff\xfe{}", "json")
    assert e.value.motivo == "corpo_nao_utf8"


# ------------------------------------------------------------------ teto por segundo
def test_balde_deixa_passar_ate_a_taxa_e_conta_o_resto():
    balde = li.Balde(taxa=10)
    assert balde.permitir(4, agora=0.0) == 4
    assert balde.permitir(10, agora=0.0) == 6
    assert balde.descartados == 4


def test_balde_repoe_fichas_com_o_tempo():
    balde = li.Balde(taxa=10)
    balde.permitir(10, agora=0.0)
    assert balde.permitir(5, agora=0.5) == 5      # meio segundo repõe 5 fichas
    assert balde.permitir(10, agora=1.5) == 10    # nunca acima da taxa de um segundo


def test_balde_ajustado_nunca_guarda_mais_que_o_teto_novo():
    balde = li.Balde(taxa=100)
    balde.ajustar(5)
    assert balde.permitir(100, agora=balde.quando) == 5


# ------------------------------------------------------------------ filtro
def _evento(**troca):
    dados = {"rastro_id": "AAA0A00", "tempo_evento": datetime.datetime(2026, 1, 15, 12, tzinfo=UTC),
             "lon": -46.6, "lat": -23.5, "wkt": None, "atributos": {"velocidade": 42.5}}
    dados.update(troca)
    return m.Evento(**dados)


def test_filtro_ausente_deixa_tudo_passar():
    assert f.aceita(f.compilar(None), _evento()) is True
    assert f.aceita(f.compilar("  "), _evento()) is True


def test_filtro_sobre_campo_mapeado():
    ast = f.compilar("$velocidade > 40")
    assert f.aceita(ast, _evento()) is True
    assert f.aceita(ast, _evento(atributos={"velocidade": 10})) is False


def test_filtro_sobre_coordenada_e_rastro():
    assert f.aceita(f.compilar("$lat < -20 && $rastro_id == 'AAA0A00'"), _evento()) is True


def test_filtro_com_campo_fora_da_lista_branca_e_erro_nomeado():
    with pytest.raises(f.ErroFiltro):
        f.aceita(f.compilar("$campo_que_nao_existe > 1"), _evento())


def test_filtro_nao_booleano_e_erro_nomeado():
    with pytest.raises(f.ErroFiltro) as e:
        f.aceita(f.compilar("$velocidade + 1"), _evento())
    assert e.value.motivo == "filtro_nao_booleano"


def test_filtro_com_sintaxe_errada_e_recusado_na_compilacao():
    with pytest.raises(f.ErroFiltro) as e:
        f.compilar("$a >")
    assert e.value.motivo == "filtro_invalido"


# ------------------------------------------------------------------ o caminho inteiro do lote
def _fonte(**troca):
    mapa, _ = m.validar({"campo_tempo": {"caminho": "ts", "tipo": "iso"}, "campo_rastro": "id",
                         "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
                         "campos": [{"caminho": "v", "coluna": "v", "tipo": "numero"}]})
    dados = {"id": "11111111-1111-1111-1111-111111111111", "tenant_id": 1, "dono_id": 2, "dono_login": "admin",
             "tipo": "http", "nome": "fonte de teste", "estado": "ativa", "config": {}, "limite_eventos_s": 5,
             "mapa": mapa, "filtro_texto": None, "filtro_ast": None, "balde": li.Balde(taxa=5)}
    dados.update(troca)
    return Fonte(**dados)


def _registros(n, **troca):
    base = {"ts": "2026-01-15T12:00:00+00:00", "lon": -46.6, "lat": -23.5, "v": 50}
    base.update(troca)
    return [dict(base, id=f"r{i}") for i in range(n)]


def test_filtro_na_entrada_descarta_e_conta():
    """Cláusula do portão: 'filtro na entrada descarta e conta'."""
    fonte = _fonte(filtro_texto="$v > 40", filtro_ast=f.compilar("$v > 40"), limite_eventos_s=100,
                   balde=li.Balde(taxa=100))
    fila = Fila()
    resumo = entrada.ingerir(fonte, _registros(3, v=50) + _registros(2, v=10), fila)
    assert resumo["aceitos"] == 3
    assert resumo["descartados_filtro"] == 2
    conta = fila.conta(fonte.id).instantaneo()
    assert conta["aceitos"] == 3 and conta["descartados_filtro"] == 2 and conta["recebidos"] == 5
    assert fila.tamanho() == 3


def test_teto_por_segundo_descarta_e_conta():
    fonte = _fonte()
    fila = Fila()
    resumo = entrada.ingerir(fonte, _registros(12), fila)
    assert resumo["aceitos"] == 5 and resumo["descartados_limite"] == 7
    assert fila.conta(fonte.id).instantaneo()["descartados_limite"] == 7


def test_evento_invalido_conta_por_motivo():
    fonte = _fonte(limite_eventos_s=100, balde=li.Balde(taxa=100))
    fila = Fila()
    resumo = entrada.ingerir(fonte, _registros(2) + _registros(1, lat=999), fila)
    assert resumo["aceitos"] == 2 and resumo["descartados_invalido"] == 1
    assert fila.conta(fonte.id).instantaneo()["motivos"]["coordenada_fora_da_faixa"] == 1


def test_fonte_pausada_guarda_no_buffer_e_drena_ao_retomar():
    """Cláusula do portão: 'fonte pausada não perde eventos ... (buffer declarado)'."""
    fonte = _fonte(estado="pausada", limite_eventos_s=100, balde=li.Balde(taxa=100))
    fila = Fila()
    resumo = entrada.ingerir(fonte, _registros(30), fila)
    assert resumo["em_buffer"] == 30 and resumo["aceitos"] == 0 and fila.tamanho() == 0
    fonte.estado = "ativa"
    assert entrada.drenar_buffer(fonte, fila) == 30
    assert fila.tamanho() == 30 and not fonte.buffer


def test_buffer_de_pausa_tem_teto_declarado_e_conta_o_que_passa_dele():
    fonte = _fonte(estado="pausada", limite_eventos_s=1, balde=li.Balde(taxa=10_000))
    assert fonte.buffer_max == limites.FLUXO_BUFFER_PAUSA_S
    fila = Fila()
    resumo = entrada.ingerir(fonte, _registros(fonte.buffer_max + 5), fila)
    assert resumo["em_buffer"] == fonte.buffer_max
    assert fila.conta(fonte.id).instantaneo()["motivos"]["buffer_de_pausa_cheio"] == 5


def test_fila_cheia_descarta_o_evento_novo_e_conta():
    fonte = _fonte(limite_eventos_s=1000, balde=li.Balde(taxa=1000))
    fila = Fila(teto=10)
    resumo = entrada.ingerir(fonte, _registros(25), fila)
    assert resumo["aceitos"] == 10
    assert fila.conta(fonte.id).instantaneo()["motivos"]["fila_cheia"] == 15
