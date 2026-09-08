"""Rotas do visualizador de mapa (item L2-01-mapa-web).

Três famílias:

* `/api/mapa/camadas` e `/api/mapa/camadas/{id}` — o que o painel "Camadas" precisa para desenhar a
  lista, o estilo e a legenda: título, geometria, número de feições, extensão, campos, simbologia
  (`plat.item.dados.simbologia`, conceito C2), as camadas MapLibre já montadas e a legenda gerada da
  MESMA lista de classes (`app/mapa/simbologia.py`).
* `/api/mapa/camadas/{id}/tilejson` — TileJSON 3.0.0 apontando para o repasse de tile. Ele CUNHA um
  token de serviço de curta duração com escopo `camada:ler:<id>` (só aquela camada, 12 h), porque o
  Martin só sabe autorizar por token no `query_params` da função de tile (conceito C3/C9) e o navegador
  entra por sessão/cookie. O token anterior com o mesmo nome é revogado antes: um usuário nunca acumula
  tokens ao reabrir o mapa.
* `/tiles/{esquema}/{funcao}/{z}/{x}/{y}` — repasse para o Martin (127.0.0.1:8151) com a MESMA validação
  de token que `/internal/tiles/verificar` faz para o `auth_request` do nginx (`app.tiles.rotas.autorizar`,
  uma implementação só). É o caminho usado pelo visualizador e por qualquer cliente que não tenha o nginx
  na frente; com nginx, a mesma URL pode ser servida direto pelo Martin com `auth_request`, sem Python no
  caminho do tile (ADR do item).
"""

from __future__ import annotations

import json
import logging
import secrets

import httpx
from fastapi import APIRouter, Path, Request
from fastapi.responses import Response

from app import db
from app.auth.sessao import Auth, autenticado, sha256_hex
from app.erros import ErroAPI
from app.mapa import simbologia as simb_mod
from app.settings import settings
from app.tiles.rotas import autorizar

