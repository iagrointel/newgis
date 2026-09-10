"""Perfil de elevação ao longo de uma linha (item L2-09-d; ativo da casa do L2-09-a, refeito em master).

A linha (observador → alvo em coordenadas do SRID do terreno) é cortada em `n_amostras` pontos EQUIDISTANTES
(inclusive os dois extremos) e cada ponto recebe a altura bilinear da grade. Estatísticas:

  * `ganho_m` / `perda_m` — soma só das subidas e só das descidas entre amostras consecutivas;
  * `declividade_max` — maior |Δz/Δd| entre amostras consecutivas, em GRAUS e em % (entre amostras
    equidistantes o denominador é constante, mas o valor vem do par de amostras de verdade, com a
    distância dele);
  * `z_min_m` / `z_max_m` da amostragem.

A cláusula do portão ("perfil conferido com rasterio.sample") é prova direta: nos pontos que caem no
CENTRO de célula, o bilinear da casa é exatamente o nearest do rasterio.sample, e o teste compara os
dois valor a valor.
"""

import math

from app import limites
from app.analise3d.terreno import Terreno
from app.erros import ErroAPI


def perfil(
    terreno: Terreno,
    ponto_a: tuple[float, float],
    ponto_b: tuple[float, float],
    n_amostras: int,
) -> dict:
    ax, ay = ponto_a
    bx, by = ponto_b
    terreno.exigir_dentro(ax, ay, "ponto inicial")
    terreno.exigir_dentro(bx, by, "ponto final")
    if not (2 <= n_amostras <= limites.ANALISE3D_AMOSTRAS_MAX):
        raise ErroAPI(
            422,
            "amostras_invalidas",
            f"n_amostras precisa estar entre 2 e {limites.ANALISE3D_AMOSTRAS_MAX}",
        )
    distancia = math.hypot(bx - ax, by - ay)
    if distancia <= 0:
        raise ErroAPI(422, "linha_nula", "os dois pontos da linha são o mesmo")

    amostras: list[dict] = []
    for i in range(n_amostras):
        d = distancia * i / (n_amostras - 1)
        x, y = ax + (bx - ax) * (d / distancia), ay + (by - ay) * (d / distancia)
        amostras.append({"d_m": d, "x": x, "y": y, "z_m": terreno.amostrar(x, y)})

    ganho = perda = 0.0
    decl_max_graus = 0.0
    decl_max_pct = 0.0
    decl_max_d = 0.0
    for a, b in zip(amostras, amostras[1:], strict=False):
        dz = b["z_m"] - a["z_m"]
        dd = b["d_m"] - a["d_m"]
        if dz > 0:
            ganho += dz
        else:
            perda += -dz
        if dd > 0:
            graus = math.degrees(math.atan(abs(dz) / dd))
            if graus > decl_max_graus:
                decl_max_graus, decl_max_pct, decl_max_d = graus, 100.0 * abs(dz) / dd, dd

    zs = [a["z_m"] for a in amostras]
    return {
        "distancia_m": distancia,
        "n_amostras": n_amostras,
        "amostras": amostras,
        "estatisticas": {
            "ganho_m": ganho,
            "perda_m": perda,
            "declividade_max_graus": decl_max_graus,
            "declividade_max_pct": decl_max_pct,
            "declividade_max_distancia_m": decl_max_d,
            "z_min_m": min(zs),
            "z_max_m": max(zs),
        },
    }
