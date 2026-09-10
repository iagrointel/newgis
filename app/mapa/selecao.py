"""Seleção e filtro do mapa (item L2-01-h-selecao-filtros): construtor de filtro por atributo em
CQL2-JSON (`app.consulta.cql2`, mesmo vocabulário declarado pela `vista_de_camada` na ADR 0004),
seleção espacial por polígono/retângulo/laço desenhado no cliente e seleção "feições de A que
intersectam/estão a X m de B" entre duas camadas.

Filtro/seleção EFÊMEROS não gravam nada aqui — o cliente aplica o resultado (`ids`) como filtro do
MapLibre e guarda o estado na URL (`web/js/mapa/estado_url.js`). O que é PERSISTENTE reaproveita o
catálogo genérico já pronto (`POST /api/itens`), sem rota nova:

* filtro persistente "na camada do mapa" -> item `tipo=vista_de_camada`, `dados={"camada_id","filtro"}`
  (mesmo objeto CQL2-JSON que este módulo valida em `/filtrar` — o cliente valida chamando `/filtrar`
  antes de salvar, este módulo nunca precisa saber sobre a escrita).
* seleção salva para reuso -> item `tipo=selecao`, `dados={"camada_id","ids","criterio","contagem"}`
  (migração `20260907T1242_selecao_filtro.sql`).

Nenhuma das duas rotas de escrita mora aqui: só o cálculo (contagem, lista de fids, tradução CQL2)."""

from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.consulta.cql2 import GEOJSON_TIPOS, compilar_cql2
from app.consulta.where_ast import ErroWhere
from app.erros import ErroAPI
from app.mapa.rotas import SQL_CAMADA

