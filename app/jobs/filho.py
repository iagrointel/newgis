"""Processo filho: um por job (ADR 0003 seção 4.3). Logo depois do fork: PR_SET_PDEATHSIG=SIGKILL (pai morto leva o
filho), threads de BLAS = threads_blas do tipo, RLIMIT_DATA = VmData herdado do fork + memoria_mb do job (não RLIMIT_AS: numpy/OpenBLAS
reservam endereço e travam), pool do pai descartado, SIGTERM vira flag lida por progresso()/cancelado(). Códigos
de saída: 0 concluído · 3 cancelado · 4 FalhaDefinitiva · 5 memória excedida · 1 exceção comum. Sempre os._exit."""

import ctypes
import gc
import json
import os
import resource
import shutil
import signal
import sys
import traceback
from pathlib import Path

from app import db as banco
from app.jobs.contexto_job import ContextoJob
from app.jobs.registro import Cancelado, FalhaDefinitiva, Tarefa

PR_SET_PDEATHSIG = 1
CODIGO_OK, CODIGO_ERRO, CODIGO_CANCELADO, CODIGO_DEFINITIVA, CODIGO_MEMORIA = 0, 1, 3, 4, 5
CAMINHO_PROC_CGROUP = Path("/proc/self/cgroup")  # nomes em constantes (não inline) para o teste de unidade
RAIZ_CGROUP = Path("/sys/fs/cgroup")              # trocar por um diretório de teste via monkeypatch
# Reserva subtraída do teto do cgroup antes de virar RLIMIT_DATA (item L0-05-e): RLIMIT_DATA conta segmento de
# dados + mmap anônimo privado do PRÓPRIO filho; o cgroup conta RSS + cache de página do CGROUP INTEIRO (pai +
# todos os filhos vivos). Valor fixo, não medido nesta rodada (RSS do pai medido no ADR 0003 = 25.920 kB;
# 96 MB dá folga de ~3,7× esse número para o pai e para o overhead do runtime do contêiner) — reavaliar com
# `docker stats`/`MemoryPeak` se algum job legítimo passar a ser clampado sem necessidade.
RESERVA_CGROUP_MB = 96
CAMINHO_PROC_STATUS = Path("/proc/self/status")  # VmData do processo (constante para o teste de unidade)


