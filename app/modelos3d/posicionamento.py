"""Onde o modelo cai no globo: longitude, latitude, altura, rotação e escala.

Duas saídas, uma geodésia só:

* `matriz_ecef()` — a matriz 4x4 que o OGC 3D Tiles põe em `root.transform`: leva o sistema local do
  tile (leste, norte, cima, em metros) para o sistema geocêntrico WGS 84 (ECEF). É o que faz o tileset
  aparecer no lugar certo do planeta sem nenhum campo proprietário.
* `caixa_geografica()` — a caixa que o modelo ocupa depois de posicionado, em graus e metros. É com ela
  que a cláusula do portão compara o que o navegador desenhou (tolerância declarada em metros).

Convenção do sistema local do modelo (a mesma do glTF, Y para cima), fixada aqui e em lugar nenhum mais:
X do modelo aponta para o LESTE, Y para CIMA, -Z para o NORTE, antes da rotação. `rotacao` é o azimute em
graus, medido do norte no sentido horário (a mesma leitura de uma bússola e do `bearing` do MapLibre), e
gira o modelo em torno do eixo vertical. `escala` multiplica as três dimensões.

Elipsoide WGS 84 (EPSG:4979), que é o que 3D Tiles e o MapLibre usam. A altura é elipsoidal, não
ortométrica: a plataforma não aplica ondulação do geoide em lugar nenhum, e dizer o contrário seria
prometer precisão vertical que não existe aqui.
"""

from __future__ import annotations

import math

A = 6378137.0  # semieixo maior WGS 84, metros
F = 1.0 / 298.257223563
E2 = F * (2 - F)


def geodesico_para_ecef(lon: float, lat: float, altura: float) -> tuple[float, float, float]:
    fi, lam = math.radians(lat), math.radians(lon)
    sen_fi, cos_fi = math.sin(fi), math.cos(fi)
    n = A / math.sqrt(1 - E2 * sen_fi * sen_fi)
    return ((n + altura) * cos_fi * math.cos(lam),
            (n + altura) * cos_fi * math.sin(lam),
            (n * (1 - E2) + altura) * sen_fi)


