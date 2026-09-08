"""Posição do Sol (azimute e elevação) pelo algoritmo da calculadora solar do NOAA — item
L2-09-b-cena-extrusao-slides.

Para que serve: a cena 3D ilumina as extrusões com a luz do MapLibre (`map.setLight`), cuja posição é
dada em ângulos. Quem escolhe a data e a hora é o usuário (e o slide guarda o instante), então alguém
precisa converter "21 de dezembro, 12 h, nesta latitude" em azimute e elevação. Essa conta mora aqui,
no servidor, e não no navegador: uma implementação só, testável contra uma segunda fórmula
independente (a do Astronomical Almanac, escrita dentro do teste).

Passos, os mesmos da planilha do NOAA (General Solar Position Calculations, NOAA Global Monitoring
Laboratory): dia juliano, século juliano, longitude média, anomalia média, equação do centro,
longitude aparente, obliquidade corrigida, declinação, equação do tempo, hora solar verdadeira,
ângulo horário, zênite e azimute.

Fora de escopo, declarado: refração atmosférica (o valor devolvido é a posição GEOMÉTRICA do centro do
disco solar; perto do horizonte a posição aparente fica até cerca de 0,5° mais alta) e paralaxe. Para
iluminar uma cena, nenhuma das duas muda o que se vê.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass

JD_EPOCA_2000 = 2451545.0
DIAS_POR_SECULO = 36525.0


@dataclass(frozen=True)
class Posicao:
    azimute: float  # graus a partir do norte, no sentido horário (0 = norte, 90 = leste)
    elevacao: float  # graus acima do horizonte (negativo = abaixo)
    declinacao: float  # graus
    equacao_do_tempo_min: float  # minutos
    instante_utc: str


def dia_juliano(instante: datetime.datetime) -> float:
    """Dia juliano do instante (convertido para UTC). Fórmula de Fliegel-Van Flandern com a fração do dia."""
    t = instante.astimezone(datetime.UTC)
    a = (14 - t.month) // 12
    y = t.year + 4800 - a
    m = t.month + 12 * a - 3
    jdn = t.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    fracao = (t.hour - 12) / 24.0 + t.minute / 1440.0 + (t.second + t.microsecond / 1e6) / 86400.0
    return jdn + fracao


def posicao(latitude: float, longitude: float, instante: datetime.datetime) -> Posicao:
    """Azimute e elevação do Sol em (latitude, longitude) no instante dado (qualquer fuso; convertido
    para UTC). Latitude em graus norte-positivo, longitude em graus leste-positivo."""
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude fora de -90..90")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude fora de -180..180")
    if instante.tzinfo is None:
        raise ValueError("o instante precisa ter fuso horário (use datetime com tzinfo)")
    utc = instante.astimezone(datetime.UTC)
    jd = dia_juliano(utc)
    sec = (jd - JD_EPOCA_2000) / DIAS_POR_SECULO

    lon_media = (280.46646 + sec * (36000.76983 + sec * 0.0003032)) % 360.0
    anomalia_media = 357.52911 + sec * (35999.05029 - 0.0001537 * sec)
    excentricidade = 0.016708634 - sec * (0.000042037 + 0.0000001267 * sec)
    am = math.radians(anomalia_media)
    centro = (
        math.sin(am) * (1.914602 - sec * (0.004817 + 0.000014 * sec))
        + math.sin(2 * am) * (0.019993 - 0.000101 * sec)
        + math.sin(3 * am) * 0.000289
    )
    lon_verdadeira = lon_media + centro
    omega = math.radians(125.04 - 1934.136 * sec)
    lon_aparente = lon_verdadeira - 0.00569 - 0.00478 * math.sin(omega)

    obliquidade_media = 23.0 + (26.0 + (21.448 - sec * (46.815 + sec * (0.00059 - sec * 0.001813))) / 60.0) / 60.0
    obliquidade = math.radians(obliquidade_media + 0.00256 * math.cos(omega))

    declinacao = math.asin(math.sin(obliquidade) * math.sin(math.radians(lon_aparente)))

    # equação do tempo (minutos): diferença entre o meio-dia solar verdadeiro e o médio
    y = math.tan(obliquidade / 2.0) ** 2
    lm = math.radians(lon_media)
    eq_tempo = 4.0 * math.degrees(
        y * math.sin(2 * lm)
        - 2 * excentricidade * math.sin(am)
        + 4 * excentricidade * y * math.sin(am) * math.cos(2 * lm)
        - 0.5 * y * y * math.sin(4 * lm)
        - 1.25 * excentricidade * excentricidade * math.sin(2 * am)
    )

    minutos_utc = utc.hour * 60.0 + utc.minute + (utc.second + utc.microsecond / 1e6) / 60.0
    hora_solar = (minutos_utc + eq_tempo + 4.0 * longitude) % 1440.0
    angulo_horario = math.radians(hora_solar / 4.0 - 180.0)

    lat = math.radians(latitude)
    cos_zenite = math.sin(lat) * math.sin(declinacao) + math.cos(lat) * math.cos(declinacao) * math.cos(angulo_horario)
    zenite = math.acos(max(-1.0, min(1.0, cos_zenite)))
    elevacao = 90.0 - math.degrees(zenite)

    seno_zenite = math.sin(zenite)
    if abs(seno_zenite) < 1e-9 or abs(math.cos(lat)) < 1e-9:
        # Sol no zênite (ou observador no polo): o azimute é indeterminado; o norte é a escolha declarada
        azimute = 0.0
    else:
        cos_az = (math.sin(lat) * math.cos(zenite) - math.sin(declinacao)) / (math.cos(lat) * seno_zenite)
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        azimute = (az + 180.0) % 360.0 if angulo_horario > 0 else (540.0 - az) % 360.0

    return Posicao(
        azimute=azimute,
        elevacao=elevacao,
        declinacao=math.degrees(declinacao),
        equacao_do_tempo_min=eq_tempo,
        instante_utc=utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def luz_maplibre(p: Posicao, intensidade: float = 0.35) -> dict:
    """A luz do MapLibre no formato do estilo: `position` é [raio, azimute, ângulo polar], com o azimute
    medido a partir do norte e o polar a partir do zênite (90 − elevação). Com o Sol abaixo do horizonte
    a posição é presa ao horizonte e a intensidade cai a zero — cena noturna, sem sombra invertida."""
    abaixo = p.elevacao <= 0.0
    polar = 90.0 - max(p.elevacao, 0.0)
    return {
        "anchor": "map",
        "position": [1.5, round(p.azimute, 3), round(polar, 3)],
        "color": "#ffffff",
        "intensity": 0.0 if abaixo else max(0.0, min(1.0, intensidade)),
    }


__all__ = ["Posicao", "dia_juliano", "posicao", "luz_maplibre"]
