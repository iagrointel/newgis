"""Agregação de grade para feição (item L3-07-agregacao): leva o resultado do motor, calculado por CÉLULA
da grade, para uma FEIÇÃO qualquer (imóvel, lote, município, setor censitário — qualquer polígono que o
usuário forneça), e o caminho inverso (feição -> células) para exibir a composição da nota.

Método (decisão do item, o mesmo que `cbre.imoveis_fav` já fazia à mão em SQL para o piloto CBRE — este
módulo generaliza para qualquer conjunto de células e qualquer fator, ver `pipeline/85_fatores.sql` do
projeto `cbre`):

1. interseção geométrica entre a feição e cada célula que ela toca, com `ST_Area` no CRS MÉTRICO de
   trabalho (nunca grau, nunca Web Mercator — a mesma zona UTM SIRGAS 2000 do conjunto de unidades);
2. por fator, a média da feição é a média dos valores das células PONDERADA pela área de interseção,
   somada só sobre as células NÃO VETADAS (célula vetada não teria nota naquele fator: o veto é tratado à
   parte, não como um fator zerado, para não puxar a média sem necessidade);
3. fração vetada da feição = área em células vetadas / área total intersectada (aqui SIM sobre todas as
   células que a feição toca, vetadas ou não — é essa fração que decide o quanto da feição está sob
   restrição);
4. veto principal = motivo da célula vetada de MAIOR área de interseção (o veto que mais pesa na feição,
   não o primeiro que aparecer); empate de área é desempatado por `cell_id` (determinístico — sem isso
   duas consultas equivalentes, mas com plano de execução diferente, podem devolver motivos diferentes
   para a mesma feição, achado rodando a refutação do item: `tests/unit/test_amc_agregacao_adversario.py`);
5. a favorabilidade da feição é a combinação (`app.amc.combinacao.combinar`, mesmos pesos/combinador/
   política do modelo) dos valores médios por fator, multiplicada por (1 − fração vetada) — fração vetada
   1,0 zera a nota e não precisa de combinação nenhuma;
6. limiar de fração vetada declarado por quem chama (nunca calculado): acima dele a feição sai do
   ranking (`fora_do_ranking = true`), mas continua tendo os números — não é apagada;
7. feição que não toca NENHUMA célula não é zero: sai com `sem_celula = true` e todo o resto `None`.

O módulo não abre conexão: recebe um cursor já aberto e DUAS consultas SQL prontas (não construídas a
partir de entrada do usuário) que devolvem, cada uma, linhas já no CRS de trabalho:

- `celulas_sql`: `(cell_id text, geom geometry, veto boolean, motivo text, fatores jsonb)` — um fator por
  chave do jsonb, valor numérico ou `null`; célula sem nenhum fator ainda entra na fração vetada;
- `feicoes_sql` (opcional; ver `feicoes_de_geojson`): `(feicao_id text, geom geometry)`.

Isso deixa o mesmo motor servir tanto a execução real (`app.amc.tarefas`/rotas, ver
`celulas_de_execucao_sql`) quanto a comparação com `cbre.hex_fav`/`cbre.imoveis_fav` que prova o item
(mesma consulta, fonte diferente: ver `tests/unit/test_amc_agregacao_cbre.py`)."""

from __future__ import annotations

import json
import time

from app.amc import combinacao as mod_combinacao
from app.amc import explicacao as mod_explicacao


class ErroAgregacao(ValueError):
    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe or {}


# ---------------------------------------------------------------------- fontes de entrada prontas
def feicoes_de_geojson(
    feicoes: list[tuple[str, dict]], srid_trabalho: int, srid_entrada: int = 4326,
) -> tuple[str, dict]:
    """SQL + parâmetros para `feicoes_sql`: reprojeta uma lista (id, GeoJSON Polygon/MultiPolygon) do
    `srid_entrada` (4326 por padrão — o que chega do usuário) para o CRS de trabalho. `feicoes` vem do
    pedido do usuário (GeoJSON), por isso passa por `ST_MakeValid` — geometria de upload não é confiável
    como a do banco. `srid_entrada` só muda em teste, para descrever a geometria sintética já no próprio
    CRS métrico (evita coordenada de grau inventada sem sentido geográfico)."""
    if not feicoes:
        raise ErroAgregacao("sem_feicoes", "nenhuma feição para agregar")
    ids = [str(i) for i, _ in feicoes]
    if len(set(ids)) != len(ids):
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        raise ErroAgregacao("feicao_id_duplicado", f"id de feição repetido: {', '.join(repetidos)}",
                            {"repetidos": repetidos})
    geojsons = [json.dumps(g) for _, g in feicoes]
    sql = (
        "SELECT x.feicao_id, ST_Transform(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(x.gj), "
        "%(srid_entrada)s)), %(srid_trabalho)s) AS geom "
        "FROM unnest(%(feicao_ids)s::text[], %(feicao_geojsons)s::text[]) AS x(feicao_id, gj)"
    )
    return sql, {"srid_trabalho": srid_trabalho, "srid_entrada": srid_entrada, "feicao_ids": ids,
                 "feicao_geojsons": geojsons}


