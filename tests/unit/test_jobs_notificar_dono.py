"""Worker._notificar_dono (item L0-03-k, achado G2-7): `app/notificacoes.TIPOS` já declarava "jobs/concluido" e
"jobs/falhou" desde a primeira passagem, mas nenhum código chamava `plat.notificar` quando um job terminava — o
worker terminava o job e ninguém era avisado. Sem banco: `Worker.um` é substituído por um espião que só grava
a consulta e os parâmetros; o que se prova aqui é que a SQL emitida é a certa (função, ordem dos parâmetros,
tipo, chave de dedup, teto por minuto), não o efeito no banco (isso é tests/api/catalogo/test_notificacoes.py,
que já cobre dedup/RLS/teto por minuto para a mesma função `plat.notificar`)."""

import uuid

import pytest

from app import limites
from app.jobs.worker import Worker


def _worker_espiao(monkeypatch):
    chamadas = []

    def um_falso(self, consulta, params=()):
        chamadas.append((consulta, params))
        return {"id": str(uuid.uuid4())}

    monkeypatch.setattr(Worker, "um", um_falso)
    w = Worker.__new__(Worker)  # sem __init__: não abre conexão nem processos
    w.nome = "teste-worker:1"
    return w, chamadas


def _job(usuario_id=42, tenant_id=7, tipo="prova.progresso"):
    return {"id": uuid.uuid4(), "tenant_id": tenant_id, "usuario_id": usuario_id, "tipo": tipo}


def test_job_concluido_chama_plat_notificar_com_tipo_e_chave_certos(monkeypatch):
    w, chamadas = _worker_espiao(monkeypatch)
    job = _job()
    w._notificar_dono(job, "concluido")
    assert len(chamadas) == 1
    consulta, params = chamadas[0]
    assert "plat.notificar" in consulta
    tenant_id, usuario_id, tipo, titulo, chave, corpo, url, alvo_tipo, alvo_id, teto = params
    assert (tenant_id, usuario_id) == (job["tenant_id"], job["usuario_id"])
    assert tipo == "jobs/concluido"
    assert chave == f"jobs/concluido:{job['id']}"
    assert alvo_tipo == "job" and alvo_id == str(job["id"])
    assert teto == limites.NOTIFICACOES_POR_MINUTO
    assert job["tipo"] in titulo


def test_job_falhou_usa_tipo_e_chave_de_falha(monkeypatch):
    w, chamadas = _worker_espiao(monkeypatch)
    job = _job()
    w._notificar_dono(job, "falhou")
    _, params = chamadas[0]
    assert params[2] == "jobs/falhou"
    assert params[4] == f"jobs/falhou:{job['id']}"


def test_job_sem_dono_nao_notifica(monkeypatch):
    w, chamadas = _worker_espiao(monkeypatch)
    job = _job(usuario_id=None)
    w._notificar_dono(job, "concluido")
    assert chamadas == [], "job periódico/sistema (sem usuario_id) não deveria gerar chamada nenhuma"


def test_falha_ao_notificar_nao_propaga(monkeypatch):
    """Notificar é efeito colateral de o job ter terminado; um erro aqui não pode dar a impressão de que o
    job em si falhou (a mensagem de log é o único efeito, não uma exceção subindo)."""
    w = Worker.__new__(Worker)
    w.nome = "teste-worker:1"

    def um_explode(self, consulta, params=()):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(Worker, "um", um_explode)
    w._notificar_dono(_job(), "concluido")  # não deve levantar


@pytest.mark.parametrize("estado", ["concluido", "falhou", "cancelado"])
def test_terminar_so_notifica_em_concluido_ou_falhou(monkeypatch, estado):
    """`_terminar` só chama `_notificar_dono` para os dois estados finais que o usuário quer saber; cancelado é
    pedido pelo próprio usuário (não precisa de aviso)."""
    w = Worker.__new__(Worker)
    w.nome = "teste-worker:1"
    chamado = []
    monkeypatch.setattr(Worker, "_notificar_dono", lambda self, job, est: chamado.append(est))
    monkeypatch.setattr(Worker, "um", lambda self, consulta, params=(): {"ok": True})
    w._terminar(_job(), estado, None, None, {})
    assert chamado == ([estado] if estado in ("concluido", "falhou") else [])


def test_terminar_nao_notifica_quando_job_terminar_recusa(monkeypatch):
    """job_terminar devolve ok=False quando o job já não era deste worker (ex.: devolvido por outro caminho
    antes); sem sucesso na transição não há por que notificar."""
    w = Worker.__new__(Worker)
    w.nome = "teste-worker:1"
    chamado = []
    monkeypatch.setattr(Worker, "_notificar_dono", lambda self, job, est: chamado.append(est))
    monkeypatch.setattr(Worker, "um", lambda self, consulta, params=(): {"ok": False})
    w._terminar(_job(), "concluido", None, None, {})
    assert chamado == []
