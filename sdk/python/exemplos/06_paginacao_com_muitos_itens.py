"""Exemplo 6/10 — paginação de verdade: cria itens suficientes para forçar mais de uma página e
prova que `.itens.todos()` os devolve todos, sem duplicar nem perder nenhum."""

from __future__ import annotations

from _ambiente import DADOS_MAPA
from plat import Plataforma

N = 7
TAMANHO_PAGINA = 3


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-06")
    criados: list[str] = []
    try:
        for i in range(N):
            item = p.itens.criar("mapa", f"sdk exemplo 06 — item {i}", tags=["sdk-exemplo-06"], dados=DADOS_MAPA)
            criados.append(item["id"])

        pagina = p.itens.listar(tags=["sdk-exemplo-06"], limite=TAMANHO_PAGINA)
        assert len(pagina["itens"]) == TAMANHO_PAGINA
        assert pagina["proximo_cursor"]
        print(f"1ª página: {len(pagina['itens'])} de {pagina['total']}, cursor={pagina['proximo_cursor'][:8]}...")

        ids_vistos = {it["id"] for it in p.itens.todos(tags=["sdk-exemplo-06"])}
        assert ids_vistos == set(criados), (ids_vistos, set(criados))
        print(f"todos(): {len(ids_vistos)} item(ns), nenhum perdido nem duplicado")
    finally:
        for item_id in criados:
            p.itens.apagar(item_id)
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
