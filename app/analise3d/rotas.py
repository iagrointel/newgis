"""Rotas /api/analise3d (item L2-09-d): linha de visada, bacia visual (gdal_viewshed), perfil de elevação
e sombra projetada — sobre um terreno INLINE na requisição (`app/analise3d/terreno.py`).

Toda resposta carrega `procedencia` (ferramenta, versão, sha256 da grade de entrada, comando quando há
binário, e a aproximação declarada). `salvar_item` presente = o resultado vira item `analise_3d` do
catálogo pela MESMA função do POST /api/itens (`app/catalogo/rotas_itens.criar`): cota, JSON Schema,
evento `itens/adicionar` e RLS são os do catálogo — e o privilégio `conteudo.criar` é exigido aqui,
igual à rota direta, para não existir caminho de criar item sem o privilégio dele.

Privilégio publicado: leitura do inquilino para calcular; `conteudo.criar` quando o resultado vira item
(declaração `rls:visibilidade|conteudo.criar`, a mesma forma da edição de itens).
"""

import datetime

from fastapi import APIRouter, Request

from app import db
from app.analise3d import perfil as mod_perfil
from app.analise3d import sombra as mod_sombra
from app.analise3d import visada as mod_visada
from app.analise3d import vista as mod_vista
from app.analise3d.modelos import (
    PerfilEntrada,
    SombraEntrada,
    ViewshedEntrada,
    VisadaEntrada,
    dados_do_item,
)
from app.analise3d.sol import posicao_solar
from app.analise3d.terreno import SRID_MAX, SRID_MIN, Terreno, sha256_da_grade
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api/analise3d", tags=["analise3d"])
DECLARACAO = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.criar"}
ESCOPO = "analise3d:usar"

APROXIMACAO_SOMBRA = (
    "prisma vertical sobre superfície plana; posição solar pelo algoritmo NOAA "
    "(declinação aparente e equação do tempo, refração de Saemundsson; 0,01° declarado); "
    "o relevo não curva a sombra e a estrutura da base não projeta sombra própria"
)


def _exigir_srid(srid: int) -> None:
    if not (SRID_MIN <= srid <= SRID_MAX):
        raise ErroAPI(
            422,
            "srid_invalido",
            f"srid {srid} fora da faixa aceita ({SRID_MIN}-{SRID_MAX}, SIRGAS 2000 UTM sul, metros)",
        )


def _quando_utc(data_hora: str) -> datetime.datetime:
    try:
        quando = datetime.datetime.fromisoformat(data_hora)
    except ValueError as e:
        raise ErroAPI(422, "data_invalida", f"data_hora '{data_hora}' não é ISO 8601") from e
    if quando.tzinfo is None:
        raise ErroAPI(422, "data_sem_fuso", "data_hora precisa de fuso (ex.: 2026-12-21T12:00:00-03:00)")
    return quando.astimezone(datetime.UTC)


def _centroide_4326(poligono: dict, srid: int) -> tuple[float, float]:
    """Centroide do polígono em (lon, lat) para a posição solar — rasterio, sem consulta ao banco."""
    import rasterio.crs
    from rasterio.warp import transform as warp_transform
    from shapely.geometry import shape

    g = shape(poligono)
    if g.is_empty:
        raise ErroAPI(422, "solido_invalido", "polígono do sólido vazio")
    xs, ys = warp_transform(
        rasterio.crs.CRS.from_epsg(srid), rasterio.crs.CRS.from_epsg(4326), [g.centroid.x], [g.centroid.y]
    )
    return (float(xs[0]), float(ys[0]))


def _salvar_item(request: Request, auth: Auth, analise: str, titulo: str, resumo: str | None,
                 tags: list[str], parametros: dict, resultado_item: dict, procedencia: dict) -> str:
    """Cria o item `analise_3d` pela rota do catálogo (mesmo privilégio, cota, validação e evento)."""
    from app.catalogo import rotas_itens
    from app.catalogo.modelos import ItemEntrada

    entrada = ItemEntrada(
        tipo="analise_3d",
        titulo=titulo,
        resumo=resumo,
        tags=tags,
        dados=dados_do_item(analise, parametros, resultado_item, procedencia),
    )
    item = rotas_itens.criar(entrada, request, auth)
    return str(item["id"])


def _checar_salvar(auth: Auth, salvar) -> None:
    if salvar is not None and not auth.tem("conteudo.criar"):
        raise ErroAPI(403, "sem_privilegio", "salvar o resultado como item exige o privilégio conteudo.criar",
                      {"exigido": "conteudo.criar"})


