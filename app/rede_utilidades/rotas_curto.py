"""Rotas do curto-circuito e da coordenação de proteção (item L4-27-curto-circuito-e-protecao).

  * `POST /api/rede/{rede_id}/subrede/{nome}/curto` — calcula e grava. As PREMISSAS vão no corpo; a
    potência de curto-circuito da fonte é obrigatória, e uma fonte de impedância nula é recusada com
    422 em vez de devolver corrente infinita.
  * `GET  /api/rede/{rede_id}/subrede/{nome}/curto` — a tabela do último cálculo (colunas descritas,
    linhas ordenadas da maior corrente para a menor) com as premissas ao lado.
  * `GET  /api/rede/{rede_id}/subrede/{nome}/curto/camada` — o MESMO resultado como camada de pontos
    (GeoJSON), com a coordenada lida da topologia na hora.

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
from app.rede_utilidades import curto_circuito

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — curto-circuito e proteção"])
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


def _calcular_sincrono(rid: str, nome: str, corpo: dict, tier: str | None, ano: int | None,
                       jusante: bool, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        try:
            saida = curto_circuito.calcular_e_gravar(cur, auth.tenant_id, rid, nome, corpo, tier, ano,
                                                     jusante)
        except curto_circuito.ErroCurto as e:
            raise ErroAPI(422, e.codigo, e.mensagem) from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/curto_circuito", "rede", rid,
                         {"subrede": saida["subrede"], "barras": saida["barras"],
                          "premissas": saida["premissas"],
                          "vereditos": saida["resumo"]["dispositivos_por_veredito"]})
    return saida


def _ler_sincrono(rid: str, nome: str, como_camada: bool, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        return (curto_circuito.camada if como_camada else curto_circuito.tabela)(cur, rid, nome)


@router.post("/{rede_id}/subrede/{nome}/curto", status_code=200, openapi_extra=EDITAR)
async def calcular_curto(rede_id: str, nome: str, request: Request,
                         premissas: dict = Body(default_factory=dict),
                         tier: str | None = None, ano: int | None = None, jusante: bool = False,
                         auth: Auth = autenticado("rede.editar")):
    """Corrente de curto-circuito por barra (trifásica e fase-terra) e verificação de coordenação simples
    do dispositivo a montante de cada barra, sobre o mesmo modelo em memória que os exportadores usam.

    O corpo são as PREMISSAS: `potencia_de_curto_mva` (obrigatória — sem ela a impedância da fonte é nula
    e a corrente seria infinita), `relacao_x_r_fonte`, `fator_tensao_c`, `fator_sequencia_zero_linha`,
    `fator_sequencia_zero_fonte` e `base_mva`. Todas saem gravadas ao lado do resultado. É triagem:
    a impedância de condutor e a do transformador são valores de REFERÊNCIA declarados, porque o cadastro
    de distribuição não os traz."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_calcular_sincrono, rid, nome, premissas, tier, ano, jusante, auth,
                                   request)


@router.get("/{rede_id}/subrede/{nome}/curto", openapi_extra=LER)
async def ler_curto(rede_id: str, nome: str, auth: Auth = autenticado()):
    """A tabela do último cálculo desta subrede: uma linha por barra, com a corrente trifásica, a
    fase-terra, o dispositivo a montante e o veredito de coordenação; as premissas do cálculo vêm no
    mesmo corpo, porque o número não se lê sem elas."""
    return await run_in_threadpool(_ler_sincrono, _uuid_ok(rede_id), nome, False, auth)


@router.get("/{rede_id}/subrede/{nome}/curto/camada", openapi_extra=LER)
async def ler_curto_camada(rede_id: str, nome: str, auth: Auth = autenticado()):
    """O mesmo resultado como camada de pontos (GeoJSON): um ponto por barra que tem nó com geometria,
    com corrente e veredito nas propriedades. Barra sem coordenada é contada em `barras_sem_coordenada`
    e não vira feição."""
    return await run_in_threadpool(_ler_sincrono, _uuid_ok(rede_id), nome, True, auth)
