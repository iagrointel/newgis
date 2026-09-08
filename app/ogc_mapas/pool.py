"""Limite de desenho simultâneo do WMS/WMTS (item L2-04-i; refutação do item: 200 pedidos de
4.096x4.096 em paralelo não podem derrubar a API).

Uma imagem de 4.096x4.096 em RGBA com superamostragem chega a centenas de MB; sem limite, N pedidos
grandes simultâneos consomem toda a RAM do processo e o que morre é a API inteira, não só o pedido.
Aqui o custo é contado em MEGAPIXELS em voo: quem chega além do orçamento espera um pouco e, se o
orçamento não abrir, recebe 503 com `ServiceException` — a resposta certa de um serviço OGC ocupado,
que o cliente sabe repetir. É a mesma disciplina do pool do motor de render (L2-12-a): fila curta com
recusa explícita em vez de fila infinita.
"""

from __future__ import annotations

import threading

# orçamento total de pixels em voo (Mpx). 64 Mpx = quatro imagens de 4.096x4.096 ao mesmo tempo.
ORCAMENTO_MPX = 64.0
ESPERA_S = 5.0


class ServidorOcupado(RuntimeError):
    def __init__(self, mpx: float, em_voo: float):
        super().__init__("desenho ocupado")
        self.mpx = mpx
        self.em_voo = em_voo


class _Orcamento:
    def __init__(self, total_mpx: float):
        self.total = total_mpx
        self.em_voo = 0.0
        self.pico = 0.0
        self.recusados = 0
        self.atendidos = 0
        self._cond = threading.Condition()

    def _custo(self, largura: int, altura: int) -> float:
        # superamostragem 2x dobra o lado (4x a área) até o teto do pintor
        area = largura * altura
        fator = 4 if area <= 2_000_000 else 1
        return (area * fator) / 1_000_000

    def adquirir(self, largura: int, altura: int) -> float:
        custo = min(self._custo(largura, altura), self.total)
        with self._cond:
            if not self._cond.wait_for(lambda: self.em_voo + custo <= self.total, timeout=ESPERA_S):
                self.recusados += 1
                raise ServidorOcupado(custo, self.em_voo)
            self.em_voo += custo
            self.atendidos += 1
            self.pico = max(self.pico, self.em_voo)
            return custo

    def liberar(self, custo: float) -> None:
        with self._cond:
            self.em_voo = max(0.0, self.em_voo - custo)
            self._cond.notify_all()

    def estatisticas(self) -> dict:
        return {"orcamento_mpx": self.total, "em_voo_mpx": round(self.em_voo, 2),
                "pico_mpx": round(self.pico, 2), "atendidos": self.atendidos, "recusados": self.recusados}


_orcamento = _Orcamento(ORCAMENTO_MPX)


def estatisticas() -> dict:
    return _orcamento.estatisticas()


def zerar() -> None:
    """Só para teste: reinicia os contadores (nunca chamar em serviço)."""
    global _orcamento
    _orcamento = _Orcamento(ORCAMENTO_MPX)


class reservar:  # noqa: N801 - gerente de contexto, lê melhor em minúscula no ponto de uso
    """`with reservar(largura, altura):` — segura o orçamento durante o desenho e devolve no fim."""

    def __init__(self, largura: int, altura: int):
        self.largura = largura
        self.altura = altura
        self.custo = 0.0

    def __enter__(self):
        self.custo = _orcamento.adquirir(self.largura, self.altura)
        return self

    def __exit__(self, *_exc):
        _orcamento.liberar(self.custo)
        return False


def teto_lado() -> int:
    """O mesmo teto do motor de render (`PLAT_RENDER_MAX_PX`); import tardio para este módulo seguir
    importável sem ambiente configurado."""
    from app.settings import settings

    return settings.PLAT_RENDER_MAX_PX
