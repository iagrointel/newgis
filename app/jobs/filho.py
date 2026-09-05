"""Processo filho: um por job (ADR 0003 seção 4.3). Logo depois do fork: PR_SET_PDEATHSIG=SIGKILL (pai morto leva o
filho), threads de BLAS = threads_blas do tipo, RLIMIT_DATA = memoria_mb do job (não RLIMIT_AS: numpy/OpenBLAS
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


def _pdeathsig() -> None:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG) falhou")
    if os.getppid() == 1:  # o pai morreu entre o fork e o prctl
        os._exit(CODIGO_ERRO)


def preparar_ambiente(memoria_mb: int, threads_blas: int) -> None:
    for chave in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[chave] = str(threads_blas)
    limite = int(memoria_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (limite, limite))


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


def executar(job: dict, tarefa: Tarefa, pipe_w: int, dir_jobs: Path, worker: str, fds_fechar: list[int]) -> None:
    """Corpo do filho; nunca retorna."""
    codigo = CODIGO_ERRO
    saida: dict = {"estado": "falhou", "erro": "filho terminou sem resultado"}
    ctx = None
    try:
        _pdeathsig()
        for fd in fds_fechar:
            try:
                os.close(fd)
            except OSError:
                pass
        preparar_ambiente(int(job["memoria_mb"]), tarefa.threads_blas)
        banco._pool = None  # nunca herdar o pool (sockets partilhados entre pai e filho)
        dir_trabalho = dir_jobs / str(job["id"])
        dir_trabalho.mkdir(parents=True, exist_ok=True)
        ctx = ContextoJob(job, dir_trabalho, worker)

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
            mensagem = f"memória excedida (limite {job['memoria_mb']} MB)"
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
