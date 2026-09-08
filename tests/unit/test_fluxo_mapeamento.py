"""Mapeamento de campos da fonte de fluxo (item L2-14-a-ingestao-de-fluxos).

Cláusula do portão coberta aqui: "mapeamento com fuso converte corretamente". As demais checagens são a
fronteira de confiança do receptor — coordenada fora da faixa, tempo no futuro, id de rastro de 1 MB e valor
de texto gigante são exatamente o que a refutação do item manda enviar.
"""

import datetime

import pytest

from app import limites
from app.fluxo import mapeamento as m

UTC = datetime.UTC


def _mapa(**troca):
    base = {
        "campo_tempo": {"caminho": "ts", "tipo": "iso", "fuso": "America/Sao_Paulo"},
        "campo_rastro": "veiculo.placa",
        "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
        "campos": [{"caminho": "velocidade", "coluna": "velocidade", "tipo": "numero"}],
    }
    base.update(troca)
    mapa, _ = m.validar(base)
    return mapa


def test_caminho_com_ponto_e_indice():
    registro = {"a": {"b": [{"c": 7}]}}
    assert m.ler_caminho(registro, "a.b[0].c") == 7
    assert m.ler_caminho(registro, "a.b[3].c") is None
    assert m.ler_caminho(registro, "a.x") is None


def test_fuso_declarado_converte_texto_sem_deslocamento_para_utc():
    """São Paulo é UTC-3 o ano todo desde 2019 (fim do horário de verão): 09:00 local = 12:00 UTC."""
    mapa = _mapa()
    evento = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00", "lon": -46.6, "lat": -23.5,
                              "veiculo": {"placa": "AAA0A00"}, "velocidade": 42.5})
    assert isinstance(evento, m.Evento)
    assert evento.tempo_evento == datetime.datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    assert evento.rastro_id == "AAA0A00"
    assert evento.atributos == {"velocidade": 42.5}


def test_deslocamento_no_proprio_dado_manda_no_fuso_declarado():
    """Texto COM deslocamento não é reinterpretado: o dado já disse onde está."""
    mapa = _mapa()
    evento = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00+00:00", "lon": 0, "lat": 0})
    assert evento.tempo_evento == datetime.datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def test_fuso_com_horario_de_verao_do_hemisferio_norte():
    """Fuso não é deslocamento fixo: Lisboa é UTC+0 em janeiro e UTC+1 em julho."""
    mapa = _mapa(campo_tempo={"caminho": "ts", "tipo": "iso", "fuso": "Europe/Lisbon"})
    inverno = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0})
    verao = m.aplicar(mapa, {"ts": "2026-07-15T09:00:00", "lon": 0, "lat": 0})
    assert inverno.tempo_evento.hour == 9
    assert verao.tempo_evento.hour == 8


def test_epoca_em_segundos_e_milissegundos():
    for tipo, valor in (("epoch_s", 1_767_182_400), ("epoch_ms", 1_767_182_400_000)):
        mapa = _mapa(campo_tempo={"caminho": "ts", "tipo": tipo})
        evento = m.aplicar(mapa, {"ts": valor, "lon": 0, "lat": 0})
        assert evento.tempo_evento == datetime.datetime(2025, 12, 31, 12, 0, tzinfo=UTC)


def test_formato_de_texto_declarado():
    mapa = _mapa(campo_tempo={"caminho": "ts", "tipo": "texto", "formato": "%d/%m/%Y %H:%M:%S", "fuso": "UTC"})
    evento = m.aplicar(mapa, {"ts": "15/01/2026 09:00:00", "lon": 0, "lat": 0})
    assert evento.tempo_evento == datetime.datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def test_fuso_desconhecido_e_recusado_na_validacao():
    with pytest.raises(m.ErroMapeamento) as e:
        _mapa(campo_tempo={"caminho": "ts", "tipo": "iso", "fuso": "America/Nao_Existe"})
    assert e.value.motivo == "fuso_desconhecido"


def test_tempo_no_futuro_e_descartado_com_motivo():
    """Refutação do item: 'tempo no futuro'."""
    mapa = _mapa(campo_tempo={"caminho": "ts", "tipo": "iso"})
    adiante = datetime.datetime.now(UTC) + datetime.timedelta(seconds=limites.FLUXO_TEMPO_FUTURO_MAX_S + 60)
    erro = m.aplicar(mapa, {"ts": adiante.isoformat(), "lon": 0, "lat": 0})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "tempo_no_futuro"


