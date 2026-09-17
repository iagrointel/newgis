"""Formulário com campo de senha nunca pode cair para GET (achado de 17/09/2026, em PRODUÇÃO).

O DEFEITO, medido ao vivo: `web/login.html` declarava `<form>` sem `method`. O padrão do HTML é GET.
O envio real é feito pelo ouvinte de submit em `web/js/auth/login.js`; quando ele ainda não ligou — a
primeira visita, rede lenta, JS atrasado, ou o usuário apertando Enter cedo — o navegador envia o
formulário sozinho, por GET. A senha vai para a barra de endereço, para o histórico do navegador,
para o `Referer` do próximo pedido e para o log de acesso do servidor.

A defesa é uma palavra: `method="post"`. Corpo de POST não entra em URL, não entra em histórico e não
entra em log de acesso. O ouvinte de submit continua sendo quem envia; o `method` só decide o que
acontece quando ele NÃO está lá.

Este teste é a catraca: qualquer `<form>` num arquivo que tenha campo de senha precisa declarar
`method="post"`. Vale para o produto e para os exemplos do SDK — exemplo é o que o cliente copia.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "web"
RE_FORM = re.compile(r"<form\b[^>]*>", re.I)


def _paginas_com_senha() -> list[Path]:
    return sorted(p for p in WEB.rglob("*.html") if 'type="password"' in p.read_text(encoding="utf-8"))


def test_ha_paginas_com_senha_para_conferir():
    # controle: se a varredura parar de achar páginas, o teste vira decoração e ninguém percebe.
    assert len(_paginas_com_senha()) >= 5


def test_formulario_de_senha_nunca_cai_para_get():
    faltam = []
    for pagina in _paginas_com_senha():
        for tag in RE_FORM.findall(pagina.read_text(encoding="utf-8")):
            if 'method="post"' not in tag.lower().replace("'", '"'):
                faltam.append(f"{pagina.relative_to(RAIZ)}: {tag}")
    assert not faltam, "form sem method=post em página com campo de senha (senha vai para a URL):\n" + "\n".join(faltam)


def test_controle_positivo_a_varredura_pega_um_form_plantado(tmp_path):
    # sem controle positivo não se sabe se o teste mede alguma coisa.
    plantada = WEB / "zz_controle_senha_get.html"
    plantada.write_text('<form id="x"><input type="password" name="s"></form>', encoding="utf-8")
    try:
        achadas = [p for p in _paginas_com_senha() if p == plantada]
        assert achadas, "a varredura não achou a página plantada"
        tag = RE_FORM.findall(plantada.read_text(encoding="utf-8"))[0]
        assert 'method="post"' not in tag
    finally:
        plantada.unlink()
