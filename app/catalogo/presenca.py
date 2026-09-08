"""Presença em documento (item L5-13-edicao-concorrente; L5_CONCEITO D12: "presença por SSE, quem está no documento
e em que nó"; "bloqueio leve por nó: aviso, não trava"). Sem tabela: a presença é efêmera (some sozinha em
`EXPIRA_S` sem batimento). Registro em memória por processo, com fan-out entre processos por NOTIFY no canal
`<PLAT_CANAL_JOB>_presenca` (a API de produção roda com 2 workers, L7-19; um LISTEN por processo, mesmo desenho de
app/jobs/eventos.py), para que quem abriu o documento num worker veja quem abriu no outro. O batimento
(`POST /api/itens/{id}/presenca`) grava a entrada e notifica; o fluxo SSE (`GET .../presenca/eventos`) manda a
lista inteira a cada mudança e um keepalive. Só quem pode LER o item (RLS de plat.item, 404 antes daqui) entra;
o que sai é login, nome, nó selecionado e instante — nunca o documento."""

from __future__ import annotations

import asyncio
import collections
import datetime
import json
import logging
import select
import threading
import time

import psycopg2

from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings

log = logging.getLogger("plat.presenca")
EXPIRA_S = 12          # sem batimento por mais que isto, a presença some (o cliente bate a cada 5 s)
KEEPALIVE_S = 15
DURACAO_MAX_S = 1800
POR_USUARIO_MAX = 50  # conexões de presença são baratas (1 varredura/s) e o e2e abre muitas abas
CAMPOS = ("usuario_id", "login", "nome", "sessao", "no", "em")

_trava = threading.Lock()
# chave = (tenant_id, item_id) -> {sessao: entrada}; `sessao` é um id opaco por aba (gerado pelo cliente)
_presentes: dict[tuple[int, str], dict[str, dict]] = collections.defaultdict(dict)
_assinantes: dict[tuple[int, str], set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = collections.defaultdict(set)
_por_usuario: collections.Counter = collections.Counter()
_thread: threading.Thread | None = None


def canal() -> str:
    return f"{settings.PLAT_CANAL_JOB}_presenca"


def _agora() -> float:
    return time.time()


def _iso(t: float) -> str:
    return datetime.datetime.fromtimestamp(t, datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _limpar(chave: tuple[int, str]) -> None:
    limite = _agora() - EXPIRA_S
    entradas = _presentes.get(chave)
    if not entradas:
        return
    for sessao in [s for s, e in entradas.items() if e["_em"] < limite]:
        entradas.pop(sessao, None)
    if not entradas:
        _presentes.pop(chave, None)


def listar(tenant_id: int, item_id: str) -> list[dict]:
    chave = (tenant_id, item_id)
    with _trava:
        _limpar(chave)
        entradas = sorted(_presentes.get(chave, {}).values(), key=lambda e: e["_em"])
        return [{c: e[c] for c in CAMPOS} for e in entradas]


def _aplicar(tenant_id: int, item_id: str, sessao: str, entrada: dict | None) -> None:
    chave = (tenant_id, item_id)
    with _trava:
        if entrada is None:
            _presentes.get(chave, {}).pop(sessao, None)
            if not _presentes.get(chave):
                _presentes.pop(chave, None)
        else:
            _presentes[chave][sessao] = entrada
        _limpar(chave)
        alvos = list(_assinantes.get(chave, ()))
    for loop, fila in alvos:
        try:
            loop.call_soon_threadsafe(fila.put_nowait, True)
        except RuntimeError:
            pass


def _entrada(usuario_id: int, login: str, nome: str, sessao: str, no: str | None, em: float) -> dict:
    return {"usuario_id": usuario_id, "login": login, "nome": nome, "sessao": sessao, "no": no,
            "em": _iso(em), "_em": em}


def bater(cur, tenant_id: int, item_id: str, usuario_id: int, login: str, nome: str, sessao: str, no: str | None,
          sair: bool = False) -> list[dict]:
    """Batimento (ou saída) de uma aba: aplica localmente e avisa os outros processos por NOTIFY. Devolve a
    lista atual (o próprio caller incluído) — a primeira resposta já vale como "quem está aqui"."""
    em = _agora()
    carga = {"t": tenant_id, "i": item_id, "s": sessao, "sair": sair,
             "e": None if sair else {"usuario_id": usuario_id, "login": login, "nome": nome, "no": no, "em": em}}
    _aplicar(tenant_id, item_id, sessao, None if sair else _entrada(usuario_id, login, nome, sessao, no, em))
    try:
        cur.execute("SELECT pg_notify(%s, %s)", (canal(), json.dumps(carga, ensure_ascii=False)))
    except psycopg2.Error as e:  # a presença local continua valendo; só o outro processo deixa de ver
        log.warning("pg_notify de presença falhou: %s", str(e).strip()[:200])
    return listar(tenant_id, item_id)


# ---------------------------------------------------------------- LISTEN (fan-out entre processos)
def _conectar():
    return psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)


def _garantir_thread() -> None:
    global _thread
    with _trava:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_escutar, name="plat-listen-presenca", daemon=True)
            _thread.start()


