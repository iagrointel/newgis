"""RLIMIT_DATA sob cgroup v2 (item L0-05-e-worker-em-container): `limite_memoria_cgroup_mb()` resolve o caminho
do cgroup do processo via /proc/self/cgroup (nunca hardcoded — MEDIDO 06/09/2026 que o cgroup do processo NÃO
está sempre em /sys/fs/cgroup/memory.max fora de contêiner: a unidade plat-worker vive em
/system.slice/plat-worker.service) e `memoria_efetiva_mb()`/`preparar_ambiente()` nunca aplicam um RLIMIT_DATA
acima do teto do cgroup menos a reserva. `preparar_ambiente()` de verdade chama `resource.setrlimit`, que só
pode BAIXAR o teto no processo que o chama (`ValueError: not allowed to raise maximum limit` na segunda chamada
que tentasse subir) — por isso a aritmética do clamp é testada pura (`memoria_efetiva_mb`, sem setrlimit) e só
o caminho ponta-a-ponta roda uma vez, num subprocesso isolado, para não poluir o processo do pytest."""

import subprocess
import sys
import textwrap
from pathlib import Path

from app.jobs import filho

ROOT = Path(__file__).resolve().parents[2]


def _cgroup_v2(tmp_path, caminho_relativo: str, memory_max: str):
    """Monta uma árvore de arquivos igual à de /proc/self/cgroup + /sys/fs/cgroup para o teste, sem tocar no
    cgroup real do processo de teste."""
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text(f"0::{caminho_relativo}\n")
    raiz_cgroup = tmp_path / "sys_fs_cgroup"
    (raiz_cgroup / caminho_relativo.lstrip("/")).mkdir(parents=True)
    (raiz_cgroup / caminho_relativo.lstrip("/") / "memory.max").write_text(memory_max)
    return proc_cgroup, raiz_cgroup


def test_sem_proc_cgroup_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", tmp_path / "nao_existe")
    assert filho.limite_memoria_cgroup_mb() is None


def test_memory_max_max_devolve_none(tmp_path, monkeypatch):
    proc_cgroup, raiz = _cgroup_v2(tmp_path, "/system.slice/plat-worker.service", "max")
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    monkeypatch.setattr(filho, "RAIZ_CGROUP", raiz)
    assert filho.limite_memoria_cgroup_mb() is None


def test_memory_max_numerico_vira_mb(tmp_path, monkeypatch):
    # 512 MiB (o valor medido nesta máquina para a unidade plat-worker é 2 GiB = 2147483648 bytes)
    proc_cgroup, raiz = _cgroup_v2(tmp_path, "/system.slice/plat-worker.service", str(512 * 1024 * 1024))
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    monkeypatch.setattr(filho, "RAIZ_CGROUP", raiz)
    assert filho.limite_memoria_cgroup_mb() == 512


def test_cgroup_v1_hierarquia_multipla_devolve_none(tmp_path, monkeypatch):
    proc_cgroup = tmp_path / "proc_self_cgroup"
    proc_cgroup.write_text("12:memory:/docker/abcdef\n11:cpu,cpuacct:/docker/abcdef\n")  # v1: sem linha "0::"
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    assert filho.limite_memoria_cgroup_mb() is None


def test_memoria_efetiva_sem_teto_de_cgroup_usa_o_pedido(tmp_path, monkeypatch):
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", tmp_path / "nao_existe")
    assert filho.memoria_efetiva_mb(256) == 256


def test_memoria_efetiva_clampa_pelo_teto_do_cgroup(tmp_path, monkeypatch):
    # cgroup com teto de 200 MB e reserva de 96 MB (RESERVA_CGROUP_MB): teto útil = 104 MB, abaixo dos 256
    # pedidos pelo job — o clamp tem de vencer.
    proc_cgroup, raiz = _cgroup_v2(tmp_path, "/docker/1234", str(200 * 1024 * 1024))
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    monkeypatch.setattr(filho, "RAIZ_CGROUP", raiz)
    assert filho.memoria_efetiva_mb(256) == 200 - filho.RESERVA_CGROUP_MB == 104


def test_memoria_efetiva_nao_clampa_quando_cgroup_folgado(tmp_path, monkeypatch):
    # a unidade plat-worker em produção mede 2 GiB (2147483648 bytes) de MemoryMax; um job de 256 MB nunca é
    # clampado por esse teto (regressão: garante que a produção de hoje não muda de comportamento).
    proc_cgroup, raiz = _cgroup_v2(tmp_path, "/system.slice/plat-worker.service", "2147483648")
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    monkeypatch.setattr(filho, "RAIZ_CGROUP", raiz)
    assert filho.memoria_efetiva_mb(256) == 256


