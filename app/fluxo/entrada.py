"""O caminho de UM lote de eventos, da lista de registros crus até a fila de escrita (item
L2-14-a-ingestao-de-fluxos). Etapas, nesta ordem, e todas contadas:

  1. teto por segundo (`limite.Balde`)  → `descartados_limite`
  2. mapeamento (`mapeamento.aplicar`)  → `descartados_invalido` (com o motivo)
  3. filtro de entrada (`filtro.aceita`)→ `descartados_filtro`
  4. fila (ou buffer de pausa)

O teto vem ANTES do mapeamento de propósito: numa rajada acima do teto, o trabalho de converter o evento é
justamente o que não se quer gastar. O preço é que um evento descartado por teto não é conferido — e por
isso a contagem de inválidos vale só sobre o que passou pelo teto, o que está declarado no manual.
"""

from __future__ import annotations

import datetime

from app.fluxo import filtro as mod_filtro
from app.fluxo import mapeamento as mod_mapeamento

UTC = datetime.UTC


def ingerir(fonte, registros: list, fila, *, agora: datetime.datetime | None = None) -> dict:
    """Devolve o resumo do lote: recebidos, aceitos, descartados por motivo."""
    agora = agora or datetime.datetime.now(UTC)
    contador = fila.conta(fonte.id)
    contador.recebidos += len(registros)
    resumo = {"recebidos": len(registros), "aceitos": 0, "descartados_limite": 0,
              "descartados_invalido": 0, "descartados_filtro": 0, "em_buffer": 0}

    passam = fonte.balde.permitir(len(registros))
    if passam < len(registros):
        excesso = len(registros) - passam
        contador.descartados_limite += excesso
        contador.somar_motivo("teto_por_segundo")
        resumo["descartados_limite"] = excesso

    for registro in registros[:passam]:
        evento = mod_mapeamento.aplicar(fonte.mapa, registro, agora=agora)
        if isinstance(evento, mod_mapeamento.ErroEvento):
            contador.descartados_invalido += 1
            contador.somar_motivo(evento.motivo)
            resumo["descartados_invalido"] += 1
            continue
        try:
            if not mod_filtro.aceita(fonte.filtro_ast, evento):
                contador.descartados_filtro += 1
                contador.somar_motivo("filtro")
                resumo["descartados_filtro"] += 1
                continue
        except mod_filtro.ErroFiltro as e:
            contador.descartados_filtro += 1
            contador.somar_motivo(e.motivo)
            resumo["descartados_filtro"] += 1
            continue

        if fonte.ativa:
            if fila.enfileirar(fonte.tenant_id, fonte.id, evento, recebido_em=agora):
                resumo["aceitos"] += 1
            else:
                resumo["descartados_limite"] += 1
        elif len(fonte.buffer) < fonte.buffer_max:
            # pausada: guarda, não perde (cláusula do portão). O buffer tem teto declarado.
            fonte.buffer.append((evento, agora))
            resumo["em_buffer"] += 1
        else:
            contador.descartados_limite += 1
            contador.somar_motivo("buffer_de_pausa_cheio")
            resumo["descartados_limite"] += 1
    return resumo


def drenar_buffer(fonte, fila) -> int:
    """Fonte retomada: o que ficou guardado durante a pausa entra na fila, na ordem de chegada."""
    if not fonte.ativa:
        return 0
    n = 0
    contador = fila.conta(fonte.id)
    while fonte.buffer:
        evento, recebido = fonte.buffer.popleft()
        if fila.enfileirar(fonte.tenant_id, fonte.id, evento, recebido_em=recebido):
            n += 1
        else:
            contador.descartados_limite += 1
            contador.somar_motivo("fila_cheia_ao_drenar")
    return n