def celulas_de_geojson(celulas: list[tuple[str, dict, bool, str | None, dict]], srid_trabalho: int,
                       srid_entrada: int = 4326) -> tuple[str, dict]:
    """`celulas_sql` sintética para teste/uso avulso: cada célula é
    ``(cell_id, geojson, veto, motivo, fatores)``. Útil para testar `agregar()` sem nenhuma tabela do
    motor — só geometria e números, do mesmo jeito que `feicoes_de_geojson` faz para a feição
    (`srid_entrada` pelo mesmo motivo: descrever célula sintética já em metros, sem inventar grau)."""
    if not celulas:
        raise ErroAgregacao("sem_celulas", "nenhuma célula para agregar")
    ids = [str(c[0]) for c in celulas]
    geojsons = [json.dumps(c[1]) for c in celulas]
    vetos = [bool(c[2]) for c in celulas]
    motivos = [c[3] for c in celulas]
    fatores = [json.dumps(c[4] or {}) for c in celulas]
    sql = (
        "SELECT x.cell_id, ST_Transform(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(x.gj), "
        "%(srid_entrada)s)), %(srid_trabalho)s) AS geom, x.veto, x.motivo, x.fatores::jsonb AS fatores "
        "FROM unnest(%(celula_ids)s::text[], %(celula_geojsons)s::text[], %(celula_vetos)s::bool[], "
        "%(celula_motivos)s::text[], %(celula_fatores)s::text[]) "
        "AS x(cell_id, gj, veto, motivo, fatores)"
    )
    return sql, {"srid_trabalho": srid_trabalho, "srid_entrada": srid_entrada, "celula_ids": ids,
                 "celula_geojsons": geojsons, "celula_vetos": vetos, "celula_motivos": motivos,
                 "celula_fatores": fatores}


def celulas_de_execucao_sql() -> str:
    """`celulas_sql` para uma execução real do motor: célula = unidade do conjunto, veto/motivo e
    favorabilidade JÁ COMBINADA do resultado (`plat.amc_resultado`).

    Limite honesto e deliberado deste item (mesmo padrão de `app/amc/executor.py` e
    `app/amc/explicacao.py`, que documentam os limites deles do mesmo jeito): a matriz fator-a-fator
    JÁ TRANSFORMADA (bruto -> nota 0-100) não é persistida por célula hoje — só o `amc_fator_bruto`
    (valor bruto, antes da transformação declarada no modelo) e o `amc_resultado.favorabilidade` (já
    combinado com os pesos). Recompor a transformação de cada fator aqui duplicaria o escopo do item
    L3-01-d-transformacoes (pendente, veto do próprio código: `executor.py` só resolve a transformação
    'linear' e levanta erro claro nas outras) sem a verificação cruzada que aquele item exige.

    Por isso a célula entra na agregação com UM fator sintético, `favorabilidade`, igual ao que o motor
    já combinou — a agregação por feição vira `Σ área·favorabilidade / Σ área` sobre as células não
    vetadas, exatamente a mesma conta que `cbre.imoveis_fav` faz para cada `f_*` (a prova do item usa
    `cbre.hex_fav`, que tem VÁRIOS fatores já transformados, exatamente para provar que o mecanismo
    geométrico generaliza para N fatores — aqui a integração real começa com N = 1 porque é o que o
    resto do motor persiste hoje). Recombinar por vários fatores no nível da feição (o `modelo_definicao`
    continua aceito por `agregar()` para esse caso) fica pronto para quando a nota por fator existir."""
    return (
        "SELECT u.unidade_id AS cell_id, ST_Transform(u.geom, %(srid_trabalho)s) AS geom, "
        "r.vetado AS veto, r.motivo, "
        "jsonb_build_object('favorabilidade', r.favorabilidade) AS fatores "
        "FROM plat.amc_unidade u JOIN plat.amc_resultado r "
        "  ON r.execucao_id = %(execucao_id)s AND r.unidade_id = u.unidade_id "
        "WHERE u.conjunto_id = %(conjunto_id)s"
    )


