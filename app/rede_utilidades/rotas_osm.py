"""Rotas do conector OpenStreetMap power=* (item L4-05-g-osm-power; ADR 20260906T2226).

`POST /api/rede/{rede_id}/importar-osm` monta a rede power=* de UM município a partir de um extrato
OSM (.pbf/.osm) que JÁ ESTÁ na máquina (caminho de servidor — o mesmo desenho do importador BDGD de
L4-01-modelo-rede; upload de arquivo pela API é o item L4-01-c). `GET /api/rede/{rede_id}/importacoes`
é a ficha das importações da rede: fonte, licença (ODbL, no OSM), aviso ("cadastro comunitário, não
oficial"), contagens conferidas e desvios — o registro que a refutação lê.

Mesmo padrão de `rotas.py`: escrita exige `rede.editar`; leitura segue a visibilidade por inquilino
(RLS); trabalho pesado no threadpool (lição do achado A4 do item L4-01-a)."""

import psycopg2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import osm_power
from app.rede_utilidades.modelos import (
    ImportacaoFichaLista,
    ImportacaoOsmEntrada,
    ImportacaoOsmResultado,
)

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — conector OSM"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


def _uuid_ok(valor: str) -> str:
    import uuid as uuid_mod

    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _importar_sincrono(rid: str, corpo: ImportacaoOsmEntrada, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid FOR UPDATE", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        try:
            resultado = osm_power.importar(
                cur, auth.tenant_id, rid, corpo.caminho,
                corpo.municipio.model_dump(), corpo.nome_municipio,
            )
        except osm_power.ErroOsm as e:
            raise ErroAPI(422, "extrato_invalido", str(e)) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/importar_osm", "rede", rid,
                         {"municipio": corpo.nome_municipio, "caminho": corpo.caminho,
                          "conferido": resultado["conferido"]})
    return resultado


@router.post("/{rede_id}/importar-osm", response_model=ImportacaoOsmResultado, status_code=201,
             openapi_extra=EDITAR)
async def importar_osm(rede_id: str, corpo: ImportacaoOsmEntrada, request: Request,
                       auth: Auth = autenticado("rede.editar")):
    """Importa power=* do município para a rede (que já deve ter o pacote eletrica-br importado).
    Numa transação: ou entra tudo, ou nada. A contagem por etiqueta é conferida contra o extrato e
    o que não entra vira desvio explicado — nunca silêncio."""
    rid = _uuid_ok(rede_id)
    resultado = await run_in_threadpool(_importar_sincrono, rid, corpo, auth, request)
    return {
        "rede_id": rid,
        "licenca": osm_power.LICENCA_OSM,
        "aviso": osm_power.AVISO_OSM,
        **resultado,
    }


def _ficha_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "fonte": r["fonte"],
        "caminho": r["caminho"],
        "distribuidora": r["distribuidora"],
        "municipio": r["municipio"],
        "sha256": r["sha256"],
        "licenca": r["licenca"],
        "aviso": r["aviso"],
        "estado": r["estado"],
        "contagens": r["contagens"],
        "desvios": r["desvios"],
        "erro": r["erro"],
        "criado_em": iso(r["criado_em"]),
        "concluido_em": iso(r["concluido_em"]),
    }


@router.get("/{rede_id}/importacoes", response_model=ImportacaoFichaLista, openapi_extra=LER)
def listar_importacoes(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """A ficha das importações da rede (mais recente primeiro). É onde a licença da fonte e o
    aviso de confiança aparecem SEMPRE — no OSM: ODbL e "cadastro comunitário, não oficial"."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        cur.execute(
            "SELECT id, fonte, caminho, distribuidora, municipio, sha256, licenca, aviso, estado, "
            "contagens, desvios, erro, criado_em, concluido_em "
            "FROM plat.rede_importacao WHERE rede_id = %s::uuid ORDER BY criado_em DESC",
            (rid,),
        )
        itens = [_ficha_json(r) for r in cur.fetchall()]
        return {"total": len(itens), "itens": itens}
