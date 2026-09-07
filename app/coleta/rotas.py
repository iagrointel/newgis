"""Rotas do formulário de coleta (item L2-07-b): importar XLSForm (cria o item `formulario` e, sem camada
informada, a camada de destino e as camadas filhas das repetições), ler o documento, responder e consultar a
tabela de equivalência XLSForm -> linguagem própria."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app import db, limites
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, tipos
from app.catalogo.camada_nova import criar_camada
from app.coleta import respostas, xlsform
from app.coleta.documento import COLUNAS_AUTOMATICAS, COLUNAS_REPETICAO, META_PG, TIPO_PG, folhas, nos
from app.coleta.xpath import tabela_equivalencia
from app.edicao.modelos import UUID_PADRAO, Modelo, Saida
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["formularios"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
PUBLICAR = {"x-auth": "S/T", "x-privilegio": "conteudo.publicar_camada"}
RESPONDER = {"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"}


class XlsformEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=255)
    conteudo: str = Field(min_length=1)  # base64 da planilha (escrita sob cookie é JSON, ADR 0002 seção 5.3)
    titulo: str | None = Field(default=None, max_length=250)
    camada_destino: str | None = Field(default=None, pattern=UUID_PADRAO)


class AnexoResposta(Modelo):
    campo: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    conteudo: str = Field(min_length=1)


class RespostaEntrada(Modelo):
    valores: dict[str, Any] = Field(default_factory=dict, max_length=limites.FORMULARIO_CAMPOS_MAX)
    repeticoes: dict[str, list[dict[str, Any]]] = Field(default_factory=dict, max_length=50)
    inicio: str | None = Field(default=None, max_length=40)
    fim: str | None = Field(default=None, max_length=40)
    dispositivo: str | None = Field(default=None, max_length=200)
    anexos: list[AnexoResposta] = Field(default_factory=list, max_length=limites.FORMULARIO_ANEXOS_MAX)


class FormularioSaida(Saida):
    id: str
    titulo: str
    documento: dict


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _auth_editor(auth: Auth = autenticado(escopo_token="camada:editar")) -> Auth:  # noqa: B008
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
                      {"exigido": "feicoes.editar|feicoes.editar_total"})
    return auth


def _formulario_ou_404(cur, item_id: str) -> dict:
    r = comum.item_ou_404(cur, item_id)
    if r["tipo"] != "formulario":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    return r


def _colunas_de(campos: list[dict]) -> list[dict]:
    """Campos-folha (fora repetições) -> colunas da camada, na ordem do formulário."""
    saida = []
    for c, rep in folhas(campos):
        if rep is not None or c["tipo"] in ("nota", "geoponto", "grupo", "repeticao"):
            continue
        tipo = META_PG.get(c.get("meta"), "text") if c["tipo"] == "meta" else TIPO_PG[c["tipo"]]
        saida.append({"nome": c["nome"], "tipo": tipo, "alias": _rotulo_padrao(c)})
    return saida


def _rotulo_padrao(c: dict) -> str:
    r = c.get("rotulo") or {}
    return (next(iter(r.values()), None) or c["nome"])[:250]


def _ligar_colunas(campos: list[dict], mapa: dict[str, str], dentro_de_repeticao: bool = False) -> None:
    for c in campos:
        if c["tipo"] == "repeticao":
            continue  # as filhas são ligadas à camada filha, em _ligar_colunas da própria repetição
        if c["tipo"] == "grupo":
            _ligar_colunas(c.get("filhos") or [], mapa, dentro_de_repeticao)
            continue
        if c["nome"] in mapa:
            c["campo_destino"] = mapa[c["nome"]]


def _existente_ou_404(cur, camada_id: str) -> dict:
    r = comum.item_ou_404(cur, camada_id)
    if r["tipo"] != "camada_vetorial" or (r["dados"] or {}).get("fonte") != "hospedada":
        raise ErroAPI(422, "camada_destino_invalida", "a camada de destino tem de ser vetorial hospedada")
    return r


def _tem_geoponto(campos: list[dict]) -> bool:
    return any(c["tipo"] == "geoponto" for c, rep in folhas(campos) if rep is None)


@router.get("/formularios/equivalencia", openapi_extra=LER)
def equivalencia(auth: Auth = autenticado()) -> dict:
    """Tabela XLSForm -> linguagem própria por função (feito / parcial / fora), C6."""
    return {"funcoes": tabela_equivalencia()}


@router.post("/formularios/xlsform", status_code=201, response_model=FormularioSaida, openapi_extra=PUBLICAR)
def importar_xlsform(corpo: XlsformEntrada, request: Request,
                     auth: Auth = autenticado("conteudo.publicar_camada")):
    try:
        conteudo = base64.b64decode(corpo.conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "conteudo_invalido", "conteúdo não é base64 válido") from e
    try:
        with db.db(auth.contexto()) as cur:
            existente = _existente_ou_404(cur, corpo.camada_destino) if corpo.camada_destino else None
            doc = xlsform.importar(conteudo, corpo.nome)
            titulo = (corpo.titulo or doc["titulo"] or corpo.nome)[:250]
            # sem geopoint a camada declara `geometria: nenhuma` (a coluna geom física existe, nula; ver
            # app/catalogo/camada_nova.py) e a API de edição não exige geometria ao adicionar
            sem_geom = {"geometria": "nenhuma"} if not _tem_geoponto(doc["campos"]) else None
            if existente is not None:
                camada_id = existente["id"]
                nomes_existentes = {c["nome"] for c in (existente["dados"] or {}).get("campos") or []}
                mapa = {c["nome"]: c["nome"] for c in _colunas_de(doc["campos"]) if c["nome"] in nomes_existentes}
                for c in _colunas_de(doc["campos"]):
                    if c["nome"] not in nomes_existentes:
                        doc["avisos"].append({"campo": c["nome"], "papel": "coluna", "funcao": "", "estado": "fora",
                                              "trecho": c["nome"], "motivo": "camada de destino sem esta coluna"})
            else:
                colunas = _colunas_de(doc["campos"]) + [{"nome": n, "tipo": t} for n, t in COLUNAS_AUTOMATICAS]
                camada_id, dados = criar_camada(cur, auth.usuario_id, titulo, colunas, extra_dados=sem_geom)
                mapa = dados["mapa_nomes"]
            _ligar_colunas(doc["campos"], mapa)
            doc["camada_destino"] = str(camada_id)
            doc["camadas_filhas"] = {}
            for no in nos(doc["campos"]):
                if no["tipo"] != "repeticao":
                    continue
                colunas = _colunas_de(no.get("filhos") or []) + [{"nome": n, "tipo": t} for n, t in COLUNAS_REPETICAO]
                filha_id, dados_f = criar_camada(cur, auth.usuario_id, f"{titulo} - {_rotulo_padrao(no)}", colunas,
                                                 extra_dados={"geometria": "nenhuma"})
                _ligar_colunas(no.get("filhos") or [], dados_f["mapa_nomes"], True)
                doc["camadas_filhas"][no["nome"]] = str(filha_id)
                cur.execute(
                    "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, %s::uuid, "
                    "'repeticao_de_camada', %s) ON CONFLICT DO NOTHING",
                    (str(camada_id), str(filha_id), auth.tenant_id))
            doc["tem_geometria"] = _tem_geoponto(doc["campos"])
            tipos.validar("formulario", doc)
            cur.execute(
                "INSERT INTO plat.item(tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, modificado_por) "
                "VALUES (%s, 'formulario', %s, %s, %s, 'inquilino', %s, %s) RETURNING id",
                (auth.tenant_id, titulo, auth.usuario_id, _jsonb(doc), auth.usuario_id, auth.usuario_id))
            item_id = str(cur.fetchone()["id"])
            cur.execute(
                "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, %s::uuid, "
                "'formulario_de_camada', %s) ON CONFLICT DO NOTHING", (item_id, str(camada_id), auth.tenant_id))
            comum.registrar_evento(cur, request, "formularios/importar", "item", item_id,
                                   {"camada": str(camada_id), "campos": len(list(folhas(doc["campos"]))),
                                    "avisos": len(doc["avisos"])})
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return FormularioSaida(id=item_id, titulo=titulo, documento=doc)


@router.get("/formularios/{id}", response_model=FormularioSaida, openapi_extra=LER)
def obter_formulario(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")) -> FormularioSaida:
    iid = comum.uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = _formulario_ou_404(cur, iid)
    return FormularioSaida(id=str(r["id"]), titulo=r["titulo"], documento=r["dados"] or {})


@router.post("/formularios/{id}/respostas", status_code=201, openapi_extra=RESPONDER)
def responder_formulario(id: str, corpo: RespostaEntrada, request: Request,
                         auth: Auth = Depends(_auth_editor)) -> dict:
    iid = comum.uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            formulario = _formulario_ou_404(cur, iid)
            camada = (formulario["dados"] or {}).get("camada_destino")
            if camada:
                esc.exigir_escopo(auth, "camada:editar", camada)
            saida = respostas.responder(cur, request, auth, formulario, corpo.model_dump())
            comum.registrar_evento(cur, request, "formularios/responder", "item", iid,
                                   {"feicao": saida["feicao"]["id"], "repeticoes": saida["repeticoes"]})
            return saida
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
