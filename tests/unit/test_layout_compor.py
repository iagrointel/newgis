"""Unidade do layout (item L2-12-b-layouts-elementos-exportacao): geometria (escala ↔ zoom, papel, UTM, GMS),
validação nomeada por campo, e o compositor sem banco nem navegador (quadro falso) — PDF com texto selecionável
(pdftotext acha o título e os rótulos da grade), SVG, PNG, legenda de 300 classes paginada/declarada, teto de
pixels do quadro em A0 a 300 DPI (refutação do item: resolução efetiva declarada, nunca estouro silencioso)."""

from __future__ import annotations

import math
import shutil
import subprocess

import pytest

from app import limites
from app.layout import compor, modelos
from app.layout import geometria as geo

CENTRO = (-46.53, -23.46)


def _fontes(legenda=None, render=None):
    def ficha(cid):
        if cid == "sem":
            return None
        return {
            "id": cid,
            "titulo": f"Camada {cid}",
            "geometria": "Polygon",
            "legenda": legenda or [{"rotulo": "classe A", "cor": "#ff0000", "forma": "poligono"}],
            "dados": {"proveniencia": {"fonte": "Fonte de teste"}},
        }

    return compor.Fontes(
        ficha_camada=ficha,
        render_quadro=render or (lambda q, m, el: compor.png_vazio(min(q.largura_px, 32), min(q.altura_px, 32))),
        inquilino_nome="Inquilino de teste",
        autor="Autor de teste",
    )


# ---------------------------------------------------------------- geometria
def test_escala_e_zoom_sao_inversos_e_independem_da_latitude_no_papel():
    for lat in (0.0, -23.46, 45.0):
        for escala in (500, 20000, 1_000_000):
            for dpi in (96, 150, 300):
                z = geo.zoom_da_escala(escala, dpi, lat)
                assert math.isclose(geo.escala_do_zoom(z, dpi, lat), escala, rel_tol=1e-9)
                # metros por pixel no papel: N * 0,0254 / dpi, seja qual for a latitude
                assert math.isclose(geo.metros_por_pixel_web_mercator(lat, z), escala * 0.0254 / dpi, rel_tol=1e-9)


def test_quadro_por_escala_mede_o_terreno_que_o_papel_diz():
    dpi, escala, w_mm = 150, 20000, 300.0
    w_px = geo.mm_para_px(w_mm, dpi)
    q = geo.quadro_por_escala(CENTRO, escala, w_px, geo.mm_para_px(240, dpi), dpi)
    o, s, le, n = q.extensao()
    # largura do quadro no terreno (na latitude do centro) = 300 mm × 20.000 = 6.000 m, a ≤ 0,1 %
    real = geo.distancia_geodesica_m(o, CENTRO[1], le, CENTRO[1])
    assert abs(real - w_mm / 1000 * escala) / (w_mm / 1000 * escala) < 0.001
    # ida e volta pixel ↔ geográfica
    x, y = q.para_pixel(*CENTRO)
    assert math.isclose(x, w_px / 2) and math.isclose(y, q.altura_px / 2)
    lon, lat = q.para_geografica(x + 100, y - 50)
    xx, yy = q.para_pixel(lon, lat)
    assert math.isclose(xx, x + 100, abs_tol=1e-6) and math.isclose(yy, y - 50, abs_tol=1e-6)


def test_quadro_por_extensao_cabe_inteiro():
    ext = (-46.60, -23.50, -46.40, -23.40)
    q = geo.quadro_por_extensao(ext, 1000, 800, 96)
    o, s, le, n = q.extensao()
    assert o <= ext[0] + 1e-9 and le >= ext[2] - 1e-9 and s <= ext[1] + 1e-9 and n >= ext[3] - 1e-9


