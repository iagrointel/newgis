"""Terreno de entrada da análise 3D: grade regular de alturas em SRID projetado (metros).

Convenções declaradas (as MESMAS de um GeoTIFF de MDT, para que o que a rota escreve em disco seja
pixel a pixel o que o cliente mandou):

  * `srid` entre 31965 e 31985 — SIRGAS 2000 UTM hemisfério sul, zonas 17S a 25S (mesma faixa da
    migração do L3-19; garante METRO como unidade, que é o que as análises assumem);
  * `x0`/`y0` são o canto SUDOESTE da grade; a célula (coluna c, linha r) cobre o quadrado
    `[x0 + c*t, x0 + (c+1)*t) × [y0 + (nlinhas-1-r)*t, y0 + (nlinhas-r)*t)` — a LINHA 0 de `alturas`
    é a do NORTE, como o primeiro registro de um GeoTIFF;
  * `amostrar(x, y)` é bilinear (o valor no vértice da grade é exatamente o valor da célula).

Proteção de RAM: a grade inteira é rejeitada antes de qualquer cálculo quando passa de
`limites.ANALISE3D_CELULAS_MAX` células (mesma disciplina da ESCALA_CELULAS_MAX do L3-19).
"""

import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import limites
from app.erros import ErroAPI

SRID_MIN = 31965
SRID_MAX = 31985