def _pdeathsig(pid_pai_esperado: int) -> None:
    """`pid_pai_esperado` é o PID do worker medido ANTES do fork (worker.py captura `os.getpid()` e repassa).
    MEDIDO 06/09/2026 (item L0-05-e): checar `os.getppid() == 1` para decidir "o pai morreu entre o fork e o
    prctl" só vale fora de contêiner. Dentro de um contêiner Docker sem `--init`, o PRÓPRIO WORKER roda como
    PID 1 do contêiner (visto em GET /saude: "pid": 1) — todo filho reparentado por morte do pai vai para
    PID 1 tanto faz onde ele mora, mas aqui PID 1 É o pai vivo, não o init do sistema; a checagem antiga
    confundia as duas coisas e matava todo filho, sempre, no contêiner (reproduzido: 100% dos jobs falhavam
    com código de saída 1, sem log, sem traceback — o processo morre aqui, antes de qualquer coisa que
    escreva em algum lugar). A comparação certa, dentro ou fora de contêiner, é contra o PID que era o pai
    ANTES do fork: se mudou, o pai de verdade morreu; se PID 1 sempre foi o pai (contêiner sem --init), nada
    mudou e o filho segue."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG) falhou")
    if os.getppid() != pid_pai_esperado:  # o pai morreu entre o fork e o prctl (reparentado para outro pid)
        os._exit(CODIGO_ERRO)


def limite_memoria_cgroup_mb() -> int | None:
    """Teto de memória do cgroup v2 do processo atual, em MB, ou `None` se não houver cgroup v2 unificado, se o
    cgroup não tiver teto (`memory.max` = `max`) ou se o arquivo não puder ser lido.

    MEDIDO nesta máquina 06/09/2026: o caminho do cgroup do processo NÃO é sempre `/sys/fs/cgroup/memory.max` —
    só é, por coincidência, quando o cgroup é remontado na raiz por um namespace de cgroup próprio (é o caso de
    um contêiner Docker padrão: `/proc/self/cgroup` mostra `0::/` dentro dele). Fora de contêiner (sessão desta
    máquina, ou a unidade `plat-worker` do systemd) o processo vive num cgroup filho: sessão de usuário mostrou
    `0::/user.slice/user-0.slice/session-192870.scope` (`memory.max` = `max`, sem teto); a unidade em produção
    mostrou `0::/system.slice/plat-worker.service` com `memory.max` = 2147483648 (os 2 GiB do `MemoryMax=2G` do
    `deploy/plat-worker.service`) — o mesmo mecanismo de cgroup v2 serve o contêiner e a unidade systemd sem
    distinção de código. Por isso o caminho é sempre resolvido via `/proc/self/cgroup`, nunca hardcoded."""
    try:
        linhas = CAMINHO_PROC_CGROUP.read_text().splitlines()
    except OSError:
        return None
    caminho_relativo = None
    for linha in linhas:
        partes = linha.split(":", 2)
        if len(partes) == 3 and partes[0] == "0" and partes[1] == "":  # cgroup v2 unificado (hierarquia única)
            caminho_relativo = partes[2]
            break
    if caminho_relativo is None:
        return None  # só cgroup v1 (hierarquias múltiplas) ou /proc/self/cgroup em formato inesperado
    caminho = RAIZ_CGROUP / caminho_relativo.lstrip("/") / "memory.max"
    try:
        conteudo = caminho.read_text().strip()
    except OSError:
        return None
    if conteudo == "max":
        return None
    try:
        return int(conteudo) // (1024 * 1024)
    except ValueError:
        return None


def vmdata_mb() -> int:
    """VmData do processo em MB (segmento de dados + mmap anônimo privado — exatamente o que RLIMIT_DATA conta).

    MEDIDO 06/09/2026 nesta máquina: `import app.jobs.tipos` (o registro dos 20 tipos, que puxa GDAL/rasterio,
    numpy e psycopg2) leva o VmData do worker de 5 MB para 551 MB. O filho nasce de `fork()` e HERDA esse
    VmData. Por isso RLIMIT_DATA não pode ser o número declarado do job em termos absolutos: um job de
    `memoria_mb=256` nascia com 551 MB de VmData já contra um teto de 256 MB e morria com MemoryError na
    primeira alocação (medido: `prova.memoria(mb=64)` falhava com "memória excedida (limite 256 MB)"). O
    limite aplicado é `base do fork + memoria_mb`, ou seja `memoria_mb` é o que o JOB pode alocar além da
    base do worker — que é o que o número declarado sempre quis dizer."""
    try:
        for linha in CAMINHO_PROC_STATUS.read_text().splitlines():
            if linha.startswith("VmData:"):
                return int(linha.split()[1]) // 1024  # kB -> MB
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def memoria_efetiva_mb(memoria_mb: int) -> int:
    """Aritmética pura do clamp (sem tocar em RLIMIT — testável sem subprocesso, já que `setrlimit(RLIMIT_DATA)`
    só pode BAIXAR o teto no processo que o chama; testar a syscall de verdade duas vezes no mesmo processo de
    teste falha com 'not allowed to raise maximum limit'). `memoria_mb` do job nunca vence o teto do cgroup."""
    efetivo_mb = int(memoria_mb)
    teto_cgroup = limite_memoria_cgroup_mb()
    if teto_cgroup is not None:
        teto_util = max(1, teto_cgroup - RESERVA_CGROUP_MB)
        efetivo_mb = min(efetivo_mb, teto_util)
    return efetivo_mb


def preparar_ambiente(memoria_mb: int, threads_blas: int, base_mb: int | None = None) -> int:
    """Aplica RLIMIT_DATA e devolve o ORÇAMENTO efetivo do job em MB (item L0-05-e: nunca acima do teto do
    cgroup, contêiner ou unidade systemd — `memoria_mb` do job é o pedido; o cgroup é o que existe de verdade).
    Chamado uma vez por filho recém-forkado (nunca duas vezes no mesmo processo: RLIMIT_DATA só desce, não sobe).

    O RLIMIT_DATA aplicado é `base_mb + orçamento`, com `base_mb` = VmData herdado do worker no fork (ver
    `vmdata_mb`); `base_mb` explícito só existe para o teste, que precisa de um número determinístico."""
    for chave in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[chave] = str(threads_blas)
    efetivo_mb = memoria_efetiva_mb(memoria_mb)
    base = vmdata_mb() if base_mb is None else int(base_mb)
    limite = (base + efetivo_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (limite, limite))
    return efetivo_mb


def _escrever(pipe_w: int, saida: dict) -> None:
    dados = json.dumps(saida, ensure_ascii=False, default=str).encode("utf-8")
    try:
        while dados:
            n = os.write(pipe_w, dados)
            dados = dados[n:]
    except OSError:
        pass
    finally:
        try:
            os.close(pipe_w)
        except OSError:
            pass


def executar(job: dict, tarefa: Tarefa, pipe_w: int, dir_jobs: Path, worker: str, fds_fechar: list[int],
             pid_pai_esperado: int) -> None:
    """Corpo do filho; nunca retorna. `pid_pai_esperado` = `os.getpid()` do worker, medido ANTES do fork
    (worker.py o repassa) — ver o comentário de `_pdeathsig`."""
    codigo = CODIGO_ERRO
    saida: dict = {"estado": "falhou", "erro": "filho terminou sem resultado"}
    ctx = None
    try:
        _pdeathsig(pid_pai_esperado)
        for fd in fds_fechar:
            try:
                os.close(fd)
            except OSError:
                pass
        memoria_mb_efetiva = preparar_ambiente(int(job["memoria_mb"]), tarefa.threads_blas)
        banco._pool = None  # nunca herdar o pool (sockets partilhados entre pai e filho)
        dir_trabalho = dir_jobs / str(job["id"])
        dir_trabalho.mkdir(parents=True, exist_ok=True)
        ctx = ContextoJob(job, dir_trabalho, worker)
        if memoria_mb_efetiva < int(job["memoria_mb"]):
            ctx.log("AVISO", f"RLIMIT_DATA reduzido de {job['memoria_mb']} MB para {memoria_mb_efetiva} MB "
                             f"pelo teto do cgroup (contêiner ou MemoryMax da unidade)")

        def ao_sigterm(_sinal, _quadro):
            ctx.sinal_parar = True

        signal.signal(signal.SIGTERM, ao_sigterm)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            parametros = tarefa.parametros.model_validate(job.get("parametros") or {}).model_dump()
            resultado = tarefa.funcao(ctx, **parametros)
            if resultado is None:
                resultado = {}
            json.dumps(resultado, default=str)
            saida = {"estado": "concluido", "resultado": resultado, "entradas": ctx.entradas}
            codigo = CODIGO_OK
        except Cancelado as e:
            saida = {"estado": "cancelado", "erro": str(e)[:2000], "entradas": ctx.entradas}
            codigo = CODIGO_CANCELADO
        except FalhaDefinitiva as e:
            _registrar_erro(ctx, e)
            saida = {"estado": "falhou", "erro": f"{e}"[:2000], "entradas": ctx.entradas}
            codigo = CODIGO_DEFINITIVA
        except MemoryError:
            gc.collect()
            mensagem = f"memória excedida (limite {memoria_mb_efetiva} MB)"
            try:
                ctx.log("ERRO", mensagem)
            except Exception:  # noqa: BLE001 — sem memória para logar; o pai marca pelo código de saída
                pass
            saida = {"estado": "falhou", "erro": mensagem, "entradas": ctx.entradas}
            codigo = CODIGO_MEMORIA
        except BaseException as e:  # noqa: BLE001 — qualquer outra exceção da tarefa é falha comum (retenta)
            _registrar_erro(ctx, e)
            saida = {"estado": "falhou", "erro": f"{type(e).__name__}: {e}"[:2000], "entradas": ctx.entradas}
            codigo = CODIGO_ERRO
    except BaseException as e:  # noqa: BLE001 — falha na preparação do filho
        saida = {"estado": "falhou", "erro": f"preparação do filho: {type(e).__name__}: {e}"[:2000]}
        codigo = CODIGO_ERRO
    finally:
        try:
            _escrever(pipe_w, saida)
        finally:
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:  # noqa: BLE001
                pass
            os._exit(codigo)


def _registrar_erro(ctx: ContextoJob | None, e: BaseException) -> None:
    if ctx is None:
        return
    try:
        ctx.log("ERRO", "".join(traceback.format_exception(type(e), e, e.__traceback__))[-4000:])
    except Exception:  # noqa: BLE001 — o log é auxiliar; a saída pelo pipe é o canal principal
        pass


def apagar_dir(dir_jobs: Path, job_id) -> None:
    shutil.rmtree(dir_jobs / str(job_id), ignore_errors=True)
