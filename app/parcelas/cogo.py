"""Criação de parcela por linhas COGO (o "e2e" do portão): um trajeto de rumos e distâncias
caminha do ponto inicial, fecha o anel, mede o erro de fechamento e grava pontos, linhas,
associações e a parcela — na ordem que o modelo exige.

Rumo é AZIMUTE em graus (0 = norte = +Y, cresce para o leste, 0-360) — o mesmo contrato da
coluna `plat.parcela_linha.rumo_graus`. Arco: raio > 0 curva à direita (horário), raio < 0 à
esquerda; a GEOMETRIA gravada é a corda (o par de vértices reais do arco) — a polilinha de
arco é fase de desenho, e a paridade marca isso. O fechamento do trajeto usa os pontos de
chegada reais, então o erro de fechamento é honesto mesmo com arco.

O erro de fechamento (misclose) fica na parcela: `erro_fechamento_m` (distância entre o
último ponto do trajeto e o ponto inicial) e `erro_fechamento_razao` (perímetro / erro;
nulo quando o trajeto fecha exato). Nenhuma verificação a mais é imposta: quem cria decide
se o erro é aceitável — o número fica declarado na ficha.
"""

import math
from typing import Iterable

from app import limites
from app.erros import ErroAPI
from app.parcelas import modelo

TERRA = math.pi / 180.0


def caminhar(inicio: tuple[float, float], trajeto: Iterable[tuple]) -> dict:
    """Caminha o trajeto a partir de `inicio`. Cada passo é (rumo_graus, distancia_m) ou
    (rumo_graus, arco_m, raio_m) — raio negativo curva à esquerda. Devolve vértices (com o
    ponto inicial no fim, fechado), perímetro, erro de fechamento e razão."""
    x, y = float(inicio[0]), float(inicio[1])
    vertices = [(x, y)]
    perimetro = 0.0
    passos = list(trajeto)
    if not passos:
        raise ErroAPI(422, "valor_invalido", "trajeto precisa de pelo menos um passo")
    if len(passos) > limites.PARCELA_TRAJETO_MAX:
        raise ErroAPI(422, "regras_demais", f"o teto são {limites.PARCELA_TRAJETO_MAX} passos por parcela")
    for passo in passos:
        rumo, dist = float(passo[0]), float(passo[1])
        raio = float(passo[2]) if len(passo) > 2 else None
        if raio is None:
            dx = dist * math.sin(rumo * TERRA)
            dy = dist * math.cos(rumo * TERRA)
        else:
            # arco: o rumo é a TANGENTE inicial; o sinal do raio dá o lado (positivo curva à
            # direita). A chegada é o ponto real do arco; a geometria gravada é a corda.
            if raio == 0 or dist > 2 * math.pi * abs(raio) + 1e-9:
                raise ErroAPI(422, "valor_invalido", "comprimento de arco maior que o círculo completo")
            x, y = _arco_chegada(x, y, rumo, dist, raio)
            vertices.append((x, y))
            perimetro += dist
            continue
        x, y = x + dx, y + dy
        vertices.append((x, y))
        perimetro += dist
    vx, vy = vertices[-1]
    sx, sy = vertices[0]
    fechamento = math.hypot(vx - sx, vy - sy)
    return {
        "vertices": vertices,
        "perimetro_m": perimetro,
        "fechamento_m": fechamento,
        "razao": (perimetro / fechamento) if fechamento > 1e-9 else None,
    }


def _arco_chegada(x: float, y: float, rumo: float, arco: float, raio: float) -> tuple[float, float]:
    """Chegada de um arco circular: centro = ponto + normal à tangente na direção do raio;
    chegada = rotação do ponto inicial pelo ângulo delta em torno do centro."""
    r = abs(raio)
    delta = arco / r  # > 0
    # centro fica a |raio| do ponto, perpendicular à tangente: à direita se raio > 0
    lado = 1.0 if raio > 0 else -1.0
    tx = math.sin(rumo * TERRA)
    ty = math.cos(rumo * TERRA)
    cx = x + lado * r * ty   # normal à direita da tangente
    cy = y - lado * r * tx
    # ângulo do ponto no centro; rotação horária (raio > 0) diminui o ângulo matemático
    a0 = math.atan2(y - cy, x - cx)
    a1 = a0 - lado * delta
    return cx + r * math.cos(a1), cy + r * math.sin(a1)


