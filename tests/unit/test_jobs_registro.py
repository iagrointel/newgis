"""Registro de tipos (ADR 0003 seção 3.1): nome repetido, nome fora do padrão, memoria_mb acima do teto, executor
'gpu' sem PLAT_GPU_SSH, gpu sem pesado, JSON Schema gerado, descrição para /api/jobs/tipos. Sem banco."""

import pytest
from pydantic import BaseModel

from app import settings as cfg
from app.jobs import registro

AMBIENTE = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat", "PLAT_SECRET": "ab" * 32, "PLAT_AMBIENTE": "dev",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido", "PLAT_WORKER_MEMORIA_MB": "512",
}


class P(BaseModel):
    n: int = 1


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    # Os tipos REAIS da casa entram no registro ANTES do teto artificial de 512 MB e antes do retrato
    # `antes`. Sem isto acontecem dois estragos: a primeira importação de app.jobs.tipos dentro de um teste
    # deste arquivo esbarra no teto artificial (amc.gerar_unidades pede 768 MB, amc.recombinar pede o
    # orçamento do motor) e falha com ErroRegistro; e a limpeza do fim do teste, que só deveria tirar os
    # tipos sintéticos, arrancaria do registro global os tipos reais importados durante ele — o teste
    # seguinte, em qualquer arquivo, encontraria o registro incompleto.
    import app.jobs.tipos  # noqa: F401

    for k, v in AMBIENTE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PLAT_GPU_SSH", raising=False)
    cfg.obter.cache_clear()
    antes = set(registro.REGISTRO)
    yield
    for nome in set(registro.REGISTRO) - antes:
        registro.REGISTRO.pop(nome, None)
    cfg.obter.cache_clear()


def test_registra_e_descreve():
    @registro.tarefa(nome="teste.unidade", descricao="d", parametros=P, memoria_mb=256, timeout_s=10)
    def f(ctx, n: int = 1):
        return {"n": n}

    t = registro.REGISTRO["teste.unidade"]
    assert t.funcao is f and t.pesado is False and t.executor == "local" and t.perfil_minimo == "editor"
    d = registro.descrever(t)
    assert d["parametros_schema"]["properties"]["n"]["type"] == "integer"
    assert registro.validar_parametros(t, {"n": "3"}) == {"n": 3}
    assert registro.chave_de(t, {"n": 3}) is None


def test_nome_repetido_e_recusado():
    registro.tarefa(nome="teste.repetido", descricao="d", parametros=P)(lambda ctx: {})
    with pytest.raises(registro.ErroRegistro, match="repetido"):
        registro.tarefa(nome="teste.repetido", descricao="d", parametros=P)


@pytest.mark.parametrize("nome", ["Teste.x", "teste", "teste..x", "1teste.x", "teste.X"])
def test_nome_fora_do_padrao(nome):
    with pytest.raises(registro.ErroRegistro, match="padrão"):
        registro.tarefa(nome=nome, descricao="d", parametros=P)


def test_memoria_acima_do_teto_e_abaixo_do_minimo():
    with pytest.raises(registro.ErroRegistro, match="PLAT_WORKER_MEMORIA_MB"):
        registro.tarefa(nome="teste.memoria_alta", descricao="d", parametros=P, pesado=True, memoria_mb=513)
    with pytest.raises(registro.ErroRegistro, match="fora de"):
        registro.tarefa(nome="teste.memoria_baixa", descricao="d", parametros=P, memoria_mb=64)


def test_leve_nao_passa_de_1024_e_gpu_exige_pesado_e_chave(monkeypatch):
    monkeypatch.setenv("PLAT_WORKER_MEMORIA_MB", "4096")
    cfg.obter.cache_clear()
    with pytest.raises(registro.ErroRegistro, match="pesado=True"):
        registro.tarefa(nome="teste.leve_grande", descricao="d", parametros=P, memoria_mb=2048)
    with pytest.raises(registro.ErroRegistro, match="pesado=True"):
        registro.tarefa(nome="teste.gpu_leve", descricao="d", parametros=P, executor="gpu")
    with pytest.raises(registro.ErroRegistro, match="PLAT_GPU_SSH"):
        registro.tarefa(nome="teste.gpu", descricao="d", parametros=P, executor="gpu", pesado=True)
    monkeypatch.setenv("PLAT_GPU_SSH", "gpu")
    cfg.obter.cache_clear()
    registro.tarefa(nome="teste.gpu_ok", descricao="d", parametros=P, executor="gpu", pesado=True)(lambda ctx: {})
    assert registro.REGISTRO["teste.gpu_ok"].executor == "gpu"


def test_validacoes_simples():
    for kw, texto in ((dict(timeout_s=0), "timeout_s"), (dict(tentativas=0), "tentativas"),
                      (dict(executor="nuvem"), "executor"), (dict(perfil_minimo="deus"), "perfil_minimo")):
        with pytest.raises(registro.ErroRegistro, match=texto):
            registro.tarefa(nome="teste.simples", descricao="d", parametros=P, **kw)
    with pytest.raises(registro.ErroRegistro, match="pydantic"):
        registro.tarefa(nome="teste.simples", descricao="d", parametros=dict)


def test_tipos_de_prova_estao_registrados():
    from app.jobs.tipos import REGISTRO

    assert {"prova.progresso", "prova.memoria", "prova.falha", "prova.ignora_cancelamento", "prova.pesado",
            "prova.tempo_esgotado", "jobs.expurgo"} <= set(REGISTRO)
    assert REGISTRO["prova.tempo_esgotado"].timeout_s == 5 and REGISTRO["prova.pesado"].pesado
    assert registro.ordem_perfil("admin") > registro.ordem_perfil("editor") > registro.ordem_perfil("campo")
