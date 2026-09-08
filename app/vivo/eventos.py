"""Fluxo de eventos de camada por SSE (item L2-06-d-atualizacao-viva-sse).

Desenho copiado, de propósito, do progresso de job (`app/jobs/eventos.py`, ADR 0003 seção 5) — a plataforma
tem UM mecanismo de empurrão, não dois: gatilho no banco → `pg_notify` → UM thread LISTEN por processo →
fan-out para as filas asyncio dos clientes. O que muda aqui é o recorte: em vez de assinar um job, o cliente
assina uma LISTA DE CAMADAS, e o filtro é (inquilino, camada).

Garantias que o portão do item cobra e onde elas moram neste arquivo:
* nenhum evento para cliente de outro inquilino — `_distribuir` compara `tenant_id` antes de enfileirar e o
  gerador compara de novo antes de escrever no fluxo (defesa em duas camadas, a segunda sobrevive a um erro
  de indexação da primeira);
* limite de conexões por inquilino e por usuário declarado (`app/limites.py`) — `reservar` levanta 429;
* reconexão com `Last-Event-ID` — `plat.camada_eventos_desde` reenvia o que passou na janela de retenção;
* coalescência: um evento por COMANDO (o gatilho é `FOR EACH STATEMENT`), e o navegador ainda agrupa por
  fonte com atraso de 1 s (`web/js/vivo/assinatura.js`); este módulo não segura evento.
"""

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
from starlette.concurrency import run_in_threadpool

from app import db as banco
from app import limites
from app.db import Contexto
from app.erros import ErroAPI
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings

log = logging.getLogger("plat.vivo")

KEEPALIVE_S = limites.VIVO_SSE_KEEPALIVE_S
DURACAO_MAX_S = limites.VIVO_SSE_DURACAO_MAX_S
POR_INQUILINO_MAX = limites.VIVO_SSE_POR_INQUILINO
POR_USUARIO_MAX = limites.VIVO_SSE_POR_USUARIO
CAMADAS_MAX = limites.VIVO_SSE_CAMADAS_MAX
JANELA_MIN = limites.VIVO_EVENTO_JANELA_MIN
PODA_A_CADA_S = 60

_trava = threading.Lock()
# assinante = (loop, fila, tenant_id, frozenset de camadas); guardado por camada para o fan-out ser O(1)
_assinantes: dict[str, set[tuple]] = collections.defaultdict(set)
_por_inquilino: collections.Counter = collections.Counter()
_por_usuario: collections.Counter = collections.Counter()
_thread: threading.Thread | None = None


def _conectar():
    """Conexão do LISTEN pela fábrica de cursor do ambiente — sem ela o módulo ignora PLAT_SCHEMA e uma
    trilha isolada escutaria o canal de produção (mesmo achado F9 que `app/jobs/eventos.py` documenta)."""
    return psycopg2.connect(settings.PLAT_DSN, cursor_factory=CursorSchemaAmbiente)


def _garantir_thread() -> None:
    global _thread
    with _trava:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_escutar, name="plat-listen-camada", daemon=True)
            _thread.start()


def _escutar() -> None:
    while True:
        con = None
        try:
            con = _conectar()
            con.autocommit = True
            with con.cursor() as cur:
                cur.execute(f"LISTEN {settings.PLAT_CANAL_CAMADA}")
            ultima_poda = 0.0
            while True:
                if select.select([con], [], [], 5.0) == ([], [], []):
                    ultima_poda = _podar_se_na_hora(con, ultima_poda)
                    continue
                con.poll()
                while con.notifies:
                    n = con.notifies.pop(0)
                    _distribuir(n.payload)
                ultima_poda = _podar_se_na_hora(con, ultima_poda)
        except Exception as e:  # noqa: BLE001 — reconecta: só a preparação repete (disciplina do pool)
            log.warning("LISTEN %s caiu: %s; reconectando em 1 s", settings.PLAT_CANAL_CAMADA, str(e).strip()[:200])
            try:
                if con is not None:
                    con.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)


def _podar_se_na_hora(con, ultima: float) -> float:
    """Retenção da janela de reconexão. Roda no thread do LISTEN (nunca no caminho da edição) e no máximo
    uma vez por minuto — a tabela é pequena por construção e o DELETE usa o índice por tempo."""
    agora = time.monotonic()
    if agora - ultima < PODA_A_CADA_S:
        return ultima
    try:
        with con.cursor() as cur:
            cur.execute("SELECT plat.camada_eventos_podar(%s) AS n", (JANELA_MIN,))
    except Exception as e:  # noqa: BLE001 — poda é higiene, nunca derruba o fluxo de eventos
        log.warning("poda de camada_evento falhou: %s", str(e).strip()[:200])
    return agora