def criar_parcela_cogo(cur, tenant_id: int, *, registro_id, ponto_inicial_id, codigo, tipo,
                       trajeto, precisao_xy_m=None, precisao_rumo_s=None, precisao_dist_cm=None,
                       area_declarada_m2=None, atributos=None, origem="medida") -> dict:
    """O e2e do portão: registro → trajeto COGO → pontos intermediários, linhas, associações e
    parcela, numa transação (o cursor vem de fora). O ponto inicial é REUSADO (não se cria
    outro no mesmo lugar); cada vértice novo vira ponto com a precisão declarada no argumento.
    Trajeto que NÃO fecha: o anel guarda o ponto de chegada REAL e a aresta de fechamento (do
    chegada de volta ao início) nasce SEM rumo e SEM distância — o misclose fica declarado na
    parcela e a aresta não finge ser medida (nada fecha em silêncio)."""
    resultado = caminhar(_ponto_xy_inicial(cur, ponto_inicial_id), trajeto)
    fechado = resultado["fechamento_m"] <= 1e-9
    anel = resultado["vertices"][:-1] if fechado else list(resultado["vertices"])
    ponto_ids = [str(ponto_inicial_id)]
    for vertice in anel[1:]:
        p = modelo.criar_ponto(cur, tenant_id, x=vertice[0], y=vertice[1], precisao_xy_m=precisao_xy_m,
                               origem=origem, registro_id=registro_id)
        ponto_ids.append(p["id"])
    linha_ids = []
    for i in range(len(ponto_ids)):
        de_id = ponto_ids[i]
        para_id = ponto_ids[(i + 1) % len(ponto_ids)]
        if i < len(trajeto):
            passo = trajeto[i]
            rumo = float(passo[0])
            raio = float(passo[2]) if len(passo) > 2 else None
            arco_m = float(passo[1]) if raio is not None else None
            linha = modelo.criar_linha(
                cur, tenant_id, de_ponto_id=de_id, para_ponto_id=para_id, rumo_graus=rumo,
                distancia_m=float(passo[1]), raio_m=raio,  # com sinal: positivo curva à direita
                arco_m=arco_m, tipo_cogo="arco" if raio is not None else "reta",
                precisao_rumo_s=precisao_rumo_s, precisao_dist_cm=precisao_dist_cm, origem=origem,
                registro_id=registro_id,
            )
        else:
            # aresta de fechamento do anel do misclose: não é medida, não finge ser
            linha = modelo.criar_linha(cur, tenant_id, de_ponto_id=de_id, para_ponto_id=para_id,
                                       tipo_cogo="reta", origem=origem, registro_id=registro_id)
        linha_ids.append(linha["id"])
    return modelo.criar_parcela(
        cur, tenant_id, tipo=tipo, codigo=codigo, registro_id=registro_id, anel=anel,
        area_declarada_m2=area_declarada_m2, atributos=atributos, linha_ids=linha_ids,
        erro_fechamento_m=resultado["fechamento_m"], erro_fechamento_razao=resultado["razao"],
    )


def _ponto_xy_inicial(cur, ponto_inicial_id) -> tuple[float, float]:
    cur.execute("SELECT ST_X(geom) AS x, ST_Y(geom) AS y FROM plat.parcela_ponto WHERE id = %s::uuid",
                (str(ponto_inicial_id),))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(422, "valor_invalido", f"ponto inicial {ponto_inicial_id} não existe")
    return float(r["x"]), float(r["y"])
