"""Item L3-07-agregacao — REFUTAÇÃO exigida pelo portão: "adversário recalcula 50 feições com
ST_Intersection à mão no psql e compara". Este teste NÃO importa nem chama nenhuma função de
`app.amc.agregacao` para calcular o valor esperado — a consulta de referência é escrita do zero aqui,
com `ST_Intersection`/`ST_Area` direto em SQL, do mesmo jeito que um humano no psql faria. Só depois os
dois números (o daqui e o de `agregacao.agregar()`) são comparados.

Amostra: 50 imóveis de `cbre.imoveis_candidatos`, escolhidos por `md5(car_cod || sal)` (determinístico,
sem depender de ordem física da tabela). Comparados: área total de interseção, contagem de células não
vetadas, fração vetada, veto principal e a média ponderada de três fatores (`f_zon`, `f_rod`, `f_agua`)
— os mesmos números que o portão do item exige."""

import pytest

from app.amc import agregacao

SAL = "sal-adversario-l307"
_CELULAS_SQL = (
    "SELECT h.hex_id::text AS cell_id, h.geom_utm AS geom, hf.veto, hf.veto_motivo AS motivo, "
    "jsonb_build_object('f_zon', hf.f_zon, 'f_rod', hf.f_rod, 'f_agua', hf.f_agua) AS fatores "
    "FROM cbre.hex h JOIN cbre.hex_fav hf USING (hex_id)"
)


def _amostra_50(cur) -> list[str]:
    cur.execute(
        "SELECT car_cod FROM cbre.imoveis_candidatos ORDER BY md5(car_cod || %s) LIMIT 50",
        (SAL,),
    )
    return [r["car_cod"] for r in cur.fetchall()]


def _referencia_a_mao(cur, ids: list[str]) -> dict[str, dict]:
    """Recálculo independente: ST_Intersection/ST_Area escritos aqui, nunca em `app/amc/agregacao.py`."""
    cur.execute(
        """
        WITH inter AS (
            SELECT i.car_cod, h.hex_id, hf.veto, hf.veto_motivo,
                   ST_Area(ST_Intersection(i.geom, h.geom_utm)) AS a,
                   hf.f_zon, hf.f_rod, hf.f_agua
            FROM cbre.imoveis_candidatos i
            JOIN cbre.hex h ON ST_Intersects(i.geom, h.geom_utm)
            JOIN cbre.hex_fav hf USING (hex_id)
            WHERE i.car_cod = ANY(%(ids)s)
        ),
        tot AS (
            SELECT car_cod, sum(a) AS area_total, sum(a) FILTER (WHERE veto) AS area_veto,
                   count(*) FILTER (WHERE NOT veto) AS n_cel,
                   (array_agg(veto_motivo ORDER BY a DESC, hex_id) FILTER (WHERE veto))[1] AS veto_principal
            FROM inter GROUP BY car_cod
        ),
        media AS (
            SELECT car_cod,
                sum(a * f_zon) FILTER (WHERE NOT veto AND f_zon IS NOT NULL)
                    / NULLIF(sum(a) FILTER (WHERE NOT veto AND f_zon IS NOT NULL), 0) AS f_zon,
                sum(a * f_rod) FILTER (WHERE NOT veto AND f_rod IS NOT NULL)
                    / NULLIF(sum(a) FILTER (WHERE NOT veto AND f_rod IS NOT NULL), 0) AS f_rod,
                sum(a * f_agua) FILTER (WHERE NOT veto AND f_agua IS NOT NULL)
                    / NULLIF(sum(a) FILTER (WHERE NOT veto AND f_agua IS NOT NULL), 0) AS f_agua
            FROM inter GROUP BY car_cod
        )
        SELECT t.car_cod, t.area_total, t.n_cel,
               coalesce(t.area_veto, 0) / NULLIF(t.area_total, 0) AS fracao_vetada,
               t.veto_principal, m.f_zon, m.f_rod, m.f_agua
        FROM tot t LEFT JOIN media m USING (car_cod)
        """,
        {"ids": ids},
    )
    return {r["car_cod"]: dict(r) for r in cur.fetchall()}


def test_adversario_recalcula_50_feicoes_com_st_intersection_a_mao_no_psql(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        ids = _amostra_50(cur)
        assert len(ids) == 50
        referencia = _referencia_a_mao(cur, ids)
        assert set(referencia) == set(ids)

        feicoes_sql = ("SELECT car_cod AS feicao_id, geom FROM cbre.imoveis_candidatos "
                       "WHERE car_cod = ANY(%(amostra_ids)s)")
        r = agregacao.agregar(cur, feicoes_sql, {"amostra_ids": ids}, _CELULAS_SQL, {})

    assert len(r["resultados"]) == 50
    por_id = {x["feicao_id"]: x for x in r["resultados"]}

    for cid in ids:
        ref = referencia[cid]
        calc = por_id[cid]
        assert calc["area_total_m2"] == pytest.approx(float(ref["area_total"]), rel=1e-9)
        assert calc["n_cel"] == ref["n_cel"]
        if ref["fracao_vetada"] is None:
            assert calc["fracao_vetada"] is None
        else:
            assert calc["fracao_vetada"] == pytest.approx(float(ref["fracao_vetada"]), rel=1e-9)
        assert calc["veto_principal"] == ref["veto_principal"]
        for fator in ("f_zon", "f_rod", "f_agua"):
            esperado = ref[fator]
            obtido = calc["fatores_media"].get(fator)
            if esperado is None:
                assert obtido is None, f"{cid}/{fator}: adversário deu NULL, agregar() deu {obtido}"
            else:
                assert obtido == pytest.approx(float(esperado), rel=1e-9), (
                    f"{cid}/{fator}: adversário {esperado} != agregar() {obtido}"
                )
