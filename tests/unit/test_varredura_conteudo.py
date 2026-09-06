"""Item L7-03-b-antivirus-anexos (docs/SEGURANCA.md §8; app/varredura_conteudo.py). Cobre a cláusula do portão
("arquivo com extensão .jpg mas conteúdo de script recusado") e a razão medida de NÃO existir um denylist de
tipo perigoso que valha para `application/octet-stream` (o teste `test_binario_generico_aleatorio_nunca_e_
recusado_por_assinatura` é a prova permanente daquela medição — se algum dia alguém reintroduzir o denylist e
esse teste começar a falhar de vez em quando, é o sinal de que a medição de 06/09/2026 ainda vale)."""

import io
import os
import zipfile

import pytest

from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho


def _zip_de_verdade() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "oi")
    return buf.getvalue()


def test_extensao_jpg_com_conteudo_de_script_e_recusado():
    """A cláusula literal do portão: Content-Type declarado image/jpeg, bytes reais de um script de shell."""
    with pytest.raises(ConteudoRecusado) as exc:
        escanear_cabecalho(b"#!/bin/sh\necho pwned\n", "image/jpeg")
    assert exc.value.resultado.tipo_detectado == "text/x-shellscript"
    assert "image/jpeg" in str(exc.value)


def test_png_de_verdade_passa():
    png_real = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 64
    r = escanear_cabecalho(png_real, "image/png")
    assert r.permitido is True
    assert r.tipo_detectado == "image/png"


def test_jpeg_de_verdade_passa():
    jpeg_real = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\x00" * 64
    r = escanear_cabecalho(jpeg_real, "image/jpeg")
    assert r.permitido is True


def test_svg_com_script_declarado_como_imagem_e_recusado():
    """Polyglot óbvio: SVG (que é XML/texto) com <script> embutido, declarado como image/png."""
    svg_malicioso = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    with pytest.raises(ConteudoRecusado):
        escanear_cabecalho(svg_malicioso, "image/png")


def test_zip_declarado_como_pdf_e_recusado():
    with pytest.raises(ConteudoRecusado):
        escanear_cabecalho(_zip_de_verdade(), "application/pdf")


def test_kmz_de_verdade_e_um_zip_e_passa():
    r = escanear_cabecalho(_zip_de_verdade(), "application/vnd.google-earth.kmz")
    assert r.permitido is True


def test_csv_de_texto_simples_passa():
    r = escanear_cabecalho(b"a,b,c\n1,2,3\n", "text/csv")
    assert r.permitido is True


def test_conteudo_vazio_e_recusado():
    with pytest.raises(ConteudoRecusado):
        escanear_cabecalho(b"", "image/png")


def test_content_type_com_parametro_de_charset_e_normalizado():
    """`Content-Type: text/csv; charset=utf-8` (o `;` cortado antes de bater com TIPOS_PERMITIDOS)."""
    r = escanear_cabecalho(b"a,b,c\n1,2,3\n", "text/csv; charset=utf-8")
    assert r.permitido is True


def test_binario_generico_aleatorio_nunca_e_recusado_por_assinatura():
    """A razão medida do módulo para NÃO ter denylist sob `application/octet-stream`: bytes aleatórios às vezes
    saem classificados pelo libmagic como algo "perigoso" por coincidência de assinatura (MEDIDO: ~0,9%, 18/2000
    amostras de 4 KiB) — se isso reprovasse, o upload binário genérico (CAD, dado proprietário) reprovaria ao
    acaso. Roda muitas amostras para tornar a alegação robusta neste teste, não só uma vez por sorte."""
    for _ in range(200):
        r = escanear_cabecalho(os.urandom(4096), "application/octet-stream")
        assert r.permitido is True, r