log = logging.getLogger("plat.mapa")
router = APIRouter(tags=["mapa"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

# validade do token cunhado para o navegador: uma jornada de trabalho, nunca os 90 dias do token de
# serviço comum (ADR 0002 seção 8). O mapa recunha sozinho ao recarregar a página.
HORAS_TOKEN_MAPA = 12
NOME_TOKEN = "mapa-web"

SQL_CAMADA = """
SELECT i.id, i.titulo, i.descricao, i.dados, i.criado_em
FROM plat.item i
WHERE i.tipo IN ('camada_vetorial', 'vista_de_camada') AND i.apagado_em IS NULL
"""


def _extensao(cur, dados: dict) -> list[float] | None:
    """Extensão em graus. Vem gravada em `dados.extensao` quando a ingestão a calculou; senão é medida
    uma vez com ST_Extent e devolvida (sem gravar: quem grava é a ingestão, não uma rota de leitura)."""
    ext = dados.get("extensao")
    if isinstance(ext, list) and len(ext) == 4:
        return [float(v) for v in ext]
    esquema, tabela = dados.get("schema"), dados.get("tabela")
    if not esquema or not tabela:
        return None
    cur.execute("SELECT plat.camada_extensao(%s, %s) AS e", (esquema, tabela))
    linha = cur.fetchone()
    return list(linha["e"]) if linha and linha["e"] else None


def _n_feicoes(cur, dados: dict) -> int | None:
    n = dados.get("n_feicoes")
    if isinstance(n, int):
        return n
    est = (dados.get("estatisticas") or {}) if isinstance(dados.get("estatisticas"), dict) else {}
    for chave in ("feicoes", "linhas", "n_feicoes"):
        if isinstance(est.get(chave), int):
            return est[chave]
    return None


def _ficha(cur, linha: dict, completo: bool) -> dict:
    dados = linha["dados"] or {}
    geometria = dados.get("geometria") or "Point"
    tabela = dados.get("tabela") or ""
    esquema = dados.get("schema") or ""
    funcao = ("t_" + tabela[2:]) if tabela.startswith("c_") else None
    simb = simb_mod.normalizar(dados.get("simbologia"), geometria)
    fonte = f"plat-{linha['id']}"
    ficha = {
        "id": str(linha["id"]),
        "titulo": linha["titulo"],
        "geometria": geometria,
        "familia": simb_mod.familia(geometria),
        "srid": dados.get("srid"),
        "campos": dados.get("campos") or [],
        "n_feicoes": _n_feicoes(cur, dados),
        "servivel": bool(funcao and esquema),
        "simbologia": simb,
        "legenda": simb_mod.legenda(simb, geometria),
        "estilo": simb_mod.camadas_maplibre(simb, geometria, fonte, fonte, funcao or "camada"),
        "tilejson": f"/api/mapa/camadas/{linha['id']}/tilejson" if funcao else None,
        # item L2-03-edicao: o que a tela de edição precisa saber SEM abrir outra rota — nunca schema/tabela
        # (isso fica só no servidor). "editavel" já resume fonte hospedada + edicao.habilitada.
        "editavel": bool(dados.get("fonte") == "hospedada" and (dados.get("edicao") or {}).get("habilitada")),
        "regras_campo": dados.get("regras_campo") or {},
        "somente_proprias": bool((dados.get("edicao") or {}).get("somente_proprias")),
        "geometria_travada": bool((dados.get("edicao") or {}).get("geometria_travada")),
    }
    if completo:
        ficha["descricao"] = linha["descricao"]
        ficha["extensao"] = _extensao(cur, dados)
    else:
        ext = dados.get("extensao")
        ficha["extensao"] = [float(v) for v in ext] if isinstance(ext, list) and len(ext) == 4 else None
    return ficha


@router.get("/api/mapa/camadas", openapi_extra=X)
def listar_camadas(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Camadas vetoriais que a sessão pode ler (a RLS de plat.item decide), prontas para o mapa."""
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_CAMADA + " ORDER BY i.titulo")
        linhas = cur.fetchall()
        return {"camadas": [_ficha(cur, ln, completo=False) for ln in linhas]}


@router.get("/api/mapa/camadas/{id}", openapi_extra=X)
def obter_camada(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (id,))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "camada_inexistente", "camada inexistente ou sem permissão de leitura")
        return _ficha(cur, linha, completo=True)


@router.get("/api/mapa/camadas/{id}/tilejson", openapi_extra=X)
def tilejson(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (id,))
        linha = cur.fetchone()
        if linha is None:
            raise ErroAPI(404, "camada_inexistente", "camada inexistente ou sem permissão de leitura")
        dados = linha["dados"] or {}
        esquema, tabela = dados.get("schema"), dados.get("tabela")
        if not esquema or not tabela or not tabela.startswith("c_"):
            raise ErroAPI(422, "camada_sem_tabela", "esta camada não é hospedada: não há tile a servir")
        funcao = "t_" + tabela[2:]
        if auth.modo != "sessao":
            raise ErroAPI(403, "so_sessao", "o TileJSON com token cunhado só sai sob sessão de usuário; "
                                            "cliente externo usa o próprio token de serviço na URL do tile")
        nome = f"{NOME_TOKEN}:{id}"
        cur.execute("UPDATE plat.token_servico SET revogado_em = now() "
                    "WHERE usuario_id = %s AND nome = %s AND revogado_em IS NULL",
                    (auth.usuario_id, nome))
        valor = "plat_" + secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, "
            "restricao, expira_em) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, "
            "now() + make_interval(hours => %s)) RETURNING id, expira_em",
            (auth.tenant_id, auth.usuario_id, nome, sha256_hex(valor), valor[:12],
             [f"camada:ler:{id}"], json.dumps({}), HORAS_TOKEN_MAPA))
        criado = cur.fetchone()
        ext = _extensao(cur, dados)
    base = str(request.base_url).rstrip("/")
    return {
        "tilejson": "3.0.0",
        "name": linha["titulo"],
        "scheme": "xyz",
        "tiles": [f"{base}/tiles/{esquema}/{funcao}/{{z}}/{{x}}/{{y}}?token={valor}"],
        "minzoom": 0,
        "maxzoom": 20,
        "bounds": ext or [-180, -85, 180, 85],
        "vector_layers": [{"id": funcao, "fields": {c.get("nome"): c.get("tipo", "text")
                                                    for c in (dados.get("campos") or [])}}],
        "expira_em": criado["expira_em"].isoformat(),
        "token_id": criado["id"],
    }


@router.get("/tiles/{esquema}/{funcao}/{z}/{x}/{y}", include_in_schema=False)
async def tile(
    request: Request,
    esquema: str = Path(pattern=r"^d_[a-z0-9_]{1,60}$"),
    funcao: str = Path(pattern=r"^t_[0-9a-f]{16}$"),
    z: int = Path(ge=0, le=24),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
):
    """Repasse do tile do Martin, com a MESMA autorização do auth_request do nginx.

    O `.mvt`/`.pbf` no fim do y é aceito porque alguns clientes o acrescentam; o Martin não usa extensão.
    """
    y_texto = str(y)
    token = request.query_params.get("token")
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    origem = request.headers.get("origin") or request.headers.get("referer")
    veredito = autorizar(f"/tiles/{esquema}/{funcao}/{z}/{x}/{y_texto}", token, ip, origem)
    if veredito.status != 204:
        return Response(status_code=veredito.status, headers={"X-Motivo-Recusa": veredito.motivo})
    # PLAT_MARTIN_URL é opcional no .env (app/settings.py); o padrão é o endereço da unidade plat-martin
    base_martin = (settings.PLAT_MARTIN_URL or "http://127.0.0.1:8151").rstrip("/")
    alvo = f"{base_martin}/{funcao}/{z}/{x}/{y_texto}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as cliente:
            # `Accept-Encoding: identity`: o Martin gzipa o MVT por padrão e o cliente httpx descompacta
            # sozinho ao ler `.content`. Repassar o cabeçalho `Content-Encoding: gzip` junto com um corpo JÁ
            # descompactado entrega ao navegador um tile que ele tenta inflar de novo — MEDIDO nesta suíte
            # ("Error -3 while decompressing data: incorrect header check"). Pedimos sem compressão e
            # entregamos o corpo como veio; quem comprime na saída é o nginx, uma camada só.
            r = await cliente.get(alvo, params={"token": token or ""},
                                  headers={"Accept-Encoding": "identity"})
    except httpx.HTTPError as e:
        log.warning("tile: martin inacessível em %s: %s", alvo, e)
        raise ErroAPI(503, "tiles_indisponiveis", "servidor de tiles indisponível") from e
    if r.status_code == 204 or not r.content:
        return Response(status_code=204)
    if r.status_code >= 400:
        log.warning("tile: martin devolveu %s para %s", r.status_code, alvo)
        raise ErroAPI(502, "tile_falhou", "o servidor de tiles recusou o pedido")
    cabecalhos = {"Cache-Control": "private, max-age=60"}
    return Response(content=r.content, media_type="application/vnd.mapbox-vector-tile", headers=cabecalhos)
