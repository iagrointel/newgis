"""Exemplo 2/10 — listar o catálogo (`GET /api/itens`), uma página e todas."""

from __future__ import annotations

from plat import Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-02")
    try:
        pagina = p.itens.listar(limite=5)
        assert set(pagina) >= {"total", "itens", "proximo_cursor"}
        assert isinstance(pagina["itens"], list)
        print(f"página 1: {len(pagina['itens'])} de {pagina['total']} item(ns)")

        # paginação embutida: itera o catálogo inteiro sem ler proximo_cursor na mão
        contagem = sum(1 for _ in p.itens.todos())
        assert contagem == pagina["total"]
        print(f"todos(): {contagem} item(ns) no total, batendo com a página 1")
    finally:
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
