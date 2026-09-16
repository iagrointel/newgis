"""Adversário L2 (linha, parte 3) — item `L2-16-a-sdk-python-geo`.

A hipótese do item promete uma CAMADA GEOESPACIAL sobre o SDK gerado do OpenAPI: `Camada.ler(filtro,
campos, bbox) -> GeoDataFrame` (paginação transparente), `Camada.escrever(gdf, modo) -> edições pelo
L2-03-a`, `Raster.ler(bbox, bandas, resolução) -> array via TiTiler/COG por STAC`, `Tabela`, `Mapa`
(documento) e mapa em notebook (widget leve HTML com MapLibre). O portão (literal) exige doctest dos
exemplos rodando contra a instalação de demo, leitura de raster comparada a rasterio direto e widget
renderizando em notebook headless.

Achado (nesta rodada, antes do conserto): existiam DOIS pacotes Python diferentes chamados `plat`,
versão `0.1.0` os dois:

  1. `sdk/python/src/plat` — item L7-08-b-sdk-python (SDK genérico gerado do OpenAPI: `.itens`,
     `.jobs`, `.camadas` como visão de `/api/itens`). É este que está de fato instalado no venv da
     casa (`pip show plat` -> Location .../enterprise/venv/..., conferido nesta rodada).
  2. `pacote/plat` — o pacote que instala.sh (`--imagem-notebook`) copia para dentro da imagem docker
     do notebook por inquilino (item L2-16-b) e que `pacote/pyproject.toml` declarava como
     `name = "plat"` `version = "0.1.0"` — o mesmo nome e a mesma versão do pacote 1.

⚡ Decisão do gerente G3 (16/09/2026, `laco/handoffs/T9/FASE1.md`): canônico = `sdk/python` (`plat`);
o pacote 2 foi renomeado `plat_geo` (`pacote/plat_geo/`, `pacote/pyproject.toml` com
`name = "plat_geo"`) e passou a viver ao lado do genérico sem colisão de nome — a primeira cláusula
abaixo (nomes/versões distintos) já não é mais uma refutação, é o estado atual; fica registrada
como teste de regressão (não mais `xfail`). As cláusulas seguintes (Raster/Camada/Tabela/widget/
índice) continuam abertas — o rename não implementou nenhuma delas.

`pacote/plat_geo` é o único candidato a "a camada geoespacial" do item L2-16-a. Ele expõe só
`Plataforma`, `Catalogo` (CRUD genérico de item, sem bbox/GeoDataFrame), `Acervo`, `Jobs` e
`Ferramentas` (dispara job, inclusive um atalho `.buffer()`) — nenhuma classe `Raster`, `Tabela` ou
`Mapa`, e nenhum método `ler`/`escrever` que devolva ou aceite um GeoDataFrame. A imagem docker do
notebook instala geopandas/rasterio/duckdb/shapely (`deploy/notebook/contexto/Dockerfile`), mas o SDK
que ela também instala não usa nenhuma dessas bibliotecas: 0 ocorrência de `geopandas`/`GeoDataFrame`/
`rasterio` em todo `pacote/plat_geo/*.py` (conferido nesta rodada com grep). Não existe também nenhum
"índice interno de pacotes do repositório" (portão literal): o SDK só vira um tarball copiado para o
contexto de build da imagem docker (`install.sh` seção h5), nunca é publicado em lugar nenhum que um
`pip install plat --index-url ...` de fora alcance.

Reprodução (sem rede, sem banco — só o código-fonte do worktree):

    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh \
        tests/api/adversario/test_l2_16a_sdk_geo_ausente.py -q -rxX
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACOTE_PLAT = ROOT / "pacote" / "plat_geo"


def _carregar_pacote_plat():
    """Importa `pacote/plat_geo` (pós-G3: nome próprio, não colide mais com o `plat` genérico de
    `sdk/python` — antes do rename este loader usava um alias manual em `sys.modules` só para
    evitar a colisão de nome; hoje um `import plat_geo` comum já resolve certo)."""
    pacote_dir = ROOT / "pacote"
    if str(pacote_dir) not in sys.path:
        sys.path.insert(0, str(pacote_dir))
    if "plat_geo" in sys.modules:
        return sys.modules["plat_geo"]
    import plat_geo

    return plat_geo


def test_l2_16a_pacotes_plat_e_plat_geo_tem_identidade_distinta():
    """Regressão do G3 (16/09/2026): `sdk/python/pyproject.toml` (`plat`) e `pacote/pyproject.toml`
    (`plat_geo`) já não declaram o mesmo (nome, versão) — antes deste conserto os dois eram
    `('plat', '0.1.0')` com APIs incompatíveis (`sdk/python` usa `httpx` + `.itens`/`.camadas`;
    `pacote/plat_geo` usa `requests` + `.catalogo`) e este teste era `xfail(strict=True)` (a
    colisão era o achado do adversário). Se algum dia voltar a colidir, este teste falha de novo."""
    sdk_pyproject = (ROOT / "sdk" / "python" / "pyproject.toml").read_text()
    pacote_pyproject = (ROOT / "pacote" / "pyproject.toml").read_text()

    def nome_versao(texto: str) -> tuple[str, str]:
        nome = re.search(r'(?m)^name\s*=\s*"([^"]+)"', texto).group(1)
        versao = re.search(r'(?m)^version\s*=\s*"([^"]+)"', texto).group(1)
        return nome, versao

    ident_sdk = nome_versao(sdk_pyproject)
    ident_pacote = nome_versao(pacote_pyproject)
    assert ident_sdk != ident_pacote, (
        "os dois pacotes deveriam ter nomes distintos (ou ao menos versões diferentes) para não "
        f"colidir num mesmo índice: sdk/python={ident_sdk} pacote/={ident_pacote}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-16-a: o portão promete Camada.ler(filtro,campos,bbox)->GeoDataFrame e "
        "Camada.escrever(gdf,...); pacote/plat_geo/catalogo.py::Catalogo só tem CRUD genérico de item "
        "(listar/iterar/abrir/criar/atualizar/substituir_dados/apagar), sem bbox nem GeoDataFrame"
    ),
)
def test_l2_16a_camada_le_e_escreve_geodataframe():
    modulo = _carregar_pacote_plat()
    assert hasattr(modulo, "Camada") or hasattr(modulo.Catalogo, "ler"), (
        "nenhuma classe/metodo do SDK geoespacial lê uma camada como GeoDataFrame"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-16-a: o portão promete Raster.ler(bbox,bandas,resolução) -> array comparável a rasterio "
        "direto; não existe nenhuma classe Raster em pacote/plat_geo, nem import de rasterio/numpy"
    ),
)
def test_l2_16a_classe_raster_existe():
    modulo = _carregar_pacote_plat()
    assert hasattr(modulo, "Raster"), "classe Raster ausente do SDK geoespacial (pacote/plat_geo)"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-16-a: o portão promete Tabela e Mapa (documento) como domínios do SDK, ao lado de "
        "catálogo/acervo/jobs/ferramentas; pacote/plat_geo só tem os quatro últimos"
    ),
)
def test_l2_16a_tabela_e_mapa_documento_existem():
    modulo = _carregar_pacote_plat()
    assert hasattr(modulo, "Tabela"), "classe Tabela ausente"
    assert hasattr(modulo, "Mapa"), "classe Mapa (documento) ausente"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-16-a: o portão promete 'mapa em notebook (widget leve HTML com MapLibre)' com teste "
        "headless via nbconvert; não existe módulo nem exemplo nenhum do SDK que renderize um widget "
        "de mapa (0 arquivo em pacote/plat_geo ou sdk/python/exemplos menciona MapLibre/notebook/widget)"
    ),
)
def test_l2_16a_widget_de_mapa_em_notebook_existe():
    fontes = list(PACOTE_PLAT.glob("*.py")) + list((ROOT / "sdk" / "python" / "exemplos").glob("*.py"))
    achou = any(
        re.search(r"maplibre|ipyleaflet|_repr_html_|display\(", arquivo.read_text(), re.IGNORECASE)
        for arquivo in fontes
    )
    assert achou, "nenhum arquivo do SDK (pacote/plat_geo ou exemplos) implementa widget de mapa em notebook"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-16-a: o portão promete o SDK 'publicado no índice interno de pacotes do repositório'; "
        "não existe índice de pacotes nenhum (devpi/simple-index/pypiserver) no repositório — o "
        "único caminho de distribuição é a cópia de pacote/ para o contexto docker do notebook "
        "(install.sh, seção h5), que não é um índice de pacotes"
    ),
)
def test_l2_16a_indice_interno_de_pacotes_existe():
    candidatos = list(ROOT.rglob("*devpi*")) + list(ROOT.rglob("*pypiserver*")) + list(ROOT.rglob("simple-index*"))
    candidatos = [c for c in candidatos if ".git" not in c.parts]
    assert candidatos, "nenhum índice interno de pacotes encontrado no repositório"