def test_memoria_efetiva_nunca_abaixo_de_1_mb(tmp_path, monkeypatch):
    # teto do cgroup menor que a reserva: o mínimo nunca é <= 0 (setrlimit com 0 é um caso degenerado à parte)
    proc_cgroup, raiz = _cgroup_v2(tmp_path, "/docker/1234", str(10 * 1024 * 1024))
    monkeypatch.setattr(filho, "CAMINHO_PROC_CGROUP", proc_cgroup)
    monkeypatch.setattr(filho, "RAIZ_CGROUP", raiz)
    assert filho.memoria_efetiva_mb(256) == 1


def test_preparar_ambiente_ponta_a_ponta_em_subprocesso_isolado(tmp_path):
    """`resource.setrlimit(RLIMIT_DATA)` só baixa o teto no processo que o chama (setrlimit(2): um processo sem
    CAP_SYS_RESOURCE não pode reerguer o hard limit) — testar a syscall de verdade duas vezes no processo do
    pytest quebraria o segundo teste ("not allowed to raise maximum limit"). Por isso este único teste ponta-a-
    ponta roda num interpretador Python novo (subprocess), do jeito que o filho de verdade roda: um processo, uma
    chamada de preparar_ambiente()."""
    caminho_relativo = "/docker/teste-l0-05-e"
    proc_cgroup, raiz = _cgroup_v2(tmp_path, caminho_relativo, str(200 * 1024 * 1024))
    script = textwrap.dedent(f"""
        import resource
        from pathlib import Path
        from app.jobs import filho
        filho.CAMINHO_PROC_CGROUP = Path({str(proc_cgroup)!r})
        filho.RAIZ_CGROUP = Path({str(raiz)!r})
        efetivo = filho.preparar_ambiente(memoria_mb=256, threads_blas=1, base_mb=300)
        limite, _ = resource.getrlimit(resource.RLIMIT_DATA)
        assert efetivo == 104, efetivo
        # RLIMIT_DATA = base herdada do fork (300 MB, fixa aqui para o teste ser determinístico) + orçamento
        assert limite == (300 + 104) * 1024 * 1024, limite
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10, check=False,
                        cwd=ROOT)
    assert r.returncode == 0 and r.stdout.strip() == "OK", f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_vmdata_mb_le_o_proc_status(tmp_path, monkeypatch):
    """VmData vem de /proc/self/status em kB e vira MB (o filho herda o VmData do worker no fork)."""
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmSize:\t 1234 kB\nVmData:\t  551548 kB\nVmRSS:\t  106172 kB\n")
    monkeypatch.setattr(filho, "CAMINHO_PROC_STATUS", status)
    assert filho.vmdata_mb() == 538  # 551548 kB // 1024


def test_vmdata_mb_sem_arquivo_devolve_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(filho, "CAMINHO_PROC_STATUS", tmp_path / "nao_existe")
    assert filho.vmdata_mb() == 0


def test_preparar_ambiente_soma_a_base_em_subprocesso_isolado(tmp_path):
    """Sem teto de cgroup, RLIMIT_DATA = VmData REAL do processo + o orçamento do job. Regressão do defeito
    medido em 06/09/2026: `import app.jobs.tipos` deixa o worker com 551 MB de VmData, o filho herda esses
    551 MB no fork e um RLIMIT_DATA absoluto de 256 MB fazia `prova.memoria(mb=64)` morrer com MemoryError."""
    script = textwrap.dedent("""
        import resource
        from pathlib import Path
        from app.jobs import filho
        filho.CAMINHO_PROC_CGROUP = Path("/nao/existe/cgroup")   # sem teto de cgroup
        base = filho.vmdata_mb()
        efetivo = filho.preparar_ambiente(memoria_mb=256, threads_blas=1)
        limite, _ = resource.getrlimit(resource.RLIMIT_DATA)
        assert efetivo == 256, efetivo
        assert limite >= (base + 256) * 1024 * 1024, (base, limite)
        assert limite < (base + 256 + 32) * 1024 * 1024, (base, limite)
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30, check=False,
                       cwd=ROOT)
    assert r.returncode == 0 and r.stdout.strip() == "OK", f"stdout={r.stdout!r} stderr={r.stderr!r}"
