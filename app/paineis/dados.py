"""Motor de dados por FONTE de um painel (item L2-06-a-modelo-painel-fontes): agrupa todos os elementos
que apontam para a MESMA fonte (`corpo.fontes[].id`) numa única leitura por ciclo de atualização — nunca
uma consulta por elemento (cláusula do portão e do adversário: "deve agrupar por fonte, não 1 por
elemento"). Cada elemento pede uma agregação pequena (contagem, soma/média/mínimo/máximo, contagem por
categoria, ou linhas cruas para a tabela) sobre os campos que a fonte já expõe (lista branca
`fonte.campos` do documento) — a agregação roda inteira no Postgres, nunca no navegador.

Isto reusa a MESMA gramática auditada de filtro que `POST /api/camadas/{id}/estatisticas` (item
L2-06-e-estatisticas-servidor) usa (`app.consulta.where_ast`), via o tradutor CQL2→texto de
`app.paineis.cql2` — quando o L2-06-e estiver na árvore principal, esta função pode passar a delegar
a agregação inteira a `app.estatistica.agregacao` sem trocar o contrato HTTP dos dois endpoints deste
item (rotas.py); até lá, este módulo cobre só as agregações que os quatro tipos de elemento do esquema
v3 (texto/indicador/gráfico/tabela) usam."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.paineis.cql2 import cql2_para_texto

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FUNCOES = {"contagem": "count", "soma": "sum", "media": "avg", "minimo": "min", "maximo": "max"}
LIMITE_LINHAS_MAX = 1000
LIMITE_CATEGORIAS_MAX = 50
LIMITE_PEDIDOS_POR_FONTE = 60  # bem acima dos elementos que um painel real tem (200, mas todos numa fonte é raro)


def _ident(nome: str, rotulo: str) -> str:
    if not isinstance(nome, str) or not IDENT_RE.match(nome):
        raise ErroAPI(422, "campo_invalido", f"{rotulo} inválido: {nome!r}")
    return nome


def _campo_da_fonte(campo: str, campos_fonte: list[str]) -> str:
    if campo not in campos_fonte:
        raise ErroAPI(422, "campo_fora_da_fonte", f"campo fora da lista de campos da fonte: {campo}")
    return _ident(campo, "campo")


def montar_where(fonte: dict, filtro_execucao: dict | None, campos_fonte: list[str]) -> tuple[str, list]:
    """Combina o filtro FIXO da vista (`fonte.filtro`, CQL2-JSON, decidido por quem edita o painel) com
    os valores de EXECUÇÃO (filtros globais do painel + parâmetros de URL, decididos por quem abre a
    tela) — sempre por igualdade e só em campo que a própria fonte já expõe: o runtime nunca amplia o
    poder de consulta além do que o autor do painel liberou ao criar a fonte."""
    textos = []
    fixo = cql2_para_texto(fonte.get("filtro"))
    if fixo:
        textos.append(f"({fixo})")
    colunas_ident = {c: f'"{c}"' for c in campos_fonte}
    for campo, valor in (filtro_execucao or {}).items():
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
        return "", []
    try:
        consulta = compilar_where(" AND ".join(textos), colunas_ident)
    except ErroWhere as exc:
        raise ErroAPI(400, exc.codigo, exc.mensagem, exc.detalhe) from exc
    return consulta.sql, list(consulta.params)


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
    where_sql, where_params = montar_where(fonte, filtro_execucao, campos_fonte)
    resultados: dict[str, dict] = {}
    for chave, pedido in pedidos.items():
        if not isinstance(pedido, dict):
            raise ErroAPI(422, "pedido_invalido", f"pedido inválido para {chave!r}")
        tipo = pedido.get("agregacao")

        if tipo == "linhas":
            campos = [c for c in (pedido.get("campos") or campos_fonte) if c in campos_fonte]
            if not campos:
                raise ErroAPI(422, "sem_campos", "pedido de linhas sem campos válidos da fonte")
            for c in campos:
                _ident(c, "campo")
            limite = min(int(pedido.get("limite") or 50), LIMITE_LINHAS_MAX)
            lista_campos = ", ".join(f'"{c}"' for c in campos)
            sql = f'SELECT {lista_campos} FROM "{schema}"."{tabela}"'
            params = list(where_params)
            if where_sql:
                sql += f" WHERE {where_sql}"
            ordenacao = pedido.get("ordenacao") or {}
            campo_ord = ordenacao.get("campo")
            if campo_ord and campo_ord in campos_fonte:
                direcao = "DESC" if ordenacao.get("direcao") == "desc" else "ASC"
                sql += f' ORDER BY "{_ident(campo_ord, "campo de ordenação")}" {direcao}'
            sql += " LIMIT %s"
            params.append(limite)
            cur.execute(sql, params)
            linhas = [dict(r) for r in cur.fetchall()]
            if medida:
                medida.total_consultas_sql += 1
            resultados[chave] = {"tipo": "linhas", "colunas": campos, "linhas": linhas}
            continue

        if tipo == "categorias":
            campo = _campo_da_fonte(pedido.get("campo", ""), campos_fonte)
            max_categorias = min(int(pedido.get("max_categorias") or 8), LIMITE_CATEGORIAS_MAX)
            agregacao_valor = pedido.get("agregacao_valor") or "contagem"
            if agregacao_valor == "contagem":
                expr_valor = "count(*)"
            else:
                campo_valor = _campo_da_fonte(pedido.get("campo_valor", ""), campos_fonte)
                if agregacao_valor not in _FUNCOES:
                    raise ErroAPI(422, "agregacao_invalida", f"agregação de valor desconhecida: {agregacao_valor!r}")
                expr_valor = f'{_FUNCOES[agregacao_valor]}("{campo_valor}")'
            sql = f'SELECT "{campo}" AS categoria, {expr_valor} AS valor FROM "{schema}"."{tabela}"'
            params = list(where_params)
            if where_sql:
                sql += f" WHERE {where_sql}"
            sql += f' GROUP BY "{campo}" ORDER BY 2 DESC LIMIT %s'
            params.append(max_categorias)
            cur.execute(sql, params)
            linhas = [dict(r) for r in cur.fetchall()]
            for linha in linhas:
                if hasattr(linha.get("valor"), "quantize"):
                    linha["valor"] = float(linha["valor"])
            if medida:
                medida.total_consultas_sql += 1
            resultados[chave] = {"tipo": "categorias", "linhas": linhas}
            continue

        if tipo not in _FUNCOES:
            raise ErroAPI(422, "agregacao_invalida", f"agregação desconhecida: {tipo!r}")
        campo = pedido.get("campo")
        if tipo == "contagem" and not campo:
            expr = "count(*)"
        else:
            campo = _campo_da_fonte(campo or "", campos_fonte)
            expr = f'{_FUNCOES[tipo]}("{campo}")'
        sql = f'SELECT {expr} AS valor FROM "{schema}"."{tabela}"'
        params = list(where_params)
        if where_sql:
            sql += f" WHERE {where_sql}"
        cur.execute(sql, params)
        row = cur.fetchone()
        valor = row["valor"] if row is not None else None
        if hasattr(valor, "quantize"):
            valor = float(valor)
        if medida:
            medida.total_consultas_sql += 1
        resultados[chave] = {"tipo": "numero", "valor": valor}
    return resultados
