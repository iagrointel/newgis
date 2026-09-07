"""Motor de agregação estatística (item L2-06-e-estatisticas-servidor): traduz um pedido canônico
{filtro, extensao, grupos, estatisticas, faixa_data, having, ordenacao, limite} em UM SQL parametrizado
com GROUP BY/date_trunc, sem nunca concatenar valor de usuário no texto — só identificador validado por
`consulta.where_ast.IDENT_RE`. Serve tabela, gráfico, indicador, legenda E `outStatistics` do
FeatureServer (`traduzir_outstatistics`), que só reempacota o payload Esri para este mesmo formato.

Reusa o padrão de leitura do item L2-02-b (`app/estatistica/classificacao.py`/`rotas.py`): a única
travessia de linha a linha que este módulo faz é a checagem de "grupo acima do limite" (a query real é
sempre GROUP BY no Postgres — pedir 1 mi de linhas cruas para agregar em Python, como a classificação
faz para os cortes, seria o oposto do que a cláusula de desempenho pede aqui). Onde a leitura em massa
por cursor de tupla se aplica de verdade é dentro do próprio SQL: o Postgres já faz isso nativamente
com GROUP BY/HAVING, então este módulo delega a agregação inteira ao banco e só lê o resultado, que por
definição tem no máximo `LIMITE_GRUPOS` linhas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

LIMITE_GRUPOS = 10_000

FUNCOES_SIMPLES = {
    "count": "count", "sum": "sum", "avg": "avg", "min": "min", "max": "max",
    "stddev": "stddev", "var": "variance",
}
FUNCOES_TODAS = FUNCOES_SIMPLES.keys() | {"percentile", "count_distinct"}

GRANULARIDADES = {"dia": "day", "semana": "week", "mes": "month", "trimestre": "quarter", "ano": "year"}


class ErroAgregacao(Exception):
    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(mensagem)


def _validar_ident(nome: str, rotulo: str) -> str:
    if not isinstance(nome, str) or not IDENT_RE.match(nome):
        raise ErroAgregacao("identificador_invalido", f"{rotulo} inválido: {nome!r}")
    return nome


@dataclass
class Estatistica:
    campo: str
    tipo: str
    percentil: float | None = None
    alias: str | None = None

    def nome_saida(self) -> str:
        if self.alias:
            return self.alias
        if self.tipo == "percentile":
            return f"percentile_{int(self.percentil)}_{self.campo}"
        return f"{self.tipo}_{self.campo}"


@dataclass
class FaixaData:
    campo: str
    granularidade: str
    fuso: str = "America/Sao_Paulo"
    alias: str = "faixa"


@dataclass
class PedidoAgregacao:
    grupos: list[str] = field(default_factory=list)
    estatisticas: list[Estatistica] = field(default_factory=list)
    faixa_data: FaixaData | None = None
    having: str | None = None
    ordenacao: str | None = None
    limite: int = LIMITE_GRUPOS


def montar_pedido(corpo: dict) -> PedidoAgregacao:
    """Valida e normaliza o corpo JSON do pedido. Levanta `ErroAgregacao` (o chamador HTTP vira 422)."""
    grupos = [_validar_ident(g, "campo de grupo") for g in corpo.get("grupos") or []]

    estatisticas: list[Estatistica] = []
    for e in corpo.get("estatisticas") or []:
        campo = _validar_ident(e.get("campo", ""), "campo de estatística")
        tipo = e.get("tipo")
        if tipo not in FUNCOES_TODAS:
            raise ErroAgregacao("estatistica_invalida", f"tipo de estatística desconhecido: {tipo!r}")
        percentil = e.get("percentil")
        if tipo == "percentile":
            if percentil is None or not (0 <= float(percentil) <= 100):
                raise ErroAgregacao("percentil_invalido", "percentil precisa estar entre 0 e 100")
            percentil = float(percentil)
        alias = e.get("alias")
        if alias is not None:
            _validar_ident(alias, "alias de estatística")
        estatisticas.append(Estatistica(campo=campo, tipo=tipo, percentil=percentil, alias=alias))
    if len(estatisticas) > 50:
        raise ErroAgregacao("estatisticas_demais", "no máximo 50 estatísticas por pedido")
    faixa = None
    fd = corpo.get("faixa_data")
    if fd:
        campo = _validar_ident(fd.get("campo", ""), "campo de faixa de data")
        gran = fd.get("granularidade")
        if gran not in GRANULARIDADES:
            raise ErroAgregacao("granularidade_invalida", f"granularidade desconhecida: {gran!r}")
        fuso = fd.get("fuso") or "America/Sao_Paulo"
        alias = fd.get("alias") or "faixa"
        _validar_ident(alias, "alias de faixa de data")
        faixa = FaixaData(campo=campo, granularidade=gran, fuso=fuso, alias=alias)

    if not estatisticas and not grupos and not fd:
        raise ErroAgregacao("pedido_vazio", "informe ao menos um grupo, uma faixa de data ou uma estatística")

    limite = int(corpo.get("limite") or LIMITE_GRUPOS)
    if limite < 1 or limite > LIMITE_GRUPOS:
        raise ErroAgregacao(
            "limite_invalido", f"limite precisa estar entre 1 e {LIMITE_GRUPOS} grupos por pedido"
        )

    return PedidoAgregacao(
        grupos=grupos, estatisticas=estatisticas, faixa_data=faixa,
        having=corpo.get("having"), ordenacao=corpo.get("ordenacao"), limite=limite,
    )


def _expr_estatistica_sem_alias(e: Estatistica, colunas: dict[str, str]) -> str:
    """A expressão agregada CRUA (sem `AS alias`) — é isto, não o alias, que precisa ir num `HAVING`:
    Postgres avalia HAVING antes de nomear as colunas de saída, então `HAVING alias > x` sempre dá
    `column "alias" does not exist`, mesmo quando `alias` aparece no SELECT."""
    if e.campo not in colunas and e.campo != "*":
        raise ErroAgregacao("campo_inexistente", f"campo inexistente nesta camada: {e.campo}")
    col = f'"{e.campo}"'
    if e.tipo == "count":
        return f'count({col if e.campo != "*" else "*"})'
    if e.tipo == "count_distinct":
        return f'count(DISTINCT {col})'
    if e.tipo == "percentile":
        return f'percentile_cont({e.percentil / 100.0!r}) WITHIN GROUP (ORDER BY {col})'
    return f'{FUNCOES_SIMPLES[e.tipo]}({col})'


def _expr_estatistica(e: Estatistica, colunas: dict[str, str]) -> str:
    return f'{_expr_estatistica_sem_alias(e, colunas)} AS "{e.nome_saida()}"'


def _expr_grupo_data(faixa: FaixaData) -> str:
    unidade = GRANULARIDADES[faixa.granularidade]
    col = f'"{faixa.campo}"'
    # date_trunc no FUSO do pedido, não no fuso do servidor: converte para o fuso, trunca, converte de
    # volta para timestamptz — é o mesmo padrão do `AT TIME ZONE` duplo que faz o corte de mês bater
    # exatamente na virada local (31/07 23:30 America/Sao_Paulo cai em julho, não em agosto UTC).
    return (
        f"(date_trunc('{unidade}', ({col}) AT TIME ZONE %s) AT TIME ZONE %s) "
        f'AS "{faixa.alias}"'
    )


@dataclass
class SqlAgregacao:
    sql: str
    params: list
    colunas_saida: list[str]
    tem_limite_extra: bool  # LIMIT pedido+1 embutido para detectar excesso de grupos


def construir_sql(
    schema: str, tabela: str, pedido: PedidoAgregacao, colunas: dict[str, str],
    where_sql: str = "", where_params: list | None = None,
) -> SqlAgregacao:
    """Monta o SQL de agregação. `where_sql`/`where_params` já vêm compilados por
    `app.consulta.where_ast.compilar_where` (o filtro do pedido é texto na mesma gramática do resto da
    trilha; CQL2-JSON completo é trabalho futuro do próprio where_ast, ver seu docstring)."""
    _validar_ident(schema, "schema"), _validar_ident(tabela, "tabela")
    for g in pedido.grupos:
        if g not in colunas:
            raise ErroAgregacao("campo_inexistente", f"campo de grupo inexistente: {g}")
    for e in pedido.estatisticas:
        if e.campo not in colunas and e.campo != "*":
            raise ErroAgregacao("campo_inexistente", f"campo inexistente nesta camada: {e.campo}")
    if pedido.faixa_data and pedido.faixa_data.campo not in colunas:
        raise ErroAgregacao("campo_inexistente", f"campo de faixa de data inexistente: {pedido.faixa_data.campo}")

    params: list = list(where_params or [])
    select_grupos = [f'"{g}"' for g in pedido.grupos]
    agrupa_por = [f'"{g}"' for g in pedido.grupos]
    colunas_saida = list(pedido.grupos)

    if pedido.faixa_data:
        expr_completa = _expr_grupo_data(pedido.faixa_data)
        expr_sem_alias = expr_completa.rsplit(" AS ", 1)[0]
        select_grupos.append(expr_completa)
        params += [pedido.faixa_data.fuso, pedido.faixa_data.fuso]
        # agrupa pela EXPRESSÃO, não pelo alias: reconstrução idêntica à do SELECT, com os MESMOS
        # parâmetros de fuso repetidos na mesma ordem (um %s por AT TIME ZONE).
        agrupa_por.append(expr_sem_alias)
        params += [pedido.faixa_data.fuso, pedido.faixa_data.fuso]
        colunas_saida.append(pedido.faixa_data.alias)

    select_stats = [_expr_estatistica(e, colunas) for e in pedido.estatisticas]
    colunas_saida += [e.nome_saida() for e in pedido.estatisticas]

    select_sql = ", ".join(select_grupos + select_stats) if (select_grupos or select_stats) else "1"
    sql = f'SELECT {select_sql} FROM "{schema}"."{tabela}"'
    if where_sql:
        sql += f" WHERE {where_sql}"
    if agrupa_por:
        sql += " GROUP BY " + ", ".join(agrupa_por)

    if pedido.having:
        # HAVING referencia a EXPRESSÃO agregada, não o alias de saída (ver docstring de
        # `_expr_estatistica_sem_alias`) — por isso o nome que o usuário digita no `having`
        # (o alias da estatística) é mapeado para a expressão crua, não para `"alias"` entre aspas.
        colunas_having = {e.nome_saida(): _expr_estatistica_sem_alias(e, colunas) for e in pedido.estatisticas}
        colunas_having.update({g: f'"{g}"' for g in pedido.grupos})
        from app.consulta.where_ast import ErroWhere, compilar_where

        try:
            consulta = compilar_where(pedido.having, colunas_having)
        except ErroWhere as exc:
            raise ErroAgregacao(exc.codigo, exc.mensagem) from exc
        sql += f" HAVING {consulta.sql}"
        params += list(consulta.params)

    if pedido.ordenacao:
        campo_ord = pedido.ordenacao.lstrip("-")
        direcao = "DESC" if pedido.ordenacao.startswith("-") else "ASC"
        if campo_ord not in colunas_saida:
            raise ErroAgregacao("ordenacao_invalida", f"ordenação por campo fora da saída: {campo_ord}")
        sql += f' ORDER BY "{campo_ord}" {direcao}'
    elif pedido.grupos or pedido.faixa_data:
        sql += " ORDER BY 1"

    # LIMIT pedido.limite + 1: se voltar mais que pedido.limite linhas, é excesso de grupos (422), não
    # um corte silencioso de dado — a rota decide o código de erro olhando `len(linhas) > pedido.limite`.
    sql += " LIMIT %s"
    params.append(pedido.limite + 1)

    return SqlAgregacao(sql=sql, params=params, colunas_saida=colunas_saida, tem_limite_extra=True)


# ---------------------------------------------------------------- outStatistics (FeatureServer/Esri)
_ESRI_FUNCOES = {
    "count": "count", "sum": "sum", "avg": "avg", "min": "min", "max": "max",
    "stddev": "stddev", "var": "var",
}


def traduzir_outstatistics(q: dict) -> dict:
    """Reempacota um pedido no formato `outStatistics`/`groupByFieldsForStatistics`/`having`/`orderByFields`
    do REST API da Esri (`query-feature-service-layer#outStatistics`) no formato canônico deste módulo —
    MESMO caminho de código de `construir_sql`, provando que uma única rota atende os dois clientes."""
    grupos = [g.strip() for g in str(q.get("groupByFieldsForStatistics") or "").split(",") if g.strip()]
    estatisticas = []
    for st in q.get("outStatistics") or []:
        tipo_esri = str(st.get("statisticType", "")).lower()
        if tipo_esri not in _ESRI_FUNCOES:
            raise ErroAgregacao("estatistica_invalida", f"statisticType desconhecido: {tipo_esri!r}")
        estatisticas.append({
            "campo": st["onStatisticField"],
            "tipo": _ESRI_FUNCOES[tipo_esri] if _ESRI_FUNCOES[tipo_esri] != "var" else "var",
            "alias": st.get("outStatisticFieldName"),
        })
    corpo: dict = {"grupos": grupos, "estatisticas": estatisticas}
    if q.get("having"):
        corpo["having"] = q["having"]
    if q.get("orderByFields"):
        campo, *resto = q["orderByFields"].strip().split()
        corpo["ordenacao"] = ("-" + campo) if resto and resto[0].upper() == "DESC" else campo
    return corpo
