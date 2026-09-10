"""Bacia visual (viewshed) por `gdal_viewshed` (item L2-09-d; ativo da casa do L2-05-e, reusado).

Nada de viewshed próprio: o servidor escreve o terreno como GeoTIFF float32, roda o BINÁRIO
`gdal_viewshed` por subprocesso (com relógio de `limites.ANALISE3D_GDAL_TIMEOUT_S`) e devolve

  * `geotiff_base64` — os BYTES do arquivo que o gdal_viewshed escreveu, sem retoque nenhum (é isso
    que a cláusula "byte a byte contra o gdal_viewshed direto" compara);
  * `png_viewshed_base64` / `png_relevo_base64` — só no modo NORMAL: o raster pintado (verde =
    visível, vermelho = invisível declarado, transparente = fora de alcance) sobre o relevo
    sombreado em cinza, para o mapa e para a tela /analise3d;
  * contagem de células por valor declarado e os SHA-256 de entrada e de saída (procedência).

Valores declarados, nunca inferidos: `-vv` (visível, padrão 255), `-iv` (invisível, padrão 128) e
`-ov` (fora de alcance, padrão 0) são passados ao binário e a contagem usa exatamente esses três
valores — no modo DEM/GROUND a saída é de alturas em float64 e a contagem é omitida (não faz sentido por valor).

Semântica do GDAL, medida nesta máquina (09/09): `-oz` é altura RELATIVA ao terreno (observador a -5
com DEM plano a 100 devolve raster com células visíveis — o binário não recusa observador abaixo do
terreno, então A ROTA recusa antes, com 422); com `-md`, o raster de saída é RECORTADO à janela do
alcance (linhas/colunas diferentes do terreno de entrada) — o recorte vem do binário e é devolvido
como ele escreveu.
"""

import base64
import hashlib
import io
import subprocess

import numpy as np

from app import limites
from app.analise3d.terreno import Terreno
from app.erros import ErroAPI

MODOS = {"normal": "NORMAL", "dem": "DEM", "ground": "GROUND"}


def versao_gdal() -> str:
    """Versão do GDAL da casa (procedência; uma chamada por resposta de viewshed)."""
    try:
        r = subprocess.run(["gdalinfo", "--version"], capture_output=True, text=True, timeout=10)
        saida = (r.stdout or r.stderr).strip()
        return saida.splitlines()[0] if saida else "desconhecida"
    except (OSError, subprocess.TimeoutExpired):
        return "desconhecida"


def _png_do_viewshed(
    matriz: np.ndarray, alturas: np.ndarray, visivel: int, invisivel: int, fora: int
) -> tuple[bytes, bytes]:
    """(PNG do viewshed pintado, PNG do relevo sombreado). Modo NORMAL; PIL e numpy só aqui."""
    from PIL import Image

    altura, largura = matriz.shape
    tela = np.zeros((altura, largura, 4), dtype=np.uint8)
    tela[matriz == visivel] = (30, 160, 60, 170)  # verde: visível
    if invisivel not in (visivel, fora):
        tela[matriz == invisivel] = (190, 40, 40, 170)  # vermelho: invisível declarado
    vista = Image.fromarray(tela, "RGBA")

    relevo = np.asarray(alturas, dtype=np.float64)
    if relevo.shape[0] > 1 and relevo.shape[1] > 1 and float(relevo.max() - relevo.min()) > 0:
        gz, gy = np.gradient(relevo)  # gradiente por célula; luz vinda de noroeste (aproximação declarada)
        brilho = (gz - gy).ravel()
        faixa = float(brilho.max() - brilho.min()) or 1.0
        cinza = (255 * (brilho - brilho.min()) / faixa).astype(np.uint8)
        relevo_png = Image.fromarray(cinza.reshape(altura, largura), "L")
    else:
        # terreno plano: cinza cheio (gradiente é zero; a tela não mente sobre o que não tem relevo)
        relevo_png = Image.new("L", (largura, altura), 128)

    b_vista, b_relevo = io.BytesIO(), io.BytesIO()
    vista.save(b_vista, "PNG")
    relevo_png.save(b_relevo, "PNG")
    return b_vista.getvalue(), b_relevo.getvalue()


