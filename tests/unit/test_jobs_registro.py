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


def test_tipos_de_prova_estao_registrados(monkeypatch):
    # o teto de 512 MB do fixture `ambiente` é artificial (serve aos testes de VALIDAÇÃO logo acima); aqui
    # importam-se os tipos DE VERDADE, que declaram até 1024 MB (exportacao.gerar, intercambio.exportar_*),
    # e o teto tem de ser o real da instalação — o padrão documentado em .env.exemplo.
    monkeypatch.setenv("PLAT_WORKER_MEMORIA_MB", "1536")
    cfg.obter.cache_clear()
    from app.jobs.tipos import REGISTRO

    assert {"prova.progresso", "prova.memoria", "prova.falha", "prova.ignora_cancelamento", "prova.pesado",
            "prova.tempo_esgotado", "jobs.expurgo"} <= set(REGISTRO)
    assert REGISTRO["prova.tempo_esgotado"].timeout_s == 5 and REGISTRO["prova.pesado"].pesado
    assert registro.ordem_perfil("admin") > registro.ordem_perfil("editor") > registro.ordem_perfil("campo")


def test_status_amostrar_esta_registrado(monkeypatch):
    # achado L7-03-f (comentário do commit acb7132f3, item A do achado): `app/status_tarefas.py` declara o
    # periódico `status.amostrar` mas NINGUÉM importava o módulo em `app/jobs/tipos.py` — o tipo nunca
    # entrava em REGISTRO e o job periódico (retrato de /status a cada 5 min) ficava órfão, nunca disparava.
    # Consertado somando `from app import status_tarefas` a `app/jobs/tipos.py` (mesmo padrão de
    # `app.jobs.seguranca`, registrado no mesmo commit). Prova de que o tipo agora entra em vigor:
    monkeypatch.setenv("PLAT_WORKER_MEMORIA_MB", "1536")
    cfg.obter.cache_clear()
    from app.jobs.tipos import REGISTRO

    assert "status.amostrar" in REGISTRO
    assert REGISTRO["status.amostrar"].perfil_minimo == "admin"
    from app.jobs.periodicos import PERIODICOS

    assert ("retrato operacional", "*/5 * * * *", "status.amostrar", {}) in PERIODICOS


def _periodicos_reais(monkeypatch) -> list[tuple[str, str, str, dict]]:
    """Importa app.jobs.tipos (soma REGISTRO e PERIODICOS de todo módulo da casa) sob o teto real de
    memória — mesma disciplina de test_tipos_de_prova_estao_registrados: sem isto, tipos reais como
    exportacao.gerar (até 1024 MB) esbarram no teto artificial de 512 MB do fixture `ambiente`."""
    monkeypatch.setenv("PLAT_WORKER_MEMORIA_MB", "1536")
    cfg.obter.cache_clear()
    from app.jobs.periodicos import PERIODICOS

    return list(PERIODICOS)


@pytest.mark.parametrize("indice", range(30))  # teto folgado: cresce sozinho conforme PERIODICOS cresce
def test_todo_periodico_tem_tipo_registrado(indice, monkeypatch):
    """Acréscimo ao achado L7-03-f (item A): dois órfãos já apareceram (status.amostrar,
    catalogo.notificacoes_expurgar) — um tipo em PERIODICOS cujo módulo nunca foi importado em
    app/jobs/tipos.py, ou cuja função nunca foi escrita, nunca dispara. Parametrizado sobre TODOS os
    períodicos hoje registrados (não uma lista fixa) para pegar o PRÓXIMO órfão sozinho, sem precisar
    editar este teste de novo."""
    periodicos = _periodicos_reais(monkeypatch)
    if indice >= len(periodicos):
        pytest.skip(f"só há {len(periodicos)} periódicos hoje")
    nome_p, cron, tipo, _parametros = periodicos[indice]
    from app.jobs.tipos import REGISTRO

    assert tipo in REGISTRO, f"periódico {nome_p!r} ({tipo}) sem tipo registrado em app.jobs.tipos"
    assert len(cron.split()) == 5, f"periódico {nome_p!r}: cron {cron!r} sem 5 campos"
