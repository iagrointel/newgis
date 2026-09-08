"""Cluster Garage de teste com N nós na MESMA máquina (item L7-07-b-replica-garage; docs/RUNBOOKS/garage.md).
Cada nó é um processo `garage server` com config, metadados e dados próprios em um diretório temporário,
portas efêmeras (rpc, s3, admin) e os segredos (`rpc_secret`, `admin_token`, `metrics_token`) em ARQUIVOS 0600
lidos por `*_file` — o mesmo desenho do L7-19 (segredo fora do arquivo de configuração). Usa o binário da
instalação (`PLAT_GARAGE_BIN`, padrão o da prova do pipeline) — nunca a instância de produção, nunca docker.

O que o harness sabe fazer: subir, conectar os nós entre si, aplicar um layout com zonas e rf, parar/religar
um nó pelo PID (sinal TERM), criar chave/bucket/cota, e chamar a CLI (`status`, `repair blocks`, `repair scrub`,
`block list-errors`, `stats`) contra qualquer nó. O que ele NÃO faz: matar processo que não é dele."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

BIN = os.environ.get("PLAT_GARAGE_BIN") or "/home/dev/plataforma/pipeline/bin/garage"


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class No:
    indice: int
    raiz: Path
    rpc: int
    s3: int
    admin: int
    zona: str
    processo: subprocess.Popen | None = None
    id_completo: str = ""
    log: Path = field(default_factory=Path)

    @property
    def config(self) -> Path:
        return self.raiz / "garage.toml"

    @property
    def vivo(self) -> bool:
        return self.processo is not None and self.processo.poll() is None

    @property
    def s3_url(self) -> str:
        return f"http://127.0.0.1:{self.s3}"


class Cluster:
    def __init__(self, n: int, rf: int, zonas: list[str] | None = None, base: Path | None = None):
        self.raiz = Path(tempfile.mkdtemp(prefix="plat-garage-teste-", dir=str(base) if base else None))
        self.rf = rf
        self.rpc_secret = secrets.token_hex(32)
        self.admin_token = secrets.token_hex(24)
        self.metrics_token = secrets.token_hex(24)
        seg = self.raiz / "segredos"
        seg.mkdir(mode=0o700)
        for nome, valor in (("rpc_secret", self.rpc_secret), ("admin_token", self.admin_token),
                            ("metrics_token", self.metrics_token)):
            arq = seg / nome
            arq.write_text(valor + "\n", encoding="utf-8")
            arq.chmod(0o600)
        self.nos: list[No] = []
        for i in range(n):
            raiz = self.raiz / f"no{i + 1}"
            (raiz / "meta").mkdir(parents=True)
            (raiz / "data").mkdir()
            zona = (zonas or [f"z{k + 1}" for k in range(n)])[i]
            no = No(i + 1, raiz, porta_livre(), porta_livre(), porta_livre(), zona)
            no.log = raiz / "garage.log"
            no.config.write_text(
                f'metadata_dir = "{raiz / "meta"}"\n'
                f'data_dir = "{raiz / "data"}"\n'
                'db_engine = "lmdb"\n'
                f"replication_factor = {rf}\n"
                f'rpc_bind_addr = "127.0.0.1:{no.rpc}"\n'
                f'rpc_public_addr = "127.0.0.1:{no.rpc}"\n'
                f'rpc_secret_file = "{seg / "rpc_secret"}"\n'
                "[s3_api]\n"
                's3_region = "garage"\n'
                f'api_bind_addr = "127.0.0.1:{no.s3}"\n'
                'root_domain = ".s3.garage.localhost"\n'
                "[admin]\n"
                f'api_bind_addr = "127.0.0.1:{no.admin}"\n'
                f'admin_token_file = "{seg / "admin_token"}"\n'
                f'metrics_token_file = "{seg / "metrics_token"}"\n',
                encoding="utf-8",
            )
            self.nos.append(no)

    # ------------------------------------------------------------------ processos
    def subir(self, no: No) -> None:
        if no.vivo:
            return
        log = open(no.log, "ab")  # noqa: SIM115 — fechado em parar()
        no.processo = subprocess.Popen(
            [BIN, "-c", str(no.config), "server"], stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "RUST_LOG": "garage=info"}, start_new_session=True,
        )
        no._log_fd = log  # type: ignore[attr-defined]
        fim = time.monotonic() + 30
        while time.monotonic() < fim:
            # `node id` lê a chave do metadata_dir e responde antes de o servidor escutar; só `status` prova
            # que o RPC está de pé (era isto que fazia `repair` falhar com "Connection refused" logo após religar)
            r = self.cli(no, "node", "id", "-q", checar=False)
            if r.returncode == 0 and "@" in r.stdout and self.cli(no, "status", checar=False).returncode == 0:
                no.id_completo = r.stdout.strip().splitlines()[-1].strip()
                return
            time.sleep(0.3)
        raise RuntimeError(
            f"nó {no.indice} não respondeu ao `node id` em 30 s; log: {no.log.read_text()[-2000:]}"
        )

    def parar(self, no: No, sinal: int = signal.SIGTERM, timeout: float = 20) -> None:
        if not no.vivo:
            return
        assert no.processo is not None
        os.kill(no.processo.pid, sinal)  # só o PID que ESTE harness criou
        try:
            no.processo.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.kill(no.processo.pid, signal.SIGKILL)
            no.processo.wait(timeout=10)
        fd = getattr(no, "_log_fd", None)
        if fd:
            fd.close()

    def subir_todos(self) -> None:
        for no in self.nos:
            self.subir(no)

    def parar_todos(self) -> None:
        for no in self.nos:
            self.parar(no)

    def destruir(self) -> None:
        self.parar_todos()
        shutil.rmtree(self.raiz, ignore_errors=True)

    # ------------------------------------------------------------------ CLI
    def cli(self, no: No, *args: str, checar: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
        r = subprocess.run([BIN, "-c", str(no.config), *args], capture_output=True, text=True, timeout=timeout)
        if checar and r.returncode != 0:
            raise RuntimeError(f"garage {' '.join(args)} (nó {no.indice}) falhou: {r.stdout}\n{r.stderr}")
        return r

    def conectar(self) -> None:
        """cada nó conhece os outros (node connect é simétrico depois do primeiro aperto de mão)."""
        for a in self.nos:
            for b in self.nos:
                if a is not b:
                    self.cli(a, "node", "connect", b.id_completo)
        self.esperar_status(len(self.nos))

    def nos_no_status(self, no: No) -> list[dict]:
        r = self.cli(no, "status")
        saida = []
        for linha in r.stdout.splitlines():
            partes = linha.split()
            if len(partes) >= 2 and re.fullmatch(r"[0-9a-f]{16}", partes[0]):
                saida.append({"id": partes[0], "linha": linha})
        return saida

    def esperar_status(self, esperados: int, timeout: float = 30) -> None:
        fim = time.monotonic() + timeout
        vivo = next(n for n in self.nos if n.vivo)
        while time.monotonic() < fim:
            if len(self.nos_no_status(vivo)) >= esperados:
                return
            time.sleep(0.5)
        raise RuntimeError(
            f"status não mostrou {esperados} nós em {timeout} s:\n{self.cli(vivo, 'status').stdout}"
        )

    def aplicar_layout(self, capacidade: str = "1G") -> None:
        primeiro = self.nos[0]
        for no in self.nos:
            id_curto = no.id_completo.split("@")[0][:16]
            self.cli(primeiro, "layout", "assign", "-z", no.zona, "-c", capacidade, id_curto)
        self.cli(primeiro, "layout", "apply", "--version", "1")
        time.sleep(1.0)

    def criar_chave_e_bucket(self, bucket: str, cota: str | None = None) -> tuple[str, str]:
        no = next(n for n in self.nos if n.vivo)
        self.cli(no, "key", "create", "teste")
        info = self.cli(no, "key", "info", "--show-secret", "teste").stdout
        chave = re.search(r"Key ID:\s*(\S+)", info).group(1)
        segredo = re.search(r"Secret key:\s*(\S+)", info).group(1)
        self.cli(no, "bucket", "create", bucket)
        self.cli(no, "bucket", "allow", "--read", "--write", "--owner", bucket, "--key", "teste")
        if cota:
            self.cli(no, "bucket", "set-quotas", "--max-size", cota, bucket)
        return chave, segredo

    def erros_de_bloco(self, no: No) -> int:
        r = self.cli(no, "block", "list-errors", checar=False)
        return sum(1 for li in r.stdout.splitlines() if re.match(r"^[0-9a-f]{8,}", li.strip()))

    def _stats(self, no: No) -> dict:
        r = self.cli(no, "stats", checar=False).stdout
        fila = re.search(r"resync queue length:\s*(\d+)", r, re.I)
        erros = re.search(r"blocks with resync errors:\s*(\d+)", r, re.I)
        refs = re.search(r"^\s*block_ref\s+(\d+)", r, re.M)
        return {
            "fila": int(fila.group(1)) if fila else None, "erros": int(erros.group(1)) if erros else None,
            "block_ref": int(refs.group(1)) if refs else None, "bruto": r,
        }

    def esperar_resync(self, no: No, referencia: No, timeout: float = 600) -> float:
        """Nó recém-religado: (1) espera a anti-entropia de METADADOS trazer as referências de bloco
        (`block_ref` de `garage stats` igual ao do nó de referência — sem isso `repair blocks` não sabe o que
        falta); (2) `repair --yes blocks` enfileira a cópia; (3) espera a fila de resync zerar sem erro.
        Devolve segundos do total. Tranquilidade dos workers zerada antes (senão o Garage espera de propósito
        entre blocos, e a medida vira medida da tranquilidade, não da cópia)."""
        t0 = time.monotonic()
        self.cli(no, "worker", "set", "resync-tranquility", "0", checar=False)
        self.cli(no, "worker", "set", "resync-worker-count", "8", checar=False)
        fim = time.monotonic() + timeout
        alvo = self._stats(referencia)["block_ref"]
        # MEDIDO (07/09, 3 nós rf=3): sem isto a anti-entropia de metadados só passa a cada 10 min (o nó voltou e
        # ficou 613 s com block_ref = 0); `repair tables` nos nós QUE TÊM o dado empurra na hora (3 s para 100)
        # MEDIDO (07/09): sem refazer o `node connect` nos dois sentidos, o nó religado aparece "healthy" no status
        # dos outros mas com hostname "?" e a sincronização de tabelas não acontece (1000 objetos, 0 refs em 300 s);
        # com o connect refeito + `repair tables`, 100 objetos em 3 s.
        self.conectar()
        time.sleep(2.0)
        for outro in self.nos:
            if outro.vivo:
                self.cli(outro, "repair", "--yes", "tables", checar=False)
        while time.monotonic() < fim and self._stats(no)["block_ref"] != alvo:
            time.sleep(0.5)
        self.cli(no, "repair", "--yes", "blocks")
        esperados = self.blocos_em_disco(referencia)
        while time.monotonic() < fim:
            s = self._stats(no)
            # a fila de resync guarda entradas com nova tentativa agendada mesmo depois de copiadas; o critério
            # de "sincronizado" é o bloco ESTAR no disco (o que o adversário compara), sem erro de resync
            if (s["erros"] or 0) == 0 and s["block_ref"] == alvo and self.blocos_em_disco(no) >= esperados:
                return time.monotonic() - t0
            time.sleep(0.5)
        raise RuntimeError(f"resync não completou em {timeout} s:\n{self._stats(no)['bruto']}")

    @staticmethod
    def blocos_em_disco(no: No) -> set[str]:
        """nomes (hash) dos blocos gravados no data_dir do nó, sem sufixo de compressão: é o que o adversário
        compara entre os dois nós (bloco = arquivo nomeado pelo hash do conteúdo)."""
        saida = set()
        for _raiz, _dirs, arquivos in os.walk(no.raiz / "data"):
            for a in arquivos:
                saida.add(a.split(".", 1)[0])
        return saida

    def scrub(self, no: No, timeout: float = 600) -> str:
        self.cli(no, "repair", "--yes", "scrub", "start")
        fim = time.monotonic() + timeout
        ultimo = ""
        viu_ocupado = False
        inicio = time.monotonic()
        while time.monotonic() < fim:
            ultimo = self.cli(no, "worker", "list", checar=False).stdout
            linha = next((li for li in ultimo.splitlines() if "scrub" in li.lower()), "")
            partes = linha.split()
            estado = partes[1].lower() if len(partes) > 1 else ""
            if estado == "busy":
                viu_ocupado = True
            # o scrub de poucos blocos termina antes da primeira leitura: 3 s de graça cobrem esse caso
            if linha and estado == "idle" and (viu_ocupado or time.monotonic() - inicio > 3):
                return linha
            time.sleep(0.5)
        raise RuntimeError(f"scrub não terminou em {timeout} s:\n{ultimo}")
