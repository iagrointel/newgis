"""Exemplo 9/10 — compartilhar um item com o inquilino inteiro e conferir."""

from __future__ import annotations

from _ambiente import DADOS_MAPA
from plat import Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-09")
    item = None
    try:
        item = p.itens.criar("mapa", "sdk exemplo 09 — item a compartilhar", dados=DADOS_MAPA)
        assert item["acesso"] == "privado"

        p.itens.compartilhar(item["id"], acesso="inquilino")
        estado = p.itens.compartilhamento(item["id"])
        assert estado["acesso"] == "inquilino"
        print(f"compartilhado: acesso={estado['acesso']!r}")

        de_volta = p.itens.obter(item["id"])
        assert de_volta["acesso"] == "inquilino"
        print("confirmado em GET /api/itens/{id}")
    finally:
        if item is not None:
            p.itens.apagar(item["id"])
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
