"""Páginas servidas pela API (ADR 0002 seção 15): os 6 caminhos = 200 text/html com Cache-Control: no-store.
Arquivo que o frontend ainda não entregou = pulado com o nome (a rota devolve 404, nunca uma casca)."""

import pytest

from app.paginas import PAGINAS, WEB


@pytest.mark.parametrize("caminho", sorted(PAGINAS))
def test_pagina_200_html_no_store(cliente, caminho):
    if not (WEB / PAGINAS[caminho]).is_file():
        assert cliente.get(caminho).status_code == 404
        pytest.skip(f"web/{PAGINAS[caminho]} ainda não existe (trilha frontend)")
    r = cliente.get(caminho)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    assert '<meta name="robots" content="noindex, nofollow">' in r.text


def test_seis_caminhos_do_adr():
    assert set(PAGINAS) >= {"/entrar", "/conta", "/admin/usuarios", "/admin/grupos", "/admin/tokens", "/admin/log"}
