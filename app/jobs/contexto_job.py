"""O que a tarefa recebe: `ContextoJob` (ADR 0003 seção 3.2). Roda no processo filho, dentro do inquilino do job
(`app.db.db(Contexto(tenant_id, usuario_id, 'worker'))`), com progresso a no máximo 1 escrita/s, log em
`plat.job_log` com teto de 10.000 linhas, checagem barata de cancelamento e subprocesso (neto) que herda o
RLIMIT_DATA e morre com o cancelamento. Regra para toda tarefa: trabalho longo FORA do bloco `with ctx.db()`
(o servidor tem idle_in_transaction_session_timeout = 60 s)."""

import subprocess
import time
import uuid
from pathlib import Path

from app import db as banco
from app.jobs.registro import Cancelado

INTERVALO_PROGRESSO_S = 1.0
INTERVALO_FLAG_S = 0.5
TETO_LOG = 10_000
BLOCO_SUPRIMIDO = 1_000
NIVEIS = ("DEBUG", "INFO", "AVISO", "ERRO")


class ContextoJob:
    def __init__(self, job: dict, dir_trabalho: Path, worker: str):
        self.job_id: uuid.UUID = uuid.UUID(str(job["id"]))
        self.tenant_id: int = int(job["tenant_id"])
        self.usuario_id: int | None = job.get("usuario_id")
        self.tipo: str = job["tipo"]
        self.tentativa: int = int(job.get("tentativa") or 1)
        self.dir_trabalho: Path = dir_trabalho
        self.worker: str = worker
        self.entradas: list[dict] = []
        self.sinal_parar = False  # ligado pelo handler de SIGTERM do filho
        self._ctx = banco.Contexto(self.tenant_id, self.usuario_id or 0, "worker")
        self._ultimo_progresso = 0.0
        self._ultima_checagem = 0.0
        self._flag = False
        self._linhas_log = 0
        self._suprimidas = 0

    # ---------------------------------------------------------------- banco
    def db(self):
        """Cursor RealDict já dentro do inquilino do job; commit no fim do bloco."""
        return banco.db(self._ctx)

    # ---------------------------------------------------------------- progresso e cancelamento
    def progresso(self, pct: int, mensagem: str = "") -> None:
        pct = max(0, min(100, int(pct)))
        agora = time.monotonic()
        if agora - self._ultimo_progresso < INTERVALO_PROGRESSO_S:
            self.verificar()
            return
        self._ultimo_progresso = agora
        with self.db() as cur:
            cur.execute(
                "UPDATE plat.job SET progresso = %s, mensagem = left(%s, 200), heartbeat_em = now() "
                "WHERE id = %s AND estado = 'rodando' AND worker = %s RETURNING cancelar_solicitado",
                (pct, mensagem or None, str(self.job_id), self.worker),
            )
            linha = cur.fetchone()
        self._ultima_checagem = agora
        if linha is None:
            self._flag = True
            raise Cancelado("o job deixou de estar rodando neste worker (devolvido ou ceifado)")
        self._flag = bool(linha["cancelar_solicitado"])
        if self._flag or self.sinal_parar:
            raise Cancelado("cancelamento solicitado")

    def cancelado(self) -> bool:
        """Leitura barata da flag: sinal do worker, ou uma consulta a cada 0,5 s."""
        if self.sinal_parar or self._flag:
            return True
        agora = time.monotonic()
        if agora - self._ultima_checagem < INTERVALO_FLAG_S:
            return False
        self._ultima_checagem = agora
        with self.db() as cur:
            cur.execute("SELECT cancelar_solicitado, estado, worker FROM plat.job WHERE id = %s", (str(self.job_id),))
            linha = cur.fetchone()
        self._flag = linha is None or bool(linha["cancelar_solicitado"]) or linha["estado"] != "rodando" \
            or linha["worker"] != self.worker
        return self._flag

    def verificar(self) -> None:
        if self.cancelado():
            raise Cancelado("cancelamento solicitado")

    def dormir(self, segundos: float) -> None:
        """Espera cooperativa: dorme em fatias de 0,25 s checando o cancelamento (a cada 0,5 s no banco)."""
        fim = time.monotonic() + max(0.0, segundos)
        while True:
            self.verificar()
            resto = fim - time.monotonic()
            if resto <= 0:
                return
            time.sleep(min(0.25, resto))

    # ---------------------------------------------------------------- log e proveniência
    def log(self, nivel: str, mensagem: str) -> None:
        nivel = nivel.upper()
        if nivel not in NIVEIS:
            nivel = "INFO"
        self._linhas_log += 1
        if self._linhas_log > TETO_LOG:
            self._suprimidas += 1
            if self._suprimidas % BLOCO_SUPRIMIDO != 0:
                return
            mensagem = f"{BLOCO_SUPRIMIDO} linhas suprimidas (teto de {TETO_LOG} linhas por job)"
            nivel = "AVISO"
        with self.db() as cur:
            cur.execute(
                "INSERT INTO plat.job_log(job_id, tenant_id, nivel, mensagem) VALUES (%s, %s, %s, left(%s, 4000))",
                (str(self.job_id), self.tenant_id, nivel, str(mensagem)),
            )
            cur.execute("UPDATE plat.job SET linhas_log = linhas_log + 1 WHERE id = %s", (str(self.job_id),))

    def entrada(self, item_id: uuid.UUID | str | None, sha256: str, descricao: str = "") -> None:
        self.entradas.append({"item_id": str(item_id) if item_id else None, "sha256": sha256,
                              "descricao": descricao[:200]})

    # ---------------------------------------------------------------- neto
    def subprocesso(self, argv: list[str], **kw) -> subprocess.CompletedProcess:
        """Roda ogr2ogr/gdal/etc. como neto (herda RLIMIT_DATA e as variáveis de threads); stdout/stderr vão para o
        log; o cancelamento mata o neto (SIGTERM, +5 s SIGKILL) e levanta Cancelado."""
        kw.setdefault("cwd", str(self.dir_trabalho))
        kw.setdefault("text", True)
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
        saida = erro = ""
        try:
            while True:
                try:
                    saida, erro = proc.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancelado():
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        raise Cancelado(f"subprocesso {argv[0]} interrompido por cancelamento") from None
        finally:
            for nome, texto in (("stdout", saida), ("stderr", erro)):
                for linha in (texto or "").splitlines():
                    if linha.strip():
                        self.log("INFO" if nome == "stdout" else "AVISO", f"{argv[0]} {nome}: {linha}")
        return subprocess.CompletedProcess(argv, proc.returncode, saida, erro)
