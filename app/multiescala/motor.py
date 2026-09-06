"""Motor das grades aninhadas (item L3-19-multiescala).

Duas execuções ligadas:

  1. MACRO — grade de resolução grossa (ex.: 1 km) sobre a área de estudo inteira; toda célula é calculada;
     a regra de aprovação (limiar de nota ou percentual do topo) escolhe as REGIÕES que seguem para o micro.
  2. MICRO — grade de resolução fina (ex.: 100 m) gerada SÓ dentro das células macro aprovadas. A célula micro
     fora dessas regiões não é gerada nem calculada: as duas grades compartilham origem e CRS, e a resolução
     macro é múltiplo inteiro k da micro, então a célula macro (col, lin) contém exatamente as micro
     (col*k + dx, lin*k + dy) com 0 <= dx, dy < k. O recorte é aritmético — não existe um passo que produza a
     célula de fora e depois a descarte.

Custo por ESCALA, não por célula (regra do motor de LT): o valor de um fator é agregado por BLOCO na resolução
NATIVA declarada da fonte (`plat.escala_bloco`) e reaproveitado por todas as células que caem no mesmo bloco.
Um fator de 1 km numa grade de 100 m custa uma agregação por quilômetro quadrado, não uma por célula de 100 m;
o relatório publica `blocos_usados` ao lado de `celulas` para que isso seja conferível.

Escala declarada: `escala_grosseira` é CALCULADO aqui (resolucao_fonte_m > resolucao_grade_m), nunca recebido do
cliente. É a refutação do item: quem usar um fator de 1 km numa grade de 100 m recebe o fator marcado como
'grosseira' no relatório, queira ou não.

Combinação: nota = Σ(peso × favorabilidade) / Σ(peso) sobre os fatores COM dado na célula (decisão A5 do
L3L6_CONCEITO: ausente é excluído e a cobertura é gravada, nunca COALESCE(...,0)). Favorabilidade 0-100 em
ponto flutuante, NULL para ausente (decisão A3).
"""

import json
import math
import time
from dataclasses import dataclass

from app import limites
from app.erros import ErroAPI
from app.multiescala import crs as crs_mod


@dataclass(frozen=True)
class FatorPedido:
    fator_id: str
    peso: float


def _um(cur, sql: str, params) -> dict:
    cur.execute(sql, params)
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "nao_encontrado", "registro inexistente")
    return r


# ------------------------------------------------------------------ área de estudo


def criar_conjunto(cur, tenant_id: int, usuario_id: int, nome: str, area: dict) -> dict:
    """Grava a área de estudo, resolve o CRS de trabalho pelo centróide e mede a extensão em metros."""
    geojson = json.dumps(area, ensure_ascii=False)
    cur.execute(
        "SELECT ST_X(c) AS lon, ST_Y(c) AS lat, ST_NPoints(g) AS n FROM ("
        "  SELECT g, ST_Centroid(g) AS c FROM (SELECT ST_GeomFromGeoJSON(%s) AS g) q0"
        ") q",
        (geojson,),
    )
    r = cur.fetchone()
    if r is None or r["lon"] is None:
        raise ErroAPI(422, "area_invalida", "a área de estudo não é um polígono GeoJSON válido")
    if r["n"] > limites.ESCALA_AREA_VERTICES_MAX:
        raise ErroAPI(
            422, "area_com_vertices_demais",
            f"a área tem {r['n']} vértices; o teto é {limites.ESCALA_AREA_VERTICES_MAX}",
        )
    srid = crs_mod.srid_de(float(r["lon"]), float(r["lat"]))
    cur.execute(
        "SELECT ST_XMin(g) AS x0, ST_YMin(g) AS y0, ST_XMax(g) AS x1, ST_YMax(g) AS y1 "
        "FROM (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s) AS g) q",
        (geojson, srid),
    )
    e = cur.fetchone()
    largura, altura = float(e["x1"]) - float(e["x0"]), float(e["y1"]) - float(e["y0"])
    if largura <= 0 or altura <= 0:
        raise ErroAPI(422, "area_degenerada", "a área de estudo não tem extensão em metros")
    cur.execute(
        "INSERT INTO plat.escala_conjunto(tenant_id, nome, srid_trabalho, area, origem_x_m, origem_y_m, "
        "largura_m, altura_m, dono_id) "
        "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, %s, %s) "
        "RETURNING id, nome, srid_trabalho, origem_x_m, origem_y_m, largura_m, altura_m, criado_em",
        (tenant_id, nome, srid, geojson, float(e["x0"]), float(e["y0"]), largura, altura, usuario_id),
    )
    return cur.fetchone()


