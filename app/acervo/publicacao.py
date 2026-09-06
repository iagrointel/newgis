"""Leitura das camadas publicadas sem cópia (item L6-01-b-view-so-leitura; migração
20260906T15521aa_acervo_publicacao.sql; publicador `scripts/acervo_publicar.py`).

Cada camada exposta do registro (`plat.acervo_camada`) vira uma view em `plat_acervo`, com a lista branca de
colunas e o porteiro `plat.acervo_pode_ler('<camada>')` no WHERE. Estas rotas são a porta HTTP dessas views:

  GET    /api/acervo/camadas                        lista o que está publicado e o que este inquilino assina
  POST   /api/acervo/camadas/{camada}/assinatura    o inquilino passa a poder ler a camada
  DELETE /api/acervo/camadas/{camada}/assinatura    o inquilino deixa de poder ler
  GET    /api/acervo/camadas/{camada}/feicoes       GeoJSON por caixa envolvente
  GET    /api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt   tile vetorial da MESMA view

O caminho usa `view_nome` (minúsculo, [a-z0-9_]) e não o `acervo_camada_id` (que tem '/' e '.'). A tradução
de um para o outro é uma consulta a `plat.acervo_publicacao`, nunca uma montagem de string.

Só leitura, e a recusa não é da aplicação: a view NÃO tem GRANT de INSERT/UPDATE/DELETE para `plat_app`, e a
tabela de origem em `public` não tem GRANT nenhum para `plat_app` (as duas provas negativas estão em
tests/api/test_acervo_publicacao.py, feitas com a role da aplicação, não com postgres). Por isso não existe
rota de escrita aqui: qualquer verbo de escrita nestes caminhos devolve 405 do próprio FastAPI.

Sem assinatura o resultado é 403 na API e ZERO LINHA na view — os dois, não um ou outro. O 403 é conveniência
de quem chama; a garantia é a view.
"""

import json
import re

from fastapi import APIRouter, Path, Query, Request, Response

