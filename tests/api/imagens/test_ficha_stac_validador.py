"""Cláusula do portão do item L1-27: "propriedades STAC validadas por `stac-validator` com as extensões
`eo`, `view`, `sat`, `proj`, `raster`".

O item STAC é montado a partir da MESMA função que a API usa para gravar (`ficha.para_stac` +
`ficha.links_stac` + `ficha.EXTENSOES_STAC`) — validar um JSON escrito à mão no teste não provaria nada
sobre o produto. O `stac-validator` baixa os esquemas das extensões da rede; sem rede o teste é saltado,
nunca aprovado por omissão.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.imagens import ficha as fi

EXTENSOES_EXIGIDAS = ("eo", "view", "sat", "projection", "raster")


def _achar_stac_validator() -> str | None:
    candidato = Path(sys.executable).with_name("stac-validator")
    return str(candidato) if candidato.exists() else shutil.which("stac-validator")


STAC_VALIDATOR = _achar_stac_validator()
pytestmark = pytest.mark.skipif(
    STAC_VALIDATOR is None, reason="stac-validator não está instalado nesta máquina (venv)"
)

FICHA = {
    "plataforma": "sentinel-2b", "instrumentos": ["msi"], "gsd": 10,
    "data_aquisicao": "2026-05-01T13:00:00Z", "fornecedor": "agência de teste interno",
    "licenca": "cc-by-4.0", "fonte": "upload", "atribuicao": "atribuição de teste interno",
    "nuvem_pct": 3.2, "sol_elevacao": 55.1, "sol_azimute": 40.0, "angulo_off_nadir": 4.1,
    "angulo_incidencia": 8.0, "orbita_estado": "descending", "orbita_relativa": 24,
    "orbita_absoluta": 48123, "constelacao": "sentinel-2",
}


def _tem_rede() -> bool:
    try:
        with urllib.request.urlopen(  # noqa: S310 — endereço fixo do esquema oficial da extensão
            "https://stac-extensions.github.io/eo/v1.1.0/schema.json", timeout=15
        ) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def item_da_ficha(bruto: dict) -> dict:
    """Item STAC completo montado do jeito que a plataforma monta: as propriedades vêm de `para_stac`."""
    f = fi.validar(bruto)
    colecao = "1-imagens"
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": list(fi.EXTENSOES_STAC),
        "id": "item-da-ficha",
        "collection": colecao,
        "geometry": {"type": "Polygon", "coordinates": [
            [[-47.0, -16.0], [-46.0, -16.0], [-46.0, -15.0], [-47.0, -15.0], [-47.0, -16.0]]
        ]},
        "bbox": [-47.0, -16.0, -46.0, -15.0],
        "properties": {
            **fi.para_stac(f),
            "proj:epsg": 4326,
            "proj:shape": [1024, 1024],
            "proj:transform": [0.001, 0.0, -47.0, 0.0, -0.001, -15.0],
        },
        "assets": {
            "cientifico": {
                "href": "https://exemplo.invalido/imagem.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data"],
                "raster:bands": [{
                    "nodata": 0, "data_type": "uint16",
                    "statistics": {"minimum": 1, "maximum": 10000, "mean": 1200.0, "stddev": 300.0,
                                   "valid_percent": 100.0},
                }],
            }
        },
        "links": [
            *fi.links_stac(f),
            {"rel": "collection", "href": f"https://exemplo.invalido/collections/{colecao}",
             "type": "application/json"},
        ],
    }


def validar(item: dict, tmp_path: Path) -> dict:
    caminho = tmp_path / "item.json"
    caminho.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    saida = subprocess.run(  # noqa: S603 — binário do próprio venv, sem shell, argumentos fixos
        [STAC_VALIDATOR, "validate", str(caminho)], capture_output=True, text=True, timeout=180, check=False
    )
    # o CLI imprime um aviso de versão antes do JSON e a linha de tempo depois: recortar do primeiro "["
    # até o "]" que fecha, em vez de tentar decodificar a saída inteira
    inicio, fim = saida.stdout.find("["), saida.stdout.rfind("]")
    assert inicio >= 0 and fim > inicio, saida.stdout + saida.stderr
    return json.loads(saida.stdout[inicio:fim + 1])[0]


def test_extensoes_declaradas_sao_as_cinco_do_portao():
    """Antes de chamar a rede: as cinco extensões do portão têm de estar na lista que a plataforma declara."""
    declaradas = " ".join(fi.EXTENSOES_STAC)
    faltam = [e for e in EXTENSOES_EXIGIDAS if f"stac-extensions.github.io/{e}/" not in declaradas]
    assert faltam == [], faltam


def test_item_montado_da_ficha_valida_no_stac_validator(tmp_path, medida):
    if not _tem_rede():
        pytest.skip("sem rede para baixar os esquemas das extensões STAC")
    r = validar(item_da_ficha(FICHA), tmp_path)
    assert r["valid_stac"] is True, r
    usados = " ".join(r["schema"])
    faltam = [e for e in EXTENSOES_EXIGIDAS if f"stac-extensions.github.io/{e}/" not in usados]
    assert faltam == [], (faltam, r["schema"])
    medida("L1-27-ficha-de-metadado-e-licenca-da-imagem")(
        "stac_validator_extensoes", 1, "0=reprovou,1=passou",
        f"{Path(STAC_VALIDATOR).name} validate <item montado por app.imagens.ficha.para_stac>; "
        f"esquemas usados: {r['schema']}",
    )


@pytest.mark.parametrize("codigo", [lic.codigo for lic in fi.LICENCAS])
def test_toda_licenca_da_tabela_produz_item_stac_valido(codigo, tmp_path):
    """`license` do STAC tem forma fechada (identificador SPDX ou `other`): a tabela da casa não pode ter
    uma linha que gere item inválido."""
    if not _tem_rede():
        pytest.skip("sem rede para baixar os esquemas das extensões STAC")
    r = validar(item_da_ficha({**FICHA, "licenca": codigo}), tmp_path)
    assert r["valid_stac"] is True, (codigo, r)
