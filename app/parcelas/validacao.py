"""Validação da malha de parcelas (a primeira metade da refutação do item: "o adversário cria
duas parcelas ativas do mesmo tipo sobrepostas e confere que a validação aponta").

Sobreposição é por TIPO, entre parcelas ATIVAS do mesmo inquilino: duas parcelas ativas do
tipo 'lote' que se cruzam com área maior que a tolerância são um par apontado, com a área da
interseção. A tolerância existe porque limites partilhados gerados por malha (Voronoi,
importação) deixam lascas de flutuante-ponto de ~1e-9 m² — lascas não são sobreposição.
Parcelas históricas nunca apontam (só o 'atual' se valida). O teto
`PARCELA_VALIDACAO_PARES_MAX` limita a lista devolvida; o total é contado à parte.
"""

from app import limites
from app.erros import ErroAPI

TOLERANCIA_M2 = 0.01  # 1 cm²: lascas de malha não são sobreposição (interseção de vizinhos fecha em ~0)


def sobreposicoes(cur, *, tenant_id: int, tipo: str | None = None,
                  tolerancia_m2: float = TOLERANCIA_M2) -> dict:
    if tipo is not None and tipo not in modelo_tipos():
        raise ErroAPI(422, "tipo_invalido", f"tipo precisa ser um de: {', '.join(modelo_tipos())}")
    cur.execute(
        "SELECT count(*) AS total FROM ("
        "  SELECT a.id FROM plat.parcela a JOIN plat.parcela b"
        "    ON a.tenant_id = b.tenant_id AND a.tipo = b.tipo AND a.id < b.id"
        "   AND a.ativa AND b.ativa AND a.geom && b.geom"
        "   AND ST_Intersects(a.geom, b.geom)"
        "  WHERE a.tenant_id = %s AND ST_Area(ST_Intersection(a.geom, b.geom)) > %s"
        "    AND (%s::text IS NULL OR a.tipo = %s)"
        ") s",
        (tenant_id, tolerancia_m2, tipo, tipo),
    )
    total = int(cur.fetchone()["total"])
    cur.execute(
        "SELECT a.tipo, a.codigo AS a_codigo, b.codigo AS b_codigo, a.id AS a_id, b.id AS b_id, "
        "       ST_Area(ST_Intersection(a.geom, b.geom)) AS area_m2 "
        "FROM plat.parcela a JOIN plat.parcela b"
        "  ON a.tenant_id = b.tenant_id AND a.tipo = b.tipo AND a.id < b.id"
        " AND a.ativa AND b.ativa AND a.geom && b.geom"
        " AND ST_Intersects(a.geom, b.geom)"
        "WHERE a.tenant_id = %s AND ST_Area(ST_Intersection(a.geom, b.geom)) > %s"
        "  AND (%s::text IS NULL OR a.tipo = %s) "
        "ORDER BY ST_Area(ST_Intersection(a.geom, b.geom)) DESC LIMIT %s",
        (tenant_id, tolerancia_m2, tipo, tipo, limites.PARCELA_VALIDACAO_PARES_MAX),
    )
    pares = cur.fetchall()
    return {
        "total": total,
        "truncado": total > len(pares),
        "pares": [
            {"tipo": r["tipo"], "a": r["a_codigo"], "b": r["b_codigo"],
             "a_id": r["a_id"], "b_id": r["b_id"], "area_m2": float(r["area_m2"])}
            for r in pares
        ],
        "tolerancia_m2": tolerancia_m2,
    }


def modelo_tipos() -> tuple:
    from app.parcelas.modelo import TIPOS  # import tardio evita ciclo de módulo
    return TIPOS
