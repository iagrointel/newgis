"""Rotas da atualização em lote, da conferência e da exportação de subrede (item L4-04-b).

  * `POST /api/rede/{rede_id}/subredes/atualizar` — enfileira o job que atualiza as subredes SUJAS da rede
    (`todas=true` refaz a rede inteira). A atualização de UMA subrede continua síncrona, em
    `rotas_controladores.py` — é rápida e a tela precisa da resposta na hora.
  * `PUT /api/rede/{rede_id}/tier/{codigo}/propagadores` — declara os atributos que o tier propaga.
  * `GET /api/rede/{rede_id}/subredes/conferencia` — compara o nome calculado da subrede com um atributo do
    ARQUIVO no mesmo elemento; a diferença sai listada como candidata a erro de cadastro, nunca como erro
    provado.
  * `GET /api/rede/{rede_id}/subrede/{nome}/exportar` — o JSON da subrede (elementos, conectividade,
    controladores, resumo), validado contra o esquema declarado antes de sair. Com `formato=dss`
    (item L4-05-a-exportar-opendss) a mesma rota devolve a PASTA OpenDSS da subrede, num zip: Master.dss,
    Linhas.dss, Transformadores.dss, Cargas.dss, Curvas.dss, resumo.json e NAO_FAZ.md."""

import io
import uuid as uuid_mod
import zipfile

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de
from app.rede_utilidades import opendss, subredes
from app.rede_utilidades.modelos import PropagadoresEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — subredes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
CONFERENCIA_LIMITE_MAX = 1000


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


@router.post("/{rede_id}/subredes/atualizar", status_code=202, openapi_extra=EDITAR)
def atualizar_subredes(rede_id: str, request: Request, todas: bool = False, tier: str | None = None,
                       auth: Auth = autenticado("rede.editar")):
    """Enfileira o job `redes.subredes_atualizar`. Devolve 202 com o id do job: quem chama acompanha em
    `GET /api/jobs/{id}` como em qualquer outro trabalho pesado da plataforma."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
    job = servico.criar(sessao_de(auth), "redes.subredes_atualizar",
                        {"rede_id": rid, "todas": todas, "tier": tier})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "redes/subredes_atualizar", "rede", rid,
                         {"job_id": str(job["id"]), "todas": todas, "tier": tier})
    return {"rede_id": rid, "job_id": str(job["id"]), "todas": todas, "tier": tier}


@router.put("/{rede_id}/tier/{codigo}/propagadores", status_code=200, openapi_extra=EDITAR)
def definir_propagadores(rede_id: str, codigo: str, corpo: PropagadoresEntrada, request: Request,
                         auth: Auth = autenticado("rede.editar")):
    """Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            r = subredes.definir_propagadores(cur, rid, codigo, corpo.propagadores)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/tier_propagadores", "rede", rid, r)
        return r


@router.get("/{rede_id}/subredes/conferencia", openapi_extra=LER)
def conferir_subredes(rede_id: str, atributo: str = "ctmt", grupo: str = "trecho_de_media_tensao",
                      tier: str | None = None, limite: int = 200,
                      auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Concordância entre o nome da subrede calculado pelo traçado e o atributo do arquivo no mesmo elemento.
    A saída traz o universo (quantos elementos), quantos são comparáveis e a lista das diferenças — que são
    candidatas a erro de cadastro, não erro provado."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return subredes.conferir(cur, rid, atributo, grupo, tier, min(max(limite, 1),
                                                                     CONFERENCIA_LIMITE_MAX))


def _exportar_sincrono(rid: str, nome: str, tier: str | None, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return subredes.exportar(cur, rid, nome, tier)


def _exportar_dss_sincrono(rid: str, nome: str, tier: str | None, ano: int | None, jusante: bool,
                           auth: Auth) -> bytes:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        saida = subredes.exportar_dss(cur, rid, nome, tier, ano, jusante)
    pasta = opendss.sanear(nome)
    memoria = io.BytesIO()
    # ZIP_DEFLATED e não ZIP_STORED: a curva de 864 pontos é texto muito repetido e o zip cai a uma fração.
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo, texto in saida["arquivos"].items():
            z.writestr(f"{pasta}/{arquivo}", texto)
    return memoria.getvalue()


@router.get("/{rede_id}/subrede/{nome}/exportar", openapi_extra=LER)
async def exportar_subrede(rede_id: str, nome: str, tier: str | None = None, formato: str = "json",
                           ano: int | None = None, jusante: bool = False,
                           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """`formato=json` (padrão): rede, subrede (com a linha agregada), controladores, elementos,
    conectividade e resumo, validado contra `plat.rede.subrede_exportada` antes de sair.

    `formato=dss`: a pasta OpenDSS da subrede, num zip. `ano` escolhe o calendário da curva de 864 pontos
    (24 h x 3 tipos de dia x 12 meses); o padrão é o ano corrente. `jusante=true` inclui as subredes de tier
    inferior que penduram nesta — é o alimentador inteiro, com transformador e carga, em vez de só o tier
    pedido."""
    rid = _uuid_ok(rede_id)
    if formato == "json":
        return await run_in_threadpool(_exportar_sincrono, rid, nome, tier, auth)
    if formato != "dss":
        raise ErroAPI(422, "formato_desconhecido", "formato tem de ser 'json' ou 'dss'")
    if ano is not None and not 1970 <= ano <= 2200:
        raise ErroAPI(422, "ano_fora_da_faixa", "ano tem de estar entre 1970 e 2200")
    bruto = await run_in_threadpool(_exportar_dss_sincrono, rid, nome, tier, ano, jusante, auth)
    return Response(
        content=bruto, media_type="application/zip",
        headers={"Cache-Control": "no-store",
                 "Content-Disposition": f'attachment; filename="{opendss.sanear(nome)}-dss.zip"'},
    )
