"""Geometria do layout (item L2-12-b-layouts-elementos-exportacao): papel, quadro de mapa e projeções.

Tudo o que aqui é número vem de uma definição declarada, para o adversário poder refutar com régua:

* **Web Mercator do MapLibre**: no zoom `z` o mundo tem `512 · 2^z` pixels (tile de 512 px). Metros por pixel
  na latitude φ: `2πR·cos φ / (512·2^z)`, R = 6.378.137 m. É a MESMA convenção que a página headless usa para
  desenhar, então a escala impressa sai da mesma conta que o desenho — não de uma aproximação paralela.
* **Escala 1:N em papel**: um quadro de `w_mm` de largura a 1:N cobre `w_mm/1000·N` metros no terreno; a
  `dpi` pixels por polegada o quadro tem `w_mm/25,4·dpi` pixels, logo metros por pixel = `N·0,0254/dpi`,
  independente da latitude. O zoom que realiza isso na latitude do centro é `log2(2πR·cos φ / (512·mpp))`.
* **UTM** (grade e norte de grade) por `pyproj`, fuso pelo centro do quadro; **convergência meridiana**
  `γ ≈ (λ − λ0)·sin φ` para a seta de norte de grade.

Nada aqui toca banco, navegador ou arquivo: é matemática pura e testável por unidade."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyproj import Transformer

R_TERRA = 6378137.0
TILE_PX = 512
POLEGADA_M = 0.0254

# papéis ISO 216 (A) e carta, em mm, no sentido retrato (largura, altura)
PAPEIS: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
    "carta": (215.9, 279.4),
}


def dimensoes_papel(papel: str, orientacao: str) -> tuple[float, float]:
    """(largura_mm, altura_mm) do papel na orientação pedida."""
    if papel not in PAPEIS:
        raise ValueError(f"papel desconhecido: {papel!r}; aceitos {sorted(PAPEIS)}")
    w, h = PAPEIS[papel]
    if orientacao == "paisagem":
        return h, w
    if orientacao == "retrato":
        return w, h
    raise ValueError(f"orientação desconhecida: {orientacao!r}")


def mm_para_px(mm: float, dpi: int) -> int:
    return max(1, round(mm / 25.4 * dpi))


def metros_por_pixel_web_mercator(lat: float, zoom: float) -> float:
    return 2 * math.pi * R_TERRA * math.cos(math.radians(lat)) / (TILE_PX * 2**zoom)


def metros_por_pixel_da_escala(escala: float, dpi: int) -> float:
    """1:N a `dpi` → metros do terreno por pixel da imagem (independe da latitude)."""
    return escala * POLEGADA_M / dpi


def zoom_da_escala(escala: float, dpi: int, lat: float) -> float:
    mpp = metros_por_pixel_da_escala(escala, dpi)
    return math.log2(2 * math.pi * R_TERRA * math.cos(math.radians(lat)) / (TILE_PX * mpp))


def escala_do_zoom(zoom: float, dpi: int, lat: float) -> float:
    """inversa de `zoom_da_escala`: N tal que a imagem a `dpi` está a 1:N na latitude do centro."""
    return metros_por_pixel_web_mercator(lat, zoom) * dpi / POLEGADA_M


def _x_mundo(lon: float, zoom: float) -> float:
    return (lon + 180.0) / 360.0 * TILE_PX * 2**zoom


def _y_mundo(lat: float, zoom: float) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    phi = math.radians(lat)
    return (1.0 - math.log(math.tan(phi) + 1.0 / math.cos(phi)) / math.pi) / 2.0 * TILE_PX * 2**zoom


def _lon_mundo(x: float, zoom: float) -> float:
    return x / (TILE_PX * 2**zoom) * 360.0 - 180.0


def _lat_mundo(y: float, zoom: float) -> float:
    n = math.pi - 2.0 * math.pi * y / (TILE_PX * 2**zoom)
    return math.degrees(math.atan(math.sinh(n)))


@dataclass(frozen=True)
class Quadro:
    """Quadro de mapa resolvido: centro, zoom e tamanho em pixels (a imagem que a página headless desenha)."""

    centro: tuple[float, float]  # lon, lat
    zoom: float
    largura_px: int
    altura_px: int
    dpi: int

    @property
    def escala(self) -> float:
        return escala_do_zoom(self.zoom, self.dpi, self.centro[1])

    def para_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """coordenada geográfica → pixel do quadro (origem no canto superior esquerdo)."""
        x = _x_mundo(lon, self.zoom) - _x_mundo(self.centro[0], self.zoom) + self.largura_px / 2.0
        y = _y_mundo(lat, self.zoom) - _y_mundo(self.centro[1], self.zoom) + self.altura_px / 2.0
        return x, y

    def para_geografica(self, x: float, y: float) -> tuple[float, float]:
        lon = _lon_mundo(x - self.largura_px / 2.0 + _x_mundo(self.centro[0], self.zoom), self.zoom)
        lat = _lat_mundo(y - self.altura_px / 2.0 + _y_mundo(self.centro[1], self.zoom), self.zoom)
        return lon, lat

    def extensao(self) -> tuple[float, float, float, float]:
        o, n = self.para_geografica(0, 0)
        le, s = self.para_geografica(self.largura_px, self.altura_px)
        return o, s, le, n


def quadro_por_escala(centro: tuple[float, float], escala: float, largura_px: int, altura_px: int, dpi: int) -> Quadro:
    return Quadro(
        centro=(float(centro[0]), float(centro[1])),
        zoom=zoom_da_escala(escala, dpi, centro[1]),
        largura_px=largura_px,
        altura_px=altura_px,
        dpi=dpi,
    )


def quadro_por_extensao(
    extensao: tuple[float, float, float, float], largura_px: int, altura_px: int, dpi: int
) -> Quadro:
    """Menor zoom em que a extensão inteira cabe no quadro (o mesmo critério do `fitBounds` sem margem)."""
    o, s, le, n = (float(v) for v in extensao)
    if not (o < le and s < n):
        raise ValueError("extensão inválida: oeste < leste e sul < norte")
    lon_c = (o + le) / 2.0
    # o centro em y é o ponto médio em Mercator, não a média das latitudes (o fitBounds faz o mesmo)
    yc = (_y_mundo(n, 0) + _y_mundo(s, 0)) / 2.0
    lat_c = _lat_mundo(yc, 0)
    dx = _x_mundo(le, 0) - _x_mundo(o, 0)
    dy = _y_mundo(s, 0) - _y_mundo(n, 0)
    zx = math.log2(largura_px / dx) if dx > 0 else 24
    zy = math.log2(altura_px / dy) if dy > 0 else 24
    zoom = max(0.0, min(zx, zy, 24.0))
    return Quadro(centro=(lon_c, lat_c), zoom=zoom, largura_px=largura_px, altura_px=altura_px, dpi=dpi)


def distancia_geodesica_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Haversine sobre a esfera de R_TERRA (a régua do teste do portão usa esta MESMA função)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_TERRA * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- barra de escala
_PASSOS_BONITOS = (1, 2, 2.5, 5)


def comprimento_bonito_m(largura_max_mm: float, escala: float) -> float:
    """Maior distância "redonda" (1, 2, 2,5 ou 5 × 10^k metros) cuja barra cabe em `largura_max_mm` a 1:N."""
    max_m = largura_max_mm / 1000.0 * escala
    if max_m <= 0:
        return 1.0
    melhor = 1.0
    exp = int(math.floor(math.log10(max_m)))
    for k in range(exp - 1, exp + 2):
        for p in _PASSOS_BONITOS:
            v = p * 10**k
            if v <= max_m and v > melhor:
                melhor = v
    return float(melhor)


def rotulo_distancia(metros: float) -> str:
    if metros >= 1000:
        km = metros / 1000.0
        texto = f"{km:.2f}".rstrip("0").rstrip(".")
        return f"{texto.replace('.', ',')} km"
    texto = f"{metros:.1f}".rstrip("0").rstrip(".")
    return f"{texto.replace('.', ',')} m"


# ---------------------------------------------------------------- UTM e convergência
def fuso_utm(lon: float, lat: float) -> tuple[int, str]:
    fuso = int(math.floor((lon + 180.0) / 6.0)) + 1
    fuso = max(1, min(60, fuso))
    return fuso, ("S" if lat < 0 else "N")


def epsg_utm(lon: float, lat: float) -> int:
    fuso, hem = fuso_utm(lon, lat)
    return (32700 if hem == "S" else 32600) + fuso


def convergencia_meridiana_graus(lon: float, lat: float) -> float:
    """γ ≈ (λ − λ0)·sin φ, em graus (positivo = norte de grade a leste do verdadeiro)."""
    fuso, _ = fuso_utm(lon, lat)
    lon0 = (fuso - 1) * 6 - 180 + 3
    return math.degrees(math.radians(lon - lon0) * math.sin(math.radians(lat)))


def transformador_utm(epsg: int) -> tuple[Transformer, Transformer]:
    """(geográfica→UTM, UTM→geográfica), sempre com eixos (lon, lat) / (E, N)."""
    ida = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    volta = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return ida, volta


def passo_bonito(intervalo: float, alvo_divisoes: int = 4) -> float:
    """passo "redondo" que divide `intervalo` em cerca de `alvo_divisoes` partes."""
    if intervalo <= 0:
        return 1.0
    bruto = intervalo / max(1, alvo_divisoes)
    exp = int(math.floor(math.log10(bruto)))
    for p in _PASSOS_BONITOS:
        v = p * 10**exp
        if v >= bruto:
            return float(v)
    return float(10 ** (exp + 1))


def passo_bonito_graus(intervalo_graus: float, alvo_divisoes: int = 4) -> float:
    """passo em graus tirado de uma lista sexagesimal (frações de grau/minuto/segundo que se leem bem)."""
    passos = (
        [1 / 3600 * k for k in (1, 2, 5, 10, 15, 30)]
        + [1 / 60 * k for k in (1, 2, 5, 10, 15, 30)]
        + [1, 2, 5, 10, 15, 30]
    )
    bruto = intervalo_graus / max(1, alvo_divisoes)
    for p in passos:
        if p >= bruto:
            return p
    return 30.0


def graus_para_gms(valor: float, eixo: str) -> str:
    """graus decimais → G°M'S" com hemisfério (eixo 'lon' → E/W, 'lat' → N/S)."""
    hem = ("E" if valor >= 0 else "W") if eixo == "lon" else ("N" if valor >= 0 else "S")
    v = abs(valor)
    g = int(v)
    m_f = (v - g) * 60
    m = int(m_f)
    s = round((m_f - m) * 60)
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        g += 1
    if s:
        return f"{g}°{m:02d}'{s:02d}\"{hem}"
    if m:
        return f"{g}°{m:02d}'{hem}"
    return f"{g}°{hem}"