# ------------------------------------------------------------------ grades


def _conferir_resolucao(resolucao_m: float) -> None:
    if not limites.ESCALA_RESOLUCAO_MIN_M <= resolucao_m <= limites.ESCALA_RESOLUCAO_MAX_M:
        raise ErroAPI(
            422, "resolucao_fora_da_faixa",
            f"resolução de {resolucao_m} m fora da faixa "
            f"{limites.ESCALA_RESOLUCAO_MIN_M}–{limites.ESCALA_RESOLUCAO_MAX_M} m",
        )


def gerar_grade_macro(cur, tenant_id: int, conjunto: dict, resolucao_m: float) -> dict:
    """Grade macro sobre a área inteira. Conta as células ANTES de materializar (nx × ny) e recusa acima do teto."""
    _conferir_resolucao(resolucao_m)
    nx = max(1, math.ceil(float(conjunto["largura_m"]) / resolucao_m))
    ny = max(1, math.ceil(float(conjunto["altura_m"]) / resolucao_m))
    possiveis = nx * ny
    if possiveis > limites.ESCALA_CELULAS_MAX:
        raise ErroAPI(
            422, "grade_grande_demais",
            f"a grade de {resolucao_m} m teria {possiveis} células ({nx}×{ny}); o teto é "
            f"{limites.ESCALA_CELULAS_MAX}. Aumente a resolução ou reduza a área.",
            {"celulas_estimadas": possiveis, "colunas": nx, "linhas": ny},
        )
    cur.execute(
        "INSERT INTO plat.escala_grade(tenant_id, conjunto_id, nivel, resolucao_m, colunas, linhas, "
        "celulas_possiveis) VALUES (%s, %s::uuid, 'macro', %s, %s, %s, %s) RETURNING id",
        (tenant_id, str(conjunto["id"]), resolucao_m, nx, ny, possiveis),
    )
    grade_id = str(cur.fetchone()["id"])
    x0, y0, srid = float(conjunto["origem_x_m"]), float(conjunto["origem_y_m"]), int(conjunto["srid_trabalho"])
    cur.execute(
        "INSERT INTO plat.escala_celula(tenant_id, grade_id, col, lin, centro_x_m, centro_y_m, geom) "
        "SELECT %(t)s, %(g)s::uuid, c.col, c.lin, "
        "       %(x0)s + (c.col + 0.5) * %(r)s, %(y0)s + (c.lin + 0.5) * %(r)s, "
        "       ST_Transform(c.env, 4326) "
        "FROM ("
        "  SELECT col, lin, ST_MakeEnvelope(%(x0)s + col * %(r)s, %(y0)s + lin * %(r)s, "
        "                                   %(x0)s + (col + 1) * %(r)s, %(y0)s + (lin + 1) * %(r)s, "
        "                                   %(srid)s) AS env "
        "  FROM generate_series(0, %(nx)s - 1) AS col, generate_series(0, %(ny)s - 1) AS lin"
        ") c "
        "WHERE ST_Intersects(c.env, (SELECT ST_Transform(area, %(srid)s) FROM plat.escala_conjunto "
        "                            WHERE id = %(cj)s::uuid))",
        {"t": tenant_id, "g": grade_id, "x0": x0, "y0": y0, "r": resolucao_m, "srid": srid,
         "nx": nx, "ny": ny, "cj": str(conjunto["id"])},
    )
    celulas = cur.rowcount
    cur.execute("UPDATE plat.escala_grade SET celulas = %s WHERE id = %s::uuid", (celulas, grade_id))
    return _um(cur, "SELECT * FROM plat.escala_grade WHERE id = %s::uuid", (grade_id,))


