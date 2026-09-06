"""Portão literal L0-05-b (achado do testador T3: TETO_LOG/BLOCO_SUPRIMIDO existiam em ContextoJob.log() desde a
entrega original, mas nenhum teste chamava 10 mil linhas para provar o resumo). Sem banco: `ContextoJob.db()` é
substituído por um cursor falso que só grava (nivel, mensagem); os limites de produção (10.000/1.000) são
monkeypatchados para valores pequenos para o teste rodar em milissegundos, e um segundo teste confirma que as
constantes de produção continuam 10_000/1_000 (documentado no módulo) — a lógica é a mesma, só a escala muda."""

import uuid
from pathlib import Path

import app.jobs.contexto_job as cj


class _CursorFalso:
    def __init__(self, sink: list):
        self.sink = sink

    def execute(self, sql, params=()):
        # (job_id, tenant_id, nivel, mensagem) — só nivel/mensagem interessam ao teste
        self.sink.append((params[2], params[3]))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _ContextoGerenciadorFalso:
    def __init__(self, sink: list):
        self.sink = sink

    def __enter__(self):
        return _CursorFalso(self.sink)

    def __exit__(self, *exc):
        return False


def _ctx_com_sink(monkeypatch, teto: int, bloco: int) -> tuple[cj.ContextoJob, list]:
    monkeypatch.setattr(cj, "TETO_LOG", teto)
    monkeypatch.setattr(cj, "BLOCO_SUPRIMIDO", bloco)
    job = {"id": uuid.uuid4(), "tenant_id": 1, "usuario_id": 1, "tipo": "teste.log", "tentativa": 1}
    ctx = cj.ContextoJob(job, Path("/tmp"), "worker-teste")
    sink: list = []
    monkeypatch.setattr(ctx, "db", lambda: _ContextoGerenciadorFalso(sink))
    return ctx, sink


def test_log_ate_o_teto_grava_toda_linha(monkeypatch):
    ctx, sink = _ctx_com_sink(monkeypatch, teto=20, bloco=5)
    for i in range(20):
        ctx.log("INFO", f"linha {i}")
    assert len(sink) == 20
    assert all(nivel == "INFO" for nivel, _ in sink)


def test_log_acima_do_teto_e_resumido_em_blocos(monkeypatch):
    """10 mil linhas (aqui: teto=20, bloco=5, escala reduzida) → só a linha nº bloco de cada excedente vira
    resumo AVISO; as demais são suprimidas (nenhuma escrita no banco)."""
    ctx, sink = _ctx_com_sink(monkeypatch, teto=20, bloco=5)
    total_chamadas = 20 + 5 * 3 + 2  # 3 resumos completos + 2 linhas suprimidas ainda sem fechar o próximo bloco
    for i in range(total_chamadas):
        ctx.log("INFO", f"linha {i}")
    # 20 linhas normais + 3 resumos (a cada 5 suprimidas); as 2 últimas suprimidas não geram linha ainda
    assert len(sink) == 20 + 3
    resumos = sink[20:]
    for nivel, mensagem in resumos:
        assert nivel == "AVISO"
        assert mensagem == "5 linhas suprimidas (teto de 20 linhas por job)"
    assert ctx._linhas_log == total_chamadas
    assert ctx._suprimidas == total_chamadas - 20


def test_log_nivel_desconhecido_vira_info(monkeypatch):
    ctx, sink = _ctx_com_sink(monkeypatch, teto=100, bloco=100)
    ctx.log("bagunça", "x")
    assert sink[-1][0] == "INFO"


def test_constantes_de_producao_sao_10000_e_1000():
    """Documentado no módulo (docstring) e no ADR 0003 seção 3.2: se alguém mudar o número aqui sem mudar o
    texto, este teste é o primeiro a acusar — nunca deixamos a constante real ir para 10001/999 por engano."""
    assert cj.TETO_LOG == 10_000
    assert cj.BLOCO_SUPRIMIDO == 1_000