def test_folga_de_relogio_dentro_do_limite_passa():
    mapa = _mapa(campo_tempo={"caminho": "ts", "tipo": "iso"})
    adiante = datetime.datetime.now(UTC) + datetime.timedelta(seconds=10)
    assert isinstance(m.aplicar(mapa, {"ts": adiante.isoformat(), "lon": 0, "lat": 0}), m.Evento)


@pytest.mark.parametrize("lon,lat", [(200.0, 0.0), (-181.0, 0.0), (0.0, 91.0), (0.0, -90.5)])
def test_coordenada_fora_da_faixa_e_descartada(lon, lat):
    """Refutação do item: 'coordenada fora da faixa'."""
    erro = m.aplicar(_mapa(), {"ts": "2026-01-15T09:00:00", "lon": lon, "lat": lat})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "coordenada_fora_da_faixa"


def test_coordenada_nao_numerica_e_descartada():
    erro = m.aplicar(_mapa(), {"ts": "2026-01-15T09:00:00", "lon": "leste", "lat": 0})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "coordenada_invalida"


def test_id_de_rastro_de_um_mega_e_recusado():
    """Refutação do item: 'id de rastro com 1 MB'."""
    erro = m.aplicar(_mapa(), {"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0,
                               "veiculo": {"placa": "x" * 1_000_000}})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "rastro_longo"


def test_texto_gigante_em_campo_mapeado_e_recusado():
    mapa = _mapa(campos=[{"caminho": "obs", "coluna": "obs", "tipo": "texto"}])
    erro = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0, "obs": "y" * 100_000})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "texto_longo"


def test_geometria_wkt_e_geojson():
    ponto = {"ts": "2026-01-15T09:00:00", "geom": "POINT(-46.6 -23.5)"}
    evento = m.aplicar(_mapa(geometria={"modo": "wkt", "caminho": "geom"}), ponto)
    assert (round(evento.lon, 4), round(evento.lat, 4)) == (-46.6, -23.5)
    evento = m.aplicar(_mapa(geometria={"modo": "geojson", "caminho": "geometry"}),
                       {"ts": "2026-01-15T09:00:00", "geometry": {"type": "Point", "coordinates": [-46.6, -23.5]}})
    assert (round(evento.lon, 4), round(evento.lat, 4)) == (-46.6, -23.5)


def test_wkt_de_poligono_e_recusado():
    erro = m.aplicar(_mapa(geometria={"modo": "wkt", "caminho": "geom"}),
                     {"ts": "2026-01-15T09:00:00", "geom": "POLYGON((0 0, 1 0, 1 1, 0 0))"})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "geometria_invalida"


def test_esquema_de_destino_e_gerado_do_mapeamento():
    mapa = _mapa(campos=[{"caminho": "a.b", "tipo": "inteiro"}, {"caminho": "c", "coluna": "cc", "tipo": "texto"}])
    esquema = m.esquema_destino(mapa)
    por_nome = {c["nome"]: c for c in esquema}
    assert por_nome["a_b"]["tipo"] == "inteiro"
    assert por_nome["cc"]["origem"] == "c"
    assert por_nome["tempo_evento"]["tipo"] == "data"
    assert por_nome["geom"]["tipo"] == "geometria"


def test_coluna_repetida_e_recusada():
    with pytest.raises(m.ErroMapeamento) as e:
        _mapa(campos=[{"caminho": "a", "coluna": "x", "tipo": "texto"},
                      {"caminho": "b", "coluna": "x", "tipo": "texto"}])
    assert e.value.motivo == "coluna_repetida"


def test_campos_demais_e_recusado():
    with pytest.raises(m.ErroMapeamento) as e:
        _mapa(campos=[{"caminho": f"c{i}", "coluna": f"c{i}", "tipo": "texto"}
                      for i in range(limites.FLUXO_CAMPOS_MAX + 1)])
    assert e.value.motivo == "campos_demais"


def test_valor_numerico_invalido_e_descartado():
    mapa = _mapa(campos=[{"caminho": "v", "coluna": "v", "tipo": "numero"}])
    erro = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0, "v": "muito"})
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "valor_invalido"


def test_campo_ausente_vira_nulo_e_nao_erro():
    mapa = _mapa(campos=[{"caminho": "v", "coluna": "v", "tipo": "numero"}])
    evento = m.aplicar(mapa, {"ts": "2026-01-15T09:00:00", "lon": 0, "lat": 0})
    assert evento.atributos == {"v": None}


def test_registro_que_nao_e_objeto_e_recusado():
    erro = m.aplicar(_mapa(), [1, 2, 3])
    assert isinstance(erro, m.ErroEvento) and erro.motivo == "registro_tipo_errado"
