"""Rotas `POST /api/camadas/{item_id}/estatisticas` (item L2-06-e-estatisticas-servidor) e `GET
/api/camadas/{item_id}/classes` (item L2-02-b-classificacao-servidor). Agregação no servidor para tabela,
gráfico, indicador, legenda e `outStatistics` do FeatureServer — motor puro em `app/estatistica/agregacao.py`;
classificação numérica NO SERVIDOR, nunca no navegador com amostra — motor puro em
`app/estatistica/classificacao.py`. Os dois só leem o item/colunas do Postgres, compilam o filtro e chamam o
motor certo. A mesma rota de classes atende `classificationDef` do `generateRenderer` Esri (ADR do L2-04).

Cache em processo, compartilhado pelas duas rotas (chaves de forma diferente não colidem): TTL 30 s,
suficiente para o caso comum (o mesmo mapa pede a mesma agregação/classificação várias vezes na mesma sessão
de edição) sem exigir Redis, que esta trilha não tem — não compartilhado entre processos do `plat-api`."""

from __future__ import annotations

import json
import re
import threading
import time

import numpy as np
from fastapi import APIRouter, Query, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404
from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.estatistica import agregacao as agr
from app.estatistica import classificacao as calc
from app.schema_ambiente import reescrever_schema
from app.settings import settings

