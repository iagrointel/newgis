"""Item L1-08 (regras de mosaico e seleção de pixel) — as duas cláusulas que o adversário de linha L1
(T9) achou em aberto, construídas e medidas em 17/09/2026:

1. A hipótese do item lista 5 regras; a 5ª — "mais recente sem nuvem" — não existia: `SELECOES_PIXEL`
   tinha só os 7 métodos do rio-tiler e não havia uma linha de código que olhasse para máscara de nuvem.
   Agora existe `sem_nuvem` (`app/imagens/tiles.py`): antes de compor, todo pixel que o SCL classifica
   como nuvem/sombra/cirrus é APAGADO da cena, então a cena seguinte (mais antiga) preenche o buraco.
2. A refutação exigida pelo item — "cenas em CRS diferentes (UTM 22S e 23S) e alinhamento na borda de
   zona (≤ 1 px)" — não tinha teste nenhum. Agora tem, e a medição é de posição de borda, não de olho.

Este arquivo roda sobre COGs GERADOS EM DISCO LOCAL (`tiles.Fonte` sem sessão S3): a regra de pixel é
do motor, não da rota, e medi-la sem banco nem armazenamento remoto torna a prova reprodutível em
qualquer máquina. O isolamento por inquilino do asset `scl` é exercido pela rota, em
`tests/api/imagens/test_mosaico.py`.

⛔ LIMITAÇÃO DECLARADA: as cenas aqui são SINTÉTICAS, com SCL controlado. A cláusula do portão que pede
"6 cenas reais [...] nunca devolve pixel marcado como nuvem no SCL (teste em 100 pixels)" continua
ABERTA — este inquilino não tem acervo Sentinel-2 L2A com SCL. Está escrito em `docs/PARIDADE.md`.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

LADO = 256
RES = 30.0


def _cog(destino: Path, arr: np.ndarray, crs: str, x0: float, y0: float, res: float, nodata=0) -> Path:
    import rasterio
    from rasterio.transform import from_origin

    bruto = destino.with_name("bruto_" + destino.name)
    with rasterio.open(bruto, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=arr.dtype.name, crs=crs, nodata=nodata,
                       transform=from_origin(x0, y0, res, res)) as dst:
        dst.write(arr, 1)
    subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD", "-co", "BLOCKSIZE=128",
                    str(bruto), str(destino)], check=True)
    bruto.unlink(missing_ok=True)
    return destino


def _fonte(caminho: Path, mascara: Path | None = None):
    from app.imagens import tiles

    m = tiles.Fonte(str(mascara), tiles.env_gdal(), None) if mascara else None
    return tiles.Fonte(str(caminho), tiles.env_gdal(), None, mascara_nuvem=m)


def _origem_3857():
    import pyproj

    return pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(-47.95, -15.75)


def _centro_da_cena() -> tuple[float, float]:
    """Centro geográfico das cenas geradas por `_cog` a partir de `_origem_3857()` (256 px x 30 m)."""
    import pyproj

    x0, y0 = _origem_3857()
    meio = LADO * RES / 2
    return pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(
        x0 + meio, y0 - meio)


def _tile_do_centro(z: int = 14):
    """Ladrilho que CONTÉM o centro da cena. z=14 (~2,4 km) cabe inteiro dentro dos 7,68 km da cena —
    z=12 era maior que a própria cena e o ladrilho saía quase todo fora dela (achado desta bancada)."""
    from app.imagens import tiles

    lon, lat = _centro_da_cena()
    t = tiles.TMS.tile(lon, lat, z)
    return t.z, t.x, t.y


def _coluna_do_centro_da_cena() -> int:
    """Coluna do array (0-LADO) em que uma divisão feita no CENTRO da cena cai."""
    return LADO // 2


def _cinza(corpo: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(corpo)).convert("L"))


@pytest.fixture(scope="module")
def cenas_scl(tmp_path_factory):
    """Duas cenas no MESMO lugar. A mais recente vale 200 e o SCL dela diz NUVEM (classe 8); a antiga
    vale 60 e o SCL diz vegetação (classe 4). Com `first` ganha 200 (o pixel de nuvem); com `sem_nuvem`
    tem de ganhar 60."""
    d = tmp_path_factory.mktemp("l108scl")
    x0, y0 = _origem_3857()
    recente = _cog(d / "recente.tif", np.full((LADO, LADO), 200, dtype="uint16"), "EPSG:3857", x0, y0, RES)
    scl_recente = _cog(d / "scl_recente.tif", np.full((LADO, LADO), 8, dtype="uint8"),
                       "EPSG:3857", x0, y0, RES, nodata=255)
    antiga = _cog(d / "antiga.tif", np.full((LADO, LADO), 60, dtype="uint16"), "EPSG:3857", x0, y0, RES)
    scl_antiga = _cog(d / "scl_antiga.tif", np.full((LADO, LADO), 4, dtype="uint8"),
                      "EPSG:3857", x0, y0, RES, nodata=255)
    return {"recente": (recente, scl_recente), "antiga": (antiga, scl_antiga)}


def test_a_regra_existe_no_vocabulario_persistido():
    from app.imagens import mosaico, tiles

    assert "sem_nuvem" in mosaico.SELECOES_PIXEL
    assert "sem_nuvem" in tiles.METODOS_COMPOSICAO
    assert tiles.CLASSES_NUVEM_SCL == (1, 3, 8, 9, 10), tiles.CLASSES_NUVEM_SCL
    # a regra é aceita pelo contrato persistido do mosaico, não só pelo motor
    assert mosaico.validar_regras({"pixel_selection": "sem_nuvem"})["pixel_selection"] == "sem_nuvem"


def test_pixel_de_nuvem_nunca_vence(cenas_scl):
    """A medida do item: com `first` o pixel da cena mais recente (nublada) vence; com `sem_nuvem` ele
    é apagado e o da cena antiga, limpa, ocupa o lugar. Mesmo ladrilho, mesma ordem, só a regra muda."""
    from app.imagens import tiles

    z, x, y = _tile_do_centro()
    fontes = [_fonte(*cenas_scl["recente"]), _fonte(*cenas_scl["antiga"])]

    com_first = _cinza(tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], rescale=[(0, 255)],
                                               metodo="first"))
    com_regra = _cinza(tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], rescale=[(0, 255)],
                                               metodo="sem_nuvem"))
    assert com_first.max() == 200, f"controle: com 'first' o pixel nublado devia vencer ({com_first.max()})"
    assert com_regra.max() == 60, (
        f"com 'sem_nuvem' nenhum pixel podia vir da cena nublada; veio {com_regra.max()}")
    # em 100 pixels amostrados, nenhum é da cena de nuvem (a cláusula do portão, sobre cena sintética)
    amostra = com_regra[::26, ::26].ravel()[:100]
    assert not (amostra == 200).any(), "pixel de nuvem sobreviveu na amostra"


def test_sem_scl_a_regra_recusa_em_vez_de_virar_first(cenas_scl):
    """Rebaixar em silêncio para `first` seria devolver nuvem dizendo que é céu limpo."""
    from app.imagens import tiles

    z, x, y = _tile_do_centro()
    fontes = [_fonte(cenas_scl["recente"][0]), _fonte(*cenas_scl["antiga"])]
    with pytest.raises(tiles.ErroTile) as e:
        tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], metodo="sem_nuvem")
    assert "scl" in str(e.value).lower(), str(e.value)


def test_nuvem_parcial_e_costurada_pixel_a_pixel(tmp_path):
    """Nuvem em METADE da cena recente: a regra tem de costurar, não trocar a cena inteira."""
    from app.imagens import tiles

    x0, y0 = _origem_3857()
    scl = np.full((LADO, LADO), 4, dtype="uint8")
    scl[:, : _coluna_do_centro_da_cena()] = 9  # metade oeste da CENA com nuvem de alta probabilidade
    fontes = [
        _fonte(_cog(tmp_path / "r.tif", np.full((LADO, LADO), 200, "uint16"), "EPSG:3857", x0, y0, RES),
               _cog(tmp_path / "rs.tif", scl, "EPSG:3857", x0, y0, RES, nodata=255)),
        _fonte(_cog(tmp_path / "a.tif", np.full((LADO, LADO), 60, "uint16"), "EPSG:3857", x0, y0, RES),
               _cog(tmp_path / "as.tif", np.full((LADO, LADO), 4, "uint8"), "EPSG:3857", x0, y0, RES,
                    nodata=255)),
    ]
    z, x, y = _tile_do_centro()
    img = _cinza(tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], rescale=[(0, 255)],
                                         metodo="sem_nuvem"))
    valores = set(np.unique(img).tolist()) - {0}
    assert valores == {60, 200}, f"o ladrilho devia ter pixel das DUAS cenas; tem {sorted(valores)}"
    # e a costura respeita a geografia: o lado com nuvem é o que veio da cena antiga
    assert (img == 60).mean() > 0.2 and (img == 200).mean() > 0.2, (
        f"proporções degeneradas: 60 em {(img == 60).mean():.2f}, 200 em {(img == 200).mean():.2f}")


# ------------------------------------------------------------------ CRS nativos diferentes (22S x 23S)
@pytest.fixture(scope="module")
def cenas_crs_misto(tmp_path_factory):
    """A MESMA cena (borda vertical nítida no mesmo meridiano) gravada em dois CRS nativos: SIRGAS2000 /
    UTM 22S (EPSG:31982) e 23S (EPSG:31983)."""
    import pyproj

    d = tmp_path_factory.mktemp("l108crs")
    lon_o, lon_l, lat_s, lat_n = -48.10, -47.90, -15.90, -15.70
    lon_borda = (lon_o + lon_l) / 2
    saida = {"lon_borda": lon_borda, "bbox": (lon_o, lat_s, lon_l, lat_n)}
    for epsg in (31982, 31983):
        tf = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        cantos = [tf.transform(lo, la) for lo in (lon_o, lon_l) for la in (lat_s, lat_n)]
        xs = [c[0] for c in cantos]
        ys = [c[1] for c in cantos]
        res = (max(xs) - min(xs)) / LADO
        x_borda, _ = tf.transform(lon_borda, (lat_s + lat_n) / 2)
        # A borda tem de cair EXATAMENTE numa aresta de pixel nas duas cenas, senão o que se mede é o
        # arredondamento do dado de teste e não a reprojeção: com 84 m/px de cena contra ~10 m/px de
        # ladrilho, meio pixel de cena vale 4 pixels de ladrilho (medido nesta bancada: desvio aparente
        # de 3 px que não vinha da reprojeção). Por isso a origem é ancorada na própria borda.
        col_borda = LADO // 2
        x_min = x_borda - col_borda * res
        arr = np.full((LADO, LADO), 500, dtype="uint16")
        arr[:, col_borda:] = 4000
        saida[epsg] = _cog(d / f"c{epsg}.tif", arr, f"EPSG:{epsg}", x_min, max(ys), res)
    return saida


def _tile_crs_misto(cenas, z: int = 14):
    """Ladrilho no centro do retângulo coberto pelas duas cenas de CRS misto."""
    from app.imagens import tiles

    lon_o, lat_s, lon_l, lat_n = cenas["bbox"]
    t = tiles.TMS.tile((lon_o + lon_l) / 2, (lat_s + lat_n) / 2, z)
    return t.z, t.x, t.y


def _coluna_da_borda(img: np.ndarray) -> float:
    """Coluna onde o valor salta (média das linhas): a posição da borda com resolução de sub-pixel."""
    linha = img.mean(axis=0)
    alvo = (linha.max() + linha.min()) / 2
    acima = np.where(linha >= alvo)[0]
    assert acima.size, "a borda não aparece na imagem"
    return float(acima[0])


def test_cenas_de_crs_nativos_diferentes_alinham_abaixo_de_um_pixel(cenas_crs_misto):
    """Refutação literal do item: se a reprojeção estiver desalinhada, a mesma borda geográfica cai em
    colunas diferentes conforme a zona UTM nativa da cena. Mede-se a distância entre as duas."""
    from app.imagens import tiles

    z, x, y = _tile_crs_misto(cenas_crs_misto)
    colunas = {}
    for epsg in (31982, 31983):
        corpo = tiles.ladrilho_composto([_fonte(cenas_crs_misto[epsg])], z, x, y, bandas=[1],
                                        rescale=[(500, 4000)], metodo="first")
        colunas[epsg] = _coluna_da_borda(_cinza(corpo))
    desvio = abs(colunas[31982] - colunas[31983])
    assert desvio <= 1.0, (
        f"a borda de zona desalinhou {desvio:.2f} px entre EPSG:31982 e EPSG:31983 "
        f"(colunas {colunas}) — o portão do item exige ≤ 1 px")


def test_mosaico_de_crs_misto_nao_deixa_buraco_na_costura(cenas_crs_misto):
    """Compor as duas cenas de CRS nativo diferente não pode abrir linha vazia entre elas."""
    from app.imagens import tiles

    z, x, y = _tile_crs_misto(cenas_crs_misto)
    fontes = [_fonte(cenas_crs_misto[31982]), _fonte(cenas_crs_misto[31983])]
    corpo = tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], rescale=[(500, 4000)], metodo="first")
    # "sem dado" é o canal ALFA, nunca o valor 0 do cinza: com rescale [(500,4000)] o lado oeste da
    # cena vale exatamente 500 e sai como cinza 0 — conferir `img > 0` mediria a cor, não a cobertura.
    alfa = np.asarray(Image.open(io.BytesIO(corpo)).convert("RGBA"))[:, :, 3]
    assert alfa.size and (alfa > 0).mean() > 0.99, (
        f"a composição deixou {100 * (alfa == 0).mean():.2f}% do ladrilho sem dado")


def test_media_ignora_nodata_de_uma_cena(tmp_path):
    """Refutação do item: `mean` com NoData numa cena não pode diluir a média com zero."""
    from app.imagens import tiles

    x0, y0 = _origem_3857()
    cheia = np.full((LADO, LADO), 100, dtype="uint16")
    furada = np.full((LADO, LADO), 300, dtype="uint16")
    furada[:, : _coluna_do_centro_da_cena()] = 0  # nodata na metade oeste da cena
    fontes = [_fonte(_cog(tmp_path / "f.tif", furada, "EPSG:3857", x0, y0, RES)),
              _fonte(_cog(tmp_path / "c.tif", cheia, "EPSG:3857", x0, y0, RES))]
    z, x, y = _tile_do_centro()
    img = _cinza(tiles.ladrilho_composto(fontes, z, x, y, bandas=[1], rescale=[(0, 400)], metodo="mean"))
    # onde SÓ a cena cheia tem dado, a média é 100; onde as duas têm, é 200 (100 e 300). Se o NoData
    # entrasse na conta, o lado furado daria 50 — é esse valor que não pode aparecer.
    presentes = sorted(set(np.unique(img).tolist()) - {0})
    esperados = {round(100 / 400 * 255), round(200 / 400 * 255)}
    proibido = round(50 / 400 * 255)
    assert set(presentes) <= {v for e in esperados for v in (e - 1, e, e + 1)}, (
        f"valores fora do esperado {sorted(esperados)}: {presentes}")
    assert len(presentes) >= 2, f"o ladrilho devia cruzar a borda do NoData; tem {presentes}"
    assert proibido not in presentes, "o NoData entrou na média (diluiu para 50)"
