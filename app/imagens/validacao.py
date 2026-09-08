"""Validação isolada de raster antes de qualquer conversão (item L1-01-ingest-raster). Adaptador fino
sobre `app.raster.validacao.validar()` (item L1-01-b, ADR 0015): a leitura do arquivo do CLIENTE roda
inteira no subprocesso isolado daquele módulo (RLIMIT_AS/CPU/NOFILE/CORE, seccomp fechando
`socket(AF_INET/AF_INET6)`, ambiente GDAL sem rede/`readdir`/PAM, VRT conferido recursivamente por
`realpath`, zip pelo diretório central) — este módulo NUNCA chama `gdalinfo`/rasterio diretamente
sobre o arquivo enviado.

Histórico: a primeira versão deste módulo (turno do agente Kimi) rodava `gdalinfo -json` como neto do
job só com variáveis de ambiente como defesa (`GDAL_DISABLE_READDIR_ON_OPEN`, sem proxy/credencial de
nuvem no ambiente) — exatamente a defesa que o adversário do item L1-01-b já tinha provado insuficiente
(env var sozinha não fecha `/vsicurl`/PROJ na rede, achados 1-3 e 8 daquele repasse). Trocado nesta
revisão pelo módulo com seccomp; nenhuma regra de negócio abaixo mudou.

Regras de negócio preservadas (a refutação do item nomeia as três primeiras):
- sem CRS resolvível (EPSG): pendência ensinando a reenviar com `epsg_declarado`; com o campo, o EPSG
  vira a decisão humana registrada em `epsg_origem='declarado'`;
- nodata fora do intervalo do dtype (ex.: -9999 em Byte) ou NaN em dtype inteiro: corrigido para
  `None` (a declaração é irrepresentável e enganaria as estatísticas), registrado em `nodata_corrigido`;
- 16 bits (UInt16/Int16): dtype preservado no perfil científico;
- dtype sem conversão possível (`info.tipo_convertivel=false`: complexo, int64/uint64) ou WKT2 sem EPSG:
  recusa — a conversão para COG (item L1-01-c) não serve esses tipos e a geometria STAC exige EPSG.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from app import limites
from app.raster import validacao as _isolado

# variáveis que NÃO chegam ao neto do `gdal_translate` de conversão (cog.py): a conversão roda depois
# da validação já ter aceitado o arquivo, mas continua sem credencial/proxy de nuvem por princípio.
_BLOQUEADAS = (
    "AWS_", "GS_", "AZURE", "CPL_VSIL_", "GDAL_HTTP", "HTTP_PROXY", "HTTPS_PROXY",
    "http_proxy", "https_proxy",
)

# tipo do rasterio (numpy) -> nome GDAL, para preservar a interface que `cog.py` já lê (`rel.dtype`,
# comparado contra "Byte"/"UInt16"/.../"Float32" em vários pontos).
_DTYPE_RASTERIO_PARA_GDAL: dict[str, str] = {
    "uint8": "Byte", "int8": "Int8",
    "uint16": "UInt16", "int16": "Int16",
    "uint32": "UInt32", "int32": "Int32",
    "uint64": "UInt64", "int64": "Int64",
    "float32": "Float32", "float64": "Float64",
    "complex64": "CFloat32", "complex128": "CFloat64",
}

FAIXAS_DTYPE: dict[str, tuple[float, float]] = {
    "Byte": (0, 255),
    "UInt16": (0, 65535),
    "Int16": (-32768, 32767),
    "UInt32": (0, 4294967295),
    "Int32": (-2147483648, 2147483647),
}


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
    isolamento: dict = field(default_factory=dict)  # `info.isolamento` do subprocesso (prova, não promessa)

    def nodata_final(self) -> list[float | None]:
        return self.nodata_corrigido if self.nodata_corrigido is not None else self.nodata


def ambiente_isolado() -> dict:
    """Ambiente do neto do `gdal_translate` de CONVERSÃO (`cog.py`), rodado depois de a validação já ter
    aceitado o arquivo: o do worker menos credenciais/proxy de rede, mais o cadeado de sidecar. A leitura
    do arquivo ainda não confiado (a validação em si) não usa isto — usa o subprocesso com seccomp de
    `app.raster.validacao`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_BLOQUEADAS)}
    env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    return env


