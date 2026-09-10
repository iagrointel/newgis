"""Rota `POST /api/camadas/{item_id}/estatisticas` (item L2-06-e-estatisticas-servidor): agregação no
servidor para tabela, gráfico, indicador, legenda e `outStatistics` do FeatureServer — motor puro em
`app/estatistica/agregacao.py`, este módulo só lê o item/colunas do Postgres, compila o filtro e chama
o motor. Cache em processo por `(camada, versão, corpo canônico)`, TTL 30 s (cláusula do portão)."""

from __future__ import annotations

import json
import re
import threading
import time

from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404
from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.estatistica import agregacao as agr
from app.schema_ambiente import reescrever_schema
from app.settings import settings

router = APIRouter(tags=["estatistica"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

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
