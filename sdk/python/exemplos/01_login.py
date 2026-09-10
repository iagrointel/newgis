"""Exemplo 1/10 — login por usuário e senha, primeiro token de serviço.

`Plataforma.entrar()` faz `POST /api/login` e, com a sessão resultante, `POST /api/tokens`
(que só aceita sessão de cookie — nunca outro token). O SDK devolve um `Plataforma` já pronto
para uso por token dali em diante; é o padrão para o resto dos exemplos."""

from __future__ import annotations

from plat import Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> dict:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-01")
    try:
        eu = p.eu()
        assert eu["login"] == login
        assert p.token.startswith("plat_")
        print(f"login ok: {eu['login']} (inquilino {eu['inquilino']['nome']!r}, perfil {eu['perfil']!r})")
        return eu
    finally:
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
