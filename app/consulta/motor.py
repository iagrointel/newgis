"""Motor da operação `query` do FeatureServer (item L2-04-c, ADR 0016). Recebe os parâmetros já
normalizados (`PedidoQuery`) e devolve um `Resultado*` — nunca monta o corpo JSON/GeoJSON/PBF aqui
(isso é `app/consulta/serializar.py`); a única responsabilidade deste módulo é gerar SQL parametrizado
e decidir o que a Esri chama de "modo" da consulta (feições, contagem, ids, extensão, estatísticas).

Garantia de segurança (a que não pode falhar): toda cláusula que carrega texto do cliente passa por
`where_ast` (que já é parametrizado) ou por um identificador revalidado pelo regex de `app.consulta.campos`
antes de entrar numa f-string de SQL. Nenhuma outra rota deste módulo aceita string livre do cliente
dentro do texto do SQL — literal de geometria e datas vira parâmetro (`%s`), nunca texto colado."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

import psycopg2
import psycopg2.errors

from app.consulta import campos as campos_mod
from app.consulta import geometria_esri as geo
from app.consulta import quantizacao as quant
from app.consulta import where_ast
from app.erros import ErroAPI

# Erros de TIPO/valor que o Postgres só descobre ao executar (`fid LIKE '1%'` num bigint, `fid = 'abc'`,
# percentil fora de 0-1): a consulta é parametrizada e não tem efeito, mas sem esta rede o cliente veria um
# 500 com o SQL no traceback do servidor. Item L7-03-d: vira 400 nomeado, sem texto do banco na resposta.
_ERROS_DE_CONSULTA = (psycopg2.errors.DataError, psycopg2.errors.UndefinedFunction, psycopg2.errors.DatatypeMismatch,
                      psycopg2.errors.AmbiguousFunction, psycopg2.errors.UndefinedColumn)


def _executar(cur, sql: str, params) -> None:
    try:
        cur.execute(sql, params)
    except _ERROS_DE_CONSULTA as e:
        raise ErroAPI(
            400, "consulta_invalida",
            "consulta recusada pelo banco: tipo ou valor incompatível com o campo (ex.: LIKE em campo numérico)",
            {"classe": type(e).__name__},
        ) from e

MAX_RECORD_COUNT_PADRAO = 2000
MAX_RECORD_COUNT_TETO = 5000
MAX_IDS_SEM_LIMITE = 500_000  # returnIdsOnly não pagina (contrato Esri); teto de segurança nosso
ORDER_DIRECAO_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?$", re.IGNORECASE)


def _bool(v, default=False) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def _int(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError) as e:
        raise ErroAPI(400, "parametro_invalido", f"esperava inteiro: {v!r}") from e


@dataclass
class PedidoQuery:
    """Um campo por parâmetro Esri (nomes da doc, `f` incluído) — ver docs/PARIDADE.md para o
    veredito feito/parcial/fora de cada um, com a URL e a data de acesso registradas no item."""

    where: str | None = None
    objectIds: str | None = None
    geometry: str | None = None
    geometryType: str | None = None
    inSR: str | None = None
    spatialRel: str = "esriSpatialRelIntersects"
    relationParam: str | None = None
    distance: float = 0.0
    units: str = "esriSRUnit_Meter"
    time: str | None = None
    outFields: str = "*"
    returnGeometry: bool = True
    maxAllowableOffset: float | None = None
    geometryPrecision: int | None = None
    defaultSR: str | None = None
    outSR: str | None = None
    havingClause: str | None = None
    gdbVersion: str | None = None
    returnDistinctValues: bool = False
    returnIdsOnly: bool = False
    returnCountOnly: bool = False
    returnExtentOnly: bool = False
    orderByFields: str | None = None
    groupByFieldsForStatistics: str | None = None
    outStatistics: str | None = None
    returnZ: bool = False
    returnM: bool = False
    multipatchOption: str | None = None
    resultOffset: int | None = None
    resultRecordCount: int | None = None
    quantizationParameters: str | None = None
    returnCentroid: bool = False
    resultType: str | None = None
    historicMoment: str | None = None
    returnTrueCurves: bool = False
    sqlFormat: str = "standard"
    returnExceededLimitFeatures: bool = True
    datumTransformation: str | None = None
    timeReferenceUnknownClient: bool = False
    returnEnvelope: bool = False
    fullText: str | None = None
    uniqueIds: str | None = None
    returnUniqueIdsOnly: bool = False
    resultPaginationToken: str | None = None
    f: str = "json"


@dataclass
class ResultadoFeatures:
    modo: str  # "features" | "estatisticas"
    campos_saida: list  # [{"nome","tipo_esri","alias"}]
    objectIdFieldName: str
    globalIdFieldName: str | None
    geometryType: str | None
    spatialReference: int
    features: list  # [{"attributes": {...}, "geometry": dict|None, "centroid": dict|None}]
    exceededTransferLimit: bool
    hasZ: bool
    hasM: bool
    extent: dict | None = None
    resultPaginationToken: str | None = None
    transform: object | None = None  # quantizacao.Quantizacao, se pedido


@dataclass
class ResultadoCount:
    count: int


@dataclass
class ResultadoIds:
    objectIdFieldName: str
    objectIds: list


@dataclass
class ResultadoExtent:
    extent: dict | None
    count: int | None = None


def _outfields(p: PedidoQuery, meta: list[dict]) -> list[dict]:
    # a Esri inclui o campo de OID (e o globalid, se houver) dentro de `attributes` mesmo com
    # outFields="*" — objectIdFieldName/globalIdFieldName só dizem QUAL desses campos tem esse papel
    disponiveis = {c["nome"]: c for c in meta}
    if (p.outFields or "*").strip() == "*":
        return list(meta)
    nomes = [n.strip() for n in p.outFields.split(",") if n.strip()]
    saida = []
    for n in nomes:
        if n not in disponiveis:
            raise ErroAPI(400, "campo_desconhecido", f"outFields: campo inexistente: {n!r}", {"campo": n})
        saida.append(disponiveis[n])
    return saida


def _order_by(p: PedidoQuery, colunas_sql: dict, oid_sql: str) -> tuple[str, list[tuple[str, str]]]:
    """Devolve (`ORDER BY ...` pronto, [(coluna_sql, direcao), ...]) — sempre com o OID como
    desempate final para que a paginação seja determinística (exigência do portão)."""
    pares: list[tuple[str, str]] = []
    if p.orderByFields:
        for parte in p.orderByFields.split(","):
            parte = parte.strip()
            if not parte or not ORDER_DIRECAO_RE.match(parte):
                raise ErroAPI(400, "orderby_invalido", f"orderByFields inválido: {parte!r}")
            bits = parte.split()
            nome = bits[0]
            direcao = bits[1].upper() if len(bits) > 1 else "ASC"
            if nome not in colunas_sql:
                raise ErroAPI(400, "campo_desconhecido", f"orderByFields: campo inexistente: {nome!r}")
            pares.append((colunas_sql[nome], direcao))
    if not any(c == oid_sql for c, _ in pares):
        pares.append((oid_sql, "ASC"))
    clausula = "ORDER BY " + ", ".join(f"{c} {d}" for c, d in pares)
    return clausula, pares


def _token_codificar(pares_valores: list) -> str:
    return base64.urlsafe_b64encode(json.dumps(pares_valores, default=str).encode()).decode()


def _token_decodificar(token: str) -> list:
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception as e:  # noqa: BLE001 — qualquer token ilegível é erro do cliente, não 500
        raise ErroAPI(400, "token_invalido", "resultPaginationToken ilegível ou corrompido") from e


def _clausula_where(p: PedidoQuery, colunas_sql: dict) -> tuple[list, list]:
    clausulas: list[str] = []
    params: list = []
    if p.sqlFormat and p.sqlFormat != "standard":
        raise ErroAPI(422, "sqlformat_fora", "sqlFormat só suporta 'standard' (dialeto nativo do banco é recusado)")
    if p.gdbVersion and p.gdbVersion not in ("SDE.DEFAULT", "DEFAULT"):
        raise ErroAPI(422, "gdbversion_fora", "camada não versionada: só SDE.DEFAULT é aceito")
    if p.historicMoment:
        raise ErroAPI(422, "historicmoment_fora", "camada sem arquivo histórico (branch versioning); ver L2-03-d")
    if p.time:
        raise ErroAPI(422, "time_fora", "camada sem timeInfo configurado nesta implementação")
    if p.where and p.where.strip() not in ("1=1", ""):
        try:
            c = where_ast.compilar_where(p.where, colunas_sql)
        except where_ast.ErroWhere as e:
            raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
        clausulas.append(c.sql)
        params.extend(c.params)
    # uniqueIds (11.5) filtra pelo campo de unicidade — nesta implementação uniqueIdField ==
    # objectIdFieldName (fid, declarado no PARIDADE.md: sem campo de unicidade separado do OID),
    # por isso o filtro é o mesmo de objectIds; aceitar os dois juntos soma os conjuntos (OR)
    for nome_param in ("objectIds", "uniqueIds"):
        bruto = getattr(p, nome_param)
        if not bruto:
            continue
        try:
            ids = [int(x) for x in bruto.split(",") if x.strip() != ""]
        except ValueError as e:
            raise ErroAPI(400, f"{nome_param.lower()}_invalido",
                           f"{nome_param} precisa ser lista de inteiros separada por vírgula") from e
        if ids:
            clausulas.append(f'{colunas_sql["fid"]} = ANY(%s)')
            params.append(ids)
    return clausulas, params


def _clausula_espacial(p: PedidoQuery, srid_nativo: int) -> tuple[str | None, list]:
    if not p.geometry:
        return None, []
    obj, tipo = geo.parse_geometry(p.geometry, p.geometryType)
    n_vert = geo.contar_vertices(obj, tipo)
    if n_vert > geo.MAX_VERTICES:
        raise ErroAPI(
            413, "geometria_grande_demais", f"geometria de filtro com {n_vert} vértices (teto {geo.MAX_VERTICES})"
        )
    in_sr = geo.sr_wkid(p.inSR) or geo.sr_wkid(p.defaultSR) or srid_nativo
    wkt = geo.para_ewkt(obj, tipo, in_sr)
    rel = p.spatialRel or "esriSpatialRelIntersects"
    op = geo.SPATIAL_REL.get(rel)
    if op is None:
        raise ErroAPI(400, "spatialrel_invalido", f"spatialRel não reconhecido: {rel!r}")
    filtro_sql = "ST_Transform(ST_GeomFromEWKT(%s), %s)"
    params = [wkt, srid_nativo]
    dist_m = float(p.distance or 0)
    if dist_m > 0:
        fator = geo.UNIDADES_METROS.get(p.units or "esriSRUnit_Meter")
        if fator is None:
            raise ErroAPI(400, "unidade_invalida", f"units não reconhecido: {p.units!r}")
        metros = dist_m * fator
        filtro_sql = f"ST_Transform(ST_Buffer(ST_Transform({filtro_sql}, 4326)::geography, %s)::geometry, %s)"
        params += [metros, srid_nativo]
    if rel == "esriSpatialRelEnvelopeIntersects":
        return f"ST_Intersects(ST_Envelope(geom), ST_Envelope({filtro_sql}))", params
    if rel == "esriSpatialRelRelation":
        padrao = p.relationParam or ""
        if not re.fullmatch(r"[0-9FT*]{9}", padrao):
            raise ErroAPI(400, "relationparam_invalido", "relationParam precisa ser um padrão DE-9IM de 9 caracteres")
        return f"ST_Relate(geom, {filtro_sql}, %s)", [*params, padrao]
    return f"{op}(geom, {filtro_sql})", params


def _clausula_fulltext(p: PedidoQuery, meta: list[dict]) -> tuple[str | None, list]:
    """11.4: `to_tsvector('simple', unaccent(coalesce(campo,''))) @@ plainto_tsquery('simple', unaccent(termo))`
    em todo campo de texto — dialeto 'simple' (sem stemming de idioma) para não perder correspondência
    em nome próprio/código, `unaccent` para o acervo em português."""
    if not p.fullText:
        return None, []
    textos = campos_mod.campos_texto(meta)
    if not textos:
        raise ErroAPI(422, "fulltext_sem_campo_texto", "camada sem campo de texto para fullText")
    partes = [
        f"to_tsvector('simple', unaccent(coalesce(\"{n}\", ''))) @@ plainto_tsquery('simple', unaccent(%s))"
        for n in textos
    ]
    params = [p.fullText] * len(partes)
    return "(" + " OR ".join(partes) + ")", params


def preparar_pedido(p: PedidoQuery, meta: list[dict], srid_nativo: int) -> dict:
    """Monta as peças SQL comuns a todos os modos (where, filtro espacial, fullText, lista branca,
    outFields) — chamado uma vez por pedido; os modos (feições/contagem/ids/extensão/estatísticas)
    reaproveitam o resultado."""
    colunas_sql = campos_mod.lista_branca(meta)
    clausulas, params = _clausula_where(p, colunas_sql)
    esp_sql, esp_params = _clausula_espacial(p, srid_nativo)
    if esp_sql:
        clausulas.append(esp_sql)
        params += esp_params
    ft_sql, ft_params = _clausula_fulltext(p, meta)
    if ft_sql:
        clausulas.append(ft_sql)
        params += ft_params
    where_final = " AND ".join(f"({c})" for c in clausulas) if clausulas else "TRUE"
    return {"colunas_sql": colunas_sql, "where_sql": where_final, "where_params": params}


def executar_count(cur, schema: str, tabela: str, prep: dict) -> ResultadoCount:
    _executar(cur, f'SELECT count(*) AS n FROM "{schema}"."{tabela}" WHERE {prep["where_sql"]}', prep["where_params"])
    return ResultadoCount(count=int(cur.fetchone()["n"]))


def executar_ids(cur, schema: str, tabela: str, prep: dict) -> ResultadoIds:
    sql = f'SELECT fid FROM "{schema}"."{tabela}" WHERE {prep["where_sql"]} ORDER BY fid LIMIT %s'
    _executar(cur, sql, [*prep["where_params"], MAX_IDS_SEM_LIMITE + 1])
    linhas = cur.fetchall()
    if len(linhas) > MAX_IDS_SEM_LIMITE:
        raise ErroAPI(413, "resultado_grande_demais", f"mais de {MAX_IDS_SEM_LIMITE} ids; filtre mais")
    return ResultadoIds(objectIdFieldName="fid", objectIds=[r["fid"] for r in linhas])


def executar_extent(cur, schema: str, tabela: str, prep: dict, srid_saida: int, com_count: bool) -> ResultadoExtent:
    _executar(cur,
        f'SELECT ST_Extent(ST_Transform(geom, %s)) AS ext, count(*) AS n '
        f'FROM "{schema}"."{tabela}" WHERE {prep["where_sql"]}',
        [srid_saida, *prep["where_params"]],
    )
    r = cur.fetchone()
    extent = None
    if r["ext"]:
        m = re.match(r"BOX\(([-\d.eE]+) ([-\d.eE]+),([-\d.eE]+) ([-\d.eE]+)\)", r["ext"])
        if m:
            xmin, ymin, xmax, ymax = (float(x) for x in m.groups())
            extent = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "spatialReference": {"wkid": srid_saida}}
    return ResultadoExtent(extent=extent, count=int(r["n"]) if com_count else None)


_STAT_FUNC = {
    "count": "count", "sum": "sum", "min": "min", "max": "max", "avg": "avg", "stddev": "stddev", "var": "variance",
    "percentile_cont": "percentile_cont", "percentile_disc": "percentile_disc",
}
_IDENT_SIMPLES = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _outstatistics_sql(outStatistics: str, groupBy: str | None, colunas_sql: dict) -> tuple[list, list, dict]:
    try:
        specs = json.loads(outStatistics)
    except json.JSONDecodeError as e:
        raise ErroAPI(400, "outstatistics_invalido", "outStatistics precisa ser JSON") from e
    if not isinstance(specs, list) or not specs:
        raise ErroAPI(400, "outstatistics_invalido", "outStatistics precisa ser uma lista não vazia")
    grupos_sql = []
    grupos_saida = []
    if groupBy:
        for nome in (n.strip() for n in groupBy.split(",") if n.strip()):
            if nome not in colunas_sql:
                raise ErroAPI(400, "campo_desconhecido", f"groupByFieldsForStatistics: campo inexistente {nome!r}")
            grupos_sql.append(colunas_sql[nome])
            grupos_saida.append(nome)
    selects = list(grupos_sql)
    aliases = {n: colunas_sql[n] for n in grupos_saida}  # grupos entram na lista branca do havingClause também
    saida_meta = [{"nome": n, "tipo_esri": "esriFieldTypeString"} for n in grupos_saida]
    for spec in specs:
        tipo = str(spec.get("statisticType", "")).lower()
        campo = spec.get("onStatisticField")
        alias = spec.get("outStatisticFieldName") or f"{tipo}_{campo}"
        if not _IDENT_SIMPLES.match(alias):
            raise ErroAPI(400, "outstatistics_invalido", f"outStatisticFieldName inválido: {alias!r}")
        if tipo == "count" and (not campo or campo == "*"):
            expr = "count(*)"
        else:
            if campo not in colunas_sql:
                raise ErroAPI(400, "campo_desconhecido", f"outStatistics: campo inexistente {campo!r}")
            func = _STAT_FUNC.get(tipo)
            if func is None:
                raise ErroAPI(422, "statistictype_fora", f"statisticType não suportado: {tipo!r}")
            if func in ("percentile_cont", "percentile_disc"):
                try:
                    pct = float((spec.get("statisticParameters") or {}).get("value", 0.5))
                except (TypeError, ValueError) as e:
                    raise ErroAPI(400, "outstatistics_invalido", "statisticParameters.value precisa ser número") from e
                if not 0.0 <= pct <= 1.0:
                    raise ErroAPI(400, "outstatistics_invalido", "statisticParameters.value precisa estar entre 0 e 1")
                expr = f"{func}({pct}) WITHIN GROUP (ORDER BY {colunas_sql[campo]})"
            else:
                expr = f"{func}({colunas_sql[campo]})"
        selects.append(f'{expr} AS "{alias}"')
        # HAVING não pode referenciar o alias da SELECT (Postgres avalia HAVING antes da lista de
        # projeção — testado com dado real: "column ... does not exist"); a lista branca do
        # havingClause aponta para a EXPRESSÃO agregada de novo, nunca para texto do usuário
        aliases[alias] = expr
        saida_meta.append({"nome": alias, "tipo_esri": "esriFieldTypeDouble"})
    return selects, grupos_sql, {"aliases": aliases, "saida_meta": saida_meta, "grupos_saida": grupos_saida}


def executar_estatisticas(
    cur, schema: str, tabela: str, prep: dict, p: PedidoQuery, srid_saida: int
) -> ResultadoFeatures:
    selects, grupos_sql, info = _outstatistics_sql(
        p.outStatistics, p.groupByFieldsForStatistics, prep["colunas_sql"]
    )
    sql = f'SELECT {", ".join(selects)} FROM "{schema}"."{tabela}" WHERE {prep["where_sql"]}'
    params = list(prep["where_params"])
    if grupos_sql:
        sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(grupos_sql)))
    if p.havingClause:
        try:
            h = where_ast.compilar_where(p.havingClause, info["aliases"])
        except where_ast.ErroWhere as e:
            raise ErroAPI(400, e.codigo, e.mensagem, e.detalhe) from e
        sql += f" HAVING {h.sql}"
        params += h.params
    _executar(cur, sql, params)
    linhas = cur.fetchall()
    features = [{"attributes": dict(r), "geometry": None, "centroid": None} for r in linhas]
    return ResultadoFeatures(
        modo="estatisticas", campos_saida=info["saida_meta"], objectIdFieldName="", globalIdFieldName=None,
        geometryType=None, spatialReference=srid_saida, features=features, exceededTransferLimit=False,
        hasZ=False, hasM=False,
    )


def executar_features(cur, schema: str, tabela: str, prep: dict, p: PedidoQuery, meta: list[dict],
                       srid_nativo: int, geometria_tipo_esri: str | None) -> ResultadoFeatures:
    colunas_sql = prep["colunas_sql"]
    saida_meta = _outfields(p, meta)
    if p.returnDistinctValues:
        saida_meta = [c for c in saida_meta if c["nome"] not in ("fid", "globalid")]
    srid_saida = geo.sr_wkid(p.outSR) or srid_nativo
    retorna_geom = p.returnGeometry and not p.returnDistinctValues
    max_rec = min(p.resultRecordCount or MAX_RECORD_COUNT_PADRAO, MAX_RECORD_COUNT_TETO)
    if p.resultRecordCount and p.resultRecordCount > MAX_RECORD_COUNT_TETO:
        max_rec = MAX_RECORD_COUNT_TETO

    order_clause, order_pares = _order_by(p, colunas_sql, colunas_sql["fid"])
    where_sql = prep["where_sql"]
    params = list(prep["where_params"])

    token_pode = order_pares and all(d == "ASC" for _, d in order_pares) and not p.resultOffset
    if p.resultPaginationToken:
        if not token_pode:
            raise ErroAPI(
                422, "paginationtoken_fora", "resultPaginationToken exige orderBy só ascendente (ou padrão fid)"
            )
        valores = _token_decodificar(p.resultPaginationToken)
        if len(valores) != len(order_pares):
            raise ErroAPI(400, "token_invalido", "resultPaginationToken não confere com orderByFields do pedido")
        cols = ", ".join(c for c, _ in order_pares)
        marcadores = ", ".join(["%s"] * len(valores))
        where_sql = f"({where_sql}) AND ROW({cols}) > ROW({marcadores})"
        params = params + valores

    # returnDistinctValues nunca inclui o OID: `fid` é único por linha e a distinção de qualquer
    # combinação de atributos nunca aconteceria com ele na projeção (comportamento real da Esri:
    # a operação ignora o campo de OID quando returnDistinctValues=true)
    if p.returnDistinctValues:
        campos_select = [f'"{c["nome"]}"' for c in saida_meta if c["nome"] not in ("fid", "globalid")]
        if not campos_select:
            raise ErroAPI(
                422, "outfields_obrigatorio",
                "returnDistinctValues exige outFields com pelo menos 1 campo além de OID/globalid",
            )
    else:
        campos_select = ['"fid"'] + [f'"{c["nome"]}"' for c in saida_meta if c["nome"] != "fid"]
    if retorna_geom:
        geom_expr = "geom"
        if p.maxAllowableOffset:
            geom_expr = f"ST_SimplifyPreserveTopology({geom_expr}, %s)"
        if srid_saida != srid_nativo:
            geom_expr = f"ST_Transform({geom_expr}, %s)"
        geom_expr = f"ST_AsGeoJSON({geom_expr}) AS _geom"
    if p.returnCentroid:
        cent_expr = "ST_Centroid(geom)"
        if srid_saida != srid_nativo:
            cent_expr = f"ST_Transform({cent_expr}, %s)"
        cent_expr = f"ST_AsGeoJSON({cent_expr}) AS _centroid"

    distinct = "DISTINCT " if p.returnDistinctValues else ""
    select_parts = campos_select[:]
    # ordem dos parâmetros tem de seguir a ordem em que os "%s" aparecem NO TEXTO final do SQL:
    # primeiro os do SELECT (geometria/centroide), depois os do WHERE, por fim LIMIT/OFFSET
    select_params = []
    if retorna_geom:
        select_parts.append(geom_expr)
        if p.maxAllowableOffset:
            select_params.append(float(p.maxAllowableOffset))
        if srid_saida != srid_nativo:
            select_params.append(srid_saida)
    if p.returnCentroid:
        select_parts.append(cent_expr)
        if srid_saida != srid_nativo:
            select_params.append(srid_saida)
    sql = f'SELECT {distinct}{", ".join(select_parts)} FROM "{schema}"."{tabela}" WHERE {where_sql}'
    if not p.returnDistinctValues:
        sql += f" {order_clause}"
    sql += " LIMIT %s OFFSET %s"
    limite = max_rec + 1
    offset = int(p.resultOffset or 0)
    _executar(cur, sql, [*select_params, *params, limite, offset])
    linhas = cur.fetchall()
    excedeu = len(linhas) > max_rec
    linhas = linhas[:max_rec]
    # returnExceededLimitFeatures=false (default é true): quando o teto seria excedido, a Esri
    # devolve ZERO feições em vez de uma página truncada — `exceededTransferLimit` continua true
    if excedeu and not p.returnExceededLimitFeatures:
        linhas = []

    quantizador = None
    if p.quantizationParameters:
        try:
            qobj = json.loads(p.quantizationParameters)
        except json.JSONDecodeError as e:
            raise ErroAPI(400, "quantizacao_invalida", "quantizationParameters precisa ser JSON") from e
        quantizador = quant.parse(qobj)

    precisao = p.geometryPrecision

    def _formatar_coord(x, y):
        if precisao is not None:
            x, y = round(x, precisao), round(y, precisao)
        if quantizador:
            return list(quantizador.quantizar(x, y))
        return [x, y]

    features = []
    for r in linhas:
        attrs = {}
        for c in saida_meta:
            v = r.get(c["nome"])
            if c["tipo_esri"] == "esriFieldTypeSmallInteger" and isinstance(v, bool):
                v = 1 if v else 0
            attrs[c["nome"]] = v
        geometria = None
        if retorna_geom and r.get("_geom") is not None:
            geometria = _geojson_para_esri(r["_geom"], geometria_tipo_esri, _formatar_coord)
        centroide = None
        if p.returnCentroid and r.get("_centroid") is not None:
            cx, cy = _extrair_xy_geojson(r["_centroid"])
            centroide = {"x": cx, "y": cy}
        features.append({"attributes": attrs, "geometry": geometria, "centroid": centroide})

    resultado = ResultadoFeatures(
        modo="features", campos_saida=saida_meta, objectIdFieldName="fid",
        globalIdFieldName="globalid" if any(c["nome"] == "globalid" for c in meta) else None,
        geometryType=geometria_tipo_esri if retorna_geom else None,
        spatialReference=srid_saida, features=features, exceededTransferLimit=excedeu,
        hasZ=p.returnZ, hasM=False, transform=quantizador,
    )
    if excedeu and token_pode and features:
        # o token guarda o valor de cada coluna de ordenação NA ÚLTIMA linha devolvida (RealDict,
        # por nome de coluna — nunca pelo SQL da expressão, que pode ter alias/cast)
        ultima = linhas[len(features) - 1]
        valores_tok = [ultima.get(col_sql.split(".")[-1].strip('"')) for col_sql, _ in order_pares]
        resultado.resultPaginationToken = _token_codificar(valores_tok)
    return resultado


def _extrair_xy_geojson(geojson_str: str) -> tuple[float, float]:
    obj = json.loads(geojson_str)
    c = obj["coordinates"]
    return float(c[0]), float(c[1])


def _geojson_para_esri(geojson_str: str, tipo_esri: str | None, formatar):
    obj = json.loads(geojson_str)
    t = obj["type"]
    coords = obj["coordinates"]
    if t == "Point":
        x, y = formatar(coords[0], coords[1])
        return {"x": x, "y": y}
    if t == "MultiPoint":
        return {"points": [formatar(p[0], p[1]) for p in coords]}
    if t in ("LineString",):
        return {"paths": [[formatar(p[0], p[1]) for p in coords]]}
    if t == "MultiLineString":
        return {"paths": [[formatar(p[0], p[1]) for p in linha] for linha in coords]}
    if t == "Polygon":
        return {"rings": [[formatar(p[0], p[1]) for p in anel] for anel in coords]}
    if t == "MultiPolygon":
        aneis = []
        for poligono in coords:
            aneis.extend([formatar(p[0], p[1]) for p in anel] for anel in poligono)
        return {"rings": aneis}
    raise ErroAPI(500, "geometria_nao_convertida", f"tipo GeoJSON sem conversão Esri: {t}")  # pragma: no cover
