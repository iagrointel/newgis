"""Edição em lote (item L2-03-f-edicao-em-lote-calculo-campo): `POST /api/camadas/{id}/lote` sobre uma seleção
(ids, expressão `onde` ou todas) — calcular campo por expressão (L2-10-c) TRADUZIDA para SQL quando o subconjunto
permite (`app/expressao/compilador_sql.py`) e avaliada linha a linha no servidor quando não; atribuir valor fixo;
apagar; corrigir geometria inválida (ST_MakeValid com relatório); copiar/mover para outra camada com mapeamento de
campos. Pré-visualização (10 primeiras linhas antes/depois) sem gravar. Até LOTE_SINCRONO_MAX feições roda dentro
do pedido; acima, vira o job `camadas.lote` (L0-05) com progresso e cancelamento.

Regras herdadas do L2-03-a (C5: uma porta de escrita, uma validação): mesma `validar_atributos` (tipo, tamanho,
domínio de `regras_campo`, campo somente-leitura, rastreio nunca aceito), mesmo `exigir_camada_editavel`, mesma
regra "só as próprias" (a seleção é restringida às feições do ator quando a camada liga `somente_proprias` e ele
não tem `feicoes.editar_total`), mesmos gatilhos da tabela (`tg_versao`, `tg_historico` → uma linha de
`plat.feicao_historico` por feição tocada, também no job), mesmo bump de `tiles_versao` e um evento por lote.

Transação: TODO o lote (síncrono ou job) roda numa transação só, em sub-lotes de LOTE_TRANSACAO feições com
progresso entre eles; erro no modo `transacao` ou cancelamento do job desfaz tudo — a camada volta ao estado
anterior (portão do item). O modo `parcial` (só calcular/atribuir) grava as linhas válidas e devolve as falhas
nomeadas por feição; ele sempre avalia linha a linha (uma linha errada não pode derrubar o UPDATE do sub-lote).

Campos derivados de geometria disponíveis na expressão (calculados no banco, geodésicos): `$area_m2`,
`$comprimento_m`, `$perimetro_m` (geography) e `$x`/`$y` (centroide no SRID da camada) — a linguagem não tem
tipo geometria nesta passagem (L2-10-c), então "área geográfica / 10.000" é `$area_m2 / 10000`."""

from __future__ import annotations

import datetime
import decimal
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import psycopg2
import psycopg2.errors
import psycopg2.extras

from app import limites
from app.edicao.modelos import LoteEntrada, LoteFalha, LotePrevia, LoteSaida
from app.edicao.servico import (
    RESERVADOS,
    _ident,
    _schema_tabela,
    camada_ou_404,
    validar_atributos,
)
from app.erros import ErroAPI
from app.expressao import avaliador_py as expr
from app.expressao.compilador_sql import NaoTraduzivel, compilar
from app.ingestao.geometria import MULTI_DE

DERIVADOS = {
    "area_m2": "ST_Area(geom::geography)",
    "comprimento_m": "ST_Length(geom::geography)",
    "perimetro_m": "ST_Perimeter(geom::geography)",
    "x": "ST_X(ST_Centroid(geom))",
    "y": "ST_Y(ST_Centroid(geom))",
}
_DIM = {"Point": 1, "MultiPoint": 1, "LineString": 2, "MultiLineString": 2, "Polygon": 3, "MultiPolygon": 3}
_RE_TIPO_PG = re.compile(r"^[a-z][a-z ]{0,40}$")
_TIPOS_ARRAY = {"integer": "bigint", "bigint": "bigint", "smallint": "bigint", "double precision": "double precision",
                "real": "double precision", "numeric": "double precision", "boolean": "boolean", "text": "text"}
Progresso = Callable[[int, int], None]


@dataclass
class Ator:
    """O que o lote precisa saber de quem pede — a rota tira da sessão; o job guarda o mesmo par nos parâmetros
    (a checagem de privilégio já aconteceu na rota que criou o job; o inquilino é o do próprio job, pela RLS)."""

    usuario_id: int
    editar_total: bool


@dataclass
class Plano:
    dados: dict
    schema: str
    tabela: str
    tem_geom: bool
    colunas: dict[str, str]
    derivados: dict[str, str]
    campo: str | None = None
    tipo_campo: str | None = None
    ast: Any = None
    sql_expr: str | None = None
    sql_params: list = field(default_factory=list)
    traducao: str | None = None
    traducao_motivo: str | None = None
    sel_sql: str = "TRUE"
    sel_params: list = field(default_factory=list)
    fids: list[int] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    destino: dict | None = None  # copiar/mover: {schema, tabela, dados, mapeamento, geom_sql, item_id}
    valor: Any = None