def _procedencia(analise: str, terreno: Terreno | None, **extra) -> dict:
    base = {
        "analise": analise,
        "ferramenta": extra.pop("ferramenta", "plat.analise3d"),
        "sha256_terreno": sha256_da_grade(terreno) if terreno is not None else None,
        "medido_em": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


@router.post("/visada", openapi_extra=DECLARACAO)
def visada(corpo: VisadaEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    _checar_salvar(auth, corpo.salvar_item)
    _exigir_srid(corpo.terreno.srid)
    r = mod_visada.linha_de_visada(
        corpo.terreno,
        corpo.observador,
        corpo.alvo,
        corpo.altura_observador_m,
        corpo.altura_alvo_m,
        corpo.passo_m,
    )
    procedencia = _procedencia("visada", corpo.terreno, aproximacao="amostragem bilinear no terreno; "
                                "o ponto de obstrução é o centro do primeiro passo em que o terreno "
                                "ultrapassa a reta, com erro máximo do próprio passo declarado")
    resposta: dict = {**r, "procedencia": procedencia}
    item_id = None
    with db.db(auth.contexto()) as cur:
        if corpo.salvar_item is not None:
            item_id = _salvar_item(
                request, auth, "visada", corpo.salvar_item.titulo, corpo.salvar_item.resumo,
                corpo.salvar_item.tags,
                {
                    "observador": corpo.observador, "alvo": corpo.alvo,
                    "altura_observador_m": corpo.altura_observador_m, "altura_alvo_m": corpo.altura_alvo_m,
                    "passo_m": corpo.passo_m, "srid": corpo.terreno.srid,
                    "x0": corpo.terreno.x0, "y0": corpo.terreno.y0, "celula_m": corpo.terreno.celula_m,
                },
                {"visivel": r["visivel"], "distancia_m": r["distancia_m"],
                 "ponto_de_obstrucao": r["ponto_de_obstrucao"], "amostras_n": r["amostras_n"]},
                procedencia,
            )
            resposta["item_id"] = item_id
        registrar_evento(cur, request, "analise3d/visada", "item" if item_id else None, item_id,
                         {"visivel": r["visivel"], "distancia_m": round(r["distancia_m"], 3),
                          "obstruido": r["ponto_de_obstrucao"] is not None, "item_id": item_id})
    return resposta


@router.post("/viewshed", openapi_extra=DECLARACAO)
def viewshed(corpo: ViewshedEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    _checar_salvar(auth, corpo.salvar_item)
    _exigir_srid(corpo.terreno.srid)
    r = mod_vista.bacia_visual(
        corpo.terreno,
        corpo.observador,
        corpo.altura_observador_m,
        corpo.altura_alvo_m,
        corpo.distancia_max_m,
        corpo.coef_curvatura,
        corpo.modo,
        corpo.visivel_valor,
        corpo.invisivel_valor,
        corpo.fora_de_alcance_valor,
    )
    procedencia = _procedencia(
        "viewshed", corpo.terreno,
        ferramenta="gdal_viewshed",
        versao_gdal=r["versao_gdal"],
        comando=r["comando"],
        sha256_viewshed=r["sha256_viewshed_geotiff"],
        aproximacao="execução direta do binário gdal_viewshed sobre o GeoTIFF da grade; o GeoTIFF da "
                    "resposta são os bytes escritos pelo binário, sem retoque",
    )
    resposta: dict = {**r, "procedencia": procedencia}
    item_id = None
    with db.db(auth.contexto()) as cur:
        if corpo.salvar_item is not None:
            # o item guarda o RESUMO (contagem, sha256, comando) — o GeoTIFF base64 não cabe em `dados`
            # e fica na resposta da análise; o sha256 permite reproduzir o raster byte a byte.
            item_id = _salvar_item(
                request, auth, "viewshed", corpo.salvar_item.titulo, corpo.salvar_item.resumo,
                corpo.salvar_item.tags,
                {
                    "observador": corpo.observador, "altura_observador_m": corpo.altura_observador_m,
                    "altura_alvo_m": corpo.altura_alvo_m, "distancia_max_m": corpo.distancia_max_m,
                    "coef_curvatura": corpo.coef_curvatura, "modo": corpo.modo,
                    "visivel_valor": corpo.visivel_valor, "invisivel_valor": corpo.invisivel_valor,
                    "fora_de_alcance_valor": corpo.fora_de_alcance_valor, "srid": corpo.terreno.srid,
                    "x0": corpo.terreno.x0, "y0": corpo.terreno.y0, "celula_m": corpo.terreno.celula_m,
                },
                {
                    "resumido_no_item": True,
                    "sha256_terreno_geotiff": r["sha256_terreno_geotiff"],
                    "sha256_viewshed_geotiff": r["sha256_viewshed_geotiff"],
                    "dimensoes": r["dimensoes"],
                    "celulas_visiveis": r.get("celulas_visiveis"),
                    "celulas_invisiveis": r.get("celulas_invisiveis"),
                    "celulas_fora_de_alcance": r.get("celulas_fora_de_alcance"),
                },
                procedencia,
            )
            resposta["item_id"] = item_id
        registrar_evento(cur, request, "analise3d/viewshed", "item" if item_id else None, item_id,
                         {"celulas_visiveis": r.get("celulas_visiveis"),
                          "sha256_viewshed": r["sha256_viewshed_geotiff"][:12], "item_id": item_id})
    return resposta


@router.post("/perfil", openapi_extra=DECLARACAO)
def perfil(corpo: PerfilEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    _checar_salvar(auth, corpo.salvar_item)
    _exigir_srid(corpo.terreno.srid)
    r = mod_perfil.perfil(corpo.terreno, corpo.ponto_a, corpo.ponto_b, corpo.n_amostras)
    procedencia = _procedencia("perfil", corpo.terreno,
                               aproximacao="amostragem equidistante bilinear; declividade máxima entre "
                                           "amostras consecutivas")
    resposta: dict = {**r, "procedencia": procedencia}
    item_id = None
    with db.db(auth.contexto()) as cur:
        if corpo.salvar_item is not None:
            item_id = _salvar_item(
                request, auth, "perfil", corpo.salvar_item.titulo, corpo.salvar_item.resumo,
                corpo.salvar_item.tags,
                {"ponto_a": corpo.ponto_a, "ponto_b": corpo.ponto_b, "n_amostras": corpo.n_amostras,
                 "srid": corpo.terreno.srid},
                {"estatisticas": r["estatisticas"], "distancia_m": r["distancia_m"],
                 "amostras": r["amostras"]},
                procedencia,
            )
            resposta["item_id"] = item_id
        registrar_evento(cur, request, "analise3d/perfil", "item" if item_id else None, item_id,
                         {"distancia_m": round(r["distancia_m"], 3),
                          "ganho_m": round(r["estatisticas"]["ganho_m"], 3),
                          "perda_m": round(r["estatisticas"]["perda_m"], 3), "item_id": item_id})
    return resposta


@router.post("/sombra", openapi_extra=DECLARACAO)
def sombra(corpo: SombraEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    _checar_salvar(auth, corpo.salvar_item)
    _exigir_srid(corpo.srid)
    quando = _quando_utc(corpo.data_hora)
    solidos: list[dict] = []
    for i, s in enumerate(corpo.solidos):
        lon, lat = _centroide_4326(s.poligono, corpo.srid)
        sol = posicao_solar(quando, lat, lon)
        if sol["elevacao_graus"] <= 0.0:
            raise ErroAPI(422, "sol_abaixo_do_horizonte",
                          f"sólido {i}: Sol abaixo do horizonte no instante e no lugar pedidos")
        try:
            resultado = mod_sombra.sombra_do_solido(
                s.poligono, s.altura_m, sol["azimute_graus"], sol["elevacao_graus"]
            )
        except ValueError as e:
            raise ErroAPI(422, "solido_invalido", f"sólido {i}: {e}") from e
        solidos.append({
            "altura_m": s.altura_m,
            "centroide": {"lon": lon, "lat": lat},
            "azimute_sol_graus": sol["azimute_graus"],
            "elevacao_sol_graus": sol["elevacao_graus"],
            "declinacao_graus": sol["declinacao_graus"],
            "equacao_do_tempo_min": sol["equacao_do_tempo_min"],
            **resultado,
        })
    procedencia = _procedencia("sombra", None, ferramenta="plat.analise3d/sol (NOAA) + shapely",
                               aproximacao=APROXIMACAO_SOMBRA)
    resposta: dict = {"data_hora": corpo.data_hora, "srid": corpo.srid, "solidos": solidos,
                      "procedencia": procedencia}
    item_id = None
    with db.db(auth.contexto()) as cur:
        if corpo.salvar_item is not None:
            item_id = _salvar_item(
                request, auth, "sombra", corpo.salvar_item.titulo, corpo.salvar_item.resumo,
                corpo.salvar_item.tags,
                {"data_hora": corpo.data_hora, "srid": corpo.srid,
                 "alturas_m": [s.altura_m for s in corpo.solidos]},
                {"solidos": solidos},
                procedencia,
            )
            resposta["item_id"] = item_id
        registrar_evento(cur, request, "analise3d/sombra", "item" if item_id else None, item_id,
                         {"solidos": len(solidos),
                          "data_hora": corpo.data_hora, "item_id": item_id})
    return resposta
