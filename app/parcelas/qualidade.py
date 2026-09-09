"""Camada de qualidade da malha de parcelas — item L4-parcelas-03-ajuste-e-qualidade. Par:
docs/PARIDADE_PARCELAS.md §13 (Find Gaps and Overlaps / parcelfabricdataqualitylayers do Pro).

Três seções, tudo sobre parcelas ATIVAS do mesmo inquilino (e do mesmo tipo, quando declarado):

- SOBREPOSIÇÕES: pares do mesmo tipo com interseção de área acima da tolerância (reuso direto
  de validacao.sobreposicoes, item 01).
- LACUNAS: faces fechadas pelas próprias bordas das parcelas que NÃO pertencem a parcela
  nenhuma — Polygonize das bordas DENTRO DE CADA REGISTRO (cada registro é um levantamento;
  espaço entre registros não é lacuna de malha) e a face cujo ponto sobre a superfície não é
  coberto por nenhuma parcela é uma lacuna, com a área. A contagem INDEPENDENTE (ST_Overlaps
  no par, ST_Difference na face) é a prova do portão, em tests/api/parcelas/test_qualidade.py.
- REGRAS DE ATRIBUTO (parcelfabricattributerules): área CALCULADA × DECLARADA com desvio acima
  da tolerância e FECHAMENTO — parcela com erro_fechamento_m acima do teto declarado. A regra
  não altera dado: aponta.

A camada é um relatório vivo, não tabela: cada chamada mede o estado atual do banco. Os tetos
limitam só as LISTAS; os totais são contados à parte (mesma regra da validação do item 01).
"""

from app import limites
from app.erros import ErroAPI
from app.parcelas import validacao

# Fechamento: um traverse de malha urbana fecha em centímetros; acima disso a parcela carrega o
# erro declarado na criação (erro_fechamento_m do item 01/02) e entra na camada.
TOLERANCIA_FECHAMENTO_M = 0.10


