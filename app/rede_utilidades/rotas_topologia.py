"""Rotas de feições e topologia derivada da rede de utilidades (item L4-01-b-topologia-derivada; ADR 0020).

`POST /api/rede/{rede_id}/feicoes/pontos` e `.../linhas` gravam as camadas de rede (normais, editáveis) que a
topologia deriva. `POST /api/rede/{rede_id}/topologia/habilitar` reconstrói o índice inteiro (nunca incremental
nesta passagem — ver docs/rede/TOPOLOGIA.md); `GET .../topologia` devolve o resumo da última construção;
`GET .../topologia/nos` e `.../arestas` listam o resultado (paginação simples, sem filtro espacial ainda).

Mesmo padrão de `rotas.py`: escrita exige `rede.editar`; leitura segue a visibilidade por inquilino (RLS);
construção pesada vai para o threadpool (lição do achado A4 do item L4-01-a)."""

import json
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import feicoes, lacos, topologia, tracado
from app.rede_utilidades.modelos import (
    Feicao,
    FeicaoLinhaEntrada,
    FeicaoPontoEntrada,
    TopologiaResumo,
    TracadoEntrada,
)

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades — topologia"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
LISTA_LIMITE_MAX = 2000


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _rede_existe(cur, rede_id: str) -> None:
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


def _feicao_json(r: dict) -> dict:
    return {"id": str(r["id"]), "tipo_id": str(r["tipo_id"]), "fase_bitmask": r["fase_bitmask"],
            "atributos": r["atributos"], "criado_em": iso(r["criado_em"])}