def gerar_grade_micro(cur, tenant_id: int, conjunto: dict, macro: dict, execucao_pai_id: str,
                      resolucao_m: float) -> dict:
    """Grade micro DENTRO das células macro aprovadas. k = resolução macro / micro tem de ser inteiro >= 2."""
    _conferir_resolucao(resolucao_m)
    res_macro = float(macro["resolucao_m"])
    k_exato = res_macro / resolucao_m
    k = round(k_exato)
    if k < 2 or abs(k_exato - k) > 1e-9:
        raise ErroAPI(
            422, "aninhamento_nao_inteiro",
            f"a resolução macro ({res_macro:g} m) precisa ser múltiplo inteiro >= 2 da micro "
            f"({resolucao_m:g} m); a razão pedida é {k_exato:g}",
            {"razao": k_exato},
        )
    cur.execute(
        "SELECT count(*) AS n FROM plat.escala_resultado WHERE execucao_id = %s::uuid AND aprovada",
        (execucao_pai_id,),
    )
    aprovadas = cur.fetchone()["n"]
    if aprovadas == 0:
        raise ErroAPI(
            422, "macro_sem_regiao_aprovada",
            "a execução macro não aprovou nenhuma região; não há onde refinar",
        )
    geradas = aprovadas * k * k
    possiveis = int(macro["celulas"]) * k * k
    if geradas > limites.ESCALA_CELULAS_MAX:
        raise ErroAPI(
            422, "grade_grande_demais",
            f"refinar {aprovadas} regiões macro a {resolucao_m:g} m daria {geradas} células; o teto é "
            f"{limites.ESCALA_CELULAS_MAX}. Aperte a regra de aprovação ou use resolução maior.",
            {"celulas_estimadas": geradas, "regioes_aprovadas": aprovadas, "fator_aninhamento": k},
        )
    cur.execute(
        "INSERT INTO plat.escala_grade(tenant_id, conjunto_id, nivel, resolucao_m, grade_pai_id, "
        "fator_aninhamento, colunas, linhas, celulas_possiveis) "
        "VALUES (%s, %s::uuid, 'micro', %s, %s::uuid, %s, %s, %s, %s) RETURNING id",
        (tenant_id, str(conjunto["id"]), resolucao_m, str(macro["id"]), k,
         int(macro["colunas"]) * k, int(macro["linhas"]) * k, possiveis),
    )
    grade_id = str(cur.fetchone()["id"])
    x0, y0, srid = float(conjunto["origem_x_m"]), float(conjunto["origem_y_m"]), int(conjunto["srid_trabalho"])
    cur.execute(
        "INSERT INTO plat.escala_celula(tenant_id, grade_id, col, lin, centro_x_m, centro_y_m, geom) "
        "SELECT %(t)s, %(g)s::uuid, mc.col * %(k)s + dx, mc.lin * %(k)s + dy, "
        "       %(x0)s + (mc.col * %(k)s + dx + 0.5) * %(r)s, %(y0)s + (mc.lin * %(k)s + dy + 0.5) * %(r)s, "
        "       ST_Transform(ST_MakeEnvelope("
        "         %(x0)s + (mc.col * %(k)s + dx) * %(r)s, %(y0)s + (mc.lin * %(k)s + dy) * %(r)s, "
        "         %(x0)s + (mc.col * %(k)s + dx + 1) * %(r)s, %(y0)s + (mc.lin * %(k)s + dy + 1) * %(r)s, "
        "         %(srid)s), 4326) "
        "FROM plat.escala_celula mc "
        "JOIN plat.escala_resultado res ON res.celula_id = mc.id AND res.execucao_id = %(pai)s::uuid "
        "                              AND res.aprovada "
        "CROSS JOIN generate_series(0, %(k)s - 1) AS dx "
        "CROSS JOIN generate_series(0, %(k)s - 1) AS dy "
        "WHERE mc.grade_id = %(gm)s::uuid",
        {"t": tenant_id, "g": grade_id, "k": k, "x0": x0, "y0": y0, "r": resolucao_m, "srid": srid,
         "pai": execucao_pai_id, "gm": str(macro["id"])},
    )
    celulas = cur.rowcount
    cur.execute("UPDATE plat.escala_grade SET celulas = %s WHERE id = %s::uuid", (celulas, grade_id))
    return _um(cur, "SELECT * FROM plat.escala_grade WHERE id = %s::uuid", (grade_id,))


# ------------------------------------------------------------------ execução


def _blocos_do_fator(cur, tenant_id: int, fator_id: str, srid: int, resolucao_bloco: float) -> int:
    """Agrega as amostras do fator em blocos da resolução de avaliação. Devolve quantos blocos foram
    calculados AGORA (os que já estavam no cache não voltam a ser agregados)."""
    cur.execute(
        "WITH pontos AS ("
        "  SELECT ST_Transform(geom, %(srid)s) AS p, valor FROM plat.escala_amostra "
        "  WHERE tenant_id = %(t)s AND fator_id = %(f)s::uuid"
        "), blocos AS ("
        "  SELECT floor(ST_X(p) / %(r)s)::int AS bx, floor(ST_Y(p) / %(r)s)::int AS by, "
        "         avg(valor) AS v, count(*) AS n FROM pontos GROUP BY 1, 2"
        ") "
        "INSERT INTO plat.escala_bloco(tenant_id, fator_id, srid, resolucao_m, bloco_x, bloco_y, valor, amostras) "
        "SELECT %(t)s, %(f)s::uuid, %(srid)s, %(r)s, bx, by, v, n FROM blocos "
        "ON CONFLICT (tenant_id, fator_id, srid, resolucao_m, bloco_x, bloco_y) DO NOTHING",
        {"t": tenant_id, "f": fator_id, "srid": srid, "r": resolucao_bloco},
    )
    return cur.rowcount