def test_papeis_utm_gms_e_barra_bonita():
    assert geo.dimensoes_papel("A3", "paisagem") == (420.0, 297.0)
    assert geo.dimensoes_papel("carta", "retrato") == (215.9, 279.4)
    with pytest.raises(ValueError):
        geo.dimensoes_papel("A5", "retrato")
    assert geo.epsg_utm(-46.53, -23.46) == 32723  # fuso 23 sul (São Paulo)
    assert geo.fuso_utm(-46.53, 10.0) == (23, "N")
    assert abs(geo.convergencia_meridiana_graus(-45.0, -23.46)) < 1e-9  # no meridiano central γ = 0
    assert geo.convergencia_meridiana_graus(-46.53, -23.46) > 0  # oeste do MC no hemisfério sul → positivo
    assert geo.graus_para_gms(-46.5, "lon") == "46°30'W"
    assert geo.graus_para_gms(-23.4625, "lat") == "23°27'45\"S"
    assert geo.comprimento_bonito_m(70, 20000) == 1000.0  # 70 mm a 1:20.000 = 1.400 m → 1 km
    assert geo.comprimento_bonito_m(70, 500) == 25.0  # 35 m → 25 m
    assert geo.rotulo_distancia(2500) == "2,5 km" and geo.rotulo_distancia(250) == "250 m"


# ---------------------------------------------------------------- validação nomeada
def test_validar_nomeia_o_campo():
    with pytest.raises(modelos.ErroLayout) as e:
        modelos.validar({"papel": "A5", "elementos": []})
    assert e.value.campo == "papel"
    with pytest.raises(modelos.ErroLayout) as e:
        modelos.validar(
            {
                "papel": "A4",
                "orientacao": "retrato",
                "elementos": [{"tipo": "mapa", "x": 100, "y": 10, "w": 150, "h": 50}],
            }
        )
    assert e.value.campo == "elementos[0]"  # sai do papel (x + w > 210)
    with pytest.raises(modelos.ErroLayout) as e:
        modelos.validar(
            {
                "papel": "A4",
                "orientacao": "retrato",
                "elementos": [{"tipo": "mapa", "x": 10, "y": 10, "w": 100, "h": 50, "modo": "escala", "escala": 5000}],
            }
        )
    assert e.value.campo == "elementos[0].centro"
    doc = modelos.validar(modelos.modelo_padrao("a3-paisagem-completo"))
    assert doc["papel"] == "A3" and len(doc["elementos"]) == 9
    for m in modelos.MODELOS_PADRAO:
        modelos.validar(m)  # todos os modelos padrão passam pela própria validação


