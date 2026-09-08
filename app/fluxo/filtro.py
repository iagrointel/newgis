"""Filtro na entrada da fonte (item L2-14-a-ingestao-de-fluxos): a MESMA linguagem de expressão do item
L2-10-c (`app.expressao.avaliador_py`), sem avaliador novo e sem `eval`.

O contexto exposto ao filtro é a lista BRANCA: os campos mapeados (pelo nome de coluna) mais `rastro_id`,
`tempo_evento` (milissegundos desde a época, a convenção de data da linguagem), `lon` e `lat`. Campo fora
dessa lista é `campo_nao_permitido`, nunca `nulo` silencioso.

Orçamento por evento: `FLUXO_FILTRO_PASSOS_MAX` passos e `FLUXO_FILTRO_MS` de relógio — bem abaixo do
padrão do servidor (100 mil passos, 500 ms), porque aqui a expressão roda uma vez POR EVENTO e não uma vez
por pedido. Expressão que estoura o orçamento descarta o evento como `filtro_erro` (contado), nunca derruba
o processo.
"""

from __future__ import annotations

from app import limites
from app.expressao import avaliador_py as expr


class ErroFiltro(ValueError):
    def __init__(self, motivo: str, detalhe: str = ""):
        super().__init__(detalhe or motivo)
        self.motivo = motivo
        self.detalhe = detalhe or motivo


def compilar(texto: str | None):
    """Texto → AST (uma vez por fonte, nunca por evento). None quando não há filtro."""
    if texto is None or not texto.strip():
        return None
    try:
        return expr.analisar(texto)
    except expr.ErroExpressao as e:
        raise ErroFiltro("filtro_invalido", f"{e.codigo}: {e}") from e


def contexto_do_evento(evento) -> dict:
    ctx = dict(evento.atributos)
    ctx["rastro_id"] = evento.rastro_id
    ctx["tempo_evento"] = int(evento.tempo_evento.timestamp() * 1000)
    ctx["lon"] = evento.lon
    ctx["lat"] = evento.lat
    return ctx


def aceita(ast, evento) -> bool:
    """Sem filtro, tudo passa. Resultado não booleano ou erro de avaliação = evento NÃO passa (e o motivo
    fica no ErroFiltro para quem quiser contar por motivo)."""
    if ast is None:
        return True
    try:
        valor = expr.avaliar(ast, contexto_do_evento(evento),
                            limite_passos=limites.FLUXO_FILTRO_PASSOS_MAX, limite_ms=limites.FLUXO_FILTRO_MS)
    except expr.ErroExpressao as e:
        raise ErroFiltro("filtro_erro", f"{e.codigo}: {e}") from e
    if not isinstance(valor, bool):
        raise ErroFiltro("filtro_nao_booleano", f"o filtro devolveu {type(valor).__name__}, não booleano")
    return valor
