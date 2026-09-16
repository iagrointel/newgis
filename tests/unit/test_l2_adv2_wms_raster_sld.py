"""Adversário de linha L2 (parte 2), item `L2-04-i-wms-wmts-sld` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

A hipótese do item promete um WMS único "por token para mapas e camadas do catálogo" cujo GetMap é
"renderizado: raster pelo TiTiler (L1-02, reprojeção) e vetor pelo motor do L2-12-a", com
`sld/sld_body` valendo para as duas famílias de camada. O que o commit citado (`4d0db485` e a cadeia
que fecha, `d1577b5d8`) realmente entrega é só a metade vetorial: `app/ogc_mapas/rotas_wms.py`
(`/wms/{item_id}`) — zero menção a raster/COG/TiTiler no módulo inteiro — e o único SLD_BODY
funcional (`app/ogc_mapas/sld_leitura.py`, via `defusedxml`) só existe nesse caminho.

O WMS raster que a casa tem é um artefato de OUTRO item, anterior (`L1-02-g-wms-1-3-0-raster`,
`app/imagens/rotas_wms.py`, `/svc/{token}/wms`), que REJEITA `SLD`/`SLD_BODY` explicitamente
("SLD/SLD_BODY não é suportado nesta implementação") — por desenho daquele item, não por regressão
deste. Logo: não existe, em lugar nenhum do repositório, um único serviço WMS que sirva raster E
vetor com estilo `sld_body`, como a hipótese do item promete e como um cliente real (QGIS "Adicionar
camada WMS") entenderia "o WMS da plataforma".

A cláusula LITERAL do portão fala só de "GetMap vetorial", então isto não derruba o portão citado no
ledger — mas documenta que a hipótese usada para justificar "ENTREGUE" é mais larga que o que existe,
e que "por token para mapas e camadas do catálogo" (plural, incluindo raster) é falso hoje."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _texto(caminho: str) -> str:
    return (RAIZ / caminho).read_text(encoding="utf-8")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-04-i promete GetMap com raster via TiTiler + SLD_BODY para 'camadas do catálogo' em geral; "
        "o único WMS raster do repositório (item L1-02-g, app/imagens/rotas_wms.py) rejeita SLD/SLD_BODY "
        "explicitamente e o WMS de L2-04-i (app/ogc_mapas/rotas_wms.py) não tem NENHUMA menção a "
        "raster/COG/TiTiler — as duas famílias de camada nunca convivem no mesmo serviço com estilo."
    ),
)
def test_wms_unico_serve_raster_e_vetor_com_sld_body():
    vetor = _texto("app/ogc_mapas/rotas_wms.py") + _texto("app/ogc_mapas/pintor.py") + _texto(
        "app/ogc_mapas/dados.py"
    )
    for palavra in ("raster", "cog", "titiler", "COG", "TiTiler"):
        assert palavra not in vetor, "achado já teria caído sozinho: WMS vetorial passou a falar de raster"

    raster = _texto("app/imagens/rotas_wms.py")
    assert "não é suportado nesta implementação" in raster  # SLD_BODY recusado por desenho do L1-02-g

    # a asserção que o item promete: o MESMO serviço deveria aceitar SLD_BODY também para raster.
    # como não existe, provamos a ausência com uma asserção que a hipótese exige e a implementação nega.
    assert "SLD_BODY" in raster and "sld_leitura" in raster, (
        "para a hipótese do item ser verdadeira, o WMS raster precisaria delegar SLD_BODY ao MESMO "
        "leitor defusedxml do WMS vetorial (app/ogc_mapas/sld_leitura.py) — hoje ele nem importa o módulo"
    )
