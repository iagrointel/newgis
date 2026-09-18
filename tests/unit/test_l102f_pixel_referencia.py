"""Item L1-02-f — cláusula "6 predefinições de fábrica ... com teste de imagem por PIXEL DE REFERÊNCIA".

O adversário de linha L1 (T9) achou que essa prova não existia no repositório: o docstring do arquivo do
construtor admitia que a comparação pixel a pixel "está no relatório do turno, não aqui" — isto é, não
era reproduzível por quem lesse o repositório depois.

Aqui ela é reproduzível. O COG é gerado em disco local pela MESMA fórmula determinística de
`tests/api/imagens/apoio_raster.py` (nenhum dado de cliente, nenhuma leitura remota, nenhum banco), as 6
predefinições de fábrica são resolvidas pelo MESMO caminho das rotas (`predefinicoes._resolver_fabrica`
-> `tiles.recorte` / `predefinicoes.renderizar_hillshade`), e as cores de 9 pixels fixos de cada saída
são comparadas com `tests/dados/predefinicoes_referencia.json`, que está commitado.

Comparar 9 pixels amostrados, e não o sha256 do PNG, é deliberado: o hash do arquivo muda com a versão
do libpng e mediria o compressor, não a renderização. A tolerância de 2 níveis por canal absorve
diferença de arredondamento entre versões de rio-tiler sem deixar passar troca de rampa ou de banda
(uma predefinição errada troca dezenas de níveis, não dois).

Para REGERAR a referência depois de uma mudança DELIBERADA de renderização:
    PLAT_REGERAR_REFERENCIA=1 venv/bin/pytest tests/unit/test_l102f_pixel_referencia.py -q
e conferir o diff do JSON antes de commitar.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
REFERENCIA = RAIZ / "tests" / "dados" / "predefinicoes_referencia.json"
LADO = 256
AMOSTRAS = [(r, c) for r in (10, 128, 245) for c in (10, 128, 245)]
TOLERANCIA = 2

# mesma estatística declarada em tests/api/imagens/test_predefinicoes.py (a faixa exata que a fórmula
# geradora produz — não um número inventado)
ESTATISTICAS = [
    {"nodata": 0.0, "statistics": {"minimum": 400.0, "maximum": 717.0, "mean": 570.0, "stddev": 90.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 700.0, "maximum": 913.0, "mean": 810.0, "stddev": 60.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 900.0, "maximum": 2100.0, "mean": 1500.0, "stddev": 600.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 1200.0, "maximum": 3800.0, "mean": 2500.0, "stddev": 1300.0,
                                   "valid_percent": 100.0}},
]


@pytest.fixture(scope="module")
def cog_e_stac(tmp_path_factory):
    """COG de 4 bandas idêntico ao de `apoio_raster._gerar_cog` (mesma fórmula, mesmo canto, mesma
    resolução), gerado localmente — a referência de pixel só vale se o dado de entrada for o mesmo."""
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    from tests.api.imagens.apoio_raster import CANTO_LAT, CANTO_LON, RESOLUCAO

    destino = tmp_path_factory.mktemp("l102f") / "referencia.tif"
    tf = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = tf.transform(CANTO_LON, CANTO_LAT)
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    veg = ((np.sin(xx / 60.0) + np.cos(yy / 45.0)) > 0).astype("float32")
    bandas = [
        (400 + 300 * (1 - veg) + (xx % 17)).astype("uint16"),
        (700 + 200 * veg + (yy % 13)).astype("uint16"),
        (900 + 1200 * (1 - veg)).astype("uint16"),
        (1200 + 2600 * veg).astype("uint16"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        bruto = Path(tmp) / "bruto.tif"
        with rasterio.open(bruto, "w", driver="GTiff", height=LADO, width=LADO, count=4,
                           dtype="uint16", crs="EPSG:3857", nodata=0,
                           transform=from_origin(x0, y0, RESOLUCAO, RESOLUCAO)) as dst:
            for i, b in enumerate(bandas, start=1):
                dst.write(b, i)
        subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD",
                        "-co", "BLOCKSIZE=128", str(bruto), str(destino)], check=True)
    with rasterio.open(destino) as ds:
        limites = ds.bounds
    stac = {"assets": {"cientifico": {"raster:bands": ESTATISTICAS}}}
    return {"caminho": destino, "stac": stac, "bounds": tuple(limites)}


def _render(nome: str, cog_e_stac) -> np.ndarray:
    """A MESMA cadeia que a rota percorre: resolver a predefinição de fábrica e desenhar o recorte."""
    from app.imagens import predefinicoes as pred
    from app.imagens import tiles

    fonte = tiles.Fonte(str(cog_e_stac["caminho"]), tiles.env_gdal(), None)
    resolvido = pred._resolver_fabrica(nome, cog_e_stac["stac"], "cientifico")  # noqa: SLF001
    bbox = cog_e_stac["bounds"]
    if resolvido.hillshade:
        corpo = pred.renderizar_hillshade(
            fonte, banda=(resolvido.bandas or [1])[0], formato="png", resampling=resolvido.resampling,
            nodata_transparente=resolvido.nodata_transparente,
            parte=(bbox, tiles.CRS.from_user_input("EPSG:3857"), LADO, LADO))
    else:
        corpo = tiles.recorte(fonte, bbox, "EPSG:3857", LADO, LADO, formato="png",
                              expressao=resolvido.expressao, bandas=resolvido.bandas,
                              rescale=resolvido.rescale, colormap=resolvido.colormap,
                              transparente=True, resampling=resolvido.resampling)
    return np.asarray(Image.open(io.BytesIO(corpo)).convert("RGB"))


def _amostrar(img: np.ndarray) -> list[list[int]]:
    return [[int(v) for v in img[r, c]] for r, c in AMOSTRAS]


def test_as_seis_predefinicoes_de_fabrica_existem():
    from app.imagens import predefinicoes as pred

    assert len(pred.FABRICA) >= 6, sorted(pred.FABRICA)
    assert {"rgb-natural", "falsa-cor-nir", "ndvi", "ndwi", "relevo-sombreado"} <= set(pred.FABRICA)


def test_pixel_de_referencia_das_predefinicoes_de_fabrica(cog_e_stac):
    """A prova que faltava: cada predefinição de fábrica desenha as MESMAS cores que a referência
    commitada, nos mesmos 9 pixels."""
    from app.imagens import predefinicoes as pred

    atual = {nome: _amostrar(_render(nome, cog_e_stac)) for nome in sorted(pred.FABRICA)}

    if os.environ.get("PLAT_REGERAR_REFERENCIA"):
        REFERENCIA.parent.mkdir(parents=True, exist_ok=True)
        REFERENCIA.write_text(json.dumps(
            {"_leia": "gerado por tests/unit/test_l102f_pixel_referencia.py; ver o docstring de lá",
             "amostras": [list(a) for a in AMOSTRAS], "cores": atual},
            ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip("referência regerada — confira o diff e rode de novo sem PLAT_REGERAR_REFERENCIA")

    assert REFERENCIA.exists(), (
        f"{REFERENCIA.relative_to(RAIZ)} não existe; gere com PLAT_REGERAR_REFERENCIA=1")
    esperado = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    assert [list(a) for a in AMOSTRAS] == esperado["amostras"], "as posições amostradas mudaram"
    assert set(atual) == set(esperado["cores"]), (
        f"o conjunto de predefinições de fábrica mudou: {sorted(set(atual) ^ set(esperado['cores']))}")
    for nome, cores in atual.items():
        for indice, (agora, antes) in enumerate(zip(cores, esperado["cores"][nome], strict=True)):
            for canal, (a, b) in enumerate(zip(agora, antes, strict=True)):
                assert abs(a - b) <= TOLERANCIA, (
                    f"{nome}: pixel {AMOSTRAS[indice]} canal {canal} mudou de {b} para {a} "
                    f"(tolerância {TOLERANCIA})")


def test_predefinicoes_diferentes_pintam_diferente(cog_e_stac):
    """Controle do teste acima: se todas as referências fossem iguais, a comparação não provaria nada."""
    rgb = _amostrar(_render("rgb-natural", cog_e_stac))
    ndvi = _amostrar(_render("ndvi", cog_e_stac))
    assert rgb != ndvi, "cor verdadeira e NDVI não podem amostrar as mesmas cores"


# ------------------------------------------------------------------ tabela de cor explícita (a outra cláusula)
def test_colormap_explicito_por_valor_pinta_a_cor_pedida(cog_e_stac):
    """A hipótese do item promete "colormap explícito por intervalo/valor"; até 17/09 o esquema só
    aceitava NOME de rampa. Aqui a cor sai exatamente onde a tabela mandou."""
    from app.imagens import tiles

    # a tabela de cor é aplicada sobre o valor JÁ ESTICADO para 0-255 (comportamento do rio-tiler, o
    # mesmo do colormap por nome): por isso os intervalos são declarados nesse domínio, e o `rescale`
    # diz que faixa do dado bruto vai para lá. O corte em 128 parte a banda 4 (1200..3800) ao meio.
    cm = {"tipo": "intervalo", "entradas": [[[0, 128], [255, 0, 0, 255]], [[128, 256], [0, 0, 255, 255]]]}
    fonte = tiles.Fonte(str(cog_e_stac["caminho"]), tiles.env_gdal(), None)
    corpo = tiles.recorte(fonte, cog_e_stac["bounds"], "EPSG:3857", 64, 64, formato="png",
                          bandas=[4], rescale=[(1200, 3800)], colormap=cm, transparente=True)
    img = np.asarray(Image.open(io.BytesIO(corpo)).convert("RGB")).reshape(-1, 3)
    cores = {tuple(c) for c in img}
    assert cores <= {(255, 0, 0), (0, 0, 255)}, f"cor fora da tabela explícita: {sorted(cores)[:5]}"
    assert len(cores) == 2, f"a banda 4 tem valores nos dois intervalos; pintou só {cores}"


def test_colormap_explicito_de_70_mil_entradas_e_recusado():
    """Refutação literal do item ("colormap de 70.000 entradas"): agora é testável contra a CAPACIDADE
    real, não contra um nome inventado."""
    from app.imagens import predefinicoes as pred
    from app.erros import ErroAPI

    enorme = {"tipo": "valor", "entradas": {str(i): [1, 2, 3, 255] for i in range(70000)}}
    with pytest.raises(ErroAPI) as e:
        pred.validar_corpo({"titulo": "t", "colormap": enorme})
    assert e.value.status_code == 422, e.value.status_code


def test_colormap_explicito_bem_formado_e_aceito_pelo_esquema():
    from app.imagens import predefinicoes as pred

    pred.validar_corpo({"titulo": "t", "colormap": {
        "tipo": "valor", "entradas": {"4": [0, 200, 0], "8": [220, 220, 220, 128]}}})
    pred.validar_corpo({"titulo": "t", "colormap": {
        "tipo": "intervalo", "entradas": [[[-1, 0], [200, 0, 0]], [[0, 1], [0, 200, 0]]]}})
    pred.validar_corpo({"titulo": "t", "colormap": "rdylgn"})


def test_colormap_explicito_malformado_e_recusado():
    from app.erros import ErroAPI
    from app.imagens import predefinicoes as pred

    for ruim in (
        {"tipo": "valor"},                                        # sem entradas
        {"tipo": "outro", "entradas": {"1": [0, 0, 0]}},           # tipo fora do enum
        {"tipo": "valor", "entradas": {"1": [0, 0, 999]}},         # componente fora de 0-255
        {"tipo": "intervalo", "entradas": [[[0], [0, 0, 0]]]},     # intervalo sem os dois limites
    ):
        with pytest.raises(ErroAPI):
            pred.validar_corpo({"titulo": "t", "colormap": ruim})


def test_legenda_sai_da_mesma_tabela_de_cor():
    """A legenda da tabela explícita tem de vir da MESMA estrutura que pinta o pixel."""
    from app.imagens import predefinicoes as pred

    cm = {"tipo": "valor", "entradas": {"4": [0, 200, 0], "8": [220, 220, 220]}}
    resolvido = pred.Resolvido(
        nome="scl", titulo="Classificação de cena", fabrica=False, versao=1, bandas=[1], expressao=None,
        colormap=cm, rescale=None, nodata_transparente=True, opacidade=1.0, resampling="nearest",
        hillshade=False, parcial=False)
    doc = pred.legenda_json(resolvido)
    assert doc["tipo"] == "tabela_de_cor"
    assert doc["amostras"] == [{"valor": 4, "cor": "#00c800"}, {"valor": 8, "cor": "#dcdcdc"}], doc["amostras"]
    png = pred.legenda_png(resolvido)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
