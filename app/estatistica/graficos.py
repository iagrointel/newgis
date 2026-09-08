"""Consultas de gráfico por camada (item L2-01-i-graficos-de-camada): SQL puro, sem I/O, para a rota
`POST /api/camadas/{id}/grafico` (`app/estatistica/rotas_graficos.py`).

Cinco tipos, todos agregados NO SERVIDOR (o navegador nunca recebe a tabela crua — refutação do item:
nenhuma resposta passa de 1 MB, seja a camada de 1 milhão de linhas ou de 5.000 categorias):

* `barras` e `pizza`: contagem, soma ou média por categoria, ordenadas por valor, cortadas nas
  `max_categorias` maiores; o resto vira UM grupo `outros` com a sua contagem, soma e número de
  categorias — o motor do L2-06-e responde 422 acima de 10.000 grupos, que é o contrato certo para uma
  TABELA e o errado para um gráfico, que precisa degradar em vez de recusar;
* `linha`: por faixa de data (dia/semana/mês/trimestre/ano no fuso pedido) — usa o motor do L2-06-e tal
  qual (`agregacao.construir_sql` com `faixa_data`), inclusive o corte de mês no fuso;
* `histograma`: N faixas de largura igual entre o mínimo e o máximo do campo, com as bordas calculadas
  EXATAMENTE como `numpy.histogram` (linspace: `lo + i*passo`, última borda = máximo; valor igual ao
  máximo cai na última faixa; todos os valores iguais → faixa [lo-0,5, hi+0,5]) e a atribuição por
  `width_bucket(x, bordas[])`, que é a mesma busca binária nas bordas do numpy;
* `dispersao`: regressão linear no servidor (`regr_slope/regr_intercept/regr_r2`, mínimos quadrados —
  o mesmo problema que `numpy.polyfit(x, y, 1)` resolve) mais uma AMOSTRA de pontos por `TABLESAMPLE
  SYSTEM` limitada a `amostra` — o gráfico desenha a amostra, a reta e o r² vêm do total;
* `contagem`: só o total de linhas do filtro, para o mapa mostrar quantas feições uma barra seleciona.

Filtro (`where` SQL-92 do `app.consulta.where_ast`) e extensão chegam já compilados do chamador."""

from __future__ import annotations

from dataclasses import dataclass

from app import limites
from app.estatistica import agregacao as agr

TIPOS = ("barras", "pizza", "linha", "histograma", "dispersao", "contagem")
ESTATISTICAS = ("count", "sum", "avg")
TIPOS_NUMERICOS = {"smallint", "integer", "bigint", "numeric", "real", "double precision"}
TIPOS_DATA = {"date", "timestamp without time zone", "timestamp with time zone"}


class ErroGrafico(agr.ErroAgregacao):
    """Mesmo contrato do motor: (codigo, mensagem) → a rota devolve 422."""


@dataclass
class PedidoGrafico:
    tipo: str
    campo: str | None = None
    campo_y: str | None = None
    estatistica: str = "count"
    granularidade: str = "mes"
    fuso: str = "America/Sao_Paulo"
    faixas: int = 10
    max_categorias: int = limites.GRAFICO_CATEGORIAS_PADRAO
    amostra: int = limites.GRAFICO_AMOSTRA_PADRAO


def _inteiro(corpo: dict, chave: str, padrao: int, minimo: int, maximo: int) -> int:
    v = corpo.get(chave, padrao)
    if v is None:
        return padrao
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
        raise ErroGrafico(f"{chave}_invalido", f"{chave} precisa ser inteiro entre {minimo} e {maximo}")
    v = int(v)
    if v < minimo or v > maximo:
        raise ErroGrafico(f"{chave}_invalido", f"{chave} precisa ser inteiro entre {minimo} e {maximo}")
    return v


