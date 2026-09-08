"""Exemplo 7/10 — gerir tokens de serviço: criar com escopo restrito, listar, revogar.

Criar/listar/revogar tokens exige sessão de cookie na API (`so_sessao=True`); só funciona porque
este `Plataforma` veio de `.entrar()` (que guarda a sessão do login) — ver `plat/cliente.py`,
classe `Tokens`."""

from __future__ import annotations

from plat import ErroPlataforma, Plataforma


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-07")
    try:
        token = p.tokens.criar("sdk-exemplo-07-leitura", ["catalogo:ler"], validade_dias=1)
        assert token["token"].startswith("plat_")
        print(f"token criado: id={token['id']}, escopos={token['escopos']}")

        listados = p.tokens.listar()
        assert any(t["id"] == token["id"] for t in listados)
        print(f"listar(): {len(listados)} token(ns) do usuário, o novo entre eles")

        p.tokens.revogar(token["id"])
        leitor = Plataforma(url, token=token["token"])
        try:
            leitor.itens.listar(limite=1)
            raise AssertionError("token revogado ainda deveria funcionar? não.")
        except ErroPlataforma as erro:
            assert erro.status == 401
            print(f"revogado: novo uso dá {erro.status} {erro.tipo}")
    finally:
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