def _distribuir(carga: str) -> None:
    try:
        dados = json.loads(carga)
    except ValueError:
        return
    camada = str(dados.get("camada"))
    tenant = dados.get("tenant_id")
    with _trava:
        alvos = list(_assinantes.get(camada, ()))
    for loop, fila, tenant_assinante, _camadas in alvos:
        if str(tenant_assinante) != str(tenant):
            continue
        try:
            loop.call_soon_threadsafe(fila.put_nowait, dados)
        except RuntimeError:
            pass  # laço já fechado; a assinatura sai no finally do gerador


def _sse(evento: str, dados, id_: int | None = None) -> bytes:
    corpo = json.dumps(dados, ensure_ascii=False, default=str)
    cabeca = f"event: {evento}\n" + (f"id: {id_}\n" if id_ is not None else "")
    return (cabeca + f"data: {corpo}\n\n").encode("utf-8")


def reservar(tenant_id: int, usuario_id: int) -> None:
    """Duas cotas: por INQUILINO (o limite que o item manda declarar) e por USUÁRIO (uma aba aberta demais
    de uma pessoa não pode consumir a cota da empresa inteira)."""
    with _trava:
        if _por_inquilino[tenant_id] >= POR_INQUILINO_MAX:
            raise ErroAPI(429, "sse_limite_inquilino",
                          f"máximo de {POR_INQUILINO_MAX} conexões de eventos por inquilino neste processo")
        if _por_usuario[(tenant_id, usuario_id)] >= POR_USUARIO_MAX:
            raise ErroAPI(429, "sse_limite_usuario",
                          f"máximo de {POR_USUARIO_MAX} conexões de eventos por usuário neste processo")
        _por_inquilino[tenant_id] += 1
        _por_usuario[(tenant_id, usuario_id)] += 1


def _liberar(tenant_id: int, usuario_id: int) -> None:
    with _trava:
        _por_inquilino[tenant_id] = max(0, _por_inquilino[tenant_id] - 1)
        _por_usuario[(tenant_id, usuario_id)] = max(0, _por_usuario[(tenant_id, usuario_id)] - 1)


def versoes(ctx: Contexto, camadas: list[str]) -> dict[str, int]:
    """Versão corrente de cada camada assinada (base para o cliente decidir se já está atualizado)."""
    with banco.db(ctx, somente_leitura=True) as cur:
        cur.execute(
            "SELECT camada_id, versao FROM plat.camada_versao WHERE camada_id = ANY(%s::uuid[])",
            (list(camadas),),
        )
        atuais = {str(r["camada_id"]): int(r["versao"]) for r in cur.fetchall()}
    return {c: atuais.get(c, 0) for c in camadas}


def perdidos(ctx: Contexto, camadas: list[str], desde: int) -> list[dict]:
    with banco.db(ctx, somente_leitura=True) as cur:
        cur.execute(
            "SELECT id, camada_id, versao, operacao, em FROM plat.camada_eventos_desde(%s, %s::uuid[], %s)",
            (desde, list(camadas), 500),
        )
        return [dict(r) for r in cur.fetchall()]


def _evento_de_camada(dados: dict) -> dict:
    return {
        "camada": str(dados.get("camada") or dados.get("camada_id")),
        "versao": int(dados.get("versao") or 0),
        "operacao": dados.get("operacao"),
        "em": dados.get("em"),
    }


async def gerar(ctx: Contexto, tenant_id: int, usuario_id: int, camadas: list[str], ultimo_id: int | None):
    """Gerador SSE. A rota já resolveu as camadas sob RLS (404 antes daqui) e já fez a reserva de cota."""
    _garantir_thread()
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue()
    conjunto = frozenset(camadas)
    assinatura = (loop, fila, tenant_id, conjunto)
    with _trava:
        for c in conjunto:
            _assinantes[c].add(assinatura)
    try:
        atuais = await run_in_threadpool(versoes, ctx, camadas)
        yield _sse("pronto", {"camadas": camadas, "versoes": atuais, "em": _agora(),
                              "keepalive_s": KEEPALIVE_S, "janela_reconexao_min": JANELA_MIN})
        if ultimo_id is not None:
            for ev in await run_in_threadpool(perdidos, ctx, camadas, ultimo_id):
                yield _sse("camada", _evento_de_camada(ev), ev["id"])
        inicio = time.monotonic()
        while time.monotonic() - inicio < DURACAO_MAX_S:
            try:
                ev = await asyncio.wait_for(fila.get(), KEEPALIVE_S)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            if str(ev.get("tenant_id")) != str(tenant_id):
                continue  # segunda barreira: nada de outro inquilino chega ao fluxo
            if str(ev.get("camada")) not in conjunto:
                continue
            yield _sse("camada", _evento_de_camada(ev), ev.get("id"))
        yield _sse("fim", {"motivo": "tempo máximo da conexão; reconecte", "em": _agora()})
    finally:
        with _trava:
            for c in conjunto:
                _assinantes[c].discard(assinatura)
                if not _assinantes[c]:
                    _assinantes.pop(c, None)
        _liberar(tenant_id, usuario_id)


def _agora() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