def camada_qualidade(cur, *, tenant_id: int, tipo: str | None = None,
                     tolerancia_m2: float = validacao.TOLERANCIA_M2) -> dict:
    if tipo is not None and tipo not in validacao.modelo_tipos():
        raise ErroAPI(422, "tipo_invalido", f"tipo precisa ser um de: {', '.join(validacao.modelo_tipos())}")
    if tolerancia_m2 <= 0:
        raise ErroAPI(422, "valor_invalido", "toleranciaM2 precisa ser positiva")

    sobre = validacao.sobreposicoes(cur, tenant_id=tenant_id, tipo=tipo, tolerancia_m2=tolerancia_m2)
    sobre_area = sum(p["area_m2"] for p in sobre["pares"])

    # ---- lacunas: faces das bordas que nenhuma parcela cobre. ESCOPO: dentro de cada MALHA
    # (registro) — cada registro é um levantamento; espaço entre dois registros não é lacuna de
    # malha nenhuma. Medido (09/09): o polygonize do corpus INTEIRO de uma vez (11.473 lotes)
    # não termina — rodou 20 min de GEOS a 100 % e estourou 3 GB até o kernel matar o backend
    # (e o Postgres de produção junto); por registro a maior malha do corpus tem 968 lotes e
    # o mesmo cálculo é trivial. O polygonize é a parte cara (GEOS, não work_mem): faz UMA vez
    # por registro numa tabela temporária, e conta, soma e lista a partir dela.
    cur.execute("DROP TABLE IF EXISTS lacunas_face")  # duas chamadas na mesma transação
    cur.execute(
        "CREATE TEMP TABLE lacunas_face ON COMMIT DROP AS "
        "SELECT (ST_Dump(ST_Polygonize(b.g))).geom AS g FROM ("
        "  SELECT p.criada_por_registro, ST_UnaryUnion(ST_Collect(ST_Boundary(p.geom))) AS g"
        "  FROM plat.parcela p"
        "  WHERE p.tenant_id = %s AND p.ativa AND p.criada_por_registro IS NOT NULL"
        "   AND (%s::text IS NULL OR p.tipo = %s)"
        "  GROUP BY p.criada_por_registro"
        ") b",
        (tenant_id, tipo, tipo),
    )
    cur.execute(
        "SELECT count(*) AS total, COALESCE(ST_Area(ST_UnaryUnion(ST_Collect(g))), 0) AS area_m2 "
        "FROM lacunas_face WHERE ST_Area(g) > %s AND NOT EXISTS ("
        "  SELECT 1 FROM plat.parcela p WHERE p.tenant_id = %s AND p.ativa"
        "   AND (%s::text IS NULL OR p.tipo = %s) AND ST_Covers(p.geom, ST_PointOnSurface(g)))",
        (tolerancia_m2, tenant_id, tipo, tipo),
    )
    r = cur.fetchone()
    lacunas = {
        "total": int(r["total"]),
        "area_m2": float(r["area_m2"]),
        "truncado": False,
        "faces": [],
        "tolerancia_m2": tolerancia_m2,
    }
    cur.execute(
        "SELECT ST_Area(g) AS area_m2, ST_AsText(ST_Centroid(g)) AS centroide, "
        "       ST_NPoints(g) AS vertices FROM lacunas_face"
        " WHERE ST_Area(g) > %s AND NOT EXISTS ("
        "  SELECT 1 FROM plat.parcela p WHERE p.tenant_id = %s AND p.ativa"
        "   AND (%s::text IS NULL OR p.tipo = %s) AND ST_Covers(p.geom, ST_PointOnSurface(g)))"
        " ORDER BY ST_Area(g) DESC LIMIT %s",
        (tolerancia_m2, tenant_id, tipo, tipo, limites.PARCELA_QUALIDADE_FACES_MAX),
    )
    lacunas["faces"] = [
        {"area_m2": float(x["area_m2"]), "centroide": x["centroide"], "vertices": int(x["vertices"])}
        for x in cur.fetchall()
    ]
    lacunas["truncado"] = lacunas["total"] > len(lacunas["faces"])

    # ---- regras de atributo: área declarada × calculada e fechamento
    cur.execute(
        "SELECT count(*) AS total, COALESCE(max(abs(p.area_calculada_m2 - p.area_declarada_m2)), 0) "
        "  AS desvio_maximo_m2 FROM plat.parcela p"
        " WHERE p.tenant_id = %s AND p.ativa AND p.area_declarada_m2 IS NOT NULL"
        "  AND (%s::text IS NULL OR p.tipo = %s)"
        "  AND abs(p.area_calculada_m2 - p.area_declarada_m2) > %s",
        (tenant_id, tipo, tipo, tolerancia_m2),
    )
    r = cur.fetchone()
    area_desvio = {"total": int(r["total"]), "desvio_maximo_m2": float(r["desvio_maximo_m2"])}
    cur.execute(
        "SELECT count(*) AS total, COALESCE(max(p.erro_fechamento_m), 0) AS erro_maximo_m "
        "FROM plat.parcela p"
        " WHERE p.tenant_id = %s AND p.ativa AND p.erro_fechamento_m IS NOT NULL"
        "  AND (%s::text IS NULL OR p.tipo = %s) AND p.erro_fechamento_m > %s",
        (tenant_id, tipo, tipo, TOLERANCIA_FECHAMENTO_M),
    )
    r = cur.fetchone()
    fechamento = {"total": int(r["total"]), "erro_maximo_m": float(r["erro_maximo_m"]),
                  "tolerancia_m": TOLERANCIA_FECHAMENTO_M}
    cur.execute(
        "SELECT count(*) AS n FROM plat.parcela WHERE tenant_id = %s AND ativa "
        " AND (%s::text IS NULL OR tipo = %s)",
        (tenant_id, tipo, tipo),
    )
    avaliadas = int(cur.fetchone()["n"])

    return {
        "lotes_avaliados": avaliadas,
        "tipo": tipo,
        "sobreposicoes": {**sobre, "area_m2": round(sobre_area, 6)},
        "lacunas": lacunas,
        "atributos": {"area_declarada_vs_calculada": {**area_desvio, "tolerancia_m2": tolerancia_m2},
                      "fechamento": fechamento},
    }