class Terreno(BaseModel):
    """Grade de alturas do terreno, em SRID projetado (metros)."""

    model_config = ConfigDict(extra="forbid")

    srid: int = Field(..., description="SIRGAS 2000 UTM sul (31965-31985): zona do terreno")
    x0: float = Field(..., description="oeste da grade, no SRID, em metros")
    y0: float = Field(..., description="sul da grade, no SRID, em metros")
    celula_m: float = Field(..., gt=0, description="lado da célula, em metros")
    alturas: list[list[float]] = Field(..., min_length=1, description="linhas de NORTE para SUL")

    @field_validator("alturas")
    @classmethod
    def _validar_grade(cls, v: list[list[float]]) -> list[list[float]]:
        ncol = len(v[0])
        if ncol < 2 or any(len(linha) != ncol for linha in v):
            raise ValueError("todas as linhas da grade têm de ter o mesmo número de colunas (>= 2)")
        if len(v) * ncol > limites.ANALISE3D_CELULAS_MAX:
            raise ValueError(
                f"grade com {len(v) * ncol} células; o teto é {limites.ANALISE3D_CELULAS_MAX}"
            )
        alt_max = limites.ANALISE3D_ALTURA_MAX_M
        if any(abs(z) > alt_max for linha in v for z in linha):
            raise ValueError(f"altura fora da faixa aceita (|z| <= {alt_max} m)")
        if any(not math.isfinite(z) for linha in v for z in linha):
            raise ValueError("alturas precisam ser números finitos (sem NaN nem infinito)")
        return v

    # ------------------------------------------------------------------ geometria da grade

    @property
    def nlinhas(self) -> int:
        return len(self.alturas)

    @property
    def ncolunas(self) -> int:
        return len(self.alturas[0])

    @property
    def x1(self) -> float:
        return self.x0 + self.ncolunas * self.celula_m

    @property
    def y1(self) -> float:
        return self.y0 + self.nlinhas * self.celula_m

    def exigir_dentro(self, x: float, y: float, nome: str) -> None:
        """Recusa ponto fora da grade (422, com o nome do ponto no erro: observador, alvo, linha)."""
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            raise ErroAPI(
                422,
                "ponto_fora_do_terreno",
                f"{nome} ({x:.1f}, {y:.1f}) está fora do terreno "
                f"({self.x0:.1f}..{self.x1:.1f}, {self.y0:.1f}..{self.y1:.1f})",
            )

    def exigir_sobre_o_terreno(self, x: float, y: float, altura_extra: float, nome: str) -> float:
        """Altura absoluta do ponto = terreno + extra; extra negativo abaixo do solo é recusado.

        É a refutação do item ('adversário põe observador abaixo do terreno'): o ponto não é
        silenciosamente tapado — a rota devolve 422 com o nome do ponto.
        """
        self.exigir_dentro(x, y, nome)
        if altura_extra < 0:
            raise ErroAPI(
                422,
                "ponto_abaixo_do_terreno",
                f"{nome} está {abs(altura_extra):.2f} m abaixo da superfície do terreno",
                {"ponto": nome, "deficit_m": abs(altura_extra)},
            )
        return self.amostrar(x, y) + altura_extra

    # ------------------------------------------------------------------ amostragem

    def amostrar(self, x: float, y: float) -> float:
        """Altura bilinear no ponto; x/y FORA da grade levanta ValueError (use `exigir_dentro` antes).

        A banda de borda (até meia célula do limite) amostra a célula do bordo: o bilinear é de CENTRO
        de célula, e o ponto no limite exato da grade é o valor da célula da borda, não erro."""
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            raise ValueError(f"({x}, {y}) fora da grade")
        # coordenada contínua na grade: colunas de oeste para leste; linhas contadas do NORTE
        fc = min(max((x - self.x0) / self.celula_m - 0.5, 0.0), float(self.ncolunas - 1))
        fr = min(max((self.y1 - y) / self.celula_m - 0.5, 0.0), float(self.nlinhas - 1))
        c0 = min(int(math.floor(fc)), self.ncolunas - 2)
        r0 = min(int(math.floor(fr)), self.nlinhas - 2)
        dc, dr = fc - c0, fr - r0
        z00 = self.alturas[r0][c0]
        z01 = self.alturas[r0][c0 + 1]
        z10 = self.alturas[r0 + 1][c0]
        z11 = self.alturas[r0 + 1][c0 + 1]
        return (z00 * (1 - dc) * (1 - dr) + z01 * dc * (1 - dr) + z10 * (1 - dc) * dr + z11 * dc * dr)

    # ------------------------------------------------------------------ GeoTIFF (gdal_viewshed e provas)

    def para_numpy(self) -> np.ndarray:
        """Matriz float32 linha 0 = norte (ordem GeoTIFF); a MESMA matriz que `escrever_geotiff` grava."""
        return np.asarray(self.alturas, dtype=np.float32)

    def escrever_geotiff(self, caminho: str | Path) -> str:
        """Grava o terreno como GeoTIFF float32 (o formato que o gdal_viewshed lê) e devolve o sha256."""
        import rasterio
        from rasterio.transform import from_origin

        dados = self.para_numpy()
        transforme = from_origin(self.x0, self.y1, self.celula_m, self.celula_m)
        with rasterio.open(
            caminho,
            "w",
            driver="GTiff",
            height=dados.shape[0],
            width=dados.shape[1],
            count=1,
            dtype="float32",
            crs=rasterio.crs.CRS.from_epsg(self.srid),
            transform=transforme,
        ) as dst:
            dst.write(dados, 1)
        return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()

    def geotiff_temporario(self):
        """Context manager: GeoTIFF do terreno num arquivo temporário (apagado ao sair)."""
        return _temp_geotiff(self)


class _temp_geotiff:
    """`with terreno.geotiff_temporario() as (caminho, sha256):` — arquivo temporário próprio por chamada."""

    def __init__(self, terreno: Terreno):
        self._terreno = terreno
        self.sha256: str = ""
        self.caminho: Path | None = None
        self._tmp: tempfile.TemporaryDirectory | None = None

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="plat-analise3d-")
        self.caminho = Path(self._tmp.name) / "terreno.tif"
        self.sha256 = self._terreno.escrever_geotiff(self.caminho)
        return self.caminho, self.sha256

    def __exit__(self, *exc):
        if self._tmp is not None:
            self._tmp.cleanup()
        return False


def sha256_da_grade(terreno: Terreno) -> str:
    """Procedência da ENTRADA: digest do JSON canônico da grade (independente de formatação do cliente)."""
    canonico = json.dumps(
        {
            "srid": terreno.srid,
            "x0": terreno.x0,
            "y0": terreno.y0,
            "celula_m": terreno.celula_m,
            "alturas": terreno.alturas,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
