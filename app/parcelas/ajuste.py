"""Ajuste por mínimos quadrados ponderado (weighted LSA) da malha de parcelas — item
L4-parcelas-03-ajuste-e-qualidade. Par: docs/PARIDADE_PARCELAS.md §13 (analyzeByLSA/applyLSA
da fachada ParcelFabricServer; aboutmeasurementaccuracy para as categorias de exatidão).

O que resolve: a rede de LINHAS com medida COGO (rumo_graus + distancia_m, parâmetros do item
01/02) e PONTOS, com 3+ pontos de CONTROLE fixando o datum (categoria 'controle' ou fixo=true).
Saída: coordenadas ajustadas, resíduo por linha em unidade natural e normalizado (v/sigma),
sigma zero a posteriori, precisão por ponto, e a lista de suspeitas (|v/sigma| > 3) — é daí que
a medida grosseira sai destacada (a refutação do portão).

A matemática é numpy puro: Gauss-Newton com matriz de projeto normalizada pelos sigma
(a ponderação é 1/sigma², e normalizar as linhas equivale a aplicá-la), solução por
mínimos quadrados em valor singular (a rede livre com datum fixado pelos controles é de posto
cheio quando há pelo menos 2 controles; rank deficiente resolve sem explodir).

Precisão por CATEGORIA DECLARADA (a coluna nasceu na migração 20260909T0010): a tabela abaixo
é a declaração da casa; a coluna explícita da linha/ponto (precisao_dist_cm, precisao_rumo_s,
precisao_xy_m) vence quando preenchida. Nada é inferido: quem não declara, herda a categoria.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import psycopg2

from app import limites
from app.erros import ErroAPI
from app.parcelas.modelo import SRID

RHO = 206264.80624709636          # segundos de arco por radiano
MAX_ITERACOES = 12                # teto de Gauss-Newton (a doc não publica o dela)
TOLERANCIA_PADRAO_M = 0.05        # convergenceTolerance da doc: 0,05 m por iteração
TETO_RESIDUO = 3.0                # |v/sigma| acima disso entra em 'suspeitas' (blunder)

# sigma em METROS por categoria de ponto; 'controle' é o datum da rede
CATEGORIAS_PONTO = {"controle": 0.005, "apoio": 0.05}
# (sigma_distancia_m, sigma_rumo_s) por categoria de linha
CATEGORIAS_LINHA = {"medido": (0.02, 10.0), "escritura": (0.10, 60.0), "derivado": (0.50, 300.0)}

ANALISES = ("CONSISTENCY_CHECK", "WEIGHTED_LEAST_SQUARES")


@dataclass
class _Ponto:
    id: str
    x: float
    y: float
    categoria: str
    fixo: bool
    nome: str | None
    sigma_xy: float


@dataclass
class _Linha:
    id: str
    de: str
    para: str
    distancia: float
    rumo: float
    sigma_d: float
    sigma_t: float


@dataclass
class _Rede:
    pontos: dict[str, _Ponto] = field(default_factory=dict)
    linhas: list[_Linha] = field(default_factory=list)


# ------------------------------------------------------------------ rede a partir do banco


def _coletar_rede(cur, tenant_id: int, parcela_ids: list[str]) -> _Rede:
    """Submalha das parcelas pedidas: pontos e linhas ATIVAS associadas, com medida COGO
    declarada (linha sem rumo ou sem distância não é observação — sai da rede e do relatório).
    Arco fica fora (declaração §13: o ajuste da casa é de rede retilínea)."""
    if not parcela_ids:
        raise ErroAPI(422, "valor_invalido", "selecione ao menos uma parcela (parcelFeatures)")
    if len(parcela_ids) > limites.PARCELA_ATRIBUICAO_MAX:
        raise ErroAPI(422, "parcelas_demais",
                      f"{len(parcela_ids)} parcelas numa rodada de ajuste; "
                      f"o teto é {limites.PARCELA_ATRIBUICAO_MAX}")
    rede = _Rede()
    cur.execute(
        "SELECT p.id::text AS id, ST_X(p.geom) AS x, ST_Y(p.geom) AS y, p.categoria, p.fixo, "
        "p.nome, p.precisao_xy_m FROM plat.parcela_ponto p "
        "JOIN plat.parcela_linha l ON p.id = l.de_ponto_id OR p.id = l.para_ponto_id "
        "JOIN plat.parcela_linha_parcela u ON u.linha_id = l.id "
        "WHERE u.parcela_id = ANY(%s::uuid[]) AND l.ativa AND p.tenant_id = %s "
        "GROUP BY p.id",
        (parcela_ids, tenant_id),
    )
    for r in cur.fetchall():
        categoria = r["categoria"]
        if categoria not in CATEGORIAS_PONTO:
            raise ErroAPI(422, "categoria_desconhecida",
                          f"ponto {r['id']} com categoria '{categoria}' sem sigma declarado")
        rede.pontos[str(r["id"])] = _Ponto(
            id=str(r["id"]), x=float(r["x"]), y=float(r["y"]), categoria=categoria,
            fixo=bool(r["fixo"]) or categoria == "controle", nome=r["nome"],
            sigma_xy=float(r["precisao_xy_m"]) if r["precisao_xy_m"] is not None
            else CATEGORIAS_PONTO[categoria],
        )
    cur.execute(
        "SELECT DISTINCT l.id::text AS id, l.de_ponto_id::text AS de, l.para_ponto_id::text AS para, "
        "l.distancia_m, l.rumo_graus, l.categoria, l.precisao_dist_cm, l.precisao_rumo_s "
        "FROM plat.parcela_linha l JOIN plat.parcela_linha_parcela u ON u.linha_id = l.id "
        "WHERE u.parcela_id = ANY(%s::uuid[]) AND l.ativa AND l.tipo_cogo = 'reta' "
        "AND l.rumo_graus IS NOT NULL AND l.distancia_m IS NOT NULL AND l.tenant_id = %s",
        (parcela_ids, tenant_id),
    )
    for r in cur.fetchall():
        categoria = r["categoria"]
        if categoria not in CATEGORIAS_LINHA:
            raise ErroAPI(422, "categoria_desconhecida",
                          f"linha {r['id']} com categoria '{categoria}' sem sigma declarado")
        rede.linhas.append(_Linha(
            id=str(r["id"]), de=r["de"], para=r["para"], distancia=float(r["distancia_m"]),
            rumo=float(r["rumo_graus"]),
            sigma_d=float(r["precisao_dist_cm"]) / 100.0 if r["precisao_dist_cm"] is not None
            else CATEGORIAS_LINHA[categoria][0],
            sigma_t=float(r["precisao_rumo_s"]) if r["precisao_rumo_s"] is not None
            else CATEGORIAS_LINHA[categoria][1],
        ))
    if not rede.linhas:
        raise ErroAPI(422, "rede_sem_observacoes",
                      "a seleção não tem nenhuma linha com rumo e distância declarados: nada a ajustar")
    if len(rede.linhas) > limites.PARCELA_AJUSTE_LINHAS_MAX:
        raise ErroAPI(422, "linhas_demais",
                      f"{len(rede.linhas)} linhas na rede; o teto é {limites.PARCELA_AJUSTE_LINHAS_MAX}")
    return rede


# ------------------------------------------------------------------ mínimos quadrados


def _rumo_graus(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _resolver(rede: _Rede, tolerancia_m: float, sem_linhas: frozenset[str]) -> dict:
    """Gauss-Newton sobre a rede; devolve o relatório (nada escreve). A exclusão declarada
    (sem_linhas) tira a medida DA RODADA — a casa não apaga medida, a refutação usa isto."""
    observadas = [ln for ln in rede.linhas if ln.id not in sem_linhas]
    usados = {p for ln in observadas for p in (ln.de, ln.para)}
    incognitas = [p.id for p in rede.pontos.values() if not p.fixo and p.id in usados]
    indice = {pid: i for i, pid in enumerate(incognitas)}
    u = 2 * len(incognitas)
    n = 2 * len(observadas)
    redundancia = n - u
    if redundancia <= 0:
        raise ErroAPI(422, "rede_sem_redundancia",
                      f"a rede tem {n} observações e {u} incógnitas: sem sobra para avaliar resíduo "
                      "(faltam pontos de controle ou medidas)")
    xy = {pid: (p.x, p.y) for pid, p in rede.pontos.items()}  # o ajuste acontece AQUI, na memória

    iteracoes = 0
    maior = 0.0
    for _ in range(MAX_ITERACOES):
        iteracoes += 1
        a = np.zeros((n, u))
        b = np.zeros(n)
        for k, ln in enumerate(observadas):
            (x1, y1), (x2, y2) = xy[ln.de], xy[ln.para]
            dx, dy = x2 - x1, y2 - y1
            d = math.hypot(dx, dy)
            if d <= 0.0:
                raise ErroAPI(422, "valor_invalido", f"linha {ln.id} tem os dois pontos no mesmo lugar")
            # observação de DISTÂNCIA (d = |p2 - p1|: as derivadas em relação ao PONTO 1
            # carregam o sinal trocado em relação ao ponto 2)
            a[k, :] = 0.0
            # o vetor de parâmetros é [x0, y0, x1, y1, ...]: o ponto j ocupa as
            # colunas 2j e 2j + 1 (o mesmo mapa do passo de atualização abaixo);
            # a linha INTEIRA é normalizada pelo sigma (o b abaixo também é) —
            # sem isso o sistema linearizado mistura unidade e o passo explode
            if ln.de in indice:
                i = 2 * indice[ln.de]
                a[k, i] = -dx / d / ln.sigma_d
                a[k, i + 1] = -dy / d / ln.sigma_d
            if ln.para in indice:
                j = 2 * indice[ln.para]
                a[k, j] = dx / d / ln.sigma_d
                a[k, j + 1] = dy / d / ln.sigma_d
            b[k] = (ln.distancia - d) / ln.sigma_d
            # observação de RUMO (de norte, horário): theta = atan2(dx, dy)
            dk2 = d * d
            t_calc = _rumo_graus(dx, dy)
            dif = (ln.rumo - t_calc + 180.0) % 360.0 - 180.0  # embrulho de círculo
            a[n // 2 + k, :] = 0.0
            if ln.de in indice:
                i = 2 * indice[ln.de]
                a[n // 2 + k, i] = -(dy / dk2) * RHO / ln.sigma_t
                a[n // 2 + k, i + 1] = (dx / dk2) * RHO / ln.sigma_t
            if ln.para in indice:
                j = 2 * indice[ln.para]
                a[n // 2 + k, j] = (dy / dk2) * RHO / ln.sigma_t
                a[n // 2 + k, j + 1] = -(dx / dk2) * RHO / ln.sigma_t
            b[n // 2 + k] = dif * 3600.0 / ln.sigma_t
        passo, *_ = np.linalg.lstsq(a, b, rcond=None)
        maior = 0.0
        for pid, i in indice.items():
            x, y = xy[pid]
            xy[pid] = (x + float(passo[2 * i]), y + float(passo[2 * i + 1]))
            maior = max(maior, abs(float(passo[2 * i])), abs(float(passo[2 * i + 1])))
        if maior < tolerancia_m:
            break
    convergiu = maior < tolerancia_m

    # resíduos FINAIS nas unidades naturais (não os do último passo linearizado)
    linhas_rel = []
    soma_v2 = 0.0
    for ln in observadas:
        (x1, y1), (x2, y2) = xy[ln.de], xy[ln.para]
        d_calc = math.hypot(x2 - x1, y2 - y1)
        t_calc = _rumo_graus(x2 - x1, y2 - y1)
        v_d = ln.distancia - d_calc
        v_t = ((ln.rumo - t_calc + 180.0) % 360.0 - 180.0) * 3600.0
        norm = max(abs(v_d) / ln.sigma_d, abs(v_t) / ln.sigma_t)
        soma_v2 += (v_d / ln.sigma_d) ** 2 + (v_t / ln.sigma_t) ** 2
        linhas_rel.append({"id": ln.id, "de": ln.de, "para": ln.para,
                           "residuo_distancia_m": round(v_d, 6), "residuo_rumo_s": round(v_t, 4),
                           "sigma_distancia_m": ln.sigma_d, "sigma_rumo_s": ln.sigma_t,
                           "normalizado": round(norm, 3)})
    sigma0 = math.sqrt(soma_v2 / redundancia)
    # cofatores a posteriori: Q = (AᵀA)⁻¹ do ÚLTIMO sistema; precisão escalar por ponto
    q = np.linalg.pinv(a.T @ a)
    pontos_rel = []
    deslocamentos = []
    for pid, p in rede.pontos.items():
        x0, y0 = p.x, p.y
        x1, y1 = xy[pid]
        desloc = math.hypot(x1 - x0, y1 - y0)
        if p.fixo or pid not in indice:
            precisao = p.sigma_xy if p.fixo else None
        else:
            i = indice[pid]
            precisao = round(sigma0 * math.sqrt(float(q[2 * i, 2 * i]) + float(q[2 * i + 1, 2 * i + 1])), 6)
        pontos_rel.append({"id": pid, "nome": p.nome, "categoria": p.categoria, "fixo": p.fixo,
                           "x_anterior": round(x0, 6), "y_anterior": round(y0, 6),
                           "x": round(x1, 6), "y": round(y1, 6),
                           "deslocamento_m": round(desloc, 6), "precisao_xy_m": precisao})
        if not p.fixo and pid in usados:
            deslocamentos.append(desloc)
    ordenadas = sorted(linhas_rel, key=lambda r: r["normalizado"], reverse=True)
    relatorio = {
        "convergiu": convergiu, "iteracoes": iteracoes,
        "tolerancia_convergencia_m": tolerancia_m,
        "sigma_zero": round(sigma0, 6), "redundancia": redundancia,
        "observacoes": n, "incognitas": u,
        "linhas_excluidas": sorted(sem_linhas),
        "deslocamento_maximo_m": round(max(deslocamentos), 6) if deslocamentos else 0.0,
        "maior_residuo": {"linha_id": ordenadas[0]["id"], "normalizado": ordenadas[0]["normalizado"],
                          "residuo_distancia_m": ordenadas[0]["residuo_distancia_m"],
                          "residuo_rumo_s": ordenadas[0]["residuo_rumo_s"]},
        "suspeitas": [r["id"] for r in ordenadas if r["normalizado"] > TETO_RESIDUO],
        "pontos": pontos_rel, "linhas": ordenadas,
    }
    return relatorio


def _validar_analysis(analysis_type: str) -> None:
    if analysis_type not in ANALISES:
        raise ErroAPI(422, "valor_invalido",
                      f"analysisType precisa ser uma de: {', '.join(ANALISES)}")


# ------------------------------------------------------------------ operações


def analisar(cur, tenant_id: int, *, parcela_ids: list[str], analysis_type="WEIGHTED_LEAST_SQUARES",
             tolerancia_m: float = TOLERANCIA_PADRAO_M, sem_linhas=()) -> dict:
    """Análise (analyzeByLSA): resolve e devolve o relatório. NADA escreve — nem coordenada,
    nem precisão; o checksum da malha no teste é a prova."""
    _validar_analysis(analysis_type)
    if not 0 < tolerancia_m <= 10.0:
        raise ErroAPI(422, "valor_invalido", "convergenceTolerance precisa estar em (0, 10] metros")
    if len(sem_linhas) > limites.PARCELA_AJUSTE_LINHAS_MAX:
        raise ErroAPI(422, "linhas_demais", "exclusão demais para uma rodada")
    rede = _coletar_rede(cur, tenant_id, parcela_ids)
    return _resolver(rede, tolerancia_m, frozenset(sem_linhas))


def aplicar(cur, tenant_id: int, *, parcela_ids: list[str], tolerancia_movimento_m: float = 0.05,
            atualizar_atributos: bool = True, tolerancia_m: float = TOLERANCIA_PADRAO_M,
            sem_linhas=()) -> dict:
    """Aplicação (applyLSA): resolve, MOVE os pontos (deslocamento > movementTolerance, a regra
    da doc), propaga para a geometria de linha e de parcela e GRAVA A VERSÃO em
    plat.parcela_ajuste (o relatório integral é o antes; append-only)."""
    _validar_analysis("WEIGHTED_LEAST_SQUARES")  # aplicar é sempre ponderado; CONSISTENCY é só análise
    if not 0 <= tolerancia_movimento_m <= 10.0:
        raise ErroAPI(422, "valor_invalido", "movementTolerance precisa estar em [0, 10] metros")
    rede = _coletar_rede(cur, tenant_id, parcela_ids)
    relatorio = _resolver(rede, tolerancia_m, frozenset(sem_linhas))
    if not relatorio["convergiu"]:
        raise ErroAPI(422, "ajuste_nao_convergiu",
                      f"o ajuste não convergiu em {MAX_ITERACOES} iterações; nada foi escrito")
    movidos = [p for p in relatorio["pontos"] if not p["fixo"] and p["deslocamento_m"] > tolerancia_movimento_m]
    for p in movidos:
        cur.execute(
            "UPDATE plat.parcela_ponto SET geom = ST_SetSRID(ST_MakePoint(%s,%s),%s), "
            "precisao_xy_m = COALESCE(%s, precisao_xy_m), atualizado_em = now() WHERE id = %s::uuid",
            (p["x"], p["y"], SRID, p["precisao_xy_m"] if atualizar_atributos else None, p["id"]),
        )
    ids_parcelas = [str(i) for i in parcela_ids]
    if movidos:
        # a geometria da LINHA é sempre os dois pontos (invariante do modelo, item 01)
        cur.execute(
            "UPDATE plat.parcela_linha l SET geom = ST_SetSRID(ST_MakeLine(p1.geom, p2.geom),%s) "
            "FROM plat.parcela_ponto p1, plat.parcela_ponto p2 "
            "WHERE l.de_ponto_id = p1.id AND l.para_ponto_id = p2.id "
            "AND (p1.id = ANY(%s::uuid[]) OR p2.id = ANY(%s::uuid[]))",
            (SRID, [p["id"] for p in movidos], [p["id"] for p in movidos]),
        )
        # a face da parcela volta a fechar pelas linhas dela (o mesmo polygonize do build);
        # anel aberto não tem face: a geometria anterior fica, e o relatório diz quais
        cur.execute(
            "SELECT p.id::text AS id, ST_AsText(f.g) AS wkt FROM plat.parcela p "
            "CROSS JOIN LATERAL (SELECT ST_UnaryUnion(ST_Collect(l.geom)) AS g "
            "  FROM plat.parcela_linha_parcela u JOIN plat.parcela_linha l ON l.id = u.linha_id "
            "  WHERE u.parcela_id = p.id AND l.ativa) linhas, "
            "LATERAL (SELECT (ST_Dump(ST_Polygonize(linhas.g))).geom AS g) f "
            "WHERE p.id = ANY(%s::uuid[]) AND ST_GeometryType(f.g) = 'ST_Polygon'",
            (ids_parcelas,),
        )
        faces = {r["id"]: r["wkt"] for r in cur.fetchall()}
        for pid in ids_parcelas:
            if pid in faces:
                cur.execute(
                    "UPDATE plat.parcela SET geom = ST_GeomFromText(%s,%s), "
                    "area_calculada_m2 = ST_Area(geom), atualizado_em = now() WHERE id = %s::uuid",
                    (faces[pid], SRID, pid),
                )
    cur.execute(
        "INSERT INTO plat.parcela_ajuste(tenant_id, analise, sigma_zero, iteracoes, redundancia, "
        "deslocamento_maximo_m, pontos_ajustados, linhas_observadas) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (tenant_id, psycopg2.extras.Json(relatorio), relatorio["sigma_zero"],
         relatorio["iteracoes"], relatorio["redundancia"],
         relatorio["deslocamento_maximo_m"], len(movidos), len(relatorio["linhas"])),
    )
    ajuste_id = str(cur.fetchone()["id"])
    return {"id": ajuste_id, "relatorio": relatorio, "movidos": movidos,
            "sem_face": [pid for pid in ids_parcelas if pid not in faces] if movidos else []}