def ator_de(auth) -> Ator:
    return Ator(usuario_id=auth.usuario_id, editar_total=auth.tem("feicoes.editar_total"))


# ---------------------------------------------------------------- erros
def _erro_expressao(e: expr.ErroExpressao, feicao: str | None = None) -> ErroAPI:
    detalhe = dict(e.detalhe) if isinstance(e.detalhe, dict) else ({"detalhe": e.detalhe} if e.detalhe else {})
    if feicao:
        detalhe["id"] = feicao
    return ErroAPI(422, e.codigo, f"expressão: {e}", detalhe or None)


def erro_do_banco_lote(e: psycopg2.Error) -> ErroAPI:
    """Erro do Postgres dentro do lote → 422 nomeado (a transação inteira já foi desfeita por quem chama)."""
    msg = (e.diag.message_primary or str(e)).strip()[:300]
    if isinstance(e, psycopg2.errors.DivisionByZero):
        return ErroAPI(422, "divisao_por_zero", "expressão: divisão por zero em alguma feição")
    if isinstance(e, (psycopg2.errors.InvalidTextRepresentation, psycopg2.errors.DatatypeMismatch,
                      psycopg2.errors.NumericValueOutOfRange, psycopg2.errors.UndefinedFunction,
                      psycopg2.errors.InvalidParameterValue, psycopg2.errors.CannotCoerce)):
        return ErroAPI(422, "tipo_invalido", f"valor incompatível com o campo: {msg}")
    if isinstance(e, psycopg2.errors.InvalidArgumentForPowerFunction):
        return ErroAPI(422, "numero_invalido", f"expressão: {msg}")
    if isinstance(e, psycopg2.errors.InternalError_):
        return ErroAPI(422, "geometria_invalida", f"geometria recusada pelo banco: {msg}")
    if isinstance(e, psycopg2.errors.StringDataRightTruncation):
        return ErroAPI(422, "texto_grande", msg)
    from app.catalogo import comum

    return comum.erro_do_banco(e)


# ---------------------------------------------------------------- planejamento (nada é escrito aqui)
def _colunas_da_camada(dados: dict) -> dict[str, str]:
    cols = {}
    for c in dados.get("campos") or []:
        nome, tipo = c.get("nome"), str(c.get("tipo") or "text")
        if isinstance(nome, str) and nome not in RESERVADOS and _RE_TIPO_PG.match(tipo):
            cols[nome] = tipo
    return cols


def _campo_alvo(plano: Plano, campo: str | None) -> tuple[str, str]:
    if not campo:
        raise ErroAPI(422, "campo_obrigatorio", "informe `campo`", {"campo": "campo"})
    if campo in RESERVADOS:
        raise ErroAPI(422, "campo_de_rastreio", f"campo de rastreio não se calcula: {campo}", {"campo": campo})
    if campo not in plano.colunas:
        raise ErroAPI(422, "campo_inexistente", f"campo inexistente nesta camada: {campo}", {"campo": campo})
    if (plano.dados.get("regras_campo") or {}).get(campo, {}).get("somente_leitura"):
        raise ErroAPI(422, "campo_somente_leitura", f"campo somente-leitura: {campo}", {"campo": campo})
    return campo, plano.colunas[campo]


def _analisar(texto: str | None, onde: str) -> Any:
    if not texto or not texto.strip():
        raise ErroAPI(422, "expressao_vazia", f"informe `{onde}`", {"campo": onde})
    try:
        return expr.analisar(texto)
    except expr.ErroExpressao as e:
        raise _erro_expressao(e) from e


