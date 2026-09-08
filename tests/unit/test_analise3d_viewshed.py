"""Unidade da bacia visual (L2-09-d).

Cláusula 2 do portão: "viewshed igual ao gdal_viewshed direto (byte a byte)" — o teste roda o
BINÁRIO duas vezes: uma pela casa (`bacia_visual`) e outra direto, com a MESMA linha de comando
devolvida na resposta, sobre o MESMO GeoTIFF de entrada; os dois arquivos de saída têm de ser o
mesmo byte a byte.

Refutação do item: relevo ÍNGREME comparado com o gdal_viewshed (mesma comparação byte a byte em
condição adversa) e observador abaixo do terreno (a rota recusa; o binário sozinho não recusaria).
"""

import base64
import hashlib
import subprocess

import pytest

from app.analise3d.terreno import Terreno
from app.analise3d.vista import bacia_visual
from app.erros import ErroAPI

CELULA = 10.0
N = 40  # 40x40 células de 10 m = 400 m de lado
X0, Y0 = 250000.0, 7350000.0
OBS = (X0 + 5 * CELULA, Y0 + 20 * CELULA)


def terreno_relevo(ingreme: bool) -> Terreno:
    """Relevo suave (cone largo) ou íngreme (cone estreito e alto)."""
    import math

    cume = 40.0 if not ingreme else 200.0
    sigma = 80.0 if not ingreme else 30.0
    alturas = []
    for i in range(N):
        linha = []
        for j in range(N):
            r2 = (j * CELULA - 200.0) ** 2 + (i * CELULA - 200.0) ** 2
            linha.append(round(cume * math.exp(-r2 / (2 * sigma * sigma)), 3))
        alturas.append(linha)
    return Terreno(srid=31983, x0=X0, y0=Y0, celula_m=CELULA, alturas=alturas)


def gdal_direto(terreno: Terreno, comando: list[str], tmp) -> bytes:
    """Reescreve o GeoTIFF da grade e roda a MESMA linha de comando que a casa rodou, num diretório novo.

    `comando` vem da resposta e termina com `<origem> <destino>`; os dois caminhos são trocados pelos
    do diretório de teste para não depender do temporário já apagado da casa.
    """
    origem = tmp / "terreno.tif"
    destino = tmp / "direto.tif"
    terreno.escrever_geotiff(origem)
    diretivo = comando[:-2] + [str(origem), str(destino)]
    r = subprocess.run(diretivo, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"gdal_viewshed direto falhou: {r.stderr}"
    return destino.read_bytes()


@pytest.mark.parametrize("ingreme", [False, True])
def test_clausula_2_viewshed_igual_ao_gdal_direto_byte_a_byte(ingreme, tmp_path, medida):
    terreno = terreno_relevo(ingreme)
    r = bacia_visual(terreno, OBS, altura_observador_m=2.0, distancia_max_m=30000.0)
    esperado = gdal_direto(terreno, r["comando"], tmp_path)
    nosso = base64.b64decode(r["geotiff_base64"])
    assert nosso == esperado, "o GeoTIFF da casa não é o byte a byte do gdal_viewshed direto"
    assert r["sha256_viewshed_geotiff"] == hashlib.sha256(nosso).hexdigest()
    assert r["ferramenta"] == "gdal_viewshed"
    assert r["versao_gdal"] and "GDAL" in r["versao_gdal"]
    assert r["dimensoes"]["linhas"] == N and r["dimensoes"]["colunas"] == N
    assert r["celulas_visiveis"] > 0
    medida("L2-09-d-analise-3d-visibilidade")(
        "clausula2_viewshed_byte_a_byte_igual", 1, "booleano",
        "GeoTIFF da rota igual ao gdal_viewshed direto (mesmo comando, mesma grade), relevo suave e íngreme",
    )


def test_png_do_modo_normal_sobre_o_relevo():
    import io

    from PIL import Image

    r = bacia_visual(terreno_relevo(False), OBS, 2.0, distancia_max_m=30000.0)
    vista = Image.open(io.BytesIO(base64.b64decode(r["png_viewshed_base64"])))
    relevo = Image.open(io.BytesIO(base64.b64decode(r["png_relevo_base64"])))
    assert vista.mode == "RGBA" and vista.size == (N, N)
    assert relevo.mode == "L" and relevo.size == (N, N)
    cores = vista.convert("RGBA").getcolors(maxcolors=256)
    alpha = [c for c in cores if c[1][3] > 0]
    assert len(alpha) >= 2, "esperava verde (visível) e vermelho (invisível) no PNG pintado"


def test_modo_dem_saida_float32_sem_contagem_nem_png():
    import io

    import rasterio

    r = bacia_visual(terreno_relevo(False), OBS, 2.0, distancia_max_m=30000.0, modo="dem")
    with rasterio.open(io.BytesIO(base64.b64decode(r["geotiff_base64"]))) as ds:
        assert ds.dtypes[0] == "float64"  # DEM sai float64: o binário escreve assim
    assert "png_viewshed_base64" not in r
    assert "celulas_visiveis" not in r


def test_md_corta_o_raster_a_janela_do_binario():
    """Com -md curto (100 m), o raster sai RECORTADO — dimensoes menores que a grade; é o binário
    escrevendo, e a casa devolve como ele escreveu (a comparação byte a byte já cobre o conteúdo)."""
    r = bacia_visual(terreno_relevo(False), OBS, 2.0, distancia_max_m=100.0)
    assert r["dimensoes"]["linhas"] < N and r["dimensoes"]["colunas"] < N


def test_refutacao_relevo_igreme_observador_abaixo_do_terreno_e_422():
    with pytest.raises(ErroAPI) as e:
        bacia_visual(terreno_relevo(True), OBS, altura_observador_m=-3.0)
    assert e.value.status_code == 422 and e.value.erro == "ponto_abaixo_do_terreno"


def test_modo_invalido_distancia_acima_do_teto_e_valores_fora_da_faixa():
    terreno = terreno_relevo(False)
    with pytest.raises(ErroAPI) as e:
        bacia_visual(terreno, OBS, 2.0, modo="sombra")
    assert e.value.erro == "modo_invalido"
    with pytest.raises(ErroAPI) as e:
        bacia_visual(terreno, OBS, 2.0, distancia_max_m=40_000.0)
    assert e.value.erro == "distancia_acima_do_teto"
    with pytest.raises(ErroAPI) as e:
        bacia_visual(terreno, OBS, 2.0, visivel_valor=300)
    assert e.value.erro == "valor_raster_invalido"