router = APIRouter(tags=["mapa", "selecao"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
LIMITE_AMOSTRA_PADRAO = 5000
LIMITE_AMOSTRA_MAX = 20000
LIMITE_VALORES_PADRAO = 200
LIMITE_VALORES_MAX = 2000


# =================================================================== leitura da camada + lista branca
def _camada_ou_404(cur, id: str) -> dict:
    cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (id,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "camada_inexistente", "camada inexistente ou sem permissão de leitura")
    return linha


def _tabela_sql(dados: dict) -> str:
    esquema, tabela = dados.get("schema"), dados.get("tabela")
    if not (esquema and tabela and IDENT_RE.match(esquema) and IDENT_RE.match(tabela)):
        raise ErroAPI(422, "camada_sem_tabela", "esta camada não é hospedada: não há tabela para consultar")
    return f'"{esquema}"."{tabela}"'


def _colunas_da_camada(dados: dict) -> dict:
    """Lista branca campo -> {sql, tipo[, srid]} para `compilar_cql2`. `fid` (chave da ingestão, item
    L0-04) e `geom` sempre entram; os demais vêm de `dados.campos`, e só se o nome bater no padrão de
    identificador — um `dados` corrompido nunca vira SQL interpolado sem essa conferência."""
    colunas: dict = {
        "fid": {"sql": '"fid"', "tipo": "bigint"},
        "geom": {"sql": '"geom"', "tipo": "geometry", "srid": int(dados.get("srid") or 4326)},
    }
    for c in dados.get("campos") or []:
        nome = c.get("nome")
        if isinstance(nome, str) and IDENT_RE.match(nome) and nome not in colunas:
            colunas[nome] = {"sql": f'"{nome}"', "tipo": (c.get("tipo") or "text").lower()}
    return colunas


def _campo_permitido(colunas: dict, campo: str) -> dict:
    info = colunas.get(campo)
    if info is None:
        raise ErroAPI(422, "campo_nao_permitido",
                       f"campo não está na lista branca da camada: {campo}", {"campo": campo})
    return info


def _erro_cql2(e: ErroWhere) -> ErroAPI:
    return ErroAPI(422, e.codigo, e.mensagem, e.detalhe)


# =================================================================== /valores (construtor de filtro)
@router.get("/api/mapa/camadas/{id}/valores", openapi_extra=X)
def valores_unicos(id: str, campo: str, limite: int = LIMITE_VALORES_PADRAO,
                    auth: Auth = autenticado(escopo_token="catalogo:ler")):
    limite = max(1, min(limite, LIMITE_VALORES_MAX))
    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
        dados = linha["dados"] or {}
        tabela = _tabela_sql(dados)
        colunas = _colunas_da_camada(dados)
        info = _campo_permitido(colunas, campo)
        if info["tipo"] == "geometry":
            raise ErroAPI(422, "campo_geometria", "campo de geometria não tem valores únicos para o construtor")
        cur.execute(f'SELECT DISTINCT {info["sql"]} AS v FROM {tabela} WHERE {info["sql"]} IS NOT NULL '
                    f'ORDER BY 1 LIMIT %s', (limite,))
        linhas = cur.fetchall()
    valores = [r["v"] for r in linhas]
    return {"campo": campo, "valores": valores, "truncado": len(valores) == limite}


# =================================================================== /filtrar (CQL2-JSON -> contagem + ids)
class FiltrarEntrada(BaseModel):
    filtro: dict
    limite_amostra: int = Field(default=LIMITE_AMOSTRA_PADRAO, ge=1, le=LIMITE_AMOSTRA_MAX)


@router.post("/api/mapa/camadas/{id}/filtrar", openapi_extra=X)
def filtrar(id: str, corpo: FiltrarEntrada, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
        dados = linha["dados"] or {}
        tabela = _tabela_sql(dados)
        colunas = _colunas_da_camada(dados)
        try:
            consulta = compilar_cql2(corpo.filtro, colunas)
        except ErroWhere as e:
            raise _erro_cql2(e) from e
        cur.execute(f"SELECT count(*) AS n FROM {tabela} WHERE {consulta.sql}", consulta.params)
        n = cur.fetchone()["n"]
        cur.execute(f"SELECT fid FROM {tabela} WHERE {consulta.sql} ORDER BY fid LIMIT %s",
                    consulta.params + [corpo.limite_amostra])
        ids = [r["fid"] for r in cur.fetchall()]
    return {"n": n, "ids": ids, "truncado": n > len(ids), "sql_equivalente": consulta.sql}


# =================================================================== /selecionar (geometria desenhada)
MODOS_COMBINACAO = {"novo", "somar", "subtrair", "interseccionar"}


class SelecionarEntrada(BaseModel):
    geometria: dict
    relacao: str = "intersects"  # intersects | dwithin
    distancia_m: float | None = None
    modo: str = "novo"
    ids_atuais: list = Field(default_factory=list)
    limite_amostra: int = Field(default=LIMITE_AMOSTRA_PADRAO, ge=1, le=LIMITE_AMOSTRA_MAX)


@router.post("/api/mapa/camadas/{id}/selecionar", openapi_extra=X)
def selecionar(id: str, corpo: SelecionarEntrada, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    if corpo.relacao not in ("intersects", "dwithin"):
        raise ErroAPI(422, "relacao_invalida", "relacao precisa ser 'intersects' ou 'dwithin'")
    if corpo.modo not in MODOS_COMBINACAO:
        raise ErroAPI(422, "modo_invalido", f"modo precisa ser um de {sorted(MODOS_COMBINACAO)}")
    if not isinstance(corpo.geometria, dict) or corpo.geometria.get("type") not in GEOJSON_TIPOS:
        raise ErroAPI(422, "geometria_invalida", "geometria GeoJSON inválida")
    if corpo.relacao == "dwithin" and (corpo.distancia_m is None or corpo.distancia_m <= 0):
        raise ErroAPI(422, "distancia_invalida", "dwithin exige distancia_m > 0")

    no = {"op": "s_intersects", "args": [{"property": "geom"}, corpo.geometria]}
    if corpo.relacao == "dwithin":
        no = {"op": "s_dwithin", "args": [{"property": "geom"}, corpo.geometria, corpo.distancia_m]}

    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
        dados = linha["dados"] or {}
        tabela = _tabela_sql(dados)
        colunas = _colunas_da_camada(dados)
        try:
            consulta = compilar_cql2(no, colunas)
        except ErroWhere as e:
            raise _erro_cql2(e) from e
        cur.execute(f"SELECT fid FROM {tabela} WHERE {consulta.sql} ORDER BY fid LIMIT %s",
                    consulta.params + [corpo.limite_amostra])
        ids_novos = [r["fid"] for r in cur.fetchall()]

    atuais = set(corpo.ids_atuais or [])
    novos = set(ids_novos)
    if corpo.modo == "novo":
        finais = novos
    elif corpo.modo == "somar":
        finais = atuais | novos
    elif corpo.modo == "subtrair":
        finais = atuais - novos
    else:  # interseccionar
        finais = atuais & novos
    ids_final = sorted(finais)[: corpo.limite_amostra]
    return {"n": len(finais), "ids": ids_final, "truncado": len(finais) > len(ids_final)}


# =================================================================== /selecao-espacial (A x B)
class SelecaoEspacialEntrada(BaseModel):
    camada_a: str
    camada_b: str
    relacao: str = "intersects"
    distancia_m: float | None = None
    limite_amostra: int = Field(default=LIMITE_AMOSTRA_PADRAO, ge=1, le=LIMITE_AMOSTRA_MAX)


@router.post("/api/mapa/selecao-espacial", openapi_extra=X)
def selecao_espacial(corpo: SelecaoEspacialEntrada, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    if corpo.relacao not in ("intersects", "dwithin"):
        raise ErroAPI(422, "relacao_invalida", "relacao precisa ser 'intersects' ou 'dwithin'")
    if corpo.relacao == "dwithin" and (corpo.distancia_m is None or corpo.distancia_m <= 0):
        raise ErroAPI(422, "distancia_invalida", "dwithin exige distancia_m > 0")
    with db.db(auth.contexto()) as cur:
        la = _camada_ou_404(cur, corpo.camada_a)
        lb = _camada_ou_404(cur, corpo.camada_b)
        dados_a, dados_b = la["dados"] or {}, lb["dados"] or {}
        tabela_a, tabela_b = _tabela_sql(dados_a), _tabela_sql(dados_b)
        srid_a = int(dados_a.get("srid") or 4326)
        if corpo.relacao == "intersects":
            cond = f"ST_Intersects(a.geom, ST_Transform(b.geom, {srid_a}))"
            params: list = []
        else:
            cond = "ST_DWithin(ST_Transform(a.geom, 4326)::geography, ST_Transform(b.geom, 4326)::geography, %s)"
            params = [float(corpo.distancia_m)]
        cur.execute(f"SELECT count(*) AS n FROM {tabela_a} a WHERE EXISTS "
                    f"(SELECT 1 FROM {tabela_b} b WHERE {cond})", params)
        n = cur.fetchone()["n"]
        cur.execute(f"SELECT a.fid FROM {tabela_a} a WHERE EXISTS "
                    f"(SELECT 1 FROM {tabela_b} b WHERE {cond}) ORDER BY a.fid LIMIT %s",
                    params + [corpo.limite_amostra])
        ids = [r["fid"] for r in cur.fetchall()]
    return {"n": n, "ids": ids, "truncado": n > len(ids)}