def _traduzir(plano: Plano, ast, avaliacao: str, tipo_alvo: str | None) -> None:
    """Decide sql × linha a linha para `calcular`: pedido explícito, subconjunto traduzível e tipo do campo alvo
    compatível com o tipo da expressão (texto ← número passa pela formatação do avaliador: linha a linha)."""
    plano.ast = ast
    if avaliacao == "linha_a_linha":
        plano.traducao, plano.traducao_motivo = "linha_a_linha", "pedido pelo chamador"
        return
    try:
        sql, params, tipo = compilar(ast, plano.colunas, plano.derivados)
    except NaoTraduzivel as e:
        if avaliacao == "sql":
            raise ErroAPI(422, "expressao_sem_traducao", f"expressão sem tradução SQL: {e.motivo}") from e
        plano.traducao, plano.traducao_motivo = "linha_a_linha", e.motivo
        return
    except expr.ErroExpressao as e:
        raise _erro_expressao(e) from e
    if tipo_alvo is not None:
        alvo_num = tipo_alvo in ("integer", "bigint", "smallint", "double precision", "real", "numeric")
        alvo_txt = tipo_alvo in ("text", "character varying", "varchar")
        alvo_bool = tipo_alvo == "boolean"
        compativel = tipo == "nulo" or (alvo_num and tipo == "numero") or (alvo_txt and tipo == "texto") \
            or (alvo_bool and tipo == "booleano")
        if not compativel:
            motivo = f"expressão de tipo {tipo} para campo {tipo_alvo}: conversão pela regra do avaliador"
            if avaliacao == "sql":
                raise ErroAPI(422, "expressao_sem_traducao", motivo)
            plano.traducao, plano.traducao_motivo = "linha_a_linha", motivo
            return
    plano.sql_expr, plano.sql_params, plano.traducao = sql, params, "sql"


def _contexto_da_linha(plano: Plano, linha: dict) -> dict:
    ctx: dict[str, Any] = {}
    for nome in plano.colunas:
        v = linha.get(nome)
        if isinstance(v, decimal.Decimal):
            v = float(v)
        elif isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
            v = v.isoformat()
        elif isinstance(v, (bytes, memoryview)):
            v = None
        ctx[nome] = v
    for nome in plano.derivados:
        v = linha.get(f"__{nome}")
        ctx[nome] = float(v) if v is not None else None
    ctx["fid"] = linha.get("fid")
    return ctx


def _sql_leitura(plano: Plano) -> str:
    cols = ", ".join(_ident(c) for c in plano.colunas)
    deriv = "".join(f", ({sql}) AS __{nome}" for nome, sql in plano.derivados.items())
    return f'SELECT fid, globalid{", " + cols if cols else ""}{deriv} FROM "{plano.schema}"."{plano.tabela}"'


def _selecionar_por_expressao_python(cur, plano: Plano, ast) -> list[int]:
    """`onde` sem tradução SQL: percorre a seleção em blocos e guarda os fids em que a expressão é verdadeira."""
    fids: list[int] = []
    ultimo = -1
    while True:
        cur.execute(_sql_leitura(plano) + " WHERE fid > %s ORDER BY fid LIMIT %s", (ultimo, limites.LOTE_TRANSACAO))
        linhas = cur.fetchall()
        if not linhas:
            return fids
        for ln in linhas:
            try:
                v = expr.avaliar(ast, _contexto_da_linha(plano, ln), limite_ms=limites.LOTE_EXPRESSAO_MS)
            except expr.ErroExpressao as e:
                raise _erro_expressao(e, str(ln["globalid"])) from e
            if v is True:
                fids.append(int(ln["fid"]))
        ultimo = int(linhas[-1]["fid"])


def _resolver_selecao(cur, plano: Plano, corpo: LoteEntrada, ator: Ator) -> None:
    sel = corpo.selecao
    formas = sum(1 for x in (sel.ids is not None, bool(sel.onde), sel.todas) if x)
    if formas != 1:
        raise ErroAPI(422, "selecao_invalida", "informe exatamente uma seleção: `ids`, `onde` ou `todas`")
    partes: list[str] = []
    params: list = []
    if sel.ids is not None:
        ids = []
        for i in sel.ids:
            try:
                ids.append(str(__import__("uuid").UUID(str(i))))
            except (ValueError, TypeError) as e:
                raise ErroAPI(422, "selecao_invalida", f"id inválido na seleção: {i!r}") from e
        partes.append("globalid = ANY(%s::uuid[])")
        params.append(ids)
    elif sel.onde:
        ast = _analisar(sel.onde, "selecao.onde")
        try:
            sql, p, tipo = compilar(ast, plano.colunas, plano.derivados)
            if tipo not in ("booleano", "nulo"):
                raise ErroAPI(422, "tipo_invalido", f"`onde` deve ser booleano, é {tipo}")
            partes.append(f"coalesce(({sql}), false)")
            params.extend(p)
        except NaoTraduzivel as e:
            plano.avisos.append(f"seleção `onde` avaliada linha a linha: {e.motivo}")
            fids = _selecionar_por_expressao_python(cur, plano, ast)
            partes.append("fid = ANY(%s::bigint[])")
            params.append(fids)
        except expr.ErroExpressao as e:
            raise _erro_expressao(e) from e
    else:
        partes.append("TRUE")
    if (plano.dados.get("edicao") or {}).get("somente_proprias") and not ator.editar_total:
        cur.execute(f'SELECT count(*) AS n FROM "{plano.schema}"."{plano.tabela}" WHERE {" AND ".join(partes)}', params)
        antes = cur.fetchone()["n"]
        partes.append("criado_por = %s")
        params.append(ator.usuario_id)
        cur.execute(f'SELECT count(*) AS n FROM "{plano.schema}"."{plano.tabela}" WHERE {" AND ".join(partes)}', params)
        depois = cur.fetchone()["n"]
        if depois < antes:
            plano.avisos.append(f"{antes - depois} feição(ões) de outros usuários fora do lote "
                                "(esta camada só permite editar as próprias)")
    plano.sel_sql = " AND ".join(partes)
    plano.sel_params = params
    cur.execute(f'SELECT fid FROM "{plano.schema}"."{plano.tabela}" WHERE {plano.sel_sql} ORDER BY fid', params)
    plano.fids = [int(r["fid"]) for r in cur.fetchall()]


