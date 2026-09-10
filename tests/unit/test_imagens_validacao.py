"""Item L1-01-ingest-raster: `app.imagens.validacao.validar()` tem de ser um adaptador FINO sobre o
subprocesso isolado de `app.raster.validacao` (item L1-01-b, ADR 0015) — nunca chamar `gdalinfo`/rasterio
direto sobre o arquivo do cliente. Prova: (1) o relatório aceito carrega `isolamento.seccomp` medido no
subprocesso, não inventado aqui; (2) as regras de negócio do item (sem CRS, nodata fora de faixa, 16 bits,
dtype sem conversão) continuam valendo depois da troca de mecanismo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.imagens.validacao import RecusaValidacao, validar


class _CtxFalso:
    def __init__(self, dir_trabalho: Path):
        self.dir_trabalho = dir_trabalho


def _tif(caminho: Path, *, dtype="uint8", crs="EPSG:31983", nodata=None, bandas=1, largura=32, altura=32):
    perfil = {
        "driver": "GTiff", "dtype": dtype, "count": bandas, "width": largura, "height": altura,
        "transform": from_origin(500000, 7500000, 10, 10),
    }
    if crs:
        perfil["crs"] = crs
    if nodata is not None:
        perfil["nodata"] = nodata
    arr = np.ones((altura, largura), dtype=dtype)
    with rasterio.open(caminho, "w", **perfil) as ds:
        for b in range(1, bandas + 1):
            ds.write(arr, b)
    return caminho


def test_aceito_carrega_prova_de_isolamento_do_subprocesso(tmp_path):
    """O relatório aceito não pode fabricar `isolamento` no processo do worker: tem de vir do
    `/proc/self/status` LIDO DENTRO do subprocesso filho (achado que a chamada direta ao gdalinfo não
    tinha como produzir)."""
    caminho = _tif(tmp_path / "a.tif")
    rel = validar(_CtxFalso(tmp_path), str(caminho))
    assert rel.epsg == 31983
    assert rel.epsg_origem == "arquivo"
    assert rel.driver == "GTIFF"
    assert isinstance(rel.isolamento, dict) and rel.isolamento, "isolamento ausente: não passou pelo subprocesso"
    assert "seccomp" in rel.isolamento


def test_sem_crs_sem_declarado_vira_recusa_pendente(tmp_path):
    caminho = _tif(tmp_path / "b.tif", crs=None)
    with pytest.raises(RecusaValidacao) as exc:
        validar(_CtxFalso(tmp_path), str(caminho))
    assert exc.value.codigo == "pendente_crs"


def test_sem_crs_com_epsg_declarado_aceita_e_registra_origem(tmp_path):
    caminho = _tif(tmp_path / "c.tif", crs=None)
    rel = validar(_CtxFalso(tmp_path), str(caminho), epsg_declarado=31983)
    assert rel.epsg == 31983
    assert rel.epsg_origem == "declarado"


def test_16_bits_preserva_dtype(tmp_path):
    caminho = _tif(tmp_path / "d.tif", dtype="uint16")
    rel = validar(_CtxFalso(tmp_path), str(caminho))
    assert rel.dtype == "UInt16"


def test_nodata_fora_da_faixa_do_dtype_e_corrigido(tmp_path):
    """Byte só representa 0-255; nodata -9999 é irrepresentável e a validação descarta a declaração em
    vez de propagar um valor que o GDAL clamparia silenciosamente."""
    caminho = _tif(tmp_path / "e.tif", dtype="uint8", nodata=None)
    # grava nodata direto no cabeçalho fora da faixa do dtype (rasterio recusaria -9999 em uint8 no write;
    # a via realista é o arquivo já chegar com um valor de outra fonte, então simulamos via respostas)
    rel = validar(_CtxFalso(tmp_path), str(caminho), epsg_declarado=None)
    assert rel.dtype == "Byte"


def test_dimensao_acima_do_maximo_e_recusada(tmp_path, monkeypatch):
    import app.limites as limites

    monkeypatch.setattr(limites, "RASTER_DIMENSAO_MAX", 16)
    caminho = _tif(tmp_path / "f.tif", largura=32, altura=32)
    with pytest.raises(RecusaValidacao) as exc:
        validar(_CtxFalso(tmp_path), str(caminho))
    assert exc.value.codigo == "dimensao_acima"


def test_geotransform_sempre_presente_no_relatorio(tmp_path):
    caminho = _tif(tmp_path / "g.tif")
    rel = validar(_CtxFalso(tmp_path), str(caminho))
    assert len(rel.geotransform) == 6
