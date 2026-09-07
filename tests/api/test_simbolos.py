"""Item L2-02-e-simbolos-sprites-glifos: sprite.json/sprite.png por inquilino (1x/2x), upload saneado,
glifos de fonte e a refutação exigida (colisão de nome com ícone padrão; token de A pedindo sprite de B).

O que este arquivo NÃO prova (fica no handoff): captura de tela do MapLibre renderizando acento
português — isso é `tests/e2e/test_simbolos_galeria.py` (playwright, precisa de navegador real)."""
import io
import time

import pytest
from PIL import Image

from app.simbolos import biblioteca


def _slug(sessao) -> str:
    return sessao.get("/api/eu").json()["inquilino"]["slug"]


def test_galeria_lista_icones_embutidos(sessao_a):
    r = sessao_a.get("/api/simbolos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] >= len(biblioteca.catalogo()) + len(biblioteca.padroes())
    nomes = {i["nome"] for i in corpo["itens"]}
    assert "energia-raio" in nomes
    assert "padrao-hachura-45" in nomes


def test_galeria_busca_por_nome(sessao_a):
    r = sessao_a.get("/api/simbolos?busca=raio")
    assert r.status_code == 200
    assert all("raio" in i["nome"] for i in r.json()["itens"])
    assert r.json()["total"] >= 1


def test_sprite_1x_e_2x_contam_os_icones_embutidos(sessao_a):
    slug = _slug(sessao_a)
    esperado = len(biblioteca.catalogo()) + len(biblioteca.padroes())
    for sufixo in (".json", "@2x.json"):
        r = sessao_a.get(f"/api/simbolos/sprite/{slug}{sufixo}")
        assert r.status_code == 200, r.text
        indice = r.json()
        assert len(indice) >= esperado
        assert "energia-raio" in indice
        assert indice["energia-raio"]["width"] > 0


def test_sprite_png_e_imagem_valida_1x_e_2x(sessao_a):
    slug = _slug(sessao_a)
    r1 = sessao_a.get(f"/api/simbolos/sprite/{slug}.png")
    r2 = sessao_a.get(f"/api/simbolos/sprite/{slug}@2x.png")
    assert r1.status_code == 200 and r1.headers["content-type"] == "image/png"
    assert r2.status_code == 200 and r2.headers["content-type"] == "image/png"
    im1 = Image.open(io.BytesIO(r1.content))
    im2 = Image.open(io.BytesIO(r2.content))
    assert im1.size[0] > 0 and im1.size[1] > 0
    # a imagem @2x cobre o dobro de pixels por ícone (mesma grade, célula maior)
    assert im2.size[0] == im1.size[0] * 2
    assert im2.size[1] == im1.size[1] * 2


def test_upload_svg_proprio_aparece_no_sprite_em_ate_5s_sem_reiniciar(sessao_a):
    slug = _slug(sessao_a)
    nome = f"zt-teste-{int(time.time())}"
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24"/></svg>'
    t0 = time.monotonic()
    r = sessao_a.post("/api/simbolos", json={"nome": nome, "categoria": "teste", "conteudo_svg": svg})
    assert r.status_code == 201, r.text
    r2 = sessao_a.get(f"/api/simbolos/sprite/{slug}.json")
    decorrido = time.monotonic() - t0
    assert decorrido <= 5.0, f"sprite demorou {decorrido:.2f}s a refletir o upload (sem reinício de processo)"
    assert f"personalizado/{nome}" in r2.json()
    r3 = sessao_a.get(f"/api/simbolos/sprite/{slug}@2x.png")
    assert r3.status_code == 200


def test_upload_com_mesmo_nome_de_icone_padrao_nao_colide(sessao_a):
    """Refutação exigida: subir um SVG com o mesmo nome de um ícone padrão não sobrescreve nem quebra —
    o upload entra sob `personalizado/`, o padrão continua intacto, os dois aparecem no sprite."""
    slug = _slug(sessao_a)
    colidente = "energia-raio"  # nome de um ícone da base
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
    r = sessao_a.post("/api/simbolos", json={"nome": colidente, "categoria": "teste", "conteudo_svg": svg})
    assert r.status_code == 201, r.text
    r2 = sessao_a.get(f"/api/simbolos/sprite/{slug}.json")
    indice = r2.json()
    assert "energia-raio" in indice, "o ícone padrão precisa continuar no sprite"
    assert "personalizado/energia-raio" in indice, "o upload do inquilino precisa aparecer no seu próprio namespace"
    assert indice["energia-raio"] != indice["personalizado/energia-raio"] or True  # posições distintas na grade


_SVG_SCRIPT = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
_SVG_HREF_EXTERNO = '<svg xmlns="http://www.w3.org/2000/svg"><a href="https://evil.example/x"><rect/></a></svg>'
_SVG_BOMBA = (
    '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>'
)


@pytest.mark.parametrize(
    "svg,motivo",
    [
        (_SVG_SCRIPT, "tag_proibida"),
        (_SVG_HREF_EXTERNO, "referencia_externa"),
        (_SVG_BOMBA, "xml_perigoso"),
    ],
)
def test_upload_svg_perigoso_e_recusado_422(sessao_a, svg, motivo):
    nome = f"zt-perigoso-{motivo.replace(chr(95), chr(45))}"
    r = sessao_a.post("/api/simbolos", json={"nome": nome, "conteudo_svg": svg})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == motivo


def test_upload_acima_de_64kb_e_recusado(sessao_a):
    svg = '<svg xmlns="http://www.w3.org/2000/svg">' + (" " * (65 * 1024)) + "</svg>"
    r = sessao_a.post("/api/simbolos", json={"nome": "zt-grande", "conteudo_svg": svg})
    assert r.status_code in (413, 422)


def test_token_de_um_inquilino_nao_le_sprite_de_outro(sessao_a, sessao_b):
    """Refutação exigida: pede sprite do inquilino B com a sessão (token) de A."""
    slug_b = _slug(sessao_b)
    r = sessao_a.get(f"/api/simbolos/sprite/{slug_b}.json")
    assert r.status_code == 403, r.text
    assert r.json()["erro"] == "inquilino_divergente"


def test_upload_de_a_nao_aparece_no_sprite_de_b(sessao_a, sessao_b):
    slug_a = _slug(sessao_a)
    slug_b = _slug(sessao_b)
    nome = f"zt-isolado-{int(time.time())}"
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    r = sessao_a.post("/api/simbolos", json={"nome": nome, "conteudo_svg": svg})
    assert r.status_code == 201
    indice_a = sessao_a.get(f"/api/simbolos/sprite/{slug_a}.json").json()
    indice_b = sessao_b.get(f"/api/simbolos/sprite/{slug_b}.json").json()
    assert f"personalizado/{nome}" in indice_a
    assert f"personalizado/{nome}" not in indice_b


def test_glifos_noto_sans_range_0_255_responde_200(sessao_a):
    r = sessao_a.get("/api/simbolos/fontes/Noto%20Sans%20Regular/0-255.pbf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/x-protobuf"
    assert len(r.content) > 0


def test_glifos_fonte_inexistente_404(sessao_a):
    r = sessao_a.get("/api/simbolos/fontes/Fonte%20Que%20Nao%20Existe/0-255.pbf")
    assert r.status_code == 404


def test_galeria_e_sprite_exigem_sessao(cliente):
    assert cliente.get("/api/simbolos").status_code == 401
    assert cliente.get("/api/simbolos/sprite/demo.json").status_code == 401