def _planejar_destino(cur, plano: Plano, corpo: LoteEntrada, ator: Ator) -> None:
    if not corpo.destino:
        raise ErroAPI(422, "destino_obrigatorio", "copiar/mover exige `destino.camada`")
    item_d, dados_d = camada_ou_404(cur, corpo.destino.camada)
    if not ator.editar_total and not (dados_d.get("edicao") or {}).get("habilitada"):
        raise ErroAPI(403, "edicao_desabilitada", "edição de feição não habilitada na camada de destino")
    schema_d, tabela_d = _schema_tabela(dados_d)
    if schema_d == plano.schema and tabela_d == plano.tabela:
        raise ErroAPI(422, "destino_invalido", "a camada de destino é a própria camada de origem")
    colunas_d = _colunas_da_camada(dados_d)
    regras_d = dados_d.get("regras_campo") or {}
    mapeamento = {}
    for dest, orig in corpo.destino.mapeamento.items():
        if dest in RESERVADOS or dest not in colunas_d:
            raise ErroAPI(422, "campo_inexistente", f"campo inexistente na camada de destino: {dest}", {"campo": dest})
        if regras_d.get(dest, {}).get("somente_leitura"):
            raise ErroAPI(422, "campo_somente_leitura", f"campo somente-leitura no destino: {dest}", {"campo": dest})
        if orig not in plano.colunas:
            raise ErroAPI(422, "campo_inexistente", f"campo inexistente na camada de origem: {orig}", {"campo": orig})
        mapeamento[dest] = orig
    geom_sql = None
    tipo_o, tipo_d = plano.dados.get("geometria"), dados_d.get("geometria")
    tem_geom_d = tipo_d not in (None, "nenhuma")
    if plano.tem_geom and tem_geom_d:
        if tipo_o != tipo_d and MULTI_DE.get(tipo_o) != tipo_d and tipo_d != "Geometry":
            raise ErroAPI(422, "tipo_geometria_invalido",
                          f"geometria {tipo_o} da origem não cabe na coluna {tipo_d} do destino",
                          {"tipo_enviado": tipo_o, "tipo_esperado": tipo_d})
        geom_sql = "geom"
        if int(plano.dados["srid"]) != int(dados_d["srid"]):
            geom_sql = f"ST_Transform(geom, {int(dados_d['srid'])})"
        if MULTI_DE.get(tipo_o) == tipo_d:
            geom_sql = f"ST_Multi({geom_sql})"
    elif plano.tem_geom != tem_geom_d:
        raise ErroAPI(422, "camada_sem_geometria", "origem e destino precisam ambas ter (ou não ter) geometria")
    plano.destino = {"schema": schema_d, "tabela": tabela_d, "dados": dados_d, "mapeamento": mapeamento,
                     "geom_sql": geom_sql, "item_id": str(item_d["id"]), "colunas": colunas_d}


