"""Exemplo 10/10 — erros do SDK como Problem Details (RFC 9457) e um token de escopo insuficiente.

Este é o mesmo cenário que o adversário do item roda (ver `tests/sdk/test_adversario.py`): aqui é
só a demonstração honesta em forma de exemplo, não a auditoria."""

from __future__ import annotations

from plat import ErroPlataforma, Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-10")
    token_leitura = None
    try:
        try:
            p.itens.obter("00000000-0000-0000-0000-000000000000")
            raise AssertionError("item inexistente deveria dar 404")
        except ErroPlataforma as erro:
            assert erro.status == 404
            assert erro.tipo  # "type" da RFC 9457
            assert erro.titulo  # "title"
            assert erro.instancia  # "instance" — o req_id, casa com plat.log_acesso
            print(f"Problem Details: status={erro.status} tipo={erro.tipo!r} instancia={erro.instancia}")
            print("to_problem_details():", erro.to_problem_details())

        token_leitura = p.tokens.criar("sdk-exemplo-10-leitura", ["catalogo:ler"])
        leitor = Plataforma(url, token=token_leitura["token"])
        try:
            leitor.itens.criar("mapa", "não deveria existir")
            raise AssertionError("escopo catalogo:ler não deveria permitir escrita")
        except ErroPlataforma as erro:
            assert erro.status == 403
            assert erro.tipo == "escopo_insuficiente"
            print(f"escopo insuficiente: {erro.status} {erro.tipo} — {erro.titulo}")
    finally:
        if token_leitura is not None:
            p.tokens.revogar(token_leitura["id"])
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
