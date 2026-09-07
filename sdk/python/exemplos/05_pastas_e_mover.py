"""Exemplo 5/10 — criar uma pasta e mover um item para dentro dela.

`.itens.mover()` é ergonômico; criar pasta não tem view no SDK ainda (`/api/pastas` é outro
recurso) — mostra como usar o cliente GERADO direto quando a camada escrita à mão não cobre algo,
sem esperar o SDK inteiro ser reescrito à mão para toda rota nova."""

from __future__ import annotations

from _ambiente import DADOS_MAPA
from plat import Plataforma
from plat_gerado.api.pastas import apagar_api_pastas_id_delete as rt_apagar_pasta
from plat_gerado.api.pastas import criar_api_pastas_post as rt_criar_pasta
from plat_gerado.models.pasta_entrada import PastaEntrada


def main(url: str, inquilino: str, login: str, senha: str) -> None:
    p = Plataforma.entrar(url, inquilino, login, senha, nome_token="sdk-python-exemplo-05")
    item = pasta_id = None
    try:
        resposta = rt_criar_pasta.sync_detailed(client=p._cliente, body=PastaEntrada(nome="sdk exemplo 05"))
        assert resposta.status_code == 201, resposta.content
        import json

        pasta = json.loads(resposta.content)
        pasta_id = pasta["id"]
        print(f"pasta criada: {pasta_id}")

        item = p.itens.criar("mapa", "sdk exemplo 05 — item a mover", dados=DADOS_MAPA)
        movido = p.itens.mover(item["id"], pasta_id)
        assert movido["pasta"]["id"] == pasta_id
        print(f"item movido para a pasta {movido['pasta']['nome']!r}")
    finally:
        if item is not None:
            p.itens.apagar(item["id"])
        if pasta_id is not None:
            rt_apagar_pasta.sync_detailed(id=pasta_id, client=p._cliente)
        p.tokens.revogar(p.token_id)
        p.fechar()


if __name__ == "__main__":
    from _ambiente import do_ambiente

    main(*do_ambiente())