def planejar(cur, camada_id: str, corpo: LoteEntrada, ator: Ator) -> Plano:
    """Resolve camada, campo, expressão (tradução) e seleção; não grava nada."""
    _item, dados = camada_ou_404(cur, camada_id)
    if not ator.editar_total and not (dados.get("edicao") or {}).get("habilitada"):
        raise ErroAPI(403, "edicao_desabilitada", "edição de feição não habilitada nesta camada")
    schema, tabela = _schema_tabela(dados)
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    plano = Plano(dados=dados, schema=schema, tabela=tabela, tem_geom=tem_geom, colunas=_colunas_da_camada(dados),
                  derivados=dict(DERIVADOS) if tem_geom else {})
    op = corpo.operacao
    if op == "calcular":
        plano.campo, plano.tipo_campo = _campo_alvo(plano, corpo.campo)
        _traduzir(plano, _analisar(corpo.expressao, "expressao"), corpo.avaliacao, plano.tipo_campo)
        if corpo.modo == "parcial" and plano.traducao == "sql":
            plano.traducao, plano.traducao_motivo = "linha_a_linha", "modo parcial avalia linha a linha"
    elif op == "atribuir":
        plano.campo, plano.tipo_campo = _campo_alvo(plano, corpo.campo)
        limpos, _av = validar_atributos({plano.campo: corpo.valor}, dados, "atualizar")
        plano.valor = limpos.get(plano.campo)
    elif op == "corrigir_geometria":
        if not tem_geom:
            raise ErroAPI(422, "camada_sem_geometria", "esta camada não tem coluna de geometria")
        if (dados.get("edicao") or {}).get("geometria_travada"):
            raise ErroAPI(422, "geometria_travada", "geometria travada nesta camada: só atributo é editável")
    elif op in ("copiar", "mover"):
        _planejar_destino(cur, plano, corpo, ator)
    if corpo.modo == "parcial" and op not in ("calcular", "atribuir"):
        raise ErroAPI(422, "modo_invalido", "o modo parcial só vale para calcular/atribuir")
    _resolver_selecao(cur, plano, corpo, ator)
    return plano


# ---------------------------------------------------------------- validação de domínio em SQL (caminho sql)
def _condicoes_invalidas(campo: str, tipo: str, regra: dict, inserindo: bool) -> tuple[list[str], list]:
    ident = _ident(campo)
    conds: list[tuple[str, str]] = []
    params: list = []
    numerico = tipo in ("integer", "bigint", "smallint", "double precision", "real", "numeric")
    valores = regra.get("dominio_valores")
    if valores is not None:
        arr = "double precision" if numerico else ("boolean" if tipo == "boolean" else "text")
        conds.append(("fora_do_dominio", f"({ident} IS NOT NULL AND NOT ({ident}::{arr} = ANY(%s::{arr}[])))"))
        params.append([float(v) if numerico else v for v in valores])
    if numerico:
        if regra.get("dominio_min") is not None:
            conds.append(("fora_do_dominio", f"({ident} < %s)"))
            params.append(float(regra["dominio_min"]))
        if regra.get("dominio_max") is not None:
            conds.append(("fora_do_dominio", f"({ident} > %s)"))
            params.append(float(regra["dominio_max"]))
    if tipo in ("text", "character varying", "varchar"):
        conds.append(("texto_grande", f"(octet_length({ident}) > %s)"))
        params.append(limites.EDICAO_TEXTO_MAX)
    if inserindo and regra.get("obrigatorio"):
        conds.append(("campo_obrigatorio", f"({ident} IS NULL)"))
    return [f"CASE WHEN {c} THEN '{codigo}' END" for codigo, c in conds], params


def _conferir_dominio_sql(cur, schema: str, tabela: str, colunas: dict[str, str], regras: dict, campos: list[str],
                          chave: str, valores: list, inserindo: bool) -> None:
    """Depois de um UPDATE/INSERT por SQL, procura no sub-lote linhas que violem tipo/tamanho/domínio — a mesma
    regra de `validar_atributos`, escrita em SQL; a primeira violação derruba o lote (modo transação)."""
    for campo in campos:
        regra = regras.get(campo) or {}
        cases, params = _condicoes_invalidas(campo, colunas[campo], regra, inserindo)
        if not cases:
            continue
        cur.execute(
            f'SELECT globalid, {_ident(campo)} AS valor, coalesce({", ".join(cases)}) AS codigo '
            f'FROM "{schema}"."{tabela}" WHERE {chave} = ANY(%s) AND coalesce({", ".join(cases)}) IS NOT NULL LIMIT 5',
            [*params, valores, *params],
        )
        ruins = cur.fetchall()
        if ruins:
            codigo = ruins[0]["codigo"]
            mensagens = {"fora_do_dominio": "valor fora do domínio do campo", "texto_grande": "texto acima do limite",
                         "campo_obrigatorio": "campo obrigatório vazio"}
            raise ErroAPI(422, codigo, f"{mensagens[codigo]} {campo} em {len(ruins)}+ feição(ões)",
                          {"campo": campo, "ids": [str(r["globalid"]) for r in ruins],
                           "valor": _json_seguro(ruins[0]["valor"])})


