"""GeocodeServer compatível (item L2-11-b-geocodificador-brasil, ADR 0013 seção 5): o mesmo motor por trás de
`/api/geocodificar` respondendo o protocolo REST do ArcGIS Enterprise Geocode Service, para que ArcGIS Pro,
QGIS (locator "ArcGIS geocoder") ou qualquer app JS Esri usem esta instalação como se fosse um locator publicado.

Cobertura (docs/PARIDADE.md tem a linha viva; fontes: developers.arcgis.com/rest/services-reference/enterprise/
geocode-service, find-address-candidates, reverse-geocode, suggest, geocode-addresses, 2026-09-06):
  feito    - GET .../GeocodeServer?f=json (descritor); findAddressCandidates (SingleLine ou multifield;
             outFields; maxLocations; f=json); reverseGeocode (location=x,y ou {"x":..,"y":..}; f=json);
             suggest (text; magicKey na resposta reaproveitável em findAddressCandidates); geocodeAddresses
             em lote (addresses.records[].attributes.{OBJECTID,SingleLine|Address+City+Region+Postal}).
  parcial  - score/atributos de saída: não replica 1:1 o vocabulário Esri (Addr_type, Loc_name, Match_addr);
             devolve os nomes em português do motor nativo dentro de `attributes`, mais um Addr_type
             aproximado (mapeado da hierarquia de recuo) para clientes que só leem esse campo.
  fora     - outSR (sempre 4326), searchExtent, location=x,y de preferência (boost), category, langCode,
             paginação search/start/num, autenticação por `generateToken` da Esri (usa o token do plat).
Autenticação: o protocolo Esri manda o token como parâmetro de URL `token=...` (GeocodeServer publicado em
ArcGIS Server/Portal não usa cabeçalho Authorization) — por isso este router aceita o MESMO token de serviço
do plat só que por querystring, além do cabeçalho normal; reaproveita `app.auth.sessao._auth_de_token` (função
"privada" do módulo, mas mesmo pacote `app`) só para isso, sem duplicar a lógica de validação de token."""

import json
import logging

from fastapi import APIRouter, Request

from app import db
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.erros import ErroAPI
from app.geocodificador import motor
from app.geocodificador.normalizacao import analisar_linha_unica, expandir_abreviacoes, extrair_cep

log = logging.getLogger("plat.geocodificador.esri")
router = APIRouter(tags=["geocodificador-esri"])
PREFIXO = "/rest/services/Geocodificador/GeocodeServer"
ESCOPO = "geocodificar:usar"

# hierarquia de recuo -> Addr_type aproximado do vocabulário Esri (parcial: ver docstring do módulo)
ADDR_TYPE = {
    "numero_exato": "PointAddress",
    "interpolado_na_face": "StreetAddress",
    "aproximado_no_logradouro": "StreetName",
    "aproximado_no_bairro": "Locality",
    "aproximado_no_cep": "PostalExt",
    "aproximado_no_municipio": "Locality",
}


# item L7-08-d: estas rotas autenticam DENTRO do handler (`_autenticar` abaixo aceita `?token=`, protocolo
# Esri), logo não há dependência `autenticado(...)` de onde derivar o `x-plat-escopo`. Aqui, e só aqui, ele é
# declarado — e a varredura de tests/api/test_portal_chaves.py confere a declaração contra o servidor.
X_ESRI = {"x-auth": "S/T", "x-plat-escopo": ESCOPO}
# o descritor do locator é metadado e NÃO autentica (ver a docstring de `descritor_servico`): a etiqueta
# tem de dizer isso, senão o portal promete uma proteção que o servidor não faz. Achado da varredura de
# tests/api/test_portal_chaves.py::test_varredura_sem_chave_nenhuma_nao_devolve_200.
X_ESRI_ABERTO = {"x-auth": "-", "x-privilegio": "publico", "x-plat-escopo": "publico"}


def _autenticar(request: Request):
    """Sessão/cabeçalho Authorization normal OU `?token=`/form `token=` (protocolo Esri)."""
    try:
        auth = auth_sessao.resolver(request)
    except ErroAPI:
        auth = None
    if auth is None:
        tok = request.query_params.get("token")
        if not tok:
            raise ErroAPI(401, "token_requerido", "informe token=<token de serviço plat> (protocolo Esri) ou "
                           "o cabeçalho Authorization: Bearer")
        auth = auth_sessao._auth_de_token(request, tok)  # noqa: SLF001 — reuso deliberado, ver docstring
        request.state.auth = auth
    esc.exigir_escopo(auth, ESCOPO)
    return auth


