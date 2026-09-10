"""Unidade do site (item L5-20-sites-paginas-publicas): regras de montagem do documento e as funções puras da
renderização (escolha da página, contraste da cor do inquilino, escape do texto do autor, origens declaradas
para a política de conteúdo). Nada aqui toca banco — o que precisa de banco está em
`tests/api/catalogo/test_site.py`."""

import pytest

from app.catalogo import site, site_render
from app.catalogo.documento import gerar_ulid
from app.erros import ErroAPI


def no(tipo, pai=None, **props):
    return {"id": gerar_ulid(), "tipo": tipo, "pai": pai, "propriedades": props}


def documento(nos):
    return {"tipo": "site", "esquema_versao": 1, "corpo": {"nos": nos, "ligacoes": []}}


def validar(nos, monkeypatch):
    monkeypatch.setattr(site.tipos, "familia_de", lambda t: "site")
    site.validar_documento("site", documento(nos))


def regras(nos, monkeypatch) -> list[str]:
    with pytest.raises(ErroAPI) as e:
        validar(nos, monkeypatch)
    assert e.value.status_code == 422 and e.value.erro == "site_invalido"
    return [d["regra"] for d in e.value.detalhe]


def test_montagem_certa_passa(monkeypatch):
    p = no("pagina", titulo="Início", caminho="inicio", inicial=True)
    s = no("secao", pai=p["id"], rotulo="Bloco")
    validar([p, s, no("texto", pai=s["id"], texto="conteúdo")], monkeypatch)


def test_cartao_fora_de_secao_e_secao_fora_de_pagina(monkeypatch):
    p = no("pagina", titulo="p", caminho="p")
    assert "cartao_na_secao" in regras([p, no("texto", pai=p["id"], texto="x")], monkeypatch)
    s = no("secao", rotulo="s")
    assert "secao_na_pagina" in regras([s], monkeypatch)


def test_pagina_so_na_raiz_e_uma_inicial(monkeypatch):
    a = no("pagina", titulo="a", caminho="a", inicial=True)
    b = no("pagina", pai=a["id"], titulo="b", caminho="b")
    assert "pagina_na_raiz" in regras([a, b], monkeypatch)
    c = no("pagina", titulo="c", caminho="c", inicial=True)
    assert "inicial_repetida" in regras([a, c], monkeypatch)


def test_caminho_invalido_e_repetido(monkeypatch):
    assert "caminho_invalido" in regras([no("pagina", titulo="a", caminho="Com Espaço")], monkeypatch)
    a = no("pagina", titulo="a", caminho="igual")
    b = no("pagina", titulo="b", caminho="igual")
    assert "caminho_repetido" in regras([a, b], monkeypatch)


@pytest.mark.parametrize(
    "tipo,props,regra",
    [
        ("texto", {"texto": "   "}, "obrigatorio"),
        ("imagem", {"url": "https://fora.exemplo.org/a.png", "alternativo": "x"}, "url_interna"),
        ("imagem", {"url": "/static/a.png", "alternativo": ""}, "obrigatorio"),
        ("incorporado", {"url": "http://sem-tls.exemplo.org/"}, "url_https"),
        ("chamada", {"destino": "javascript:alert(1)", "rotulo_botao": "ir"}, "destino_invalido"),
        ("mapa", {}, "obrigatorio"),
        ("galeria", {"limite": 999}, "faixa"),
    ],
)
def test_propriedade_de_cartao_invalida(monkeypatch, tipo, props, regra):
    p = no("pagina", titulo="p", caminho="p")
    s = no("secao", pai=p["id"], rotulo="s")
    assert regra in regras([p, s, no(tipo, pai=s["id"], **props)], monkeypatch)


def test_documento_de_outra_familia_nao_e_tocado(monkeypatch):
    monkeypatch.setattr(site.tipos, "familia_de", lambda t: "app")
    site.validar_documento("app", documento([no("texto", texto="x")]))  # sem exceção: a regra é só do site


# ---------------------------------------------------------------- renderização (funções puras)
def test_pagina_por_caminho_escolhe_inicial_e_respeita_ordem():
    a = no("pagina", titulo="a", caminho="a", ordem=2)
    b = no("pagina", titulo="b", caminho="b", ordem=1, inicial=True)
    corpo = documento([a, b])["corpo"]
    assert site_render.pagina_por_caminho(corpo, "")["id"] == b["id"]
    assert site_render.pagina_por_caminho(corpo, "a")["id"] == a["id"]
    assert site_render.pagina_por_caminho(corpo, "z") is None
    assert [n["id"] for n in site_render.paginas(corpo)] == [b["id"], a["id"]]


def test_cor_do_texto_segue_o_contraste():
    assert site_render.cor_do_texto("#1f4b99") == "#ffffff"   # marca escura: texto claro
    assert site_render.cor_do_texto("#ffe066") == "#111111"   # marca clara: texto escuro
    assert site_render.cor_do_texto("nao-e-cor") == "#ffffff"  # entrada torta não derruba a página


def test_texto_do_autor_e_escapado_e_quebrado_em_paragrafos():
    html = site_render.cartao_texto(None, no("texto", texto="<script>alerta()</script>\n\nsegundo"))
    assert "<script>" not in html and "&lt;script&gt;alerta()&lt;/script&gt;" in html
    assert html.count("<p>") == 2


def test_hosts_incorporados_lista_so_https_declarado():
    corpo = documento([
        no("incorporado", url="https://um.exemplo.org/a?b=1"),
        no("incorporado", url="https://um.exemplo.org/c"),
        no("incorporado", url="https://dois.exemplo.org:8443/d"),
    ])["corpo"]
    assert site_render.hosts_incorporados(corpo) == ["https://um.exemplo.org", "https://dois.exemplo.org:8443"]


def test_todo_cartao_do_vocabulario_tem_renderizador():
    assert set(site_render.RENDERIZADORES) == site.CARTOES and len(site.CARTOES) == 9
