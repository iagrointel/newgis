"""Adversário de linha L7 operação (parte 2) — item `L7-13-a-chamados`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`).

`app/chamados/rotas.py::_verificar_anexo` chama `objetos.escanear_cabecalho(dados[:65536], ...)` —
só os primeiros 64 KiB do anexo, mesmo que `limites.CHAMADO_ANEXO_BYTES_MAX` permita até 8.000.000
bytes (`app/chamados/rotas.py::anexar`, linha do teto). `app/varredura_conteudo.py` documenta a
checagem 3 ("carga executável no CORPO INTEIRO") como valendo sobre o corpo inteiro que o CHAMADOR
entrega — mas o chamador aqui entrega só a fatia de 64 KiB, não o corpo inteiro do anexo.

Um PNG estruturalmente válido cujo chunk `IEND` termina EXATAMENTE no byte 65536 preenche toda a
fatia examinada sem sobra (a checagem 4, "byte depois do fim do formato", não acusa nada porque não
há byte depois do fim DENTRO da fatia) — e qualquer coisa colada a partir do byte 65536 (um
`<script>...` repetido, por exemplo) nunca é vista por nenhuma das 5 checagens da varredura. O
resultado: um anexo de chamado com conteúdo executável embutido, bem abaixo do teto de 8 MB, passa
por `_verificar_anexo` como PNG legítimo — o portão literal ("anexo malicioso recusado em duas
camadas") não se sustenta para anexos entre 64 KiB e 8 MB com a carga colada depois do byte 65536."""

from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("PLAT_AMBIENTE", "dev")


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return len(dados).to_bytes(4, "big") + tipo + dados + zlib.crc32(tipo + dados).to_bytes(4, "big")


def _png_estrutural_de_tamanho(tamanho_total: int) -> bytes:
    """PNG cujo IEND termina exatamente em `tamanho_total` bytes — sem sobra dentro da fatia."""
    assinatura = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    iend = _chunk(b"IEND", b"")
    usado = len(assinatura) + len(ihdr) + 12 + len(iend)  # 12 = cabeçalho+crc do chunk de enchimento
    enchimento = _chunk(b"IDAT", b"\x00" * (tamanho_total - usado))
    png = assinatura + ihdr + enchimento + iend
    assert len(png) == tamanho_total
    return png


@pytest.mark.xfail(
    strict=True,
    reason=(
        "_verificar_anexo só examina dados[:65536] mesmo com CHAMADO_ANEXO_BYTES_MAX=8_000_000: um "
        "PNG estrutural que preenche exatamente os primeiros 65536 bytes (IEND no byte 65536, sem "
        "sobra dentro da fatia) esconde qualquer carga colada depois desse byte de todas as 5 "
        "checagens da varredura. Item L7-13-a-chamados, cláusula 'anexo malicioso recusado'."
    ),
)
def test_anexo_com_carga_apos_65536_bytes_e_recusado():
    from app.chamados import rotas as chamados_rotas

    png_ate_janela = _png_estrutural_de_tamanho(65536)
    carga_maliciosa = b"<script>alert(document.cookie)</script>" * 20
    dados = png_ate_janela + carga_maliciosa
    assert len(dados) < 8_000_000  # bem abaixo do teto de tamanho do anexo

    with pytest.raises(Exception):  # noqa: B017 — a rota levanta HTTPException 422 nomeada; o que se afirma é que NÃO passa
        chamados_rotas._verificar_anexo("png", dados)
