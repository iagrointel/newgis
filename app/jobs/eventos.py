"""Progresso em tempo real por SSE (ADR 0003 seção 5): um thread LISTEN plat_job por processo, iniciado na primeira
conexão (sem hook de startup), fan-out por job_id para filas asyncio via call_soon_threadsafe; gerador que manda
`estado` (lido do banco), `log` e `fim`; keepalive 15 s; reenvio do log a partir de Last-Event-ID; 30 min no máximo;
reconexão do LISTEN com a mesma disciplina do pool (refaz só a preparação).

Orçamento de conexões (achado do adversário G3, 06/09): antes havia UM contador, por usuário, em memória de
processo — sem dimensão de inquilino (um inquilino com muitos usuários consumia toda a máquina) e sem contar
que a unidade sobe `--workers N` (o limite publicado valia N vezes). Agora são três tetos, todos da
INSTALAÇÃO inteira (app/limites.py), repartidos pelo número de processos da API antes de virar teto local:
por usuário, por inquilino e total. `cota_por_processo` é a única conta que faz essa repartição, e o teste
da trava confere que o produto teto_local × processos não passa do teto publicado."""

import asyncio
import collections
import datetime
import json
import logging
import select
import threading
import time

import psycopg2
from starlette.concurrency import run_in_threadpool

from app import limites
from app.jobs import servico
from app.jobs.contexto import ErroServico, Sessao
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings

log = logging.getLogger("plat.eventos")
KEEPALIVE_S = 15
DURACAO_MAX_S = 1800
FINAIS = ("concluido", "falhou", "cancelado")

# tetos da INSTALAÇÃO (não do processo): app/limites.py, seção "eventos em tempo real"
POR_USUARIO_MAX = limites.SSE_POR_USUARIO
POR_INQUILINO_MAX = limites.SSE_POR_INQUILINO
TOTAL_MAX = limites.SSE_TOTAL


def cota_por_processo(teto_instalacao: int) -> int:
    """Fatia do teto da instalação que cabe a ESTE processo. A unidade sobe `uvicorn --workers N`
    (deploy/plat-api.service); sem esta divisão o teto publicado valeria N vezes."""
    return max(1, teto_instalacao // max(1, settings.PLAT_API_PROCESSOS))


_trava = threading.Lock()
_assinantes: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = collections.defaultdict(set)
_por_usuario: collections.Counter = collections.Counter()
_por_inquilino: collections.Counter = collections.Counter()
_abertas = 0
_thread: threading.Thread | None = None


def _conectar():
    """Conexão do LISTEN pelo MESMO caminho do resto da aplicação: com a fábrica de cursor do ambiente.
    Sem ela o módulo inteiro ignora PLAT_SCHEMA e qualquer SQL daqui vai ao `plat` de produção mesmo
    rodando numa trilha isolada (achado F9)."""
    return psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)


def _garantir_thread() -> None:
    global _thread
    with _trava:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_escutar, name="plat-listen-plat_job", daemon=True)
            _thread.start()


def _escutar() -> None:
    while True:
        con = None
        try:
            con = _conectar()
            con.autocommit = True
            with con.cursor() as cur:
                cur.execute(f"LISTEN {settings.PLAT_CANAL_JOB}")
            while True:
                if select.select([con], [], [], 5.0) == ([], [], []):
                    continue
                con.poll()
                while con.notifies:
                    n = con.notifies.pop(0)
                    _distribuir(n.payload)
        except Exception as e:  # noqa: BLE001 — reconecta: só a preparação repete
            log.warning("LISTEN %s caiu: %s; reconectando em 1 s", settings.PLAT_CANAL_JOB, str(e).strip()[:200])
            try:
                if con is not None:
                    con.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)


def _distribuir(carga: str) -> None:
    try:
        dados = json.loads(carga)
    except ValueError:
        return
    jid = str(dados.get("job"))
    with _trava:
        alvos = list(_assinantes.get(jid, ()))
    for loop, fila in alvos:
        try:
            loop.call_soon_threadsafe(fila.put_nowait, dados)
        except RuntimeError:
            pass  # laço já fechado; a assinatura sai no finally do gerador