def bacia_visual(
    terreno: Terreno,
    observador: tuple[float, float],
    altura_observador_m: float,
    altura_alvo_m: float = 0.0,
    distancia_max_m: float | None = None,
    coef_curvatura: float = 0.85714,
    modo: str = "normal",
    visivel_valor: int = 255,
    invisivel_valor: int = 128,
    fora_de_alcance_valor: int = 0,
) -> dict:
    """Roda o gdal_viewshed sobre o terreno e devolve o raster (GeoTIFF base64), PNGs e procedência."""
    ox, oy = observador
    terreno.exigir_sobre_o_terreno(ox, oy, altura_observador_m, "observador")
    if modo not in MODOS:
        raise ErroAPI(422, "modo_invalido", f"modo '{modo}' não é um dos: {', '.join(sorted(MODOS))}")
    if distancia_max_m is not None and distancia_max_m > limites.ANALISE3D_DISTANCIA_MAX_M:
        raise ErroAPI(
            422,
            "distancia_acima_do_teto",
            f"distância máxima de {distancia_max_m:g} m passa do teto de {limites.ANALISE3D_DISTANCIA_MAX_M:g} m",
        )
    valores = {"visivel": visivel_valor, "invisivel": invisivel_valor, "fora_de_alcance": fora_de_alcance_valor}
    for nome, v in valores.items():
        if not (0 <= v <= 255):
            raise ErroAPI(422, "valor_raster_invalido", f"valor {nome} precisa estar entre 0 e 255")

    with terreno.geotiff_temporario() as (origem, sha_entrada):
        destino = origem.with_name("viewshed.tif")
        comando = [
            "gdal_viewshed",
            "-ox", f"{ox:.6f}",
            "-oy", f"{oy:.6f}",
            "-oz", f"{altura_observador_m:.6f}",
            "-tz", f"{altura_alvo_m:.6f}",
            "-cc", f"{coef_curvatura:.5f}",
            "-vv", str(visivel_valor),
            "-iv", str(invisivel_valor),
            "-ov", str(fora_de_alcance_valor),
            "-om", MODOS[modo],
            "-q",
            str(origem),
            str(destino),
        ]
        if distancia_max_m is not None:
            comando[1:1] = ["-md", f"{distancia_max_m:.6f}"]
        try:
            r = subprocess.run(
                comando, capture_output=True, text=True, timeout=limites.ANALISE3D_GDAL_TIMEOUT_S
            )
        except subprocess.TimeoutExpired as e:
            raise ErroAPI(
                504,
                "viewshed_tempo_esgotado",
                f"gdal_viewshed passou de {limites.ANALISE3D_GDAL_TIMEOUT_S} s",
            ) from e
        if r.returncode != 0 or not destino.exists():
            detalhe = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["sem saída"]
            raise ErroAPI(422, "viewshed_falhou", f"gdal_viewshed recusou a entrada: {detalhe[0][:400]}")
        geotiff = destino.read_bytes()
        sha_saida = hashlib.sha256(geotiff).hexdigest()

    import rasterio

    with rasterio.open(io.BytesIO(geotiff)) as ds:
        matriz = ds.read(1)
        # janela que o binário devolveu (o -md RECORTA o raster): geotransform do arquivo de saída
        col0 = int(round((ds.transform.c - terreno.x0) / terreno.celula_m))
        lin0 = int(round((terreno.y1 - ds.transform.f) / terreno.celula_m))
        nh, nw = int(matriz.shape[0]), int(matriz.shape[1])
        janela_ok = col0 >= 0 and lin0 >= 0 and lin0 + nh <= terreno.nlinhas and col0 + nw <= terreno.ncolunas

    saida: dict = {
        "geotiff_base64": base64.b64encode(geotiff).decode("ascii"),
        "comando": comando,
        "ferramenta": "gdal_viewshed",
        "versao_gdal": versao_gdal(),
        "sha256_terreno_geotiff": sha_entrada,
        "sha256_viewshed_geotiff": sha_saida,
        "dimensoes": {"linhas": nh, "colunas": nw},
        "modo": modo,
    }
    if modo == "normal":
        saida["celulas_visiveis"] = int((matriz == visivel_valor).sum())
        saida["celulas_invisiveis"] = int((matriz == invisivel_valor).sum()) if invisivel_valor not in (
            visivel_valor,
            fora_de_alcance_valor,
        ) else 0
        fora = fora_de_alcance_valor not in (visivel_valor, invisivel_valor)
        saida["celulas_fora_de_alcance"] = int((matriz == fora_de_alcance_valor).sum()) if fora else 0
        if janela_ok:
            # o relevo sombreado é recortado à MESMA janela do raster de saída — o PNG nunca
            # desalinha do GeoTIFF; sem janela encaixável, os PNGs são omitidos (nada de colagem)
            relevo = terreno.para_numpy()[lin0 : lin0 + nh, col0 : col0 + nw]
            png_vista, png_relevo = _png_do_viewshed(
                matriz, relevo, visivel_valor, invisivel_valor, fora_de_alcance_valor
            )
            saida["png_viewshed_base64"] = base64.b64encode(png_vista).decode("ascii")
            saida["png_relevo_base64"] = base64.b64encode(png_relevo).decode("ascii")
    return saida