from app import db
from app.acervo.modelos import AcervoCamadaPagina, AcervoFeicoes
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(tags=["acervo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ASSINAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
LIMITE_MAX = 5000
_NOME_VIEW = re.compile(r"^[a-z0-9_]{1,63}$")


def _schema_views() -> str:
    """`plat_acervo` em produção; `<schema>_acervo` em homologação e nas bases por trilha (a mesma regra que
    app/schema_ambiente.py aplica ao texto das consultas)."""
    return f"{settings.PLAT_SCHEMA}_acervo"


def _publicacao(cur, camada: str) -> dict:
    """Linha de plat.acervo_publicacao pelo nome da view. 404 quando não existe — a API não distingue
    'camada inexistente' de 'camada não publicada': quem não pode ver não recebe confirmação de existência."""
    if not _NOME_VIEW.match(camada):
        raise ErroAPI(404, "camada_inexistente", "camada do acervo inexistente")
    cur.execute(
        "SELECT p.acervo_camada_id, p.view_nome, p.schema_origem, p.tabela_origem, p.coluna_geom, p.srid, "
        "p.colunas, c.fonte_id, c.linhas_exatas "
        "FROM plat.acervo_publicacao p JOIN plat.acervo_camada c USING (acervo_camada_id) "
        "WHERE p.view_nome = %s",
        (camada,),
    )
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "camada_inexistente", "camada do acervo inexistente")
    return linha


def _exigir_assinatura(cur, pub: dict) -> None:
    cur.execute("SELECT plat.acervo_pode_ler(%s) AS pode", (pub["acervo_camada_id"],))
    if not cur.fetchone()["pode"]:
        raise ErroAPI(
            403,
            "sem_assinatura",
            "o inquilino não assina esta camada do acervo",
            {"camada": pub["view_nome"]},
        )


@router.get("/api/acervo/camadas", response_model=AcervoCamadaPagina, openapi_extra=LER)
def listar_camadas(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT p.view_nome, p.acervo_camada_id, c.fonte_id, p.schema_origem, p.tabela_origem, "
            "p.coluna_geom, p.srid, p.colunas, c.linhas_exatas, c.tipo_geom, "
            "(a.tenant_id IS NOT NULL) AS assinada "
            "FROM plat.acervo_publicacao p "
            "JOIN plat.acervo_camada c USING (acervo_camada_id) "
            "LEFT JOIN plat.acervo_assinatura a ON a.acervo_camada_id = p.acervo_camada_id "
            "ORDER BY p.view_nome"
        )
        linhas = cur.fetchall()
    return {"total": len(linhas), "camadas": [dict(li) for li in linhas]}


@router.post("/api/acervo/camadas/{camada}/assinatura", status_code=201, openapi_extra=ASSINAR)
def assinar(camada: str, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        pub = _publicacao(cur, camada)
        cur.execute(
            "INSERT INTO plat.acervo_assinatura(tenant_id, acervo_camada_id, assinado_por) "
            "VALUES (%s, %s, %s) ON CONFLICT (tenant_id, acervo_camada_id) DO NOTHING",
            (auth.tenant_id, pub["acervo_camada_id"], auth.usuario_id),
        )
        registrar_evento(cur, request, "acervo/assinar", "acervo_camada", None,
                         {"camada": camada, "acervo_camada_id": pub["acervo_camada_id"]})
    return {"camada": camada, "assinada": True}


@router.delete("/api/acervo/camadas/{camada}/assinatura", openapi_extra=ASSINAR)
def cancelar_assinatura(camada: str, request: Request, auth: Auth = autenticado("conteudo.registrar_fonte")):
    ctx = auth.contexto()
    with db.db(ctx) as cur:
        pub = _publicacao(cur, camada)
        cur.execute(
            "DELETE FROM plat.acervo_assinatura WHERE tenant_id = %s AND acervo_camada_id = %s",
            (auth.tenant_id, pub["acervo_camada_id"]),
        )
        registrar_evento(cur, request, "acervo/cancelar", "acervo_camada", None,
                         {"camada": camada, "acervo_camada_id": pub["acervo_camada_id"]})
    return {"camada": camada, "assinada": False}


def _caixa(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    partes = bbox.split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ser 'oeste,sul,leste,norte' em graus")
    try:
        oeste, sul, leste, norte = (float(p) for p in partes)
    except ValueError:
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ser 'oeste,sul,leste,norte' em graus") from None
    if not (oeste < leste and sul < norte):
        raise ErroAPI(422, "bbox_invalida", "bbox precisa ter oeste < leste e sul < norte")
    return oeste, sul, leste, norte


@router.get("/api/acervo/camadas/{camada}/feicoes", response_model=AcervoFeicoes, openapi_extra=LER)
def feicoes(
    camada: str,
    bbox: str | None = Query(default=None, description="oeste,sul,leste,norte em graus (EPSG:4326)"),
    limite: int = Query(default=500, ge=1, le=LIMITE_MAX),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    with db.db(auth.contexto()) as cur:
        pub = _publicacao(cur, camada)
        _exigir_assinatura(cur, pub)
        caixa = _caixa(bbox)
        colunas = [c for c in pub["colunas"] if c != pub["coluna_geom"]]
        # identificadores vêm do REGISTRO (validados por _NOME_VIEW e pela lista de colunas da view), nunca do
        # chamador; ainda assim vão citados por format_ident, que é a citação do próprio servidor.
        lista = ", ".join(_ident(c) for c in colunas)
        geom = _ident(pub["coluna_geom"])
        onde, params = "true", []
        if caixa:
            onde = f"{geom} && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"
            params = list(caixa)
        sql = (
            f"SELECT {lista}, ST_AsGeoJSON({geom})::json AS geometria "
            f'FROM {_ident(_schema_views())}.{_ident(pub["view_nome"])} WHERE {onde} LIMIT %s'
        )
        cur.execute(sql, [*params, limite])
        linhas = cur.fetchall()
    feats = []
    for li in linhas:
        g = li.pop("geometria")
        feats.append({"type": "Feature", "geometry": g, "properties": {k: _json_ok(v) for k, v in li.items()}})
    return {"type": "FeatureCollection", "camada": camada, "total": len(feats), "features": feats}


@router.get("/api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt", openapi_extra=LER)
def tile(
    camada: str,
    z: int = Path(ge=0, le=22),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela)."""
    limite = 1 << z
    if x >= limite or y >= limite:
        raise ErroAPI(422, "tile_invalido", f"x e y precisam ser menores que {limite} no zoom {z}")
    with db.db(auth.contexto()) as cur:
        pub = _publicacao(cur, camada)
        _exigir_assinatura(cur, pub)
        geom = _ident(pub["coluna_geom"])
        alvo = f'{_ident(_schema_views())}.{_ident(pub["view_nome"])}'
        # o recorte acontece em 4326 (ST_Transform da CAIXA, não da coluna): assim o índice GiST da tabela
        # original é usado e só as feições que sobram são reprojetadas. Transformar a coluna no WHERE varreria
        # as 7,36 mi de linhas e estoura em geometria com coordenada inválida (medido: "transform: Invalid
        # coordinate (2049)" no CAR nacional).
        cur.execute(
            f"WITH caixa AS (SELECT ST_TileEnvelope(%s, %s, %s) AS env), "  # noqa: S608 — identificadores citados
            f"recorte AS (SELECT ST_AsMVTGeom(ST_Transform(ST_MakeValid(t.{geom}), 3857), c.env, 4096, 64, true) "
            f"  AS geom FROM {alvo} t, caixa c WHERE t.{geom} && ST_Transform(c.env, 4326)) "
            f"SELECT ST_AsMVT(recorte, %s, 4096, 'geom') AS mvt FROM recorte WHERE geom IS NOT NULL",
            (z, x, y, camada),
        )
        mvt = cur.fetchone()["mvt"]
    return Response(content=bytes(mvt or b""), media_type="application/vnd.mapbox-vector-tile")


def _ident(nome: str) -> str:
    """Citação de identificador sem depender de conexão aberta: só nomes que já passaram por validação
    chegam aqui (nome de view do registro, coluna da lista branca, schema montado de settings)."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", nome):
        raise ErroAPI(500, "identificador_invalido", "identificador do registro fora do formato esperado")
    return '"' + nome + '"'


def _json_ok(valor):
    """datetime/date/Decimal do psycopg2 não são serializáveis por padrão; nada aqui inventa valor."""
    if valor is None or isinstance(valor, (str, int, float, bool, list, dict)):
        return valor
    try:
        json.dumps(valor)
        return valor
    except TypeError:
        return str(valor)
