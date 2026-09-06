"""Conjunto de unidades de análise (item L3-01-b-unidades; decisão A7). Duas origens:

- GRADE hexagonal (`ST_HexagonGrid`) ou quadrada (`ST_SquareGrid`), gerada no CRS de trabalho (UTM SIRGAS 2000 da zona
  do centróide, app/amc/crs.py) com o lado pedido, recortada ao polígono da área de estudo e gravada em 4326 com a
  área geodésica de cada célula. Roda como job (`amc.gerar_unidades`, app/amc/tarefas.py) em faixas de até
  FAIXA_CELULAS células, com progresso e cancelamento entre faixas; a grade é determinística (origem no 0,0 do CRS),
  então as faixas se juntam por `ON CONFLICT DO NOTHING` na chave (conjunto_id, unidade_id) = '<i>_<j>'.
- FEIÇÕES do usuário (GeoJSON FeatureCollection, polígonos), síncronas, com o id do usuário preservado como
  `unidade_id`; id duplicado ou ausente recusa o conjunto inteiro com a lista.

Sem h3-pg nesta máquina (medido no L3L6_CONCEITO): H3 fica como índice opcional via biblioteca Python, fora daqui."""

import json
import math
import time

import psycopg2.extras

from app import limites
from app.amc import crs as crs_mod
from app.erros import ErroAPI

FAIXA_CELULAS = 100_000
AREA_HEX = 3.0 * math.sqrt(3.0) / 2.0  # área do hexágono de lado 1 (ST_HexagonGrid: size = lado = circunraio)
TIPOS_GRADE = ("hexagonal", "quadrada")


def area_celula_m2(tipo: str, lado_m: float) -> float:
    return AREA_HEX * lado_m * lado_m if tipo == "hexagonal" else lado_m * lado_m


