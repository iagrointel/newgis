"""Rotas da galeria de mapas base (item L2-01-e-mapas-base). Três operações próprias além do catálogo
genérico (que já cobre criar/editar/apagar um item comum via /api/itens, inclusive mudar `dados.ordem` por
PATCH):

  GET  /api/mapas-base              lista os `mapa_base` do inquilino, já na ordem da galeria
  POST /api/mapas-base/instalar     semeia as fontes padrão (semear.py), idempotente
  POST /api/mapas-base/{id}/tornar-padrao   troca o padrão do inquilino em UMA transação (nunca dois defaults)
  GET  /api/mapas-base/osm/{z}/{x}/{y}.png  proxy raster do OSM (proxy_osm.py)
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum as catalogo_comum
from app.catalogo.modelos import Item, ItemEntrada
from app.catalogo.rotas_itens import criar as criar_item
from app.catalogo.rotas_itens import editar_item
from app.erros import ErroAPI
from app.mapas_base import proxy_osm, semear
from app.settings import settings

router = APIRouter(tags=["mapas-base"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "conteudo.criar"}
SQL_GALERIA = catalogo_comum.SQL_ITEM + (
    " WHERE i.tipo = 'mapa_base' AND i.apagado_em IS NULL ORDER BY (i.dados->>'ordem')::int NULLS LAST, i.criado_em"
)


@router.get("/api/mapas-base", response_model=list[Item], openapi_extra=LER)
def listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_GALERIA)
        linhas = cur.fetchall()
    return [catalogo_comum.item_json(r, auth) for r in linhas]


def _ja_instalado(cur) -> set[str]:
    cur.execute("SELECT dados->>'tipo' AS fonte FROM plat.item WHERE tipo = 'mapa_base' AND apagado_em IS NULL")
    return {r["fonte"] for r in cur.fetchall() if r["fonte"]}


@router.post("/api/mapas-base/instalar", response_model=list[Item], status_code=201, openapi_extra=ESCREVER)
def instalar(request: Request, auth: Auth = autenticado("conteudo.criar")):
    """Cria os itens que faltam entre as fontes padrão (semear.definicoes_padrao); pular o que o admin já tem
    instalado (por `dados.tipo`, nunca por título — o admin pode ter renomeado) faz a rota ser chamável de
    novo sem duplicar nem sobrescrever edição manual (ordem/padrão/título já mudados)."""
    definicoes = semear.definicoes_padrao(settings.PLAT_TITILER_URL)
    criados: list[str] = []
    with db.db(auth.contexto()) as cur:
        instaladas = _ja_instalado(cur)
        for d in definicoes:
            if d["dados"]["tipo"] in instaladas:
                continue
            corpo = ItemEntrada(
                tipo="mapa_base", titulo=d["titulo"], resumo=d.get("resumo"),
                creditos=d.get("creditos"), termos_de_uso=d.get("termos_de_uso"), dados=d["dados"],
            )
            item = criar_item(corpo, request, auth=auth)
            criados.append(item["id"])
        cur.execute(SQL_GALERIA)
        linhas = cur.fetchall()
    return [catalogo_comum.item_json(r, auth) for r in linhas]


@router.post("/api/mapas-base/{id}/tornar-padrao", response_model=Item, openapi_extra=ESCREVER)
def tornar_padrao(id: str, request: Request, auth: Auth = autenticado("conteudo.criar")):
    """Torna `id` o mapa base padrão do inquilino: desliga o padrão anterior (se houver) e liga o novo dentro
    da MESMA transação — nunca dois defaults ao mesmo tempo, sem depender da corrida cair no índice único
    `ux_item_mapa_base_padrao` (esse índice é só a rede de segurança de última linha)."""
    with db.db(auth.contexto()) as cur:
        alvo = catalogo_comum.item_ou_404(cur, id)
        if alvo["tipo"] != "mapa_base":
            raise ErroAPI(422, "tipo_invalido", "o item não é um mapa base", {"tipo": alvo["tipo"]})
        cur.execute(
            "SELECT id, dados FROM plat.item WHERE tipo = 'mapa_base' AND apagado_em IS NULL "
            "AND id <> %s::uuid AND (dados->>'padrao')::boolean IS TRUE",
            (id,),
        )
        for anterior in cur.fetchall():
            novo_dados = dict(anterior["dados"])
            novo_dados["padrao"] = False
            editar_item(cur, request, auth, str(anterior["id"]), {"dados": novo_dados})
        novo_dados_alvo = dict(alvo["dados"])
        novo_dados_alvo["padrao"] = True
        r = editar_item(cur, request, auth, id, {"dados": novo_dados_alvo})
    return catalogo_comum.item_json(r, auth)


@router.get("/api/mapas-base/osm/{z}/{x}/{y}.png", openapi_extra=LER)
def proxy_osm_ladrilho(z: int, x: int, y: int, auth: Auth = autenticado(escopo_token="catalogo:ler")) -> Response:
    """Sem parâmetro de host: o único jeito de este endpoint falar com outro servidor é mudar
    `limites.MAPA_BASE_OSM_HOSTS` no código — nenhum valor de requisição chega ao host de saída
    (ver docstring de app.mapas_base.proxy_osm; refutação do item: "tenta usar como proxy aberto")."""
    return proxy_osm.resposta_ladrilho(z, x, y)