def _json_seguro(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, (bytes, memoryview)):
        return None
    return v


# ---------------------------------------------------------------- execução (dentro da transação de quem chama)
def _atualizar_sql(cur, plano: Plano, lote: list[int], ator: Ator, valor_sql: str, params: list) -> int:
    cur.execute(
        f'UPDATE "{plano.schema}"."{plano.tabela}" SET {_ident(plano.campo)} = {valor_sql}, '
        f"atualizado_em = now(), atualizado_por = %s WHERE fid = ANY(%s::bigint[])",
        [*params, ator.usuario_id, lote],
    )
    return cur.rowcount


def _calcular_sql_lote(cur, plano: Plano, lote: list[int], ator: Ator) -> int:
    tipo = plano.tipo_campo
    if tipo in ("integer", "bigint", "smallint"):
        # o avaliador só aceita inteiro exato num campo inteiro (tipo_invalido); o cast do banco arredondaria
        cur.execute(
            f'SELECT globalid FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[]) '
            f"AND ({plano.sql_expr}) IS NOT NULL AND ({plano.sql_expr}) <> trunc(({plano.sql_expr})::numeric) LIMIT 1",
            [lote, *plano.sql_params, *plano.sql_params, *plano.sql_params],
        )
        r = cur.fetchone()
        if r:
            raise ErroAPI(422, "tipo_invalido", f"campo {plano.campo} exige inteiro",
                          {"campo": plano.campo, "id": str(r["globalid"])})
    n = _atualizar_sql(cur, plano, lote, ator, f"({plano.sql_expr})::{tipo}", plano.sql_params)
    _conferir_dominio_sql(cur, plano.schema, plano.tabela, plano.colunas, plano.dados.get("regras_campo") or {},
                          [plano.campo], "fid", lote, False)
    return n


def _calcular_linhas_lote(cur, plano: Plano, lote: list[int], ator: Ator, corpo: LoteEntrada,
                          falhas: list[LoteFalha], contagem: dict) -> int:
    cur.execute(_sql_leitura(plano) + " WHERE fid = ANY(%s::bigint[]) ORDER BY fid", (lote,))
    linhas = cur.fetchall()
    fids: list[int] = []
    valores: list = []
    for ln in linhas:
        gid = str(ln["globalid"])
        try:
            v = expr.avaliar(plano.ast, _contexto_da_linha(plano, ln), limite_ms=limites.LOTE_EXPRESSAO_MS)
            limpos, _av = validar_atributos({plano.campo: v}, plano.dados, "atualizar")
            v = limpos.get(plano.campo)
        except (expr.ErroExpressao, ErroAPI) as e:
            erro = _erro_expressao(e, gid) if isinstance(e, expr.ErroExpressao) else e
            if corpo.modo == "transacao":
                if isinstance(erro, ErroAPI) and isinstance(erro.detalhe, dict):
                    erro.detalhe.setdefault("id", gid)
                raise erro from e
            contagem["falhas"] += 1
            if len(falhas) < limites.LOTE_FALHAS_MAX:
                falhas.append(LoteFalha(id=gid, erro=erro.erro, mensagem=str(erro.detail), detalhe=erro.detalhe))
            continue
        fids.append(int(ln["fid"]))
        valores.append(None if v is None else (json.dumps(v) if isinstance(v, (list, dict)) else str(v)))
    if not fids:
        return 0
    cur.execute(
        f'UPDATE "{plano.schema}"."{plano.tabela}" AS x SET {_ident(plano.campo)} = v.valor::{plano.tipo_campo}, '
        f"atualizado_em = now(), atualizado_por = %s "
        f"FROM unnest(%s::bigint[], %s::text[]) AS v(fid, valor) WHERE x.fid = v.fid",
        (ator.usuario_id, fids, valores),
    )
    return cur.rowcount


