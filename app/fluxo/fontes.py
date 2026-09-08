"""Registro em memória das fontes de fluxo (item L2-14-a-ingestao-de-fluxos).

O processo `plat-fluxo` não vai ao banco por evento: carrega as fontes de `plat.fluxo_fonte` a cada
`RECARGA_S` (e sob pedido) e guarda, por fonte, o mapeamento já validado, o filtro já analisado, o balde de
fichas do teto por segundo e o buffer de pausa. É essa carga que torna o caminho do evento uma conta de
memória — nenhuma consulta, nenhuma decodificação de configuração por evento.

Buffer de pausa (cláusula do portão "fonte pausada não perde eventos do WebSocket por 30 s"): a fonte
pausada NÃO descarta; guarda em uma fila com teto DECLARADO de `FLUXO_BUFFER_PAUSA_S` segundos de eventos ao
teto da própria fonte (`limite_eventos_s`), nunca mais que `FLUXO_BUFFER_PAUSA_MAX`. Retomada, o buffer é
drenado na ordem de chegada. Cheio, o evento novo é descartado e contado — pausa não é armazenamento.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from app import db, limites
from app.db import Contexto
from app.fluxo import filtro as mod_filtro
from app.fluxo import limite as mod_limite
from app.fluxo import mapeamento as mod_mapeamento

log = logging.getLogger("plat.fluxo.fontes")
RECARGA_S = 5.0


def limites_tipos_ativos() -> tuple[str, ...]:
    """Tipos que exigem thread de conector no processo (os passivos não têm o que iniciar)."""
    from app.fluxo.tipos import TIPOS_CONECTOR

    return TIPOS_CONECTOR


@dataclass
class Fonte:
    id: str
    tenant_id: int
    dono_id: int
    dono_login: str
    tipo: str
    nome: str
    estado: str
    config: dict
    limite_eventos_s: int
    mapa: mod_mapeamento.Mapa
    filtro_texto: str | None
    filtro_ast: object | None
    balde: mod_limite.Balde
    buffer: deque = field(default_factory=deque)
    filtro_quebrado: str | None = None   # filtro que não compila: a fonte segue, o motivo fica visível

    @property
    def ativa(self) -> bool:
        return self.estado == "ativa"

    @property
    def buffer_max(self) -> int:
        return min(self.limite_eventos_s * limites.FLUXO_BUFFER_PAUSA_S, limites.FLUXO_BUFFER_PAUSA_MAX)


class Registro:
    def __init__(self):
        self._fontes: dict[str, Fonte] = {}
        self._trava = threading.Lock()
        self.carregado_em: float = 0.0
        self.erro_da_carga: str | None = None

    # ------------------------------------------------------------ leitura
    def obter(self, fonte_id: str) -> Fonte | None:
        with self._trava:
            return self._fontes.get(fonte_id)

    def todas(self) -> list[Fonte]:
        with self._trava:
            return list(self._fontes.values())

    def inquilino_da_fonte(self, fonte_id: str) -> int | None:
        f = self.obter(fonte_id)
        return None if f is None else f.tenant_id

    def contexto_do_inquilino(self, tenant_id: int) -> Contexto:
        """Contexto de escrita: inquilino da fonte, usuário = dono de alguma fonte dele (a RLS de
        `plat.fluxo_evento` só olha o inquilino; o usuário entra no registro de acesso)."""
        for f in self.todas():
            if f.tenant_id == tenant_id:
                return Contexto(tenant_id, f.dono_id, f.dono_login)
        return Contexto(tenant_id, 0, "plat-fluxo")

    # ------------------------------------------------------------ carga
    def carregar(self) -> int:
        """Lê TODAS as fontes de todos os inquilinos. Roda como `plat_app` sem contexto de inquilino, o que
        a RLS zeraria — por isso a consulta usa a função de leitura por inquilino: uma passada por inquilino
        que tem fonte. Devolve quantas fontes ficaram no registro."""
        try:
            with db.db() as cur:
                cur.execute("SELECT DISTINCT tenant_id FROM plat.fluxo_fonte")
                inquilinos = [r["tenant_id"] for r in cur.fetchall()]
        except Exception as e:  # noqa: BLE001 — banco fora: mantém o registro anterior e segue
            self.erro_da_carga = f"{type(e).__name__}: {e}"
            log.exception("fluxo: lista de inquilinos com fonte não lida")
            return len(self._fontes)

        novas: dict[str, Fonte] = {}
        for tenant_id in inquilinos:
            try:
                with db.db(Contexto(tenant_id, 0, "plat-fluxo")) as cur:
                    cur.execute(
                        "SELECT f.id, f.tenant_id, f.dono_id, u.login AS dono_login, f.tipo, f.nome, f.estado, "
                        "f.config, f.limite_eventos_s, f.mapeamento, f.filtro "
                        "FROM plat.fluxo_fonte f JOIN plat.usuario u ON u.id = f.dono_id"
                    )
                    linhas = cur.fetchall()
            except Exception as e:  # noqa: BLE001
                self.erro_da_carga = f"{type(e).__name__}: {e}"
                log.exception("fluxo: fontes do inquilino %s não lidas", tenant_id)
                continue
            for r in linhas:
                fonte = self._montar(r)
                if fonte is not None:
                    novas[fonte.id] = fonte

        with self._trava:
            # preserva balde e buffer das fontes que continuam existindo (recarregar não pode zerar o teto
            # nem jogar fora o que a fonte pausada guardou)
            for fid, nova in novas.items():
                antiga = self._fontes.get(fid)
                if antiga is not None:
                    nova.balde = antiga.balde
                    nova.balde.ajustar(nova.limite_eventos_s)
                    nova.buffer = antiga.buffer
            self._fontes = novas
            self.carregado_em = time.time()
            self.erro_da_carga = None
        return len(novas)

    def _montar(self, r: dict) -> Fonte | None:
        fid = str(r["id"])
        try:
            mapa = mod_mapeamento.de_json(r["mapeamento"] or {})
        except mod_mapeamento.ErroMapeamento:
            log.exception("fluxo: mapeamento da fonte %s inválido; fonte ignorada", fid)
            return None
        quebrado, ast = None, None
        try:
            ast = mod_filtro.compilar(r["filtro"])
        except mod_filtro.ErroFiltro as e:
            quebrado = e.detalhe
            log.warning("fluxo: filtro da fonte %s não compila (%s); a fonte aceita tudo", fid, e.detalhe)
        return Fonte(
            id=fid, tenant_id=r["tenant_id"], dono_id=r["dono_id"], dono_login=r["dono_login"],
            tipo=r["tipo"], nome=r["nome"], estado=r["estado"], config=r["config"] or {},
            limite_eventos_s=r["limite_eventos_s"], mapa=mapa, filtro_texto=r["filtro"], filtro_ast=ast,
            balde=mod_limite.Balde(taxa=float(r["limite_eventos_s"])), filtro_quebrado=quebrado,
        )
