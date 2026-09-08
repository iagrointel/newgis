"""Unidade do perfil de elevação (L2-09-d).

Cláusula 3 do portão: "perfil conferido com rasterio.sample" — a linha é escolhida passando pelo
CENTRO das células; nesses pontos o bilinear da casa é, por construção, exatamente o valor do pixel
que o `rasterio.sample` devolve. O teste escreve o GeoTIFF da grade, lê de volta com o rasterio e
compara valor a valor, e confere as estatísticas num relevo de rampa com contas à mão.
"""

import math

import pytest

from app.analise3d.perfil import perfil
from app.analise3d.terreno import Terreno
from app.erros import ErroAPI

CELULA = 10.0
N = 20  # 20x20 células de 10 m
X0, Y0 = 260000.0, 7340000.0


def terreno_ondulado() -> Terreno:
    alturas = []
    for i in range(N):
        linha = []
        for j in range(N):
            linha.append(round(10 + 5 * math.sin(i * 0.7) + 3 * math.cos(j * 0.9), 3))
        alturas.append(linha)
    return Terreno(srid=31983, x0=X0, y0=Y0, celula_m=CELULA, alturas=alturas)


def test_clausula_3_perfil_confere_com_rasterio_sample(tmp_path, medida):
    import rasterio

    terreno = terreno_ondulado()
    geotiff = tmp_path / "terreno.tif"
    terreno.escrever_geotiff(geotiff)
    y_linha = Y0 + 7.5 * CELULA  # centro da linha r (linha 0 = norte): y1 - (r + 0.5) * célula
    a = (X0 + 0.5 * CELULA, y_linha)
    b = (X0 + (N - 0.5) * CELULA, y_linha)
    r = perfil(terreno, a, b, N)
    with rasterio.open(geotiff) as ds:
        for amostra in r["amostras"]:
            (pixel,) = ds.sample([(amostra["x"], amostra["y"])])
            assert amostra["z_m"] == pytest.approx(float(pixel[0]), abs=1e-6), (
                f"bilinear da casa divergiu do rasterio.sample em ({amostra['x']}, {amostra['y']})"
            )
    medida("L2-09-d-analise-3d-visibilidade")(
        "clausula3_amostras_conferidas_rasterio_sample", len(r["amostras"]), "amostras",
        "valor a valor no centro de célula: bilinear da casa == rasterio.sample no GeoTIFF escrito",
    )


def test_bilinear_a_mao_na_grade_2x2():
    t = Terreno(srid=31983, x0=X0, y0=Y0, celula_m=10.0, alturas=[[0.0, 10.0], [20.0, 40.0]])
    r = perfil(t, (t.x0, t.y0), (t.x1, t.y1), 3)
    # extremos na banda de borda = célula do canto; meio da diagonal = média das 4 células
    assert r["amostras"][0]["z_m"] == pytest.approx(20.0)  # (x0, y0): linha 1, coluna 0
    assert r["amostras"][1]["z_m"] == pytest.approx((10.0 + 40.0 + 20.0 + 0.0) / 4.0)
    assert r["amostras"][2]["z_m"] == pytest.approx(10.0)  # (x1, y1): linha 0, coluna 1


def test_estatisticas_da_rampa_contadas_a_mao():
    # rampa: sobe 0 -> 30 m em 100 m e desce 30 -> 0 m em outros 100 m; 11 amostras de 20 m
    alturas = [[0.0] * 21 for _ in range(3)]
    for j in range(21):
        z = 3.0 * j if j <= 10 else 60.0 - 3.0 * j
        alturas[0][j] = z
        alturas[1][j] = z
        alturas[2][j] = z
    t = Terreno(srid=31983, x0=X0, y0=Y0, celula_m=10.0, alturas=alturas)
    a = (X0 + 0.5 * CELULA, Y0 + 1.5 * CELULA)
    b = (X0 + 20.5 * CELULA, Y0 + 1.5 * CELULA)
    r = perfil(t, a, b, 21)
    e = r["estatisticas"]
    assert r["distancia_m"] == pytest.approx(200.0)
    assert e["ganho_m"] == pytest.approx(30.0)
    assert e["perda_m"] == pytest.approx(30.0)
    assert e["z_min_m"] == pytest.approx(0.0)
    assert e["z_max_m"] == pytest.approx(30.0)
    # cada par de amostras consecutivas tem Δz 6 m em 20 m
    assert e["declividade_max_graus"] == pytest.approx(math.degrees(math.atan(3.0 / 10.0)))
    assert e["declividade_max_pct"] == pytest.approx(30.0)
    assert e["declividade_max_distancia_m"] == pytest.approx(10.0)
    assert len(r["amostras"]) == 21
    assert r["amostras"][0]["d_m"] == 0.0 and r["amostras"][-1]["d_m"] == pytest.approx(200.0)


def test_entradas_invalidas_viram_422():
    t = terreno_ondulado()
    with pytest.raises(ErroAPI) as e:
        perfil(t, (X0, Y0), (X0, Y0), 10)
    assert e.value.status_code == 422 and e.value.erro == "linha_nula"
    with pytest.raises(ErroAPI) as e:
        perfil(t, (X0, Y0), (X0 + 100, Y0), 1)
    assert e.value.erro == "amostras_invalidas"
    with pytest.raises(ErroAPI) as e:
        perfil(t, (X0, Y0), (X0 + 100, Y0), 20_001)
    assert e.value.erro == "amostras_invalidas"
    with pytest.raises(ErroAPI) as e:
        perfil(t, (-1.0, Y0), (X0 + 100, Y0), 10)
    assert e.value.erro == "ponto_fora_do_terreno"