def ecef_para_geodesico(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Inversa por iteração de Bowring; converge em poucas voltas para alturas de edificação."""
    lon = math.degrees(math.atan2(y, x))
    p = math.hypot(x, y)
    if p == 0.0:
        lat = 90.0 if z >= 0 else -90.0
        return lon, lat, abs(z) - A * (1 - F)
    fi = math.atan2(z, p * (1 - E2))
    for _ in range(8):
        sen_fi = math.sin(fi)
        n = A / math.sqrt(1 - E2 * sen_fi * sen_fi)
        altura = p / math.cos(fi) - n
        novo = math.atan2(z, p * (1 - E2 * n / (n + altura)))
        if abs(novo - fi) < 1e-14:
            fi = novo
            break
        fi = novo
    sen_fi = math.sin(fi)
    n = A / math.sqrt(1 - E2 * sen_fi * sen_fi)
    return lon, math.degrees(fi), p / math.cos(fi) - n


def base_enu(lon: float, lat: float) -> tuple[tuple, tuple, tuple]:
    """Vetores unitários leste, norte e cima no sistema geocêntrico, no ponto dado."""
    fi, lam = math.radians(lat), math.radians(lon)
    sen_fi, cos_fi, sen_lam, cos_lam = math.sin(fi), math.cos(fi), math.sin(lam), math.cos(lam)
    leste = (-sen_lam, cos_lam, 0.0)
    norte = (-sen_fi * cos_lam, -sen_fi * sen_lam, cos_fi)
    cima = (cos_fi * cos_lam, cos_fi * sen_lam, sen_fi)
    return leste, norte, cima


def matriz_ecef(lon: float, lat: float, altura: float = 0.0) -> list[float]:
    """4x4 em ordem de COLUNA (a ordem que 3D Tiles e glTF usam em `transform`/`matrix`).

    Colunas: leste, norte, cima, origem. O conteúdo do tile é Y para cima e o cliente de 3D Tiles aplica
    a troca Y-para-Z antes desta matriz (o padrão manda: glTF é Y-up, o tile é Z-up)."""
    leste, norte, cima = base_enu(lon, lat)
    o = geodesico_para_ecef(lon, lat, altura)
    return [leste[0], leste[1], leste[2], 0.0,
            norte[0], norte[1], norte[2], 0.0,
            cima[0], cima[1], cima[2], 0.0,
            o[0], o[1], o[2], 1.0]


def local_para_enu(p: tuple[float, float, float], rotacao: float = 0.0,
                   escala: float = 1.0) -> tuple[float, float, float]:
    """Ponto do modelo (X leste, Y cima, -Z norte) para metros locais (leste, norte, cima)."""
    x, y, z = p[0] * escala, p[1] * escala, p[2] * escala
    leste0, norte0 = x, -z
    a = math.radians(rotacao)
    sen, cos = math.sin(a), math.cos(a)
    # azimute horário a partir do norte: um vetor que apontava para o norte passa a apontar para `rotacao`
    return (leste0 * cos + norte0 * sen, -leste0 * sen + norte0 * cos, y)


def enu_para_geodesico(lon: float, lat: float, altura: float,
                       enu: tuple[float, float, float]) -> tuple[float, float, float]:
    leste, norte, cima = base_enu(lon, lat)
    o = geodesico_para_ecef(lon, lat, altura)
    x = o[0] + leste[0] * enu[0] + norte[0] * enu[1] + cima[0] * enu[2]
    y = o[1] + leste[1] * enu[0] + norte[1] * enu[1] + cima[1] * enu[2]
    z = o[2] + leste[2] * enu[0] + norte[2] * enu[1] + cima[2] * enu[2]
    return ecef_para_geodesico(x, y, z)


def cantos(minimo, maximo) -> list[tuple[float, float, float]]:
    return [(minimo[0] if i & 1 else maximo[0], minimo[1] if i & 2 else maximo[1],
             minimo[2] if i & 4 else maximo[2]) for i in range(8)]


def caixa_geografica(minimo, maximo, lon: float, lat: float, altura: float = 0.0,
                     rotacao: float = 0.0, escala: float = 1.0) -> dict:
    """Caixa envolvente do modelo já posicionado. `minimo`/`maximo` vêm de `glb.caixa()`.

    Devolve os limites em graus (oeste, sul, leste, norte), a faixa de altura em metros e os 8 cantos —
    os cantos são o que o teste do portão compara com o que o navegador projetou na tela."""
    pontos = [enu_para_geodesico(lon, lat, altura, local_para_enu(p, rotacao, escala))
              for p in cantos(minimo, maximo)]
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    alts = [p[2] for p in pontos]
    return {
        "oeste": min(lons), "sul": min(lats), "leste": max(lons), "norte": max(lats),
        "altura_minima": min(alts), "altura_maxima": max(alts),
        "cantos": [[round(p[0], 9), round(p[1], 9), round(p[2], 4)] for p in pontos],
    }


def distancia_m(a: tuple[float, float], b: tuple[float, float], lat_referencia: float | None = None,
                altura_m: float = 0.0) -> float:
    """Distância no plano local entre dois pares (lon, lat), em metros. Bom para as dezenas de metros de
    uma edificação; não é geodésica de longa distância e não é usado como tal em lugar nenhum.

    `altura_m` importa: a mesma diferença em graus cobre mais metros a 760 m de altitude do que ao nível
    do elipsoide (6 mm em 50 m, medido). Sem ela, a conta erra na terceira casa do metro — pouco para o
    portão de 0,5 m, e o bastante para a aritmética fechada deste módulo não fechar."""
    lat0 = math.radians(lat_referencia if lat_referencia is not None else (a[1] + b[1]) / 2)
    w = math.sqrt(1 - E2 * math.sin(lat0) ** 2)
    n = A / w + altura_m                  # raio de curvatura da grande normal (leste-oeste), na altura
    m = A * (1 - E2) / w ** 3 + altura_m  # raio de curvatura meridiana (norte-sul), na altura
    dx = math.radians(b[0] - a[0]) * n * math.cos(lat0)
    dy = math.radians(b[1] - a[1]) * m
    return math.hypot(dx, dy)


__all__ = ["geodesico_para_ecef", "ecef_para_geodesico", "base_enu", "matriz_ecef", "local_para_enu",
           "enu_para_geodesico", "caixa_geografica", "cantos", "distancia_m", "A"]
