"""Unidade do terreno da análise 3D (L2-09-d): validação da grade, amostragem bilinear e GeoTIFF."""

import hashlib

import pytest
from pydantic import ValidationError

from app.analise3d.terreno import Terreno, sha256_da_grade
from app.erros import ErroAPI


def grade_simples() -> Terreno:
    return Terreno(
        srid=31983, x0=200000.0, y0=7400000.0, celula_m=10.0, alturas=[[0.0, 10.0], [20.0, 40.0]]
    )


def test_grade_precisa_ser_retangular_com_2_colunas_ou_mais():
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[1, 2], [3]])
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[1]])


def test_grade_acima_do_teto_de_celulas_e_recusada():
    n = 600  # 600*600 = 360.000 > 250.000
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[0.0] * n for _ in range(n)])


def test_altura_nao_finita_ou_fora_da_faixa_e_recusada():
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[0.0, 10_001.0], [0.0, 0.0]])
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[0.0, float("nan")], [0.0, 0.0]])


def test_chave_desconhecida_e_recusada():
    with pytest.raises(ValidationError):
        Terreno(srid=31983, x0=0, y0=0, celula_m=1, alturas=[[0, 0], [0, 0]], crs="4326")


def test_amostrar_bilinear_no_centro_da_celula_2x2():
    t = grade_simples()
    cx = t.x0 + t.celula_m  # fronteira entre as duas colunas
    cy = t.y0 + t.celula_m  # fronteira entre as duas linhas (linha 0 = norte)
    assert t.amostrar(cx, cy) == pytest.approx((10.0 + 40.0 + 0.0 + 20.0) / 4.0)


def test_amostrar_no_vertice_da_grade_e_o_valor_da_celula():
    t = grade_simples()
    # canto noroeste = célula (linha 0, coluna 0) = 0.0; canto sudeste = célula (linha 1, coluna 1) = 40.0
    assert t.amostrar(t.x0, t.y1) == pytest.approx(0.0)
    assert t.amostrar(t.x1, t.y0) == pytest.approx(40.0)


def test_amostrar_fora_da_grade_levanta_valueerror():
    with pytest.raises(ValueError):
        grade_simples().amostrar(-5.0, 7400000.0)


def test_ponto_fora_e_abaixo_do_terreno_viram_422():
    t = grade_simples()
    with pytest.raises(ErroAPI) as fora:
        t.exigir_dentro(999.0, 7400000.0, "alvo")
    assert fora.value.status_code == 422 and fora.value.erro == "ponto_fora_do_terreno"
    with pytest.raises(ErroAPI) as baixo:
        t.exigir_sobre_o_terreno(200000.0, 7400001.0, -0.5, "observador")
    assert baixo.value.status_code == 422 and baixo.value.erro == "ponto_abaixo_do_terreno"


def test_geotiff_temporario_grava_e_apaga():
    import rasterio

    t = grade_simples()
    with t.geotiff_temporario() as (caminho, sha):
        assert len(sha) == 64
        with rasterio.open(caminho) as ds:
            lida = ds.read(1)
            assert ds.crs.to_epsg() == 31983
        assert lida.tolist() == [[0.0, 10.0], [20.0, 40.0]]
        bytes_arquivo = caminho.read_bytes()
    assert hashlib.sha256(bytes_arquivo).hexdigest() == sha
    assert not caminho.exists()


def test_sha256_da_grade_independe_da_ordem_das_chaves_do_json():
    t = grade_simples()
    outro = Terreno(
        srid=31983, x0=200000.0, y0=7400000.0, celula_m=10.0, alturas=[[0.0, 10.0], [20.0, 40.0]]
    )
    assert sha256_da_grade(t) == sha256_da_grade(outro)
    diferente = Terreno(
        srid=31983, x0=200000.0, y0=7400000.0, celula_m=10.0, alturas=[[0.0, 10.0], [20.0, 41.0]]
    )
    assert sha256_da_grade(t) != sha256_da_grade(diferente)