def montar_pedido(corpo: dict) -> PedidoGrafico:
    """Valida o corpo JSON sem olhar a camada (campos são conferidos contra as colunas em `construir`)."""
    if not isinstance(corpo, dict):
        raise ErroGrafico("pedido_invalido", "o corpo precisa ser um objeto JSON")
    tipo = corpo.get("tipo")
    if tipo not in TIPOS:
        raise ErroGrafico("tipo_invalido", f"tipo de gráfico desconhecido: {tipo!r}; use um de {', '.join(TIPOS)}")
    campo = corpo.get("campo")
    if tipo != "contagem":
        campo = agr._validar_ident(campo, "campo")
    campo_y = corpo.get("campo_y")
    if campo_y is not None:
        campo_y = agr._validar_ident(campo_y, "campo_y")
    estatistica = corpo.get("estatistica") or "count"
    if estatistica not in ESTATISTICAS:
        raise ErroGrafico("estatistica_invalida", f"estatística desconhecida: {estatistica!r}; use count, sum ou avg")
    if estatistica != "count" and tipo in ("barras", "pizza", "linha") and not campo_y:
        raise ErroGrafico("campo_y_obrigatorio", f"a estatística {estatistica} precisa de campo_y")
    if tipo == "dispersao" and not campo_y:
        raise ErroGrafico("campo_y_obrigatorio", "dispersão precisa de campo (x) e campo_y (y)")
    granularidade = corpo.get("granularidade") or "mes"
    if granularidade not in agr.GRANULARIDADES:
        raise ErroGrafico("granularidade_invalida", f"granularidade desconhecida: {granularidade!r}")
    fuso = corpo.get("fuso") or "America/Sao_Paulo"
    if not isinstance(fuso, str) or len(fuso) > 64:
        raise ErroGrafico("fuso_invalido", "fuso precisa ser um nome IANA de até 64 caracteres")
    return PedidoGrafico(
        tipo=tipo, campo=campo, campo_y=campo_y, estatistica=estatistica, granularidade=granularidade,
        fuso=fuso,
        faixas=_inteiro(corpo, "faixas", 10, 1, limites.GRAFICO_FAIXAS_MAX),
        max_categorias=_inteiro(corpo, "max_categorias", limites.GRAFICO_CATEGORIAS_PADRAO, 1,
                                limites.GRAFICO_CATEGORIAS_MAX),
        amostra=_inteiro(corpo, "amostra", limites.GRAFICO_AMOSTRA_PADRAO, 10, limites.GRAFICO_AMOSTRA_MAX),
    )


def _exigir(campo: str, colunas: dict[str, str], rotulo: str, tipos: set[str] | None = None) -> str:
    if campo not in colunas:
        raise ErroGrafico("campo_inexistente", f"{rotulo} inexistente nesta camada: {campo}")
    if tipos is not None and colunas[campo] not in tipos:
        raise ErroGrafico("campo_tipo_invalido", f"{rotulo} '{campo}' é {colunas[campo]}, precisa ser um de "
                          f"{', '.join(sorted(tipos))}")
    return f'"{campo}"'


def _de(schema: str, tabela: str) -> str:
    agr._validar_ident(schema, "schema")
    agr._validar_ident(tabela, "tabela")
    return f'"{schema}"."{tabela}"'


def _onde(where_sql: str, extra: str = "") -> str:
    partes = [p for p in (where_sql, extra) if p]
    return (" WHERE " + " AND ".join(f"({p})" for p in partes)) if partes else ""


@dataclass
class Sql:
    sql: str
    params: list


def sql_contagem(schema, tabela, where_sql, where_params) -> Sql:
    return Sql(f"SELECT count(*) AS total FROM {_de(schema, tabela)}{_onde(where_sql)}", list(where_params))


def sql_categorias(schema, tabela, p: PedidoGrafico, colunas, where_sql, where_params) -> Sql:
    """Uma consulta só: agrega por categoria, ordena por valor, corta nas `max_categorias` maiores e traz,
    em janelas, os totais de que o `outros` é a diferença (grupos, linhas, soma) — o resto NUNCA vem."""
    cx = _exigir(p.campo, colunas, "campo")
    if p.estatistica == "count":
        cy, valor = "NULL::float8", "n"
    else:
        cy = _exigir(p.campo_y, colunas, "campo_y", TIPOS_NUMERICOS) + "::float8"
        valor = "s" if p.estatistica == "sum" else "s / nullif(ny, 0)"
    sql = (
        f"WITH g AS (SELECT {cx} AS chave, count(*) AS n, count({cy}) AS ny, sum({cy}) AS s "
        f"FROM {_de(schema, tabela)}{_onde(where_sql)} GROUP BY 1) "
        f"SELECT chave, n, ny, s, {valor} AS valor, count(*) OVER () AS grupos, sum(n) OVER () AS n_total, "
        f"sum(ny) OVER () AS ny_total, sum(s) OVER () AS s_total, "
        f"coalesce(sum(n) FILTER (WHERE chave IS NULL) OVER (), 0) AS nulos "
        f"FROM g ORDER BY {valor} DESC NULLS LAST, chave LIMIT %s"
    )
    return Sql(sql, list(where_params) + [p.max_categorias])


def sql_linha(schema, tabela, p: PedidoGrafico, colunas, where_sql, where_params) -> Sql:
    """Faixa de data pelo motor do L2-06-e (mesmo `AT TIME ZONE` duplo e mesmo limite de grupos)."""
    _exigir(p.campo, colunas, "campo", TIPOS_DATA)
    estat = [agr.Estatistica(campo="*", tipo="count", alias="n")]  # count(*): a faixa NULL (data nula) conta
    if p.estatistica != "count":
        _exigir(p.campo_y, colunas, "campo_y", TIPOS_NUMERICOS)
        estat.append(agr.Estatistica(campo=p.campo_y, tipo=p.estatistica, alias="valor"))
    pedido = agr.PedidoAgregacao(
        estatisticas=estat, faixa_data=agr.FaixaData(campo=p.campo, granularidade=p.granularidade, fuso=p.fuso),
        ordenacao="faixa", limite=agr.LIMITE_GRUPOS,
    )
    m = agr.construir_sql(schema, tabela, pedido, colunas, where_sql, list(where_params))
    return Sql(m.sql, m.params)


