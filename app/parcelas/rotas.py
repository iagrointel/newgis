"""Fachada REST dos fluxos da malha de parcelas (item L4-parcelas-02-fluxos-cogo): as sete
operações do ParcelFabricServer mapeadas com a forma da documentação de desenvolvedores Esri
(consultada em 08/09/2026; a tabela operação por operação, com o que é aceito, mapeado e
ignorado, está em docs/PARIDADE_PARCELAS.md §11):

    POST /api/parcelas/fabrica/build
    POST /api/parcelas/fabrica/divide
    POST /api/parcelas/fabrica/merge
    POST /api/parcelas/fabrica/clip
    POST /api/parcelas/fabrica/createSeeds
    POST /api/parcelas/fabrica/reconstructFromSeeds
    POST /api/parcelas/fabrica/assignFeaturesToRecord

Mapeamentos declarados (detalhes em §11): a resposta carrega `moment`, `exceededTransferLimit`,
`success` e `serviceEdits` (id da camada + editedFeatures.adds/updates resumidos); erro é HTTP
4xx do padrão da casa, nunca `success:false` com 200. `gdbVersion`, `sessionId`, `async`, `f` e
`spatialReference` são aceitos para a forma bater com a doc e sem efeito — a casa tem uma versão
só por inquilino, roda sempre síncrona e trabalha em SIRGAS 2000 UTM 22S (SRID 31982). O `record`
é obrigatório nas operações que nascem/matem feição (regra do registro, item 01)."""

from datetime import datetime, timezone
from typing import Literal

import psycopg2
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import comum as auth_comum
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.parcelas import fluxos

