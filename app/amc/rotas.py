"""Rotas do motor de análise multicritério — modelo, conjunto de unidades e execução (item
L3-01-a-modelo-dado; laco/decomposicao/L3L6_CONCEITO.md seção A). Privilégio `analise.amc` (já existe em
003_identidade_acesso.sql) para escrita; leitura é RLS puro (qualquer membro do inquilino lê o que existe).

Extração de fator, transformação e combinação (o que CALCULA favorabilidade) são os itens L3-01-c/d/e — aqui
a execução nasce no estado `registrada` e só congela proveniência (modelo+versão, pesos, camadas declaradas,
motor, semente). `amc_fator_bruto`/`amc_resultado` não têm rota de escrita nesta trilha (materializados pela
extração/combinação futura); a listagem de resultados já existe porque a explicabilidade é o contrato de API,
mesmo com a tabela vazia até esses itens rodarem."""

import json
import secrets

import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app import versao as versao_mod
from app.amc import esquema
from app.amc.modelos import (
    Conjunto,
    ConjuntoEntrada,
    ConjuntoPagina,
    Execucao,
    ExecucaoEntrada,
    ExecucaoPagina,
    Modelo,
    ModeloEditar,
    ModeloEntrada,
    ModeloPagina,
    ModeloValidado,
    ResultadoPagina,
    ValidarEntrada,
)
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento, uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/amc", tags=["amc"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCREVER = {"x-auth": "S/T", "x-privilegio": "analise.amc"}

# códigos de RAISE EXCEPTION dos gatilhos de 20260906T1900_amc_modelo.sql → (status, mensagem legível)
ERROS_AMC = {
    "amc_modelo_nao_apaga": (409, "modelo já executado nunca se apaga; crie outro modelo"),
    "amc_modelo_identidade_imutavel": (
        409, "modelo já executado: definição e hash não mudam mais; crie um modelo novo"),
    "amc_modelo_tenant_imutavel": (403, "operação fora do inquilino da sessão"),
    "amc_execucao_concluida_imutavel": (409, "execução concluída não se apaga"),
    "amc_execucao_proveniencia_imutavel": (409, "o que rodou não muda; só o estado avança"),
    "amc_execucao_tenant_incoerente": (422, "modelo e conjunto de unidades precisam ser do mesmo inquilino"),
    "amc_execucao_inexistente": (404, "execução inexistente"),
    "amc_materializado_imutavel": (409, "fator bruto e resultado não se editam; rode outra execução"),
}


def _erro_amc(e: Exception) -> ErroAPI:
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        if codigo in ERROS_AMC:
            status, mensagem = ERROS_AMC[codigo]
            return ErroAPI(status, codigo, mensagem)
    return auth_comum.erro_do_banco(e)


def _erro_validacao(definicao: dict) -> list[dict]:
    """As duas camadas (esquema/tipos.py já usa este padrão): estrutural primeiro; a semântica só roda
    quando a estrutura de `fatores` já é uma lista de objetos (senão os erros se confundem)."""
    erros = esquema.erros_estruturais(definicao)
    erros.extend(esquema.erros_semanticos(definicao))
    return erros


def _motor_versao() -> str:
    try:
        sha = versao_mod.git_sha_curto()
    except RuntimeError:
        sha = "semsha"
    return f"amc/1.0+{versao_mod.versao()}+{sha}"


