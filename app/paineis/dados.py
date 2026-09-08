"""Motor de dados por FONTE de um painel (itens L2-06-a-modelo-painel-fontes e L2-06-b-elementos-basicos):
agrupa todos os elementos que apontam para a MESMA fonte (`corpo.fontes[].id`) numa única leitura por ciclo de
atualização — nunca uma consulta por elemento (cláusula do portão do L2-06-a e do adversário).

Item L2-06-b: TODO NÚMERO vem do motor de agregação do L2-06-e (`app.estatistica.agregacao`), nunca de conta
no navegador e nunca de SQL próprio deste módulo — é a delegação que o docstring anterior deixou prometida
("quando o L2-06-e estiver na árvore principal, esta função pode passar a delegar a agregação inteira") e que
o teste `test_paineis_elementos.py` confere contra SQL direto. O que este módulo ainda monta à mão é só o que
NÃO é agregação: leitura de linhas cruas (tabela, lista paginada, detalhes de uma feição), onde o motor de
agregação não se aplica.

O filtro continua com a MESMA gramática auditada do resto da trilha (`app.consulta.where_ast` via o tradutor
CQL2→texto de `app.paineis.cql2`): o filtro FIXO da fonte (decidido por quem edita o painel) combinado com os
valores de EXECUÇÃO (filtros globais e parâmetros de URL de quem abre a tela), sempre por igualdade e só em
campo que a fonte já expõe.

Tipos de pedido (um por elemento do L2-06-b; os quatro primeiros são o contrato do L2-06-a, mantido):
  contagem|soma|media|minimo|maximo  -> {tipo: numero}            (indicador simples)
  categorias                         -> {tipo: categorias}        (barras/pizza de uma série)
  linhas                             -> {tipo: linhas}            (tabela/lista, com paginação e total)
  indicador                          -> {tipo: numero}            (qualquer estatística do L2-06-e, com percentil)
  serie                              -> {tipo: serie}             (gráfico serial: por categoria ou por data,
                                                                   várias séries, granularidade com fuso)
  grupos                             -> {tipo: grupos}            (tabela agrupada com subtotal e total geral)
  uma_feicao                         -> {tipo: feicao}            (indicador "uma feição", detalhes, texto rico)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.estatistica import agregacao
from app.paineis.cql2 import cql2_para_texto

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FUNCOES = {"contagem": "count", "soma": "sum", "media": "avg", "minimo": "min", "maximo": "max"}
LIMITE_LINHAS_MAX = 1000
LIMITE_CATEGORIAS_MAX = 50
LIMITE_SERIES = 8          # séries por gráfico serial (o Dashboards empilha poucas; acima disso vira ilegível)
LIMITE_CHAVES_SERIE = 500  # categorias/faixas de data por gráfico serial
LIMITE_GRUPOS_TABELA = 500 # grupos com subtotal numa tabela agrupada
# nomes do produto -> tipos do motor de agregação do L2-06-e (app.estatistica.agregacao.FUNCOES_TODAS)
ESTATISTICAS = {"contagem": "count", "soma": "sum", "media": "avg", "minimo": "min", "maximo": "max",
                "desvio_padrao": "stddev", "variancia": "var", "percentil": "percentile",
                "contagem_distinta": "count_distinct"}
LIMITE_PEDIDOS_POR_FONTE = 60  # bem acima dos elementos que um painel real tem (200, mas todos numa fonte é raro)


def _ident(nome: str, rotulo: str) -> str:
    if not isinstance(nome, str) or not IDENT_RE.match(nome):
        raise ErroAPI(422, "campo_invalido", f"{rotulo} inválido: {nome!r}")
    return nome


def _campo_da_fonte(campo: str, campos_fonte: list[str]) -> str:
    if campo not in campos_fonte:
        raise ErroAPI(422, "campo_fora_da_fonte", f"campo fora da lista de campos da fonte: {campo}")
    return _ident(campo, "campo")


CHAVE_EXTENSAO = "__extensao"   # caixa o,s,l,n em EPSG:4326 (o `tipo: geometria` que o esquema do painel prevê)
COLUNA_GEOMETRIA = "geom"       # nome fixo da coluna de geometria de toda camada (plat.camada_preparar)


def _caixa(valor) -> list[float]:
    """'o,s,l,n' (EPSG:4326) -> quatro floats validados. Nunca vira texto no SQL: entra como parâmetro."""
    partes = valor if isinstance(valor, (list, tuple)) else str(valor).split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "extensao_invalida", "extensão precisa ser 'oeste,sul,leste,norte' em EPSG:4326")
    try:
        o, s, le, n = (float(x) for x in partes)
    except (TypeError, ValueError) as e:
        raise ErroAPI(422, "extensao_invalida", "extensão com número inválido") from e
    if not (-180 <= o <= 180 and -180 <= le <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        raise ErroAPI(422, "extensao_fora_do_mundo", "extensão fora do intervalo de longitude/latitude")
    return [min(o, le), min(s, n), max(o, le), max(s, n)]


def montar_where(fonte: dict, filtro_execucao: dict | None, campos_fonte: list[str]) -> tuple[str, list]:
    """Combina o filtro FIXO da vista (`fonte.filtro`, CQL2-JSON, decidido por quem edita o painel) com
    os valores de EXECUÇÃO (filtros globais do painel + parâmetros de URL, decididos por quem abre a
    tela) — sempre por igualdade e só em campo que a própria fonte já expõe: o runtime nunca amplia o
    poder de consulta além do que o autor do painel liberou ao criar a fonte."""
    textos = []
    extra_sql: list[str] = []
    extra_params: list = []
    fixo = cql2_para_texto(fonte.get("filtro"))
    if fixo:
        textos.append(f"({fixo})")
    colunas_ident = {c: f'"{c}"' for c in campos_fonte}
    for campo, valor in (filtro_execucao or {}).items():
        # item L2-06-b: a EXTENSÃO do elemento de mapa filtra as outras fontes do painel — condição espacial
        # na coluna de geometria da camada, com os quatro números como parâmetro (nunca interpolados)
        if campo == CHAVE_EXTENSAO and valor not in (None, ""):
            caixa = _caixa(valor)
            extra_sql.append(f'"{COLUNA_GEOMETRIA}" && ST_MakeEnvelope(%s, %s, %s, %s, 4326)')
            extra_params += caixa
            continue
        if campo not in campos_fonte or valor is None or valor == "":
            continue
        _ident(campo, "campo de filtro de execução")
        if isinstance(valor, bool):
            continue  # CQL2/where_ast não comparam booleano; ignora silenciosamente (defesa, não recusa a tela)
        if isinstance(valor, (int, float)):
            textos.append(f"{campo} = {valor!r}")
        else:
            v = str(valor).replace("'", "''")
            textos.append(f"{campo} = '{v}'")
    if not textos:
        return (" AND ".join(extra_sql), list(extra_params)) if extra_sql else ("", [])
    try:
        consulta = compilar_where(" AND ".join(textos), colunas_ident)
    except ErroWhere as exc:
        raise ErroAPI(400, exc.codigo, exc.mensagem, exc.detalhe) from exc
    sql = consulta.sql
    params = list(consulta.params)
    if extra_sql:
        sql = f"({sql}) AND " + " AND ".join(extra_sql)
        params += extra_params
    return sql, params


@dataclass
class ConsultaMedida:
    total_consultas_sql: int = 0


def executar_pedidos(
    cur, schema: str, tabela: str, fonte: dict, pedidos: dict[str, dict], filtro_execucao: dict | None,
    medida: ConsultaMedida | None = None,
) -> dict[str, dict]:
    """`pedidos` é {chave_do_elemento: {agregacao, campo?, campos?, limite?, ordenacao?, max_categorias?}}.
    UMA chamada desta função cobre todo elemento de uma fonte — é o chamador HTTP (rotas.py) que
    garante isso agrupando por `fonte_id` antes de chegar aqui; esta função em si roda 1 SQL por PEDIDO
    (não por elemento — pedidos duplicados entre elementos podem ser deduplicados pelo chamador se quiser,
    mas o ponto do portão é o número de REQUISIÇÕES HTTP por fonte, que já cai para 1 por ciclo)."""

    if len(pedidos) > LIMITE_PEDIDOS_POR_FONTE:
        raise ErroAPI(422, "pedidos_demais", f"no máximo {LIMITE_PEDIDOS_POR_FONTE} pedidos por fonte")
    campos_fonte = list(fonte.get("campos") or [])
    colunas = {c: f'"{c}"' for c in campos_fonte}
    where_sql, where_params = montar_where(fonte, filtro_execucao, campos_fonte)
    resultados: dict[str, dict] = {}
    for chave, pedido in pedidos.items():
        if not isinstance(pedido, dict):
            raise ErroAPI(422, "pedido_invalido", f"pedido inválido para {chave!r}")
        tipo = pedido.get("agregacao")
        ctx = _Contexto(cur, schema, tabela, colunas, campos_fonte, where_sql, where_params, medida)
        if tipo in ("linhas", "uma_feicao"):
            resultados[chave] = _linhas(ctx, pedido, uma=(tipo == "uma_feicao"))
        elif tipo == "categorias":
            resultados[chave] = _categorias(ctx, pedido)
        elif tipo == "serie":
            resultados[chave] = _serie(ctx, pedido)
        elif tipo == "grupos":
            resultados[chave] = _grupos(ctx, pedido)
        elif tipo == "indicador" or tipo in _FUNCOES:
            resultados[chave] = _numero(ctx, pedido, tipo)
        else:
            raise ErroAPI(422, "agregacao_invalida", f"agregação desconhecida: {tipo!r}")
    return resultados


@dataclass
class _Contexto:
    cur: object
    schema: str
    tabela: str
    colunas: dict
    campos_fonte: list
    where_sql: str
    where_params: list
    medida: "ConsultaMedida | None" = None


def _agregar(ctx: _Contexto, corpo_pedido: dict) -> list[dict]:
    """Ponte única para o motor do L2-06-e: valida o pedido, monta UM SQL e devolve as linhas. Todo número
    que um elemento de painel mostra passa por aqui (cláusula do item L2-06-b)."""
    try:
        pedido = agregacao.montar_pedido(corpo_pedido)
        montado = agregacao.construir_sql(
            ctx.schema, ctx.tabela, pedido, ctx.colunas, ctx.where_sql, list(ctx.where_params),
        )
    except agregacao.ErroAgregacao as e:
        raise ErroAPI(422, e.codigo, e.mensagem) from e
    ctx.cur.execute(montado.sql, montado.params)
    linhas = [dict(r) for r in ctx.cur.fetchall()]
    if ctx.medida:
        ctx.medida.total_consultas_sql += 1
    if montado.tem_limite_extra and len(linhas) > pedido.limite:
        raise ErroAPI(422, "grupos_demais",
                      f"a consulta devolveu mais de {pedido.limite} grupos; use um campo com menos valores "
                      "distintos ou aumente o limite do elemento", {"limite": pedido.limite})
    return [{k: _valor_json(v) for k, v in linha.items()} for linha in linhas]


def _valor_json(v):
    if hasattr(v, "quantize"):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _estatistica_do_pedido(pedido: dict, campos_fonte: list, prefixo: str = "") -> dict:
    """{estatistica, campo, percentil} do produto -> {tipo, campo, percentil, alias} do motor."""
    nome = pedido.get(f"{prefixo}estatistica") or pedido.get(f"{prefixo}agregacao") or "contagem"
    if nome not in ESTATISTICAS:
        raise ErroAPI(422, "estatistica_invalida", f"estatística desconhecida: {nome!r}",
                      {"aceitas": sorted(ESTATISTICAS)})
    campo = pedido.get(f"{prefixo}campo")
    if nome == "contagem" and not campo:
        campo = "*"
    else:
        campo = _campo_da_fonte(campo or "", campos_fonte)
    saida = {"tipo": ESTATISTICAS[nome], "campo": campo, "alias": "valor"}
    if nome == "percentil":
        saida["percentil"] = pedido.get("percentil", 50)
    return saida


def _numero(ctx: _Contexto, pedido: dict, tipo: str) -> dict:
    est = _estatistica_do_pedido(pedido if tipo == "indicador" else {**pedido, "estatistica": tipo},
                                 ctx.campos_fonte)
    linhas = _agregar(ctx, {"estatisticas": [est]})
    valor = linhas[0].get("valor") if linhas else None
    return {"tipo": "numero", "valor": valor}


def _categorias(ctx: _Contexto, pedido: dict) -> dict:
    campo = _campo_da_fonte(pedido.get("campo", ""), ctx.campos_fonte)
    limite = min(int(pedido.get("max_categorias") or 8), LIMITE_CATEGORIAS_MAX)
    est = _estatistica_do_pedido(
        {"estatistica": pedido.get("agregacao_valor") or "contagem", "campo": pedido.get("campo_valor")},
        ctx.campos_fonte,
    )
    linhas = _agregar(ctx, {"grupos": [campo], "estatisticas": [est], "ordenacao": "-valor", "limite": limite})
    return {"tipo": "categorias",
            "linhas": [{"categoria": linha.get(campo), "valor": linha.get("valor")} for linha in linhas]}


def _series_do_pedido(pedido: dict, campos_fonte: list) -> list[dict]:
    brutas = pedido.get("series") or [{"estatistica": pedido.get("estatistica") or "contagem",
                                       "campo": pedido.get("campo")}]
    if len(brutas) > LIMITE_SERIES:
        raise ErroAPI(422, "series_demais", f"no máximo {LIMITE_SERIES} séries por gráfico")
    saida = []
    for i, s in enumerate(brutas):
        if not isinstance(s, dict):
            raise ErroAPI(422, "serie_invalida", "cada série precisa ser um objeto")
        est = _estatistica_do_pedido(s, campos_fonte)
        est["alias"] = f"s{i}"
        est["rotulo"] = s.get("rotulo") or (f"{s.get('estatistica') or 'contagem'}"
                                            + (f" de {s.get('campo')}" if s.get("campo") else ""))
        saida.append(est)
    return saida


def _serie(ctx: _Contexto, pedido: dict) -> dict:
    """Gráfico serial: por CATEGORIA (`grupo`) ou por DATA (`faixa_data` com granularidade e fuso do
    inquilino), com uma ou várias séries. O fuso vai para o motor, que faz o `AT TIME ZONE` no Postgres —
    o navegador nunca reagrupa data (é o teste de fronteira de mês do portão)."""
    series = _series_do_pedido(pedido, ctx.campos_fonte)
    limite = min(int(pedido.get("limite") or 60), LIMITE_CHAVES_SERIE)
    corpo = {"estatisticas": [{k: v for k, v in s.items() if k != "rotulo"} for s in series], "limite": limite}
    faixa = pedido.get("faixa_data")
    if faixa:
        campo = _campo_da_fonte((faixa or {}).get("campo", ""), ctx.campos_fonte)
        corpo["faixa_data"] = {"campo": campo, "granularidade": faixa.get("granularidade") or "mes",
                               "fuso": faixa.get("fuso") or "America/Sao_Paulo", "alias": "faixa"}
        chave_col, granularidade = "faixa", corpo["faixa_data"]["granularidade"]
        corpo["ordenacao"] = "faixa"
    else:
        campo = _campo_da_fonte(pedido.get("grupo", ""), ctx.campos_fonte)
        corpo["grupos"] = [campo]
        chave_col, granularidade = campo, None
        corpo["ordenacao"] = pedido.get("ordenacao") or "-s0"
    linhas = _agregar(ctx, corpo)
    return {
        "tipo": "serie", "chave": chave_col, "granularidade": granularidade,
        "chaves": [linha.get(chave_col) for linha in linhas],
        "series": [{"alias": s["alias"], "rotulo": s["rotulo"],
                    "valores": [linha.get(s["alias"]) for linha in linhas]} for s in series],
    }


def _grupos(ctx: _Contexto, pedido: dict) -> dict:
    """Tabela agrupada: uma linha por combinação de `grupos`, com as estatísticas pedidas, mais a linha de
    TOTAL geral (a mesma agregação sem `grupos` — nunca a soma das linhas no navegador, que erraria em média
    e em contagem distinta)."""
    grupos = [_campo_da_fonte(g, ctx.campos_fonte) for g in (pedido.get("grupos") or [])]
    if not grupos:
        raise ErroAPI(422, "sem_grupos", "pedido de grupos sem campo de agrupamento")
    series = _series_do_pedido(pedido, ctx.campos_fonte)
    limpas = [{k: v for k, v in s.items() if k != "rotulo"} for s in series]
    limite = min(int(pedido.get("limite") or 100), LIMITE_GRUPOS_TABELA)
    ordenacao = pedido.get("ordenacao") or f"-{series[0]['alias']}"
    linhas = _agregar(ctx, {"grupos": grupos, "estatisticas": limpas, "ordenacao": ordenacao, "limite": limite})
    total = _agregar(ctx, {"estatisticas": limpas})
    return {"tipo": "grupos", "grupos": grupos,
            "series": [{"alias": s["alias"], "rotulo": s["rotulo"]} for s in series],
            "linhas": linhas, "total": total[0] if total else {}}


def _linhas(ctx: _Contexto, pedido: dict, uma: bool = False) -> dict:
    """Linhas cruas (tabela, lista paginada, detalhes). Não é agregação: é leitura da tabela da camada, com
    lista branca de campos, ordenação, LIMIT/OFFSET e o total vindo do motor de agregação (count)."""
    campos = [c for c in (pedido.get("campos") or ctx.campos_fonte) if c in ctx.campos_fonte]
    if not campos:
        raise ErroAPI(422, "sem_campos", "pedido de linhas sem campos válidos da fonte")
    for c in campos:
        _ident(c, "campo")
    limite = 1 if uma else min(int(pedido.get("limite") or 50), LIMITE_LINHAS_MAX)
    deslocamento = max(0, int(pedido.get("deslocamento") or 0))
    lista = [f'"{c}"' for c in campos]
    if pedido.get("geometria"):
        # elemento de mapa: centroide em EPSG:4326 (a coluna de geometria não é campo da fonte — o painel
        # nunca expõe a geometria crua, só o ponto que o desenho precisa)
        lista += [f'ST_X(ST_Centroid(ST_Transform("{COLUNA_GEOMETRIA}", 4326)))::float8 AS __lon',
                  f'ST_Y(ST_Centroid(ST_Transform("{COLUNA_GEOMETRIA}", 4326)))::float8 AS __lat']
    lista_campos = ", ".join(lista)
    sql = f'SELECT {lista_campos} FROM "{ctx.schema}"."{ctx.tabela}"'
    params = list(ctx.where_params)
    if ctx.where_sql:
        sql += f" WHERE {ctx.where_sql}"
    ordenacao = pedido.get("ordenacao") or {}
    campo_ord = ordenacao.get("campo")
    if campo_ord and campo_ord in ctx.campos_fonte:
        direcao = "DESC" if ordenacao.get("direcao") == "desc" else "ASC"
        sql += f' ORDER BY "{_ident(campo_ord, "campo de ordenação")}" {direcao}'
    sql += " LIMIT %s OFFSET %s"
    params += [limite, deslocamento]
    ctx.cur.execute(sql, params)
    linhas = [{k: _valor_json(v) for k, v in dict(r).items()} for r in ctx.cur.fetchall()]
    if ctx.medida:
        ctx.medida.total_consultas_sql += 1
    if uma:
        return {"tipo": "feicao", "campos": campos, "valores": linhas[0] if linhas else None}
    saida = {"tipo": "linhas", "colunas": campos, "linhas": linhas, "deslocamento": deslocamento,
             "limite": limite}
    if pedido.get("total"):
        contagem = _agregar(ctx, {"estatisticas": [{"tipo": "count", "campo": "*", "alias": "valor"}]})
        saida["total"] = contagem[0].get("valor") if contagem else None
    return saida