def _corrigir_lote(cur, plano: Plano, lote: list[int], ator: Ator) -> int:
    dim = _DIM.get(plano.dados.get("geometria"))
    corrigida = "ST_MakeValid(geom)"
    if dim:
        corrigida = f"ST_CollectionExtract({corrigida}, {dim})"
        if str(plano.dados.get("geometria", "")).startswith("Multi"):
            corrigida = f"ST_Multi({corrigida})"
    cur.execute(
        f'UPDATE "{plano.schema}"."{plano.tabela}" SET geom = {corrigida}, atualizado_em = now(), atualizado_por = %s '
        f"WHERE fid = ANY(%s::bigint[]) AND NOT ST_IsValid(geom)",
        (ator.usuario_id, lote),
    )
    return cur.rowcount


def _copiar_lote(cur, plano: Plano, lote: list[int], ator: Ator, mover: bool) -> int:
    d = plano.destino
    cols_d = [_ident(k) for k in d["mapeamento"]]
    cols_o = [_ident(v) for v in d["mapeamento"].values()]
    if d["geom_sql"]:
        cols_d.append("geom")
        cols_o.append(d["geom_sql"])
    cols_d.append("criado_por")
    cols_o.append("%s")
    cur.execute(
        f'INSERT INTO "{d["schema"]}"."{d["tabela"]}" ({", ".join(cols_d)}) '
        f'SELECT {", ".join(cols_o)} FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[]) '
        f"ORDER BY fid RETURNING globalid",
        (ator.usuario_id, lote),
    )
    novos = [str(r["globalid"]) for r in cur.fetchall()]
    _conferir_dominio_sql(cur, d["schema"], d["tabela"], d["colunas"], d["dados"].get("regras_campo") or {},
                          list(d["colunas"]), "globalid::text", novos, True)
    if mover:
        cur.execute(f'DELETE FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[])', (lote,))
    return len(novos)


def executar(cur, plano: Plano, corpo: LoteEntrada, ator: Ator, progresso: Progresso | None = None) -> LoteSaida:
    """Aplica a operação sobre `plano.fids` em sub-lotes de LOTE_TRANSACAO, na transação do cursor recebido.
    Levanta ErroAPI (modo transação) — quem chama desfaz a transação inteira."""
    t0 = time.monotonic()
    saida = LoteSaida(execucao="sincrono", operacao=corpo.operacao, total=len(plano.fids), avisos=list(plano.avisos),
                      traducao=plano.traducao, traducao_motivo=plano.traducao_motivo)
    contagem = {"falhas": 0}
    feitas = 0
    try:
        for i in range(0, len(plano.fids), limites.LOTE_TRANSACAO):
            lote = plano.fids[i:i + limites.LOTE_TRANSACAO]
            op = corpo.operacao
            if op == "calcular" and plano.traducao == "sql":
                saida.alteradas += _calcular_sql_lote(cur, plano, lote, ator)
            elif op == "calcular":
                saida.alteradas += _calcular_linhas_lote(cur, plano, lote, ator, corpo, saida.falhas, contagem)
            elif op == "atribuir":
                saida.alteradas += _atualizar_sql(cur, plano, lote, ator, f"%s::{plano.tipo_campo}", [plano.valor])
            elif op == "apagar":
                cur.execute(f'DELETE FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[])', (lote,))
                saida.apagadas += cur.rowcount
            elif op == "corrigir_geometria":
                saida.corrigidas += _corrigir_lote(cur, plano, lote, ator)
            elif op in ("copiar", "mover"):
                n = _copiar_lote(cur, plano, lote, ator, op == "mover")
                saida.criadas += n
                if op == "mover":
                    saida.apagadas += n
            feitas += len(lote)
            if progresso:
                progresso(feitas, len(plano.fids))
    except psycopg2.Error as e:
        raise erro_do_banco_lote(e) from e
    saida.falhas_total = contagem["falhas"]
    saida.duracao_ms = int((time.monotonic() - t0) * 1000)
    return saida


def registrar_efeitos(cur, plano: Plano, saida: LoteSaida, item_id: str, evento: Callable[[str, dict], None]) -> None:
    """Bump de `tiles_versao` (origem e destino) e um evento por lote — o mesmo que `aplicar_edicoes` faz."""
    tocadas = saida.alteradas + saida.apagadas + saida.criadas + saida.corrigidas
    itens = [item_id] + ([plano.destino["item_id"]] if plano.destino and saida.criadas else [])
    if tocadas:
        for iid in itens:
            cur.execute(
                "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
                "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid", (iid,),
            )
    evento("camadas/lote", {"operacao": saida.operacao, "execucao": saida.execucao, "total": saida.total,
                            "alteradas": saida.alteradas, "apagadas": saida.apagadas, "criadas": saida.criadas,
                            "corrigidas": saida.corrigidas, "falhas": saida.falhas_total, "modo": plano.traducao,
                            "destino": plano.destino["item_id"] if plano.destino else None})