def _modelo_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "nome": r["nome"], "definicao": r["definicao"], "versao_hash": r["versao_hash"],
        "executado": bool(r["executado"]), "criado_em": iso(r["criado_em"]), "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar_modelo(cur, mid: str) -> dict:
    cur.execute(
        "SELECT id, nome, definicao, versao_hash, executado, criado_em, atualizado_em "
        "FROM plat.amc_modelo WHERE id = %s",
        (mid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "modelo_inexistente", "modelo inexistente")
    return r


# ---------------------------------------------------------------- modelo
@router.post("/modelos/validar", response_model=ModeloValidado, openapi_extra=LER)
def validar(corpo: ValidarEntrada, auth: Auth = autenticado(escopo_token="amc:usar")):
    """Valida sem gravar (não toca o banco; qualquer membro autenticado pode conferir o próprio rascunho)."""
    erros = _erro_validacao(corpo.definicao)
    if erros:
        return {"valido": False, "versao_hash": None, "erros": erros}
    return {"valido": True, "versao_hash": esquema.hash_canonico(corpo.definicao), "erros": []}


@router.post("/modelos", response_model=Modelo, status_code=201, openapi_extra=ESCREVER)
def criar(corpo: ModeloEntrada, request: Request, auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    erros = _erro_validacao(corpo.definicao)
    if erros:
        raise ErroAPI(422, "modelo_invalido", "documento do modelo viola o esquema amc_modelo.v1", erros)
    versao_hash = esquema.hash_canonico(corpo.definicao)
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.amc_modelo(tenant_id, nome, definicao, versao_hash, criado_por, atualizado_por) "
                "VALUES (%s, %s, %s::jsonb, %s, %s, %s) RETURNING id",
                (auth.tenant_id, " ".join(corpo.nome.split()), _jsonb(corpo.definicao), versao_hash,
                 auth.usuario_id, auth.usuario_id),
            )
            mid = str(cur.fetchone()["id"])
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/modelo_criar", "amc_modelo", mid,
                         {"nome": corpo.nome, "versao_hash": versao_hash})
        return _modelo_json(_carregar_modelo(cur, mid))