router = APIRouter(prefix="/api/parcelas/fabrica", tags=["parcelas"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "parcelas:usar"

OPCOES_DIVIDE = Literal["ProportionalArea", "EqualArea", "EqualWidth"]
OPCOES_CLIP = Literal["PreserveArea", "DiscardArea", "PreserveBothAreasSplit"]


class Extent(BaseModel):
    """Envelope da doc (buildExtent/extent). spatialReference é aceito e ignorado (SRID fixo)."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    spatialReference: dict | None = None


class _OpEntrada(BaseModel):
    """Parâmetros comuns da doc: gdbVersion e sessionId aceitos sem efeito (versão única por
    inquilino). f/async são do transporte HTTP e nem entram no corpo."""
    gdbVersion: str | None = None
    sessionId: str | None = None


class BuildEntrada(_OpEntrada):
    record: str
    tipo: Literal["lote", "gleba", "quadra", "servidao", "estrato"] | None = None
    buildExtent: Extent | None = None


class DivideEntrada(_OpEntrada):
    """Divide na forma da doc (divideOption + bearing) OU com linha de corte direta (campo
    `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11)."""
    divideParcelGuid: str | None = None
    divideParcelType: Literal["lote", "gleba", "quadra", "servidao", "estrato"] | None = None
    record: str
    divideOption: OPCOES_DIVIDE | None = None
    divideNumberOfParts: int = Field(default=2, ge=2)
    dividePartAreaOrWidth: float = Field(default=0.0, ge=0)
    divideLineBearing: float | None = Field(default=None, ge=0, lt=360)
    divideLeftSide: bool = True
    divideDistributeRemainder: bool = False
    linha: list[list[float]] | None = None


class MergeEntrada(_OpEntrada):
    parentParcels: list[dict]
    record: str
    targetParcelType: Literal["lote", "gleba", "quadra", "servidao", "estrato"] | None = None
    codigo: str | None = None
    defaultAreaUnit: int | None = None  # aceito e ignorado: a casa grava área sempre em m²
    mergeInto: str | None = None        # aceito e declarado não implementado (§11) — recusa


class ClipEntrada(_OpEntrada):
    parentParcels: list[dict]
    record: str
    clippingParcels: list[dict] | None = None
    clippingGeometry: dict | None = None  # GeoJSON Polygon (a doc manda geometria + SR)
    clipOption: OPCOES_CLIP
    codigo: str | None = None
    defaultAreaUnit: int | None = None    # aceito e ignorado: a casa grava área sempre em m²


class CreateSeedsEntrada(_OpEntrada):
    record: str
    extent: Extent | None = None


class ReconstructEntrada(_OpEntrada):
    extent: Extent
    record: str  # divergência declarada (§11): a casa exige registro para a parcela nascer


class AssignEntrada(_OpEntrada):
    parcelFeatures: list[dict]
    record: str
    writeAttribute: Literal["CreatedByRecord", "RetiredByRecord"]


# ------------------------------------------------------------------ resposta na forma da doc


def _feicao(r: dict) -> dict:
    saida = {"id": str(r["id"]), "codigo": r["codigo"]}
    if r.get("area_calculada_m2") is not None:
        saida["areaCalculadaM2"] = round(float(r["area_calculada_m2"]), 4)
    return saida


def _resposta(request: Request, cur, tipo_evento: str, alvo_id: str, propriedades: dict,
              camada: str, adds: list[dict], updates: list[dict]) -> dict:
    registrar_evento(cur, request, tipo_evento, "parcela", alvo_id, propriedades)
    return {
        "moment": iso(datetime.now(timezone.utc)),
        "exceededTransferLimit": False,
        "success": True,
        "serviceEdits": [{"id": camada, "editedFeatures": {
            "adds": [_feicao(a) for a in adds],
            "updates": [_feicao(u) for u in updates if u is not None],
        }}],
    }


def _corpo_geojson_poligono(geo: dict) -> str:
    """GeoJSON Polygon -> WKT (a casa recebe a geometria no corpo; SR é o fixo da malha)."""
    try:
        if geo.get("type") != "Polygon":
            raise ValueError
        anel = geo["coordinates"][0]
        pts = [(float(x), float(y)) for x, y in anel]
    except (KeyError, TypeError, ValueError) as e:
        raise ErroAPI(422, "valor_invalido", "clippingGeometry precisa ser um GeoJSON Polygon") from e
    if len(pts) < 4 or pts[0] != pts[-1]:
        raise ErroAPI(422, "valor_invalido", "clippingGeometry precisa de anel fechado com 4+ pontos")
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"


def _rodar(fn, *a, **kw):
    """Chama o fluxo e traduz erro do banco (CHECK/FK/unidade) no padrão da casa."""
    try:
        return fn(*a, **kw)
    except psycopg2.Error as e:
        raise auth_comum.erro_do_banco(e) from e


def _um_pai(pares: list[dict], campo: str) -> str:
    if not pares or len(pares) > 1:
        raise ErroAPI(422, "valor_invalido", f"{campo} aceita exatamente 1 feição na casa (a doc aceita array)")
    fid = (pares[0] or {}).get("id")
    if not fid:
        raise ErroAPI(422, "valor_invalido", f"{campo} precisa de {{id, layerId}}")
    return str(fid)


# ------------------------------------------------------------------ operações


@router.post("/build", status_code=200, openapi_extra=LER)
def build(corpo: BuildEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Build (forma da doc `.../ParcelFabricServer/build`): fecha anéis com as linhas livres e
    cria uma parcela por face. record é obrigatório na casa (divergência §11)."""
    extent = corpo.buildExtent.model_dump() if corpo.buildExtent else None
    with db.db(auth.contexto()) as cur:
        criadas = _rodar(fluxos.construir, cur, auth.tenant_id, registro_id=corpo.record,
                         tipo=corpo.tipo, extent=extent)
        return _resposta(request, cur, "parcelas/build", corpo.record,
                         {"faces": len(criadas)}, "Parcela",
                         criadas, [])


@router.post("/divide", status_code=200, openapi_extra=LER)
def divide(corpo: DivideEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Divide (forma da doc `.../ParcelFabricServer/divide`): por rumo com divideOption
    (ProportionalArea/EqualArea/EqualWidth) ou por linha de corte direta (campo `linha`)."""
    with db.db(auth.contexto()) as cur:
        if corpo.linha is not None:
            if corpo.divideParcelGuid is None:
                raise ErroAPI(422, "valor_invalido", "divideParcelGuid é obrigatório")
            if len(corpo.linha) != 2 or any(len(p) != 2 for p in corpo.linha):
                raise ErroAPI(422, "valor_invalido", "linha de corte precisa de 2 pontos [x, y]")
            criadas = _rodar(fluxos.dividir_por_linha, cur, auth.tenant_id,
                             parcela_id=corpo.divideParcelGuid,
                             registro_id=corpo.record, linha=corpo.linha,
                             tipo=corpo.divideParcelType)
            op = "linha"
        else:
            if corpo.divideParcelGuid is None:
                raise ErroAPI(422, "valor_invalido", "divideParcelGuid é obrigatório")
            if corpo.divideOption is None or corpo.divideLineBearing is None:
                raise ErroAPI(422, "valor_invalido",
                              "informe divideOption + divideLineBearing OU a linha de corte")
            criadas = _rodar(fluxos.dividir, cur, auth.tenant_id, parcela_id=corpo.divideParcelGuid,
                             registro_id=corpo.record, rumo_graus=corpo.divideLineBearing,
                             opcao=corpo.divideOption,
                             numero_de_partes=corpo.divideNumberOfParts,
                             parte_area_ou_largura=corpo.dividePartAreaOrWidth,
                             lado_esquerdo=corpo.divideLeftSide,
                             distribuir_restante=corpo.divideDistributeRemainder,
                             tipo=corpo.divideParcelType)
            op = corpo.divideOption
        return _resposta(request, cur, "parcelas/divide", str(criadas[0]["id"]) if criadas else "-",
                         {"divideOption": op, "partes": len(criadas)}, "Parcela", criadas, [])


@router.post("/merge", status_code=200, openapi_extra=LER)
def merge(corpo: MergeEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Merge (forma da doc `.../ParcelFabricServer/merge`): une as parentParcels em uma parcela.
    Linhas externas continuam ativas; a interna é RETIRADA (a casa não apaga, §11)."""
    if corpo.mergeInto is not None:
        raise ErroAPI(422, "valor_invalido",
                      "mergeInto não é implementado na casa: a união sempre cria parcela nova")
    ids = []
    for par in corpo.parentParcels:
        fid = (par or {}).get("id")
        if not fid:
            raise ErroAPI(422, "valor_invalido", "parentParcels precisa de {{id, layerId}} por item")
        ids.append(str(fid))
    with db.db(auth.contexto()) as cur:
        unida = _rodar(fluxos.unir, cur, auth.tenant_id, parcela_ids=ids, registro_id=corpo.record,
                       codigo=corpo.codigo, tipo=corpo.targetParcelType)
        return _resposta(request, cur, "parcelas/merge", str(unida["id"]),
                         {"origens": len(ids)}, "Parcela", [unida], [])


@router.post("/clip", status_code=200, openapi_extra=LER)
def clip(corpo: ClipEntrada, request: Request, auth: Auth = autenticado(escopo_token=ESCOPO)):
    """Clip (forma da doc `.../ParcelFabricServer/clip`): recorta a parcela com clippingGeometry
    (GeoJSON Polygon) OU clippingParcels, com clipOption PreserveArea/DiscardArea/
    PreserveBothAreasSplit."""
    pai = _um_pai(corpo.parentParcels, "parentParcels")
    wkt = _corpo_geojson_poligono(corpo.clippingGeometry) if corpo.clippingGeometry else None
    recorte_id = None
    if corpo.clippingParcels:
        recorte_id = _um_pai(corpo.clippingParcels, "clippingParcels")
    if wkt is None and recorte_id is None:
        raise ErroAPI(422, "valor_invalido", "informe clippingGeometry OU clippingParcels")
    with db.db(auth.contexto()) as cur:
        r = _rodar(fluxos.recortar, cur, auth.tenant_id, parcela_id=pai, registro_id=corpo.record,
                   opcao=corpo.clipOption, geometria_wkt=wkt,
                   parcela_recorte_id=recorte_id, codigo=corpo.codigo)
        return _resposta(request, cur, "parcelas/clip", pai,
                         {"clipOption": corpo.clipOption, "adds": len(r["adds"])},
                         "Parcela", r["adds"], [r["atualizado"]] if r["atualizado"] else [])


@router.post("/createSeeds", status_code=200, openapi_extra=LER)
def create_seeds(corpo: CreateSeedsEntrada, request: Request,
                 auth: Auth = autenticado(escopo_token=ESCOPO)):
    """CreateSeeds (forma da doc `.../ParcelFabricServer/createSeeds`): uma semente por face
    fechada pelas linhas do registro."""
    extent = corpo.extent.model_dump() if corpo.extent else None
    with db.db(auth.contexto()) as cur:
        criadas = _rodar(fluxos.criar_sementes, cur, auth.tenant_id, registro_id=corpo.record,
                         extent=extent)
        return _resposta(request, cur, "parcelas/create_seeds", corpo.record,
                         {"sementes": len(criadas)}, "Semente",
                         [{"id": s["id"], "codigo": f"semente-{i + 1}"}
                          for i, s in enumerate(criadas)], [])


@router.post("/reconstructFromSeeds", status_code=200, openapi_extra=LER)
def reconstruct_from_seeds(corpo: ReconstructEntrada, request: Request,
                           auth: Auth = autenticado(escopo_token=ESCOPO)):
    """ReconstructFromSeeds (forma da doc `.../ParcelFabricServer/reconstructFromSeeds`):
    reconstrói parcelas das sementes na extent; a resposta carrega reconstructedParcelCount."""
    extent = corpo.extent.model_dump()
    with db.db(auth.contexto()) as cur:
        r = _rodar(fluxos.reconstruir_de_sementes, cur, auth.tenant_id, registro_id=corpo.record,
                   extent=extent)
        resposta = _resposta(request, cur, "parcelas/reconstruct_from_seeds", corpo.record,
                             {"reconstructedParcelCount": r["count"]}, "Parcela", r["criadas"], [])
        resposta["reconstructedParcelCount"] = r["count"]
        return resposta


@router.post("/assignFeaturesToRecord", status_code=200, openapi_extra=LER)
def assign_features_to_record(corpo: AssignEntrada, request: Request,
                              auth: Auth = autenticado(escopo_token=ESCOPO)):
    """AssignFeaturesToRecord (forma da doc `.../ParcelFabricServer/assignFeaturesToRecord`; o
    portão chama de assignToRecord): atribui parcela/linha/ponto/conexão a um registro, com
    writeAttribute CreatedByRecord|RetiredByRecord."""
    with db.db(auth.contexto()) as cur:
        r = _rodar(fluxos.atribuir_a_registro, cur, auth.tenant_id, pares=corpo.parcelFeatures,
                   registro_id=corpo.record, escrever=corpo.writeAttribute)
        return _resposta(request, cur, "parcelas/assign_features_to_record", corpo.record,
                         {"writeAttribute": r["writeAttribute"], "feicoes": len(r["feitos"])},
                         r["feitos"][0]["layerId"] if r["feitos"] else "Parcela", [], [])