def executar(cur, tenant_id: int, usuario_id: int, conjunto: dict, grade: dict, fatores: list[FatorPedido],
             aprovacao_tipo: str, aprovacao_valor: float, execucao_pai_id: str | None = None) -> dict:
    """Calcula a grade inteira e grava execução, fatores, fator bruto por célula e resultado."""
    inicio = time.monotonic()
    if not fatores:
        raise ErroAPI(422, "sem_fator", "a execução precisa de pelo menos um fator")
    if len(fatores) > limites.ESCALA_FATORES_MAX:
        raise ErroAPI(422, "fatores_demais", f"o teto é {limites.ESCALA_FATORES_MAX} fatores por execução")
    if len({f.fator_id for f in fatores}) != len(fatores):
        raise ErroAPI(422, "fator_repetido", "o mesmo fator aparece duas vezes na execução")
    celulas = int(grade["celulas"])
    ligacoes = celulas * len(fatores)
    if ligacoes > limites.ESCALA_LIGACOES_MAX:
        raise ErroAPI(
            422, "execucao_grande_demais",
            f"{celulas} células × {len(fatores)} fatores = {ligacoes} linhas de fator bruto; o teto é "
            f"{limites.ESCALA_LIGACOES_MAX}",
            {"celulas": celulas, "fatores": len(fatores), "linhas": ligacoes},
        )
    srid = int(conjunto["srid_trabalho"])
    res_grade = float(grade["resolucao_m"])
    cur.execute(
        "INSERT INTO plat.escala_execucao(tenant_id, conjunto_id, grade_id, nivel, execucao_pai_id, "
        "aprovacao_tipo, aprovacao_valor, celulas, celulas_possiveis, dono_id) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (tenant_id, str(conjunto["id"]), str(grade["id"]), grade["nivel"],
         execucao_pai_id, aprovacao_tipo, aprovacao_valor, celulas, int(grade["celulas_possiveis"]), usuario_id),
    )
    execucao_id = str(cur.fetchone()["id"])

    for pedido in fatores:
        fator = _um(
            cur,
            "SELECT id, nome, papel, resolucao_fonte_m FROM plat.escala_fator WHERE id = %s::uuid",
            (pedido.fator_id,),
        )
        res_fonte = float(fator["resolucao_fonte_m"])
        # a avaliação nunca é mais fina que a fonte declarada: bloco = max(escala da fonte, escala da grade)
        res_bloco = max(res_fonte, res_grade)
        grosseira = res_fonte > res_grade
        calculados = _blocos_do_fator(cur, tenant_id, str(fator["id"]), srid, res_bloco)
        cur.execute(
            "INSERT INTO plat.escala_execucao_fator(execucao_id, fator_id, tenant_id, peso, resolucao_fonte_m, "
            "resolucao_grade_m, razao_escala, escala, escala_grosseira, blocos_calculados) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)",
            (execucao_id, str(fator["id"]), tenant_id, pedido.peso, res_fonte, res_grade,
             res_fonte / res_grade, "grosseira" if grosseira else "propria", grosseira, calculados),
        )
        cur.execute(
            "INSERT INTO plat.escala_fator_celula(execucao_id, celula_id, fator_id, tenant_id, bloco_x, "
            "bloco_y, valor) "
            "SELECT %(e)s::uuid, c.id, %(f)s::uuid, %(t)s, k.bx, k.by, b.valor "
            "FROM plat.escala_celula c "
            "CROSS JOIN LATERAL (SELECT floor(c.centro_x_m / %(r)s)::int AS bx, "
            "                           floor(c.centro_y_m / %(r)s)::int AS by) k "
            "LEFT JOIN plat.escala_bloco b ON b.tenant_id = %(t)s AND b.fator_id = %(f)s::uuid "
            "     AND b.srid = %(srid)s AND b.resolucao_m = %(r)s AND b.bloco_x = k.bx AND b.bloco_y = k.by "
            "WHERE c.grade_id = %(g)s::uuid",
            {"e": execucao_id, "f": str(fator["id"]), "t": tenant_id, "r": res_bloco, "srid": srid,
             "g": str(grade["id"])},
        )
        cur.execute(
            "WITH lim AS (SELECT min(valor) AS mn, max(valor) AS mx FROM plat.escala_fator_celula "
            "             WHERE execucao_id = %(e)s::uuid AND fator_id = %(f)s::uuid AND valor IS NOT NULL) "
            "UPDATE plat.escala_fator_celula fc SET favorabilidade = CASE "
            "  WHEN fc.valor IS NULL THEN NULL "
            "  WHEN lim.mx = lim.mn THEN 50.0 "
            "  WHEN %(papel)s = 'custo' THEN 100.0 * (lim.mx - fc.valor) / (lim.mx - lim.mn) "
            "  ELSE 100.0 * (fc.valor - lim.mn) / (lim.mx - lim.mn) END "
            "FROM lim WHERE fc.execucao_id = %(e)s::uuid AND fc.fator_id = %(f)s::uuid",
            {"e": execucao_id, "f": str(fator["id"]), "papel": fator["papel"]},
        )
        cur.execute(
            "UPDATE plat.escala_execucao_fator ef SET "
            "  blocos_usados = s.blocos, celulas_com_dado = s.com_dado, valor_min = s.mn, valor_max = s.mx "
            "FROM (SELECT count(DISTINCT (bloco_x, bloco_y)) AS blocos, "
            "             count(*) FILTER (WHERE valor IS NOT NULL) AS com_dado, "
            "             min(valor) AS mn, max(valor) AS mx "
            "      FROM plat.escala_fator_celula WHERE execucao_id = %(e)s::uuid AND fator_id = %(f)s::uuid) s "
            "WHERE ef.execucao_id = %(e)s::uuid AND ef.fator_id = %(f)s::uuid",
            {"e": execucao_id, "f": str(fator["id"])},
        )

    cur.execute(
        "INSERT INTO plat.escala_resultado(execucao_id, celula_id, tenant_id, nota, cobertura, aprovada) "
        "SELECT %(e)s::uuid, c.id, %(t)s, "
        "  CASE WHEN coalesce(sum(ef.peso) FILTER (WHERE fc.favorabilidade IS NOT NULL), 0) > 0 "
        "       THEN sum(ef.peso * fc.favorabilidade) FILTER (WHERE fc.favorabilidade IS NOT NULL) "
        "            / sum(ef.peso) FILTER (WHERE fc.favorabilidade IS NOT NULL) "
        "       ELSE NULL END, "
        "  coalesce(sum(ef.peso) FILTER (WHERE fc.favorabilidade IS NOT NULL), 0) / sum(ef.peso), "
        "  false "
        "FROM plat.escala_celula c "
        "JOIN plat.escala_execucao_fator ef ON ef.execucao_id = %(e)s::uuid "
        "LEFT JOIN plat.escala_fator_celula fc ON fc.execucao_id = %(e)s::uuid AND fc.celula_id = c.id "
        "     AND fc.fator_id = ef.fator_id "
        "WHERE c.grade_id = %(g)s::uuid GROUP BY c.id",
        {"e": execucao_id, "t": tenant_id, "g": str(grade["id"])},
    )
    if aprovacao_tipo == "limiar":
        cur.execute(
            "UPDATE plat.escala_resultado SET aprovada = true "
            "WHERE execucao_id = %s::uuid AND nota IS NOT NULL AND nota >= %s",
            (execucao_id, aprovacao_valor),
        )
    else:  # top_pct — o vocabulário fechado está em limites.ESCALA_APROVACAO_TIPOS
        cur.execute(
            "WITH ord AS ("
            "  SELECT celula_id, row_number() OVER (ORDER BY nota DESC, celula_id) AS rn, "
            "         count(*) OVER () AS total "
            "  FROM plat.escala_resultado WHERE execucao_id = %(e)s::uuid AND nota IS NOT NULL"
            ") "
            "UPDATE plat.escala_resultado r SET aprovada = true FROM ord "
            "WHERE r.execucao_id = %(e)s::uuid AND r.celula_id = ord.celula_id "
            "  AND ord.rn <= greatest(1, ceil(ord.total * %(v)s / 100.0))",
            {"e": execucao_id, "v": aprovacao_valor},
        )
    cur.execute(
        "UPDATE plat.escala_execucao SET "
        "  celulas_com_nota = (SELECT count(*) FROM plat.escala_resultado "
        "                      WHERE execucao_id = %(e)s::uuid AND nota IS NOT NULL), "
        "  celulas_aprovadas = (SELECT count(*) FROM plat.escala_resultado "
        "                       WHERE execucao_id = %(e)s::uuid AND aprovada), "
        "  duracao_ms = %(ms)s "
        "WHERE id = %(e)s::uuid",
        {"e": execucao_id, "ms": int((time.monotonic() - inicio) * 1000)},
    )
    return _um(cur, "SELECT * FROM plat.escala_execucao WHERE id = %s::uuid", (execucao_id,))
