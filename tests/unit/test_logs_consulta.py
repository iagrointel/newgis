"""Item L7-06-c: `plat logs --req-id` reúne as linhas dos serviços do mesmo pedido, em ordem de relógio.

Aqui a prova é da REUNIÃO e da ORDEM sobre linhas no formato real de cada serviço (nginx JSON do
`log_format plat_json`, linha JSON da API e do worker, linha de erro do Postgres com `app=plat:<id>`).
A prova de que os serviços de verdade emitem essas linhas está em tests/api/test_logs_req_id_banca.py.
"""

import argparse
import json

import pytest

from app import logs_consulta
from scripts import plat as cli

REQ = "a1b2c3d4e5f60718"
OUTRO = "ffffffffffffffff"


def _escrever(caminho, linhas):
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


@pytest.fixture()
def banca(tmp_path):
    """Um pedido de tile que falha: nginx recebe, API tenta, Postgres recusa, worker registra a limpeza."""
    nginx = _escrever(tmp_path / "nginx.log", [
        json.dumps({"ts": "2026-09-07T12:00:00+00:00", "req_id": REQ, "rota": "/tiles/teste/1/2/3.pbf",
                    "status": 500, "upstream": "127.0.0.1:8151"}),
        json.dumps({"ts": "2026-09-07T12:00:09+00:00", "req_id": OUTRO, "rota": "/api/eu", "status": 200}),
    ])
    api = _escrever(tmp_path / "api.log", [
        json.dumps({"ts": "2026-09-07T12:00:00.100+00:00", "nivel": "ERROR", "msg": "tile falhou",
                    "req_id": REQ, "rota": "/tiles/teste/1/2/3.pbf"}),
        json.dumps({"ts": "2026-09-07T12:00:00.050+00:00", "nivel": "INFO", "msg": "tile pedido",
                    "req_id": REQ, "rota": "/tiles/teste/1/2/3.pbf"}),
        json.dumps({"ts": "2026-09-07T12:00:09.100+00:00", "nivel": "INFO", "msg": "outro", "req_id": OUTRO}),
    ])
    postgres = _escrever(tmp_path / "postgres.log", [
        f"2026-09-07 12:00:00.080 UTC [900] db=iagro_sat,user=plat_app,app=plat:{REQ[:12]},client=127.0.0.1 "
        "ERROR:  relation \"plat.camada_inexistente\" does not exist",
        "2026-09-07 12:00:09.050 UTC [901] db=iagro_sat,user=plat_app,app=plat:ffffffffffff,client=127.0.0.1 LOG: ok",
    ])
    worker = _escrever(tmp_path / "worker.log", [
        json.dumps({"ts": "2026-09-07T12:00:00.300+00:00", "nivel": "WARNING", "msg": "job de tile descartado",
                    "req_id": REQ, "job_id": 7}),
    ])
    return (f"nginx=arquivo:{nginx},api=arquivo:{api},postgres=arquivo:{postgres},worker=arquivo:{worker}")


def test_reune_os_quatro_servicos_em_ordem(banca):
    linhas = logs_consulta.reunir(REQ, especificacao=banca)
    assert [linha.servico for linha in linhas] == ["nginx", "api", "postgres", "api", "worker"]
    assert {linha.servico for linha in linhas} == {"nginx", "api", "postgres", "worker"}, "4 serviços"
    horarios = [linha.em for linha in linhas]
    assert horarios == sorted(horarios), "as linhas têm de sair em ordem de relógio"
    assert all(REQ in linha.texto or REQ[:12] in linha.texto for linha in linhas)


def test_nao_traz_linha_de_outro_pedido(banca):
    linhas = logs_consulta.reunir(REQ, especificacao=banca)
    assert not any(OUTRO in linha.texto for linha in linhas)
    outras = logs_consulta.reunir(OUTRO, especificacao=banca)
    assert [linha.servico for linha in outras] == ["nginx", "postgres", "api"]
    assert not any(REQ in linha.texto for linha in outras)


def test_postgres_casa_pelo_prefixo_de_12_do_application_name(banca):
    """`application_name` só leva 12 hex do identificador (app/log.py::nome_aplicacao_pg); sem o segundo
    anzol a linha do Postgres se perderia, e a correlação com o banco morreria."""
    postgres = [linha for linha in logs_consulta.reunir(REQ, especificacao=banca) if linha.servico == "postgres"]
    assert len(postgres) == 1 and f"app=plat:{REQ[:12]}" in postgres[0].texto
    assert logs_consulta.anzois(REQ) == (REQ, REQ[:12])


def test_req_id_invalido_e_fonte_invalida_sao_recusados(banca):
    for ruim in ("", "curto", "zzzzzzzzzzzzzzzz", "a1b2c3d4; rm -rf /"):
        with pytest.raises(ValueError):
            logs_consulta.reunir(ruim, especificacao=banca)
    for ruim in ("api=coisa:/x", "=journal:u", "api=journal:"):
        with pytest.raises(ValueError):
            logs_consulta.fontes(ruim)


def test_fonte_inexistente_nao_derruba_a_consulta(tmp_path):
    assert logs_consulta.reunir(REQ, especificacao=f"api=arquivo:{tmp_path}/nao_existe.log") == []


def test_cli_imprime_em_ordem_e_devolve_1_quando_nao_acha(banca, capsys, monkeypatch):
    monkeypatch.setenv("PLAT_LOG_FONTES", banca)
    assert cli.principal(["logs", "--req-id", REQ, "--json"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert [linha["servico"] for linha in saida] == ["nginx", "api", "postgres", "api", "worker"]
    assert cli.principal(["logs", "--req-id", "0" * 16]) == 1
    assert cli.principal(["logs", "--req-id", "nao-hexadecimal"]) == 2


def test_cli_converte_prazo():
    assert cli.minutos("10min") == 10.0
    assert cli.minutos("30s") == 0.5
    assert cli.minutos("2h") == 120.0
    assert cli.minutos("7") == 7.0
    with pytest.raises(argparse.ArgumentTypeError):
        cli.minutos("depois")
