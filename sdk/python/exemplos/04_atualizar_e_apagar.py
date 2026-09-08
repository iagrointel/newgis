"""Exemplo 4/10 — edição parcial (`PATCH`) e apagar (`DELETE`) de um item."""

from __future__ import annotations

from _ambiente import DADOS_MAPA
from plat import ErroPlataforma, Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-04")
    item = None
    try:
        item = p.itens.criar("mapa", "sdk exemplo 04 — mapa de teste", resumo="antes", dados=DADOS_MAPA)
        assert item["resumo"] == "antes"

        atualizado = p.itens.atualizar(item["id"], resumo="depois", tags=["sdk", "exemplo"])
        assert atualizado["resumo"] == "depois"
        assert atualizado["versao_atual"] == item["versao_atual"] + 1
        print(f"editado: resumo {atualizado['resumo']!r}, versão {atualizado['versao_atual']}")

        p.itens.apagar(item["id"])
        print("apagado")
        try:
            p.itens.obter(item["id"])
            raise AssertionError("item deveria ter sumido")
        except ErroPlataforma as erro:
            assert erro.status == 404
            print(f"confirmado: {erro.status} {erro.tipo}")
        item = None
    finally:
        if item is not None:
            p.itens.apagar(item["id"])
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
