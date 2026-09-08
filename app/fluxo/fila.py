"""Fila em memória e escrita em lote no Postgres (item L2-14-a-ingestao-de-fluxos; decisão C14 do
L2_CONCEITO). Um lote por segundo, por inquilino, com métricas por fonte.

MEDIDO nesta trilha (e é por isso que NÃO se usa COPY, apesar de a decisão C14 dizer "COPY"):

    psycopg2.errors.FeatureNotSupported: COPY FROM not supported with row-level security
    HINT: Use INSERT statements instead.

`plat.fluxo_evento` tem RLS por inquilino — que é o isolamento que o portão do item exige — logo COPY FROM
está fora da mesa enquanto a escrita passar pela role `plat_app`. O substituto é UM `INSERT ... SELECT FROM
unnest(...)` por lote, com um array por coluna: uma única ida ao servidor, uma única análise de comando, e a
política de RLS aplicada linha a linha pelo Postgres. Medido nesta máquina (carga 9, 12 núcleos):
10.000 linhas em 160 ms = 62.419 linhas/s — seis vezes o alvo de 10 mil eventos/s do portão.

A fila é um `deque` com teto (`FLUXO_FILA_MAX`): cheia, o evento novo é DESCARTADO e CONTADO. Descartar o
evento novo (e não o mais antigo) mantém a ordem do que já foi aceito e torna a perda visível na métrica em
vez de silenciosa.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app import db, limites
from app.db import Contexto

log = logging.getLogger("plat.fluxo.fila")
UTC = datetime.UTC

SQL_INSERIR = (
    "INSERT INTO plat.fluxo_evento(tenant_id, fonte_id, rastro_id, tempo_evento, recebido_em, geom, atributos) "
    "SELECT %s, %s::uuid, r, t::timestamptz, rec::timestamptz, "
    "CASE WHEN x IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(x, y), 4326) END, a::jsonb "
    "FROM unnest(%s::text[], %s::text[], %s::text[], %s::float8[], %s::float8[], %s::text[]) "
    "AS u(r, t, rec, x, y, a)"
)


@dataclass
class Contadores:
    recebidos: int = 0
    aceitos: int = 0
    descartados_filtro: int = 0
    descartados_limite: int = 0
    descartados_invalido: int = 0
    atraso_ms_ultimo: int | None = None
    atrasos: list = field(default_factory=list)   # amostra da janela corrente, para a mediana
    ultimo_evento_em: datetime.datetime | None = None
    motivos: dict = field(default_factory=dict)   # motivo de descarte → contagem (só para o /saude)

    def somar_motivo(self, motivo: str) -> None:
        self.motivos[motivo] = self.motivos.get(motivo, 0) + 1

    def instantaneo(self) -> dict:
        atrasos = sorted(self.atrasos)
        p50 = atrasos[len(atrasos) // 2] if atrasos else None
        return {
            "recebidos": self.recebidos, "aceitos": self.aceitos,
            "descartados_filtro": self.descartados_filtro, "descartados_limite": self.descartados_limite,
            "descartados_invalido": self.descartados_invalido,
            "atraso_ms_ultimo": self.atraso_ms_ultimo, "atraso_ms_p50": p50,
            "ultimo_evento_em": self.ultimo_evento_em.isoformat() if self.ultimo_evento_em else None,
            "motivos": dict(self.motivos),
        }


@dataclass
class _Linha:
    tenant_id: int
    fonte_id: str
    rastro_id: str | None
    tempo_evento: datetime.datetime
    recebido_em: datetime.datetime
    lon: float | None
    lat: float | None
    atributos: dict


class Fila:
    """Fila única do processo; a escrita agrupa por (inquilino, fonte) e faz um INSERT por grupo."""

    def __init__(self, *, teto: int = limites.FLUXO_FILA_MAX, intervalo_s: float = limites.FLUXO_LOTE_INTERVALO_S):
        self._itens: deque[_Linha] = deque()
        self._teto = teto
        self._intervalo = intervalo_s
        self._trava = threading.Lock()
        self._acordar = threading.Event()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.contadores: dict[str, Contadores] = {}
        self.gravados = 0
        self.lotes = 0
        self.erros_de_escrita = 0

    # ------------------------------------------------------------ contadores
    def conta(self, fonte_id: str) -> Contadores:
        c = self.contadores.get(fonte_id)
        if c is None:
            c = self.contadores[fonte_id] = Contadores()
        return c

    # ------------------------------------------------------------ entrada
    def enfileirar(self, tenant_id: int, fonte_id: str, evento, *, recebido_em=None) -> bool:
        """False quando a fila está cheia (evento descartado e contado)."""
        c = self.conta(fonte_id)
        with self._trava:
            if len(self._itens) >= self._teto:
                c.descartados_limite += 1
                c.somar_motivo("fila_cheia")
                return False
            recebido = recebido_em or datetime.datetime.now(UTC)
            self._itens.append(_Linha(tenant_id, fonte_id, evento.rastro_id, evento.tempo_evento, recebido,
                                      evento.lon, evento.lat, evento.atributos))
        atraso = int((recebido - evento.tempo_evento).total_seconds() * 1000)
        c.aceitos += 1
        c.atraso_ms_ultimo = atraso
        c.ultimo_evento_em = evento.tempo_evento
        if len(c.atrasos) < 10_000:
            c.atrasos.append(atraso)
        self._acordar.set()
        return True

    def tamanho(self) -> int:
        with self._trava:
            return len(self._itens)

    # ------------------------------------------------------------ escrita
    def _tirar_lote(self) -> list[_Linha]:
        with self._trava:
            n = min(len(self._itens), limites.FLUXO_LOTE_LINHAS_MAX)
            return [self._itens.popleft() for _ in range(n)]

    def escrever_uma_vez(self, contexto_de_inquilino) -> int:
        """Drena um lote e grava. `contexto_de_inquilino(tenant_id)` devolve o `db.Contexto` da escrita.
        Devolve quantas linhas foram gravadas. Nunca levanta: falha de banco devolve as linhas à fila."""
        lote = self._tirar_lote()
        if not lote:
            return 0
        grupos: dict[tuple[int, str], list[_Linha]] = {}
        for linha in lote:
            grupos.setdefault((linha.tenant_id, linha.fonte_id), []).append(linha)
        gravadas = 0
        for (tenant_id, fonte_id), linhas in grupos.items():
            try:
                with db.db(contexto_de_inquilino(tenant_id)) as cur:
                    cur.execute(SQL_INSERIR, (
                        tenant_id, fonte_id,
                        [x.rastro_id for x in linhas],
                        [x.tempo_evento.isoformat() for x in linhas],
                        [x.recebido_em.isoformat() for x in linhas],
                        [x.lon for x in linhas],
                        [x.lat for x in linhas],
                        [json.dumps(x.atributos, ensure_ascii=False, default=str) for x in linhas],
                    ))
                gravadas += len(linhas)
            except Exception:  # noqa: BLE001 — banco fora do ar não pode matar o processo nem perder o lote
                self.erros_de_escrita += 1
                log.exception("fluxo: lote de %d eventos da fonte %s não gravado; devolvido à fila",
                              len(linhas), fonte_id)
                with self._trava:
                    self._itens.extendleft(reversed(linhas))
                    if len(self._itens) > self._teto:
                        excedente = len(self._itens) - self._teto
                        for _ in range(excedente):
                            self._itens.pop()
                        self.conta(fonte_id).descartados_limite += excedente
        self.gravados += gravadas
        self.lotes += 1
        return gravadas

    def gravar_metricas(self, contexto_de_inquilino, inquilino_da_fonte) -> None:
        """Espelha os contadores em `plat.fluxo_metrica` (uma linha por fonte). Nunca levanta."""
        for fonte_id, c in list(self.contadores.items()):
            tenant_id = inquilino_da_fonte(fonte_id)
            if tenant_id is None:
                continue
            inst = c.instantaneo()
            try:
                with db.db(contexto_de_inquilino(tenant_id)) as cur:
                    cur.execute(
                        "INSERT INTO plat.fluxo_metrica(fonte_id, tenant_id, recebidos, aceitos, "
                        "descartados_filtro, descartados_limite, descartados_invalido, atraso_ms_ultimo, "
                        "atraso_ms_p50, ultimo_evento_em, atualizado_em) "
                        "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
                        "ON CONFLICT (fonte_id) DO UPDATE SET recebidos = EXCLUDED.recebidos, "
                        "aceitos = EXCLUDED.aceitos, descartados_filtro = EXCLUDED.descartados_filtro, "
                        "descartados_limite = EXCLUDED.descartados_limite, "
                        "descartados_invalido = EXCLUDED.descartados_invalido, "
                        "atraso_ms_ultimo = EXCLUDED.atraso_ms_ultimo, atraso_ms_p50 = EXCLUDED.atraso_ms_p50, "
                        "ultimo_evento_em = EXCLUDED.ultimo_evento_em, atualizado_em = now()",
                        (fonte_id, tenant_id, inst["recebidos"], inst["aceitos"], inst["descartados_filtro"],
                         inst["descartados_limite"], inst["descartados_invalido"], inst["atraso_ms_ultimo"],
                         inst["atraso_ms_p50"], c.ultimo_evento_em),
                    )
            except Exception:  # noqa: BLE001 — métrica nunca derruba a ingestão
                log.exception("fluxo: métrica da fonte %s não gravada", fonte_id)

    # ------------------------------------------------------------ laço
    def iniciar(self, contexto_de_inquilino, inquilino_da_fonte) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._laco, name="fluxo-escritor", daemon=True,
                                        args=(contexto_de_inquilino, inquilino_da_fonte))
        self._thread.start()

    def parar(self, espera_s: float = 5.0) -> None:
        self._parar.set()
        self._acordar.set()
        if self._thread is not None:
            self._thread.join(timeout=espera_s)
            self._thread = None

    def _laco(self, contexto_de_inquilino, inquilino_da_fonte) -> None:
        ultima_metrica = 0.0
        while not self._parar.is_set():
            self._acordar.wait(timeout=self._intervalo)
            self._acordar.clear()
            while self.escrever_uma_vez(contexto_de_inquilino) and not self._parar.is_set():
                pass
            agora = time.monotonic()
            if agora - ultima_metrica >= self._intervalo:
                ultima_metrica = agora
                self.gravar_metricas(contexto_de_inquilino, inquilino_da_fonte)
        # parada limpa: o que sobrou na fila é gravado antes de sair
        while self.escrever_uma_vez(contexto_de_inquilino):
            pass
        self.gravar_metricas(contexto_de_inquilino, inquilino_da_fonte)


def contexto_do_inquilino(tenant_id: int) -> Contexto:
    """Contexto de escrita do processo plat-fluxo: o inquilino é o da FONTE, o usuário é o DONO dela — quem
    resolve os dois é `app/fluxo/fontes.py`, e é por isso que este módulo recebe a função pronta."""
    return Contexto(tenant_id, 0, "plat-fluxo")
