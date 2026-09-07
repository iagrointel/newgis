"""Worker da fila (`python -m app.jobs.worker`; unidade plat-worker; ADR 0003 seção 4). Processo pai com UMA conexão
própria autocommit (nunca o pool de app.db) como a role plat_worker (PLAT_DSN_WORKER; única com EXECUTE nas funções
que mudam estado, migração 006) em LISTEN plat_worker; identidade `<PLAT_WORKER_NOME ou hostname>:<pid>` (012: dois
processos com o mesmo nome-base nunca roubam jobs um do outro; a ceifa é só por heartbeat vencido); laço de ≤ 1 s por
select(); job_pegar por
SKIP LOCKED; fork por job com pipe; heartbeat de 10 s; cancelamento por escalonamento (30 s SIGTERM, +10 s SIGKILL);
timeout_s; "1 pesado por vez" por advisory lock de sessão; ceifa de órfãos a cada 30 s; relógio das agendas; parada
limpa (SIGTERM: devolve os jobs com reinicios += 1, SIGTERM ao filho, 20 s, SIGKILL). /saude em 127.0.0.1:8153
atendido no próprio laço (sem thread: fork com threads é armadilha)."""

import datetime
import json
import logging
import os
import platform
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

from app import log as plat_log
from app import metricas
from app.jobs import agenda as mod_agenda
from app.jobs import filho as mod_filho
from app.jobs.tipos import REGISTRO
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings
from app.versao import git_sha_curto, versao

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("plat.worker")

TICK_S = 1.0
HEARTBEAT_S = 10
CEIFA_S = 30
LIMITE_SEM_SINAL_S = 60
LIMITE_WORKER_S = 90
GRACA_CANCELAMENTO_S = 30
GRACA_KILL_S = 10
ESPERA_PARADA_S = 20
LOCK_PESADO = "plat.job.pesado"  # nome-base; a chave real leva o schema (ver _chave_pesado)


def _chave_pesado() -> str:
    """07/09 (achado do item L2-15-a + classe F5): a chave era CONSTANTE no cluster inteiro, então o worker
    de uma trilha isolada segurava o "1 pesado por vez" de produção e de todas as outras trilhas. A chave
    leva o schema do ambiente: cada base tem a sua vez de pesado."""
    from app.settings import settings

    return f"{settings.PLAT_SCHEMA}.job.pesado"
UTC = datetime.UTC


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def rss_kb() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("VmRSS:"):
                    return int(linha.split()[1])
    except OSError:
        pass
    return 0


class Filho:
    __slots__ = ("pid", "job", "pipe_r", "buffer", "eof", "iniciado", "ultimo_hb", "cancel_em", "sigterm_em",
                 "sigkill_em", "motivo", "pesado")

    def __init__(self, pid: int, job: dict, pipe_r: int):
        self.pid = pid
        self.job = job
        self.pipe_r = pipe_r
        self.buffer = b""
        self.eof = False
        self.iniciado = time.monotonic()
        self.ultimo_hb = self.iniciado
        self.cancel_em: float | None = None
        self.sigterm_em: float | None = None
        self.sigkill_em: float | None = None
        self.motivo: str | None = None
        self.pesado = bool(job["pesado"])


