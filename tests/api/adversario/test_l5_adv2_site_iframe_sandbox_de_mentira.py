"""Adversário de linha L5 builder (parte 2) — item L5-20-sites-paginas-publicas.

Achado (hipótese transversal desta rodada: nem todo iframe de conteúdo incorporado da linha L5 segue a
MESMA lista seleta de tokens de sandbox — a própria casa já sabe, em DOIS lugares, que
`allow-scripts` + `allow-same-origin` juntos anulam o sandbox):

- `web/js/widgets/seguro.js` (item L5-01-d-widgets-pagina-menu, widget "incorporar" do construtor de
  app/painel) define `SANDBOX_PERMITIDO = ['allow-scripts', 'allow-forms', 'allow-popups',
  'allow-presentation']` e comenta, no próprio código: "`allow-same-origin` nunca, porque com scripts
  permitiria ao conteúdo remover o próprio sandbox".
- `tests/e2e/test_widget_externo.py` (item L5-36-widgets-personalizados-sdk) tem a asserção
  `assert resultado["origem"] == "null", "sandbox com allow-same-origin = isolamento de mentira"` — a
  própria suíte da casa CHAMA essa combinação de "isolamento de mentira".

Mas `app/catalogo/site_render.py::cartao_incorporado` (item L5-20-sites-paginas-publicas, cartão
"incorporado" do construtor de site do inquilino) monta o iframe com
`sandbox="allow-scripts allow-same-origin allow-popups"` — a EXATA combinação que a casa, em outro lugar,
chama de isolamento de mentira. É uma função pura (não depende de rede nem de banco: `cartao_incorporado`
só lê `no['propriedades']` e devolve uma string), então dá para provar isso sem servidor.

Risco concreto: o cartão "incorporado" do site é o único lugar da linha onde a URL do iframe é escolhida
pelo administrador do INQUILINO (não pelo autor do widget do L5-01-d, que já usa a lista segura) — se essa
URL um dia apontar para o PRÓPRIO domínio da plataforma (outra página do mesmo site multi-inquilino, ou uma
rota que reflita algo), o iframe herda a origem verdadeira (allow-same-origin) com scripts ligados
(allow-scripts) sobre ela — exatamente o cenário que o resto da casa já sabe evitar. O item L5-20 não lista
esta cláusula na refutação exigida (fala de vazamento de item privado pela galeria, não de sandbox), mas o
padrão de segurança que o restante da linha declara como doutrina ("nunca allow-same-origin com scripts")
é justamente o tipo de suposição comum que este laudo foi pedido para atacar primeiro."""

from __future__ import annotations

import pytest

from app.catalogo.site_render import cartao_incorporado

ITEM = "L5-20-sites-paginas-publicas"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-20: app/catalogo/site_render.py::cartao_incorporado monta "
        'sandbox="allow-scripts allow-same-origin allow-popups" — a combinação que '
        "web/js/widgets/seguro.js (L5-01-d) e tests/e2e/test_widget_externo.py (L5-36) tratam, na MESMA "
        "casa, como 'isolamento de mentira' (allow-same-origin nunca pode conviver com allow-scripts no "
        "sandbox de conteúdo incorporado escolhido por terceiro)"
    ),
)
def test_cartao_incorporado_do_site_nunca_combina_allow_scripts_com_allow_same_origin():
    no = {"propriedades": {"url": "https://exemplo.invalido/pagina", "titulo": "quadro de teste"}}
    html_gerado = cartao_incorporado(None, no)
    tem_scripts = "allow-scripts" in html_gerado
    tem_mesma_origem = "allow-same-origin" in html_gerado
    assert not (tem_scripts and tem_mesma_origem), (
        "o iframe do cartão incorporado do site combina allow-scripts com allow-same-origin — a mesma "
        "combinação que o restante da linha L5 (seguro.js, test_widget_externo.py) trata como sandbox "
        f"anulado: {html_gerado!r}"
    )