def _sse(evento: str, dados, id_: int | None = None) -> bytes:
    corpo = json.dumps(dados, ensure_ascii=False, default=str)
    cabeca = f"event: {evento}\n" + (f"id: {id_}\n" if id_ is not None else "")
    return (cabeca + f"data: {corpo}\n\n").encode("utf-8")


def reservar(sessao: Sessao) -> None:
    """Três tetos, do mais estreito ao mais largo: usuário, inquilino e instalação. O do inquilino é o que
    impede um inquilino de consumir o orçamento inteiro da máquina com muitos usuários."""
    global _abertas
    chave = (sessao.tenant_id, sessao.usuario_id)
    with _trava:
        if _por_usuario[chave] >= cota_por_processo(POR_USUARIO_MAX):
            raise ErroServico(429, "sse_limite",
                              f"máximo de {POR_USUARIO_MAX} conexões de eventos por usuário nesta instalação")
        if _por_inquilino[sessao.tenant_id] >= cota_por_processo(POR_INQUILINO_MAX):
            raise ErroServico(429, "sse_limite_inquilino",
                              f"máximo de {POR_INQUILINO_MAX} conexões de eventos por inquilino nesta instalação")
        if _abertas >= cota_por_processo(TOTAL_MAX):
            raise ErroServico(429, "sse_limite_instalacao",
                              f"máximo de {TOTAL_MAX} conexões de eventos abertas nesta instalação")
        _por_usuario[chave] += 1
        _por_inquilino[sessao.tenant_id] += 1
        _abertas += 1


def _liberar(sessao: Sessao) -> None:
    global _abertas
    chave = (sessao.tenant_id, sessao.usuario_id)
    with _trava:
        _por_usuario[chave] = max(0, _por_usuario[chave] - 1)
        if not _por_usuario[chave]:
            _por_usuario.pop(chave, None)
        _por_inquilino[sessao.tenant_id] = max(0, _por_inquilino[sessao.tenant_id] - 1)
        if not _por_inquilino[sessao.tenant_id]:
            _por_inquilino.pop(sessao.tenant_id, None)
        _abertas = max(0, _abertas - 1)


async def gerar(sessao: Sessao, job: dict, ultimo_id: int | None):
    """Gerador SSE; `job` já foi lido sob RLS pela rota (404 antes daqui). A reserva por usuário já foi feita."""
    jid = str(job["id"])
    _garantir_thread()
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue()
    with _trava:
        _assinantes[jid].add((loop, fila))
    try:
        yield _sse("estado", job)
        if ultimo_id is not None:
            linhas = await run_in_threadpool(servico.log, sessao, jid, ultimo_id, None, servico.LOG_LIMITE_MAX)
            for li in linhas["linhas"]:
                yield _sse("log", li, li["id"])
        if job["estado"] in FINAIS:
            yield _sse("fim", job)
            return
        inicio = time.monotonic()
        while time.monotonic() - inicio < DURACAO_MAX_S:
            try:
                ev = await asyncio.wait_for(fila.get(), KEEPALIVE_S)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            if str(ev.get("tenant_id")) != str(sessao.tenant_id):
                continue
            if "log" in ev:
                li = ev["log"]
                yield _sse("log", li, li.get("id"))
                continue
            try:
                job = await run_in_threadpool(servico.obter, sessao, jid)
            except ErroServico:
                yield _sse("fim", {"id": jid, "estado": "inexistente", "em": _agora()})
                return
            yield _sse("estado", job)
            if job["estado"] in FINAIS:
                yield _sse("fim", job)
                return
        yield _sse("fim", {"id": jid, "estado": job["estado"], "motivo": "tempo máximo da conexão (30 min); reconecte"})
    finally:
        with _trava:
            _assinantes[jid].discard((loop, fila))
            if not _assinantes[jid]:
                _assinantes.pop(jid, None)
        _liberar(sessao)


def _agora() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