# ---------------------------------------------------------------------- núcleo (SQL de interseção)
_SQL_INTERSECAO = """
WITH feicoes AS ({feicoes_sql}),
celulas AS ({celulas_sql}),
inter AS (
    SELECT f.feicao_id, c.cell_id, c.veto, c.motivo, c.fatores,
           ST_Area(ST_Intersection(f.geom, c.geom)) AS area_m2
    FROM feicoes f JOIN celulas c ON ST_Intersects(f.geom, c.geom)
    WHERE ST_Area(ST_Intersection(f.geom, c.geom)) > 0
),
tot AS (
    SELECT feicao_id,
           sum(area_m2) AS area_total_m2,
           sum(area_m2) FILTER (WHERE veto) AS area_vetada_m2,
           count(*) FILTER (WHERE NOT veto) AS n_cel,
           count(*) AS n_cel_tocadas,
           (array_agg(motivo ORDER BY area_m2 DESC, cell_id)
             FILTER (WHERE veto AND motivo IS NOT NULL))[1] AS veto_principal
    FROM inter GROUP BY feicao_id
),
expandido AS (
    SELECT feicao_id, area_m2, kv.key AS fator, (NULLIF(kv.value, 'null'))::float8 AS valor
    FROM inter, LATERAL jsonb_each_text(coalesce(fatores, '{{}}'::jsonb)) AS kv
    WHERE NOT veto
),
medias AS (
    SELECT feicao_id, fator, sum(area_m2 * valor) / NULLIF(sum(area_m2) FILTER (WHERE valor IS NOT NULL), 0) AS media
    FROM expandido WHERE valor IS NOT NULL GROUP BY feicao_id, fator
),
medias_json AS (
    SELECT feicao_id, jsonb_object_agg(fator, media) AS fatores_media FROM medias GROUP BY feicao_id
)
SELECT f.feicao_id, t.area_total_m2, t.area_vetada_m2, t.n_cel, t.n_cel_tocadas, t.veto_principal,
       CASE WHEN t.area_total_m2 IS NULL OR t.area_total_m2 <= 0 THEN NULL
            ELSE coalesce(t.area_vetada_m2, 0) / t.area_total_m2 END AS fracao_vetada,
       mj.fatores_media
FROM feicoes f
LEFT JOIN tot t USING (feicao_id)
LEFT JOIN medias_json mj USING (feicao_id)
"""

_SQL_CELULAS_DE_UMA_FEICAO = """
WITH feicoes AS ({feicoes_sql}),
celulas AS ({celulas_sql})
SELECT c.cell_id, c.veto, c.motivo,
       ST_Area(ST_Intersection(f.geom, c.geom)) AS area_intersecao_m2,
       ST_Area(c.geom) AS area_celula_m2, c.fatores
FROM feicoes f JOIN celulas c ON ST_Intersects(f.geom, c.geom)
WHERE f.feicao_id = %(feicao_id_alvo)s AND ST_Area(ST_Intersection(f.geom, c.geom)) > 0
ORDER BY area_intersecao_m2 DESC
"""


