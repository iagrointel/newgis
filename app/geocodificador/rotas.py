"""API própria do geocodificador (item L2-11-b-geocodificador-brasil, ADR 0013 seção 4):
POST /api/geocodificar, POST /api/reverso, GET /api/sugerir. Sem tabela de inquilino (mesmo motivo do
L2-11-c-rota-matriz-isocrona: dado aberto do IBGE, não do dono do token) — a autenticação exige só o escopo
`geocodificar:usar` (token) ou sessão de usuário."""

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from app import db
from app.auth.sessao import autenticado
from app.erros import ErroAPI
from app.geocodificador import motor
from app.geocodificador.normalizacao import analisar_linha_unica, expandir_abreviacoes, extrair_cep

log = logging.getLogger("plat.geocodificador.rotas")
router = APIRouter(prefix="/api", tags=["geocodificador"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}
MAX_LOCATIONS_TETO = 50


def _cep_valido(v: str | None) -> str | None:
    if v is None:
        return None
    v2 = "".join(c for c in v if c.isdigit())
    if len(v2) != 8:
        raise ValueError("CEP precisa de 8 dígitos")
    return v2


class PedidoGeocodificar(BaseModel):
    endereco: str | None = Field(None, description="linha única, ex.: 'Rua X, 123, Bairro, Município - UF'")
    logradouro: str | None = None
    numero: int | None = Field(None, ge=0, le=999999)
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = Field(None, min_length=2, max_length=2)
    cep: str | None = None
    max_locations: int = Field(10, ge=1, le=MAX_LOCATIONS_TETO)

    @field_validator("cep")
    @classmethod
    def _v_cep(cls, v):
        return _cep_valido(v)

    @field_validator("uf")
    @classmethod
    def _v_uf(cls, v):
        return v.upper() if v else v


class PedidoReverso(BaseModel):
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    raio_m: float = Field(2000.0, gt=0, le=50000)


def _resolver_campos(pedido: PedidoGeocodificar) -> dict:
    """Campos estruturados têm prioridade; `endereco` (linha única) preenche o que faltar — mistura os dois
    sem exigir um formato só (paridade com o `singleLine` x multifield do Esri)."""
    logradouro = pedido.logradouro
    numero = pedido.numero
    bairro = pedido.bairro
    municipio = pedido.municipio
    uf = pedido.uf
    cep = pedido.cep
    if pedido.endereco:
        livre = analisar_linha_unica(pedido.endereco)
        logradouro = logradouro or livre.logradouro
        numero = numero if numero is not None else livre.numero
        bairro = bairro or livre.bairro
        municipio = municipio or livre.municipio
        uf = uf or livre.uf
        cep = cep or (extrair_cep(livre.cep) if livre.cep else None) or livre.cep
    if logradouro:
        logradouro = expandir_abreviacoes(logradouro)
    if not any([logradouro, bairro, municipio, cep]):
        raise ErroAPI(
            422, "endereco_vazio",
            "informe ao menos um de: endereco, logradouro, bairro, municipio ou cep",
        )
    return {"logradouro": logradouro, "numero": numero, "bairro": bairro, "municipio": municipio, "uf": uf,
            "cep": cep}


@router.post("/geocodificar", openapi_extra=X)
def geocodificar(pedido: PedidoGeocodificar, auth=autenticado(escopo_token="geocodificar:usar")):
    campos = _resolver_campos(pedido)
    with db.db() as cur:
        try:
            candidatos = motor.buscar(cur, max_locations=pedido.max_locations, **campos)
        except motor.InconsistenciaEndereco as e:
            raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e
    if not candidatos:
        raise ErroAPI(
            422, "sem_correspondencia",
            "nenhum lugar do CNEFE carregado corresponde ao pedido (UF/município ainda não instalado, ou "
            "logradouro/bairro sem semelhança suficiente)",
            {"pedido": campos},
        )
    return {"candidatos": [c.como_dict() for c in candidatos], "total": len(candidatos)}


@router.post("/reverso", openapi_extra=X)
def reverso(pedido: PedidoReverso, auth=autenticado(escopo_token="geocodificar:usar")):
    with db.db() as cur:
        r = motor.reverso(cur, pedido.lon, pedido.lat, pedido.raio_m)
    if r is None:
        raise ErroAPI(422, "sem_dado_instalado", "nenhuma UF do CNEFE está instalada ainda")
    return r


@router.get("/sugerir", openapi_extra=X)
def sugerir(
    q: str = Query(..., min_length=2, max_length=200),
    limite: int = Query(10, ge=1, le=25),
    auth=autenticado(escopo_token="geocodificar:usar"),
):
    with db.db() as cur:
        return {"sugestoes": motor.sugerir(cur, q, limite)}
