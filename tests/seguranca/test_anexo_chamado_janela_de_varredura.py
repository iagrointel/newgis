"""Furo 5 — janela de varredura do anexo de chamado (achados `L7-13-a-chamados` e `L7-03-b-antivirus-anexos`).

ACHADO (adversário de linha L7, turno 9, `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`):
`app/chamados/rotas.py::_verificar_anexo` entregava à varredura só `dados[:65536]`, enquanto `anexar` aceita
até `limites.CHAMADO_ANEXO_BYTES_MAX` (8 MB). Um PNG estruturalmente válido cujo `IEND` termina EXATAMENTE no
byte 65536 preenche a fatia examinada sem deixar sobra — a checagem 4 da varredura ("byte depois do fim do
formato") não acusa nada, porque dentro da fatia não há nada depois do fim — e a carga colada a partir do byte
65536 nunca era vista por checagem nenhuma. A varredura só enxerga o que o chamador entrega
(docstring de `app/varredura_conteudo.py`); aqui o chamador entregava uma fatia.

CONSERTO: `_verificar_anexo` entrega o corpo INTEIRO. O teto de 8 MB é conferido em `anexar` antes
(`413 arquivo_grande`), então o que chega à varredura é sempre limitado.

Cada prova vem em par (a regra da casa: sem controle positivo o conserto não vale):
  ATAQUE   — o anexo com carga depois do byte 65536 é recusado;
  LEGÍTIMO — um PNG do MESMO tamanho, sem carga, continua aceito.

Os dois outros vetores que o laudo cita para `L7-03-b` (Content-Type fora da lista desligando a varredura;
polyglot imagem+script) já estavam fechados antes deste turno — o próprio adversário registrou isso ao
reconferir. Ficam medidos aqui mesmo assim, com o mesmo par, para que uma regressão apareça como falha e não
como silêncio.

Tudo offline: chama as funções puras (`app.chamados.rotas._verificar_anexo`, `app.varredura_conteudo`), sem
HTTP, sem banco e sem Garage.
"""

from __future__ import annotations

import zlib

import pytest

from app import limites, varredura_conteudo
from app.chamados import rotas as chamados
from app.erros import ErroAPI

JANELA_ANTIGA = 65536  # a fatia que `_verificar_anexo` entregava antes do conserto
CARGA = b"<script>alert(document.cookie)</script>"


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return len(dados).to_bytes(4, "big") + tipo + dados + zlib.crc32(tipo + dados).to_bytes(4, "big")


def _png_de(tamanho: int) -> bytes:
    """PNG estruturalmente válido (IHDR + IDAT de enchimento + IEND) com EXATAMENTE `tamanho` bytes."""
    assinatura = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    iend = _chunk(b"IEND", b"")
    usado = len(assinatura) + len(ihdr) + 12 + len(iend)  # 12 = cabeçalho+crc do IDAT de enchimento
    assert tamanho > usado
    png = assinatura + ihdr + _chunk(b"IDAT", b"\x00" * (tamanho - usado)) + iend
    assert len(png) == tamanho
    return png


def test_ataque_anexo_com_carga_depois_do_byte_65536_e_recusado():
    """ATAQUE: PNG que termina exatamente no fim da janela antiga, com script colado depois."""
    dados = _png_de(JANELA_ANTIGA) + CARGA * 20
    assert len(dados) < limites.CHAMADO_ANEXO_BYTES_MAX  # bem abaixo do teto: não é o tamanho que barra
    with pytest.raises(ErroAPI) as e:
        chamados._verificar_anexo("png", dados)
    assert e.value.status_code == 415
    assert e.value.erro == "conteudo_recusado"


def test_legitimo_anexo_do_mesmo_tamanho_sem_carga_continua_aceito():
    """CONTROLE POSITIVO do mesmo par: o PNG do mesmo tamanho, só que sem script, passa."""
    dados = _png_de(JANELA_ANTIGA + len(CARGA) * 20)
    chamados._verificar_anexo("png", dados)  # não levanta


@pytest.mark.parametrize("offset", [JANELA_ANTIGA, JANELA_ANTIGA + 1, 2 * JANELA_ANTIGA, 4_000_000])
def test_ataque_carga_em_qualquer_ponto_do_anexo_e_recusada(offset: int):
    """A janela não pode voltar a ter borda nenhuma: a carga é recusada esteja onde estiver, até perto do teto."""
    dados = _png_de(offset) + CARGA
    with pytest.raises(ErroAPI) as e:
        chamados._verificar_anexo("png", dados)
    assert e.value.status_code == 415


def test_legitimo_png_grande_de_bytes_aleatorios_no_corpo_continua_aceito():
    """CONTROLE POSITIVO: enchimento de 4 MB sem nenhum padrão de carga não vira falso positivo."""
    dados = _png_de(4_000_000)
    chamados._verificar_anexo("png", dados)


# ---------------------------------------------------------------------------------------------------------
# L7-03-b: os dois vetores irmãos, medidos para que uma regressão apareça (já estavam fechados).
@pytest.mark.parametrize(
    "content_type", ["image/png", "application/octet-stream", "tipo/que-nao-existe", ""]
)
def test_ataque_content_type_fora_da_lista_nao_desliga_a_varredura(content_type: str):
    """ATAQUE: escolher um Content-Type fora da tabela não pode ser um jeito de não ser examinado."""
    dados = _png_de(4096) + CARGA
    with pytest.raises(varredura_conteudo.ConteudoRecusado):
        varredura_conteudo.escanear_cabecalho(dados, content_type)


def test_legitimo_binario_generico_com_content_type_desconhecido_continua_aceito():
    """CONTROLE POSITIVO: o rigor máximo para tipo desconhecido não pode recusar binário legítimo."""
    import os as _os

    for _ in range(20):
        varredura_conteudo.escanear_cabecalho(_os.urandom(8192), "tipo/que-nao-existe")  # não levanta


def test_ataque_polyglot_imagem_mais_script_e_recusado():
    """ATAQUE: GIF/JPEG/PNG válido com script colado depois, declarado como a própria imagem."""
    gif = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00" + b"\x3b"
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
    for corpo, tipo in ((gif, "image/gif"), (jpeg, "image/jpeg"), (_png_de(1024), "image/png")):
        with pytest.raises(varredura_conteudo.ConteudoRecusado):
            varredura_conteudo.escanear_cabecalho(corpo + CARGA, tipo)


def test_legitimo_imagem_sem_script_continua_aceita():
    """CONTROLE POSITIVO do par acima: a MESMA imagem, sem a carga, é aceita."""
    gif = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00" + b"\x3b"
    varredura_conteudo.escanear_cabecalho(gif, "image/gif")  # não levanta
    varredura_conteudo.escanear_cabecalho(_png_de(1024), "image/png")