def agregar(
    cur,
    feicoes_sql: str,
    feicoes_params: dict,
    celulas_sql: str,
    celulas_params: dict,
    *,
    modelo_definicao: dict | None = None,
    pesos: dict | None = None,
    limiar_fracao_vetada: float = 0.5,
) -> dict:
    """Agrega grade -> feição. `feicoes_sql`/`celulas_sql` são as consultas descritas no docstring do
    módulo; os `_params` de cada uma são passados juntos (chaves distintas — é responsabilidade de quem
    monta o SQL não colidir nomes de parâmetro).

    Devolve `{"tempo_ms", "limiar_fracao_vetada", "resultados": [...]}`; cada resultado tem `feicao_id`,
    `sem_celula`, `area_total_m2`, `fracao_vetada`, `veto_principal`, `n_cel`, `fatores_media`,
    `combinacao` (nota 0-100 antes do veto, `None` se não houver peso/fator com dado),
    `favorabilidade` (combinação × (1 − fração vetada), `None` se sem célula ou sem combinação) e
    `fora_do_ranking` (fração vetada >= limiar; `False` quando `sem_celula`, nunca `None`)."""
    if not (0.0 <= limiar_fracao_vetada <= 1.0):
        raise ErroAgregacao("limiar_invalido", "limiar de fração vetada tem de estar entre 0 e 1",
                            {"limiar_fracao_vetada": limiar_fracao_vetada})
    params = {**feicoes_params, **celulas_params}
    sql = _SQL_INTERSECAO.format(feicoes_sql=feicoes_sql, celulas_sql=celulas_sql)
    t0 = time.monotonic()
    cur.execute(sql, params)
    linhas = cur.fetchall()
    tempo_ms = round((time.monotonic() - t0) * 1000, 1)

    fatores_ids = None
    if modelo_definicao is not None:
        fatores_ids = [f["id"] for f in modelo_definicao["fatores"]]
        pesos_resolvidos = [float((pesos or {}).get(fid, next(
            f["peso"] for f in modelo_definicao["fatores"] if f["id"] == fid))) for fid in fatores_ids]
        combinador_esquema = (modelo_definicao.get("combinador") or {}).get("tipo", "soma_ponderada_normalizada")
        combinador = mod_explicacao.MAPA_COMBINADOR[combinador_esquema]
        politica = mod_explicacao.MAPA_POLITICA[modelo_definicao.get("dado_ausente", "excluir_fator")]

    resultados = []
    for linha in linhas:
        sem_celula = linha["area_total_m2"] is None
        item = {
            "feicao_id": linha["feicao_id"],
            "sem_celula": sem_celula,
            "area_total_m2": linha["area_total_m2"],
            "n_cel": linha["n_cel"] if not sem_celula else None,
            "n_cel_tocadas": linha["n_cel_tocadas"] if not sem_celula else None,
            "fracao_vetada": linha["fracao_vetada"],
            "veto_principal": linha["veto_principal"],
            "fatores_media": dict(linha["fatores_media"]) if linha["fatores_media"] else {},
            "combinacao": None,
            "favorabilidade": None,
            "fora_do_ranking": False,
        }
        if not sem_celula:
            item["fora_do_ranking"] = (linha["fracao_vetada"] or 0.0) >= limiar_fracao_vetada
            fm = item["fatores_media"]
            fav = None
            if fatores_ids is not None:
                matriz = [[fm.get(fid) for fid in fatores_ids]]
                res = mod_combinacao.combinar(
                    matriz, pesos_resolvidos, combinador=combinador, politica_ausente=politica,
                    ids_fatores=fatores_ids,
                )
                v = res.fav[0]
                fav = float(v) if v == v else None  # v == v descarta NaN
            elif len(fm) == 1:
                # sem modelo declarado: um só fator agregado é a própria combinação (peso 1, sem fuzzy) —
                # é o caso de `celulas_de_execucao_sql`, cuja célula já traz a favorabilidade combinada.
                (unico,) = fm.values()
                fav = float(unico) if unico is not None else None
            if fav is not None:
                item["combinacao"] = round(fav, 4)
                fracao = linha["fracao_vetada"] or 0.0
                item["favorabilidade"] = round(fav * (1.0 - fracao), 4)
        resultados.append(item)
    return {"tempo_ms": tempo_ms, "limiar_fracao_vetada": limiar_fracao_vetada, "resultados": resultados}


def celulas_de_uma_feicao(cur, feicoes_sql: str, feicoes_params: dict, celulas_sql: str, celulas_params: dict,
                           feicao_id: str) -> list[dict]:
    """Caminho inverso (feição -> células), para exibir a composição da nota: toda célula que a feição
    toca, com a área de interseção e a área total da célula, ordenada da maior contribuição para a menor."""
    params = {**feicoes_params, **celulas_params, "feicao_id_alvo": str(feicao_id)}
    sql = _SQL_CELULAS_DE_UMA_FEICAO.format(feicoes_sql=feicoes_sql, celulas_sql=celulas_sql)
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]
