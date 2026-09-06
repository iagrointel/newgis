"""Trava de regressão: o advisory lock "1 pesado por vez" (`app/jobs/worker.py::_pegar`) é um recurso
PARTILHADO por todo o banco (achado do gerente 06/09, junto ao laudo `ataque-g3-ADVERSARIO.md`) — nome do
lock e disciplina de soltar são as duas metades do mesmo defeito.

Metade 1 (namespace): o nome fixo `"plat.job.pesado"` fazia produção, homologação e toda trilha (schema
diferente, banco `iagro_sat` igual) disputarem o MESMO semáforo — `LOCK_PESADO` agora carrega
`settings.PLAT_SCHEMA`.

Metade 2 (disciplina de soltar), o achado NOVO, medido ao vivo em 06/09: a trilha `destrava` (backend
2796174, `plat_tdestrava_worker`) ficou HORAS segurando o lock com a fila da própria base VAZIA, porque
`_pegar()` só recalculava `pesado_ok` dentro de `if not self.lock_pesado:` — se o lock já estava preso de
uma volta anterior, `pesado_ok` ficava em `False` pelo resto da função, e as duas únicas chamadas de
`_soltar_pesado()` exigem `pesado_ok` verdadeiro. Um worker ocioso que segurou o lock uma vez nunca mais o
soltava sozinho, e travava "1 pesado por vez" para toda trilha e para produção (advisory lock é do BANCO,
não do schema). `pesado_ok` agora É `self.lock_pesado`, sempre: a decisão de soltar usa o estado real.

Metade 3 (achada testando as duas primeiras, rodando a suíte inteira): advisory lock do Postgres é
REENTRANTE na mesma sessão. Um worker com `PLAT_WORKER_PROCESSOS > 1` que já tinha um pesado em
`self.filhos` continuava pedindo `job_pegar(nome, pesado_ok=True)` para a vaga seguinte só porque
`self.lock_pesado` era `True` — e recebia um SEGUNDO pesado para si mesmo, rodando os dois em paralelo
dentro do MESMO worker (`tests/api/jobs/test_jobs_fila.py::test_pesado_nunca_em_paralelo_com_pesado`
reprovou com isso, sem nenhuma outra trilha envolvida). `pesado_ok` agora exige as duas coisas: o lock
preso E nenhum pesado nosso já em curso."""

from __future__ import annotations

from app import limites  # noqa: F401 — garante settings carregado antes do import de worker
from app.jobs import worker as mod_worker


class WorkerFalso(mod_worker.Worker):
    """Mesma classe, sem tocar banco nem processo: `um`/`sql` são gravadores em memória."""

    def __init__(self, respostas: dict[str, dict | None]):
        # não chama Worker.__init__ (abriria conexão/porta); só o que _pegar/_soltar_pesado usam.
        self.nome = "teste:1"
        self.processos = 1
        self.filhos = {}
        self.parando = False
        self.lock_pesado = False
        self.chamadas: list[str] = []
        self.pedidos_job_pegar: list[bool] = []
        self._respostas = respostas

    def um(self, consulta: str, params=()) -> dict | None:
        self.chamadas.append(" ".join(consulta.split()))
        if "pg_try_advisory_lock" in consulta:
            return self._respostas.get("acquire")
        if "job_pegar" in consulta:
            self.pedidos_job_pegar.append(bool(params[1]))  # (nome, pesado_ok)
            return self._respostas.get("job")
        raise AssertionError(f"consulta inesperada: {consulta}")

    def sql(self, consulta: str, params=()) -> list[dict]:
        self.chamadas.append(" ".join(consulta.split()))
        return []


def test_worker_ocioso_com_lock_preso_de_volta_anterior_solta_sozinho():
    """Cenário exato medido em produção: `self.lock_pesado` já é True (lock preso numa volta anterior, sem
    nenhum filho pesado em curso) e a fila não tem NADA pendente. `_pegar()` tem de soltar o lock — sem
    isso, nenhuma trilha e nem produção completam um job pesado enquanto este worker existir."""
    w = WorkerFalso({"job": None})
    w.lock_pesado = True  # o defeito só aparece quando o lock JÁ estava preso antes desta chamada
    w._pegar()
    assert w.lock_pesado is False, "worker ocioso continuou segurando o advisory lock de 'pesado'"
    assert any("pg_advisory_unlock" in c for c in w.chamadas), "nenhum pg_advisory_unlock foi emitido"
    # o lock já estava preso: não deve tentar adquirir de novo antes de decidir soltar
    assert not any("pg_try_advisory_lock" in c for c in w.chamadas), (
        "reaqueriu o lock que já tinha, em vez de reconhecer o estado atual")


