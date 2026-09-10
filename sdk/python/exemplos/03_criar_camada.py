"""Exemplo 3/10 — criar uma camada (`POST /api/itens` com `tipo=camada_vetorial`).

`.camadas` é uma VISÃO de `.itens` filtrada por tipo — não existe rota própria `/api/camadas`
(ver `sdk/python/README.md`, "o que não existe ainda")."""

from __future__ import annotations

from plat import Plataforma

DADOS_CAMADA = {
    "schema": "plat_trabalho",
    "tabela": "zt_sdk_exemplo_03",
    "geometria": "Point",
    "srid": 4326,
    "campos": [{"nome": "rotulo", "tipo": "text"}],
    "fonte": "hospedada",
}


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-03")
    camada = None
    try:
        camada = p.camadas.criar(titulo="sdk exemplo 03 — camada de teste", dados=DADOS_CAMADA)
        assert camada["tipo"] == "camada_vetorial"
        print(f"camada criada: {camada['id']} ({camada['titulo']!r})")

        de_volta = p.itens.obter(camada["id"])
        assert de_volta["id"] == camada["id"]
        print("confirmada por GET /api/itens/{id}")
    finally:
        if camada is not None:
            p.itens.apagar(camada["id"])
            print("apagada (limpeza do exemplo)")
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