@router.get("/modelos", response_model=ModeloPagina, openapi_extra=LER)
def listar_modelos(auth: Auth = autenticado(escopo_token="amc:usar")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_modelo")
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT id, nome, definicao, versao_hash, executado, criado_em, atualizado_em "
            "FROM plat.amc_modelo ORDER BY atualizado_em DESC LIMIT %s",
            (limites.PAGINA_MAX,),
        )
        itens = [_modelo_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/modelos/{id}", response_model=Modelo, openapi_extra=LER)
def ver_modelo(id: str, auth: Auth = autenticado(escopo_token="amc:usar")):
    mid = uuid_ok(id, "modelo_inexistente", "modelo inexistente")
    with db.db(auth.contexto()) as cur:
        return _modelo_json(_carregar_modelo(cur, mid))


@router.put("/modelos/{id}", response_model=Modelo, openapi_extra=ESCREVER)
def editar_modelo(id: str, corpo: ModeloEditar, request: Request,
                   auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    mid = uuid_ok(id, "modelo_inexistente", "modelo inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar_modelo(cur, mid)
        if corpo.definicao is not None and atual["executado"]:
            raise ErroAPI(409, "amc_modelo_identidade_imutavel",
                          "modelo já executado: definição e hash não mudam mais; crie um modelo novo")
        campos, params = [], []
        versao_hash = atual["versao_hash"]
        if corpo.nome is not None:
            campos.append("nome = %s")
            params.append(" ".join(corpo.nome.split()))
        if corpo.definicao is not None:
            erros = _erro_validacao(corpo.definicao)
            if erros:
                raise ErroAPI(422, "modelo_invalido", "documento do modelo viola o esquema amc_modelo.v1", erros)
            versao_hash = esquema.hash_canonico(corpo.definicao)
            campos.append("definicao = %s::jsonb")
            params.append(_jsonb(corpo.definicao))
            campos.append("versao_hash = %s")
            params.append(versao_hash)
        campos.append("atualizado_por = %s")
        params.append(auth.usuario_id)
        if campos:
            params.append(mid)
            try:
                cur.execute(f"UPDATE plat.amc_modelo SET {', '.join(campos)} WHERE id = %s", params)  # noqa: S608
            except psycopg2.Error as e:
                raise _erro_amc(e) from e
            registrar_evento(cur, request, "amc/modelo_editar", "amc_modelo", mid, {"versao_hash": versao_hash})
        return _modelo_json(_carregar_modelo(cur, mid))


@router.delete("/modelos/{id}", status_code=204, openapi_extra=ESCREVER)
def apagar_modelo(id: str, request: Request, auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    mid = uuid_ok(id, "modelo_inexistente", "modelo inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar_modelo(cur, mid)
        try:
            cur.execute("DELETE FROM plat.amc_modelo WHERE id = %s", (mid,))
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/modelo_apagar", "amc_modelo", mid, {"nome": atual["nome"]})


# ---------------------------------------------------------------- conjunto de unidades
def _conjunto_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "nome": r["nome"], "tipo": r["tipo"], "lado_m": r["lado_m"],
        "n_unidades": r["n_unidades"], "config": r["config"] or {}, "criado_em": iso(r["criado_em"]),
    }


def _carregar_conjunto(cur, cid: str) -> dict:
    cur.execute(
        "SELECT id, nome, tipo, lado_m, n_unidades, config, criado_em FROM plat.amc_conjunto_unidade WHERE id = %s",
        (cid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "conjunto_inexistente", "conjunto de unidades inexistente")
    return r


@router.post("/conjuntos", response_model=Conjunto, status_code=201, openapi_extra=ESCREVER)
def criar_conjunto(corpo: ConjuntoEntrada, request: Request,
                    auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.amc_conjunto_unidade(tenant_id, nome, tipo, lado_m, n_unidades, config, criado_por) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.tipo, corpo.lado_m, corpo.n_unidades,
                 _jsonb(corpo.config), auth.usuario_id),
            )
            cid = str(cur.fetchone()["id"])
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/conjunto_criar", "amc_conjunto_unidade", cid,
                         {"nome": corpo.nome, "tipo": corpo.tipo})
        return _conjunto_json(_carregar_conjunto(cur, cid))


@router.get("/conjuntos", response_model=ConjuntoPagina, openapi_extra=LER)
def listar_conjuntos(auth: Auth = autenticado(escopo_token="amc:usar")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.amc_conjunto_unidade")
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT id, nome, tipo, lado_m, n_unidades, config, criado_em FROM plat.amc_conjunto_unidade "
            "ORDER BY criado_em DESC LIMIT %s",
            (limites.PAGINA_MAX,),
        )
        itens = [_conjunto_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/conjuntos/{id}", response_model=Conjunto, openapi_extra=LER)
def ver_conjunto(id: str, auth: Auth = autenticado(escopo_token="amc:usar")):
    cid = uuid_ok(id, "conjunto_inexistente", "conjunto de unidades inexistente")
    with db.db(auth.contexto()) as cur:
        return _conjunto_json(_carregar_conjunto(cur, cid))


@router.delete("/conjuntos/{id}", status_code=204, openapi_extra=ESCREVER)
def apagar_conjunto(id: str, request: Request, auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    cid = uuid_ok(id, "conjunto_inexistente", "conjunto de unidades inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar_conjunto(cur, cid)
        try:
            cur.execute("DELETE FROM plat.amc_conjunto_unidade WHERE id = %s", (cid,))
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/conjunto_apagar", "amc_conjunto_unidade", cid, {"nome": atual["nome"]})


# ---------------------------------------------------------------- execução
def _execucao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "modelo_id": str(r["modelo_id"]), "modelo_versao_hash": r["modelo_versao_hash"],
        "conjunto_id": str(r["conjunto_id"]), "pesos": r["pesos"] or {}, "camadas": r["camadas"] or [],
        "motor_versao": r["motor_versao"], "semente": r["semente"], "estado": r["estado"],
        "criado_em": iso(r["criado_em"]), "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar_execucao(cur, eid: str) -> dict:
    cur.execute(
        "SELECT id, modelo_id, modelo_versao_hash, conjunto_id, pesos, camadas, motor_versao, semente, estado, "
        "criado_em, atualizado_em FROM plat.amc_execucao WHERE id = %s",
        (eid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
    return r


def _pesos_ok(pesos: dict, fatores_ids: set[str]) -> dict:
    """Pesos escolhidos pelo usuário para ESTA execução (nunca 'pesos medidos'): vazio = usa o peso
    declarado no modelo para cada fator; se vier preenchido, toda chave precisa ser um fator do modelo."""
    if not pesos:
        return {}
    desconhecidos = sorted(set(pesos) - fatores_ids)
    if desconhecidos:
        raise ErroAPI(422, "pesos_fator_desconhecido", f"pesos citam fator fora do modelo: {desconhecidos}",
                      {"desconhecidos": desconhecidos, "fatores_do_modelo": sorted(fatores_ids)})
    return pesos


@router.post("/execucoes", response_model=Execucao, status_code=201, openapi_extra=ESCREVER)
def criar_execucao(corpo: ExecucaoEntrada, request: Request,
                    auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    mid = uuid_ok(corpo.modelo_id, "modelo_inexistente", "modelo inexistente")
    cid = uuid_ok(corpo.conjunto_id, "conjunto_inexistente", "conjunto de unidades inexistente")
    with db.db(auth.contexto()) as cur:
        modelo = _carregar_modelo(cur, mid)
        _carregar_conjunto(cur, cid)  # 404 se não for do inquilino da sessão
        fatores_ids = {f["id"] for f in (modelo["definicao"].get("fatores") or []) if isinstance(f, dict) and "id" in f}
        pesos = _pesos_ok({k: v for k, v in corpo.pesos.items()}, fatores_ids)
        camadas = [c.model_dump() for c in corpo.camadas]
        semente = corpo.semente if corpo.semente is not None else secrets.randbits(62)
        try:
            cur.execute(
                "INSERT INTO plat.amc_execucao(tenant_id, modelo_id, modelo_versao_hash, conjunto_id, pesos, "
                "camadas, motor_versao, semente, criado_por) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s) RETURNING id",
                (auth.tenant_id, mid, modelo["versao_hash"], cid, _jsonb(pesos), _jsonb(camadas),
                 _motor_versao(), semente, auth.usuario_id),
            )
            eid = str(cur.fetchone()["id"])
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/execucao_criar", "amc_execucao", eid,
                         {"modelo_id": mid, "versao_hash": modelo["versao_hash"], "conjunto_id": cid,
                          "semente": semente})
        return _execucao_json(_carregar_execucao(cur, eid))


@router.get("/execucoes", response_model=ExecucaoPagina, openapi_extra=LER)
def listar_execucoes(modelo_id: str | None = None, auth: Auth = autenticado(escopo_token="amc:usar")):
    onde, params = ["true"], []
    if modelo_id:
        onde.append("modelo_id = %s")
        params.append(uuid_ok(modelo_id, "modelo_inexistente", "modelo inexistente"))
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.amc_execucao WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT id, modelo_id, modelo_versao_hash, conjunto_id, pesos, camadas, motor_versao, semente, "  # noqa: S608
            f"estado, criado_em, atualizado_em FROM plat.amc_execucao WHERE {filtro} "
            f"ORDER BY criado_em DESC LIMIT %s",
            (*params, limites.PAGINA_MAX),
        )
        itens = [_execucao_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/execucoes/{id}", response_model=Execucao, openapi_extra=LER)
def ver_execucao(id: str, auth: Auth = autenticado(escopo_token="amc:usar")):
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    with db.db(auth.contexto()) as cur:
        return _execucao_json(_carregar_execucao(cur, eid))


@router.delete("/execucoes/{id}", status_code=204, openapi_extra=ESCREVER)
def apagar_execucao(id: str, request: Request, auth: Auth = autenticado("analise.amc", escopo_token="amc:usar")):
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar_execucao(cur, eid)
        try:
            cur.execute("DELETE FROM plat.amc_execucao WHERE id = %s", (eid,))
        except psycopg2.Error as e:
            raise _erro_amc(e) from e
        registrar_evento(cur, request, "amc/execucao_apagar", "amc_execucao", eid, {"estado": atual["estado"]})


@router.get("/execucoes/{id}/resultados", response_model=ResultadoPagina, openapi_extra=LER)
def listar_resultados(id: str, auth: Auth = autenticado(escopo_token="amc:usar")):
    """Explicabilidade é o contrato (A9/A10): a tabela existe vazia até L3-01-d calcular; a rota já garante que
    A não lê resultado de execução de B (404 na execução-mãe barra tudo antes de tocar amc_resultado)."""
    eid = uuid_ok(id, "execucao_inexistente", "execução inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar_execucao(cur, eid)
        cur.execute("SELECT count(*) AS n FROM plat.amc_resultado WHERE execucao_id = %s", (eid,))
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT unidade_id, favorabilidade, vetado, motivo, cobertura FROM plat.amc_resultado "
            "WHERE execucao_id = %s ORDER BY unidade_id LIMIT %s",
            (eid, limites.PAGINA_MAX),
        )
        itens = [dict(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


def _jsonb(valor):
    return json.dumps(valor, ensure_ascii=False, default=str)