async def _parametros(request: Request) -> dict:
    """Esri aceita GET (querystring) e POST (form ou querystring); nunca JSON de corpo nas rotas de
    geocodificação (isso é só do geocodeAddresses, tratado à parte)."""
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
    return p


def _campos_de(p: dict) -> dict:
    single = p.get("SingleLine") or p.get("singleLine")
    logradouro = p.get("address")
    bairro = p.get("neighborhood")
    municipio = p.get("city")
    uf = (p.get("region") or "")[:2].upper() or None
    cep = p.get("postal")
    numero = None
    if single:
        livre = analisar_linha_unica(single)
        logradouro = logradouro or livre.logradouro
        numero = livre.numero
        bairro = bairro or livre.bairro
        municipio = municipio or livre.municipio
        uf = uf or livre.uf
        cep = cep or livre.cep
    if logradouro:
        logradouro = expandir_abreviacoes(logradouro)
    if cep:
        cep = extrair_cep(cep) or "".join(c for c in cep if c.isdigit()) or None
    return {"logradouro": logradouro, "numero": numero, "bairro": bairro, "municipio": municipio, "uf": uf,
            "cep": cep}


@router.get(PREFIXO, openapi_extra=X_ESRI_ABERTO, operation_id="geocodificador_esri_descritor_get")
@router.post(PREFIXO, openapi_extra=X_ESRI_ABERTO, operation_id="geocodificador_esri_descritor_post")
async def descritor_servico(request: Request):
    """Descritor do locator (ADR 0013 seção 5.1) — mínimo para o QGIS/ArcGIS reconhecerem o serviço como
    GeocodeServer (capabilities, candidateFields, spatialReference); não exige autenticação (só metadado)."""
    return {
        "currentVersion": 11.3,
        "serviceDescription": "Geocodificador plat — CNEFE 2022 (IBGE), análise/beta privado",
        "addressFields": [
            {"name": "SingleLine", "type": "esriFieldTypeString", "length": 250, "required": False},
            {"name": "Address", "type": "esriFieldTypeString", "length": 250, "required": False},
            {"name": "City", "type": "esriFieldTypeString", "length": 120, "required": False},
            {"name": "Region", "type": "esriFieldTypeString", "length": 2, "required": False},
            {"name": "Postal", "type": "esriFieldTypeString", "length": 8, "required": False},
        ],
        "singleLineAddressField": {"name": "SingleLine", "type": "esriFieldTypeString", "length": 250},
        "candidateFields": [
            {"name": "Match_addr", "type": "esriFieldTypeString"},
            {"name": "Addr_type", "type": "esriFieldTypeString"},
            {"name": "Score", "type": "esriFieldTypeDouble"},
        ],
        "spatialReference": {"wkid": 4326, "latestWkid": 4326},
        "locatorProperties": {"MatchScoreThreshold": 60, "MinMatchScore": 0, "SuggestedBatchSize": 500},
        "capabilities": "Geocode,ReverseGeocode,Suggest",
    }


@router.get(f"{PREFIXO}/findAddressCandidates", openapi_extra=X_ESRI,
            operation_id="geocodificador_esri_find_address_candidates_get")
@router.post(f"{PREFIXO}/findAddressCandidates", openapi_extra=X_ESRI,
             operation_id="geocodificador_esri_find_address_candidates_post")
async def find_address_candidates(request: Request):
    _autenticar(request)
    p = await _parametros(request)
    campos = _campos_de(p)
    if not any([campos["logradouro"], campos["bairro"], campos["municipio"], campos["cep"]]):
        return {"spatialReference": {"wkid": 4326}, "candidates": []}
    max_locations = int(p.get("maxLocations") or 10)
    with db.db() as cur:
        try:
            candidatos = motor.buscar(cur, max_locations=max_locations, **campos)
        except motor.InconsistenciaEndereco as e:
            raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
    saida = []
    for c in candidatos:
        d = c.como_dict()
        saida.append({
            "address": d["endereco"],
            "location": {"x": d["lon"], "y": d["lat"]},
            "score": d["score"],
            "attributes": {
                "Match_addr": d["endereco"], "Addr_type": ADDR_TYPE.get(d["tipo_acerto"], "Locality"),
                "Score": d["score"], "tipo_acerto": d["tipo_acerto"], "municipio": d["municipio"], "uf": d["uf"],
            },
            "extent": {"xmin": d["lon"] - 0.01, "ymin": d["lat"] - 0.01, "xmax": d["lon"] + 0.01,
                       "ymax": d["lat"] + 0.01},
        })
    return {"spatialReference": {"wkid": 4326}, "candidates": saida}


