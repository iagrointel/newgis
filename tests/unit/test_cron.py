"""Cron com fuso (ADR 0003 seção 7): 5 expressões válidas com as ocorrências esperadas, 3 inválidas, intervalo
< 15 min recusado, dia de troca de horário sem ocorrência perdida ou duplicada, ultima_vencida. Sem banco."""

import datetime

import pytest

from app.jobs import agenda

UTC = datetime.UTC
BASE = datetime.datetime(2026, 9, 5, 13, 30, tzinfo=UTC)  # 10:30 em São Paulo


@pytest.mark.parametrize("expr,fuso,esperadas", [
    ("*/15 2 * * *", "America/Sao_Paulo", ["2026-09-06T02:00:00-03:00", "2026-09-06T02:15:00-03:00"]),
    ("30 3 * * *", "America/Sao_Paulo", ["2026-09-06T03:30:00-03:00", "2026-09-07T03:30:00-03:00"]),
    ("0 12 * * 1", "America/Sao_Paulo", ["2026-09-07T12:00:00-03:00", "2026-09-14T12:00:00-03:00"]),
    ("0 0 1 * *", "UTC", ["2026-10-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00"]),
    ("45 23 * * 0", "America/Manaus", ["2026-09-06T23:45:00-04:00", "2026-09-13T23:45:00-04:00"]),
])
def test_expressoes_validas(expr, fuso, esperadas):
    tz = agenda.validar_fuso(fuso)
    proximas = agenda.validar_cron(expr, fuso, BASE)
    assert [p.astimezone(tz).isoformat() for p in proximas[:2]] == esperadas
    assert all(p.tzinfo == UTC for p in proximas)


@pytest.mark.parametrize("expr", ["61 * * * *", "a b c d e", "* * * *", "", "*/15 * * * * *"])
def test_expressoes_invalidas(expr):
    with pytest.raises(agenda.ErroAgenda) as e:
        agenda.validar_cron(expr, "America/Sao_Paulo", BASE)
    assert e.value.codigo == "cron_invalida"


@pytest.mark.parametrize("expr", ["*/5 * * * *", "*/14 * * * *", "0,10 * * * *"])
def test_intervalo_menor_que_15_min_e_recusado(expr):
    with pytest.raises(agenda.ErroAgenda) as e:
        agenda.validar_cron(expr, "America/Sao_Paulo", BASE)
    assert e.value.codigo == "intervalo_minimo"


def test_fuso_invalido():
    with pytest.raises(agenda.ErroAgenda) as e:
        agenda.validar_cron("0 3 * * *", "Marte/Olympus", BASE)
    assert e.value.codigo == "fuso_invalido"


def test_troca_de_horario_nao_perde_nem_duplica():
    base = datetime.datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
    tz = agenda.validar_fuso("America/New_York")
    proximas = [p.astimezone(tz) for p in agenda.ocorrencias("30 2 * * *", "America/New_York", base, 3)]
    dias = [p.date().isoformat() for p in proximas]
    assert dias == ["2026-03-08", "2026-03-09", "2026-03-10"], proximas
    assert proximas[0].utcoffset() == datetime.timedelta(hours=-4)


def test_proxima_e_ultima_vencida():
    prox = agenda.proxima("*/15 * * * *", "UTC", BASE)
    assert prox == BASE + datetime.timedelta(minutes=15)
    assert agenda.ultima_vencida("*/15 * * * *", "UTC", BASE) == BASE
    assert agenda.ultima_vencida("*/15 * * * *", "UTC", BASE + datetime.timedelta(minutes=7)) == BASE


def test_relogio_de_teste_so_em_dev():
    class S:
        PLAT_RELOGIO_TESTE = "2026-01-02T03:04:05+00:00"
        producao = False

    assert agenda.agora_do_worker(S) == datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    S.producao = True
    assert (datetime.datetime.now(UTC) - agenda.agora_do_worker(S)).total_seconds() < 5
