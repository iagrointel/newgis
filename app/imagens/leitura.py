"""Registro de leitura de ladrilho por token (item L1-02-tiles-token).

Por que agregar em vez de gravar linha por ladrilho: uma tela de mapa pede ~40 ladrilhos e a bancada
deste item mede milhares por segundo — uma linha por leitura em `plat.log_acesso` transformaria a tabela
de auditoria em fila de escrita. Aqui a contagem sobe em memória e desce ao banco por lote, numa linha
por (inquilino, token, item, dia). O token nunca é gravado; só o `token_id`, como no resto da casa.

Perda aceita e declarada: se o processo morre antes da descarga, perdem-se no máximo os eventos dos
últimos `INTERVALO_S` segundos. A contagem é de uso, não de cobrança fiscal — quem cobra é o L7-09, que
lê esta tabela sabendo disso.
"""

from __future__ import annotations

import datetime
import logging
import threading

from app import db

INTERVALO_S = 2.0
MAX_PENDENTE = 500

log = logging.getLogger("plat.tiles.leitura")
_trava = threading.Lock()
_pendente: dict[tuple[int, int, str, datetime.date], list[int]] = {}
_ultima_descarga = 0.0


def contar(tenant_id: int, token_id: int, item: str, bytes_saida: int, erro: bool = False) -> None:
    """Soma um evento ao agregado em memória; descarrega quando passa do intervalo ou do teto."""
    global _ultima_descarga
    if not tenant_id or not token_id:
        return
    import time

    chave = (int(tenant_id), int(token_id), str(item)[:128], datetime.date.today())
    with _trava:
        alvo = _pendente.setdefault(chave, [0, 0, 0])
        if erro:
            alvo[2] += 1
        else:
            alvo[0] += 1
            alvo[1] += int(bytes_saida or 0)
        agora = time.monotonic()
        vencido = (agora - _ultima_descarga) >= INTERVALO_S or len(_pendente) >= MAX_PENDENTE
        if not vencido:
            return
        lote = dict(_pendente)
        _pendente.clear()
        _ultima_descarga = agora
    _gravar(lote)


def descarregar() -> int:
    """Força a descarga (usada pelo teste e pelo desligamento). Devolve quantas linhas foram escritas."""
    with _trava:
        lote = dict(_pendente)
        _pendente.clear()
    return _gravar(lote)


def _gravar(lote: dict) -> int:
    if not lote:
        return 0
    try:
        with db.db() as cur:
            for (tenant_id, token_id, item, dia), (n, bytes_saida, erros) in lote.items():
                cur.execute(
                    "SELECT plat.tile_leitura_registrar(%s, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, token_id, item, dia, n, bytes_saida, erros),
                )
        return len(lote)
    except Exception as e:  # registro de uso nunca derruba a entrega do ladrilho
        log.warning("descarga do registro de leitura falhou (%s eventos perdidos): %s", len(lote), e)
        return 0


def contagem(cur, tenant_id: int, dias: int = 30) -> list[dict]:
    """Contagem por token no inquilino atual (RLS): o que a tela de tokens e o L7-09 leem."""
    cur.execute(
        """
        SELECT l.token_id, k.nome AS token_nome, k.prefixo, k.revogado_em,
               sum(l.ladrilhos)::bigint AS ladrilhos, sum(l.bytes)::bigint AS bytes,
               sum(l.erros)::bigint AS erros, count(DISTINCT l.item) AS itens,
               min(l.primeiro_em) AS primeiro_em, max(l.ultimo_em) AS ultimo_em
          FROM plat.tile_leitura l
          JOIN plat.token_servico k ON k.id = l.token_id
         WHERE l.tenant_id = %s AND l.dia >= current_date - %s::int
         GROUP BY l.token_id, k.nome, k.prefixo, k.revogado_em
         ORDER BY ladrilhos DESC
        """,
        (tenant_id, dias),
    )
    return [dict(r) for r in cur.fetchall()]


__all__ = ["INTERVALO_S", "contagem", "contar", "descarregar"]