@router.get(f"{PREFIXO}/reverseGeocode", openapi_extra=X_ESRI,
            operation_id="geocodificador_esri_reverse_geocode_get")
@router.post(f"{PREFIXO}/reverseGeocode", openapi_extra=X_ESRI,
             operation_id="geocodificador_esri_reverse_geocode_post")
async def reverse_geocode(request: Request):
    _autenticar(request)
    p = await _parametros(request)
    loc = p.get("location")
    if not loc:
        raise ErroAPI(422, "location_ausente", "informe location=<lon>,<lat> ou {'x':..,'y':..}")
    try:
        if loc.strip().startswith("{"):
            obj = json.loads(loc)
            lon, lat = float(obj["x"]), float(obj["y"])
        else:
            lon_s, lat_s = loc.split(",")[:2]
            lon, lat = float(lon_s), float(lat_s)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise ErroAPI(422, "location_invalida", f"location inválida: {loc!r}") from e
    raio_m = float(p.get("distance") or 2000)
    with db.db() as cur:
        r = motor.reverso(cur, lon, lat, raio_m)
    if r is None or r["fora_do_raio"]:
        raise ErroAPI(
            (404 if r is None else 400), "nao_encontrado" if r is None else "fora_da_distancia",
            "nenhum endereço instalado" if r is None else f"vizinho mais próximo a {r['distancia_m']} m, "
            f"acima de distance={raio_m}",
        )
    return {
        "address": {
            "Match_addr": r["endereco"], "Address": r["logradouro"], "City": r["municipio"], "Region": r["uf"],
            "Postal": r["cep"],
        },
        "location": {"x": r["lon"], "y": r["lat"]},
    }


@router.api_route(f"{PREFIXO}/suggest", methods=["GET"], openapi_extra=X_ESRI,
                   operation_id="geocodificador_esri_suggest")
async def suggest(request: Request):
    _autenticar(request)
    p = await _parametros(request)
    texto = p.get("text")
    if not texto or len(texto) < 2:
        return {"suggestions": []}
    limite = int(p.get("maxSuggestions") or 10)
    with db.db() as cur:
        sugestoes = motor.sugerir(cur, texto, limite)
    return {"suggestions": [{"text": s["texto"], "magicKey": s["chave"], "isCollection": False} for s in sugestoes]}


@router.api_route(f"{PREFIXO}/geocodeAddresses", methods=["POST"], openapi_extra=X_ESRI,
                   operation_id="geocodificador_esri_geocode_addresses")
async def geocode_addresses(request: Request):
    """Lote (item L2-11-a-geocodificacao-csv reusa este mesmo caminho para o motor, não esta rota HTTP).
    Corpo: {"addresses": {"records": [{"attributes": {"OBJECTID": 1, "SingleLine": "..."}}]}} — igual ao
    parâmetro `addresses` do geocodeAddresses da Esri (aqui já como JSON de corpo, não form-encoded, porque
    o único cliente medido neste turno é o teste HTTP direto; um cliente Esri real manda form/querystring —
    registrado como pendência em docs/PARIDADE.md, não como feito)."""
    _autenticar(request)
    corpo = await request.json()
    registros = (corpo.get("addresses") or {}).get("records") or []
    if not registros:
        raise ErroAPI(422, "lote_vazio", "addresses.records vazio")
    if len(registros) > 500:
        raise ErroAPI(422, "lote_grande_demais", "máximo 500 registros por chamada (SuggestedBatchSize)")
    locais = []
    with db.db() as cur:
        for reg in registros:
            atrs = reg.get("attributes", {})
            oid = atrs.get("OBJECTID")
            campos = _campos_de({
                "SingleLine": atrs.get("SingleLine"), "address": atrs.get("Address"), "city": atrs.get("City"),
                "region": atrs.get("Region"), "postal": atrs.get("Postal"),
            })
            try:
                candidatos = motor.buscar(cur, max_locations=1, **campos) if any(campos.values()) else []
            except motor.InconsistenciaEndereco:
                candidatos = []
            if candidatos:
                d = candidatos[0].como_dict()
                locais.append({
                    "address": d["endereco"], "location": {"x": d["lon"], "y": d["lat"]},
                    "score": d["score"],
                    "attributes": {"ResultID": oid, "Status": "M", "Match_addr": d["endereco"],
                                   "Addr_type": ADDR_TYPE.get(d["tipo_acerto"], "Locality")},
                })
            else:
                locais.append({"address": "", "location": {"x": None, "y": None}, "score": 0,
                                "attributes": {"ResultID": oid, "Status": "U"}})
    return {"spatialReference": {"wkid": 4326}, "locations": locais}
