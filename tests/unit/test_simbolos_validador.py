"""Item L2-02-e-simbolos-sprites-glifos: saneamento do SVG do inquilino, incluindo a refutação exigida
(bomba de XML via DOCTYPE/ENTITY)."""
import pytest

from app.simbolos import biblioteca, validador


def test_icone_proprio_passa():
    svg = biblioteca.montar_svg(biblioteca.catalogo()[0]).encode("utf-8")
    texto = validador.sanear_svg(svg)
    assert texto.startswith("<svg")


@pytest.mark.parametrize("nome", ["en ergia", "-energia", "a" * 65, ""])
def test_nomes_invalidos_recusados(nome):
    with pytest.raises(validador.SvgRecusado):
        validador.validar_nome(nome)


def test_nome_valido_normaliza_minusculo():
    assert validador.validar_nome("Meu-Icone-1") == "meu-icone-1"


def test_recusa_script():
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    assert e.value.motivo == "tag_proibida"


def test_recusa_href_externo():
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg"><a href="https://evil.example/x"><rect/></a></svg>'
        )
    assert e.value.motivo == "referencia_externa"


def test_recusa_evento_onload():
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>')
    assert e.value.motivo == "atributo_evento"


def test_recusa_tamanho_acima_de_64kb():
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(b"<svg>" + b" " * (65 * 1024) + b"</svg>")
    assert e.value.motivo == "tamanho"


def test_recusa_use_recursivo():
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><use href="#a"/></svg>')
    assert e.value.motivo == "tag_proibida"


def test_recusa_bomba_de_entidade_xml():
    """A refutação do item: SVG com bomba de XML (bilhões de risos via ENTITY)."""
    bomba = (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "a"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><title>&c;</title></svg>'
    )
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(bomba)
    assert e.value.motivo == "xml_perigoso"


def test_recusa_muitos_elementos_mesmo_sem_entidade():
    """Segunda camada de defesa contra a bomba: mesmo sem DOCTYPE, um SVG com elementos demais é recusado —
    o teto de 64 kB por si só limita quantos cabem, mas o teto de contagem é a defesa explícita e barata."""
    muitos = b'<svg xmlns="http://www.w3.org/2000/svg">' + (b'<circle r="1"/>' * 3000) + b"</svg>"
    with pytest.raises(validador.SvgRecusado) as e:
        validador.sanear_svg(muitos)
    assert e.value.motivo == "elementos_demais"