# ---------------------------------------------------------------- compositor
@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext ausente")
def test_pdf_a3_completo_tem_texto_selecionavel_grade_utm_e_escala(tmp_path):
    m = modelos.modelo_padrao("a3-paisagem-completo")
    m["elementos"][2].update({"modo": "escala", "escala": 20000, "centro": list(CENTRO)})
    doc = modelos.validar(m)
    mapa = {"titulo": "Mapa de prova do layout", "camadas": [{"camada_id": "c1", "opacidade": 1.0}]}
    comp = compor.compor(doc, mapa, _fontes(), dpi=96, formato="pdf")
    assert comp.dados[:5] == b"%PDF-" and comp.content_type == "application/pdf"
    pdf = tmp_path / "a3.pdf"
    pdf.write_bytes(comp.dados)
    texto = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
    assert "Mapa de prova do layout" in texto  # título selecionável
    assert "Escala 1:20.000" in texto
    assert "Inquilino de teste" in texto and "Autor de teste" in texto
    assert "classe A" in texto  # legenda com o rótulo da classe
    assert "OpenStreetMap" in texto  # atribuição obrigatória do mapa-base
    rotulos = comp.relatorio["grade"]["rotulos"]
    assert any(r.endswith(" E") for r in rotulos) and any(r.endswith(" N") for r in rotulos)
    for r in rotulos:
        assert r.split(" ")[0] in texto.replace("\n", " ")  # o teste LÊ o texto do PDF (cláusula da grade UTM)
    escala = comp.relatorio["escala"]["mapa"]
    assert abs(escala["escala"] - 20000) / 20000 < 0.001
    assert {e["id"]: e["estado"] for e in comp.relatorio["elementos"]}["grade"] == "ok"
    # o mesmo documento em SVG (texto como <text>) e em PNG
    svg = compor.compor(doc, mapa, _fontes(), dpi=96, formato="svg")
    assert svg.dados.startswith(b"<svg") and b"Mapa de prova do layout" in svg.dados and b"<image" in svg.dados
    png = compor.compor(doc, mapa, _fontes(), dpi=72, formato="png")
    assert png.dados[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = compor.imagem_dimensoes(png.dados)
    assert abs(w - 420 / 25.4 * 72) <= 2 and abs(h - 297 / 25.4 * 72) <= 2  # A3 paisagem a 72 DPI


def test_legenda_de_300_classes_e_paginada_e_declarada():
    m = modelos.modelo_padrao("a4-paisagem-legenda")
    doc = modelos.validar(m)
    legenda = [{"rotulo": f"classe {i:03d}", "cor": f"#{i % 256:02x}4040", "forma": "poligono"} for i in range(300)]
    comp = compor.compor(
        doc, {"titulo": "x", "camadas": [{"camada_id": "c1"}]}, _fontes(legenda=legenda), dpi=72, formato="svg"
    )
    leg = comp.relatorio["legenda"]
    assert leg["truncados"] > 0 and leg["itens"] <= 30
    assert f"+{leg['truncados']} itens" in comp.dados.decode("utf-8")
    estado = {e["id"]: e for e in comp.relatorio["elementos"]}["legenda"]
    assert estado["estado"] == "aproximado" and "paginação" in estado["nota"]


def test_a0_a_300_dpi_1_500_respeita_o_teto_de_pixels_e_declara_a_resolucao():
    pedidos = []

    def render(q, m, el):
        pedidos.append((q.largura_px, q.altura_px, q.zoom))
        return compor.png_vazio(8, 8)

    doc = modelos.validar(
        {
            "papel": "A0",
            "orientacao": "paisagem",
            "elementos": [
                {
                    "tipo": "mapa",
                    "id": "mapa",
                    "x": 20,
                    "y": 20,
                    "w": 1100,
                    "h": 780,
                    "modo": "escala",
                    "escala": 500,
                    "centro": list(CENTRO),
                },
                {"tipo": "escala", "id": "escala", "x": 20, "y": 810, "w": 120, "h": 14},
            ],
        }
    )
    comp = compor.compor(doc, {"titulo": "A0"}, _fontes(render=render), dpi=300, formato="svg")
    w_px, h_px, zoom = pedidos[0]
    assert max(w_px, h_px) == limites.LAYOUT_QUADRO_PIXELS_MAX
    assert comp.relatorio["resolucao_efetiva_dpi"] < 300
    assert {e["id"]: e for e in comp.relatorio["elementos"]}["mapa"]["estado"] == "aproximado"
    # a escala no papel continua 1:500 (o quadro cobre o mesmo terreno com menos pixels)
    assert abs(comp.relatorio["escala"]["mapa"]["escala"] - 500) / 500 < 0.001


def test_atribuicao_automatica_e_quadro_sem_render_nao_derrubam_a_pagina():
    def render(q, m, el):
        raise RuntimeError("motor indisponível")

    doc = modelos.validar(
        {
            "papel": "A4",
            "orientacao": "retrato",
            "elementos": [
                {
                    "tipo": "mapa",
                    "id": "mapa",
                    "x": 10,
                    "y": 10,
                    "w": 190,
                    "h": 200,
                    "modo": "extensao",
                    "extensao": [-46.6, -23.5, -46.4, -23.4],
                }
            ],
        }
    )
    comp = compor.compor(doc, {"titulo": "sem motor"}, _fontes(render=render), dpi=72, formato="svg")
    assert any("não foi desenhado" in a for a in comp.relatorio["avisos"])
    assert any("atribuição do mapa-base acrescentada" in a for a in comp.relatorio["avisos"])
    assert b"OpenStreetMap" in comp.dados