def _conferir_nodata(dtype: str, nodata: list[float | None]) -> tuple[list[float | None] | None, list[str]]:
    """Devolve (corrigido ou None se nada mudou, avisos). Nodata fora da faixa do dtype vira None: a
    declaração é irrepresentável no dtype (o GDAL clampeia na leitura e as estatísticas sairiam erradas)
    — derrubar a declaração errada é o conserto sem perda, registrado na proveniência."""
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
        invalido = math.isnan(v) or v < lo or v > hi or v != int(v)
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
    """Valida o raster LOCAL em `caminho` chamando o subprocesso isolado de `app.raster.validacao`;
    levanta `RecusaValidacao` para `recusado`. Pendência de CRS bloqueia (a única entrada humana que o
    item aceita é `epsg_declarado`); pendência de `nodata`/`data_aquisicao`/`escala` NÃO bloqueia — o
    item ainda não tem tela de resposta para elas, e a hipótese é "importa certo ou recusa": um raster
    sem NoData declarado tem de entrar sem máscara, com o aviso registrado, não travar a ingestão.
    `epsg_declarado` só é usado quando o arquivo não traz CRS próprio, e fica registrado como decisão
    humana, nunca silencioso."""
    respostas = {"crs": f"EPSG:{epsg_declarado}"} if epsg_declarado is not None else None
    dir_trabalho = getattr(ctx, "dir_trabalho", None)
    relatorio = _isolado.validar(
        caminho,
        perfil="dados",
        respostas=respostas,
        cota_bytes=limites.RASTER_BYTES_MAX,
        dir_trabalho=dir_trabalho,
    )
    estado = relatorio.get("estado")
    if estado == "recusado":
        problemas = relatorio.get("problemas") or ["raster recusado pela validação isolada"]
        raise RecusaValidacao("recusado", "; ".join(problemas), relatorio)
    pendencias_nao_bloqueantes: list[str] = []
    if estado == "pendente":
        pendencias = relatorio.get("pendencias") or []
        bloqueantes = [p for p in pendencias if p.get("campo") == "crs"]
        if bloqueantes:
            raise RecusaValidacao("pendente_crs", bloqueantes[0]["mensagem"], relatorio)
        pendencias_nao_bloqueantes = [p["mensagem"] for p in pendencias]

    info = relatorio.get("info") or {}
    driver = (info.get("driver") or info.get("formato") or "").upper()
    largura, altura = int(info.get("largura") or 0), int(info.get("altura") or 0)
    bandas = int(info.get("bandas") or 0)
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
    if not info.get("tipo_convertivel", True):
        raise RecusaValidacao(
            "dtype_nao_suportado",
            f"tipo de dado {info.get('tipo')!r} não suportado para conversão nesta instalação "
            "(raster complexo/64-bits fica para item próprio)",
        )

    dtype_rasterio = info.get("tipo") or ""
    dtype = _DTYPE_RASTERIO_PARA_GDAL.get(dtype_rasterio, dtype_rasterio.capitalize())

    crs = info.get("crs")
    if not crs or crs.get("epsg") is None:
        rotulo = (crs or {}).get("rotulo", "sem CRS")
        raise RecusaValidacao(
            "crs_sem_epsg",
            f"CRS sem código EPSG resolvível ({rotulo}): a ingestão exige EPSG, WKT2 puro não é aceito",
        )
    epsg = int(crs["epsg"])
    epsg_origem = "declarado" if crs.get("origem") == "informado" else "arquivo"

    geotransform = info.get("geotransform") or []
    if not geotransform or len(geotransform) != 6:
        raise RecusaValidacao(
            "sem_geotransform",
            "o raster tem CRS mas não tem geotransform (não é georreferenciado pixel a pixel): "
            "georreferencie antes de enviar",
        )

    nodata_info = info.get("nodata")
    valor_nodata = nodata_info.get("valor") if isinstance(nodata_info, dict) else None
    nodata = [valor_nodata] * bandas if bandas else []
    nodata_corrigido, avisos_nodata = _conferir_nodata(dtype, nodata)

    avisos = list(relatorio.get("avisos") or [])
    avisos.extend(avisos_nodata)
    avisos.extend(pendencias_nao_bloqueantes)
    categorico = "palette" in (info.get("colorinterp") or [])

    return RelatorioValidacao(
        driver=driver, largura=largura, altura=altura, bandas=bandas, dtype=dtype,
        epsg=epsg, epsg_origem=epsg_origem, nodata=nodata, nodata_corrigido=nodata_corrigido,
        geotransform=[float(v) for v in geotransform], wkt=(crs or {}).get("wkt2"),
        categorico=categorico, avisos=avisos, isolamento=info.get("isolamento") or {},
    )
