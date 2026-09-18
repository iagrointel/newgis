"""Adversário de linha L1 imagens (parte 2, turno 9) — item `L1-25-servico-de-imagem-esri-compativel`,
ENTREGUE (commit 2a3472990). Duas cláusulas LITERAIS do portão citam capacidades que o próprio código
e a própria suíte do item documentam como NÃO implementadas:

1. Portão: "`exportImage` com `bbox` em 3857 e 4326 devolve PNG/JPEG/TIFF alinhado ao XYZ (≤ 1 px)".
   `app/imagens/rotas_imageserver.py` só aceita png/jpg (`?format=`); o teste do PRÓPRIO item que
   fecha esta cláusula (`tests/api/imagens/test_imageserver_token.py::
   test_export_image_format_nao_suportado_e_recusado_em_json_esri`) usa `format=tiff` como exemplo
   de FORMATO RECUSADO — a evidência commitada do fechamento prova o contrário do que o portão pede.
2. Portão: "`mosaicRule` limitada às [métodos] do L1-08" — a hipótese do item promete o protocolo
   "sobre cada item e mosaico". O docstring do próprio módulo admite: "mosaicRule: as regras L1-08
   estão disponíveis nos mosaicos STAC; exportImage ainda recusa qualquer valor não-vazio" e "cada
   item é um raster único, não um mosaico multi-cena — `capabilities` nunca anuncia 'Catalog'".
   `test_export_image_mosaic_rule_e_recusado` fecha o item confirmando a recusa incondicional.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_imageserver_gate.py -q -rxX`."""

from __future__ import annotations

import pytest

from tests.api.imagens.test_imageserver_token import _base, raster_demo, token_img  # noqa: F401
# 18/09/2026 — INSTRUMENTO CONSERTADO, nenhuma asserção mexida. Este portão vive em tests/unit/ e puxa
# as fixtures do arquivo do construtor, mas `token_*` depende de `sessao_a`, que é definida em
# tests/api/conftest.py — conftest que NÃO alcança tests/unit/. Sem esta linha o teste dá ERRO de setup
# ('fixture sessao_a not found'), e o `xfail(strict=True)` transforma esse erro em XFAIL: o portão passa
# a reportar 'o defeito continua' sem nunca ter tocado no produto. Medido hoje com --runxfail.
from tests.api.conftest import cred, sessao_a  # noqa: F401
from tests.api.imagens.conftest import tenant_id_a  # noqa: F401


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-25 CAI: exportImage recusa format=tiff (400, 'formato nao suportado' — ver "
        "test_export_image_format_nao_suportado_e_recusado_em_json_esri, que usa exatamente format=tiff "
        "como exemplo de recusa), mas o portao literal exige PNG/JPEG/TIFF alinhado ao XYZ."
    ),
)
def test_export_image_devolve_tiff(token_img, raster_demo):  # noqa: F811  (fixtures importadas do arquivo do construtor)
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(
        f"{_base(tok, item)}/exportImage",
        params={
            "bbox": "-47.95,-15.94,-47.76,-15.75",
            "bboxSR": "4326",
            "size": "256,256",
            "format": "tiff",
            "f": "image",
        },
    )
    assert r.status_code == 200, f"exportImage format=tiff deveria devolver 200; devolveu {r.status_code}: {r.text}"
    assert r.headers.get("content-type", "").startswith("image/tif"), r.headers.get("content-type")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L1-25 CAI: exportImage recusa QUALQUER mosaicRule nao-vazio incondicionalmente (ver "
        "test_export_image_mosaic_rule_e_recusado e o docstring do modulo: 'exportImage ainda recusa "
        "qualquer valor nao-vazio' / 'cada item e um raster unico, nao um mosaico multi-cena'), mas o "
        "portao literal pede mosaicRule LIMITADA (nao ausente) as regras do L1-08, que ja esta ENTREGUE "
        "nesta mesma linha (mosaicos STAC com regra 'lock' funcionando em app/imagens/mosaico.py)."
    ),
)
def test_export_image_aceita_mosaicrule_lock_limitado_ao_l1_08(token_img, raster_demo):  # noqa: F811  (fixtures importadas do arquivo do construtor)
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    regra = '{"mosaicMethod":"esriMosaicLockRaster","lockRasterIds":["%s"]}' % item
    r = c.get(
        f"{_base(tok, item)}/exportImage",
        params={
            "bbox": "-47.95,-15.94,-47.76,-15.75",
            "bboxSR": "4326",
            "size": "256,256",
            "format": "png",
            "f": "image",
            "mosaicRule": regra,
        },
    )
    assert r.status_code == 200, (
        f"mosaicRule com metodo do L1-08 (lock) deveria ser aceito, mesmo que limitado; devolveu "
        f"{r.status_code}: {r.text}"
    )
