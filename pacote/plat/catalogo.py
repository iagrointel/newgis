"""Catálogo de itens: listagem paginada por cursor (transparente em `iterar`), busca, abertura,
criação, atualização e apagado. A paginação segue o `proximo_cursor` que a API devolve — o SDK
nunca carrega o catálogo inteiro na memória (`iterar` é gerador).

Exemplo (`pla` é uma `Plataforma` já conectada, injetada pela suíte de doctests):

    >>> pagina = pla.catalogo.listar(limite=5)
    >>> todos = [i["id"] for i in pla.catalogo.iterar(limite=5)]
    >>> len(todos) >= len(pagina.itens)
    True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from plat.cliente import Plataforma


@dataclass
class Pagina:
    """Uma página da listagem: `itens`, `total` (pode ser aproximado) e o cursor da página seguinte."""
    total: int
    itens: list[dict]
    proximo_cursor: str | None
    aproximado: bool = False


class Catalogo:
    def __init__(self, pla: Plataforma):
        self._pla = pla

    # ---------------------------------------------------------------- leitura
    def listar(self, *, q: str | None = None, tipo: str | None = None, tags: list[str] | None = None,
               limite: int | None = 100, deslocamento: int | None = None,
               cursor: str | None = None, ordenar: str | None = None) -> Pagina:
        """Uma página de itens (`GET /api/itens`). Passe `cursor` da página anterior para avançar."""
        params: dict[str, Any] = {}
        if q:
            params["q"] = q
        if tipo:
            params["tipo"] = tipo
        if tags:
            params["tags"] = ",".join(tags)
        if limite is not None:
            params["limite"] = limite
        if deslocamento is not None:
            params["deslocamento"] = deslocamento
        if cursor:
            params["cursor"] = cursor
        if ordenar:
            params["ordenar"] = ordenar
        d = self._pla.get("/api/itens", params=params) or {}
        return Pagina(total=int(d.get("total", 0)), itens=list(d.get("itens") or []),
                      proximo_cursor=d.get("proximo_cursor"), aproximado=bool(d.get("aproximado")))

    def iterar(self, *, q: str | None = None, tipo: str | None = None, tags: list[str] | None = None,
               limite: int = 100) -> Iterator[dict]:
        """Todos os itens que casam, página por página; parar é só parar de iterar (gerador)."""
        cursor: str | None = None
        while True:
            pagina = self.listar(q=q, tipo=tipo, tags=tags, limite=limite, cursor=cursor)
            yield from pagina.itens
            if not pagina.proximo_cursor or not pagina.itens:
                return
            cursor = pagina.proximo_cursor

    def abrir(self, item_id: str) -> dict:
        """Um item por id (`GET /api/itens/{id}`); item de outro inquilino levanta `NaoEncontrado` (RLS)."""
        return self._pla.get(f"/api/itens/{item_id}")

    # ---------------------------------------------------------------- escrita
    def criar(self, *, tipo: str, titulo: str, dados: dict | None = None, resumo: str | None = None,
              descricao: str | None = None, tags: list[str] | None = None,
              creditos: str | None = None, **extras: Any) -> dict:
        """Cria item (`POST /api/itens`); o `tipo` precisa existir em `GET /api/tipos-item` e os
        `dados` passam pelo JSON Schema do tipo. Sem privilégio de escrita: `ErroPermissao` (403)."""
        corpo: dict[str, Any] = {"tipo": tipo, "titulo": titulo, "dados": dados or {}}
        if resumo is not None:
            corpo["resumo"] = resumo
        if descricao is not None:
            corpo["descricao"] = descricao
        if tags is not None:
            corpo["tags"] = tags
        if creditos is not None:
            corpo["creditos"] = creditos
        corpo.update(extras)
        return self._pla.post("/api/itens", json=corpo)

    def atualizar(self, item_id: str, campos: dict[str, Any]) -> dict:
        """Muda campos soltos (`PATCH /api/itens/{id}`): título, resumo, tags, creditos."""
        return self._pla.patch(f"/api/itens/{item_id}", json=campos)

    def substituir_dados(self, item_id: str, dados: dict) -> dict:
        """Substitui o bloco `dados` INTEIRO (a API não faz união: o dicionário enviado passa a ser o
        `dados` do item) — validado pelo JSON Schema do tipo antes de gravar."""
        return self._pla.patch(f"/api/itens/{item_id}", json={"dados": dados})

    def apagar(self, item_id: str) -> None:
        """Manda para a lixeira lógica (`DELETE /api/itens/{id}`); `None` em 204."""
        self._pla.delete(f"/api/itens/{item_id}")
