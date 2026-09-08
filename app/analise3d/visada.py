"""Linha de visada (item L2-09-d): observador -> alvo amostrado no terreno.

Mecânica: o segmento observador→alvo é cortado em passos de no máximo `passo_m` metros (padrão: metade
da célula do terreno); em cada ponto t ∈ [0, 1] se calcula a altura da RETA entre a altura absoluta do
observador e a do alvo (terreno + altura extra dos dois lados) e a do TERRENO (bilinear). O primeiro
ponto em que o terreno ultrapassa a reta OBSTRUI a visada; o ponto de obstrução devolvido é o CENTRO do
passo onde isso aconteceu — por isso o erro máximo do ponto é o próprio passo declarado na resposta
(= passo_m). O veredito é booleano e a resposta carrega as amostras para conferência fora da caixa.

A cláusula do portão (ponto de obstrução a <= 30 m num morro sintético) é prova direta dessa mecânica.
"""

import math

from app.analise3d.terreno import Terreno

TERRENO_POR_SOBRE_MARGEM = 1e-9  # terreno exatamente na altura da reta não obstrui (tangência)


def linha_de_visada(
    terreno: Terreno,
    obs: tuple[float, float],
    alvo: tuple[float, float],
    altura_observador_m: float,
    altura_alvo_m: float,
    passo_m: float | None = None,
    amostras_max: int | None = None,
) -> dict:
    """Amostra a visada e devolve veredito, ponto de obstrução e as amostras (d, z_reta, z_terreno)."""
    from app import limites

    ox, oy = obs
    tx, ty = alvo
    z_obs = terreno.exigir_sobre_o_terreno(ox, oy, altura_observador_m, "observador")
    z_alvo = terreno.exigir_sobre_o_terreno(tx, ty, altura_alvo_m, "alvo")

    dx, dy = tx - ox, ty - oy
    distancia = math.hypot(dx, dy)
    if distancia <= 0:
        from app.erros import ErroAPI

        raise ErroAPI(422, "visada_nula", "observador e alvo são o mesmo ponto")

    passo = passo_m if passo_m is not None else terreno.celula_m / 2.0
    if passo <= 0:
        from app.erros import ErroAPI

        raise ErroAPI(422, "passo_invalido", "passo da amostragem precisa ser positivo")
    teto = amostras_max or limites.ANALISE3D_AMOSTRAS_MAX
    n = int(math.ceil(distancia / passo)) + 1
    if n > teto:
        from app.erros import ErroAPI

        raise ErroAPI(
            422,
            "amostras_acima_do_teto",
            f"visada com {n} amostras no passo de {passo:g} m; o teto é {teto} "
            f"(aumente o passo ou diminua a distância)",
        )

    amostras: list[dict] = []
    obstrucao: dict | None = None
    for i in range(n):
        d = min(i * passo, distancia)
        x, y = ox + dx * (d / distancia), oy + dy * (d / distancia)
        fração = d / distancia
        z_reta = z_obs + (z_alvo - z_obs) * fração
        z_terreno = terreno.amostrar(x, y)
        if obstrucao is None and z_terreno > z_reta + TERRENO_POR_SOBRE_MARGEM:
            obstrucao = {
                "x": x,
                "y": y,
                "z_terreno_m": z_terreno,
                "z_linha_m": z_reta,
                "distancia_do_observador_m": d,
                "distancia_do_alvo_m": distancia - d,
            }
        amostras.append({"d_m": d, "x": x, "y": y, "z_linha_m": z_reta, "z_terreno_m": z_terreno})

    return {
        "visivel": obstrucao is None,
        "distancia_m": distancia,
        "z_observador_m": z_obs,
        "z_alvo_m": z_alvo,
        "passo_m": passo,
        "amostras_n": len(amostras),
        "ponto_de_obstrucao": obstrucao,
        "amostras": amostras,
    }
