"""Rotas da rede simples (item L4-18-rede-simples-trace-network).

`POST /api/rede/simples` cria a rede a partir de DUAS camadas do inquilino (uma de linhas, uma de pontos) em
uma única chamada: cria a rede, instala o catálogo mínimo, copia as feições, grava a configuração de direção
de fluxo e constrói a topologia. É essa chamada única que faz o "≤ 3 cliques" da tela: escolher a camada de
linhas, escolher a de pontos, clicar em criar.

`GET /api/rede/{rede_id}/simples` devolve a configuração (camadas de origem, campo de direção, mapa de
valores, atributos de rede declarados) e `POST /api/rede/{rede_id}/promover` promove a rede a rede de
utilidades, carimbando o pacote mínimo."""

import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import simples, topologia
from app.rede_utilidades.modelos import RedeSimplesEntrada

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — rede simples"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _criar_sincrono(corpo: RedeSimplesEntrada, auth: Auth, request: Request) -> dict:
    atributos_rede = simples.conferir_atributos_rede([a.model_dump() for a in corpo.atributos_rede])
    mapa = {str(k).strip().lower(): v for k, v in (corpo.mapa_direcao or {}).items()}
    for v in mapa.values():
        if v not in simples.DIRECOES:
            raise ErroAPI(422, "direcao_invalida",
                          f"o mapa de direção só aceita {simples.DIRECOES}; veio {v!r}")
    with db.db(auth.contexto()) as cur:
        camada_linha = simples.camada(cur, corpo.camada_linha_id, "linha")
        camada_ponto = simples.camada(cur, corpo.camada_ponto_id, "ponto")
        try:
            cur.execute(
                "INSERT INTO plat.rede(tenant_id, nome, disciplina, descricao, tolerancia_m, dono_id, modo) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'simples') RETURNING id",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.disciplina, corpo.descricao,
                 corpo.tolerancia_m, auth.usuario_id),
            )
            rede_id = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma rede com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e

        try:
            simples.instalar_catalogo_minimo(cur, auth.tenant_id, rede_id, auth.usuario_id,
                                             corpo.disciplina, corpo.nome)
            contagens = simples.carregar_camadas(cur, auth.tenant_id, rede_id, camada_linha, camada_ponto,
                                                 corpo.campo_direcao, mapa)
            simples.gravar_config(cur, auth.tenant_id, rede_id, camada_linha, camada_ponto,
                                  corpo.campo_direcao, mapa, atributos_rede)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e

        resumo = topologia.habilitar(cur, auth.tenant_id, rede_id, auth.usuario_id)
        registrar_evento(cur, request, "redes/simples_criar", "rede", rede_id, {
            "nome": corpo.nome, "camada_linha_id": corpo.camada_linha_id,
            "camada_ponto_id": corpo.camada_ponto_id, "campo_direcao": corpo.campo_direcao,
            "trechos": contagens["trechos"], "juncoes": contagens["juncoes"], "nos": resumo["nos"],
            "arestas": resumo["arestas"],
        })
        return {
            "rede_id": rede_id, "modo": "simples", "nome": corpo.nome,
            "camada_linha": {"id": camada_linha["id"], "titulo": camada_linha["titulo"]},
            "camada_ponto": ({"id": camada_ponto["id"], "titulo": camada_ponto["titulo"]}
                             if camada_ponto else None),
            "campo_direcao": corpo.campo_direcao, "mapa_direcao": mapa, "atributos_rede": atributos_rede,
            "feicoes": {"trechos": contagens["trechos"], "juncoes": contagens["juncoes"]},
            "topologia": {"nos": resumo["nos"], "arestas": resumo["arestas"],
                          "nos_orfaos": resumo["nos_orfaos"], "arestas_sem_no": resumo["arestas_sem_no"],
                          "duracao_ms": resumo["duracao_ms"]},
        }


@router.post("/simples", status_code=201, openapi_extra=EDITAR)
async def criar_rede_simples(corpo: RedeSimplesEntrada, request: Request,
                             auth: Auth = autenticado("rede.editar")):
    """Cria uma rede simples a partir de duas camadas do inquilino numa chamada só: rede + catálogo mínimo +
    feições copiadas + configuração de direção de fluxo + topologia construída. Tudo numa transação: se algo
    falhar, nenhuma rede pela metade fica no banco. Trabalho pesado (cópia e topologia) vai para o
    threadpool, para não segurar o laço de eventos da API inteira."""
    return await run_in_threadpool(_criar_sincrono, corpo, auth, request)


@router.get("/{rede_id}/simples", openapi_extra=LER)
def ver_config_simples(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT modo FROM plat.rede WHERE id = %s::uuid", (rid,))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
        cfg = simples.ler_config(cur, rid)
        if cfg is None:
            raise ErroAPI(404, "config_inexistente", "esta rede não nasceu como rede simples")
        return {**cfg, "modo": r["modo"], "criado_em": iso(cfg["criado_em"])}


def _promover_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        try:
            res = simples.promover(cur, auth.tenant_id, rid, auth.usuario_id)
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/simples_promover", "rede", rid,
                         {"codigo": res["codigo"], "versao": res["versao"], "sha256": res["sha256"]})
        return res


@router.post("/{rede_id}/promover", status_code=201, openapi_extra=EDITAR)
async def promover_rede_simples(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Promove a rede simples a rede de utilidades: grava o PACOTE MÍNIMO (o mesmo catálogo que ela já usava,
    agora validado pelo esquema do pacote, com sha256 e bytes) e muda o modo. A partir daí
    `GET /api/rede/{id}/pacote` devolve o pacote, e o inquilino pode importar por cima dele um pacote de
    ativos de verdade."""
    rid = _uuid_ok(rede_id)
    return await run_in_threadpool(_promover_sincrono, rid, auth, request)