# ---------------------------------------------------------------- pré-visualização (nunca grava)
def previa(cur, plano: Plano, corpo: LoteEntrada, ator: Ator) -> LoteSaida:
    fids = plano.fids[:limites.LOTE_PREVIA]
    saida = LoteSaida(execucao="previa", operacao=corpo.operacao, total=len(plano.fids), avisos=list(plano.avisos),
                      traducao=plano.traducao, traducao_motivo=plano.traducao_motivo, previa=[])
    if not fids:
        return saida
    op = corpo.operacao
    try:
        if op == "calcular" and plano.traducao == "sql":
            cur.execute(
                f'SELECT globalid, {_ident(plano.campo)} AS antes, ({plano.sql_expr})::{plano.tipo_campo} AS depois '
                f'FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[]) ORDER BY fid',
                [*plano.sql_params, fids],
            )
            for r in cur.fetchall():
                saida.previa.append(LotePrevia(id=str(r["globalid"]), antes=_json_seguro(r["antes"]),
                                               depois=_json_seguro(r["depois"])))
        elif op == "calcular":
            cur.execute(_sql_leitura(plano) + " WHERE fid = ANY(%s::bigint[]) ORDER BY fid", (fids,))
            for ln in cur.fetchall():
                gid = str(ln["globalid"])
                antes = _json_seguro(ln.get(plano.campo))
                try:
                    v = expr.avaliar(plano.ast, _contexto_da_linha(plano, ln), limite_ms=limites.LOTE_EXPRESSAO_MS)
                    limpos, _av = validar_atributos({plano.campo: v}, plano.dados, "atualizar")
                    saida.previa.append(LotePrevia(id=gid, antes=antes, depois=_json_seguro(limpos.get(plano.campo))))
                except (expr.ErroExpressao, ErroAPI) as e:
                    erro = _erro_expressao(e, gid) if isinstance(e, expr.ErroExpressao) else e
                    saida.previa.append(LotePrevia(id=gid, antes=antes, erro=erro.erro, mensagem=str(erro.detail)))
        elif op in ("atribuir", "apagar"):
            cur.execute(_sql_leitura(plano) + " WHERE fid = ANY(%s::bigint[]) ORDER BY fid", (fids,))
            for ln in cur.fetchall():
                gid = str(ln["globalid"])
                if op == "atribuir":
                    saida.previa.append(LotePrevia(id=gid, antes=_json_seguro(ln.get(plano.campo)), depois=plano.valor))
                else:
                    atrs = {c: _json_seguro(ln.get(c)) for c in plano.colunas}
                    saida.previa.append(LotePrevia(id=gid, antes=atrs, depois=None))
        elif op == "corrigir_geometria":
            dim = _DIM.get(plano.dados.get("geometria"))
            corrigida = f"ST_CollectionExtract(ST_MakeValid(geom), {dim})" if dim else "ST_MakeValid(geom)"
            cur.execute(
                f"SELECT globalid, ST_IsValid(geom) AS valida, ST_IsValidReason(geom) AS motivo, "
                f"GeometryType({corrigida}) AS tipo_depois, ST_IsValid({corrigida}) AS valida_depois "
                f'FROM "{plano.schema}"."{plano.tabela}" WHERE fid = ANY(%s::bigint[]) ORDER BY fid', (fids,),
            )
            for r in cur.fetchall():
                saida.previa.append(LotePrevia(
                    id=str(r["globalid"]), antes={"valida": r["valida"], "motivo": r["motivo"]},
                    depois=None if r["valida"] else {"valida": r["valida_depois"], "tipo": r["tipo_depois"]}))
        elif op in ("copiar", "mover"):
            d = plano.destino
            cur.execute(_sql_leitura(plano) + " WHERE fid = ANY(%s::bigint[]) ORDER BY fid", (fids,))
            for ln in cur.fetchall():
                antes = {c: _json_seguro(ln.get(c)) for c in plano.colunas}
                depois = {dest: _json_seguro(ln.get(orig)) for dest, orig in d["mapeamento"].items()}
                saida.previa.append(LotePrevia(id=str(ln["globalid"]), antes=antes, depois=depois))
    except psycopg2.Error as e:
        raise erro_do_banco_lote(e) from e
    return saida
