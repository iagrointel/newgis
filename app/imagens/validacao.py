"""Validação isolada de raster antes de qualquer conversão (item L1-01-ingest-raster; ADR
20260906T2127 decisão 3). Roda `gdalinfo -json` como NETO do job (`ctx.subprocesso`: herda o
RLIMIT_DATA do worker e morre com o cancelamento), com `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`
(o GDAL nunca abre arquivo vizinho por conta própria — sidecar .aux.xml/.wld com conteúdo hostil
não entra) e o ambiente do processo sem variável de proxy/credencial de nuvem: o arquivo validado
é sempre a cópia LOCAL no diretório de trabalho do job, nunca uma URL.

Regras (a refutação do item nomeia as três primeiras):
- sem CRS: RecusaValidacao('sem_crs') com mensagem que ensina a reenviar declarando o EPSG;
  com `epsg_declarado` no pedido, o EPSG é aceito e fica registrado como decisão humana;
- nodata fora do intervalo do dtype (ex.: -9999 em Byte): corrige para None (a declaração é
  impossível de representar e enganaria as estatísticas) e registra em `nodata_corrigido`;
  nodata NaN em dtype inteiro idem; nodata impossível de outra forma recusa;
- 16 bits (UInt16/Int16): importa certo — dtype preservado no perfil científico;
- dtype complexo (CInt16/CFloat32/...) ou dimensão/bandas acima de app.limites: recusa.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import pyproj

from app import limites

# variáveis que NÃO chegam ao neto: credenciais/proxy de nuvem (a validação nunca sai à rede)
_BLOQUEADAS = (
    "AWS_", "GS_", "AZURE", "CPL_VSIL_", "GDAL_HTTP", "HTTP_PROXY", "HTTPS_PROXY",
    "http_proxy", "https_proxy",
)

FAIXAS_DTYPE: dict[str, tuple[float, float]] = {
    "Byte": (0, 255),
    "UInt16": (0, 65535),
    "Int16": (-32768, 32767),
    "UInt32": (0, 4294967295),
    "Int32": (-2147483648, 2147483647),
}
DTYPES_ACEITOS = tuple(FAIXAS_DTYPE) + ("Float32", "Float64")


class RecusaValidacao(ValueError):
    """Entrada recusada com mensagem para o usuário (código estável + detalhes)."""

    def __init__(self, codigo: str, mensagem: str, detalhes: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.detalhes = detalhes or {}


@dataclass
class RelatorioValidacao:
    driver: str
    largura: int
    altura: int
    bandas: int
    dtype: str
    epsg: int
    epsg_origem: str                    # 'arquivo' | 'declarado'
    nodata: list[float | None]
    nodata_corrigido: list[float | None] | None  # None = nada precisou corrigir
    geotransform: list[float]
    wkt: str | None
    categorico: bool
    avisos: list[str] = field(default_factory=list)

    def nodata_final(self) -> list[float | None]:
        return self.nodata_corrigido if self.nodata_corrigido is not None else self.nodata


def ambiente_isolado() -> dict:
    """Ambiente do neto: o do worker MENOS credenciais/proxy de rede, MAIS o cadeado de sidecar."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_BLOQUEADAS)}
    env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    return env


def _gdalinfo(ctx, caminho: str) -> dict:
    r = ctx.subprocesso(["gdalinfo", "-json", "-nomd", caminho], env=ambiente_isolado())
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        detalhe = (linhas[-1] if linhas else "sem detalhe")[:300]
        codigo = "formato_nao_suportado" if "not recognized as being in a supported file format" in (r.stderr or "") \
            else "nao_abre"
        raise RecusaValidacao(
            codigo,
            f"o GDAL não abriu o arquivo como raster suportado nesta instalação: {detalhe}",
        )
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RecusaValidacao("nao_abre", f"gdalinfo não devolveu JSON válido: {e}") from e


def _epsg_de(wkt: str | None) -> int | None:
    if not wkt:
        return None
    try:
        return pyproj.CRS.from_user_input(wkt).to_epsg(min_confidence=70)
    except pyproj.exceptions.CRSError:
        return None


def _nodata_bandas(info: dict, bandas: int) -> list[float | None]:
    saida: list[float | None] = []
    for b in (info.get("bands") or [])[:bandas]:
        v = b.get("noDataValue")
        saida.append(float(v) if isinstance(v, (int, float)) else None)
    while len(saida) < bandas:
        saida.append(None)
    return saida


