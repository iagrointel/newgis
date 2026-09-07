"""Item L7-06-c: nível de log ajustável em tempo de execução, sem reinício (app/log.py).

O que se prova aqui: o filtro decide POR REGISTRO (não pelo `Logger.level`), o override mais específico
vence, o prazo expira, o arquivo é relido quando muda e — a cláusula do portão — mudar o nível muda o
VOLUME de linhas de fato emitidas pelo mesmo trecho de código, no mesmo processo, sem reiniciar nada.
"""

import io
import json
import logging
import os

import pytest

from app import log as plat_log


@pytest.fixture()
def arquivo_nivel(tmp_path, monkeypatch):
    caminho = tmp_path / "log_nivel.json"
    monkeypatch.setenv("PLAT_LOG_NIVEL_ARQUIVO", str(caminho))
    yield caminho


@pytest.fixture()
def raiz_limpa():
    """Guarda e devolve os handlers da raiz: `configurar()` mexe no logging do processo inteiro."""
    raiz = logging.getLogger()
    antes, nivel = list(raiz.handlers), raiz.level
    yield raiz
    raiz.handlers[:] = antes
    raiz.setLevel(nivel)


def _capturar(raiz) -> io.StringIO:
    """Troca o destino do handler JSON por um buffer, sem tirar o filtro (é ele que está em teste)."""
    handler = next(h for h in raiz.handlers if getattr(h, "_plat_json", False))
    buffer = io.StringIO()
    handler.stream = buffer
    return buffer


def _niveis_emitidos(buffer: io.StringIO) -> list[str]:
    return [json.loads(linha)["nivel"] for linha in buffer.getvalue().splitlines() if linha.strip()]


def test_definir_listar_remover_e_prazo(arquivo_nivel):
    assert plat_log.listar_overrides() == []
    registro = plat_log.definir_override("app.consulta", "debug", minutos=10)
    assert registro["nivel"] == "DEBUG" and registro["expira_em"]
    assert [o["componente"] for o in plat_log.listar_overrides()] == ["app.consulta"]

    # redefinir o MESMO componente substitui, não duplica
    plat_log.definir_override("app.consulta", "ERROR")
    ativos = plat_log.listar_overrides()
    assert len(ativos) == 1 and ativos[0]["nivel"] == "ERROR" and ativos[0]["expira_em"] is None

    assert plat_log.remover_override("app.consulta") is True
    assert plat_log.remover_override("app.consulta") is False
    assert plat_log.listar_overrides() == []
    with pytest.raises(ValueError):
        plat_log.definir_override("app.consulta", "TRACE")


def test_override_expirado_nao_conta(arquivo_nivel):
    plat_log.definir_override("app.x", "DEBUG", minutos=10)
    bruto = json.loads(arquivo_nivel.read_text(encoding="utf-8"))
    bruto[0]["expira_em"] = "2020-01-01T00:00:00+00:00"
    arquivo_nivel.write_text(json.dumps(bruto), encoding="utf-8")
    assert plat_log.listar_overrides() == []
    assert len(plat_log.listar_overrides(incluir_expirados=True)) == 1
    filtro = plat_log.FiltroNivelDinamico("WARNING")
    assert filtro.nivel_efetivo("app.x") == logging.WARNING


def test_mais_especifico_vence_e_rota_casa_por_prefixo(arquivo_nivel):
    plat_log.definir_override("*", "ERROR")
    plat_log.definir_override("rota:/api/tiles", "DEBUG")
    filtro = plat_log.FiltroNivelDinamico("INFO")
    assert filtro.nivel_efetivo("app.qualquer") == logging.ERROR
    assert filtro.nivel_efetivo("app.qualquer", "/api/tiles/1/2/3.pbf") == logging.DEBUG
    assert filtro.nivel_efetivo("app.qualquer", "/api/camadas") == logging.ERROR
    plat_log.definir_override("app.consulta", "WARNING")
    filtro = plat_log.FiltroNivelDinamico("INFO")
    # o logger filho herda do componente pai declarado
    assert filtro.nivel_efetivo("app.consulta.sql") == logging.WARNING
    assert filtro.nivel_efetivo("app.consultax") == logging.ERROR  # prefixo só vale com ponto


def test_volume_muda_em_tempo_de_execucao_sem_reiniciar(arquivo_nivel, raiz_limpa):
    """Cláusula do portão: 'mudar nível em runtime muda o volume (medido)'. Mesmo processo, mesmo
    handler, mesmas 40 chamadas de log — só o arquivo de override muda entre as três medidas."""
    plat_log.configurar("WARNING")
    buffer = _capturar(raiz_limpa)
    registrador = logging.getLogger("app.medida_volume")

    def emitir_lote():
        for _ in range(10):
            registrador.debug("linha de depuração")
            registrador.info("linha informativa")
            registrador.warning("linha de aviso")
            registrador.error("linha de erro")

    emitir_lote()
    padrao = len(_niveis_emitidos(buffer))

    plat_log.definir_override("app.medida_volume", "DEBUG")
    buffer.seek(0), buffer.truncate(0)
    emitir_lote()
    com_debug = _niveis_emitidos(buffer)

    plat_log.definir_override("app.medida_volume", "ERROR")
    buffer.seek(0), buffer.truncate(0)
    emitir_lote()
    com_erro = len(_niveis_emitidos(buffer))

    assert padrao == 20, f"WARNING+ deveria emitir 20 das 40, emitiu {padrao}"
    assert len(com_debug) == 40 and set(com_debug) == {"DEBUG", "INFO", "WARNING", "ERROR"}
    assert com_erro == 10
    medida = {"chamadas_por_lote": 40, "linhas_no_padrao_WARNING": padrao,
              "linhas_com_override_DEBUG": len(com_debug), "linhas_com_override_ERROR": com_erro}
    assert medida["linhas_com_override_DEBUG"] > medida["linhas_no_padrao_WARNING"] > medida["linhas_com_override_ERROR"]


def test_arquivo_ilegivel_nao_derruba_nem_prende_o_nivel(arquivo_nivel, raiz_limpa):
    arquivo_nivel.write_text("{isto não é json", encoding="utf-8")
    filtro = plat_log.FiltroNivelDinamico("INFO")
    assert filtro.nivel_efetivo("app.x") == logging.INFO
    os.remove(arquivo_nivel)
    assert filtro.nivel_efetivo("app.x") == logging.INFO