class ErroValidacao(ValueError):
    def __init__(self, codigo: str, mensagem: str, detalhe=None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe

    def api(self) -> ErroAPI:
        return ErroAPI(422, self.codigo, self.mensagem, self.detalhe)


# ---------------------------------------------------------------- geometria de entrada
def _coords(geom: dict) -> list[tuple[float, float]]:
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        return [(float(p[0]), float(p[1])) for anel in c for p in anel]
    if t == "MultiPolygon":
        return [(float(p[0]), float(p[1])) for pol in c for anel in pol for p in anel]
    return []


def _checar_poligono(geom, caminho: str) -> None:
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ErroValidacao("geometria_invalida", f"{caminho}: a unidade de análise é uma área (Polygon ou "
                            f"MultiPolygon); veio {getattr(geom, 'get', lambda k: None)('type')!r}",
                            {"caminho": caminho})
    pontos = _coords(geom)
    if len(pontos) < 4:
        raise ErroValidacao("geometria_invalida", f"{caminho}: polígono com menos de 4 vértices", {"caminho": caminho})
    for lon, lat in pontos:
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ErroValidacao("geometria_invalida", f"{caminho}: coordenada fora de longitude/latitude (esperado "
                                f"EPSG:4326): {lon}, {lat}", {"caminho": caminho})


def _bbox_centroide(pontos: list[tuple[float, float]]) -> tuple[tuple[float, float, float, float], tuple[float, float]]:
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    return bbox, ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def preparar_grade(cur, tipo: str, lado_m: float, area_estudo: dict) -> dict:
    """Valida a área, escolhe o CRS (centróide REAL via ST_Centroid) e estima a contagem; recusa acima do teto.
    Devolve {ficha_crs, area_plano_m2, contagem_esperada, area_estudo_wkt}. Não grava nada."""
    if tipo not in TIPOS_GRADE:
        raise ErroValidacao("tipo_invalido", f"tipo de grade inválido: {tipo!r} (hexagonal ou quadrada)")
    if not (limites.AMC_LADO_M_MIN <= lado_m <= limites.AMC_LADO_M_MAX):
        raise ErroValidacao("lado_invalido",
                            f"lado da célula fora de [{limites.AMC_LADO_M_MIN}, {limites.AMC_LADO_M_MAX}] m")
    _checar_poligono(area_estudo, "$.area_estudo")
    pontos = _coords(area_estudo)
    bbox, _ = _bbox_centroide(pontos)
    cur.execute(
        "SELECT ST_AsEWKT(g) AS wkt, ST_X(ST_Centroid(g)) AS cx, ST_Y(ST_Centroid(g)) AS cy, ST_IsValid(g) AS valida, "
        "ST_Area(g::geography) AS area_geo FROM (SELECT ST_Multi(ST_MakeValid("
        "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))) g) s",
        (json.dumps(area_estudo),),
    )
    r = cur.fetchone()
    if r["area_geo"] is None or r["area_geo"] <= 0:
        raise ErroValidacao("geometria_invalida", "área de estudo sem área (polígono degenerado)")
    if r["area_geo"] / 1e6 > limites.AMC_AREA_ESTUDO_KM2_MAX:
        raise ErroValidacao("area_grande_demais", f"área de estudo de {r['area_geo'] / 1e6:,.0f} km² passa do teto de "
                            f"{limites.AMC_AREA_ESTUDO_KM2_MAX:,} km²", {"km2": r["area_geo"] / 1e6})
    try:
        ficha = crs_mod.ficha_crs(pontos, bbox, (r["cx"], r["cy"]))
    except ValueError as e:
        raise ErroValidacao("crs_fora_da_cobertura", str(e)) from e
    cur.execute("SELECT ST_Area(ST_Transform(ST_GeomFromEWKT(%s), %s)) AS a", (r["wkt"], ficha["srid_trabalho"]))
    area_plano = cur.fetchone()["a"]
    esperado = area_plano / area_celula_m2(tipo, lado_m)
    if esperado > limites.AMC_UNIDADES_MAX:
        raise ErroValidacao("grade_grande_demais", f"≈ {esperado:,.0f} células passam do teto de "
                            f"{limites.AMC_UNIDADES_MAX:,} unidades por conjunto; aumente o lado ou reduza a área",
                            {"contagem_esperada": round(esperado), "teto": limites.AMC_UNIDADES_MAX})
    return {"ficha_crs": ficha, "area_plano_m2": area_plano, "area_geodesica_m2": r["area_geo"],
            "contagem_esperada": esperado, "area_estudo_wkt": r["wkt"]}


# ---------------------------------------------------------------- geração da grade (dentro do job)
def _sql_faixa(tipo: str) -> str:
    funcao = "ST_HexagonGrid" if tipo == "hexagonal" else "ST_SquareGrid"
    # a célula inteira dentro da área entra como está; a de borda é recortada (ST_Intersection); vazias/linhas saem
    return f"""
    WITH a AS (SELECT ST_Transform(area_estudo, %(srid)s) AS g FROM plat.amc_conjunto_unidade WHERE id = %(cid)s),
    faixa AS (SELECT ST_MakeEnvelope(%(xmin)s, %(ymin)s, %(xmax)s, %(ymax)s, %(srid)s) AS b),
    cel AS (SELECT (c).i, (c).j, (c).geom FROM faixa, LATERAL (SELECT {funcao}(%(lado)s, faixa.b) AS c) s),
    rec AS (
      SELECT cel.i, cel.j,
             CASE WHEN ST_Within(cel.geom, a.g) THEN cel.geom ELSE ST_Intersection(cel.geom, a.g) END AS g
      FROM cel, a WHERE ST_Intersects(cel.geom, a.g)
    ),
    lim AS (SELECT i, j, ST_Multi(ST_CollectionExtract(g, 3)) AS g FROM rec)
    INSERT INTO plat.amc_unidade (conjunto_id, tenant_id, unidade_id, geom, area_m2)
    SELECT %(cid)s, %(tid)s, i::text || '_' || j::text, ST_Transform(g, 4326), ST_Area(ST_Transform(g, 4326)::geography)
    FROM lim WHERE NOT ST_IsEmpty(g)
    ON CONFLICT (conjunto_id, unidade_id) DO NOTHING
    """


def _faixas(bbox_plano: tuple[float, float, float, float], area_plano: float, area_cel: float, lado: float) -> list:
    """Divide o bbox (no CRS de trabalho) em faixas horizontais com ≈ FAIXA_CELULAS células cada. A margem de 2 lados
    em cada borda garante que as células que cruzam a divisa apareçam nas duas faixas (a chave deduplica)."""
    xmin, ymin, xmax, ymax = bbox_plano
    n = max(1, math.ceil((area_plano / area_cel) / FAIXA_CELULAS))
    altura = (ymax - ymin) / n
    margem = 2.0 * lado
    return [(xmin - margem, ymin + k * altura - margem, xmax + margem, ymin + (k + 1) * altura + margem)
            for k in range(n)]


def gerar_grade(ctx, conjunto_id: str) -> dict:
    """Corpo do job amc.gerar_unidades. `ctx` é o ContextoJob (ou um equivalente nos testes: db(), progresso(), log(),
    verificar()). Reexecução recomeça do zero (apaga as unidades do conjunto). Devolve a ficha gravada."""
    t0 = time.monotonic()
    with ctx.db() as cur:
        cur.execute(
            "SELECT id, tenant_id, tipo, lado_m, srid_trabalho, estado, ficha, "
            "ST_XMin(t) AS xmin, ST_YMin(t) AS ymin, ST_XMax(t) AS xmax, ST_YMax(t) AS ymax, ST_Area(t) AS area_plano "
            "FROM (SELECT *, ST_Transform(area_estudo, srid_trabalho) AS t "
            "      FROM plat.amc_conjunto_unidade WHERE id = %s) c",
            (conjunto_id,),
        )
        c = cur.fetchone()
        if c is None:
            raise ErroValidacao("conjunto_inexistente", "conjunto de unidades inexistente")
        if c["tipo"] not in TIPOS_GRADE:
            raise ErroValidacao("tipo_invalido", "o job de grade só serve a conjuntos hexagonal/quadrada")
        cur.execute("DELETE FROM plat.amc_unidade WHERE conjunto_id = %s", (conjunto_id,))
    tipo, lado, srid = c["tipo"], float(c["lado_m"]), int(c["srid_trabalho"])
    a_cel = area_celula_m2(tipo, lado)
    faixas = _faixas((c["xmin"], c["ymin"], c["xmax"], c["ymax"]), c["area_plano"], a_cel, lado)
    ctx.log("INFO", f"grade {tipo} lado {lado:g} m em EPSG:{srid}: {len(faixas)} faixa(s), "
                    f"≈ {c['area_plano'] / a_cel:,.0f} células esperadas")
    for k, (xmin, ymin, xmax, ymax) in enumerate(faixas):
        ctx.verificar()
        with ctx.db() as cur:
            cur.execute("SET LOCAL work_mem = '256MB'")
            cur.execute(_sql_faixa(tipo), {"cid": conjunto_id, "tid": c["tenant_id"], "srid": srid, "lado": lado,
                                           "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax})
        ctx.progresso(int(5 + 90 * (k + 1) / len(faixas)), f"faixa {k + 1} de {len(faixas)}")
    with ctx.db() as cur:
        cur.execute("SELECT count(*) AS n, coalesce(sum(area_m2), 0) AS a FROM plat.amc_unidade WHERE conjunto_id = %s",
                    (conjunto_id,))
        r = cur.fetchone()
        ficha = dict(c["ficha"] or {})
        esperado = c["area_plano"] / a_cel
        ficha.update({
            "tipo": tipo, "lado_m": lado, "area_celula_nominal_m2": round(a_cel, 3),
            "area_estudo_plano_m2": round(c["area_plano"], 3),
            "contagem_esperada": round(esperado, 2), "n_unidades": int(r["n"]),
            "desvio_contagem_pct": round((int(r["n"]) - esperado) / esperado * 100.0, 4) if esperado else None,
            "area_total_geodesica_m2": round(float(r["a"]), 3),
            "faixas": len(faixas), "tempo_geracao_s": round(time.monotonic() - t0, 3),
            "funcao": "ST_HexagonGrid" if tipo == "hexagonal" else "ST_SquareGrid",
            "recorte": "célula inteira dentro da área mantida; célula de borda recortada (ST_Intersection)",
        })
        n = int(r["n"])
        if n > limites.AMC_UNIDADES_MAX:
            # `preparar_grade` compara o teto com a ESTIMATIVA área/área-da-célula; a célula de borda entra
            # recortada e o resultado pode passar do teto (o adversário do item mediu 1.000.175 unidades com o
            # teto em 1.000.000). Aqui o teto é conferido sobre a CONTAGEM REAL: passou, limpa e recusa.
            motivo = (f"{n:,} unidades geradas passam do teto de {limites.AMC_UNIDADES_MAX:,} por conjunto (a "
                      f"estimativa antes de gerar era {esperado:,.0f}); aumente o lado ou reduza a área de estudo")
            cur.execute("DELETE FROM plat.amc_unidade WHERE conjunto_id = %s", (conjunto_id,))
            ficha.update({"recusado": True, "motivo_recusa": motivo, "n_unidades_geradas": n, "n_unidades": 0,
                          "teto_unidades": limites.AMC_UNIDADES_MAX, "area_total_geodesica_m2": 0.0})
            cur.execute(
                "UPDATE plat.amc_conjunto_unidade SET estado = 'falhou', n_unidades = 0, area_total_m2 = 0, "
                "ficha = %s, erro = %s, pronto_em = NULL WHERE id = %s",
                (psycopg2.extras.Json(ficha), motivo, conjunto_id),
            )
            ctx.log("ERRO", motivo)
            ctx.progresso(100, "recusado: teto de unidades por conjunto")
            return ficha
        cur.execute(
            "UPDATE plat.amc_conjunto_unidade SET estado = 'pronto', n_unidades = %s, area_total_m2 = %s, ficha = %s, "
            "pronto_em = now(), erro = NULL WHERE id = %s",
            (n, float(r["a"]), psycopg2.extras.Json(ficha), conjunto_id),
        )
    ctx.progresso(100, f"{int(r['n']):,} unidades")
    return ficha


# ---------------------------------------------------------------- feições do usuário (síncrono)
def validar_feicoes(colecao, campo_id: str | None) -> list[tuple[str, dict]]:
    """[(unidade_id, geometria)] com ids únicos e polígonos válidos; id vem de feature.id ou de properties[campo_id]."""
    if not isinstance(colecao, dict) or colecao.get("type") != "FeatureCollection" or \
            not isinstance(colecao.get("features"), list):
        raise ErroValidacao("feicoes_invalidas", "esperado um GeoJSON FeatureCollection em $.feicoes")
    feicoes = colecao["features"]
    if not feicoes:
        raise ErroValidacao("feicoes_invalidas", "FeatureCollection vazia")
    if len(feicoes) > limites.AMC_FEICOES_INLINE_MAX:
        raise ErroValidacao("feicoes_demais", f"{len(feicoes):,} feições passam do teto de "
                            f"{limites.AMC_FEICOES_INLINE_MAX:,} por envio", {"teto": limites.AMC_FEICOES_INLINE_MAX})
    saida = []
    vistos: dict[str, int] = {}
    duplicados: dict[str, list[int]] = {}
    sem_id = []
    for i, f in enumerate(feicoes):
        if not isinstance(f, dict) or f.get("type") != "Feature":
            raise ErroValidacao("feicoes_invalidas", f"$.feicoes.features[{i}] não é um Feature")
        bruto = (f.get("properties") or {}).get(campo_id) if campo_id else f.get("id")
        if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
            sem_id.append(i)
            continue
        uid = str(bruto).strip()
        if len(uid) > 200:
            raise ErroValidacao("feicoes_invalidas", f"$.feicoes.features[{i}]: id com mais de 200 caracteres")
        if uid in vistos:
            duplicados.setdefault(uid, [vistos[uid]]).append(i)
            continue
        vistos[uid] = i
        _checar_poligono(f.get("geometry"), f"$.feicoes.features[{i}].geometry")
        saida.append((uid, f["geometry"]))
    origem = f"properties.{campo_id}" if campo_id else "feature.id"
    if sem_id:
        raise ErroValidacao("feicoes_sem_id", f"{len(sem_id)} feição(ões) sem id em {origem}; toda unidade precisa de "
                            f"id estável (primeiras posições: {sem_id[:10]})",
                            {"posicoes": sem_id[:100], "origem": origem})
    if duplicados:
        lista = sorted(duplicados)
        raise ErroValidacao("feicoes_id_duplicado", f"{len(duplicados)} id(s) repetido(s) em {origem}: "
                            f"{', '.join(lista[:10])}{' …' if len(lista) > 10 else ''}; "
                            f"o id da unidade tem de ser único",
                            {"duplicados": {k: v for k, v in list(duplicados.items())[:100]}, "origem": origem})
    return saida


PAGINA_FEICOES = 500  # feições por comando (mesmo tamanho de lote de antes; agora em UM texto de consulta)

# Consulta em TEXTO de propósito: `psycopg2.extras.execute_values` montaria o comando final em bytes e escaparia da
# reescrita de schema de app/schema_ambiente.py, mandando o literal `plat.` ao servidor mesmo em homologação ou numa
# base por trilha (defeito achado pelo adversário do item L3-01-b em 06/09/2026). O lote entra como UM parâmetro
# jsonb e vira linhas com `jsonb_to_recordset`, o que também evita montar VALUES de tamanho variável.
SQL_GRAVAR_FEICOES = """
INSERT INTO plat.amc_unidade (conjunto_id, tenant_id, unidade_id, geom, area_m2)
SELECT %s::uuid, %s::int, v.uid, g, ST_Area(g::geography)
FROM jsonb_to_recordset(%s::jsonb) AS v(uid text, gj jsonb),
LATERAL (SELECT ST_Multi(ST_CollectionExtract(
           ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(v.gj::text), 4326)), 3)) AS g) s
WHERE NOT ST_IsEmpty(g)
"""


def gravar_feicoes(cur, conjunto_id: str, tenant_id: int, feicoes: list[tuple[str, dict]]) -> dict:
    """Insere as feições (ST_MakeValid, MultiPolygon, 4326) e fecha a ficha (CRS pelo centróide da união dos bboxes)."""
    t0 = time.monotonic()
    for inicio in range(0, len(feicoes), PAGINA_FEICOES):
        lote = [{"uid": uid, "gj": g} for uid, g in feicoes[inicio:inicio + PAGINA_FEICOES]]
        cur.execute(SQL_GRAVAR_FEICOES, (conjunto_id, tenant_id, json.dumps(lote)))
    cur.execute(
        "SELECT n, a, ST_XMin(e) AS xmin, ST_YMin(e) AS ymin, ST_XMax(e) AS xmax, ST_YMax(e) AS ymax, "
        "ST_X(ST_Centroid(e)) AS cx, ST_Y(ST_Centroid(e)) AS cy FROM ("
        "  SELECT count(*) AS n, coalesce(sum(area_m2), 0) AS a, "
        "         ST_SetSRID(ST_Extent(geom)::geometry, 4326) AS e "
        "  FROM plat.amc_unidade WHERE conjunto_id = %s::uuid) s",
        (conjunto_id,),
    )
    r = cur.fetchone()
    if not r["n"]:
        raise ErroValidacao("feicoes_invalidas", "nenhuma feição com área depois de ST_MakeValid")
    pontos = [p for _uid, g in feicoes for p in _coords(g)]
    ficha = crs_mod.ficha_crs(pontos, (r["xmin"], r["ymin"], r["xmax"], r["ymax"]), (r["cx"], r["cy"]))
    ficha.update({"tipo": "feicoes", "n_unidades": int(r["n"]), "feicoes_recebidas": len(feicoes),
                  "feicoes_descartadas_sem_area": len(feicoes) - int(r["n"]),
                  "area_total_geodesica_m2": round(float(r["a"]), 3),
                  "tempo_geracao_s": round(time.monotonic() - t0, 3),
                  "recorte": "feições do usuário como vieram (ST_MakeValid; só a parte poligonal)"})
    cur.execute(
        "UPDATE plat.amc_conjunto_unidade SET estado = 'pronto', srid_trabalho = %s, n_unidades = %s, "
        "area_total_m2 = %s, "
        "ficha = %s, pronto_em = now() WHERE id = %s",
        (ficha["srid_trabalho"], int(r["n"]), float(r["a"]), psycopg2.extras.Json(ficha), conjunto_id),
    )
    return ficha