class Worker:
    def __init__(self):
        # identidade única por processo (correção T2 (2)): dois workers com o mesmo nome-base nunca se confundem
        self.nome_base = settings.PLAT_WORKER_NOME or socket.gethostname()
        self.nome = f"{self.nome_base}:{os.getpid()}"
        self.processos = settings.PLAT_WORKER_PROCESSOS
        self.dir_jobs = Path(settings.PLAT_JOBS_DIR) if settings.PLAT_JOBS_DIR else ROOT / "var" / "jobs"
        self.max_reinicios = settings.PLAT_JOB_MAX_REINICIOS
        self.porta = urlparse(settings.PLAT_WORKER_URL or "http://127.0.0.1:8153").port or 8153
        self.filhos: dict[int, Filho] = {}
        self.parando = False
        self.lock_pesado = False
        self.con = None
        self.sock: socket.socket | None = None
        self.acorda_r = self.acorda_w = -1  # self-pipe: SIGCHLD/SIGTERM acordam o select (nunca esperar o tick de 1 s)
        self.ultimo_hb = 0.0
        self.ultima_ceifa = 0.0
        self.ultimo_tick_ms = 0.0
        self.gdal = self._versao_gdal() if any("gdal" in t.ferramentas for t in REGISTRO.values()) else None

    # ---------------------------------------------------------------- banco
    def _conectar(self) -> None:
        if not settings.PLAT_DSN_WORKER:
            raise RuntimeError("chave obrigatória ausente para o worker: PLAT_DSN_WORKER "
                               "(role plat_worker; o install.sh grava)")
        self.con = psycopg2.connect(settings.PLAT_DSN_WORKER, cursor_factory=CursorSchemaAmbiente)
        self.con.autocommit = True
        with self.con.cursor() as cur:
            cur.execute(f"SET search_path = {settings.PLAT_SCHEMA}, public")
            cur.execute(f"LISTEN {settings.PLAT_CANAL_WORKER}")
        self.lock_pesado = False  # sessão nova: o advisory lock anterior morreu com a sessão anterior

    def sql(self, consulta: str, params=()) -> list[dict]:
        """Executa uma consulta; só a CONEXÃO é refeita quando fechada (a consulta nunca é repetida às cegas)."""
        if self.con is None or self.con.closed:
            self._conectar()
        with self.con.cursor() as cur:
            cur.execute(consulta, params)
            return [dict(r) for r in cur.fetchall()] if cur.description else []

    def um(self, consulta: str, params=()) -> dict | None:
        linhas = self.sql(consulta, params)
        return linhas[0] if linhas else None

    # ---------------------------------------------------------------- partida e laço
    def rodar(self) -> int:
        self.dir_jobs.mkdir(parents=True, exist_ok=True)
        signal.signal(signal.SIGTERM, self._ao_sinal)
        signal.signal(signal.SIGINT, self._ao_sinal)
        signal.signal(signal.SIGCHLD, self._ao_sigchld)
        self.acorda_r, self.acorda_w = os.pipe()
        os.set_blocking(self.acorda_r, False)
        os.set_blocking(self.acorda_w, False)
        signal.set_wakeup_fd(self.acorda_w, warn_on_full_buffer=False)
        self._abrir_saude()
        self._conectar()
        self.sql("SELECT plat.worker_registrar(%s, %s, %s, %s, %s)",
                 (self.nome, os.getpid(), versao(), git_sha_curto(), self.processos))
        # ceifa na partida só por heartbeat vencido (do job e do worker dono), nunca por nome (migração 012)
        orfaos = self.um("SELECT plat.job_ceifar(%s, %s) AS n", (LIMITE_SEM_SINAL_S, self.max_reinicios))
        log.info("worker iniciado: nome=%s processos=%s porta=%s tipos=%s orfaos_devolvidos=%s",
                 self.nome, self.processos, self.porta, len(REGISTRO), orfaos["n"] if orfaos else 0)
        try:
            mod_agenda.sincronizar_periodicos(self.con, mod_agenda.agora_do_worker(settings))
        except Exception:  # noqa: BLE001 — periódicos não podem impedir a fila de rodar
            log.exception("sincronização dos periódicos falhou")
        while not self.parando:
            try:
                t0 = time.monotonic()
                self.tick()
                self.ultimo_tick_ms = round((time.monotonic() - t0) * 1000, 1)
                self._esperar()
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                log.error("banco indisponível: %s; reconectando em 2 s", str(e).strip()[:200])
                self.con = None
                time.sleep(2)
            except Exception:  # noqa: BLE001 — o laço nunca morre por exceção de um tick
                log.exception("erro no tick")
                time.sleep(1)
        self._parar()
        return 0

    def _ao_sinal(self, _sinal, _quadro) -> None:
        self.parando = True

    def _ao_sigchld(self, _sinal, _quadro) -> None:
        pass  # o efeito é o wakeup_fd ficar legível: o select acorda e _colher faz o waitpid

    def tick(self) -> None:
        agora = time.monotonic()
        if agora - self.ultimo_hb >= HEARTBEAT_S:
            self.sql("SELECT plat.worker_heartbeat(%s, %s, %s)", (self.nome, rss_kb(), len(self.filhos)))
            self.ultimo_hb = agora
        if agora - self.ultima_ceifa >= CEIFA_S:
            self.ultima_ceifa = agora
            self._ceifar()
        self._vigiar(agora)
        self._colher()
        if not self.parando:
            self._pegar()

    def _esperar(self) -> None:
        fds = [self.con.fileno(), self.acorda_r] + [f.pipe_r for f in self.filhos.values() if not f.eof]
        if self.sock is not None:
            fds.append(self.sock.fileno())
        try:
            prontos, _, _ = select.select(fds, [], [], TICK_S)
        except InterruptedError:
            return
        if self.acorda_r in prontos:
            try:
                while os.read(self.acorda_r, 4096):
                    pass
            except BlockingIOError:
                pass
        if self.con.fileno() in prontos:
            self.con.poll()
            while self.con.notifies:
                n = self.con.notifies.pop(0)
                self._ao_notificar(n.payload)
        if self.sock is not None and self.sock.fileno() in prontos:
            self._atender_saude()

    def _ao_notificar(self, carga: str) -> None:
        try:
            dados = json.loads(carga)
        except ValueError:
            return
        if dados.get("cancelar"):
            for f in self.filhos.values():
                if str(f.job["id"]) == str(dados.get("job")) and f.cancel_em is None:
                    f.cancel_em = time.monotonic()

    # ---------------------------------------------------------------- ceifa e agendas (a cada 30 s)
    def _ceifar(self) -> None:
        r = self.um("SELECT plat.job_ceifar(%s, %s) AS n", (LIMITE_SEM_SINAL_S, self.max_reinicios))
        if r and r["n"]:
            log.warning("ceifa: %s jobs sem sinal devolvidos", r["n"])
        w = self.um("SELECT plat.worker_ceifar(%s) AS n", (LIMITE_WORKER_S,))
        if w and w["n"]:
            log.warning("ceifa: %s workers sem sinal apagados", w["n"])
        try:
            criados = mod_agenda.tick(self.con, mod_agenda.agora_do_worker(settings))
            for jid in criados:
                log.info("agenda enfileirou job", extra={"job_id": jid})
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            raise
        except Exception:  # noqa: BLE001
            log.exception("relógio das agendas falhou")

    # ---------------------------------------------------------------- filhos
    def _vigiar(self, agora: float) -> None:
        for pid, f in list(self.filhos.items()):
            if agora - f.ultimo_hb >= HEARTBEAT_S:
                f.ultimo_hb = agora
                r = self.um("SELECT plat.job_heartbeat(%s, %s) AS cancelar", (f.job["id"], self.nome))
                flag = r["cancelar"] if r else None
                if flag is None:
                    if f.motivo is None:
                        f.motivo = "perdido"
                        log.warning("job deixou de ser deste worker; encerrando o filho",
                                    extra={"job_id": str(f.job["id"]), "pid_filho": pid})
                        self._sinal(f, signal.SIGTERM, agora)
                elif flag and f.cancel_em is None:
                    f.cancel_em = agora
            if f.cancel_em is not None and f.sigterm_em is None and agora - f.cancel_em >= GRACA_CANCELAMENTO_S:
                f.motivo = f.motivo or "cancelar"
                self._sinal(f, signal.SIGTERM, agora)
            if f.sigterm_em is None and agora - f.iniciado > float(f.job["timeout_s"]):
                f.motivo = "timeout"
                self._sinal(f, signal.SIGTERM, agora)
            if f.sigterm_em is not None and f.sigkill_em is None and agora - f.sigterm_em >= GRACA_KILL_S:
                self._sinal(f, signal.SIGKILL, agora)

    def _sinal(self, f: Filho, sinal: int, agora: float) -> None:
        try:
            os.kill(f.pid, sinal)
        except ProcessLookupError:
            return
        if sinal == signal.SIGKILL:
            f.sigkill_em = agora
        else:
            f.sigterm_em = agora
        log.info("sinal %s ao filho (%s)", sinal, f.motivo, extra={"job_id": str(f.job["id"]), "pid_filho": f.pid})

    def _colher(self) -> None:
        for pid, f in list(self.filhos.items()):
            if not f.eof:
                self._ler_pipe(f)
            try:
                wpid, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                wpid, status = pid, 0
            if wpid != pid:
                continue
            while not f.eof:
                self._ler_pipe(f, bloqueante=True)
            try:
                os.close(f.pipe_r)
            except OSError:
                pass
            del self.filhos[pid]
            self._finalizar(f, os.waitstatus_to_exitcode(status))

    def _ler_pipe(self, f: Filho, bloqueante: bool = False) -> None:
        if bloqueante:
            os.set_blocking(f.pipe_r, True)
        try:
            while True:
                dados = os.read(f.pipe_r, 65536)
                if not dados:
                    f.eof = True
                    return
                f.buffer += dados
        except BlockingIOError:
            return
        except OSError:
            f.eof = True

    def _pesado_rodando(self) -> bool:
        return any(f.pesado for f in self.filhos.values())

    def _pegar(self) -> None:
        while len(self.filhos) < self.processos and not self.parando:
            # 07/09 (achado do item L2-15-a): o lock ficava preso quando o filho pesado terminava — o tick
            # seguinte entrava com lock_pesado=True, pesado_ok=False por inicialização, e nunca soltava.
            # Regra: segura o lock enquanto (e só enquanto) há filho pesado rodando.
            if self.lock_pesado and not self._pesado_rodando():
                self._soltar_pesado()
            pesado_ok = self.lock_pesado
            if not pesado_ok:
                r = self.um("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (_chave_pesado(),))
                pesado_ok = bool(r and r["ok"])
                self.lock_pesado = pesado_ok
            job = self.um("SELECT * FROM plat.job_pegar(%s, %s)", (self.nome, pesado_ok and not self._pesado_rodando()))
            if job is None or job.get("id") is None:
                if pesado_ok and not self._pesado_rodando():
                    self._soltar_pesado()
                return
            if not job["pesado"] and pesado_ok and not self._pesado_rodando():
                self._soltar_pesado()
            self._lancar(job)

    def _soltar_pesado(self) -> None:
        if self.lock_pesado:
            self.sql("SELECT pg_advisory_unlock(hashtext(%s))", (_chave_pesado(),))
            self.lock_pesado = False

    def _lancar(self, job: dict) -> None:
        tarefa = REGISTRO.get(job["tipo"])
        if tarefa is None:
            self.sql("SELECT plat.job_terminar(%s, %s, 'falhou', NULL, %s, NULL)",
                     (job["id"], self.nome, f"tipo de job não registrado neste worker: {job['tipo']}"))
            metricas.registrar_job_processado(job["tipo"], "falhou")
            return
        r, w = os.pipe()
        os.set_blocking(r, False)
        fechar = [self.con.fileno(), r, self.acorda_r] + [f.pipe_r for f in self.filhos.values()]
        if self.sock is not None:
            fechar.append(self.sock.fileno())
        sys.stdout.flush()
        sys.stderr.flush()
        pid_pai_esperado = os.getpid()  # medido ANTES do fork (item L0-05-e: ver o comentário de mod_filho._pdeathsig)
        pid = os.fork()
        if pid == 0:
            try:
                signal.set_wakeup_fd(-1)
                signal.signal(signal.SIGCHLD, signal.SIG_DFL)
                mod_filho.executar(job, tarefa, w, self.dir_jobs, self.nome, fechar, pid_pai_esperado)
            finally:
                os._exit(1)
        os.close(w)
        self.filhos[pid] = Filho(pid, job, r)
        self.sql("SELECT plat.job_pid(%s, %s, %s)", (job["id"], self.nome, pid))
        log.info("job iniciado", extra={"job_id": str(job["id"]), "tipo": job["tipo"], "tenant_id": job["tenant_id"],
                                        "pid_filho": pid})

    # ---------------------------------------------------------------- fim de um filho
    def _proveniencia(self, job: dict, saida: dict) -> dict:
        t = REGISTRO.get(job["tipo"])
        prov = {
            "tipo": job["tipo"], "versao_tipo": t.versao if t else None, "git_sha": git_sha_curto(), "versao": versao(),
            "parametros": job.get("parametros"), "entradas": saida.get("entradas", []), "worker": self.nome,
            "python": platform.python_version(), "iniciado_em": _iso(job.get("iniciado_em")),
            "terminado_em": _iso(datetime.datetime.now(UTC)),
            "tentativa": job.get("tentativa"), "reinicios": job.get("reinicios"),
        }
        if t and "gdal" in t.ferramentas:
            prov["gdal"] = self.gdal
        return prov

    def _terminar(self, job: dict, estado: str, resultado, erro: str | None, prov: dict) -> bool:
        r = self.um("SELECT plat.job_terminar(%s, %s, %s, %s, %s, %s) AS ok",
                    (job["id"], self.nome, estado, psycopg2.extras.Json(resultado) if resultado is not None else None,
                     erro, psycopg2.extras.Json(prov)))
        ok = bool(r and r["ok"])
        if not ok:
            log.warning("job_terminar recusado (job já não era deste worker)", extra={"job_id": str(job["id"])})
        return ok

    def _finalizar(self, f: Filho, codigo: int) -> None:
        job = f.job
        try:
            saida = json.loads(f.buffer.decode("utf-8")) if f.buffer else {}
        except ValueError:
            saida = {}
        if f.pesado:
            self._soltar_pesado()
        if self.parando:
            return  # já devolvido em _parar()
        prov = self._proveniencia(job, saida)
        estado: str | None
        if f.motivo == "timeout":
            estado = "falhou"
            self._terminar(job, estado, None, f"tempo esgotado (timeout_s = {job['timeout_s']})", prov)
        elif f.motivo == "cancelar" and codigo != mod_filho.CODIGO_CANCELADO:
            estado = "cancelado"
            self._terminar(job, estado, None, "morto após ignorar cancelamento", prov)
        elif f.motivo == "perdido":
            estado = None
        elif codigo == mod_filho.CODIGO_OK:
            estado = "concluido"
            self._terminar(job, estado, saida.get("resultado", {}), None, prov)
        elif codigo == mod_filho.CODIGO_CANCELADO:
            estado = "cancelado"
            self._terminar(job, estado, None, saida.get("erro"), prov)
        elif codigo == mod_filho.CODIGO_DEFINITIVA:
            estado = "falhou"
            self._terminar(job, estado, None, saida.get("erro") or "falha definitiva", prov)
        else:
            if codigo == mod_filho.CODIGO_MEMORIA:
                erro = saida.get("erro") or f"memória excedida (limite {job['memoria_mb']} MB)"
            elif codigo < 0:
                extra = " (limite de memória do serviço ou kill externo)" if codigo == -9 else ""
                erro = saida.get("erro") or f"morto por sinal {-codigo}{extra}"
            else:
                erro = saida.get("erro") or f"código de saída {codigo}"
            espera = 2 ** int(job["tentativa"])
            r = self.um("SELECT plat.job_devolver(%s, %s, %s, true, %s, %s, %s) AS estado",
                        (job["id"], self.nome, erro, espera, self.max_reinicios, psycopg2.extras.Json(prov)))
            estado = r["estado"] if r else None
        if estado in ("concluido", "cancelado", "pendente"):
            mod_filho.apagar_dir(self.dir_jobs, job["id"])
        # plat_jobs_processados_total (item L7-06-a): só estado FINAL de verdade — "pendente" é devolução
        # para nova tentativa, não fim de vida do job, e não deve inflar o contador de processados.
        if estado in ("concluido", "falhou", "cancelado"):
            metricas.registrar_job_processado(job["tipo"], estado)
        log.info("job terminou: %s (código %s)", estado, codigo,
                 extra={"job_id": str(job["id"]), "tipo": job["tipo"], "tenant_id": job["tenant_id"],
                        "pid_filho": f.pid})

    # ---------------------------------------------------------------- parada
    def _parar(self) -> None:
        log.info("parando: %s filhos vivos", len(self.filhos))
        for pid, f in list(self.filhos.items()):
            r = self.um("SELECT plat.job_devolver(%s, %s, 'worker reiniciado', false, 0, %s) AS estado",
                        (f.job["id"], self.nome, self.max_reinicios))
            log.info("job devolvido na parada: %s", r["estado"] if r else None,
                     extra={"job_id": str(f.job["id"]), "pid_filho": pid})
            self._sinal(f, signal.SIGTERM, time.monotonic())
        fim = time.monotonic() + ESPERA_PARADA_S
        while self.filhos and time.monotonic() < fim:
            self._colher()
            time.sleep(0.2)
        for f in list(self.filhos.values()):
            self._sinal(f, signal.SIGKILL, time.monotonic())
        while self.filhos:
            self._colher()
            time.sleep(0.1)
        self._soltar_pesado()
        self.sql("SELECT plat.worker_desregistrar(%s)", (self.nome,))
        try:
            self.con.close()
        except Exception:  # noqa: BLE001
            pass
        if self.sock is not None:
            self.sock.close()
        log.info("worker parado")

    # ---------------------------------------------------------------- saúde (:8153, no laço, sem thread)
    def _abrir_saude(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", self.porta))
        s.listen(8)
        s.setblocking(False)
        self.sock = s

    def estado_saude(self) -> dict:
        return {
            "worker": self.nome, "nome_base": self.nome_base, "pid": os.getpid(), "versao": versao(),
            "git_sha": git_sha_curto(),
            "processos": self.processos, "rodando": [str(f.job["id"]) for f in self.filhos.values()],
            "pesado_em_curso": any(f.pesado for f in self.filhos.values()), "ultimo_tick_ms": self.ultimo_tick_ms,
            "rss_kb": rss_kb(), "em": _iso(datetime.datetime.now(UTC)),
            # item L0-05-e: teto do cgroup v2 do worker (contêiner Docker ou MemoryMax da unidade systemd),
            # None quando não há teto; é o mesmo número que app.jobs.filho aplica ao RLIMIT_DATA dos filhos
            "cgroup_memoria_max_mb": mod_filho.limite_memoria_cgroup_mb(),
        }

    def _atender_saude(self) -> None:
        try:
            c, _ = self.sock.accept()
        except (BlockingIOError, OSError):
            return
        try:
            c.settimeout(1.0)
            try:
                pedido = c.recv(2048).decode("latin-1", "replace")
            except OSError:
                pedido = ""
            linha = pedido.split("\r\n", 1)[0]
            if linha.startswith(("GET /saude", "HEAD /saude")):
                corpo = json.dumps(self.estado_saude(), ensure_ascii=False).encode("utf-8")
                status = "200 OK"
                tipo_conteudo = "application/json; charset=utf-8"
            elif linha.startswith(("GET /metrics", "HEAD /metrics")):
                # item L7-06-a: mesmo contrato de cardinalidade de app/metricas.py; só as métricas DESTE
                # processo (worker) — plat_jobs_processados_total. Sem fila (evita 2º pool de conexões
                # só para repetir o que a API já expõe em /metrics via plat.fila_estado()).
                corpo, tipo_conteudo = metricas.expor()
                status = "200 OK"
            else:
                corpo = b'{"erro": "rota_inexistente"}'
                status = "404 Not Found"
                tipo_conteudo = "application/json; charset=utf-8"
            cab = (f"HTTP/1.1 {status}\r\nContent-Type: {tipo_conteudo}\r\nCache-Control: no-store\r\n"
                   f"Content-Length: {len(corpo)}\r\nConnection: close\r\n\r\n").encode("ascii")
            c.sendall(cab + (b"" if linha.startswith("HEAD") else corpo))
        except OSError:
            pass
        finally:
            c.close()

    @staticmethod
    def _versao_gdal() -> str | None:
        try:
            r = subprocess.run(["ogrinfo", "--version"], capture_output=True, text=True, timeout=10)
            return r.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None


def main() -> int:
    plat_log.configurar(settings.PLAT_LOG_NIVEL)
    return Worker().rodar()


if __name__ == "__main__":
    sys.exit(main())
