"""Posição solar (algoritmo NOAA) para a análise de sombra.

APROXIMAÇÃO DECLARADA (repetida na resposta de cada sombra): o algoritmo é o da NOAA Global Monitoring
Laboratory / formulação de Meeus — declinação aparente e equação do tempo pela série de baixa precisão
(exatidão declarada da fonte: 0,01° em posição, que é 0,2 % de comprimento de sombra a 45°). A refração
atmosférica é aplicada pela fórmula padrão da NOAA (só tem efeito perto do horizonte, < 1°) e a paralaxe
do Sol é ignorada. Terra plana na escala da análise: o prisma é vertical e a superfície é plana no SRID
da análise (relevo não curva a sombra — quem modela sombra sobre relevo é a família raster/L2-09).

Retorno: azimute (0-360°, do norte, sentido horário) e elevação (graus acima do horizonte).
"""

import datetime
import math


def _rad(graus: float) -> float:
    return graus * math.pi / 180.0


def _graus(rad: float) -> float:
    return rad * 180.0 / math.pi


def dia_juliano(quando: datetime.datetime) -> float:
    """Dia juliano (século juliano após J2000.0 sai na divisão por 36525)."""
    return quando.timestamp() / 86400.0 + 2440587.5


def posicao_solar(quando_utc: datetime.datetime, lat_graus: float, lon_graus: float) -> dict:
    """Azimute e elevação do Sol no instante UTC, para o ponto (lat, lon) em graus."""
    quando = quando_utc if quando_utc.tzinfo else quando_utc.replace(tzinfo=datetime.UTC)
    jd = dia_juliano(quando)
    t = (jd - 2451545.0) / 36525.0

    # geometria da órbita (NOAA solar calculator, equações de Meeus de baixa precisão)
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m_rad = _rad(m)
    # equação do centro: os coeficientes já estão em GRAUS na formulação de Meeus — o produto é graus,
    # sem conversão (embrulhar em graus de novo era o defeito que dava declinação 2° errada)
    c = (
        math.sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * m_rad) * (0.019993 - 0.000101 * t)
        + math.sin(3 * m_rad) * 0.000289
    )
    verdadeira = l0 + c
    aparente = verdadeira - 0.00569 - 0.00478 * math.sin(_rad(125.04 - 1934.136 * t))

    # obliquidade média corrigida (u = séculos julianos desde J2000.0, o mesmo `t`)
    u = t
    eps0 = (
        23.0 + (26.0 + ((21.448 - u * (46.8150 + u * (0.00059 - u * 0.001813)))) / 60.0) / 60.0
    )
    eps = eps0 + 0.00256 * math.cos(_rad(125.04 - 1934.136 * t))

    declinacao = _graus(math.asin(math.sin(_rad(eps)) * math.sin(_rad(aparente))))

    # equação do tempo (minutos)
    y = math.tan(_rad(eps / 2.0)) ** 2
    l0_rad = _rad(l0)
    eq_tempo = 4.0 * _graus(
        y * math.sin(2 * l0_rad)
        - 2 * e * math.sin(m_rad)
        + 4 * e * y * math.sin(m_rad) * math.cos(2 * l0_rad)
        - 0.5 * y * y * math.sin(4 * l0_rad)
        - 1.25 * e * e * math.sin(2 * m_rad)
    )

    # hora verdadeira local: a UTC + longitude/15 (min) + equação do tempo
    utc_min = quando.hour * 60.0 + quando.minute + quando.second / 60.0 + quando.microsecond / 6e7
    hora_verdadeira_min = utc_min + eq_tempo + 4.0 * lon_graus
    angulo_horario = _rad(hora_verdadeira_min / 4.0 - 180.0)  # graus -> ângulo (0 = meio-dia solar)

    lat_rad = _rad(lat_graus)
    dec_rad = _rad(declinacao)
    cos_zenite = (
        math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(angulo_horario)
    )
    cos_zenite = max(-1.0, min(1.0, cos_zenite))
    zenite = math.acos(cos_zenite)
    elevacao = 90.0 - _graus(zenite)

    # refração atmosférica (Saemundsson, a usada pela NOAA; em arcmin -> graus; zero acima de 85°,
    # que é o caso das sombras do meio-dia: sem efeito medido no portão do item)
    if elevacao > 85.0:
        refracao = 0.0
    else:
        e = max(elevacao, -1.0)  # abaixo do horizonte a fórmula continua finita
        refracao = (1.02 / math.tan(_rad(e + 10.3 / (e + 5.11)))) / 60.0
    elevacao_corrigida = elevacao + refracao

    # azimute do norte, sentido horário (fórmula NOAA)
    cos_az = (math.sin(lat_rad) * cos_zenite - math.sin(dec_rad)) / (
        math.cos(lat_rad) * math.sin(zenite)
    ) if math.sin(zenite) != 0 else 1.0
    cos_az = max(-1.0, min(1.0, cos_az))
    azimute = _graus(math.acos(cos_az))
    if angulo_horario > 0.0:
        azimute = (azimute + 180.0) % 360.0
    else:
        azimute = (540.0 - azimute) % 360.0

    return {
        "azimute_graus": azimute,
        "elevacao_graus": elevacao_corrigida,
        "declinacao_graus": declinacao,
        "equacao_do_tempo_min": eq_tempo,
    }
