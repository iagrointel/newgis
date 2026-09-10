"""Rotas do fluxo de potência do alimentador (item L4-07-fluxo-de-potencia).

  * `POST /api/rede/{rede_id}/subrede/{nome}/fluxo` — analisa o alimentador e grava. Os PARÂMETROS vão no
    corpo (modo, ponto, ano, fator de carga, modelo de carga ZIP, tensão da fonte, corrente nominal de
    referência, geração distribuída) e saem gravados junto do resultado.
  * `GET  /api/rede/{rede_id}/subrede/{nome}/fluxo` — a tabela do último cálculo, com a ficha ao lado
    (parâmetros, versão da topologia e ESTADO DE CONVERGÊNCIA).
  * `GET  /api/rede/{rede_id}/subrede/{nome}/fluxo/camada?grandeza=tensao|corrente|carregamento` — o mesmo
    resultado como camada para o mapa.

O caminho pesado (uma cooperativa inteira) é o job `redes.analisar_alimentador`, não estas rotas: o motor
OpenDSS é global ao processo e uma varredura de 864 pontos num alimentador grande não cabe numa requisição.

Mesmo padrão dos outros módulos de rede: escrita exige `rede.editar`, leitura segue a visibilidade por
inquilino (RLS), trabalho pesado vai para o threadpool."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Body, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import fluxo_potencia

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — fluxo de potência"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _calcular_sincrono(rid: str, nome: str, corpo: dict, tier: str | None, jusante: bool,
                       auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            saida = fluxo_potencia.calcular_e_gravar(cur, auth.tenant_id, rid, nome, corpo, tier, jusante)
        except fluxo_potencia.ErroFluxo as e:
            raise ErroAPI(422, e.codigo, e.mensagem) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/fluxo_potencia", "rede", rid,
                         {"subrede": saida["subrede"], "parametros": saida["parametros"],
                          "convergencia": saida["convergencia"],
                          "ponto_critico": saida["ponto_critico"]})
    return saida


def _ler_sincrono(rid: str, nome: str, grandeza: str | None, tipo: str | None, limite: int,
                  auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        if grandeza is not None:
            return fluxo_potencia.camada(cur, rid, nome, grandeza)
        return fluxo_potencia.tabela(cur, rid, nome, tipo, limite)


@router.post("/{rede_id}/subrede/{nome}/fluxo", status_code=200, openapi_extra=EDITAR)
async def calcular_fluxo(rede_id: str, nome: str, request: Request,
                         parametros: dict = Body(default_factory=dict),
                         tier: str | None = None, jusante: bool = False,
                         auth: Auth = autenticado("rede.editar")):
    """Fluxo de potência trifásico desequilibrado do alimentador, no OpenDSS, sobre o MESMO modelo em
    memória que os exportadores usam.

    O corpo são os PARÂMETROS: `modo` (`anual`, os 864 pontos da curva, ou `hora`), `ponto`, `ano`,
    `fator_de_carga`, `modelo_de_carga` (com `zipv` obrigatório quando `zip`), `tensao_da_fonte_pu`,
    `corrente_nominal_a` e `com_geracao_distribuida`. Todos saem gravados ao lado do resultado, com a
    versão da topologia e o estado de convergência. É triagem: a impedância de condutor é a padrão do
    OpenDSS, porque o cadastro de distribuição não a traz."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_calcular_sincrono, rid, nome, parametros, tier, jusante, auth, request)


@router.get("/{rede_id}/subrede/{nome}/fluxo", openapi_extra=LER)
async def ler_fluxo(rede_id: str, nome: str, tipo: str | None = None, limite: int = 5000,
                    auth: Auth = autenticado()):
    """A tabela do último cálculo deste alimentador: uma linha por elemento (barra e fase, trecho,
    transformador), ordenada pelo que dói primeiro — menor tensão, maior carregamento, maior perda. A ficha
    do resultado (parâmetros, versão da topologia, convergência) vem no mesmo corpo, porque o número não se
    lê sem a hipótese que o produziu nem sem saber se o cálculo fechou."""
    return await run_in_threadpool(_ler_sincrono, _uuid_ok(rede_id), nome, None, tipo, limite, auth)


@router.get("/{rede_id}/subrede/{nome}/fluxo/camada", openapi_extra=LER)
async def ler_fluxo_camada(rede_id: str, nome: str, grandeza: str = "tensao", auth: Auth = autenticado()):
    """O mesmo resultado como camada para o mapa: `tensao` (um ponto por barra e fase, em por unidade),
    `corrente` (a linha do trecho, em ampere) ou `carregamento` (a mesma linha, em por cento da corrente
    nominal declarada). Elemento sem geometria é contado em `elementos_sem_geometria` e não vira feição."""
    return await run_in_threadpool(_ler_sincrono, _uuid_ok(rede_id), nome, grandeza, None, 0, auth)