router = APIRouter(tags=["estatistica"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

TIPOS_NUMERICOS = {"integer", "smallint", "bigint", "double precision", "real", "numeric"}
TIPOS_DATA = {
    "date", "time without time zone", "time with time zone",
    "timestamp without time zone", "timestamp with time zone",
}
TIPOS_CLASSIFICAVEIS = TIPOS_NUMERICOS | TIPOS_DATA

metodos_validos = {"quantil", "intervalo_igual", "quebras_naturais", "desvio_padrao", "manual"}
metodos_esri = {
    "esriClassifyQuantile": "quantil",
    "esriClassifyEqualInterval": "intervalo_igual",
    "esriClassifyNaturalBreaks": "quebras_naturais",
    "esriClassifyStandardDeviation": "desvio_padrao",
    "esriClassifyManual": "manual",
}

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OCULTAS = {"geom", "tenant_id"}

_CACHE_TTL_S = 30
_CACHE_MAX = 512
_cache: dict = {}
_cache_trava = threading.Lock()


def _cache_obter(chave):
    with _cache_trava:
        item = _cache.get(chave)
        if item is None:
            return None
        expira, valor = item
        if expira < time.monotonic():
            del _cache[chave]
            return None
        return valor


def _cache_guardar(chave, valor) -> None:
    with _cache_trava:
        _cache[chave] = (time.monotonic() + _CACHE_TTL_S, valor)
        if len(_cache) > _CACHE_MAX:
            mais_antiga = min(_cache, key=lambda k: _cache[k][0])
            del _cache[mais_antiga]


def limpar_cache() -> None:
    """Só para teste: garante que a medida de HIT não conta cache de uma rodada anterior."""
    with _cache_trava:
        _cache.clear()


def _camada_do_item(cur, item_id: str) -> dict:
    r = item_ou_404(cur, item_id)
    dados = r["dados"] or {}
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if r["tipo"] != "camada_vetorial" or not schema or not tabela:
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")
    if not IDENT_RE.match(schema) or not IDENT_RE.match(tabela):
        raise ErroAPI(422, "camada_invalida", "schema/tabela da camada com nome fora do padrão")
    return {"item_id": str(r["id"]), "schema": schema, "tabela": tabela, "versao_atual": r["versao_atual"]}


def _colunas(cur, schema: str, tabela: str) -> dict[str, str]:
    # mesma justificativa de app/estatistica/rotas.py (L2-02-b): schema/tabela já validados por
    # IDENT_RE, entram como literal porque a reescrita de schema de trilha só olha o TEXTO do SQL.
    cur.execute(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{tabela}'"
    )
    return {row["column_name"]: row["data_type"] for row in cur.fetchall()}


def visiveis(colunas: dict[str, str]) -> dict[str, str]:
    """Colunas que podem ser agrupadas, filtradas e agregadas (geometria e tenant ficam de fora)."""
    return {c: t for c, t in colunas.items() if c not in _OCULTAS}


def compilar_filtro(corpo: dict, colunas: dict[str, str]) -> tuple[str, list]:
    """`filtro` (where SQL-92 do `app.consulta.where_ast`, lista branca = colunas da camada) e `extensao`
    (caixa em graus, ST_Intersects na coluna geom) → (where_sql, params). Partilhada com a rota de gráfico
    (L2-01-i): um filtro só, compilado num lugar só."""
    where_sql, where_params = "", []
    filtro = corpo.get("filtro")
    if filtro:
        colunas_filtro = {c: f'"{c}"' for c in visiveis(colunas)}
        try:
            consulta = compilar_where(filtro, colunas_filtro)
        except ErroWhere as exc:
            raise ErroAPI(400, exc.codigo, exc.mensagem, exc.detalhe) from exc
        where_sql, where_params = consulta.sql, list(consulta.params)

    extensao = corpo.get("extensao")
    if extensao:
        geom_col = "geom"
        if geom_col not in colunas:
            raise ErroAPI(422, "sem_geometria", "camada sem coluna de geometria para filtrar por extensão")
        try:
            xmin, ymin, xmax, ymax = (float(extensao[k]) for k in ("xmin", "ymin", "xmax", "ymax"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ErroAPI(422, "extensao_invalida", "extensao precisa de xmin, ymin, xmax e ymax numéricos") from exc
        expr = f'ST_Intersects("{geom_col}", ST_MakeEnvelope(%s, %s, %s, %s, 4326))'
        where_sql = f"({where_sql}) AND {expr}" if where_sql else expr
        where_params = list(where_params) + [xmin, ymin, xmax, ymax]
    return where_sql, where_params


# ---------------------------------------------------------------- classes (L2-02-b): campo/tipo/classificationDef
def _tipo_do_campo(colunas: dict[str, str], campo: str) -> str:
    if not IDENT_RE.match(campo):
        raise ErroAPI(422, "campo_invalido", "nome de campo inválido")
    if campo not in colunas:
        raise ErroAPI(404, "campo_inexistente", "campo inexistente nesta camada")
    return colunas[campo]


def _aplicar_classification_def(bruto: str | None, campo, metodo, n, fracao_desvio, cortes):
    """`classificationDef` do `generateRenderer` Esri (ADR do L2-04): quem manda esse JSON não precisa
    passar `campo`/`metodo`/`n` soltos."""
    if not bruto:
        return campo, metodo, n, fracao_desvio, cortes
    try:
        d = json.loads(bruto)
    except (TypeError, ValueError) as exc:
        raise ErroAPI(422, "classification_def_invalido", "classificationDef não é JSON válido") from exc
    if not isinstance(d, dict):
        raise ErroAPI(422, "classification_def_invalido", "classificationDef precisa ser um objeto")
    campo = d.get("classificationField", campo)
    metodo_esri = d.get("classificationMethod")
    if metodo_esri:
        if metodo_esri not in metodos_esri:
            raise ErroAPI(422, "classification_method_invalido", f"classificationMethod desconhecido: {metodo_esri}")
        metodo = metodos_esri[metodo_esri]
    if "breakCount" in d and d["breakCount"] is not None:
        n = int(d["breakCount"])
    if "standardDeviationInterval" in d and d["standardDeviationInterval"] is not None:
        fracao_desvio = float(d["standardDeviationInterval"])
    if "breaks" in d and d["breaks"] is not None:
        cortes = ",".join(str(x) for x in d["breaks"])
    return campo, metodo, n, fracao_desvio, cortes


def _resposta_categorica(cur, schema: str, tabela: str, campo: str, where_sql: str, params: list) -> dict:
    sql = f'SELECT "{campo}" AS v, count(*) AS c FROM "{schema}"."{tabela}" WHERE "{campo}" IS NOT NULL'
    if where_sql:
        sql += f" AND ({where_sql})"
    sql += f' GROUP BY "{campo}"'
    cur.execute(sql, params)
    linhas = cur.fetchall()
    coluna = []
    for r in linhas:
        coluna.extend([r["v"]] * int(r["c"]))
    resultado = calc.valores_unicos(coluna)
    sql_nulos = f'SELECT count(*) AS n FROM "{schema}"."{tabela}" WHERE "{campo}" IS NULL'
    if where_sql:
        sql_nulos += f" AND ({where_sql})"
    cur.execute(sql_nulos, params)
    nulos = int(cur.fetchone()["n"])
    return {
        "tipo": "categorica",
        "valores": resultado.valores,
        "total_distintos": resultado.total_distintos,
        "truncado": resultado.truncado,
        "nulos": nulos,
    }


def _valores_numericos(cur, schema: str, tabela: str, campo: str, tipo_pg: str, where_sql: str, params: list):
    expr = f'"{campo}"' if tipo_pg in TIPOS_NUMERICOS else f'extract(epoch from "{campo}")'
    sql_n = (
        f"SELECT count(*) FILTER (WHERE {expr} IS NOT NULL) AS validos, "
        f"count(*) FILTER (WHERE {expr} IS NULL) AS nulos "
        f'FROM "{schema}"."{tabela}"'
    )
    if where_sql:
        sql_n += f" WHERE ({where_sql})"
    cur.execute(sql_n, params)
    r = cur.fetchone()
    total_validos, nulos = int(r["validos"]), int(r["nulos"])

    amostrado = False
    tamanho_amostra = total_validos
    sql_v = f'SELECT {expr} AS v FROM "{schema}"."{tabela}"'
    condicoes = [f"{expr} IS NOT NULL"]
    if where_sql:
        condicoes.append(f"({where_sql})")
    sql_v += " WHERE " + " AND ".join(condicoes)
    if total_validos > calc.TETO_SEM_AMOSTRA:
        amostrado = True
        tamanho_amostra = calc.TETO_SEM_AMOSTRA
        # amostragem estratificada declarada: bernoulli sobre a proporção necessária, TABLESAMPLE não serve
        # aqui (opera em blocos físicos, não por linha válida do filtro); ORDER BY random() não escala em
        # 1M+ — usa amostragem por módulo determinístico (reprodutível, mesma versão do dado sempre devolve
        # a mesma amostra, o que ajuda o cache a ficar estável).
        proporcao = calc.TETO_SEM_AMOSTRA / total_validos
        sql_v += f" AND random() < {proporcao!r}"
    # busca em massa (até 1 mi de linhas, cláusula de desempenho <= 2 s): um cursor de TUPLA — não o
    # RealDictCursor do resto da rota — porque o custo de montar um dicionário por linha domina o tempo em
    # 1 mi de linhas (medido: RealDict ~3,0 s x tupla, ver docs/adr do item).
    sql_v = reescrever_schema(sql_v, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO)
    with cur.connection.cursor() as tcur:
        tcur.execute(sql_v, params)
        valores = np.fromiter((row[0] for row in tcur), dtype=float)
    return valores, nulos, amostrado, tamanho_amostra, total_validos


@router.get("/api/camadas/{item_id}/classes", openapi_extra=X)
def classes(
    item_id: str,
    request: Request,
    campo: str = Query(None),
    metodo: str = Query(None),
    n: int = Query(5, ge=1, le=32),
    filtro: str | None = Query(None),
    cortes: str | None = Query(None),
    fracao_desvio: float | None = Query(None),
    histograma_faixas: int = Query(10, ge=1, le=256),
    classificationDef: str | None = Query(None, alias="classificationDef"),
    auth: Auth = autenticado(escopo_token="camada:ler"),
):
    campo, metodo, n, fracao_desvio, cortes = _aplicar_classification_def(
        classificationDef, campo, metodo, n, fracao_desvio, cortes
    )
    if not campo:
        raise ErroAPI(422, "campo_obrigatorio", "informe campo (ou classificationDef.classificationField)")
    if metodo and metodo not in metodos_validos:
        raise ErroAPI(422, "metodo_invalido", f"método desconhecido: {metodo}")

    with db.db(auth.contexto()) as cur:
        camada = _camada_do_item(cur, item_id)
        colunas = visiveis(_colunas(cur, camada["schema"], camada["tabela"]))
        tipo_pg = _tipo_do_campo(colunas, campo)

        where_sql, params = "", []
        if filtro:
            colunas_filtro = {c: f'"{c}"' for c in colunas}
            try:
                consulta = compilar_where(filtro, colunas_filtro)
            except ErroWhere as exc:
                raise ErroAPI(400, exc.codigo, exc.mensagem, exc.detalhe) from exc
            where_sql, params = consulta.sql, list(consulta.params)

        if tipo_pg not in TIPOS_CLASSIFICAVEIS:
            if metodo:
                raise ErroAPI(
                    422, "metodo_incompativel_com_tipo",
                    f"método '{metodo}' é numérico; o campo '{campo}' é do tipo '{tipo_pg}' (use sem "
                    "metodo para obter valores únicos, ou classifique um campo numérico/data)",
                )
            resposta = _resposta_categorica(cur, camada["schema"], camada["tabela"], campo, where_sql, params)
            chave = (camada["item_id"], camada["versao_atual"], campo, "categorica", None, filtro)
            resposta["cache"] = False
            _cache_guardar(chave, resposta)
            return resposta

        metodo = metodo or "quantil"
        chave = (camada["item_id"], camada["versao_atual"], campo, metodo, n, filtro, cortes, fracao_desvio)
        cacheado = _cache_obter(chave)
        if cacheado is not None:
            saida = dict(cacheado)
            saida["cache"] = True
            return saida

        valores, nulos, amostrado, tamanho_amostra, total_validos = _valores_numericos(
            cur, camada["schema"], camada["tabela"], campo, tipo_pg, where_sql, params
        )
        if valores.size == 0:
            raise ErroAPI(422, "sem_dados", "campo sem nenhum valor não nulo para classificar")

        agregado = False
        try:
            if metodo == "quantil":
                lista_cortes = calc.quantil(valores, n)
            elif metodo == "intervalo_igual":
                lista_cortes = calc.intervalo_igual(valores, n)
            elif metodo == "quebras_naturais":
                lista_cortes, agregado = calc.quebras_naturais(valores, n)
            elif metodo == "desvio_padrao":
                lista_cortes = calc.desvio_padrao(valores, fracao_desvio or 1.0)
            elif metodo == "manual":
                if not cortes:
                    raise ErroAPI(422, "cortes_obrigatorios", "método manual exige o parâmetro cortes")
                lista_cortes = calc.manual(valores, [float(x) for x in cortes.split(",")])
            else:  # pragma: no cover — já validado em metodos_validos
                raise ErroAPI(422, "metodo_invalido", f"método desconhecido: {metodo}")
        except calc.ErroClassificacao as exc:
            raise ErroAPI(422, exc.codigo, exc.mensagem) from exc

        resumo = calc.resumo(valores, nulos)
        contagens = calc.contagem_por_classe(valores, lista_cortes)
        histo = calc.histograma(valores, histograma_faixas)

        resposta = {
            "tipo": "numerica",
            "metodo": metodo,
            "n": n,
            "campo": campo,
            "cortes": lista_cortes,
            "contagem_por_classe": contagens,
            "resumo": resumo,
            "histograma": histo,
            "amostrado": amostrado,
            "tamanho_amostra": tamanho_amostra,
            "total_validos": total_validos,
            "agregado_jenks": agregado,
            "cache": False,
        }
        _cache_guardar(chave, resposta)
        return resposta


@router.post("/api/camadas/{item_id}/estatisticas", openapi_extra=X)
def estatisticas(
    item_id: str,
    corpo: dict,
    request: Request,
    auth: Auth = autenticado(escopo_token="camada:ler"),
):
    with db.db(auth.contexto()) as cur:
        camada = _camada_do_item(cur, item_id)
        todas = _colunas(cur, camada["schema"], camada["tabela"])
        colunas = visiveis(todas)

        try:
            pedido = agr.montar_pedido(corpo)
        except agr.ErroAgregacao as exc:
            raise ErroAPI(422, exc.codigo, exc.mensagem) from exc

        # corpo CANÔNICO para a chave de cache: chaves ordenadas, sem espaço supérfluo — dois pedidos
        # logicamente iguais com chaves em ordem diferente batem na mesma entrada.
        corpo_canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
        chave = (camada["item_id"], camada["versao_atual"], corpo_canonico)
        cacheado = _cache_obter(chave)
        if cacheado is not None:
            saida = dict(cacheado)
            saida["cache"] = True
            return saida

        where_sql, where_params = compilar_filtro(corpo, todas)

        try:
            sql_montado = agr.construir_sql(
                camada["schema"], camada["tabela"], pedido, colunas, where_sql, where_params
            )
        except agr.ErroAgregacao as exc:
            raise ErroAPI(422, exc.codigo, exc.mensagem) from exc

        sql_final = reescrever_schema(sql_montado.sql, settings.PLAT_SCHEMA, settings.PLAT_SCHEMA_TRABALHO)
        with cur.connection.cursor() as tcur:
            tcur.execute(sql_final, sql_montado.params)
            colnames = [d.name for d in tcur.description]
            linhas_brutas = tcur.fetchall()

        excedeu = len(linhas_brutas) > pedido.limite
        if excedeu:
            raise ErroAPI(
                422, "limite_de_grupos_excedido",
                f"a agregação produziu mais de {pedido.limite} grupos; refine o filtro ou os grupos",
            )

        linhas = []
        for row in linhas_brutas:
            registro = {}
            for nome, valor in zip(colnames, row, strict=True):
                if hasattr(valor, "isoformat"):
                    registro[nome] = valor.isoformat()
                elif hasattr(valor, "quantize"):  # decimal.Decimal
                    registro[nome] = float(valor)
                else:
                    registro[nome] = valor
            linhas.append(registro)

        resposta = {"colunas": sql_montado.colunas_saida, "linhas": linhas, "total_grupos": len(linhas), "cache": False}
        _cache_guardar(chave, resposta)
        return resposta