def sql_histograma(schema, tabela, p: PedidoGrafico, colunas, where_sql, where_params) -> Sql:
    """Bordas = linspace(lo, hi, N+1) do numpy, em float8 dentro do Postgres (mesma aritmética IEEE:
    `lo + i*passo`, passo = (hi-lo)/N, última borda = hi); atribuição por width_bucket(x, bordas[]),
    com x = hi (faixa N+1) somado à última faixa, como o numpy fecha a última à direita.

    Forma da consulta MEDIDA na camada de 1 mi de linhas: as bordas entram na agregação como InitPlan
    (`(SELECT bordas FROM b)`, parâmetro avaliado uma vez e passado aos trabalhadores), o que mantém as
    duas passagens em varredura paralela — 113 ms; a mesma lógica com LEFT JOIN LATERAL correlacionado
    perdia o paralelismo e levava 645 ms (p95), acima do portão de 500 ms."""
    cx = _exigir(p.campo, colunas, "campo", TIPOS_NUMERICOS) + "::float8"
    de, onde = _de(schema, tabela), _onde(where_sql)
    sql = (
        f"WITH lim AS MATERIALIZED (SELECT min({cx}) AS lo, max({cx}) AS hi, count({cx}) AS n, "
        f"count(*) - count({cx}) AS nulos FROM {de}{onde}), "
        f"b AS MATERIALIZED (SELECT (ARRAY(SELECT lo2 + i * ((hi2 - lo2) / %s) FROM generate_series(0, %s - 1) i) "
        f"|| ARRAY[hi2]) AS bordas, lo2 AS lo, hi2 AS hi FROM "
        f"(SELECT CASE WHEN lo = hi THEN lo - 0.5 ELSE lo END AS lo2, "
        f"CASE WHEN lo = hi THEN hi + 0.5 ELSE hi END AS hi2 FROM lim) s), "
        f"c AS (SELECT least(width_bucket({cx}, (SELECT bordas FROM b)), %s) AS faixa, count(*) AS conta "
        f"FROM {de}{_onde(where_sql, f'{cx} IS NOT NULL')} GROUP BY 1) "
        f"SELECT b.bordas, b.lo, b.hi, lim.n, lim.nulos, c.faixa, c.conta "
        f"FROM lim CROSS JOIN b LEFT JOIN c ON true ORDER BY c.faixa"
    )
    params = list(where_params) + [p.faixas, p.faixas, p.faixas] + list(where_params)
    return Sql(sql, params)


def sql_regressao(schema, tabela, p: PedidoGrafico, colunas, where_sql, where_params) -> Sql:
    cx = _exigir(p.campo, colunas, "campo", TIPOS_NUMERICOS) + "::float8"
    cy = _exigir(p.campo_y, colunas, "campo_y", TIPOS_NUMERICOS) + "::float8"
    sql = (
        f"SELECT regr_slope({cy}, {cx}) AS a, regr_intercept({cy}, {cx}) AS b, regr_r2({cy}, {cx}) AS r2, "
        f"regr_count({cy}, {cx}) AS n, count(*) AS total, min({cx}) AS x_min, max({cx}) AS x_max, "
        f"min({cy}) AS y_min, max({cy}) AS y_max FROM {_de(schema, tabela)}{_onde(where_sql)}"
    )
    return Sql(sql, list(where_params))


def sql_amostra(schema, tabela, p: PedidoGrafico, colunas, where_sql, where_params, percentual: float) -> Sql:
    """Amostra de pontos por página (TABLESAMPLE SYSTEM): custo proporcional ao percentual, não à tabela.
    Percentual 100 = tabela inteira (camadas pequenas), e o LIMIT segura o tamanho da resposta."""
    cx = _exigir(p.campo, colunas, "campo", TIPOS_NUMERICOS) + "::float8"
    cy = _exigir(p.campo_y, colunas, "campo_y", TIPOS_NUMERICOS) + "::float8"
    pct = min(100.0, max(0.001, float(percentual)))
    amostragem = "" if pct >= 100 else " TABLESAMPLE SYSTEM (%s)"
    sql = (
        f"SELECT {cx} AS x, {cy} AS y FROM {_de(schema, tabela)}{amostragem}"
        f"{_onde(where_sql, f'{cx} IS NOT NULL AND {cy} IS NOT NULL')} LIMIT %s"
    )
    params = ([] if pct >= 100 else [pct]) + list(where_params) + [p.amostra]
    return Sql(sql, params)


def percentual_amostra(reltuples: float | None, amostra: int) -> float:
    """Quantos por cento das páginas ler para obter ~1,5× `amostra` linhas (folga para páginas vazias)."""
    if not reltuples or reltuples <= 0 or reltuples <= amostra * 1.5:
        return 100.0
    return max(0.001, min(100.0, 100.0 * amostra * 1.5 / float(reltuples)))