def test_worker_com_lock_preso_e_job_leve_disponivel_solta_e_lanca():
    """Mesmo ponto de partida (lock preso de uma volta anterior), mas com um job LEVE disponível: o worker
    tem de pegar o job (não precisa do lock para ele) e soltar o lock que não está usando."""
    job_leve = {"id": "11111111-1111-1111-1111-111111111111", "pesado": False, "tipo": "prova.progresso"}
    w = WorkerFalso({"job": job_leve})
    lancados = []

    def _lancar_falso(job):
        # marca a "vaga" ocupada para o while de _pegar() parar, como o fork de verdade faria
        lancados.append(job)
        w.filhos[1] = object()

    w._lancar = _lancar_falso
    w.lock_pesado = True
    w._pegar()
    assert lancados == [job_leve], "o job leve disponível não foi lançado"
    assert w.lock_pesado is False, "o lock ficou preso mesmo sem nenhum job pesado em curso"
    assert any("pg_advisory_unlock" in c for c in w.chamadas)


def test_worker_com_lock_preso_e_pesado_em_curso_nao_solta():
    """Guarda-costas do conserto: se HÁ um filho pesado de verdade em curso (o caso comum e correto), o
    worker NUNCA deve soltar o lock só porque esta volta de `_pegar()` não achou outro job para o segundo
    processo."""
    Filho = mod_worker.Filho
    filho_pesado = Filho(pid=999, job={"id": "x", "pesado": True}, pipe_r=-1)
    w = WorkerFalso({"job": None})
    w.processos = 2
    w.filhos = {999: filho_pesado}
    w.lock_pesado = True
    w._pegar()
    assert w.lock_pesado is True, "soltou o lock com um job pesado de verdade ainda em curso"
    assert not any("pg_advisory_unlock" in c for c in w.chamadas)


def test_worker_com_pesado_em_curso_nunca_pede_um_segundo_pesado_para_si():
    """Segunda metade do mesmo defeito, achada testando a primeira: advisory lock do Postgres é REENTRANTE
    na mesma sessão (`pg_try_advisory_lock` devolve `true` de novo se a MESMA conexão já segura o lock).
    Um worker com `PLAT_WORKER_PROCESSOS > 1` (`worker_extra`,
    tests/api/jobs/test_jobs_fila.py::test_pesado_nunca_em_paralelo_com_pesado) que já tem UM pesado em
    `self.filhos` não pode pedir `job_pegar(nome, pesado_ok=True)` de novo para a segunda vaga — pediria (e
    receberia) um SEGUNDO pesado para si mesmo, rodando os dois em paralelo dentro do MESMO processo, sem
    nenhuma outra trilha envolvida. `pesado_ok` só é verdadeiro quando o lock está preso E não há pesado
    nosso em curso."""
    Filho = mod_worker.Filho
    filho_pesado = Filho(pid=999, job={"id": "x", "pesado": True}, pipe_r=-1)
    job_leve = {"id": "22222222-2222-2222-2222-222222222222", "pesado": False, "tipo": "prova.progresso"}
    w = WorkerFalso({"job": job_leve})
    w.processos = 2
    w.filhos = {999: filho_pesado}
    w.lock_pesado = True
    lancados = []
    w._lancar = lambda job: (lancados.append(job), w.filhos.__setitem__(1000, object()))
    w._pegar()
    assert w.pedidos_job_pegar == [False], (
        f"pediu job_pegar com pesado_ok={w.pedidos_job_pegar} enquanto já tinha um pesado em curso — "
        "isso deixaria o worker pegar um segundo pesado para si mesmo")
    assert lancados == [job_leve]
    assert w.lock_pesado is True, "soltou o lock com o pesado original ainda em curso"
