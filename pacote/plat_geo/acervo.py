"""Acervo da casa (fontes oficiais com procedência): listagem e ficha por fonte, e o registro de uma
fonte como item `conexao` do inquilino (`assinar`). Regra da casa: só fonte com licença ESCRITA
aparece na listagem; fonte marcada com risco de dado pessoal exige `confirma_risco_pii=True` em
`assinar` (senão a API devolve 409 `adicionar_recusado_pii`).

Exemplo (`pla` é uma `Plataforma` já conectada, injetada pela suíte de doctests):

    >>> d = pla.acervo.fontes(limite=5)
    >>> d["total"] >= len(d["itens"]) >= 0
    True
    >>> f = d["itens"][0]["fonte_id"] if d["itens"] else None
    >>> f is None or pla.acervo.ficha(f)["fonte_id"] == f
    True
"""

from __future__ import annotations

from typing import Any

from plat_geo.cliente import Plataforma


class Acervo:
    def __init__(self, pla: Plataforma):
        self._pla = pla

    def fontes(self, *, dominio: str | None = None, q: str | None = None, limite: int | None = 100,
               deslocamento: int | None = None) -> dict:
        """Página da listagem (`GET /api/acervo`): `{"total": n, "itens": [...]}`; pagina por `deslocamento`."""
        params: dict[str, Any] = {}
        if dominio:
            params["dominio"] = dominio
        if q:
            params["q"] = q
        if limite is not None:
            params["limite"] = limite
        if deslocamento is not None:
            params["deslocamento"] = deslocamento
        return self._pla.get("/api/acervo", params=params)

    def iterar(self, *, dominio: str | None = None, q: str | None = None, limite: int = 100):
        """Todas as fontes (com licença escrita) visíveis ao token, lote por lote (gerador)."""
        deslocamento = 0
        while True:
            pagina = self.fontes(dominio=dominio, q=q, limite=limite, deslocamento=deslocamento)
            itens = pagina.get("itens") or []
            yield from itens
            deslocamento += len(itens)
            if not itens or deslocamento >= int(pagina.get("total", 0)):
                return

    def ficha(self, fonte_id: str) -> dict:
        """Ficha completa da fonte (`GET /api/acervo/{fonte_id}`): licença, frescor, tabelas, registros."""
        return self._pla.get(f"/api/acervo/{fonte_id}")

    def assinar(self, fonte_id: str, *, confirma_risco_pii: bool = False) -> dict:
        """Cria item `conexao` que referencia a fonte (`POST /api/acervo/{fonte_id}/adicionar`).
        `confirma_risco_pii=True` é a confirmação EXPLÍCITA do responsável pelos dados — a casa
        recusa (409) a assinatura de fonte marcada com risco de dado pessoal sem ela."""
        corpo = {"confirma_risco_pii": confirma_risco_pii}
        return self._pla.post(f"/api/acervo/{fonte_id}/adicionar", json=corpo)