def _escutar() -> None:
    while True:
        con = None
        try:
            con = _conectar()
            con.autocommit = True
            with con.cursor() as cur:
                cur.execute(f"LISTEN {canal()}")
            while True:
                if select.select([con], [], [], 5.0) == ([], [], []):
                    continue
                con.poll()
                while con.notifies:
                    n = con.notifies.pop(0)
                    _receber(n.payload, n.pid, con.get_backend_pid())
        except Exception as e:  # noqa: BLE001 — reconecta: só a preparação repete
            log.warning("LISTEN %s caiu: %s; reconectando em 1 s", canal(), str(e).strip()[:200])
            try:
                if con is not None:
                    con.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)


def _receber(carga: str, pid_origem: int, pid_proprio: int) -> None:
    try:
        d = json.loads(carga)
        t, i, s = int(d["t"]), str(d["i"]), str(d["s"])
    except (ValueError, KeyError, TypeError):
        return
    e = d.get("e")
    if d.get("sair") or not e:
        _aplicar(t, i, s, None)
        return
    _aplicar(t, i, s, _entrada(int(e["usuario_id"]), str(e["login"]), str(e["nome"]), s, e.get("no"), float(e["em"])))


# ---------------------------------------------------------------- SSE
def _sse(evento: str, dados) -> bytes:
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False, default=str)}\n\n".encode()


def reservar(tenant_id: int, usuario_id: int) -> bool:
    chave = (tenant_id, usuario_id)
    with _trava:
        if _por_usuario[chave] >= POR_USUARIO_MAX:
            return False
        _por_usuario[chave] += 1
        return True


def _liberar(tenant_id: int, usuario_id: int) -> None:
    chave = (tenant_id, usuario_id)
    with _trava:
        _por_usuario[chave] = max(0, _por_usuario[chave] - 1)


async def gerar(tenant_id: int, item_id: str, usuario_id: int, desconectou=None):
    """Gerador SSE: manda `presenca` (lista inteira) na conexão e a cada mudança; keepalive; expira os batimentos
    velhos mesmo sem mudança (varredura a cada segundo enquanto houver alguém). `desconectou` (corrotina, a
    `request.is_disconnected` da rota) encerra o gerador na varredura seguinte à saída do cliente — e libera a vaga
    por usuário mesmo quando o servidor não cancela a tarefa por conta própria."""
    _garantir_thread()
    chave = (tenant_id, item_id)
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue()
    with _trava:
        _assinantes[chave].add((loop, fila))
    try:
        ultimo = listar(tenant_id, item_id)
        yield _sse("presenca", ultimo)
        inicio = time.monotonic()
        ultimo_keepalive = time.monotonic()
        while time.monotonic() - inicio < DURACAO_MAX_S:
            try:
                await asyncio.wait_for(fila.get(), 1.0)
            except TimeoutError:
                pass
            if desconectou is not None and await desconectou():
                return
            atual = listar(tenant_id, item_id)
            if atual != ultimo:
                ultimo = atual
                yield _sse("presenca", atual)
                ultimo_keepalive = time.monotonic()
            elif time.monotonic() - ultimo_keepalive >= KEEPALIVE_S:
                yield b": keepalive\n\n"
                ultimo_keepalive = time.monotonic()
        yield _sse("fim", {"motivo": "tempo máximo da conexão (30 min); reconecte"})
    finally:
        with _trava:
            _assinantes[chave].discard((loop, fila))
            if not _assinantes[chave]:
                _assinantes.pop(chave, None)
        _liberar(tenant_id, usuario_id)