@router.post("/{rede_id}/feicoes/pontos", response_model=Feicao, status_code=201, openapi_extra=EDITAR)
def criar_feicao_ponto(rede_id: str, corpo: FeicaoPontoEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = feicoes.criar_ponto(cur, auth.tenant_id, rid, corpo)
        registrar_evento(cur, request, "redes/feicao_criar", "rede", rid,
                         {"tipo": "ponto", "grupo": corpo.grupo, "tipo_codigo": corpo.tipo_codigo})
        return _feicao_json(r)


@router.post("/{rede_id}/feicoes/linhas", response_model=Feicao, status_code=201, openapi_extra=EDITAR)
def criar_feicao_linha(rede_id: str, corpo: FeicaoLinhaEntrada, request: Request,
                        auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        r = feicoes.criar_linha(cur, auth.tenant_id, rid, corpo)
        registrar_evento(cur, request, "redes/feicao_criar", "rede", rid,
                         {"tipo": "linha", "grupo": corpo.grupo, "tipo_codigo": corpo.tipo_codigo})
        return _feicao_json(r)


@router.get("/{rede_id}/feicoes/pontos", openapi_extra=LER)
def listar_feicoes_ponto(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = feicoes.listar_pontos(cur, rid, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": [_feicao_json(r) for r in itens]}


@router.get("/{rede_id}/feicoes/linhas", openapi_extra=LER)
def listar_feicoes_linha(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        itens = feicoes.listar_linhas(cur, rid, min(limite, LISTA_LIMITE_MAX))
        return {"total": len(itens), "itens": [_feicao_json(r) for r in itens]}


@router.post("/{rede_id}/feicoes/pontos/applyEdits", status_code=200, openapi_extra=EDITAR)
async def aplicar_edicoes_ponto(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """applyEdits da camada de dispositivos (paridade FeatureServer): `adds`/`updates`/`deletes` numa chamada,
    geometria no JSON da Esri (`{"x":..,"y":..}`), resultado por feição. Cada feição gravada marca a área
    suja correspondente se a topologia já foi construída (refutação do item L4-01-b)."""
    rid = _uuid_ok(rede_id)
    corpo = await request.json()
    return await run_in_threadpool(_apply_edits_sincrono, rid, corpo, "ponto", auth, request)


@router.post("/{rede_id}/feicoes/linhas/applyEdits", status_code=200, openapi_extra=EDITAR)
async def aplicar_edicoes_linha(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """applyEdits da camada de trechos: geometria `{"paths": [[[lon, lat], ...]]}` (um caminho por feição)."""
    rid = _uuid_ok(rede_id)
    corpo = await request.json()
    return await run_in_threadpool(_apply_edits_sincrono, rid, corpo, "linha", auth, request)


def _apply_edits_sincrono(rid: str, corpo: dict, geometria: str, auth: Auth, request: Request) -> dict:
    if not isinstance(corpo, dict) or not any(k in corpo for k in ("adds", "updates", "deletes")):
        raise ErroAPI(422, "pedido_invalido", "o corpo exige ao menos uma das chaves adds/updates/deletes")
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        res = feicoes.aplicar_edicoes(cur, auth.tenant_id, rid, corpo, geometria)
        n_ok = sum(1 for k in ("addResults", "updateResults", "deleteResults")
                   for i in res[k] if i["success"])
        n_erro = sum(1 for k in ("addResults", "updateResults", "deleteResults")
                     for i in res[k] if not i["success"])
        registrar_evento(cur, request, "redes/feicao_editar", "rede", rid,
                         {"camada": geometria, "gravadas": n_ok, "recusadas": n_erro})
    return res


def _habilitar_sincrono(rid: str, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        try:
            resumo = topologia.habilitar(cur, auth.tenant_id, rid, auth.usuario_id)
        except LookupError as e:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e
        except Exception as e:  # noqa: BLE001 — erro do banco vira mensagem legível, nunca 500 cru
            import psycopg2

            if isinstance(e, psycopg2.Error):
                raise auth_comum.erro_do_banco(e) from e
            raise
        registrar_evento(cur, request, "redes/topologia_habilitar", "rede", rid, resumo)
    return resumo


@router.post("/{rede_id}/topologia/habilitar", response_model=TopologiaResumo, status_code=201,
             openapi_extra=EDITAR)
async def habilitar_topologia(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma."""
    rid = _uuid_ok(rede_id)
    resumo = await run_in_threadpool(_habilitar_sincrono, rid, auth, request)
    return {**resumo, "construido_em": iso(resumo["construido_em"])}


@router.get("/{rede_id}/topologia", response_model=TopologiaResumo, openapi_extra=LER)
def ver_resumo_topologia(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT rede_id, tolerancia_m, nos, arestas, nos_orfaos, arestas_sem_no, duracao_ms, construido_em "
            "FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rid,),
        )
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "topologia_inexistente", "esta rede ainda não teve a topologia habilitada")
        return {
            "rede_id": str(r["rede_id"]), "tolerancia_m": float(r["tolerancia_m"]), "nos": r["nos"],
            "arestas": r["arestas"], "nos_orfaos": r["nos_orfaos"], "arestas_sem_no": r["arestas_sem_no"],
            "duracao_ms": r["duracao_ms"], "construido_em": iso(r["construido_em"]),
        }


@router.get("/{rede_id}/topologia/nos", openapi_extra=LER)
def listar_nos(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT n.id, n.papel, n.tipo_id, n.origem_id, n.terminal_num, ST_X(n.geom) AS lon, "
            "ST_Y(n.geom) AS lat, "
            "(SELECT count(*) FROM plat.rede_topo_aresta a "
            " WHERE a.no_origem_id = n.id OR a.no_destino_id = n.id) AS grau "
            "FROM plat.rede_topo_no n WHERE n.rede_id = %s::uuid ORDER BY n.criado_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "papel": r["papel"], "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
             "origem_id": str(r["origem_id"]) if r["origem_id"] else None, "terminal_num": r["terminal_num"],
             "grau": r["grau"], "lon": r["lon"], "lat": r["lat"]}
            for r in cur.fetchall()
        ]
        return {"total": len(itens), "itens": itens}


@router.get("/{rede_id}/topologia/arestas", openapi_extra=LER)
def listar_arestas(rede_id: str, limite: int = 200, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute(
            "SELECT id, grupo_id, tipo_id, origem_id, no_origem_id, no_destino_id, comprimento_m, "
            "fase_bitmask, atributos FROM plat.rede_topo_aresta WHERE rede_id = %s::uuid "
            "ORDER BY criado_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "grupo_id": str(r["grupo_id"]), "tipo_id": str(r["tipo_id"]) if r["tipo_id"] else None,
             "origem_id": str(r["origem_id"]), "no_origem_id": str(r["no_origem_id"]) if r["no_origem_id"] else None,
             "no_destino_id": str(r["no_destino_id"]) if r["no_destino_id"] else None,
             "comprimento_m": r["comprimento_m"], "fase_bitmask": r["fase_bitmask"], "atributos": r["atributos"]}
            for r in cur.fetchall()
        ]
        return {"total": len(itens), "itens": itens}


# --- área suja e traçado mínimo (refutação do item) ---------------------------------------------------------

@router.get("/{rede_id}/topologia/areas-sujas", openapi_extra=LER)
def listar_areas_sujas(rede_id: str, limite: int = 200,
                       auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """As áreas sujas abertas da rede: onde uma edição (applyEdits ou criação simples) passou DEPOIS da última
    construção da topologia e o índice gravado é, portanto, suspeito. `habilitar` as apaga ao reconstruir."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute("SELECT count(*) AS n FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid", (rid,))
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT id, motivo, feicao_id, criado_em, ST_AsGeoJSON(geom) AS geojson "
            "FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid ORDER BY criado_em LIMIT %s",
            (rid, min(limite, LISTA_LIMITE_MAX)),
        )
        itens = [
            {"id": str(r["id"]), "motivo": r["motivo"],
             "feicao_id": str(r["feicao_id"]) if r["feicao_id"] else None,
             "criado_em": iso(r["criado_em"]), "geometria": json.loads(r["geojson"])}
            for r in cur.fetchall()
        ]
        return {"total": total, "itens": itens}


def _alcance_sincrono(rid: str, no_id: str, auth: Auth) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        cur.execute("SELECT 1 FROM plat.rede_topo_no WHERE id = %s::uuid AND rede_id = %s::uuid",
                    (no_id, rid))
        if cur.fetchone() is None:
            raise ErroAPI(404, "no_inexistente", "este nó não existe na topologia desta rede")
        # varredura de conectividade pura (o "traçado" desta passagem): tudo o que se alcança do nó andando
        # pelas arestas, nos dois sentidos, sem regra de fluxo nem estado de chave (isso é o item seguinte
        # da linha L4 — fronteira honesta, docs/rede/TOPOLOGIA.md seção 6). UNION (não ALL) sobre o id da
        # aresta é o que garante a parada em grafo com ciclo.
        cur.execute(
            "WITH RECURSIVE alc(aresta_id, no_a, no_b) AS ("
            "  SELECT a.id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
            "  WHERE a.rede_id = %s::uuid AND %s::uuid IN (a.no_origem_id, a.no_destino_id)"
            "  UNION"
            "  SELECT a.id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
            "  JOIN alc ON a.rede_id = %s::uuid "
            "   AND (a.no_origem_id IN (alc.no_a, alc.no_b) OR a.no_destino_id IN (alc.no_a, alc.no_b))"
            ") SELECT count(*) AS arestas, "
            "  (SELECT count(*) FROM (SELECT no_a FROM alc UNION SELECT no_b FROM alc) n) AS nos "
            "FROM alc",
            (rid, no_id, rid),
        )
        r = cur.fetchone()
        cur.execute(
            "SELECT count(*) AS n FROM plat.rede_topo_area_suja WHERE rede_id = %s::uuid", (rid,))
        areas_sujas = cur.fetchone()["n"]
        # o traçado atravessa área suja se alguma aresta alcançada toca o polígono de uma área aberta:
        # nesse caso o resultado acima é calculado sobre índice POSSIVELMENTE velho e não é confiável.
        cur.execute(
            "WITH RECURSIVE alc(aresta_id, no_a, no_b) AS ("
            "  SELECT a.id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
            "  WHERE a.rede_id = %s::uuid AND %s::uuid IN (a.no_origem_id, a.no_destino_id)"
            "  UNION"
            "  SELECT a.id, a.no_origem_id, a.no_destino_id FROM plat.rede_topo_aresta a "
            "  JOIN alc ON a.rede_id = %s::uuid "
            "   AND (a.no_origem_id IN (alc.no_a, alc.no_b) OR a.no_destino_id IN (alc.no_a, alc.no_b))"
            ") SELECT EXISTS ("
            "  SELECT 1 FROM plat.rede_topo_aresta a JOIN plat.rede_topo_area_suja s "
            "   ON s.rede_id = a.rede_id AND ST_Intersects(s.geom, a.geom) "
            "  WHERE a.id IN (SELECT aresta_id FROM alc)) AS atravessa",
            (rid, no_id, rid),
        )
        atravessa = cur.fetchone()["atravessa"]
        return {
            "no_inicio": no_id, "nos_alcancados": r["nos"], "arestas_alcancadas": r["arestas"],
            "areas_sujas_abertas": areas_sujas, "atravessa_area_suja": atravessa,
        }


@router.get("/{rede_id}/topologia/alcance", openapi_extra=LER)
async def alcance(rede_id: str, no: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Traçado mínimo de conectividade: o conjunto de nós/arestas alcançáveis a partir de `no`. Sem regra de
    fluxo (montante/jusante) nem estado de chave — isso é o item seguinte da linha L4."""
    rid = _uuid_ok(rede_id)
    nid = _uuid_ok_no(no)
    return await run_in_threadpool(_alcance_sincrono, rid, nid, auth)


def _uuid_ok_no(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "no_inexistente", "nó inexistente") from e


# --- traçado: conectado, subrede (L4-02-a), laços, caminho_curto, isolados (L4-02-d) --------------------

def _tracar_sincrono(rid: str, corpo: TracadoEntrada, auth: Auth, request: Request) -> dict:
    with db.db(auth.contexto()) as cur:
        _rede_existe(cur, rid)
        barreiras = [b.model_dump() for b in corpo.barreiras]
        try:
            if corpo.tipo in tracado.TIPOS_TRACADO:
                resultado = tracado.tracar(
                    cur, auth.tenant_id, rid, corpo.tipo,
                    [p.model_dump() for p in corpo.pontos_partida], barreiras,
                )
            elif corpo.tipo == "lacos":
                resultado = lacos.detectar_lacos(cur, auth.tenant_id, rid, barreiras)
            elif corpo.tipo == "isolados":
                resultado = lacos.isolados(cur, auth.tenant_id, rid, corpo.categoria_controlador, barreiras)
            elif corpo.tipo == "caminho_curto":
                if len(corpo.pontos_partida) != 1:
                    raise ErroAPI(422, "origem_invalida",
                                  "caminho_curto exige exatamente um ponto em pontos_partida (a origem)")
                if corpo.destino is None:
                    raise ErroAPI(422, "destino_obrigatorio", "caminho_curto exige o campo 'destino'")
                resultado = lacos.caminho_curto(
                    cur, auth.tenant_id, rid, corpo.pontos_partida[0].model_dump(),
                    corpo.destino.model_dump(), corpo.atributo_custo, corpo.k, barreiras,
                )
            else:  # nunca alcançado — o pattern do pydantic já barrou; guarda por clareza
                raise ErroAPI(422, "tipo_invalido", f"tipo desconhecido: {corpo.tipo}")
        except psycopg2.Error as e:  # noqa: BLE001 — erro do banco vira mensagem legível, nunca 500 cru
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/tracar", "rede", rid,
                         {"tipo": corpo.tipo, "contagem": resultado.get("contagem"),
                          "duracao_ms": resultado.get("duracao_ms")})
    return resultado


@router.post("/{rede_id}/tracar", status_code=200, openapi_extra=LER)
async def tracar_rede(rede_id: str, corpo: TracadoEntrada, request: Request,
                      auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Traça `tipo=conectado` (tudo que se alcança do(s) ponto(s) de partida, respeitando a traversabilidade
    de cada dispositivo e as barreiras) ou `tipo=subrede` (o mesmo, mas parando em qualquer controlador de
    outra subrede — hoje, categoria `transformacao` do pacote); ou, item L4-02-d-lacos-e-caminho-curto:
    `tipo=lacos` (ciclos por componente biconexo, `pgr_biconnectedComponents`), `tipo=isolados` (elementos sem
    caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`, `pgr_connectedComponents`)
    ou `tipo=caminho_curto` (origem em `pontos_partida[0]`, `destino`, custo = `atributo_custo` ou o
    comprimento geodésico por padrão; `k` alternativas por `pgr_ksp` quando `k>1`). Ponto de partida, destino
    e barreira são a mesma forma: feição+terminal ou coordenada com tolerância. Não exige `rede.editar`: é
    leitura sobre o índice já construído (mesmo privilégio de `topologia/alcance`), nunca grava nada na rede.
    Sem `response_model` fixo porque cada `tipo` devolve um formato diferente (ver `docs/openapi.json` para o
    formato de cada um, e os testes de cada item para exemplo)."""
    rid = _uuid_ok(rede_id)
    resultado = await run_in_threadpool(_tracar_sincrono, rid, corpo, auth, request)
    return resultado