def _conferir_nodata(dtype: str, nodata: list[float | None]) -> tuple[list[float | None] | None, list[str]]:
    """Devolve (corrigido ou None se nada mudou, avisos). Nodata fora da faixa do dtype vira None:
    a declaração é irrepresentável no dtype (o GDAL clampeia na leitura e as estatísticas sairiam
    erradas) — derrubar a declaração errada é o conserto sem perda, registrado na proveniência."""
    faixa = FAIXAS_DTYPE.get(dtype)
    if faixa is None:  # Float32/Float64: qualquer nodata real é representável
        for v in nodata:
            if v is not None and math.isnan(v):
                return None, ["nodata NaN em banda de ponto flutuante mantido (NaN é o próprio nodata)"]
        return None, []
    lo, hi = faixa
    corrigido: list[float | None] = []
    mudou = False
    avisos: list[str] = []
    for i, v in enumerate(nodata):
        if v is None:
            corrigido.append(None)
            continue
        invalido = math.isnan(v) or v < lo or v > hi or (dtype != "Float32" and v != int(v))
        if invalido:
            corrigido.append(None)
            mudou = True
            avisos.append(
                f"nodata declarado ({v}) fora do intervalo do tipo {dtype} [{lo}, {hi}] na banda {i + 1}: "
                "declaração descartada (não representável); nenhum pixel é mascarado no produto"
            )
        else:
            corrigido.append(float(int(v)))
    return (corrigido if mudou else None), avisos


def validar(ctx, caminho: str, epsg_declarado: int | None = None) -> RelatorioValidacao:
    """Valida o raster LOCAL em `caminho`; levanta RecusaValidacao. `epsg_declarado` só é usado
    quando o arquivo não traz CRS próprio (e fica registrado como decisão humana, nunca silencioso)."""
    info = _gdalinfo(ctx, caminho)
    driver = (info.get("driverShortName") or "").upper()
    largura, altura = info.get("size", [0, 0])[:2]
    bandas_info = info.get("bands") or []
    bandas = len(bandas_info)
    if not largura or not altura or not bandas:
        raise RecusaValidacao("raster_vazio", "o arquivo não tem dimensões ou bandas de raster")
    if largura > limites.RASTER_DIMENSAO_MAX or altura > limites.RASTER_DIMENSAO_MAX:
        raise RecusaValidacao(
            "dimensao_acima",
            f"raster de {largura}x{altura} pixels acima do máximo desta instalação "
            f"({limites.RASTER_DIMENSAO_MAX} por eixo)",
        )
    if bandas > limites.RASTER_BANDAS_MAX:
        raise RecusaValidacao(
            "bandas_acima",
            f"raster com {bandas} bandas acima do máximo desta instalação ({limites.RASTER_BANDAS_MAX})",
        )

    dtype = bandas_info[0].get("type", "")
    if dtype not in DTYPES_ACEITOS:
        raise RecusaValidacao(
            "dtype_nao_suportado",
            f"tipo de dado {dtype!r} não suportado (aceitos: {', '.join(DTYPES_ACEITOS)}); "
            "raster complexo (SAR) fica para item próprio",
        )
    mistos = {b.get("type") for b in bandas_info}
    if len(mistos) > 1:
        raise RecusaValidacao(
            "dtype_misto",
            f"bandas com tipos mistos {sorted(mistos)}: separe em arquivos de um tipo só antes de enviar",
        )

    wkt = (info.get("coordinateSystem") or {}).get("wkt")
    epsg = _epsg_de(wkt)
    epsg_origem = "arquivo"
    if epsg is None:
        if epsg_declarado is None:
            raise RecusaValidacao(
                "sem_crs",
                "o raster não declara sistema de coordenadas (CRS): reenvie informando o EPSG no campo "
                "'epsg_declarado' do pedido (ex.: 4326 para graus, 31983 para SIRGAS 2000 UTM 23S)",
            )
        try:
            pyproj.CRS.from_epsg(int(epsg_declarado))
        except (pyproj.exceptions.CRSError, ValueError, TypeError) as e:
            raise RecusaValidacao(
                "epsg_invalido", f"EPSG declarado {epsg_declarado!r} não existe na base EPSG: {e}"
            ) from e
        epsg = int(epsg_declarado)
        epsg_origem = "declarado"

    geotransform = info.get("geoTransform") or []
    if not geotransform or len(geotransform) != 6:
        raise RecusaValidacao(
            "sem_geotransform",
            "o raster tem CRS mas não tem geotransform (não é georreferenciado pixel a pixel): "
            "georreferencie antes de enviar",
        )

    nodata = _nodata_bandas(info, bandas)
    nodata_corrigido, avisos = _conferir_nodata(dtype, nodata)
    categorico = any(b.get("colorTable") for b in bandas_info)

    return RelatorioValidacao(
        driver=driver, largura=int(largura), altura=int(altura), bandas=bandas, dtype=dtype,
        epsg=epsg, epsg_origem=epsg_origem, nodata=nodata, nodata_corrigido=nodata_corrigido,
        geotransform=[float(v) for v in geotransform], wkt=wkt, categorico=categorico, avisos=avisos,
    )
